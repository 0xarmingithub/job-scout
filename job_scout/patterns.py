"""
patterns.py. What your application folders say when you read them together.

Every application folder has a notes.md with a status, and may have a jd.md and
a gap-analysis.md with a coverage table (docs/applications.md). Read one at a
time they are a record of what happened. Read together they answer questions no
single folder can:

  - Which requirement keeps coming back as Not Covered, across every posting?
    That is the thing to learn, or the kind of role to stop applying for.
  - Where do applications actually stop? Drafted and never sent is a different
    failure from sent and rejected, and it is often the commoner one.
  - Which kinds of role get furthest?
  - What has been sitting untouched for weeks?

    job-scout patterns
    job-scout patterns --stale-days 30
    job-scout patterns --output reports/patterns.md

This reads. It changes nothing, and it never edits a notes.md, a profile or a
threshold. `job-scout calibrate` is the companion that asks whether the score
predicted the outcome; this one asks what the applications themselves say.

## The one number that is not measured here

Conversion rate. Below a handful of sent applications with a recorded result,
a rate says more about which folders exist than about what converts, and a
percentage over five applications is an anecdote. The funnel prints the counts,
says how many are missing, and stops there. It starts stating rates when there
are enough.

## Role families

"Which kinds of role get furthest" groups applications by the family their
title belongs to. Families come from profile.yaml:

    role_families:                    # optional
      - name: Platform and SRE
        keywords: [platform, sre, reliability, devops]
      - name: Architecture
        keywords: [architect, architecture]

A title belongs to a family when it contains any of its keywords. When
role_families is absent there is one family per entry of target_roles, and a
title belongs to it when it contains the words that make that entry specific
(the entry "Site Reliability Engineer" is matched by "site" and "reliability",
not by "engineer"). A title can belong to several families, or to none.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import outcomes
from .calibrate import _MIN_DECIDED as MIN_SENT_FOR_RATES
from .config import ConfigError
from .track_record import classify

# How stale a drafted application has to be before it is worth naming.
DEFAULT_STALE_DAYS = 21

# Statuses that mean the application left the building.
SENT = ("applied", "interviewing", "offer", "rejected", "no_response")

# A gap-analysis coverage table row:
#   | JD requirement | Priority | Coverage | Evidence | Tailoring action |
# Only the first three columns are read. Bold markers are stripped.
_TABLE_ROW = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_NOT_COVERED = re.compile(r"not\s*covered", re.IGNORECASE)
_WEAK = re.compile(r"\bweak", re.IGNORECASE)
_COVERED = re.compile(r"strongl|^covered|\bfully\b|transferable", re.IGNORECASE)

# Words that carry no identity in a requirement line, so counting them would
# just rank "experience" first every time.
_REQUIREMENT_NOISE = {
    "and", "or", "the", "a", "an", "of", "in", "on", "for", "to", "with", "at",
    "experience", "years", "strong", "good", "knowledge", "skills", "ability",
    "working", "work", "understanding", "proven", "solid", "hands", "level",
    "plus", "must", "should", "have", "having", "is", "are", "be", "as", "by",
    "e", "g", "eg", "etc", "via", "from", "into", "across", "within", "using",
    "role", "team", "teams", "including", "such", "other", "more", "than",
    "requirement", "requirements", "p0", "p1", "p2", "not", "covered",
    "hands-on", "preferred", "familiarity", "familiar", "advantage", "bonus",
    "nice", "ideally", "desirable", "equivalent", "similar", "related",
    "relevant", "deep", "demonstrated", "track", "record", "min", "least",
}

# Words in a job title that do not say what kind of job it is. Dropped when a
# family is derived from a target role, so "Platform Engineer" is recognised by
# "platform" and not by "engineer", which every engineering title shares.
_GENERIC_TITLE_WORDS = {
    "and", "or", "the", "of", "for", "in", "at", "to", "a", "an",
    "senior", "junior", "lead", "staff", "principal", "head", "chief", "associate",
    "engineer", "engineering", "developer", "specialist", "consultant", "manager",
    "ii", "iii", "iv", "i",
}


# --- Role families ------------------------------------------------------------

@dataclass(frozen=True)
class Family:
    """A kind of role. `terms` are lowercase words or phrases."""

    name: str
    terms: tuple[str, ...]
    require_all: bool = False


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9+#.]*", text.lower())


def _same_word(a: str, b: str) -> bool:
    """Equal, or the same stem: "architect" and "architecture", "platform" and "platforms"."""
    if a == b:
        return True
    return min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a))


def _has_term(role_words: list[str], role_text: str, term: str) -> bool:
    if " " in term:
        return term in role_text
    return any(_same_word(word, term) for word in role_words)


def family_from_title(title: str) -> Family | None:
    """The family a target role stands for, or None when the title has no words."""
    words = _words(title)
    key = [word for word in dict.fromkeys(words) if word not in _GENERIC_TITLE_WORDS and len(word) > 1]
    if not key:
        key = list(dict.fromkeys(words))
    if not key:
        return None
    return Family(name=title.strip(), terms=tuple(key), require_all=True)


def families_from_profile(profile: dict) -> list[Family]:
    """
    The role families for this profile: role_families when given, else one per
    target_roles entry. Raises ConfigError for a role_families entry it cannot read.
    """
    declared = profile.get("role_families")
    if declared is not None:
        if not isinstance(declared, list):
            raise ConfigError(
                "profile.yaml: role_families must be a list, each entry a name or "
                "a mapping with 'name' and 'keywords'."
            )
        families: list[Family] = []
        for index, entry in enumerate(declared):
            if isinstance(entry, str) and entry.strip():
                families.append(Family(entry.strip(), (entry.strip().lower(),)))
                continue
            if isinstance(entry, dict):
                name = str(entry.get("name") or "").strip()
                keywords = entry.get("keywords")
                if (
                    name and isinstance(keywords, list)
                    and keywords and all(isinstance(item, str) and item.strip() for item in keywords)
                ):
                    families.append(
                        Family(name, tuple(item.strip().lower() for item in keywords))
                    )
                    continue
            raise ConfigError(
                f"profile.yaml: role_families[{index}] must be a name, or a mapping with "
                "a 'name' and a non-empty list of 'keywords'."
            )
        return families

    families = []
    for title in profile.get("target_roles") or []:
        family = family_from_title(str(title))
        if family is not None and family.name not in {f.name for f in families}:
            families.append(family)
    return families


def families_for(role: str, families: list[Family]) -> list[str]:
    """Names of every family this job title belongs to."""
    role_words = _words(role)
    role_text = " ".join(role_words)
    matched = []
    for family in families:
        tests = [_has_term(role_words, role_text, term) for term in family.terms]
        if all(tests) if family.require_all else any(tests):
            matched.append(family.name)
    return matched


# --- Reading the folders ------------------------------------------------------

def _folder_date(name: str) -> date | None:
    match = re.search(r"-(\d{8})$", name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def coverage_rows(app_dir: Path) -> list[dict]:
    """
    Every row of the gap-analysis coverage table.

    Returns [{"requirement", "priority", "coverage"}]. Header and separator
    rows are dropped by requiring at least three cells and rejecting a cell
    that is all dashes.
    """
    path = Path(app_dir) / "gap-analysis.md"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    rows = []
    for line in text.splitlines():
        match = _TABLE_ROW.match(line.strip())
        if not match:
            continue
        # Bold markers are removed everywhere, not just at the ends. A cell
        # reading "File-based integration: **EDI**" would otherwise keep the
        # opening pair and print as "**EDI".
        cells = [
            cell.replace("**", "").strip()
            for cell in match.group("cells").split("|")
        ]
        if len(cells) < 3:
            continue
        requirement, priority, coverage = cells[0], cells[1], cells[2]
        if not requirement or set(requirement) <= set("-: "):
            continue
        if requirement.lower().startswith("jd requirement"):
            continue
        rows.append({
            "requirement": requirement,
            "priority": priority,
            "coverage": coverage,
        })
    return rows


def collect(applications_dir: Path, ignore: tuple[str, ...] = ()) -> list[dict]:
    """One record per application folder, whether or not it has a status."""
    records = []
    for app_dir in outcomes.application_folders(applications_dir):
        status = outcomes.status_for(app_dir, ignore) or ""
        company, role = outcomes.company_and_role(app_dir)
        records.append({
            "folder": app_dir.name,
            "date": _folder_date(app_dir.name),
            "company": company,
            "role": role,
            "status": status,
            "class": classify(status) if status else "unrecorded",
            "coverage": coverage_rows(app_dir),
            "has_cv": any(
                (app_dir / name).exists() for name in ("CV.tex", "CV.md", "CV-ats.md", "CV.pdf")
            ),
        })
    return records


# --- The sections -------------------------------------------------------------

def _requirement_tokens(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_][\w+#/.-]*", text.lower(), re.UNICODE)
    return {
        word.strip("./-")
        for word in words
        if len(word.strip("./-")) > 2 and word.strip("./-") not in _REQUIREMENT_NOISE
    }


def section_funnel(records: list[dict]) -> list[str]:
    counts = Counter(record["class"] for record in records)
    sent = sum(counts[name] for name in SENT)
    out = [
        "## Where applications stop",
        "",
        f"{len(records)} application folder(s).",
        "",
        "| Stage | Count |",
        "|---|---|",
    ]
    order = ("unrecorded", "other", "withdrawn", "applied", "interviewing", "offer", "rejected")
    labels = {
        "unrecorded": "No **Status:** line at all",
        "other": "Drafted, never marked sent",
        "withdrawn": "Read and chosen not to apply",
        "applied": "Sent, no answer yet",
        "interviewing": "Reached interview",
        "offer": "Offer",
        "rejected": "Rejected",
    }
    for name in order:
        if counts.get(name):
            out.append(f"| {labels[name]} | {counts[name]} |")

    leaked = counts.get("unrecorded", 0) + counts.get("other", 0)
    out.append("")
    if leaked:
        out.append(
            f"**{leaked} of {len(records)} never reached an employer as far as these "
            f"folders know.** Some of those were sent and the status line was never "
            f"updated, which is the same thing from here: an application whose result "
            f"is only in someone's memory is one the scorer never learns from. See the "
            f"Status line convention in docs/applications.md."
        )
    if sent < MIN_SENT_FOR_RATES:
        out.append("")
        out.append(
            f"No conversion rate is stated. {sent} sent application(s) with a "
            f"recorded result is below the floor of {MIN_SENT_FOR_RATES}, and a "
            f"percentage over that many is an anecdote."
        )
    return out


def section_recurring_gaps(records: list[dict], limit: int = 15) -> list[str]:
    """
    What keeps coming back as Not Covered.

    Counted by application, not by table row, so a posting that names a tool
    four times counts once. That matters: the question is how many employers
    wanted it, not how verbose their posting was.

    A stop word list is not enough on its own. A skill you have turns up in Not
    Covered rows too, inside qualified requirements like "architecture
    workshops facilitation", and ranking on raw counts puts it at the top of a
    list about things you do every day.

    So the test is not how often a term is missing. It is whether any
    application, anywhere, marked it covered. One does, and the term is
    something the record can answer in some form; the gap is in the qualifier
    around it, not in the term. Zero do, and the term is a hole. What survives
    is specific: a modelling language, a vendor product, a certification.

    This is deliberately strict, and it drops real near-misses. A requirement
    marked Transferable in one application takes its term off this list even
    though the next employer may not accept the transfer. That case belongs in
    the gap analysis for that posting, which already handles it properly. This
    list answers a narrower question: what is missing every single time.
    """
    per_token_apps: dict[str, set[str]] = defaultdict(set)
    per_token_examples: dict[str, set[str]] = defaultdict(set)
    weak_apps: dict[str, set[str]] = defaultdict(set)
    covered_apps: dict[str, set[str]] = defaultdict(set)
    analysed = 0

    for record in records:
        if not record["coverage"]:
            continue
        analysed += 1
        for row in record["coverage"]:
            coverage = row["coverage"]
            tokens = _requirement_tokens(row["requirement"])
            if _NOT_COVERED.search(coverage):
                for token in tokens:
                    per_token_apps[token].add(record["folder"])
                    per_token_examples[token].add(row["requirement"][:70])
            elif _WEAK.search(coverage):
                for token in tokens:
                    weak_apps[token].add(record["folder"])
            elif _COVERED.search(coverage):
                for token in tokens:
                    covered_apps[token].add(record["folder"])

    out = [
        "## What keeps coming back as a gap",
        "",
        f"Read from {analysed} gap-analysis coverage table(s). A term is counted "
        f"once per application, however often the posting repeats it, and any "
        f"term that some other application marked covered is left out. What is "
        f"left is what the record cannot answer anywhere.",
        "",
    ]
    if not per_token_apps:
        out.append("No `Not Covered` rows found. Either the gaps are closed or the "
                   "coverage tables are not being written in the standard format.")
        return out

    specific = [
        (token, folders)
        for token, folders in per_token_apps.items()
        if len(folders) >= 2 and not covered_apps.get(token)
    ]
    if not specific:
        out.append("Nothing recurs. Every unmet requirement so far is a one-off.")
        return out

    ranked = sorted(specific, key=lambda item: (-len(item[1]), item[0]))
    out.append("| Term | Not covered in | Also weak in | A requirement that named it |")
    out.append("|---|---|---|---|")
    for token, folders in ranked[:limit]:
        example = sorted(per_token_examples[token])[0].replace("|", "/")
        out.append(
            f"| `{token}` | {len(folders)} | {len(weak_apps.get(token, ()))} "
            f"| {example} |"
        )

    hidden = len(ranked) - limit
    if hidden > 0:
        out.append("")
        out.append(f"{hidden} more term(s) recur; raise `--top` to see them.")

    out.append("")
    out.append(
        "Read this as a shortlist, not a to-do list. A term at the top is one "
        "several employers asked for and nothing in your own record of experience answers. "
        "Closing it is one option; deciding to stop applying for roles that "
        "need it is an equally good one, and cheaper."
    )
    return out


def section_families(records: list[dict], families: list[Family]) -> list[str]:
    tallies: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        for name in families_for(record["role"], families) or ["unclassified"]:
            tallies[name][record["class"]] += 1
            tallies[name]["total"] += 1

    out = [
        "## Which kinds of role get furthest",
        "",
        "A posting counts in every family its title matches, so the columns sum "
        "to more than the number of applications. Forcing one label per role "
        "would decide the answer before counting it.",
        "",
    ]
    if not families:
        out += [
            "profile.yaml has no role_families and no target_roles, so every "
            "application is unclassified. Add target_roles, or a role_families "
            "list, to group them.",
            "",
        ]
    out += [
        "| Family | Applications | Sent | Reached interview | Chose not to apply |",
        "|---|---|---|---|---|",
    ]
    for name, counts in sorted(tallies.items(), key=lambda item: (-item[1]["total"], item[0])):
        sent = sum(counts[stage] for stage in SENT)
        out.append(
            f"| {name} | {counts['total']} | {sent} | "
            f"{counts['interviewing'] + counts['offer']} | {counts['withdrawn']} |"
        )
    return out


def section_stale(records: list[dict], stale_days: int, today: date) -> list[str]:
    stale = []
    for record in records:
        if record["class"] not in ("other", "unrecorded"):
            continue
        if not record["date"]:
            continue
        age = (today - record["date"]).days
        if age >= stale_days and record["has_cv"]:
            stale.append((age, record))

    out = [
        "## Drafted, tailored, and still sitting there",
        "",
        f"A CV was written and the folder has not moved in {stale_days} days or "
        f"more. Either it was sent and the status line was never updated, or the "
        f"work is finished and unused.",
        "",
    ]
    if not stale:
        out.append("Nothing. Every tailored application has a current status.")
        return out

    out.append("| Days | Application | Status |")
    out.append("|---|---|---|")
    # Sort on the age only. Two folders of the same age would otherwise be
    # compared as dicts, which raises.
    for age, record in sorted(stale, key=lambda pair: -pair[0]):
        status = (record["status"] or "no status line").replace("|", "/")[:60]
        out.append(f"| {age} | `{record['folder']}` | {status} |")
    out.append("")
    out.append(
        f"{len(stale)} folder(s). Each one is either a lost result or an "
        f"unfinished application, and the two are indistinguishable from here."
    )
    return out


# --- Putting it together ------------------------------------------------------

def render(
    applications_dir: Path,
    profile: dict | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    top: int = 15,
    today: date | None = None,
    ignore: tuple[str, ...] = (),
) -> str:
    today = today or date.today()
    records = collect(applications_dir, ignore)
    if not records:
        return f"No application folders under {applications_dir}."

    families = families_from_profile(profile or {})
    parts = [
        f"# Application patterns, {today.isoformat()}",
        "",
        "Read from the application folders themselves. Nothing here is a model's "
        "opinion; every number is a count of files on disk.",
        "",
    ]
    for section in (
        section_funnel(records),
        section_recurring_gaps(records, top),
        section_families(records, families),
        section_stale(records, stale_days, today),
    ):
        parts.extend(section)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def command(args, settings, output_fn=print) -> int:
    """`job-scout patterns`. Returns the exit code."""
    directory = settings.applications_dir
    if directory is None:
        output_fn(
            "applications_dir is not set in config.yaml, so there are no application "
            "folders to read. See docs/applications.md."
        )
        return 2
    if not directory.is_dir():
        output_fn(f"{directory} is not a directory.")
        return 2

    try:
        report = render(
            directory, settings.profile, args.stale_days, args.top,
            ignore=settings.status_ignore_phrases,
        )
    except ConfigError as exc:
        output_fn(f"Configuration problem:\n\n{exc}\n")
        return 2

    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8")
        output_fn(f"Wrote {target}")
    else:
        output_fn(report)
    return 0
