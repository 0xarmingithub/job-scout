"""
jobindex_cli detail when the CLI cannot parse the ad. Some ads redirect to an
employer's recruiting site, whose meta tags use single quotes. The CLI reads
only double quotes, so it fails. The scout reads the page itself.
"""

import pytest

from job_scout.sources import danish_cli
from job_scout.sources.danish_cli import PORTALS, PortalError

PAGE = (
    "<html><head>"
    "<meta content='Senior Advisor til Defence hos Acme' property='og:title'>"
    "<script>window.dataLayer = window.dataLayer || [];</script>"
    "<style>.x { color: red; }</style>"
    "</head><body><h1>Senior Advisor</h1>"
    "<p>Vil du v\u00e6re med til at udvikle n\u00e6ste generation?</p>"
    "</body></html>"
)


def test_script_and_style_blocks_are_not_part_of_the_text(monkeypatch):
    monkeypatch.setattr(danish_cli, "_read_page", lambda url: PAGE)
    text = danish_cli._jobindex_page_text("https://www.jobindex.dk/jobannonce/h1")
    assert "dataLayer" not in text
    assert "color: red" not in text
    assert "Senior Advisor" in text
    assert "v\u00e6re med" in text  # Danish letters survive


def test_an_unreadable_page_gives_empty_text(monkeypatch):
    monkeypatch.setattr(danish_cli, "_read_page", lambda url: None)
    assert danish_cli._jobindex_page_text("https://www.jobindex.dk/jobannonce/h1") == ""


def test_the_jobindex_cli_parse_error_falls_back_to_the_page(monkeypatch):
    monkeypatch.setattr(danish_cli, "_bun", lambda: "bun")
    monkeypatch.setattr(danish_cli, "_cli_root", lambda: "C:/unused")
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)

    def cli(bun, root, portal, args, timeout):
        raise PortalError("PARSE_ERROR", "Failed to parse job listing HTML")

    monkeypatch.setattr(danish_cli, "_run_cli", cli)
    monkeypatch.setattr(danish_cli, "_jobindex_page_text", lambda url: "from the ad page")
    item = {"id": "h1000002", "url": "https://www.jobindex.dk/jobannonce/h1000002"}
    cache = {}
    got = danish_cli._detail("bun", "C:/unused", PORTALS["jobindex_cli"], item, cache, 0)
    assert got == "from the ad page"


def test_other_portals_do_not_use_the_jobindex_fallback(monkeypatch):
    monkeypatch.setattr(danish_cli, "_bun", lambda: "bun")
    monkeypatch.setattr(danish_cli, "_cli_root", lambda: "C:/unused")
    monkeypatch.setattr(danish_cli.time, "sleep", lambda s: None)

    def cli(bun, root, portal, args, timeout):
        raise PortalError("PARSE_ERROR", "boom")

    monkeypatch.setattr(danish_cli, "_run_cli", cli)
    monkeypatch.setattr(danish_cli, "_jobindex_page_text", lambda url: pytest.fail("not for jobnet"))
    item = {"id": "x", "url": "https://jobnet.dk/job/x"}
    assert danish_cli._detail("bun", "C:/unused", PORTALS["jobnet"], item, {}, 0) == ""
