"""
calibrate.py: does the score predict anything?

`stats` says what the scorer produced. This says whether it was right. It takes
the outcomes you recorded in outcomes.csv, finds what the scout scored each of
those postings at the time, and puts the two side by side:

    job-scout calibrate
    job-scout calibrate --min-similarity 0.4

Reading it:

  A score is only useful if applications that scored higher convert better than
  applications that scored lower. That is the whole claim, and it is testable.
  If the bands come out flat, the number is decoration and the threshold is an
  arbitrary line through noise. If they come out inverted, the profile is
  describing a job you do not actually get hired for.

  Rates are over applications you actually sent. Postings you read and skipped
  are counted separately, because a deliberate no is evidence about the posting
  rather than a loss.

This command reads. It never edits config.yaml, the threshold, the profile, or
outcomes.csv. Deciding what to do about a flat curve is yours; the point of
splitting it out is that the number is not quietly tuned by the thing being
measured.

## The join

outcomes.csv records a title and a company. jobs.db records the same two, as
the job board spelled them, plus the score. Nothing links them but those two
strings, so they are matched by overlapping words with the company required to
agree. Anything below the similarity floor is reported as unmatched rather than
guessed at: a wrong join is worse than a missing one, because it silently moves
a real outcome into the wrong band.
"""

import re
import sqlite3
from pathlib import Path

from . import track_record

# Below this many sent-and-decided applications, any rate is one person's
# anecdote with a percent sign after it. career-ops uses five; the extra three
# buy a second band with something in it.
_MIN_DECIDED = 8

# Word overlap needed before two titles are called the same posting.
_MIN_SIMILARITY = 0.5

# A gap this wide between the top and bottom band is the difference between
# "the score is telling you something" and "these are the same number twice".
_SEPARATION_POINTS = 15.0

_BANDS = (
    (80, 101, "80 to 100"),
    (70, 80, "70 to 79"),
    (60, 70, "60 to 69"),
    (50, 60, "50 to 59"),
    (0, 50, "under 50"),
)

# Words that appear in every second job title and carry no identity.
_NOISE = {
    "a", "an", "and", "at", "for", "in", "of", "the", "to", "with",
    "m", "f", "d", "w", "x", "h",  # the (m/f/d) and (m/w/d) suffixes
}

# Legal forms, regions and filler that two unrelated employers share. Without
# this, "LEGO Group" matches "Nigel Wright Group" on the word they have in
# common and one company's outcome lands in another company's band.
_COMPANY_NOISE = _NOISE | {
    "group", "holding", "holdings", "company", "co", "corp", "corporation",
    "inc", "incorporated", "ltd", "limited", "llc", "plc", "ag", "sa", "se",
    "aps", "ab", "as", "bv", "nv", "oy", "gmbh", "kg",
    "denmark", "danmark", "nordic", "nordics", "scandinavia", "international",
    "global", "europe", "emea", "part",
}

# Sent, and the employer has said something or gone silent. These are the rows a
# rate can be computed over.
_SENT = ("applied", "interviewing", "offer", "rejected", "no_response")
_CONVERTED = ("interviewing", "offer")

# Phrases that mean somebody actually spoke to you. Deliberately narrower than
# the scorer's list: a bare "screen" is as often "rejected at CV screening",
# which is the opposite of a conversation, so it has to be qualified.
_INTERVIEW_TEXT = (
    "interview", "video screen", "phone screen", "screening call",
    "technical call", "video call", "onsite", "round ",
)


def _tokens(text: str) -> set[str]:
    words = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split()
    return {word for word in words if word not in _NOISE}


def _company_tokens(text: str) -> set[str]:
    """
    The words that actually identify an employer.

    Single letters are dropped whatever they are. "A/S" splits into "a" and
    "s", and a stop word list that happens to name one but not the other is a
    guard with a hole in it: every Danish company ends in A/S, so they all
    shared the token "s" and "Dampskibsselskabet NORDEN A/S" matched "Bunker
    Holding A/S" on it. One letter cannot identify an employer.

    If stripping the filler leaves nothing, the filler is the name, so the
    plain words are used rather than an empty set.
    """
    words = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split()
    distinct = {
        word for word in words if len(word) > 1 and word not in _COMPANY_NOISE
    }
    return distinct or set(words)


def _similarity(left: set[str], right: set[str]) -> float:
    """Jaccard. Symmetric on purpose: a one-sided measure calls every short
    title a match for every long one that happens to contain it."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def reached_interview(row: dict) -> bool:
    """
    Did this application get a conversation?

    `classify` answers "where did it end", so a rejection after three rounds
    classifies as rejected, which is right for the scorer and wrong here. The
    question a score has to predict is whether anyone wanted to talk.
    """
    if row["class"] in _CONVERTED:
        return True
    return any(hint in row["status"].lower() for hint in _INTERVIEW_TEXT)


def load_scores(db_path: Path) -> list[dict]:
    """Every scored posting the scout has ever seen."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT title, company, score, first_seen FROM seen_jobs "
            "WHERE score IS NOT NULL"
        ).fetchall()
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()
    return [
        {
            "title": title or "",
            "company": company or "",
            "score": float(score),
            "first_seen": first_seen or "",
            "title_tokens": _tokens(title),
            "company_tokens": _company_tokens(company),
        }
        for title, company, score, first_seen in rows
    ]


def match(outcome: dict, scored: list[dict], floor: float = _MIN_SIMILARITY) -> dict | None:
    """
    The scored posting this outcome came from, or None.

    The company has to agree. Two different employers advertising "Senior Cloud
    Architect" in the same month is not unusual, and without that test the join
    would happily put one company's rejection in another company's band.
    """
    title = _tokens(outcome["title"])
    company = _company_tokens(outcome["company"])
    if not title:
        return None

    best, best_score = None, 0.0
    for candidate in scored:
        both_named = bool(company and candidate["company_tokens"])
        agrees = both_named and bool(company & candidate["company_tokens"])
        similarity = _similarity(title, candidate["title_tokens"])
        if not agrees:
            if both_named:
                continue  # two named employers that are not the same employer
            # One side did not record an employer, so there is nothing to test
            # it against. Only an almost exact title is safe here.
            if similarity < 0.9:
                continue
        if similarity > best_score:
            best, best_score = candidate, similarity

    if best is None or best_score < floor:
        return None
    return dict(best, similarity=round(best_score, 2))


def band_of(score: float) -> str:
    for low, high, label in _BANDS:
        if low <= score < high:
            return label
    return _BANDS[-1][2]


def _percent(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:5.0f}%" if whole else "     ."


def render(
    db_path: Path,
    outcomes_path: Path,
    threshold: int = 70,
    floor: float = _MIN_SIMILARITY,
) -> str:
    """The whole report as text, so a caller can print it or send it."""
    outcomes = track_record.read_outcomes(Path(outcomes_path))
    if not outcomes:
        return (
            f"No outcomes at {outcomes_path}.\n"
            f"Nothing to calibrate against. Record how your applications ended "
            f"and this becomes the check on whether the score meant anything."
        )

    scored = load_scores(db_path)
    if not scored:
        return (
            f"No scored postings in {db_path}.\n"
            f"Calibration compares outcomes against what the scout scored them "
            f"at the time, so it needs a database with history in it."
        )

    joined, unmatched = [], []
    for row in outcomes:
        found = match(row, scored, floor)
        (joined if found else unmatched).append(
            dict(row, score=found["score"], similarity=found["similarity"])
            if found else row
        )

    sent = [row for row in joined if row["class"] in _SENT]
    skipped = [row for row in joined if row["class"] == "withdrawn"]
    in_flight = [row for row in joined if row["class"] == "other"]

    out: list[str] = [
        f"{len(outcomes)} recorded outcome(s); {len(joined)} matched to a score "
        f"the scout gave at the time.",
        f"{len(sent)} were sent and have an answer. Rates below are over those.",
    ]

    if len(sent) < _MIN_DECIDED:
        out.append("")
        out.append(
            f"Verdict: insufficient. {_MIN_DECIDED} sent applications with a "
            f"matched score is the floor for saying anything about a rate, and "
            f"there are {len(sent)}."
        )
        out.append(_shortfall_advice(unmatched, in_flight))
        out.extend(_evidence(sent, skipped, in_flight, unmatched, threshold))
        return "\n".join(out)

    by_band: dict[str, list[dict]] = {}
    for row in sent:
        by_band.setdefault(band_of(row["score"]), []).append(row)

    populated = [
        (label, by_band[label])
        for _, _, label in _BANDS
        if by_band.get(label)
    ]
    rates = {
        label: 100.0 * sum(reached_interview(r) for r in rows) / len(rows)
        for label, rows in populated
    }
    top, bottom = populated[0][0], populated[-1][0]
    spread = rates[top] - rates[bottom]

    if len(populated) < 2:
        verdict = (
            "insufficient. Every matched application is in one band, so there "
            "is nothing to compare it against."
        )
    elif spread >= _SEPARATION_POINTS:
        verdict = (
            f"separating. The {top} band reaches interview {spread:.0f} points "
            f"more often than the {bottom} band. The score is carrying real signal."
        )
    elif spread <= -_SEPARATION_POINTS:
        verdict = (
            f"inverted. The {bottom} band converts {abs(spread):.0f} points better "
            f"than the {top} band. The profile is describing the wrong job."
        )
    else:
        verdict = (
            f"flat. Top and bottom bands are {abs(spread):.0f} points apart, "
            f"inside the noise. The score is not yet telling you which "
            f"applications to make."
        )

    out.append("")
    out.append(f"Verdict: {verdict}")
    out.append("")
    out.append("  band        sent   reached interview   offer")
    for label, rows in populated:
        interviews = sum(reached_interview(r) for r in rows)
        offers = sum(r["class"] == "offer" for r in rows)
        marker = " <- threshold" if label.startswith(str(threshold)[:2]) else ""
        out.append(
            f"  {label:10} {len(rows):5}   {_percent(interviews, len(rows))} "
            f"({interviews:2})      {_percent(offers, len(rows))}{marker}"
        )

    out.extend(_evidence(sent, skipped, in_flight, unmatched, threshold))
    return "\n".join(out)


def _shortfall_advice(unmatched: list[dict], in_flight: list[dict]) -> str:
    if unmatched:
        return (
            f"{len(unmatched)} outcome(s) could not be matched to a score. Most "
            f"of those are applications you found yourself, before or outside the "
            f"scout, which have no score to calibrate."
        )
    if in_flight:
        return (
            f"{len(in_flight)} matched application(s) have no result yet. Update "
            f"their status when one arrives and they join the table."
        )
    return "Keep recording outcomes. This gets useful on its own."


def _evidence(
    sent: list[dict],
    skipped: list[dict],
    in_flight: list[dict],
    unmatched: list[dict],
    threshold: int,
) -> list[str]:
    """Everything the table left out, so the table cannot be read as the whole story."""
    out = ["", "What the table leaves out"]
    out.append(f"  {len(in_flight):3}  matched, still in flight, no result yet")
    out.append(f"  {len(unmatched):3}  outcomes with no matching score in the database")

    if skipped:
        above = sum(r["score"] >= threshold for r in skipped)
        out.append(
            f"  {len(skipped):3}  read and chosen not to apply, "
            f"{above} of them scored {threshold} or more"
        )
        if above:
            out.append(
                f"       Those {above} are the scorer's clearest misses: it said "
                f"yes and you said no with the full posting in front of you."
            )

    weak = [row for row in sent if row.get("similarity", 1.0) < 0.75]
    if weak:
        out.append(
            f"  {len(weak):3}  joined on a weak title match, worth checking by eye:"
        )
        for row in sorted(weak, key=lambda r: r["similarity"]):
            label = " at ".join(p for p in (row["title"], row["company"]) if p)
            out.append(f"       {row['similarity']:.2f}  {label[:60]}")
    return out
