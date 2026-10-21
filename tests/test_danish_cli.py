"""
Danish portal CLIs. Mapping, detail cleaning, command building and the fetch
loop, with the CLI calls faked. The live check is in test_danish_live.py.
"""

import pytest

from job_scout import sources
from job_scout.sources import danish_cli
from job_scout.sources.danish_cli import PORTALS, PortalError, fetch_danish_jobs, html_to_text


def test_html_becomes_one_line_per_block():
    assert html_to_text("<p>Hej</p><ul><li>Python &amp; C#</li></ul>") == "Hej\nPython & C#"


def test_jobbank_search_item_maps_to_the_job_shape():
    item = {
        "id": "1000001", "title": "Senior Model Developer", "company": "Østerby",
        "location": "Storkøbenhavn", "jobType": "Fuldtidsjob",
        "description": "<p>Fuldtidsjob hos Østerby</p>",
        "url": "https://jobbank.dk/job/1000001/acme/senior-model-developer",
        "date": "2026-10-15",
    }
    job = PORTALS["jobbank"].to_job(item, "model developer")
    assert job["site"] == "jobbank"
    assert job["company"] == "Østerby"
    assert job["description"] == "Fuldtidsjob hos Østerby"
    assert job["date_posted"] == "2026-10-15"
    assert job["search_term"] == "model developer"


def test_jobnet_item_maps_and_falls_back_to_hiring_org():
    item = {
        "id": "75715ba0", "title": "Backend Engineer", "company": "",
        "hiringOrgName": "Tailwind", "location": "Odense",
        "url": "https://jobnet.dk/job/75715ba0", "date": "2026-10-08",
    }
    job = PORTALS["jobnet"].to_job(item, "python")
    assert job["site"] == "jobnet"
    assert job["company"] == "Tailwind"
    assert job["description"] == ""  # filled by a detail call later


def test_jobdanmark_item_joins_job_types():
    item = {
        "title": "FE søger en Storage Specialist", "company": "Nordic Test Org",
        "jobTypes": ["fuldtid", "deltid"], "location": "København Ø",
        "url": "https://jobdanmark.dk/job/fe-soeger", "date": "2026-10-19", "id": "fe-soeger",
    }
    job = PORTALS["jobdanmark"].to_job(item, "storage")
    assert job["site"] == "jobdanmark"
    assert job["job_type"] == "fuldtid, deltid"


def test_jobindex_cli_item_maps_with_site_name_that_differs_from_the_playwright_source():
    item = {
        "id": "h1000001", "title": "Software Engineer", "company": "Alder Group A/S",
        "location": "Aarhus N", "date": "2026-10-16", "url": "https://www.jobindex.dk/jobannonce/h1000001",
        "description": None,
    }
    job = PORTALS["jobindex_cli"].to_job(item, "software")
    assert job["site"] == "jobindex_cli"
    assert job["description"] == ""


def test_jobindex_detail_drops_the_cookie_banner():
    detail = {"description": "Real posting text.\nAnsvarlig brug af dine oplysninger\n× Accepter alle"}
    assert PORTALS["jobindex_cli"].detail_text(detail) == "Real posting text."


def test_jobbank_and_jobnet_detail_html_is_stripped():
    assert PORTALS["jobbank"].detail_text({"description": "<p>Python</p><li>SQL</li>"}) == "Python\nSQL"
    assert PORTALS["jobnet"].detail_text({"body": "<p>Backend &amp; API</p>"}) == "Backend & API"


@pytest.mark.parametrize(
    "portal, expected",
    [
        ("jobbank", ["search", "--key", "python", "--limit", "3"]),
        ("jobnet", ["search", "--search-string", "python", "--per-page", "3", "--limit", "3"]),
        ("jobdanmark", ["search", "--text", "python", "--limit", "3"]),
        ("jobindex_cli", ["search", "-q", "python", "--limit", "3"]),
    ],
)
def test_search_arguments_match_each_cli(portal, expected):
    assert PORTALS[portal].search_args("python", 3) == expected


def test_without_the_clone_the_source_returns_nothing_and_runs_no_command(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_PORTAL_CLIS", raising=False)
    monkeypatch.setattr(danish_cli, "_run_cli", lambda *a, **k: pytest.fail("no CLI call expected"))
    searches = [{"term": "python", "sites": ["jobbank"], "results_wanted": 3}]
    assert fetch_danish_jobs("jobbank", searches) == []


def _fake_cli(search_results, details):
    """Stand-in for _run_cli. Records every call so tests can count them."""
    calls = []

    def run(bun, root, portal, args, timeout):
        calls.append((portal.name, args[0], args[1]))
        if args[0] == "search":
            return {"results": search_results}
        return details.get(args[1])

    return run, calls


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setattr(danish_cli, "_bun", lambda: "bun")
    monkeypatch.setattr(danish_cli, "_cli_root", lambda: tmp_path)
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)


def test_a_stub_description_gets_a_detail_call_and_the_detail_text(monkeypatch, fake_env):
    results = [{"id": "h1", "title": "Dev", "company": "Acme", "location": "Aarhus",
                "url": "https://www.jobindex.dk/jobannonce/h1", "date": "2026-10-16", "description": None}]
    run, calls = _fake_cli(results, {"h1": {"description": "Full text of the posting."}})
    monkeypatch.setattr(danish_cli, "_run_cli", run)

    jobs = fetch_danish_jobs("jobindex_cli", [{"term": "dev", "results_wanted": 5}])
    assert jobs[0]["description"] == "Full text of the posting."
    assert ("jobindex_cli", "detail", "h1") in calls


def test_the_same_posting_found_by_two_searches_is_detailed_once(monkeypatch, fake_env):
    results = [{"id": "h1", "title": "Dev", "url": "https://www.jobindex.dk/jobannonce/h1", "description": None}]
    run, calls = _fake_cli(results, {"h1": {"description": "Text."}})
    monkeypatch.setattr(danish_cli, "_run_cli", run)

    jobs = fetch_danish_jobs("jobindex_cli", [{"term": "dev"}, {"term": "engineer"}])
    assert len(jobs) == 1  # same URL, kept once
    assert [c for c in calls if c[1] == "detail"] == [("jobindex_cli", "detail", "h1")]


def test_a_posting_that_is_gone_keeps_its_search_text(monkeypatch, fake_env):
    results = [{"id": "gone", "title": "Dev", "url": "https://jobnet.dk/job/gone", "description": ""}]
    run, _ = _fake_cli(results, {"gone": None})  # None is what NOT_FOUND becomes
    monkeypatch.setattr(danish_cli, "_run_cli", run)

    jobs = fetch_danish_jobs("jobnet", [{"term": "dev"}])
    assert jobs[0]["description"] == ""


def test_a_search_error_propagates_so_the_report_records_it(monkeypatch, fake_env):
    def boom(bun, root, portal, args, timeout):
        raise PortalError("RATE_LIMITED", "HTTP 429")

    monkeypatch.setattr(danish_cli, "_run_cli", boom)
    with pytest.raises(PortalError):
        fetch_danish_jobs("jobbank", [{"term": "dev"}])


def test_the_registry_knows_the_four_portals():
    for name in ("jobbank", "jobnet", "jobdanmark", "jobindex_cli"):
        assert name in sources.ALL_SITES
    assert sources.unknown_sites([{"term": "x", "sites": ["jobbank", "monster"]}]) == ["monster"]


def test_the_detail_cap_stops_further_detail_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(danish_cli, "MAX_DETAIL_CALLS_PER_RUN", 1)
    monkeypatch.setattr(danish_cli, "_run_cli", lambda *a, **k: calls.append(a[3]) or {"description": "x"})
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)
    cache: dict[str, str] = {}
    for job_id in ("a", "b"):
        danish_cli._detail(None, None, PORTALS["jobindex_cli"], {"id": job_id}, cache, 0)
    assert calls == [["detail", "a"]]
    assert cache == {"a": "x"}
