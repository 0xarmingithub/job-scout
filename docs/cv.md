# The CV pipeline: `job-scout cv`

Turns a CV you already have into a plain `resume.yaml`, fills your own template
with it, compiles a PDF, and checks that an applicant tracking system (ATS) can
read the result.

It keeps two things apart:

- **Content**: what the CV says. It lives in `resume.yaml`, a plain file that
  belongs to nobody.
- **Layout**: how it looks. It lives in a template that you own: a `.tex` file,
  or a Word file with your styles. This project ships one neutral example and no
  one's real template.

Everything here is optional and separate from the daily run, which never touches
it. Only `import` calls a model, and it asks before it sends anything.

```
your CV  --import-->  resume.yaml  --build-->  cv.pdf  --verify-->  what an ATS reads
(.docx .pdf .txt .md)                (your template)
```

## Install

```bash
pip install -e ".[cv]"     # pypdf, python-docx, jinja2
job-scout cv doctor        # what else you need, for your platform
```

`doctor` looks at six tools and installs nothing. It prints the command to run
for the operating system you are on:

| Tool | Needed for |
|---|---|
| `latexmk` | `cv build`, compiling a `.tex` template to a PDF |
| `pandoc` | `cv render --renderer docx`, writing a Word file |
| `pypdf` | `cv verify` (the default reader), and `cv import` of a PDF |
| `pdftotext` | `cv verify --extractor both`, an optional second opinion |
| `jinja2` | `cv render` and `cv build` with a `.tex` template |
| `python-docx` | `cv import` of a Word file |

You need only the ones for the commands you use. Markdown output needs none.

## A first run

```bash
job-scout cv example mycv          # a fictional resume.yaml and a neutral .tex template
job-scout cv build mycv/resume.yaml --template mycv/example.tex
job-scout cv verify mycv/resume.pdf --resume mycv/resume.yaml
```

Then replace the example's content with your own, or draft it from your CV:

```bash
job-scout cv import my-old-cv.docx --out mycv/resume.yaml --force
```

## `job-scout cv import`

Reads a CV (`.docx`, `.pdf`, `.txt` or `.md`) and drafts `resume.yaml` from it
with a model.

```bash
job-scout cv import my-cv.pdf
job-scout cv import my-cv.pdf --out resume.yaml --model claude:sonnet
```

**Where your CV goes.** The whole text of the CV, which is your name, contact
details and every employer, is sent to the backend named in `cv_model`. For a
hosted API that means it leaves your machine. For a CLI such as `claude`, the
CLI sends it to the vendor. Before it sends anything the command shows the file,
how many characters go, and the backend that receives them, and asks:

```
  File:     my-cv.pdf (4,210 characters)
  Goes to:  claude:sonnet, through the claude command, which sends it to Anthropic

Send it? (y/N):
```

The default is no. Nothing is sent until you answer `y`. The scout keeps no copy
of the CV and sends it nowhere else.

For a script, `--yes` answers that question in advance. Use it only when you have
already decided where the CV may go. Without a terminal and without `--yes`, the
command stops and says so rather than sending.

**`cv_model`.** A separate setting from `scoring_model`, with no default. The
first time you run `import` with no `cv_model` in `config.yaml`, in a terminal, it
asks which model to use. When a scoring model is set, the first question is:

```
Use the same model as scoring? (Y/n):
```

Answering yes uses your scoring model. Answering no walks you through choosing
another. Either way the answer is written to `cv_model` in `config.yaml`, and
either way you still get the "Send it?" question above. Where there is no
terminal, set `cv_model` yourself or pass `--model BACKEND:MODEL`. See
[configuration.md](configuration.md#cv_model).

**It is a draft.** A model reading free text can put a date on the wrong job or
merge two roles. It is told to invent nothing and to leave a missing field
missing, and its output is checked against the `resume.yaml` format, but only you
can check it against your career. The command ends by telling you what to look
at: dates, numbers, and anything it left out or tidied up.

It will not overwrite an existing `resume.yaml` without `--force`.

## `job-scout cv convert`

Turns job-scout's own tailored draft (the ATS-safe Markdown that the tailoring
step writes, see [tailoring.md](tailoring.md)) into `resume.yaml`. No model call.
Education dates are pulled out of free text with a regular expression, so check
them.

```bash
job-scout cv convert CV-ats.md --out resume.yaml
```

## `job-scout cv render`

Fills a template with `resume.yaml` and writes the result. The output suffix
chooses what is produced, or pass `--renderer`.

```bash
job-scout cv render resume.yaml --template my-template.tex  --out cv.tex
job-scout cv render resume.yaml --template my-styles.docx   --out cv.docx
job-scout cv render resume.yaml                             --out cv.md
```

The resume defaults to `resume.yaml` in the current directory.

## `job-scout cv build`

Renders a `.tex` template and compiles it to a PDF with `latexmk`.

```bash
job-scout cv build resume.yaml --template my-template.tex
job-scout cv build resume.yaml --template my-template.tex --out ~/cv/morgan-reyes.pdf
```

The filled `.tex` and everything LaTeX writes beside it (`.aux`, `.log`, and the
rest) go into a temporary folder that is deleted afterwards. The PDF lands next
to your `resume.yaml` with the same name, or where `--out` says. Your template's
folder is added to `TEXINPUTS`, so a template that loads a `.cls`, a `.sty` or an
image by relative path finds it where you keep it.

If `latexmk` is missing, the command says so and points at `job-scout cv doctor`.
If the compile fails, it shows the compiler's first error and the lines after it,
which is the cause rather than the cascade.

## `job-scout cv verify`

Reads a compiled PDF the way an ATS will, and reports what breaks.

```bash
job-scout cv verify cv.pdf --resume resume.yaml
job-scout cv verify cv.pdf --name "Morgan Reyes" --email morgan.reyes@example.com --phone "+45 12 34 56 78"
job-scout cv verify cv.pdf --resume resume.yaml --jd posting.md --extractor both
```

A clean compile proves the document built. It says nothing about what a parser
gets back out of it, and the extracted text is the only version a recruiter's
software ever sees. The expected name, email and phone come from your
`resume.yaml` (or from the flags), so a changed phone number cannot make the
check pass against a PDF that no longer carries it.

| Check | Fails or warns when |
|---|---|
| text layer | The PDF has almost no selectable text, as with a scanned image. Fails. |
| pages | There are more pages than `--max-pages` (default 2). Fails. |
| contact | The email or name does not extract. Fails. The phone only warns. |
| reading order | The name is not in the first 300 characters of page 1, so a parser takes something else for the name. Fails. |
| encoding | Accented letters come out as garbage. Fails. Ligature code points only warn. |
| residue | A LaTeX command shows up in the text layer. Fails. |
| headings | Fewer than three of Experience, Education, Skills, Summary and similar. Warns. |
| keywords | With `--jd`, fewer than `--min-coverage` of the posting's commonest terms appear. Warns. |

Exit code 0 means every check passed or warned. Exit code 1 means at least one
failed. Exit code 2 means the command could not run, for example a file is
missing.

`pypdf` is the default reader. `--extractor both` adds Poppler's `pdftotext` as a
second opinion when it is installed, and says so when it is not. The two disagree
occasionally, and an ATS runs one of them. `--dump-text PATH` writes out the
extracted text so you can read what a parser sees.

A low keyword score is sometimes correct. A term you have not earned should stay
out of your CV, and that outranks any coverage target.

## The `.tex` template contract

Any `.tex` file is a template if it uses these tokens in place of Jinja2's usual
braces, chosen so they do not collide with LaTeX's own `{}` and `%`:

```
\VAR{expr}                         print a value, e.g. \VAR{name}
\BLOCK{for x in list} ... \BLOCK{endfor}
\BLOCK{if cond} ... \BLOCK{else} ... \BLOCK{endif}
\#{comment}                        a comment, left out of the output
```

Every `\VAR{}` value is LaTeX-escaped for you (`&`, `%`, `_`, `#`, `$` and the
rest), so raw content cannot break the compile. A `\VAR{}` that names something
`resume.yaml` does not have is an error rather than a silent blank, because a
field quietly missing from a CV is worse than a build that stops.

The names a template can use:

| Name | What it is |
|---|---|
| `name`, `summary` | text |
| `contact.email`, `contact.phone`, `contact.location` | text, empty when not given |
| `contact.links` | a mapping of label to URL, loop with `contact.links.items()` |
| `experience` | a list; each has `title`, `company`, `location`, `dates`, `bullets` |
| `education` | a list; each has `degree`, `institution`, `dates` |
| `skills` | a list of text |
| `skill_groups` | a mapping of group name to a list of text. Wins over `skills` when both are given, if your template says so |
| `certifications`, `projects`, `interests` | lists of text |
| `extra` | a mapping of heading to text, for sections that fit nowhere else |

`job-scout cv example` writes a working template (`example.tex`) that uses all of
them. Copy it and change the styling.

## The Word template contract

Any `.docx` can be a template. Open it in Word and set the styles named `Title`,
`Heading 1`, `Heading 2`, `Heading 3`, `Body Text` and `List Bullet` the way you
like (font, size, colour, spacing), then save it. Pandoc copies those style
definitions onto the generated content. It never copies the reference file's own
text.

If you have no styled file yet, ask Pandoc for its default and restyle that:

```bash
pandoc -o my-styles.docx --print-default-data-file reference.docx
```

## `resume.yaml`

```yaml
name: Morgan Reyes
contact:
  email: morgan.reyes@example.com      # required
  phone: "+45 12 34 56 78"
  location: Odense, Denmark
  links: {LinkedIn: "https://linkedin.example/in/morgan-reyes"}
summary: A short paragraph.
experience:                            # each needs title, company, dates
  - {title: Senior Platform Engineer, company: Contoso Ltd, dates: "2022-2026", bullets: ["..."]}
education:                             # each needs degree, institution, dates
  - {degree: BSc Computer Science, institution: Example University, dates: "2015-2019"}
skills: [Python, Kubernetes]           # or skill_groups
```

`name`, `contact.email`, `summary`, `experience`, `education`, and one of `skills`
or `skill_groups` are required. A missing one is named in the error. The whole
file is in `job_scout/cv/templates/resume.example.yaml`.

## Limits

- Everything here is a command-line tool. Someone with no terminal experience
  cannot use it as it stands, and there is no hosted version or web form.
- It does not analyse a job description against your CV, find gaps, or write a
  cover letter. That belongs to the tailoring step.
- `verify` checks that a file is machine-readable. It does not judge the writing.
