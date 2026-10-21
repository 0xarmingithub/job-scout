"""
The scoring model is the person's choice. There is no default, `job-scout init`
asks, and an empty choice fails with a message that says how to fix it.
"""

import pytest
import yaml

from job_scout import cli
from job_scout.config import SCORING_MODEL_UNSET, seed_config_dir
from job_scout.matcher import ScoringUnavailable, score_jobs
from job_scout.setup_prompt import SetupCancelled, choose_scoring_model, set_scoring_model


def _answers(*given):
    queue = list(given)

    def ask(prompt):
        if not queue:
            raise EOFError
        return queue.pop(0)

    return ask


def _choose(*given):
    lines = []
    spec = choose_scoring_model(_answers(*given), lines.append)
    return spec, "\n".join(lines)


# --- the prompt ------------------------------------------------------------------

def test_api_then_gemini_then_enter_uses_the_example_model():
    spec, _ = _choose("1", "1", "")
    assert spec == "gemini:gemini-3.7-flash"


def test_cli_then_claude_with_a_typed_model():
    spec, _ = _choose("2", "1", "opus")
    assert spec == "claude:opus"


def test_openrouter_codex_and_grok_are_offered():
    assert _choose("1", "2", "")[0] == "openrouter:google/gemini-3.7-flash"
    assert _choose("2", "2", "")[0] == "codex:gpt-5"
    assert _choose("2", "3", "")[0] == "grok:grok-4"


def test_a_bad_answer_is_asked_again():
    spec, text = _choose("x", "9", "2", "1", "sonnet")
    assert spec == "claude:sonnet"
    assert "Type a number from 1 to 2" in text


def test_ending_the_prompt_cancels_it():
    with pytest.raises(SetupCancelled):
        choose_scoring_model(_answers("1"), lambda line: None)  # runs out of answers


def test_five_bad_answers_cancel_it():
    with pytest.raises(SetupCancelled):
        choose_scoring_model(_answers(*["x"] * 5), lambda line: None)


def test_the_prompt_says_there_are_two_separate_model_choices():
    _, text = _choose("1", "1", "")
    assert "two model choices" in text
    assert "CV drafting" in text
    assert "--with-tailoring" in text
    assert "API" in text and "CLI" in text


# --- writing the answer ------------------------------------------------------------

def test_set_scoring_model_changes_one_line_and_keeps_the_rest(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('# keep me\nnotify_threshold: 65\nscoring_model: ""\nscoring_retries: 1\n', encoding="utf-8")
    assert set_scoring_model(path, "claude:sonnet") is True
    assert path.read_text(encoding="utf-8") == (
        '# keep me\nnotify_threshold: 65\nscoring_model: "claude:sonnet"\nscoring_retries: 1\n'
    )


def test_set_scoring_model_reports_a_config_without_the_line(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("notify_threshold: 65\n", encoding="utf-8")
    assert set_scoring_model(path, "claude:sonnet") is False


# --- init ----------------------------------------------------------------------------

def _model_in(target):
    return yaml.safe_load((target / "config.yaml").read_text(encoding="utf-8"))["scoring_model"]


def test_the_shipped_config_has_no_model(tmp_path):
    seed_config_dir(tmp_path / "cfg")
    assert _model_in(tmp_path / "cfg") == ""


def test_init_with_a_flag_writes_the_model(tmp_path, capsys):
    target = tmp_path / "cfg"
    assert cli.main(["init", str(target), "--scoring-model", "claude:sonnet"]) == 0
    assert _model_in(target) == "claude:sonnet"
    assert 'scoring_model set to "claude:sonnet"' in capsys.readouterr().out


def test_init_without_a_flag_and_without_a_terminal_leaves_it_empty_and_says_so(tmp_path, capsys):
    target = tmp_path / "cfg"
    assert cli.main(["init", str(target)]) == 0  # pytest has no terminal
    assert _model_in(target) == ""
    out = capsys.readouterr().out
    assert "does not choose one for you" in out
    assert "--scoring-model BACKEND:MODEL" in out
    assert "--force" not in out.split("scoring_model is empty")[1].split("Next:")[0]


@pytest.mark.parametrize("bad", ["foo", "claude:", "nonsense:model", "   ", "claude sonnet"])
def test_a_malformed_flag_is_refused_and_writes_nothing(tmp_path, capsys, bad):
    target = tmp_path / "cfg"
    assert cli.main(["init", str(target), "--scoring-model", bad]) == 2
    assert _model_in(target) == ""
    assert "must be BACKEND:MODEL" in capsys.readouterr().err


def test_the_flag_alone_updates_an_existing_config_without_touching_anything_else(tmp_path):
    target = tmp_path / "cfg"
    cli.main(["init", str(target)])
    (target / "profile.yaml").write_text("candidate: {name: Mine}\n", encoding="utf-8")
    before = (target / "config.yaml").read_text(encoding="utf-8")

    assert cli.main(["init", str(target), "--scoring-model", "codex:gpt-5"]) == 0

    after = (target / "config.yaml").read_text(encoding="utf-8")
    assert _model_in(target) == "codex:gpt-5"
    assert after.replace('scoring_model: "codex:gpt-5"', 'scoring_model: ""') == before
    assert "Mine" in (target / "profile.yaml").read_text(encoding="utf-8")


# --- an empty choice fails clearly ---------------------------------------------------------

def test_a_run_without_a_model_says_how_to_fix_it():
    with pytest.raises(ScoringUnavailable) as caught:
        score_jobs([{"title": "x", "company": "y", "description": "z"}],
                   config={"scoring_model": "", "searches": []}, profile={})
    assert str(caught.value) == SCORING_MODEL_UNSET
    assert "--scoring-model BACKEND:MODEL" in str(caught.value)


def test_check_reports_the_missing_model(tmp_path, capsys):
    target = tmp_path / "cfg"
    seed_config_dir(target)
    cli.main(["check", "--config-dir", str(target)])
    out = capsys.readouterr().out
    assert "NOT SET" in out
    assert "no scoring_model chosen" in out
