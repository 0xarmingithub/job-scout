"""
outcomes.py. Turn application folders into the outcomes file the scorer reads.

You keep one folder per application, each with a notes.md that has a
**Status:** line (see docs/applications.md). This module reads those lines and
writes outcomes.csv, which track_record.py then feeds to the scorer and
`job-scout calibrate` joins to what the scout scored.

    job-scout outcomes              write the outcomes file
    job-scout outcomes --print      show what it would write, write nothing

It also runs at the start of `job-scout run` when `applications_dir` is set in
config.yaml, so the scorer always sees the current state of your folders.

The output header is exactly `title,company,status,folder`. track_record.py
needs only the first three columns and ignores `folder`; the fourth is there so
a wrong row can be traced back to the folder it came from.

Your own wording can get in the way of the reader. If a status line uses a
phrase that contains a status word but means something else (a step of your own
process that happens to include the word "interview", say), list the phrase under
`status_ignore_phrases` in config.yaml. It is removed from the status before
anything is matched, so it cannot be mistaken for an employer interview.
"""

import csv
import logging
import re
from pathlib import Path

from .redact import redact

logger = logging.getLogger(__name__)

GENERATED_HEADER = ("title", "company", "status", "folder")

_STATUS_LINE = re.compile(
    r"^\s*[-*]?\s*\*\*Status:\*\*\s*(.+)$", re.IGNORECASE | re.MULTILINE
)

# Heading prefixes to strip off a jd.md first heading before reading company and role.
_HEADING_PREFIXES = ("job description", "jd", "job ad", "job posting")

# An em dash, an en dash and a middle dot, written as escapes so this file holds
# no dash glyphs of its own. They are data: the jd.md and notes.md files this
# reads use them as separators.
_DASHES = (chr(0x2014), chr(0x2013))
_MIDDOT = chr(0x00B7)

_INTERVIEW_HINTS = ("interview", "screen", "round ", "technical call", "video call")
_REJECTED_HINTS = ("reject",)

# `Company:` and `Role title:` at the top of a jd.md, with or without the
# surrounding asterisks. When these are present they are the answer and no
# guessing is needed.
_FRONT_MATTER = re.compile(
    r"^\s*\**\s*(company|role title)\s*\**\s*:\s*\**\s*(.+?)\s*\**\s*$",
    re.IGNORECASE,
)

# Nobody's employer is called this. A jd.md that says so is recording that the
# company was not stated in the posting, which is not the same as a name.
_NOT_A_COMPANY = {"unknown", "n/a", "na", "not stated", "not listed", "undisclosed"}

# Everything after one of these in a Company line is a description of the
# company rather than part of its name: "Contoso (a Fabrikam company)",
# "Contoso - garden tools", "Contoso, Springfield".
_COMPANY_TAIL = ("(", *_DASHES, " / ", " - ", ", ")

# Separators that put a company on one side of a heading and a role on the
# other. A bare hyphen is only a separator with spaces around it, or every
# hyphenated word would split.
_HEADING_SPLIT = re.compile(
    r"\s*(?:[" + "".join(_DASHES) + _MIDDOT + r"|:,]|(?<= )-(?= ))\s*"
)


# --- Reading one folder -------------------------------------------------------

def _clean(text: str, ignore: tuple[str, ...] = ()) -> str:
    """Drop the phrases the person asked to ignore and collapse whitespace."""
    cleaned = text
    for phrase in ignore:
        if phrase.strip():
            cleaned = re.sub(re.escape(phrase.strip()), "", cleaned, flags=re.IGNORECASE)
    trim = " -" + "".join(_DASHES) + _MIDDOT + ","
    return re.sub(r"\s+", " ", cleaned).strip(trim)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _stem(folder: str) -> str:
    """The folder name without its trailing -YYYYMMDD."""
    return re.sub(r"-\d{8}$", "", folder)


def _read(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[:limit]) if limit else text


def _read_front_matter(app_dir: Path) -> tuple[str, str]:
    """(company, role) from jd.md's leading key lines. Either may be empty."""
    found: dict[str, str] = {}
    for line in _read(app_dir / "jd.md", limit=30).splitlines():
        match = _FRONT_MATTER.match(line)
        if match:
            found.setdefault(match.group(1).lower(), match.group(2).strip())
    return _trim_company(found.get("company", "")), found.get("role title", "")


def _trim_company(value: str) -> str:
    """
    The company's name, without the paragraph of context after it.

    These lines are written for a human reading the folder later, so they carry
    a valuation, an employee count or a parent group. None of that helps match
    the row against a job board's own spelling of the name.
    """
    text = value.strip()
    for marker in _COMPANY_TAIL:
        text = text.split(marker)[0]
    text = text.strip(" " + "".join(_DASHES) + _MIDDOT + ",:*")
    return "" if text.lower() in _NOT_A_COMPANY else text


def _heading(app_dir: Path) -> str:
    """The jd.md first heading, with any "Job description <dash>" prefix removed."""
    heading = ""
    for line in _read(app_dir / "jd.md").splitlines():
        line = line.strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            break
    if not heading:
        return ""

    for separator in (*_DASHES, ":", "-"):
        head, sep, tail = heading.partition(separator)
        if sep and head.strip().lower().rstrip(":") in _HEADING_PREFIXES:
            return tail.strip()
    return heading


def _stem_starts_with(stem: str, candidate: str) -> bool:
    """Does the folder open with this candidate company's first word?"""
    tokens = [token for token in _slug(candidate).split("-") if len(token) >= 2]
    return bool(tokens) and stem.startswith(tokens[0])


def _company_from_heading(heading: str, stem: str) -> tuple[str, str]:
    """
    (company, role) when the heading names the company on one end.

    The folder decides. It is always named company-first, so a candidate is
    only accepted when the folder starts with it. That is what stops
    "Tech Lead, Embedded Platform (Contoso)" from reading "Embedded Platform"
    as the employer.
    """
    bracket = re.search(r"\(([^()]{2,40})\)\s*$", heading)
    if bracket and _stem_starts_with(stem, bracket.group(1)):
        return bracket.group(1).strip(), heading[: bracket.start()].strip(" ,-")

    breaks = list(_HEADING_SPLIT.finditer(heading))
    if not breaks:
        return "", heading

    first, last = breaks[0], breaks[-1]
    candidates = (
        (heading[: first.start()].strip(), heading[first.end():].strip()),
        (heading[last.end():].strip(), heading[: last.start()].strip()),
    )
    for company, role in candidates:
        if company and role and _stem_starts_with(stem, company):
            return company, role
    return "", heading


def _company_from_folder(stem: str, role: str) -> str:
    """
    Last resort: the folder's leading words that the role does not use.

    `contoso-platform-engineer` with the role "Platform Engineer" leaves
    "contoso". When the role uses every word, there is nothing to find and the
    first word is the best guess available.
    """
    role_tokens = set(_slug(role).split("-"))
    leading: list[str] = []
    for token in stem.split("-"):
        if token in role_tokens:
            break
        leading.append(token)
    if not leading:
        leading = stem.split("-")[:1]
    return " ".join(leading).title()


def company_and_role(app_dir: Path) -> tuple[str, str]:
    """
    (company, role) for one application folder.

    Three sources, best first. The `Company:` line a jd.md was saved with is
    authoritative. Failing that the first heading is split, with the folder
    deciding which half is the employer. Failing that the folder itself is read.

    Company matters more than it looks: it is the column the scorer shows the
    model as real outcome history, and the key `calibrate` joins on to find
    what the scout scored a posting before it became an application.
    """
    stem = _stem(app_dir.name)
    front_company, front_role = _read_front_matter(app_dir)
    heading = _heading(app_dir)

    company, role = ("", "")
    if heading:
        company, role = _company_from_heading(heading, stem)
    role = front_role or role or heading or stem.replace("-", " ").title()
    company = front_company or company or _company_from_folder(stem, role)
    return company, role


def status_for(app_dir: Path, ignore: tuple[str, ...] = ()) -> str | None:
    """
    The normalised status text for one application, or None if it has none.

    `ignore` is the config's status_ignore_phrases: text to remove first.
    """
    notes = app_dir / "notes.md"
    if not notes.is_file():
        return None
    body = _read(notes)

    match = _STATUS_LINE.search(body)
    if not match:
        return None

    status = _clean(match.group(1), ignore)
    if not status:
        return None

    # A rejection that reached interview is a different signal from a rejection
    # at screening, and the difference is usually recorded in the body rather
    # than the status line.
    lowered = status.lower()
    if any(hint in lowered for hint in _REJECTED_HINTS):
        body_lowered = _clean(body, ignore).lower()
        if any(hint in body_lowered for hint in _INTERVIEW_HINTS):
            return "rejected after interview"

    return status


# --- Reading every folder -----------------------------------------------------

def application_folders(applications_dir: Path) -> list[Path]:
    """
    The application folders, oldest name first.

    A folder whose name starts with "." or "_" is not an application (a
    template, an archive), so it is skipped everywhere this is used.
    """
    directory = Path(applications_dir)
    if not directory.is_dir():
        return []
    return [
        path for path in sorted(directory.iterdir())
        if path.is_dir() and not path.name.startswith((".", "_"))
    ]


def silent(applications_dir: Path, ignore: tuple[str, ...] = ()) -> list[str]:
    """
    Application folders with no readable **Status:** line.

    These are the ones the scorer never hears about and `calibrate` cannot use.
    Each one is a real application whose result is sitting only in someone's
    memory, so the list is printed rather than left to be noticed.
    """
    return [
        folder.name for folder in application_folders(applications_dir)
        if not status_for(folder, ignore)
    ]


def collect(applications_dir: Path, ignore: tuple[str, ...] = ()) -> list[dict]:
    """Every application with a readable Status line, oldest folder first."""
    rows: list[dict] = []
    for folder in application_folders(applications_dir):
        status = status_for(folder, ignore)
        if not status:
            continue
        company, role = company_and_role(folder)
        rows.append({
            "title": role or folder.name,
            "company": company,
            "status": status,
            "folder": folder.name,
        })
    return rows


# --- Writing the file ---------------------------------------------------------

def is_generated(path: Path) -> bool:
    """
    True if writing to this path cannot destroy a hand-kept file.

    A file we wrote has our four-column header. A file somebody keeps by hand
    usually has the three columns of the documented format. If `outcomes_file`
    points at one of those, rewriting it would erase their work, so it is left
    alone and the run says why.
    """
    path = Path(path)
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False
    first = text.splitlines()[0] if text.strip() else ""
    if not first.strip():
        return True
    header = tuple(cell.strip().lower() for cell in next(csv.reader([first]), []))
    return header == GENERATED_HEADER


def write(rows: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(GENERATED_HEADER)
        for row in rows:
            writer.writerow([row["title"], row["company"], row["status"], row["folder"]])


def summary(rows: list[dict]) -> str:
    """How the scorer will classify these statuses, so a wrong one shows here."""
    from .track_record import classify

    counts: dict[str, int] = {}
    for row in rows:
        key = classify(row["status"])
        counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))


def render_rows(rows: list[dict]) -> str:
    """The rows as `status  title at company`, one per line, for --print."""
    if not rows:
        return ""
    width = max(len(row["status"]) for row in rows)
    lines = []
    for row in rows:
        label = " at ".join(part for part in (row["title"], row["company"]) if part)
        lines.append(f"{row['status']:<{width}}  {label}")
    return "\n".join(lines)


def silent_notice(names: list[str]) -> str:
    if not names:
        return ""
    lines = [
        f"\n{len(names)} application folder(s) have no **Status:** line, so their "
        f"result is invisible to both the scorer and calibrate:"
    ]
    lines += [f"  {name}" for name in names]
    lines.append("  The Status line format is in docs/applications.md.")
    return "\n".join(lines)


# --- Running it ---------------------------------------------------------------

def refresh(settings, dispatcher, dry_run: bool = False) -> None:
    """
    Rebuild the outcomes file at the start of a run, when applications_dir is set.

    Never raises, because outcome history improves scoring and a run that cannot
    read it is still worth doing. It is not silent though: a rebuild that fails
    means the run scored without the real conversion data, and a failure that
    only reaches a log file is the kind that costs someone a week.
    """
    directory = settings.applications_dir
    if directory is None:
        return

    def trouble(message: str) -> None:
        logger.error("%s", message)
        if not dry_run:
            dispatcher.send_alert(message)

    try:
        if not directory.is_dir():
            trouble(
                f"applications_dir is {directory}, which is not a directory. This run "
                "scored without application outcomes. Create the folder, or remove "
                "applications_dir from config.yaml."
            )
            return

        target = settings.outcomes_path
        if not is_generated(target):
            trouble(
                f"{target} looks like a hand-kept outcomes file (it has no 'folder' "
                "column), so it was not overwritten and this run scored with it as it "
                "is. With applications_dir set the file is generated: remove "
                "outcomes_file from config.yaml, or point it at a new path."
            )
            return

        ignore = settings.status_ignore_phrases
        rows = collect(directory, ignore)
        write(rows, target)
        quiet = silent(directory, ignore)
        logger.info(
            "Outcomes: %d from %s%s", len(rows), directory,
            f", {len(quiet)} folder(s) with no Status line" if quiet else "",
        )
    except Exception as exc:
        trouble(redact(
            f"Rebuilding the outcomes file failed ({type(exc).__name__}: {exc}), so "
            "this run scored without application outcomes. Run `job-scout outcomes "
            "--print` to see why."
        ))


def command(args, settings, input_fn=input, output_fn=print, interactive: bool = False) -> int:
    """`job-scout outcomes`. Returns the exit code."""
    directory = Path(args.applications_dir).expanduser() if args.applications_dir else (
        settings.applications_dir
    )
    if directory is None:
        output_fn(
            "applications_dir is not set. Add it to config.yaml, or pass "
            "--applications-dir PATH. See docs/applications.md."
        )
        return 2
    if not directory.is_dir():
        output_fn(f"{directory} is not a directory.")
        return 2

    ignore = settings.status_ignore_phrases
    rows = collect(directory, ignore)
    quiet = silent(directory, ignore)

    if args.show:
        text = render_rows(rows)
        output_fn(text if text else f"No **Status:** lines found under {directory}.")
        notice = silent_notice(quiet)
        if notice:
            output_fn(notice)
        return 0

    target = Path(args.output).expanduser() if args.output else settings.outcomes_path
    if not is_generated(target):
        output_fn(
            f"{target} looks like a hand-kept outcomes file (it has no 'folder' "
            "column). Not overwritten. Pass --output PATH to write somewhere else."
        )
        return 1
    write(rows, target)
    output_fn(f"Wrote {len(rows)} outcome(s) to {target}")
    if rows:
        output_fn(f"  {summary(rows)}")
    else:
        output_fn(f"  No **Status:** lines found under {directory}. Scoring works without them.")
    notice = silent_notice(quiet)
    if notice:
        output_fn(notice)

    from . import privacy

    privacy.offer_employers(
        sorted({row["company"] for row in rows if row["company"]}),
        privacy.resolve_path(config_dir=settings.config_dir),
        input_fn=input_fn,
        output_fn=output_fn,
        interactive=interactive and not args.no_prompt,
    )
    return 0
