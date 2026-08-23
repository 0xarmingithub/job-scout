"""
Config loading, and the thing that makes the private-repo case work: the scout
must run against a config directory that is nowhere near the package.
"""

import pytest

from job_scout import config as cfg

# ─── Finding the config directory ─────────────────────────────────────────────

def test_cli_flag_wins(tmp_path):
    (tmp_path / "config.yaml").write_text("searches: []", encoding="utf-8")
    assert cfg.resolve_config_dir(str(tmp_path)) == tmp_path.resolve()


def test_environment_variable_is_used_when_there_is_no_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_CONFIG_DIR", str(tmp_path))
    assert cfg.resolve_config_dir(None) == tmp_path.resolve()


def test_the_flag_beats_the_environment_variable(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("JOB_SCOUT_CONFIG_DIR", str(tmp_path))
    assert cfg.resolve_config_dir(str(other)) == other.resolve()


def test_the_current_directory_is_used_when_it_has_a_config(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("searches: []", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cfg.resolve_config_dir(None) == tmp_path.resolve()


def test_falling_back_to_the_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no config.yaml here
    assert cfg.resolve_config_dir(None) == cfg.PACKAGE_ROOT


def test_a_missing_config_dir_says_what_to_do(tmp_path):
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.resolve_config_dir(str(tmp_path / "does-not-exist"))
    assert "job-scout init" in str(excinfo.value)


def test_a_bad_environment_variable_says_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_CONFIG_DIR", str(tmp_path / "nope"))
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.resolve_config_dir(None)
    assert "JOB_SCOUT_CONFIG_DIR" in str(excinfo.value)


# ─── The data directory ───────────────────────────────────────────────────────

def test_data_dir_defaults_inside_the_config_dir(tmp_path):
    assert cfg.resolve_data_dir(tmp_path) == tmp_path / "data"
    assert (tmp_path / "data").is_dir()


def test_data_dir_can_be_moved_with_a_flag(tmp_path):
    target = tmp_path / "elsewhere"
    assert cfg.resolve_data_dir(tmp_path, str(target)) == target.resolve()


def test_data_dir_can_be_moved_with_an_environment_variable(tmp_path, monkeypatch):
    target = tmp_path / "elsewhere"
    monkeypatch.setenv("JOB_SCOUT_DATA_DIR", str(target))
    assert cfg.resolve_data_dir(tmp_path) == target.resolve()


# ─── Seeding ──────────────────────────────────────────────────────────────────

def test_init_copies_the_templates(tmp_path):
    written = cfg.seed_config_dir(tmp_path / "new")
    names = {path.name for path in written}
    assert names == {"config.yaml", "profile.yaml", ".env.example"}


def test_init_never_overwrites_your_edits(tmp_path):
    target = tmp_path / "new"
    cfg.seed_config_dir(target)
    (target / "profile.yaml").write_text("mine: yes", encoding="utf-8")
    cfg.seed_config_dir(target)
    assert (target / "profile.yaml").read_text(encoding="utf-8") == "mine: yes"


def test_init_force_does_overwrite(tmp_path):
    target = tmp_path / "new"
    cfg.seed_config_dir(target)
    (target / "profile.yaml").write_text("mine: yes", encoding="utf-8")
    cfg.seed_config_dir(target, overwrite=True)
    assert "Morgan Reyes" in (target / "profile.yaml").read_text(encoding="utf-8")


# ─── Loading, end to end, from a directory outside the package ────────────────

def test_settings_load_from_an_external_directory(config_dir):
    settings = cfg.load_settings(str(config_dir))
    assert settings.config_dir == config_dir.resolve()
    assert settings.data_dir == config_dir.resolve() / "data"
    assert settings.notify_threshold == 65
    assert len(settings.searches) == 4
    assert settings.scoring_model.startswith("gemini:")
    assert settings.notifier_specs == [
        {"type": "file", "path": "matches.md", "format": "markdown", "append": True}
    ]
    assert settings.profile["candidate"]["name"] == "Morgan Reyes"


def test_config_and_data_directories_can_be_completely_separate(config_dir, tmp_path):
    data = tmp_path / "somewhere" / "else"
    settings = cfg.load_settings(str(config_dir), str(data))
    assert settings.data_dir == data.resolve()
    assert settings.config_dir != settings.data_dir


def test_outcomes_path_defaults_next_to_the_config(config_dir):
    settings = cfg.load_settings(str(config_dir))
    assert settings.outcomes_path == config_dir.resolve() / "outcomes.csv"


def test_outcomes_path_can_be_absolute(config_dir, tmp_path):
    settings = cfg.load_settings(str(config_dir))
    settings.config["outcomes_file"] = str(tmp_path / "elsewhere.csv")
    assert settings.outcomes_path == tmp_path / "elsewhere.csv"


# ─── Validation ───────────────────────────────────────────────────────────────

def _settings(tmp_path, config: dict, profile: dict | None = None) -> cfg.Settings:
    return cfg.Settings(
        config_dir=tmp_path,
        data_dir=tmp_path / "data",
        config=config,
        profile=profile if profile is not None else {"candidate": {"name": "X"}},
    )


def test_no_searches_is_rejected_with_an_example(tmp_path):
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate(_settings(tmp_path, {"notifiers": [{"type": "file"}]}))
    assert "searches:" in str(excinfo.value)


def test_a_search_with_no_term_is_rejected(tmp_path):
    with pytest.raises(cfg.ConfigError, match="has no 'term'"):
        cfg.validate(_settings(tmp_path, {
            "searches": [{"sites": ["linkedin"]}],
            "notifiers": [{"type": "file"}],
        }))


def test_an_impossible_threshold_is_rejected(tmp_path):
    with pytest.raises(cfg.ConfigError, match="between 0 and 100"):
        cfg.validate(_settings(tmp_path, {
            "searches": [{"term": "x"}],
            "notify_threshold": 500,
            "notifiers": [{"type": "file"}],
        }))


def test_a_profile_with_no_candidate_is_rejected(tmp_path):
    with pytest.raises(cfg.ConfigError, match="candidate"):
        cfg.validate(_settings(tmp_path, {
            "searches": [{"term": "x"}],
            "notifiers": [{"type": "file"}],
        }, profile={}))


def test_no_notifier_is_rejected_with_the_zero_setup_answer(tmp_path):
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate(_settings(tmp_path, {"searches": [{"term": "x"}]}))
    assert "type: file" in str(excinfo.value)


def test_a_notifier_may_be_written_as_a_bare_name(tmp_path):
    settings = _settings(tmp_path, {"searches": [{"term": "x"}], "notifiers": ["file"]})
    assert settings.notifier_specs == [{"type": "file"}]


def test_broken_yaml_says_which_file(tmp_path):
    (tmp_path / "config.yaml").write_text("searches: [\n  - unclosed", encoding="utf-8")
    (tmp_path / "profile.yaml").write_text("candidate: {name: X}", encoding="utf-8")
    with pytest.raises(cfg.ConfigError, match="config.yaml"):
        cfg.load_settings(str(tmp_path))


def test_a_missing_file_points_at_init(tmp_path):
    (tmp_path / "config.yaml").write_text("searches: []", encoding="utf-8")
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_settings(str(tmp_path))
    assert "profile.yaml" in str(excinfo.value)
    assert "job-scout init" in str(excinfo.value)
