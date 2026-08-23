"""
Shared test fixtures.

Two rules hold for this whole suite:

  1. No network. Nothing here contacts a job board, a model, or Apify.
  2. No keys. Every test runs with the environment scrubbed, so a developer who
     happens to have GOOGLE_API_KEY set locally gets the same results as CI.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Everything the scout reads from the environment. Cleared before every test.
_SCOUT_ENV_VARS = (
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "APIFY_API_TOKEN",
    "CAREERJET_API_KEY",
    "CAREERJET_REFERER",
    "CAREERJET_USER_IP",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "WEBHOOK_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_SECURITY",
    "LLM_CLI_SSH_HOST",
    "LLM_CLI_SSH_KEY",
    "LLM_CLI_ENV_FILE",
    "LLM_CLI_TIMEOUT",
    "LLM_CLI_CONCURRENCY",
    "LLM_CLI_FORCE_SSH",
    "JOB_SCOUT_CONFIG_DIR",
    "JOB_SCOUT_DATA_DIR",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Run every test as if nothing is configured."""
    for name in _SCOUT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """Stop python-dotenv from reading a developer's real .env into a test."""
    monkeypatch.setattr("job_scout.config.load_env", lambda config_dir: None)


@pytest.fixture
def no_clis(monkeypatch):
    """Pretend no CLI backend is installed, whatever the developer has."""
    monkeypatch.setattr("job_scout.llm.backend.shutil.which", lambda name: None)


@pytest.fixture
def sample_jobs() -> list[dict]:
    """Three postings: two are the same advert from different boards."""
    return [
        {
            "title": "Solution Architect",
            "company": "Northwind Energy",
            "location": "Berlin, Germany",
            "description": "short",
            "url": "https://linkedin.example/1",
            "site": "linkedin",
            "date_posted": "2026-08-20",
            "salary": "",
            "job_type": "",
            "is_remote": False,
            "search_term": "solution architect",
        },
        {
            "title": "Solution Architect",
            "company": "Northwind Energy",
            "location": "Berlin, Germany",
            "description": "a much longer description with kubernetes and terraform in it",
            "url": "https://careerjet.example/1",
            "site": "careerjet",
            "date_posted": "2026-08-20",
            "salary": "",
            "job_type": "",
            "is_remote": False,
            "search_term": "solution architect",
        },
        {
            "title": "Platform Engineer",
            "company": "Halden Data",
            "location": "Berlin, Germany",
            "description": "kubernetes, terraform, aws",
            "url": "https://linkedin.example/2",
            "site": "linkedin",
            "date_posted": "2026-08-21",
            "salary": "",
            "job_type": "",
            "is_remote": False,
            "search_term": "platform engineer",
        },
    ]


@pytest.fixture
def config_dir(tmp_path) -> Path:
    """A throwaway config directory seeded from the shipped templates."""
    from job_scout.config import seed_config_dir

    target = tmp_path / "config"
    seed_config_dir(target)
    return target
