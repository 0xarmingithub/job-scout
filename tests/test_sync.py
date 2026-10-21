"""
The optional `git pull` of the config directory.

git is never run here: subprocess is replaced by a script of answers, so the
tests cover the retry and the alert decision without a repository or a network.
"""

import subprocess

import pytest

from job_scout import cli, sync
from job_scout.config import ConfigError, load_settings, merge_sync


class FakeGit:
    """Answers each git call from a script. Records what was asked."""

    def __init__(self, pulls, behind="0\n", behind_code=0):
        self.pulls = list(pulls)  # (returncode, stdout, stderr) or an exception
        self.behind = behind
        self.behind_code = behind_code
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0", "git must never wait for a password"
        assert kwargs["timeout"] > 0
        if argv[1] == "pull":
            outcome = self.pulls.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            code, out, err = outcome
            return subprocess.CompletedProcess(argv, code, stdout=out, stderr=err)
        if argv[1] == "rev-list":
            return subprocess.CompletedProcess(
                argv, self.behind_code, stdout=self.behind, stderr=""
            )
        raise AssertionError(f"unexpected git call {argv}")

    @property
    def pull_count(self):
        return sum(1 for call in self.calls if call[1] == "pull")


def _pull(git, retries=2):
    sleeps = []
    result = sync.pull("config", retries=retries, wait_seconds=7, runner=git, sleep=sleeps.append)
    return result, sleeps


def test_a_clean_pull_is_one_call_and_no_alert():
    git = FakeGit([(0, "Already up to date.\n", "")])
    result, sleeps = _pull(git)
    assert result.ok and not result.alert
    assert git.pull_count == 1 and sleeps == []
    assert git.calls[0][:3] == ["git", "pull", "--ff-only"]


def test_a_failure_is_retried_after_a_wait_and_a_later_success_is_quiet():
    git = FakeGit([(1, "", "could not resolve host"), (0, "Updating\n", "")])
    result, sleeps = _pull(git)
    assert result.ok and not result.alert
    assert git.pull_count == 2
    assert sleeps == [7]


def test_it_gives_up_after_the_configured_retries():
    git = FakeGit([(1, "", "network down")] * 3)
    result, sleeps = _pull(git, retries=2)
    assert not result.ok
    assert git.pull_count == 3
    assert sleeps == [7, 7], "no wait after the last attempt"


def test_zero_retries_means_one_attempt():
    git = FakeGit([(1, "", "network down")])
    result, sleeps = _pull(git, retries=0)
    assert git.pull_count == 1 and sleeps == []
    assert not result.ok


def test_a_failed_pull_while_up_to_date_does_not_alert():
    git = FakeGit([(1, "", "network down")] * 3, behind="0\n")
    result, _ = _pull(git)
    assert not result.ok
    assert result.alert == "", "a failed pull that changes nothing is not worth waking anyone"


def test_a_failed_pull_while_behind_alerts_with_a_reason_and_a_fix():
    git = FakeGit([(1, "", "network down")] * 3, behind="4\n")
    result, _ = _pull(git)
    assert not result.ok
    assert "4 commit(s) behind" in result.alert
    assert "network down" in result.alert
    assert "git pull --ff-only" in result.alert


def test_not_knowing_whether_it_is_behind_does_not_alert():
    """No upstream branch, so rev-list fails. Guessing would alert on every run."""
    git = FakeGit([(1, "", "no tracking information")] * 3, behind="", behind_code=128)
    result, _ = _pull(git)
    assert not result.ok and result.alert == ""


def test_a_timeout_counts_as_a_failed_attempt():
    git = FakeGit([subprocess.TimeoutExpired("git", 120)] * 3, behind="2\n")
    result, _ = _pull(git)
    assert "timed out" in result.message
    assert "2 commit(s) behind" in result.alert


def test_a_missing_git_is_a_sentence_not_a_traceback():
    git = FakeGit([FileNotFoundError("git")])
    result, _ = _pull(git)
    assert not result.ok
    assert "git is not installed" in result.message
    assert git.pull_count == 1, "retrying will not install git"


def test_a_credential_in_git_output_never_reaches_the_alert():
    secret_url = "https://user:hunter2@example.test/x.git"  # pre-push-check: allow
    git = FakeGit([(1, "", f"fatal: unable to access {secret_url}")] * 3, behind="1\n")
    result, _ = _pull(git)
    assert "hunter2" not in result.alert
    assert "hunter2" not in result.message


# --- Reading the config ---------------------------------------------------------------

def _config(tmp_path, text):
    (tmp_path / "config.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_sync_is_off_unless_asked_for(tmp_path):
    assert sync.read_block(_config(tmp_path, "notify_threshold: 65\n")) is None
    git = FakeGit([])
    assert sync.before_run(tmp_path, runner=git, sleep=lambda s: None).attempted is False
    assert git.calls == []


def test_git_pull_true_turns_it_on_with_defaults(tmp_path):
    block = sync.read_block(_config(tmp_path, "sync:\n  git_pull: true\n"))
    assert block["retries"] == 2 and block["retry_wait_seconds"] == 10


def test_before_run_uses_the_configured_retries_and_wait(tmp_path):
    _config(tmp_path, "sync:\n  git_pull: true\n  retries: 1\n  retry_wait_seconds: 3\n")
    git = FakeGit([(1, "", "down"), (1, "", "down")])
    sleeps = []
    result = sync.before_run(tmp_path, runner=git, sleep=sleeps.append)
    assert result.attempted and not result.ok
    assert git.pull_count == 2 and sleeps == [3]


def test_a_missing_or_broken_config_file_means_no_sync(tmp_path):
    assert sync.read_block(tmp_path) is None
    assert sync.read_block(_config(tmp_path, ": : not yaml [")) is None
    assert sync.read_block(_config(tmp_path, "- a list\n")) is None


def test_a_wrong_sync_block_is_reported_by_load_settings_not_by_the_pull(config_dir):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\nsync:\n  git_pull: yes please\n")
    assert sync.read_block(config_dir) is None
    with pytest.raises(ConfigError, match="sync.git_pull must be true or false"):
        load_settings(str(config_dir))


@pytest.mark.parametrize(
    "block,message",
    [
        ("sync: true\n", "must be a mapping"),
        ("sync:\n  pull: true\n", "unknown key"),
        ("sync:\n  retries: -1\n", "sync.retries"),
        ("sync:\n  retries: two\n", "sync.retries"),
        ("sync:\n  retry_wait_seconds: 1.5\n", "sync.retry_wait_seconds"),
    ],
)
def test_wrong_values_are_rejected_with_the_key_name(block, message):
    import yaml

    with pytest.raises(ConfigError, match=message):
        merge_sync(yaml.safe_load(block))


def test_the_defaults_are_what_the_docs_say():
    assert merge_sync({}) == {"git_pull": False, "retries": 2, "retry_wait_seconds": 10}


# --- Reporting -----------------------------------------------------------------------------

class Recorder:
    def __init__(self):
        self.alerts = []

    def send_alert(self, body):
        self.alerts.append(body)
        return 1


def test_report_sends_the_alert_and_only_the_alert():
    recorder = Recorder()
    sync.report(sync.SyncResult(attempted=True, ok=False, message="m", alert="behind"), recorder)
    assert recorder.alerts == ["behind"]


def test_report_is_silent_for_success_failure_without_alert_and_no_attempt():
    recorder = Recorder()
    sync.report(sync.SyncResult(), recorder)
    sync.report(sync.SyncResult(attempted=True, ok=True, message="fine"), recorder)
    sync.report(sync.SyncResult(attempted=True, ok=False, message="down"), recorder)
    assert recorder.alerts == []


def test_an_alert_that_cannot_be_sent_does_not_raise():
    class Broken:
        def send_alert(self, body):
            raise RuntimeError("telegram is down")

    sync.report(sync.SyncResult(attempted=True, ok=False, message="m", alert="behind"), Broken())


# --- Through the command ------------------------------------------------------------------------

def test_a_real_run_pulls_first_and_a_dry_run_never_does(config_dir, monkeypatch):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\nsync:\n  git_pull: true\n")
    calls = []

    def fake_before_run(directory, **kwargs):
        calls.append(directory)
        return sync.SyncResult()

    monkeypatch.setattr(sync, "before_run", fake_before_run)
    monkeypatch.setattr("job_scout.run.run_once", lambda settings, dry_run, limit: _FakeResult())
    monkeypatch.setattr("job_scout.run.setup_logging", lambda *a, **k: None)

    assert cli.main(["run", "--config-dir", str(config_dir)]) == 0
    assert calls == [config_dir.resolve()]

    calls.clear()
    monkeypatch.setattr(cli, "_print_dry_run", lambda *a: None)
    assert cli.main(["run", "--dry-run", "--config-dir", str(config_dir)]) == 0
    assert calls == [], "a dry run changes nothing on disk"


def test_a_behind_config_is_alerted_through_the_notifiers(config_dir, monkeypatch):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\nsync:\n  git_pull: true\n")
    failed = sync.SyncResult(attempted=True, ok=False, message="down", alert="you are behind")
    monkeypatch.setattr(sync, "before_run", lambda directory, **kwargs: failed)
    monkeypatch.setattr("job_scout.run.run_once", lambda settings, dry_run, limit: _FakeResult())
    monkeypatch.setattr("job_scout.run.setup_logging", lambda *a, **k: None)

    assert cli.main(["run", "--config-dir", str(config_dir)]) == 0

    matches = (config_dir / "data" / "matches.md").read_text(encoding="utf-8")
    assert "ALERT" in matches and "you are behind" in matches


class _FakeResult:
    ok = True
    matched: list = []
    stats = None
