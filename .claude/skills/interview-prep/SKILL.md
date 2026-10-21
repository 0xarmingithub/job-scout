---
name: interview-prep
description: Build STAR-format talking points, anticipated questions and questions for the interviewer from a tailored CV and its job description. Draws only on the master content file and the application's gap analysis.
---

# Interview prep

The tailored CV is also the interview script: every bullet on it is something
the interviewer may ask about. This skill turns the strongest bullets into
stories the user can tell truthfully, and prepares honest answers for the gaps.

Doing this by hand instead? For each top bullet write Situation, Task, Action,
Result and Reflection in your own words, then list three questions you expect
and three you want to ask.

Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

- After the tailored CV exists and the user has approved it.
- When an interview is scheduled and the user says "prepare me for the
  {company} interview" or "STAR stories for this role".
- When the user reports an interview or a status change: update the `Status:`
  line in `notes.md` first (vocabulary in
  [docs/applications.md](../../../docs/applications.md)), then prepare. Once
  `job-scout outcomes` exists (available from 1.8.0) that line is what feeds
  the outcome data used in scoring, so a stale line quietly drops the
  application from it.

## Inputs

- The tailored CV in the application folder: the stories the interviewer will probe.
- `analysis.md`: what the role values most.
- `gap-analysis.md`: where the hard questions will come from.
- The user's master content file: context that did not fit on the CV.

## Output

Append to `notes.md` in the application folder:

```markdown
## Interview prep, YYYY-MM-DD

### Stories (one per top bullet on the tailored CV)

#### Story 1: {bullet, abbreviated}, at {Company, year}

- **Situation:** {one or two sentences of real context, not generic}
- **Task:** {what was specifically the user's job}
- **Action:** {what they did: tools, decisions, who they influenced}
- **Result:** {the number from the master file, plus the qualitative outcome}
- **Reflection:** {what they learned, what they would do differently}
- **Likely follow-ups:**
  - "How did you measure {number}?" and an answer angle
  - "What did not work?" and an answer angle

(repeat for the top 3 to 5 bullets)

### Anticipated questions

#### Technical
- "Walk me through how you would design X": answer angle and the story to anchor on
- "What is your experience with {P0 tool}": the story to anchor on

#### Behavioural
- A conflict with a stakeholder: story
- A failure: story, honest, with the reflection
- Why this role and this company: answer angle
- Why leave the current role: forward-looking answer angle

#### Gap probes (from the real gaps in gap-analysis.md)
- "You have no direct {X} experience": honest answer, ramp-up plan, closest adjacent experience

### Questions for the interviewer

- Two or three about the role, drawn from the posting
- One about what success looks like at 30, 60 and 90 days
- One about how the team works and how decisions are made
- One about the company's near-term challenge

### Salary and logistics

- Market range for this role and level: {source, or "user to research"}
- Target and walk-away: {user to fill in}
- Format, length, interviewers, tech check, materials to have open
```

## Workflow

1. Read the tailored CV. Pick the 3 to 5 bullets that are most relevant to the
   posting and best backed by numbers.
2. For each, build a story anchored in a specific role, year and project from
   the master file. If the master file lacks the context, write
   `USER NEEDS TO ADD: story context for bullet X` in `notes.md` and ask. Do not
   fill the hole with plausible detail.
3. Read `analysis.md`. For each P0 or P1 keyword likely to be probed, write a
   one-line answer angle tied to a story.
4. Read the real gaps in `gap-analysis.md`. For each, prepare the honest
   framing: acknowledge it, show how they would ramp up, point to the closest
   adjacent experience.
5. Draft 5 to 7 questions for the interviewer. Skip anything the posting or the
   company's website already answers.
6. Leave salary and logistics as a checklist for the user to complete.

## Rules

- Every story anchors in a real role, year and project from the master file. No
  generic narratives, no invented scenes.
- Reflection is mandatory. Interviewers weigh what was learned as much as the win.
- Write bullet-point notes, not scripts. Memorised answers sound rehearsed.
- On gaps, an honest answer with a ramp-up plan beats deflection. Never bluff.
- On leaving the current role, talk about what the new role offers, not what was
  wrong with the old one.
- Numbers in a story are the numbers on the CV, from the master file. No new ones.

## Anti-patterns

- Stories written as case studies in the third person.
- Generic questions such as "what is the culture like?".
- Naming a salary figure with no market reference.
- Asking the interviewer nothing.
