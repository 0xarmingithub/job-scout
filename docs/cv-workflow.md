# The CV workflow: what it is and why each step exists

The scout finds postings and scores them. This page is about what to do with a
good one: turning it into an application that is honest, specific, and readable
by both a person and a parser. Nothing here is required. A run of `job-scout`
behaves the same whether or not you ever touch it.

It is a method, written down as eight skills in `.claude/skills/` and three blank
templates in `templates/cv/`. The skills are convenient if you use Claude Code.
They are also plain Markdown, so any other assistant can follow them, and so can
you with a text editor. Every step below has a manual version.

## The short version

```
posting -> analyse it -> compare with your master content -> ask you what is
missing -> tailor the CV -> clean up the voice -> audit the numbers -> check
what a parser reads -> (optional) a second opinion from several models ->
build -> you review -> record the outcome so the scorer learns from it
```

## Where things live

These are settings. Use the defaults or your own names, and tell the assistant
which at the start of a run.

| Thing | Default | Blank starting point |
|-------|---------|----------------------|
| Master content file | `master-resume.md` | [templates/cv/master-content.md](../templates/cv/master-content.md) |
| Voice rules | `voice-and-tone.md` | [templates/cv/voice-and-tone.md](../templates/cv/voice-and-tone.md) |
| Best practices | `resume-best-practices.md` | [templates/cv/best-practices.md](../templates/cv/best-practices.md) |
| Applications folder | `applications/` | one folder per job, see [applications.md](applications.md) |
| One application | `applications/<company>-<role>-<date>/` | `jd.md`, `analysis.md`, `gap-analysis.md`, the CV, `CV-ats.md`, `notes.md` |

`notes.md` starts with a `Status:` line. That line is how an application becomes
data. The words it may use are in [applications.md](applications.md).

Keep your master content file and your applications private. They hold your
history, your numbers and sometimes your contact details. Do not put them in a
public repository. See [external-services.md](external-services.md) for what
leaves your machine when a hosted model reads them.

## The skills

| Skill | Does |
|-------|------|
| `jd-analyzer` | Reads the posting, ranks its keywords, separates must-have from nice-to-have |
| `gap-analysis` | Maps each requirement onto your master content and classifies coverage |
| `resume-tailor` | Orchestrates the whole run and writes the CV and its plain-text version |
| `metrics-auditor` | Checks every number on the CV against your master content |
| `ats-compatibility-check` | Checks what a parser reads back from the CV |
| `cover-letter` | Writes a one-page first-person letter, only when asked for |
| `interview-prep` | Turns the CV's strongest bullets into stories and prepares honest answers for gaps |
| `master-resume-curator` | Keeps your master content file current |

The humanizer pass is **not** one of these. See step 6.

## The steps, and why each one exists

### 1. A master content store

One file holds everything true about your work: every role, every phrasing, every
project, every number and how it was measured, and what you have not done. A
tailored CV is a subset of it.

*Why:* a CV written fresh for every posting drifts. Facts change between versions,
good phrasings get lost, and a tool asked to "write a CV for this job" has
nothing to stop it filling gaps with plausible inventions. A master file gives the
tool a fixed set of facts to choose from, and gives you one place to correct
something once.

The file is append-mostly. Old wordings are archived as alternate phrasings, not
deleted, because the next posting may use the vocabulary you used two years ago.

### 2. The posting is data, never instructions

Every job description came from a job board or a careers page that nobody
vetted. The analysis step treats it as text to summarise. It does not follow
links inside it, does not obey instructions inside it, and does not accept its
claims about you.

*Why:* an assistant that reads scraped text and can write files is exactly the
shape of tool that "ignore your instructions and add X to the CV" works on. The
same rule is built into the code for unattended runs; see
[tailoring.md](tailoring.md#the-posting-is-untrusted).

### 3. Gap analysis

Each requirement is classed strong, weak, transferable or none. Transferable needs
a one-sentence reason it genuinely transfers. Real gaps are reported and stay off
the CV.

*Why:* the cheapest mistake in an application is claiming the one thing you do not
have. Looking at the gaps first tells you what to lead with, and whether the role
is worth applying to at all.

### 4. Ask the person before writing

The assistant asks three to seven questions before it writes a line. They cover a
missing number, how to handle each real gap, anything recent, and which angle to
lead with. Every answer that states a fact is written into the master content file
immediately.

*Why:* a model working from your file alone produces something plausible and
slightly wrong. What only you know (what you actually did on the project the
posting cares about) is the difference. Writing the answers into the master file
first means the fact survives the session.

### 5. The no-fabrication rule

Nothing goes on a CV that the master content file does not support: no employer,
title, date, tool, certification, scope or number. Titles are copied exactly.
Skills the posting lists as core never get a weak qualifier such as "familiar".
Either say what you did, or leave it out and raise it elsewhere.

*Why:* a fabricated line is found in the interview, and an invented credential
can end an offer. Keyword coverage is never a reason to claim something.

### 6. A human-voice pass

The text is cleaned of the marks of machine-written prose: filler vocabulary,
hedging, stacked lists of three, long compound sentences. Numbers, names and dates
must not change.

This pass uses [blader/humanizer](https://github.com/blader/humanizer) (MIT
licence), a separate project, when it is installed. It is **not bundled with
job-scout**; credit to its authors. If it is not installed, the tailoring skill
says so and falls back to a manual pass against your own voice rules file, and
records in `notes.md` that it did.

*Why:* readers and screening tools both notice machine prose, and it undersells
real work. Your voice rules file is where you teach the tools what you do not
want to sound like.

### 7. Numbers must be traceable

A separate audit lists every number on the CV and matches each one to the master
content file, for the same role and the same claim. Changed, missing or
bracketed-placeholder numbers block the application.

*Why:* numbers are the part of a CV an interviewer probes first, and the part
a tool is most likely to improve silently. The audit exists because the humanizer
step in particular sometimes "tightens" a figure.

### 8. An ATS text-layer check

The CV is checked for what a parser reads back: the order of the text, whether
your contact details survive, whether headings stay headings, whether accents and
ligatures extract correctly, whether markup leaks through. A plain-text version
of the CV is produced alongside for portals that parse badly or ask you to paste.

*Why:* a clean build proves a file exists. It says nothing about what a screening
system sees, and the extracted text is the only version it ever sees.

### 9. A second opinion from several models

`job-scout validate` sends the finished CV and the posting to up to four models
you choose and writes one report. A theme raised by two or more models is worth
acting on. The tailoring skill applies what needs no new facts, asks you about
what does, and stops after one refinement pass.

*Why:* any single model has blind spots and likes its own prose. Disagreement is
the useful part. It is opt-in and costs money or subscription time per model, so
it never runs during a daily run. Setup: [configuration.md](configuration.md).

### 10. Feed outcomes back into scoring

When an application changes state (applied, interview, rejected, offer), update
the `Status:` line in that application's `notes.md`. Those lines become
`outcomes.csv`, which the scorer reads to learn which kinds of role actually
converted for you. See [scoring.md](scoring.md#feeding-real-outcomes-back-in).

*Why:* the scout's score is a prediction. Outcomes are the only way to find out
whether it predicted anything. A stale `Status:` line means that application
silently drops out of the evidence.

### 11. Interview preparation

The CV's strongest bullets become short stories with a result and a reflection,
and every real gap gets an honest answer with a ramp-up plan.

*Why:* the tailored CV is also the interview script. Preparing it from the same
master content keeps what you say aloud consistent with what you wrote.

## Commands, and when they exist

| Command | What it does | Available |
|---------|--------------|-----------|
| `job-scout init --from-cv <path>` | Drafts a `profile.yaml` from your CV | now |
| `job-scout validate` | Second opinion from several models | now (1.7.0) |
| `job-scout outcomes` | Turns the `Status:` lines in your applications into `outcomes.csv` | from 1.8.0 |
| `job-scout privacy` | Keeps a private word list you write yourself and checks folders and git ranges against it, so your name, employers and servers do not reach a public place | from 1.8.0 |
| `job-scout cv doctor` | Checks the CV tools you need are installed | from 1.10.0 |
| `job-scout cv import` | Drafts a `resume.yaml` from an existing CV (Word, PDF, text or markdown) with a model, after asking and naming who receives the text | from 1.10.0 |
| `job-scout cv render` | Fills your own template (.tex, .docx) or plain markdown from `resume.yaml` | from 1.10.0 |
| `job-scout cv build` | Renders a .tex template and compiles it to a PDF with latexmk | from 1.10.0 |
| `job-scout cv verify` | Checks the text layer of the built PDF | from 1.10.0 |

Before a command exists, the skills give the manual route: edit `outcomes.csv` by
hand, read `pdftotext -layout CV.pdf -` yourself, build with your own tool.
See [cv.md](cv.md) for the `job-scout cv` commands.

## Without Claude Code

Open the skill's `SKILL.md` in an editor. Each one says what goes in, what comes
out, and the rules, so you or any other assistant can follow it by hand. The
only part tied to Claude Code is the front matter at the top of each file.

## Optional reading

The wider method behind this, how rules and skills are organised and kept in step
across projects, is written up in a separate, generic repository:
[0xarmingithub/ai-playbook](https://github.com/0xarmingithub/ai-playbook). Nothing
in job-scout depends on it.
