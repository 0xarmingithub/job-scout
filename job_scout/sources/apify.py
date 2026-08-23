"""
apify.py — run any Apify job-scraping Actor and fold its results into the scout.

Why this exists. LinkedIn and Indeed rate-limit datacenter IP addresses much
harder than home connections, so the direct scrapers get thin results on a cloud
VM and thinner still on GitHub Actions. Apify runs the scrape on its own
infrastructure with its own proxy pool, which is both the practical fix for that
and a cleaner position on terms of service: you are paying a platform to do the
collection under its own agreements rather than scraping the board yourself.

It costs money. Apify's free plan includes $5 of platform usage a month and does
not ask for a card; the cheapest paid plan is $29/month. Individual Actors charge
on top of that — some per result, some as a monthly rental. Check the price on
the Actor's own page before you point this at 400 postings a day.

Setup:

    1. Sign up at https://apify.com and copy your API token from
       Settings -> Integrations.
    2. Put APIFY_API_TOKEN=... in your .env file.
    3. Pick one or more Actors from https://apify.com/store and describe them in
       config.yaml under `apify:`.

There is no default Actor, deliberately: every Actor bills differently and none
of them should start charging you because a source name appeared in a list.

Configuration:

    apify:
      run_timeout_seconds: 300      # give up on one Actor run after this
      memory_mbytes: 1024           # optional; omit to use the Actor's default
      actors:
        - id: misceres/indeed-scraper
          site: indeed              # label used for duplicate priority
          input:
            position: "{term}"
            location: "{location}"
            country: "{country}"
            maxItemsPerSearch: "{results_wanted}"

        - id: bebity/linkedin-jobs-scraper
          site: linkedin
          input:
            title: "{term}"
            location: "{location}"
            rows: "{results_wanted}"

Anything in `input` is passed to the Actor untouched, except that these
placeholders are filled in from the search that triggered the run:

    {term} {location} {country} {results_wanted} {hours_old}

A placeholder that is the entire value keeps its type, so "{results_wanted}"
arrives at the Actor as the number 50, not the string "50".

Reading the results. Actors do not agree on field names, so each scout field is
filled from the first key present out of a list of known aliases — `title`,
`positionName` and `jobTitle` all become `title`. If your Actor uses a name that
is not on the list, override it per Actor:

    field_map:
      title: myWeirdTitleField
      url: myWeirdLinkField

Verified against Apify's live documentation on 2026-08-23:

    Start a run     POST https://api.apify.com/v2/actors/{id}/runs
                    where {id} is username~actor-name (tilde, not slash)
    Run status      GET  https://api.apify.com/v2/actor-runs/{runId}
    Results         GET  https://api.apify.com/v2/datasets/{datasetId}/items
    Auth            Authorization: Bearer <token>

    misceres/indeed-scraper       $3.00 per 1,000 job listings
    bebity/linkedin-jobs-scraper  $29.99/month rental plus platform usage
"""

import logging
import os
import re
import time

logger = logging.getLogger(__name__)

API_BASE = "https://api.apify.com/v2"

DEFAULT_RUN_TIMEOUT = 300
POLL_INTERVAL = 5.0
_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "TIMING-OUT"}

# Which Actor output keys map onto which scout field. First key present wins.
DEFAULT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "positionName", "jobTitle", "position", "name"),
    "company": ("company", "companyName", "employer", "organization",
                "hiringOrganization", "companyTitle"),
    "location": ("location", "jobLocation", "locationName", "formattedLocation",
                 "city", "place"),
    "description": ("description", "descriptionText", "jobDescription",
                    "jobDescriptionText", "snippet", "descriptionHTML"),
    "url": ("url", "jobUrl", "link", "jobLink", "applyUrl", "applyLink",
            "jobPostingUrl", "externalApplyLink"),
    "date_posted": ("postedAt", "publishedAt", "datePosted", "postedDate",
                    "postingDate", "listedAt", "date"),
    "salary": ("salary", "salaryText", "salaryInfo", "compensation", "salaryRange"),
    "job_type": ("jobType", "employmentType", "contractType", "workType"),
    "is_remote": ("isRemote", "remote", "workplaceType"),
}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_apify_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
    """Run every configured Actor once per search and normalise what comes back."""
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The apify source needs the requests package, which is not "
            "installed. Install it with: pip install requests"
        ) from exc

    settings = (config or {}).get("apify") or {}
    actors = settings.get("actors") or []

    token = os.environ.get("APIFY_API_TOKEN", "").strip()
    if not token:
        logger.warning(
            "Apify skipped: APIFY_API_TOKEN is not set. Get a token at "
            "https://apify.com (Settings -> Integrations) and put "
            "APIFY_API_TOKEN=... in your .env file, or remove 'apify' from your "
            "sites list."
        )
        return []

    if not actors:
        logger.warning(
            "Apify skipped: 'apify' is in your sites list but config.yaml has no "
            "`apify: actors:` block, so there is nothing to run. Actors bill "
            "individually, so this repo deliberately ships no default. See "
            "docs/adding-a-job-source.md for two ready-to-paste examples."
        )
        return []

    run_timeout = int(settings.get("run_timeout_seconds", DEFAULT_RUN_TIMEOUT))
    memory_mbytes = settings.get("memory_mbytes")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for actor in actors:
        actor_id = str(actor.get("id") or "").strip()
        if not actor_id:
            logger.error("Apify: an entry under `actors:` has no `id` — skipping it")
            continue

        site_label = str(actor.get("site") or "apify").strip().lower()
        aliases = _merge_aliases(actor.get("field_map"))

        for search in searches:
            term = str(search["term"])
            payload = _render_input(actor.get("input") or {}, search)
            logger.info("Apify: %s for '%s'", actor_id, term)

            try:
                items = _run_actor(
                    session, actor_id, payload, run_timeout, memory_mbytes,
                    limit=int(search.get("results_wanted", 50)),
                )
            except Exception as exc:
                # One Actor failing must not cost you the other sources.
                logger.error("Apify: %s failed for '%s': %s", actor_id, term, exc)
                continue

            before = len(jobs)
            for item in items:
                job = _map_item(item, aliases, site_label, term)
                url = job.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    jobs.append(job)
            logger.info(
                "Apify: %s '%s' -> %d items, %d usable",
                actor_id, term, len(items), len(jobs) - before,
            )

    return jobs


# ─── Talking to the API ───────────────────────────────────────────────────────

def _actor_path(actor_id: str) -> str:
    """Apify writes username/actor-name as username~actor-name in a URL."""
    return actor_id.replace("/", "~")


def _run_actor(session, actor_id: str, payload: dict, run_timeout: int,
               memory_mbytes, limit: int) -> list[dict]:
    """Start a run, wait for it to finish, and return its dataset items."""
    params: dict[str, object] = {"timeout": run_timeout}
    if memory_mbytes:
        params["memory"] = int(memory_mbytes)

    response = session.post(
        f"{API_BASE}/actors/{_actor_path(actor_id)}/runs",
        params=params,
        json=payload,
        timeout=60,
    )
    if response.status_code == 404:
        raise RuntimeError(
            f"Apify has no Actor called '{actor_id}'. Check the id on the "
            f"Actor's page — it is the username and the Actor name, e.g. "
            f"misceres/indeed-scraper."
        )
    if response.status_code in (401, 403):
        raise RuntimeError(
            "Apify rejected the token. Check APIFY_API_TOKEN in your .env file."
        )
    response.raise_for_status()

    run = (response.json() or {}).get("data") or {}
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError(f"Apify did not return a run id: {str(run)[:200]}")

    status, dataset_id = _wait_for_run(session, run_id, run_timeout)

    if status != "SUCCEEDED":
        raise RuntimeError(
            f"Apify run {run_id} finished as {status}. Open "
            f"https://console.apify.com/actors/runs/{run_id} for the log."
        )
    if not dataset_id:
        return []

    return _fetch_dataset(session, dataset_id, limit)


def _wait_for_run(session, run_id: str, run_timeout: int) -> tuple[str, str]:
    """Poll until the run reaches a terminal state. Returns (status, dataset id)."""
    deadline = time.monotonic() + run_timeout + 30
    while True:
        response = session.get(f"{API_BASE}/actor-runs/{run_id}", timeout=30)
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        status = str(data.get("status") or "")
        if status in _TERMINAL_STATES:
            return status, str(data.get("defaultDatasetId") or "")
        if time.monotonic() > deadline:
            _abort_run(session, run_id)
            raise RuntimeError(
                f"Apify run {run_id} was still {status or 'starting'} after "
                f"{run_timeout}s — aborted it so it stops charging. Raise "
                f"apify.run_timeout_seconds if the Actor is genuinely this slow."
            )
        time.sleep(POLL_INTERVAL)


def _abort_run(session, run_id: str) -> None:
    """Stop a run we have given up on, so it does not keep billing."""
    try:
        session.post(f"{API_BASE}/actor-runs/{run_id}/abort", timeout=30)
    except Exception as exc:  # aborting is best-effort
        logger.debug("Apify: could not abort run %s: %s", run_id, exc)


def _fetch_dataset(session, dataset_id: str, limit: int) -> list[dict]:
    response = session.get(
        f"{API_BASE}/datasets/{dataset_id}/items",
        params={"format": "json", "clean": "true", "limit": max(1, limit)},
        timeout=120,
    )
    response.raise_for_status()
    items = response.json()
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


# ─── Input templating ─────────────────────────────────────────────────────────

def _render_input(template, search: dict):
    """
    Fill {term}, {location} and friends into the Actor input.

    A value that is exactly one placeholder keeps the placeholder's type, so
    "{results_wanted}" becomes the number 50 rather than the string "50".
    """
    values = {
        "term": str(search.get("term", "")),
        "location": str(search.get("location") or ""),
        "country": str(search.get("country_indeed") or search.get("country") or ""),
        "results_wanted": int(search.get("results_wanted", 50)),
        "hours_old": int(search.get("hours_old", 72)),
    }
    return _substitute(template, values)


def _substitute(node, values: dict):
    if isinstance(node, dict):
        return {key: _substitute(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute(item, values) for item in node]
    if isinstance(node, str):
        whole = _PLACEHOLDER_RE.fullmatch(node.strip())
        if whole and whole.group(1) in values:
            return values[whole.group(1)]
        return _PLACEHOLDER_RE.sub(
            lambda match: str(values.get(match.group(1), match.group(0))), node
        )
    return node


# ─── Reading the results ──────────────────────────────────────────────────────

def _merge_aliases(field_map) -> dict[str, tuple[str, ...]]:
    """Put any per-Actor override at the front of that field's alias list."""
    aliases = {field: keys for field, keys in DEFAULT_FIELD_ALIASES.items()}
    if isinstance(field_map, dict):
        for field, key in field_map.items():
            if field in aliases and key:
                aliases[field] = (str(key),) + aliases[field]
    return aliases


def _first_present(item: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in item and item[key] not in (None, "", [], {}):
            return item[key]
    return None


def _as_text(value) -> str:
    """Flatten whatever an Actor put in a field into a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "title", "text", "value", "displayName"):
            if value.get(key):
                return _as_text(value[key])
        return ""
    if isinstance(value, (list, tuple)):
        parts = [_as_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    return str(value).strip()


def _map_item(item: dict, aliases: dict[str, tuple[str, ...]],
              site_label: str, search_term: str) -> dict:
    description = _as_text(_first_present(item, aliases["description"]))
    if "<" in description and ">" in description:
        description = _TAG_RE.sub(" ", description)
        description = re.sub(r"\s+", " ", description).strip()

    location = _as_text(_first_present(item, aliases["location"]))
    remote_raw = _first_present(item, aliases["is_remote"])
    is_remote = (
        bool(remote_raw)
        if isinstance(remote_raw, bool)
        else "remote" in f"{_as_text(remote_raw)} {location}".lower()
    )

    return {
        "title":       _as_text(_first_present(item, aliases["title"])),
        "company":     _as_text(_first_present(item, aliases["company"])),
        "location":    location,
        "description": description,
        "url":         _as_text(_first_present(item, aliases["url"])),
        "site":        site_label,
        "date_posted": _normalise_date(_as_text(_first_present(item, aliases["date_posted"]))),
        "salary":      _as_text(_first_present(item, aliases["salary"])),
        "job_type":    _as_text(_first_present(item, aliases["job_type"])),
        "is_remote":   is_remote,
        "search_term": search_term,
    }


def _normalise_date(value: str) -> str:
    """
    Return an ISO date when the Actor gave a real timestamp, otherwise whatever
    it said. Actors report anything from "2026-08-22T09:00:00.000Z" to "Today",
    and a wrong-looking date is better than a fabricated one.
    """
    if not value:
        return ""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else value
