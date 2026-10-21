"""
The CV check is opt-in. It asks each chosen model for its own analysis, keeps a
failure from stopping the others, and never runs as part of a daily run.
"""

import pytest
import yaml

from job_scout import cli, validate_cv
from job_scout.validate_cv import build_report, call_model, extract_score, validate

ANALYSIS = """### MATCH SCORE
72%
Strong on Azure, weak on Kubernetes.

### KEYWORD COVERAGE
- **WELL COVERED**: Azure
"""


def test_the_score_is_read_from_under_match_score():
    assert extract_score(ANALYSIS) == "72%"


def test_a_score_without_a_percent_sign_is_still_read():
    assert extract_score("### MATCH SCORE\n64\nFair.\n") == "64%"


def test_a_missing_or_nonsense_score_is_not_guessed():
    assert extract_score("no headings here at all") == "N/A"
    assert extract_score("### MATCH SCORE\nvery good\n") == "N/A"
    assert extract_score("### MATCH SCORE\n250%\n") == "N/A"


def test_the_report_has_one_section_per_model_and_an_average():
    results = [
        {"model": "claude:sonnet", "analysis": ANALYSIS, "error": None},
        {"model": "codex:gpt-5", "analysis": "### MATCH SCORE\n50%\nOk.\n", "error": None},
    ]
    text = build_report(results, "jd.md", "cv.md")
    assert "## claude:sonnet" in text and "## codex:gpt-5" in text
    assert "**Match score:** 72%" in text
    assert "**Average across 2 model(s):** 61%" in text
    assert "Two models often" in text  # the caution is always printed


def test_a_model_that_failed_is_reported_and_left_out_of_the_average():
    results = [
        {"model": "claude:sonnet", "analysis": "", "error": "CLI not found"},
        {"model": "codex:gpt-5", "analysis": "### MATCH SCORE\n40%\n", "error": None},
    ]
    text = build_report(results, "jd.md", "cv.md")
    assert "The model did not answer: CLI not found" in text
    assert "**Average across 1 model(s):** 40%" in text


def test_one_failing_model_does_not_stop_the_others(monkeypatch):
    def fake(spec, system, user, max_tokens=None, temperature=None):
        if spec == "bad:one":
            raise RuntimeError("boom")
        return ANALYSIS

    monkeypatch.setattr(validate_cv, "run_model", fake)
    results = validate("jd", "cv", ["bad:one", "good:two"])
    assert [r["model"] for r in results] == ["bad:one", "good:two"]
    assert results[0]["error"] and results[1]["error"] is None
    assert results[1]["analysis"] == ANALYSIS


def test_more_than_four_models_is_refused():
    with pytest.raises(ValueError):
        validate("jd", "cv", ["a:1", "a:2", "a:3", "a:4", "a:5"])


def test_no_models_is_refused():
    with pytest.raises(ValueError):
        validate("jd", "cv", [])


def test_a_model_call_never_raises(monkeypatch):
    monkeypatch.setattr(validate_cv, "run_model", lambda *a, **k: 1 / 0)
    result = call_model("x:y", "jd", "cv")
    assert result["error"] and result["analysis"] == ""


def _files(tmp_path):
    jd = tmp_path / "jd.md"
    cv = tmp_path / "cv.md"
    jd.write_text("Azure architect", encoding="utf-8")
    cv.write_text("Azure engineer", encoding="utf-8")
    return jd, cv


def test_the_command_without_models_and_without_a_terminal_says_how_to_set_them(tmp_path, capsys):
    jd, cv = _files(tmp_path)
    rc = cli.main(["validate", "--jd", str(jd), "--cv", str(cv), "--output", str(tmp_path / "r.md")])
    assert rc == 2
    assert "cv_validator_models" in capsys.readouterr().err
    assert not (tmp_path / "r.md").exists()


def test_the_command_uses_the_models_in_the_config(tmp_path, monkeypatch, capsys):
    jd, cv = _files(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"cv_validator_models": ["claude:sonnet"], "notifiers": [], "searches": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_cv, "run_model", lambda *a, **k: ANALYSIS)
    out = tmp_path / "report.md"
    rc = cli.main(["validate", "--jd", str(jd), "--cv", str(cv), "--output", str(out),
                   "--config-dir", str(cfg)])
    assert rc == 0
    assert "**Match score:** 72%" in out.read_text(encoding="utf-8")


def test_a_missing_input_file_is_named(tmp_path, capsys):
    rc = cli.main(["validate", "--jd", str(tmp_path / "nope.md"), "--cv", str(tmp_path / "x.md"),
                   "--output", str(tmp_path / "r.md")])
    assert rc == 1
    assert "Cannot read" in capsys.readouterr().err


def test_the_daily_run_never_calls_the_cv_check(monkeypatch):
    """The check is opt-in: the run path must not import or call it."""
    import job_scout.run as run_module
    source = open(run_module.__file__, encoding="utf-8").read()
    assert "validate_cv" not in source
    assert "cv_validator_models" not in source
