"""
base.py. What every notifier has in common.

A notifier takes the finished run and puts it somewhere you will see it. The
formatting helpers live here so a Telegram message, an email and a Markdown file
all describe the same job the same way.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..redact import redact


@dataclass
class RunStats:
    """The numbers behind one run, used in every digest header."""

    total_fetched: int = 0
    total_new: int = 0
    total_rejected: int = 0
    threshold: int = 65
    elapsed_seconds: float = 0.0
    source_summary: str = ""
    # What the labels mean. Separate from threshold, which decides whether you
    # hear about a posting at all. Set with `advanced.score_bands`.
    strong_at: int = 80
    possible_at: int = 65
    # Set by anything that is not a daily run, so the digest says what it is.
    # `job-scout roundup` sets them. Empty means a normal run, and the header
    # reads exactly as it always has.
    title: str = ""
    subtitle: str = ""
    # What to say when nothing matched. The default text talks about sources
    # and fetching, which is right for a run and wrong for a summary of one.
    empty_message: str = ""

    @property
    def matched(self) -> int:
        return max(0, self.total_new - self.total_rejected)


@dataclass
class Notifier:
    """
    One place results get sent.

    Subclasses implement check(), send_digest() and send_alert(). None of them
    may raise: a broken notifier reports False and the run carries on to the next
    one, because losing today's results is worse than losing one channel.
    """

    spec: dict = field(default_factory=dict)
    data_dir: Path = field(default_factory=Path)

    name = "base"

    # Whether this channel can carry a file. A webhook has nowhere to put
    # one, so the dispatcher skips it rather than counting a failure.
    can_send_documents = False

    def check(self) -> str | None:
        """None when this notifier can run, else one sentence saying what is missing."""
        return None

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        raise NotImplementedError

    def send_alert(self, body: str) -> bool:
        """Report a run-level failure. Defaults to a digest-shaped message."""
        raise NotImplementedError

    def send_document(self, path: "Path", caption: str = "") -> bool:
        """
        Put a file in front of the reader.

        Only implemented where it means something. Check can_send_documents
        before calling, or use Dispatcher.send_document, which does.
        """
        raise NotImplementedError


# ─── Shared formatting ────────────────────────────────────────────────────────

def score_label(score: int, stats: "RunStats | None" = None) -> str:
    """
    The three bands. Anything below your threshold never reaches a notifier.

    The cut-offs come from the run, so `advanced.score_bands` in config.yaml
    changes what STRONG and POSSIBLE mean.
    """
    strong = stats.strong_at if stats else 80
    possible = stats.possible_at if stats else 65
    if score >= strong:
        return "STRONG"
    if score >= possible:
        return "POSSIBLE"
    return "LONG SHOT"


def job_lines(job: dict, stats: "RunStats | None" = None) -> list[str]:
    """One job as a list of plain-text lines. Used by every notifier."""
    score = int(job.get("score", 0))
    verdict = job.get("verdict") or {}
    site = (job.get("site") or "").upper()
    location = job.get("location") or ""

    where = location
    if site:
        where = f"{location} [{site}]" if location else f"[{site}]"

    lines = [f"[{score_label(score, stats)}] {score}% {job.get('title', '?')}"]
    lines.append(f"Company:  {job.get('company', '?')}")
    if where:
        lines.append(f"Location: {where}")
    if job.get("salary"):
        lines.append(f"Salary:   {job['salary']}")

    matches = " | ".join(str(item) for item in (verdict.get("key_matches") or [])[:3])
    gaps = " | ".join(str(item) for item in (verdict.get("gaps") or [])[:2])
    reasoning = str(verdict.get("reasoning") or "").strip()

    if matches:
        lines.append(f"Matches:  {matches}")
    if gaps:
        lines.append(f"Gaps:     {gaps}")
    if reasoning:
        lines.append(f"Why:      {reasoning}")
    if job.get("url"):
        lines.append(f"Link:     {job['url']}")
    return lines


def format_job(job: dict, stats: "RunStats | None" = None) -> str:
    return "\n".join(job_lines(job, stats))


def digest_header(matched_jobs: list[dict], stats: RunStats) -> str:
    count = len(matched_jobs)
    title = stats.title or f"Job Scout, {date.today().strftime('%d %b %Y')}"
    subtitle = stats.subtitle or (
        f"{count} match{'' if count == 1 else 'es'} "
        f"| {stats.total_new} new "
        f"| {stats.total_rejected} below {stats.threshold} "
        f"| {stats.total_fetched} fetched"
    )
    return f"{title}\n{subtitle}"


def no_match_body(stats: RunStats) -> str:
    """
    What to say when nothing matched. The three cases mean different things and
    the difference matters: zero fetched usually means something is broken.
    """
    if stats.empty_message:
        return stats.empty_message
    if stats.total_fetched == 0:
        return (
            "Every source returned 0 jobs.\n"
            "That normally means a source is blocked or misconfigured rather "
            "than that the market is quiet.\n"
            f"Sources: {stats.source_summary or 'none ran'}\n"
            "Run `job-scout check` and look at scout.log in your data directory."
        )
    if stats.total_new == 0:
        return (
            f"No new postings today.\n"
            f"Fetched {stats.total_fetched}, all of them already seen.\n"
            f"Sources: {stats.source_summary}"
        )
    return (
        f"No matches at or above {stats.threshold}.\n"
        f"Scanned {stats.total_new} new | {stats.total_rejected} below threshold "
        f"| {stats.total_fetched} fetched.\n"
        f"Sources: {stats.source_summary}"
    )


def full_digest_text(matched_jobs: list[dict], stats: RunStats) -> str:
    """The whole digest as one block of text, for channels that send one message."""
    if not matched_jobs:
        return f"{digest_header(matched_jobs, stats)}\n\n{no_match_body(stats)}"
    parts = [digest_header(matched_jobs, stats)]
    parts += [format_job(job, stats) for job in matched_jobs]
    return "\n\n".join(parts)


def alert_text(body: str) -> str:
    """A run-level failure, with anything that looks like a credential removed."""
    return (
        f"Job Scout ALERT, {date.today().strftime('%d %b %Y')}\n\n{redact(body)}"
    )
