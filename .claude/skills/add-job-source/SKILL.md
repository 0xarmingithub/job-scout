---
name: add-job-source
description: Add a new job board to Job Scout. Use when someone wants postings from a board the scout does not cover, names a national job site, or says LinkedIn and Indeed are missing jobs they see elsewhere.
---

# Adding a job board

A source is one function returning a list of dictionaries. About 40 lines. The
full contract and a complete worked example are in
[docs/adding-a-job-source.md](../../docs/adding-a-job-source.md) — read it before
writing code, and follow it rather than this file where they differ.

## Check the two cheaper options first

Do not write a scraper for a board that is already covered.

**Careerjet** aggregates many national boards through a licensed partner API. If
it covers the country, the user needs a locale setting and no code at all:

```yaml
careerjet:
  locale_code: de_DE
```

**An Apify Actor** may already exist. Search
[apify.com/store](https://apify.com/store) for the board's name. If there is one,
it is a config block — and keeping it working when the board redesigns is
somebody else's job:

```yaml
apify:
  actors:
    - id: someone/theboard-scraper
      site: theboard
      input:
        query: "{term}"
        location: "{location}"
        limit: "{results_wanted}"
```

Tell the user this costs money and check the Actor's price with them.

Only write a source when neither covers it.

## Decide what kind of source it is

**A REST API.** The easy case. Model it on
`job_scout/sources/careerjet.py`. Read the API docs — do not guess parameter
names from memory.

**A rendered page.** The board builds its results in the browser, so a plain HTTP
request returns an empty shell. Playwright and BeautifulSoup, modelled on
`job_scout/sources/jobindex.py`. Add the dependencies as an extra, never to the
core.

**A plain HTML page.** requests plus BeautifulSoup. No browser needed.

Before writing a scraper, check the board's terms and its `robots.txt`, and tell
the user what you found. This repo is honest that LinkedIn and Indeed prohibit
automated scraping; be equally honest about a new one.

## Write it

`job_scout/sources/<name>.py`:

```python
def fetch_<name>_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
```

Return dictionaries with exactly these keys:

```
title, company, location, description, url, site,
date_posted, salary, job_type, is_remote, search_term
```

Two matter most.

**`url` is the job's identity.** It is hashed into the id that stops a posting
being shown twice, so it has to be stable between runs. If the board hands out
rotating tracking URLs, find the canonical one.

**`description` is what the scorer reads.** A source returning a 100-character
teaser scores badly, and it will look like the model is stupid when it was shown
almost nothing. If the results list only has a snippet, consider fetching the
detail page.

## Three rules, and they are the point of the review

**Never raise for something the user can fix.** Missing key, missing package,
missing browser: one log line naming what to install or set, then `return []`.

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

**Never let one search term take down the others.** Catch per term, log, carry
on.

**Be polite.** Sleep between pages, respect `results_wanted`, one run a day.

## Wire it in

`job_scout/sources/__init__.py` — three edits:

1. add the name to `STANDALONE_SITES`
2. add a `_load_<name>()` that imports lazily
3. add it to the `loaders` mapping in `fetch_jobs`

The lazy import matters: someone who never uses this source must never have to
install what it needs.

Then `job_scout/dedup.py` — add it to `DEFAULT_SITE_PRIORITY`. Lower number wins
when the same advert appears on two boards. Put it above LinkedIn only if its
descriptions are genuinely fuller.

If it needs a package the core does not have, add an extra in `pyproject.toml`.
Never a core dependency.

## Test it

No network, no keys. Pull the mapping into its own function so it can be tested
directly:

```python
def test_myboard_is_skipped_without_a_key(caplog):
    assert myboard.fetch_myboard_jobs([{"term": "x"}], {}) == []
    assert "MYBOARD_API_KEY" in caplog.text


def test_myboard_maps_a_result():
    job = myboard._map_job({"title": "SRE", "permalink": "https://x/1"}, "sre")
    assert job["site"] == "myboard"
```

For a scraper, save one real page as a fixture and parse that. See
`test_jobindex_parses_a_card_from_saved_html` in `tests/test_sources.py`.

Also extend
`tests/test_run.py::test_a_run_finishes_with_none_of_the_optional_pieces` so the
new source is part of the "everything optional is absent" run.

```bash
pytest -q
ruff check job_scout tests
```

## Document it

- A docstring at the top of the module: what it needs, where to sign up, which
  country. That docstring is what people find.
- A row in the site-names table in
  [docs/configuration.md](../../docs/configuration.md).
- A commented block in `job_scout/templates/config.yaml` if it takes settings.
- A row in `job_scout/templates/.env.example` for any credential.

## Then try it for real

```bash
job-scout check                              # the new site should be recognised
job-scout run --dry-run --limit 5
```

Do not commit or push. Show the user the diff and let them decide.
