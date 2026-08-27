"""
ask.py: put a few questions to you before the work is done.

A model writing a tailored CV from your profile alone produces something
plausible and slightly wrong. The missing part is the thing only you know: what
you actually did on the project the posting cares about, whether you would
really take the job, what to leave out. So the scout asks, waits, and uses the
answer.

    ask:
      questions:
        - "Which project of yours is closest to this role?"
        - "Anything to leave off the CV for this one?"
      timeout_hours: 24

## How the waiting works

There is no daemon. The daily run posts the questions and exits. A second
command collects the answers, and systemd runs it every few minutes:

    job-scout ask                one collection pass
    job-scout ask --status       what is outstanding
    job-scout ask --cancel       drop it

A long-lived process that dies quietly is exactly the failure this project
avoids everywhere else, and you answer in hours, not seconds. A timer costs
five minutes of latency and nothing else.

## What counts as an answer

Anything you send to the bot. There is no format, no numbering to match, no
reply threading. Every message is kept and handed over as written, because the
thing reading it is a model and prose is what it wants.

It stops waiting when you send /done, or after 30 quiet minutes once you have
said something, or at the deadline, whichever comes first. At the deadline it
goes ahead with whatever it has, including nothing.

## One at a time

While a question is outstanding, no new one is opened. Two unanswered sets of
questions is worse than a missed day.
"""

import json
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILENAME = "pending_ask.json"
LOCK_FILENAME = "ask.lock"

UPDATES_URL = "https://api.telegram.org/bot{token}/getUpdates"
SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

# A lock older than this belonged to a process that died. Ten minutes is longer
# than any collection pass and shorter than the gap between daily runs.
_STALE_LOCK_MINUTES = 10

# More than a handful and you will not answer any of them.
_MAX_QUESTIONS = 5

_DEFAULTS = {
    "questions": [],
    "questions_command": "",
    "timeout_hours": 24,
    "quiet_minutes": 30,
    "questions_timeout_seconds": 120,
}


@dataclass
class AskConfig:
    questions: list[str] = field(default_factory=list)
    questions_command: str = ""
    timeout_hours: int = 24
    quiet_minutes: int = 30
    questions_timeout_seconds: int = 120


def is_configured(config: dict) -> bool:
    """True when there is anything to ask."""
    block = config.get("ask")
    if not isinstance(block, dict):
        return False
    return bool(block.get("questions")) or bool(str(block.get("questions_command") or "").strip())


def load(config: dict) -> AskConfig:
    block = config.get("ask") or {}
    merged = dict(_DEFAULTS)
    merged.update(block if isinstance(block, dict) else {})
    questions = [
        str(item).strip() for item in (merged["questions"] or []) if str(item).strip()
    ]
    return AskConfig(
        questions=questions[:_MAX_QUESTIONS],
        questions_command=str(merged["questions_command"] or "").strip(),
        timeout_hours=max(1, int(merged["timeout_hours"])),
        quiet_minutes=max(1, int(merged["quiet_minutes"])),
        questions_timeout_seconds=max(1, int(merged["questions_timeout_seconds"])),
    )


# ─── Credentials ──────────────────────────────────────────────────────────────

def credentials(config: dict) -> tuple[str, str]:
    """
    The bot token and the one chat that may answer.

    Taken from the telegram notifier's entry if there is one, so a working setup
    needs no second copy of the same two values.
    """
    token_env, chat_env = "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
    for spec in config.get("notifiers") or []:
        if isinstance(spec, dict) and str(spec.get("type", "")).lower() == "telegram":
            token_env = str(spec.get("token_env") or token_env)
            chat_env = str(spec.get("chat_id_env") or chat_env)
            break
    return os.environ.get(token_env, "").strip(), os.environ.get(chat_env, "").strip()


# ─── State on disk ────────────────────────────────────────────────────────────

def state_path(data_dir: Path) -> Path:
    return Path(data_dir) / STATE_FILENAME


def read_state(data_dir: Path) -> dict | None:
    path = state_path(data_dir)
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Ignoring unreadable %s: %s", path, exc)
        return None
    return loaded if isinstance(loaded, dict) else None


def write_state(data_dir: Path, state: dict) -> bool:
    path = state_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError as exc:
        logger.error("Could not write %s: %s", path, exc)
        return False


def clear_state(data_dir: Path) -> None:
    try:
        state_path(data_dir).unlink(missing_ok=True)
    except OSError as exc:
        logger.error("Could not remove %s: %s", state_path(data_dir), exc)


def is_pending(data_dir: Path) -> bool:
    return read_state(data_dir) is not None


# ─── Opening a question ───────────────────────────────────────────────────────

def questions_for(config: AskConfig, job: dict, job_file: Path | None = None) -> list[str]:
    """
    The questions to put. A configured list wins; otherwise a command supplies
    them, one per line, and its failure is not fatal.
    """
    if config.questions:
        return config.questions
    if not config.questions_command:
        return []
    try:
        tokens = shlex.split(config.questions_command)
    except ValueError as exc:
        logger.error("ask.questions_command cannot be parsed: %s", exc)
        return []
    if not tokens:
        return []
    argv = [token.replace("{job_file}", str(job_file or "")) for token in tokens]
    try:
        completed = subprocess.run(
            argv,
            input=json.dumps(job, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=config.questions_timeout_seconds,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Could not run ask.questions_command: %s", exc)
        return []
    if completed.returncode != 0:
        logger.error(
            "ask.questions_command exited %d, so no questions are being asked. %s",
            completed.returncode, (completed.stderr or "")[-300:],
        )
        return []
    lines = [line.strip(" -*\t") for line in (completed.stdout or "").splitlines()]
    return [line for line in lines if line][:_MAX_QUESTIONS]


def message_text(job: dict, questions: list[str]) -> str:
    numbered = "\n".join(f"{n}. {q}" for n, q in enumerate(questions, start=1))
    return (
        f"Before I tailor for {job.get('title', '?')} at {job.get('company', '?')}"
        f" ({job.get('score', '?')}%):\n\n"
        f"{numbered}\n\n"
        f"Answer in your own words, in as many messages as you like. "
        f"Send /done when you have finished, or say nothing and I will go "
        f"ahead without it."
    )


def open_ask(config: dict, data_dir: Path, ask_config: AskConfig, job: dict) -> bool:
    """
    Post the questions and record that we are waiting. Never raises.

    Returns False when nothing was opened, which includes the ordinary case of
    one already being outstanding.
    """
    if is_pending(data_dir):
        logger.info("A question is already outstanding, so today's is not being asked.")
        return False

    questions = questions_for(ask_config, job)
    if not questions:
        logger.info("No questions to ask.")
        return False

    token, chat_id = credentials(config)
    if not token or not chat_id:
        logger.error(
            "Cannot ask anything: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are "
            "not both set. Remove the ask block or set them in your .env file."
        )
        return False

    offset = _latest_update_id(token)
    if not _send(token, chat_id, message_text(job, questions)):
        return False

    now = datetime.now()
    return write_state(data_dir, {
        "opened": now.isoformat(timespec="seconds"),
        "deadline": (now + timedelta(hours=ask_config.timeout_hours)).isoformat(
            timespec="seconds"
        ),
        "last_activity": now.isoformat(timespec="seconds"),
        "offset": offset,
        "chat_id": chat_id,
        "questions": questions,
        "answers": [],
        "job": job,
    })


# ─── Collecting answers ───────────────────────────────────────────────────────

def collect(config: dict, data_dir: Path, ask_config: AskConfig) -> tuple[str, dict | None]:
    """
    One collection pass.

    Returns (outcome, state). Outcome is one of:
        "none"      nothing is outstanding
        "waiting"   still waiting, state updated with anything new
        "ready"     finished. The caller should do the work now
        "locked"    another pass is running
    """
    # Checked before the lock. A timer runs this every few minutes and almost
    # every pass has nothing to do; those passes should touch nothing at all.
    if not is_pending(data_dir):
        return "none", None

    lock = _take_lock(data_dir)
    if lock is None:
        return "locked", None
    try:
        state = read_state(data_dir)
        if state is None:
            return "none", None

        token, _ = credentials(config)
        chat_id = str(state.get("chat_id") or "")
        if token and chat_id:
            _drain(token, chat_id, state)
        else:
            logger.error("Cannot collect answers without a bot token and chat id.")

        write_state(data_dir, state)

        finished, why = _is_finished(state, ask_config)
        if finished:
            logger.info("Question closed: %s", why)
            return "ready", state
        return "waiting", state
    finally:
        _release_lock(lock)


def answers_text(state: dict) -> str:
    """Everything you said, in the order you said it."""
    return "\n\n".join(str(item.get("text", "")).strip() for item in state.get("answers") or [])


def _is_finished(state: dict, config: AskConfig) -> tuple[bool, str]:
    now = datetime.now()
    if state.get("done"):
        return True, "you sent /done"
    deadline = _parse(state.get("deadline"))
    if deadline and now >= deadline:
        count = len(state.get("answers") or [])
        return True, f"the deadline passed with {count} message(s)"
    answers = state.get("answers") or []
    if answers:
        last = _parse(state.get("last_activity"))
        if last and now - last >= timedelta(minutes=config.quiet_minutes):
            return True, f"{config.quiet_minutes} quiet minutes after your last message"
    return False, ""


def _parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _drain(token: str, chat_id: str, state: dict) -> None:
    """Read new messages from the one allowed chat into the state, in place."""
    # The offset asks Telegram not to resend what we have already handled. We
    # check it again here rather than trusting the answer: a repeated update
    # would otherwise be recorded as a second, identical reply.
    seen = int(state.get("offset") or 0)
    for update in _get_updates(token, seen + 1):
        update_id = int(update.get("update_id") or 0)
        if update_id <= seen:
            continue
        state["offset"] = max(int(state.get("offset") or 0), update_id)

        message = update.get("message") or {}
        # Anyone who learns a bot token can message it. Only one chat is ours.
        if str((message.get("chat") or {}).get("id", "")) != chat_id:
            continue
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        if text.lower().startswith("/done"):
            state["done"] = True
            state["last_activity"] = datetime.now().isoformat(timespec="seconds")
            continue
        if text.startswith("/"):
            continue  # some other command, not an answer
        state.setdefault("answers", []).append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        })
        state["last_activity"] = datetime.now().isoformat(timespec="seconds")


# ─── Telegram ─────────────────────────────────────────────────────────────────

def _get_updates(token: str, offset: int) -> list[dict]:
    """New updates, or an empty list. Never raises."""
    try:
        import requests
    except ImportError:
        logger.error("Collecting answers needs the requests package.")
        return []
    try:
        response = requests.get(
            UPDATES_URL.format(token=token),
            params={"offset": offset, "timeout": 0},
            timeout=30,
        )
    except Exception as exc:
        logger.error("Could not reach Telegram: %s", exc)
        return []
    if response.status_code == 409:
        logger.error(
            "Telegram says something else is already reading this bot's "
            "messages. Only one collector may run at a time: stop the other "
            "one, or any webhook set on the bot."
        )
        return []
    if not response.ok:
        logger.error("Telegram returned %d: %s", response.status_code, response.text[:200])
        return []
    try:
        payload = response.json()
    except ValueError:
        logger.error("Telegram sent something that is not JSON.")
        return []
    result = payload.get("result")
    return result if isinstance(result, list) else []


def _latest_update_id(token: str) -> int:
    """
    Where to start reading from.

    Called when the questions go out, so anything you sent the bot before it
    asked is not mistaken for an answer.
    """
    updates = _get_updates(token, 0)
    return max((int(u.get("update_id") or 0) for u in updates), default=0)


def _send(token: str, chat_id: str, text: str) -> bool:
    try:
        import requests
    except ImportError:
        logger.error("Asking anything needs the requests package.")
        return False
    try:
        response = requests.post(
            SEND_URL.format(token=token),
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
    except Exception as exc:
        logger.error("Could not send the questions: %s", exc)
        return False
    if not response.ok:
        logger.error("Telegram returned %d: %s", response.status_code, response.text[:200])
        return False
    return True


# ─── The lock ─────────────────────────────────────────────────────────────────

def _take_lock(data_dir: Path) -> Path | None:
    """
    Stop two collection passes running at once.

    Systemd will not start a service that is still running, so this is for the
    hand-run case: you check on it while the timer fires.
    """
    path = Path(data_dir) / LOCK_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
            if age < timedelta(minutes=_STALE_LOCK_MINUTES):
                logger.info("Another collection pass is running. Skipping this one.")
                return None
            logger.warning("Removing a stale lock at %s", path)
            path.unlink(missing_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")
        return path
    except OSError as exc:
        logger.error("Could not take the lock at %s: %s", path, exc)
        return None


def _release_lock(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
