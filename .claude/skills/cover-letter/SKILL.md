---
name: cover-letter
description: Write a tailored one-page, first-person cover letter for an application whose CV already exists. Use only when the posting or portal asks for a letter, or the user asks for one. Never by default.
---

# Cover letter

A cover letter is where one real gap from the gap analysis can be addressed
honestly, and where the user says in their own voice why this role and this
company. It builds on the finished CV. It never adds a claim the CV did not
already earn.

Doing this by hand instead? Follow "Structure" below on one page, then check
every claim against your master content file.

Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

Run this only when:

- the posting or the application portal asks for a cover letter (or
  "motivation letter", "letter of application"), or
- the user explicitly asks for one.

If neither is true, do not write one and do not suggest one in the middle of a
run. Offering one after the CV is finished is fine. Producing one unprompted is
not. This is the default; a user who wants a letter on every application can
say so, and then that instruction replaces it.

## Position in the pipeline

After the tailored CV exists and has passed the metrics and ATS checks, before
the user's final review. The letter must agree with the CV in every fact and
number.

## Inputs

- `jd.md`, `analysis.md` and `gap-analysis.md` in the application folder.
- The tailored CV and `CV-ats.md`: the claims already made.
- The user's master content file: the only source of facts.
- The user's voice rules (default `voice-and-tone.md`).
- The user's own letter template, if they have one. Copy it into the
  application folder. Never edit the original in place.

## Outputs

- The letter in the user's format, in the application folder (for example
  `cover-letter.tex` or `cover-letter.docx`).
- `cover-letter.md`: plain text for portal text boxes. Use plain ASCII
  characters, so names with accents are written without them if the portal is
  known to mangle them.
- A note in `notes.md` under a heading with today's date: why the letter was
  written (posting asked, or user asked), who it is addressed to, which gap was
  addressed and how, and the build result if it was compiled.

## Structure

```
Header and date
Salutation: "Dear {Name}," if the posting names a contact, else "Dear Hiring Team,"
Opening        : "I am writing to apply for the {ROLE} position." One sentence of
                 strongest evidence. One sentence saying what the letter covers.
Why me         : the project or platform that maps most directly onto the posting,
                 with its scope and numbers (the same numbers as the CV).
                 Then transferable strengths, and the one real gap, handled honestly.
Why {Company}  : the role framed as a specific problem the company has. No praise.
                 Why the team's way of working fits how the user works.
What I will do : first months, concrete deliverables in the posting's own words.
                 Then longer-term outcomes, measurable, not a list of activities.
Close          : "Best regards," and the user's name. Nothing else.
```

One page, always.

## Voice

- First person throughout: "I designed", "I would focus on". This deliberately
  differs from a CV, which drops the pronoun. Telegraphic third-person phrasing
  in a letter reads as stiff.
- Everything else in the voice rules applies: no AI vocabulary, no filler, no
  emojis, no dashes used as punctuation, active voice.
- Professional but not stiff. "I am writing to apply for..." beats both
  "Applying for..." and "I'm thrilled about...".
- No fabrication. Every claim and number traces to the master file, and the
  numbers are identical to the CV's. Never re-derive one.

## Gap handling

- Lead with the adjacent strength, then name the gap as a difference in tooling
  or setting, not as an apology. For example: "I have not run X in production.
  The pipeline design, staged rollouts and infrastructure-as-code habits I use
  with Y carry over directly."
- One gap at most. Several read as a list of weaknesses.
- Never claim the missing skill. Never say "familiar with".
- Only use an "it carries over" argument that is true. If it is not, leave the
  gap for the interview.

## Workflow

1. Confirm the trigger above. If neither holds, stop.
2. Find the contact in `jd.md`. Fall back to "Dear Hiring Team,".
3. Copy the user's template into the application folder.
4. Draft to the structure. Use evidence from the CV and the master file, and the
   posting's own vocabulary for deliverables.
5. Run the humanizer pass (see the tailor skill for how, and what to do if it is
   not installed). The opening needs a specific check: it should be first person
   and direct, not telegraphic.
6. Traceability pass: every claim, number and tool against the master file, and
   the letter against the CV.
7. Build it if the format needs building. A non-zero exit is a failed build. The
   letter must come out at one page.
8. Write `cover-letter.md`.
9. Log it in `notes.md`.

## Before declaring it done

- [ ] The trigger was explicit.
- [ ] First person throughout, with a direct opening.
- [ ] One page.
- [ ] No claim outside the master file. Numbers match the CV exactly.
- [ ] At most one gap, framed honestly.
- [ ] No AI-sounding vocabulary, no dashes as punctuation.
- [ ] `cover-letter.md` exists and pastes cleanly into a text box.
- [ ] `notes.md` is updated.

## Anti-patterns

- Writing a letter because "it would strengthen the application".
- Generic praise ("I have long admired..."). Describe the problem instead.
- Walking through the CV line by line. The letter argues fit. It does not repeat the CV.
- Addressing several gaps, or apologising for one.
- Padding to fill a page, or running over one.
