# Running it on GitHub Actions

Free, needs no machine of your own, and returns fewer results than any other
path. Read the next section before you invest an afternoon in this.

## Read this before you invest an afternoon

**Do not scrape LinkedIn or Indeed from GitHub Actions. Use the Apify source
instead.** The rest of this page assumes you will.

Two separate problems, and the second is the one people miss.

**Your requests come from a shared pool.** A GitHub-hosted runner is a
throwaway machine on Azure, and its IP address is recycled between everybody's
jobs. When LinkedIn or Indeed blocks that address, you inherit the block without
having done anything, and your own scraping helps get the next person blocked.
You cannot fix this from your side, because the address is not yours. You do not
even get a stable one to be blocked consistently.

**Datacenter addresses are throttled harder anyway.** The same `config.yaml`
that returns 200 postings from a home connection can return a handful from a
runner, or nothing.

Neither is a bug in the scout, and no setting works around them.

The fix is [Apify](#making-apify-work-from-actions). It runs the collection on
its own machines through its own proxy pool, so nothing is ever requested from
GitHub's addresses. It also puts the scraping under Apify's agreements rather
than yours. It costs money. That is the trade.

If you would rather not pay, the honest options are:

| | |
|---|---|
| **Use only sources that do not care where you call from** | Careerjet is a licensed API. Drop `linkedin` and `indeed` from every `sites:` list. |
| **Use a VM instead** | [setup-systemd.md](setup-systemd.md). An Oracle always-free VM costs nothing, has a stable address, and does not have either problem. |

For a scheduled scout that reliably works and costs nothing, the VM is the
answer, not this page.

## Setup

### 1. Get your own copy of the repository

The schedule and the secrets live in the repository, so it has to be one you
control. Forking works, but a private copy is better, because your
`profile.yaml` is a document about you and step 3 commits it.

```bash
git clone https://github.com/0xarmingithub/job-scout.git my-job-scout
cd my-job-scout
git remote remove origin
gh repo create my-job-scout --private --source=. --push
```

Without the `gh` command line tool: create an empty private repository on
github.com, then `git remote add origin <its-url>` and `git push -u origin main`.

Forks have one extra wrinkle worth knowing. GitHub disables scheduled workflows
in a fork until you enable them by hand, on the Actions tab.

### 2. Add your secrets

On github.com, in your repository: Settings, then Secrets and variables, then
Actions, then New repository secret. Add one per row.

| Secret | Needed for |
|---|---|
| `GOOGLE_API_KEY` | scoring. Required. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | notifications on your phone |
| `WEBHOOK_URL` | Slack or Discord instead |
| `APIFY_API_TOKEN` | the Apify source |
| `CAREERJET_API_KEY`, `CAREERJET_REFERER`, `CAREERJET_USER_IP` | the Careerjet source |

Never put a key in `config.yaml`. `.github/workflows/scout.yml` already reads all
of the above from secrets.

Careerjet has a wrinkle here: it checks that the calling IP matches the one you
registered, and a runner's IP changes every time. Careerjet is effectively not
usable from Actions unless your account is registered against a wide range.

### 3. Commit a config, in `myconfig/`

The runner is a fresh machine. It can only see what is committed, so your
`config.yaml` and `profile.yaml` have to be in the repository.

**Put them in `myconfig/`, not the repo root.** The root copies are gitignored on
purpose — they are the scratch copies a local run creates, and if they were
committed a `git pull` could clobber your edits. `git add config.yaml` at the
root will simply refuse.

```bash
job-scout init myconfig
# edit myconfig/profile.yaml and myconfig/config.yaml
git add myconfig
git commit -m "My job search config"
git push
```

The shipped workflow already runs with `--config-dir myconfig`. If `myconfig/` is
missing it falls back to the fictional example profile and prints a warning on
the run page, so a first run works either way — it just will not be about you.

Nothing secret goes in either file. Keys come from repository secrets.

### 4. Turn the workflow on

Before you do: the config `job-scout init` wrote uses `sites: [linkedin, indeed]`,
which is the thing this page opened by telling you not to do from a runner. Set
up [Apify](#making-apify-work-from-actions) first, or expect thin results and
know why.

`.github/workflows/scout.yml` ships ready to go and runs at 12:00 UTC daily.
Being in the repository is not enough to make it fire, though.

Open the Actions tab. If GitHub shows a banner asking whether to enable
workflows, say yes. Then find **scout** in the left-hand list. If it says
disabled, use the menu on the right to enable it.

Three reasons a schedule silently never runs, all of which look identical from
the outside:

- **Forks have scheduled workflows disabled by default.** You have to enable
  them by hand.
- **GitHub disables a schedule after 60 days of no activity** in the repository.
  A commit turns it back on.
- The workflow file is on a branch other than your default one. Schedules only
  run from the default branch.

Run it once by hand before trusting the schedule: Actions, then scout, then Run
workflow.

Two things about GitHub's scheduler worth knowing once it is running:

- **It is UTC only** and ignores daylight saving, so a fixed cron drifts by an
  hour twice a year against your local time.
- **It fires late when GitHub is busy**, sometimes by 30 minutes or more. For a
  daily job that does not matter.

### 5. Check what happened

The run page shows the log. It also uploads `data/matches.md` and
`data/scout.log` as an artifact, downloadable for 14 days — useful while you are
still tuning the threshold.

## Remembering what it has already seen

This is the part that needs attention.

The scout remembers every posting in `data/jobs.db`. A runner is destroyed after
each run, so without help every run sees every posting as new and sends you the
same jobs every day.

The shipped workflow uses `actions/cache`:

```yaml
- uses: actions/cache@v4
  with:
    path: data
    key: job-scout-data-${{ github.run_id }}
    restore-keys: |
      job-scout-data-
```

A fresh key each run with a shared prefix means each run restores the most recent
cache and saves a new one.

Two limits worth knowing:

- **GitHub deletes a cache not read for 7 days.** A daily run keeps it warm. If
  you pause for a fortnight, the first run back re-notifies you about everything.
- **10 GB total cache per repository.** `jobs.db` is a few megabytes, so this
  will not be your problem.

If you want it properly durable, commit `jobs.db` to a branch instead. Add
`contents: write` permission and a commit step. The cache is simpler and good
enough for most people.

## Making Apify work from Actions

Do this. It is what turns the Actions path from a disappointment into something
that works, and it keeps GitHub's shared addresses out of the job boards
entirely.

### 1. Get a token

Sign up at [apify.com](https://apify.com). The free plan includes $5 of platform
usage a month and asks for no card.

Then: Settings, then Integrations, then copy the Personal API token. It starts
with `apify_api_`.

Add it to your repository as the `APIFY_API_TOKEN` secret.

### 2. Pick an Actor

Search [apify.com/store](https://apify.com/store) for the board you want. Open
it and read two things before you commit: the pricing tab, and the input schema.

Two that were checked against Apify's live documentation on 2026-08-23:

| Actor | Price then | What it scrapes |
|---|---|---|
| `misceres/indeed-scraper` | $3.00 per 1,000 listings | Indeed |
| `bebity/linkedin-jobs-scraper` | $29.99/month plus usage | LinkedIn |

Prices change. Check the Actor's page yourself.

### 3. Put it in `myconfig/config.yaml`

```yaml
apify:
  run_timeout_seconds: 300
  actors:
    - id: misceres/indeed-scraper
      site: indeed
      input:
        position: "{term}"
        location: "{location}"
        country: "{country}"
        maxItemsPerSearch: "{results_wanted}"
```

`{term}`, `{location}`, `{country}` and `{results_wanted}` are filled in from
each search. A placeholder that is the whole value keeps its type, so
`"{results_wanted}"` reaches the Actor as the number 50.

Set `run_timeout_seconds` deliberately. The scout aborts a run that overruns so
it stops charging you, but too low a value throws away what it already paid for.

### 4. Point your searches at it

This is the step people forget, and without it nothing changes.

```yaml
searches:
  - term: "platform engineer"
    sites: [apify]          # not [linkedin, indeed]
    location: "Berlin, Germany"
    country_indeed: "Germany"
    results_wanted: 50
```

Every search that still lists `linkedin` or `indeed` goes on hitting the boards
directly from GitHub's addresses. Change all of them.

### 5. Commit and check

```bash
git add myconfig && git commit -m "Use Apify" && git push
```

Then run the workflow by hand from the Actions tab and read the log. The Apify
console at [console.apify.com](https://console.apify.com) shows each run, what
it cost, and its own log when something fails.

### What it costs

At 50 listings a term across four terms, `misceres/indeed-scraper` is 200
listings a day. About $0.60 a day, or $18 a month, on top of Apify's free $5.

Cut it by lowering `results_wanted`, running fewer search terms, or moving the
schedule to every other day. The seen-jobs database means a less frequent run
does not lose you postings, it just finds them later.

## What this path costs

| | |
|---|---|
| GitHub Actions | Free on public repositories. Private ones get 2,000 minutes a month on the free plan; a daily run uses roughly 150. |
| Scoring | Free on Gemini's free tier. |
| Apify | Optional, and the only line that is not free. |

## When to give up on it

If you have tried this and the results are thin, and you do not want to pay for
Apify — put it on a VM. An Oracle Cloud always-free instance costs nothing, has
a residential-ish reputation as far as the boards are concerned, and runs the
same scout with a systemd timer. [setup-systemd.md](setup-systemd.md).
