# Start here if you are not a developer

Everything else in this repository assumes you have Python and know what a
terminal is. This page does not.

Be honest with yourself about one thing first: this is a command-line tool. There
is no window with buttons. You will type a few commands, edit a text file, and
that is the whole experience. If that is fine, this takes about twenty minutes
and you never have to touch it again.

If you would rather not, there are two easier routes:

- **Hand it to an AI.** Copy the prompt at the top of the
  [README](../README.md#would-you-rather-not-read-this) into Claude Code, Cursor,
  Codex or Copilot with this repository open. It asks you five questions and does
  the rest.
- **Ask someone.** Anyone who writes software will get this running in ten
  minutes.

## 1. Open a terminal

| | |
|---|---|
| **Windows** | Press Start, type `powershell`, press Enter. |
| **macOS** | Press Cmd and Space, type `terminal`, press Enter. |
| **Linux** | You know where it is. |

A window with a text prompt appears. Everything below gets typed there, one line
at a time, pressing Enter after each.

## 2. Check for Python

Type this and press Enter:

```
python --version
```

You want **3.10 or higher**. Three outcomes:

**It printed something like `Python 3.12.4`.** Good. Skip to step 4.

**It printed `Python 3.9.x` or lower.** Too old. Install a newer one, step 3.

**It said "not recognized", "command not found", or opened the Microsoft
Store.** Python is not installed. Step 3.

On some Macs and Linux boxes the command is `python3` rather than `python`. Try
that before assuming it is missing. If `python3 --version` works, use `python3`
everywhere below.

## 3. Install Python

**Windows.** In the same PowerShell window:

```
winget install Python.Python.3.12
```

Then **close the window and open a new one**, or the change will not have taken
effect. Check with `python --version`.

If `winget` is not available, download the installer from
[python.org/downloads](https://www.python.org/downloads/). During the install,
**tick "Add python.exe to PATH"** on the first screen. People miss this and then
nothing works.

**macOS.** If you have Homebrew:

```
brew install python@3.12
```

If you do not, get the installer from
[python.org/downloads](https://www.python.org/downloads/) and run it.

**Ubuntu or Debian.**

```
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

`python3-venv` is a separate package on these systems and you will need it. The
error you get without it is not helpful.

**Fedora.**

```
sudo dnf install -y python3 python3-pip git
```

## 4. Check for git

```
git --version
```

If that fails: `winget install Git.Git` on Windows, `brew install git` on macOS,
or the apt or dnf line above on Linux. On Windows, close and reopen the terminal
afterwards.

## 5. Get a free API key

The scout needs one model to read job postings for you. Google gives one away.

1. Open [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Sign in with a Google account.
3. Click **Create API key**.
4. Copy it. It starts with `AIza`.

No credit card, and the free allowance is far more than a once-a-day run uses.

Keep that key somewhere for a minute. Treat it like a password.

## 6. Install and run

Four commands. Copy them one at a time.

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
python -m venv .venv
```

Then activate the environment. **This line is different on Windows:**

| | |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| macOS or Linux | `. .venv/bin/activate` |

If PowerShell refuses with something about execution policies, run this once and
try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then:

```bash
pip install -r requirements.txt
```

That takes a couple of minutes and prints a lot. Ignore it unless it ends with
an error.

Now save your key. Replace `AIza-your-key-here` with the real one:

```bash
echo "GOOGLE_API_KEY=AIza-your-key-here" > .env
```

Check it worked:

```bash
job-scout check
```

You want to see `READY` next to the scoring backend and next to `file`. If
anything says NOT READY it tells you exactly what is missing.

Then:

```bash
job-scout run
```

## 7. What to expect

**It takes about fifteen minutes the first time** and it is not stuck. Most of
that is asking job boards for results.

**It may find twenty or more matches.** That is not a mistake. The first run
scores every posting currently listed, so you get weeks of backlog at once. From
tomorrow you get only what is new, which is usually nothing to five.

Results are written to `data/matches.md`. Open it in any text editor.

Right now it is searching for a **fictional** person: a platform engineer in
Berlin. That is deliberate, so you can see whether the scoring makes sense
before writing anything about yourself.

## 8. Make it about you

If you have your CV as a file, this is one command:

```bash
pip install -e ".[cv]"
job-scout init . --from-cv path/to/your-cv.pdf --force
```

It reads your CV and fills in most of `profile.yaml`. Note that this sends your
CV text to Google, which is worth knowing before you run it.

Then open `profile.yaml` in a text editor and write the one section a CV cannot
give you: **`confirmed_gaps`**, the things that come up in job adverts in your
field that you have genuinely never done. Five minutes there is worth more than
anything else you can do.

Then open `config.yaml` and change the `searches` to your own job titles and
your own city.

Run `job-scout run --dry-run` as many times as you like. It scores everything and
prints it without saving or sending anything, so it is safe to experiment.

## 9. Make it run by itself

The scout does not schedule itself. Pick whichever fits:

| | |
|---|---|
| Run it by hand when you feel like it | Nothing to do. `job-scout run`. |
| Every day on this computer | A cron line or a Task Scheduler entry. [setup-local.md](setup-local.md#7-run-it-every-day) |
| Every day whether or not your computer is on | A small free server. [setup-systemd.md](setup-systemd.md) |
| Every day, no server of your own | [setup-github-actions.md](setup-github-actions.md). Read the warning first. |

## When something goes wrong

Two things, in order:

```bash
job-scout check
```

That reports everything that is and is not set up, with the reason.

Then [troubleshooting.md](troubleshooting.md), which is written around symptoms
rather than causes, so look for the sentence that matches what you are seeing.

Every credential you might need, and how to get it, is on one page:
[external-services.md](external-services.md).
