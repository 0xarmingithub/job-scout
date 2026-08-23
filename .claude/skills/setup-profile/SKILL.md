---
name: setup-profile
description: Interview the user about their job search and write their profile.yaml and config.yaml. Use when someone is setting Job Scout up for the first time, says the results are irrelevant, or asks to change what the scout looks for.
---

# Setting up a Job Scout profile

`profile.yaml` decides what counts as a match. Everything else is plumbing. Your
job is to interview the user properly and write a file that is honest, specific,
and complete.

Doing this by hand instead? Copy `job_scout/templates/profile.yaml`, read the
comments in it, and fill it in. This skill is a guided version of that, not a
different mechanism.

## Ask for the CV first

Before anything else, ask whether they have their CV as a file. If they do:

```bash
job-scout init <config-dir> --from-cv <path-to-cv>
```

That drafts the roles, skills, languages, industries and keywords from the CV
and saves roughly half an hour of interviewing. `.pdf` and `.docx` need
`pip install -e ".[cv]"`; `.txt` and `.md` need nothing.

Then read the draft back to them and interview only about what a CV cannot say.
That is sections 1, 4 and 5 below, and section 4 is the important one. Skip
sections 2 and 3 unless the draft got something wrong.

Without a CV, run the whole interview.

## Rules

**Never invent a skill, a job, or a level.** Everything in the file comes from
what the user told you. If you are unsure whether they have used something, ask.
A profile with a skill they cannot discuss in an interview produces matches they
cannot use.

**`confirmed_gaps` is the most valuable section.** Spend real time on it. Anyone
can list skills; the gaps are what stop the scorer sending an ML role because it
saw "Python". Users under-report gaps, they are trained to sell themselves. Ask
directly and make it easy to say no.

**Be specific in gaps.** "Machine learning" caps every posting that mentions ML
anywhere. "Training models, feature stores, model serving, MLflow, vector
databases. Has consumed model APIs, has never owned a model" is a gap the model
can actually judge a posting against.

**Keep the pre-filter broad.** It exists to skip pastry chefs, not to judge fit.
Too narrow and good jobs never reach the scorer at all. Aim for 30 to 60
keywords.

**Do not commit anything.** Write the files. The user decides what happens next.

## The interview

Ask in this order. One topic at a time. This is a lot of questions and dumping
them all at once gets you shallow answers.

### 1. Where they are and what would disqualify them

- Where do they live? Where will they actually work. On-site, hybrid, remote?
- Are there places they will not commute to? (This becomes
  `hard_exclude_location_patterns`. Ask for cities and regions, and warn that
  these are substring matches, so "york" catches New York.)
- **Work authorisation.** Citizenship, visa, permit, clearance. This is the one
  people forget and it produces the most useless matches. Permanent residence is
  not citizenship, and some roles require citizenship.
- **Languages, with honest levels.** "Conversational German" and "can run a
  workshop in German" are different jobs. In a non-English market this is the
  single most effective filter in the file.

### 2. Level and titles

- Current role, in a sentence or two. What do they actually own?
- Years of experience.
- What level are they aiming at? Be blunt. This rejects roles below them.
- **Every title the job goes by.** Companies name the same job five ways.
  "Platform Engineer", "SRE", "Infrastructure Engineer", "DevOps Engineer" may
  all be the same job. Push for the full list.

### 3. Skills, in two tiers

- **Core**: what would they happily be interviewed on tomorrow?
- **Secondary**: what have they used once, or could pick up in a fortnight?

Ask for the specific version. "Cloud" is useless. "AWS. EKS, RDS, IAM, VPC
design" is what the scorer can match against a posting.

### 4. Gaps

Ask straight out, and give permission:

> What comes up in job adverts in your field that you genuinely have not done?
> Nobody has done everything, and this is the section that makes the scout
> useful, it is not a weakness audit.

Prompt by category if they stall: frontend, mobile, machine learning, data
engineering, embedded, security operations, enterprise platforms like SAP or
Salesforce, people management.

For each one, get the specific boundary. "Has operated the databases, never owned
the pipelines" is worth ten times "no data engineering".

### 5. Search terms and sources

- Four to eight search terms. Not their job title, the terms they would type
  into a board.
- Which country? That decides the sources:
  - Everywhere: `linkedin`, `indeed`
  - Denmark: add `jobindex` (needs Playwright. Say so)
  - Non-English market: mention Careerjet with a locale
- Tell them plainly: LinkedIn and Indeed prohibit automated scraping in their
  terms. They are on by default because they work. It is the user's call.

### 6. Where results go

- File is the default and needs nothing.
- Telegram takes about five minutes and puts jobs on their phone.
- Ask whether they want to set one up now or start with the file.

## Writing the files

Write `profile.yaml` and `config.yaml` into the config directory, the repo root
unless they told you otherwise, or wherever `--config-dir` points.

Keep the section comments from the template. They are the documentation people
find later.

Set `notify_threshold` to 65 for two sources, 70 for four or more.

## Then check it

```bash
job-scout check
job-scout run --dry-run --limit 10
```

`--dry-run` records nothing and sends nothing, so you can run it repeatedly.

Read the scores back to the user and ask whether they agree. That conversation is
the real test of the profile, and it usually produces two or three corrections.

If most postings score in the 30s and 40s, the profile and the search terms are
describing different jobs. Fix the profile first, never the threshold.
