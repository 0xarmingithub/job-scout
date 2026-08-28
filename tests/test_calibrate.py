"""
`job-scout calibrate`.

Two things have to hold. A wrong join is worse than a missing one, because it
moves a real outcome into a band it did not come from and nobody can see that
happened. And a verdict must never be stated on data that cannot support it: an
encouraging table over four applications is how a threshold gets tuned to noise.
"""

import csv

from job_scout import calibrate
from job_scout.calibrate import band_of, match, reached_interview, render
from job_scout.dedup import JobStore


def _db(tmp_path, jobs):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([
        {
            "url": f"https://example.test/{index}",
            "title": title, "company": company, "location": "Copenhagen",
            "site": "linkedin", "status": "new", "score": score,
            "date_posted": "", "search_term": "architect",
        }
        for index, (title, company, score) in enumerate(jobs)
    ])
    return tmp_path / "jobs.db"


def _outcomes(tmp_path, rows):
    path = tmp_path / "outcomes.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["title", "company", "status"])
        writer.writerows(rows)
    return path


def _scored(*jobs):
    return [
        {
            "title": title, "company": company, "score": float(score),
            "first_seen": "2026-05-01",
            "title_tokens": calibrate._tokens(title),
            "company_tokens": calibrate._company_tokens(company),
        }
        for title, company, score in jobs
    ]


# ─── Bands ────────────────────────────────────────────────────────────────────

def test_the_bands_do_not_overlap_or_leave_a_gap():
    assert band_of(100) == "80 to 100"
    assert band_of(80) == "80 to 100"
    assert band_of(79.9) == "70 to 79"
    assert band_of(70) == "70 to 79"
    assert band_of(49) == "under 50"
    assert band_of(0) == "under 50"


# ─── The join ─────────────────────────────────────────────────────────────────

def test_the_same_posting_is_found():
    found = match(
        {"title": "Senior Cloud Architect", "company": "Ambu", "status": "", "class": ""},
        _scored(("Senior Cloud Architect", "Ambu", 85)),
    )
    assert found["score"] == 85
    assert found["similarity"] == 1.0


def test_the_same_title_at_a_different_employer_is_not_a_match():
    assert match(
        {"title": "Senior Cloud Architect", "company": "Ambu", "status": "", "class": ""},
        _scored(("Senior Cloud Architect", "Coloplast", 85)),
    ) is None


def test_a_shared_legal_suffix_is_not_a_shared_employer():
    """
    "LEGO Group" and "Nigel Wright Group" have one word in common and nothing
    else. Matching on it put a recruiter's posting in LEGO's band.
    """
    assert match(
        {"title": "Lead Engineer", "company": "LEGO Group", "status": "", "class": ""},
        _scored(("Lead Engineer", "Nigel Wright Group", 40)),
    ) is None


def test_a_shared_legal_form_letter_is_not_a_shared_employer():
    """
    "A/S" splits into "a" and "s". Filtering one and not the other left every
    Danish company sharing the token "s", which is the whole market this was
    written for, and the employer guard passed on it.
    """
    assert calibrate._company_tokens("Dampskibsselskabet NORDEN A/S") == {
        "dampskibsselskabet", "norden",
    }
    assert match(
        {"title": "Senior Solution Architect", "company": "Dampskibsselskabet NORDEN A/S",
         "status": "", "class": ""},
        _scored(("Senior Solution Architect, Network", "Bunker Holding A/S", 0)),
    ) is None


def test_a_short_company_name_survives_the_filter():
    """EY, n8n and 3M are two or three characters and are still the name."""
    for name in ("EY", "n8n", "3M", "WSA"):
        assert calibrate._company_tokens(name) == {name.lower()}


def test_a_company_written_two_ways_still_matches():
    found = match(
        {"title": "Senior Software Architect", "company": "WSA", "status": "", "class": ""},
        _scored(("Senior Software Architect", "WSA - Wonderful Sound for All", 90)),
    )
    assert found["score"] == 90


def test_an_unnamed_employer_needs_an_almost_exact_title():
    scored = _scored(
        ("Senior Cloud Architect for the Platform Team", "", 85),
        ("Senior Cloud Architect", "", 60),
    )
    row = {"title": "Senior Cloud Architect", "company": "", "status": "", "class": ""}
    assert match(row, scored)["score"] == 60


def test_a_title_too_different_is_left_unmatched():
    assert match(
        {"title": "Integrations Engineer", "company": "Acme", "status": "", "class": ""},
        _scored(("Warehouse Operative", "Acme", 20)),
    ) is None


def test_the_floor_can_be_raised():
    row = {"title": "Senior Integrations Engineer", "company": "Acme", "status": "", "class": ""}
    scored = _scored(("Senior Software Engineer", "Acme", 75))
    assert match(row, scored, floor=0.5) is not None
    assert match(row, scored, floor=0.75) is None


# ─── What counts as reaching interview ────────────────────────────────────────

def test_a_rejection_after_interview_still_counts_as_an_interview():
    """
    `classify` says where it ended, which is what the scorer wants. Here the
    question is whether anyone wanted to talk, and they did.
    """
    assert reached_interview({"class": "rejected", "status": "rejected after interview"})
    assert not reached_interview({"class": "rejected", "status": "rejected at screening"})


def test_an_offer_counts():
    assert reached_interview({"class": "offer", "status": "offer accepted"})


# ─── The report ───────────────────────────────────────────────────────────────

def test_no_outcomes_says_what_is_missing(tmp_path):
    out = render(_db(tmp_path, [("Architect", "Acme", 80)]), tmp_path / "nothing.csv")
    assert "No outcomes" in out
    assert "Record how your applications ended" in out


def test_no_database_says_what_is_missing(tmp_path):
    out = render(tmp_path / "nothing.db", _outcomes(tmp_path, [["Architect", "Acme", "rejected"]]))
    assert "No scored postings" in out


def test_too_few_outcomes_refuses_to_state_a_rate(tmp_path):
    db = _db(tmp_path, [("Cloud Architect", "Acme", 85), ("Data Engineer", "Beta", 60)])
    outcomes = _outcomes(tmp_path, [
        ["Cloud Architect", "Acme", "interviewing"],
        ["Data Engineer", "Beta", "rejected"],
    ])
    out = render(db, outcomes)
    assert "Verdict: insufficient" in out
    assert "reached interview" not in out  # no table at all


def test_a_score_that_predicts_is_called_separating(tmp_path):
    jobs, rows = [], []
    for index in range(5):
        jobs.append((f"Cloud Architect {index}", f"High{index}", 85))
        rows.append([f"Cloud Architect {index}", f"High{index}", "interviewing"])
    for index in range(5):
        jobs.append((f"Data Engineer {index}", f"Low{index}", 45))
        rows.append([f"Data Engineer {index}", f"Low{index}", "rejected"])

    out = render(_db(tmp_path, jobs), _outcomes(tmp_path, rows))
    assert "Verdict: separating" in out
    assert "80 to 100" in out
    assert "under 50" in out


def test_a_score_that_predicts_backwards_is_called_inverted(tmp_path):
    jobs, rows = [], []
    for index in range(5):
        jobs.append((f"Cloud Architect {index}", f"High{index}", 85))
        rows.append([f"Cloud Architect {index}", f"High{index}", "rejected"])
    for index in range(5):
        jobs.append((f"Data Engineer {index}", f"Low{index}", 45))
        rows.append([f"Data Engineer {index}", f"Low{index}", "interviewing"])

    assert "Verdict: inverted" in render(_db(tmp_path, jobs), _outcomes(tmp_path, rows))


def test_a_score_that_predicts_nothing_is_called_flat(tmp_path):
    jobs, rows = [], []
    for index in range(4):
        jobs.append((f"Cloud Architect {index}", f"High{index}", 85))
        rows.append([
            f"Cloud Architect {index}", f"High{index}",
            "interviewing" if index < 2 else "rejected",
        ])
    for index in range(4):
        jobs.append((f"Data Engineer {index}", f"Low{index}", 45))
        rows.append([
            f"Data Engineer {index}", f"Low{index}",
            "interviewing" if index < 2 else "rejected",
        ])

    assert "Verdict: flat" in render(_db(tmp_path, jobs), _outcomes(tmp_path, rows))


def test_everything_in_one_band_is_not_a_verdict(tmp_path):
    jobs, rows = [], []
    for index in range(9):
        jobs.append((f"Cloud Architect {index}", f"Acme{index}", 85))
        rows.append([
            f"Cloud Architect {index}", f"Acme{index}",
            "interviewing" if index < 4 else "rejected",
        ])
    out = render(_db(tmp_path, jobs), _outcomes(tmp_path, rows))
    assert "Verdict: insufficient" in out
    assert "nothing to compare it against" in out


def test_postings_you_skipped_are_counted_apart_from_losses(tmp_path):
    jobs, rows = [], []
    for index in range(9):
        jobs.append((f"Cloud Architect {index}", f"Acme{index}", 85))
        rows.append([f"Cloud Architect {index}", f"Acme{index}", "rejected"])
    jobs.append(("Warehouse Lead", "Skipme", 90))
    rows.append(["Warehouse Lead", "Skipme", "withdrawn, not applied"])

    out = render(_db(tmp_path, jobs), _outcomes(tmp_path, rows), threshold=70)
    assert "read and chosen not to apply, 1 of them scored 70 or more" in out
    assert "clearest misses" in out


def test_an_unmatched_outcome_is_reported_not_guessed(tmp_path):
    db = _db(tmp_path, [("Cloud Architect", "Acme", 85)])
    outcomes = _outcomes(tmp_path, [
        ["Cloud Architect", "Acme", "interviewing"],
        ["Head of Catering", "Nowhere Ltd", "rejected"],
    ])
    out = render(db, outcomes)
    assert "1 matched to a score" in out
    assert "1  outcomes with no matching score" in out


def test_a_weak_join_is_named_so_it_can_be_checked(tmp_path):
    jobs, rows = [], []
    for index in range(9):
        jobs.append((f"Cloud Architect {index}", f"Acme{index}", 85))
        rows.append([f"Cloud Architect {index}", f"Acme{index}", "rejected"])
    jobs.append(("Senior Software Engineer", "Enkel Energi", 75))
    rows.append(["Senior Integrations Engineer", "Enkel", "rejected"])

    out = render(_db(tmp_path, jobs), _outcomes(tmp_path, rows))
    assert "weak title match" in out
    assert "Senior Integrations Engineer at Enkel" in out


def test_calibrate_writes_nothing(tmp_path):
    """It measures the scorer. A measurement that edits its subject is not one."""
    db = _db(tmp_path, [("Cloud Architect", "Acme", 85)])
    outcomes = _outcomes(tmp_path, [["Cloud Architect", "Acme", "interviewing"]])
    before = {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    render(db, outcomes)
    after = {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert before == after
