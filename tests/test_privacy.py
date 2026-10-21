"""
The private word list.

Three promises matter more than the features. Nothing is added without an
answer, a non-interactive caller never waits, and the terms are never printed.
Every name here is fictional.
"""

import os
import subprocess
import sys

import pytest

from job_scout import cli, privacy
from job_scout.setup_prompt import SetupCancelled


def _answers(*given):
    queue = list(given)

    def ask(prompt):
        if not queue:
            raise EOFError
        return queue.pop(0)

    return ask


def _no_input(prompt):
    raise AssertionError("nothing should have been asked")


def _git_available():
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


needs_git = pytest.mark.skipif(not _git_available(), reason="git is not available")


@pytest.fixture
def listing(tmp_path):
    return tmp_path / "privacy.txt"


# --- Variants --------------------------------------------------------------------

def test_a_name_gets_a_reversed_form_and_a_surname():
    found = privacy.variants("name", "Morgan Reyes")
    assert found[0] == "morgan reyes"
    assert "reyes morgan" in found
    assert "reyes" in found
    assert "morgan" not in found, "a first name alone matches too much"


def test_accents_are_folded_both_ways():
    found = privacy.variants("place", "Østerby")
    assert "østerby" in found
    assert "osterby" in found
    assert "oesterby" in found


def test_an_email_adds_the_part_before_the_at_sign():
    found = privacy.variants("email", "morgan.reyes@contoso.example")
    assert "morgan.reyes@contoso.example" in found
    assert "morgan.reyes" in found


def test_a_phone_number_is_listed_without_spaces_and_without_the_plus():
    found = privacy.variants("phone", "+45 12 34 56 78")
    assert "+4512345678" in found
    assert "4512345678" in found


def test_an_employer_is_listed_without_its_legal_suffix():
    found = privacy.variants("employer", "Contoso Denmark A/S")
    assert "contoso denmark a/s" in found
    assert "contoso" in found


def test_a_key_file_is_listed_with_and_without_its_extension():
    found = privacy.variants("keyfile", "fabrikam-vm.key")
    assert "fabrikam-vm.key" in found
    assert "fabrikam-vm" in found


def test_a_repository_is_listed_with_and_without_its_owner():
    found = privacy.variants("repo", "morgan-reyes/job-search-private")
    assert "job-search-private" in found


def test_a_term_that_would_match_everything_is_not_listed():
    assert privacy.variants("other", "ab") == []
    assert privacy.variants("name", "") == []


def test_variants_are_unique_and_lowercase():
    found = privacy.variants("name", "Morgan Reyes")
    assert len(found) == len(set(found))
    assert all(item == item.lower() for item in found)


# --- The file --------------------------------------------------------------------

def test_adding_creates_the_file_with_a_header_and_skips_duplicates(listing):
    assert privacy.add_terms(listing, ["Contoso", "contoso", "Fabrikam"]) == 2
    assert privacy.add_terms(listing, ["CONTOSO"]) == 0
    assert privacy.read_terms(listing) == ["contoso", "fabrikam"]
    assert listing.read_text(encoding="utf-8").startswith("# job-scout privacy list")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no file modes")
def test_the_file_is_private_to_its_owner(listing):
    privacy.add_terms(listing, ["contoso"])
    assert (listing.stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no file modes")
def test_a_file_with_looser_permissions_is_tightened_when_written(listing):
    listing.write_text("contoso\n", encoding="utf-8")
    os.chmod(listing, 0o644)
    privacy.add_terms(listing, ["fabrikam"])
    assert (listing.stat().st_mode & 0o777) == 0o600


def test_comments_and_blank_lines_are_not_terms(listing):
    listing.write_text("# a comment\n\nContoso\n   \n# declined: Litware\n", encoding="utf-8")
    assert privacy.read_terms(listing) == ["contoso"]


def test_a_missing_file_reads_as_empty(tmp_path):
    assert privacy.read_terms(tmp_path / "none.txt") == []
    assert privacy.read_declined(tmp_path / "none.txt") == set()


# --- Where it lives ----------------------------------------------------------------

def test_an_explicit_file_wins_over_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_DENYLIST", str(tmp_path / "env.txt"))
    chosen = privacy.resolve_path(config_dir=tmp_path, file=str(tmp_path / "mine.txt"))
    assert chosen == tmp_path / "mine.txt"


def test_the_environment_variable_pre_push_check_reads_comes_next(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_DENYLIST", str(tmp_path / "env.txt"))
    assert privacy.resolve_path(config_dir=tmp_path) == tmp_path / "env.txt"


def test_a_user_keeps_the_list_in_their_config_directory(tmp_path):
    assert privacy.resolve_path(config_dir=tmp_path) == tmp_path / "privacy.txt"


def test_a_directory_with_a_config_yaml_is_a_config_directory(tmp_path):
    (tmp_path / "config.yaml").write_text("searches: []\n", encoding="utf-8")
    assert privacy.resolve_path(cwd=tmp_path) == tmp_path / "privacy.txt"


@needs_git
def test_a_contributor_keeps_it_inside_the_git_directory(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "pre_push_check.py").write_text("", encoding="utf-8")
    (tmp_path / "job_scout").mkdir()
    (tmp_path / "job_scout" / "__init__.py").write_text("", encoding="utf-8")

    chosen = privacy.resolve_path(cwd=tmp_path)

    assert chosen == (tmp_path / ".git" / "denylist.txt").resolve()


@needs_git
def test_a_users_own_repository_is_not_mistaken_for_the_project(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    assert privacy.resolve_path(cwd=tmp_path) == tmp_path / "privacy.txt"


@needs_git
def test_the_real_git_directory_is_found_from_a_worktree_too():
    """
    In a worktree `.git` is a file, so `.git/denylist.txt` is a path through a
    file. Run against whatever checkout the tests are in: a worktree here, a
    normal clone elsewhere. Either way the answer has to be a real directory.
    """
    from pathlib import Path

    here = Path(__file__).resolve().parent.parent
    common = privacy.git_common_dir(here)
    if common is None:
        pytest.skip("not a git checkout")
    assert common.is_dir()
    assert (common / "HEAD").exists()


def _init_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def _is_ignored(repo, name="privacy.txt"):
    result = subprocess.run(
        ["git", "check-ignore", "-q", name], cwd=repo, capture_output=True
    )
    return result.returncode == 0


@needs_git
def test_the_list_is_kept_out_of_a_repository_that_does_not_ignore_it(tmp_path):
    _init_repo(tmp_path)
    path = tmp_path / "privacy.txt"
    notes = []

    privacy.add_terms(path, ["contoso"], notes.append)

    assert len(notes) == 1 and "never commits" in notes[0]
    assert _is_ignored(tmp_path)
    assert privacy.keep_out_of_git(path) is None, "the second call has nothing left to do"
    lines = (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert lines.count("/privacy.txt") == 1


@needs_git
def test_a_list_git_already_tracks_gets_a_warning(tmp_path):
    _init_repo(tmp_path)
    path = tmp_path / "privacy.txt"
    path.write_text("contoso\n", encoding="utf-8")
    subprocess.run(["git", "add", "privacy.txt"], cwd=tmp_path, check=True, capture_output=True)
    notes = []

    privacy.add_terms(path, ["fabrikam"], notes.append)

    assert notes and "WARNING" in notes[0] and "git rm --cached" in notes[0]


@needs_git
def test_every_write_path_keeps_the_list_out_of_git_not_only_init_and_add(tmp_path):
    """
    The employer offer and the declined note write to the list too. Each of them
    has to leave git unable to commit it, however the file came to be written.
    """
    for case in ("accepted", "declined", "all the rest"):
        repo = tmp_path / case.replace(" ", "-")
        repo.mkdir()
        _init_repo(repo)
        path = repo / "privacy.txt"
        path.write_text("litware\n", encoding="utf-8")   # a list that already exists
        assert not _is_ignored(repo)

        answers = {"accepted": ("y", "y"), "declined": ("y", "n"), "all the rest": ("y", "a")}[case]
        privacy.offer_employers(
            ["Contoso"], path, input_fn=_answers(*answers), output_fn=lambda s: None,
            interactive=True,
        )
        assert _is_ignored(repo), case


@needs_git
def test_record_declined_alone_also_excludes_the_file(tmp_path):
    _init_repo(tmp_path)
    privacy.record_declined(tmp_path / "privacy.txt", "Contoso")
    assert _is_ignored(tmp_path)


@needs_git
def test_the_tracked_warning_is_shown_once_not_once_per_employer(tmp_path):
    _init_repo(tmp_path)
    path = tmp_path / "privacy.txt"
    path.write_text("litware\n", encoding="utf-8")
    subprocess.run(["git", "add", "privacy.txt"], cwd=tmp_path, check=True, capture_output=True)
    out = []

    privacy.offer_employers(
        ["Adatum", "Contoso", "Fabrikam"], path, input_fn=_answers("y", "a"),
        output_fn=out.append, interactive=True,
    )

    assert sum("WARNING" in line for line in out) == 1


@needs_git
def test_privacy_add_through_the_cli_excludes_the_file_and_says_so(tmp_path, capsys):
    _init_repo(tmp_path)
    path = tmp_path / "privacy.txt"
    assert cli.main(["privacy", "add", "Contoso", "--file", str(path)]) == 0
    assert "never commits" in capsys.readouterr().out
    assert _is_ignored(tmp_path)


def test_a_list_outside_any_repository_needs_nothing(tmp_path):
    assert privacy.keep_out_of_git(tmp_path / "privacy.txt") is None


# --- init --------------------------------------------------------------------------

def test_init_asks_each_question_and_saves_the_variants(listing):
    out = []
    answers = _answers(
        "Morgan Reyes", "",                      # name
        "morgan.reyes@contoso.example", "",      # email
        "",                                      # phone
        "Østerby", "",                      # place
        "Contoso A/S", "Fabrikam", "",           # employers
        "", "", "",                              # host, keyfile, repo
    )
    added = privacy.build_list(listing, answers, out.append)

    terms = privacy.read_terms(listing)
    assert added == len(terms) > 8
    for expected in ("morgan reyes", "reyes", "morgan.reyes", "osterby", "contoso", "fabrikam"):
        assert expected in terms
    assert "Saved" in "\n".join(out)


def test_init_never_prints_what_was_typed(listing):
    out = []
    privacy.build_list(listing, _answers("Morgan Reyes", "", "", "", "", "", "Contoso", "", "", "", ""), out.append)
    text = "\n".join(out).lower()
    assert "reyes" not in text
    assert "contoso" not in text


def test_init_keeps_what_was_entered_if_the_person_stops_early(listing):
    out = []
    # Ends part way through the third question with no further input.
    privacy.build_list(listing, _answers("Morgan Reyes", "", "morgan@contoso.example"), out.append)
    assert "morgan reyes" in privacy.read_terms(listing)
    assert "Stopped early" in "\n".join(out)


def test_init_adds_to_a_list_that_is_already_there(listing):
    privacy.add_terms(listing, ["litware"])
    privacy.build_list(listing, _answers("Morgan Reyes", "", "", "", "", "", "", "", "", "", "", ""), lambda s: None)
    terms = privacy.read_terms(listing)
    assert "litware" in terms and "morgan reyes" in terms


def test_init_with_no_terminal_refuses_instead_of_hanging(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    code = cli.main(["privacy", "init", "--file", str(tmp_path / "p.txt")])
    assert code == 2
    assert "needs a terminal" in capsys.readouterr().out
    assert not (tmp_path / "p.txt").exists()


# --- Offering new employers ----------------------------------------------------------

def test_a_non_interactive_call_adds_nothing_and_never_asks(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Contoso", "Fabrikam"], listing, input_fn=_no_input, output_fn=lambda s: None,
        interactive=False,
    )
    assert added == 0
    assert privacy.read_terms(listing) == ["litware"]


def test_with_no_list_yet_it_points_to_init_and_asks_nothing(tmp_path):
    out = []
    added = privacy.offer_employers(
        ["Contoso"], tmp_path / "privacy.txt", input_fn=_no_input, output_fn=out.append,
        interactive=True,
    )
    assert added == 0
    assert not (tmp_path / "privacy.txt").exists()
    assert "privacy init" in "\n".join(out)


def test_an_employer_already_listed_is_not_offered(listing):
    privacy.add_terms(listing, ["contoso"])
    added = privacy.offer_employers(
        ["Contoso Denmark A/S"], listing, input_fn=_no_input, output_fn=lambda s: None,
        interactive=True,
    )
    assert added == 0


def test_saying_no_to_the_first_question_adds_nothing(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Contoso"], listing, input_fn=_answers(""), output_fn=lambda s: None, interactive=True,
    )
    assert added == 0
    assert privacy.read_terms(listing) == ["litware"]


def test_each_employer_is_asked_about_and_only_yes_adds_it(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Contoso", "Fabrikam"], listing,
        input_fn=_answers("y", "y", "n"), output_fn=lambda s: None, interactive=True,
    )
    terms = privacy.read_terms(listing)
    assert added == 1
    assert "contoso" in terms
    assert "fabrikam" not in terms


def test_a_no_is_remembered_and_not_asked_again(listing):
    privacy.add_terms(listing, ["litware"])
    privacy.offer_employers(
        ["Fabrikam"], listing, input_fn=_answers("y", "n"), output_fn=lambda s: None,
        interactive=True,
    )
    assert "fabrikam" in privacy.read_declined(listing)
    assert "fabrikam" not in privacy.read_terms(listing), "a declined note is not a term"

    again = privacy.offer_employers(
        ["Fabrikam"], listing, input_fn=_no_input, output_fn=lambda s: None, interactive=True,
    )
    assert again == 0


def test_all_the_rest_is_still_a_decision_the_person_made(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Adatum", "Contoso", "Fabrikam"], listing,
        input_fn=_answers("y", "a"), output_fn=lambda s: None, interactive=True,
    )
    terms = privacy.read_terms(listing)
    assert {"adatum", "contoso", "fabrikam"} <= set(terms)
    assert added == 3


def test_stop_ends_the_offers_and_leaves_the_rest_unrecorded(listing):
    privacy.add_terms(listing, ["litware"])
    privacy.offer_employers(
        ["Adatum", "Contoso"], listing, input_fn=_answers("y", "s"), output_fn=lambda s: None,
        interactive=True,
    )
    assert privacy.read_terms(listing) == ["litware"]
    assert privacy.read_declined(listing) == set()


def test_running_out_of_input_mid_offer_stops_without_hanging(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Adatum", "Contoso"], listing, input_fn=_answers("y"), output_fn=lambda s: None,
        interactive=True,
    )
    assert added == 0


def test_gibberish_answers_do_not_loop_forever(listing):
    privacy.add_terms(listing, ["litware"])
    added = privacy.offer_employers(
        ["Adatum"], listing, input_fn=_answers("y", "?", "?", "?", "?"),
        output_fn=lambda s: None, interactive=True,
    )
    assert added == 0


# --- Checking -----------------------------------------------------------------------------

def test_a_hit_reports_where_and_which_entry_but_never_the_term(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text(
        "nothing here\nI worked at Contoso for years\n", encoding="utf-8"
    )
    result = privacy.check_tree(tmp_path, ["litware", "contoso"])

    assert result.files == 1
    (hit,) = result.hits
    assert (hit.path, hit.line, hit.column, hit.entry) == ("docs/notes.md", 2, 13, 2)
    shown = privacy.describe(hit)
    assert "docs/notes.md:2:13" in shown and "#2" in shown
    assert "contoso" not in shown.lower()


def test_matching_ignores_case(tmp_path):
    (tmp_path / "a.txt").write_text("CONTOSO\n", encoding="utf-8")
    assert len(privacy.check_tree(tmp_path, ["contoso"]).hits) == 1


def test_a_clean_tree_has_no_hits_and_binary_files_are_skipped(tmp_path):
    (tmp_path / "a.txt").write_text("nothing\n", encoding="utf-8")
    (tmp_path / "b.png").write_bytes(b"contoso")
    (tmp_path / "c.dat").write_bytes(b"contoso\0more")
    result = privacy.check_tree(tmp_path, ["contoso"])
    assert result.hits == [] and result.files == 1


def test_the_list_file_itself_is_never_scanned(tmp_path):
    path = tmp_path / "privacy.txt"
    privacy.add_terms(path, ["contoso"])
    result = privacy.check_tree(tmp_path, ["contoso"], skip=path)
    assert result.hits == []


@needs_git
def test_a_tree_scan_skips_what_git_ignores(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("contoso\n", encoding="utf-8")
    (tmp_path / "public.txt").write_text("contoso\n", encoding="utf-8")
    result = privacy.check_tree(tmp_path, ["contoso"])
    assert [hit.path for hit in result.hits] == ["public.txt"]


def test_a_range_scan_reads_added_lines_and_commit_identities(tmp_path, monkeypatch):
    diff = (
        "diff --git a/docs/a.md b/docs/a.md\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/a.md\n"
        "@@ -3,0 +4,2 @@\n"
        "+a clean line\n"
        "+a line about Contoso\n"
        "@@ -9 +11 @@\n"
        "-old Contoso\n"
        "+new line\n"
    )
    log = f"abc1234{chr(31)}Morgan Contoso <m@example.test>{chr(31)}Morgan Contoso <m@example.test>\n"

    def fake_git(args, cwd):
        text = diff if args[0] == "diff" else log
        return subprocess.CompletedProcess(args, 0, stdout=text, stderr="")

    monkeypatch.setattr(privacy, "_git", fake_git)
    result = privacy.check_range("A..B", ["contoso"], tmp_path)

    where = sorted((hit.path, hit.line) for hit in result.hits)
    assert ("docs/a.md", 5) in where, "line numbers follow the hunk header"
    assert ("docs/a.md", 4) not in where
    assert ("commit abc1234", 0) in where
    assert not any(line == 11 for _, line in where), "a removed line is not a leak"


# --- The command line ----------------------------------------------------------------------

def test_add_then_count_through_the_cli(tmp_path, capsys):
    path = str(tmp_path / "p.txt")
    assert cli.main(["privacy", "add", "Contoso A/S", "--file", path]) == 0
    capsys.readouterr()
    assert cli.main(["privacy", "list", "--count", "--file", path]) == 0
    assert capsys.readouterr().out.strip().isdigit()


def test_list_never_prints_a_term(tmp_path, capsys):
    path = tmp_path / "p.txt"
    privacy.add_terms(path, ["contoso", "fabrikam"])
    cli.main(["privacy", "list", "--file", str(path)])
    cli.main(["privacy", "list", "--count", "--file", str(path)])
    out = capsys.readouterr().out.lower()
    assert "contoso" not in out and "fabrikam" not in out
    assert "2" in out


def test_add_with_an_exact_flag_adds_no_variants(tmp_path):
    path = tmp_path / "p.txt"
    assert cli.main(["privacy", "add", "Østerby", "--exact", "--file", str(path)]) == 0
    assert privacy.read_terms(path) == ["østerby"]


def test_a_term_that_is_too_short_is_refused(tmp_path, capsys):
    code = cli.main(["privacy", "add", "ab", "--file", str(tmp_path / "p.txt")])
    assert code == 2
    assert "at least" in capsys.readouterr().out


def test_check_exits_one_on_a_hit_and_zero_when_clean(tmp_path, capsys):
    listing_path = tmp_path / "p.txt"
    privacy.add_terms(listing_path, ["contoso"])
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.md").write_text("fine\n", encoding="utf-8")

    assert cli.main(["privacy", "check", str(tree), "--file", str(listing_path)]) == 0
    assert "Clean" in capsys.readouterr().out

    (tree / "a.md").write_text("fine\nContoso\n", encoding="utf-8")
    assert cli.main(["privacy", "check", str(tree), "--file", str(listing_path)]) == 1
    out = capsys.readouterr().out
    assert "a.md:2:1" in out
    assert "contoso" not in out.lower().replace("a.md", "")


def test_check_without_a_list_says_so_and_does_not_pass_silently(tmp_path, capsys):
    code = cli.main(["privacy", "check", str(tmp_path), "--file", str(tmp_path / "none.txt")])
    assert code == 2
    assert "nothing was checked" in capsys.readouterr().out


def test_privacy_with_no_subcommand_explains_itself(capsys):
    assert cli.main(["privacy"]) == 2
    assert "privacy init" in capsys.readouterr().out


def test_setup_cancelled_is_the_same_type_the_model_prompt_uses():
    assert privacy.SetupCancelled is SetupCancelled


# --- The outcomes command offers, and only offers -----------------------------------------------

def test_outcomes_offers_new_employers_when_a_person_is_there(config_dir):
    from job_scout import outcomes
    from job_scout.config import load_settings

    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    app = config_dir / "applications" / "contoso-kiosk-attendant-20250421"
    app.mkdir(parents=True)
    (app / "notes.md").write_text("**Status:** rejected", encoding="utf-8")
    (app / "jd.md").write_text("**Company:** Contoso\n", encoding="utf-8")
    privacy.add_terms(config_dir / "privacy.txt", ["litware"])

    class Args:
        applications_dir = None
        output = None
        show = False
        no_prompt = False

    settings = load_settings(str(config_dir))
    outcomes.command(Args(), settings, input_fn=_answers("y", "y"), output_fn=lambda s: None,
                     interactive=True)
    assert "contoso" in privacy.read_terms(config_dir / "privacy.txt")


def test_outcomes_run_by_a_timer_adds_nothing_and_does_not_ask(config_dir):
    from job_scout import outcomes
    from job_scout.config import load_settings

    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    app = config_dir / "applications" / "contoso-kiosk-attendant-20250421"
    app.mkdir(parents=True)
    (app / "notes.md").write_text("**Status:** rejected", encoding="utf-8")
    (app / "jd.md").write_text("**Company:** Contoso\n", encoding="utf-8")
    privacy.add_terms(config_dir / "privacy.txt", ["litware"])

    class Args:
        applications_dir = None
        output = None
        show = False
        no_prompt = False

    settings = load_settings(str(config_dir))
    outcomes.command(Args(), settings, input_fn=_no_input, output_fn=lambda s: None,
                     interactive=False)
    assert privacy.read_terms(config_dir / "privacy.txt") == ["litware"]


def test_no_prompt_flag_silences_the_offer_even_in_a_terminal(config_dir):
    from job_scout import outcomes
    from job_scout.config import load_settings

    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    app = config_dir / "applications" / "contoso-kiosk-attendant-20250421"
    app.mkdir(parents=True)
    (app / "notes.md").write_text("**Status:** rejected", encoding="utf-8")
    privacy.add_terms(config_dir / "privacy.txt", ["litware"])

    class Args:
        applications_dir = None
        output = None
        show = False
        no_prompt = True

    outcomes.command(Args(), load_settings(str(config_dir)), input_fn=_no_input,
                     output_fn=lambda s: None, interactive=True)
    assert privacy.read_terms(config_dir / "privacy.txt") == ["litware"]
