"""
file_writer.py. Write results to a file. Needs no credentials at all.

This is the zero-setup default, and the one to use for your first run: you get
to see whether the scoring is any good before you go and register a bot.

    notifiers:
      - type: file
        path: matches.md      # relative to your data directory
        format: markdown      # markdown | text | csv | json
        append: true          # keep every run's results, oldest first

CSV is the one to pick if you want to sort and filter in a spreadsheet. JSON
writes one object per line, which is what you want if something downstream is
going to read it.
"""

import csv
import io
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .base import (
    Notifier, RunStats, alert_text, digest_header, format_job, no_match_body,
    note_text,
)

logger = logging.getLogger(__name__)

_FORMATS = ("markdown", "text", "csv", "json")

_CSV_COLUMNS = (
    "run_at", "score", "title", "company", "location", "site",
    "salary", "url", "key_matches", "gaps", "reasoning", "search_term",
)


class FileNotifier(Notifier):
    name = "file"
    can_send_documents = True

    @property
    def path(self) -> Path:
        configured = str(self.spec.get("path") or "").strip()
        if not configured:
            configured = f"matches.{self._extension}"
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (self.data_dir / path)

    @property
    def format(self) -> str:
        value = str(self.spec.get("format") or "markdown").strip().lower()
        return value if value in _FORMATS else "markdown"

    @property
    def _extension(self) -> str:
        return {"markdown": "md", "text": "txt", "csv": "csv", "json": "jsonl"}[self.format]

    @property
    def append(self) -> bool:
        return bool(self.spec.get("append", True))

    def check(self) -> str | None:
        configured = str(self.spec.get("format") or "markdown").strip().lower()
        if configured and configured not in _FORMATS:
            return (
                f"File notifier: format '{configured}' is not one of "
                f"{', '.join(_FORMATS)}."
            )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"File notifier cannot create {self.path.parent}: {exc}"
        return None

    # ── Writing ──────────────────────────────────────────────────────────────

    def send_digest(self, matched_jobs: list[dict], stats: RunStats) -> bool:
        try:
            if self.format == "csv":
                text = self._as_csv(matched_jobs)
            elif self.format == "json":
                text = self._as_json(matched_jobs)
            elif self.format == "text":
                text = self._as_text(matched_jobs, stats)
            else:
                text = self._as_markdown(matched_jobs, stats)
            self._write(text)
            logger.info("Wrote %d match(es) to %s", len(matched_jobs), self.path)
            return True
        except OSError as exc:
            logger.error("File notifier could not write %s: %s", self.path, exc)
            return False

    def send_document(self, path: Path, caption: str = "") -> bool:
        """
        Copy the file next to the digest.

        Here so a setup with no credentials at all still ends up with the
        document on disk. It is a copy, not a move: whoever produced the
        file owns it.
        """
        source = Path(path)
        if not source.is_file():
            logger.error("Cannot copy %s: there is no such file", source)
            return False
        destination = self.path.parent / source.name
        if destination.resolve() == source.resolve():
            logger.info("%s is already where the file notifier writes", source.name)
            return True
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        except OSError as exc:
            logger.error("Could not copy %s to %s: %s", source, destination, exc)
            return False
        logger.info("Copied %s to %s", source.name, destination)
        return True

    def send_alert(self, body: str) -> bool:
        try:
            self._write(f"{alert_text(body)}\n")
            return True
        except OSError as exc:
            logger.error("File notifier could not write alert to %s: %s", self.path, exc)
            return False

    def send_note(self, body: str) -> bool:
        try:
            self._write(f"{note_text(body)}\n")
            return True
        except OSError as exc:
            logger.error("File notifier could not write note to %s: %s", self.path, exc)
            return False

    def _write(self, text: str) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self.append and path.exists() else "w"
        with open(path, mode, encoding="utf-8", newline="") as handle:
            handle.write(text)

    # ── Formats ──────────────────────────────────────────────────────────────

    def _as_markdown(self, jobs: list[dict], stats: RunStats) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        out = [f"## {stamp}: {len(jobs)} match(es)", ""]
        out.append(f"- Fetched {stats.total_fetched}, {stats.total_new} new, "
                   f"{stats.total_rejected} below {stats.threshold}")
        if stats.source_summary:
            out.append(f"- Sources: {stats.source_summary}")
        out.append("")
        if not jobs:
            out.append(no_match_body(stats))
            out.append("")
            return "\n".join(out) + "\n"
        for job in jobs:
            verdict = job.get("verdict") or {}
            out.append(f"### {job.get('score', 0)}% {job.get('title', '?')}")
            out.append(f"**{job.get('company', '?')}**. {job.get('location', '')} "
                       f"({job.get('site', '')})")
            if job.get("salary"):
                out.append(f"Salary: {job['salary']}")
            if verdict.get("key_matches"):
                out.append(f"Matches: {', '.join(str(m) for m in verdict['key_matches'][:3])}")
            if verdict.get("gaps"):
                out.append(f"Gaps: {', '.join(str(g) for g in verdict['gaps'][:2])}")
            if verdict.get("reasoning"):
                out.append(f"Why: {verdict['reasoning']}")
            if job.get("url"):
                out.append(f"<{job['url']}>")
            out.append("")
        return "\n".join(out) + "\n"

    def _as_text(self, jobs: list[dict], stats: RunStats) -> str:
        parts = [digest_header(jobs, stats)]
        parts += [format_job(job, stats) for job in jobs] or [no_match_body(stats)]
        return "\n\n".join(parts) + "\n\n"

    def _as_csv(self, jobs: list[dict]) -> str:
        stamp = datetime.now().isoformat(timespec="seconds")
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        if not (self.append and self.path.exists() and self.path.stat().st_size > 0):
            writer.writerow(_CSV_COLUMNS)
        for job in jobs:
            verdict = job.get("verdict") or {}
            writer.writerow([
                stamp,
                job.get("score", 0),
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("site", ""),
                job.get("salary", ""),
                job.get("url", ""),
                "; ".join(str(m) for m in (verdict.get("key_matches") or [])),
                "; ".join(str(g) for g in (verdict.get("gaps") or [])),
                verdict.get("reasoning", ""),
                job.get("search_term", ""),
            ])
        return buffer.getvalue()

    def _as_json(self, jobs: list[dict]) -> str:
        stamp = datetime.now().isoformat(timespec="seconds")
        lines = []
        for job in jobs:
            record = {key: value for key, value in job.items() if key != "description"}
            record["run_at"] = stamp
            lines.append(json.dumps(record, ensure_ascii=False, default=str))
        return "\n".join(lines) + ("\n" if lines else "")
