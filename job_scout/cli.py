"""
cli.py — the `job-scout` command.

    job-scout run                    do a run
    job-scout run --dry-run          score and print, record nothing, send nothing
    job-scout run --limit 5          stop after 5 postings reach the scorer
    job-scout check                  tell me what is and is not set up
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
    return _cmd_run(args)


# ─── Commands ─────────────────────────────────────────────────────────────────

def _cmd_init(args) -> int:
    target = Path(args.directory).expanduser()
    written = seed_config_dir(target, overwrite=args.force)
    if not written:
        print(f"{target} already has a {CONFIG_FILENAME} and a {PROFILE_FILENAME}. "
              f"Pass --force to overwrite them.")
        return 0
    print(f"Wrote into {target}:")
    for path in written:
        print(f"  {path.name}")
    print(
        "\nNext:\n"
        f"  1. Edit {target / PROFILE_FILENAME} — it decides what counts as a match.\n"
        f"  2. Edit {target / CONFIG_FILENAME} — set your search terms.\n"
        f"  3. Copy .env.example to .env and fill in one API key.\n"
        f"  4. job-scout run --config-dir {target}"
    )
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
        f"({'found' if outcomes.exists() else 'absent — scoring works without it'})"
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

    print()
    problems = bool(problem) or ready_count == 0
    print("Not ready to run." if problems else "Ready to run: job-scout run")
    return 1 if problems else 0


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
    print("DRY RUN — nothing was recorded and nothing was sent")
    print("=" * 72)
    print(full_digest_text(result.matched, result.stats))
    print("=" * 72)
    print(
        f"{len(result.matched)} of {result.stats.total_new} new postings scored "
        f"at or above {settings.notify_threshold}."
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
