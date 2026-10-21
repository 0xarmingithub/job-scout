"""
cli.py. The `job-scout cv` subcommands.

    job-scout cv doctor                    which optional tools are installed, and how to get the rest
    job-scout cv example [DIR]             copy a neutral resume.yaml and .tex template to start from
    job-scout cv import CV_FILE            draft resume.yaml from an existing CV, with a model
    job-scout cv convert DRAFT.md          resume.yaml from job-scout's tailored Markdown draft
    job-scout cv render [RESUME] --out F   resume.yaml into your template (.tex, .docx) or markdown
    job-scout cv build [RESUME] --template T.tex
                                           render a .tex template and compile it to a PDF
    job-scout cv verify PDF                read the PDF the way an ATS will

Only `import` calls a model, and it asks before it sends anything.
"""

import argparse
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from ..config import CONFIG_FILENAME, ConfigError, resolve_config_dir
from ..cv_import import CvImportError
from ..llm import parse_spec
from ..setup_prompt import SetupCancelled
from . import CvError, doctor, importer, model_prompt, verify
from .render import RENDERERS, render, renderer_for
from .schema import Resume, validate

DEFAULT_RESUME = "resume.yaml"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
EXAMPLE_FILES = ("resume.example.yaml", "example.tex")


def _interactive() -> bool:
    """True when a person is at a terminal who can answer a question."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _err(message: str) -> None:
    print(message, file=sys.stderr)


# --- Parser ------------------------------------------------------------------

def add_cv_parser(subparsers: argparse._SubParsersAction) -> None:
    cv = subparsers.add_parser(
        "cv",
        help="turn a CV into resume.yaml, and resume.yaml into a finished document",
        description="The CV pipeline. Content lives in resume.yaml; layout lives in a "
                    "template you own. See docs/cv.md.",
    )
    cv.set_defaults(_cv_parser=cv)
    sub = cv.add_subparsers(dest="cv_command")

    sub.add_parser("doctor", help="report which of the optional CV tools are installed")

    example = sub.add_parser(
        "example", help="copy a neutral resume.yaml and .tex template to start from",
    )
    example.add_argument("directory", nargs="?", default=".", help="where to put them (default: here)")
    example.add_argument("--force", action="store_true", help="overwrite files already there")

    imp = sub.add_parser(
        "import",
        help="draft resume.yaml from an existing CV (.docx, .pdf, .txt, .md) with a model",
    )
    imp.add_argument("cv_file", help="the CV to read")
    imp.add_argument("--out", default=DEFAULT_RESUME, help=f"where to write the draft (default: {DEFAULT_RESUME})")
    imp.add_argument("--model", metavar="BACKEND:MODEL", help="use this model instead of cv_model, for example claude:sonnet")
    imp.add_argument(
        "--yes", action="store_true",
        help="do not ask before sending the CV to the model. For scripts. "
             "You are agreeing to send the whole text of the CV to the model's backend",
    )
    imp.add_argument("--force", action="store_true", help="overwrite the output file if it exists")
    imp.add_argument("--config-dir", help="directory holding config.yaml (for cv_model)")

    conv = sub.add_parser(
        "convert", help="resume.yaml from job-scout's tailored Markdown draft (no model call)",
    )
    conv.add_argument("draft", help="the tailored Markdown draft, for example CV-ats.md")
    conv.add_argument("--out", default=DEFAULT_RESUME, help=f"where to write it (default: {DEFAULT_RESUME})")
    conv.add_argument("--force", action="store_true", help="overwrite the output file if it exists")

    rend = sub.add_parser("render", help="resume.yaml into your template or into markdown")
    rend.add_argument("resume", nargs="?", default=DEFAULT_RESUME, help=f"default: {DEFAULT_RESUME}")
    rend.add_argument("--out", required=True, help="the file to write: .tex, .docx or .md")
    rend.add_argument("--template", help="your own .tex or .docx template. Markdown needs none")
    rend.add_argument(
        "--renderer", choices=RENDERERS,
        help="default: chosen from the suffix of --out",
    )

    build = sub.add_parser("build", help="render a .tex template and compile it to a PDF with latexmk")
    build.add_argument("resume", nargs="?", default=DEFAULT_RESUME, help=f"default: {DEFAULT_RESUME}")
    build.add_argument("--template", required=True, help="your own .tex template")
    build.add_argument("--out", help="the PDF to write (default: next to the resume, same name)")

    ver = sub.add_parser(
        "verify", help="read a compiled PDF the way an applicant tracking system will",
    )
    ver.add_argument("pdf", help="the compiled CV")
    ver.add_argument("--resume", help=f"take the expected name, email and phone from this file (default: ./{DEFAULT_RESUME} if present)")
    ver.add_argument("--name", help="the name the PDF should carry. Overrides the resume")
    ver.add_argument("--email", help="the email the PDF should carry. Overrides the resume")
    ver.add_argument("--phone", help="the phone the PDF should carry. Overrides the resume")
    ver.add_argument("--jd", help="the job description, as text or markdown, for a keyword check")
    ver.add_argument(
        "--extractor", choices=(*verify.EXTRACTORS, "both"), default="pypdf",
        help="which reader to check with. 'both' adds pdftotext as a second opinion "
             "when it is installed (default: pypdf)",
    )
    ver.add_argument("--max-pages", type=int, default=2, help="default: 2")
    ver.add_argument("--min-chars", type=int, default=800, help="fewest characters a real CV extracts (default: 800)")
    ver.add_argument("--min-coverage", type=float, default=0.6, help="share of the posting's commonest terms expected in the PDF (default: 0.6)")
    ver.add_argument("--dump-text", metavar="PATH", help="also write the extracted text here, to read what a parser sees")


# --- Dispatch ----------------------------------------------------------------

def run_cv(
    args: argparse.Namespace,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    command = getattr(args, "cv_command", None)
    if not command:
        args._cv_parser.print_help()
        return 2
    try:
        if command == "doctor":
            return _cmd_doctor()
        if command == "example":
            return _cmd_example(args)
        if command == "import":
            return _cmd_import(args, input_fn, output_fn)
        if command == "convert":
            return _cmd_convert(args)
        if command == "render":
            return _cmd_render(args)
        if command == "build":
            return _cmd_build(args)
        if command == "verify":
            return _cmd_verify(args)
    except (CvError, CvImportError) as exc:
        _err(f"\n{exc}\n")
        return 1
    except ConfigError as exc:
        _err(f"\n{exc}\n")
        return 2
    _err(f"Unknown cv command {command!r}.")  # pragma: no cover - argparse rejects it first
    return 2


# --- Helpers -----------------------------------------------------------------

def _load_resume(path: str) -> Resume:
    file = Path(path).expanduser()
    if not file.is_file():
        raise CvError(
            f"No resume at {file}. Draft one from your CV with `job-scout cv import your-cv.pdf`, "
            f"or start from a neutral example with `job-scout cv example`."
        )
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CvError(f"{file} is not valid YAML:\n{exc}") from exc
    try:
        return validate(data)
    except ValueError as exc:
        raise CvError(f"{file}: {exc}") from exc


def _refuse_overwrite(out: Path, force: bool) -> None:
    if out.exists() and not force:
        raise CvError(
            f"{out} already exists, and overwriting it would lose any edits you made. "
            f"Pass --force to replace it, or --out to write somewhere else."
        )


def _write(out: Path, text: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


# --- Commands ----------------------------------------------------------------

def _cmd_doctor() -> int:
    platform = doctor.current_platform()
    print(doctor.report(doctor.diagnose(), platform))
    return 0


def _cmd_example(args: argparse.Namespace) -> int:
    target = Path(args.directory).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    written, kept = [], []
    for name in EXAMPLE_FILES:
        # The example resume is shipped as resume.example.yaml but is meant to be
        # edited, so it lands as resume.yaml, the name every other command expects.
        destination = target / ("resume.yaml" if name == "resume.example.yaml" else name)
        if destination.exists() and not args.force:
            kept.append(destination)
            continue
        shutil.copyfile(TEMPLATE_DIR / name, destination)
        written.append(destination)
    for path in written:
        print(f"Wrote {path}")
    for path in kept:
        print(f"Kept {path}, which is already there. Pass --force to replace it.")
    print(
        f"\nNext:\n"
        f"  1. Put your own details in {target / 'resume.yaml'}.\n"
        f"  2. job-scout cv build {target / 'resume.yaml'} --template {target / 'example.tex'}\n"
        f"The example is a fictional person. Replace all of it."
    )
    return 0


def _cmd_import(
    args: argparse.Namespace,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> int:
    cv_path = Path(args.cv_file).expanduser()
    out = Path(args.out).expanduser()
    _refuse_overwrite(out, args.force)

    # Read the file before asking anything, so an unreadable CV fails before the
    # person has answered a question, and the consent prompt can say how much goes.
    cv_text = importer.read_text(cv_path)

    config_dir = resolve_config_dir(args.config_dir)
    configured, scoring_model = model_prompt.read_models(config_dir)
    spec = (args.model or configured).strip()
    interactive = _interactive()

    if spec:
        try:
            parse_spec(spec)
        except ValueError as exc:
            raise CvError(f"The model {spec!r} is not usable: {exc}") from exc
    else:
        if not interactive:
            _err(f"\n{model_prompt.CV_MODEL_UNSET}\n")
            return 2
        try:
            spec = model_prompt.choose_cv_model(scoring_model, input_fn, output_fn)
        except SetupCancelled:
            print("\nNo model chosen. Nothing was sent.")
            return 1
        config_path = config_dir / CONFIG_FILENAME
        if model_prompt.set_cv_model(config_path, spec):
            print(f'\ncv_model set to "{spec}" in {config_path}.')
        else:
            print(
                f"\nNot saved: there is no {CONFIG_FILENAME} in {config_dir}. To keep this choice, "
                f'add  cv_model: "{spec}"  to your config.yaml.'
            )

    if not args.yes:
        if not interactive:
            _err(
                "\nThis would send the whole text of your CV to a model, and there is no terminal "
                "to ask you in.\nRun it in a terminal, or pass --yes to agree in advance.\n"
            )
            return 2
        try:
            agreed = model_prompt.confirm_send(spec, cv_path, len(cv_text), input_fn, output_fn)
        except SetupCancelled:
            agreed = False
        if not agreed:
            print("\nNothing was sent.")
            return 1

    print(f"\nReading {cv_path} with {spec} ...")
    yaml_text, _ = importer.draft_resume(cv_text, spec)
    _write(out, yaml_text)
    print(f"\nWrote {out}.\n\n{importer.REVIEW_REMINDER}")
    print(f"\nThen: job-scout cv build {out} --template your-template.tex")
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    from . import ats_markdown

    draft = Path(args.draft).expanduser()
    out = Path(args.out).expanduser()
    if not draft.is_file():
        raise CvError(f"No draft at {draft}.")
    _refuse_overwrite(out, args.force)
    try:
        data = ats_markdown.parse(draft.read_text(encoding="utf-8"))
        resume = validate(data)
    except ValueError as exc:
        raise CvError(f"{draft} could not be converted: {exc}") from exc
    _write(out, importer.resume_to_yaml(resume))
    print(f"Wrote {out}. Check the education dates before you trust them.")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    resume = _load_resume(args.resume)
    out = Path(args.out).expanduser()
    renderer = renderer_for(out, args.renderer)
    template = Path(args.template).expanduser() if args.template else None
    out.parent.mkdir(parents=True, exist_ok=True)
    render(resume, renderer, template, out)
    print(f"Wrote {out}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    from .build import build_pdf

    resume_path = Path(args.resume).expanduser()
    resume = _load_resume(args.resume)
    out = Path(args.out).expanduser() if args.out else resume_path.with_suffix(".pdf")
    template = Path(args.template).expanduser()
    if not template.is_file():
        raise CvError(
            f"No template at {template}. Pass --template with the path to your own .tex file. "
            f"To start from a neutral one: job-scout cv example"
        )
    pdf = build_pdf(resume, template, out)
    print(f"Wrote {pdf}")
    print(f"Check it reads cleanly: job-scout cv verify {pdf} --resume {resume_path}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).expanduser()
    if not pdf.is_file():
        _err(f"No such file: {pdf}")
        return 2
    jd_text = None
    if args.jd:
        jd_path = Path(args.jd).expanduser()
        if not jd_path.is_file():
            _err(f"No such file: {jd_path}")
            return 2
        jd_text = jd_path.read_text(encoding="utf-8", errors="replace")

    resume_file = args.resume or (DEFAULT_RESUME if Path(DEFAULT_RESUME).is_file() else None)
    expected = verify.expected_from_resume(Path(resume_file)) if resume_file else {}
    if args.resume and not expected:
        _err(f"Could not read a name, email or phone from {args.resume}.")
        return 2
    for key in ("name", "email", "phone"):
        given = getattr(args, key)
        if given:
            expected[key] = given.strip()

    chosen = list(verify.EXTRACTORS) if args.extractor == "both" else [args.extractor]
    failed = False
    shown = 0
    for name in chosen:
        if args.extractor == "both" and name == "pdftotext" and shutil.which("pdftotext") is None:
            print("\nSkipped pdftotext: it is not on your PATH. `job-scout cv doctor` shows how to install it.")
            continue
        results, text = verify.verify(
            pdf, expected, jd_text, name, args.max_pages, args.min_chars, args.min_coverage,
        )
        if shown:
            print()
        shown += 1
        print(verify.report(pdf, name, results))
        failed = failed or any(r.verdict == verify.FAIL for r in results)
        if args.dump_text and text:
            target = Path(args.dump_text).expanduser()
            if len(chosen) > 1:
                target = target.with_suffix(f".{name}{target.suffix}")
            target.write_text(text, encoding="utf-8")
            print(f"  extracted text written to {target}")
    return 1 if failed else 0
