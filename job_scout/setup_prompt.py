"""
setup_prompt.py. Ask the person which model scores their job postings.

The scout does not pick a model for you. A hosted model and a coding assistant
on your own machine cost different things, need different setup, and score
differently, so `job-scout init` asks, and writes the answer to config.yaml.

Two model choices exist in this project, and they are separate:

  1. scoring_model. Runs on every posting that passes the keyword filter, so its
     cost grows with volume. This is the question asked here.
  2. tailor.command. Runs only on the day's best match, to draft a CV. It is a
     command, set in config.yaml with `job-scout init --with-tailoring`.
"""

import re
from collections.abc import Callable
from pathlib import Path

# (backend, what it is, what it needs, example model). The example is only
# there so a blank answer has something to fall back on. Model names change,
# so the prompt says to check the provider's list.
API_BACKENDS = (
    ("gemini", "Google Gemini API", "GOOGLE_API_KEY and the google-genai package", "gemini-3.7-flash"),
    ("openrouter", "OpenRouter (many models, pay per token)", "OPENROUTER_API_KEY", "google/gemini-3.7-flash"),
)
CLI_BACKENDS = (
    ("claude", "Claude Code on this machine", "the claude command, signed in", "sonnet"),
    ("codex", "Codex on this machine", "the codex command, signed in", "gpt-5"),
    ("grok", "Grok on this machine", "the grok command, signed in", "grok-4"),
)

INTRO = """\
Which model should score job postings?

This is the first of two model choices in this project:
  1. Scoring (asked now). Runs on every posting that passes the keyword filter,
     so what it costs grows with how many postings you search.
  2. CV drafting (optional, later). Runs only on the day's best match. It is a
     separate command, set with `job-scout init --with-tailoring`.

How should the scoring model run?
  1) API  a hosted model that you call with a key
  2) CLI  a coding assistant already installed on this machine
"""


class SetupCancelled(Exception):
    """The person ended the prompt (Ctrl-D, Ctrl-C) without choosing."""


def _ask_number(
    question: str,
    count: int,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> int:
    """Ask until the answer is a number from 1 to count. Returns it zero-based."""
    for _ in range(5):
        try:
            answer = input_fn(question).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupCancelled from exc
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer) - 1
        output_fn(f"  Type a number from 1 to {count}.")
    raise SetupCancelled


def choose_scoring_model(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    """Walk the person through API or CLI, then backend, then model. Returns "backend:model"."""
    output_fn(INTRO)
    kind = _ask_number("Choose 1 or 2: ", 2, input_fn, output_fn)
    backends = API_BACKENDS if kind == 0 else CLI_BACKENDS

    output_fn("\nWhich one?")
    for number, (_, name, needs, _) in enumerate(backends, start=1):
        output_fn(f"  {number}) {name}. Needs {needs}.")
    backend, _, _, example = backends[_ask_number("Choose a number: ", len(backends), input_fn, output_fn)]

    output_fn(
        f"\nWhich {backend} model? Model names change, so check the provider's current list."
    )
    try:
        model = input_fn(f"Model name, or press Enter for the example ({example}): ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise SetupCancelled from exc
    return f"{backend}:{model or example}"


def set_scoring_model(config_path: Path, spec: str) -> bool:
    """
    Write `scoring_model: "spec"` into config.yaml, replacing the existing line
    and keeping every comment and every other line as it was. Returns False when
    there is no scoring_model line to replace.
    """
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^scoring_model:.*$", re.MULTILINE)
    if not pattern.search(text):
        return False
    config_path.write_text(pattern.sub(f'scoring_model: "{spec}"', text, count=1), encoding="utf-8")
    return True


def choose_validator_models(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> list[str]:
    """
    Pick the models for the CV check, one at a time, up to four. Each is chosen the
    same way as the scoring model. Returns the list of "backend:model" specs.
    """
    output_fn(
        "\nWhich models should check a CV? Choose one or more, up to four. Each one\n"
        "gives its own opinion, so you can compare them. This is opt-in: the daily run\n"
        "never checks a CV."
    )
    specs: list[str] = []
    while len(specs) < 4:
        spec = choose_scoring_model(input_fn, output_fn)
        if spec not in specs:
            specs.append(spec)
        if len(specs) == 4:
            break
        try:
            more = input_fn("Add another model? Type y to add one, or press Enter to finish: ").strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupCancelled from exc
        if more != "y":
            break
    return specs
