"""
normalize.py. Keys that let the store recognise one advert under different spelling.

The same job reaches the scout from several boards, and each board writes the
title and company its own way: "Contoso Denmark A/S", "Contoso", "Østerby"
and "Osterby". These functions reduce that spelling to a key. They do not decide
whether a job is new. dedup.py does that, using these keys.
"""

import re
import unicodedata

# Legal and country words that differ between boards for the same employer.
# Dropped from company names only.
COMPANY_NOISE = frozenset({
    "a", "s", "as", "aps", "ab", "ltd", "llc", "gmbh", "inc", "corp", "co",
    "denmark", "danmark", "dk", "group",
})

_DANISH_LETTERS = str.maketrans({"æ": "ae", "ø": "o", "å": "a", "Æ": "ae", "Ø": "o", "Å": "a"})
_BRACKETED = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_NON_WORD = re.compile(r"[^a-z0-9]+")

# Most normalized words of a description that are kept for comparison. Long enough
# to cover the whole ad. Shorter heads were tried first and failed: a company's
# boilerplate intro, which opens many of its ads, made different jobs look identical.
DESCRIPTION_HEAD_WORDS = 3000
MIN_DESCRIPTION_WORDS = 30


def normalize_text(text: str) -> str:
    """Lowercase, fold accents and Danish letters, and keep only letters and digits, one space apart."""
    folded = (text or "").translate(_DANISH_LETTERS)
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    return _NON_WORD.sub(" ", folded.lower()).strip()


def title_key(title: str) -> str:
    """A title without bracketed extras such as job codes or locations in parentheses."""
    return normalize_text(_BRACKETED.sub(" ", title or ""))


def company_key(company: str) -> str:
    """A company name with legal suffixes and country words removed."""
    words = [word for word in normalize_text(company).split() if word not in COMPANY_NOISE]
    return " ".join(words)


def content_key(title: str, company: str) -> str:
    """The exact-match key for one advert, or "" when either part is missing."""
    t, c = title_key(title), company_key(company)
    return f"{t}|{c}" if t and c else ""


def title_words(title: str) -> frozenset[str]:
    return frozenset(title_key(title).split())


def description_head(description: str) -> str:
    """The description, normalized, up to DESCRIPTION_HEAD_WORDS words. Empty when too short to compare."""
    words = normalize_text(description).split()
    if len(words) < MIN_DESCRIPTION_WORDS:
        return ""
    return " ".join(words[:DESCRIPTION_HEAD_WORDS])


def shingles(head: str, size: int = 3) -> frozenset[tuple[str, ...]]:
    """Runs of `size` consecutive words. Two texts that share many runs are probably the same text."""
    words = head.split()
    return frozenset(tuple(words[i:i + size]) for i in range(max(0, len(words) - size + 1)))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
