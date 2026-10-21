"""
verify.py. Read a compiled CV PDF the way an applicant tracking system will.

A clean compile proves the document built. It proves nothing about what a parser
gets back out of it, and the extracted text is the only version a recruiter's
software ever sees. A CV can compile perfectly and still arrive with the phone
number in an image, the name below a sidebar, or a Danish town spelled with
garbage where the o-with-a-stroke should be.

    job-scout cv verify cv.pdf
    job-scout cv verify cv.pdf --jd posting.md --extractor both

Exit code 0 means every check passed or warned. Exit code 1 means at least one
failed, so it can sit in a script or a git hook.

The expected name, email and phone come from your resume.yaml (or from --name,
--email and --phone), so a changed phone number cannot make this pass against a
PDF that no longer carries it.

Text comes from pypdf by default. Poppler's `pdftotext` is an optional second
opinion (--extractor both), because the two disagree occasionally and an ATS runs
one of them, not both.

What each check is for:

  text layer      A PDF built from an image has no text. Some parsers return an
                  empty document and score it zero without telling anyone.
  pages           Past two pages, most screeners read the first two.
  contact         An email a parser cannot find is an application that cannot be
                  replied to. This is the one failure that costs the job outright.
  reading order   Parsers take the first lines as the candidate's name. When a
                  sidebar or a section heading extracts first, the field is
                  filled with that instead.
  encoding        Mangled accented letters mean the font's encoding did not
                  survive extraction. Nordic and German names break first.
  residue         A stray LaTeX macro in the text layer means a command did not
                  expand. It is invisible on the page and quoted back in the
                  parsed record.
  headings        Workday, Greenhouse, Lever and Taleo segment on literal
                  section words. "Career Highlights" is not one of them.
  keywords        With --jd, how much of the posting's own vocabulary survived
                  into the text layer.

Nothing here judges the writing. It checks that the file is machine-readable.
"""

import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

# Section words the big parsers segment on. A CV using none of them is read as
# one undifferentiated block of text.
ATS_HEADINGS = (
    "experience", "employment", "work history",
    "education", "skills", "summary", "profile", "certification",
)

# Text that was UTF-8 and got decoded as Latin-1 somewhere in the chain. Built
# from code points rather than typed out, so this file does not itself contain
# the damage it looks for.
def _garble(code_point: int) -> str:
    return chr(code_point).encode("utf-8").decode("latin-1")


MOJIBAKE = (
    _garble(0xF8),            # o with a stroke
    _garble(0xE6),            # ae
    _garble(0xE5),            # a with a ring
    _garble(0xFC),            # u with a diaeresis
    _garble(0x2014)[:2],      # the start of a mangled dash or quote
    chr(0xE2) + chr(0x20AC),  # the same, as Windows-1252 shows it
    chr(0xFFFD),              # the replacement character itself
)

# Ligature code points. Valid Unicode, and a real problem: a parser searching
# for "identify" does not find a text layer that spells it with the fi ligature.
LIGATURES = {
    chr(0xFB00): "ff",
    chr(0xFB01): "fi",
    chr(0xFB02): "fl",
    chr(0xFB03): "ffi",
    chr(0xFB04): "ffl",
}

LATEX_RESIDUE = re.compile(r"\\[a-zA-Z]{2,}|\\\\|\$\\|\{\\")

# Words too common to say anything about coverage.
STOPWORDS = {
    "a", "about", "all", "an", "and", "any", "are", "as", "at", "be", "been",
    "both", "but", "by", "can", "for", "from", "has", "have", "how", "in",
    "into", "is", "it", "its", "more", "most", "not", "of", "on", "one", "or",
    "our", "out", "over", "role", "should", "such", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "to", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "who", "will",
    "with", "would", "you", "your", "job", "work", "team", "teams", "years",
    "experience", "working", "well", "also", "new", "other", "within",
    # Corporate filler. Present in every posting, absent from every good CV,
    # and each one crowds a real term out of the top of the list.
    "ability", "across", "basis", "business", "clear", "company", "ensure",
    "ensuring", "good", "help", "including", "make", "opportunity", "part",
    "people", "position", "provide", "responsible", "solution", "solutions",
    "strong", "take", "us", "using", "want", "way", "while", "world",
}

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass
class Result:
    """One check, its verdict, and what to do about it."""

    name: str
    verdict: str
    detail: str
    fix: str = ""


def _flat(text: str) -> str:
    """
    Comparable form of a piece of text: composed Unicode, lower case, runs of
    whitespace collapsed. Extractors insert spaces and line breaks inside a run
    of text, and some return accented letters as a base letter plus a combining
    mark, so both sides are flattened before they are compared.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


# --- Getting the text out ----------------------------------------------------

def extract_pypdf(pdf: Path) -> tuple[list[str], str | None]:
    """(pages, error). Returns ([], reason) when pypdf cannot be used."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return [], (
            "pypdf is not installed. Install it with: pip install pypdf  "
            "(or check with Poppler instead: --extractor pdftotext)"
        )
    try:
        reader = PdfReader(str(pdf))
        return [page.extract_text() or "" for page in reader.pages], None
    except Exception as exc:  # a corrupt PDF is a result, not a crash
        return [], f"pypdf could not read it: {exc}"


def extract_pdftotext(pdf: Path) -> tuple[list[str], str | None]:
    """
    (pages, error) through Poppler. `-layout` is deliberately not used: an ATS
    reads the raw stream order, and asking Poppler to reconstruct columns would
    hide exactly the reading-order problem this is looking for.
    """
    binary = shutil.which("pdftotext")
    if not binary:
        return [], "pdftotext is not on your PATH. `job-scout cv doctor` shows how to install Poppler"
    try:
        done = subprocess.run(
            [binary, "-enc", "UTF-8", str(pdf), "-"],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"pdftotext failed: {exc}"
    if done.returncode != 0:
        return [], f"pdftotext exited {done.returncode}: {done.stderr.decode(errors='replace')[:200]}"
    text = done.stdout.decode("utf-8", errors="replace")
    return text.split("\f")[:-1] or [text], None


EXTRACTORS = {"pypdf": extract_pypdf, "pdftotext": extract_pdftotext}


# --- What the CV is supposed to say ------------------------------------------

def expected_from_resume(path: Path) -> dict:
    """
    Name, email and phone as resume.yaml states them. Reads the raw file rather
    than validating it, so a draft that is missing a section can still be checked.
    Returns {} when the file is absent or unreadable.
    """
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
    found = {
        "name": str(data.get("name") or "").strip(),
        "email": str(contact.get("email") or "").strip(),
        "phone": str(contact.get("phone") or "").strip(),
    }
    return {key: value for key, value in found.items() if value}


def jd_keywords_from_text(text: str, limit: int = 25) -> list[str]:
    """
    The posting's own vocabulary, commonest first.

    Crude on purpose. This is a coverage check on the text layer, not a tailoring
    judgement: it only needs to know whether the words made it through the PDF.
    """
    counts: dict[str, int] = {}
    # Unicode-aware: an ASCII-only pattern cuts a word with a Nordic letter in it into
    # fragments and then reports them all as missing from the CV.
    for word in re.findall(r"[^\W\d_][\w+#./-]{2,}", text.lower(), re.UNICODE):
        word = word.strip("./-")
        if len(word) < 3 or word in STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, count in ranked if count >= 2][:limit]


# --- The checks. Each takes text and returns a Result ------------------------

def check_text_layer(pages: list[str], floor: int) -> Result:
    total = sum(len(page.strip()) for page in pages)
    if total >= floor:
        return Result("text layer", PASS, f"{total} characters extracted")
    return Result(
        "text layer", FAIL,
        f"only {total} characters extracted, expected at least {floor}",
        "The PDF has little or no selectable text. Check that the fonts are "
        "embedded and that nothing on the page is a raster image.",
    )


def check_pages(pages: list[str], limit: int) -> Result:
    if len(pages) <= limit:
        return Result("pages", PASS, f"{len(pages)} page(s)")
    return Result(
        "pages", FAIL, f"{len(pages)} pages, limit is {limit}",
        "Cut the lowest-value lines, or raise the limit with --max-pages if a longer CV is right.",
    )


def _phone_found(expected_phone: str, text: str) -> bool:
    """
    Digits are compared, not text, because extractors put spaces inside a number.
    A phone written with a country code in resume.yaml still counts when the PDF
    shows only the national part, so the last eight digits are accepted too.
    """
    wanted = re.sub(r"\D", "", expected_phone)
    if not wanted:
        return True
    digits = re.sub(r"\D", "", text)
    return wanted in digits or (len(wanted) > 8 and wanted[-8:] in digits)


def check_contact(text: str, expected: dict) -> Result:
    if not expected:
        return Result(
            "contact", WARN, "no name, email or phone to check against",
            "Pass --resume resume.yaml, or --name, --email and --phone.",
        )

    flat = _flat(text)
    missing = []
    if "email" in expected and _flat(expected["email"]) not in flat:
        missing.append(f"email ({expected['email']})")
    if "phone" in expected and not _phone_found(expected["phone"], text):
        missing.append(f"phone ({expected['phone']})")
    if "name" in expected and _flat(expected["name"]) not in flat:
        missing.append(f"name ({expected['name']})")

    if not missing:
        return Result("contact", PASS, "name, email and phone all extract")
    verdict = FAIL if any(item.startswith(("email", "name")) for item in missing) else WARN
    return Result(
        "contact", verdict, "missing from the text layer: " + ", ".join(missing),
        "A detail that does not extract cannot be parsed into the application "
        "record. Check it is real text and not part of an image or a symbol font.",
    )


def check_reading_order(pages: list[str], expected: dict, window: int = 300) -> Result:
    if not pages or "name" not in expected:
        return Result("reading order", WARN, "no name to look for")
    surname = _flat(expected["name"].split()[-1])
    first_page = _flat(pages[0])
    if surname in first_page[:window]:
        return Result("reading order", PASS, f"name extracts at character {first_page.find(surname)}")
    position = first_page.find(surname)
    where = f"character {position}" if position >= 0 else "not on page 1 at all"
    return Result(
        "reading order", FAIL, f"the name is {where}, not in the first {window}",
        "Parsers take the opening lines as the candidate's name. Something is "
        "extracting ahead of the header. Check the header block comes first in "
        "the document, not just visually at the top.",
    )


def check_encoding(text: str) -> Result:
    damaged = [sequence for sequence in MOJIBAKE if sequence in text]
    if damaged:
        samples = []
        for sequence in damaged[:3]:
            index = text.find(sequence)
            samples.append(repr(text[max(0, index - 12):index + 12]))
        return Result(
            "encoding", FAIL, f"{len(damaged)} damaged sequence(s): " + "; ".join(samples),
            "The font encoding did not survive extraction. Accented letters break "
            "first. Check the PDF is built with a Unicode-capable engine and the "
            "fonts are embedded.",
        )

    ligatures = sorted(char for char in LIGATURES if char in text)
    if ligatures:
        plain = ", ".join(f"{char!r} for '{LIGATURES[char]}'" for char in ligatures)
        return Result(
            "encoding", WARN, f"ligature code points in the text layer: {plain}",
            "A parser searching for 'identify' will not match a text layer that "
            "spells it with a ligature. Harmless in most modern ATS, worth knowing about.",
        )
    return Result("encoding", PASS, "no mojibake, no ligature code points")


def check_residue(text: str) -> Result:
    found = sorted(set(LATEX_RESIDUE.findall(text)))
    if not found:
        return Result("residue", PASS, "no LaTeX in the text layer")
    return Result(
        "residue", FAIL, f"LaTeX in the extracted text: {', '.join(found[:6])}",
        "A macro did not expand. It is invisible on the page and lands verbatim "
        "in the parsed record.",
    )


def check_headings(text: str) -> Result:
    lowered = text.lower()
    present = sorted({word for word in ATS_HEADINGS if word in lowered})
    if len(present) >= 3:
        return Result("headings", PASS, f"found {', '.join(present)}")
    return Result(
        "headings", WARN, f"only found {', '.join(present) or 'none'}",
        "Workday, Greenhouse, Lever and Taleo segment on literal section words. "
        "Use Experience, Education and Skills rather than invented headings.",
    )


def check_keywords(text: str, keywords: list[str], floor: float) -> Result:
    if not keywords:
        return Result("keywords", WARN, "no job description given, or nothing to extract from it")
    lowered = text.lower()
    missing = [word for word in keywords if word not in lowered]
    covered = (len(keywords) - len(missing)) / len(keywords)
    detail = f"{covered:.0%} of the posting's {len(keywords)} commonest terms are in the PDF"
    if covered >= floor:
        if missing:
            detail += ". Absent: " + ", ".join(missing[:8])
        return Result("keywords", PASS, detail)
    return Result(
        "keywords", WARN, detail + ". Absent: " + ", ".join(missing[:12]),
        "Low coverage is sometimes correct: a term you have not earned stays out, "
        "and an honest CV outranks any keyword target. Check the list and decide "
        "term by term.",
    )


# --- Running them ------------------------------------------------------------

def run_checks(
    pages: list[str],
    expected: dict,
    keywords: list[str] | None = None,
    max_pages: int = 2,
    min_chars: int = 800,
    min_coverage: float = 0.6,
) -> list[Result]:
    """Every check over already-extracted pages. Pure, so a test needs no PDF."""
    text = "\n".join(pages)
    return [
        check_text_layer(pages, min_chars),
        check_pages(pages, max_pages),
        check_contact(text, expected),
        check_reading_order(pages, expected),
        check_encoding(text),
        check_residue(text),
        check_headings(text),
        check_keywords(text, keywords or [], min_coverage),
    ]


def verify(
    pdf: Path,
    expected: dict,
    jd_text: str | None = None,
    extractor: str = "pypdf",
    max_pages: int = 2,
    min_chars: int = 800,
    min_coverage: float = 0.6,
) -> tuple[list[Result], str]:
    """Extract with one reader, run the checks. Returns (results, extracted text)."""
    pages, error = EXTRACTORS[extractor](pdf)
    if error:
        return [Result("extract", FAIL, error)], ""
    keywords = jd_keywords_from_text(jd_text) if jd_text else []
    results = run_checks(pages, expected, keywords, max_pages, min_chars, min_coverage)
    return results, "\n".join(pages)


def report(pdf: Path, extractor: str, results: list[Result]) -> str:
    marks = {PASS: "ok  ", WARN: "warn", FAIL: "FAIL"}
    lines = [f"{pdf}  (read with {extractor})", ""]
    for result in results:
        lines.append(f"  [{marks[result.verdict]}] {result.name:14} {result.detail}")
        if result.fix and result.verdict != PASS:
            lines.extend(f"                        {part}" for part in _wrap(result.fix, 72))
    failures = sum(r.verdict == FAIL for r in results)
    warnings = sum(r.verdict == WARN for r in results)
    passed = sum(r.verdict == PASS for r in results)
    lines += ["", f"  {failures} failed, {warnings} warned, {passed} passed."]
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out
