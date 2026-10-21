"""
`job-scout cv verify`: the checks as pure functions over text, and the extractors
against a PDF built by hand.

A check that always passes looks exactly like a CV that is fine, so each check has
a case that makes it fail and a case that makes it pass.
"""

import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml
from cv_helpers import RESUME, good_cv_lines, write_pdf

from job_scout.cv import verify as v

# Built from code points, so this file holds neither the accented letters nor the
# damage the tests look for.
O_STROKE = chr(0xF8)
AE_UP, AE_LOW = chr(0xC6), chr(0xE6)
E_ACUTE, COMBINING_ACUTE = chr(0xE9), chr(0x301)
LIGATURE_FI = chr(0xFB01)
MOJIBAKE_O_STROKE = O_STROKE.encode("utf-8").decode("latin-1")

PERSON = {"name": "Morgan Reyes", "email": "morgan.reyes@example.com", "phone": "+45 12 34 56 78"}


# --- Reading what the CV should say -----------------------------------------

def test_expected_values_come_from_resume_yaml(tmp_path):
    path = tmp_path / "resume.yaml"
    path.write_text(yaml.safe_dump(RESUME), encoding="utf-8")
    assert v.expected_from_resume(path) == PERSON


def test_an_incomplete_resume_still_yields_what_it_has(tmp_path):
    path = tmp_path / "resume.yaml"
    path.write_text("name: Morgan Reyes\ncontact: {email: m@example.com}\n", encoding="utf-8")
    assert v.expected_from_resume(path) == {"name": "Morgan Reyes", "email": "m@example.com"}


def test_a_missing_or_broken_resume_is_empty_not_a_crash(tmp_path):
    assert v.expected_from_resume(tmp_path / "nothing.yaml") == {}
    broken = tmp_path / "broken.yaml"
    broken.write_text("name: [unclosed", encoding="utf-8")
    assert v.expected_from_resume(broken) == {}
    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("just text", encoding="utf-8")
    assert v.expected_from_resume(scalar) == {}


# --- The individual checks ---------------------------------------------------

def test_an_image_only_pdf_fails_the_text_layer_check():
    assert v.check_text_layer([""], 800).verdict == v.FAIL
    assert v.check_text_layer(["x" * 900], 800).verdict == v.PASS


def test_a_third_page_fails():
    assert v.check_pages(["a", "b"], 2).verdict == v.PASS
    assert v.check_pages(["a", "b", "c"], 2).verdict == v.FAIL


def test_a_missing_email_fails_and_a_missing_phone_only_warns():
    assert v.check_contact("Morgan Reyes\nOdense\n12345678", PERSON).verdict == v.FAIL
    assert v.check_contact("Morgan Reyes\nmorgan.reyes@example.com", PERSON).verdict == v.WARN
    body = "Morgan Reyes morgan.reyes@example.com (+45) 12 34 56 78"
    assert v.check_contact(body, PERSON).verdict == v.PASS


def test_no_expected_values_is_a_warning_that_says_how_to_fix_it():
    result = v.check_contact("anything", {})
    assert result.verdict == v.WARN
    assert "--resume" in result.fix


def test_a_phone_broken_across_spaces_still_counts():
    """Extractors insert whitespace inside a number. Digits are compared, not text."""
    body = "Morgan Reyes morgan.reyes@example.com 4 5 1 2 3 4 5 6 7 8"
    assert v.check_contact(body, PERSON).verdict == v.PASS


def test_a_phone_shown_without_its_country_code_still_counts():
    body = "Morgan Reyes morgan.reyes@example.com 12 34 56 78"
    assert v.check_contact(body, PERSON).verdict == v.PASS


def test_a_different_phone_number_is_not_accepted():
    body = "Morgan Reyes morgan.reyes@example.com 99 88 77 66"
    assert v.check_contact(body, PERSON).verdict == v.WARN


def test_a_name_split_across_lines_still_counts():
    body = "Morgan\nReyes  morgan.reyes@example.com"
    assert v.check_contact(body, {"name": "Morgan Reyes", "email": PERSON["email"]}).verdict == v.PASS
    assert v.check_reading_order(["Morgan\n  Reyes"], PERSON).verdict == v.PASS


def test_a_decomposed_accent_in_the_pdf_matches_a_composed_name():
    """Some extractors return a base letter plus a combining mark."""
    composed_name = {"name": f"{E_ACUTE}mile Fabrikam"}
    decomposed_pdf = f"e{COMBINING_ACUTE}mile Fabrikam"
    assert v.check_contact(decomposed_pdf, composed_name).verdict == v.PASS
    assert v.check_contact("emile Fabrikam", composed_name).verdict == v.FAIL


def test_a_name_that_extracts_after_the_sidebar_fails():
    buried = "SKILLS\n" + "Azure Kubernetes Terraform " * 40 + "\nMorgan Reyes"
    assert v.check_reading_order([buried], PERSON).verdict == v.FAIL
    assert v.check_reading_order(["Morgan Reyes\nOdense"], PERSON).verdict == v.PASS


def test_a_name_missing_from_page_one_says_so():
    result = v.check_reading_order(["nothing here"], PERSON)
    assert result.verdict == v.FAIL
    assert "not on page 1" in result.detail


def test_no_name_to_look_for_is_a_warning():
    assert v.check_reading_order(["text"], {"email": "m@example.com"}).verdict == v.WARN


def test_mojibake_fails_and_a_ligature_only_warns():
    assert v.check_encoding(f"based in S{MOJIBAKE_O_STROKE}nderborg").verdict == v.FAIL
    assert v.check_encoding(f"identi{LIGATURE_FI}ed the fault").verdict == v.WARN
    assert v.check_encoding(f"identified the fault in S{O_STROKE}nderborg").verdict == v.PASS


def test_the_replacement_character_fails():
    assert v.check_encoding(f"a {chr(0xFFFD)} b").verdict == v.FAIL


def test_an_unexpanded_macro_fails():
    assert v.check_residue(r"Led \textbf{four} engineers").verdict == v.FAIL
    assert v.check_residue("Led four engineers").verdict == v.PASS


def test_invented_headings_warn():
    assert v.check_headings("Career Highlights\nWhat I Bring").verdict == v.WARN
    assert v.check_headings("Experience\nEducation\nSkills").verdict == v.PASS


def test_keyword_coverage_is_measured_against_the_posting():
    keywords = ["kubernetes", "terraform", "azure", "kafka"]
    assert v.check_keywords("azure kubernetes terraform kafka", keywords, 0.6).verdict == v.PASS
    result = v.check_keywords("azure only", keywords, 0.6)
    assert result.verdict == v.WARN
    assert "kubernetes" in result.detail


def test_no_posting_given_is_a_warning_not_a_pass():
    assert v.check_keywords("anything at all", [], 0.6).verdict == v.WARN


# --- Pulling keywords out of a posting --------------------------------------

def test_a_non_ascii_word_stays_in_one_piece():
    words = v.jd_keywords_from_text(f"{AE_UP}r{O_STROKE} Fabrikam. " * 3 + "kubernetes kubernetes")
    assert f"{AE_LOW}r{O_STROKE}" in words
    assert "r" not in words


def test_corporate_filler_does_not_crowd_out_real_terms():
    text = (
        "business business company company ensuring ensuring solutions solutions "
        "kubernetes kubernetes terraform terraform"
    )
    assert set(v.jd_keywords_from_text(text)) == {"kubernetes", "terraform"}


def test_a_word_used_once_is_not_a_keyword():
    assert v.jd_keywords_from_text("kubernetes kubernetes cobol") == ["kubernetes"]


# --- All the checks together, on text ---------------------------------------

def test_a_good_cv_has_no_failures():
    results = v.run_checks(["\n".join(good_cv_lines())], PERSON, min_chars=400)
    assert [r.name for r in results if r.verdict == v.FAIL] == []


def test_every_check_can_fail_at_once():
    pages = ["x\n" * 3, "y", "z"]  # tiny, three pages
    results = v.run_checks(pages, PERSON, ["kubernetes"], max_pages=2)
    failed = {r.name for r in results if r.verdict == v.FAIL}
    assert {"text layer", "pages", "contact", "reading order"} <= failed


def test_the_report_names_each_failure_and_what_to_do():
    results = [v.check_pages(["a", "b", "c"], 2), v.check_residue("clean")]
    text = v.report(Path("cv.pdf"), "pypdf", results)
    assert "FAIL" in text and "pages" in text
    assert "1 failed" in text and "1 passed" in text


# --- The extractors, against a PDF made by hand -----------------------------

needs_pypdf = pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None, reason="pypdf is an optional extra"
)


@needs_pypdf
def test_pypdf_reads_the_text_back_out_of_a_made_pdf(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    pages, error = v.extract_pypdf(pdf)
    assert error is None
    assert len(pages) == 1
    assert "Morgan Reyes" in pages[0]
    assert "morgan.reyes@example.com" in pages[0]


@needs_pypdf
def test_a_made_pdf_passes_every_check(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    results, text = v.verify(pdf, PERSON, min_chars=400)
    assert [(r.name, r.detail) for r in results if r.verdict == v.FAIL] == []
    assert "Kubernetes" in text


@needs_pypdf
def test_accented_letters_survive_the_round_trip(tmp_path):
    lines = ["Morgan Reyes", f"Based in S{O_STROKE}nderborg"] + good_cv_lines()[2:]
    pdf = write_pdf(tmp_path / "cv.pdf", [lines])
    results, text = v.verify(pdf, PERSON, min_chars=400)
    assert f"S{O_STROKE}nderborg" in text
    assert next(r for r in results if r.name == "encoding").verdict == v.PASS


@needs_pypdf
def test_mojibake_in_a_real_pdf_is_caught(tmp_path):
    lines = ["Morgan Reyes", f"Based in S{MOJIBAKE_O_STROKE}nderborg"] + good_cv_lines()[2:]
    pdf = write_pdf(tmp_path / "cv.pdf", [lines])
    results, _ = v.verify(pdf, PERSON, min_chars=400)
    assert next(r for r in results if r.name == "encoding").verdict == v.FAIL


@needs_pypdf
def test_a_name_buried_below_a_sidebar_in_a_real_pdf_fails(tmp_path):
    lines = ["Skills"] + ["Azure Kubernetes Terraform Python Docker Linux Go"] * 8 + good_cv_lines()
    pdf = write_pdf(tmp_path / "cv.pdf", [lines])
    results, _ = v.verify(pdf, PERSON, min_chars=400)
    assert next(r for r in results if r.name == "reading order").verdict == v.FAIL


@needs_pypdf
def test_three_pages_in_a_real_pdf_fail_the_page_check(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()] * 3)
    results, _ = v.verify(pdf, PERSON, min_chars=400)
    assert next(r for r in results if r.name == "pages").verdict == v.FAIL


@needs_pypdf
def test_a_pdf_with_no_text_fails_the_text_layer_check(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [[]])
    results, _ = v.verify(pdf, PERSON)
    assert next(r for r in results if r.name == "text layer").verdict == v.FAIL


@needs_pypdf
def test_a_file_that_is_not_a_pdf_is_a_result_not_a_traceback(tmp_path):
    bad = tmp_path / "cv.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    results, text = v.verify(bad, PERSON)
    assert text == ""
    assert results[0].name == "extract" and results[0].verdict == v.FAIL


@needs_pypdf
def test_keywords_from_a_posting_are_checked_against_the_pdf(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    posting = "Kubernetes Terraform Kubernetes Terraform cobol cobol mainframe mainframe"
    results, _ = v.verify(pdf, PERSON, posting, min_chars=400)
    keywords = next(r for r in results if r.name == "keywords")
    assert keywords.verdict == v.WARN
    assert "cobol" in keywords.detail


def test_pypdf_missing_names_the_install_command(monkeypatch, tmp_path):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("pypdf"):
            raise ImportError("no pypdf")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    pages, error = v.extract_pypdf(tmp_path / "cv.pdf")
    assert pages == []
    assert "pip install pypdf" in error


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="Poppler's pdftotext is not installed")
def test_pdftotext_reads_the_same_made_pdf(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    pages, error = v.extract_pdftotext(pdf)
    assert error is None
    assert "Morgan Reyes" in pages[0]
    results, _ = v.verify(pdf, PERSON, extractor="pdftotext", min_chars=400)
    assert [r.name for r in results if r.verdict == v.FAIL] == []


def test_pdftotext_missing_says_how_to_get_it(monkeypatch, tmp_path):
    monkeypatch.setattr(v.shutil, "which", lambda name: None)
    pages, error = v.extract_pdftotext(tmp_path / "cv.pdf")
    assert pages == []
    assert "job-scout cv doctor" in error
