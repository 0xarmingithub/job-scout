"""
guard.py. Invisible characters are removed and counted, tampering and look-alike
words are flagged, and ordinary Danish text is left alone.
"""

from job_scout.guard import clean_text, guard_job, is_flagged


def test_clean_danish_text_is_unchanged():
    text = "Udvikler til Odense. Æble, øl og åbent kontor."
    cleaned, found = clean_text(text)
    assert cleaned == text
    assert found == {"invisible": 0, "tampering": False, "lookalikes": []}


def test_invisible_characters_are_removed_and_counted():
    cleaned, found = clean_text("Pyt​hon﻿ developer")
    assert cleaned == "Python developer"
    assert found["invisible"] == 2
    assert found["tampering"] is True  # zero-width inside a word


def test_bidi_override_is_tampering():
    _, found = clean_text("Senior ‮euqnoh")
    assert found["tampering"] is True


def test_zero_width_inside_a_word_is_tampering():
    _, found = clean_text("Ja​va")
    assert found["tampering"] is True


def test_zero_width_at_the_edge_of_a_word_is_not_tampering():
    cleaned, found = clean_text("Java​ developer")
    assert cleaned == "Java developer"
    assert found["invisible"] == 1
    assert found["tampering"] is False


def test_cyrillic_lookalike_inside_a_latin_word_is_listed():
    _, found = clean_text("Work at Аpple")  # Cyrillic А then Latin pple
    assert found["lookalikes"] == ["Аpple"]


def test_a_pure_greek_word_is_not_a_lookalike():
    _, found = clean_text("Mathematics: αβγ")
    assert found["lookalikes"] == []


def test_guard_job_cleans_every_text_field_and_flags_tampering():
    job = {"title": "Dev​", "company": "Østerby", "description": "Python ‮abc"}
    guard_job(job)
    assert job["title"] == "Dev"
    assert job["company"] == "Østerby"
    assert "bidi control" in job["guard"]
    assert is_flagged(job["guard"])


def test_invisible_characters_alone_are_cleaned_not_flagged():
    job = {"title": "Python‍ developer", "company": "Acme", "description": "Soft­ware"}
    guard_job(job)
    assert job["title"] == "Python developer"
    assert job["description"] == "Software"
    assert job["guard"] == "cleaned: 2 invisible characters removed"
    assert not is_flagged(job["guard"])


def test_a_clean_job_says_clean():
    job = {"title": "Engineer", "company": "Meridian", "description": "Wind."}
    guard_job(job)
    assert job["guard"] == "clean"
    assert not is_flagged(job["guard"])
