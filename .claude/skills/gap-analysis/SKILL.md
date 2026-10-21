---
name: gap-analysis
description: Map a job description's requirements onto the user's master content file and classify coverage. Shows where to emphasise and where a real gap exists. Never closes a gap by inventing evidence.
---

# Gap analysis

Takes the ranked requirements from `jd-analyzer` and checks each one against
what the user has actually done, as recorded in their master content file. The
output tells the tailoring step what to lead with, what to play down, and what
must not be claimed at all.

Doing this by hand instead? Take the P0 and P1 items from `analysis.md`, search
your master content file for each, and fill in the table below.

Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

- After `jd-analyzer` has written `analysis.md`.
- Before `resume-tailor`, so it knows what to emphasise and what to leave out.
- On its own, when the user asks "what is missing for this role" or "am I a fit".

## Input

- `analysis.md` in the application folder.
- The user's master content file (default `master-resume.md`; start from
  `templates/cv/master-content.md` if there is none yet). If the user has
  `confirmed_gaps` in `profile.yaml`, read them too: they are gaps the user has
  already admitted.

## Output

Write `gap-analysis.md` in the application folder:

```markdown
# Gap analysis: {Company}, {Role}

**Heuristic match score:** {0 to 100}, {one-line justification}

## Coverage table

| Requirement | Priority | Coverage | Evidence in the master file | Tailoring action |
|-------------|----------|----------|-----------------------------|------------------|
| ... | P0 / P1 / P2 | Strong / Weak / Transferable / None | {role and bullet reference} | {lead the summary / top bullet / skills line / play down / acknowledge the gap} |

## Coverage summary

- Strong: N of total P0 and P1 requirements
- Weak: N
- Transferable: N
- Real gaps: N

## Reframing for weak coverage

For each weakly covered item, the strongest honest reframing using content that
is already in the master file. Cite the bullets to adapt.

## Transferable items, with an honesty check

For each: the proposed angle, and one sentence on why the experience genuinely
transfers. If you cannot write that sentence, it is a real gap.

## Real gaps

For each:
- **Gap:** ...
- **Severity for this role:** blocker / significant / minor
- **Handling:** raise in a cover letter | raise in an interview | play down on the CV | not worth mentioning
- **Never:** add it to the CV.

## Recommendations to the user

- Skills they could realistically pick up before applying
- Master-file entries that need their confirmation or more detail first
- Whether to apply at all
```

## Workflow

1. Read `analysis.md`. It must exist.
2. Walk every P0 and P1 requirement. For each, search the master file for direct
   and adjacent evidence.
3. Classify:
   - **Strong:** direct experience with the named tool, skill or scope, ideally
     with a number.
   - **Weak:** older, lighter or adjacent experience that can honestly be reframed.
   - **Transferable:** no direct match, but another role or project genuinely
     produced the same competency.
   - **None:** no honest claim is possible.
4. Compute the heuristic score in code, not in your head. With counts of strong
   P0, strong P1, weak P0, weak P1, transferable, total P0 and total P1:

   ```bash
   python -c "sP0,sP1,wP0,wP1,t,nP0,nP1=0,0,0,0,0,1,1; print(round((sP0*3+sP1*2+wP0*1.5+wP1+t*0.5)/(nP0*3+nP1*2)*100))"
   ```

   Replace the seven numbers with the real counts. Flag any result under 60.
5. Write the reframing notes for weak items, citing where in the master file.
6. Test every transferable framing with the one-sentence rule above.
7. Be honest in the recommendations. If the role is a stretch, say so.

## Rules

- Judge coverage against the master content file only, never against what you
  assume the user also knows.
- Never invent evidence to move an item from weak to strong.
- "Transferable" needs a defensible mechanism. A vague analogy is a real gap.
- A high score does not mean "apply". If real gaps cover more than about 30% of
  the P0 requirements, recommend pausing and building the skill first, not
  sending a weak application.
- Each real gap is a finding to report. This skill does not fix it.

## Handoff

The user reads the recommendations and decides. When they say go, run
`.claude/skills/resume-tailor/SKILL.md`.
