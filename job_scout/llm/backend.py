#!/usr/bin/env python3
"""
backend.py — One entry point for every model call.

You pick a backend in config.yaml with `scoring_model: "backend:model"`. All five
backends are optional. You install what the one you picked needs, and nothing
else. Choosing a backend you have not set up produces a sentence telling you what
to install or which variable to set — never a stack trace.

    gemini:gemini-2.5-flash              Google API. Needs the google-genai
                                         package and GOOGLE_API_KEY. Free tier.
    openrouter:google/gemini-2.5-flash   OpenRouter HTTP API. Needs requests and
                                         OPENROUTER_API_KEY. Pay per token.
    claude:sonnet                        Claude Code CLI. Needs the `claude`
                                         binary. Runs on your subscription.
    grok:grok-4                          Grok CLI. Needs the `grok` binary.
    codex:gpt-5                          Codex CLI. Needs the `codex` binary.

Where a CLI backend runs:

    1. If the binary is on the local PATH, it runs locally.
    2. Otherwise, if LLM_CLI_SSH_HOST is set, it runs on that host over SSH.
    3. Otherwise the call fails with a message naming both options.

Environment variables the CLI backends read:

    LLM_CLI_SSH_HOST     e.g. ubuntu@vm.example.com
    LLM_CLI_SSH_KEY      path to the private key
    LLM_CLI_ENV_FILE     file sourced on the remote host before the CLI runs
                         (default: ~/.llm-cli-env)
    LLM_CLI_TIMEOUT      seconds per call (default 600)
    LLM_CLI_CONCURRENCY  parallel CLI calls (default 1)
    LLM_CLI_FORCE_SSH    set to 1 to skip the local binary and always use SSH
"""

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_DEFAULT_TIMEOUT = 600
_DEFAULT_REMOTE_ENV = "~/.llm-cli-env"

# Binary name per CLI backend.
_BINARIES = {"claude": "claude", "grok": "grok", "codex": "codex"}

# Every backend name the spec parser recognises.
KNOWN_BACKENDS = ("gemini", "openrouter", "claude", "grok", "codex")

# What to tell someone whose CLI is not installed. Only commands that are
# actually correct are quoted; where a vendor's install path varies, the
# message names the binary and the SSH escape hatch instead of guessing.
_CLI_INSTALL_HINT = {
    "claude": "Install it with: npm install -g @anthropic-ai/claude-code",
    "codex": "Install it with: npm install -g @openai/codex",
    "grok": "Install the Grok CLI from xAI so that `grok` is on your PATH",
}


class ModelError(RuntimeError):
    """A model call failed. The message is shown to the user as-is."""


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------

def parse_spec(spec: str) -> tuple[str, str]:
    """
    Split a model spec into (backend, model_id).

    'claude:sonnet'                    -> ('claude', 'sonnet')
    'gemini:gemini-2.5-flash'          -> ('gemini', 'gemini-2.5-flash')
    'openrouter:openai/gpt-4o'         -> ('openrouter', 'openai/gpt-4o')
    'openai/gpt-4o'                    -> ('openrouter', 'openai/gpt-4o')
    """
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("empty model spec")

    backend, sep, model = spec.partition(":")
    if sep and backend in KNOWN_BACKENDS:
        model = model.strip()
        if not model:
            raise ValueError(
                f"model spec '{spec}' names the backend but no model. "
                f"Write it as '{backend}:<model-id>'."
            )
        return backend, model
    # No recognised prefix: treat a bare 'vendor/model' id as OpenRouter.
    return "openrouter", spec


def label_for(spec: str) -> str:
    """Human-readable name for logs, e.g. 'claude:sonnet (CLI)'."""
    backend, model = parse_spec(spec)
    if backend == "openrouter":
        return f"{model} (OpenRouter)"
    if backend == "gemini":
        return f"{model} (Google API)"
    return f"{backend}:{model} (CLI)"


def uses_cli(spec: str) -> bool:
    return parse_spec(spec)[0] in _BINARIES


# ---------------------------------------------------------------------------
# Preflight — say what is missing before spending a run finding out
# ---------------------------------------------------------------------------

def _module_installed(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return False


def preflight(spec: str) -> str | None:
    """
    Return None if this backend can run right now, else one sentence naming
    exactly what is missing and how to supply it.
    """
    try:
        backend, model = parse_spec(spec)
    except ValueError as exc:
        return (
            f"scoring_model '{spec}' is not usable: {exc} "
            f"Pick one of: {', '.join(KNOWN_BACKENDS)}."
        )

    if backend == "gemini":
        if not _module_installed("google.genai"):
            return (
                "Backend 'gemini' needs the google-genai package, which is not "
                "installed. Install it with: pip install google-genai"
            )
        if not os.getenv("GOOGLE_API_KEY", "").strip():
            return (
                "Backend 'gemini' needs GOOGLE_API_KEY, which is not set. "
                "Get a free key at https://aistudio.google.com/apikey and put "
                "GOOGLE_API_KEY=... in your .env file."
            )
        return None

    if backend == "openrouter":
        if not _module_installed("requests"):
            return (
                "Backend 'openrouter' needs the requests package, which is not "
                "installed. Install it with: pip install requests"
            )
        if not os.getenv("OPENROUTER_API_KEY", "").strip():
            return (
                "Backend 'openrouter' needs OPENROUTER_API_KEY, which is not set. "
                "Create a key at https://openrouter.ai/keys and put "
                "OPENROUTER_API_KEY=... in your .env file."
            )
        return None

    if backend in _BINARIES:
        binary = _BINARIES[backend]
        force_ssh = os.getenv("LLM_CLI_FORCE_SSH", "").strip().lower() in ("1", "true", "yes")
        have_local = bool(shutil.which(binary)) and not force_ssh
        have_ssh = bool(os.getenv("LLM_CLI_SSH_HOST", "").strip())
        if have_local or have_ssh:
            return None
        return (
            f"Backend '{backend}' needs the `{binary}` command, which is not on "
            f"your PATH. {_CLI_INSTALL_HINT[backend]}, or run it on another "
            f"machine by setting LLM_CLI_SSH_HOST=user@host (and LLM_CLI_SSH_KEY "
            f"if the key is not your default one)."
        )

    return f"Unknown backend '{backend}'. Pick one of: {', '.join(KNOWN_BACKENDS)}."


def check_all(specs: tuple[str, ...] | None = None) -> list[tuple[str, str | None]]:
    """
    Preflight one representative spec per backend and return
    [(spec, None-if-ready-else-message), ...]. Used by `job-scout check`.
    """
    if specs is None:
        specs = (
            "gemini:gemini-2.5-flash",
            "openrouter:google/gemini-2.5-flash",
            "claude:sonnet",
            "grok:grok-4",
            "codex:gpt-5",
        )
    return [(spec, preflight(spec)) for spec in specs]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _flatten(system: str, user: str) -> str:
    """
    The CLIs take a single prompt, not a system/user pair. Fold the system
    prompt in as a leading instruction block and tell the agent to answer from
    the text alone — otherwise it will try to open files and run commands.
    """
    return (
        f"{system.strip()}\n\n"
        "Answer using only the text below. Do not read files, run commands, "
        "search the web, or use any tools. Reply with the analysis text only, "
        "with no preamble and no closing remarks.\n\n"
        f"{user.strip()}"
    )


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def _local_argv(backend: str, model: str, prompt: str, out_file: str) -> list[str]:
    if backend == "claude":
        return [
            "claude", "-p", prompt,
            "--model", model,
            "--disallowedTools", "Bash", "Edit", "Write", "WebFetch", "WebSearch",
        ]
    if backend == "grok":
        return [
            "grok", "-p", prompt,
            "--model", model,
            "--always-approve",
            "--disable-web-search",
        ]
    if backend == "codex":
        return [
            "codex", "exec", "-",
            "--model", model,
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "-o", out_file,
        ]
    raise ValueError(f"unknown CLI backend: {backend}")


def _remote_script(backend: str, model: str) -> str:
    """
    Bash run on the remote host. The prompt arrives on stdin as base64, so no
    quoting or encoding problem can corrupt a posting that contains quotes,
    newlines or emoji.
    """
    env_file = os.getenv("LLM_CLI_ENV_FILE", _DEFAULT_REMOTE_ENV)
    header = (
        "set -eu\n"
        f'ENVF="{env_file}"\n'
        'ENVF="${ENVF/#\\~/$HOME}"\n'
        'if [ -f "$ENVF" ]; then set -a; . "$ENVF"; set +a; fi\n'
        'export PATH="$HOME/.local/bin:$HOME/.grok/bin:$PATH"\n'
        'd=$(mktemp -d)\n'
        'trap "rm -rf $d" EXIT\n'
        'base64 -d > "$d/prompt.txt"\n'
        'p=$(cat "$d/prompt.txt")\n'
    )
    # Every CLI gets "< /dev/null". The script itself arrives on bash's stdin,
    # and an agent CLI that reads stdin will otherwise swallow the lines below
    # it and treat them as part of the prompt.
    if backend == "claude":
        body = (
            f'claude -p "$p" --model {model} '
            "--disallowedTools Bash Edit Write WebFetch WebSearch < /dev/null\n"
        )
    elif backend == "grok":
        body = (
            f'grok -p "$p" --model {model} '
            "--always-approve --disable-web-search < /dev/null\n"
        )
    elif backend == "codex":
        body = (
            f'codex exec "$p" --model {model} --sandbox read-only '
            '--skip-git-repo-check -o "$d/out.txt" < /dev/null > /dev/null 2>&1\n'
            'cat "$d/out.txt"\n'
        )
    else:
        raise ValueError(f"unknown CLI backend: {backend}")
    return header + body


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _run_local(backend: str, model: str, prompt: str, timeout: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out_file = str(Path(tmp) / "out.txt")
        argv = _local_argv(backend, model, prompt, out_file)
        stdin_text = prompt if backend == "codex" else None
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if backend == "codex":
            produced = Path(out_file)
            if produced.exists() and produced.read_text(encoding="utf-8").strip():
                return produced.read_text(encoding="utf-8").strip()
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ModelError(f"{backend} CLI exited {proc.returncode}: {detail[:400]}")
        text = (proc.stdout or "").strip()
        if not text:
            raise ModelError(f"{backend} CLI returned no output")
        return text


def _run_ssh(backend: str, model: str, prompt: str, timeout: int) -> str:
    host = os.getenv("LLM_CLI_SSH_HOST", "").strip()
    key = os.getenv("LLM_CLI_SSH_KEY", "").strip()
    if not host:
        raise ModelError(preflight(f"{backend}:{model}") or f"{backend} CLI unavailable")

    argv = ["ssh"]
    if key:
        argv += ["-i", key]
    argv += [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ServerAliveInterval=30",
        host,
        "bash -s",
    ]

    script = _remote_script(backend, model)
    payload = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    # The script consumes the base64 prompt from its own stdin, so send the
    # script with the payload already inlined.
    stdin_text = script.replace(
        'base64 -d > "$d/prompt.txt"\n',
        f"printf %s '{payload}' | base64 -d > \"$d/prompt.txt\"\n",
    )

    # Binary stdin: on Windows, text mode rewrites "\n" as "\r\n" and bash then
    # chokes on the stray carriage returns.
    proc = subprocess.run(
        argv,
        input=stdin_text.encode("utf-8"),
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        raise ModelError(f"{backend} CLI over SSH exited {proc.returncode}: {detail[:400]}")
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if not text:
        raise ModelError(f"{backend} CLI over SSH returned no output")
    return text


def _run_gemini(model: str, system: str, user: str) -> str:
    # google-genai warns on every generate_content call that we should be using
    # its chat API. We send one prompt and want one reply, so there is nothing
    # to act on, and the warning lands in the user's terminal on every run.
    import logging

    logging.getLogger("google_genai").setLevel(logging.ERROR)

    try:
        from google import genai
    except ImportError as exc:
        raise ModelError(
            "Backend 'gemini' needs the google-genai package, which is not "
            "installed. Install it with: pip install google-genai"
        ) from exc

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ModelError(
            "Backend 'gemini' needs GOOGLE_API_KEY, which is not set. Get a free "
            "key at https://aistudio.google.com/apikey and put GOOGLE_API_KEY=... "
            "in your .env file."
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model, contents=f"{system.strip()}\n\n{user.strip()}"
    )
    text = (response.text or "").strip()
    if not text:
        raise ModelError(f"{model} returned no text")
    return text


def _run_openrouter(model: str, system: str, user: str,
                    max_tokens: int, temperature: float, timeout: int) -> str:
    try:
        import requests
    except ImportError as exc:
        raise ModelError(
            "Backend 'openrouter' needs the requests package, which is not "
            "installed. Install it with: pip install requests"
        ) from exc

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ModelError(
            "Backend 'openrouter' needs OPENROUTER_API_KEY, which is not set. "
            "Create a key at https://openrouter.ai/keys and put "
            "OPENROUTER_API_KEY=... in your .env file."
        )

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/0xarmingithub/job-scout",
            "X-Title": "Job Scout",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    if not content:
        raise ModelError(f"empty response content: {str(data)[:300]}")
    return content.strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_model(spec: str, system: str, user: str,
              max_tokens: int = 2048, temperature: float = 0.3) -> str:
    """
    Call one model and return its text. Raises ModelError on failure.

    system/temperature/max_tokens apply to the OpenRouter path. The CLI path
    folds the system prompt into the single prompt the CLI accepts and leaves
    sampling to the CLI's own defaults.
    """
    backend, model = parse_spec(spec)
    timeout = int(os.getenv("LLM_CLI_TIMEOUT", _DEFAULT_TIMEOUT))

    if backend == "openrouter":
        return _run_openrouter(model, system, user, max_tokens, temperature, timeout)
    if backend == "gemini":
        return _run_gemini(model, system, user)

    prompt = _flatten(system, user)
    force_ssh = os.getenv("LLM_CLI_FORCE_SSH", "").strip().lower() in ("1", "true", "yes")
    try:
        if not force_ssh and shutil.which(_BINARIES[backend]):
            return _run_local(backend, model, prompt, timeout)
        return _run_ssh(backend, model, prompt, timeout)
    except subprocess.TimeoutExpired as exc:
        raise ModelError(f"{backend}:{model} timed out after {timeout}s") from exc


def concurrency_for(specs: list[str]) -> int:
    """
    How many calls to run at once. Each CLI process takes 200-400 MB, so CLI
    runs default to 1. HTTP backends stay parallel.
    """
    if any(uses_cli(s) for s in specs):
        return max(1, int(os.getenv("LLM_CLI_CONCURRENCY", "1")))
    return max(1, len(specs))
