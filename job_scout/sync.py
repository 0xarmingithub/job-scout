"""
sync.py. Optionally pull the config directory before a run.

If your config directory is a git repository, a profile you push from your
laptop can be live on the machine that runs the scout the next morning, without
anyone logging in. Turn it on in config.yaml:

    sync:
      git_pull: true
      retries: 2
      retry_wait_seconds: 10

The pull is `git pull --ff-only`. It is tried again after a short wait, because
the usual failure is a network that is not up yet.

When the pull still fails, you are told only if it matters. A failed pull while
you are already up to date changes nothing and would be noise every morning. A
failed pull while the remote has commits you do not have means the run is about
to use a stale profile, and that is the quiet failure worth an alert.

One limit, stated plainly: "behind" is measured against the remote as git last
saw it (the remote-tracking branch), not against the remote itself. This module
cannot ask the remote when the network is down, which is the usual reason a pull
fails. So if the pull fails and git has never fetched the newer commits, the
copy looks up to date and no alert is sent. The alert fires when git already
knows about commits it has not applied, for example after an earlier fetch, or
when the pull fails for a reason other than the network (a diverged branch or
local changes in the way).

A run never fails because of this. Every outcome here is a result, not an
exception.
"""

import logging
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .redact import redact

logger = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 120


@dataclass
class SyncResult:
    """What the pull did. `alert` is a message to send, or empty when nobody needs telling."""

    attempted: bool = False
    ok: bool = True
    message: str = ""
    alert: str = ""


def _run(args: list[str], cwd: Path, runner: Callable) -> subprocess.CompletedProcess:
    return runner(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _failure_text(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip() or f"git exited {result.returncode}"


def commits_behind(config_dir: Path, runner: Callable = subprocess.run) -> int | None:
    """
    How many commits the upstream branch has that this checkout lacks, as of the
    last time git looked at the remote. None when that cannot be told, for example
    when there is no upstream branch.
    """
    try:
        result = _run(["rev-list", "--count", "HEAD..@{upstream}"], config_dir, runner)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def pull(
    config_dir: Path,
    retries: int = 2,
    wait_seconds: float = 10,
    runner: Callable = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> SyncResult:
    """
    `git pull --ff-only` in the config directory, tried again on failure.

    runner and sleep are parameters so a test can run the whole thing without
    git, a network or a wait.
    """
    config_dir = Path(config_dir)
    attempts = max(0, retries) + 1
    reason = ""

    for attempt in range(1, attempts + 1):
        try:
            result = _run(["pull", "--ff-only"], config_dir, runner)
        except FileNotFoundError:
            return SyncResult(
                attempted=True, ok=False,
                message="git is not installed on this machine, so sync.git_pull was skipped. "
                        "Install git, or set sync.git_pull to false.",
            )
        except subprocess.TimeoutExpired:
            reason = f"git pull timed out after {GIT_TIMEOUT_SECONDS}s"
        except (OSError, subprocess.SubprocessError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
        else:
            if result.returncode == 0:
                text = (result.stdout or "").strip() or "Already up to date"
                return SyncResult(attempted=True, ok=True, message=text)
            reason = _failure_text(result)

        logger.warning("git pull failed (attempt %d of %d): %s", attempt, attempts, redact(reason))
        if attempt < attempts:
            sleep(wait_seconds)

    behind = commits_behind(config_dir, runner)
    message = f"git pull failed after {attempts} attempt(s): {redact(reason)}"
    if behind:
        alert = (
            f"The config directory is {behind} commit(s) behind its upstream, and "
            "`git pull` failed, so this run uses a stale profile and config.\n\n"
            f"Reason: {redact(reason)}\n\n"
            f"Check: cd {config_dir} && git pull --ff-only"
        )
        return SyncResult(attempted=True, ok=False, message=message, alert=alert)
    return SyncResult(attempted=True, ok=False, message=message)


def read_block(config_dir: Path) -> dict | None:
    """
    The merged `sync:` block from config.yaml, read before the full settings load.

    The pull has to happen before the settings are loaded, or the run would use
    the old files it was meant to replace. None when sync is off, the file is
    unreadable, or the block is wrong; load_settings reports a wrong block.
    """
    import yaml

    from .config import CONFIG_FILENAME, ConfigError, merge_sync

    try:
        raw = yaml.safe_load((Path(config_dir) / CONFIG_FILENAME).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        block = merge_sync(raw)
    except ConfigError:
        return None
    return block if block["git_pull"] else None


def before_run(
    config_dir: Path,
    runner: Callable = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> SyncResult:
    """Pull if config.yaml asks for it. Returns a result with attempted=False when it does not."""
    block = read_block(config_dir)
    if block is None:
        return SyncResult()
    return pull(
        config_dir,
        retries=int(block["retries"]),
        wait_seconds=float(block["retry_wait_seconds"]),
        runner=runner,
        sleep=sleep,
    )


def report(result: SyncResult, dispatcher) -> None:
    """
    Log what the pull did and send the alert, if there is one.

    Separate from before_run because the pull happens before the settings, and
    so the notifiers, exist. A failure to send never reaches the caller.
    """
    if not result.attempted:
        return
    if result.ok:
        logger.info("Config sync: %s", result.message)
        return
    logger.warning("Config sync: %s", result.message)
    if result.alert:
        try:
            dispatcher.send_alert(result.alert)
        except Exception as exc:
            logger.error("Could not send the sync alert: %s", redact(str(exc)))
