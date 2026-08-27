"""
Tests for the tailor step.

The two things worth being sure of: a posting's text can never be executed, and
a command that fails cannot fail the run that called it.

The commands here are real subprocesses, but they are all `sys.executable`, so
nothing outside Python is needed and nothing touches the network.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from job_scout import tailor
from job_scout.config import Settings

JOB = {
    "title": "Solution Architect",
    "company": "Northwind Energy",
    "location": "Berlin",
    "site": "linkedin",
    "url": "https://example.test/1",
    "score": 91,
    "description": "kubernetes and terraform",
    "verdict": {"reasoning": "close fit", "key_matches": ["Azure"], "gaps": ["No pharma"]},
}


def settings_for(tmp_path, tailor_block: dict, notifiers=None) -> Settings:
    return Settings(
        config_dir=tmp_path,
        data_dir=tmp_path / "data",
        config={
            "tailor": tailor_block,
            "notifiers": notifiers or [{"type": "file"}],
        },
        profile={"candidate": {"name": "Someone"}},
    )


def writer_command(text: str = "written by the command") -> str:
    """A command that writes {output_file}, the way a real one must."""
    script = (
        "import sys,pathlib;"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding='utf-8')"
    )
    return f'"{sys.executable}" -c "{script}" {{output_file}} "{text}"'


# ─── Choosing what to work on ─────────────────────────────────────────────────

def test_only_the_top_scores_are_worth_a_model_call(tmp_path):
    config = tailor.load({"tailor": {"command": "x", "min_score": 85}}, tmp_path, tmp_path)
    picked = tailor.pick(
        [{"score": 91}, {"score": 86}, {"score": 72}], config
    )
    assert [job["score"] for job in picked] == [91]


def test_top_n_takes_more_than_one(tmp_path):
    config = tailor.load(
        {"tailor": {"command": "x", "min_score": 70, "top_n": 2}}, tmp_path, tmp_path
    )
    assert len(tailor.pick([{"score": 91}, {"score": 86}, {"score": 72}], config)) == 2


def test_nothing_is_picked_when_nothing_is_good_enough(tmp_path):
    config = tailor.load({"tailor": {"command": "x", "min_score": 95}}, tmp_path, tmp_path)
    assert tailor.pick([{"score": 91}], config) == []


def test_the_same_posting_gets_the_same_filename(tmp_path):
    config = tailor.load({"tailor": {"command": "x"}}, tmp_path, tmp_path)
    today = date(2026, 8, 28)
    assert tailor.output_path(JOB, config, today).name == (
        "2026-08-28-northwind-energy-solution-architect.md"
    )


def test_a_filename_survives_punctuation_in_a_job_title(tmp_path):
    config = tailor.load({"tailor": {"command": "x"}}, tmp_path, tmp_path)
    job = {"company": "A/S Grønt & Co", "title": "Arkitekt (IoT), 100%"}
    name = tailor.output_path(job, config, date(2026, 8, 28)).name
    assert name.endswith(".md")
    assert "/" not in name and "%" not in name


# ─── Building the command ─────────────────────────────────────────────────────

def test_a_job_description_becomes_one_argument_not_a_command():
    """The whole point. A posting is data and must never be parsed as shell."""
    argv, _ = tailor.build_argv(
        "mycmd {prompt}", {"prompt": "; rm -rf / #  $(whoami) `id`"}
    )
    assert argv == ["mycmd", "; rm -rf / #  $(whoami) `id`"]


def test_placeholders_are_filled_from_the_map():
    argv, stdin = tailor.build_argv(
        "tool --in {prompt_file} --out {output_file}",
        {"prompt": "p", "prompt_file": "/tmp/p.md", "output_file": "/tmp/o.md"},
    )
    assert argv == ["tool", "--in", "/tmp/p.md", "--out", "/tmp/o.md"]
    assert stdin is None


def test_a_command_mentioning_no_prompt_gets_it_on_stdin():
    argv, stdin = tailor.build_argv("tool --out {output_file}", {
        "prompt": "the prompt", "output_file": "/tmp/o.md",
    })
    assert stdin == "the prompt"
    assert "the prompt" not in argv


def test_an_over_long_prompt_moves_to_stdin_rather_than_failing():
    """Linux refuses one argument over about 128 KB. A CV can reach that."""
    huge = "x" * 40_000
    argv, stdin = tailor.build_argv("tool {prompt}", {"prompt": huge})
    assert argv == ["tool"]
    assert stdin == huge


def test_an_unparseable_command_says_so(tmp_path):
    with pytest.raises(tailor.TailorError):
        tailor.build_argv('tool "unclosed', {"prompt": "p"})


# ─── The prompt ───────────────────────────────────────────────────────────────

def test_the_prompt_gets_the_posting_and_your_answers():
    rendered = tailor.render_prompt(
        "Role: {title} at {company}. Gaps: {gaps}. You said: {answers}",
        JOB, "I led the Azure migration", Path("/tmp/out.md"),
    )
    assert "Solution Architect at Northwind Energy" in rendered
    assert "No pharma" in rendered
    assert "I led the Azure migration" in rendered


def test_a_stray_brace_in_a_prompt_is_left_alone():
    """Prose contains braces. Losing a day's work to one would be a poor trade."""
    rendered = tailor.render_prompt("Use {title} and keep {this_one}", JOB, "", Path("o"))
    assert "Solution Architect" in rendered
    assert "{this_one}" in rendered


# ─── Running it ───────────────────────────────────────────────────────────────

def test_a_working_command_produces_the_document(tmp_path):
    settings = settings_for(tmp_path, {"command": writer_command(), "min_score": 80})
    produced = tailor.tailor_job(settings, JOB, answers="", today=date(2026, 8, 28))
    assert produced is not None
    assert produced.read_text(encoding="utf-8") == "written by the command"


def test_the_command_is_given_the_posting_as_json(tmp_path):
    """A command that is a script wants data, not a prompt."""
    script = (
        "import sys,json,pathlib;"
        "job=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'));"
        "pathlib.Path(sys.argv[2]).write_text(job['company'],encoding='utf-8')"
    )
    command = f'"{sys.executable}" -c "{script}" {{job_file}} {{output_file}}'
    settings = settings_for(tmp_path, {"command": command})
    produced = tailor.tailor_job(settings, JOB, today=date(2026, 8, 28))
    assert produced.read_text(encoding="utf-8") == "Northwind Energy"


def test_your_answers_reach_the_command_in_a_file(tmp_path):
    script = (
        "import sys,pathlib;"
        "pathlib.Path(sys.argv[2]).write_text("
        "pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'),encoding='utf-8')"
    )
    command = f'"{sys.executable}" -c "{script}" {{answers_file}} {{output_file}}'
    settings = settings_for(tmp_path, {"command": command})
    produced = tailor.tailor_job(settings, JOB, answers="the OT/IT one", today=date(2026, 8, 28))
    assert produced.read_text(encoding="utf-8") == "the OT/IT one"


def test_a_command_that_writes_nothing_is_a_failure(tmp_path):
    """Silently producing no document is worse than breaking."""
    settings = settings_for(tmp_path, {"command": f'"{sys.executable}" -c "pass"'})
    assert tailor.tailor_job(settings, JOB, today=date(2026, 8, 28)) is None


def test_a_command_that_exits_non_zero_is_a_failure(tmp_path):
    settings = settings_for(tmp_path, {"command": f'"{sys.executable}" -c "raise SystemExit(3)"'})
    assert tailor.tailor_job(settings, JOB, today=date(2026, 8, 28)) is None


def test_a_command_that_is_not_installed_says_which_one(tmp_path, caplog):
    settings = settings_for(tmp_path, {"command": "definitely-not-installed {output_file}"})
    assert tailor.tailor_job(settings, JOB, today=date(2026, 8, 28)) is None
    assert "definitely-not-installed" in caplog.text


def test_a_hanging_command_is_stopped(tmp_path):
    settings = settings_for(tmp_path, {
        "command": f'"{sys.executable}" -c "import time; time.sleep(30)"',
        "timeout_seconds": 1,
    })
    assert tailor.tailor_job(settings, JOB, today=date(2026, 8, 28)) is None


def test_a_posting_is_never_tailored_twice(tmp_path):
    """The second call must not spend another model call."""
    settings = settings_for(tmp_path, {"command": writer_command("first")})
    first = tailor.tailor_job(settings, JOB, today=date(2026, 8, 28))

    settings = settings_for(tmp_path, {"command": writer_command("second")})
    second = tailor.tailor_job(settings, JOB, today=date(2026, 8, 28))

    assert first == second
    assert second.read_text(encoding="utf-8") == "first"


def test_the_result_is_delivered(tmp_path):
    from job_scout.notifiers import Dispatcher, build

    settings = settings_for(tmp_path, {"command": writer_command()})
    out = tmp_path / "data"
    dispatcher = Dispatcher(build([{"type": "file", "path": str(out / "matches.md")}], out))
    produced = tailor.tailor_job(
        settings, JOB, dispatcher=dispatcher, today=date(2026, 8, 28)
    )
    assert (out / produced.name).exists()


def test_deliver_false_leaves_it_on_disk_only(tmp_path):
    from job_scout.notifiers import Dispatcher, build

    settings = settings_for(tmp_path, {"command": writer_command(), "deliver": False})
    out = tmp_path / "elsewhere"
    dispatcher = Dispatcher(build([{"type": "file", "path": str(out / "matches.md")}], out))
    produced = tailor.tailor_job(
        settings, JOB, dispatcher=dispatcher, today=date(2026, 8, 28)
    )
    assert produced.exists()
    assert not (out / produced.name).exists()


# ─── Configuration ────────────────────────────────────────────────────────────

def test_no_tailor_block_means_nothing_happens():
    assert tailor.is_configured({}) is False
    assert tailor.is_configured({"tailor": {}}) is False
    assert tailor.is_configured({"tailor": {"command": "x"}}) is True


def test_an_empty_command_says_what_to_do(tmp_path):
    with pytest.raises(tailor.TailorError) as excinfo:
        tailor.load({"tailor": {"command": "  "}}, tmp_path, tmp_path)
    assert "remove the tailor block" in str(excinfo.value)


def test_a_missing_prompt_file_says_where_it_looked(tmp_path):
    config = tailor.load(
        {"tailor": {"command": "x", "prompt_file": "nope.md"}}, tmp_path, tmp_path
    )
    with pytest.raises(tailor.TailorError) as excinfo:
        tailor.read_template(config)
    assert "nope.md" in str(excinfo.value)


def test_the_job_payload_carries_what_a_command_needs():
    payload = tailor._job_payload(JOB)
    assert payload["company"] == "Northwind Energy"
    assert payload["verdict"]["reasoning"] == "close fit"
    assert json.dumps(payload)
