"""
cv_model in config.yaml: no default, validated when set, shipped commented out,
and documented. Plus the package data that lets an installed copy find the
example template.
"""

import re
from pathlib import Path

import pytest
import yaml

from job_scout.config import TEMPLATE_DIR, ConfigError, load_settings
from job_scout.cv.model_prompt import set_cv_model

REPO_ROOT = Path(__file__).resolve().parent.parent


def _set_raw(config_dir, line):
    path = config_dir / "config.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + line + "\n", encoding="utf-8")


def test_there_is_no_default_cv_model(config_dir):
    settings = load_settings(str(config_dir))
    assert settings.cv_model == ""


def test_the_shipped_template_does_not_choose_one_for_you():
    text = (TEMPLATE_DIR / "config.yaml").read_text(encoding="utf-8")
    assert "cv_model" not in yaml.safe_load(text)
    assert re.search(r"^# cv_model: ", text, re.MULTILINE), "shown as a commented example"
    assert not re.search(r"^cv_model:", text, re.MULTILINE)


def test_a_chosen_model_loads(config_dir):
    set_cv_model(config_dir / "config.yaml", "claude:sonnet")
    assert load_settings(str(config_dir)).cv_model == "claude:sonnet"


def test_cv_model_may_differ_from_scoring_model(config_dir):
    set_cv_model(config_dir / "config.yaml", "codex:gpt-5")
    settings = load_settings(str(config_dir))
    assert settings.cv_model == "codex:gpt-5"
    assert settings.scoring_model == "gemini:test-model"


def test_a_blank_cv_model_is_the_same_as_none(config_dir):
    _set_raw(config_dir, 'cv_model: ""')
    assert load_settings(str(config_dir)).cv_model == ""


def test_a_backend_with_no_model_stops_the_run_with_a_sentence(config_dir):
    _set_raw(config_dir, 'cv_model: "claude:"')
    with pytest.raises(ConfigError, match="cv_model"):
        load_settings(str(config_dir))


def test_a_cv_model_that_is_not_text_stops_the_run_with_a_sentence(config_dir):
    _set_raw(config_dir, "cv_model: [claude, sonnet]")
    with pytest.raises(ConfigError, match="cv_model must be text"):
        load_settings(str(config_dir))


def test_the_option_is_documented():
    docs = (REPO_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    assert re.search(r"^\| `cv_model` \|", docs, re.MULTILINE), "a row in the top-level table"
    assert "### `cv_model`" in docs
    cv_docs = (REPO_ROOT / "docs" / "cv.md").read_text(encoding="utf-8")
    assert "Use the same model as scoring? (Y/n)" in cv_docs


def test_the_example_template_is_declared_as_package_data():
    """Without this line an installed copy has no example.tex to start from."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"cv/templates/*"' in pyproject
    assert (REPO_ROOT / "job_scout" / "cv" / "__init__.py").is_file(), "cv is a package, so it is found"


def test_the_old_toolkit_folder_is_only_a_pointer():
    folder = REPO_ROOT / "contrib" / "cv-toolkit"
    assert [p.name for p in folder.iterdir()] == ["README.md"]
    assert "docs/cv.md" in (folder / "README.md").read_text(encoding="utf-8")
