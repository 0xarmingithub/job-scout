"""
danish_cli.py. Four Danish job boards through the portal CLIs in
MadsLorentzen/ai-job-search (MIT): jobbank, jobnet, jobdanmark and jobindex_cli.

Each portal has a `search` and a `detail` command that print JSON. This module
runs them with bun, maps the JSON onto the job shape in sources/__init__.py,
and fills in the description with a `detail` call when the search result has
none or only a stub.

Setup, once per machine:
  1. Install bun (https://bun.sh), and put it on PATH or set JOB_SCOUT_BUN.
  2. Clone https://github.com/MadsLorentzen/ai-job-search somewhere.
  3. Run `bun install` in each .agents/skills/<portal>-search/cli folder.
  4. Set JOB_SCOUT_PORTAL_CLIS to the clone's root folder.

If bun or the clone is missing, each source logs one line and returns nothing.
"""

import html
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_SECONDS = 120
DETAIL_TIMEOUT_SECONDS = 60
# A search result with a description shorter than this gets a detail call.
STUB_DESCRIPTION_CHARS = 200
# Per portal, per run. Each search can return up to results_wanted postings, and
# every stub then costs one request to the portal. The cap keeps a daily run to
# a few minutes and the request count low on sites that have not been asked
# for this volume before.
MAX_DETAIL_CALLS_PER_RUN = 60
# Jobindex's detail page carries a cookie banner after the posting text.
_JOBINDEX_BANNER = "Ansvarlig brug af dine oplysninger"

_TAG_BREAK = re.compile(r"(?i)<br\s*/?>|</p>|</li>|</h\d>")
_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    """Turn a small HTML fragment into plain text with one line per block."""
    text = _TAG_BREAK.sub("\n", raw or "")
    text = html.unescape(_TAG.sub(" ", text))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class Portal:
    name: str
    skill: str
    search_args: Callable[[str, int], list[str]]
    to_job: Callable[[dict, str], dict]
    detail_text: Callable[[dict], str] | None


class PortalError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _job(site: str, term: str, *, title: str, description: str = "",
         job_type: str = "", url: str, company: str, location: str, date: str) -> dict:
    # The portals send names as HTML-escaped text, so "&amp;" arrives as the
    # five characters, not as an ampersand. Decode them here.
    return {
        "title": html.unescape(title or ""),
        "company": html.unescape(company or ""),
        "location": html.unescape(location or ""),
        "description": description or "",
        "url": url or "",
        "site": site,
        "date_posted": date or "",
        "salary": "",
        "job_type": job_type or "",
        # The portal does not say whether a job is remote. The scorer reads the text.
        "is_remote": False,
        "search_term": term,
    }


def _map_jobbank(item: dict, term: str) -> dict:
    return _job(
        "jobbank", term,
        title=item.get("title"), description=html_to_text(item.get("description") or ""),
        job_type=item.get("jobType"), url=item.get("url"),
        company=item.get("company"), location=item.get("location"), date=item.get("date"),
    )


def _map_jobnet(item: dict, term: str) -> dict:
    return _job(
        "jobnet", term,
        title=item.get("title"), url=item.get("url"),
        company=item.get("company") or item.get("hiringOrgName"),
        location=item.get("location"), date=item.get("date"),
    )


def _map_jobdanmark(item: dict, term: str) -> dict:
    return _job(
        "jobdanmark", term,
        title=item.get("title"), job_type=", ".join(item.get("jobTypes") or []),
        url=item.get("url"), company=item.get("company") or item.get("companyName"),
        location=item.get("location"), date=item.get("date"),
    )


def _map_jobindex(item: dict, term: str) -> dict:
    return _job(
        "jobindex_cli", term,
        title=item.get("title"), url=item.get("url"),
        company=item.get("company"), location=item.get("location"), date=item.get("date"),
    )


def _detail_jobbank(detail: dict) -> str:
    return html_to_text(detail.get("description") or "")


def _detail_jobnet(detail: dict) -> str:
    return html_to_text(detail.get("body") or "")


def _detail_jobdanmark(detail: dict) -> str:
    return (detail.get("description") or "").strip()


def _detail_jobindex(detail: dict) -> str:
    text = detail.get("description") or ""
    return text.split(_JOBINDEX_BANNER)[0].strip()


PORTALS: dict[str, Portal] = {
    "jobbank": Portal(
        "jobbank", "jobbank-search",
        lambda term, n: ["search", "--key", term, "--limit", str(n)],
        _map_jobbank, _detail_jobbank,
    ),
    "jobnet": Portal(
        "jobnet", "jobnet-search",
        lambda term, n: ["search", "--search-string", term, "--per-page", str(n), "--limit", str(n)],
        _map_jobnet, _detail_jobnet,
    ),
    "jobdanmark": Portal(
        "jobdanmark", "jobdanmark-search",
        lambda term, n: ["search", "--text", term, "--limit", str(n)],
        _map_jobdanmark, _detail_jobdanmark,
    ),
    "jobindex_cli": Portal(
        "jobindex_cli", "jobindex-search",
        lambda term, n: ["search", "-q", term, "--limit", str(n)],
        _map_jobindex, _detail_jobindex,
    ),
}

DANISH_CLI_SITES = tuple(PORTALS)


def _bun() -> str | None:
    return os.environ.get("JOB_SCOUT_BUN") or shutil.which("bun")


def _cli_root() -> Path | None:
    raw = os.environ.get("JOB_SCOUT_PORTAL_CLIS")
    if not raw:
        return None
    root = Path(raw)
    return root if root.is_dir() else None


def _run_cli(bun: str, root: Path, portal: Portal, args: list[str], timeout: int):
    """Run one portal command and return its parsed JSON. None when the posting is gone."""
    skill_dir = root / ".agents" / "skills" / portal.skill / "cli"
    cmd = [bun, "run", str(skill_dir / "src" / "cli.ts"), *args, "--format", "json"]
    proc = subprocess.run(
        cmd, cwd=skill_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    body = proc.stdout.strip() or proc.stderr.strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{portal.name} printed no JSON (exit {proc.returncode}): {body[:200]}") from exc
    if proc.returncode != 0 or (isinstance(data, dict) and "error" in data):
        code = data.get("code", "ERROR") if isinstance(data, dict) else "ERROR"
        if code == "NOT_FOUND":
            return None
        message = data.get("error", body[:200]) if isinstance(data, dict) else body[:200]
        raise PortalError(code, message)
    return data


def fetch_danish_jobs(
    portal_name: str,
    searches: list[dict],
    config: dict | None = None,
    known=None,
) -> list[dict]:
    """Search one portal for every search that lists it in its sites."""
    portal = PORTALS[portal_name]
    bun, root = _bun(), _cli_root()
    if bun is None or root is None:
        logger.warning(
            "%s skipped: needs bun on PATH (or JOB_SCOUT_BUN) and JOB_SCOUT_PORTAL_CLIS "
            "set to a checkout of MadsLorentzen/ai-job-search.", portal_name,
        )
        return []

    from ..config import merge_advanced

    delay = max(1.0, float(merge_advanced(config or {})["source_delay_seconds"]))
    details: dict[str, str] = {}
    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for search in searches:
        term = str(search.get("term") or "").strip()
        if not term:
            continue
        want = int(search.get("results_wanted") or 20)
        data = _run_cli(bun, root, portal, portal.search_args(term, want), SEARCH_TIMEOUT_SECONDS)
        time.sleep(delay)
        for item in (data or {}).get("results", [])[:want]:
            job = portal.to_job(item, term)
            if not job["url"] or job["url"] in seen_urls:
                continue
            seen_urls.add(job["url"])
            already_known = known is not None and known.known_by(job) != ""
            if portal.detail_text and not already_known and len(job["description"]) < STUB_DESCRIPTION_CHARS:
                job["description"] = _detail(bun, root, portal, item, details, delay) or job["description"]
            jobs.append(job)

    logger.info("%s: %d jobs from the portal CLI", portal_name, len(jobs))
    return jobs


_LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _find_job_posting(value):
    if isinstance(value, list):
        for item in value:
            found = _find_job_posting(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            return value
        return _find_job_posting(value.get("@graph"))
    return None


def parse_job_posting_ld(page: str) -> dict | None:
    """
    The JobPosting in a page's JSON-LD. Lenient on purpose: the strict parser
    rejects raw control characters, which some job pages contain.
    """
    for block in _LD_JSON.findall(page):
        try:
            data = json.loads(block, strict=False)
        except ValueError:
            continue
        found = _find_job_posting(data)
        if found:
            return found
    return None


def _read_page(url: str) -> str | None:
    """The page's HTML, following redirects. None when it cannot be read."""
    request = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
    try:
        with urllib.request.urlopen(request, timeout=DETAIL_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except OSError as exc:
        logger.warning("page %s could not be read: %s", url, exc)
        return None


_NON_TEXT = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>", re.S | re.I)


def _jobindex_page_text(url: str) -> str:
    """
    Text of an external Jobindex ad, read from the page the redirect ends on.
    The whole visible body is used, which includes some page furniture. The
    scorer copes with that; the title is already known from the search result.
    """
    if not url:
        return ""
    page = _read_page(url)
    if not page:
        return ""
    body = _NON_TEXT.sub(" ", page)
    return html_to_text(body)


def _jobbank_page_text(url: str) -> str:
    """Description read straight from the job page, for postings the CLI cannot parse."""
    if not url:
        return ""
    page = _read_page(url)
    if not page:
        return ""
    posting = parse_job_posting_ld(page)
    if not posting:
        logger.warning("jobbank page %s has no JobPosting data", url)
        return ""
    return html_to_text(posting.get("description") or "")


def _detail(bun, root, portal: Portal, item: dict, cache: dict[str, str], delay: float) -> str:
    """Full description for one posting. Cached per run so a repeat hit costs nothing."""
    job_id = str(item.get("id") or "")
    if not job_id:
        return ""
    if job_id not in cache and len(cache) >= MAX_DETAIL_CALLS_PER_RUN:
        # The search text stays as it is. Raise the cap in this module if a
        # portal's postings are mostly stubs and you want their full text.
        return ""
    if job_id not in cache:
        try:
            detail = _run_cli(bun, root, portal, ["detail", job_id], DETAIL_TIMEOUT_SECONDS)
            cache[job_id] = portal.detail_text(detail) if detail else ""
        except PortalError as exc:
            if exc.code == "PARSE_ERROR" and portal.name == "jobbank":
                # The CLI's JSON parser rejects this page's JSON-LD (raw control
                # characters inside a string). Python's parser accepts it.
                cache[job_id] = _jobbank_page_text(item.get("url") or "")
            elif exc.code == "PARSE_ERROR" and portal.name == "jobindex_cli":
                # The CLI reads only double-quoted meta tags. Some ads redirect to an
                # employer's recruiting site that uses single quotes.
                cache[job_id] = _jobindex_page_text(item.get("url") or "")
            else:
                logger.warning("%s detail %s failed (keeping the search text): %s", portal.name, job_id, exc)
                cache[job_id] = ""
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            logger.warning("%s detail %s failed (keeping the search text): %s", portal.name, job_id, exc)
            cache[job_id] = ""
        time.sleep(delay)
    return cache[job_id]
