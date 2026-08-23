# Adding a job source

About 40 lines of work. A source is one function that returns a list of
dictionaries.

Do this when your country has a board that the existing sources do not reach —
which is most countries. jobindex.dk in Denmark, StepStone in Germany,
Werk.nl in the Netherlands, Seek in Australia. National boards carry postings
that never reach LinkedIn.

## Before you write anything

Two cheaper options first.

**Does Careerjet already cover it?** Careerjet aggregates a lot of national
boards and is a licensed API, so you get the listings without writing a scraper
or breaking anyone's terms. Add `careerjet` to your `sites` and set the locale.

**Is there an Apify Actor?** Search [apify.com/store](https://apify.com/store).
If there is, you need no code at all — just a block in `config.yaml`. It costs
money, and it is somebody else's job to keep it working when the board changes
its markup.

Write a source when neither of those covers it.

## The contract

One function. This shape:

```python
def fetch_myboard_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
    ...
```

`searches` is every search whose `sites` list names your source. `config` is the
whole `config.yaml`, so you can read your own settings block from it.

Return a list of dictionaries with exactly these keys:

```python
{
    "title":       str,   # required
    "company":     str,   # required
    "location":    str,
    "description": str,   # the scorer reads this — get as much as you can
    "url":         str,   # required, unique, stable. This is the job's identity.
    "site":        str,   # your source name, used for duplicate priority
    "date_posted": str,   # ISO date, or "" if the board does not say
    "salary":      str,   # free text, or ""
    "job_type":    str,   # free text, or ""
    "is_remote":   bool,
    "search_term": str,   # which search found it
}
```

Two of those matter more than the rest.

**`url` is the job's identity.** It is hashed into the id that stops a posting
being shown twice. It must be stable between runs. If the board hands out
rotating tracking URLs, find the canonical one — otherwise the same job arrives
every day. (There is a title-and-company fallback for exactly this case, but it
only looks back 7 days.)

**`description` is what the scorer reads.** A source that returns a 100-character
teaser will score badly, and it will look like the model is stupid when the
problem is that it was shown almost nothing. If the board only gives a snippet in
the results list, consider fetching the detail page.

## Three rules

**Never raise for a condition the user can fix.** Missing key, missing package,
missing browser: log one line naming what to install or set, and return `[]`. The
dispatcher catches exceptions too, but a caught exception produces a traceback in
the log where a sentence would do.

```python
token = os.environ.get("MYBOARD_API_KEY", "").strip()
if not token:
    logger.warning(
        "MyBoard skipped: MYBOARD_API_KEY is not set. Get a key at "
        "https://myboard.example/api and put MYBOARD_API_KEY=... in your .env "
        "file, or remove 'myboard' from your sites list."
    )
    return []
```

**Never let one search take down the others.** Catch per search term, log, carry
on. Eight terms and one bad response should cost you one term.

**Be polite.** Sleep between pages. Respect `results_wanted`. One run a day.

## Worked example

`job_scout/sources/myboard.py`:

```python
"""
myboard.py — MyBoard.example.

A REST API. Needs MYBOARD_API_KEY in .env. Sign up at
https://myboard.example/api — free for personal use.
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

API = "https://api.myboard.example/v1/search"
PAGE_DELAY = 0.5


def fetch_myboard_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The myboard source needs the requests package. "
            "Install it with: pip install requests"
        ) from exc

    token = os.environ.get("MYBOARD_API_KEY", "").strip()
    if not token:
        logger.warning(
            "MyBoard skipped: MYBOARD_API_KEY is not set. Get a key at "
            "https://myboard.example/api, or remove 'myboard' from your sites."
        )
        return []

    settings = (config or {}).get("myboard") or {}
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    jobs: list[dict] = []
    seen: set[str] = set()

    for search in searches:
        term = str(search["term"])
        wanted = int(search.get("results_wanted", 50))
        logger.info("MyBoard: '%s' (want %d)", term, wanted)

        try:
            response = session.get(
                API,
                params={
                    "q": term,
                    "location": search.get("location", ""),
                    "limit": wanted,
                    "country": settings.get("country", "gb"),
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # One bad term must not cost you the other seven.
            logger.error("MyBoard: '%s' failed: %s", term, exc)
            continue

        for raw in payload.get("results", []):
            url = (raw.get("permalink") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append({
                "title":       (raw.get("title") or "").strip(),
                "company":     (raw.get("employer") or "").strip(),
                "location":    (raw.get("place") or "").strip(),
                "description": (raw.get("body") or "").strip(),
                "url":         url,
                "site":        "myboard",
                "date_posted": (raw.get("published") or "")[:10],
                "salary":      (raw.get("pay") or "").strip(),
                "job_type":    (raw.get("contract") or "").strip(),
                "is_remote":   bool(raw.get("remote")),
                "search_term": term,
            })

        time.sleep(PAGE_DELAY)

    logger.info("MyBoard: %d jobs", len(jobs))
    return jobs
```

## Wiring it in

Three small edits in `job_scout/sources/__init__.py`:

```python
STANDALONE_SITES = ("jobindex", "careerjet", "apify", "myboard")


def _load_myboard():
    from .myboard import fetch_myboard_jobs
    return fetch_myboard_jobs


# in fetch_jobs(), add to the loaders mapping:
    loaders = {
        "jobindex": _load_jobindex,
        "careerjet": _load_careerjet,
        "apify": _load_apify,
        "myboard": _load_myboard,
    }
```

The import is deferred on purpose. Someone who never uses your source should
never have to install what it needs.

Then add it to the duplicate priority in `job_scout/dedup.py`:

```python
DEFAULT_SITE_PRIORITY = {
    "linkedin": 0,
    ...
    "myboard": 7,
}
```

Where it goes depends on whether your board's descriptions are fuller than
LinkedIn's. Lower number wins.

## Optional dependencies

If your source needs a package the core does not, add an extra rather than a
dependency — nobody should install a browser for a source they do not use.

```toml
[project.optional-dependencies]
myboard = ["some-client>=2.0"]
```

## Testing it

Tests must pass with no network and no keys. Test the pure parts directly and
stub the rest:

```python
def test_myboard_is_skipped_without_a_key(caplog):
    assert myboard.fetch_myboard_jobs([{"term": "x"}], {}) == []
    assert "MYBOARD_API_KEY" in caplog.text


def test_myboard_maps_a_result():
    raw = {"title": "SRE", "employer": "Acme", "permalink": "https://x/1"}
    job = myboard._map_job(raw, "sre")     # pull the mapping into its own function
    assert job["site"] == "myboard"
    assert set(job) == EXPECTED_KEYS
```

For a scraper, save one real page of HTML as a fixture and parse that. See
`test_jobindex_parses_a_card_from_saved_html` in `tests/test_sources.py`.

Run it:

```bash
pytest -q
```

## Documenting it

- A docstring at the top of your module saying what it needs and where to sign
  up. That docstring is the documentation people actually find.
- A row in the site-names table in [configuration.md](configuration.md).
- A commented block in `job_scout/templates/config.yaml` if it needs settings.

## Then send it

Pull requests welcome. Include the tests, and say in the description which
country the board covers and whether it needs an account.
