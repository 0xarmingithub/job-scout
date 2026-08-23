# How scoring works

Every posting goes through three tiers, cheapest first. Most never reach the one
that costs money.

## Tier 0 — location

If the posting's location contains any string from
`hard_exclude_location_patterns`, it is dropped. Case-insensitive substring
match, and nothing else happens to it.

```yaml
hard_exclude_location_patterns:
  - "munich"
  - "hamburg"
```

Status written: `rejected_location`.

Two traps. A posting whose location is empty is **let through**, on the grounds
that no information is not the same as bad information. And these are substrings,
so `"york"` matches New York, and `"berlin"` matches Berlin, New Hampshire.

## Tier 1 — keywords

Two checks, both free.

**Title exclusions.** If the title contains any string from
`hard_exclude_title_patterns`, the posting is dropped. This is where you kill
whole categories: junior roles, internships, sales jobs, disciplines you do not
work in.

Mind the spaces. `"hr "` catches "HR Manager" and not "shrink". `" intern"`
catches "Intern" and "Marketing Intern" and not "Internal Tools Engineer".

**Keyword hit.** At least one keyword must appear somewhere in the title or the
description. The keyword list is built from two places:

1. Every word of every `term` in your searches, minus stop words and anything
   shorter than three characters.
2. Everything in `extra_pre_filter_keywords`.

Status written: `rejected_prefilter`.

This filter is deliberately generous — one hit out of a hundred words is enough.
It is not there to judge fit. It is there to stop you paying a model to read a
pastry chef vacancy. If you want to know what it is throwing away, set
`pre_filter: false` and compare a day's results. Expect the bill to go up by
about an order of magnitude.

Words that appear in nearly every posting in your market carry no signal and
just widen the net. Add them to `pre_filter_stop_words`:

```yaml
pre_filter_stop_words:
  - denmark
  - danish
```

## Tier 2 — the model

What survives is sent to your chosen backend with a prompt built from
`profile.yaml`. The reply is JSON:

```json
{
  "score": 84,
  "language_barrier": false,
  "work_authorization_barrier": false,
  "seniority_match": "match",
  "key_matches": ["Kubernetes", "Terraform", "AWS"],
  "gaps": ["Kafka Streams"],
  "reasoning": "Runs exactly the platform stack the candidate owns."
}
```

Three of those fields are hard rejections and override the score entirely:

| Field | Meaning | Status written |
|---|---|---|
| `language_barrier` | needs fluent command of a language you do not have | `rejected_language` |
| `work_authorization_barrier` | needs citizenship, a permit or a clearance you lack | `rejected_work_authorization` |
| `seniority_match: too_junior` | aimed below your level | `rejected_seniority` |

`too_senior` is not rejected by default — being told about a stretch role is
usually welcome. Set `reject_too_senior: true` if you disagree.

If the model call fails, it is retried `scoring_retries` times (default 1). If
it still fails, or the reply contains no JSON, the posting gets
`scoring_error` and the run carries on. One bad posting never stops a run.

## The prompt

Assembled from `profile.yaml` at run time. Every section maps to a field:

| Prompt section | Comes from |
|---|---|
| Experience, seniority, location, work authorisation, languages | `candidate` |
| Target roles | `target_roles` |
| Core skills, secondary skills | `core_skills`, `secondary_skills` |
| Preferred industries | `industries_preferred` |
| Confirmed gaps, and the cap rule | `confirmed_gaps` |
| Real application outcomes | `outcomes.csv`, if present |
| The posting itself | title, company, location, first 3,500 characters of the description |

To see the exact prompt your profile produces:

```python
import yaml
from job_scout.matcher import build_prompt_template

profile = yaml.safe_load(open("profile.yaml", encoding="utf-8"))
print(build_prompt_template(profile))
```

## Confirmed gaps do most of the work

Anyone can list skills. The list that changes the results is the one saying what
you cannot do.

If a posting's core day-to-day responsibilities need one of your confirmed gaps,
the model is instructed to cap the score at 40, however heavily the other
keywords overlap. A posting that mentions the same thing as a nice-to-have is
unaffected.

This is what stops a machine-learning role scoring 85 because it mentioned
Python, Kubernetes and AWS. Be specific:

```yaml
confirmed_gaps:
  # Vague. Half the industry "does" ML.
  - "Machine learning"

  # Specific. The model can tell whether the posting needs this.
  - "Machine learning and MLOps — training models, feature stores, model
     serving, MLflow, vector databases, RAG pipelines. Has consumed model
     APIs, has never owned a model."
```

Write them the way you would explain the gap to an honest recruiter.

## Feeding real outcomes back in

Optional, and off unless the file exists. Put an `outcomes.csv` next to your
`config.yaml`:

```csv
title,company,status
Senior Platform Engineer,Northwind Energy,rejected
IoT Solution Architect,Vestbridge Systems,interviewing
Cloud Infrastructure Engineer,Halden Data,offer
DevOps Engineer,Meridian Logistics,no response
```

Three columns are required and any others are ignored, so keep a date or a note
alongside them if you like. Statuses are matched loosely: "rejected after final
round" is rejected, "first screen booked" is interviewing, "ghosted" is no
response.

The scorer is shown three groups and told to find the pattern itself rather than
being given a rule:

| Group | Statuses | Why it is separate |
|---|---|---|
| Converted | `interviewing`, `offer` | What worked |
| Applied and did not convert | `rejected`, `no_response` | Applied, lost. Often about competition, not fit. |
| Read and chose not to apply | `withdrawn` | The strongest signal of the three, and the one people leave out |

That third group is worth filling in. A role you read in full and decided
against is the same judgement the scorer is trying to make, made by you with the
whole posting in front of you. Statuses are printed verbatim, so
"withdrawn (not applied)" stays distinguishable from "withdrawn after second
interview" — they mean different things and the model can tell.

The list is capped at 25 outcomes so the prompt does not grow without adding
information.

If the file is missing, malformed, or has the wrong column names, the run logs
one line and scores without it.

## Setting the threshold

`notify_threshold` is the lowest score you get told about. Everything below it is
still recorded, so it never comes back tomorrow.

| Sources | Start at |
|---|---|
| Two (LinkedIn, Indeed) | 65 |
| Four or more | 70 |

Then adjust on volume, not on feeling:

- **More than about five a day**: raise it by 5.
- **Nothing for a week**: lower it by 5, and check the near misses first.

To see what the near misses actually scored without changing anything:

```bash
job-scout run --dry-run
```

That scores everything and prints it, records nothing, and sends nothing — so
you can run it repeatedly against the same day's postings.

The bands in a notification are fixed and separate from your threshold:

| Score | Label |
|---|---|
| 80-100 | STRONG |
| 65-79 | POSSIBLE |
| below 65 | LONG SHOT |

## Every status a posting can end up with

| Status | What happened |
|---|---|
| `new` | Passed everything and has a score |
| `rejected_location` | Location matched an exclusion |
| `rejected_prefilter` | No keyword hit, or the title matched an exclusion |
| `rejected_language` | Needs a language you do not have |
| `rejected_work_authorization` | Needs citizenship, a permit or a clearance |
| `rejected_seniority` | Aimed below your level |
| `scoring_error` | The model call or the JSON parse failed |

All of them are written to `jobs.db`, so nothing is ever scored twice. To see
what happened yesterday:

```bash
sqlite3 data/jobs.db \
  "SELECT status, COUNT(*) FROM seen_jobs GROUP BY status ORDER BY 2 DESC;"
```
