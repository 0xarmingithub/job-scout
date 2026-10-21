"""
model_prompt.py. Which model reads your CV, and whether you agree to send it.

`job-scout cv import` is the one place in this project that sends the whole of a
CV to a model: name, contact details, every employer. So it has its own setting,
`cv_model`, with no default, and it always asks before sending.

The first time, with no `cv_model` in config.yaml, it asks one question:

    Use the same model as scoring? (Y/n)

Either answer still ends at the consent prompt, which names the backend that
will receive the text. Nothing is sent before that prompt is answered with y,
unless a script passed --yes.

Every prompt takes `input_fn` and `output_fn`, like setup_prompt.py, so a test can
drive it without a terminal.
"""

import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path

import yaml

from ..llm import parse_spec
from ..llm.backend import _BINARIES
from ..setup_prompt import API_BACKENDS, CLI_BACKENDS, SetupCancelled, _ask_number

CV_MODEL_UNSET = (
    "config.yaml has no cv_model, and this project does not choose one for you.\n"
    "Set it as backend:model in config.yaml, for example\n"
    "  cv_model: \"claude:sonnet\"\n"
    "or pass --model BACKEND:MODEL to this command, or run it in a terminal to be asked.\n"
    "See docs/cv.md."
)

# Who ends up holding the text, by backend. Only facts about the vendor's own
# service, nothing about the person's account or plan.
_RECIPIENT = {
    "gemini": "Google's Gemini API, so the text leaves this machine and goes to Google",
    "openrouter": "OpenRouter, which passes it on to whichever company runs the model",
    "claude": "the claude command, which sends it to Anthropic",
    "codex": "the codex command, which sends it to OpenAI",
    "grok": "the grok command, which sends it to xAI",
}

_YES = {"y", "yes"}
_NO = {"n", "no"}


def describe_backend(spec: str) -> str:
    """One sentence saying what the model spec is and who receives the text."""
    backend, _ = parse_spec(spec)
    recipient = _RECIPIENT.get(backend, backend)
    suffix = ""
    force_ssh = os.getenv("LLM_CLI_FORCE_SSH", "").strip().lower() in ("1", "true", "yes")
    if backend in ("claude", "codex", "grok") and (force_ssh or not shutil.which(_BINARIES[backend])):
        host = os.getenv("LLM_CLI_SSH_HOST", "").strip()
        if host:
            suffix = f", run over SSH on {host}, which is not this machine"
    return f"{spec}, through {recipient}{suffix}"


# --- Reading and writing the setting -----------------------------------------

def _read_config(config_dir: Path) -> dict:
    path = Path(config_dir) / "config.yaml"
    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_models(config_dir: Path) -> tuple[str, str]:
    """(cv_model, scoring_model) from config.yaml, each empty when not set. Needs no profile."""
    config = _read_config(config_dir)
    return (
        str(config.get("cv_model") or "").strip(),
        str(config.get("scoring_model") or "").strip(),
    )


def set_cv_model(config_path: Path, spec: str) -> bool:
    """
    Write `cv_model: "spec"` into config.yaml, keeping every comment and every
    other line. Replaces an active cv_model line, else the commented example in
    the shipped template, else appends. Returns False when there is no config.yaml.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        return False
    text = config_path.read_text(encoding="utf-8")
    line = f'cv_model: "{spec}"'
    for pattern in (r"^cv_model:.*$", r"^#\s*cv_model:.*$"):
        compiled = re.compile(pattern, re.MULTILINE)
        if compiled.search(text):
            config_path.write_text(compiled.sub(lambda _m: line, text, count=1), encoding="utf-8")
            return True
    separator = "" if text.endswith("\n") else "\n"
    config_path.write_text(f"{text}{separator}\n{line}\n", encoding="utf-8")
    return True


# --- The prompts -------------------------------------------------------------

def _read_line(question: str, input_fn: Callable[[str], str]) -> str:
    try:
        return input_fn(question).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise SetupCancelled from exc


def _yes_no(
    question: str,
    default: bool,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> bool:
    """Ask until the answer is y or n. A bare Enter takes the default."""
    for _ in range(5):
        answer = _read_line(question, input_fn).lower()
        if not answer:
            return default
        if answer in _YES:
            return True
        if answer in _NO:
            return False
        output_fn("  Type y or n.")
    raise SetupCancelled


def _walk_to_a_model(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str:
    """API or CLI, then which backend, then which model. Returns "backend:model"."""
    output_fn("How should the CV model run?\n  1) API  a hosted model that you call with a key\n"
              "  2) CLI  a coding assistant already installed on this machine")
    kind = _ask_number("Choose 1 or 2: ", 2, input_fn, output_fn)
    backends = API_BACKENDS if kind == 0 else CLI_BACKENDS

    output_fn("\nWhich one?")
    for number, (_, name, needs, _) in enumerate(backends, start=1):
        output_fn(f"  {number}) {name}. Needs {needs}.")
    backend, _, _, example = backends[
        _ask_number("Choose a number: ", len(backends), input_fn, output_fn)
    ]
    output_fn(f"\nWhich {backend} model? Model names change, so check the provider's current list.")
    model = _read_line(f"Model name, or press Enter for the example ({example}): ", input_fn)
    return f"{backend}:{model or example}"


def choose_cv_model(
    scoring_model: str = "",
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    """
    Pick the model that reads the CV. Returns "backend:model".

    When a scoring model is set, the first question is whether to reuse it. Saying
    no, or having none to reuse, walks through API or CLI, backend, then model.
    Raises SetupCancelled if the person ends the prompt.
    """
    output_fn(
        "Which model should read your CV?\n\n"
        "This is a separate choice from the model that scores job postings, because a CV\n"
        "holds your name, contact details and whole employment history, and it is sent\n"
        "to this model in full."
    )
    if scoring_model:
        output_fn(f"\nThe scoring model is {scoring_model}.")
        if _yes_no("Use the same model as scoring? (Y/n): ", True, input_fn, output_fn):
            return scoring_model
        output_fn("")
    return _walk_to_a_model(input_fn, output_fn)


def confirm_send(
    spec: str,
    source: Path,
    characters: int,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> bool:
    """
    The consent prompt. Names the file, how much of it goes, and the backend that
    receives it. The default is no. Raises SetupCancelled if the person ends the prompt.
    """
    output_fn(
        "\nImporting a CV sends its text to a model. That text has your name, contact\n"
        "details and employment history in it.\n\n"
        f"  File:     {source} ({characters:,} characters)\n"
        f"  Goes to:  {describe_backend(spec)}\n"
    )
    return _yes_no("Send it? (y/N): ", False, input_fn, output_fn)
