---
name: master-resume-curator
description: Keep the user's master content file current. Add new wins, refine bullet variants, record confirmed facts, retire statements that are no longer true. Maintains the single source of truth every tailoring run draws from.
---

# Master content curator

Everything the other skills write about the user comes from one file, the master
content file. If a fact is not in it, it does not go on a CV. This skill keeps
that file complete, honest and current.

Doing this by hand instead? Open the file, follow the "Workflow" headings below
for the kind of change you are making, and keep every old phrasing.

The file's default name is `master-resume.md`, in the workspace root. The blank
starting point is [templates/cv/master-content.md](../../../templates/cv/master-content.md).
Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

- The user says "I just shipped X, add it" or "capture this for later".
- The user brings a new role, project, certification, side project or number.
- The user corrects a figure or asks to retire a statement that is no longer true.
- A tailoring run produced new confirmed facts or new bullet phrasings (the
  tailor skill calls this skill twice for exactly that reason).
- Every month or two, as a check-in, even when nothing was asked.

## Inputs

- The master content file.
- What the user tells you, in their own words, with dates and numbers.
- Optionally: an existing CV, a LinkedIn export, a previous version. Reading an
  existing CV into the file: `job-scout init --from-cv <path>` drafts a profile
  from one today, and `job-scout cv import` (available from 1.10.0) drafts a
  `resume.yaml` from one, which the user can then use to extend the master content file. Either way, treat the
  result as a draft the user must read, never as confirmed fact.

## Output

An updated master content file. This skill changes nothing else: it does not
touch any CV, and it does not touch the applications folder, except to flag one
(see "Retiring a statement").

## Workflow

### Adding a bullet to an existing role

1. Find the role under "Work experience".
2. Put the strongest current phrasing under "Canonical bullets". Anything else
   goes under "Alternate phrasings".
3. If the bullet introduces a number, add it to that role's "Defensible metrics"
   line, with a note of how it was measured.
4. If the user is unsure of the number, store the bullet without the figure, put
   `[USER TO CONFIRM]` beside it, and add a line to "Open questions". Never
   store a guess as a metric.

### Adding a role

1. Insert it in reverse chronological order under "Work experience".
2. Copy the structure of the existing roles: heading with company and title,
   a line with location and dates, then the bullet blocks.
3. The title is the exact title the user held. Not a friendlier version.
4. Write three to five canonical bullets using the formula in the voice file.
5. Verify every number with the user before it is stored.

### Adding a skill, tool or competency

1. Find the right group under "Skills".
2. Add it only if the user could discuss it for a minute in an interview. If you
   are not sure, ask: "Did you use X in production, and at what scale?"
3. Record depth honestly ("hands-on in production", "read about it, no hands-on
   use"). The depth decides how a later tailoring run may word it.

### Adding a certification or course

1. Add a row to "Certifications" with issuer and date.
2. Mark in-progress items as in progress.
3. Add the topic to "Skills" only if the user has practical depth, not only the
   certificate.

### Refining or replacing a bullet

1. Do not delete the old phrasing. Move it to "Alternate phrasings".
2. Promote the new phrasing to "Canonical".
3. Reason: a later posting may use the old vocabulary.

### Recording confirmed facts from an interview

The tailor skill asks the user questions before it writes a CV. Every answer that
states a fact (a number, a tool, a scope, a decision) goes into the role's
"Confirmed additional facts" block with the date, before the CV is written.
A fact that exists only in a CV or only in a chat is a fact that will be lost.

### Retiring a statement that is no longer true

1. Move it to "Alternate phrasings" as struck-through text, with a comment saying
   when and why it was retired.
2. If a number is no longer defensible, search the applications folder for CVs
   that use it and flag each in its `notes.md`. Do not edit those CVs here.

### Keeping the scout's profile in step

If the user runs job-scout, `profile.yaml` is what the scorer reads. When the
master file gains a skill, tool or industry, suggest the matching change in
`core_skills`, `secondary_skills`, `extra_pre_filter_keywords` or
`industries_preferred`. When it gains a real gap, suggest it for `confirmed_gaps`.
Ask first. Do not edit the profile silently.

### Before the user sends the file anywhere

The master file holds more of a person than any CV should. If the user wants a
hosted model to read it, remind them what it contains. `job-scout privacy`
(available from 1.8.0) keeps the user's own private word list and checks files
against it. To see what a hosted model receives, read
[docs/external-services.md](../../../docs/external-services.md).

### Periodic check-in

Every month or two, ask:
- Anything new at your current employer worth recording: projects, scope, numbers?
- Any certification or course in progress?
- Any side project, talk or publication?
- Any application outcome that changed? (Update the `Status:` line in that
  application's `notes.md`; see [docs/applications.md](../../../docs/applications.md).)

## Rules

- The master file only grows. Phrasings pile up as a library on purpose. Prune
  statements that are untrue, never ones that are merely old.
- Every number must be defensible. When a user gives you one, ask "how was it
  measured, and could you explain it to a sceptical interviewer?" If not, tag
  it `[USER TO CONFIRM]`.
- Do not polish the master file. A recruiter never reads it, and several
  phrasings of the same fact are a feature.
- Personal details (phone, address, date of birth) live in their own section at
  the end, never inline in a role.
- The "Open questions" list belongs to the user. Never resolve an item in it
  without their answer.
- Never copy a requirement from a job posting into this file as if it were the
  user's experience. A posting is not evidence about the user.

## Anti-patterns

- Importing a LinkedIn export or an old CV and overwriting phrasings the user
  chose carefully.
- Promoting an unverified number from a quick chat to a canonical bullet.
- Deleting old bullets "to tidy up".
- Listing a participation as an award, or a course as a qualification.
