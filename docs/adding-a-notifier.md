# Adding a notifier

About 30 lines. A notifier is a class with three methods.

Four ship: `file`, `telegram`, `email` and `webhook`. Before writing one, check
whether the `webhook` notifier with `flavor: raw` already covers your service —
it posts `{"text": "..."}` to any URL, which is what Mattermost, Google Chat,
Zulip, ntfy and most others accept.

Write your own when the service needs a different payload shape, an SDK, or
something other than HTTP.

## The contract

```python
from .base import Notifier, RunStats, alert_text, full_digest_text


class MyNotifier(Notifier):
    name = "myservice"

    def check(self) -> str | None:
        """None if this can send right now, else one sentence saying what is
        missing and how to supply it."""

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        """Send the results. Return True on success. Never raise."""

    def send_alert(self, body: str) -> bool:
        """Send a run-level failure. Return True on success. Never raise."""
```

You get two attributes: `self.spec`, your entry from `config.yaml` as a dict, and
`self.data_dir`, the run's data directory.

## The rules

**Never raise.** A notifier that throws takes down a run that already did its
work. Catch, log, return `False`. The dispatcher catches exceptions as a
backstop, but a log line beats a traceback.

**`check()` must name what is missing.** Not "not configured". The variable, and
where to get its value:

```python
def check(self) -> str | None:
    if not self.token:
        return (
            "MyService notifier needs MYSERVICE_TOKEN, which is not set. "
            "Create a token at https://myservice.example/tokens and put "
            "MYSERVICE_TOKEN=... in your .env file."
        )
    return None
```

That sentence is what `job-scout check` prints, and it is usually the only
documentation anyone reads.

**Credentials come from the environment, never from `config.yaml`.** That file
gets committed. Put a variable *name* in config if you want it configurable:

```yaml
  - type: myservice
    token_env: MYSERVICE_TOKEN
```

**Implement `send_alert`.** It is how a failed run reaches you. A notifier that
only sends good news is half a notifier.

**Use the shared formatters** in `job_scout/notifiers/base.py`, so every channel describes
a job the same way:

| Function | Gives you |
|---|---|
| `format_job(job)` | one job as plain text |
| `job_lines(job)` | the same, as a list, if you need to restructure it |
| `digest_header(jobs, stats)` | the counts line |
| `no_match_body(stats)` | what to say when nothing matched — three different cases |
| `full_digest_text(jobs, stats)` | the whole thing as one block |
| `alert_text(body)` | a failure message, with credentials already stripped |
| `score_label(score)` | STRONG / POSSIBLE / LONG SHOT |

`alert_text` runs the body through `redact()`. If you build a failure message
yourself, call `redact()` on it — error text routinely contains the token that
caused the error.

## Worked example

`job_scout/notifiers/myservice.py`:

```python
"""
myservice.py — send the digest to MyService.

    notifiers:
      - type: myservice
        channel: "#jobs"
        token_env: MYSERVICE_TOKEN

Get a token at https://myservice.example/tokens and put it in .env.
"""

import logging
import os

from .base import Notifier, RunStats, alert_text, full_digest_text

logger = logging.getLogger(__name__)

API = "https://api.myservice.example/v1/messages"
MAX_MESSAGE = 4000


class MyServiceNotifier(Notifier):
    name = "myservice"

    @property
    def token(self) -> str:
        return os.environ.get(
            str(self.spec.get("token_env") or "MYSERVICE_TOKEN"), ""
        ).strip()

    @property
    def channel(self) -> str:
        return str(self.spec.get("channel") or "").strip()

    def check(self) -> str | None:
        try:
            import requests  # noqa: F401
        except ImportError:
            return (
                "MyService notifier needs the requests package. "
                "Install it with: pip install requests"
            )
        if not self.token:
            return (
                "MyService notifier needs MYSERVICE_TOKEN, which is not set. "
                "Create a token at https://myservice.example/tokens and put "
                "MYSERVICE_TOKEN=... in your .env file."
            )
        if not self.channel:
            return "MyService notifier has no `channel:` in config.yaml."
        return None

    def _post(self, text: str) -> bool:
        problem = self.check()
        if problem:
            logger.error("%s", problem)
            return False

        import requests

        try:
            response = requests.post(
                API,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"channel": self.channel, "body": text[:MAX_MESSAGE]},
                timeout=20,
            )
            if not response.ok:
                logger.error(
                    "MyService returned %d: %s",
                    response.status_code, response.text[:200],
                )
                return False
            return True
        except requests.RequestException as exc:
            logger.error("MyService request failed: %s", exc)
            return False

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        return self._post(full_digest_text(matched_jobs, stats))

    def send_alert(self, body: str) -> bool:
        return self._post(alert_text(body))
```

## Wiring it in

One import and one line in `job_scout/notifiers/__init__.py`:

```python
from .myservice import MyServiceNotifier

REGISTRY = {
    "file": FileNotifier,
    "telegram": TelegramNotifier,
    "email": EmailNotifier,
    "webhook": WebhookNotifier,
    "myservice": MyServiceNotifier,
}
```

The name in `REGISTRY` is what people write as `type:` in `config.yaml`.

## Message limits

Most services cap a message. The file writer does not care; the others chunk on
line boundaries. Copy the `_split` helper from `telegram.py` or `webhook.py` —
splitting mid-line makes a job listing unreadable.

Current limits used here: Telegram 4,000 characters per message; Discord 1,900;
Slack 3,500 (its real limit is higher, but a wall of text is unreadable anyway).

## Testing it

No network. Test `check()` for both states, and test that sending without
credentials returns `False` rather than raising:

```python
def test_myservice_says_what_is_missing(tmp_path):
    notifier = build([{"type": "myservice", "channel": "#jobs"}], tmp_path)[0]
    assert "MYSERVICE_TOKEN" in notifier.check()


def test_myservice_is_ready_once_the_token_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("MYSERVICE_TOKEN", "test")
    notifier = build([{"type": "myservice", "channel": "#jobs"}], tmp_path)[0]
    assert notifier.check() is None


def test_myservice_refuses_to_send_rather_than_raising(tmp_path, stats):
    notifier = build([{"type": "myservice"}], tmp_path)[0]
    assert notifier.send_digest([], stats) is False
```

## Documenting it

- A docstring at the top with the config block and where to get the credential.
- A subsection in [configuration.md](configuration.md#notifiers).
- A commented entry in `job_scout/templates/config.yaml`.
- A row in `job_scout/templates/.env.example` for the variable.

Pull requests welcome.
