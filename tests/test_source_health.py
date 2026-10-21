"""
source_health.py. A source that goes quiet is reported, one that errors is not
counted as a zero, degraded output is named, and a 429 is never called broken.
"""

from job_scout import source_health
from job_scout.sources import FetchReport


def _report(per_source=None, errors=None, degraded=None):
    report = FetchReport(per_source=per_source or {}, errors=errors or {})
    report.degraded = degraded or {}
    return report


def test_a_source_silent_for_three_runs_after_jobs_is_reported(tmp_path):
    for count in (5, 0, 0, 0):
        lines = source_health.check_run(tmp_path, _report({"jobbank": count}))
    assert any(line.startswith("jobbank returned 0 jobs for 3 runs in a row") for line in lines)


def test_two_quiet_runs_are_not_yet_a_problem(tmp_path):
    for count in (5, 0, 0):
        lines = source_health.check_run(tmp_path, _report({"jobbank": count}))
    assert lines == []


def test_a_source_that_never_returned_jobs_is_not_reported_as_silent(tmp_path):
    for _ in range(4):
        lines = source_health.check_run(tmp_path, _report({"jobnet": 0}))
    assert lines == []


def test_an_errored_source_is_not_recorded_as_a_zero(tmp_path):
    source_health.check_run(tmp_path, _report({"jobnet": 4}))
    source_health.check_run(tmp_path, _report({"jobnet": 0}, errors={"jobnet": "boom"}))
    history = source_health.load_history(tmp_path / source_health.HISTORY_FILE)
    assert history == {"jobnet": [4]}


def test_a_dry_run_reads_history_but_does_not_write_it(tmp_path):
    source_health.check_run(tmp_path, _report({"jobbank": 5}, ), record_history=False)
    assert not (tmp_path / source_health.HISTORY_FILE).exists()


def test_degraded_company_title_and_domain_are_named():
    jobs = [
        {"company": "", "title": "<b>Dev</b>", "url": "https://example.com/x"},
        {"company": "", "title": "Dev", "url": "https://jobbank.dk/job/1"},
    ]
    reasons = source_health.degraded_reasons("jobbank", jobs)
    assert "no company on any of 2 results" in reasons
    assert "HTML tags in 1 titles" in reasons
    assert "1 links off the portal" in reasons


def test_entities_in_titles_are_not_degraded():
    jobs = [{"company": "Østerby", "title": "Ingeniør &amp; Chef", "url": "https://jobdanmark.dk/job/a"}]
    assert source_health.degraded_reasons("jobdanmark", jobs) == []


def test_jobindex_external_links_are_not_degraded():
    jobs = [{"company": "Acme", "title": "Dev", "url": "https://job.paychex.eu/ad/x"}]
    assert source_health.degraded_reasons("jobindex", jobs) == []
    assert source_health.degraded_reasons("jobindex_cli", jobs) == []


def test_a_healthy_batch_has_no_degraded_reasons():
    jobs = [{"company": "Meridian", "title": "Engineer", "url": "https://jobdanmark.dk/job/a"}]
    assert source_health.degraded_reasons("jobdanmark", jobs) == []


def test_degraded_output_is_reported_by_check_run(tmp_path):
    report = _report({"jobindex_cli": 3}, degraded={"jobindex_cli": ["no company on any of 3 results"]})
    lines = source_health.check_run(tmp_path, report)
    assert lines == ["jobindex_cli output looks broken: no company on any of 3 results."]


def test_429_is_rate_limited_not_broken():
    assert source_health.is_rate_limited("HTTP 429 Too Many Requests")
    assert not source_health.is_rate_limited("boom")


def test_summary_tags_rate_limits_failures_and_degraded_output():
    report = _report(
        {"jobbank": 3},
        errors={"careerjet": "HTTP 429", "apify": "boom"},
        degraded={"jobnet": ["no company on any of 2 results"]},
    )
    summary = report.summary()
    assert "careerjet: rate-limited" in summary
    assert "apify: FAILED" in summary
    assert "jobnet: DEGRADED" in summary
