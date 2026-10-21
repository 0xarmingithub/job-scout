"""
`job-scout cv build`: fill a template, compile with latexmk.

CI may have no LaTeX, so almost everything here replaces latexmk with a stand-in
and checks what was asked of it. One test runs the real thing and is skipped when
latexmk or jinja2 is missing.
"""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from cv_helpers import RESUME

from job_scout.cv import CvError
from job_scout.cv import build as b
from job_scout.cv import render as r
from job_scout.cv.schema import validate

TEMPLATE = Path(r.__file__).resolve().parent / "templates" / "example.tex"
needs_jinja2 = pytest.mark.skipif(
    importlib.util.find_spec("jinja2") is None, reason="jinja2 is an optional extra"
)


def _resume():
    return validate(yaml.safe_load(yaml.safe_dump(RESUME)))


class FakeLatexmk:
    """Stands in for subprocess.run. Records the call and writes (or not) a PDF."""

    def __init__(self, returncode=0, write_pdf=True, log_text=""):
        self.returncode = returncode
        self.write_pdf = write_pdf
        self.log_text = log_text
        self.calls = []

    def __call__(self, argv, cwd=None, env=None, **kwargs):
        self.calls.append({"argv": argv, "cwd": Path(cwd), "env": env})
        tex = Path(cwd) / argv[-1]
        assert tex.is_file(), "the filled .tex must exist in the working directory"
        if self.write_pdf:
            tex.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
        if self.log_text:
            tex.with_suffix(".log").write_text(self.log_text, encoding="utf-8")
        return subprocess.CompletedProcess(argv, self.returncode, stdout=b"", stderr=b"")


@pytest.fixture
def with_latexmk(monkeypatch):
    monkeypatch.setattr(b.shutil, "which", lambda name: "/usr/bin/latexmk")


def test_without_latexmk_the_message_names_the_fix(monkeypatch, tmp_path):
    monkeypatch.setattr(b.shutil, "which", lambda name: None)
    with pytest.raises(CvError) as excinfo:
        b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    message = str(excinfo.value)
    assert "latexmk" in message
    assert "job-scout cv doctor" in message
    assert not (tmp_path / "cv.pdf").exists()


@needs_jinja2
def test_a_missing_template_is_named(with_latexmk, tmp_path):
    with pytest.raises(CvError) as excinfo:
        b.build_pdf(_resume(), tmp_path / "gone.tex", tmp_path / "cv.pdf")
    assert "gone.tex" in str(excinfo.value)


def test_a_template_that_is_not_tex_is_refused(tmp_path):
    with pytest.raises(CvError, match="not a .tex file"):
        b.build_pdf(_resume(), tmp_path / "styles.docx", tmp_path / "cv.pdf")


@needs_jinja2
def test_the_pdf_lands_where_asked_and_nothing_else_does(with_latexmk, monkeypatch, tmp_path):
    fake = FakeLatexmk()
    monkeypatch.setattr(b.subprocess, "run", fake)
    out = tmp_path / "out" / "cv.pdf"
    result = b.build_pdf(_resume(), TEMPLATE, out)
    assert result == out and out.read_bytes().startswith(b"%PDF")
    assert [p.name for p in out.parent.iterdir()] == ["cv.pdf"]
    assert not fake.calls[0]["cwd"].exists(), "the working directory is cleaned up"


@needs_jinja2
def test_latexmk_is_asked_to_stop_on_error(with_latexmk, monkeypatch, tmp_path):
    fake = FakeLatexmk()
    monkeypatch.setattr(b.subprocess, "run", fake)
    b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    argv = fake.calls[0]["argv"]
    assert argv[0] == "latexmk" and "-halt-on-error" in argv and "-pdf" in argv


@needs_jinja2
def test_the_templates_folder_is_on_texinputs(with_latexmk, monkeypatch, tmp_path):
    monkeypatch.setenv("TEXINPUTS", "/already/there")
    fake = FakeLatexmk()
    monkeypatch.setattr(b.subprocess, "run", fake)
    b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    parts = fake.calls[0]["env"]["TEXINPUTS"].split(os.pathsep)
    assert parts[0] == str(TEMPLATE.parent)
    assert "/already/there" in parts
    assert parts[-1] == "", "a trailing separator keeps TeX's own search path"


@needs_jinja2
def test_a_failed_compile_shows_the_first_error_not_the_whole_log(with_latexmk, monkeypatch, tmp_path):
    log = "This is pdfTeX\n(./cv.tex\n! Undefined control sequence.\nl.12 \\fancything\n\nlater noise\n"
    monkeypatch.setattr(b.subprocess, "run", FakeLatexmk(returncode=12, write_pdf=False, log_text=log))
    with pytest.raises(CvError) as excinfo:
        b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    message = str(excinfo.value)
    assert "Undefined control sequence" in message
    assert "This is pdfTeX" not in message
    assert "exit 12" in message
    assert not (tmp_path / "cv.pdf").exists()


@needs_jinja2
def test_a_zero_exit_with_no_pdf_is_still_a_failure(with_latexmk, monkeypatch, tmp_path):
    monkeypatch.setattr(b.subprocess, "run", FakeLatexmk(returncode=0, write_pdf=False))
    with pytest.raises(CvError, match="latexmk failed"):
        b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")


@needs_jinja2
def test_a_compile_that_hangs_is_stopped_with_an_explanation(with_latexmk, monkeypatch, tmp_path):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 300)

    monkeypatch.setattr(b.subprocess, "run", hang)
    with pytest.raises(CvError, match="without finishing"):
        b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")


@needs_jinja2
def test_the_filled_tex_has_the_resume_in_it(with_latexmk, monkeypatch, tmp_path):
    seen = {}

    def capture(argv, cwd=None, env=None, **kwargs):
        tex = Path(cwd) / argv[-1]
        seen["tex"] = tex.read_text(encoding="utf-8")
        tex.with_suffix(".pdf").write_bytes(b"%PDF")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(b.subprocess, "run", capture)
    b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    assert "Morgan Reyes" in seen["tex"] and "morgan.reyes@example.com" in seen["tex"]


@needs_jinja2
@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk is not installed")
def test_a_real_build_produces_a_pdf(tmp_path):
    out = b.build_pdf(_resume(), TEMPLATE, tmp_path / "cv.pdf")
    assert out.read_bytes().startswith(b"%PDF")
    assert [p.name for p in tmp_path.iterdir()] == ["cv.pdf"]


@needs_jinja2
@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk is not installed")
def test_a_real_compile_error_comes_back_as_a_sentence_not_a_traceback(tmp_path):
    template = tmp_path / "broken.tex"
    template.write_text(
        "\\documentclass{article}\\begin{document}\\nosuchmacro \\VAR{name}\\end{document}\n",
        encoding="utf-8",
    )
    with pytest.raises(CvError) as excinfo:
        b.build_pdf(_resume(), template, tmp_path / "cv.pdf")
    assert "nosuchmacro" in str(excinfo.value) or "Undefined control sequence" in str(excinfo.value)
