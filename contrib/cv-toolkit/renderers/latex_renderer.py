"""Fills the user's own .tex template with resume.yaml content.

Placeholder contract (what a user's template must use):
  \\VAR{expr}                 -- print a value, e.g. \\VAR{name}
  \\BLOCK{for x in list} ... \\BLOCK{endfor}  -- repeat, e.g. over experience
  \\#{comment}                -- comment, stripped from output

Every \\VAR{} value is LaTeX-escaped automatically, so raw resume content
(names with "&", bullets with "%") can't break compilation.

See templates/example.tex for a working template built on this contract.
"""
import subprocess
from dataclasses import asdict

import jinja2

from schema import Resume

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


def _latex_escape(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


def _make_env(template_dir: str) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        finalize=_latex_escape,
    )


def render(resume: Resume, template_path: str | None, out_path: str) -> None:
    if not template_path:
        raise ValueError("the latex renderer needs --template pointing at your own .tex file")

    import os
    template_dir = os.path.dirname(os.path.abspath(template_path)) or "."
    template_name = os.path.basename(template_path)

    env = _make_env(template_dir)
    template = env.get_template(template_name)
    filled = template.render(**asdict(resume))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(filled)


def compile_pdf(tex_path: str) -> str | None:
    """Optional: compile the filled .tex to PDF via latexmk, if it's on PATH.
    Returns the PDF path on success, None if latexmk isn't available."""
    import os
    if subprocess.run(["where" if os.name == "nt" else "which", "latexmk"],
                       capture_output=True).returncode != 0:
        return None
    tex_dir = os.path.dirname(os.path.abspath(tex_path)) or "."
    tex_name = os.path.basename(tex_path)
    subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", tex_name],
                    cwd=tex_dir, capture_output=True, check=True)
    return os.path.splitext(tex_path)[0] + ".pdf"
