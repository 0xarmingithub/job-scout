"""
dedup.py. Remember every job you have already seen, so you see it once.

Two different jobs are done here.

1. Cross-source dedup, within a single run. The same advert is often indexed by
   LinkedIn, Indeed and an aggregator at the same time. dedup_by_content() keeps
   one copy: the one from the highest-priority board, breaking ties by whichever
   copy has the longest description, because the scorer reads that description.

2. Across-run dedup. Every job ever fetched, including the ones that scored
   badly, is written to a SQLite table so it never reaches the scorer again.
   That is what keeps the daily model bill near zero after the first week.
   The one exception is a posting that failed to score: it is tried again on
   the next runs, up to `error_retries` times, then given up on.

The store is a single file, jobs.db, in your data directory.
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .normalize import (
    company_key,
    description_head,
    jaccard,
    shingles,
    title_words,
)
from .normalize import (
    content_key as advert_key,
)

logger = logging.getLogger(__name__)

# Two postings from the same company count as one advert when their titles
# share at least this share of words. Set high on purpose: "Solution Architect"
# and "Solution Architect IoT" must stay two jobs.
_NEAR_TITLE_JACCARD = 0.8
# Two descriptions count as one advert when they share this share of 3-word runs.
_NEAR_DESCRIPTION_JACCARD = 0.6

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

# How many later runs a posting that failed to score is tried again on.
_ERROR_RETRIES = 3


def make_job_id(url: str) -> str:
    """Stable 16-character id derived from the job URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _verdict_json(job: dict) -> str:
    """
    The scorer's reasoning, stored so a later command can explain a score
    without re-scoring the posting. Empty string when there is nothing to keep,
    which is every rejected job: they never reach the model.
    """
    verdict = job.get("verdict") or {}
    if not verdict:
        return ""
    try:
        return json.dumps(verdict, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


class KnownJobs:
    """
    What the store holds, read once per run, so the checks do not each query the
    database. add() lets a job accepted in this batch count against the next ones.
    """

    def __init__(self, url_ids, content_keys, by_company):
        self.url_ids: set[str] = set(url_ids)
        self.content_keys: set[str] = set(content_keys)
        # company key -> [(title words, description shingles), ...]
        self.by_company: dict[str, list] = by_company

    def known_by(self, job: dict) -> str:
        """"url" or "content" when the job is already known exactly, else ""."""
        url = job.get("url") or ""
        if url and make_job_id(url) in self.url_ids:
            return "url"
        key = advert_key(job.get("title"), job.get("company"))
        if key and key in self.content_keys:
            return "content"
        return ""

    def near_duplicate(self, job: dict) -> str:
        """Why the job is a near-copy of a known one from the same company, or "" if it is not."""
        company = company_key(job.get("company"))
        if not company:
            return ""
        words = title_words(job.get("title"))
        desc = shingles(description_head(job.get("description") or ""))
        for known_words, known_desc in self.by_company.get(company, ()):
            if len(words) >= 2 and len(known_words) >= 2:
                if jaccard(words, known_words) >= _NEAR_TITLE_JACCARD:
                    return "similar title"
            if desc and known_desc and jaccard(desc, known_desc) >= _NEAR_DESCRIPTION_JACCARD:
                return "similar description"
        return ""

    def add(self, job: dict) -> None:
        self.url_ids.add(make_job_id(job.get("url") or ""))
        key = advert_key(job.get("title"), job.get("company"))
        if key:
            self.content_keys.add(key)
        company = company_key(job.get("company"))
        if company and job.get("title"):
            desc = shingles(description_head(job.get("description") or ""))
            self.by_company.setdefault(company, []).append((title_words(job.get("title")), desc))


class JobStore:
    """The seen-jobs table. One instance per run."""

    def __init__(
        self,
        db_path: Path,
        lookback_days: int = _CONTENT_LOOKBACK_DAYS,
        error_retries: int = _ERROR_RETRIES,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # How far back the title-and-company check looks. Set it with
        # `advanced.seen_lookback_days` in config.yaml.
        self.lookback_days = max(0, int(lookback_days))
        # How many more runs a `scoring_error` posting gets. Set it with
        # `advanced.scoring_error_retries` in config.yaml.
        self.error_retries = max(0, int(error_retries))

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
                search_term TEXT,
                verdict_json TEXT,
                attempts    INTEGER DEFAULT 1
            )
            """
        )
        # verdict_json arrived after 1.0.0. A database created before it exists
        # and holds real history, so add the column in place. Nobody should have
        # to delete a year of seen jobs to take an upgrade.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
        if "verdict_json" not in columns:
            conn.execute("ALTER TABLE seen_jobs ADD COLUMN verdict_json TEXT")
        # attempts arrived in 1.5.0. Existing rows count as one attempt, so a
        # posting that failed before the upgrade gets its retries too.
        if "attempts" not in columns:
            conn.execute("ALTER TABLE seen_jobs ADD COLUMN attempts INTEGER DEFAULT 1")
        # desc_head arrived in 1.6.0: the start of the description, normalized, so a
        # later board's copy of the same advert can be recognised. Rows from before
        # have none, and only the title rule applies to them.
        if "desc_head" not in columns:
            conn.execute("ALTER TABLE seen_jobs ADD COLUMN desc_head TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_jobs_first_seen "
            "ON seen_jobs (first_seen)"
        )
        conn.commit()
        return conn

    def connect(self) -> sqlite3.Connection:
        """
        An open connection with the schema up to date.

        Public because `job-scout roundup` reads this same table and should
        not have to know how to migrate it first.
        """
        return self._conn()

    def snapshot(self) -> "KnownJobs":
        """
        Read what the store holds, once. URLs are kept for the whole history.
        Titles, companies and descriptions are kept for the lookback window,
        because only those are compared fuzzily.
        """
        cutoff = (date.today() - timedelta(days=self.lookback_days)).isoformat()
        conn = self._conn()
        try:
            settled = "NOT (status = 'scoring_error' AND COALESCE(attempts, 1) <= ?)"
            rows = conn.execute(
                "SELECT job_id, title, company, desc_head, first_seen FROM seen_jobs "
                f"WHERE {settled}",
                (self.error_retries,),
            ).fetchall()
        finally:
            conn.close()

        url_ids = set()
        content_keys = set()
        by_company: dict[str, list] = {}
        for job_id, title, company, desc_head, first_seen in rows:
            url_ids.add(job_id)
            if (first_seen or "") < cutoff:
                continue
            key = advert_key(title, company)
            if key:
                content_keys.add(key)
            company_name = company_key(company)
            if company_name and title:
                by_company.setdefault(company_name, []).append(
                    (title_words(title), shingles(desc_head or ""))
                )
        return KnownJobs(url_ids, content_keys, by_company)

    def filter_new(self, jobs: list[dict]) -> list[dict]:
        """
        Return only the jobs this store has not seen before, and not repeats of
        them from another board or on another day.

        Four checks, cheapest first:
          1. The same URL. Exact.
          2. The same title and company after normalizing spelling, within the
             lookback window. "Contoso Denmark A/S" matches "Contoso".
          3. The same company with a near-identical title (word overlap of at
             least _NEAR_TITLE_JACCARD).
          4. The same company with a near-identical description, where both
             descriptions are known (_NEAR_DESCRIPTION_JACCARD).

        Checks 3 and 4 only look at postings from the same company, so they stay
        cheap. A job accepted earlier in this batch counts against later ones.

        A posting recorded as `scoring_error` counts as unseen until it has used
        up its retries, so a timeout does not lose it for good.
        """
        if not jobs:
            return []

        known = self.snapshot()
        new_jobs: list[dict] = []
        skipped_url = skipped_content = skipped_near = 0
        for job in jobs:
            reason = known.known_by(job)
            if reason == "url":
                skipped_url += 1
                continue
            if reason == "content":
                skipped_content += 1
                continue
            near = known.near_duplicate(job)
            if near:
                skipped_near += 1
                logger.info(
                    "Near-duplicate skipped (%s): %s at %s",
                    near, job.get("title", ""), job.get("company", ""),
                )
                continue
            known.add(job)
            new_jobs.append(job)

        logger.info(
            "Dedup: %d raw -> %d new (skipped %d by URL, %d by title+company, %d near-duplicate)",
            len(jobs), len(new_jobs), skipped_url, skipped_content, skipped_near,
        )
        return new_jobs

    def mark_seen(self, jobs: list[dict]) -> None:
        """
        Record every processed job, the rejected ones included, so tomorrow's
        run neither re-fetches nor re-scores them.

        A job already recorded as `scoring_error` is updated in place: its new
        score and status replace the error, and its attempt count goes up. Any
        other existing row is left alone.
        """
        if not jobs:
            return

        today = date.today().isoformat()
        conn = self._conn()
        try:
            conn.executemany(
                """
                INSERT INTO seen_jobs
                    (job_id, url, title, company, location, site,
                     score, status, first_seen, date_posted, search_term,
                     verdict_json, desc_head)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    score = excluded.score,
                    status = excluded.status,
                    verdict_json = excluded.verdict_json,
                    attempts = COALESCE(seen_jobs.attempts, 1) + 1
                WHERE seen_jobs.status = 'scoring_error'
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
                        _verdict_json(job),
                        description_head(job.get("description") or ""),
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
      2. If tied, the longer description, because that is what the scorer reads.
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
            # No title or no company means no reliable key. Always keep it.
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
