# AGENTS.md

Instructions for AI coding tools working in this repository.

**This file is not Claude-specific.** It follows the
[AGENTS.md](https://agents.md) convention and is read by Claude Code, Cursor,
Aider, Codex, Copilot's workspace instructions, and anything else that looks for
it. `.claude/skills/` holds Claude Code skills, which are a convenience on top of
this file, not a replacement for it. Every workflow they cover is also written
down as manual steps.

---

## What this project is

A job-hunting agent. It searches job boards daily, scores every posting from 0 to
100 against a profile written in YAML, and sends the good ones to a notifier.

The idea that matters: **behaviour lives in `profile.yaml`, not in code.** If a
change would be better expressed as a new profile field than as a new branch in
`matcher.py`, make it a profile field.

---

## Rules

### 1. Optional means optional

Every source, notifier and backend except one of each must be skippable. A run
must finish cleanly with no Playwright, no Careerjet key, no Apify token and no
`outcomes.csv`.

This is enforced by `tests/test_run.py::test_a_run_finishes_with_none_of_the_optional_pieces`.
If you add anything optional, extend that test.

### 2. A missing dependency gets a sentence, not a traceback

Name the thing and how to get it:

```python
# Wrong
raise ImportError("playwright not found")

# Right
logger.warning(
    "JobIndex skipped: playwright is not installed. Install it with: "
    "pip install playwright && playwright install chromium --with-deps "
    "— or remove 'jobindex' from your sites list."
)
return []
```

For backends, that sentence belongs in `preflight()` in
`job_scout/llm/backend.py`, so `job-scout check` can show it before a run starts.

### 3. One failure never takes down a run

A source that breaks costs you that source. A notifier that breaks costs you that
channel. A posting that fails to score costs you that posting. Catch, log, carry
on.

The one exception: a scoring backend that is not set up at all stops the run
before it starts, because a run that scores nothing is not worth doing.

### 4. A failed run must reach the user

Anything that goes wrong at run level goes to the notifiers via
`Dispatcher.send_alert()`. A run that dies quietly in a log file is the failure
that costs someone a week of stale results. This is not optional politeness; it
is the reason the alerting path exists.

### 5. Credentials never leave the machine in a message

Everything a notifier sends passes through `redact()` in `job_scout/redact.py`.
Error text routinely contains the token that caused the error. If you add a new
credential shape, add a pattern there and a test in `tests/test_redact.py`.

### 6. Python 3.10 is the floor

Enforced by `tests/test_compat.py`, which parses every source file with the 3.10
grammar. No `match` statements are needed, no `tomllib`, no `datetime.UTC`, no
`StrEnum`, no `itertools.batched`.

### 7. Tests run with no network and no API keys

`tests/conftest.py` scrubs every environment variable the scout reads and blocks
`.env` loading, so a developer with `GOOGLE_API_KEY` set gets the same results as
CI. Never write a test that contacts a job board or a model.

### 8. Nothing personal ships

The example profile is a fictional person, Morgan Reyes. No real names,
employers, addresses, IP addresses, keys or personal domains anywhere in the
repository, including in comments and example values. `tests/test_compat.py`
checks the shipped profile for this.

### 9. Plain language in user-facing text

Log lines, error messages, docstrings and documentation are read by someone
trying to get something working. Say what happened and what to do. Keep exact
terms exact — variable names, file paths, commands, error codes and numbers are
never softened.

### 10. Two files hold behaviour, and neither is code

`job_scout/templates/config.yaml` and `job_scout/templates/profile.yaml` are the
shipped defaults. They are copied to the repo root on first run and the copies
are gitignored, so a user's edits survive `git pull` and never get pushed. Change
the templates, not the copies.

---

## Layout

```
job_scout/
  cli.py            the `job-scout` command
  run.py            one run, start to finish; the alerting lives here
  config.py         finding and validating config.yaml / profile.yaml
  matcher.py        the three scoring tiers and the prompt
  dedup.py          the seen-jobs store and cross-source deduplication
  track_record.py   the optional outcomes.csv
  redact.py         stripping credentials out of text
  llm/backend.py    all five model backends, and preflight()
  sources/          one module per job board
  notifiers/        one module per output channel
  templates/        the shipped config.yaml, profile.yaml and .env.example
tests/              no network, no keys
docs/               one file per topic
examples/denmark/   a complete worked setup
deploy/             systemd units and an install script
```

The job dictionary that flows through the whole pipeline is documented at the top
of `job_scout/sources/__init__.py`. Do not change its keys without updating
every source, `dedup.py` and `job_scout/notifiers/base.py`.

---

## Common tasks

### Add a job source

Read [docs/adding-a-job-source.md](docs/adding-a-job-source.md). One function
returning a list of job dicts, one entry in `STANDALONE_SITES`, one loader, one
line in `DEFAULT_SITE_PRIORITY`. Import it lazily inside the loader so people who
do not use it never install its dependencies.

### Add a notifier

Read [docs/adding-a-notifier.md](docs/adding-a-notifier.md). A `Notifier`
subclass with `check`, `send_digest` and `send_alert`, plus one line in
`REGISTRY`.

### Change the scoring prompt

`build_prompt_template()` in `job_scout/matcher.py`. If you add a field to the
JSON the model returns, handle it in `score_jobs()`, document it in
[docs/scoring.md](docs/scoring.md), and add a case to
`tests/test_matcher.py`. If a change can be a profile field instead, make it one.

### Add a config option

1. Read it in `Settings` or where it is used.
2. Validate it in `config.validate()` if a wrong value should stop a run.
3. Add it to the shipped template with a comment saying what it does.
4. Add a row to [docs/configuration.md](docs/configuration.md).
5. Test the default and at least one non-default value.

---

## Before you say you are done

```bash
pytest -q                    # all green, no network
ruff check job_scout tests
job-scout check              # every backend and notifier reports honestly
job-scout run --dry-run      # a real run that records and sends nothing
```

Then, for anything user-facing, follow your own instructions literally in a clean
directory. Every step you had to guess is a documentation bug.

---

## Things not to do

- **Do not add a required dependency** for a source or backend most people will
  not use. Use `[project.optional-dependencies]`.
- **Do not hardcode a country, language or currency** in `job_scout/`. Denmark is
  an example under `examples/denmark/`, not a default.
- **Do not add a default Apify Actor.** Actors bill individually and none should
  start charging someone because a name appeared in a list.
- **Do not remove the terms-of-service disclaimer** from the README or from
  `job_scout/sources/jobspy_source.py`. LinkedIn and Indeed prohibit automated scraping;
  people should know that before they turn them on.
- **Do not make the scout write to its config directory** during a run. Config in,
  data out, and they can be on different filesystems.
- **Do not commit `config.yaml`, `profile.yaml`, `.env`, `data/` or
  `outcomes.csv`** from the repo root. They are gitignored for a reason.
