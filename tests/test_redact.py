"""
Everything a notifier sends goes through redact() first. These are the shapes
that have actually turned up in error text in production.
"""

import pytest

from job_scout.redact import redact


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "gho_" + "B" * 36,
        "github_pat_" + "C" * 40,
        "AIza" + "D" * 35,
        "apify_api_" + "E" * 30,
        "sk-" + "F" * 40,
        "123456789:AAH" + "G" * 30,
    ],
)
def test_credentials_never_survive(secret):
    output = redact(f"the call failed with {secret} in the message")
    assert secret not in output
    assert "REDACTED" in output


def test_a_password_in_a_url_is_removed():
    output = redact("fatal: could not read https://someone:hunter2@github.com/x/y.git")
    assert "hunter2" not in output
    assert "://***REDACTED***@github.com" in output


def test_a_bearer_header_is_removed():
    output = redact("Authorization: Bearer abcdefghijklmnop1234567890")
    assert "abcdefghijklmnop1234567890" not in output
    assert "Bearer ***REDACTED***" in output


def test_a_token_query_parameter_is_removed():
    output = redact("GET https://api.example.com/v2/items?token=supersecretvalue&limit=5")
    assert "supersecretvalue" not in output
    assert "limit=5" in output, "the rest of the URL must survive"


def test_ordinary_text_is_left_alone():
    text = "Careerjet returned 0 jobs for 'platform engineer' on page 3."
    assert redact(text) == text


def test_empty_input():
    assert redact("") == ""
    assert redact(None) == ""


def test_several_secrets_in_one_message():
    output = redact(f"first ghp_{'A' * 36} then sk-{'B' * 40}")
    assert "REDACTED" in output
    assert "ghp_A" not in output
    assert "sk-B" not in output
