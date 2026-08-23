"""
email_smtp.py. Send the digest as one email over SMTP.

Config:

    notifiers:
      - type: email
        to: you@example.com          # or a list
        from: scout@example.com      # defaults to SMTP_USER
        subject: "Job Scout"         # the date is appended

Credentials come from the environment, never from config.yaml:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=an-app-password
    SMTP_SECURITY=starttls           # starttls | ssl | none

On Gmail this needs an App Password, not your normal password: turn on 2-step
verification, then create one at https://myaccount.google.com/apppasswords.

Port 587 means STARTTLS and port 465 means implicit SSL. If you leave
SMTP_SECURITY unset, the port decides.
"""

import logging
import os
import smtplib
from datetime import date
from email.message import EmailMessage

from .base import Notifier, RunStats, alert_text, full_digest_text

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    name = "email"

    @property
    def host(self) -> str:
        return os.environ.get("SMTP_HOST", "").strip()

    @property
    def port(self) -> int:
        raw = os.environ.get("SMTP_PORT", "").strip()
        try:
            return int(raw) if raw else 587
        except ValueError:
            return 587

    @property
    def user(self) -> str:
        return os.environ.get("SMTP_USER", "").strip()

    @property
    def password(self) -> str:
        return os.environ.get("SMTP_PASSWORD", "").strip()

    @property
    def security(self) -> str:
        configured = os.environ.get("SMTP_SECURITY", "").strip().lower()
        if configured in ("starttls", "ssl", "none"):
            return configured
        return "ssl" if self.port == 465 else "starttls"

    @property
    def recipients(self) -> list[str]:
        raw = self.spec.get("to")
        if isinstance(raw, str):
            return [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []

    @property
    def sender(self) -> str:
        return str(self.spec.get("from") or self.user or "").strip()

    def check(self) -> str | None:
        if not self.recipients:
            return (
                "Email notifier has no recipient. Add `to: you@example.com` "
                "under the email entry in config.yaml."
            )
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", self.host),
                ("SMTP_USER", self.user),
                ("SMTP_PASSWORD", self.password),
            )
            if not value
        ]
        if missing:
            return (
                f"Email notifier needs {', '.join(missing)} in your .env file. "
                f"On Gmail, SMTP_PASSWORD must be an App Password, not your "
                f"account password."
            )
        if not self.sender:
            return "Email notifier has no sender. Set SMTP_USER or add `from:` to config.yaml."
        return None

    # ── Sending ──────────────────────────────────────────────────────────────

    def _send(self, subject: str, body: str) -> bool:
        problem = self.check()
        if problem:
            logger.error("%s", problem)
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(body)

        try:
            if self.security == "ssl":
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=30)
            with server:
                if self.security == "starttls":
                    server.starttls()
                server.login(self.user, self.password)
                server.send_message(message)
            logger.info("Email sent to %s", ", ".join(self.recipients))
            return True
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Email send failed via %s:%d. %s", self.host, self.port, exc)
            return False

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        prefix = str(self.spec.get("subject") or "Job Scout")
        count = len(matched_jobs)
        subject = (
            f"{prefix}: {count} match{'' if count == 1 else 'es'} "
            f". {date.today().strftime('%d %b %Y')}"
        )
        return self._send(subject, full_digest_text(matched_jobs, stats))

    def send_alert(self, body: str) -> bool:
        prefix = str(self.spec.get("subject") or "Job Scout")
        return self._send(f"{prefix} ALERT, {date.today().strftime('%d %b %Y')}",
                          alert_text(body))
