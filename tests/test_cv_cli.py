"""
The `job-scout cv` command line, with the model stubbed.

Most of this is about one thing: `cv import` must never send a CV anywhere before
the person has agreed, and must say plainly where it is going.
"""

import importlib.util

import pytest
import yaml
from cv_helpers import RESUME, good_cv_lines, write_pdf

from job_scout import cli
from job_scout.cv import cli as cvcli
from job_scout.cv import importer

needs_pypdf = pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None, reason="pypdf is an optional extra"
)

GOOD_YAML = yaml.safe_dump(RESUME, sort_keys=False)
CV_TEXT = (
    "Morgan Reyes\nmorgan.reyes@example.com\nPlatform engineer at Contoso Ltd, 2022-2026.\n"
    + "Cut deploy time from 40 min to 6 min. " * 8
)


class Session:
    """Drives `job-scout cv ...` with scripted answers and a stub model."""

    def __init__(self, monkeypatch, config_dir, tmp_path):
        self.monkeypatch = monkeypatch
        self.config_dir = config_dir
        self.tmp = tmp_path
        self.sent = []          # (spec, user text) for every model call
        self.events = []        # the order of prompts and model calls
        self.reply = GOOD_YAML
        self.cv = tmp_path / "my-cv.txt"
        self.cv.write_text(CV_TEXT, encoding="utf-8")
        self.out = tmp_path / "resume.yaml"
        monkeypatch.setattr(importer, "preflight", lambda spec: None)
        monkeypatch.setattr(importer, "run_model", self._model)

    def _model(self, spec, system, user, max_tokens=2048, temperature=0.3):
        self.sent.append((spec, user))
        self.events.append("model")
        return self.reply

    def run(self, *argv, answers=(), interactive=True):
        self.monkeypatch.setattr(cvcli, "_interactive", lambda: interactive)
        queue = list(answers)
        self.asked = []

        def ask(prompt):
            self.asked.append(prompt)
            self.events.append("ask")
            if not queue:
                raise EOFError
            return queue.pop(0)

        args = cli.build_parser().parse_args(["cv", *argv])
        return cvcli.run_cv(args, input_fn=ask, output_fn=print)

    def import_cv(self, *extra, answers=(), interactive=True):
        return self.run(
            "import", str(self.cv), "--out", str(self.out), "--config-dir", str(self.config_dir),
            *extra, answers=answers, interactive=interactive,
        )

    def config_text(self):
        return (self.config_dir / "config.yaml").read_text(encoding="utf-8")

    def set_cv_model(self, spec):
        from job_scout.cv.model_prompt import set_cv_model

        set_cv_model(self.config_dir / "config.yaml", spec)


@pytest.fixture
def session(monkeypatch, config_dir, tmp_path):
    return Session(monkeypatch, config_dir, tmp_path)


# --- import: nothing is sent before the person agrees -----------------------

def test_declining_sends_nothing_and_writes_nothing(session, capsys):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv(answers=["n"]) == 1
    assert session.sent == []
    assert not session.out.exists()
    assert "Nothing was sent." in capsys.readouterr().out


def test_the_default_answer_to_the_consent_prompt_is_no(session):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv(answers=[""]) == 1
    assert session.sent == []


def test_agreeing_sends_the_cv_and_writes_the_draft(session, capsys):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv(answers=["y"]) == 0
    assert session.sent[0][0] == "claude:sonnet"
    assert "Contoso Ltd" in session.sent[0][1]
    assert yaml.safe_load(session.out.read_text(encoding="utf-8"))["name"] == "Morgan Reyes"
    out = capsys.readouterr().out
    assert "model's draft" in out, "the review reminder is printed"
    assert "Anthropic" in out, "the consent prompt named who receives the text"
    assert "my-cv.txt" in out


def test_the_question_is_asked_before_the_model_is_called(session):
    session.set_cv_model("claude:sonnet")
    session.import_cv(answers=["y"])
    assert session.events == ["ask", "model"]


def test_yes_skips_the_question_for_scripts(session):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv("--yes", interactive=False) == 0
    assert session.asked == []
    assert len(session.sent) == 1


def test_without_a_terminal_or_yes_it_refuses_rather_than_sending(session, capsys):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv(interactive=False) == 2
    assert session.sent == []
    err = capsys.readouterr().err
    assert "--yes" in err and "terminal" in err


def test_ctrl_d_at_the_consent_prompt_sends_nothing(session):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv(answers=[]) == 1
    assert session.sent == []


# --- import: choosing cv_model ------------------------------------------------

def test_first_use_asks_whether_to_reuse_the_scoring_model_then_still_asks_consent(session):
    # config_dir fixture sets scoring_model to gemini:test-model
    assert session.import_cv(answers=["", "y"]) == 0
    assert session.asked[0] == "Use the same model as scoring? (Y/n): "
    assert session.asked[1] == "Send it? (y/N): "
    assert session.sent[0][0] == "gemini:test-model"
    assert 'cv_model: "gemini:test-model"' in session.config_text()


def test_first_use_declining_to_reuse_walks_to_another_and_still_asks_consent(session):
    assert session.import_cv(answers=["n", "2", "1", "", "y"]) == 0
    assert session.sent[0][0] == "claude:sonnet"
    assert 'cv_model: "claude:sonnet"' in session.config_text()
    assert 'scoring_model: "gemini:test-model"' in session.config_text()
    assert session.asked[-1] == "Send it? (y/N): "


def test_the_choice_is_kept_even_if_the_person_then_declines_to_send(session):
    assert session.import_cv(answers=["", "n"]) == 1
    assert session.sent == []
    assert 'cv_model: "gemini:test-model"' in session.config_text()


def test_the_second_time_the_model_question_is_not_asked_again(session):
    session.import_cv(answers=["", "y"])
    session.out.unlink()
    session.import_cv(answers=["y"])
    assert session.asked == ["Send it? (y/N): "]


def test_first_use_with_no_terminal_says_how_to_set_cv_model(session, capsys):
    assert session.import_cv("--yes", interactive=False) == 2
    assert session.sent == []
    err = capsys.readouterr().err
    assert "cv_model" in err and "--model" in err


def test_the_model_flag_overrides_the_setting_and_needs_no_question(session):
    session.set_cv_model("claude:sonnet")
    assert session.import_cv("--model", "codex:gpt-5", "--yes") == 0
    assert session.sent[0][0] == "codex:gpt-5"
    assert session.asked == []
    assert 'cv_model: "claude:sonnet"' in session.config_text(), "a flag is for one run only"


def test_a_malformed_model_flag_is_refused_before_anything_is_sent(session, capsys):
    assert session.import_cv("--model", "claude:", "--yes") == 1
    assert session.sent == []
    assert "not usable" in capsys.readouterr().err


def test_ctrl_d_while_choosing_the_model_sends_nothing(session, capsys):
    assert session.import_cv(answers=[]) == 1
    assert session.sent == []
    assert "No model chosen" in capsys.readouterr().out


def test_with_no_config_yaml_the_choice_is_used_but_not_saved(session, capsys):
    (session.config_dir / "config.yaml").unlink()
    assert session.import_cv(answers=["2", "1", "", "y"]) == 0
    assert session.sent[0][0] == "claude:sonnet"
    assert not (session.config_dir / "config.yaml").exists()
    assert "Not saved" in capsys.readouterr().out


# --- import: the file and the draft -------------------------------------------

def test_an_unreadable_cv_fails_before_any_question(session, capsys):
    session.cv = session.tmp / "gone.pdf"
    assert session.import_cv(answers=[]) == 1
    assert session.asked == []
    assert "No CV at" in capsys.readouterr().err


def test_an_existing_output_is_not_overwritten_without_force(session, capsys):
    session.set_cv_model("claude:sonnet")
    session.out.write_text("name: my hand edits\n", encoding="utf-8")
    assert session.import_cv("--yes") == 1
    assert session.sent == []
    assert session.out.read_text(encoding="utf-8") == "name: my hand edits\n"
    assert "--force" in capsys.readouterr().err


def test_force_replaces_it(session):
    session.set_cv_model("claude:sonnet")
    session.out.write_text("name: old\n", encoding="utf-8")
    assert session.import_cv("--yes", "--force") == 0
    assert "Morgan Reyes" in session.out.read_text(encoding="utf-8")


def test_a_reply_that_is_not_yaml_writes_nothing(session, capsys):
    session.set_cv_model("claude:sonnet")
    session.reply = "I am sorry, I cannot do that."
    assert session.import_cv("--yes") == 1
    assert not session.out.exists()
    assert "not a YAML mapping" in capsys.readouterr().err


def test_a_draft_that_breaks_the_format_writes_nothing(session, capsys):
    session.set_cv_model("claude:sonnet")
    session.reply = "name: Morgan Reyes\n"
    assert session.import_cv("--yes") == 1
    assert not session.out.exists()
    assert "missing top-level" in capsys.readouterr().err


def test_a_backend_that_is_not_ready_says_what_is_missing(session, monkeypatch, capsys):
    session.set_cv_model("claude:sonnet")
    monkeypatch.setattr(importer, "preflight", lambda spec: "the claude command is not on your PATH.")
    assert session.import_cv("--yes") == 1
    assert session.sent == []
    assert "not on your PATH" in capsys.readouterr().err


def test_a_bad_config_dir_is_a_sentence(session, tmp_path, capsys):
    args = ["import", str(session.cv), "--config-dir", str(tmp_path / "nope"), "--yes"]
    assert session.run(*args) == 2
    assert "not a directory" in capsys.readouterr().err


# --- the other subcommands -----------------------------------------------------

def test_cv_with_no_subcommand_prints_help_and_exits_2(monkeypatch, capsys):
    assert cli.main(["cv"]) == 2
    assert "doctor" in capsys.readouterr().out


def test_example_writes_a_resume_and_a_template_and_keeps_edits(tmp_path, capsys):
    target = tmp_path / "mine"
    assert cli.main(["cv", "example", str(target)]) == 0
    assert (target / "resume.yaml").is_file() and (target / "example.tex").is_file()
    (target / "resume.yaml").write_text("name: edited\n", encoding="utf-8")
    assert cli.main(["cv", "example", str(target)]) == 0
    assert (target / "resume.yaml").read_text(encoding="utf-8") == "name: edited\n"
    assert "Kept" in capsys.readouterr().out
    assert cli.main(["cv", "example", str(target), "--force"]) == 0
    assert "Morgan Reyes" in (target / "resume.yaml").read_text(encoding="utf-8")


def test_render_markdown_end_to_end(tmp_path, capsys):
    resume = tmp_path / "resume.yaml"
    resume.write_text(GOOD_YAML, encoding="utf-8")
    out = tmp_path / "cv.md"
    assert cli.main(["cv", "render", str(resume), "--out", str(out)]) == 0
    assert "# Morgan Reyes" in out.read_text(encoding="utf-8")


def test_render_with_a_missing_resume_says_how_to_make_one(tmp_path, capsys):
    assert cli.main(["cv", "render", str(tmp_path / "nope.yaml"), "--out", str(tmp_path / "cv.md")]) == 1
    err = capsys.readouterr().err
    assert "job-scout cv import" in err and "job-scout cv example" in err


def test_render_with_a_broken_resume_names_the_field(tmp_path, capsys):
    resume = tmp_path / "resume.yaml"
    resume.write_text("name: Morgan Reyes\n", encoding="utf-8")
    assert cli.main(["cv", "render", str(resume), "--out", str(tmp_path / "cv.md")]) == 1
    assert "missing top-level" in capsys.readouterr().err


def test_render_with_invalid_yaml_is_a_sentence(tmp_path, capsys):
    resume = tmp_path / "resume.yaml"
    resume.write_text("name: [unclosed", encoding="utf-8")
    assert cli.main(["cv", "render", str(resume), "--out", str(tmp_path / "cv.md")]) == 1
    assert "not valid YAML" in capsys.readouterr().err


def test_render_tex_without_a_template_says_so(tmp_path, capsys):
    resume = tmp_path / "resume.yaml"
    resume.write_text(GOOD_YAML, encoding="utf-8")
    assert cli.main(["cv", "render", str(resume), "--out", str(tmp_path / "cv.tex")]) == 1
    assert "--template" in capsys.readouterr().err


def test_build_without_latexmk_says_so_and_exits_1(tmp_path, monkeypatch, capsys):
    from job_scout.cv import build

    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    resume = tmp_path / "resume.yaml"
    resume.write_text(GOOD_YAML, encoding="utf-8")
    template = tmp_path / "t.tex"
    template.write_text("x", encoding="utf-8")
    assert cli.main(["cv", "build", str(resume), "--template", str(template)]) == 1
    assert "latexmk" in capsys.readouterr().err


def test_build_with_a_missing_template_names_it(tmp_path, capsys):
    resume = tmp_path / "resume.yaml"
    resume.write_text(GOOD_YAML, encoding="utf-8")
    assert cli.main(["cv", "build", str(resume), "--template", str(tmp_path / "gone.tex")]) == 1
    assert "gone.tex" in capsys.readouterr().err


def test_convert_turns_the_tailored_markdown_into_resume_yaml(tmp_path, capsys):
    draft = tmp_path / "CV-ats.md"
    draft.write_text(
        "# Morgan Reyes\n"
        "morgan.reyes@example.com | +45 12 34 56 78 | Odense, Denmark\n\n"
        "## Summary\nPlatform engineer.\n\n"
        "## Experience\n### Platform Engineer - Contoso Ltd, Odense\n2022 - 2026\n- Cut deploy time\n\n"
        "## Skills\nPython, Kubernetes\n\n"
        "## Education\n- BSc Computer Science - Example University, 2015 - 2019\n",
        encoding="utf-8",
    )
    out = tmp_path / "resume.yaml"
    assert cli.main(["cv", "convert", str(draft), "--out", str(out)]) == 0
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded["name"] == "Morgan Reyes"
    assert loaded["experience"][0]["company"] == "Contoso Ltd"
    assert cli.main(["cv", "convert", str(draft), "--out", str(out)]) == 1, "no silent overwrite"


# --- verify -------------------------------------------------------------------

def _resume_file(tmp_path):
    path = tmp_path / "resume.yaml"
    path.write_text(GOOD_YAML, encoding="utf-8")
    return path


@needs_pypdf
def test_verify_passes_a_good_pdf_with_exit_0(tmp_path, capsys):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    code = cli.main(["cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400"])
    assert code == 0
    assert "0 failed" in capsys.readouterr().out


@needs_pypdf
def test_verify_exits_1_when_a_check_fails(tmp_path, capsys):
    lines = [line for line in good_cv_lines() if "@" not in line]
    pdf = write_pdf(tmp_path / "cv.pdf", [lines])
    code = cli.main(["cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400"])
    assert code == 1
    assert "FAIL" in capsys.readouterr().out


@needs_pypdf
def test_flags_override_the_resume(tmp_path, capsys):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    code = cli.main([
        "cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400",
        "--email", "someone.else@example.com",
    ])
    assert code == 1
    assert "someone.else@example.com" in capsys.readouterr().out


@needs_pypdf
def test_verify_works_from_flags_alone(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    code = cli.main([
        "cv", "verify", str(pdf), "--min-chars", "400", "--name", "Morgan Reyes",
        "--email", "morgan.reyes@example.com", "--phone", "12 34 56 78",
    ])
    assert code == 0


@needs_pypdf
def test_verify_uses_resume_yaml_in_the_current_directory_when_present(tmp_path, monkeypatch):
    _resume_file(tmp_path)
    write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    monkeypatch.chdir(tmp_path)
    assert cli.main(["cv", "verify", "cv.pdf", "--min-chars", "400"]) == 0


def test_verify_a_missing_pdf_is_exit_2(tmp_path, capsys):
    assert cli.main(["cv", "verify", str(tmp_path / "gone.pdf")]) == 2
    assert "No such file" in capsys.readouterr().err


def test_verify_a_missing_jd_is_exit_2(tmp_path, capsys):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    assert cli.main(["cv", "verify", str(pdf), "--jd", str(tmp_path / "gone.md")]) == 2


def test_verify_an_unreadable_resume_is_exit_2(tmp_path, capsys):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    assert cli.main(["cv", "verify", str(pdf), "--resume", str(tmp_path / "gone.yaml")]) == 2


@needs_pypdf
def test_verify_with_a_posting_checks_keywords(tmp_path, capsys):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    jd = tmp_path / "jd.md"
    jd.write_text("cobol cobol mainframe mainframe kubernetes kubernetes", encoding="utf-8")
    cli.main(["cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400", "--jd", str(jd)])
    out = capsys.readouterr().out
    assert "cobol" in out


@needs_pypdf
def test_verify_both_skips_pdftotext_politely_when_it_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cvcli.shutil, "which", lambda name: None)
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    code = cli.main([
        "cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400",
        "--extractor", "both",
    ])
    out = capsys.readouterr().out
    assert code == 0, "a missing second opinion is not a failed check"
    assert "Skipped pdftotext" in out and "read with pypdf" in out


@needs_pypdf
def test_verify_dump_text_writes_what_the_parser_sees(tmp_path):
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    dump = tmp_path / "seen.txt"
    cli.main(["cv", "verify", str(pdf), "--resume", str(_resume_file(tmp_path)), "--min-chars", "400", "--dump-text", str(dump)])
    assert "Morgan Reyes" in dump.read_text(encoding="utf-8")


def test_verify_without_pypdf_fails_with_the_install_command(tmp_path, monkeypatch, capsys):
    from job_scout.cv import verify

    monkeypatch.setitem(
        verify.EXTRACTORS, "pypdf", lambda pdf: ([], "pypdf is not installed. Install it with: pip install pypdf")
    )
    pdf = write_pdf(tmp_path / "cv.pdf", [good_cv_lines()])
    monkeypatch.chdir(tmp_path)
    assert cli.main(["cv", "verify", str(pdf)]) == 1
    assert "pip install pypdf" in capsys.readouterr().out
