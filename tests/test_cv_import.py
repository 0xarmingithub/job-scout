"""
Drafting a profile from a CV. No network, no keys — the model call is stubbed.

The test that matters most is the one asserting confirmed_gaps comes back empty
even when the model fills it in. A CV cannot show what somebody cannot do, and a
wrong gap silently caps good jobs at 40.
"""

import builtins

import pytest
import yaml

from job_scout import cv_import
from job_scout.cv_import import CvImportError

SAMPLE_CV = """
Morgan Reyes
Senior Platform Engineer, Berlin

EXPERIENCE
Platform Engineer, Northwind Logistics, 2022 to present.
Ran the Kubernetes platform for 60 engineers. Terraform across four
environments. Built internal tooling in Go. Owned the on-call rotation.

Infrastructure Engineer, Halden Data, 2019 to 2022.
AWS, EKS, Postgres, Prometheus and Grafana. Migrated a monolith to containers.

SKILLS
Kubernetes, AWS, Terraform, Go, Python, Docker, GitLab CI, ArgoCD, Helm,
Prometheus, Grafana, PostgreSQL, Linux.

LANGUAGES
English native. German elementary.
"""

GOOD_REPLY = """
candidate:
  name: Morgan Reyes
  current_role: Platform Engineer at Northwind Logistics
  years_experience: "8"
  seniority: Senior
  location: Berlin
  work_authorization: not stated
  target_geography: not stated
  languages:
    English: Native
    German: Elementary
target_roles:
  - Platform Engineer
  - Site Reliability Engineer
core_skills:
  - Kubernetes
  - Terraform
secondary_skills:
  - Helm
confirmed_gaps: []
industries_preferred:
  - Logistics
extra_pre_filter_keywords:
  - kubernetes
  - terraform
hard_exclude_location_patterns: []
hard_exclude_title_patterns: []
"""


def _cv(tmp_path, text=SAMPLE_CV, name="cv.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _stub_model(monkeypatch, reply):
    monkeypatch.setattr(cv_import, "preflight", lambda spec: None)
    monkeypatch.setattr(cv_import, "run_model", lambda *a, **k: reply)


# ─── Reading the file ─────────────────────────────────────────────────────────

def test_reads_a_text_cv(tmp_path):
    assert "Northwind Logistics" in cv_import.read_cv_text(_cv(tmp_path))


def test_reads_a_markdown_cv(tmp_path):
    assert cv_import.read_cv_text(_cv(tmp_path, name="cv.md"))


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(CvImportError, match="No CV at"):
        cv_import.read_cv_text(tmp_path / "nope.pdf")


def test_an_unsupported_format_suggests_pasting_into_a_txt(tmp_path):
    path = tmp_path / "cv.pages"
    path.write_text("x" * 500, encoding="utf-8")
    with pytest.raises(CvImportError) as excinfo:
        cv_import.read_cv_text(path)
    assert ".txt" in str(excinfo.value)


def test_a_scanned_pdf_with_no_text_is_explained(tmp_path):
    with pytest.raises(CvImportError, match="scanned or image-only"):
        cv_import.read_cv_text(_cv(tmp_path, text="tiny"))


def test_a_very_long_cv_is_truncated(tmp_path):
    text = cv_import.read_cv_text(_cv(tmp_path, text="word " * 20_000))
    assert len(text) <= cv_import.MAX_CV_CHARS


def test_pdf_without_pypdf_names_the_package(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def no_pypdf(name, *args, **kwargs):
        if name.startswith("pypdf"):
            raise ImportError("no pypdf here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    path = tmp_path / "cv.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(CvImportError) as excinfo:
        cv_import.read_cv_text(path)
    assert "pip install pypdf" in str(excinfo.value)


def test_docx_without_python_docx_names_the_package(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def no_docx(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("no python-docx here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_docx)
    path = tmp_path / "cv.docx"
    path.write_bytes(b"PK fake")
    with pytest.raises(CvImportError) as excinfo:
        cv_import.read_cv_text(path)
    assert "pip install python-docx" in str(excinfo.value)


# ─── The prompt ───────────────────────────────────────────────────────────────

def test_the_prompt_forbids_inventing_and_forbids_filling_gaps():
    prompt = cv_import.build_prompt(SAMPLE_CV)
    assert "Never add a skill" in prompt
    assert "confirmed_gaps as an empty list" in prompt
    assert "Northwind Logistics" in prompt


def test_the_prompt_carries_the_whole_schema():
    prompt = cv_import.build_prompt(SAMPLE_CV)
    for key in (
        "candidate:", "target_roles:", "core_skills:", "secondary_skills:",
        "confirmed_gaps:", "extra_pre_filter_keywords:",
        "hard_exclude_location_patterns:", "hard_exclude_title_patterns:",
    ):
        assert key in prompt


# ─── Drafting ─────────────────────────────────────────────────────────────────

def test_a_good_reply_becomes_a_profile(tmp_path, monkeypatch):
    _stub_model(monkeypatch, GOOD_REPLY)
    text, parsed = cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")
    assert parsed["candidate"]["name"] == "Morgan Reyes"
    assert "Kubernetes" in parsed["core_skills"]
    # The written text has to survive a round trip, or config loading breaks.
    assert yaml.safe_load(text)["candidate"]["name"] == "Morgan Reyes"


def test_markdown_fences_are_stripped(tmp_path, monkeypatch):
    _stub_model(monkeypatch, f"```yaml\n{GOOD_REPLY}\n```")
    _, parsed = cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")
    assert parsed["candidate"]["name"] == "Morgan Reyes"


def test_invented_gaps_are_dropped(tmp_path, monkeypatch, caplog):
    """The whole point. A CV cannot show what somebody cannot do."""
    reply = GOOD_REPLY.replace(
        "confirmed_gaps: []",
        'confirmed_gaps:\n  - "No machine learning experience"\n'
        '  - "No frontend work"',
    )
    _stub_model(monkeypatch, reply)
    _, parsed = cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")
    assert parsed["confirmed_gaps"] == []
    assert "cannot show what somebody cannot do" in caplog.text


def test_a_backend_that_is_not_set_up_says_what_is_missing(tmp_path, no_clis):
    with pytest.raises(CvImportError) as excinfo:
        cv_import.profile_from_cv(_cv(tmp_path), "gemini:gemini-3.7-flash")
    message = str(excinfo.value)
    assert "GOOGLE_API_KEY" in message or "google-genai" in message


def test_a_reply_that_is_not_yaml_is_reported(tmp_path, monkeypatch):
    _stub_model(monkeypatch, "candidate: [unclosed\n  - broken: : :")
    with pytest.raises(CvImportError, match="valid YAML"):
        cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")


def test_a_reply_with_no_candidate_block_is_reported(tmp_path, monkeypatch):
    _stub_model(monkeypatch, "target_roles:\n  - Platform Engineer\n")
    with pytest.raises(CvImportError, match="no `candidate` block"):
        cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")


def test_a_model_failure_is_reported(tmp_path, monkeypatch):
    from job_scout.llm import ModelError

    monkeypatch.setattr(cv_import, "preflight", lambda spec: None)

    def explode(*args, **kwargs):
        raise ModelError("429 rate limited")

    monkeypatch.setattr(cv_import, "run_model", explode)
    with pytest.raises(CvImportError, match="429 rate limited"):
        cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")


# ─── What the user is told afterwards ─────────────────────────────────────────

def test_the_review_notes_lead_with_the_empty_gaps():
    notes = cv_import.review_notes(yaml.safe_load(GOOD_REPLY), "profile.yaml")
    assert "confirmed_gaps is empty" in notes
    assert "work_authorization" in notes
    assert "hard_exclude_location_patterns" in notes
    assert "Morgan Reyes" in notes


# ─── The drafted profile has to actually work ─────────────────────────────────

def test_a_drafted_profile_builds_a_scoring_prompt(tmp_path, monkeypatch):
    """A draft nothing downstream can read would be worse than no draft."""
    from job_scout.matcher import build_prompt_template

    _stub_model(monkeypatch, GOOD_REPLY)
    _, parsed = cv_import.profile_from_cv(_cv(tmp_path), "gemini:x")
    template = build_prompt_template(parsed)
    assert "Morgan Reyes" in template
    assert "{title}" in template
