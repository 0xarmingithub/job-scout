"""
nudge.py. Ask, once a week, about the applications that stopped moving.

The most common way an application tracker fails is not bad scoring. It is
application folders with no result recorded: no Status line at all, or a CV that
was drafted and never marked sent. Each one is a real application whose outcome
exists only in someone's memory, so the scorer never learns from it and
`job-scout calibrate` cannot count it.

Nothing here fixes that automatically, because the answer is in your head. What
it does is ask, on the weekly roundup you already get, so there is no new habit
to remember and no new message stream to start reading:

    job-scout nudge --dry-run      print it, send nothing
    job-scout nudge                send it

After `job-scout roundup` has gone out, it runs this too when applications_dir is
set (pass --no-nudge to roundup to skip it). Sent through whatever notifiers
config.yaml lists, as a note rather than an alert (Dispatcher.send_note).

## What counts as stopped

Two lists, deliberately kept apart because they need different answers.

  no status line     Nobody wrote one. The question is "what happened?"
  drafted and old    A CV was written and the folder is `--stale-days` days old
                     or more. The question is "did you send it?"

The age is counted from the date in the folder name (the trailing YYYYMMDD), not
from file times, which a copy or a git checkout resets. A folder whose name has
no date never counts as stale: its age is unknown, and a guess would nag about
the wrong things. It is still listed under "no status line" if it has none.

A folder with no CV in it is not listed. There is nothing to chase.
"""

import logging
from datetime import date

from . import patterns
from .patterns import DEFAULT_STALE_DAYS, MIN_SENT_FOR_RATES, SENT
from .redact import redact

logger = logging.getLogger(__name__)

# Read on a phone. Past this many lines it stops being a nudge and becomes
# something to deal with later, which means never.
MAX_LISTED = 6


def _label(record: dict) -> str:
    """Company and role, falling back to the folder when either is missing."""
    parts = [part for part in (record["company"], record["role"]) if part]
    return " - ".join(parts)[:70] if parts else record["folder"]


def build(records: list[dict], stale_days: int, today: date) -> tuple[str, int]:
    """(message, how many folders it is about). An empty message means nothing to ask."""
    silent, stale = [], []
    for record in records:
        if record["class"] not in ("other", "unrecorded"):
            continue
        if not record["has_cv"]:
            continue
        age = (today - record["date"]).days if record["date"] else 0
        if record["class"] == "unrecorded":
            silent.append((age, record))
        elif record["date"] and age >= stale_days:
            stale.append((age, record))

    total = len(silent) + len(stale)
    if not total:
        return "", 0

    lines = [
        f"{total} tailored application(s) have no result recorded.",
        "",
        "Each one is a CV that was written and an outcome nobody wrote down.",
    ]

    if silent:
        lines += ["", f"No status line at all ({len(silent)}). What happened?"]
        lines += _listing(silent)
    if stale:
        lines += ["", f"Drafted, untouched for {stale_days}+ days ({len(stale)}). Sent or not?"]
        lines += _listing(stale)

    lines += [
        "",
        "Update the Status: line in each notes.md. The vocabulary is in "
        "docs/applications.md.",
        "",
        _why_it_matters(records),
    ]
    return "\n".join(lines), total


def _why_it_matters(records: list[dict]) -> str:
    """
    How far off calibration is, counted rather than written down.

    A hardcoded "two to go" would be wrong the week after it was written, and
    a reminder carrying a stale number is a reminder that gets ignored.
    """
    sent = sum(record["class"] in SENT for record in records)
    short = MIN_SENT_FOR_RATES - sent
    if short > 0:
        return (
            f"{sent} application(s) have a recorded result. {short} more and "
            f"`job-scout calibrate` can say whether the score predicts anything."
        )
    return (
        f"{sent} application(s) have a recorded result, enough for "
        f"`job-scout calibrate` to state a rate. Every one above adds to it."
    )


def _listing(entries: list[tuple[int, dict]]) -> list[str]:
    ordered = sorted(entries, key=lambda pair: -pair[0])
    lines = [
        f"  {age:3}d  {_label(record)}" if age else f"       {_label(record)}"
        for age, record in ordered[:MAX_LISTED]
    ]
    hidden = len(ordered) - MAX_LISTED
    if hidden > 0:
        lines.append(f"  and {hidden} more. Full list: job-scout patterns")
    return lines


def send(settings, message: str) -> int:
    """
    Through every configured notifier, as a note. Returns how many took it.

    A note and not an alert: a weekly reminder filed under ALERT teaches the
    reader to skip alerts, and the next one is the run that actually died.
    """
    from .notifiers import Dispatcher
    from .notifiers import build as build_notifiers

    dispatcher = Dispatcher(build_notifiers(settings.notifier_specs, settings.data_dir))
    return dispatcher.send_note(message)


def command(args, settings, output_fn=print) -> int:
    """`job-scout nudge`. Returns the exit code."""
    directory = settings.applications_dir
    if directory is None:
        output_fn(
            "applications_dir is not set in config.yaml, so there are no application "
            "folders to ask about. See docs/applications.md."
        )
        return 2
    if not directory.is_dir():
        output_fn(f"{directory} is not a directory.")
        return 2

    message, total = build(
        patterns.collect(directory, settings.status_ignore_phrases), args.stale_days, date.today()
    )
    if not total:
        # Worth saying out loud rather than exiting silently: "nothing to
        # chase" and "the report broke" look identical from a timer's log.
        output_fn("Every tailored application has a recorded result. Nothing to ask.")
        return 0

    if args.dry_run:
        output_fn(message)
        return 0

    sent = send(settings, message)
    if not sent:
        output_fn(
            "The nudge reached no notifier. Run `job-scout check` to see what "
            "each one needs."
        )
        return 1
    output_fn(f"Nudge sent to {sent} notifier(s), about {total} application(s).")
    return 0


def after_roundup(settings, dry_run: bool, output_fn=print) -> None:
    """
    The nudge that rides along with the weekly roundup.

    Does nothing without applications_dir. Never raises and never changes the
    roundup's exit code: the roundup has already gone out, and a reminder that
    breaks must not take that away.
    """
    directory = settings.applications_dir
    if directory is None or not directory.is_dir():
        return
    try:
        message, total = build(
            patterns.collect(directory, settings.status_ignore_phrases), DEFAULT_STALE_DAYS,
            date.today(),
        )
        if not total:
            return
        if dry_run:
            output_fn("\n" + message)
            return
        sent = send(settings, message)
        if sent:
            output_fn(f"Nudge sent to {sent} notifier(s), about {total} application(s).")
        else:
            logger.warning("The nudge reached no notifier.")
    except Exception as exc:
        logger.warning("The nudge step failed and was skipped: %s", redact(str(exc)))
