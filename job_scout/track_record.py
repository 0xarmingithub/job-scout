"""
track_record.py. Feed real application outcomes back into the scorer.

Completely optional. If the file is not there, the scorer works exactly as it
otherwise would; nothing degrades and nothing warns.

The file is a CSV in your config directory called outcomes.csv:

    title,company,status
    Platform Engineer,Northwind Energy,rejected
    IoT Solution Architect,Vestbridge Systems,interviewing
    Cloud Engineer,Halden Data,offer

Only those three columns are required. Extra columns are ignored, so you can
keep a date or a note alongside them.

Recognised statuses. Anything else is counted but not classified:

    applied | screened | interviewing | offer | rejected | withdrawn | no_response

The point is not bookkeeping. It is that the scorer is told which kinds of role
actually converted for you and which did not, and can weigh a new posting
against that instead of against the profile alone.
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# How many individual outcomes to name in the prompt. Past this the prompt grows
# without telling the model anything new.
_MAX_LISTED = 25

_REQUIRED_COLUMNS = ("title", "company", "status")

_OFFER_HINTS = ("offer",)
_REJECTED_HINTS = ("reject", "declined", "unsuccessful")
_INTERVIEW_HINTS = ("interview", "screen", "technical call", "video call", "onsite")
_WITHDRAWN_HINTS = ("withdrawn", "withdrew", "skipped", "not applied")
_NO_RESPONSE_HINTS = ("no response", "no_response", "ghosted", "silence")


def classify(status_text: str) -> str:
    """Map a free-text status onto the vocabulary above."""
    text = (status_text or "").lower().strip()
    if not text:
        return "other"
    if any(hint in text for hint in _OFFER_HINTS):
        return "offer"
    if any(hint in text for hint in _REJECTED_HINTS):
        return "rejected"
    if any(hint in text for hint in _INTERVIEW_HINTS):
        return "interviewing"
    if any(hint in text for hint in _WITHDRAWN_HINTS):
        return "withdrawn"
    if any(hint in text for hint in _NO_RESPONSE_HINTS):
        return "no_response"
    if "applied" in text or "submitted" in text:
        return "applied"
    return "other"


def read_outcomes(path: Path) -> list[dict]:
    """
    Read outcomes.csv. Returns [] if the file is absent, empty, or unreadable.
    A malformed file is a warning in the log, never an error that stops a run.
    """
    path = Path(path)
    if not path.exists():
        return []

    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        logger.warning("Could not read %s (%s). Scoring without outcome data", path, exc)
        return []

    rows: list[dict] = []
    reader = csv.DictReader(text.splitlines())
    fieldnames = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
    missing = [column for column in _REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        logger.warning(
            "%s is missing the column(s) %s. Expected a header row of "
            "'title,company,status'. Scoring without outcome data.",
            path, ", ".join(missing),
        )
        return []

    for raw in reader:
        normalised = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in raw.items()
            if key is not None
        }
        title = normalised.get("title", "")
        company = normalised.get("company", "")
        status = normalised.get("status", "")
        if not (title or company) or not status:
            continue
        rows.append({
            "title": title,
            "company": company,
            "status": status,
            "class": classify(status),
        })

    if rows:
        logger.info("Loaded %d application outcome(s) from %s", len(rows), path)
    return rows


def build_context(path: Path) -> str:
    """
    Return a short block of real outcomes for the scoring prompt, or "" when
    there is no data, the caller then tells the model there is none.
    """
    rows = read_outcomes(path)
    if not rows:
        return ""

    positive = [r for r in rows if r["class"] in ("interviewing", "offer")]
    negative = [r for r in rows if r["class"] in ("rejected", "no_response")]
    # Roles the candidate read and decided not to apply for. This is a judgement
    # about the job, made with the full posting in front of them, the same
    # judgement the scorer is trying to reproduce, so it is the most direct
    # negative evidence available. Listing it separately keeps it from being
    # read as "applied and lost".
    skipped = [r for r in rows if r["class"] == "withdrawn"]

    lines = [
        f"{len(rows)} applications with a recorded outcome; "
        f"{len(positive)} reached interview or offer."
    ]

    def _describe(row: dict) -> str:
        label = " at ".join(part for part in (row["title"], row["company"]) if part)
        return f'  - "{label}" -> {row["status"]}'

    groups = (
        ("Converted", positive),
        ("Applied and did not convert", negative),
        ("Read and chose not to apply", skipped),
    )
    total_listable = sum(len(group) for _, group in groups)

    listed = 0
    for group_name, group in groups:
        if not group:
            continue
        lines.append(f"{group_name}:")
        for row in group:
            if listed >= _MAX_LISTED:
                lines.append(f"  - (+{total_listable - listed} more)")
                return "\n".join(lines)
            lines.append(_describe(row))
            listed += 1

    return "\n".join(lines)
