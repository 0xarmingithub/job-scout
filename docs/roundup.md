# The weekly roundup

A daily digest answers one question: is there anything today. It is bad at the
other one, which is what did I actually see this week. By Friday the strong
Monday posting is four notifications up the chat, and you will not scroll back
to find it.

```bash
job-scout roundup                 # the last 7 days, best 10
job-scout roundup --days 5        # the working week, run on a Friday
job-scout roundup --top 5         # a shorter message
job-scout roundup --dry-run       # print it, send nothing
```

## What it does and does not do

It reads `jobs.db` and nothing else. No board is contacted, no posting is
re-scored, no model is called. A roundup costs nothing and cannot disagree with
the digest you were sent at the time, because it is showing you the same scores.

It only includes postings that cleared your `notify_threshold` on the day they
were found. Anything a filter rejected never reached the scorer and has no score
to show, so it is not there.

## The window

`--days` counts today. That is the part worth understanding:

| Run on | `--days` | Covers |
|---|---|---|
| Friday | 5 | Monday to Friday |
| Friday | 7 | Saturday to Friday |
| Sunday | 7 | Monday to Sunday |

If you move the timer to another day, change `--days` with it. A Wednesday timer
with `--days 5` covers the previous Saturday to Wednesday, which is nobody's
working week.

## Sending it on a Friday

`deploy/install-systemd.sh` installs the units but leaves the timer off, so
enabling it is a decision you make rather than one that happens to you:

```bash
sudo systemctl enable --now job-scout-roundup.timer
systemctl list-timers job-scout-roundup.timer
```

Both the day and the window live in the units:

| File | Holds |
|---|---|
| `deploy/job-scout-roundup.timer` | `OnCalendar=Fri *-*-* 17:00:00 <your timezone>` |
| `deploy/job-scout-roundup.service` | `ExecStart=... job-scout roundup --days 5` |

Change them as a pair.

## Where it goes

The same notifiers as a daily run: everything in the `notifiers:` list of your
`config.yaml` gets it. There is no separate configuration, on purpose. A roundup
that arrives somewhere you do not read is worse than no roundup.

The header says what it is, so a Friday message is never mistaken for a daily
one:

```
Job Scout roundup, 24 Aug to 28 Aug 2026
best 10 of 23 matches at or above 70
```

## When nothing matched

You still get a message, and it says the week was quiet rather than blaming the
job boards:

```
Nothing reached 70 from 24 Aug to 28 Aug 2026.
That is a quiet week rather than a broken scout: the daily runs still
recorded everything they saw.
Check with: job-scout stats
```

That distinction matters. A daily run reporting zero matches usually means a
source broke. A roundup reporting zero means five daily runs each found nothing,
which is a fact about the market, not about your setup. If you think it is
actually broken, `job-scout stats` shows where postings are being lost.

## Upgrading from 1.0.0

The roundup needs the scorer's reasoning, and 1.0.0 did not store it. Opening
your existing `jobs.db` adds the column in place, so nothing is lost and there is
nothing to run by hand.

One consequence is worth knowing: postings recorded before you upgraded have no
saved reasoning. They still appear in a roundup with their score, company and
link, just without the "Why" line. That fixes itself as new postings come in.
