---
name: metrics-auditor
description: Check that every number in a tailored CV traces to the user's master content file. Flags unsupported or changed numbers, suggests placeholders for the user to fill, and never invents a value.
---

# Metrics auditor

A number on a CV is a claim the user will be asked to defend in an interview.
This skill checks every one against the master content file and blocks the
application from being called ready while any number is unsupported.

Doing this by hand instead? List every number in the CV, find each in your
master content file, and mark it verified, changed, or missing. The rules below
are the whole method.

Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

- Automatically after `resume-tailor` has written the CV and its ATS text version.
- Whenever the user asks "are these numbers safe" or "audit the metrics".
- After a humanizer pass, which must never change a number but sometimes does.

## Inputs

- The tailored CV and `CV-ats.md` in the application folder (or any text with
  bullets containing numbers).
- The user's master content file. It is the only source of truth for numbers.

## Output

Append to `notes.md` in the application folder, under a heading with today's date:

```markdown
## Metrics audit, YYYY-MM-DD

### Verified
- "{number and claim}": {role}, master file section {n}, matches exactly.

### Changed or unsupported (blocking)
- "{number and claim}": CV says X, master says Y. Reconcile before use.
- "{number and claim}": not in the master file at all.

### Placeholders left in the CV (blocking)
- "[PLACEHOLDER: ...]" in bullet "...". The user must supply the value or remove the claim.

### Bullets that could carry a number
- Bullet "...": no outcome is quantified. A number could come from {kind of
  measure}. Ask the user whether one exists. Do not guess.

### Result
{No invented numbers found / N problems found}
```

## Workflow

1. **Extract every number** from the CV body. Skip dates, page numbers and
   section headings. Look for percentages, counts with a unit, money, durations,
   multipliers ("3x"), and team or user counts.
2. **Find the source for each:**
   - Same figure, same role, same claim in the master file: verified.
   - Same claim with a different figure: blocking. The CV and master disagree.
   - Figure absent from the master file: blocking. Treat it as invented until
     the user confirms it.
   - A placeholder in brackets: blocking until resolved.
3. **For unquantified outcome bullets,** suggest the kind of measure that would
   strengthen them (for example, "number of teams onboarded") without supplying
   a value.
4. **Scan for round numbers that look machine-made** (50%, 100%, 10x with no
   context) and verify each against the master file.
5. **Write the audit block.**

## Rules

- A number may appear in a CV only if it exists in the master file for the same
  role and the same claim. No exceptions.
- "A reasonable estimate" is not a category. A number is either defensible, with
  the calculation or source noted in the master file, or it is a placeholder.
- When in doubt, remove the number. A strong qualitative bullet beats a wrong
  quantitative one.
- Never round, soften or generalise. "20%" stays "20%", never "about a fifth".
- Never raise a number to make a bullet land harder.

## Interaction with the humanizer pass

The humanizer must not touch numbers, names or dates. If a figure differs from
the master file and the humanizer ran last, revert the figure and record it
under "Changed or unsupported" as a humanizer change.

## Blocking criteria

The application is not ready while any of these hold:

- A changed or unsupported number remains.
- A placeholder remains in the CV or its ATS text version.

The user may accept the risk explicitly. If they do, write that acceptance into
`notes.md` with the date, so the decision is visible later.
