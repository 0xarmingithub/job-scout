---
name: tune-threshold
description: Diagnose and fix Job Scout sending too many jobs, too few, or the wrong ones. Use when someone says they are getting spam, getting nothing, or the matches are irrelevant.
---

# Tuning what Job Scout sends

Three different complaints, three different fixes. Work out which one you have
before changing anything.

**Do not just move `notify_threshold`.** It is the right fix for exactly one of
the three cases, and the wrong fix for the other two.

## Get the evidence first

```bash
job-scout run --dry-run
```

Scores everything, prints it, records nothing, sends nothing. Safe to run
repeatedly against the same day's postings, which is what makes it useful for
tuning.

Then look at what the database says about the last few days:

```bash
job-scout stats
```

That gives the status breakdown, the score distribution and the best scores
on record in one go. The distribution decides everything below: it tells you
whether the near misses sit in the 50s and 60s, where lowering the threshold
helps, or in the 30s and 40s, where it will not.

That second query is the important one. It tells you what the near misses
actually scored, which decides everything below.

## Case 1: too many, and they are good

More than about five a day, and the user would genuinely consider them.

Raise `notify_threshold` by 5. Only this case.

```yaml
notify_threshold: 70    # was 65
```

Re-check after a few days. Three a day is the target, a tool that sends forty is
a tool people stop reading.

## Case 2: too many, and they are irrelevant

Volume is fine, relevance is not. The threshold is not the problem. The profile
is.

Read three or four of the bad matches with the user and find the pattern.

**Wrong discipline**, an ML role, a data engineering role, a frontend role:

`confirmed_gaps` is too vague or missing the category. Make it specific:

```yaml
confirmed_gaps:
  - "Machine learning and MLOps. Training models, feature stores, model
     serving, MLflow, vector databases, RAG pipelines. Has consumed model
     APIs, has never owned a model."
```

If the same wrong discipline keeps appearing, kill it at Tier 1 instead, which
costs nothing:

```yaml
hard_exclude_title_patterns:
  - "machine learning"
  - "ml engineer"
  - "data scientist"
```

**Wrong level**. Roles clearly below them:

Sharpen `candidate.seniority`, and add title patterns:

```yaml
hard_exclude_title_patterns:
  - "junior "
  - " intern"
  - "graduate programme"
```

**Wrong place**. Commutes they will not do:

```yaml
hard_exclude_location_patterns:
  - "munich"
```

Warn about substrings: `"york"` catches New York.

**Wrong language or permit**. These should already be rejected. If they are
not, `candidate.languages` or `candidate.work_authorization` is too vague. Both
need to state the level and the boundary explicitly.

## Case 3: nothing at all

Check in this order. Skipping straight to the threshold is the usual mistake.

**Is anything being fetched?**

```bash
grep "Fetched" data/scout.log | tail -5
```

If the answer is zero, this is not a threshold problem. Go to
[docs/troubleshooting.md](../../../docs/troubleshooting.md), usually a blocked
source or a datacenter IP.

**Is the pre-filter eating everything?**

A large `rejected_prefilter` count means the keyword list is too narrow. Add
synonyms and adjacent technology to `extra_pre_filter_keywords`. Aim for 30 to
60 words. Broad is correct here.

Also check `hard_exclude_title_patterns` for a pattern that is too short or
missing a trailing space. `"hr"` without the space matches "Chromium".

**What did the near misses score?**

- **50s and 60s**: lower `notify_threshold` by 5. This is the real Case 3.
- **30s and 40s**: the profile and the search terms describe different jobs.
  Fix the profile. Lowering the threshold here just gives them bad matches.
- **Lots of `rejected_language` or `rejected_work_authorization`**: the market
  genuinely wants something they do not have. That is information, not a bug.
  Worth saying out loud, it may change where they look.

**Are the search terms right?**

Have them search one term on the board by hand. If the board shows nothing
either, the term is the problem.

## Score bands

Fixed, and separate from the threshold:

| Score | Label |
|---|---|
| 80-100 | STRONG |
| 65-79 | POSSIBLE |
| below 65 | LONG SHOT |

Setting `notify_threshold` below 65 means everything arrives labelled LONG SHOT,
which is honest but tiring.

## Feeding real outcomes back

If the user has applied to things and knows what happened, an `outcomes.csv` next
to their `config.yaml` improves the scoring more than any threshold change:

```csv
title,company,status
Senior Platform Engineer,Northwind Energy,rejected
IoT Solution Architect,Vestbridge Systems,interviewing
```

The scorer is shown which kinds of role converted and told to find the pattern
itself. Optional, and everything works without it.

## After any change

```bash
job-scout run --dry-run
```

Compare with what you saw before. Change one thing at a time, two changes at
once and you learn nothing.
