"""
build.py. Fill a .tex template and compile it to a PDF with latexmk.

The filled .tex and every file LaTeX writes beside it (.aux, .log and the rest)
go into a temporary directory that is deleted afterwards, so the only thing left
next to your resume.yaml is the PDF. Your template's own folder is added to
TEXINPUTS, so a template that pulls in a .cls, a .sty or an image by relative
path finds them where you keep them.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import CvError
from .render import fill_latex
from .schema import Resume

# How much of latexmk's output to show when a compile fails. The cause is almost
# always in the last few lines, and the whole log buries it.
_TAIL_LINES = 25
_COMPILE_TIMEOUT = 300

LATEXMK_MISSING = (
    "Building a PDF needs latexmk, which is not on your PATH. Run `job-scout cv doctor` "
    "for the install step. If you only want the .tex file, use `job-scout cv render` instead."
)


def latexmk_command(tex_name: str) -> list[str]:
    # -halt-on-error matters: without it LaTeX "succeeds" on a broken document
    # and writes a mangled PDF.
    return ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex_name]


def compile_tex(tex_source: str, template_dir: Path, out_pdf: Path, jobname: str = "cv") -> Path:
    """Compile LaTeX source to out_pdf. Raises CvError with the end of the log on failure."""
    if shutil.which("latexmk") is None:
        raise CvError(LATEXMK_MISSING)

    out_pdf = Path(out_pdf)
    with tempfile.TemporaryDirectory(prefix="job-scout-cv-") as tmp:
        work = Path(tmp)
        tex_path = work / f"{jobname}.tex"
        tex_path.write_text(tex_source, encoding="utf-8")

        env = dict(os.environ)
        # A trailing separator keeps TeX's own default search path after ours.
        env["TEXINPUTS"] = os.pathsep.join([str(template_dir), env.get("TEXINPUTS", ""), ""])

        try:
            done = subprocess.run(
                latexmk_command(tex_path.name),
                cwd=work, env=env, capture_output=True, timeout=_COMPILE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise CvError(
                f"latexmk ran for {_COMPILE_TIMEOUT} seconds without finishing, so it was stopped. "
                f"A template that waits for input or loops forever does this."
            ) from exc
        except OSError as exc:
            raise CvError(f"latexmk could not be started: {exc}") from exc

        pdf = work / f"{jobname}.pdf"
        if done.returncode != 0 or not pdf.is_file():
            raise CvError(_failure_message(done, work / f"{jobname}.log"))

        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, out_pdf)
    return out_pdf


def _failure_message(done: subprocess.CompletedProcess, log_path: Path) -> str:
    """What went wrong, from the .log when there is one, else from latexmk's own output."""
    text = ""
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        text = (done.stdout or b"").decode("utf-8", errors="replace") + (
            (done.stderr or b"").decode("utf-8", errors="replace")
        )
    # LaTeX flags its errors with a line that starts with "!". Show from the
    # first one, which is the cause, not the cascade after it.
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.startswith("!")), None)
    shown = lines[first:first + _TAIL_LINES] if first is not None else lines[-_TAIL_LINES:]
    return (
        f"latexmk failed (exit {done.returncode}). The compiler said:\n\n"
        + "\n".join(shown)
        + "\n\nThe usual causes are a package your TeX install does not have, or a "
        "mistake in the template. Render the .tex with `job-scout cv render` and "
        "compile it yourself to see the full log."
    )


def build_pdf(resume: Resume, template_path: Path, out_pdf: Path) -> Path:
    """Fill the template and compile it. The one call `job-scout cv build` makes."""
    template_path = Path(template_path)
    if template_path.suffix.lower() != ".tex":
        raise CvError(
            f"{template_path.name} is not a .tex file. `job-scout cv build` compiles LaTeX. "
            f"For a Word file use `job-scout cv render --template your.docx --out cv.docx`."
        )
    # Check the tool before doing any work, so the message about a missing
    # latexmk is not hidden behind a template problem the person cannot yet fix.
    if shutil.which("latexmk") is None:
        raise CvError(LATEXMK_MISSING)
    source = fill_latex(resume, template_path)
    return compile_tex(source, template_path.resolve().parent, out_pdf)
