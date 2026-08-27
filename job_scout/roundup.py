"""
roundup.py: the week in one message.

A daily digest answers "is there anything today". It is bad at "what did I
actually see this week", because by Friday the good Monday posting is four
notifications up the chat and effectively gone.

The roundup re-reads the seen-jobs database. It never re-scores anything, so it
costs nothing and can be run as often as you like:

    job-scout roundup               the last 7 days, best 10
    job-scout roundup --days 5      Monday to Friday, when run on a Friday
    job-scout roundup --dry-run     print it, send nothing

It only shows postings that already cleared your threshold on the day they were
found. Nothing is re-judged, so a roundup can never contradict the digest you
were sent at the time.
"""

import json
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .dedup import JobStore
from .notifiers.base import RunStats

logger = logging.getLogger(__name__)


def window(days: int, today: date | None = None) -> tuple[date, date]:
    """
    The inclusive date range a roundup covers.

    `days` counts today, so --days 5 on a Friday is Monday to Friday. That is
    the case worth getting right: a weekly roundup is nearly always a working
    week seen from its last day.
    """
    end = today or date.today()
    return end - timedelta(days=max(1, days) - 1), end


def collect(
    db_path: Path,
    threshold: int = 65,
    days: int = 7,
    top: int = 10,
    today: date | None = None,
) -> tuple[list[dict], int]:
    """
    The best postings in the window, highest score first.

    Returns (jobs, total). `total` is how many cleared the threshold before the
    top-N cut, because "top 10 of 23" and "10 matches" mean different things and
    a roundup that silently drops 13 postings reads as a quiet week.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return [], 0

    start, end = window(days, today)
    # Through JobStore, so an old database gets its verdict_json column added
    # rather than failing the query.
    conn = JobStore(db_path).connect()
    try:
        rows = conn.execute(
            "SELECT title, company, location, site, score, url, verdict_json "
            "FROM seen_jobs "
            "WHERE status = 'new' AND score IS NOT NULL AND score >= ? "
            "AND date(first_seen) BETWEEN date(?) AND date(?) "
            "ORDER BY score DESC, company ASC",
            (threshold, start.isoformat(), end.isoformat()),
        ).fetchall()
    except sqlite3.Error as exc:
        # A roundup is a convenience. It must never be the thing that breaks.
        logger.warning("Could not read %s for the roundup: %s", db_path, exc)
        return [], 0
    finally:
        conn.close()

    jobs = [_row_to_job(row) for row in rows]
    return jobs[: max(1, top)], len(jobs)


def stats_for(
    jobs: list[dict],
    total: int,
    threshold: int,
    days: int,
    strong_at: int = 80,
    possible_at: int = 65,
    today: date | None = None,
) -> RunStats:
    """The header and the nothing-matched text for one roundup."""
    start, end = window(days, today)
    span = f"{start.strftime('%d %b')} to {end.strftime('%d %b %Y')}"
    shown = len(jobs)
    counted = (
        f"best {shown} of {total} matches"
        if total > shown
        else f"{shown} match{'' if shown == 1 else 'es'}"
    )
    return RunStats(
        threshold=threshold,
        strong_at=strong_at,
        possible_at=possible_at,
        total_new=total,
        title=f"Job Scout roundup, {span}",
        subtitle=f"{counted} at or above {threshold}",
        empty_message=(
            f"Nothing reached {threshold} from {span}.\n"
            f"That is a quiet week rather than a broken scout: the daily runs "
            f"still recorded everything they saw.\n"
            f"Check with: job-scout stats"
        ),
    )


def _row_to_job(row: tuple) -> dict:
    """One database row in the shape every notifier already knows how to print."""
    title, company, location, site, score, url, verdict_json = row
    verdict: dict = {}
    if verdict_json:
        try:
            loaded = json.loads(verdict_json)
            verdict = loaded if isinstance(loaded, dict) else {}
        except (TypeError, ValueError):
            verdict = {}
    return {
        "title": title or "?",
        "company": company or "?",
        "location": location or "",
        "site": site or "",
        "score": int(round(float(score or 0))),
        "url": url or "",
        "verdict": verdict,
    }
