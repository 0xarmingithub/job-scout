"""
config.py — Find and load config.yaml, profile.yaml and .env.

Your configuration does not have to live inside this repository. That matters if
you keep a private profile in a private repo and clone this one read-only, or if
you run several profiles from one install.

Where the scout looks for config.yaml and profile.yaml, first hit wins:

  1. --config-dir PATH            (command-line flag)
  2. $JOB_SCOUT_CONFIG_DIR        (environment variable)
  3. ./                           (the directory you ran the command from,
                                   if it contains a config.yaml)
  4. the directory this package was installed from

Where run data goes (the SQLite seen-jobs database, the log, file-notifier
output), first hit wins:

  1. --data-dir PATH
  2. $JOB_SCOUT_DATA_DIR
  3. <config dir>/data
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# job_scout/config.py -> job_scout/ -> repo root
PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = PACKAGE_DIR.parent

# The shipped example config, profile and .env. `job-scout init` copies these.
TEMPLATE_DIR = PACKAGE_DIR / "templates"

CONFIG_FILENAME = "config.yaml"
PROFILE_FILENAME = "profile.yaml"
OUTCOMES_FILENAME = "outcomes.csv"
ENV_FILENAME = ".env"
ENV_EXAMPLE_FILENAME = ".env.example"


class ConfigError(RuntimeError):
    """Raised when configuration is missing or unusable. The message is shown
    to the user as-is, so it must say what to do next."""


# ─── Locating the config directory ────────────────────────────────────────────

def resolve_config_dir(cli_value: str | None = None) -> Path:
    """Return the directory holding config.yaml and profile.yaml."""
    if cli_value:
        path = Path(cli_value).expanduser().resolve()
        if not path.is_dir():
            raise ConfigError(
                f"--config-dir {path} is not a directory.\n"
                f"Create it and put {CONFIG_FILENAME} and {PROFILE_FILENAME} in it, "
                f"or run: job-scout init {path}"
            )
        return path

    env_value = os.environ.get("JOB_SCOUT_CONFIG_DIR", "").strip()
    if env_value:
        path = Path(env_value).expanduser().resolve()
        if not path.is_dir():
            raise ConfigError(
                f"JOB_SCOUT_CONFIG_DIR points at {path}, which is not a directory.\n"
                f"Create it, or unset the variable to use the built-in config."
            )
        return path

    cwd = Path.cwd().resolve()
    if (cwd / CONFIG_FILENAME).exists():
        return cwd

    return PACKAGE_ROOT


def seed_config_dir(target: Path, overwrite: bool = False) -> list[Path]:
    """
    Copy the shipped config.yaml, profile.yaml and .env.example into `target`.

    Returns the files it actually wrote. Existing files are left alone unless
    you pass overwrite=True, so running this twice can never lose your edits.
    """
    target = Path(target).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in (CONFIG_FILENAME, PROFILE_FILENAME, ENV_EXAMPLE_FILENAME):
        source = TEMPLATE_DIR / name
        if not source.exists():
            continue
        destination = target / name
        if destination.exists() and not overwrite:
            continue
        shutil.copyfile(source, destination)
        written.append(destination)
    return written


def resolve_data_dir(config_dir: Path, cli_value: str | None = None) -> Path:
    """Return the directory for the jobs database, log file and file-notifier output."""
    if cli_value:
        path = Path(cli_value).expanduser().resolve()
    else:
        env_value = os.environ.get("JOB_SCOUT_DATA_DIR", "").strip()
        path = Path(env_value).expanduser().resolve() if env_value else config_dir / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_env(config_dir: Path) -> None:
    """
    Load .env from the config directory, then from the current directory.

    Values already present in the real environment always win, so a systemd
    EnvironmentFile or a GitHub Actions secret is never overwritten by a
    stale file on disk.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a hard dependency
        return
    for candidate in (config_dir / ENV_FILENAME, Path.cwd() / ENV_FILENAME):
        if candidate.exists():
            load_dotenv(candidate, override=False)


# ─── Loading and validating ───────────────────────────────────────────────────

def _load_yaml(path: Path, label: str, hint: str) -> dict:
    if not path.exists():
        raise ConfigError(f"{label} not found at {path}.\n{hint}")
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{label} at {path} is not valid YAML:\n{exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{label} at {path} must be a mapping, got {type(data).__name__}.")
    return data


@dataclass
class Settings:
    """Everything one run needs, already located and validated."""

    config_dir: Path
    data_dir: Path
    config: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def searches(self) -> list[dict]:
        return list(self.config.get("searches") or [])

    @property
    def notify_threshold(self) -> int:
        return int(self.config.get("notify_threshold", 65))

    @property
    def scoring_model(self) -> str:
        spec = str(self.config.get("scoring_model") or "").strip()
        return spec or "gemini:gemini-2.5-flash"

    @property
    def outcomes_path(self) -> Path:
        configured = str(self.config.get("outcomes_file") or "").strip()
        if configured:
            path = Path(configured).expanduser()
            return path if path.is_absolute() else (self.config_dir / path)
        return self.config_dir / OUTCOMES_FILENAME

    @property
    def notifier_specs(self) -> list[dict]:
        raw = self.config.get("notifiers")
        if not raw:
            return []
        if not isinstance(raw, list):
            raise ConfigError("config.yaml: 'notifiers' must be a list of entries.")
        specs = []
        for entry in raw:
            if isinstance(entry, str):
                specs.append({"type": entry})
            elif isinstance(entry, dict):
                specs.append(dict(entry))
            else:
                raise ConfigError(
                    "config.yaml: each notifier must be a name or a mapping, "
                    f"got {type(entry).__name__}."
                )
        return specs


def load_settings(config_dir: str | None = None, data_dir: str | None = None) -> Settings:
    """Locate, load and validate everything. Raises ConfigError with a fix in the message."""
    cfg_dir = resolve_config_dir(config_dir)

    # A fresh clone has no config.yaml of its own. Rather than fail on the first
    # command anyone runs, copy the shipped example in and say so. This only
    # happens inside the checkout itself — an explicit --config-dir that is empty
    # is an error, because guessing what you meant there would be worse.
    if cfg_dir == PACKAGE_ROOT and not (cfg_dir / CONFIG_FILENAME).exists():
        written = seed_config_dir(cfg_dir)
        if written:
            print(
                "First run: copied the example "
                + ", ".join(path.name for path in written)
                + f" into {cfg_dir}.\nEdit profile.yaml to make this yours.\n"
            )

    load_env(cfg_dir)

    config = _load_yaml(
        cfg_dir / CONFIG_FILENAME,
        CONFIG_FILENAME,
        f"Copy the shipped config into place with: job-scout init {cfg_dir}",
    )
    profile = _load_yaml(
        cfg_dir / PROFILE_FILENAME,
        PROFILE_FILENAME,
        f"Copy the shipped profile into place with: job-scout init {cfg_dir}",
    )

    settings = Settings(
        config_dir=cfg_dir,
        data_dir=resolve_data_dir(cfg_dir, data_dir),
        config=config,
        profile=profile,
    )
    validate(settings)
    return settings


def validate(settings: Settings) -> None:
    """Fail early, with a message that says exactly what to change."""
    if not settings.searches:
        raise ConfigError(
            "config.yaml has no searches. Add at least one:\n\n"
            "searches:\n"
            "  - term: \"platform engineer\"\n"
            "    sites: [linkedin, indeed]\n"
            "    location: \"Berlin\"\n"
        )
    for index, search in enumerate(settings.searches):
        if not isinstance(search, dict):
            raise ConfigError(f"config.yaml: searches[{index}] must be a mapping.")
        if not str(search.get("term") or "").strip():
            raise ConfigError(f"config.yaml: searches[{index}] has no 'term'.")

    if not 0 <= settings.notify_threshold <= 100:
        raise ConfigError(
            f"config.yaml: notify_threshold is {settings.notify_threshold}, "
            f"must be between 0 and 100."
        )

    if not settings.profile.get("candidate"):
        raise ConfigError(
            "profile.yaml has no 'candidate' block. The scorer needs at least a "
            "name, a seniority and a location to judge a posting against."
        )

    if not settings.notifier_specs:
        raise ConfigError(
            "config.yaml has no notifiers, so a run would score jobs and then "
            "throw the results away. Add at least one. The one that needs no "
            "credentials is:\n\n"
            "notifiers:\n"
            "  - type: file\n"
        )
