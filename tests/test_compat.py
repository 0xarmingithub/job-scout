"""
Things that would otherwise be claims in the README rather than facts.

The Python floor is checked by parsing every source file with the 3.10 grammar,
so the number in pyproject.toml cannot quietly drift away from what the code
actually uses.
"""

import ast
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "job_scout"

MINIMUM_PYTHON = (3, 10)


def _source_files() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_there_is_something_to_check():
    assert len(_source_files()) >= 15


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_every_module_parses_as_python_3_10(path: Path):
    """
    The README says Python 3.10 or newer. This is what makes that true: the
    3.10 grammar has to accept every file, so nothing newer can sneak in.
    """
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=MINIMUM_PYTHON)
    except SyntaxError as exc:
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)} needs a newer Python than "
            f"{'.'.join(map(str, MINIMUM_PYTHON))}: {exc}"
        )


def test_pyproject_declares_the_same_floor():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected = f'requires-python = ">={".".join(map(str, MINIMUM_PYTHON))}"'
    assert expected in text


def test_this_interpreter_is_new_enough():
    assert sys.version_info >= MINIMUM_PYTHON


# ─── The shipped templates have to be valid, or a first run fails ─────────────

def test_the_shipped_config_is_valid_yaml_and_complete():
    from job_scout.config import TEMPLATE_DIR

    config = yaml.safe_load((TEMPLATE_DIR / "config.yaml").read_text(encoding="utf-8"))
    assert config["searches"], "the shipped config must work out of the box"
    assert config["notifiers"] == [
        {"type": "file", "path": "matches.md", "format": "markdown", "append": True}
    ], "the zero-credential notifier must be the default"
    assert config["scoring_model"].startswith("gemini:")
    assert 0 <= config["notify_threshold"] <= 100


def test_the_shipped_profile_exercises_every_field():
    from job_scout.config import TEMPLATE_DIR

    profile = yaml.safe_load((TEMPLATE_DIR / "profile.yaml").read_text(encoding="utf-8"))
    for key in (
        "candidate", "target_roles", "core_skills", "secondary_skills",
        "confirmed_gaps", "industries_preferred", "extra_pre_filter_keywords",
        "hard_exclude_location_patterns", "hard_exclude_title_patterns",
    ):
        assert profile.get(key), f"the example profile leaves {key} empty"

    candidate = profile["candidate"]
    for key in (
        "name", "current_role", "years_experience", "seniority", "location",
        "work_authorization", "target_geography", "languages",
    ):
        assert candidate.get(key), f"the example candidate leaves {key} empty"


def test_the_example_profile_is_the_fictional_one():
    """
    No real person's details ship in this repository.

    This asserts the positive — that the shipped profile is still the fictional
    candidate — rather than listing names to look for. A blocklist of real
    details would publish those details in a public repository, which is the
    thing it was meant to prevent.
    """
    from job_scout.config import TEMPLATE_DIR

    for path in (
        TEMPLATE_DIR / "profile.yaml",
        REPO_ROOT / "examples" / "denmark" / "profile.yaml",
    ):
        if not path.exists():
            continue
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert profile["candidate"]["name"] == "Morgan Reyes", (
            f"{path.relative_to(REPO_ROOT)} is not the fictional candidate any "
            f"more. Do not ship a real profile."
        )


def test_the_templates_are_actually_committed():
    """
    A .gitignore rule once swallowed job_scout/templates/.env.example, so the
    file existed on the author's disk and was missing from every clone. The
    tests all passed. This is the check that would have caught it.
    """
    import subprocess

    try:
        tracked = subprocess.run(
            ["git", "ls-files", "job_scout/templates"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available")
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")

    files = {line.strip() for line in tracked.stdout.splitlines() if line.strip()}
    for name in ("config.yaml", "profile.yaml", ".env.example"):
        assert f"job_scout/templates/{name}" in files, (
            f"job_scout/templates/{name} is not tracked by git, so it would be "
            f"missing from a fresh clone. Check .gitignore."
        )


def test_the_env_example_carries_no_values():
    from job_scout.config import TEMPLATE_DIR

    for line in (TEMPLATE_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        assert value == "", f"{name} in .env.example has a value in it"


def test_the_denmark_example_loads():
    from job_scout.config import load_settings

    example = REPO_ROOT / "examples" / "denmark"
    if not (example / "config.yaml").exists():
        pytest.skip("examples/denmark is not present")
    settings = load_settings(str(example))
    assert settings.searches
    assert settings.profile["candidate"]["name"]
