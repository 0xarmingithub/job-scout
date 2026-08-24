"""
`job-scout stats`. It replaced a `sqlite3` command line that is not installed on
a default Ubuntu server, so the one thing it must never do is need anything
extra itself.
"""

import sqlite3

from job_scout.dedup import JobStore
from job_scout.stats import render


def _store(tmp_path, jobs):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen(jobs)
    return tmp_path / "jobs.db"


def _job(url, status="new", score=None, title="Platform Engineer", company="Acme"):
    return {
        "url": url, "title": title, "company": company, "location": "Berlin",
        "site": "linkedin", "status": status, "score": score,
        "date_posted": "", "search_term": "platform",
    }


def test_a_missing_database_says_so_kindly(tmp_path):
    out = render(tmp_path / "nothing.db")
    assert "normal before the first run" in out
    assert "job-scout run" in out


def test_an_empty_database_says_so(tmp_path):
    path = tmp_path / "jobs.db"
    sqlite3.connect(str(path)).close()
    JobStore(path).count()
    assert "empty" in render(path)


def test_it_reports_where_postings_went(tmp_path):
    path = _store(tmp_path, [
        _job("https://a", "new", 88),
        _job("https://b", "new", 40),
        _job("https://c", "rejected_prefilter", 0),
        _job("https://d", "rejected_location", 0),
        _job("https://e", "rejected_language", 0),
    ])
    out = render(path, threshold=65)
    assert "5 postings recorded" in out
    assert "rejected_prefilter" in out
    assert "rejected_language" in out


def test_it_says_plainly_when_nothing_has_ever_cleared_the_threshold(tmp_path):
    path = _store(tmp_path, [_job("https://a", "new", 30), _job("https://b", "new", 44)])
    out = render(path, threshold=70)
    assert "Nothing has ever cleared it" in out
    assert "profile" in out and "search terms" in out


def test_it_says_the_threshold_is_reachable_when_it_is(tmp_path):
    path = _store(tmp_path, [_job("https://a", "new", 91)])
    assert "The threshold is reachable" in render(path, threshold=70)


def test_the_score_distribution_bands_appear(tmp_path):
    path = _store(tmp_path, [
        _job("https://a", "new", 95), _job("https://b", "new", 72),
        _job("https://c", "new", 61), _job("https://d", "new", 12),
    ])
    out = render(path, threshold=65)
    for band in ("80 to 100", "70 to 79", "60 to 69", "under 40"):
        assert band in out


def test_the_best_scores_name_the_job(tmp_path):
    path = _store(tmp_path, [
        _job("https://a", "new", 95, title="Senior Platform Engineer", company="Northwind"),
    ])
    out = render(path)
    assert "Senior Platform Engineer" in out
    assert "Northwind" in out


def test_a_day_that_cleared_nothing_is_flagged(tmp_path):
    path = _store(tmp_path, [_job("https://a", "new", 30)])
    assert "nothing cleared the threshold" in render(path, threshold=70)


def test_rejected_only_data_does_not_crash(tmp_path):
    """No scored rows at all is the exact case somebody runs this to diagnose."""
    path = _store(tmp_path, [
        _job("https://a", "rejected_location", 0),
        _job("https://b", "rejected_prefilter", 0),
    ])
    out = render(path, threshold=70)
    assert "2 postings recorded" in out
    assert "nothing scored in that window" in out


def test_it_uses_only_the_standard_library():
    """The whole reason it exists: no sqlite3 binary, no extra package."""
    import inspect

    import job_scout.stats as module

    source = inspect.getsource(module)
    assert "import sqlite3" in source
    for third_party in ("requests", "pandas", "yaml", "subprocess"):
        assert f"import {third_party}" not in source
