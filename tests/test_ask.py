"""
Tests for asking the owner a question and waiting for the answer.

The security property here is the one to keep: anyone who learns a bot token
can message it, so only the one configured chat is ever read.

No network. Telegram is replaced throughout.
"""

import json
import sys
from datetime import datetime, timedelta

import pytest

from job_scout import ask

CHAT = "555"
JOB = {"title": "Solution Architect", "company": "Northwind Energy", "score": 91}

CONFIG = {
    "notifiers": [{"type": "telegram"}],
    "ask": {"questions": ["Which project is closest?", "Anything to leave out?"]},
}


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)


class _Response:
    def __init__(self, payload=None, ok=True, status_code=200):
        self._payload = payload or {"ok": True, "result": []}
        self.ok = ok
        self.status_code = status_code
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def _update(update_id: int, text: str, chat_id: str = CHAT) -> dict:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": int(chat_id)}, "text": text},
    }


@pytest.fixture
def telegram(monkeypatch):
    """A fake Telegram. `inbox` is what getUpdates returns, `sent` what went out."""
    import requests

    box = {"inbox": [], "sent": []}
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: _Response({"ok": True, "result": box["inbox"]})
    )
    monkeypatch.setattr(
        requests, "post", lambda url, **kw: box["sent"].append(kw) or _Response()
    )
    return box


# ─── Configuration ────────────────────────────────────────────────────────────

def test_no_ask_block_means_no_questions():
    assert ask.is_configured({}) is False
    assert ask.is_configured({"ask": {}}) is False
    assert ask.is_configured({"ask": {"questions": ["why?"]}}) is True
    assert ask.is_configured({"ask": {"questions_command": "gen"}}) is True


def test_credentials_come_from_the_telegram_notifier(monkeypatch):
    """A working setup should not need a second copy of the same two values."""
    monkeypatch.setenv("MY_TOKEN", "t")
    monkeypatch.setenv("MY_CHAT", "c")
    config = {"notifiers": [{"type": "telegram", "token_env": "MY_TOKEN",
                             "chat_id_env": "MY_CHAT"}]}
    assert ask.credentials(config) == ("t", "c")


def test_too_many_questions_are_cut(monkeypatch):
    config = ask.load({"ask": {"questions": [f"q{n}" for n in range(20)]}})
    assert len(config.questions) == 5


# ─── Opening ──────────────────────────────────────────────────────────────────

def test_opening_posts_the_questions_and_records_the_wait(tmp_path, creds, telegram):
    assert ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB) is True

    text = telegram["sent"][0]["json"]["text"]
    assert "Northwind Energy" in text
    assert "1. Which project is closest?" in text
    assert "/done" in text

    state = ask.read_state(tmp_path)
    assert state["job"]["company"] == "Northwind Energy"
    assert state["chat_id"] == CHAT
    assert state["answers"] == []


def test_only_one_question_is_outstanding_at_a_time(tmp_path, creds, telegram):
    """Two unanswered sets of questions is worse than a missed day."""
    ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB)
    assert ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB) is False
    assert len(telegram["sent"]) == 1


def test_opening_without_credentials_is_refused(tmp_path, telegram):
    assert ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB) is False
    assert ask.read_state(tmp_path) is None


def test_messages_sent_before_the_question_are_not_answers(tmp_path, creds, telegram):
    """Whatever you said to the bot yesterday is not a reply to today's question."""
    telegram["inbox"] = [_update(41, "unrelated chatter")]
    ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB)
    assert ask.read_state(tmp_path)["offset"] == 41

    outcome, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert state["answers"] == []


# ─── Collecting ───────────────────────────────────────────────────────────────

def _open(tmp_path, telegram):
    ask.open_ask(CONFIG, tmp_path, ask.load(CONFIG), JOB)
    telegram["sent"].clear()


def test_a_reply_is_kept_as_written(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "The Grundfos edge rollout, 2024.")]

    outcome, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert outcome == "waiting"
    assert state["answers"][0]["text"] == "The Grundfos edge rollout, 2024."


def test_several_messages_are_all_kept_in_order(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "first"), _update(2, "second")]
    ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert ask.answers_text(ask.read_state(tmp_path)) == "first\n\nsecond"


def test_a_message_from_another_chat_is_ignored(tmp_path, creds, telegram):
    """Anyone who learns the token can message the bot. Only one chat is ours."""
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "give me the CV", chat_id="99999")]

    outcome, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert state["answers"] == []
    assert outcome == "waiting"


def test_done_finishes_it(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "the OT/IT one"), _update(2, "/done")]

    outcome, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert outcome == "ready"
    assert ask.answers_text(state) == "the OT/IT one"


def test_done_with_nothing_said_still_finishes(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "/done")]
    outcome, _ = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert outcome == "ready"


def test_another_command_is_not_an_answer(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "/start")]
    _, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert state["answers"] == []


def test_an_update_is_never_read_twice(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    telegram["inbox"] = [_update(1, "only once")]
    ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    # A real Telegram drops acknowledged updates. A stuck offset would not.
    _, state = ask.collect(CONFIG, tmp_path, ask.load(CONFIG))
    assert len(state["answers"]) == 1


def test_nothing_outstanding_is_not_an_error(tmp_path, creds, telegram):
    assert ask.collect(CONFIG, tmp_path, ask.load(CONFIG)) == ("none", None)


# ─── When the waiting stops ───────────────────────────────────────────────────

def _state(**overrides) -> dict:
    now = datetime.now()
    state = {
        "opened": now.isoformat(),
        "deadline": (now + timedelta(hours=24)).isoformat(),
        "last_activity": now.isoformat(),
        "answers": [],
    }
    state.update(overrides)
    return state


def test_the_deadline_ends_it_even_with_no_answer(tmp_path):
    """Say nothing and it goes ahead anyway, rather than never arriving."""
    past = (datetime.now() - timedelta(minutes=1)).isoformat()
    finished, why = ask._is_finished(_state(deadline=past), ask.load(CONFIG))
    assert finished
    assert "deadline" in why


def test_quiet_minutes_end_it_once_you_have_said_something(tmp_path):
    """You will forget /done. Waiting the full 24 hours for that is no use."""
    long_ago = (datetime.now() - timedelta(minutes=45)).isoformat()
    state = _state(last_activity=long_ago, answers=[{"at": long_ago, "text": "x"}])
    finished, why = ask._is_finished(state, ask.load(CONFIG))
    assert finished
    assert "quiet" in why


def test_quiet_minutes_do_not_end_it_before_you_answer(tmp_path):
    long_ago = (datetime.now() - timedelta(minutes=45)).isoformat()
    finished, _ = ask._is_finished(_state(last_activity=long_ago), ask.load(CONFIG))
    assert finished is False


def test_a_fresh_answer_keeps_it_open(tmp_path):
    state = _state(answers=[{"at": datetime.now().isoformat(), "text": "x"}])
    finished, _ = ask._is_finished(state, ask.load(CONFIG))
    assert finished is False


def test_an_unparseable_timestamp_does_not_end_it(tmp_path):
    finished, _ = ask._is_finished(_state(deadline="not a date"), ask.load(CONFIG))
    assert finished is False


# ─── Housekeeping ─────────────────────────────────────────────────────────────

def test_cancelling_removes_the_wait(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    assert ask.is_pending(tmp_path) is True
    ask.clear_state(tmp_path)
    assert ask.is_pending(tmp_path) is False


def test_a_corrupt_state_file_is_ignored_not_fatal(tmp_path):
    ask.state_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert ask.read_state(tmp_path) is None


def test_a_second_pass_is_locked_out(tmp_path, creds, telegram):
    _open(tmp_path, telegram)
    lock = ask._take_lock(tmp_path)
    assert lock is not None
    try:
        assert ask.collect(CONFIG, tmp_path, ask.load(CONFIG)) == ("locked", None)
    finally:
        ask._release_lock(lock)
    assert ask.collect(CONFIG, tmp_path, ask.load(CONFIG))[0] == "waiting"


# ─── Questions from a command ─────────────────────────────────────────────────

def test_a_command_can_supply_the_questions():
    script = "import sys; print('What did you build?'); print('- Why leave?')"
    config = ask.load({"ask": {"questions_command": f'"{sys.executable}" -c "{script}"'}})
    assert ask.questions_for(config, JOB) == ["What did you build?", "Why leave?"]


def test_a_configured_list_wins_over_a_command():
    config = ask.load({"ask": {"questions": ["mine"], "questions_command": "whatever"}})
    assert ask.questions_for(config, JOB) == ["mine"]


def test_a_failing_questions_command_asks_nothing_rather_than_breaking():
    config = ask.load({
        "ask": {"questions_command": f'"{sys.executable}" -c "raise SystemExit(2)"'}
    })
    assert ask.questions_for(config, JOB) == []


def test_a_missing_questions_command_asks_nothing():
    config = ask.load({"ask": {"questions_command": "definitely-not-installed"}})
    assert ask.questions_for(config, JOB) == []
