"""
Tests for `job-scout roundup`.

The roundup reads history and never re-scores, so the things worth testing are
the window arithmetic, what it refuses to show, and that it still opens a
database created before the verdict_json column existed.
"""

import json
import sqlite3
from datetime import date

import pytest

from job_scout.dedup import JobStore
from job_scout.notifiers.base import RunStats, digest_header, no_match_body
from job_scout.roundup import collect, stats_for, window

FRIDAY = date(2026, 8, 28)


def _insert(db_path, rows):
    """Put rows straight in, so a test can choose first_seen."""
    conn = JobStore(db_path).connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO seen_jobs "
            "(job_id, url, title, company, location, site, score, status, "
            " first_seen, date_posted, search_term, verdict_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _row(job_id, score, first_seen, status="new", verdict=None, company="Northwind"):
    return (
        job_id,
        f"https://example.test/{job_id}",
        "Solution Architect",
        company,
        "Berlin",
        "linkedin",
        score,
        status,
        first_seen,
        "2026-08-20",
        "solution architect",
        json.dumps(verdict) if verdict else "",
    )


# ─── window ───────────────────────────────────────────────────────────────────

def test_window_counts_today():
    """--days 5 on a Friday is Monday to Friday, not the Sunday before."""
    start, end = window(5, today=FRIDAY)
    assert start == date(2026, 8, 24)
    assert end == FRIDAY


def test_window_of_one_day_is_today_only():
    start, end = window(1, today=FRIDAY)
    assert start == end == FRIDAY


def test_window_never_goes_backwards():
    start, end = window(0, today=FRIDAY)
    assert start == end == FRIDAY


# ─── collect ──────────────────────────────────────────────────────────────────

def test_collect_returns_best_first(tmp_path):
    db = tmp_path / "jobs.db"
    _insert(db, [
        _row("a", 72, "2026-08-25"),
        _row("b", 91, "2026-08-26"),
        _row("c", 80, "2026-08-27"),
    ])
    jobs, total = collect(db, threshold=70, days=5, today=FRIDAY)
    assert [job["score"] for job in jobs] == [91, 80, 72]
    assert total == 3


def test_collect_drops_anything_below_the_threshold(tmp_path):
    db = tmp_path / "jobs.db"
    _insert(db, [_row("a", 91, "2026-08-25"), _row("b", 40, "2026-08-25")])
    jobs, total = collect(db, threshold=70, days=5, today=FRIDAY)
    assert total == 1
    assert jobs[0]["score"] == 91


def test_collect_drops_anything_outside_the_window(tmp_path):
    db = tmp_path / "jobs.db"
    _insert(db, [
        _row("inside", 91, "2026-08-24"),
        _row("before", 95, "2026-08-23"),
        _row("after", 99, "2026-08-29"),
    ])
    jobs, _ = collect(db, threshold=70, days=5, today=FRIDAY)
    assert [job["url"].rsplit("/", 1)[-1] for job in jobs] == ["inside"]


def test_collect_drops_rejected_postings(tmp_path):
    """A posting killed by a filter never reached the model. It has no score to show."""
    db = tmp_path / "jobs.db"
    _insert(db, [
        _row("scored", 91, "2026-08-25"),
        _row("filtered", 99, "2026-08-25", status="rejected_prefilter"),
    ])
    jobs, total = collect(db, threshold=70, days=5, today=FRIDAY)
    assert total == 1
    assert jobs[0]["url"].endswith("scored")


def test_collect_reports_the_total_before_the_top_cut(tmp_path):
    """"best 2 of 5" and "2 matches" mean different things."""
    db = tmp_path / "jobs.db"
    _insert(db, [_row(str(n), 80 + n, "2026-08-25") for n in range(5)])
    jobs, total = collect(db, threshold=70, days=5, top=2, today=FRIDAY)
    assert len(jobs) == 2
    assert total == 5


def test_collect_keeps_the_scorer_reasoning(tmp_path):
    db = tmp_path / "jobs.db"
    verdict = {"reasoning": "strong OT/IT overlap", "key_matches": ["Azure"], "gaps": []}
    _insert(db, [_row("a", 91, "2026-08-25", verdict=verdict)])
    jobs, _ = collect(db, threshold=70, days=5, today=FRIDAY)
    assert jobs[0]["verdict"]["reasoning"] == "strong OT/IT overlap"


def test_collect_survives_unreadable_verdict_json(tmp_path):
    db = tmp_path / "jobs.db"
    _insert(db, [_row("a", 91, "2026-08-25")])
    conn = JobStore(db).connect()
    conn.execute("UPDATE seen_jobs SET verdict_json='{not json'")
    conn.commit()
    conn.close()
    jobs, _ = collect(db, threshold=70, days=5, today=FRIDAY)
    assert jobs[0]["verdict"] == {}


def test_collect_on_a_missing_database_is_empty_not_an_error(tmp_path):
    assert collect(tmp_path / "nothing.db") == ([], 0)


def test_collect_reads_a_database_written_before_verdict_json(tmp_path):
    """
    Upgrading must not cost anyone their history. A 1.0.0 database has no
    verdict_json column; opening it adds one.
    """
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE seen_jobs ("
        " job_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT, company TEXT,"
        " location TEXT, site TEXT, score REAL, status TEXT DEFAULT 'new',"
        " first_seen TEXT, date_posted TEXT, search_term TEXT)"
    )
    conn.execute(
        "INSERT INTO seen_jobs VALUES "
        "('a', 'https://example.test/a', 'Solution Architect', 'Northwind',"
        " 'Berlin', 'linkedin', 91, 'new', '2026-08-25', '2026-08-20', 'sa')"
    )
    conn.commit()
    conn.close()

    jobs, total = collect(db, threshold=70, days=5, today=FRIDAY)
    assert total == 1
    assert jobs[0]["company"] == "Northwind"
    assert jobs[0]["verdict"] == {}


# ─── headers ──────────────────────────────────────────────────────────────────

def test_stats_names_the_span_and_the_cut(tmp_path):
    stats = stats_for([{}, {}], total=7, threshold=70, days=5, today=FRIDAY)
    assert stats.title == "Job Scout roundup, 24 Aug to 28 Aug 2026"
    assert stats.subtitle == "best 2 of 7 matches at or above 70"


def test_stats_says_the_plain_count_when_nothing_was_cut():
    stats = stats_for([{}], total=1, threshold=70, days=5, today=FRIDAY)
    assert stats.subtitle == "1 match at or above 70"


def test_empty_roundup_does_not_claim_the_sources_are_broken():
    """The default no-match text blames the job boards. For a roundup that is wrong."""
    stats = stats_for([], total=0, threshold=70, days=5, today=FRIDAY)
    body = no_match_body(stats)
    assert "quiet week" in body
    assert "Every source returned 0 jobs" not in body


def test_digest_header_is_unchanged_for_a_normal_run():
    """title and subtitle are opt-in. A run that sets neither reads as it always did."""
    stats = RunStats(total_fetched=100, total_new=10, total_rejected=8, threshold=70)
    header = digest_header([{}, {}], stats)
    assert header.startswith("Job Scout, ")
    assert "2 matches | 10 new | 8 below 70 | 100 fetched" in header


def test_digest_header_uses_the_roundup_labels_when_set():
    stats = stats_for([{}], total=1, threshold=70, days=5, today=FRIDAY)
    header = digest_header([{}], stats)
    assert header == "Job Scout roundup, 24 Aug to 28 Aug 2026\n1 match at or above 70"


# ─── the command ──────────────────────────────────────────────────────────────

def test_roundup_command_prints_and_sends_nothing_on_dry_run(tmp_path, capsys, monkeypatch):
    from job_scout.cli import main

    config_dir = tmp_path / "config"
    from job_scout.config import seed_config_dir
    seed_config_dir(config_dir)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _insert(data_dir / "jobs.db", [_row("a", 91, date.today().isoformat())])

    code = main([
        "roundup", "--dry-run",
        "--config-dir", str(config_dir),
        "--data-dir", str(data_dir),
    ])
    assert code == 0
    assert "Job Scout roundup" in capsys.readouterr().out


@pytest.mark.parametrize("days", [1, 5, 7, 30])
def test_collect_accepts_any_sane_window(tmp_path, days):
    db = tmp_path / "jobs.db"
    _insert(db, [_row("a", 91, FRIDAY.isoformat())])
    jobs, _ = collect(db, threshold=70, days=days, today=FRIDAY)
    assert len(jobs) == 1
