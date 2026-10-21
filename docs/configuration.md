# Configuration reference

Three files, and only one of them holds anything secret.

| File | Holds | Commit it? |
|---|---|---|
| `config.yaml` | Searches, threshold, which model, where results go | Yes, if it is yours to commit |
| `profile.yaml` | Who you are and what counts as a match | Your call, it is personal |
| `.env` | Every API key and token | **Never** |

How to get each of those keys, what it costs and whether it needs an account is on one page: [external-services.md](external-services.md).

The shipped copies live in `job_scout/templates/` and are copied to the repo
root the first time you run anything. Your edits to the copies are gitignored,
so a `git pull` cannot overwrite them and you cannot accidentally push them.

## Where the scout looks

`config.yaml` and `profile.yaml`, first hit wins:

1. `--config-dir PATH`
2. `$JOB_SCOUT_CONFIG_DIR`
3. the directory you ran the command from, if it has a `config.yaml`
4. the directory this package was installed from

Run data. `jobs.db`, `scout.log`, whatever the file notifier writes:

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
| `scoring_model` | string | none | `"backend:model"`. There is no default: `job-scout init` asks you. See below. |
| `cv_model` | string | none | `"backend:model"` for `job-scout cv import`. No default: it asks the first time. See [`cv_model`](#cv_model). |
| `scoring_retries` | int | `1` | Retries per posting when the model call fails. |
| `scoring_delay_seconds` | number | `0` | Pause between model calls. Raise it if you hit a rate limit. |
| `pre_filter` | bool | `true` | The free keyword filter. Turn it off only to see what it was dropping. |
| `reject_too_senior` | bool | `false` | Also reject postings judged above your level. |
| `outcomes_file` | path | `outcomes.csv` | Relative to the config directory, or absolute. |
| `applications_dir` | path | none | A folder of one folder per application. When set, the outcomes file is built from it. Relative to the config directory, or absolute. See [applications.md](applications.md). |
| `sync` | mapping | off | Pull the config directory (a git repository) before each run. See below. |
| `source_priority` | list | see below | Which board wins when the same advert appears on several. |
| `notifiers` | list | | **Required.** At least one. |
| `searches` | list | | **Required.** At least one. |
| `careerjet` | mapping | | Careerjet settings. |
| `apify` | mapping | | Apify settings. |

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
current one. For Gemini, at
[ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models).

`job-scout check` reports all five at once.

### `cv_validator_models`

A list of `backend:model` specs for `job-scout validate`. Empty by default. Set
it, or run `job-scout validate` in a terminal and choose them then. Up to four.

```yaml
cv_validator_models:
  - "claude:sonnet"
  - "codex:gpt-5"
```

### `cv_model`

`"backend:model"`, in the same format as `scoring_model`. It names the model that
reads your CV for [`job-scout cv import`](cv.md#job-scout-cv-import). Nothing else
uses it, and a search run never does.

It is a separate setting because import sends the whole text of your CV to the
backend: your name, contact details and every employer. That is a different
decision from which model scores job postings.

There is no default. With no `cv_model`, `job-scout cv import` run in a terminal
asks which model to use. When a scoring model is set, the first question is:

```
Use the same model as scoring? (Y/n):
```

Yes copies your `scoring_model`. No walks you through choosing another. Either way
the answer is written to `cv_model` here, and either way every import still asks
"Send it? (y/N)" first, naming the backend that receives the text. `--yes` skips
that second question for scripts. `--model BACKEND:MODEL` overrides the setting for
one run.

```yaml
cv_model: "claude:sonnet"
```

It is checked when config.yaml loads: a value that is not `backend:model` stops the
run with a message saying so. This is separate from the two model choices described
under [Two model choices](#two-model-choices) below.

## `job-scout validate`

A second opinion on a finished CV, from one or more models. It is opt-in: the
daily run never does this, and it costs one model call per model you chose.

```bash
job-scout validate --jd jd.md --cv cv.md --output report.md --config-dir ~/job-search
```

It sends the same analysis prompt to each model, in parallel, and writes one
report: a match score and an analysis per model, and the average. A model that
fails is listed as failed and left out of the average. The others still count.

Read the analyses before acting on a number. Models often disagree by a lot.

### Two model choices

This project uses a model in two separate places, and you choose each one.

| Step | Setting | Runs on | Cost grows with |
|---|---|---|---|
| Scoring postings | `scoring_model` | every posting that passes the keyword filter | how many postings your searches return |
| Drafting a CV | `tailor.command` | only the day's best match, if you turn it on | how many days you get a strong match |

Each can be an **API** (a hosted model you call with a key: `gemini`,
`openrouter`) or a **CLI** (a coding assistant already installed on your machine:
`claude`, `codex`, `grok`). The scoring model takes the `backend:model` form
above. The tailoring step is any command you write, so it can use a different
model, or a different tool, than scoring does. See [tailoring.md](tailoring.md).

`job-scout init <directory>` asks about the scoring model when it runs in a
terminal. Where there is no terminal (Docker, a CI job), name it with a flag:

```bash
job-scout init myconfig --scoring-model claude:sonnet
```

On an existing config the flag changes only the `scoring_model` line. It leaves
your profile and every other setting alone. Until a model is chosen, `job-scout
run` stops and says so, and `job-scout check` shows `NOT SET`.

### Application outcomes

The scorer can be told what happened to the jobs you applied for. Two ways to
give it that, and you use one of them.

By hand, a CSV at `outcomes_file`. Only these columns are required, and extra
columns are ignored:

```
title,company,status
Platform Engineer,Northwind Energy,rejected
```

Or from folders, with `applications_dir`: one folder per application, each with
a `notes.md` that has a `**Status:**` line. `job-scout outcomes` and every
`job-scout run` turn them into the file. Then the generated file is
`outcomes.csv` in your data directory, with the header
`title,company,status,folder`, and `outcomes_file` should be left unset. The
folder layout and the status words are in [applications.md](applications.md).

`status_ignore_phrases` (optional, a list of text) is removed from every Status
line before it is read. Use it when a phrase of your own contains a status word
but means something else, for example a step of your process that includes the
word "interview", which would otherwise be read as an employer interview.

`applications_dir` must be a path. A path that is not a directory does not stop a
run (the run scores without outcomes and alerts you); `job-scout check` shows
`NOT FOUND`.

### `sync`

```yaml
sync:
  git_pull: true            # default false
  retries: 2                # default 2, extra attempts after the first
  retry_wait_seconds: 10    # default 10
```

Before each real run, `git pull --ff-only` in the config directory, so a profile
pushed from another machine is live without anyone logging in. A `--dry-run`
never pulls. If every attempt fails you are alerted only when the directory is
behind its upstream; a failed pull while you are up to date is only logged.

"Behind" is measured against the remote as git last saw it, not against the
remote itself. When the pull fails because the network is down, git cannot see
newer commits either, so the directory can look up to date and no alert is sent.
The alert is reliable for failures git can explain from what it already knows,
such as a diverged branch or local changes in the way. It is not a substitute for
noticing that a profile you pushed never arrived.
Unknown keys, or a value of the wrong type, stop the run with a message.

### `source_priority`

When the same advert is found on several boards, one copy is kept: the one from
the board earliest in this list. Ties break on whichever copy has the longest
description, because that is what the scorer reads.

```yaml
source_priority: [linkedin, indeed, careerjet, apify, jobindex]
```

Anything not listed sorts last. The default is the order above.

## `advanced`

Optional, and nothing here needs changing to get started. Every value shown is
the default, so deleting a line puts it back.

| Key | Default | What it does |
|---|---|---|
| `description_chars` | `6000` | How much of a posting the model reads. The biggest lever on cost. |
| `reply_tokens` | `1024` | Room for the model's reply. Too small and a wordy answer gets cut off, which shows up as scoring errors. |
| `outcomes_listed` | `25` | How many outcomes from `outcomes.csv` reach the prompt. |
| `seen_lookback_days` | `7` | How far back the title-and-company duplicate check looks. |
| `scoring_error_retries` | `3` | How many runs a posting that failed to score is tried again on. `0` gives up at once. |
| `source_delay_seconds` | `0.5` | Seconds between paged requests to a board. |
| `score_bands.strong` | `80` | The score at which a match is labelled STRONG. |
| `score_bands.possible` | `65` | The score at which it is labelled POSSIBLE. |

```yaml
advanced:
  description_chars: 2000
  score_bands:
    strong: 85
    possible: 70
```

Two of these are worth thinking about.

**`description_chars` is the cost dial.** Halve it and you roughly halve the
token bill. The price is that the model sometimes misses a requirement buried
near the end of a long advert.

**`score_bands` is not `notify_threshold`.** The threshold decides whether you
hear about a posting at all. The bands decide what the label says once it
arrives. Setting the threshold below `score_bands.possible` means everything
turns up labelled LONG SHOT, which is honest but tiring.

Deliberately not configurable, because they are facts about somebody else's
service rather than preferences: API endpoints, Telegram's 4096-character
message limit, Discord's 2000-character one. The JobIndex scraper also refuses
to go below one second between pages whatever `source_delay_seconds` says.

## `searches`

Each entry is one query, run against every board in its `sites` list.

| Key | Type | Default | Notes |
|---|---|---|---|
| `term` | string | | **Required.** |
| `sites` | list | `[linkedin, indeed]` | See the table below. |
| `location` | string | `""` | Free text, passed to the board. |
| `country_indeed` | string | `""` | Indeed needs the country named: `"Germany"`, `"USA"`. |
| `hours_old` | int | `72` | LinkedIn and Indeed only. |
| `results_wanted` | int | `50` | Per board, per term. |
| `is_remote` | bool | `false` | Ask the board for remote-only. |
| `locale_code` | string | | Careerjet only, overrides the global setting. |

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

### `file`, no credentials

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

## Danish portals: `jobbank`, `jobnet`, `jobdanmark`, `jobindex_cli`

These four call the portal CLIs in
[MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
(MIT). They need no keys, but they need three things on the machine that runs
the scout:

1. bun on `PATH`, or its path in `JOB_SCOUT_BUN`
2. a checkout of that repo, with `bun install` run in each
   `.agents/skills/<portal>-search/cli` folder
3. `JOB_SCOUT_PORTAL_CLIS` set to the checkout's root folder

Missing any of the three logs one line and the source returns nothing.

```yaml
searches:
  - term: "IoT solution architect"
    sites: [jobbank, jobnet, jobdanmark, jobindex_cli]
    results_wanted: 20    # passed to each CLI as its result cap
```

`jobindex_cli` is a second route to Jobindex, next to the browser-based
`jobindex`. Both can be listed. Dedup keeps one copy and prefers the one from
the board earlier in `source_priority`.

If you want one Jobindex route, use `jobindex_cli`. Measured on 13 Danish
searches, twice on one day: the CLI route found more postings each time (130,
against 102 and 129), about four in five postings were on both, and the browser
route sometimes parsed the company wrongly ("Se jobbet", or the title repeated).
The two routes also use different URL shapes, so the seen-jobs store cannot
tell that they found the same posting; only the title and company key can.
When `jobindex` is not in your sites list, `jobindex_cli` shows as `jobindex` in
the run summary. When both run, each keeps its own name.

Each description comes from a detail call when the search result has none. A
detail result is cached for the run, so a posting found by two searches costs
one call.

Read the portal terms before you enable a source. The CLIs do not check
`robots.txt`. Jobindex's `robots.txt` disallows every path for every bot.

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
key present out of a list of aliases. `title`, `positionName` and `jobTitle` all
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
    German: Elementary. Can follow a stand-up, cannot run a workshop
```

## Lists

| Key | What it is for |
|---|---|
| `target_roles` | Every title the job you want goes by. Titles vary wildly between companies. |
| `role_families` | Optional. Kinds of role, each a `name` and a list of `keywords`, used only by `job-scout patterns` to group your applications. Without it there is one family per entry of `target_roles`. See [applications.md](applications.md#role-families). |
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
  - "Frontend development. React, Vue, Angular, CSS. Has never shipped a
     user interface."
  - "Machine learning and MLOps. Training models, feature stores, model
     serving, MLflow, vector databases, RAG pipelines."
```

## Filters

| Key | Effect |
|---|---|
| `extra_pre_filter_keywords` | Extra words for the free filter. Any one hit passes. |
| `pre_filter_stop_words` | Words to drop from the automatic keyword list. |
| `hard_exclude_location_patterns` | Locations rejected before anything costs money. |
| `keep_location_patterns` | Locations that pass even when they also match an exclusion, for multi-city postings. Optional. |
| `pattern_match` | `substring` (default) or `word`. How the three pattern lists above match. |
| `hard_exclude_title_patterns` | Titles rejected before anything costs money. |

All of them are case-insensitive. By default they are substring matches, the
same as Python's `in`. Set `pattern_match: word` and the title, location and
keep lists match whole words only: `"aarhus"` then matches "Aarhus, Denmark" but
not the street "Aarhusgade 12", and `"intern"` matches "Software Intern" but not
"Internal Tools". The keyword pre-filter stays a substring match either way, so
`kubernetes` still hits "Kubernetes-based". In word mode, write the whole word
you mean: `"graphic design"` no longer catches "Graphic Designer".

Watch the spaces in title patterns: `"hr "` catches "HR Manager" and not
"shrink". A bare `" intern"` catches "Marketing Intern", but also "Senior
Internal Tools Engineer" and "Industrial Internet of Things Architect". Bound it
on both sides instead: `" intern "`, `" intern,"`, `"(intern"`, `"intern)"`.

Add words that appear in every posting in your market to
`pre_filter_stop_words`. In Denmark, "denmark" and "danish" carry no signal.

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
job-scout stats                  where postings go and what they score
job-scout init DIR               put a config.yaml and profile.yaml somewhere
job-scout init DIR --from-cv CV  draft profile.yaml from your CV instead
job-scout version
```

### `stats`

The first thing to run when a run sends you nothing. It reads `jobs.db` and
shows where postings were dropped, the score distribution, the best scores on
record, and whether anything has ever cleared your threshold.

```bash
job-scout stats
job-scout stats --days 30
```

If the distribution has never produced anything above your threshold, the
problem is the profile or the search terms. Moving the threshold will not fix
it, and lowering it just delivers bad matches.

### `init --from-cv`

Reads your CV and drafts `profile.yaml` from it, using whichever backend
`scoring_model` names. `.txt` and `.md` work with no extra packages; `.pdf` and
`.docx` need `pip install -e ".[cv]"`.

```bash
job-scout init ~/job-search --from-cv ~/cv.pdf
```

Three fields come back empty on purpose, because a CV cannot supply them:

| Field | Why |
|---|---|
| `confirmed_gaps` | A CV lists what you have done. Nothing in it says what you cannot do. |
| `hard_exclude_location_patterns` | Your CV does not know which commutes you refuse. |
| `hard_exclude_title_patterns` | Same. |

If the model fills `confirmed_gaps` in anyway, the entries are dropped and a
warning is logged. A gap invented from a CV is worse than no gap at all: it caps
matching jobs at 40 and you will not notice for weeks.

Read `candidate.work_authorization` and `candidate.languages` too. Most CVs
state neither properly, and both reject a job outright rather than scoring it
low.

**Where your CV goes.** The text is sent to whichever backend `scoring_model`
names. On the default that is Google's API, and a CV carries your name, address,
phone number and employment history. To keep it on your own machine, point
`scoring_model` at `claude:`, `grok:` or `codex:` and run the CLI locally. The
scout keeps no copy of the CV and sends it nowhere else.

Re-running against an edited `profile.yaml` is refused unless you pass `--force`,
because the parts you wrote by hand are exactly the parts a CV cannot replace.

Every command takes `--config-dir`, `--data-dir` and `-v/--verbose`.

`--dry-run` is the one to use while tuning: it scores everything and prints it,
writes nothing to the database and sends nothing, so you can run it repeatedly
against the same day's postings.
