"""
The command line, with the model stubbed.

Most of this is about one thing: `init --from-cv` must never quietly replace a
profile somebody has edited. The parts they wrote by hand, above all
confirmed_gaps, are exactly the parts a CV cannot produce.
"""

import pytest
import yaml

from job_scout import cli, cv_import
from job_scout.config import TEMPLATE_DIR

DRAFT = {
    "candidate": {"name": "Morgan Reyes", "seniority": "Senior"},
    "target_roles": ["Platform Engineer"],
    "core_skills": ["Kubernetes"],
    "secondary_skills": [],
    "confirmed_gaps": [],
    "extra_pre_filter_keywords": ["kubernetes"],
    "hard_exclude_location_patterns": [],
    "hard_exclude_title_patterns": [],
}


@pytest.fixture
def stub_draft(monkeypatch):
    """Pretend the model returned a usable profile."""
    monkeypatch.setattr(
        cv_import,
        "profile_from_cv",
        lambda cv_path, model_spec: (yaml.safe_dump(DRAFT, sort_keys=False), DRAFT),
    )


@pytest.fixture
def cv(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("Morgan Reyes\nPlatform Engineer\n" + "detail " * 100, encoding="utf-8")
    return path


# ─── init ─────────────────────────────────────────────────────────────────────

def test_init_writes_the_templates(tmp_path, capsys):
    assert cli.main(["init", str(tmp_path / "cfg")]) == 0
    target = tmp_path / "cfg"
    assert (target / "config.yaml").exists()
    assert (target / "profile.yaml").exists()
    assert "--from-cv" in capsys.readouterr().out


def test_init_twice_does_not_complain_or_clobber(tmp_path, capsys):
    target = tmp_path / "cfg"
    cli.main(["init", str(target)])
    (target / "profile.yaml").write_text("candidate: {name: Mine}\n", encoding="utf-8")
    assert cli.main(["init", str(target)]) == 0
    assert "Mine" in (target / "profile.yaml").read_text(encoding="utf-8")


# ─── init --from-cv ───────────────────────────────────────────────────────────

def test_from_cv_replaces_the_shipped_example(tmp_path, cv, stub_draft, capsys):
    target = tmp_path / "cfg"
    assert cli.main(["init", str(target), "--from-cv", str(cv)]) == 0

    written = yaml.safe_load((target / "profile.yaml").read_text(encoding="utf-8"))
    assert written["candidate"]["name"] == "Morgan Reyes"
    assert written["confirmed_gaps"] == []

    out = capsys.readouterr().out
    assert "confirmed_gaps is empty" in out


def test_from_cv_refuses_to_overwrite_an_edited_profile(tmp_path, cv, stub_draft, capsys):
    """The bug this test exists for: losing hand-written confirmed_gaps."""
    target = tmp_path / "cfg"
    cli.main(["init", str(target)])
    mine = "candidate:\n  name: Mine\nconfirmed_gaps:\n  - No frontend work\n"
    (target / "profile.yaml").write_text(mine, encoding="utf-8")

    assert cli.main(["init", str(target), "--from-cv", str(cv)]) == 1
    assert (target / "profile.yaml").read_text(encoding="utf-8") == mine

    err = capsys.readouterr().err
    assert "--force" in err
    assert "confirmed_gaps" in err


def test_force_overwrites_an_edited_profile(tmp_path, cv, stub_draft):
    target = tmp_path / "cfg"
    cli.main(["init", str(target)])
    (target / "profile.yaml").write_text("candidate: {name: Mine}\n", encoding="utf-8")

    assert cli.main(["init", str(target), "--from-cv", str(cv), "--force"]) == 0
    written = yaml.safe_load((target / "profile.yaml").read_text(encoding="utf-8"))
    assert written["candidate"]["name"] == "Morgan Reyes"


def test_from_cv_into_an_empty_directory(tmp_path, cv, stub_draft):
    target = tmp_path / "brand-new"
    assert cli.main(["init", str(target), "--from-cv", str(cv)]) == 0
    assert (target / "config.yaml").exists()
    assert yaml.safe_load(
        (target / "profile.yaml").read_text(encoding="utf-8")
    )["candidate"]["name"] == "Morgan Reyes"


def test_a_cv_that_cannot_be_read_leaves_the_example_in_place(tmp_path, capsys):
    target = tmp_path / "cfg"
    assert cli.main(["init", str(target), "--from-cv", str(tmp_path / "nope.pdf")]) == 1
    # The example is still usable, which is what the error message promises.
    assert "Morgan Reyes" in (target / "profile.yaml").read_text(encoding="utf-8")
    assert "still in place" in capsys.readouterr().err


def test_the_drafted_file_keeps_a_header_explaining_the_empty_gaps(tmp_path, cv, stub_draft):
    target = tmp_path / "cfg"
    cli.main(["init", str(target), "--from-cv", str(cv)])
    text = (target / "profile.yaml").read_text(encoding="utf-8")
    assert text.startswith("# profile.yaml")
    assert "confirmed_gaps is empty on purpose" in text


# ─── Telling an edited profile from the shipped one ───────────────────────────

def test_the_shipped_example_is_recognised(tmp_path):
    target = tmp_path / "profile.yaml"
    target.write_text(
        (TEMPLATE_DIR / "profile.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert cli._is_shipped_example(target)


def test_an_edited_profile_is_not(tmp_path):
    target = tmp_path / "profile.yaml"
    target.write_text(
        (TEMPLATE_DIR / "profile.yaml").read_text(encoding="utf-8")
        + "\n# one line of mine\n",
        encoding="utf-8",
    )
    assert not cli._is_shipped_example(target)


def test_a_missing_profile_is_not_the_example(tmp_path):
    assert not cli._is_shipped_example(tmp_path / "nothing-here.yaml")


# ─── version ──────────────────────────────────────────────────────────────────

def test_version(capsys):
    assert cli.main(["version"]) == 0
    assert "job-scout" in capsys.readouterr().out
