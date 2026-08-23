# Configuration reference

Three files, and only one of them holds anything secret.

| File | Holds | Commit it? |
|---|---|---|
| `config.yaml` | Searches, threshold, which model, where results go | Yes, if it is yours to commit |
| `profile.yaml` | Who you are and what counts as a match | Your call — it is personal |
| `.env` | Every API key and token | **Never** |

The shipped copies live in `job_scout/templates/` and are copied to the repo
root the first time you run anything. Your edits to the copies are gitignored,
so a `git pull` cannot overwrite them and you cannot accidentally push them.

## Where the scout looks

`config.yaml` and `profile.yaml`, first hit wins:

1. `--config-dir PATH`
2. `$JOB_SCOUT_CONFIG_DIR`
3. the directory you ran the command from, if it has a `config.yaml`
4. the directory this package was installed from

Run data — `jobs.db`, `scout.log`, whatever the file notifier writes:

1. `--data-dir PATH`
2. `$JOB_SCOUT_DATA_DIR`
3. `<config dir>/data`

To keep your profile out of this repository entirely:

```bash
job-scout init ~/job-search
job-scout run --config-dir ~/job-search --data-dir /var/lib/job-scout
```

---

# config.yaml

## Top level

| Key | Type | Default | What it does |
|---|---|---|---|
| `notify_threshold` | int 0-100 | `65` | Lowest score you get told about. Everything below is still recorded. |
| `scoring_model` | string | `gemini:gemini-2.5-flash` | `"backend:model"`. See below. |
| `scoring_retries` | int | `1` | Retries per posting when the model call fails. |
| `scoring_delay_seconds` | number | `0` | Pause between model calls. Raise it if you hit a rate limit. |
| `pre_filter` | bool | `true` | The free keyword filter. Turn it off only to see what it was dropping. |
| `reject_too_senior` | bool | `false` | Also reject postings judged above your level. |
| `outcomes_file` | path | `outcomes.csv` | Relative to the config directory, or absolute. |
| `source_priority` | list | see below | Which board wins when the same advert appears on several. |
| `notifiers` | list | — | **Required.** At least one. |
| `searches` | list | — | **Required.** At least one. |
| `careerjet` | mapping | — | Careerjet settings. |
| `apify` | mapping | — | Apify settings. |

### `scoring_model`

`"backend:model"`. All five backends are optional; you install what your choice
needs and nothing else.

| Value | Needs |
|---|---|
| `gemini:gemini-3.7-flash` | `pip install google-genai`, `GOOGLE_API_KEY` |
| `openrouter:google/gemini-3.7-flash` | `OPENROUTER_API_KEY` |
| `claude:sonnet` | the `claude` command on your PATH |
| `grok:grok-4` | the `grok` command |
| `codex:gpt-5` | the `codex` command |

A bare `vendor/model` with a slash and no prefix is treated as OpenRouter.

Model names change. If a run fails saying the model was not found, look up a
current one — for Gemini, at
[ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models).

`job-scout check` reports all five at once.

### `source_priority`

When the same advert is found on several boards, one copy is kept: the one from
the board earliest in this list. Ties break on whichever copy has the longest
description, because that is what the scorer reads.

```yaml
source_priority: [linkedin, indeed, careerjet, apify, jobindex]
```

Anything not listed sorts last. The default is the order above.

## `searches`

Each entry is one query, run against every board in its `sites` list.

| Key | Type | Default | Notes |
|---|---|---|---|
| `term` | string | — | **Required.** |
| `sites` | list | `[linkedin, indeed]` | See the table below. |
| `location` | string | `""` | Free text, passed to the board. |
| `country_indeed` | string | `""` | Indeed needs the country named: `"Germany"`, `"USA"`. |
| `hours_old` | int | `72` | LinkedIn and Indeed only. |
| `results_wanted` | int | `50` | Per board, per term. |
| `is_remote` | bool | `false` | Ask the board for remote-only. |
| `locale_code` | string | — | Careerjet only, overrides the global setting. |

```yaml
searches:
  - term: "platform engineer"
    sites: [linkedin, indeed]
    location: "Berlin, Germany"
    country_indeed: "Germany"
    hours_old: 96
    results_wanted: 50
```

### Site names

| Name | Handled by | Needs |
|---|---|---|
| `linkedin` | python-jobspy | nothing |
| `indeed` | python-jobspy | nothing |
| `glassdoor` | python-jobspy | nothing |
| `zip_recruiter` | python-jobspy | nothing |
| `google` | python-jobspy | nothing |
| `careerjet` | this repo | a partner key, a referer and an IP |
| `apify` | this repo | a paid token and at least one Actor |
| `jobindex` | this repo | Playwright and Chromium. Denmark only. |

## `notifiers`

At least one is required. Write an entry as a mapping, or as a bare name when it
needs no settings.

### `file` — no credentials

```yaml
notifiers:
  - type: file
    path: matches.md        # relative to the data directory, or absolute
    format: markdown        # markdown | text | csv | json
    append: true            # keep every run, oldest first
```

`csv` is the one to pick for a spreadsheet. `json` writes one object per line
for something downstream to read.

### `telegram`

```yaml
  - type: telegram
    token_env: TELEGRAM_BOT_TOKEN     # optional, if you renamed the variable
    chat_id_env: TELEGRAM_CHAT_ID
```

Needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Create a bot with
[@BotFather](https://t.me/botfather), message it once, then read the chat id
from `https://api.telegram.org/bot<TOKEN>/getUpdates`.

One message per job, so each is its own notification with its own link.

### `email`

```yaml
  - type: email
    to: you@example.com       # or a list
    from: scout@example.com   # defaults to SMTP_USER
    subject: "Job Scout"      # the date is appended
```

Needs `SMTP_HOST`, `SMTP_USER` and `SMTP_PASSWORD` in `.env`. `SMTP_PORT`
defaults to 587, and the port decides the security unless you set
`SMTP_SECURITY` to `starttls`, `ssl` or `none`.

On Gmail the password must be an
[App Password](https://myaccount.google.com/apppasswords), not your account
password.

### `webhook`

```yaml
  - type: webhook
    flavor: slack           # slack | discord | raw
    url_env: WEBHOOK_URL
```

The URL is a credential and lives in `.env`. `raw` posts `{"text": "..."}`,
which suits Mattermost, Google Chat and most others.

## `careerjet`

```yaml
careerjet:
  locale_code: en_GB      # en_US, de_DE, da_DK, fr_FR, nl_NL ...
  referer: https://example.com/jobs    # or CAREERJET_REFERER in .env
  user_ip: 203.0.113.10                # or CAREERJET_USER_IP in .env
```

All three of key, referer and IP are required together. Careerjet rejects calls
whose referring site and IP do not match what you registered at
[careerjet.com/partners/api](https://www.careerjet.com/partners/api). Missing any
one of them logs which one and skips the source.

The locale is what widens the net in a non-English market: the search terms stay
in English, and `da_DK` returns Danish-language listings that English terms alone
would miss.

## `apify`

Paid, and the answer to LinkedIn and Indeed throttling datacenter IPs.

```yaml
apify:
  run_timeout_seconds: 300     # give up on one Actor run after this
  memory_mbytes: 1024          # optional; omit for the Actor's own default
  actors:
    - id: misceres/indeed-scraper
      site: indeed             # label used for duplicate priority
      input:
        position: "{term}"
        location: "{location}"
        country: "{country}"
        maxItemsPerSearch: "{results_wanted}"
```

There is no default Actor, deliberately. Every Actor bills differently and none
should start charging you because a name appeared in a list.

`input` is passed to the Actor untouched, except that these placeholders are
filled in from the search:

`{term}` `{location}` `{country}` `{results_wanted}` `{hours_old}`

A placeholder that is the whole value keeps its type, so `"{results_wanted}"`
arrives as the number 50.

Actors disagree about field names, so each scout field is filled from the first
key present out of a list of aliases — `title`, `positionName` and `jobTitle` all
become `title`. Override per Actor when yours uses something unusual:

```yaml
      field_map:
        title: myWeirdTitleField
        url: myWeirdLinkField
```

Two Actors verified against Apify's live documentation on 2026-08-23:

| Actor | Price then | Input keys |
|---|---|---|
| `misceres/indeed-scraper` | $3.00 per 1,000 listings | `position`, `location`, `country`, `maxItemsPerSearch` |
| `bebity/linkedin-jobs-scraper` | $29.99/month plus usage | `title`, `location`, `rows`, `publishedAt`, `workType`, `contractType`, `experienceLevel` |

Check the price on the Actor's own page before pointing this at hundreds of
postings a day. Apify's free plan includes $5 of platform usage a month and asks
for no card.

---

# profile.yaml

This is the file that decides what counts as a match. It is compiled into the
prompt.

## `candidate`

| Key | What to write |
|---|---|
| `name` | Yours. Appears in the prompt. |
| `current_role` | One or two sentences. What you own now. |
| `years_experience` | A string, e.g. `"8"` or `"8+"`. |
| `seniority` | Be blunt. Used to reject roles below your level. |
| `location` | Where you are. |
| `work_authorization` | Visas, permits, clearances, citizenship. Anything that disqualifies you regardless of skill. |
| `target_geography` | Where you will actually work. Say whether remote counts. |
| `languages` | A mapping of language to honest level. |

`languages` levels matter. A posting needing fluent Danish is rejected outright
if you say elementary, and that rejection is separate from the work-permit one:

```yaml
  languages:
    English: Native
    German: Elementary — can follow a stand-up, cannot run a workshop
```

## Lists

| Key | What it is for |
|---|---|
| `target_roles` | Every title the job you want goes by. Titles vary wildly between companies. |
| `core_skills` | Things you would happily be interviewed on tomorrow. |
| `secondary_skills` | Things you have used once, or could pick up fast. Weighed lower. |
| `confirmed_gaps` | **The important one.** What you genuinely cannot do. |
| `industries_preferred` | A soft signal, not a filter. Leave empty if you do not mind. |

### `confirmed_gaps`

If a posting's core day-to-day work needs one of these, the score is capped at 40
however well everything else lines up. A posting mentioning one as a nice-to-have
is unaffected.

Specific beats short:

```yaml
confirmed_gaps:
  - "Frontend development — React, Vue, Angular, CSS. Has never shipped a
     user interface."
  - "Machine learning and MLOps — training models, feature stores, model
     serving, MLflow, vector databases, RAG pipelines."
```

## Filters

| Key | Effect |
|---|---|
| `extra_pre_filter_keywords` | Extra words for the free filter. Any one hit passes. |
| `pre_filter_stop_words` | Words to drop from the automatic keyword list. |
| `hard_exclude_location_patterns` | Locations rejected before anything costs money. |
| `hard_exclude_title_patterns` | Titles rejected before anything costs money. |

All four are case-insensitive substring matches.

Watch the spaces in title patterns: `"hr "` catches "HR Manager" and not
"shrink"; `" intern"` catches "Marketing Intern" and not "Internal Tools
Engineer".

Add words that appear in every posting in your market to
`pre_filter_stop_words` — in Denmark, "denmark" and "danish" carry no signal.

---

# .env

Never committed. `job-scout check` tells you which of these you actually need.

| Variable | For |
|---|---|
| `GOOGLE_API_KEY` | the `gemini` backend |
| `OPENROUTER_API_KEY` | the `openrouter` backend |
| `LLM_CLI_SSH_HOST`, `LLM_CLI_SSH_KEY` | running a CLI backend on another machine |
| `LLM_CLI_TIMEOUT`, `LLM_CLI_CONCURRENCY`, `LLM_CLI_ENV_FILE`, `LLM_CLI_FORCE_SSH` | CLI backend tuning |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | the Telegram notifier |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY` | the email notifier |
| `WEBHOOK_URL` | the webhook notifier |
| `CAREERJET_API_KEY`, `CAREERJET_REFERER`, `CAREERJET_USER_IP` | the Careerjet source |
| `APIFY_API_TOKEN` | the Apify source |
| `JOB_SCOUT_CONFIG_DIR`, `JOB_SCOUT_DATA_DIR` | paths |

Values already in the real environment always win over the file, so a systemd
unit or a GitHub Actions secret is never overwritten by a stale `.env`.

---

# Command line

```
job-scout run                    do a run
job-scout run --dry-run          score and print, record nothing, send nothing
job-scout run --limit 5          stop after 5 postings reach the scorer
job-scout check                  what is set up and what is missing
job-scout init DIR               put a config.yaml and profile.yaml somewhere
job-scout version
```

Every command takes `--config-dir`, `--data-dir` and `-v/--verbose`.

`--dry-run` is the one to use while tuning: it scores everything and prints it,
writes nothing to the database and sends nothing, so you can run it repeatedly
against the same day's postings.
