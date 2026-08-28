"""
Notifiers. The file writer is exercised for real; the three that need the
network are only checked for the message they give when they are not set up,
and for the fact that they refuse to send rather than raise.
"""

import json

import pytest

from job_scout.notifiers import Dispatcher, UnknownNotifier, build
from job_scout.notifiers.base import (
    RunStats,
    digest_header,
    format_job,
    no_match_body,
    score_label,
)


@pytest.fixture
def matches() -> list[dict]:
    return [
        {
            "title": "Platform Engineer",
            "company": "Northwind Energy",
            "location": "Berlin, Germany",
            "site": "linkedin",
            "score": 84,
            "salary": "EUR 80,000-95,000 / yearly",
            "url": "https://example.com/job/1",
            "search_term": "platform engineer",
            "verdict": {
                "key_matches": ["Kubernetes", "Terraform", "AWS"],
                "gaps": ["Kafka Streams"],
                "reasoning": "Strong overlap on the platform stack.",
            },
        },
        {
            "title": "Site Reliability Engineer",
            "company": "Halden Data",
            "location": "Remote, EU",
            "site": "indeed",
            "score": 68,
            "url": "https://example.com/job/2",
            "search_term": "site reliability engineer",
            "verdict": {"key_matches": ["Prometheus"], "gaps": [], "reasoning": "Decent fit."},
        },
    ]


@pytest.fixture
def stats() -> RunStats:
    return RunStats(
        total_fetched=57, total_new=12, total_rejected=10,
        threshold=65, source_summary="jobspy: 57",
    )


# ─── Shared formatting ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "score,label", [(100, "STRONG"), (80, "STRONG"), (79, "POSSIBLE"),
                    (65, "POSSIBLE"), (64, "LONG SHOT"), (0, "LONG SHOT")],
)
def test_score_bands(score, label):
    assert score_label(score) == label


def test_a_job_renders_every_field_it_has(matches):
    text = format_job(matches[0])
    for expected in ("84%", "STRONG", "Platform Engineer", "Northwind Energy",
                     "Berlin", "LINKEDIN", "Kubernetes", "Kafka Streams",
                     "Strong overlap", "https://example.com/job/1"):
        assert expected in text


def test_a_job_with_no_verdict_still_renders():
    text = format_job({"title": "X", "company": "Y", "score": 70, "url": "https://z"})
    assert "70%" in text and "https://z" in text


def test_header_counts(matches, stats):
    header = digest_header(matches, stats)
    assert "2 matches" in header
    assert "12 new" in header
    assert "10 below 65" in header
    assert "57 fetched" in header


def test_header_uses_the_singular_for_one_match(matches, stats):
    assert "1 match " in digest_header(matches[:1], stats)


def test_zero_fetched_reads_as_something_is_broken():
    body = no_match_body(RunStats(total_fetched=0, source_summary="jobspy: FAILED"))
    assert "job-scout check" in body
    assert "blocked or misconfigured" in body


def test_nothing_new_reads_as_a_quiet_day():
    body = no_match_body(RunStats(total_fetched=57, total_new=0))
    assert "already seen" in body


def test_nothing_above_threshold_says_so():
    body = no_match_body(RunStats(total_fetched=57, total_new=12,
                                  total_rejected=12, threshold=70))
    assert "No matches at or above 70" in body


# ─── Building ─────────────────────────────────────────────────────────────────

def test_an_unknown_notifier_type_lists_the_real_ones(tmp_path):
    with pytest.raises(UnknownNotifier) as excinfo:
        build([{"type": "carrier-pigeon"}], tmp_path)
    assert "file" in str(excinfo.value)
    assert "telegram" in str(excinfo.value)


# ─── The file writer ──────────────────────────────────────────────────────────

def test_markdown_output(tmp_path, matches, stats):
    notifier = build([{"type": "file", "path": "matches.md"}], tmp_path)[0]
    assert notifier.check() is None
    assert notifier.send_digest(matches, stats)

    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert "### 84% Platform Engineer" in text
    assert "**Northwind Energy**" in text
    assert "<https://example.com/job/1>" in text
    assert "Sources: jobspy: 57" in text


def test_csv_output_has_a_header_once(tmp_path, matches, stats):
    notifier = build(
        [{"type": "file", "path": "matches.csv", "format": "csv"}], tmp_path
    )[0]
    notifier.send_digest(matches, stats)
    notifier.send_digest(matches, stats)

    lines = (tmp_path / "matches.csv").read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("run_at,score,title")
    assert sum(1 for line in lines if line.startswith("run_at,")) == 1
    assert len(lines) == 5  # one header, two runs of two matches


def test_json_output_is_one_object_per_line(tmp_path, matches, stats):
    notifier = build(
        [{"type": "file", "path": "matches.jsonl", "format": "json"}], tmp_path
    )[0]
    notifier.send_digest(matches, stats)

    lines = (tmp_path / "matches.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["title"] == "Platform Engineer"
    assert record["score"] == 84
    assert "run_at" in record


def test_text_output(tmp_path, matches, stats):
    notifier = build(
        [{"type": "file", "path": "matches.txt", "format": "text"}], tmp_path
    )[0]
    notifier.send_digest(matches, stats)
    assert "[STRONG] 84%" in (tmp_path / "matches.txt").read_text(encoding="utf-8")


def test_no_matches_still_writes_something_useful(tmp_path, stats):
    notifier = build([{"type": "file"}], tmp_path)[0]
    notifier.send_digest([], stats)
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert "0 match(es)" in text


def test_append_keeps_the_previous_run(tmp_path, matches, stats):
    notifier = build([{"type": "file", "append": True}], tmp_path)[0]
    notifier.send_digest(matches, stats)
    notifier.send_digest(matches, stats)
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert text.count("### 84% Platform Engineer") == 2


def test_append_false_replaces_the_file(tmp_path, matches, stats):
    notifier = build([{"type": "file", "append": False}], tmp_path)[0]
    notifier.send_digest(matches, stats)
    notifier.send_digest(matches, stats)
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert text.count("### 84% Platform Engineer") == 1


def test_an_absolute_path_is_honoured(tmp_path, matches, stats):
    target = tmp_path / "elsewhere" / "out.md"
    notifier = build([{"type": "file", "path": str(target)}], tmp_path)[0]
    notifier.send_digest(matches, stats)
    assert target.exists()


def test_an_unknown_format_is_reported(tmp_path):
    notifier = build([{"type": "file", "format": "papyrus"}], tmp_path)[0]
    assert "papyrus" in notifier.check()


def test_the_file_writer_can_alert(tmp_path):
    notifier = build([{"type": "file"}], tmp_path)[0]
    assert notifier.send_alert("The run failed.")
    assert "ALERT" in (tmp_path / "matches.md").read_text(encoding="utf-8")


def test_an_alert_never_leaks_a_token(tmp_path):
    notifier = build([{"type": "file"}], tmp_path)[0]
    notifier.send_alert(  # pre-push-check: allow
        "git failed: https://user:hunter2@github.com/x ghp_"  # pre-push-check: allow
        + "a" * 36
    )
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "ghp_" not in text
    assert "REDACTED" in text


def test_a_note_is_not_filed_as_an_alert(tmp_path):
    """
    A weekly reminder under the word ALERT teaches you to skip alerts, and the
    next one is the run that actually died.
    """
    notifier = build([{"type": "file"}], tmp_path)[0]
    assert notifier.send_note("3 applications have not moved in 21 days.")
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert "have not moved in 21 days" in text
    assert "ALERT" not in text


def test_a_note_is_redacted_like_an_alert(tmp_path):
    notifier = build([{"type": "file"}], tmp_path)[0]
    notifier.send_note(  # pre-push-check: allow
        "checked https://user:hunter2@github.com/x"  # pre-push-check: allow
    )
    text = (tmp_path / "matches.md").read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "REDACTED" in text


def test_the_dispatcher_counts_the_channels_that_took_a_note(tmp_path):
    dispatcher = Dispatcher(build([{"type": "file"}, {"type": "file"}], tmp_path))
    assert dispatcher.send_note("anything") == 2


def test_one_broken_channel_does_not_stop_a_note(tmp_path):
    class Broken:
        name = "broken"

        def send_note(self, body):
            raise RuntimeError("no")

    working = build([{"type": "file"}], tmp_path)[0]
    assert Dispatcher([Broken(), working]).send_note("still delivered") == 1


# ─── The three that need credentials ──────────────────────────────────────────

def test_telegram_says_what_is_missing(tmp_path):
    message = build([{"type": "telegram"}], tmp_path)[0].check()
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "BotFather" in message


def test_telegram_is_happy_once_both_are_set(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    assert build([{"type": "telegram"}], tmp_path)[0].check() is None


def test_telegram_refuses_to_send_rather_than_raising(tmp_path, stats):
    assert build([{"type": "telegram"}], tmp_path)[0].send_digest([], stats) is False


def test_email_wants_a_recipient(tmp_path):
    assert "no recipient" in build([{"type": "email"}], tmp_path)[0].check()


def test_email_wants_smtp_settings(tmp_path):
    message = build([{"type": "email", "to": "a@b.c"}], tmp_path)[0].check()
    assert "SMTP_HOST" in message
    assert "App Password" in message


def test_email_refuses_to_send_rather_than_raising(tmp_path, stats):
    notifier = build([{"type": "email", "to": "a@b.c"}], tmp_path)[0]
    assert notifier.send_digest([], stats) is False


def test_email_port_465_implies_ssl(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    assert build([{"type": "email", "to": "a@b.c"}], tmp_path)[0].security == "ssl"


def test_webhook_names_the_variable_it_wants(tmp_path):
    message = build([{"type": "webhook"}], tmp_path)[0].check()
    assert "WEBHOOK_URL" in message


def test_webhook_honours_a_custom_variable_name(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_JOBS_URL", "https://hooks.slack.com/x")
    notifier = build([{"type": "webhook", "url_env": "SLACK_JOBS_URL"}], tmp_path)[0]
    assert notifier.check() is None


def test_discord_uses_content_not_text(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL", "https://discord.example/x")
    notifier = build([{"type": "webhook", "flavor": "discord"}], tmp_path)[0]
    assert notifier._payload("hi") == {"content": "hi"}


# ─── The dispatcher ───────────────────────────────────────────────────────────

def test_dispatcher_reports_which_notifiers_are_ready(tmp_path):
    dispatcher = Dispatcher(build([{"type": "file"}, {"type": "telegram"}], tmp_path))
    results = dict(dispatcher.check())
    assert results["file"] is None
    assert "TELEGRAM_BOT_TOKEN" in results["telegram"]
    assert [n.name for n in dispatcher.ready()] == ["file"]


def test_one_broken_notifier_does_not_stop_the_others(tmp_path, matches, stats):
    dispatcher = Dispatcher(build([{"type": "telegram"}, {"type": "file"}], tmp_path))
    assert dispatcher.send_digest(matches, stats) == 1
    assert (tmp_path / "matches.md").exists()


def test_a_notifier_that_raises_is_swallowed(tmp_path, matches, stats):
    class Exploding:
        name = "exploding"

        def check(self):
            raise RuntimeError("boom")

        def send_digest(self, *args):
            raise RuntimeError("boom")

        def send_alert(self, *args):
            raise RuntimeError("boom")

    notifiers = build([{"type": "file"}], tmp_path)
    dispatcher = Dispatcher([Exploding()] + notifiers)
    assert dispatcher.send_digest(matches, stats) == 1
    assert dispatcher.send_alert("something went wrong") == 1
    assert dict(dispatcher.check())["exploding"] == "check failed: boom"
