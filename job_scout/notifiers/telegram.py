"""
telegram.py. Send results to a Telegram chat.

This is the reference implementation, and the one the author actually uses: a
phone notification at midday with three jobs in it is the whole point of the
project.

Setup, about five minutes:

    1. Message @BotFather on Telegram, send /newbot, and copy the token.
    2. Send your new bot any message.
    3. Open https://api.telegram.org/bot<TOKEN>/getUpdates and copy the
       "chat":{"id": ...} number.
    4. Put both in your .env file:

        TELEGRAM_BOT_TOKEN=...
        TELEGRAM_CHAT_ID=...

Config:

    notifiers:
      - type: telegram

Every message goes to TELEGRAM_CHAT_ID and nowhere else. One message per job,
so each one is its own notification and its own link.
"""

import logging
import os
import time

from .base import (
    Notifier,
    RunStats,
    alert_text,
    digest_header,
    format_job,
    no_match_body,
)

logger = logging.getLogger(__name__)

SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram allows 30 messages a second. This is far under it.
_MESSAGE_DELAY = 0.3

# Telegram rejects messages over 4096 characters.
_MAX_MESSAGE = 4000


class TelegramNotifier(Notifier):
    name = "telegram"

    @property
    def token(self) -> str:
        return os.environ.get(
            str(self.spec.get("token_env") or "TELEGRAM_BOT_TOKEN"), ""
        ).strip()

    @property
    def chat_id(self) -> str:
        return os.environ.get(
            str(self.spec.get("chat_id_env") or "TELEGRAM_CHAT_ID"), ""
        ).strip()

    def check(self) -> str | None:
        try:
            import requests  # noqa: F401
        except ImportError:
            return (
                "Telegram notifier needs the requests package, which is not "
                "installed. Install it with: pip install requests"
            )
        missing = [
            name
            for name, value in (
                ("TELEGRAM_BOT_TOKEN", self.token),
                ("TELEGRAM_CHAT_ID", self.chat_id),
            )
            if not value
        ]
        if missing:
            return (
                f"Telegram notifier needs {' and '.join(missing)}, which "
                f"{'is' if len(missing) == 1 else 'are'} not set. Create a bot "
                f"with @BotFather, then put the values in your .env file."
            )
        return None

    # ── Sending ──────────────────────────────────────────────────────────────

    def _send(self, text: str) -> bool:
        import requests

        for chunk in _split(text):
            try:
                response = requests.post(
                    SEND_URL.format(token=self.token),
                    json={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                    timeout=20,
                )
                if not response.ok:
                    logger.error(
                        "Telegram returned %d: %s",
                        response.status_code, response.text[:200],
                    )
                    return False
            except requests.RequestException as exc:
                logger.error("Telegram request failed: %s", exc)
                return False
        return True

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        problem = self.check()
        if problem:
            logger.error("%s", problem)
            return False

        if not matched_jobs:
            return self._send(
                f"{digest_header(matched_jobs, stats)}\n\n{no_match_body(stats)}"
            )

        ok = self._send(digest_header(matched_jobs, stats))
        for job in matched_jobs:
            ok = self._send(format_job(job)) and ok
            time.sleep(_MESSAGE_DELAY)
        logger.info("Telegram: sent header plus %d job messages", len(matched_jobs))
        return ok

    def send_alert(self, body: str) -> bool:
        if self.check():
            return False
        return self._send(alert_text(body))


def _split(text: str) -> list[str]:
    """Break a long message on line boundaries so Telegram accepts it."""
    if len(text) <= _MAX_MESSAGE:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > _MAX_MESSAGE and current:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks
