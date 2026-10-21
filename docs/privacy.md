# Your private word list

A job-search workspace is full of things that must never reach a public place:
your name, your employers, your town, the address of the server this runs on.
`job-scout privacy` keeps a list of those terms, written by you, and checks
folders and git ranges against it.

The project ships no one's terms. It cannot know yours, and a list of real
names written into a public repository would be the leak it exists to prevent.

```bash
job-scout privacy init               answer questions, build the list
job-scout privacy add TERM           add one term, with its spelling variants
job-scout privacy list --count       how many entries. Never shows them
job-scout privacy check              scan the current directory
job-scout privacy check path/to/dir
job-scout privacy check --range origin/main..HEAD
```

## Building the list

`job-scout privacy init` asks, one question at a time, for:

* your full name, and any other name you go by
* your email addresses
* your phone numbers
* your city, town or area, and your street if you want it kept out
* employers and clients, past and present
* server names and IP addresses you use
* file names of your SSH or API key files
* names of your private repositories

Type one answer per line and press Enter on an empty line to move on. Nothing you
type is printed back, logged or sent anywhere.

For each answer it also saves the spellings people actually write:

| You give | It also lists |
|---|---|
| a name, `Morgan Reyes` | `reyes morgan`, and the surname `reyes` (when it is four letters or more) |
| an email | the part before the `@` |
| a phone number | the number without spaces, and without the leading `+` |
| an employer, `Contoso Denmark A/S` | the name without its legal suffix, `contoso` |
| a place or any word with accents | the accent-folded form (`osterby`) and the common transliteration (`oesterby`) |
| a key file, `work-vm.key` | the name without its extension |
| a repository, `owner/name` | the name alone |

A first name on its own is not added: it matches too much to be useful. Add it
yourself with `job-scout privacy add` if you want it. A term shorter than three
characters is refused, because it would match almost everything.

`job-scout privacy add TERM` adds a term and its accent variants; `--exact` adds
it as typed. To avoid leaving a term in your shell history, pass `-` and type it
on standard input:

```bash
job-scout privacy add -
```

## Where the list lives

The list is a plain text file, one term per line, readable by you alone (mode
600 on Linux and macOS). Lines starting with `#` are comments. It is **never
committed, never logged and never printed whole**.

| Who | Where |
|---|---|
| You run the scout | `<config dir>/privacy.txt` |
| You work on the job-scout code | `<git dir>/denylist.txt`, inside `.git`, where git cannot commit it |

Which one is used is decided in this order: `--file PATH`, then the
`JOB_SCOUT_DENYLIST` environment variable, then `--config-dir` (or
`JOB_SCOUT_CONFIG_DIR`, or the current directory if it has a `config.yaml`),
then a job-scout checkout's git directory, then `privacy.txt` in the current
directory.

In a git worktree `.git` is a file, not a folder. The list is kept in the shared
git directory (`git rev-parse --git-common-dir`), so it works from every
worktree of the same repository.

When your config directory is itself inside a git repository that does not
ignore `privacy.txt`, every command that writes to the list (`init`, `add`, and
the employer offer from `outcomes`, including a "no" answer) first adds it to
`.git/info/exclude` and says so, so that a later `git add .` cannot publish it. If git already tracks the file, you
get a warning and the command to stop it.

## Checking

`job-scout privacy check` scans every file in a directory. In a git repository
that means the files git tracks plus the untracked ones it does not ignore;
elsewhere it walks the directory. Binary files, files over 2 MB and the list
itself are skipped.

`job-scout privacy check --range origin/main..HEAD` scans the lines a range
**adds** and the author and committer of every commit in it. A push publishes who
wrote each commit as well as what it says, and fixing that afterwards means
rewriting history.

A hit looks like this:

```
  docs/notes.md:12:5  matches entry #7 of privacy.txt
```

File, line, column, and the entry's file name and position within that file,
counted from the top and ignoring comments and blank lines. The term itself is
never shown. Open that file to see which one it is. For a commit, the hit names
the commit and whether it was the author or the committer, never the name and
email that matched. The exit code is 0 when clean, 1 when there is a hit, and 2
when there is no list to check against.

Matching is case-insensitive substring matching. It finds what you listed, in
the spellings you listed. It is a safety net and not a proof: a term you did not
think of is not caught.

## Keeping it current

You will apply to employers you did not list when you built it.
`job-scout outcomes`, run in a terminal, notices employers in your application
folders that are not on the list and asks:

```
3 employer(s) in your applications are not on your privacy list. Go through them one at a time? [y/N]
Add 'Contoso'? [y]es, [n]o, [a]ll the rest, [s]top:
```

* **Nothing is added without your answer.** `a` adds the rest, but only because
  you typed it.
* An employer you answer `n` for is remembered (as a comment line in the same
  file) and is not asked about again.
* It asks only when a list already exists. With none, it prints one line pointing
  at `job-scout privacy init` and asks nothing.
* **Runs without a terminal never ask and never add.** `job-scout run` rebuilds
  the outcomes file on a timer and must not wait for an answer, so only the
  `outcomes` command, typed by a person, offers. `--no-prompt` turns it off there
  too.

## Pushing safely

If you contribute to job-scout, or keep your own workspace in a repository that
might become public, run the pre-push check before pushing:

```bash
bash tools/install-git-hooks.sh        # once: installs the hook
python tools/pre_push_check.py         # on demand
```

It reads the same file, and also checks for credential shapes and for files that
should never be committed (`privacy.txt`, `denylist.txt`, `outcomes.csv`,
anything under `applications/`). It does not print your terms either: a finding
names the entry by file and position, such as `entry #3 of denylist.txt`, and
for a commit author or committer it names the commit and the field, not the
identity. Where more than one list exists (the git directory's `denylist.txt`, a
`privacy.txt` at the root of the checkout, and one in `JOB_SCOUT_CONFIG_DIR`),
the terms are combined for the check, but each finding still points at the file
it came from and its position within that file, so you know which one to open.

## If the list is lost

It is only on your machine, on purpose. Keep a copy in your password manager. A
fresh clone has no list, and the hook says so rather than passing quietly.
