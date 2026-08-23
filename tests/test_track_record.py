"""
outcomes.csv is optional. The tests that matter most are the ones proving that
its absence, or its being malformed, changes nothing about whether a run works.
"""

import pytest

from job_scout import track_record


def _write(tmp_path, text: str):
    path = tmp_path / "outcomes.csv"
    path.write_text(text, encoding="utf-8")
    return path


# ─── Absent or unusable means "carry on" ──────────────────────────────────────

def test_a_missing_file_is_not_a_problem(tmp_path):
    assert track_record.read_outcomes(tmp_path / "nothing.csv") == []
    assert track_record.build_context(tmp_path / "nothing.csv") == ""


def test_an_empty_file_is_not_a_problem(tmp_path):
    assert track_record.build_context(_write(tmp_path, "")) == ""


def test_a_header_with_no_rows_is_not_a_problem(tmp_path):
    assert track_record.build_context(_write(tmp_path, "title,company,status\n")) == ""


def test_wrong_columns_are_reported_and_ignored(tmp_path, caplog):
    path = _write(tmp_path, "job,firm,outcome\nSRE,Acme,offer\n")
    assert track_record.read_outcomes(path) == []
    assert "missing the column" in caplog.text
    assert "title,company,status" in caplog.text


def test_rows_missing_a_status_are_skipped(tmp_path):
    path = _write(
        tmp_path,
        "title,company,status\nSRE,Acme,\nPlatform Engineer,Halden,offer\n",
    )
    assert len(track_record.read_outcomes(path)) == 1


def test_extra_columns_are_ignored(tmp_path):
    path = _write(
        tmp_path,
        "title,company,status,date,notes\n"
        "SRE,Acme,rejected,2026-01-01,they went internal\n",
    )
    rows = track_record.read_outcomes(path)
    assert len(rows) == 1
    assert rows[0]["title"] == "SRE"


def test_a_byte_order_mark_from_excel_is_handled(tmp_path):
    path = tmp_path / "outcomes.csv"
    path.write_text("title,company,status\nSRE,Acme,offer\n", encoding="utf-8-sig")
    assert len(track_record.read_outcomes(path)) == 1


# ─── Classification ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "status,expected",
    [
        ("offer", "offer"),
        ("Offer accepted", "offer"),
        ("rejected", "rejected"),
        ("Rejected after final round", "rejected"),
        ("declined", "rejected"),
        ("interviewing", "interviewing"),
        ("first screen booked", "interviewing"),
        ("technical call next week", "interviewing"),
        ("withdrawn", "withdrawn"),
        ("no response", "no_response"),
        ("ghosted", "no_response"),
        ("applied", "applied"),
        ("submitted", "applied"),
        ("something else entirely", "other"),
        ("", "other"),
    ],
)
def test_status_classification(status, expected):
    assert track_record.classify(status) == expected


def test_rejected_beats_interview_when_both_words_appear():
    assert track_record.classify("rejected after interview") == "rejected"


# ─── The block that reaches the prompt ────────────────────────────────────────

def test_context_counts_and_names_the_outcomes(tmp_path):
    path = _write(
        tmp_path,
        "title,company,status\n"
        "Platform Engineer,Northwind Energy,offer\n"
        "SRE,Halden Data,interviewing\n"
        "Cloud Engineer,Vestbridge,rejected\n"
        "DevOps Engineer,Meridian,no response\n",
    )
    context = track_record.build_context(path)
    assert "4 applications" in context
    assert "2 reached interview or offer" in context
    assert "Northwind Energy" in context
    assert "Converted:" in context
    assert "Did not convert:" in context


def test_context_is_capped_so_the_prompt_does_not_balloon(tmp_path):
    rows = "".join(f"Role {i},Company {i},rejected\n" for i in range(60))
    context = track_record.build_context(_write(tmp_path, f"title,company,status\n{rows}"))
    assert context.count("  - ") <= track_record._MAX_LISTED + 1
    assert "more)" in context


def test_a_row_with_only_a_title_still_counts(tmp_path):
    path = _write(tmp_path, "title,company,status\nPlatform Engineer,,offer\n")
    assert "Platform Engineer" in track_record.build_context(path)
