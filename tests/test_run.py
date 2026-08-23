"""
A whole run, with the job boards and the model stubbed out.

The point of these is the promises the README makes: a run finishes with none of
the optional pieces installed, a failure reaches your notifiers instead of dying
in a log file, and --dry-run really does write nothing.
"""

import pytest

from job_scout import matcher, sources
from job_scout import run as run_module
from job_scout.config import load_settings
from job_scout.matcher import ScoringUnavailable


@pytest.fixture
def fake_boards(monkeypatch):
    """Two postings from a stubbed board. No network."""
    jobs = [
        {
            "title": "Senior Platform Engineer",
            "company": "Northwind Energy",
            "location": "Berlin, Germany",
            "description": "You will run our Kubernetes platform and Terraform estate.",
            "url": "https://example.com/job/1",
            "site": "linkedin",
            "date_posted": "2026-08-22",
            "salary": "",
            "job_type": "",
            "is_remote": False,
            "search_term": "platform engineer",
        },
        {
            "title": "Pastry Chef",
            "company": "Bakery GmbH",
            "location": "Berlin, Germany",
            "description": "Croissants, at scale.",
            "url": "https://example.com/job/2",
            "site": "linkedin",
            "date_posted": "2026-08-22",
            "salary": "",
            "job_type": "",
            "is_remote": False,
            "search_term": "platform engineer",
        },
    ]
    report = sources.FetchReport(per_source={"jobspy": 2})
    monkeypatch.setattr(
        run_module.sources, "fetch_jobs",
        lambda searches, config: (list(jobs), report),
    )
    return jobs


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(matcher, "preflight", lambda spec: None)
    monkeypatch.setattr(
        matcher, "run_model",
        lambda *args, **kwargs: (
            '{"score": 88, "seniority_match": "match", '
            '"key_matches": ["Kubernetes", "Terraform"], "gaps": [], '
            '"reasoning": "Runs exactly the stack the candidate owns."}'
        ),
    )


def test_a_full_run_scores_and_writes(config_dir, fake_boards, fake_model):
    settings = load_settings(str(config_dir))
    result = run_module.run_once(settings)

    assert result.ok
    assert len(result.matched) == 1, "the pastry chef should not have survived"
    assert result.matched[0]["title"] == "Senior Platform Engineer"
    assert result.matched[0]["score"] == 88
    assert result.notified == 1

    output = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "88% — Senior Platform Engineer" in output
    assert "Northwind Energy" in output


def test_the_second_run_finds_nothing_new(config_dir, fake_boards, fake_model):
    settings = load_settings(str(config_dir))
    run_module.run_once(settings)
    second = run_module.run_once(settings)

    assert second.ok
    assert second.matched == []
    assert "already seen" in (settings.data_dir / "matches.md").read_text(encoding="utf-8")


def test_a_run_finishes_with_none_of_the_optional_pieces(config_dir, fake_model, monkeypatch):
    """
    No Playwright, no Careerjet key, no Apify token, no outcomes.csv. The real
    source modules run — they are the ones that have to decline politely.
    """
    settings = load_settings(str(config_dir))
    for search in settings.config["searches"]:
        search["sites"] = ["jobindex", "careerjet", "apify"]

    assert not settings.outcomes_path.exists()

    import builtins
    real_import = builtins.__import__

    def no_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("playwright is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_playwright)

    result = run_module.run_once(settings)
    assert result.ok, result.error
    assert result.matched == []
    assert (settings.data_dir / "matches.md").exists()


def test_dry_run_records_nothing_and_sends_nothing(config_dir, fake_boards, fake_model):
    settings = load_settings(str(config_dir))
    result = run_module.run_once(settings, dry_run=True)

    assert len(result.matched) == 1
    assert result.notified == 0
    assert not (settings.data_dir / "matches.md").exists()

    # Nothing was recorded, so a second dry run sees the same posting again.
    assert len(run_module.run_once(settings, dry_run=True).matched) == 1


def test_limit_caps_what_reaches_the_model(config_dir, fake_boards, fake_model):
    settings = load_settings(str(config_dir))
    result = run_module.run_once(settings, dry_run=True, limit=1)
    assert result.stats.total_new == 1


def test_a_backend_that_is_not_set_up_alerts_instead_of_crashing(
    config_dir, fake_boards, monkeypatch, no_clis
):
    settings = load_settings(str(config_dir))
    monkeypatch.setattr(
        matcher, "preflight",
        lambda spec: "Backend 'gemini' needs GOOGLE_API_KEY, which is not set.",
    )
    result = run_module.run_once(settings)

    assert not result.ok
    assert "GOOGLE_API_KEY" in result.error
    alert = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "ALERT" in alert
    assert "GOOGLE_API_KEY" in alert


def test_an_unexpected_failure_reaches_the_notifiers(config_dir, monkeypatch):
    settings = load_settings(str(config_dir))

    def explode(searches, config):
        raise RuntimeError("the database is on fire")

    monkeypatch.setattr(run_module.sources, "fetch_jobs", explode)
    result = run_module.run_once(settings)

    assert not result.ok
    alert = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "ALERT" in alert
    assert "the database is on fire" in alert


def test_a_failure_message_never_carries_a_credential(config_dir, monkeypatch):
    settings = load_settings(str(config_dir))

    def explode(searches, config):
        raise RuntimeError("auth failed for https://user:hunter2@example.com")

    monkeypatch.setattr(run_module.sources, "fetch_jobs", explode)
    run_module.run_once(settings)

    alert = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "hunter2" not in alert
    assert "REDACTED" in alert


def test_no_jobs_at_all_is_reported_as_probably_broken(config_dir, monkeypatch, fake_model):
    settings = load_settings(str(config_dir))
    monkeypatch.setattr(
        run_module.sources, "fetch_jobs",
        lambda searches, config: ([], sources.FetchReport(errors={"jobspy": "blocked"})),
    )
    result = run_module.run_once(settings)

    assert result.ok
    output = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "blocked or misconfigured" in output


def test_source_priority_can_be_overridden_from_config():
    priority = run_module._site_priority({"source_priority": ["careerjet", "linkedin"]})
    assert priority["careerjet"] < priority["linkedin"]


def test_scoring_unavailable_is_its_own_error_type():
    assert issubclass(ScoringUnavailable, RuntimeError)
