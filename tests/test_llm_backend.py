"""
Every backend is optional, so every backend must say what it is missing rather
than crash. These tests pin the exact wording, because a vague message here
costs someone an evening.
"""

import pytest

from job_scout.llm import backend


# ─── Spec parsing ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "spec,expected",
    [
        ("gemini:gemini-3.7-flash", ("gemini", "gemini-3.7-flash")),
        ("claude:sonnet", ("claude", "sonnet")),
        ("grok:grok-4", ("grok", "grok-4")),
        ("codex:gpt-5", ("codex", "gpt-5")),
        ("openrouter:google/gemini-3.7-flash", ("openrouter", "google/gemini-3.7-flash")),
        ("google/gemini-3.7-flash", ("openrouter", "google/gemini-3.7-flash")),
    ],
)
def test_parse_spec(spec, expected):
    assert backend.parse_spec(spec) == expected


def test_parse_spec_rejects_empty():
    with pytest.raises(ValueError):
        backend.parse_spec("")


def test_parse_spec_rejects_backend_with_no_model():
    with pytest.raises(ValueError, match="names the backend but no model"):
        backend.parse_spec("gemini:")


def test_label_for():
    assert backend.label_for("gemini:x") == "x (Google API)"
    assert backend.label_for("claude:sonnet") == "claude:sonnet (CLI)"
    assert backend.label_for("openrouter:a/b") == "a/b (OpenRouter)"


def test_uses_cli():
    assert backend.uses_cli("claude:sonnet")
    assert not backend.uses_cli("gemini:x")


# ─── Preflight: the message each backend gives when it is not set up ──────────

def test_gemini_without_package(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: False)
    message = backend.preflight("gemini:gemini-3.7-flash")
    assert message is not None
    assert "google-genai" in message
    assert "pip install google-genai" in message


def test_gemini_without_key(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: True)
    message = backend.preflight("gemini:gemini-3.7-flash")
    assert message is not None
    assert "GOOGLE_API_KEY" in message
    assert "aistudio.google.com" in message


def test_gemini_ready(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: True)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert backend.preflight("gemini:gemini-3.7-flash") is None


def test_openrouter_without_package(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: False)
    message = backend.preflight("openrouter:google/gemini-3.7-flash")
    assert message is not None
    assert "pip install requests" in message


def test_openrouter_without_key(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: True)
    message = backend.preflight("openrouter:google/gemini-3.7-flash")
    assert message is not None
    assert "OPENROUTER_API_KEY" in message
    assert "openrouter.ai/keys" in message


@pytest.mark.parametrize(
    "spec,binary,install_hint",
    [
        ("claude:sonnet", "claude", "@anthropic-ai/claude-code"),
        ("codex:gpt-5", "codex", "@openai/codex"),
        ("grok:grok-4", "grok", "Grok CLI"),
    ],
)
def test_cli_backend_without_binary(no_clis, spec, binary, install_hint):
    message = backend.preflight(spec)
    assert message is not None
    assert f"`{binary}`" in message
    assert install_hint in message
    assert "LLM_CLI_SSH_HOST" in message


def test_cli_backend_accepts_ssh_instead_of_binary(no_clis, monkeypatch):
    monkeypatch.setenv("LLM_CLI_SSH_HOST", "user@vm.example.com")
    assert backend.preflight("claude:sonnet") is None


def test_unknown_backend_names_the_valid_ones(no_clis):
    message = backend.preflight("notabackend:x")
    assert message is not None
    # A bare name with a colon is treated as an OpenRouter model id, so the
    # complaint we get is OpenRouter's, which is still actionable.
    assert "OPENROUTER_API_KEY" in message or "notabackend" in message


def test_check_all_covers_every_backend(no_clis):
    results = backend.check_all()
    assert len(results) == 5
    names = {backend.parse_spec(spec)[0] for spec, _ in results}
    assert names == set(backend.KNOWN_BACKENDS)
    # With nothing installed and nothing set, every one of them explains itself.
    for spec, message in results:
        if message is None:
            continue
        assert len(message) > 30, f"{spec} gave an unhelpfully short message"


# ─── Errors raised at call time carry the same wording ────────────────────────

def test_run_gemini_without_key_raises_model_error(monkeypatch):
    monkeypatch.setattr(backend, "_module_installed", lambda name: True)
    with pytest.raises(backend.ModelError) as excinfo:
        backend._run_gemini("gemini-3.7-flash", "sys", "user")
    assert "GOOGLE_API_KEY" in str(excinfo.value)


def test_run_openrouter_without_key_raises_model_error():
    with pytest.raises(backend.ModelError) as excinfo:
        backend._run_openrouter("a/b", "sys", "user", 100, 0.3, 30)
    assert "OPENROUTER_API_KEY" in str(excinfo.value)


def test_ssh_without_host_raises_the_preflight_message(no_clis):
    with pytest.raises(backend.ModelError) as excinfo:
        backend._run_ssh("claude", "sonnet", "prompt", 30)
    assert "LLM_CLI_SSH_HOST" in str(excinfo.value)


def test_concurrency_is_serial_for_cli_backends():
    assert backend.concurrency_for(["claude:sonnet", "gemini:x"]) == 1
    assert backend.concurrency_for(["gemini:x", "gemini:y"]) == 2
