"""
The guard that stops private content reaching a public repository.

Both directions matter. Missing a real key is the obvious failure. Flagging
ordinary prose is the one that gets the check switched off, and then it protects
nothing.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import pre_push_check as guard  # noqa: E402


def _scan(tmp_path, name: str, body: str, denylist=None, monkeypatch=None):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(guard, "REPO", tmp_path)
    return guard.scan([name], denylist or [])


# ─── Credentials ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "label,secret",
    [
        ("GitHub token", "ghp_" + "A" * 36),
        ("GitHub fine-grained token", "github_pat_" + "B" * 60),
        ("Google API key", "AIza" + "C" * 35),
        ("Apify token", "apify_api_" + "D" * 30),
        ("OpenAI-style key", "sk-" + "E" * 40),
        ("Telegram bot token", "123456789:" + "F" * 35),
        ("AWS access key", "AKIA" + "G" * 16),
    ],
)
def test_a_real_credential_is_caught(tmp_path, monkeypatch, label, secret):
    findings = _scan(tmp_path, "notes.md", f"key is {secret}\n", monkeypatch=monkeypatch)
    assert findings, f"{label} was not caught"
    assert findings[0].label == label


def test_a_password_in_a_url_is_caught(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "notes.md",
        "git clone https://someone:hunter2@github.com/x/y.git\n",
        monkeypatch=monkeypatch,
    )
    assert findings and findings[0].label == "password in a URL"


def test_a_private_key_block_is_caught(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "deploy/key", "-----BEGIN OPENSSH PRIVATE KEY-----\n",
        monkeypatch=monkeypatch,
    )
    assert any(f.label == "private key block" for f in findings)


# ─── False positives, which matter just as much ───────────────────────────────

@pytest.mark.parametrize(
    "line",
    [
        "Get a key at https://aistudio.google.com/apikey and set GOOGLE_API_KEY.",
        "Tokens look like ghp_ followed by more characters.",
        "APIFY_API_TOKEN=",
        "export GOOGLE_API_KEY=your-key-here",
        "See https://user.example.com/path for details.",
        "Run: pip install -e '.[cv]'",
    ],
)
def test_ordinary_documentation_is_not_flagged(tmp_path, monkeypatch, line):
    assert _scan(tmp_path, "docs/setup.md", line + "\n", monkeypatch=monkeypatch) == []


def test_the_redaction_module_is_allowed_to_describe_token_shapes(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "job_scout/redact.py", f'PATTERN = "ghp_{"A" * 36}"\n',
        monkeypatch=monkeypatch,
    )
    assert findings == [], "files whose job is to detect secrets must not trip the check"


# ─── Files that must never be committed ───────────────────────────────────────

@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "config.yaml",
        "profile.yaml",
        "outcomes.csv",
        "data/jobs.db",
        "VM.md",
        "job-scout/VM.md",
        "deploy/server-private.key",
        "secrets/id_ed25519",
    ],
)
def test_forbidden_filenames_are_caught(tmp_path, monkeypatch, name):
    findings = _scan(tmp_path, name, "nothing secret in here\n", monkeypatch=monkeypatch)
    assert any("must not be committed" in f.label for f in findings), name


@pytest.mark.parametrize(
    "name",
    [
        ".env.example",
        "job_scout/templates/config.yaml",
        "job_scout/templates/profile.yaml",
        "examples/denmark/profile.yaml",
        "examples/outcomes.csv.sample",
        "docs/setup-systemd.md",
    ],
)
def test_the_shipped_examples_are_allowed(tmp_path, monkeypatch, name):
    findings = _scan(tmp_path, name, "example content\n", monkeypatch=monkeypatch)
    assert not any("must not be committed" in f.label for f in findings), name


# ─── The private word list ────────────────────────────────────────────────────

def test_a_private_term_is_caught(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "docs/setup.md",
        "The box lives at 203.0.113.10 and belongs to Someone Realname.\n",
        denylist=["203.0.113.10", "someone realname"],
        monkeypatch=monkeypatch,
    )
    assert len(findings) == 2
    assert all(f.label == "private term" for f in findings)


def test_private_terms_match_regardless_of_case(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "docs/setup.md", "Deployed at ACMECORP today.\n",
        denylist=["acmecorp"], monkeypatch=monkeypatch,
    )
    assert len(findings) == 1


def test_no_word_list_still_checks_credentials(tmp_path, monkeypatch):
    findings = _scan(
        tmp_path, "notes.md", f"ghp_{'A' * 36}\n", denylist=[], monkeypatch=monkeypatch
    )
    assert findings


def test_the_word_list_is_read_from_an_env_var(tmp_path, monkeypatch):
    listing = tmp_path / "private.txt"
    listing.write_text("# a comment\n\nAcmeCorp\n  spaced  \n", encoding="utf-8")
    monkeypatch.setenv("JOB_SCOUT_DENYLIST", str(listing))
    monkeypatch.setattr(guard, "REPO", tmp_path)
    assert guard.load_denylist() == ["acmecorp", "spaced"]


def test_no_word_list_anywhere_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_DENYLIST", raising=False)
    monkeypatch.setattr(guard, "REPO", tmp_path)
    assert guard.load_denylist() == []


# ─── The repository this ships in has to pass its own check ───────────────────

def test_this_repository_is_clean():
    """If this fails, something private has already been committed here."""
    monkey_free_names = guard.files_to_check("tree", None)
    assert monkey_free_names, "git ls-files returned nothing"
    findings = guard.scan(monkey_free_names, [])
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_checker_exits_non_zero_when_it_finds_something(tmp_path, monkeypatch, capsys):
    (tmp_path / "leak.md").write_text(f"ghp_{'A' * 36}\n", encoding="utf-8")
    monkeypatch.setattr(guard, "REPO", tmp_path)
    monkeypatch.setattr(guard, "files_to_check", lambda mode, rev: ["leak.md"])
    monkeypatch.delenv("JOB_SCOUT_DENYLIST", raising=False)
    assert guard.main([]) == 1
    assert "DO NOT PUSH" in capsys.readouterr().err


def test_an_allowed_file_is_still_checked_for_personal_terms(tmp_path, monkeypatch):
    """
    The allowlist exists so a file whose job is detecting secrets can contain
    secret-shaped strings. It must not become a hole where somebody's real name
    or server address passes unnoticed.
    """
    findings = _scan(
        tmp_path, "tests/test_redact.py",
        f'SECRET = "ghp_{"A" * 36}"  # deployed from /opt/somewhere-real\n',
        denylist=["/opt/somewhere-real"],
        monkeypatch=monkeypatch,
    )
    labels = [f.label for f in findings]
    assert "private term" in labels, "the word list must apply everywhere"
    assert "GitHub token" not in labels, "shapes are still exempt in an allowed file"


# ─── Commit metadata, which a push publishes just as surely as the files ──────

def test_a_private_term_in_a_commit_author_is_caught(monkeypatch):
    """
    The leak that actually happened. Every commit carried a real email, the
    files were spotless, and no file-content check would ever have seen it.
    """
    monkeypatch.setattr(
        guard, "commit_identities",
        lambda rev: [("abc1234", "Real Name <real.person@gmail.com>")],
    )
    findings = guard.scan_identities(None, ["real.person"])
    assert len(findings) == 1
    assert findings[0].label == "private term in commit author"


def test_a_clean_commit_author_passes(monkeypatch):
    monkeypatch.setattr(
        guard, "commit_identities",
        lambda rev: [("abc1234", "somehandle <somehandle@users.noreply.github.com>")],
    )
    assert guard.scan_identities(None, ["real.person"]) == []


def test_a_committer_differing_from_the_author_is_also_checked(monkeypatch):
    monkeypatch.setattr(
        guard, "commit_identities",
        lambda rev: [
            ("abc1234", "handle <handle@users.noreply.github.com>"),
            ("abc1234", "Real Name <real.person@gmail.com>"),
        ],
    )
    assert len(guard.scan_identities(None, ["real.person"])) == 1


def test_this_repository_has_no_private_identity_in_its_history():
    """The rule: no real name or email in a public repo, commit metadata included."""
    denylist = guard.load_denylist()
    if not denylist:
        pytest.skip("no private word list on this machine")
    findings = guard.scan_identities(None, denylist)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_require_denylist_refuses_when_there_is_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(guard, "REPO", tmp_path)
    monkeypatch.delenv("JOB_SCOUT_DENYLIST", raising=False)
    assert guard.main(["--require-denylist"]) == 2
    assert "Restore it" in capsys.readouterr().err
