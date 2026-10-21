#!/usr/bin/env python3
"""
check_applications.py: every application folder has a notes.md with a Status line.

An application with no recorded result is invisible to the scorer and to
`job-scout calibrate`, and a missing line looks exactly like an application that
was never sent. Run this before you commit a new application folder:

    python tools/check_applications.py                 # ./applications
    python tools/check_applications.py path/to/applications

Exit code 0 means every folder is recorded. 1 means at least one is not, and the
folders are named. 2 means the directory could not be read.

A folder whose name starts with "." or "_" (a template, an archive) is not an
application and is skipped. The format of the Status line is in
docs/applications.md.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from job_scout import outcomes  # noqa: E402


def problems(applications_dir: Path) -> list[str]:
    """One sentence per folder that is not recorded properly."""
    found = []
    for folder in outcomes.application_folders(applications_dir):
        if not (folder / "notes.md").is_file():
            found.append(f"{folder.name}: no notes.md")
        elif not outcomes.status_for(folder):
            found.append(f"{folder.name}: notes.md has no **Status:** line with a value")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?", default="applications",
        help="the folder of application folders (default: ./applications)",
    )
    args = parser.parse_args(argv)

    directory = Path(args.directory).expanduser()
    if not directory.is_dir():
        print(f"{directory} is not a directory.", file=sys.stderr)
        return 2

    folders = outcomes.application_folders(directory)
    found = problems(directory)
    if found:
        print(f"{len(found)} of {len(folders)} application folder(s) are not recorded:\n")
        for line in found:
            print(f"  {line}")
        print(
            "\nAdd a line such as `- **Status:** drafted` near the top of each notes.md. "
            "The vocabulary is in docs/applications.md."
        )
        return 1

    print(f"All {len(folders)} application folder(s) have a Status line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
