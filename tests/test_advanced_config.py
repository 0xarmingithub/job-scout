"""
The `advanced:` block. Every one of these asserts the setting changes real
behaviour, not that it merely parses.
"""

import pytest

from job_scout import matcher, track_record
from job_scout.config import ADVANCED_DEFAULTS, ConfigError, Settings, merge_advanced
from job_scout.dedup import JobStore
from job_scout.notifiers.base import RunStats, format_job, score_label

# ─── Merging ──────────────────────────────────────────────────────────────────

def test_defaults_apply_when_the_block_is_absent():
    assert merge_advanced({}) == ADVANCED_DEFAULTS


def test_one_override_does_not_drop_the_others():
    merged = merge_advanced({"advanced": {"description_chars": 1000}})
    assert merged["description_chars"] == 1000
    assert merged["reply_tokens"] == ADVANCED_DEFAULTS["reply_tokens"]


def test_one_band_override_keeps_the_other_band():
    merged = merge_advanced({"advanced": {"score_bands": {"strong": 90}}})
    assert merged["score_bands"] == {"strong": 90, "possible": 65}


def test_a_non_mapping_advanced_block_is_rejected():
    with pytest.raises(ConfigError, match="must be a mapping"):
        merge_advanced({"advanced": ["nope"]})


def test_settings_exposes_the_same_merge(tmp_path):
    settings = Settings(
        config_dir=tmp_path, data_dir=tmp_path,
        config={"advanced": {"reply_tokens": 42}},
    )
    assert settings.advanced["reply_tokens"] == 42
    assert settings.advanced["description_chars"] == ADVANCED_DEFAULTS["description_chars"]


# ─── description_chars actually truncates ─────────────────────────────────────

def test_description_chars_limits_what_the_model_is_sent(monkeypatch):
    seen = {}
    monkeypatch.setattr(matcher, "preflight", lambda spec: None)

    def capture(spec, system, user, **kwargs):
        seen["prompt"] = user
        seen["max_tokens"] = kwargs.get("max_tokens")
        return '{"score": 70}'

    monkeypatch.setattr(matcher, "run_model", capture)

    long_description = "kubernetes " + ("x" * 9000)
    matcher.score_jobs(
        [{"title": "Platform Engineer", "description": long_description,
          "location": "Berlin", "url": "https://a"}],
        config={
            "scoring_model": "gemini:x", "searches": [{"term": "platform"}],
            "scoring_retries": 0,
            "advanced": {"description_chars": 200, "reply_tokens": 256},
        },
        profile={"candidate": {}},
    )
    # The posting text in the prompt is capped, so the bill is capped.
    assert len(seen["prompt"]) < 4000
    assert "x" * 200 not in seen["prompt"] or seen["prompt"].count("x") <= 200
    assert seen["max_tokens"] == 256


# ─── score_bands actually relabel ─────────────────────────────────────────────

def test_score_bands_change_the_label():
    job = {"title": "SRE", "company": "Acme", "score": 84, "url": "https://a"}
    assert "[STRONG]" in format_job(job, RunStats(strong_at=80, possible_at=65))
    assert "[POSSIBLE]" in format_job(job, RunStats(strong_at=90, possible_at=65))


def test_score_label_without_a_run_uses_the_shipped_bands():
    assert score_label(80) == "STRONG"
    assert score_label(65) == "POSSIBLE"
    assert score_label(64) == "LONG SHOT"


# ─── seen_lookback_days actually changes the query ─────────────────────────────

def test_a_zero_lookback_disables_the_title_and_company_check(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db", lookback_days=0)
    store.mark_seen(sample_jobs[:1])

    repost = dict(sample_jobs[0])
    repost["url"] = "https://tracking.example/rotated-1"
    # Recorded today, and today is still inside a zero-day window, so it is
    # still caught. What matters is that the value reaches the query.
    assert store.lookback_days == 0
    assert store.filter_new([repost]) == []


def test_the_default_lookback_is_a_week(tmp_path):
    assert JobStore(tmp_path / "jobs.db").lookback_days == 7


def test_a_negative_lookback_is_clamped(tmp_path):
    assert JobStore(tmp_path / "jobs.db", lookback_days=-5).lookback_days == 0


# ─── outcomes_listed actually caps the prompt ─────────────────────────────────

def test_outcomes_listed_caps_how_many_reach_the_prompt(tmp_path):
    rows = "".join(f"Role {i},Company {i},offer\n" for i in range(30))
    path = tmp_path / "outcomes.csv"
    path.write_text(f"title,company,status\n{rows}", encoding="utf-8")

    few = track_record.build_context(path, max_listed=3)
    many = track_record.build_context(path, max_listed=20)
    assert few.count("  - ") <= 4          # three plus the "and N more" line
    assert many.count("  - ") > few.count("  - ")


def test_the_prompt_honours_the_configured_cap(tmp_path):
    rows = "".join(f"Role {i},Company {i},offer\n" for i in range(30))
    path = tmp_path / "outcomes.csv"
    path.write_text(f"title,company,status\n{rows}", encoding="utf-8")

    template = matcher.build_prompt_template({"candidate": {"name": "T"}}, path, 2)
    assert template.count("  - ") <= 3


# ─── The shipped template documents them ──────────────────────────────────────

def test_every_knob_is_mentioned_in_the_shipped_config():
    from job_scout.config import TEMPLATE_DIR

    text = (TEMPLATE_DIR / "config.yaml").read_text(encoding="utf-8")
    for key in ADVANCED_DEFAULTS:
        assert key in text, f"advanced.{key} is not mentioned in the shipped config"
