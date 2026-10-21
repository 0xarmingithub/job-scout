"""
Jobbank detail when the CLI cannot parse the page. The page's JSON-LD holds raw
control characters inside a string. The strict parser rejects it, and the
lenient one reads it.
"""

import io
import json

import pytest

from job_scout.sources import danish_cli
from job_scout.sources.danish_cli import PortalError, parse_job_posting_ld


def _page(description_with_raw_tab):
    # Raw tab and newline inside a JSON string, the way the live page has them.
    body = (
        '{"@context": "https://schema.org/", "@type": "JobPosting", '
        '"title": "Cloud Architect", "description": "' + description_with_raw_tab + '", '
        '"validThrough": "2026-11-20"}'
    )
    return f'<html><head><script type="application/ld+json">\n{body}\n</script></head></html>'


RAW = "<p>Job Title:</p>\tAzure\n<p>Remote &amp; hybrid</p>"


def test_the_strict_parser_rejects_the_live_pattern():
    body = _page(RAW).split(">", 2)[2].split("</script>")[0]
    with pytest.raises(ValueError):
        json.loads(body)


def test_the_lenient_parser_reads_the_same_block():
    posting = parse_job_posting_ld(_page(RAW))
    assert posting is not None
    assert posting["@type"] == "JobPosting"
    assert "Remote &amp; hybrid" in posting["description"]


def test_a_graph_wrapped_posting_is_found():
    page = (
        '<script type="application/ld+json">'
        '{"@graph": [{"@type": "Organization"}, {"@type": "JobPosting", "description": "x"}]}'
        "</script>"
    )
    assert parse_job_posting_ld(page)["description"] == "x"


def test_a_page_without_job_data_gives_none():
    assert parse_job_posting_ld("<html>no data</html>") is None


def test_the_jobbank_fallback_returns_plain_text(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        danish_cli.urllib.request, "urlopen",
        lambda request, timeout=None: Response(_page(RAW).encode("utf-8")),
    )
    text = danish_cli._jobbank_page_text("https://jobbank.dk/job/1000002/")
    assert "Job Title:" in text
    assert "Remote & hybrid" in text
    assert "<p>" not in text


def test_a_jobbank_detail_error_falls_back_to_the_page(monkeypatch):
    monkeypatch.setattr(danish_cli, "_bun", lambda: "bun")
    monkeypatch.setattr(danish_cli, "_cli_root", lambda: "C:/unused")
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)

    def cli(bun, root, portal, args, timeout):
        raise PortalError("PARSE_ERROR", "No JSON-LD found on job page")

    monkeypatch.setattr(danish_cli, "_run_cli", cli)
    monkeypatch.setattr(danish_cli, "_jobbank_page_text", lambda url: "from the page")
    item = {"id": "1000002", "url": "https://jobbank.dk/job/1000002/"}
    cache = {}
    assert danish_cli._detail("bun", "C:/unused", danish_cli.PORTALS["jobbank"], item, cache, 0) == "from the page"


def test_a_known_posting_gets_no_detail_call(monkeypatch):
    calls = []
    monkeypatch.setattr(danish_cli, "_bun", lambda: "bun")
    monkeypatch.setattr(danish_cli, "_cli_root", lambda: "C:/unused")
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)

    def cli(bun, root, portal, args, timeout):
        if args[0] == "search":
            return {"results": [{"id": "1", "title": "Dev", "company": "Acme",
                                 "url": "https://jobbank.dk/job/1", "description": ""}]}
        calls.append(args)
        return {"description": "full"}

    class Known:
        def known_by(self, job):
            return "url"

    monkeypatch.setattr(danish_cli, "_run_cli", cli)
    jobs = danish_cli.fetch_danish_jobs("jobbank", [{"term": "dev"}], {}, known=Known())
    assert len(jobs) == 1  # still reported to the store, which drops it
    assert calls == []  # but no detail request was made
