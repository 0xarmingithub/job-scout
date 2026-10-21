# Tracking your applications

The scorer gets better when it knows what happened to the jobs you applied for.
This page is how to record that without keeping a spreadsheet: one folder per
application, one line in it that says where the application stands, and a
command that turns the lines into the file the scorer reads.

It is optional. Without it a run works exactly as before.

## The convention

One folder per application, inside a folder you choose:

```
applications/
  contoso-warehouse-planner-20250421/
    notes.md          required: the Status line lives here
    jd.md             optional: the posting, saved as you read it
    CV.tex            optional: whatever you sent
  fabrikam-claims-handler-20250502/
    notes.md
```

The folder name is `<company>-<role>-<YYYYMMDD>`, lowercase, words joined with
hyphens. The date is the day you started the application. The company comes
first because that is how the company name is recovered when nothing else says
it (see "Where the company comes from").

A folder whose name starts with `.` or `_` is not an application. Use
`_template/` for a starting copy and `.archive/` for finished years.

### notes.md

Put the Status line near the top. This is the only line the tools require:

```markdown
- **Status:** drafted
- **Applied on:** 2025-04-22
- **Channel:** company portal
- **Next action:** follow up if no word by 2025-05-06
```

The words around `Status:` matter: the label must be bold, exactly
`**Status:**`, with or without the leading `- `. Everything after it on that line
is the status. The other lines are for you; nothing reads them.

### The status words

Write one of these words, or any text that contains one:

| Write | Means | The scorer reads it as |
|---|---|---|
| `drafted` | A CV exists, nothing sent | not yet an outcome |
| `submitted` | You sent it | applied |
| `acknowledged` | They confirmed they received it | applied |
| `screened` | A recruiter or a screening call | reached interview |
| `interviewing` | In the interview rounds | reached interview |
| `offer` | You have an offer | offer |
| `rejected` | They said no | rejected |
| `withdrawn` | You read it and chose not to apply, or pulled out | chose not to apply |

Other texts work too. `no response`, `ghosted` and `silence` are read as no
response, and `rejected after the second round` as rejected. A status the reader
does not recognise is kept but teaches the scorer nothing, so stay close to the
words above.

Two details worth knowing:

* A rejection whose notes mention an interview, a screen or a technical call is
  recorded as `rejected after interview`. A rejection that came after you spoke
  to them says something different from one that came at screening.
* A phrase of your own that contains a status word but means something else can
  be removed before the line is read. If your process has a step called, say,
  "interview prep", and you write `**Status:** interview prep done`, the word
  "interview" would be read as an interview with an employer. List the phrase in `config.yaml`:

  ```yaml
  status_ignore_phrases:
    - "interview prep"
  ```

  The match ignores case. Nothing is ignored unless you list it.

### jd.md (optional)

If you save the posting, put these two lines at the top. They are the most
reliable way to get the company and the title right:

```markdown
Company: Contoso
Role title: Platform Engineer
```

## Turning the folders into the outcomes file

Set the folder in `config.yaml`:

```yaml
applications_dir: applications     # relative to the config directory, or absolute
```

Then:

```bash
job-scout outcomes --print     # what it would write, one line per application
job-scout outcomes             # write the file
```

`--print` also lists every folder that has no Status line. Those are the ones
the scorer never hears about, and each is an application whose result exists
only in your memory.

The output is a CSV with the header `title,company,status,folder`. The scorer
reads the first three columns (see the format in
[configuration.md](configuration.md#application-outcomes)); `folder` is there so
a wrong row can be traced back to the folder it came from.

`job-scout run` does the same thing at the start of every run when
`applications_dir` is set, so scoring always sees the current state of your
folders. A dry run does it too: the file is derived from your folders, not a
record of the run.

### Where the file goes

With `applications_dir` set, the generated file is `outcomes.csv` in your **data
directory**, not your config directory. A run never writes into the config
directory (config in, data out), and a file that is rebuilt every day is output.

If you set `outcomes_file` yourself, the file goes there instead, with one
safeguard: a file with the three-column hand-kept header is never overwritten.
The run says so and scores with the file as it is. Do not point `outcomes_file`
at a file you edit by hand while `applications_dir` is set.

### Where the company comes from

The company column matters more than it looks. It is what the scorer shows the
model as "title at company", and what `job-scout calibrate` joins on to find the
score a posting got before it became an application. The reader tries three
things, best first:

1. The `Company:` and `Role title:` lines at the top of `jd.md`.
2. The first heading of `jd.md`, split at a dash, a colon, a comma, a middle dot
   or a trailing bracket. The folder name decides which half is the company: the
   folder starts with the company, so the half it starts with wins.
3. The folder name itself: the leading words the role title does not use.

If you can, write the two lines in `jd.md`. Then nothing is guessed.

## Checking the folders

Before you commit an application folder:

```bash
python tools/check_applications.py              # ./applications
python tools/check_applications.py path/to/applications
```

Exit code 0 means every folder has a `notes.md` with a Status line that has a
value. 1 names the folders that do not. This is in `tools/` in the job-scout
repository; it needs the job-scout package importable.

## Keeping the config directory in step: `sync`

If your config directory is a git repository, the scout can pull it before each
run, so a profile you push from your laptop is live on the machine that runs the
scout the next morning:

```yaml
sync:
  git_pull: true
  retries: 2
  retry_wait_seconds: 10
```

The pull is `git pull --ff-only`, tried again after a wait if it fails (the
usual cause is a network that is not up yet). You are alerted only when it still
fails **and** the config directory is behind its upstream. A failed pull while
you are already up to date changes nothing and would be noise every morning.
A dry run never pulls.

"Behind" is measured against the remote as git last saw it, not against the
remote itself. If the pull fails because the network is down, git cannot see
newer commits either, so the directory can look up to date and no alert is sent.
The alert is reliable for failures git can explain from what it already knows,
such as a diverged branch or local changes in the way. It does not replace
noticing that a profile you pushed never arrived.

## Keep it out of a public repository

Your application folders hold the names of real employers. If you work in a
repository that is, or might be, published, read [privacy.md](privacy.md): the
checks there stop an employer's name from reaching it.
