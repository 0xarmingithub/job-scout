# Running it on your own machine

The starting point. Do this before any of the other three paths — a scheduled
run of a badly-tuned profile is just spam you have automated.

## 1. Install

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10 or newer. Check with `python --version`.

That installs the documented default: LinkedIn and Indeed as sources, Gemini as
the scorer. For a smaller install, take only what you need:

```bash
pip install -e .                # core only
pip install -e ".[gemini]"      # + the Gemini backend
pip install -e ".[jobspy]"      # + LinkedIn, Indeed, Glassdoor, ZipRecruiter
pip install -e ".[jobindex]"    # + jobindex.dk (Denmark; also needs a browser)
pip install -e ".[all]"         # everything
```

## 2. Get one API key

Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in,
create a key. Free, no card, about a minute.

```bash
echo "GOOGLE_API_KEY=paste-it-here" > .env
```

Then check:

```bash
job-scout check
```

You want `READY` next to the scoring backend and next to `file`.

## 3. Run it against the fictional profile

```bash
job-scout run
```

The first run copies the example `config.yaml` and `profile.yaml` into the repo
and tells you it did. They describe Morgan Reyes, a senior platform engineer in
Berlin. Real postings get scored against them, which is the point: you can see
whether the scoring makes sense before writing anything about yourself.

Results are in `data/matches.md`.

### What to expect, so you do not think it is broken

Two runs of the shipped config, measured back to back on a home connection:

| | Run 1 | Run 2, straight after |
|---|---|---|
| Postings fetched | 202 | 198 |
| Already seen, skipped | 0 | 156 |
| Sent to the model | 189 | 28 |
| Matches | **23** | **0** |
| Wall clock | 882 s | 351 s |

Three things there are worth understanding, because all of them surprise people.

**Day one returns a pile.** The database starts empty, so the first run scores
every posting currently listed — weeks of them at once. Twenty-plus matches is
the backlog, not a broken threshold. **Judge the threshold on day three, not day
one.**

**The model bill collapses after day one, and the clock does not.** Run 2 made 27
model calls instead of 178, but still took six minutes, because most of the time
is spent asking LinkedIn and Indeed for results, not scoring them. Four search
terms across two boards is roughly six minutes whatever happens next. Fewer
search terms is the only thing that makes a run meaningfully faster.

**Zero matches on a run is normal and is not an error.** Run 2 found 28 postings
the first run had not seen and none of them cleared 65. On a real daily
schedule you would expect nothing at all on plenty of days — that is a small
market being a small market. Chase it only if you get nothing for a week.

If scoring errors out partway through the first run, you have hit the free
tier's per-minute limit. Add `scoring_delay_seconds: 2` to `config.yaml` and run
it again — everything already scored is recorded and will not be paid for twice.

## 4. Make it yours

Edit `profile.yaml`. In rough order of how much difference each change makes:

1. **`confirmed_gaps`** — what you genuinely cannot do. This is the section that
   stops the scorer sending you jobs that merely share vocabulary with yours.
2. **`candidate`** — seniority, location, work authorisation, languages. The
   hard rejections come from here.
3. **`core_skills`** — what you would be interviewed on tomorrow.
4. **`hard_exclude_location_patterns`** — the places you will not commute to.
5. **`hard_exclude_title_patterns`** — whole categories to kill.

Then edit `config.yaml`:

1. **`searches`** — your terms and your location. Four to eight is normal.
2. **`notify_threshold`** — 65 with two sources, 70 with four.

Then look at what it does, without recording or sending anything:

```bash
job-scout run --dry-run
```

Run that as often as you like. It changes nothing, so the same postings score
again each time and you can watch the effect of an edit directly.

## 5. Add a real notification channel

Once the scores look sensible, get them off your laptop. Telegram takes about
five minutes:

1. Message [@BotFather](https://t.me/botfather) on Telegram, send `/newbot`,
   follow the prompts, copy the token.
2. Send your new bot any message. It cannot message you until you have.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and find
   `"chat":{"id":123456789`.
4. Add both to `.env`:

   ```
   TELEGRAM_BOT_TOKEN=123456:AAH...
   TELEGRAM_CHAT_ID=123456789
   ```

5. Uncomment the telegram entry in `config.yaml`:

   ```yaml
   notifiers:
     - type: file
     - type: telegram
   ```

6. `job-scout check` — you want two `READY` lines.

Email and Slack or Discord webhooks are in
[configuration.md](configuration.md#notifiers).

## 6. Keep your profile out of the repository

If you would rather not have your details sitting in a git clone:

```bash
job-scout init ~/job-search
# edit ~/job-search/config.yaml and ~/job-search/profile.yaml
# put your key in ~/job-search/.env
job-scout run --config-dir ~/job-search
```

Or set it once:

```bash
export JOB_SCOUT_CONFIG_DIR=~/job-search
job-scout run
```

## 7. Run it every day

The scout does not schedule itself. Pick one:

- A **systemd timer** on a machine that is always on —
  [setup-systemd.md](setup-systemd.md). This is the one that works long-term.
- **GitHub Actions**, if you have no machine —
  [setup-github-actions.md](setup-github-actions.md). Fewer results; read the
  warning there first.
- **Docker** — [setup-docker.md](setup-docker.md).
- A **cron line**, if you want the shortest possible answer:

  ```cron
  0 12 * * * cd /home/you/job-scout && .venv/bin/job-scout run >> data/cron.log 2>&1
  ```

  On macOS, `launchd` is more reliable than cron for anything on a laptop that
  sleeps.

## Common first-run problems

**"No matches at or above 65."** Normal on day one, especially in a small
market. Run `--dry-run` and look at what the near misses scored. If everything is
in the 40s, your profile and your search terms are describing different jobs.

**"Every source returned 0 jobs."** Almost always a source problem, not a market
problem. Start at [troubleshooting.md](troubleshooting.md).

**The same jobs arrive twice.** Your `data/` directory moved or was deleted.
`jobs.db` is what remembers.

**It found nothing new on the second run.** Working as intended. Everything from
the first run is recorded. New postings appear at the rate the market produces
them.
