"""
guard.py. Clean a posting before anything reads it, and say what was found.

Ported from tools/posting_guard.py in MadsLorentzen/ai-job-search (MIT). Two
checks only, the ones with a deterministic answer:

  * Invisible characters (zero-width, soft hyphen, byte-order mark, bidi
    controls) are removed and counted. A bidi override or isolate, or a
    zero-width character inside a word, is flagged as tampering.
  * Words that mix Latin letters with Cyrillic or Greek letters are listed.
    These are look-alike spoofs, such as a Cyrillic "а" inside "Аpple".

A flagged posting is still scored. The verdict travels with the job so the
user can see it.
"""

import re

_INVISIBLE = re.compile("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
_ZERO_WIDTH_IN_WORD = re.compile("\\w[\u200b-\u200d\u2060\ufeff]\\w")
_WORD = re.compile(r"\w+")
_LATIN = re.compile("[A-Za-z\u00c0-\u024f]")
_LOOKALIKE = re.compile("[\u0370-\u03ff\u0400-\u04ff]")

_GUARDED_FIELDS = ("title", "company", "description")
_LISTED_LOOKALIKES = 5


def clean_text(text: str) -> tuple[str, dict]:
    """Return (cleaned text, findings) for one piece of text."""
    if not text:
        return "", {"invisible": 0, "tampering": False, "lookalikes": []}
    tampering = bool(_BIDI.search(text) or _ZERO_WIDTH_IN_WORD.search(text))
    invisible = len(_INVISIBLE.findall(text))
    cleaned = _INVISIBLE.sub("", text)
    lookalikes = sorted(
        {word for word in _WORD.findall(cleaned) if _LATIN.search(word) and _LOOKALIKE.search(word)}
    )
    return cleaned, {"invisible": invisible, "tampering": tampering, "lookalikes": lookalikes}


def guard_job(job: dict) -> dict:
    """
    Clean the title, company and description of one job in place.

    Sets job["guard"] to one of three verdicts:

      "clean"                  nothing found
      "cleaned: ..."           invisible characters were removed. Not suspicious on
                               its own: zero-width joiners and soft hyphens are common
                               in pasted text.
      "flagged: ..."           tampering or look-alike words. Scored, and shown to you.

    Returns the job.
    """
    invisible = 0
    tampering = False
    lookalikes: set[str] = set()
    for field in _GUARDED_FIELDS:
        if field not in job:
            continue
        cleaned, found = clean_text(job.get(field) or "")
        job[field] = cleaned
        invisible += found["invisible"]
        tampering = tampering or found["tampering"]
        lookalikes.update(found["lookalikes"])

    flags = []
    if tampering:
        flags.append("bidi control or zero-width character inside a word")
    if lookalikes:
        shown = ", ".join(sorted(lookalikes)[:_LISTED_LOOKALIKES])
        flags.append(f"look-alike words: {shown}")
    notes = [f"{invisible} invisible characters removed"] if invisible else []

    if flags:
        job["guard"] = "flagged: " + "; ".join(flags + notes)
    elif notes:
        job["guard"] = "cleaned: " + "; ".join(notes)
    else:
        job["guard"] = "clean"
    return job


def is_flagged(verdict: str) -> bool:
    return verdict.startswith("flagged")
