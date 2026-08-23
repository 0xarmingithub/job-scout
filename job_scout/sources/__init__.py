"""
sources — where postings come from.

Every source is optional. A source that is not installed, not configured, or
simply broken today logs one line and returns nothing. It never takes the run
down with it, because a run that dies on LinkedIn being slow is a run you stop
trusting.

Adding a source means writing one function that returns a list of job dicts in
this shape, and adding one line to SOURCES below:

    {
        "title":       str,
        "company":     str,
        "location":    str,
        "description": str,
        "url":         str,   # must be unique and stable — it is the job's id
        "site":        str,   # the source name, used for dedup priority
        "date_posted": str,   # ISO date, or "" if the board does not say
        "salary":      str,   # free text, or ""
        "job_type":    str,   # free text, or ""
        "is_remote":   bool,
        "search_term": str,   # which of your searches found it
    }

See docs/adding-a-job-source.md.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Sites that python-jobspy handles in a single call.
JOBSPY_SITES = frozenset({"linkedin", "indeed", "glassdoor", "zip_recruiter", "google"})

# Sites with their own module. Name here is what you write in `sites:`.
STANDALONE_SITES = ("jobindex", "careerjet", "apify")

ALL_SITES = tuple(sorted(JOBSPY_SITES)) + STANDALONE_SITES


@dataclass
class FetchReport:
    """What each source actually did, for the log and the run summary."""

    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.per_source.values())

    def summary(self) -> str:
        if not self.per_source and not self.errors:
            return "no sources ran"
        parts = [f"{name}: {count}" for name, count in sorted(self.per_source.items())]
        parts += [f"{name}: FAILED" for name in sorted(self.errors)]
        return " | ".join(parts)


def fetch_jobs(searches: list[dict], config: dict | None = None) -> tuple[list[dict], FetchReport]:
    """
    Run every configured search against every configured source.

    Returns (jobs, report). Jobs are deduplicated by URL within this call;
    cross-board duplicates of the same advert are handled later by
    dedup.dedup_by_content.
    """
    config = config or {}
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    report = FetchReport()

    def _absorb(name: str, jobs: list[dict]) -> None:
        added = 0
        for job in jobs:
            url = (job.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_jobs.append(job)
            added += 1
        report.per_source[name] = report.per_source.get(name, 0) + added
        logger.info("%s: %d new unique jobs", name, added)

    # ── JobSpy-backed boards ──────────────────────────────────────────────────
    jobspy_searches = []
    for search in searches:
        sites = [s for s in _sites_for(search) if s in JOBSPY_SITES]
        if sites:
            jobspy_searches.append({**search, "sites": sites})

    if jobspy_searches:
        try:
            from .jobspy_source import fetch_jobspy_jobs
            _absorb("jobspy", fetch_jobspy_jobs(jobspy_searches))
        except Exception as exc:
            logger.error("JobSpy failed (skipping): %s", exc, exc_info=True)
            report.errors["jobspy"] = str(exc)

    # ── Sources with their own module ─────────────────────────────────────────
    loaders = {
        "jobindex": _load_jobindex,
        "careerjet": _load_careerjet,
        "apify": _load_apify,
    }
    for name, loader in loaders.items():
        matching = [s for s in searches if name in _sites_for(s)]
        if not matching:
            continue
        try:
            fetch = loader()
            _absorb(name, fetch(matching, config))
        except Exception as exc:
            logger.error("%s failed (skipping): %s", name, exc, exc_info=True)
            report.errors[name] = str(exc)

    logger.info("Fetched %d unique jobs — %s", len(all_jobs), report.summary())
    return all_jobs, report


def _sites_for(search: dict) -> list[str]:
    sites = search.get("sites") or ["linkedin", "indeed"]
    return [str(site).strip().lower() for site in sites]


def _load_jobindex():
    from .jobindex import fetch_jobindex_jobs
    return fetch_jobindex_jobs


def _load_careerjet():
    from .careerjet import fetch_careerjet_jobs
    return fetch_careerjet_jobs


def _load_apify():
    from .apify import fetch_apify_jobs
    return fetch_apify_jobs


def unknown_sites(searches: list[dict]) -> list[str]:
    """Site names in the config that no source handles. Used by `job-scout check`."""
    known = set(ALL_SITES)
    found: set[str] = set()
    for search in searches:
        found.update(site for site in _sites_for(search) if site not in known)
    return sorted(found)
