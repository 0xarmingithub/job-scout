"""
`job-scout cv render`: the resume.yaml format, and the three renderers.

The LaTeX renderer is the one that can corrupt a CV without anyone noticing, so
the escaping and the "unknown field is an error" rule each have a test that would
fail without them.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml
from cv_helpers import RESUME

from job_scout.cv import CvError
from job_scout.cv import render as r
from job_scout.cv.schema import validate

TEMPLATE_DIR = Path(r.__file__).resolve().parent / "templates"
needs_jinja2 = pytest.mark.skipif(
    importlib.util.find_spec("jinja2") is None, reason="jinja2 is an optional extra"
)


def _resume(**changes):
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    data.update(changes)
    return validate(data)


# --- The format --------------------------------------------------------------

def test_the_shipped_example_resume_is_valid():
    data = yaml.safe_load((TEMPLATE_DIR / "resume.example.yaml").read_text(encoding="utf-8"))
    resume = validate(data)
    assert resume.name == "Morgan Reyes"
    assert resume.contact.email.endswith("@example.com")


def test_the_example_template_ships_beside_it():
    assert (TEMPLATE_DIR / "example.tex").is_file()
    assert sorted(path.name for path in TEMPLATE_DIR.iterdir()) == [
        "example.tex", "resume.example.yaml",
    ], "the neutral example is the only template that ships"


@pytest.mark.parametrize("missing", ["name", "contact", "summary", "experience", "education"])
def test_a_missing_top_level_field_is_named(missing):
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    data.pop(missing)
    with pytest.raises(ValueError, match=missing):
        validate(data)


def test_skills_or_skill_groups_is_required():
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    data.pop("skills")
    with pytest.raises(ValueError, match="skills"):
        validate(data)
    data["skill_groups"] = {"Languages": ["Python"]}
    assert validate(data).skill_groups == {"Languages": ["Python"]}


def test_a_missing_nested_field_says_where():
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    del data["experience"][0]["dates"]
    with pytest.raises(ValueError, match=r"experience\[0\].*dates"):
        validate(data)
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    del data["contact"]["email"]
    with pytest.raises(ValueError, match="email"):
        validate(data)


def test_wrong_shapes_are_errors_not_tracebacks():
    base = yaml.safe_load(yaml.safe_dump(RESUME))
    for field, value in [("experience", "not a list"), ("contact", ["x"]), ("education", [5])]:
        data = dict(base, **{field: value})
        with pytest.raises(ValueError):
            validate(data)
    with pytest.raises(ValueError):
        validate("just a string")


def test_numbers_and_nulls_from_a_model_draft_are_tolerated():
    data = yaml.safe_load(yaml.safe_dump(RESUME))
    data["experience"][0]["dates"] = 2022
    data["experience"][0]["bullets"] = None
    data["interests"] = None
    resume = validate(data)
    assert resume.experience[0].dates == "2022"
    assert resume.experience[0].bullets == []
    assert resume.interests == []


# --- Markdown ----------------------------------------------------------------

def test_markdown_carries_every_section():
    text = r.to_markdown(_resume(certifications=["CKA"], interests=["Running"]))
    for expected in (
        "# Morgan Reyes", "morgan.reyes@example.com", "## Summary", "## Experience",
        "Senior Platform Engineer - Contoso Ltd, Odense (2022-2026)", "- Cut deploy time",
        "## Skills", "Python, Kubernetes", "## Education", "BSc Computer Science",
        "## Certifications", "## Interests",
    ):
        assert expected in text


def test_grouped_skills_win_over_the_flat_list():
    text = r.to_markdown(_resume(skill_groups={"Languages": ["Python", "Go"]}))
    assert "**Languages:** Python, Go" in text


def test_markdown_renders_with_no_template_and_no_extras(tmp_path):
    out = tmp_path / "cv.md"
    r.render(_resume(), "markdown", None, out)
    assert out.read_text(encoding="utf-8").startswith("# Morgan Reyes")


# --- Choosing the renderer ---------------------------------------------------

def test_the_output_suffix_picks_the_renderer():
    assert r.renderer_for(Path("cv.tex"), None) == "latex"
    assert r.renderer_for(Path("cv.DOCX"), None) == "docx"
    assert r.renderer_for(Path("cv.md"), None) == "markdown"
    assert r.renderer_for(Path("cv.tex"), "markdown") == "markdown"


def test_an_unknown_suffix_asks_for_a_renderer():
    with pytest.raises(CvError, match="--renderer"):
        r.renderer_for(Path("cv.rtf"), None)


def test_an_unknown_renderer_name_is_refused(tmp_path):
    with pytest.raises(CvError, match="Unknown renderer"):
        r.render(_resume(), "pdf", None, tmp_path / "x")


# --- LaTeX -------------------------------------------------------------------

def test_special_characters_are_escaped():
    assert r.latex_escape("R&D 50% #1 $5 a_b {x} ~ ^") == (
        r"R\&D 50\% \#1 \$5 a\_b \{x\} \textasciitilde{} \textasciicircum{}"
    )
    assert r.latex_escape("a\\b") == r"a\textbackslash{}b"
    assert r.latex_escape(None) == ""


@needs_jinja2
def test_the_example_template_fills_and_leaves_no_placeholder(tmp_path):
    resume = _resume(summary="Cut costs 30% at R&D_team", certifications=["CKA"])
    out = tmp_path / "cv.tex"
    r.render(resume, "latex", TEMPLATE_DIR / "example.tex", out)
    text = out.read_text(encoding="utf-8")
    assert "Morgan Reyes" in text
    assert r"Cut costs 30\% at R\&D\_team" in text
    assert r"\VAR" not in text and r"\BLOCK" not in text
    assert "Certifications" in text


@needs_jinja2
def test_empty_optional_sections_are_left_out(tmp_path):
    out = tmp_path / "cv.tex"
    r.render(_resume(), "latex", TEMPLATE_DIR / "example.tex", out)
    text = out.read_text(encoding="utf-8")
    assert "Certifications" not in text and "Projects" not in text


@needs_jinja2
def test_a_placeholder_naming_a_missing_field_is_an_error(tmp_path):
    template = tmp_path / "mine.tex"
    template.write_text(r"\documentclass{article}\begin{document}\VAR{nmae}\end{document}", encoding="utf-8")
    with pytest.raises(CvError, match="nmae"):
        r.fill_latex(_resume(), template)


@needs_jinja2
def test_a_broken_block_names_the_line(tmp_path):
    template = tmp_path / "mine.tex"
    template.write_text("line one\n\\BLOCK{for x in skills}\n\\VAR{x}\n", encoding="utf-8")
    with pytest.raises(CvError, match=r"line \d+"):
        r.fill_latex(_resume(), template)


@needs_jinja2
def test_a_missing_template_says_where_to_get_one(tmp_path):
    with pytest.raises(CvError) as excinfo:
        r.render(_resume(), "latex", tmp_path / "gone.tex", tmp_path / "cv.tex")
    assert "gone.tex" in str(excinfo.value)
    assert "job-scout cv example" in str(excinfo.value)


def test_latex_output_without_any_template_says_so(tmp_path):
    with pytest.raises(CvError, match="--template"):
        r.render(_resume(), "latex", None, tmp_path / "cv.tex")


def test_jinja2_missing_names_the_install_command(monkeypatch, tmp_path):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "jinja2":
            raise ImportError("no jinja2")
        return real(name, *args, **kwargs)

    template = tmp_path / "t.tex"
    template.write_text("x", encoding="utf-8")
    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(CvError, match="pip install jinja2"):
        r.fill_latex(_resume(), template)


# --- Word, through Pandoc ----------------------------------------------------

def test_docx_without_pandoc_says_what_to_do(monkeypatch, tmp_path):
    monkeypatch.setattr(r.shutil, "which", lambda name: None)
    with pytest.raises(CvError) as excinfo:
        r.render(_resume(), "docx", None, tmp_path / "cv.docx")
    assert "Pandoc" in str(excinfo.value)
    assert "job-scout cv doctor" in str(excinfo.value)


def test_a_missing_docx_template_is_named(monkeypatch, tmp_path):
    monkeypatch.setattr(r.shutil, "which", lambda name: "/usr/bin/pandoc")
    with pytest.raises(CvError, match="styles.docx"):
        r.render(_resume(), "docx", tmp_path / "styles.docx", tmp_path / "cv.docx")


def test_a_pandoc_failure_shows_pandoc_s_own_words(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr(r.shutil, "which", lambda name: "/usr/bin/pandoc")
    monkeypatch.setattr(
        r.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 64, stdout=b"", stderr=b"bad reference doc"),
    )
    with pytest.raises(CvError, match="bad reference doc"):
        r.render(_resume(), "docx", None, tmp_path / "cv.docx")


def test_docx_is_built_through_pandoc_when_it_is_installed(tmp_path):
    import shutil

    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc is not installed")
    out = tmp_path / "cv.docx"
    r.render(_resume(), "docx", None, out)
    assert out.read_bytes()[:2] == b"PK", "a .docx is a zip file"
