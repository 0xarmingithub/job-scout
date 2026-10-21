"""
cv_model and the consent prompt. The CV is personal data, so the questions are
the product: they must name the backend that receives the text, default to no,
and survive Ctrl-D.
"""

from pathlib import Path

import pytest

from job_scout.config import seed_config_dir
from job_scout.cv import model_prompt as mp
from job_scout.setup_prompt import SetupCancelled


def _answers(*given):
    queue = list(given)
    asked = []

    def ask(prompt):
        asked.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)

    ask.asked = asked
    return ask


def _choose(scoring, *given):
    lines = []
    ask = _answers(*given)
    spec = mp.choose_cv_model(scoring, ask, lines.append)
    return spec, "\n".join(lines), ask


def _confirm(spec, *given):
    lines = []
    ask = _answers(*given)
    agreed = mp.confirm_send(spec, Path("cv.pdf"), 4210, ask, lines.append)
    return agreed, "\n".join(lines), ask


# --- Choosing the model ------------------------------------------------------

def test_the_first_question_is_whether_to_reuse_the_scoring_model():
    spec, shown, ask = _choose("gemini:test-model", "")
    assert spec == "gemini:test-model"
    assert ask.asked == ["Use the same model as scoring? (Y/n): "]
    assert "gemini:test-model" in shown


@pytest.mark.parametrize("answer", ["", "y", "Y", "yes", "  YES  "])
def test_anything_yes_like_reuses_the_scoring_model(answer):
    assert _choose("claude:sonnet", answer)[0] == "claude:sonnet"


@pytest.mark.parametrize("answer", ["n", "N", "no"])
def test_no_walks_through_choosing_another(answer):
    # no, then CLI (2), then claude (1), then Enter for the example model
    spec, shown, _ = _choose("gemini:test-model", answer, "2", "1", "")
    assert spec == "claude:sonnet"
    assert "separate choice from the model that scores job postings" in shown


def test_the_walk_can_pick_an_api_backend_and_type_a_model():
    spec, _, _ = _choose("claude:sonnet", "n", "1", "2", "some/model-name")
    assert spec == "openrouter:some/model-name"


def test_with_no_scoring_model_there_is_nothing_to_reuse_so_it_does_not_ask():
    spec, _, ask = _choose("", "2", "1", "sonnet")
    assert spec == "claude:sonnet"
    assert not any("same model" in prompt for prompt in ask.asked)


def test_a_muddled_answer_is_asked_again():
    spec, shown, _ = _choose("claude:sonnet", "maybe", "y")
    assert spec == "claude:sonnet"
    assert "Type y or n." in shown


def test_endless_muddle_gives_up_rather_than_loops():
    with pytest.raises(SetupCancelled):
        _choose("claude:sonnet", *["huh"] * 10)


def test_ctrl_d_at_the_first_question_cancels():
    with pytest.raises(SetupCancelled):
        _choose("claude:sonnet")


def test_ctrl_d_in_the_middle_of_the_walk_cancels():
    with pytest.raises(SetupCancelled):
        _choose("claude:sonnet", "n", "2")


# --- Consent -----------------------------------------------------------------

def test_the_consent_prompt_names_the_file_the_size_and_the_backend():
    _, shown, ask = _confirm("claude:sonnet", "n")
    assert "cv.pdf" in shown and "4,210 characters" in shown
    assert "claude:sonnet" in shown
    assert "Anthropic" in shown
    assert ask.asked == ["Send it? (y/N): "]


@pytest.mark.parametrize(
    "spec, who",
    [
        ("gemini:some-model", "Google"),
        ("openrouter:vendor/model", "OpenRouter"),
        ("claude:sonnet", "Anthropic"),
        ("codex:gpt-5", "OpenAI"),
        ("grok:grok-4", "xAI"),
    ],
)
def test_every_backend_says_who_receives_the_text(spec, who):
    assert who in mp.describe_backend(spec)
    assert spec in mp.describe_backend(spec)


def test_a_bare_vendor_slash_model_is_described_as_openrouter():
    assert "OpenRouter" in mp.describe_backend("vendor/model")


def test_a_cli_run_over_ssh_says_it_is_not_this_machine(monkeypatch):
    monkeypatch.setattr(mp.shutil, "which", lambda name: None)
    monkeypatch.setenv("LLM_CLI_SSH_HOST", "someone@build.example")
    text = mp.describe_backend("claude:sonnet")
    assert "someone@build.example" in text and "not this machine" in text


def test_a_local_cli_does_not_mention_ssh(monkeypatch):
    monkeypatch.setattr(mp.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setenv("LLM_CLI_SSH_HOST", "someone@build.example")
    assert "SSH" not in mp.describe_backend("claude:sonnet")


@pytest.mark.parametrize("answer, agreed", [("y", True), ("YES", True), ("n", False), ("", False)])
def test_only_a_yes_agrees_and_enter_means_no(answer, agreed):
    assert _confirm("claude:sonnet", answer)[0] is agreed


def test_ctrl_d_at_consent_cancels_rather_than_agreeing():
    with pytest.raises(SetupCancelled):
        _confirm("claude:sonnet")


# --- Reading and writing the setting ----------------------------------------

def test_read_models_needs_no_profile_and_no_searches(tmp_path):
    (tmp_path / "config.yaml").write_text(
        'scoring_model: "gemini:a"\ncv_model: "claude:sonnet"\n', encoding="utf-8"
    )
    assert mp.read_models(tmp_path) == ("claude:sonnet", "gemini:a")


def test_read_models_copes_with_nothing_there(tmp_path):
    assert mp.read_models(tmp_path) == ("", "")
    (tmp_path / "config.yaml").write_text("not: [valid", encoding="utf-8")
    assert mp.read_models(tmp_path) == ("", "")


def test_the_shipped_template_has_a_commented_cv_model_and_set_cv_model_uses_it(tmp_path):
    seed_config_dir(tmp_path)
    path = tmp_path / "config.yaml"
    before = path.read_text(encoding="utf-8")
    assert "\n# cv_model:" in before and "\ncv_model:" not in before
    assert mp.set_cv_model(path, "claude:sonnet") is True
    after = path.read_text(encoding="utf-8")
    assert '\ncv_model: "claude:sonnet"\n' in after
    assert "# cv_model:" not in after
    # every other line, comments included, is as it was
    assert after.replace('cv_model: "claude:sonnet"', "# cv_model: \"claude:sonnet\"") == before


def test_set_cv_model_replaces_an_active_line(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('a: 1\ncv_model: "old:model"\nb: 2\n', encoding="utf-8")
    mp.set_cv_model(path, "claude:sonnet")
    assert path.read_text(encoding="utf-8") == 'a: 1\ncv_model: "claude:sonnet"\nb: 2\n'


def test_set_cv_model_appends_when_the_file_has_no_mention(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("a: 1", encoding="utf-8")
    mp.set_cv_model(path, "claude:sonnet")
    assert path.read_text(encoding="utf-8").endswith('cv_model: "claude:sonnet"\n')
    assert path.read_text(encoding="utf-8").startswith("a: 1\n")


def test_set_cv_model_does_not_create_a_config_file(tmp_path):
    assert mp.set_cv_model(tmp_path / "config.yaml", "claude:sonnet") is False
    assert not (tmp_path / "config.yaml").exists()
