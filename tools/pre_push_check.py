#!/usr/bin/env python3
"""
pre_push_check.py: refuse to push anything that should stay private.

This repository is public. Whoever works on it probably also has a private
workspace with a real profile, real API keys and real infrastructure notes in
it. One careless `git add -A` in the wrong directory is all it takes.

    python tools/pre_push_check.py            # check what is committed
    python tools/pre_push_check.py --staged   # check what is staged
    python tools/pre_push_check.py --range origin/main..HEAD

Exit code 0 means clean. Anything else means do not push.

Three kinds of check:

1. Credential shapes. GitHub tokens, Google keys, Apify tokens, OpenAI-style
   keys, Telegram bot tokens, private key blocks, passwords inside URLs.
2. Files that should never be here at all. A real config.yaml, profile.yaml,
   .env, outcomes.csv, jobs.db, or anything named like infrastructure notes.
3. Your own words. Names, employers, addresses, IP addresses, hostnames. These
   cannot be listed in this file, because writing them here would publish the
   very thing they are meant to keep out. They live in a private word list.

## The private word list

Put one term per line, blank lines and # comments ignored, in either:

    the file named by $JOB_SCOUT_DENYLIST
    .git/denylist.txt          (inside .git, so git can never commit it)

Terms match case-insensitively anywhere in a line. Keep real names, employer
names, your town, your VM's IP, your SSH key filenames and your personal domains
in it.

Without a word list the first two checks still run.

## Installing it as a hook

    bash tools/install-git-hooks.sh

That makes `git push` run this first and stop on a failure.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Credential shapes. Kept deliberately narrow so a docstring about tokens does
# not trip them; the tests cover both directions.
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}\b")),
    ("Apify token", re.compile(r"\bapify_api_[A-Za-z0-9]{25,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{30,}\b")),
    ("Telegram bot token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{33,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password in a URL", re.compile(r"://[^/\s:@]+:[^/\s@]{3,}@")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]

# Files that have no business in a public repository, whatever is in them.
FORBIDDEN_PATHS = [
    (re.compile(r"(^|/)\.env$"), "real secrets"),
    (re.compile(r"(^|/)\.env\.(?!example$)"), "real secrets"),
    (re.compile(r"^config\.yaml$"), "your own config, gitignored on purpose"),
    (re.compile(r"^profile\.yaml$"), "your own profile, gitignored on purpose"),
    (re.compile(r"(^|/)outcomes\.csv$"), "your application history"),
    (re.compile(r"(^|/)jobs\.db$"), "your seen-jobs database"),
    (re.compile(r"(^|/)data/"), "run output"),
    (re.compile(r"(?i)(^|/)vm\.md$"), "infrastructure notes"),
    (re.compile(r"(?i)\.(pem|key|ppk|p12|pfx)$"), "a private key"),
    (re.compile(r"(?i)(^|/)id_(rsa|ed25519|ecdsa)$"), "a private key"),
]

# Anything here is allowed to contain the patterns above, because its whole job
# is to describe or detect them. Keep this list as short as possible: an allowed
# file is a file where a real key would go unnoticed.
ALLOWED_FILES = {
    "tools/pre_push_check.py",
    "job_scout/redact.py",
    "tests/test_redact.py",
    "tests/test_pre_push_check.py",
}

# One line at a time, for a fixture that has to look like a credential. Better
# than allowing a whole file, because the rest of that file stays checked.
ALLOW_MARKER = "pre-push-check: allow"

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".db", ".ico", ".zip", ".woff2"}


class Finding:
    def __init__(self, path: str, line_no: int, label: str, evidence: str):
        self.path = path
        self.line_no = line_no
        self.label = label
        self.evidence = evidence

    def __str__(self) -> str:
        where = f"{self.path}:{self.line_no}" if self.line_no else self.path
        return f"  {where}\n      {self.label}: {self.evidence}"


def load_denylist() -> list[str]:
    """Personal terms, from outside the repository's tracked files."""
    candidates = []
    from_env = os.environ.get("JOB_SCOUT_DENYLIST", "").strip()
    if from_env:
        candidates.append(Path(from_env).expanduser())
    candidates.append(REPO / ".git" / "denylist.txt")

    for path in candidates:
        if not path.is_file():
            continue
        terms = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line.lower())
        return terms
    return []


def files_to_check(mode: str, rev_range: str | None) -> list[str]:
    if mode == "staged":
        argv = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    elif rev_range:
        argv = ["git", "diff", "--name-only", "--diff-filter=ACMR", rev_range]
    else:
        argv = ["git", "ls-files"]
    result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return []
    return [name for name in result.stdout.split("\n") if name.strip()]


def scan(names: list[str], denylist: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    for name in names:
        for pattern, why in FORBIDDEN_PATHS:
            if pattern.search(name):
                findings.append(Finding(name, 0, "file must not be committed", why))
                break

        path = REPO / name
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        # An allowed file may contain credential shapes, because detecting them
        # is what it is for. It is never allowed to contain real personal
        # details, so the word-list check below still runs on it.
        shapes_exempt = name.replace("\\", "/") in ALLOWED_FILES
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for number, line in enumerate(text.splitlines(), 1):
            if not shapes_exempt and ALLOW_MARKER not in line:
                for label, pattern in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        shown = match.group(0)
                        findings.append(
                            Finding(name, number, label, shown[:12] + "..." + shown[-4:])
                        )
            lowered = line.lower()
            for term in denylist:
                if term in lowered:
                    findings.append(Finding(name, number, "private term", term))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="check staged changes only")
    parser.add_argument("--range", dest="rev_range", help="e.g. origin/main..HEAD")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    denylist = load_denylist()
    names = files_to_check("staged" if args.staged else "tree", args.rev_range)
    findings = scan(names, denylist)

    if not args.quiet:
        source = "staged changes" if args.staged else (args.rev_range or "the whole tree")
        print(f"Checked {len(names)} file(s) in {source}.")
        if denylist:
            print(f"Private word list: {len(denylist)} term(s).")
        else:
            print(
                "No private word list found. Credential and filename checks still "
                "ran.\n"
                "  Add one at .git/denylist.txt, or set $JOB_SCOUT_DENYLIST."
            )

    if findings:
        print(f"\nDO NOT PUSH. {len(findings)} problem(s):\n", file=sys.stderr)
        for finding in findings:
            print(finding, file=sys.stderr)
        print(
            "\nFix each one, then run this again. If a hit is a false positive, "
            "reword the line rather than adding an exception, so the next person "
            "does not have to decide.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print("Clean. Safe to push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
