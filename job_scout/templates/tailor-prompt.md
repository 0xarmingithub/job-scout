# Tailoring prompt

This file is a template. The scout fills in the `{placeholders}` and hands the
result to whatever `tailor.command` names in your config.yaml.

Everything in `[SQUARE BRACKETS]` is yours to replace. Nothing here knows
anything about you until you do that. Read the whole file once before your
first run: what you write here decides what the model is willing to claim on
your behalf.

Delete these four paragraphs when you have finished editing.

---

You are writing a CV tailored to one job posting.

## The posting

- Title: {title}
- Company: {company}
- Location: {location}
- Source: {site}
- Link: {url}
- The scout scored this {score} out of 100.
- Why it scored that: {reasoning}
- What it matched on: {key_matches}
- Where it saw gaps: {gaps}

Full text of the posting:

{description}

## What you have to work from

My full career history is at [PATH TO YOUR MASTER CV OR CAREER FILE]. Read it
first. It is the only source of facts about me.

[IF YOU KEEP OTHER FILES THE MODEL SHOULD READ, LIST THEM HERE. FOR EXAMPLE A
PORTFOLIO, A LIST OF PUBLICATIONS, OR A FILE OF WRITING SAMPLES THAT SHOWS YOUR
VOICE.]

## What I told you when you asked

{answers}

If that section is empty, I did not answer in time. Carry on without it and
mark anything you would have asked about, as described below.

## Rules

1. **Invent nothing.** Every claim must be traceable to a specific line in the
   file above. If the posting wants something I cannot show, leave it out. Do
   not soften a gap into a half-claim.

2. **Never guess a number.** Team sizes, budgets, percentages, dates and
   durations come from my file or they do not appear. Where a number would
   strengthen a bullet and you do not have one, write the bullet without it and
   add `[NEEDS ME: what number?]` at the end of the line.

3. **Never mention:** [ANYTHING THAT MUST NOT APPEAR. PROJECTS UNDER NDA, A
   CURRENT EMPLOYER WHO DOES NOT KNOW YOU ARE LOOKING, WORK YOU DO NOT WANT
   MORE OF. LIST IT EXPLICITLY. THERE IS NOBODY CHECKING THIS BUT YOU.]

4. **Match their words.** Where my file and the posting describe the same thing
   differently, use their phrasing. Do not stretch it to cover something I have
   not done.

5. **Order by what they asked for.** The posting's first three requirements
   should be answerable from my first half page.

6. **[YOUR OWN RULE. TONE, LENGTH, A SECTION YOU ALWAYS WANT, A FORMAT THE
   PLACES YOU APPLY TO EXPECT.]**

## Output

Write Markdown. Plain headings, no tables, no images, no columns: this has to
survive being pasted into an application form and read by software that strips
formatting.

Structure:

- Name and contact line
- A three-line summary aimed at this posting
- Experience, most recent first, with bullets chosen for this posting
- Skills, only those the posting cares about
- Education and anything else they asked for

End the file with a section headed `## Notes for me`, which is not part of the
CV. Put in it:

- every `[NEEDS ME]` you left, gathered in one list
- anything in the posting you could not answer from my file
- what you would ask me if you could

Write the finished document to: {output_file}

Write nothing to standard output. The file is the deliverable.
