# Running it on GitHub Actions

Free, needs no machine of your own, and returns fewer results than any other
path. Read the next section before you invest an afternoon in this.

## The catch, up front

**LinkedIn and Indeed throttle datacenter IP addresses much harder than home
connections.** GitHub Actions runners are about as datacenter as an IP gets.
The same `config.yaml` that returns 50 postings from your laptop can return 5
from a runner, or zero.

This is not a bug in the scout and there is nothing to configure around it. It
is what the boards do.

Three honest options:

| | |
|---|---|
| **Accept it** | Use the sources that do not care where you call from: Careerjet, and any national board. Drop LinkedIn and Indeed. |
| **Pay for Apify** | It does the collection on its own infrastructure with its own proxy pool. This is the real fix. See below. |
| **Use a VM instead** | [setup-systemd.md](setup-systemd.md). An Oracle always-free VM costs nothing and does not have this problem. |

If you want a scheduled scout that reliably works and costs nothing, the VM is
the answer, not this page.

## Setup

### 1. Fork or clone the repository

You need a repository you control, because the schedule and the secrets live in
it.

If your `profile.yaml` is going to be committed, **make the repository private**.
It is a document about you.

### 2. Add your secrets

Settings → Secrets and variables → Actions → New repository secret.

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

### 3. Commit a config

`config.yaml` and `profile.yaml` need to be in the repository, or the run has
nothing to work from. Run `job-scout init .` locally, edit both, commit them.

Nothing secret goes in either file.

### 4. Turn the workflow on

`.github/workflows/scout.yml` ships ready to go. It runs at 12:00 UTC daily.

Change the time in the `cron:` line. Two things about GitHub's scheduler that
catch people out:

- **It is UTC only** and does not follow daylight saving, so a fixed cron drifts
  by an hour twice a year against your local time.
- **It fires late when GitHub is busy**, sometimes by 30 minutes or more. For a
  daily job that does not matter.

Run it once by hand first: Actions → scout → Run workflow.

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

This is the configuration that makes the Actions path genuinely useful.

1. Sign up at [apify.com](https://apify.com). The free plan includes $5 of
   platform usage a month and asks for no card.
2. Copy your token from Settings → Integrations and add it as the
   `APIFY_API_TOKEN` secret.
3. Pick an Actor from [apify.com/store](https://apify.com/store) and put it in
   `config.yaml`:

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

4. Change your searches to use it, and drop the boards that will not answer a
   runner:

   ```yaml
   searches:
     - term: "platform engineer"
       sites: [apify]          # instead of [linkedin, indeed]
       location: "Berlin, Germany"
       country_indeed: "Germany"
       results_wanted: 50
   ```

Cost, checked on 2026-08-23: `misceres/indeed-scraper` charges $3.00 per 1,000
job listings. At 50 listings a term across four terms, that is 200 a day — about
$0.60 a day, or $18 a month. Check the Actor's own page for the current price
before you turn it on.

Set `run_timeout_seconds` deliberately. The scout aborts a run that overruns so
it stops charging you, but a timeout set too low wastes what it already spent.

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
