# CV toolkit

Turns CV content into a finished document, in whatever format you already
use -- LaTeX, Word, or plain text -- without publishing anyone's personal
template. Also reads an existing CV, or job-scout's own tailored draft, into
that content format.

This is not the "Release 2" CV toolkit described in the [main
README](../../README.md#what-is-coming). It covers the *rendering* side --
generalizing away from one specific LaTeX structure. It does not analyse a
job description, map it onto a résumé, find gaps, or draft a cover letter --
the content-analysis side "Release 2" describes is still unbuilt.

## Why it's split this way

Content (what to say) and rendering (how it looks) are separate. The
tailoring step only ever produces `resume.yaml` -- a plain, format-neutral
file. Turning that into a `.tex`, `.docx`, or plain-text file is a separate,
optional step, picked per user:

- Has LaTeX and a template already -> `latex` renderer fills their `.tex` file.
- Has Word, no LaTeX -> `docx` renderer, via Pandoc.
- Has nothing -> `markdown` renderer. No dependency beyond PyYAML. Paste the
  result into Google Docs, Word, or a job site's text box.

Nobody is asked to install LaTeX or Pandoc unless they pick that renderer.
The repo ships two generic example templates -- `templates/example.tex` and
`templates/reference.docx` -- so LaTeX and Word users can see the contract.
Neither is anyone's real CV template.

## Who this doesn't serve yet

Everything here is a command-line tool: Python, `pip install`, a terminal.
Someone with no coding background can't use it as-is -- there's no GUI and
no hosted version. Serving that audience would need a second project (a web
form or a small app in front of this), not a documentation fix. Not planned
here for now, flagging it as a known limit rather than leaving it unsaid.

## Files

| File | Job |
|---|---|
| `schema.py` | `Resume` data model + `validate()`, the one gate every renderer sits behind |
| `resume.example.yaml` | Hand-written sample content |
| `renderers/markdown_renderer.py` | Zero-dependency renderer |
| `renderers/latex_renderer.py` | Fills a user's own `.tex` template via Jinja2 (see placeholder contract below) |
| `renderers/docx_renderer.py` | Fills a user's own `.docx` styles via Pandoc's `--reference-doc` |
| `templates/example.tex` | Generic, bare-bones example LaTeX template |
| `templates/reference.docx` | Pandoc's own default reference `.docx` -- a neutral starting point to restyle |
| `adapters/ats_markdown_adapter.py` | Parses job-scout's ATS-safe Markdown CV output into `resume.yaml`'s shape (regex-based, no model call) |
| `adapters/cv_import_adapter.py` | Reads an existing CV (`.txt`/`.md`/`.pdf`/`.docx`) into `resume.yaml`'s shape via a model -- there's no fixed layout to write regex against |
| `render.py` | CLI: `resume.yaml` -> rendered file |
| `convert.py` | CLI: job-scout's tailored draft -> `resume.yaml` |
| `import_cv.py` | CLI: an existing CV you already have -> `resume.yaml` |

## Usage

```bash
pip install -r requirements.txt

# resume.yaml -> plain Markdown (works for anyone)
python render.py resume.example.yaml --renderer markdown --out cv.md

# resume.yaml -> a LaTeX PDF, using your own template
python render.py resume.example.yaml --renderer latex --template templates/example.tex --out cv.tex
latexmk -pdf cv.tex

# resume.yaml -> .docx, using your own styled reference document (needs Pandoc)
python render.py resume.example.yaml --renderer docx --template templates/reference.docx --out cv.docx

# job-scout's tailored draft -> resume.yaml
python convert.py path/to/CV-ats.md --out resume.yaml

# an existing CV you already have -> resume.yaml (needs a model on PATH,
# default is `claude -p --model sonnet`; pip install pypdf / python-docx
# first if the CV is .pdf / .docx)
python import_cv.py path/to/my-old-cv.pdf --out resume.yaml
```

## LaTeX placeholder contract

Any `.tex` file can be used as a template if it uses these Jinja2 tokens
instead of Jinja2's normal `{{ }}` / `{% %}` (chosen so they don't collide
with LaTeX's own `{}` and `%`):

```
\VAR{expr}                    print a value, e.g. \VAR{name}
\BLOCK{for x in list} ... \BLOCK{endfor}
\#{comment}
```

Every `\VAR{}` value is LaTeX-escaped automatically (`&`, `%`, `_`, etc.),
so raw resume content can't break compilation. See `templates/example.tex`
for a full working template.

## docx template contract

Any `.docx` can be a template: open it in Word, set the styles named
`Title`, `Heading 1`, `Heading 2`, `Heading 3`, `Body Text`, and `List
Bullet` however you like (font, size, color, spacing), then save it. Pandoc
copies those style definitions onto the generated content -- it never
copies the reference file's own text. Verified in testing: changing
`Heading 1` to 28pt dark red in a copy of `templates/reference.docx`
carried through to the rendered output unchanged.

## Known rough edges

`adapters/ats_markdown_adapter.py` extracts education dates from free-text
bullets with a regex, not a real parser -- tested clean against a real,
multi-decade CV with unusual entries (part-time roles, multiple degrees),
but always check the education dates in freshly converted output before
trusting them.

`adapters/cv_import_adapter.py` asks a model to read a whole CV and can
occasionally misplace a date or merge two roles, the way any summarization
step can. It's instructed never to invent a fact not in the source text, and
in testing it correctly left a missing LinkedIn URL as a bare label rather
than guessing one -- but it is still a draft. Read the output before
trusting it, same as any of a model's first-pass work. Know what it sends
where before you point it at a real CV: the full text -- name, contact
details, whole employment history -- goes to whatever `--command` names.
The default runs locally through your own Claude Code login; nothing goes
to a third-party API unless you point `--command` at one yourself.

## Writing your own adapter

`adapters/ats_markdown_adapter.py` is one example: it parses a specific
"# Name, then `## Heading` sections" Markdown format (the kind an LLM-based
CV-tailoring tool tends to produce) into `resume.yaml`. If your own
tailoring pipeline outputs something else -- different Markdown shape, a
JSON file, a database row -- write a new file under `adapters/` with a
`parse(text: str) -> dict` function returning the same shape `schema.py`
validates. Nothing else in the toolkit needs to change.
