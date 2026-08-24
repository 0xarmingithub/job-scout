# Job Scout

A job-hunting agent that runs once a day without you.

It searches several job boards, throws away everything it has already shown you,
scores every remaining posting from 0 to 100 against a written profile of you,
and sends you the good ones.

The scoring is the part worth reading about. A free keyword filter kills the
obvious mismatches first. Then a language model reads the full posting and
returns a structured verdict: a score, whether the job is disqualified outright
by a language or work-permit requirement, which of your skills actually match,
which gaps are real, and one sentence of reasoning.

**The profile is a plain YAML file.** Your skills, the roles you want, the things
you genuinely cannot do, the places you will not commute to. That file is
compiled into the prompt. Change the file and you change what the agent looks
for. There is no code to edit.

---

## Would you rather not read this?

Hand the job to an AI. Clone the repo, open it in Claude Code, Cursor, Codex,
Copilot or anything else that can run commands, and paste the prompt below. It
asks you five questions and then does the setup itself.

<details>
<summary><b>Click to expand the setup prompt, then copy the whole block</b></summary>

````text
You are setting me up with Job Scout, the repository you are in. Read README.md
first, then the setup guide under docs/ for whichever path I pick.

Before anything else, check you can actually see the repository's files. If you
cannot, stop and tell me to clone
https://github.com/0xarmingithub/job-scout and open it, then paste this again.

If you cannot run shell commands, say so once, then give me one command at a
time and wait for the output before the next.

Do not paste instructions at me. Interview me, then do the work yourself, then
tell me only the parts I have to do with my own hands.

STEP 1. Ask me these five questions in one message and wait for my answers.

  1. What job are you after, and in which city or country?
  2. Where should this run?
       a) on this computer, by hand when I feel like it
       b) on this computer, automatically every day
       c) on a small always-on server, so it runs whether or not I am here
       d) on GitHub's machines, because I do not want a server
       e) I do not know, recommend one
  3. Do you have your CV as a file? Give me the path if so. It saves you about
     half an hour.
  4. How should it tell you about matches? A file on disk needs no setup and is
     the sensible default. Telegram, email, Slack and Discord all work and take
     about five minutes each.
  5. Is there anything that rules a job out for you no matter how well it fits?
     Common ones: a language you do not speak well enough to work in, needing
     visa sponsorship, a security clearance you do not have, places you will not
     commute to.

STEP 2. Set it up.

  - Answer (e) to question 2 means: recommend (b) if their computer is usually
    on, (c) otherwise. Say why in one sentence. Never recommend (d) without
    telling them LinkedIn and Indeed throttle datacenter IP addresses hard, so
    it returns far fewer jobs unless they pay for the Apify source.
  - Follow the guide for the path they chose: docs/setup-local.md,
    docs/setup-systemd.md, docs/setup-github-actions.md or docs/setup-docker.md.
    Run the commands yourself. Do not make them copy anything you can run.
  - Profile. With a CV: `job-scout init <dir> --from-cv <path-to-cv>`. Tell them
    first that this sends the CV text to whichever model scoring_model names,
    and that a local CLI backend keeps it on their machine. Let them choose.
    Without a CV: interview them, and read .claude/skills/setup-profile/SKILL.md
    first.
  - confirmed_gaps is the section that decides whether this is useful, and it
    can never come from a CV. Ask them directly what comes up in job adverts in
    their field that they have genuinely never done. Prompt by category if they
    stall: frontend, mobile, machine learning, data engineering, embedded,
    security operations, SAP or Salesforce, managing people. Push for the
    specific boundary, so "has operated databases, never owned the pipelines"
    rather than "no data engineering".
  - Never write a skill, employer, level or date into profile.yaml that they did
    not tell you. A profile with a skill they cannot discuss in an interview
    produces matches they cannot use.
  - Stop and ask when you need an API key or a password. Say exactly where to
    get it. Never put one in config.yaml or profile.yaml; those get committed.

STEP 3. Prove it works before you hand back.

  - `job-scout check` until everything says READY.
  - `job-scout run --dry-run --limit 10`, then read the scores back to them and
    ask whether they agree. Their corrections are the real setup step.

STEP 4. Finish with four short things, and nothing else.

  - What you set up, in two sentences.
  - The one command they run, or the fact that it now runs itself and when.
  - Where the results appear.
  - What day one looks like: the first run scores every posting currently
    listed, so it takes about fifteen minutes and can return twenty or more
    matches. That is the backlog, not a broken setting. Tell them to judge it on
    day three.
````

</details>

Everything that prompt does can be done by hand. The rest of this file, and
[docs/](docs/), is the manual version.

---

## See it work in three minutes

**No Python, or not a developer?** Start at
[docs/getting-started.md](docs/getting-started.md) instead. It covers
opening a terminal, installing Python on each operating system, and
getting the free key, then comes back here.

This runs against a fictional candidate, a senior platform engineer in Berlin,
so you can watch it score real postings before writing a word about yourself.

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

echo "GOOGLE_API_KEY=your-key-here" > .env       # free, from the link below
job-scout run
```

Get the key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
It is free, takes about a minute, and needs no credit card.

Results land in `data/matches.md`. Nothing else is configured, so nothing else
happens. No bot, no email, no account anywhere.

Not sure it is set up right? `job-scout check` tells you exactly what is missing
and what to do about it.

Want to see the scoring without recording anything?
`job-scout run --dry-run --limit 5`.

### Then point it at yourself, from your CV

Most of what belongs in `profile.yaml` is already written down in your CV, so
let the scout read it:

```bash
pip install -e ".[cv]"                      # only for .pdf and .docx
job-scout init . --from-cv ~/my-cv.pdf --force
```

It fills in your roles, skills, languages and keywords, and writes "not stated"
instead of guessing at anything the CV does not say.

It deliberately leaves `confirmed_gaps` empty, and that is the section that
decides whether any of this is useful. Your CV lists what you have done. It
cannot say what you cannot do, and a wrong entry there quietly caps good jobs at
40. Write that part yourself. It takes five minutes and it is the highest-value
five minutes in the whole setup.

**This sends your CV to a model.** With the default backend that means Google's
API, and a CV carries your name, address, phone number and employment history.
If you would rather it did not leave your machine, point `scoring_model` at a
CLI backend you run locally (`claude:`, `grok:`, `codex:`) or fill in
`profile.yaml` by hand. Nothing is stored anywhere by the scout either way.

---

## What it costs

Nothing, in the normal case.

| | |
|---|---|
| Scoring | Google's free tier covers it. At the time of writing it allows 1,500 model calls a day. A steady-state run makes 30 to 60. |
| Hosting | The author's runs on an Oracle Cloud always-free VM. A laptop and `cron` works too. |
| Job boards | LinkedIn, Indeed and JobIndex are free. Careerjet's partner API is free. Apify is paid and optional. |

**Day one costs several times more than day two.** The database starts empty, so
every posting is new and every one gets scored. Two runs of the shipped config,
measured back to back:

| | Run 1 | Run 2 |
|---|---|---|
| Model calls | 178 | 27 |
| Matches | 23 | 0 |
| Wall clock | 882 s | 351 s |

The model bill collapses; the clock does not. Most of a run is spent asking the
job boards for results, not scoring them, so run time tracks how many search
terms you have rather than how much is new.

If you outgrow the free tier, Gemini Flash costs roughly **$0.12 a day** at 60
postings, about 2,000 input tokens each at $0.75 per million as of August 2026.
An estimate; check
[Google's pricing](https://ai.google.dev/gemini-api/docs/pricing) for the real
number.

### What a real run looks like

Numbers from the author's deployment, which searches Denmark across four
sources with eight search terms:

| | |
|---|---|
| Run on 2026-08-22 | 736 seconds end to end |
| New postings recorded | 57 |
| Postings sent | 3 |
| Schedule | daily at 12:00 Europe/Copenhagen |
| Host | Oracle Cloud always-free VM |

Three a day is the point. A tool that sends you forty is a tool you stop reading.

---

## What you need, and what you do not

### Required

1. **Python 3.10 or newer.** Checked, not guessed: every source file is parsed
   against the 3.10 grammar in the test suite, and CI runs 3.10 through 3.13.
2. **One scoring backend.** Gemini's free tier is the documented easy path. Any
   one of five works. See below.
3. **`profile.yaml` filled in.** A complete fictional one ships, so a first run
   works before you have written anything. When you make it yours,
   `job-scout init . --from-cv ~/cv.pdf --force` drafts most of it from your CV.
4. **`config.yaml` with at least one search.** One ships.
5. **One notifier.** The file writer needs no credentials and is the default.

That is the whole list. Everything below this line is optional and every one of
them is independently skippable.

### Optional

| | What it adds | What it costs you |
|---|---|---|
| **JobIndex source** | jobindex.dk, for Danish postings that reach no other board | Playwright and a headless Chromium. Denmark only. |
| **Careerjet source** | A licensed aggregator API across many countries | A free partner key, plus registering your IP |
| **Apify source** | Scraping run on someone else's infrastructure, with proxies | A paid API token |
| **`outcomes.csv`** | The scorer learns what actually converted for you | Keeping a three-column CSV up to date |
| **Scheduling** | It runs without you | A systemd timer, a cron line, or GitHub Actions |
| **Telegram / email / webhook** | Results on your phone instead of in a file | Five minutes each |
| **Claude Code skills** | Guided setup and tuning inside an AI coding tool | Nothing. Every workflow also has manual steps |

None of these can break a run by being absent. That is enforced by the tests,
not just claimed here: `tests/test_run.py` runs the whole pipeline with no
Playwright, no Careerjet key, no Apify token and no `outcomes.csv`, and asserts
it finishes cleanly.

### The five scoring backends

Pick one with `scoring_model: "backend:model"` in `config.yaml`. You install
what your choice needs and nothing else. Choosing one you have not set up
produces a sentence telling you what to install, never a stack trace.

| Backend | Needs | Notes |
|---|---|---|
| `gemini:gemini-3.7-flash` | `google-genai`, `GOOGLE_API_KEY` | Free tier. The documented default. |
| `openrouter:google/gemini-3.7-flash` | `requests`, `OPENROUTER_API_KEY` | Pay per token, many models. |
| `claude:sonnet` | the `claude` CLI | Runs on your subscription. |
| `grok:grok-4` | the `grok` CLI | Never calibrated for this task. |
| `codex:gpt-5` | the `codex` CLI | Never calibrated for this task. |

The three CLI backends can also run on another machine over SSH, which is how
you use a subscription CLI from a VM that has no browser.

Run `job-scout check` to see the state of all five at once.

---

## How the scoring works

Three tiers, cheapest first. Most postings never reach the part that costs money.

```
     postings from every source
              │
   ┌──────────▼──────────┐
   │ Tier 0  location    │  location matches hard_exclude_location_patterns
   └──────────┬──────────┘  → dropped, costs nothing
              │
   ┌──────────▼──────────┐
   │ Tier 1  keywords    │  no keyword hit, or title matches an exclusion
   └──────────┬──────────┘  → dropped, costs nothing
              │
   ┌──────────▼──────────┐
   │ Tier 2  the model   │  reads the posting, returns a structured verdict
   └──────────┬──────────┘  → the only step that costs money
              │
     scored, and above your threshold → sent
```

The model returns JSON, not prose:

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

`language_barrier` and `work_authorization_barrier` are hard rejections. A
perfect skills match that requires fluent Danish, or citizenship you do not
have, scores zero. That is right, and it is what a keyword filter cannot do.

The single most valuable thing in your profile is `confirmed_gaps`: a written
list of what you genuinely cannot do. Anyone can list skills. Writing down the
gaps is what stops the scorer sending you a machine-learning role because it saw
the word "Python". If a posting's core work needs one of them, the score is
capped at 40 however well everything else lines up.

Full detail in [docs/scoring.md](docs/scoring.md). Model comparisons, with the
sample sizes, in [docs/benchmarks.md](docs/benchmarks.md).

---

## Running it for real

Four ways, in the order most people should try them.

| Path | Good for | Guide |
|---|---|---|
| **By hand** | Trying it, tuning the threshold | [docs/setup-local.md](docs/setup-local.md) |
| **systemd timer on a VM** | The one that actually works long-term | [docs/setup-systemd.md](docs/setup-systemd.md) |
| **GitHub Actions** | No machine to run it on | [docs/setup-github-actions.md](docs/setup-github-actions.md) |
| **Docker** | You already run everything this way | [docs/setup-docker.md](docs/setup-docker.md) |

No machine to put it on? [docs/setup-systemd.md](docs/setup-systemd.md) walks
through getting a free Oracle Cloud VM from signup to first run, including the
two traps: which shape to pick, and the fact that Oracle reclaims Always Free
instances it decides are idle.

One warning about GitHub Actions, because it looks like the easiest path and is
not. A runner's IP address is shared and recycled between everybody's jobs, so
you inherit blocks you did not cause and help cause the next one. On top of
that, LinkedIn and Indeed throttle datacenter addresses hard. **Use the Apify
source there**, which does the collection on its own machines through its own
proxies. It costs money.
[docs/setup-github-actions.md](docs/setup-github-actions.md) has the numbers.

### Keeping your profile out of this repository

Your `config.yaml` and `profile.yaml` do not have to live in the clone. Point at
them:

```bash
job-scout run --config-dir ~/job-search --data-dir /var/lib/job-scout
```

or set `JOB_SCOUT_CONFIG_DIR` and `JOB_SCOUT_DATA_DIR`. That is how you keep a
private profile in a private repository while pulling updates here.

---

## Terms of service, plainly

**LinkedIn and Indeed both prohibit automated scraping in their terms.** Using
those sources is your decision and your risk. They are on by default because
they are what actually produces results, and this repo is not going to
pretend otherwise. You should still know what you are agreeing to when you
leave them on.

The lower-risk paths, if that matters to you:

- **Careerjet** is a licensed partner API. You are querying an interface built
  to be queried.
- **Apify** runs the collection on its own platform under its own agreements.
  It costs money.

You can drop `linkedin` and `indeed` from every `sites:` list and run entirely
on those two. Nothing else changes.

Whatever you use: keep it to one run a day, keep `results_wanted` sane, and do
not point this at a company you are trying to annoy.

---

## Documentation

| | |
|---|---|
| [Getting started from nothing](docs/getting-started.md) | No Python, no terminal experience. Start here. |
| [Outside services](docs/external-services.md) | Every account and key, what it costs, how to get it |
| [Configuration reference](docs/configuration.md) | Every field in `config.yaml` and `profile.yaml` |
| [How scoring works](docs/scoring.md) | The three tiers, the prompt, tuning the threshold |
| [Benchmarks](docs/benchmarks.md) | Which model actually discriminates, and the sample size |
| [Adding a job source](docs/adding-a-job-source.md) | About 40 lines of work |
| [Adding a notifier](docs/adding-a-notifier.md) | About 30 |
| [Troubleshooting](docs/troubleshooting.md) | Start here when it returns nothing. `job-scout stats` is the first command to run |
| [Examples](examples/) | A complete Denmark setup |
| [AGENTS.md](AGENTS.md) | Instructions for AI coding tools. Not Claude-specific. |
| [Contributing](CONTRIBUTING.md) | |

---

## What is coming

**Release 2, the CV toolkit.** Planned, not built. The same profile that scores
a posting can tailor a CV against it: analyse the job description, map it onto a
master résumé, find the real gaps, draft a cover letter, check the result parses
in an applicant tracking system, and prepare interview answers.

That work exists and runs daily, but it is written around a specific LaTeX CV
structure and a master résumé file that has no public equivalent. Shipping it
now would mean shipping something half-working, so it waits until the CV side
has been made general.

Not planned: a web interface, a hosted version, or anything that stores your
profile on someone else's machine.

---

## Licence

MIT. See [LICENSE](LICENSE).

Job boards change their markup, their rate limits and their terms whenever they
like. If a source stops returning anything, that is usually why. Start at
[docs/troubleshooting.md](docs/troubleshooting.md).
