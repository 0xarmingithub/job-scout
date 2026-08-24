"""
stats.py: what the seen-jobs database actually says.

This is the answer to "it sent me nothing, is it broken?". It reads jobs.db and
prints where postings are being lost, what the scores look like, and whether
anything has ever cleared your threshold.

    job-scout stats
    job-scout stats --days 30

Reading the numbers:

  Every posting ends with a status. `new` means it was scored. Everything
  starting `rejected_` was dropped, and by which filter tells you where to look.

  A large `rejected_prefilter` means your keyword list is too narrow, or a title
  pattern is too greedy. A large `rejected_location` means your exclusions are
  doing their job, or eating your market.

  If the distribution has nothing above your threshold and never has, the
  problem is the profile or the search terms, not the threshold.
"""

import sqlite3
from pathlib import Path


def _rows(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def _bar(count: int, largest: int, width: int = 34) -> str:
    if largest <= 0:
        return ""
    return "#" * max(1, round(width * count / largest)) if count else ""


def render(db_path: Path, threshold: int = 65, days: int = 14) -> str:
    """The whole report as text, so a caller can print it or send it."""
    db_path = Path(db_path)
    if not db_path.exists():
        return (
            f"No database at {db_path}.\n"
            f"That is normal before the first run. Try: job-scout run"
        )

    out: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        total = _rows(conn, "SELECT COUNT(*) FROM seen_jobs")[0][0]
        if not total:
            return f"{db_path} is empty. Nothing has been recorded yet."

        scored = _rows(
            conn, "SELECT COUNT(*) FROM seen_jobs WHERE status='new' AND score IS NOT NULL"
        )[0][0]
        cleared = _rows(
            conn, "SELECT COUNT(*) FROM seen_jobs WHERE status='new' AND score>=?", threshold
        )[0][0]

        out.append(f"{db_path}")
        out.append(f"{total} postings recorded, {scored} reached the scorer.")
        out.append(
            f"{cleared} have scored {threshold} or more. "
            + (
                "The threshold is reachable."
                if cleared
                else "Nothing has ever cleared it, which points at the profile "
                "or the search terms rather than the threshold."
            )
        )

        out.append("\nWhere postings ended up")
        status_rows = _rows(
            conn, "SELECT status, COUNT(*) FROM seen_jobs GROUP BY status ORDER BY 2 DESC"
        )
        largest = max((n for _, n in status_rows), default=0)
        for status, n in status_rows:
            out.append(f"  {n:6}  {status:30} {_bar(n, largest)}")

        out.append("\nScore distribution")
        band_rows = _rows(
            conn,
            """SELECT CASE
                 WHEN score>=80 THEN 'a 80 to 100'
                 WHEN score>=70 THEN 'b 70 to 79'
                 WHEN score>=60 THEN 'c 60 to 69'
                 WHEN score>=50 THEN 'd 50 to 59'
                 WHEN score>=40 THEN 'e 40 to 49'
                 ELSE 'f under 40' END AS band, COUNT(*)
               FROM seen_jobs WHERE status='new' AND score IS NOT NULL
               GROUP BY band ORDER BY band""",
        )
        largest = max((n for _, n in band_rows), default=0)
        for band, n in band_rows:
            out.append(f"  {n:6}  {band[2:]:30} {_bar(n, largest)}")

        out.append(f"\nLast {days} days")
        day_rows = _rows(
            conn,
            "SELECT first_seen, COUNT(*), MAX(score) FROM seen_jobs "
            "WHERE status='new' AND score IS NOT NULL AND first_seen>=date('now',?) "
            "GROUP BY first_seen ORDER BY first_seen",
            f"-{int(days)} days",
        )
        if not day_rows:
            out.append("  nothing scored in that window")
        for day, n, best in day_rows:
            flag = "" if (best or 0) >= threshold else "   (nothing cleared the threshold)"
            out.append(f"  {day}  scored {n:4}  best {int(best or 0):3}{flag}")

        out.append("\nBest scores on record")
        for score, title, company, seen in _rows(
            conn,
            "SELECT score, title, company, first_seen FROM seen_jobs "
            "WHERE status='new' AND score IS NOT NULL ORDER BY score DESC LIMIT 8",
        ):
            out.append(
                f"  {int(score):3}  {seen}  {(title or '')[:40]:40}  {(company or '')[:22]}"
            )
    finally:
        conn.close()

    return "\n".join(out)
