# Troubleshooting

Start here:

```bash
job-scout check
```

It reports every backend, every notifier and every source, and says what each
one needs. Most problems on this page are one line of its output.

Then read the log. `data/scout.log`, or `journalctl -u job-scout -n 200` under
systemd. Run with `-v` for more.

---

## Every source returned 0 jobs

The most common report, and almost never a quiet market.

**1. Are your search terms and location plausible?** Search the same term on
LinkedIn by hand. If the board shows nothing either, that is your answer.

**2. Are you on a datacenter IP?** LinkedIn and Indeed throttle these hard. A
cloud VM gets fewer results than a laptop; a GitHub Actions runner gets fewer
still, often zero. See
[setup-github-actions.md](setup-github-actions.md#the-catch-up-front). The fix is
the Apify source or a different machine.

**3. Which source failed?** The log names each one:

```
INFO  job_scout.sources -- jobspy: 0 new unique jobs
ERROR job_scout.sources -- careerjet failed (skipping): ...
```

**4. Try one source at a time.** Cut `config.yaml` down to a single search with a
single site and run again. That tells you whether it is one board or all of them.

**5. Is `hours_old` too tight?** The default is 72. In a small market, try 96 or
168.

---

## Everything is being filtered before it reaches the model

Symptom: lots fetched, almost nothing scored. The log shows a large number of
`rejected_prefilter`.

```bash
sqlite3 data/jobs.db \
  "SELECT status, COUNT(*) FROM seen_jobs GROUP BY status ORDER BY 2 DESC;"
```

**Your keyword list is too narrow.** It is built from the words in your search
terms plus `extra_pre_filter_keywords`. Add synonyms and adjacent technology.
Broad is right here — the filter exists to skip pastry chefs, not to judge fit.

**A title pattern is too greedy.** `"hr "` is fine. `"hr"` without the space
matches "Chromium". Check `hard_exclude_title_patterns` for a pattern with no
space or a very short one.

**A location pattern is too greedy.** `"york"` matches New York.

To find out what the filter is costing you, turn it off for one run:

```yaml
pre_filter: false
```

Compare, then turn it back on. Expect the model bill to be roughly ten times
higher with it off.

---

## No matches above the threshold

**Look at the near misses first.** Do not just lower the threshold:

```bash
job-scout run --dry-run
```

That scores everything and prints it without recording or sending anything, so
you can run it repeatedly.

- Near misses in the **50s and 60s**: lower `notify_threshold` by 5.
- Everything in the **30s and 40s**: your profile and your search terms describe
  different jobs. Fix the profile, not the threshold.
- Lots of **`rejected_language`** or **`rejected_work_authorization`**: the market
  genuinely wants something you do not have. That is information, not a bug.

**Are your `confirmed_gaps` too broad?** A gap listed as "Machine learning" caps
any posting that mentions ML anywhere. Write the specific version instead — see
[scoring.md](scoring.md#confirmed-gaps-do-most-of-the-work).

---

## The same jobs arrive every day

`jobs.db` is not surviving between runs.

| Where you run it | Likely cause |
|---|---|
| Locally | `data/` was deleted, or `--data-dir` changed |
| Docker | `/data` is not a persisted volume |
| GitHub Actions | the cache expired — GitHub deletes one unread for 7 days |
| systemd | `ReadWritePaths` does not include the data directory |

Check it is being written:

```bash
sqlite3 data/jobs.db "SELECT COUNT(*), MAX(first_seen) FROM seen_jobs;"
```

If the count is 0 after a successful run, the run is not writing there. `--dry-run`
also writes nothing, on purpose.

---

## Scoring errors

Postings with `scoring_error` mean the model call or the JSON parse failed.

```bash
grep "Scoring failed" data/scout.log
```

**A rate limit.** Gemini's free tier allows about 10 calls a minute. Slow down:

```yaml
scoring_delay_seconds: 2
```

**"Model not found".** Model names change. Look up a current one at
[ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
and put it in `scoring_model`.

**"model reply contained no JSON object".** A weaker model wrapping its answer in
prose. Try a stronger one. `scoring_retries: 2` helps with the occasional case.

**A CLI backend timing out.** They are slow — roughly 14 seconds a posting
against 2 for the API. Raise `LLM_CLI_TIMEOUT`, or use the API.

---

## Backend problems

### gemini

| Message | Fix |
|---|---|
| needs the google-genai package | `pip install google-genai` |
| needs GOOGLE_API_KEY | get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), put it in `.env` |
| 429 from the API | free tier limit — add `scoring_delay_seconds: 2` |

### openrouter

| Message | Fix |
|---|---|
| needs OPENROUTER_API_KEY | create one at [openrouter.ai/keys](https://openrouter.ai/keys) |
| 402 Payment Required | no credit on the account |

### claude, grok, codex

| Message | Fix |
|---|---|
| needs the `claude` command | install the CLI, or set `LLM_CLI_SSH_HOST=user@host` |
| CLI exited 1 | run the CLI by hand — it is usually not logged in |
| over SSH exited 255 | an SSH problem. Test `ssh -i $LLM_CLI_SSH_KEY $LLM_CLI_SSH_HOST true` |
| returned no output | the CLI is waiting for an interactive login on the remote host |

---

## Notifier problems

### Telegram

| Symptom | Cause |
|---|---|
| 401 Unauthorized | wrong `TELEGRAM_BOT_TOKEN` |
| 400 chat not found | wrong chat id, or you never messaged the bot. Message it, then re-read `getUpdates`. |
| 403 bot was blocked | you blocked it |
| Nothing arrives, no error | check `job-scout check` — the notifier is probably not in `config.yaml` at all |

### Email

| Symptom | Cause |
|---|---|
| 535 authentication failed | on Gmail you need an [App Password](https://myaccount.google.com/apppasswords), not your account password |
| connection timed out | wrong port. 587 is STARTTLS, 465 is SSL. |
| SSL error on 587 | set `SMTP_SECURITY=starttls` |

### Webhook

| Symptom | Cause |
|---|---|
| 404 | the webhook was deleted or the URL is wrong |
| 400 from Discord | set `flavor: discord` — Discord wants `content`, not `text` |
| message truncated | expected. Discord caps at 2,000 characters and the scout chunks at 1,900. |

---

## JobIndex problems

Denmark only, and the fiddliest source.

| Message | Fix |
|---|---|
| playwright is not installed | `pip install playwright && playwright install chromium --with-deps` |
| Chromium is not installed | `playwright install chromium --with-deps` |
| returns 0 jobs with no error | the site's markup changed — see below |
| the process is killed | not enough memory. Chromium needs ~500 MB. Add swap. |

If it returns nothing without complaining, JobIndex has redesigned. The parser
looks for a "save job" link matching `/bruger/dine-job/.../gem` and walks up to
the card. Save a search page and check:

```python
from job_scout.sources.jobindex import parse_search_page
jobs, has_next = parse_search_page(open("saved.html", encoding="utf-8").read(), "test")
print(len(jobs))
```

---

## Careerjet problems

| Message | Fix |
|---|---|
| CAREERJET_API_KEY / _REFERER / _USER_IP not set | all three are required together |
| 403 | the referer or IP does not match what you registered |
| unexpected response type 'LOCATIONS' | it could not resolve your location; it retries nationwide by itself |
| returns nothing in a non-English market | set `careerjet.locale_code`, e.g. `da_DK` |

Careerjet checks the calling IP against the one you registered. That makes it
awkward on a machine with a changing IP, and effectively unusable from GitHub
Actions.

---

## Apify problems

| Message | Fix |
|---|---|
| APIFY_API_TOKEN is not set | get one at [console.apify.com/settings/integrations](https://console.apify.com/settings/integrations) |
| no `apify: actors:` block | there is no default Actor. Add one — see [configuration.md](configuration.md#apify) |
| has no Actor called '...' | check the id on the Actor's page: `username/actor-name` |
| rejected the token | wrong or revoked token |
| finished as FAILED | open the run URL in the message; the Actor's own log says why |
| still running after N seconds — aborted | raise `apify.run_timeout_seconds` |

**Results come back with empty titles or URLs.** The Actor uses field names not
on the alias list. Look at one item in the Apify console and add a `field_map`:

```yaml
      field_map:
        title: jobTitleText
        url: jobPostingUrl
```

---

## The run failed and I got no message

The scout sends run-level failures to your notifiers. If nothing arrived:

**No notifier was usable.** `job-scout check`. A run with no working notifier
logs an error and puts the results in `scout.log` only.

**The run never started.** Under systemd, `systemctl list-timers job-scout.timer`.
On Actions, look at the Actions tab — a scheduled workflow is disabled
automatically after 60 days of no repository activity.

**The process was killed.** `TimeoutStartSec` hit, or the kernel's OOM killer.
`journalctl -u job-scout` and `dmesg | tail`.

---

## Starting over

Forget every posting and see everything again:

```bash
rm data/jobs.db
```

Reset the config to the shipped example:

```bash
job-scout init . --force
```

That overwrites `config.yaml` and `profile.yaml`. It does not touch `.env` or
`data/`.

---

## Reporting a problem

[github.com/0xarmingithub/job-scout/issues](https://github.com/0xarmingithub/job-scout/issues)

Include:

1. The `job-scout check` output.
2. The relevant part of `scout.log`.
3. Your `config.yaml`, minus anything private.
4. Python version and operating system.

**Read what you paste.** `scout.log` should not contain credentials — the scout
redacts them from anything it sends — but check anyway.
