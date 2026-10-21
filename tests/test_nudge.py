"""
Tests for nudge.py.

The failure mode worth guarding is not a crash. It is a reminder that nags
about the wrong things: folders with no CV in them, applications that already
have a result, or a count that was hardcoded and went stale a week later. Any
of those trains the reader to ignore it, and then the nudge is worse than
nothing.

Every name here is fictional.
"""

from datetime import date

import pytest

from job_scout import cli, nudge, patterns
from job_scout.config import load_settings

TODAY = date(2025, 10, 2)


def _app(root, folder, status="**Status:** drafted", cv=True, company="Contoso"):
    app = root / folder
    app.mkdir(parents=True)
    (app / "notes.md").write_text(status, encoding="utf-8")
    (app / "jd.md").write_text(f"**Company:** {company}\n", encoding="utf-8")
    if cv:
        (app / "CV.tex").write_text("%", encoding="utf-8")
    return app


@pytest.fixture
def apps(tmp_path):
    return tmp_path


def _build(apps, stale_days=21):
    return nudge.build(patterns.collect(apps), stale_days, TODAY)


# --- What it asks about ------------------------------------------------------------------

def test_a_folder_with_no_status_line_is_asked_about(apps):
    _app(apps, "contoso-architect-20250611", status="nothing useful here")
    message, total = _build(apps)
    assert total == 1
    assert "No status line at all (1)" in message
    assert "Contoso" in message


def test_an_old_draft_is_asked_whether_it_was_sent(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** drafted, waiting on a final read")
    message, total = _build(apps)
    assert total == 1
    assert "Sent or not?" in message


def test_a_recent_draft_is_left_alone(apps):
    _app(apps, "contoso-architect-20250925", status="**Status:** drafted")
    assert _build(apps) == ("", 0)


def test_a_finished_application_is_left_alone(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** rejected")
    _app(apps, "fabrikam-architect-20250612", status="**Status:** interviewing")
    assert _build(apps) == ("", 0)


def test_an_acknowledged_application_is_not_asked_about(apps):
    """The employer confirmed receipt. Asking "sent or not?" would be the nag that gets ignored."""
    _app(apps, "contoso-architect-20250611", status="**Status:** acknowledged")
    assert _build(apps) == ("", 0)


def test_a_folder_with_no_cv_is_not_chased(apps):
    """There is nothing to chase. A JD saved and never worked on is not an
    application whose outcome went missing."""
    _app(apps, "contoso-architect-20250611", status="no status", cv=False)
    assert _build(apps) == ("", 0)


def test_the_two_questions_are_kept_apart(apps):
    """"What happened?" and "did you send it?" need different answers."""
    _app(apps, "contoso-architect-20250611", status="no status line")
    _app(apps, "fabrikam-architect-20250612", status="**Status:** drafted")
    message, total = _build(apps)
    assert total == 2
    assert message.index("What happened?") < message.index("Sent or not?")


# --- Staying readable on a phone -----------------------------------------------------------

def test_a_long_list_is_capped_and_says_how_many_it_hid(apps):
    for index in range(nudge.MAX_LISTED + 4):
        _app(apps, f"company{index}-architect-202506{10 + index:02d}", status="no status")
    message, total = _build(apps)
    assert total == nudge.MAX_LISTED + 4
    assert "and 4 more" in message
    assert "job-scout patterns" in message


def test_the_oldest_come_first(apps):
    _app(apps, "recent-architect-20250915", status="no status", company="Recent")
    _app(apps, "ancient-architect-20250611", status="no status", company="Ancient")
    message, _ = _build(apps)
    assert message.index("Ancient") < message.index("Recent")


# --- The closing number ------------------------------------------------------------------------

def test_the_shortfall_is_counted_not_written_down(apps):
    """A hardcoded "two to go" is wrong the week after it is written, and a
    reminder carrying a stale number is one that gets ignored."""
    _app(apps, "contoso-architect-20250611", status="no status")
    for index in range(3):
        _app(apps, f"sent{index}-architect-20250612", status="**Status:** rejected")
    message, _ = _build(apps)
    short = patterns.MIN_SENT_FOR_RATES - 3
    assert f"3 application(s) have a recorded result. {short} more" in message


def test_it_says_when_calibration_is_unblocked(apps):
    _app(apps, "contoso-architect-20250611", status="no status")
    for index in range(patterns.MIN_SENT_FOR_RATES):
        _app(apps, f"sent{index}-architect-20250612", status="**Status:** rejected")
    message, _ = _build(apps)
    assert "enough for" in message
    assert "more and" not in message


def test_the_message_says_which_line_to_update_and_where_it_is_documented(apps):
    _app(apps, "contoso-architect-20250611", status="no status")
    message, _ = _build(apps)
    assert "Update the Status: line in each notes.md" in message
    assert "docs/applications.md" in message


def test_age_is_counted_from_the_date_in_the_folder_name(apps):
    """Not from file times, which a copy or a checkout resets."""
    _app(apps, "contoso-architect-20250611", status="**Status:** drafted")
    _app(apps, "fabrikam-architect-20250915", status="**Status:** drafted")
    message, total = _build(apps, stale_days=60)
    assert total == 1
    assert "113d" in message
    assert "Fabrikam" not in message


def test_a_folder_without_a_date_is_never_stale(apps):
    _app(apps, "contoso-architect", status="**Status:** drafted")
    assert _build(apps, stale_days=0) == ("", 0)


def test_a_folder_without_a_date_with_no_status_is_still_asked_about(apps):
    _app(apps, "contoso-architect", status="no status")
    message, total = _build(apps)
    assert total == 1
    assert "No status line at all" in message


def test_a_phrase_the_person_listed_does_not_count_as_a_status(apps):
    """With the phrase ignored the line is empty, so the folder is asked about."""
    _app(apps, "contoso-architect-20250611", status="**Status:** interview prep")
    records = patterns.collect(apps, ("interview prep",))
    message, total = nudge.build(records, 21, TODAY)
    assert total == 1
    assert "No status line at all" in message


# --- Sending -----------------------------------------------------------------------------------------

class _Args:
    stale_days = 21
    dry_run = False


def _settings(config_dir, status="no status", folder="contoso-architect-20250611"):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    _app(config_dir / "applications", folder, status=status)
    return load_settings(str(config_dir))


def test_nothing_to_ask_exits_zero_and_says_so(config_dir):
    settings = _settings(config_dir, status="**Status:** rejected")
    lines = []
    assert nudge.command(_Args(), settings, lines.append) == 0
    assert "Nothing to ask" in lines[0]


def test_a_dry_run_sends_nothing(config_dir, monkeypatch):
    settings = _settings(config_dir)

    def explode(settings, message):
        raise AssertionError("--dry-run must not send")

    monkeypatch.setattr(nudge, "send", explode)
    args = _Args()
    args.dry_run = True
    lines = []
    assert nudge.command(args, settings, lines.append) == 0
    assert "No status line at all" in "\n".join(lines)


def test_reaching_no_notifier_is_a_failure_not_a_silent_success(config_dir, monkeypatch):
    settings = _settings(config_dir)
    monkeypatch.setattr(nudge, "send", lambda settings, message: 0)
    assert nudge.command(_Args(), settings, lambda s: None) == 1


def test_a_successful_send_reports_how_many_channels_took_it(config_dir, monkeypatch):
    settings = _settings(config_dir)
    monkeypatch.setattr(nudge, "send", lambda settings, message: 2)
    lines = []
    assert nudge.command(_Args(), settings, lines.append) == 0
    assert "sent to 2 notifier(s)" in lines[0]


def test_it_really_goes_out_through_the_notifiers_as_a_note(config_dir):
    """The file notifier is the default. The message lands in it, and is not headed ALERT."""
    settings = _settings(config_dir)
    assert nudge.command(_Args(), settings, lambda s: None) == 0
    written = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "have no result recorded" in written
    assert "ALERT" not in written


def test_without_applications_dir_the_command_says_what_to_set(config_dir):
    settings = load_settings(str(config_dir))
    lines = []
    assert nudge.command(_Args(), settings, lines.append) == 2
    assert "applications_dir is not set" in lines[0]


# --- Riding along with the roundup -----------------------------------------------------------------

def test_without_applications_dir_the_roundup_hook_does_nothing(config_dir, monkeypatch):
    settings = load_settings(str(config_dir))
    monkeypatch.setattr(nudge, "send", lambda *a: (_ for _ in ()).throw(AssertionError("sent")))
    nudge.after_roundup(settings, dry_run=False)


def test_the_hook_sends_after_a_real_roundup(config_dir, monkeypatch):
    settings = _settings(config_dir)
    sent = []
    monkeypatch.setattr(nudge, "send", lambda settings, message: sent.append(message) or 1)
    nudge.after_roundup(settings, dry_run=False, output_fn=lambda s: None)
    assert len(sent) == 1


def test_the_hook_in_a_dry_run_prints_and_sends_nothing(config_dir, monkeypatch):
    settings = _settings(config_dir)
    monkeypatch.setattr(nudge, "send", lambda *a: (_ for _ in ()).throw(AssertionError("sent")))
    lines = []
    nudge.after_roundup(settings, dry_run=True, output_fn=lines.append)
    assert "No status line at all" in "\n".join(lines)


def test_a_broken_nudge_never_breaks_the_roundup(config_dir, monkeypatch):
    settings = _settings(config_dir)

    def explode(*args, **kwargs):
        raise RuntimeError("the folder vanished")

    monkeypatch.setattr(patterns, "collect", explode)
    nudge.after_roundup(settings, dry_run=False)  # must not raise


def test_roundup_runs_the_nudge_unless_told_not_to(config_dir, monkeypatch):
    settings_dir = str(config_dir)
    _settings(config_dir)
    calls = []
    monkeypatch.setattr(nudge, "after_roundup", lambda settings, dry_run, **k: calls.append(dry_run))
    monkeypatch.setattr(
        "job_scout.notifiers.Dispatcher.send_digest", lambda self, jobs, stats: 1
    )

    assert cli.main(["roundup", "--config-dir", settings_dir]) == 0
    assert calls == [False]

    calls.clear()
    assert cli.main(["roundup", "--config-dir", settings_dir, "--no-nudge"]) == 0
    assert calls == []

    assert cli.main(["roundup", "--config-dir", settings_dir, "--dry-run"]) == 0
    assert calls == [True]
