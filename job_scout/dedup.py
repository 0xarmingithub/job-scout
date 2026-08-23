"""
dedup.py — Remember every job you have already seen, so you see it once.

Two different jobs are done here.

1. Cross-source dedup, within a single run. The same advert is often indexed by
   LinkedIn, Indeed and an aggregator at the same time. dedup_by_content() keeps
   one copy: the one from the highest-priority board, breaking ties by whichever
   copy has the longest description, because the scorer reads that description.

2. Across-run dedup. Every job ever fetched, including the ones that scored
   badly, is written to a SQLite table so it never reaches the scorer again.
   That is what keeps the daily model bill near zero after the first week.

The store is a single file, jobs.db, in your data directory.
"""

import hashlib
import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# Lower number = higher priority when the same job is found on several boards.
# Anything not listed sorts last, which is the right default for a source
# someone added themselves.
DEFAULT_SITE_PRIORITY: dict[str, int] = {
    "linkedin": 0,
    "indeed": 1,
    "glassdoor": 2,
    "zip_recruiter": 3,
    "careerjet": 4,
    "apify": 5,
    "jobindex": 6,
}

_UNKNOWN_SITE_PRIORITY = 99

# How far back the title+company check looks. Long enough to catch an aggregator
# re-issuing the same advert under a fresh tracking URL; short enough that a
# genuinely re-opened role is not suppressed forever.
_CONTENT_LOOKBACK_DAYS = 7


def make_job_id(url: str) -> str:
    """Stable 16-character id derived from the job URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class JobStore:
    """The seen-jobs table. One instance per run."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id      TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                title       TEXT,
                company     TEXT,
                location    TEXT,
                site        TEXT,
                score       REAL,
                status      TEXT DEFAULT 'new',
                first_seen  TEXT,
                date_posted TEXT,
                search_term TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_jobs_first_seen "
            "ON seen_jobs (first_seen)"
        )
        conn.commit()
        return conn

    def filter_new(self, jobs: list[dict]) -> list[dict]:
        """
        Return only the jobs this store has not seen before.

        Two checks. The URL check is exact and always runs. The title+company
        check catches the same advert re-posted under a new URL, and only looks
        at the last 7 days.
        """
        if not jobs:
            return []

        ids = [make_job_id(job["url"]) for job in jobs]
        conn = self._conn()
        try:
            placeholders = ",".join("?" * len(ids))
            already_seen_ids = {
                row[0]
                for row in conn.execute(
                    f"SELECT job_id FROM seen_jobs WHERE job_id IN ({placeholders})",
                    ids,
                )
            }
            already_seen_content = {
                (row[0].lower().strip(), row[1].lower().strip())
                for row in conn.execute(
                    "SELECT title, company FROM seen_jobs "
                    "WHERE date(first_seen) >= date('now', ?)",
                    (f"-{_CONTENT_LOOKBACK_DAYS} days",),
                )
                if row[0] and row[1]
            }
        finally:
            conn.close()

        new_jobs: list[dict] = []
        skipped_url = 0
        skipped_content = 0
        for job, job_id in zip(jobs, ids):
            if job_id in already_seen_ids:
                skipped_url += 1
                continue
            content_key = (
                (job.get("title") or "").lower().strip(),
                (job.get("company") or "").lower().strip(),
            )
            if all(content_key) and content_key in already_seen_content:
                skipped_content += 1
                continue
            new_jobs.append(job)

        logger.info(
            "Dedup: %d raw -> %d new (skipped %d by URL, %d by title+company)",
            len(jobs), len(new_jobs), skipped_url, skipped_content,
        )
        return new_jobs

    def mark_seen(self, jobs: list[dict]) -> None:
        """
        Record every processed job, the rejected ones included, so tomorrow's
        run neither re-fetches nor re-scores them.
        """
        if not jobs:
            return

        today = date.today().isoformat()
        conn = self._conn()
        try:
            conn.executemany(
                """
                INSERT OR IGNORE INTO seen_jobs
                    (job_id, url, title, company, location, site,
                     score, status, first_seen, date_posted, search_term)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        make_job_id(job["url"]),
                        job.get("url", ""),
                        job.get("title", ""),
                        job.get("company", ""),
                        job.get("location", ""),
                        job.get("site", ""),
                        job.get("score"),
                        job.get("status", "new"),
                        today,
                        job.get("date_posted", ""),
                        job.get("search_term", ""),
                    )
                    for job in jobs
                ],
            )
            conn.commit()
            logger.info("Recorded %d jobs as seen", len(jobs))
        finally:
            conn.close()

    def count(self) -> int:
        """How many jobs the store holds. Used by `job-scout check`."""
        conn = self._conn()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0])
        finally:
            conn.close()


# ─── Cross-source duplicate removal ───────────────────────────────────────────

def dedup_by_content(
    jobs: list[dict],
    site_priority: dict[str, int] | None = None,
) -> list[dict]:
    """
    Remove duplicates within one run, where the same advert came from several
    boards. Keeps one copy per (normalised title, normalised company) pair:

      1. Highest site priority.
      2. If tied, the longer description — the scorer reads it.
      3. If still tied, whichever came first.

    Never modifies the input; returns a new list.
    """
    if not jobs:
        return []

    priority = site_priority or DEFAULT_SITE_PRIORITY
    best: dict[str, dict] = {}

    for job in jobs:
        key = content_key(job)
        if not key:
            # No title or no company means no reliable key — always keep it.
            continue
        if key not in best or _is_better(job, best[key], priority):
            best[key] = job

    result: list[dict] = []
    emitted: set[str] = set()

    for job in jobs:
        key = content_key(job)
        if not key:
            result.append(job)
            continue
        if key in emitted:
            continue
        if best[key] is job:
            result.append(job)
            emitted.add(key)

    removed = len(jobs) - len(result)
    if removed:
        logger.info(
            "Cross-source dedup: %d raw -> %d unique (removed %d duplicates)",
            len(jobs), len(result), removed,
        )
    return result


def content_key(job: dict) -> str:
    """Normalised 'title|company' string used as the duplicate key."""
    title = _norm(job.get("title") or "")
    company = _norm(job.get("company") or "")
    if not title or not company:
        return ""
    return f"{title}|{company}"


def _norm(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_better(candidate: dict, existing: dict, priority: dict[str, int]) -> bool:
    """True if candidate should replace existing as the copy we keep."""
    candidate_rank = priority.get(candidate.get("site") or "", _UNKNOWN_SITE_PRIORITY)
    existing_rank = priority.get(existing.get("site") or "", _UNKNOWN_SITE_PRIORITY)
    if candidate_rank != existing_rank:
        return candidate_rank < existing_rank
    return len(candidate.get("description") or "") > len(existing.get("description") or "")
