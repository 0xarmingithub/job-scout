"""
careerjet.py — Careerjet partner search API.

Careerjet is an aggregator with a licensed partner API, which makes it the
lowest-risk source in this repo: you are querying an interface built to be
queried, not scraping a page that asks you not to.

Sign up at https://www.careerjet.com/partners/api to get a key. Registration
asks for the URL of the site that will use the API and the IP address it will
call from, and the API rejects calls whose Referer and user_ip do not match what
you registered. That is why all three of these are required and none of them has
a default:

    CAREERJET_API_KEY   your partner key
    CAREERJET_REFERER   the site URL you registered, e.g. https://example.com/jobs
    CAREERJET_USER_IP   the public IP the request comes from

If any is missing the source logs which one and returns nothing. It never stops
a run.

API reference: https://www.careerjet.com/partners/api

Authentication:
    Basic auth — key as username, empty password.
    Authorization: Basic base64(API_KEY + ":")

Endpoint:
    GET https://search.api.careerjet.net/v4/query

Parameters used here:
    locale_code   e.g. en_GB, en_US, da_DK, de_DE. Set per search or globally.
    keywords      the search term
    location      city or region; omit for the whole country
    page          1-10
    page_size     1-100
    sort          relevance | date | salary
    fragment_size how many characters of description to return
    user_ip       the registered IP
    user_agent    a descriptive string
"""

import base64
import logging
import os
import time
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://search.api.careerjet.net/v4/query"

# Neutral default. Override with `locale_code` in config.yaml under `careerjet:`
# or per search. en_GB returns English-language listings.
DEFAULT_LOCALE = "en_GB"

# A longer excerpt gives the scorer more to work with.
FRAGMENT_SIZE = 500

# Polite delay between pages.
PAGE_DELAY = 0.5

USER_AGENT = "job-scout/1.0 (+https://github.com/0xarmingithub/job-scout)"

_SALARY_INTERVAL = {"Y": "/yr", "M": "/mo", "W": "/wk", "D": "/day", "H": "/hr"}


def fetch_careerjet_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
    """
    Fetch from Careerjet for every search that lists `careerjet` in its sites.

    Per-search keys used: term, results_wanted, location, locale_code.
    Global defaults may be set under a top-level `careerjet:` block in config.yaml.
    """
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The careerjet source needs the requests package, which is not "
            "installed. Install it with: pip install requests"
        ) from exc

    settings = (config or {}).get("careerjet") or {}

    api_key = os.environ.get("CAREERJET_API_KEY", "").strip()
    referer = os.environ.get("CAREERJET_REFERER", "").strip() or str(
        settings.get("referer") or ""
    ).strip()
    user_ip = os.environ.get("CAREERJET_USER_IP", "").strip() or str(
        settings.get("user_ip") or ""
    ).strip()

    missing = [
        name
        for name, value in (
            ("CAREERJET_API_KEY", api_key),
            ("CAREERJET_REFERER", referer),
            ("CAREERJET_USER_IP", user_ip),
        )
        if not value
    ]
    if missing:
        logger.warning(
            "Careerjet skipped: %s not set. Careerjet rejects calls whose "
            "Referer and IP do not match the ones you registered at "
            "https://www.careerjet.com/partners/api — set all three in your .env "
            "file, or remove 'careerjet' from your sites list.",
            ", ".join(missing),
        )
        return []

    default_locale = str(settings.get("locale_code") or DEFAULT_LOCALE)

    session = requests.Session()
    session.headers.update({
        "Authorization": _auth_header(api_key),
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Referer": referer,
    })

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for search in searches:
        term = str(search["term"])
        results_wanted = int(search.get("results_wanted", 20))
        location = str(search.get("location") or "")
        locale_code = str(search.get("locale_code") or default_locale)

        logger.info("Careerjet: '%s' (want %d, locale %s)", term, results_wanted, locale_code)

        page = 1
        collected = 0

        while collected < results_wanted:
            params = {
                "locale_code":   locale_code,
                "keywords":      term,
                "page":          page,
                "page_size":     min(100, results_wanted - collected),
                "sort":          "date",
                "fragment_size": FRAGMENT_SIZE,
                "user_ip":       user_ip,
                "user_agent":    USER_AGENT,
            }
            if location:
                params["location"] = location

            data = _get(session, params, term, page)
            if data is None:
                break

            if data.get("type") == "LOCATIONS":
                # Careerjet could not resolve the location. Retry without it
                # rather than returning nothing.
                logger.warning(
                    "Careerjet: could not resolve location '%s' for '%s' — "
                    "retrying nationwide", location, term,
                )
                params.pop("location", None)
                data = _get(session, params, term, page)
                if data is None:
                    break

            if data.get("type") != "JOBS":
                logger.warning(
                    "Careerjet: unexpected response type '%s' for '%s'",
                    data.get("type"), term,
                )
                break

            raw_jobs = data.get("jobs") or []
            if not raw_jobs:
                break

            for raw in raw_jobs:
                url = (raw.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append(_map_job(raw, term))
                collected += 1
                if collected >= results_wanted:
                    break

            total_pages = int(data.get("pages") or 1)
            if page >= total_pages or page >= 10:  # the API caps out at page 10
                break
            page += 1
            time.sleep(PAGE_DELAY)

        logger.info("Careerjet: '%s' -> %d jobs", term, collected)

    return jobs


# ─── Internals ────────────────────────────────────────────────────────────────

def _get(session, params: dict, term: str, page: int) -> dict | None:
    import requests

    try:
        response = session.get(API_ENDPOINT, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error("Careerjet: request failed for '%s' page %d: %s", term, page, exc)
    except ValueError as exc:
        logger.error("Careerjet: invalid JSON for '%s' page %d: %s", term, page, exc)
    return None


def _auth_header(api_key: str) -> str:
    """Careerjet wants base64(api_key + ':')."""
    credentials = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {credentials}"


def _map_job(raw: dict, search_term: str) -> dict:
    """Map one Careerjet result onto the scout schema."""
    location = (raw.get("locations") or "").strip()
    location_lower = location.lower()

    return {
        "title":       (raw.get("title") or "").strip(),
        "company":     (raw.get("company") or "").strip(),
        "location":    location,
        "description": (raw.get("description") or "").strip(),
        "url":         (raw.get("url") or "").strip(),
        "site":        "careerjet",
        "date_posted": _parse_date(raw.get("date") or ""),
        "salary":      _format_salary(raw),
        "job_type":    "",  # not returned by the API
        "is_remote":   "remote" in location_lower or "hjemmearbejde" in location_lower,
        "search_term": search_term,
    }


def _parse_date(date_str: str) -> str:
    """Careerjet sends RFC-2822 dates. Convert to ISO, or pass through unchanged."""
    if not date_str:
        return ""
    try:
        return parsedate_to_datetime(date_str).date().isoformat()
    except (TypeError, ValueError):
        return date_str


def _format_salary(raw: dict) -> str:
    salary = (raw.get("salary") or "").strip()
    if salary:
        return salary

    minimum = raw.get("salary_min")
    maximum = raw.get("salary_max")
    currency = (raw.get("salary_currency_code") or "").strip()
    interval = _SALARY_INTERVAL.get(raw.get("salary_type") or "", "")

    try:
        if minimum and maximum:
            return f"{currency} {int(minimum):,}-{int(maximum):,}{interval}".strip()
        if minimum:
            return f"{currency} {int(minimum):,}+{interval}".strip()
    except (TypeError, ValueError):
        return ""
    return ""
