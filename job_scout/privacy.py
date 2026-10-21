"""
privacy.py. Your own private word list, made by you, kept on your machine.

A job-search workspace is full of things that must not reach a public place:
your name, your employers, your town, the address of the server you run this on.
This module holds a list of those terms and checks working trees and git ranges
against it.

    job-scout privacy init               answer questions, build the list
    job-scout privacy add TERM           add one term (and its spelling variants)
    job-scout privacy list --count       how many entries, never what they are
    job-scout privacy check [PATH]       scan a folder for any listed term
    job-scout privacy check --range A..B    scan the lines a git range adds

The rules that make this safe to use:

  * Nothing ships. The project contains no one's terms, and none are guessed.
  * The list is a plain file with mode 600, kept out of git. Contributors keep it
    at .git/denylist.txt, which git can never commit. Everyone else keeps it at
    <config dir>/privacy.txt, and this module adds that path to .git/info/exclude
    when the config directory is inside a repository that does not ignore it.
  * The terms are never printed or logged. `list` shows a count. `check` shows a
    file, a line and a column, plus the entry's position in the list, and no term.
  * Nothing is added without your answer. Non-interactive runs add nothing and
    never wait for input.

tools/pre_push_check.py reads the same file.
"""

import os
import re
import stat
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .normalize import company_key
from .setup_prompt import SetupCancelled

DEFAULT_FILENAME = "privacy.txt"
CONTRIBUTOR_FILENAME = "denylist.txt"
DECLINED_PREFIX = "# declined: "
MIN_TERM_LENGTH = 3

_HEADER = (
    "# job-scout privacy list. One term per line, matched case-insensitively.\n"
    "# Local only: never commit, share or paste this file.\n"
)

_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".db", ".ico", ".zip", ".woff2",
    ".docx", ".xlsx", ".pptx", ".gz", ".whl", ".pyc",
}
_MAX_FILE_BYTES = 2_000_000

# Letters that Unicode decomposition leaves alone, and the common ways people
# write them without the letter. Both spellings are listed, because one name turns
# up as "Osterby" on one form and "Oesterby" on another.
_TRANSLITERATIONS = {
    "ø": ("o", "oe"),
    "æ": ("ae", "ae"),
    "å": ("a", "aa"),
    "ß": ("ss", "ss"),
    "ł": ("l", "l"),
    "đ": ("d", "d"),
    "ö": ("o", "oe"),
    "ä": ("a", "ae"),
    "ü": ("u", "ue"),
}


# --- Where the list lives -----------------------------------------------------

def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    """Run git. None when git is missing or the call cannot be made."""
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_common_dir(cwd: Path) -> Path | None:
    """
    The repository's real git directory, or None outside a repository.

    In a worktree `.git` is a file that points elsewhere, so the shared
    directory has to be asked for. That is where info/exclude and the
    contributor's denylist.txt live.
    """
    result = _git(["rev-parse", "--git-common-dir"], cwd)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip())
    return (path if path.is_absolute() else Path(cwd) / path).resolve()


def _is_project_checkout(cwd: Path) -> bool:
    """Is cwd inside a checkout of job-scout itself, as opposed to a user's own repository?"""
    result = _git(["rev-parse", "--show-toplevel"], cwd)
    if result is None or result.returncode != 0:
        return False
    top = Path(result.stdout.strip())
    return (top / "tools" / "pre_push_check.py").is_file() and (
        top / "job_scout" / "__init__.py"
    ).is_file()


def resolve_path(
    config_dir: Path | str | None = None,
    file: str | None = None,
    cwd: Path | None = None,
) -> Path:
    """
    Where the list is, first hit wins:

      1. file (--file)
      2. $JOB_SCOUT_DENYLIST, the variable tools/pre_push_check.py also reads
      3. <config dir>/privacy.txt, when a config directory is named, set in
         $JOB_SCOUT_CONFIG_DIR, or is the current directory
      4. inside a job-scout checkout: <git dir>/denylist.txt (a contributor)
      5. privacy.txt in the current directory
    """
    if file:
        return Path(file).expanduser()
    from_env = os.environ.get("JOB_SCOUT_DENYLIST", "").strip()
    if from_env:
        return Path(from_env).expanduser()
    if config_dir:
        return Path(config_dir).expanduser() / DEFAULT_FILENAME
    env_config = os.environ.get("JOB_SCOUT_CONFIG_DIR", "").strip()
    if env_config:
        return Path(env_config).expanduser() / DEFAULT_FILENAME

    here = Path(cwd) if cwd else Path.cwd()
    if (here / "config.yaml").exists():
        return here / DEFAULT_FILENAME
    if _is_project_checkout(here):
        common = git_common_dir(here)
        if common is not None:
            return common / CONTRIBUTOR_FILENAME
    return here / DEFAULT_FILENAME


# --- Reading and writing the list ---------------------------------------------

def read_terms(path: Path) -> list[str]:
    """The terms, in file order. Blank lines and comments are not terms."""
    path = Path(path)
    if not path.is_file():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line.lower())
    return terms


def read_declined(path: Path) -> set[str]:
    """Employers the person answered "no" to, so they are not asked again."""
    path = Path(path)
    if not path.is_file():
        return set()
    found = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(DECLINED_PREFIX):
            found.add(line[len(DECLINED_PREFIX):].strip().lower())
    return found


def _once(output_fn: Callable[[str], None]) -> Callable[[str], None]:
    """output_fn, but a message already shown is not shown again."""
    shown: set[str] = set()

    def say(message: str) -> None:
        if message not in shown:
            shown.add(message)
            output_fn(message)

    return say


def _append(
    path: Path, lines: list[str], on_note: Callable[[str], None] | None = None
) -> None:
    """
    Append lines, creating the file with mode 600 and tightening it if it exists.

    Every write goes through here, so every write first makes sure git will never
    commit the file (see keep_out_of_git). A sentence about that, if there is one,
    goes to on_note.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    note = keep_out_of_git(path)
    if note and on_note:
        on_note(note)
    existed = path.exists()
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
        if not existed:
            handle.write(_HEADER)
        for line in lines:
            handle.write(line + "\n")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # a filesystem without modes; nothing more can be done


def add_terms(
    path: Path, terms: list[str], on_note: Callable[[str], None] | None = None
) -> int:
    """Add terms that are not already listed. Returns how many were new."""
    known = set(read_terms(path))
    fresh: list[str] = []
    for term in terms:
        cleaned = term.strip().lower()
        if len(cleaned) < MIN_TERM_LENGTH or cleaned in known or cleaned in fresh:
            continue
        fresh.append(cleaned)
    if fresh:
        _append(path, fresh, on_note)
    return len(fresh)


def record_declined(
    path: Path, employer: str, on_note: Callable[[str], None] | None = None
) -> None:
    _append(path, [DECLINED_PREFIX + employer.strip()], on_note)


def keep_out_of_git(path: Path) -> str | None:
    """
    Make sure git will never commit the list. Returns a sentence to show, or None.

    A list inside .git is already safe. A list in a config directory that is
    itself a repository is the risk: one `git add .` away from being published.
    """
    path = Path(path).resolve()
    folder = path.parent
    if not folder.is_dir():
        return None
    inside = _git(["rev-parse", "--is-inside-work-tree"], folder)
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return None

    tracked = _git(["ls-files", "--error-unmatch", path.name], folder)
    if tracked is not None and tracked.returncode == 0:
        return (
            f"WARNING: git already tracks {path}. Stop tracking it with "
            f"`git rm --cached {path.name}` before you commit anything else."
        )
    ignored = _git(["check-ignore", "-q", path.name], folder)
    if ignored is not None and ignored.returncode == 0:
        return None

    top = _git(["rev-parse", "--show-toplevel"], folder)
    common = git_common_dir(folder)
    if top is None or top.returncode != 0 or common is None:
        return None
    try:
        relative = path.relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    except ValueError:
        return None
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    entry = "/" + relative
    if entry not in existing.splitlines():
        with open(exclude, "a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(entry + "\n")
    return f"Added {entry} to {exclude}, so git never commits the list."


# --- Spelling variants --------------------------------------------------------

def _ascii_forms(text: str) -> set[str]:
    """The text, lowercased, plus its accent-folded and transliterated spellings."""
    lowered = text.strip().lower()
    simple, expanded = [], []
    for char in lowered:
        if char in _TRANSLITERATIONS:
            plain, alt = _TRANSLITERATIONS[char]
            simple.append(plain)
            expanded.append(alt)
        else:
            simple.append(char)
            expanded.append(char)
    forms = {lowered}
    for chars in (simple, expanded):
        joined = "".join(chars)
        folded = unicodedata.normalize("NFKD", joined).encode("ascii", "ignore").decode("ascii")
        forms.add(folded)
    return {form for form in forms if form}


def variants(kind: str, value: str) -> list[str]:
    """
    Every spelling of one identifier worth listing.

    kind is one of: name, email, phone, place, employer, host, keyfile, repo,
    other. The result is deduplicated, lowercase and at least MIN_TERM_LENGTH
    long, and its first entry is the value as given.
    """
    value = value.strip()
    if not value:
        return []

    found: list[str] = []

    def put(*items: str) -> None:
        for item in items:
            lowered = item.strip().lower()
            for form in [lowered, *sorted(_ascii_forms(item) - {lowered})]:
                if len(form) >= MIN_TERM_LENGTH and form not in found:
                    found.append(form)

    put(value)

    if kind == "name":
        parts = value.split()
        if len(parts) >= 2:
            put(" ".join([parts[-1], *parts[:-1]]))
            if len(parts[-1]) >= 4:
                put(parts[-1])
    elif kind == "email":
        local = value.split("@")[0]
        if "@" in value and len(local) >= MIN_TERM_LENGTH:
            put(local)
    elif kind == "phone":
        compact = re.sub(r"[\s().\-]", "", value)
        put(compact)
        if compact.startswith("+"):
            put(compact[1:])
        elif compact.startswith("00"):
            put("+" + compact[2:], compact[2:])
    elif kind == "employer":
        stripped = company_key(value)
        if len(stripped) >= 4:
            put(stripped)
    elif kind == "keyfile":
        stem = value.rsplit(".", 1)[0] if "." in value else value
        if len(stem) >= 4:
            put(stem)
    elif kind == "repo" and "/" in value:
        tail = value.rsplit("/", 1)[1]
        if len(tail) >= 4:
            put(tail)
    return found


# --- Asking -------------------------------------------------------------------

QUESTIONS = (
    ("name", "Your full name, and any other name you go by."),
    ("email", "Your email addresses."),
    ("phone", "Your phone numbers."),
    ("place", "Your city, town or area, and your street if you want it kept out."),
    ("employer", "Employers and clients, past and present."),
    ("host", "Server names and IP addresses you use."),
    ("keyfile", "File names of your SSH or API key files."),
    ("repo", "Names of your private repositories."),
)


def build_list(
    path: Path,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """
    Ask for the person's own identifiers and save them with their variants.

    Returns how many entries were added. If the person ends the prompt early,
    what they have entered so far is still saved, because a short list protects
    more than none.
    """
    path = Path(path)
    existing = len(read_terms(path))
    output_fn(
        "This builds a list of terms that must never appear in anything you publish.\n"
        "You write it, it stays on this machine, and nothing you type is printed back,\n"
        "logged or sent anywhere.\n"
        f"It is saved to {path}"
        + (f" ({existing} entries already there; new ones are added)." if existing else ".")
        + "\nFor each question, type one answer per line. Press Enter on an empty line to\n"
        "move to the next question."
    )

    collected: list[str] = []
    cancelled = False
    for kind, question in QUESTIONS:
        output_fn(f"\n{question}")
        while True:
            try:
                answer = input_fn("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                cancelled = True
                break
            if not answer:
                break
            collected.extend(variants(kind, answer))
        if cancelled:
            break

    added = add_terms(path, collected, _once(output_fn))
    if cancelled:
        output_fn(f"\nStopped early. Saved what you had entered: {added} new entries.")
    else:
        output_fn(f"\nSaved {added} new entries ({len(read_terms(path))} in total).")
    output_fn(
        "Check a folder against it with `job-scout privacy check`. Add more later with\n"
        "`job-scout privacy add`."
    )
    return added


def _listed(company: str, known: set[str]) -> bool:
    """Is this employer already covered by a term, in any of its spellings?"""
    lowered = company.strip().lower()
    if any(form in known for form in variants("employer", company)):
        return True
    return any(term in lowered for term in known)


def offer_employers(
    companies: list[str],
    path: Path,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    interactive: bool = False,
) -> int:
    """
    Offer to add employers that are not on the list yet. Returns entries added.

    Never adds anything the person did not agree to, and never waits when there
    is nobody to answer: a non-interactive call returns at once. It does nothing
    when there is no list yet, because starting one is `privacy init`'s job.
    An employer answered "no" is remembered and not asked about again.
    """
    if not interactive or not companies:
        return 0
    path = Path(path)
    if not path.is_file():
        output_fn(
            "\nNo privacy list yet, so new employers are not offered. "
            "Start one with: job-scout privacy init"
        )
        return 0

    known = set(read_terms(path))
    declined = read_declined(path)
    pending = [
        company for company in companies
        if company.strip().lower() not in declined and not _listed(company, known)
    ]
    if not pending:
        return 0

    try:
        reply = input_fn(
            f"\n{len(pending)} employer(s) in your applications are not on your privacy "
            "list. Go through them one at a time? [y/N] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0
    if reply not in ("y", "yes"):
        return 0

    added = 0
    take_rest = False
    note = _once(output_fn)
    for company in pending:
        if take_rest:
            added += add_terms(path, variants("employer", company), note)
            continue
        for _ in range(3):
            try:
                answer = input_fn(
                    f"Add '{company}'? [y]es, [n]o, [a]ll the rest, [s]top: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return added
            if answer in ("y", "yes"):
                added += add_terms(path, variants("employer", company), note)
                break
            if answer in ("n", "no"):
                record_declined(path, company, note)
                break
            if answer in ("a", "all"):
                added += add_terms(path, variants("employer", company), note)
                take_rest = True
                break
            if answer in ("s", "stop"):
                return added
            output_fn("  Type y, n, a or s.")
        else:
            return added
    output_fn(f"Added {added} entries.")
    return added


# --- Checking -----------------------------------------------------------------

@dataclass
class Hit:
    path: str
    line: int
    column: int
    entry: int
    where: str = ""


@dataclass
class CheckResult:
    files: int = 0
    hits: list[Hit] = field(default_factory=list)


def scan_text(name: str, text: str, terms: list[str], first_line: int = 1) -> list[Hit]:
    """Every listed term found in the text. The hit holds a position, not the term."""
    hits: list[Hit] = []
    for offset, line in enumerate(text.splitlines()):
        lowered = line.lower()
        for index, term in enumerate(terms, start=1):
            column = lowered.find(term)
            if column >= 0:
                hits.append(Hit(name, first_line + offset, column + 1, index))
    return hits


def _tree_files(root: Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root]
    inside = _git(["rev-parse", "--is-inside-work-tree"], root)
    if inside is not None and inside.returncode == 0 and inside.stdout.strip() == "true":
        listing = _git(
            ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root
        )
        if listing is not None and listing.returncode == 0:
            return [root / name for name in listing.stdout.split("\0") if name]
    skipped = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    found: list[Path] = []
    for current, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in skipped]
        found.extend(Path(current) / name for name in names)
    return found


def check_tree(root: Path, terms: list[str], skip: Path | None = None) -> CheckResult:
    """Scan every file under root (tracked and untracked-but-not-ignored, when it is a repository)."""
    root = Path(root)
    result = CheckResult()
    skip_resolved = Path(skip).resolve() if skip else None
    for path in _tree_files(root):
        if not path.is_file() or path.suffix.lower() in _BINARY_SUFFIXES:
            continue
        if skip_resolved is not None and path.resolve() == skip_resolved:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        result.files += 1
        base = root if root.is_dir() else root.parent
        try:
            shown = path.relative_to(base).as_posix()
        except ValueError:
            shown = path.as_posix()
        result.hits.extend(scan_text(shown, raw.decode("utf-8", errors="replace"), terms))
    return result


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def check_range(rev_range: str, terms: list[str], cwd: Path) -> CheckResult:
    """
    Scan the lines a git range adds, and the author and committer of each commit.

    Only added lines are read, so an old line that was already fixed does not
    keep a range failing. Identities are checked because a push publishes who
    wrote each commit as well as what it says.
    """
    result = CheckResult()
    diff = _git(["diff", "-U0", "--no-color", "--no-ext-diff", rev_range], cwd)
    if diff is not None and diff.returncode == 0:
        current = ""
        line_no = 0
        for line in diff.stdout.splitlines():
            if line.startswith("+++ "):
                target = line[4:].strip()
                current = target[2:] if target.startswith("b/") else ""
                if current:
                    result.files += 1
            elif line.startswith("@@"):
                match = _HUNK.match(line)
                line_no = int(match.group(1)) if match else 0
            elif line.startswith("+") and not line.startswith("+++") and current:
                result.hits.extend(scan_text(current, line[1:], terms, first_line=line_no))
                line_no += 1

    separator = chr(31)
    log = _git(
        ["log", f"--format=%h{separator}%an <%ae>{separator}%cn <%ce>", rev_range], cwd
    )
    if log is not None and log.returncode == 0:
        for entry in log.stdout.splitlines():
            parts = entry.split(separator)
            if len(parts) != 3:
                continue
            commit, author, committer = parts
            for role, identity in (("author", author), ("committer", committer)):
                for hit in scan_text(f"commit {commit}", identity, terms):
                    hit.line = 0
                    hit.where = role
                    result.hits.append(hit)
    return result


def describe(hit: Hit, source: str = "") -> str:
    """One line for a hit: where it is, and which entry of which file. Never the term."""
    where = f"{hit.path}:{hit.line}:{hit.column}" if hit.line else f"{hit.path} ({hit.where})"
    entry = f"entry #{hit.entry}" + (f" of {source}" if source else "")
    return f"  {where}  matches {entry}"


# --- The command --------------------------------------------------------------

def command(
    args,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """`job-scout privacy ...`. Returns the exit code."""
    action = getattr(args, "privacy_command", None)
    if action is None:
        output_fn("Usage: job-scout privacy {init,add,list,check}. Try: job-scout privacy init")
        return 2

    path = resolve_path(config_dir=getattr(args, "config_dir", None), file=getattr(args, "file", None))

    if action == "init":
        if not (sys.stdin.isatty() and sys.stdout.isatty()) and input_fn is input:
            output_fn(
                "privacy init asks questions, so it needs a terminal. To add a term "
                "without one:\n  job-scout privacy add TERM"
            )
            return 2
        try:
            build_list(path, input_fn, output_fn)
        except SetupCancelled:
            return 0
        return 0

    if action == "add":
        terms = _terms_from_args(args)
        if not terms:
            output_fn(
                f"A term needs at least {MIN_TERM_LENGTH} characters, or it would match "
                "almost everything."
            )
            return 2
        added = add_terms(path, terms, output_fn)
        output_fn(f"Added {added} new entries ({len(read_terms(path))} in total).")
        return 0

    if action == "list":
        total = len(read_terms(path))
        if getattr(args, "count", False):
            output_fn(str(total))
        else:
            output_fn(f"{total} entries in {path}. The terms are never printed; this is a count only.")
        return 0

    if action == "check":
        terms = read_terms(path)
        if not terms:
            output_fn(
                f"No privacy list at {path}, or it is empty, so nothing was checked.\n"
                "Build one with: job-scout privacy init"
            )
            return 2
        root = Path(args.path).expanduser() if args.path else Path.cwd()
        if args.rev_range:
            result = check_range(args.rev_range, terms, root)
            source = args.rev_range
        else:
            if not root.exists():
                output_fn(f"{root} does not exist.")
                return 2
            result = check_tree(root, terms, skip=path)
            source = str(root)
        output_fn(f"Checked {result.files} file(s) in {source} against {len(terms)} entries.")
        if not result.hits:
            output_fn("Clean.")
            return 0
        output_fn(f"\n{len(result.hits)} match(es):")
        for hit in result.hits:
            output_fn(describe(hit, path.name))
        output_fn(
            "\nEntry numbers count the terms in that file from the top, comments not "
            "counted. Open the file yourself to see which one."
        )
        return 1

    output_fn(f"Unknown privacy command {action!r}.")
    return 2


def _terms_from_args(args) -> list[str]:
    """TERM from the command line, or one per line from stdin when TERM is a single dash."""
    raw = [args.term]
    if args.term == "-":
        raw = sys.stdin.read().splitlines()
    terms: list[str] = []
    for item in raw:
        item = item.strip()
        if len(item) < MIN_TERM_LENGTH:
            continue
        if getattr(args, "exact", False):
            terms.append(item)
        else:
            terms.extend(variants("other", item))
    return terms
