"""
cli.py, the `job-scout` command.

    job-scout run                    do a run
    job-scout run --dry-run          score and print, record nothing, send nothing
    job-scout run --limit 5          stop after 5 postings reach the scorer
    job-scout check                  tell me what is and is not set up
    job-scout stats                  what the seen-jobs database says
    job-scout roundup                the best of the last 7 days, in one message
    job-scout ask                    collect answers to an outstanding question
    job-scout init ~/my-job-search   put a config.yaml and profile.yaml somewhere
    job-scout version

Every command takes --config-dir and --data-dir, so your profile does not have
to live inside this repository. The same paths can be set with
JOB_SCOUT_CONFIG_DIR and JOB_SCOUT_DATA_DIR.
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import (
    CONFIG_FILENAME,
    PROFILE_FILENAME,
    ConfigError,
    Settings,
    load_settings,
    resolve_config_dir,
    seed_config_dir,
    seed_tailoring,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-scout",
        description="Search job boards, score every posting against your "
                    "profile, and send you the good ones.",
    )
    parser.add_argument("--version", action="version", version=f"job-scout {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    def _common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--config-dir",
            help="directory holding config.yaml and profile.yaml "
                 "(default: the current directory, then this repo)",
        )
        sub.add_argument(
            "--data-dir",
            help="directory for jobs.db, scout.log and file-notifier output "
                 "(default: <config dir>/data)",
        )
        sub.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    run_parser = subparsers.add_parser("run", help="do a run")
    _common(run_parser)
    run_parser.add_argument(
        "--dry-run", action="store_true",
        help="score and print the results, but record nothing and send nothing",
    )
    run_parser.add_argument(
        "--limit", type=int, default=None,
        help="stop after this many postings reach the scorer",
    )

    check_parser = subparsers.add_parser(
        "check", help="report what is configured and what each backend needs"
    )
    _common(check_parser)

    init_parser = subparsers.add_parser(
        "init", help="copy the example config.yaml and profile.yaml into a directory"
    )
    init_parser.add_argument("directory", help="where to put them")
    init_parser.add_argument(
        "--force", action="store_true", help="overwrite files that are already there"
    )
    init_parser.add_argument(
        "--with-tailoring", action="store_true",
        help="also write tailor/prompt.md and add the tailor and ask blocks to "
             "config.yaml, so the best match of the day gets worked on",
    )
    init_parser.add_argument(
        "--from-cv", metavar="PATH",
        help="draft profile.yaml from your CV (.txt, .md, .pdf or .docx) instead "
             "of copying the example. Needs a working model backend.",
    )

    stats_parser = subparsers.add_parser(
        "stats", help="what the seen-jobs database says: where postings go, what they score"
    )
    _common(stats_parser)
    stats_parser.add_argument(
        "--days", type=int, default=14, help="how many days of history to show"
    )

    roundup_parser = subparsers.add_parser(
        "roundup",
        help="one message summarising the best postings of the last few days",
    )
    _common(roundup_parser)
    roundup_parser.add_argument(
        "--days", type=int, default=7,
        help="how many days to cover, counting today (default: 7). Use 5 on a Friday for the working week",
    )
    roundup_parser.add_argument(
        "--top", type=int, default=10, help="how many postings to include (default: 10)",
    )
    roundup_parser.add_argument(
        "--dry-run", action="store_true", help="print it, send nothing",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="collect your answers to an outstanding question, then do the work",
    )
    _common(ask_parser)
    ask_parser.add_argument(
        "--status", action="store_true", help="say what is outstanding and do nothing",
    )
    ask_parser.add_argument(
        "--cancel", action="store_true", help="drop the outstanding question",
    )

    subparsers.add_parser("version", help="print the version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "version":
        print(f"job-scout {__version__}")
        return 0
    if command == "init":
        return _cmd_init(args)
    if command == "check":
        return _cmd_check(args)
    if command == "stats":
        return _cmd_stats(args)
    if command == "roundup":
        return _cmd_roundup(args)
    if command == "ask":
        return _cmd_ask(args)
    return _cmd_run(args)


# ─── Commands ─────────────────────────────────────────────────────────────────

def _cmd_init(args) -> int:
    target = Path(args.directory).expanduser()
    written = seed_config_dir(target, overwrite=args.force)

    if not written and not args.from_cv and not args.with_tailoring:
        print(f"{target} already has a {CONFIG_FILENAME} and a {PROFILE_FILENAME}. "
              f"Pass --force to overwrite them.")
        return 0

    if written:
        print(f"Wrote into {target}:")
        for path in written:
            print(f"  {path.name}")

    if args.with_tailoring:
        added = seed_tailoring(target, overwrite=args.force)
        if added:
            print("Added tailoring:")
            for path in added:
                print(f"  {path}")
            print(
                "\nBefore the first real run:\n"
                "  1. Edit " + str(target / "tailor" / "prompt.md") + ". It is "
                "full of [PLACEHOLDERS] and\n"
                "     knows nothing about you until you replace them.\n"
                "  2. Set tailor.command in " + str(target / CONFIG_FILENAME) + "\n"
                "  3. Check it: job-scout check --config-dir " + str(target)
            )
        else:
            print(f"{target} already has tailoring set up. Pass --force to replace it.")

    if args.from_cv:
        return _draft_profile_from_cv(target, Path(args.from_cv), overwrite=args.force)

    if args.with_tailoring:
        return 0

    print(
        "\nNext:\n"
        f"  1. Edit {target / PROFILE_FILENAME}. It decides what counts as a match.\n"
        f"  2. Edit {target / CONFIG_FILENAME}. Set your search terms.\n"
        f"  3. Copy .env.example to .env and fill in one API key.\n"
        f"  4. job-scout run --config-dir {target}\n"
        f"\nFaster: job-scout init {target} --from-cv path/to/your-cv.pdf"
    )
    return 0


def _draft_profile_from_cv(target: Path, cv_path: Path, overwrite: bool) -> int:
    """Replace the example profile with one drafted from the user's CV."""
    import yaml

    from .config import load_env
    from .cv_import import CvImportError, profile_from_cv, review_notes

    profile_path = target / PROFILE_FILENAME

    # A profile that is already yours is worth more than anything a CV can
    # produce, because the parts you wrote by hand are the parts a CV cannot
    # supply. Never overwrite one without being told to.
    if profile_path.exists() and not _is_shipped_example(profile_path) and not overwrite:
        print(
            f"{profile_path} already exists and has been edited.\n"
            f"Drafting from a CV would replace it, including anything you wrote "
            f"in confirmed_gaps.\n"
            f"\n"
            f"Back it up first, then pass --force:\n"
            f"  cp {profile_path} {profile_path}.bak\n"
            f"  job-scout init {target} --from-cv {cv_path} --force",
            file=sys.stderr,
        )
        return 1

    load_env(target)

    config_path = target / CONFIG_FILENAME
    model_spec = "gemini:gemini-3.7-flash"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            model_spec = str(loaded.get("scoring_model") or model_spec).strip()
        except (OSError, yaml.YAMLError):
            pass  # fall back to the default and let preflight complain usefully

    print(f"\nReading {cv_path} and drafting a profile with {model_spec} ...")
    try:
        profile_yaml, parsed = profile_from_cv(cv_path, model_spec)
    except CvImportError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        print(
            f"The example profile is still in place at {target / PROFILE_FILENAME}, "
            f"so you can edit that by hand instead.",
            file=sys.stderr,
        )
        return 1

    header = (
        "# profile.yaml. Drafted from a CV by `job-scout init --from-cv`.\n"
        "#\n"
        "# Read it before you trust it. confirmed_gaps is empty on purpose: a CV\n"
        "# says what you have done, not what you cannot do, and that section is\n"
        "# what stops the scorer sending you the wrong discipline.\n"
        "#\n"
        "# The full field reference is in docs/configuration.md.\n\n"
    )
    profile_path.write_text(header + profile_yaml, encoding="utf-8")

    print()
    print(review_notes(parsed, profile_path))
    print(f"Then: job-scout check --config-dir {target}")
    return 0


def _is_shipped_example(profile_path: Path) -> bool:
    """
    True if this profile is still the untouched example we ship.

    Used to decide whether overwriting it would lose anybody's work. Compared by
    content rather than by timestamp, so copying the file around does not make it
    look edited.
    """
    from .config import PROFILE_FILENAME as name
    from .config import TEMPLATE_DIR

    shipped = TEMPLATE_DIR / name
    if not shipped.exists():
        return False
    try:
        return (
            profile_path.read_text(encoding="utf-8").strip()
            == shipped.read_text(encoding="utf-8").strip()
        )
    except OSError:
        return False


def _cmd_stats(args) -> int:
    from .stats import render

    try:
        settings = load_settings(args.config_dir, args.data_dir)
    except ConfigError as exc:
        print(f"Configuration problem:\n\n{exc}\n", file=sys.stderr)
        return 2
    print(render(settings.data_dir / "jobs.db", settings.notify_threshold, args.days))
    return 0


def _cmd_roundup(args) -> int:
    from .notifiers import Dispatcher, build
    from .notifiers.base import full_digest_text
    from .roundup import collect, stats_for

    try:
        settings = load_settings(args.config_dir, args.data_dir)
    except ConfigError as exc:
        print(f"Configuration problem:\n\n{exc}\n", file=sys.stderr)
        return 2

    bands = settings.advanced["score_bands"]
    jobs, total = collect(
        settings.data_dir / "jobs.db",
        threshold=settings.notify_threshold,
        days=args.days,
        top=args.top,
    )
    stats = stats_for(
        jobs, total,
        threshold=settings.notify_threshold,
        days=args.days,
        strong_at=int(bands["strong"]),
        possible_at=int(bands["possible"]),
    )

    if args.dry_run:
        print(full_digest_text(jobs, stats))
        return 0

    # A roundup that reaches nobody is worth saying out loud, because the
    # command still exits 0 and looks like it worked.
    sent = Dispatcher(build(settings.notifier_specs, settings.data_dir)).send_digest(
        jobs, stats
    )
    if not sent:
        print(
            "The roundup reached no notifier. Run `job-scout check` to see "
            "what each one needs.",
            file=sys.stderr,
        )
        return 1
    print(f"Roundup sent to {sent} notifier(s): {len(jobs)} of {total} matches.")
    return 0


def _cmd_ask(args) -> int:
    from . import ask, tailor
    from .notifiers import Dispatcher, build
    from .run import setup_logging

    try:
        settings = load_settings(args.config_dir, args.data_dir)
    except ConfigError as exc:
        print(f"Configuration problem:\n\n{exc}\n", file=sys.stderr)
        return 2

    setup_logging(settings.data_dir, verbose=args.verbose)

    if args.cancel:
        if not ask.is_pending(settings.data_dir):
            print("Nothing is outstanding.")
            return 0
        ask.clear_state(settings.data_dir)
        print("Dropped the outstanding question. Nothing will be tailored for it.")
        return 0

    if args.status:
        return _print_ask_status(ask.read_state(settings.data_dir))

    if not ask.is_configured(settings.config):
        print(
            "config.yaml has no `ask` block, so there is nothing to collect.",
            file=sys.stderr,
        )
        return 2

    outcome, state = ask.collect(
        settings.config, settings.data_dir, ask.load(settings.config)
    )
    if outcome == "none":
        # A timer runs this every few minutes. Reporting "nothing to do" 288
        # times a day makes the journal useless, so only a person gets told.
        if sys.stdout.isatty():
            print("Nothing is outstanding.")
        return 0
    if outcome == "locked":
        print("Another collection pass is running.")
        return 0
    if outcome == "waiting":
        print(f"Waiting. {len(state.get('answers') or [])} message(s) so far.")
        return 0

    # Finished. Clear the state before doing the work, so a command that fails
    # is not retried every few minutes for the rest of the day.
    job = state.get("job") or {}
    answers = ask.answers_text(state)
    ask.clear_state(settings.data_dir)

    dispatcher = Dispatcher(build(settings.notifier_specs, settings.data_dir))
    produced = tailor.tailor_job(settings, job, answers=answers, dispatcher=dispatcher)
    if produced is None:
        print(
            "The tailoring command produced nothing. See scout.log for why.",
            file=sys.stderr,
        )
        return 1
    print(f"Wrote {produced}")
    return 0


def _print_ask_status(state) -> int:
    if state is None:
        print("Nothing is outstanding.")
        return 0
    job = state.get("job") or {}
    answers = state.get("answers") or []
    print(f"Asked about: {job.get('title', '?')} at {job.get('company', '?')}")
    print(f"Asked at:    {state.get('opened', '?')}")
    print(f"Deadline:    {state.get('deadline', '?')}")
    print(f"Questions:   {len(state.get('questions') or [])}")
    print(f"Your replies: {len(answers)}")
    if state.get("done"):
        print("You have sent /done. The next `job-scout ask` will do the work.")
    return 0


def _cmd_check(args) -> int:
    from .llm import check_all, label_for, preflight
    from .notifiers import Dispatcher, build
    from .sources import ALL_SITES, unknown_sites

    print(f"job-scout {__version__}\n")

    try:
        settings = load_settings(args.config_dir, args.data_dir)
    except ConfigError as exc:
        config_dir = resolve_config_dir(args.config_dir)
        print(f"Config directory: {config_dir}")
        print(f"\nCONFIGURATION PROBLEM\n{exc}\n")
        _print_backends(check_all, preflight)
        return 1

    print(f"Config directory: {settings.config_dir}")
    print(f"Data directory:   {settings.data_dir}")
    print(f"Threshold:        {settings.notify_threshold}")
    print(f"Searches:         {len(settings.searches)}")

    sites: set[str] = set()
    for search in settings.searches:
        sites.update(str(site).lower() for site in (search.get("sites") or []))
    print(f"Sources in use:   {', '.join(sorted(sites)) or 'none'}")

    unknown = unknown_sites(settings.searches)
    if unknown:
        print(
            f"  WARNING: no source handles {', '.join(unknown)}. "
            f"Known sources: {', '.join(ALL_SITES)}"
        )

    outcomes = settings.outcomes_path
    print(
        f"Outcomes file:    {outcomes} "
        f"({'found' if outcomes.exists() else 'absent. Scoring works without it'})"
    )

    # Scoring backend.
    print("\nSCORING BACKEND")
    spec = settings.scoring_model
    problem = preflight(spec)
    if problem:
        print(f"  NOT READY  {label_for(spec)}\n             {problem}")
    else:
        print(f"  READY      {label_for(spec)}")

    _print_backends(check_all, preflight)

    # Notifiers.
    print("NOTIFIERS")
    try:
        dispatcher = Dispatcher(build(settings.notifier_specs, settings.data_dir))
    except Exception as exc:
        print(f"  PROBLEM    {exc}")
        return 1
    results = dispatcher.check()
    for name, message in results:
        if message:
            print(f"  NOT READY  {name}\n             {message}")
        else:
            print(f"  READY      {name}")
    ready_count = sum(1 for _, message in results if not message)
    if ready_count == 0:
        print(
            "\n  Nothing is set up to receive results. The one that needs no "
            "credentials is:\n\n    notifiers:\n      - type: file\n"
        )

    tailoring_problem = _print_tailoring(settings)

    print()
    problems = bool(problem) or ready_count == 0 or tailoring_problem
    print("Not ready to run." if problems else "Ready to run: job-scout run")
    return 1 if problems else 0


def _unfilled_placeholders(text: str) -> list[str]:
    """
    Which of the shipped template's placeholders are still in a prompt.

    Compared against the template rather than counting brackets. A finished
    prompt has every right to contain [NEEDS ME] or [REDACTED], and a check that
    calls those a problem is a check you learn to ignore.
    """
    from .config import TAILOR_PROMPT_TEMPLATE, TEMPLATE_DIR

    source = TEMPLATE_DIR / TAILOR_PROMPT_TEMPLATE
    if not source.exists():
        return []
    import re

    shipped = set(re.findall(r"\[[A-Z][^\]]{4,}\]", source.read_text(encoding="utf-8")))
    # [NEEDS ...] is not a placeholder. The template tells the model to write it
    # where a fact is missing, and a finished prompt should still say so.
    shipped = {item for item in shipped if not item.startswith("[NEEDS")}
    return sorted(item for item in shipped if item in text)


def _print_tailoring(settings: Settings) -> bool:
    """
    What the optional follow-up step is set to do. Returns True if it is broken.

    Silent when it is not configured, because most people do not want it and a
    check that lists things you have not asked for is a worse check.
    """
    import shlex
    import shutil

    from . import ask, tailor

    if not tailor.is_configured(settings.config):
        return False

    print("\nTAILORING")
    try:
        config = tailor.load(settings.config, settings.config_dir, settings.data_dir)
    except tailor.TailorError as exc:
        print(f"  PROBLEM    {exc}")
        return True

    broken = False
    print(f"  Command:   {config.command}")
    try:
        binary = shlex.split(config.command)[0]
    except (ValueError, IndexError):
        binary = ""
    located = shutil.which(binary) if binary else None
    if located:
        print(f"  READY      {binary} at {located}")
    else:
        print(f"  NOT READY  {binary or '(no command)'} is not on this machine's PATH")
        broken = True

    if config.prompt_file is None:
        print("  Prompt:    none. The command gets the posting and nothing else")
    elif config.prompt_file.exists():
        text = config.prompt_file.read_text(encoding="utf-8", errors="replace")
        left = _unfilled_placeholders(text)
        note = f", {len(left)} still to fill in" if left else ""
        print(f"  Prompt:    {config.prompt_file}{note}")
        for placeholder in left[:3]:
            print(f"             {placeholder}")
        if left:
            print("             Edit it before the first real run.")
    else:
        print(f"  NOT READY  no prompt at {config.prompt_file}")
        broken = True

    print(f"  Works on:  the day's best match at {config.min_score} or above")
    print(f"  Writes to: {config.output_dir}")

    if ask.is_configured(settings.config):
        questions = ask.load(settings.config)
        count = len(questions.questions) or "from a command"
        print(f"  Asks:      {count} question(s), then waits {questions.timeout_hours}h")
        state = ask.read_state(settings.data_dir)
        if state:
            job = state.get("job") or {}
            print(
                f"  Waiting on: {job.get('title', '?')} at {job.get('company', '?')}, "
                f"{len(state.get('answers') or [])} repl(ies) so far"
            )
    return broken


def _print_backends(check_all, preflight) -> None:
    print("\nALL BACKENDS (you only need the one in scoring_model)")
    for spec, message in check_all():
        if message:
            print(f"  NOT READY  {spec}\n             {message}")
        else:
            print(f"  READY      {spec}")
    print()


def _cmd_run(args) -> int:
    from .run import RunResult, run_once, setup_logging

    try:
        settings = load_settings(args.config_dir, args.data_dir)
    except ConfigError as exc:
        print(f"Configuration problem:\n\n{exc}\n", file=sys.stderr)
        return 2

    setup_logging(settings.data_dir, verbose=args.verbose)
    result: RunResult = run_once(settings, dry_run=args.dry_run, limit=args.limit)

    if args.dry_run:
        _print_dry_run(result, settings)

    if not result.ok:
        return 1
    return 0


def _print_dry_run(result, settings: Settings) -> None:
    from .notifiers.base import full_digest_text

    print("\n" + "=" * 72)
    print("DRY RUN, nothing was recorded and nothing was sent")
    print("=" * 72)
    print(full_digest_text(result.matched, result.stats))
    print("=" * 72)
    print(
        f"{len(result.matched)} of {result.stats.total_new} new postings scored "
        f"at or above {settings.notify_threshold}."
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
