"""
Sources. Nothing here touches the network: the Careerjet and Apify mapping
functions are pure, the dispatcher is driven with stubs, and every source is
checked for the one property that matters most — failing without taking the run
down.

Two of these are the smoke tests that used to live inside deploy_vm.sh, rewritten
so they need neither an API key nor a browser.
"""

import pytest

from job_scout import sources
from job_scout.sources import apify, careerjet


# ─── Smoke test 4: everything imports ─────────────────────────────────────────

def test_every_module_imports():
    from job_scout import cli, config, dedup, matcher, redact, run, track_record  # noqa: F401
    from job_scout.llm import backend  # noqa: F401
    from job_scout.notifiers import base, email_smtp, file_writer, telegram, webhook  # noqa: F401
    from job_scout.sources import apify, careerjet, jobindex, jobspy_source  # noqa: F401


def test_the_site_list_is_complete():
    assert "linkedin" in sources.ALL_SITES
    assert "apify" in sources.ALL_SITES
    assert "careerjet" in sources.ALL_SITES
    assert "jobindex" in sources.ALL_SITES


def test_unknown_sites_are_reported():
    searches = [{"term": "x", "sites": ["linkedin", "monster"]}]
    assert sources.unknown_sites(searches) == ["monster"]


# ─── The dispatcher keeps going when a source falls over ──────────────────────

def test_a_failing_source_does_not_stop_the_others(monkeypatch):
    def explode(searches, config=None):
        raise RuntimeError("Careerjet is having a bad day")

    monkeypatch.setattr(sources, "_load_careerjet", lambda: explode)
    monkeypatch.setattr(
        sources, "_load_apify",
        lambda: (lambda searches, config=None: [
            {"url": "https://a", "title": "SRE", "company": "Acme"},
        ]),
    )

    jobs, report = sources.fetch_jobs(
        [{"term": "sre", "sites": ["careerjet", "apify"]}], {}
    )
    assert len(jobs) == 1
    assert "careerjet" in report.errors
    assert report.per_source["apify"] == 1
    assert "FAILED" in report.summary()


def test_duplicate_urls_are_dropped_across_sources(monkeypatch):
    same = [{"url": "https://a", "title": "SRE", "company": "Acme"}]
    monkeypatch.setattr(sources, "_load_careerjet", lambda: (lambda s, c=None: list(same)))
    monkeypatch.setattr(sources, "_load_apify", lambda: (lambda s, c=None: list(same)))

    jobs, report = sources.fetch_jobs(
        [{"term": "sre", "sites": ["careerjet", "apify"]}], {}
    )
    assert len(jobs) == 1
    assert report.total == 1


def test_a_source_nobody_asked_for_is_never_loaded(monkeypatch):
    def explode():
        raise AssertionError("apify should not have been loaded")

    monkeypatch.setattr(sources, "_load_apify", explode)
    monkeypatch.setattr(sources, "_load_careerjet", lambda: (lambda s, c=None: []))
    sources.fetch_jobs([{"term": "sre", "sites": ["careerjet"]}], {})


def test_no_searches_means_no_work():
    jobs, report = sources.fetch_jobs([], {})
    assert jobs == []
    assert report.total == 0


# ─── Careerjet ────────────────────────────────────────────────────────────────

def test_careerjet_is_skipped_without_credentials(caplog):
    assert careerjet.fetch_careerjet_jobs([{"term": "x"}], {}) == []
    assert "CAREERJET_API_KEY" in caplog.text
    assert "CAREERJET_REFERER" in caplog.text
    assert "CAREERJET_USER_IP" in caplog.text


def test_careerjet_names_only_what_is_actually_missing(monkeypatch, caplog):
    monkeypatch.setenv("CAREERJET_API_KEY", "key")
    monkeypatch.setenv("CAREERJET_REFERER", "https://example.com/jobs")
    careerjet.fetch_careerjet_jobs([{"term": "x"}], {})
    assert "CAREERJET_USER_IP" in caplog.text
    assert "CAREERJET_API_KEY" not in caplog.text


def test_careerjet_auth_header():
    # base64("testkey:") == "dGVzdGtleTo="
    assert careerjet._auth_header("testkey") == "Basic dGVzdGtleTo="


def test_careerjet_maps_a_result_onto_the_scout_schema():
    """Smoke test 5 from deploy_vm.sh: salary and date parsing."""
    raw = {
        "title": "Test Engineer",
        "company": "Acme",
        "locations": "Copenhagen",
        "description": "Test job",
        "url": "https://example.com/job/1",
        "date": "Wed, 15 Nov 2023 19:13:43 GMT",
        "salary": "kr 30.000 - 33.000",
        "salary_currency_code": "DKK",
        "salary_min": 30000,
        "salary_max": 33000,
        "salary_type": "M",
    }
    job = careerjet._map_job(raw, "test")
    assert job["date_posted"] == "2023-11-15"
    assert job["salary"] == "kr 30.000 - 33.000"
    assert job["site"] == "careerjet"
    assert job["search_term"] == "test"
    assert set(job) == {
        "title", "company", "location", "description", "url", "site",
        "date_posted", "salary", "job_type", "is_remote", "search_term",
    }


def test_careerjet_builds_a_salary_range_when_there_is_no_text():
    salary = careerjet._format_salary({
        "salary_currency_code": "EUR", "salary_min": 60000,
        "salary_max": 80000, "salary_type": "Y",
    })
    assert salary == "EUR 60,000-80,000/yr"


def test_careerjet_passes_an_unparseable_date_through():
    assert careerjet._parse_date("not a date") == "not a date"
    assert careerjet._parse_date("") == ""


def test_careerjet_spots_remote_in_either_language():
    assert careerjet._map_job({"locations": "Remote"}, "x")["is_remote"]
    assert careerjet._map_job({"locations": "Hjemmearbejde"}, "x")["is_remote"]
    assert not careerjet._map_job({"locations": "Copenhagen"}, "x")["is_remote"]


# ─── Apify ────────────────────────────────────────────────────────────────────

def test_apify_is_skipped_without_a_token(caplog):
    assert apify.fetch_apify_jobs([{"term": "x"}], {}) == []
    assert "APIFY_API_TOKEN" in caplog.text


def test_apify_is_skipped_when_no_actor_is_configured(monkeypatch, caplog):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_test")
    assert apify.fetch_apify_jobs([{"term": "x"}], {"apify": {}}) == []
    assert "no `apify: actors:` block" in caplog.text


def test_apify_writes_the_actor_id_the_way_the_api_wants_it():
    assert apify._actor_path("misceres/indeed-scraper") == "misceres~indeed-scraper"
    assert apify._actor_path("already~fine") == "already~fine"


def test_apify_fills_placeholders_into_the_actor_input():
    template = {
        "position": "{term}",
        "location": "{location}",
        "country": "{country}",
        "maxItemsPerSearch": "{results_wanted}",
        "note": "searching for {term} in {location}",
        "nested": {"deep": ["{term}"]},
    }
    search = {
        "term": "platform engineer",
        "location": "Berlin",
        "country_indeed": "Germany",
        "results_wanted": 50,
    }
    rendered = apify._render_input(template, search)
    assert rendered["position"] == "platform engineer"
    assert rendered["country"] == "Germany"
    assert rendered["maxItemsPerSearch"] == 50, "a whole-value placeholder keeps its type"
    assert isinstance(rendered["maxItemsPerSearch"], int)
    assert rendered["note"] == "searching for platform engineer in Berlin"
    assert rendered["nested"]["deep"] == ["platform engineer"]


def test_apify_leaves_an_unknown_placeholder_alone():
    rendered = apify._render_input({"x": "{nonsense}"}, {"term": "t"})
    assert rendered["x"] == "{nonsense}"


def test_apify_maps_the_indeed_actor_output():
    """The exact field names misceres/indeed-scraper returns."""
    item = {
        "positionName": "Power BI Report Analyst",
        "salary": None,
        "jobType": ["Fulltime"],
        "company": "Purple Drive Technologies",
        "location": "500 Almanor Avenue, Sunnyvale, CA 94085",
        "url": "https://www.indeed.com/company/x/jobs/1",
        "id": "cd84b0a277f6128d",
        "postedAt": "Today",
        "description": "Key words to search in resume",
        "descriptionHTML": "<p>Key words</p>",
        "externalApplyLink": None,
    }
    job = apify._map_item(item, apify._merge_aliases(None), "indeed", "analyst")
    assert job["title"] == "Power BI Report Analyst"
    assert job["company"] == "Purple Drive Technologies"
    assert job["url"] == "https://www.indeed.com/company/x/jobs/1"
    assert job["description"] == "Key words to search in resume"
    assert job["job_type"] == "Fulltime"
    assert job["date_posted"] == "Today"
    assert job["site"] == "indeed"


def test_apify_maps_a_linkedin_style_output():
    item = {
        "title": "Senior Platform Engineer",
        "companyName": "Northwind",
        "location": "Berlin, Germany",
        "jobUrl": "https://linkedin.example/jobs/1",
        "descriptionText": "Kubernetes and Terraform",
        "publishedAt": "2026-08-20T09:00:00.000Z",
        "contractType": "Full-time",
    }
    job = apify._map_item(item, apify._merge_aliases(None), "linkedin", "platform")
    assert job["title"] == "Senior Platform Engineer"
    assert job["company"] == "Northwind"
    assert job["url"] == "https://linkedin.example/jobs/1"
    assert job["date_posted"] == "2026-08-20"
    assert job["job_type"] == "Full-time"


def test_apify_field_map_overrides_the_defaults():
    item = {"title": "ignore me", "myTitle": "use me", "url": "https://a"}
    aliases = apify._merge_aliases({"title": "myTitle"})
    assert apify._map_item(item, aliases, "apify", "x")["title"] == "use me"


def test_apify_strips_html_when_only_html_is_offered():
    item = {"descriptionHTML": "<p>Hello <b>world</b></p>", "url": "https://a"}
    job = apify._map_item(item, apify._merge_aliases(None), "apify", "x")
    assert job["description"] == "Hello world"


def test_apify_flattens_awkward_shapes():
    assert apify._as_text({"name": "Acme"}) == "Acme"
    assert apify._as_text(["a", "b"]) == "a, b"
    assert apify._as_text(None) == ""
    assert apify._as_text(42) == "42"


def test_apify_detects_remote_from_either_field():
    aliases = apify._merge_aliases(None)
    assert apify._map_item({"isRemote": True, "url": "https://a"}, aliases, "x", "y")["is_remote"]
    assert apify._map_item(
        {"location": "Remote, EU", "url": "https://a"}, aliases, "x", "y"
    )["is_remote"]
    assert not apify._map_item(
        {"location": "Berlin", "url": "https://a"}, aliases, "x", "y"
    )["is_remote"]


@pytest.mark.parametrize(
    "value,expected",
    [("2026-08-20T09:00:00Z", "2026-08-20"), ("Today", "Today"), ("", "")],
)
def test_apify_date_handling(value, expected):
    assert apify._normalise_date(value) == expected


# ─── JobIndex, without a browser ──────────────────────────────────────────────

def test_jobindex_is_skipped_when_playwright_is_missing(monkeypatch, caplog):
    import builtins

    from job_scout.sources import jobindex

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert jobindex.fetch_jobindex_jobs([{"term": "x"}], {}) == []
    assert "playwright install chromium" in caplog.text


def test_jobindex_parses_a_card_from_saved_html():
    pytest.importorskip("bs4", reason="beautifulsoup4 is an optional extra")
    from job_scout.sources import jobindex

    html = """
    <html><body><div class="jobsearch-result">
      <h4><a href="/vis-job/12345">Platform Engineer</a></h4>
      <div>København</div>
      <p>We run Kubernetes.</p>
      <p>You will own the platform.</p>
      <img alt="Northwind Energy" src="/logo.png">
      <div class="jix_toolbar"><span>
        <a href="/bruger/dine-job/12345/gem">Gem job</a>
        <a href="https://example.com/apply">Se jobbet</a>
      </span></div>
    </div></body></html>
    """
    jobs, has_next = jobindex.parse_search_page(html, "platform engineer")
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Platform Engineer"
    assert job["company"] == "Northwind Energy"
    assert job["url"] == "https://example.com/apply"
    assert job["site"] == "jobindex"
    assert "Kubernetes" in job["description"]
    assert has_next is False


def test_jobindex_makes_relative_urls_absolute():
    from job_scout.sources import jobindex

    assert jobindex._resolve_url("/vis-job/1") == "https://www.jobindex.dk/vis-job/1"
    assert jobindex._resolve_url("https://x/y") == "https://x/y"
    assert jobindex._resolve_url("") == ""


# ─── JobSpy ───────────────────────────────────────────────────────────────────

def test_jobspy_says_what_to_install_when_it_is_missing(monkeypatch):
    import builtins

    from job_scout.sources import jobspy_source

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jobspy":
            raise ImportError("no jobspy here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="pip install python-jobspy"):
        jobspy_source.fetch_jobspy_jobs([{"term": "x"}])


def test_jobspy_salary_formatting():
    from job_scout.sources.jobspy_source import _format_salary

    assert _format_salary({"min_amount": 60000, "max_amount": 80000,
                           "currency": "EUR", "interval": "yearly"}) == \
        "EUR 60,000-80,000 / yearly"
    assert _format_salary({"min_amount": None, "max_amount": None}) == ""
    assert _format_salary({"min_amount": "not a number"}) == ""
