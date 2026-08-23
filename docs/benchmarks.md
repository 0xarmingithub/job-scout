# Benchmarks

One comparison, on one task, with a sample size of 20. Read the limitations
before you act on it.

## The question

The scout's whole value is whether its score separates jobs worth applying to
from jobs that are not. Any model will return a number. The question is whether
the number means anything.

## The method

The author had, at the time of the test, 20 job postings with a known human
verdict: for some of them a tailored CV was written and an application was sent;
for the others the posting was read and deliberately skipped. That verdict is
the ground truth. It is not "did they get the job" — it is "did an experienced
person, reading the whole posting, think it was worth their afternoon".

Each model scored all 20 postings from the same profile, with the same prompt,
with no knowledge of the verdict.

The measure is the **separation**: the mean score of the applied-to group minus
the mean score of the skipped group. A model that scores both groups the same
has a separation of zero and is useless, however sensible its individual numbers
look. A bigger separation is a model that can tell the two apart.

Postings are not named here. No job titles, no companies.

## The results

| Model | Separation | Applications scored above 70 |
|---|---|---|
| `gemini:gemini-3.7-flash` | **18.1 points** | — |
| `claude:sonnet` via the Claude Code CLI | 8.4 points | 0 of 7 |

Two things came out of this.

**Gemini 3.7 Flash separated the groups more than twice as well.** 18.1 points
against 8.4. On a 0-100 scale where the threshold sits at 65 or 70, an 8-point
separation is not enough to build a filter on — the two groups overlap so much
that any threshold either sends you everything or nothing.

**The Claude CLI put none of the seven real applications above 70.** Every job
the author actually applied to would have been filtered out. That is the finding
that decided it: not that the scores were lower, but that they were lower in a
way that would have hidden the good jobs.

There was also a speed difference — roughly 14 seconds per posting through the
CLI against about 2 through the API — but that was not the reason for the
switch. Correctness was.

## What this does not tell you

Be careful with all of the above.

- **n = 20.** Seven positives and thirteen negatives. That is small enough that
  a couple of borderline judgements move the numbers noticeably. No confidence
  interval is quoted because with this sample size it would be wide enough to
  make the point on its own.
- **One profile, one country, one field.** A senior infrastructure profile
  searching Denmark. Nothing here says the same ordering holds for a graduate
  designer in Brazil.
- **The ground truth is one person's judgement**, not an outcome. It measures
  agreement with that person, not whether the applications were wise.
- **The CLI path was not tuned.** It flattens the system prompt into a single
  prompt because that is what the CLI accepts, and adds an instruction not to
  use tools. A prompt written for that shape might do better. This measured the
  configuration as shipped, not the model's ceiling.
- **Models change under the same name.** These runs were in August 2026. A
  provider can change what sits behind a model id without renaming it.
- **`grok` and `codex` were never measured on this task at all.** They work.
  Whether their scores mean anything here is unknown.

## Running it yourself

If you have a set of postings with your own verdicts, the comparison is
straightforward:

1. Put the postings in a directory as plain text.
2. Score each one with each model, using the same `profile.yaml`.
3. Take the mean of the group you would apply to, minus the mean of the group
   you would skip.

`job-scout run --dry-run --limit N` scores without recording or sending
anything, which makes it safe to run repeatedly against the same postings while
you compare.

If you do this on a different profile or a different market, a pull request
adding your numbers here would be genuinely useful. State your sample size.
