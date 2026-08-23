"""
jobspy_source.py. LinkedIn, Indeed, Glassdoor, ZipRecruiter and Google Jobs.

All of these go through python-jobspy, which is the only dependency you need for
the default setup.

Read this before turning LinkedIn or Indeed on: both prohibit automated scraping
in their terms of service. Using them is your decision and your risk. The lower-
risk sources in this repo are Careerjet, which is a licensed partner API, and
Apify, which runs the scraping on its own platform under its own terms. See the
disclaimer in README.md.

A note on where you run this. LinkedIn and Indeed rate-limit datacenter IP
addresses far harder than home connections. On a cloud VM you will get fewer
results than on your laptop, and on GitHub Actions fewer still. If you need this
to work from a datacenter, use the Apify source instead.
"""

import logging

logger = logging.getLogger(__name__)


def fetch_jobspy_jobs(searches: list[dict]) -> list[dict]:
    """
    Run each search through python-jobspy and normalise the results.

    Each search dict may contain:
        term            (required) what to search for
        sites           which boards, e.g. [linkedin, indeed]
        location        free-text location
        country_indeed  Indeed's country, e.g. "Denmark", "USA"
        hours_old       only postings newer than this many hours (default 72)
        results_wanted  per board (default 50)
        is_remote       True to ask for remote-only
    """
    try:
        from jobspy import scrape_jobs
    except ImportError as exc:
        raise RuntimeError(
            "The linkedin/indeed/glassdoor/zip_recruiter/google sources need the "
            "python-jobspy package, which is not installed. Install it with: "
            "pip install python-jobspy"
        ) from exc

    jobs: list[dict] = []

    for search in searches:
        term = str(search["term"])
        sites = search.get("sites") or ["linkedin", "indeed"]
        location = search.get("location") or ""
        hours_old = int(search.get("hours_old", 72))
        results_wanted = int(search.get("results_wanted", 50))
        country_indeed = search.get("country_indeed") or search.get("country") or ""

        logger.info("JobSpy: '%s' in '%s' on %s", term, location, sites)

        kwargs = {
            "site_name": sites,
            "search_term": term,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "linkedin_fetch_description": True,
            "verbose": 0,
        }
        if location:
            kwargs["location"] = location
        if country_indeed:
            kwargs["country_indeed"] = country_indeed
        if search.get("is_remote"):
            kwargs["is_remote"] = True

        try:
            frame = scrape_jobs(**kwargs)
        except Exception as exc:
            # One board being unhappy must not cost you the other seven searches.
            logger.error("JobSpy scrape failed for '%s': %s", term, exc)
            continue

        if frame is None or getattr(frame, "empty", True):
            logger.warning("JobSpy: no results for '%s'", term)
            continue

        before = len(jobs)
        for _, row in frame.iterrows():
            url = str(row.get("job_url") or "").strip()
            if not url:
                continue
            jobs.append({
                "title":       str(row.get("title") or "").strip(),
                "company":     str(row.get("company") or "").strip(),
                "location":    str(row.get("location") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "url":         url,
                "site":        str(row.get("site") or "").strip(),
                "date_posted": str(row.get("date_posted") or "").strip(),
                "salary":      _format_salary(row),
                "job_type":    str(row.get("job_type") or "").strip(),
                "is_remote":   bool(row.get("is_remote", False)),
                "search_term": term,
            })
        logger.info("JobSpy: '%s' -> %d rows", term, len(jobs) - before)

    return jobs


def _format_salary(row) -> str:
    """Human-readable salary string, or "" when the board did not say."""
    minimum = row.get("min_amount")
    maximum = row.get("max_amount")
    currency = str(row.get("currency") or "").strip()
    interval = str(row.get("interval") or "").strip()

    def _number(value) -> str:
        return f"{int(float(value)):,}"

    try:
        if minimum and maximum:
            return f"{currency} {_number(minimum)}-{_number(maximum)} / {interval}".strip()
        if minimum:
            return f"{currency} {_number(minimum)}+ / {interval}".strip()
    except (TypeError, ValueError):
        return ""
    return ""
