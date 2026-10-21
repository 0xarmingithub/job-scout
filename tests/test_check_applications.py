"""
tools/check_applications.py: every application folder has a Status line.

The failure it guards is an application that silently drops out of the scorer's
and calibrate's view. Nothing crashes when it happens; the folder is simply
missing from the record.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_applications as check  # noqa: E402


def _folder(root, name, notes="- **Status:** drafted\n"):
    folder = root / name
    folder.mkdir(parents=True)
    if notes is not None:
        (folder / "notes.md").write_text(notes, encoding="utf-8")
    return folder


def test_every_folder_with_a_status_passes(tmp_path, capsys):
    _folder(tmp_path, "contoso-kiosk-attendant-20250421")
    _folder(tmp_path, "fabrikam-night-auditor-20250422", notes="# Notes\n\n**Status:** rejected\n")
    assert check.main([str(tmp_path)]) == 0
    assert "All 2 application folder(s)" in capsys.readouterr().out


def test_a_folder_without_notes_fails_and_is_named(tmp_path, capsys):
    _folder(tmp_path, "contoso-kiosk-attendant-20250421")
    _folder(tmp_path, "fabrikam-night-auditor-20250422", notes=None)
    assert check.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "fabrikam-night-auditor-20250422: no notes.md" in out
    assert "contoso-kiosk-attendant-20250421" not in out
    assert "1 of 2" in out


def test_a_notes_file_without_a_status_line_fails(tmp_path, capsys):
    _folder(tmp_path, "contoso-kiosk-attendant-20250421", notes="Sent it on a Tuesday, nothing back so far.\n")
    assert check.main([str(tmp_path)]) == 1
    assert "no **Status:** line" in capsys.readouterr().out


def test_a_status_line_with_nothing_after_it_fails(tmp_path):
    _folder(tmp_path, "contoso-kiosk-attendant-20250421", notes="**Status:**\n")
    assert check.main([str(tmp_path)]) == 1


def test_a_plain_status_word_without_bold_does_not_count(tmp_path):
    """The reader that feeds the scorer needs the bold form, so the gate must too."""
    _folder(tmp_path, "contoso-kiosk-attendant-20250421", notes="Status: submitted\n")
    assert check.main([str(tmp_path)]) == 1


def test_templates_and_loose_files_are_not_applications(tmp_path):
    _folder(tmp_path, "_template", notes=None)
    _folder(tmp_path, ".archive", notes=None)
    (tmp_path / "README.md").write_text("how this folder works", encoding="utf-8")
    _folder(tmp_path, "contoso-kiosk-attendant-20250421")
    assert check.main([str(tmp_path)]) == 0


def test_an_empty_folder_of_applications_passes(tmp_path, capsys):
    assert check.main([str(tmp_path)]) == 0
    assert "All 0" in capsys.readouterr().out


def test_a_directory_that_does_not_exist_is_exit_two_not_a_pass(tmp_path, capsys):
    assert check.main([str(tmp_path / "nowhere")]) == 2
    assert "is not a directory" in capsys.readouterr().err
