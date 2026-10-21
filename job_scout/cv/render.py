"""
render.py. Turn a Resume into a document, using a template that belongs to you.

Three outputs:

  latex     fills your own .tex template (needs the jinja2 package)
  docx      fills your own Word styles through Pandoc (needs Pandoc on your PATH)
  markdown  one fixed, clean layout. No template and no extra tools

The LaTeX placeholder contract. Any .tex file is a template if it uses these
tokens in place of Jinja2's usual braces, which would collide with LaTeX's own:

  \\VAR{expr}                                   print a value, e.g. \\VAR{name}
  \\BLOCK{for x in list} ... \\BLOCK{endfor}      repeat, or branch with if/else/endif
  \\#{comment}                                  a comment, left out of the output

Every \\VAR{} value is LaTeX-escaped on the way out, so a name with an "&" or a
bullet with a "%" cannot break the compile. A \\VAR{} that names something the
resume does not have is an error, not a silent blank, because a field quietly
missing from a CV is worse than a build that stops.
"""

import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from . import CvError
from .schema import Resume

LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

RENDERERS = ("latex", "docx", "markdown")
_SUFFIX_TO_RENDERER = {".tex": "latex", ".docx": "docx", ".md": "markdown", ".markdown": "markdown"}


def renderer_for(out_path: Path, given: str | None) -> str:
    """The renderer named on the command line, else the one the output suffix implies."""
    if given:
        return given
    chosen = _SUFFIX_TO_RENDERER.get(Path(out_path).suffix.lower())
    if chosen is None:
        raise CvError(
            f"Cannot tell what to produce from the output name {Path(out_path).name!r}. "
            f"Name it .tex, .docx or .md, or pass --renderer {'|'.join(RENDERERS)}."
        )
    return chosen


def latex_escape(value) -> str:
    if value is None:
        return ""
    return "".join(LATEX_SPECIAL_CHARS.get(char, char) for char in str(value))


# --- Markdown ----------------------------------------------------------------

def to_markdown(resume: Resume) -> str:
    """The shared content layout. The docx renderer feeds this to Pandoc, so both stay in step."""
    lines = [f"# {resume.name}", ""]

    contact_bits = [resume.contact.email]
    if resume.contact.phone:
        contact_bits.append(resume.contact.phone)
    if resume.contact.location:
        contact_bits.append(resume.contact.location)
    lines.append(" | ".join(contact_bits))
    for label, url in resume.contact.links.items():
        lines.append(f"[{label}]({url})")
    lines.append("")

    lines += ["## Summary", resume.summary.strip(), ""]

    lines.append("## Experience")
    for entry in resume.experience:
        where = f"{entry.company}, {entry.location}" if entry.location else entry.company
        lines.append(f"### {entry.title} - {where} ({entry.dates})")
        for bullet in entry.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    lines.append("## Skills")
    if resume.skill_groups:
        for group, items in resume.skill_groups.items():
            lines.append(f"**{group}:** {', '.join(items)}")
    else:
        lines.append(", ".join(resume.skills))
    lines.append("")

    lines.append("## Education")
    for entry in resume.education:
        lines.append(f"- **{entry.degree}**, {entry.institution} ({entry.dates})")

    if resume.certifications:
        lines += ["", "## Certifications"]
        lines += [f"- {item}" for item in resume.certifications]

    if resume.projects:
        lines += ["", "## Projects"]
        lines += [f"- {item}" for item in resume.projects]

    if resume.interests:
        lines += ["", "## Interests", "; ".join(resume.interests)]

    for heading, body in resume.extra.items():
        lines += ["", f"## {heading}", body]

    return "\n".join(lines) + "\n"


def render_markdown(resume: Resume, template_path: Path | None, out_path: Path) -> None:
    """No template needed. Anyone gets a file they can paste into a document or a job site."""
    Path(out_path).write_text(to_markdown(resume), encoding="utf-8")


# --- LaTeX -------------------------------------------------------------------

def _require_jinja2():
    try:
        import jinja2
    except ImportError as exc:
        raise CvError(
            "Filling a .tex template needs the jinja2 package, which is not installed. "
            "Install it with: pip install jinja2"
        ) from exc
    return jinja2


def fill_latex(resume: Resume, template_path: Path) -> str:
    """The template with the resume poured in. Raises CvError in plain words."""
    jinja2 = _require_jinja2()
    template_path = Path(template_path)
    if not template_path.is_file():
        raise CvError(
            f"No template at {template_path}. Pass --template with the path to your own .tex "
            f"file. To start from a neutral one: job-scout cv example <directory>"
        )

    def finalize(value):
        if isinstance(value, jinja2.Undefined):
            name = getattr(value, "_undefined_name", None) or "a value"
            raise CvError(
                f"{template_path.name} uses \\VAR{{{name}}}, and resume.yaml has no such field. "
                f"Check the spelling against docs/cv.md, or add the field."
            )
        return latex_escape(value)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.resolve().parent)),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        finalize=finalize,
        keep_trailing_newline=True,
    )
    try:
        return env.get_template(template_path.name).render(**asdict(resume))
    except jinja2.TemplateSyntaxError as exc:
        raise CvError(
            f"{template_path.name} line {exc.lineno}: {exc.message}. "
            f"Check that every \\BLOCK{{for}} and \\BLOCK{{if}} has its endfor or endif."
        ) from exc
    except jinja2.TemplateError as exc:
        raise CvError(f"{template_path.name} could not be filled: {exc}") from exc


def render_latex(resume: Resume, template_path: Path | None, out_path: Path) -> None:
    if not template_path:
        raise CvError(
            "A .tex output needs your own template. Pass --template with the path to a .tex "
            "file. To start from a neutral one: job-scout cv example <directory>"
        )
    Path(out_path).write_text(fill_latex(resume, Path(template_path)), encoding="utf-8")


# --- Word, through Pandoc ----------------------------------------------------

def render_docx(resume: Resume, template_path: Path | None, out_path: Path) -> None:
    """
    Needs Pandoc. With --template, the paragraph and heading styles of that .docx
    (Title, Heading 1 to 3, Body Text, List Bullet) are copied onto the content.
    Without one, Pandoc's own default styles are used.
    """
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise CvError(
            "Writing a .docx needs Pandoc, which is not on your PATH. Run `job-scout cv doctor` "
            "for the install step, or write markdown (--renderer markdown) instead."
        )
    command = [pandoc, "-f", "markdown", "-t", "docx", "-o", str(out_path)]
    if template_path:
        if not Path(template_path).is_file():
            raise CvError(f"No template at {template_path}. Pass --template with your own .docx file.")
        command += ["--reference-doc", str(template_path)]
    done = subprocess.run(command, input=to_markdown(resume).encode("utf-8"), capture_output=True)
    if done.returncode != 0:
        raise CvError("Pandoc failed:\n" + done.stderr.decode("utf-8", errors="replace").strip())


_DISPATCH = {"latex": render_latex, "docx": render_docx, "markdown": render_markdown}


def render(resume: Resume, renderer: str, template_path: Path | None, out_path: Path) -> None:
    if renderer not in _DISPATCH:
        raise CvError(f"Unknown renderer {renderer!r}. Use one of: {', '.join(RENDERERS)}.")
    _DISPATCH[renderer](resume, template_path, out_path)
