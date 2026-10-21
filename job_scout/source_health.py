"""
source_health.py. Notice a source that has gone quiet or started returning junk.

Ported in spirit from the portal health check in MadsLorentzen/ai-job-search
(MIT). Three checks, all run on evidence the run already holds:

  * Yield history. Each run appends how many jobs each source returned. A source
    that returns nothing for ZERO_RUNS_IN_A_ROW runs in a row, after it had
    returned jobs earlier, is reported. An error is not a zero. Errors are
    already reported as FAILED.
  * Degraded output. Flags on the jobs themselves: no company on any result,
    HTML tags or undecoded entities in titles, links that leave the portal.
  * Rate limits. An HTTP 429 is reported as rate-limited, never as broken.

Not ported yet: the sentinel probe that re-runs a known query when a source
looks broken.
"""

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ZERO_RUNS_IN_A_ROW = 3
KEEP_RUNS = 10
HISTORY_FILE = "source_history.json"

# Domains a job link from each portal should point at. A link elsewhere means
# the parser has picked up something that is not the posting. Left out on
# purpose: Jobnet and Jobindex. Both link external ads to the employer's own
# application page or to LinkedIn, so those links leave the portal by design.
# A live run flagged 65 of Jobindex's links this way before this was fixed.
PORTAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "jobbank": ("jobbank.dk",),
    "jobdanmark": ("jobdanmark.dk",),
}

# HTML tags in a title mean the parser kept markup. Entities such as &amp; are
# decoded by the Danish portal mapping, so they are not a sign of breakage.
_TAG = re.compile(r"<[a-zA-Z/]")


def is_rate_limited(message: str) -> bool:
    lowered = message.lower()
    return "429" in lowered or "rate limit" in lowered or "too many requests" in lowered


def degraded_reasons(site: str, jobs: list[dict]) -> list[str]:
    """Reasons a source's output looks broken. Empty when it looks fine."""
    if not jobs:
        return []
    reasons = []
    if all(not (job.get("company") or "").strip() for job in jobs):
        reasons.append(f"no company on any of {len(jobs)} results")
    bad_titles = sum(1 for job in jobs if _TAG.search(job.get("title") or ""))
    if bad_titles:
        reasons.append(f"HTML tags in {bad_titles} titles")
    domains = PORTAL_DOMAINS.get(site)
    if domains:
        off_portal = sum(1 for job in jobs if not _on_domain(job.get("url") or "", domains))
        if off_portal:
            reasons.append(f"{off_portal} links off the portal")
    return reasons


def _on_domain(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def load_history(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Source history at %s is unreadable. Starting it again.", path)
        return {}
    return {str(k): [int(n) for n in v] for k, v in data.items() if isinstance(v, list)}


def record(path: Path, counts: dict[str, int]) -> dict[str, list[int]]:
    """Append this run's counts and keep the last KEEP_RUNS per source."""
    history = load_history(path)
    for site, count in counts.items():
        runs = history.setdefault(site, [])
        runs.append(int(count))
        del runs[:-KEEP_RUNS]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
    tmp.replace(path)
    return history


def silent_sources(history: dict[str, list[int]], ran: set[str]) -> list[str]:
    """Sources that ran, returned nothing for the last ZERO_RUNS_IN_A_ROW runs, and had jobs before."""
    silent = []
    for site in sorted(ran):
        runs = history.get(site, [])
        if len(runs) <= ZERO_RUNS_IN_A_ROW:
            continue
        recent, earlier = runs[-ZERO_RUNS_IN_A_ROW:], runs[:-ZERO_RUNS_IN_A_ROW]
        if all(n == 0 for n in recent) and any(n > 0 for n in earlier):
            silent.append(site)
    return silent


def check_run(data_dir: Path, report, record_history: bool = True) -> list[str]:
    """
    Return one line per health problem in this run. Writes the yield history
    unless record_history is False (dry runs).
    """
    counts = {name: n for name, n in report.per_source.items() if name not in report.errors}
    path = data_dir / HISTORY_FILE
    if record_history:
        history = record(path, counts)
    else:
        history = load_history(path)
        for site, count in counts.items():
            history.setdefault(site, []).append(count)

    lines = []
    for site in silent_sources(history, set(counts)):
        lines.append(
            f"{site} returned 0 jobs for {ZERO_RUNS_IN_A_ROW} runs in a row. "
            "It returned jobs before, so the source may be blocked or its parser may be broken."
        )
    for site, reasons in sorted(report.degraded.items()):
        lines.append(f"{site} output looks broken: {'; '.join(reasons)}.")
    return lines
