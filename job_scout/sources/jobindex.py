"""
jobindex.py. Jobindex.dk, the largest Danish job board.

Denmark only. Skip this source entirely unless you are looking for work in
Denmark; it is here because it is the one board where a large share of Danish
postings never appear on LinkedIn or Indeed.

This one costs more to set up than the others. JobIndex builds its results page
in the browser, so a plain HTTP request returns an empty shell. Playwright drives
a real headless Chromium, and BeautifulSoup parses what comes back.

    pip install playwright beautifulsoup4 lxml
    playwright install chromium --with-deps

If Playwright or the browser is missing, this source logs one line saying which
command to run and returns nothing.

Page structure, confirmed by inspection in May 2026. Job boards redesign; if this
source suddenly returns nothing, this is the part that broke:

    Search URL  https://www.jobindex.dk/jobsoegning?q=TERM[&page=N]
    Job card    contains <a href="/bruger/dine-job/{id}/gem"> ("save job")
    Title       first <h4> > <a> in the card
    Location    first short text sibling after the <h4>
    Description first two <p> tags in the card body
    Apply URL   the "Se jobbet" anchor
    Company     the alt text of the logo <img>
"""

import logging
import re
import time
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jobindex.dk"
SEARCH_URL = "https://www.jobindex.dk/jobsoegning"

PAGE_DELAY = 1.0
BROWSER_TIMEOUT_MS = 30_000


def fetch_jobindex_jobs(searches: list[dict], config: dict | None = None) -> list[dict]:
    """
    Scrape JobIndex for every search that lists `jobindex` in its sites.

    Per-search keys used: term, results_wanted.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "JobIndex skipped: playwright is not installed. Install it with: "
            "pip install playwright && playwright install chromium --with-deps "
            ", or remove 'jobindex' from your sites list."
        )
        return []

    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        logger.warning(
            "JobIndex skipped: beautifulsoup4 is not installed. Install it with: "
            "pip install beautifulsoup4 lxml"
        )
        return []

    from ..config import merge_advanced

    # JobIndex is scraped rather than queried, so it gets at least a
    # second between pages whatever the global setting says.
    page_delay = max(1.0, float(merge_advanced(config or {})["source_delay_seconds"]))

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    playwright = sync_playwright().start()
    try:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            logger.warning(
                "JobIndex skipped: Chromium is not installed (%s). Install it "
                "with: playwright install chromium --with-deps", exc,
            )
            return []

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            java_script_enabled=True,
        )
        page = context.new_page()
        page.set_default_timeout(BROWSER_TIMEOUT_MS)

        _accept_cookies(page)

        for search in searches:
            term = str(search["term"])
            results_wanted = int(search.get("results_wanted", 20))
            logger.info("JobIndex: '%s' (want %d)", term, results_wanted)

            page_num = 1
            collected = 0

            while collected < results_wanted:
                # Quoting the term makes JobIndex treat it as a phrase, which
                # returns relevant hits instead of loose single-word matches.
                params = f"q=%27{quote_plus(term)}%27"
                if page_num > 1:
                    params += f"&page={page_num}"

                try:
                    page.goto(f"{SEARCH_URL}?{params}", wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector('a[href*="/bruger/dine-job/"]', timeout=5_000)
                    except Exception:
                        pass  # no results on this page. Handled below
                    html = page.content()
                except Exception as exc:
                    logger.error(
                        "JobIndex: could not load page %d for '%s': %s",
                        page_num, term, exc,
                    )
                    break

                found, has_next = parse_search_page(html, term)
                if not found:
                    break

                for job in found:
                    url = job.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        jobs.append(job)
                        collected += 1
                        if collected >= results_wanted:
                            break

                if not has_next:
                    break
                page_num += 1
                time.sleep(page_delay)

            logger.info("JobIndex: '%s' -> %d jobs", term, collected)

        browser.close()
    finally:
        playwright.stop()

    return jobs


def _accept_cookies(page) -> None:
    """Click through the consent wall once, so later pages are not blocked."""
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15_000)
        page.locator("button:has-text('Accepter')").first.click(timeout=5_000)
        logger.debug("JobIndex: cookie consent accepted")
    except Exception:
        logger.debug("JobIndex: no cookie banner to dismiss")


# ─── HTML parsing ─────────────────────────────────────────────────────────────

def _soup(html: str):
    """
    Parse with lxml when it is installed, and Python's own parser when it is
    not. lxml is faster and more forgiving of the malformed markup real pages
    contain, but not having it should cost you speed, not the source.
    """
    from bs4 import BeautifulSoup, FeatureNotFound

    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        logger.debug("JobIndex: lxml not installed, falling back to html.parser")
        return BeautifulSoup(html, "html.parser")


def parse_search_page(html: str, search_term: str) -> tuple[list[dict], bool]:
    """Parse one rendered results page. Returns (jobs, there_is_a_next_page)."""
    soup = _soup(html)
    jobs: list[dict] = []

    # Every job card carries a "save job" link. The trailing /gem excludes the
    # "register interest" dropdown links, which share the same URL prefix but
    # sit in a different part of the page.
    for save_link in soup.find_all("a", href=re.compile(r"/bruger/dine-job/.+/gem$")):
        card = _find_card_root(save_link)
        if card is None:
            continue
        job = _extract_job(card, save_link, search_term)
        if job:
            jobs.append(job)

    has_next = bool(soup.find("a", string=re.compile(r"N[æa]ste", re.IGNORECASE)))
    return jobs, has_next


def _find_card_root(save_link):
    """
    Walk up from the "save job" anchor to the card that contains the title.

    The anchor sits about six levels below the card root. Eight levels of walking
    covers that with room for a layout tweak.
    """
    element = save_link
    for _ in range(8):
        element = element.parent if element else None
        if element is None:
            return None
        name = getattr(element, "name", None)
        if name in ("body", "main", "html", None):
            return None
        if name == "div" and element.find("h4"):
            return element
    return None


def _extract_job(card, save_link, search_term: str) -> dict | None:
    heading = card.find("h4")
    if not heading:
        return None
    title_anchor = heading.find("a")
    if not title_anchor:
        return None
    title = title_anchor.get_text(strip=True)
    if not title:
        return None

    # Prefer the "Se jobbet" action link, that is the canonical advert URL.
    action = _find_action_link(save_link, "Se jobbet")
    raw_url = (action.get("href") if action else None) or title_anchor.get("href", "")
    url = _resolve_url(raw_url)

    location = _extract_location(card, heading)
    location_lower = location.lower()

    paragraphs = [p.get_text(strip=True) for p in card.find_all("p") if p.get_text(strip=True)]

    return {
        "title":       title,
        "company":     _extract_company(card),
        "location":    location,
        "description": " ".join(paragraphs[:2]),
        "url":         url,
        "site":        "jobindex",
        "date_posted": "",  # not shown in the list view
        "salary":      "",  # not shown in the list view
        "job_type":    "",  # not shown in the list view
        "is_remote":   "hjemmearbejde" in location_lower or "remote" in location_lower,
        "search_term": search_term,
    }


def _find_action_link(save_link, text: str):
    parent = save_link.parent
    if parent is None:
        return None
    for anchor in parent.find_all("a"):
        if text.lower() in anchor.get_text(strip=True).lower():
            return anchor
    return None


def _extract_company(card) -> str:
    """The logo image's alt text is the most reliable company name on the card."""
    for image in card.find_all("img"):
        alt = (image.get("alt") or "").strip()
        if alt and alt != "Søgeord:":
            return alt
    for anchor in card.find_all("a", href=True):
        href = anchor.get("href", "")
        if href.startswith("http") and "jobindex.dk" not in href:
            text = anchor.get_text(strip=True)
            if text:
                return text
    return ""


def _extract_location(card, heading) -> str:
    """The location is the first short text block after the title."""
    for sibling in heading.find_next_siblings():
        if sibling.find("h4") or sibling.find("h3"):
            continue
        text = sibling.get_text(" ", strip=True)
        if text and len(text) < 80 and not text.startswith(("Do you", "Vi ")):
            return text
    return ""


def _resolve_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    return url
