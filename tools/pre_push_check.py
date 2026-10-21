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

Four kinds of check:

1. Credential shapes. GitHub tokens, Google keys, Apify tokens, OpenAI-style
   keys, Telegram bot tokens, private key blocks, passwords inside URLs.
2. Commit author and committer identity. A push publishes who wrote each
   commit, not only what the files say. That is baked into the commit hash, so
   correcting it later means rewriting history and force-pushing. This
   repository has already had to do that once.
3. Files that should never be here at all. A real config.yaml, profile.yaml,
   .env, outcomes.csv, jobs.db, or anything named like infrastructure notes.
4. Your own words. Names, employers, addresses, IP addresses, hostnames. These
   cannot be listed in this file, because writing them here would publish the
   very thing they are meant to keep out. They live in a private word list.

## The private word list

One term per line, blank lines and # comments ignored. Every file below that
exists is read, and their terms are combined:

    the file named by $JOB_SCOUT_DENYLIST
    <git dir>/denylist.txt     (inside .git, so git can never commit it. In a
                                worktree this is the shared git directory, found
                                with `git rev-parse --git-common-dir`)
    privacy.txt                (in this checkout's root, when it is also your
                                config directory; gitignored)
    $JOB_SCOUT_CONFIG_DIR/privacy.txt

`job-scout privacy init` builds this list for you, interactively, and
`job-scout privacy check` scans against it. Neither prints your terms, and
neither does this script. A finding names the entry by file name and position
within that file ("entry #3 of privacy.txt"), and for a commit author or
committer it names the commit and the field. It never prints the term, and never
the name and email it matched.

Terms match case-insensitively anywhere in a line. Keep real names, employer
names, your town, your VM's IP, your SSH key filenames and your personal domains
in it.

Without a word list, checks 1 and 3 still run. Checks 2 and 4 need one, which
is why the hook passes --require-denylist: a fresh clone has no word list and
would otherwise look clean while checking almost nothing.

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
    (re.compile(r"(^|/)(privacy|denylist)\.txt$"), "your private word list"),
    (re.compile(r"^applications/"), "your own application folders"),
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


def git_common_dir() -> Path:
    """
    The real git directory.

    In a worktree `.git` is a file that points elsewhere, and `.git/denylist.txt`
    would be a path through a file. `git rev-parse --git-common-dir` names the
    shared directory in both cases. Falls back to `.git` when git cannot say.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return REPO / ".git"
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return REPO / ".git"
    path = Path(value)
    return path if path.is_absolute() else (REPO / path).resolve()


def denylist_files() -> list[Path]:
    """Every place the word list can be, whether or not a file is there."""
    paths = []
    from_env = os.environ.get("JOB_SCOUT_DENYLIST", "").strip()
    if from_env:
        paths.append(Path(from_env).expanduser())
    paths.append(git_common_dir() / "denylist.txt")
    paths.append(REPO / "privacy.txt")
    config_dir = os.environ.get("JOB_SCOUT_CONFIG_DIR", "").strip()
    if config_dir:
        paths.append(Path(config_dir).expanduser() / "privacy.txt")
    return paths


class Term(str):
    """
    A word-list term that remembers where it came from, so a finding can say
    "entry #3 of privacy.txt" without ever saying what the term is. It compares
    and hashes as the plain string.
    """

    source: str
    position: int

    def __new__(cls, value: str, source: str = "", position: int = 0):
        term = super().__new__(cls, value)
        term.source = source
        term.position = position
        return term


def entry_label(term: str, fallback_index: int) -> str:
    """
    Which entry this is, by file name and position within that file. Never the term.

    Lists are merged, so a bare position in the merged list would mean nothing to
    the person who has to open a file to look.
    """
    source = getattr(term, "source", "")
    if source:
        return f"entry #{term.position} of {source}"
    return f"entry #{fallback_index} of your word list"


def load_denylist() -> list[str]:
    """
    Personal terms, from outside the repository's tracked files.

    Every file that exists is read and the terms combined; a term that appears in
    more than one file is kept once, from the first. Each term is a Term, which
    knows its file name and its position within that file (counting every term
    line, comments and blanks excluded).
    """
    terms: list[Term] = []
    for path in denylist_files():
        if not path.is_file():
            continue
        position = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            position += 1
            if line not in terms:
                terms.append(Term(line, path.name, position))
    return terms


def commit_identities(rev_range: str | None) -> list[tuple[str, str, str]]:
    """
    Every (commit, "Name <email>", "author" or "committer") a push would publish.

    File contents are only half of what goes public. Author and committer
    identity are published too, they are baked into the commit hash, and
    correcting them afterwards means rewriting history and force-pushing. This
    repository has already had to do that once.
    """
    separator = chr(31)  # unit separator, safe inside a name or an email
    argv = [
        "git", "log",
        f"--format=%h{separator}%an <%ae>{separator}%cn <%ce>",
        rev_range or "HEAD",
    ]
    result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    identities: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(separator)
        if len(parts) != 3:
            continue
        commit, author, committer = parts
        identities.append((commit, author, "author"))
        if committer != author:
            identities.append((commit, committer, "committer"))
    return identities


def scan_identities(rev_range: str | None, denylist: list[str]) -> list[Finding]:
    """
    Findings for any commit whose author or committer matches the word list.

    A finding names the commit, the field and the entry. It never prints the
    identity: the name and email are exactly the private text being guarded, and
    this output lands in terminals and CI logs.
    """
    findings: list[Finding] = []
    for commit, identity, *rest in commit_identities(rev_range):
        field = rest[0] if rest else "author"
        lowered = identity.lower()
        for index, term in enumerate(denylist, start=1):
            if term in lowered:
                findings.append(
                    Finding(
                        f"commit {commit}", 0, f"private term in commit {field}",
                        entry_label(term, index),
                    )
                )
                break
    return findings


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
            for index, term in enumerate(denylist, start=1):
                if term in lowered:
                    # The position, not the term. The word list is never printed.
                    findings.append(
                        Finding(name, number, "private term", entry_label(term, index))
                    )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="check staged changes only")
    parser.add_argument("--range", dest="rev_range", help="e.g. origin/main..HEAD")
    parser.add_argument(
        "--require-denylist", action="store_true",
        help="fail if no private word list is present, rather than warning. Use "
             "this in the hook: a fresh clone does not carry one.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    denylist = load_denylist()
    if args.require_denylist and not denylist:
        print(
            "No private word list found, and --require-denylist was given.\n"
            "A fresh clone does not carry one, because it lives inside .git.\n"
            "Restore it, then run this again.",
            file=sys.stderr,
        )
        return 2

    names = files_to_check("staged" if args.staged else "tree", args.rev_range)
    findings = scan(names, denylist)
    findings += scan_identities(args.rev_range, denylist)

    if not args.quiet:
        source = "staged changes" if args.staged else (args.rev_range or "the whole tree")
        print(f"Checked {len(names)} file(s) in {source}.")
        if denylist:
            print(f"Private word list: {len(denylist)} term(s).")
        else:
            print(
                "No private word list found. Credential and filename checks still "
                "ran.\n"
                "  Build one with: job-scout privacy init\n"
                "  (or put terms in .git/denylist.txt, or set $JOB_SCOUT_DENYLIST)."
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
