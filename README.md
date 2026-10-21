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

## What it can do

Only the first three rows are needed. Every other row is optional and switches on
by itself when you set it up. Each says what it does, the command, and where the
detail is.

| | What it does | Command | Detail |
|---|---|---|---|
| **Search** | Twelve sources: LinkedIn, Indeed, Glassdoor, ZipRecruiter and Google through one library; Careerjet; Jobindex by browser; the Danish portals Jobbank, Jobnet and Jobdanmark; `jobindex_cli`, a second route to Jobindex; and Apify, which is paid | `job-scout run` | [configuration.md](docs/configuration.md) |
| **Judge** | A free location filter, a free keyword filter, then a model reads the posting and returns a score, the real gaps and one sentence of reasoning | `job-scout run` | [scoring.md](docs/scoring.md) |
| **Tell you** | A file on disk, Telegram, email, or a webhook for Slack, Discord, Mattermost and others | `job-scout check`, then the first run | [configuration.md](docs/configuration.md) |
| **The week in one message** | The best postings of the last few days, re-read from the database, no model calls | `job-scout roundup` | [roundup.md](docs/roundup.md) |
| **Learn from your results** | One folder per application with a Status line. The scorer is told what converted, and you can ask whether the score predicted anything | `job-scout outcomes`, `calibrate` | [applications.md](docs/applications.md) |
| **Chase what went quiet** | Asks about applications with no result recorded, and shows where applications stop and which gaps keep coming back | `job-scout nudge`, `patterns` | [applications.md](docs/applications.md) |
| **Draft a tailored CV** | Runs a command on the best match, after asking you a few questions on Telegram | `job-scout ask` | [tailoring.md](docs/tailoring.md) |
| **Turn a CV into documents** | Reads a Word, PDF or text CV into `resume.yaml`, fills your own template, builds a PDF, and checks that an applicant tracking system can read it | `job-scout cv` | [cv.md](docs/cv.md) |
| **A second opinion** | Up to four models review a CV against a job description. Opt-in, costs model calls | `job-scout validate` | [configuration.md](docs/configuration.md) |
| **The method** | Twelve skills for AI coding tools: four to set up and tune the scout, eight to take a posting to a tailored CV that claims nothing your records do not support | | [cv-workflow.md](docs/cv-workflow.md) |
| **Keep private things private** | A word list of your own names and employers, checked before anything reaches a public repository | `job-scout privacy` | [privacy.md](docs/privacy.md) |
| **Run itself** | By hand, a systemd timer, GitHub Actions or Docker, with timers for the daily run, the weekly roundup and the question collector | | [setup-systemd.md](docs/setup-systemd.md) |

### Every command

| Command | Use it to | Model calls | Sends a message |
|---|---|---|---|
| `job-scout init <dir>` | Create `config.yaml` and `profile.yaml`. `--from-cv` drafts the profile from your CV, `--with-tailoring` adds the tailoring blocks | With `--from-cv` | No |
| `job-scout check` | See what is configured and what each backend, notifier and source still needs. Run it first when anything is wrong | No | No |
| `job-scout run` | Do a run. `--dry-run --limit 10` scores ten postings and records and sends nothing | Yes, scoring | The digest, unless `--dry-run` |
| `job-scout stats` | See where postings go and what they score | No | No |
| `job-scout calibrate` | Find out whether higher scores really converted better | No | No |
| `job-scout roundup` | Send the best of the last few days. `--dry-run` prints it | No | Yes |
| `job-scout outcomes` | Build the outcomes file from your application folders. `--print` shows it | No | No |
| `job-scout nudge` | Ask about applications with no result recorded. `--dry-run` prints it | No | Yes |
| `job-scout patterns` | Read your application folders together | No | No |
| `job-scout ask` | Collect your answers to a tailoring question, then run your tailoring command. `--status` and `--cancel` | Yes, your command | Yes |
| `job-scout cv ...` | `doctor`, `import`, `convert`, `render`, `build`, `verify`, `example` | `import` only | No |
| `job-scout validate` | Get a second opinion on a CV | Yes | No |
| `job-scout privacy ...` | `init`, `add`, `list --count`, `check` | No | No |

---

## Would you rather not read this?

Hand the job to an AI. Clone the repo, open it in Claude Code, Cursor, Codex,
Copilot or anything else that can run commands, and paste the prompt below. It
asks about your search, then offers every optional feature above one by one,
sets up the ones you pick, proves each one works, and tells you what is on and
what is off. It asks before anything that costs money or sends a message.

<details>
<summary><b>Click to expand the setup prompt, then copy the whole block</b></summary>

````text
You are setting me up with Job Scout, the repository you are in. Your job is not
only to make it run. It is to switch on every part of it that is useful to me,
prove each part works, and leave me knowing what is on and what is off.

READ FIRST, in this order: README.md (the table "What it can do" is your map),
then AGENTS.md. Before you set up a feature, read its guide under docs/. If a
skill exists for the job, read it too: .claude/skills/ has setup-profile,
tune-threshold, debug-run, add-job-source and eight CV skills (jd-analyzer,
gap-analysis, resume-tailor, metrics-auditor, ats-compatibility-check,
cover-letter, interview-prep, master-resume-curator).

Before anything else, check you can actually see the repository's files. If you
cannot, stop and tell me to clone
https://github.com/0xarmingithub/job-scout and open it, then paste this again.

If you cannot run shell commands, say so once, then give me one command at a
time and wait for the output before the next.

Do not paste instructions at me. Interview me, then do the work yourself, then
tell me only the parts I have to do with my own hands.

RULES THAT NEVER BEND

  - Ask before anything that spends money or sends a message, and wait for a
    yes. That means: a real `job-scout run`, `roundup`, `nudge`, `ask`,
    `validate`, `cv import`, `init --from-cv`, and any command that runs a
    model. Say what it will do first. `job-scout check`, `stats`, `calibrate`,
    `patterns`, `outcomes --print`, `nudge --dry-run`, `roundup --dry-run`,
    `cv doctor` and `privacy list --count` are safe to run without asking.
    `run --dry-run` still calls the scoring model, so tell me the limit first.
  - Ask before installing anything outside this project's virtual environment.
  - Never start or enable a timer or a service without my yes.
  - Pick one config directory outside this clone, for example ~/job-search, and
    pass `--config-dir <dir>` to every job-scout command (or tell me to export
    JOB_SCOUT_CONFIG_DIR=<dir>). Without it a command reads this clone's own
    files. Keep everything personal in that directory: config.yaml,
    profile.yaml, .env, my master content file, resume.yaml, voice rules, CV
    output and the private word list. This clone's .gitignore does not know
    those names.
  - Never put a key, token or password in config.yaml or profile.yaml, which get
    committed. When a key is needed, say exactly where to get it, then tell me
    to paste it into <dir>/.env myself, in my own editor. Do not ask me to type
    it into this chat and do not read the file back. `job-scout check` tells you
    whether it is set.
  - Never write a skill, employer, level, date or number about me that I did not
    tell you. A claim I cannot discuss in an interview produces matches I cannot
    use.
  - My CV and my application notes are personal. Before any command sends them
    to a model, name the backend that receives them and let me choose, including
    a local CLI backend that keeps the text on this machine.
  - Never read, print or paste my private word list. `job-scout privacy list
    --count` shows a count and nothing else.

STEP 1. Interview me in two messages. Send the second only after I answer the
first.

  MESSAGE ONE, the search. Ask these five in one message.

  1. What job are you after, and in which city or country?
  2. Where should this run?
       a) on this computer, by hand when I feel like it
       b) on this computer, automatically every day (cron on macOS or Linux,
          Task Scheduler on Windows)
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

  MESSAGE TWO, the features. Show this list. For each one I answer yes, no or
  "tell me more". Put your recommended answer in brackets, based on message one.

  a) Weekly roundup: one message on Friday with the week's best matches. [yes]
  b) Track my applications: one folder per application with a Status line. The
     scorer learns what converted, a nudge asks about the ones that went quiet,
     and a patterns report shows where they stop. [yes if I apply to jobs]
  c) A private word list of my own names and employers, checked before anything
     reaches a public repository. [yes if I keep any repository that could
     become public]
  d) A tailored CV drafted for the day's best match, after the scout asks me a
     few questions on Telegram. Needs Telegram, a model CLI, and something that
     runs every five minutes, so only on paths (b) and (c). [only if I have a CV
     and use Telegram]
  e) The CV pipeline: read my CV into resume.yaml, fill my own template, build a
     PDF, and check an applicant tracking system can read it. [yes if I have a
     CV]
  f) A second opinion on a tailored CV from several models. Costs model calls
     each time. [no, unless I ask]
  g) Extra sources for my country. In Denmark: jobbank, jobnet, jobdanmark and
     jobindex_cli, which need bun and a checkout of the portal CLI repository
     (see docs/configuration.md). Elsewhere: ask which national job boards I use
     and follow the add-job-source skill. Careerjet needs a free key and my
     registered IP; Apify needs a paid token. [yes if it applies]
  h) Config sync: my config folder is a git repository the scout pulls before
     each run. [only on a server]

  Also ask which model I want for each job. They are separate settings and the
  data consequences differ: scoring_model reads every posting (the free Gemini
  tier is the easy option; there is no built-in default); cv_model reads my whole
  CV once; the tailoring command runs on the day's best match;
  cv_validator_models is opt-in, up to four. Recommend a local CLI backend
  (claude:, codex:, grok:) for anything that reads my CV.

STEP 2. Set it up.

  Core:

  - If `job-scout version` fails, follow docs/setup-local.md section 1 (a virtual
    environment, then `pip install -r requirements.txt`) and run everything from
    it. For feature (e) also `pip install -e ".[cv]"`, which PDF and Word CVs
    need.
  - Answer (e) to question 2 means: recommend (b) if their computer is usually
    on, (c) otherwise. Say why in one sentence. Never recommend (d) without
    telling them LinkedIn and Indeed throttle datacenter IP addresses hard, so
    it returns far fewer jobs unless they pay for the Apify source.
  - Follow the guide for the path they chose: docs/setup-local.md,
    docs/setup-systemd.md, docs/setup-github-actions.md or docs/setup-docker.md.
    Run the commands yourself. Do not make them copy anything you can run.
  - Create the config directory with the model I chose:
    `job-scout init <dir> --scoring-model BACKEND:MODEL`. There is no default
    model, and `init` only asks when it runs in a real terminal, which you are
    not in. If the backend needs an API key, I paste it into <dir>/.env.
  - Profile. With a CV: tell them first that this sends the CV text to whichever
    model scoring_model names, and that a local CLI backend keeps it on their
    machine. Let them choose, then run
    `job-scout init <dir> --from-cv <path-to-cv> --force`. Without a CV:
    interview them, and read .claude/skills/setup-profile/SKILL.md first.
  - Write my answers into the config. In <dir>/config.yaml set `searches:` (the
    terms, location, country_indeed and sites) and `notify_threshold`. In
    <dir>/profile.yaml put the deal-breakers: hard_exclude_location_patterns,
    hard_exclude_title_patterns, the candidate's languages and work
    authorisation. Set up the notifier I chose: `file` needs nothing; the others
    follow docs/configuration.md under notifiers.
  - confirmed_gaps is the section that decides whether this is useful, and it
    can never come from a CV. After `--from-cv`, confirmed_gaps and the two
    hard_exclude lists are empty on purpose, so fill all three with me. Ask them
    directly what comes up in job adverts in their field that they have
    genuinely never done. Prompt by category if they stall: frontend, mobile,
    machine learning, data engineering, embedded, security operations, SAP or
    Salesforce, managing people. Push for the specific boundary, so "has
    operated databases, never owned the pipelines" rather than "no data
    engineering".
  - If scoring errors partway through a run on the free tier, set
    `scoring_delay_seconds: 2` in config.yaml.

  Then, for each feature I said yes to, in this order, run the commands
  yourself:

  a) Roundup. `job-scout roundup --days 5 --dry-run --config-dir <dir>` shows the
     message. It is empty until the first real run has recorded postings. The
     roundup also sends the nudge when applications are tracked; `--no-nudge`
     skips it. Scheduling is below.
  b) Applications. Ask where my application folders live, or create
     applications/ in <dir>. Set `applications_dir` in config.yaml. Explain the
     Status words in docs/applications.md, then create one folder with me from
     my most recent application, with a notes.md whose Status line is what
     really happened (`submitted`, `rejected` and so on, not `drafted` unless
     that is true). docs/applications.md says how the company and role are
     read. Run `job-scout outcomes --print --no-prompt --config-dir <dir>` and
     show me the row. If some Status lines contain words that mean something
     other than an employer outcome (for example a step of my own that includes
     the word "interview"), list them under `status_ignore_phrases`. If this
     repository is cloned, `python tools/check_applications.py` checks every
     folder has a Status line.
  c) Private word list. Tell me to run `job-scout privacy init` myself, in my
     own terminal, because the answers are my own identifiers and must not be
     typed into this chat. Afterwards run `job-scout privacy list --count` and
     `job-scout privacy check`.
  d) Tailoring. On path (d) say it is unavailable. Otherwise run
     `job-scout init <dir> --with-tailoring`, read docs/tailoring.md (start with
     "The posting is untrusted"), set `tailor.command` (it ships empty, so
     nothing runs until it is set), the `ask:` block and the Telegram notifier.
     Copy templates/cv/master-content.md to <dir>/master-resume.md and help me
     fill it from my CV; the master-resume-curator skill covers this. Explain
     that the scout stops waiting for answers when I send /done, after 30 quiet
     minutes, or after 24 hours.
  e) CV pipeline. Run `job-scout cv doctor` and install only what is missing,
     and only with my yes (latexmk matters only if I want a PDF from LaTeX).
     For the import, name the backend that will receive the CV and get my yes in
     chat, then run
     `job-scout cv import <my-cv> --out <dir>/resume.yaml --model BACKEND:MODEL --yes --config-dir <dir>`.
     `--yes` is allowed only because I agreed in chat. Read resume.yaml back to
     me and fix mistakes together. Ask for my own template (.tex or .docx). With
     none, `job-scout cv example <dir>` copies a neutral one. Then
     `job-scout cv build <dir>/resume.yaml --template <tpl.tex> --out <dir>/cv.pdf`
     for a PDF, or `job-scout cv render <dir>/resume.yaml --template <tpl.docx> --out <dir>/cv.docx`
     for Word, or `--out <dir>/cv.md` for Markdown, which needs no template.
     Then `job-scout cv verify <dir>/cv.pdf --resume <dir>/resume.yaml`.
     `job-scout cv convert <draft.md>` turns a tailored Markdown draft into a
     resume.yaml.
  f) Second opinion. Set `cv_validator_models` in config.yaml and explain the
     cost. Do not run it unless I ask.
  g) Extra sources. Set `sites:` per search. For the Danish portals set
     JOB_SCOUT_BUN and JOB_SCOUT_PORTAL_CLIS. Say which sources need nothing and
     which need a key.
  h) Sync. The config folder must already be a git repository with a remote;
     I do the commit and push myself. Add the `sync:` block and explain that it
     alerts only when the local copy is behind its upstream.

  Scheduling, for the path I chose. Do nothing here without my yes.

  - Path (b): cron on macOS or Linux (docs/setup-local.md has the line), Task
    Scheduler on Windows. For the roundup, a Friday line such as
    `0 17 * * 5 cd <clone> && .venv/bin/job-scout roundup --days 5 --config-dir <dir>`.
  - Path (c): `sudo bash deploy/install-systemd.sh` enables the daily timer
    immediately, so tell me that and get my yes first. It installs the roundup
    and ask timers switched off. Enable each only for a feature I accepted:
    `sudo systemctl enable --now job-scout-roundup.timer` or
    `sudo systemctl enable --now job-scout-ask.timer`.
  - Path (d): the workflow runs the daily job only. Say plainly that there is no
    roundup and no tailoring questions there.
  - Docker: docs/setup-docker.md. It has no scheduler for the roundup or ask.

STEP 3. Prove it works before you hand back. Show me the output of each that
applies.

  - `job-scout check --config-dir <dir>` until the backend I chose, my notifiers
    and my sources say READY. Backends I did not choose can stay NOT READY.
  - `job-scout run --dry-run --limit 10 --config-dir <dir>`. It searches every
    source before it scores, so it takes minutes: run it in the background and
    read <dir>/data/scout.log. Then read the scores back to me and ask whether I
    agree. My corrections are the real setup step. Use the tune-threshold skill
    to act on them.
  - Once I agree, offer the first real `job-scout run --config-dir <dir>`, in the
    background. A Telegram, email or webhook notifier is proven only by that
    run's digest.
  - After that run: (a) `job-scout roundup --dry-run`. (b)
    `job-scout outcomes --print` and `job-scout nudge --dry-run`. Also
    `job-scout stats`. (c) `job-scout privacy list --count`. (d)
    `job-scout ask --status`. (e) `job-scout cv verify` on the PDF.

STEP 4. Finish with these five short things, and nothing else.

  - A table of the features (a) to (h): on or off, and the one command that
    changes it.
  - The one command I run, or the fact that it now runs itself and when.
  - Where the results appear.
  - What day one looks like: the first run scores every posting currently
    listed, so it takes about fifteen minutes and can return twenty or more
    matches. That is the backlog, not a broken setting. Judge it on day three.
  - How it keeps getting better. On day three, if the matches are wrong, tell me
    to say so and use the tune-threshold skill. After two weeks of recorded
    outcomes, `job-scout calibrate` says whether the score predicted anything.
    If a run returns nothing, use the debug-run skill, then `job-scout check`
    and `job-scout stats`. To add a board, use the add-job-source skill. When I
    apply to something, offer the CV skills in the order the README gives under
    "From a good match to a sent application".
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
job-scout init . --scoring-model gemini:gemini-3.7-flash
job-scout run
```

Get the key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
It is free, takes about a minute, and needs no credit card.

The second line chooses the model that scores postings. There is no default,
because this project does not pick one for you. Results land in
`data/matches.md`. Nothing else is configured, so nothing else happens. No bot, no email, no account anywhere.

Not sure it is set up right? `job-scout check` tells you exactly what is missing
and what to do about it.

Want to see the scoring without recording anything?
`job-scout run --dry-run --limit 5`.

### The week in one message

A daily digest answers "is there anything today". It is bad at "what did I
actually see this week": by Friday the strong Monday posting is four
notifications up the chat and effectively gone.

```bash
job-scout roundup --days 5      # the working week, run on a Friday
```

It re-reads the seen-jobs database and re-scores nothing, so it costs no API
calls and can be run as often as you like. To have it arrive on its own, there
is a Friday timer in `deploy/`. Detail in [docs/roundup.md](docs/roundup.md).

### Knowing what happened to your applications

Keep one folder per application with a `**Status:**` line in its `notes.md`, set
`applications_dir` in `config.yaml`, and the scorer is told what actually
converted for you. `job-scout outcomes` builds the file, `job-scout nudge` asks
about applications that went quiet (it rides along with the weekly roundup), and
`job-scout patterns` shows where your applications stop and which requirements
keep coming back as a gap. Detail in [docs/applications.md](docs/applications.md).

If you work in a repository that might become public, `job-scout privacy init`
builds a private word list of your own names and employers, kept on your machine
and never printed. Detail in [docs/privacy.md](docs/privacy.md).

### Doing something with the best one

Optional, off unless you ask for it. The scout can run a command on the
match it rates highest, usually a model that writes a tailored CV, and send
you what it produces:

```bash
job-scout init ~/job-search --with-tailoring
```

It asks you two or three questions on Telegram first, because a model
writing from your profile alone produces something plausible and slightly
wrong. With no `tailor:` block in config.yaml none of this exists and a run
behaves exactly as it did before. Detail in [docs/tailoring.md](docs/tailoring.md).

Whatever it writes is a draft, in plain Markdown, not a finished document.
[`job-scout cv`](docs/cv.md) turns that draft into a real `.tex`, `.docx`, or
plain-text file, using a template you already have.

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
| Optional model features | `init --from-cv`, `cv import`, `validate` and tailoring each make model calls, and only when you run them. On a CLI backend they use your subscription, not a per-token bill. |

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
| **Danish portals** | `jobbank`, `jobnet`, `jobdanmark` and `jobindex_cli`, with a detail call for each description. Denmark only | bun, and a checkout of the portal CLI repository ([configuration.md](docs/configuration.md)) |
| **JobIndex by browser** | `jobindex`, a second route to jobindex.dk. Measured against `jobindex_cli`, the CLI route found more and parsed companies more reliably | Playwright and a headless Chromium. Denmark only |
| **Careerjet source** | A licensed aggregator API across many countries | A free partner key, plus registering your IP |
| **Apify source** | Scraping run on someone else's infrastructure, with proxies | A paid API token |
| **Application tracking** | The scorer learns what converted. `outcomes`, `nudge` and `patterns` | One folder per application with a Status line (`applications_dir`), or a three-column `outcomes.csv` |
| **Tailoring and questions** | A tailored CV drafted for the day's best match, after asking you | A model CLI, Telegram, and a few minutes answering on your phone |
| **The CV pipeline** | `job-scout cv`: resume.yaml, your own template, a PDF, an ATS text check | Nothing for Markdown or Word. `latexmk` for a PDF from LaTeX. `cv import` makes one model call |
| **Second opinion** | `job-scout validate`, up to four models | Model calls, each time you run it |
| **Private word list** | `job-scout privacy` | Answering its questions once |
| **Scheduling** | It runs without you | A systemd timer, a cron line, or GitHub Actions |
| **Telegram / email / webhook** | Results on your phone instead of in a file | Five minutes each |
| **Skills for AI coding tools** | Guided setup, tuning and debugging, and the CV workflow, in [.claude/skills/](.claude/skills/) | Nothing. Every skill is plain Markdown with manual steps too |

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
| `gemini:gemini-3.7-flash` | `google-genai`, `GOOGLE_API_KEY` | Free tier. The easy option; there is no built-in default. |
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

### What keeps the data honest

- **Cleaning.** Invisible characters in a posting are removed and counted. Words
  that mix Latin letters with Cyrillic or Greek ones, a common look-alike trick,
  are flagged. A flagged posting is still scored, and the flag travels with it.
- **Source health.** A source that returned jobs before and then nothing for
  three runs in a row, or that returns output that looks broken (no company, HTML
  in titles), raises an alert. A rate limit is reported as a rate limit, not as a
  broken source.
- **Duplicates.** One advert on several boards is kept once, from the board
  earlier in `source_priority`. A posting you have seen never reaches the scorer
  again, and near copies of a posting you already have are skipped.
- **Secrets.** Everything a notifier sends passes through a step that strips
  credentials, because error text routinely contains the token that caused it.

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

## From a good match to a sent application

Optional. One path, with the command or skill for each step. Every step also
has manual instructions in its guide.

1. **A match arrives.** With tailoring set up, the scout asks you a few
   questions and drafts a Markdown CV for the best one
   ([tailoring.md](docs/tailoring.md)).
2. **Check it against your records.** The skills in
   [.claude/skills/](.claude/skills/) work in this order: `jd-analyzer`,
   `gap-analysis`, `resume-tailor`, `metrics-auditor` and, if you want a human
   voice pass, the third-party [humanizer](https://github.com/blader/humanizer).
   Then `cover-letter` and `interview-prep` when you need them. Blank templates
   for your master content file and voice rules are in
   [templates/cv/](templates/cv/).
3. **Make the document.** `job-scout cv render` or `build` fills your own
   template ([cv.md](docs/cv.md)).
4. **Check what an applicant tracking system will read.**
   `job-scout cv verify`, and the `ats-compatibility-check` skill.
5. **Get a second opinion.** `job-scout validate --jd jd.md --cv cv.md --output
   report.md` asks up to four models. Opt-in, and never part of the daily run.
   Set `cv_validator_models` in `config.yaml`, or choose when prompted.
6. **Check before anything goes public.** `job-scout privacy check`.
7. **Record what happened.** Put the result in the application's `Status:`
   line. The scorer reads it on the next run.

The method, and the reason for each step: [docs/cv-workflow.md](docs/cv-workflow.md).

## Documentation

| | |
|---|---|
| [Getting started from nothing](docs/getting-started.md) | No Python, no terminal experience. Start here. |
| [Outside services](docs/external-services.md) | Every account and key, what it costs, how to get it |
| [Configuration reference](docs/configuration.md) | Every field in `config.yaml` and `profile.yaml` |
| [How scoring works](docs/scoring.md) | The three tiers, the prompt, tuning the threshold, and `job-scout calibrate` for checking whether the score predicted anything |
| [Benchmarks](docs/benchmarks.md) | Which model actually discriminates, and the sample size |
| [Weekly roundup](docs/roundup.md) | One message for the week, and the Friday timer that sends it |
| [Tailoring](docs/tailoring.md) | Running a command on the day's best match, and asking you first |
| [Tracking applications](docs/applications.md) | One folder per application, the Status words, `outcomes`, `nudge`, `patterns` and `sync` |
| [Your private word list](docs/privacy.md) | `job-scout privacy`: names and employers that must never reach a public repository |
| [Adding a job source](docs/adding-a-job-source.md) | About 40 lines of work |
| [Adding a notifier](docs/adding-a-notifier.md) | About 30 |
| [Troubleshooting](docs/troubleshooting.md) | Start here when it returns nothing. `job-scout stats` is the first command to run |
| [Examples](examples/) | A complete Denmark setup |
| [The CV pipeline](docs/cv.md) | `job-scout cv`: turn a CV you already have into `resume.yaml`, fill your own template, compile a PDF, and check an applicant tracking system can read it |
| [The CV method](docs/cv-workflow.md) | The workflow behind the skills, and why each step exists |
| [AGENTS.md](AGENTS.md) | Instructions for AI coding tools. Not Claude-specific. |
| [Contributing](CONTRIBUTING.md) | |

---

## What is shipped, and what is not

The CV side that this file once listed as "coming" now exists: the
[skills](.claude/skills/), the [templates](templates/cv/), the
[method](docs/cv-workflow.md) and [`job-scout cv`](docs/cv.md). Limits worth
knowing:

- One neutral CV template ships. Bring your own for anything you send.
- `cv import` is a model reading your CV. Read the draft it writes.
- The skills are written for Claude Code and are plain Markdown, so any tool can
  follow them. Nothing about them runs unattended.
- The Grok and Codex scoring backends have never been calibrated for this task.

Not planned: a web interface, a hosted version, or anything that stores your
profile on someone else's machine.

---

## Licence

MIT. See [LICENSE](LICENSE).

Job boards change their markup, their rate limits and their terms whenever they
like. If a source stops returning anything, that is usually why. Start at
[docs/troubleshooting.md](docs/troubleshooting.md).
