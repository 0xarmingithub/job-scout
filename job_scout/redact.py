"""
redact.py — Strip credentials out of text before it leaves the machine.

Error text from git, HTTP libraries and subprocesses routinely echoes back the
thing you least want in a chat message: a token, or a URL with a password in it.
Every notifier runs its payload through redact() first.
"""

import re

# GitHub token shapes (ghp_/gho_/ghs_/ghu_/ghr_ + github_pat_), generic bearer
# tokens in a header dump, Apify/Google-style long keys in a query string, and
# any user:password embedded in a URL.
_PATTERNS = [
    # GitHub personal access tokens, OAuth tokens, server/user/refresh tokens.
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "***REDACTED***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "***REDACTED***"),
    # Google AI Studio keys.
    (re.compile(r"AIza[A-Za-z0-9_\-]{20,}"), "***REDACTED***"),
    # Apify tokens.
    (re.compile(r"apify_api_[A-Za-z0-9]{20,}"), "***REDACTED***"),
    # OpenRouter / OpenAI-style keys.
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "***REDACTED***"),
    # Telegram bot tokens: <digits>:<35 base64-ish chars>.
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}"), "***REDACTED***"),
    # Bearer tokens in a header dump.
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1***REDACTED***"),
    # A token= or api_key= query parameter.
    (re.compile(r"(?i)([?&](?:token|api_?key|access_token)=)[^&\s]+"), r"\1***REDACTED***"),
    # user:password@host inside a URL.
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://***REDACTED***@"),
]


def redact(text: str) -> str:
    """Replace every credential shape we know about with ***REDACTED***."""
    if not text:
        return ""
    out = str(text)
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out
