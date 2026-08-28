#!/usr/bin/env python3
"""
version_check.py: the version number is what ships, so it has to move.

Nobody installs this package from PyPI. Every install points at a git URL:

    pip install --upgrade 'job-scout[gemini] @ git+https://.../job-scout.git@main'

pip decides whether to reinstall by comparing version strings. When the version
has not changed, --upgrade does nothing at all. It fetches, compares 1.1.0 to
1.1.0, prints a success line and leaves the old code in place.

That has already cost a day. The fix in 1573703 was written, tested, committed
and pushed without a version bump, so the machine the bug was found on
reinstalled, reported success, and went on running the broken code.

So: a change to what gets installed, with no version bump, reaches nobody.

    python tools/version_check.py                        # the two files agree
    python tools/version_check.py --print                # print the version
    python tools/version_check.py --against origin/main  # and it has moved

Exit code 0 means fine. Anything else means do not push.

The bump is the whole release process. .github/workflows/release.yml turns a
new version on main into a tag and a GitHub release with generated notes.
Nothing about a release is manual, which is the point: the manual step is the
one that got skipped.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The two files that have to say the same number. The first is what pip reads
# and what the release tag is named after. The second is what
# `job-scout --version` prints, which is how anyone checks what a machine is
# actually running.
PYPROJECT = "pyproject.toml"
DUNDER = "job_scout/__init__.py"

# Anchored at the start of a line so `target-version` and `requires-python` in
# the ruff and project tables cannot match.
_PYPROJECT_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_DUNDER_VERSION = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)


class VersionProblem(Exception):
    """Something about the version means this push would ship to nobody."""


def _shipping(path: str) -> bool:
    """
    True for a file whose change lands in someone's installed copy.

    Docs, tests, examples and CI are not in this set. Editing them does not
    need a release, and requiring one would make the check something people
    route around.
    """
    return path.startswith("job_scout/") or path == PYPROJECT


def _read(path: str, pattern: re.Pattern, label: str) -> str:
    try:
        text = (REPO / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionProblem(f"cannot read {path}: {exc}") from exc
    match = pattern.search(text)
    if not match:
        raise VersionProblem(f"{path} has no `{label}` line")
    return match.group(1)


def current_version() -> str:
    """The version, once both files have been confirmed to agree on it."""
    packaged = _read(PYPROJECT, _PYPROJECT_VERSION, "version =")
    imported = _read(DUNDER, _DUNDER_VERSION, "__version__ =")
    if packaged != imported:
        raise VersionProblem(
            f"{PYPROJECT} says {packaged} and {DUNDER} says {imported}. They "
            f"have to match. The release tag is named after the first, and "
            f"`job-scout --version` prints the second, so a mismatch means a "
            f"machine reports a version that was never released."
        )
    return packaged


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VersionProblem(f"git {' '.join(args)} could not run: {exc}") from exc
    if result.returncode != 0:
        raise VersionProblem(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def version_at(ref: str) -> str | None:
    """What pyproject.toml declared at `ref`, or None if that is not readable."""
    try:
        text = _git("show", f"{ref}:{PYPROJECT}")
    except VersionProblem:
        return None
    match = _PYPROJECT_VERSION.search(text)
    return match.group(1) if match else None


def changed_files(ref: str) -> list[str]:
    """Paths that differ between `ref` and HEAD, from where the two last agreed."""
    try:
        base = _git("merge-base", ref, "HEAD").strip()
    except VersionProblem:
        base = ref
    output = _git("diff", "--name-only", f"{base}..HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _as_numbers(version: str) -> tuple[int, ...] | None:
    """(1, 1, 1) for "1.1.1", or None for anything with a suffix like "1.2.0rc1"."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def check_against(ref: str) -> str:
    """
    Require the version to have moved, if anything installable has moved.

    Returns a one-line summary of what it decided, so the caller can print it.
    """
    now = current_version()

    shipped = [path for path in changed_files(ref) if _shipping(path)]
    if not shipped:
        return f"nothing installable changed since {ref}, so {now} can stand"

    before = version_at(ref)
    if before is None:
        return f"cannot read the version at {ref}, so {now} is taken on trust"

    listed = ", ".join(shipped[:5]) + (f" and {len(shipped) - 5} more" if len(shipped) > 5 else "")

    if now == before:
        raise VersionProblem(
            f"{len(shipped)} installable file(s) changed since {ref} ({listed}) "
            f"and the version is still {now}.\n"
            f"\n"
            f"pip compares version strings. Leaving it at {now} means "
            f"`pip install --upgrade` finds nothing to do and every machine "
            f"keeps running the old code, while reporting a successful "
            f"install.\n"
            f"\n"
            f"Bump it in both files and commit:\n"
            f"  {PYPROJECT:<22} version = \"...\"\n"
            f"  {DUNDER:<22} __version__ = \"...\"\n"
            f"\n"
            f"That is the whole release. Pushing a new version to main cuts "
            f"the tag and the GitHub release by itself."
        )

    old_numbers, new_numbers = _as_numbers(before), _as_numbers(now)
    if old_numbers and new_numbers and new_numbers < old_numbers:
        raise VersionProblem(
            f"the version went backwards, from {before} at {ref} to {now}. "
            f"pip will not upgrade to a lower version, so this ships to nobody "
            f"for the same reason as no bump at all."
        )

    return f"{before} to {now}, with {len(shipped)} installable file(s) changed ({listed})"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the version is consistent, and that it moved."
    )
    parser.add_argument(
        "--print", action="store_true", dest="print_only",
        help="print the version and nothing else",
    )
    parser.add_argument(
        "--against", metavar="REF",
        help="also require the version to have moved since REF, if anything installable did",
    )
    args = parser.parse_args()

    try:
        version = current_version()
        if args.print_only:
            print(version)
            return 0
        summary = check_against(args.against) if args.against else f"{PYPROJECT} and {DUNDER} agree"
    except VersionProblem as exc:
        print(f"version check failed: {exc}", file=sys.stderr)
        return 1

    print(f"version {version}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
