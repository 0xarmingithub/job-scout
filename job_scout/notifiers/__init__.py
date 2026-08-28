"""
notifiers. Where results go.

Four are built in. You need at least one; the file writer needs no credentials
and is the right one for a first run.

    file      write a Markdown, text, CSV or JSON file
    telegram  a message per job in a Telegram chat
    email     one email over SMTP
    webhook   a Slack, Discord or plain JSON webhook

Add your own by writing a subclass of Notifier and adding one line to REGISTRY.
See docs/adding-a-notifier.md.

Nothing here raises. A notifier that cannot send says so in the log and returns
False, and the dispatcher moves on to the next one. Losing today's results
because one channel is down is not a trade worth making.
"""

import logging
from pathlib import Path

from .base import Notifier, RunStats
from .email_smtp import EmailNotifier
from .file_writer import FileNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier

logger = logging.getLogger(__name__)

REGISTRY: dict[str, type[Notifier]] = {
    "file": FileNotifier,
    "telegram": TelegramNotifier,
    "email": EmailNotifier,
    "webhook": WebhookNotifier,
}

__all__ = [
    "REGISTRY",
    "Dispatcher",
    "EmailNotifier",
    "FileNotifier",
    "Notifier",
    "RunStats",
    "TelegramNotifier",
    "WebhookNotifier",
    "build",
]


class UnknownNotifier(RuntimeError):
    """A notifier type in config.yaml that nothing implements."""


def build(specs: list[dict], data_dir: Path) -> list[Notifier]:
    """Turn the `notifiers:` list from config.yaml into notifier objects."""
    built: list[Notifier] = []
    for spec in specs:
        kind = str(spec.get("type") or "").strip().lower()
        if kind not in REGISTRY:
            raise UnknownNotifier(
                f"config.yaml lists a notifier of type '{kind or '(missing)'}', "
                f"which does not exist. Pick one of: {', '.join(sorted(REGISTRY))}."
            )
        built.append(REGISTRY[kind](spec=dict(spec), data_dir=Path(data_dir)))
    return built


class Dispatcher:
    """Sends to every configured notifier and swallows their failures."""

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def check(self) -> list[tuple[str, str | None]]:
        """[(name, None-if-ready-else-message), ...] for `job-scout check`."""
        results = []
        for notifier in self.notifiers:
            try:
                results.append((notifier.name, notifier.check()))
            except Exception as exc:  # a broken check is still a failed check
                results.append((notifier.name, f"check failed: {exc}"))
        return results

    def ready(self) -> list[Notifier]:
        ready = []
        for notifier in self.notifiers:
            try:
                problem = notifier.check()
            except Exception as exc:
                problem = str(exc)
            if problem:
                logger.warning("Notifier '%s' is not usable: %s", notifier.name, problem)
            else:
                ready.append(notifier)
        return ready

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> int:
        """Send to every notifier. Returns how many succeeded."""
        sent = 0
        for notifier in self.notifiers:
            try:
                if notifier.send_digest(matched_jobs, stats):
                    sent += 1
            except Exception as exc:
                logger.error("Notifier '%s' failed: %s", notifier.name, exc, exc_info=True)
        return sent

    def send_document(self, path: Path, caption: str = "") -> int:
        """
        Put a file in front of the reader. Returns how many channels took it.

        Channels that cannot carry a file are skipped rather than counted as
        failures. A webhook has nowhere to put one, and saying so once is
        more useful than four failures in the log.
        """
        able = [n for n in self.notifiers if n.can_send_documents]
        if not able:
            logger.error(
                "No configured notifier can carry a file, so %s was produced and "
                "not delivered. A file, telegram or email notifier can.",
                path,
            )
            return 0
        sent = 0
        for notifier in able:
            try:
                if notifier.send_document(Path(path), caption):
                    sent += 1
            except Exception as exc:
                logger.error(
                    "Notifier %s could not send %s: %s", notifier.name, path, exc
                )
        return sent

    def send_alert(self, body: str) -> int:
        """
        Report a run-level failure everywhere. A run that dies quietly in a log
        file is the failure mode that costs you a week of stale results, so this
        is deliberately noisy.
        """
        sent = 0
        for notifier in self.notifiers:
            try:
                if notifier.send_alert(body):
                    sent += 1
            except Exception as exc:
                logger.error("Notifier '%s' could not alert: %s", notifier.name, exc)
        return sent

    def send_note(self, body: str) -> int:
        """
        Send a plain message everywhere. Returns how many channels took it.

        The same fan-out as send_alert without the word ALERT. Anything sent on
        a schedule belongs here: a weekly reminder filed under alerts teaches
        the reader to skip alerts, and the one after that is the run that
        actually died.
        """
        sent = 0
        for notifier in self.notifiers:
            try:
                if notifier.send_note(body):
                    sent += 1
            except Exception as exc:
                logger.error("Notifier '%s' could not send a note: %s", notifier.name, exc)
        return sent
