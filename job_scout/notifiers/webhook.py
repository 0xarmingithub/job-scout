"""
webhook.py. Post the digest to a Slack or Discord incoming webhook.

Config:

    notifiers:
      - type: webhook
        flavor: slack          # slack | discord | raw
        url_env: WEBHOOK_URL   # which environment variable holds the URL

The URL is a credential. Anyone holding it can post into your channel, so it
lives in .env, never in config.yaml:

    WEBHOOK_URL=https://hooks.slack.com/services/...

Where to get one:

    Slack    https://api.slack.com/messaging/webhooks. Create an app, turn on
             Incoming Webhooks, add one to a channel.
    Discord  Channel settings -> Integrations -> Webhooks -> New Webhook.

`flavor: raw` posts {"text": "..."} as-is, which suits Mattermost, Google Chat
and anything else that accepts a plain JSON body.
"""

import logging
import os

from .base import Notifier, RunStats, alert_text, full_digest_text, note_text

logger = logging.getLogger(__name__)

_FLAVORS = ("slack", "discord", "raw")

# Discord rejects a message body over 2000 characters; Slack's limit is far
# higher but a wall of text is unreadable anyway.
_LIMITS = {"discord": 1900, "slack": 3500, "raw": 3500}


class WebhookNotifier(Notifier):
    name = "webhook"

    @property
    def flavor(self) -> str:
        value = str(self.spec.get("flavor") or "slack").strip().lower()
        return value if value in _FLAVORS else "slack"

    @property
    def url(self) -> str:
        variable = str(self.spec.get("url_env") or "WEBHOOK_URL")
        return os.environ.get(variable, "").strip()

    def check(self) -> str | None:
        try:
            import requests  # noqa: F401
        except ImportError:
            return (
                "Webhook notifier needs the requests package, which is not "
                "installed. Install it with: pip install requests"
            )
        configured = str(self.spec.get("flavor") or "slack").strip().lower()
        if configured and configured not in _FLAVORS:
            return (
                f"Webhook notifier: flavor '{configured}' is not one of "
                f"{', '.join(_FLAVORS)}."
            )
        variable = str(self.spec.get("url_env") or "WEBHOOK_URL")
        if not self.url:
            return (
                f"Webhook notifier needs {variable}, which is not set. Create an "
                f"incoming webhook in Slack or Discord and put the URL in your "
                f".env file as {variable}=..."
            )
        return None

    # ── Sending ──────────────────────────────────────────────────────────────

    def _payload(self, text: str) -> dict:
        if self.flavor == "discord":
            return {"content": text}
        return {"text": text}

    def _post(self, text: str) -> bool:
        problem = self.check()
        if problem:
            logger.error("%s", problem)
            return False

        import requests

        limit = _LIMITS[self.flavor]
        for chunk in _split(text, limit):
            try:
                response = requests.post(self.url, json=self._payload(chunk), timeout=20)
                if not response.ok:
                    logger.error(
                        "Webhook returned %d: %s",
                        response.status_code, response.text[:200],
                    )
                    return False
            except requests.RequestException as exc:
                logger.error("Webhook request failed: %s", exc)
                return False
        return True

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        return self._post(full_digest_text(matched_jobs, stats))

    def send_alert(self, body: str) -> bool:
        return self._post(alert_text(body))

    def send_note(self, body: str) -> bool:
        return self._post(note_text(body))


def _split(text: str, limit: int) -> list[str]:
    """Break on line boundaries so no chunk exceeds the platform's limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit and current:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks
