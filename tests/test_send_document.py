"""
Tests for sending a file rather than a message.

The reason this exists: a machine that runs the scout on a timer usually has a
read-only key to its own repository, so anything it produces has to be delivered
rather than committed.

No network here either. The Telegram and SMTP transports are replaced.
"""

from pathlib import Path

import pytest

from job_scout.notifiers import Dispatcher, build


@pytest.fixture
def document(tmp_path) -> Path:
    path = tmp_path / "tailored-cv.md"
    path.write_text("# Tailored CV\n\nSomething useful.\n", encoding="utf-8")
    return path


class _Response:
    def __init__(self, ok=True, status_code=200, text=""):
        self.ok = ok
        self.status_code = status_code
        self.text = text


# ─── who can carry a file at all ──────────────────────────────────────────────

def test_a_webhook_cannot_carry_a_file(tmp_path, document):
    """It posts JSON to a URL. There is nowhere for a file to go."""
    dispatcher = Dispatcher(build([{"type": "webhook"}], tmp_path))
    assert dispatcher.send_document(document) == 0


def test_a_setup_that_cannot_deliver_says_so_loudly(tmp_path, document, caplog):
    dispatcher = Dispatcher(build([{"type": "webhook"}], tmp_path))
    dispatcher.send_document(document)
    assert "not delivered" in caplog.text


# ─── the file notifier, which needs no credentials ────────────────────────────

def test_the_file_notifier_copies_it_next_to_the_digest(tmp_path, document):
    out = tmp_path / "out"
    dispatcher = Dispatcher(build([{"type": "file", "path": str(out / "matches.md")}], tmp_path))
    assert dispatcher.send_document(document) == 1
    assert (out / "tailored-cv.md").read_text(encoding="utf-8").startswith("# Tailored CV")


def test_the_original_is_left_alone(tmp_path, document):
    dispatcher = Dispatcher(build([{"type": "file"}], tmp_path))
    dispatcher.send_document(document)
    assert document.exists()


def test_a_missing_file_is_a_refusal_not_a_crash(tmp_path):
    dispatcher = Dispatcher(build([{"type": "file"}], tmp_path))
    assert dispatcher.send_document(tmp_path / "never-written.md") == 0


def test_copying_a_file_onto_itself_is_not_an_error(tmp_path):
    """The document was produced straight into the output directory."""
    document = tmp_path / "matches-dir" / "cv.md"
    document.parent.mkdir()
    document.write_text("x", encoding="utf-8")
    dispatcher = Dispatcher(
        build([{"type": "file", "path": str(document.parent / "matches.md")}], tmp_path)
    )
    assert dispatcher.send_document(document) == 1
    assert document.read_text(encoding="utf-8") == "x"


# ─── Telegram ─────────────────────────────────────────────────────────────────

def _telegram(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    return build([{"type": "telegram"}], tmp_path)[0]


def test_telegram_uploads_to_senddocument(tmp_path, document, monkeypatch):
    import requests

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(requests, "post", fake_post)
    assert _telegram(tmp_path, monkeypatch).send_document(document, "top match today") is True

    url, kwargs = calls[0]
    assert url.endswith("/sendDocument")
    assert "token-123" in url
    assert kwargs["data"]["chat_id"] == "555"
    assert kwargs["data"]["caption"] == "top match today"
    assert kwargs["files"]["document"][0] == "tailored-cv.md"


def test_telegram_truncates_an_over_long_caption(tmp_path, document, monkeypatch):
    """Telegram rejects the whole upload over 1024 characters, file included."""
    import requests

    calls = []
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append(kw) or _Response())
    _telegram(tmp_path, monkeypatch).send_document(document, "x" * 5000)
    assert len(calls[0]["data"]["caption"]) == 1024


def test_telegram_reports_a_rejection_rather_than_raising(tmp_path, document, monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "post", lambda url, **kw: _Response(ok=False, status_code=413, text="too big")
    )
    assert _telegram(tmp_path, monkeypatch).send_document(document) is False


def test_telegram_survives_a_dead_connection(tmp_path, document, monkeypatch):
    import requests

    def boom(url, **kwargs):
        raise requests.RequestException("no route to host")

    monkeypatch.setattr(requests, "post", boom)
    assert _telegram(tmp_path, monkeypatch).send_document(document) is False


def test_telegram_refuses_without_credentials(tmp_path, document):
    assert build([{"type": "telegram"}], tmp_path)[0].send_document(document) is False


def test_telegram_refuses_a_file_over_the_upload_limit(tmp_path, document, monkeypatch):
    """Checked before the upload, because failing after a 50 MB POST is rude."""
    import requests

    import job_scout.notifiers.telegram as telegram_module

    monkeypatch.setattr(telegram_module, "_MAX_DOCUMENT_BYTES", 4)
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("should not have uploaded"))
    assert _telegram(tmp_path, monkeypatch).send_document(document) is False


# ─── Email ────────────────────────────────────────────────────────────────────

class _FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        _FakeSMTP.sent.append(message)


def test_email_attaches_the_file(tmp_path, document, monkeypatch):
    import job_scout.notifiers.email_smtp as email_module

    _FakeSMTP.sent = []
    monkeypatch.setattr(email_module.smtplib, "SMTP", _FakeSMTP)
    for name, value in (
        ("SMTP_HOST", "smtp.example.test"), ("SMTP_USER", "me@example.test"),
        ("SMTP_PASSWORD", "app-password"),
    ):
        monkeypatch.setenv(name, value)

    notifier = build([{"type": "email", "to": "me@example.test"}], tmp_path)[0]
    assert notifier.send_document(document, "the week's best") is True

    message = _FakeSMTP.sent[0]
    attachments = [part for part in message.iter_attachments()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "tailored-cv.md"
    assert b"Tailored CV" in attachments[0].get_payload(decode=True)
    assert "tailored-cv.md" in message["Subject"]


def test_email_refuses_without_credentials(tmp_path, document):
    notifier = build([{"type": "email", "to": "me@example.test"}], tmp_path)[0]
    assert notifier.send_document(document) is False


# ─── the dispatcher counts channels, not attempts ─────────────────────────────

def test_the_dispatcher_reports_how_many_took_it(tmp_path, document, monkeypatch):
    import requests

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    monkeypatch.setattr(requests, "post", lambda url, **kw: _Response())

    dispatcher = Dispatcher(build(
        [{"type": "file"}, {"type": "telegram"}, {"type": "webhook"}], tmp_path
    ))
    assert dispatcher.send_document(document) == 2


def test_one_broken_channel_does_not_stop_the_others(tmp_path, document, monkeypatch):
    import requests

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")

    def boom(url, **kwargs):
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(requests, "post", boom)
    dispatcher = Dispatcher(build([{"type": "telegram"}, {"type": "file"}], tmp_path))
    assert dispatcher.send_document(document) == 1
