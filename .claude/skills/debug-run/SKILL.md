---
name: debug-run
description: Work out why a Job Scout run failed, returned nothing, or sent nothing. Use when someone reports an error, says the scout stopped working, or says they got no notification.
---

# Debugging a run

Work through this in order. Skipping to the interesting hypothesis is how people
spend an hour on a missing environment variable.

The written version of everything here, in more detail, is
[docs/troubleshooting.md](../../docs/troubleshooting.md).

## 1. Ask the machine first

```bash
job-scout check
```

Reports every backend, every notifier and every source, with the reason each one
is or is not ready. Most reports are one line of this output.

If it says NOT READY for the scoring backend or for every notifier, stop —
that is the answer.

## 2. Read the log

```bash
tail -100 data/scout.log
# under systemd:
sudo journalctl -u job-scout -n 200 --no-pager
```

Look for, in this order:

| Line | Means |
|---|---|
| `Fetched N unique jobs` | how many arrived, and from which source |
| `Dedup: N raw -> M new` | how many survived the seen-jobs check |
| `Scoring backend: ...` | which model actually ran |
| `Scoring done: ... N errors` | how many model calls failed |
| `Results: N at or above T` | how many cleared the threshold |
| `Run failed:` | it did not finish |

Those six lines tell you which stage lost the jobs. Find that first, then dig.

## 3. Match the symptom

### "Every source returned 0 jobs"

Not a quiet market — a source problem, nine times in ten.

- **Datacenter IP.** LinkedIn and Indeed throttle these hard. A cloud VM gets
  fewer results than a laptop, a GitHub Actions runner often gets none. The fix
  is the Apify source or a different machine.
- **One source or all of them?** The log names each. Cut `config.yaml` to a
  single search with a single site and run again.
- **`hours_old` too tight.** Default 72. Try 168 in a small market.
- **The search term returns nothing on the board either.** Have them check by
  hand.

### "Lots fetched, almost nothing scored"

```bash
sqlite3 data/jobs.db \
  "SELECT status, COUNT(*) FROM seen_jobs GROUP BY status ORDER BY 2 DESC;"
```

A large `rejected_prefilter` count means the keyword list is too narrow, or a
title pattern is too greedy — `"hr"` without a trailing space matches "Chromium".

To measure it, run one day with `pre_filter: false` and compare. Expect the model
bill to be roughly ten times higher.

### "It scored things but sent nothing"

Either nothing cleared the threshold, or the notifier is broken. `job-scout check`
distinguishes them in one line. If it is the threshold, use the `tune-threshold`
skill.

### "The run failed"

The error is in the log with a traceback. The scout also sends run-level failures
to the notifiers, with credentials stripped, so ask whether they got an ALERT
message — that message usually names the cause.

### "The same jobs arrive every day"

`jobs.db` is not surviving between runs.

```bash
sqlite3 data/jobs.db "SELECT COUNT(*), MAX(first_seen) FROM seen_jobs;"
```

Zero after a successful run means it is not being written there. Common causes:
Docker without a persisted `/data` volume, a GitHub Actions cache that expired,
a changed `--data-dir`, or a `--dry-run` (which records nothing on purpose).

### "Scoring errors"

```bash
grep "Scoring failed" data/scout.log
```

- **Rate limited.** Gemini's free tier allows about 10 calls a minute. Add
  `scoring_delay_seconds: 2`.
- **Model not found.** Names change. Look up a current one at
  [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models).
- **"no JSON object" in the reply.** A weaker model wrapping its answer in
  prose. Try a stronger one, or `scoring_retries: 2`.
- **A CLI backend timing out.** They take about 14 seconds a posting against 2
  for the API. Raise `LLM_CLI_TIMEOUT`.

### "The run never started"

- systemd: `systemctl list-timers job-scout.timer`
- GitHub Actions: a scheduled workflow is disabled automatically after 60 days
  of no repository activity
- The process was killed: `TimeoutStartSec` hit, or the OOM killer. Check
  `journalctl -u job-scout` and `dmesg | tail`.

## 4. Reproduce it safely

```bash
job-scout run --dry-run --limit 3 -v
```

Records nothing, sends nothing, scores three postings with debug logging. Safe to
run as many times as you like.

## 5. What not to do

- **Do not change several things at once.** You will not know which one worked.
- **Do not lower the threshold to make a source problem go away.** Find out why
  nothing was fetched.
- **Do not paste a log into an issue without reading it.** The scout redacts
  credentials from what it sends, but check.
- **Do not delete `jobs.db` to "reset" things** unless the user actually wants
  every posting shown again. That is what it does.

## 6. If it is a real bug

Say so plainly and write it up:
[github.com/0xarmingithub/job-scout/issues](https://github.com/0xarmingithub/job-scout/issues).

Include the `job-scout check` output, the relevant log lines, their `config.yaml`
minus anything private, and their Python version and operating system.
