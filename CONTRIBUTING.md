# Contributing

The two most useful contributions are a **job source for a country this does not
cover** and a **notifier for a service it does not support**. Both are small,
self-contained, and each one makes the project useful to a set of people it was
useless to before.

## Getting set up

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev,all]"
pytest -q
```

Python 3.10 or newer. The suite reaches no network and reads no API keys, so it
runs anywhere and takes a few seconds.

## Adding a job source

The one most worth doing. Most countries have a national board that carries
postings LinkedIn never sees — jobindex.dk in Denmark, StepStone in Germany, Seek
in Australia.

**Check two cheaper options first.** Careerjet may already aggregate the board,
in which case a locale setting is all anyone needs. Or there may be an
[Apify Actor](https://apify.com/store), in which case it is a config block and no
code.

If neither covers it, [docs/adding-a-job-source.md](docs/adding-a-job-source.md)
has the contract and a complete worked example. It is about 40 lines.

In the pull request, say which country the board covers and whether it needs an
account.

## Adding a notifier

[docs/adding-a-notifier.md](docs/adding-a-notifier.md). About 30 lines.

Check first whether `webhook` with `flavor: raw` already works for your service —
it posts `{"text": "..."}` to any URL, which covers Mattermost, Google Chat,
Zulip, ntfy and most others.

## Other things worth doing

- **Benchmark numbers.** [docs/benchmarks.md](docs/benchmarks.md) rests on a
  sample of 20, one profile, one country. Numbers from a different profile or
  market would be genuinely useful. State your sample size.
- **Fixing a broken scraper.** Boards redesign. If JobIndex stops returning
  anything, the parser needs updating — save a real page as a fixture and use it
  in the test.
- **Documentation.** If you followed a guide and had to guess at a step, that is
  a bug. Say where.

## The rules

Five of them, and they are all one idea: a run must survive things going wrong.

1. **Optional means optional.** A run finishes with none of the optional pieces
   installed. Extend `tests/test_run.py::test_a_run_finishes_with_none_of_the_optional_pieces`
   if you add something optional.
2. **A missing dependency gets a sentence, not a traceback.** Name the package or
   the variable, and where to get it.
3. **One failure never takes down a run.** A broken source costs that source. A
   broken notifier costs that channel.
4. **Credentials never appear in a message.** Everything sent goes through
   `redact()`. New credential shape means a new pattern and a new test.
5. **Nothing personal ships.** The example profile is fictional. No real names,
   employers, IP addresses, keys or personal domains anywhere — comments and
   example values included.

The full version, with the reasoning, is in [AGENTS.md](AGENTS.md). It is written
for AI coding tools but it is the same set of rules.

## Style

- Plain language in anything a user reads: log lines, error messages, docs. Say
  what happened and what to do about it. Keep exact terms exact — variable names,
  paths, commands, error codes and numbers are never softened.
- Comments explain **why**, not what. If a line looks wrong but is right, say why
  it is right.
- `ruff check job_scout tests` before you push. Line length 100.
- Type hints on public functions. No strict typing requirement beyond that.

## Tests

Required for anything with logic in it.

- **No network.** Ever. Stub it, or test the pure functions.
- **No API keys.** `tests/conftest.py` scrubs the environment, so a developer
  with `GOOGLE_API_KEY` set gets the same result as CI.
- Test the failure path. For a source, the most valuable test is "what happens
  when the key is missing" — not the happy path.
- For a scraper, save one real page as a fixture. See
  `test_jobindex_parses_a_card_from_saved_html`.

```bash
pytest -q
pytest -q tests/test_sources.py -k apify     # one file, one topic
```

## Pull requests

1. Branch from `main`.
2. `pytest -q` and `ruff check job_scout tests` both clean.
3. Update the docs the change touches — the configuration reference and the
   shipped template in `job_scout/templates/` are the two people miss.
4. In the description: what it does, why, and how you tested it. If you added a
   source, say whether you ran it against the live board.

CI runs the suite on Python 3.10 through 3.13.

## Reporting a bug

[github.com/0xarmingithub/job-scout/issues](https://github.com/0xarmingithub/job-scout/issues)

Include the output of `job-scout check`, the relevant part of `data/scout.log`,
your `config.yaml` minus anything private, and your Python version and operating
system.

Read what you paste. The scout redacts credentials from anything it sends, but
check anyway.

## Security

If you find something that leaks a credential or lets someone else's config
execute code, do not open a public issue. Use GitHub's private vulnerability
reporting on the repository.

## Licence

MIT. By contributing you agree your work is licensed the same way.
