"""
run.py — one complete run, start to finish.

    load config -> fetch -> dedup within the run -> dedup against history
    -> score -> record -> notify

Two properties matter more than anything else here and both are deliberate.

A source that fails does not stop the run. Job boards are flaky, rate limits move
and scrapers rot. Losing LinkedIn today should cost you LinkedIn's results, not
the whole day's.

A run that fails tells you. The worst failure this project has had in production
was a silent one: the run kept succeeding against stale configuration for a day
before anyone noticed. Anything that goes wrong at run level is sent to your
notifiers, with credentials stripped out of the message first.
"""

import logging
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import sources
from .config import Settings
from .dedup import DEFAULT_SITE_PRIORITY, JobStore, dedup_by_content
from .matcher import ScoringUnavailable, score_jobs
from .notifiers import Dispatcher, build
from .notifiers.base import RunStats
from .redact import redact

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    matched: list[dict] = field(default_factory=list)
    stats: RunStats = field(default_factory=RunStats)
    notified: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def setup_logging(data_dir: Path, verbose: bool = False) -> None:
    """Log to the console and to scout.log in the data directory."""
    data_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(data_dir / "scout.log"), encoding="utf-8"),
        ],
    )
    # Playwright and urllib3 are loud and say nothing useful at INFO.
    for noisy in ("urllib3", "playwright", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_once(settings: Settings, dry_run: bool = False, limit: int | None = None) -> RunResult:
    """
    Do one full run.

    dry_run  score and print, but write nothing to the database and send nothing.
             Use it while you are tuning notify_threshold.
    limit    stop after this many postings reach the scorer. Use it to try a new
             backend without spending a full day's budget.
    """
    started = datetime.now()
    logger.info("=== Job Scout run started %s ===", started.isoformat(timespec="seconds"))
    logger.info("Config directory: %s", settings.config_dir)
    logger.info("Data directory:   %s", settings.data_dir)

    dispatcher = Dispatcher(build(settings.notifier_specs, settings.data_dir))
    usable = dispatcher.ready()
    if not usable and not dry_run:
        # Not fatal — the run still records what it saw, and the log holds the
        # results — but say it loudly, because it means nobody will see them.
        logger.error(
            "No notifier is usable, so this run's results will only reach "
            "scout.log. Run `job-scout check` to see what each one needs."
        )

    result = RunResult()
    try:
        result = _execute(settings, dispatcher, dry_run, limit, started)
    except ScoringUnavailable as exc:
        result.error = str(exc)
        logger.error("%s", result.error)
        dispatcher.send_alert(f"The run stopped before scoring.\n\n{result.error}")
    except Exception as exc:
        result.error = redact(f"{type(exc).__name__}: {exc}")
        logger.error("Run failed: %s", result.error, exc_info=True)
        detail = redact("".join(traceback.format_exception_only(type(exc), exc)).strip())
        dispatcher.send_alert(
            "The run failed and produced no results today.\n\n"
            f"{detail}\n\n"
            f"Full traceback: {settings.data_dir / 'scout.log'}"
        )

    elapsed = (datetime.now() - started).total_seconds()
    result.stats.elapsed_seconds = elapsed
    logger.info("=== Run finished in %.1fs ===", elapsed)
    return result


def _execute(settings: Settings, dispatcher: Dispatcher, dry_run: bool,
             limit: int | None, started: datetime) -> RunResult:
    stats = RunStats(threshold=settings.notify_threshold)
    store = JobStore(settings.data_dir / "jobs.db")

    site_priority = _site_priority(settings.config)

    # 1. Fetch.
    raw_jobs, report = sources.fetch_jobs(settings.searches, settings.config)
    stats.total_fetched = len(raw_jobs)
    stats.source_summary = report.summary()

    if not raw_jobs:
        logger.warning("No jobs returned by any source.")
        return _finish(dispatcher, [], stats, dry_run, started)

    # 2. Same advert on several boards — keep the best copy.
    raw_jobs = dedup_by_content(raw_jobs, site_priority)

    # 3. Anything seen on a previous run is dropped before it costs anything.
    new_jobs = store.filter_new(raw_jobs)
    stats.total_new = len(new_jobs)
    if not new_jobs:
        logger.info("All %d fetched jobs were already seen.", len(raw_jobs))
        return _finish(dispatcher, [], stats, dry_run, started)

    if limit is not None and limit > 0 and len(new_jobs) > limit:
        logger.info("--limit %d: scoring %d of %d new jobs", limit, limit, len(new_jobs))
        new_jobs = new_jobs[:limit]
        stats.total_new = len(new_jobs)

    # 4. Score.
    scored = score_jobs(
        new_jobs,
        config=settings.config,
        profile=settings.profile,
        outcomes_path=settings.outcomes_path,
    )

    # 5. Split into what you get told about and what you do not.
    threshold = settings.notify_threshold
    matched = sorted(
        [
            job for job in scored
            if job.get("status") == "new" and int(job.get("score", 0)) >= threshold
        ],
        key=lambda job: int(job.get("score", 0)),
        reverse=True,
    )
    stats.total_rejected = len(scored) - len(matched)
    logger.info(
        "Results: %d at or above %d | %d below or rejected",
        len(matched), threshold, stats.total_rejected,
    )

    # 6. Record everything, the rejects included, so tomorrow is cheap.
    if dry_run:
        logger.info("Dry run: not recording %d jobs to the database", len(scored))
    else:
        store.mark_seen(scored)

    return _finish(dispatcher, matched, stats, dry_run, started)


def _finish(dispatcher: Dispatcher, matched: list[dict], stats: RunStats,
            dry_run: bool, started: datetime) -> RunResult:
    stats.elapsed_seconds = (datetime.now() - started).total_seconds()
    if dry_run:
        logger.info("Dry run: not sending to %d notifier(s)", len(dispatcher.notifiers))
        return RunResult(matched=matched, stats=stats, notified=0)
    sent = dispatcher.send_digest(matched, stats)
    return RunResult(matched=matched, stats=stats, notified=sent)


def _site_priority(config: dict) -> dict[str, int]:
    """
    Which board wins when the same advert comes from several. Override in
    config.yaml with `source_priority: [linkedin, careerjet, indeed]` — anything
    you leave out sorts last.
    """
    configured = config.get("source_priority")
    if not configured:
        return DEFAULT_SITE_PRIORITY
    return {str(name).strip().lower(): index for index, name in enumerate(configured)}
