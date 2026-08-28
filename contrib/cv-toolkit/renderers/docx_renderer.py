"""Turns resume.yaml into a .docx via Pandoc. Needs Pandoc installed
(https://pandoc.org/installing.html) -- nothing else in this toolkit does.

Bring your own template: point --template at a .docx file whose paragraph
and heading styles you've already set up in Word (fonts, spacing, colors).
Pandoc copies those styles onto the generated content -- it does not copy
the reference file's text. Without --template, Pandoc's own default docx
styles are used.
"""
import shutil
import subprocess

from schema import Resume
from renderers.markdown_renderer import to_markdown


def render(resume: Resume, template_path: str | None, out_path: str) -> None:
    if shutil.which("pandoc") is None:
        raise RuntimeError(
            "the docx renderer needs Pandoc on PATH -- install it from "
            "https://pandoc.org/installing.html, or use --renderer markdown instead"
        )

    markdown_text = to_markdown(resume)
    cmd = ["pandoc", "-f", "markdown", "-t", "docx", "-o", out_path]
    if template_path:
        cmd += ["--reference-doc", template_path]

    result = subprocess.run(cmd, input=markdown_text.encode("utf-8"), capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed:\n{result.stderr.decode('utf-8', errors='replace')}")
