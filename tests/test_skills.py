"""
The agent skills and the CV workflow docs are instructions people follow, so
they are tested like code: they have to parse, link to things that exist, and
follow the house style (no em or en dashes, fictional placeholders only).
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
CV_TEMPLATES = REPO_ROOT / "templates" / "cv"
CV_WORKFLOW_DOC = REPO_ROOT / "docs" / "cv-workflow.md"

# Em dash, en dash, and the look-alikes that read the same way in prose.
DASH_CHARACTERS = re.compile("[‒–—―−]")

# The eight CV skills added in 1.11.0.
CV_SKILLS = {
    "jd-analyzer",
    "gap-analysis",
    "resume-tailor",
    "metrics-auditor",
    "interview-prep",
    "cover-letter",
    "ats-compatibility-check",
    "master-resume-curator",
}

# Files another release is adding. A link to one of these is allowed to be
# dangling until that file lands; remove the entry once docs/applications.md
# exists, so the link is checked like every other.
PENDING_TARGETS: set[str] = set()


def _skill_folders() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def _front_matter(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with a --- front matter block"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict), "front matter must be a YAML mapping"
    return data


def _text_files_we_ship() -> list[Path]:
    files = sorted(SKILLS_DIR.rglob("*.md")) + sorted(CV_TEMPLATES.rglob("*.md"))
    files.append(CV_WORKFLOW_DOC)
    return files


def test_there_are_skills_to_check():
    assert CV_SKILLS <= {p.name for p in _skill_folders()}


@pytest.mark.parametrize("folder", _skill_folders(), ids=lambda p: p.name)
def test_every_skill_has_a_skill_md_with_name_and_description(folder: Path):
    skill_md = folder / "SKILL.md"
    assert skill_md.is_file(), f"{folder.name} has no SKILL.md"

    meta = _front_matter(skill_md.read_text(encoding="utf-8"))
    assert meta.get("name") == folder.name, (
        f"front matter name {meta.get('name')!r} must match the folder name {folder.name!r}"
    )
    description = str(meta.get("description") or "").strip()
    assert len(description) >= 40, f"{folder.name} needs a real description, not {description!r}"


@pytest.mark.parametrize("path", _text_files_we_ship(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_em_or_en_dashes(path: Path):
    text = path.read_text(encoding="utf-8")
    found = DASH_CHARACTERS.search(text)
    assert not found, (
        f"{path.relative_to(REPO_ROOT)} contains a dash character at offset {found.start()}. "
        f"Use a comma, a full stop, parentheses or a hyphen."
    )


def test_cv_templates_exist_and_use_the_fictional_candidate():
    master = (CV_TEMPLATES / "master-content.md").read_text(encoding="utf-8")
    assert "Morgan Reyes" in master, "the blank master file must use the fictional candidate"
    for name in ("master-content.md", "voice-and-tone.md", "best-practices.md"):
        assert (CV_TEMPLATES / name).is_file(), f"templates/cv/{name} is missing"


def test_the_humanizer_is_credited_and_not_bundled():
    """It is blader/humanizer (MIT). We point at it; we do not ship a copy."""
    assert not (SKILLS_DIR / "humanizer").exists(), "do not bundle the third-party humanizer"

    tailor = (SKILLS_DIR / "resume-tailor" / "SKILL.md").read_text(encoding="utf-8")
    workflow = CV_WORKFLOW_DOC.read_text(encoding="utf-8")
    for name, text in (("resume-tailor", tailor), ("cv-workflow", workflow)):
        assert "blader/humanizer" in text, f"{name} must credit blader/humanizer"
        assert "MIT" in text, f"{name} must state the licence"


# ─── Commands owned by other releases must say when they exist ────────────────

FUTURE_COMMANDS = re.compile(r"`job-scout (outcomes|privacy|cv (?:doctor|import|render|build|verify))")


@pytest.mark.parametrize(
    "path",
    sorted(SKILLS_DIR.rglob("SKILL.md")) + [CV_WORKFLOW_DOC],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_planned_commands_say_which_release_adds_them(path: Path):
    """
    `job-scout cv build` and friends do not exist before 1.10.0. A skill that
    names one without saying so sends the reader to a command that fails.
    """
    text = path.read_text(encoding="utf-8")
    if FUTURE_COMMANDS.search(text):
        assert re.search(r"available from 1\.(8|10)\.0|from 1\.(8|10)\.0", text), (
            f"{path.relative_to(REPO_ROOT)} names a planned command without saying "
            f"which release adds it"
        )


# ─── Links ────────────────────────────────────────────────────────────────────

LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)#\s]+)(?:#[^)]*)?\)")


@pytest.mark.parametrize(
    "path",
    sorted(SKILLS_DIR.rglob("*.md")) + sorted(CV_TEMPLATES.rglob("*.md")) + [CV_WORKFLOW_DOC],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_relative_links_point_at_real_files(path: Path):
    text = path.read_text(encoding="utf-8")
    for target in LINK.findall(text):
        resolved = (path.parent / target).resolve()
        relative = resolved.relative_to(REPO_ROOT).as_posix()
        if relative in PENDING_TARGETS:
            continue
        assert resolved.exists(), f"{path.relative_to(REPO_ROOT)} links to {target}, which does not exist"
