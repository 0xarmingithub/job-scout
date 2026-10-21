"""
Tests for outcomes.py, mostly for the company column.

A blank company is not harmless: the scorer is shown outcome history as "title
at company", and `job-scout calibrate` joins an outcome back to its score on the
employer's name. With no company the join either fails or, worse, lands on a
different employer advertising the same title.

Every name here is fictional.
"""

import csv

import pytest

from job_scout import outcomes as o
from job_scout import run as run_module
from job_scout import track_record
from job_scout.config import load_settings

EM_DASH = chr(0x2014)


def _app(root, folder, jd=None, notes="**Status:** rejected"):
    app = root / folder
    app.mkdir(parents=True)
    if jd is not None:
        (app / "jd.md").write_text(jd, encoding="utf-8")
    if notes is not None:
        (app / "notes.md").write_text(notes, encoding="utf-8")
    return app


# --- Where the company comes from ---------------------------------------------

def test_the_front_matter_company_wins(tmp_path):
    """A jd.md that states the company is not something to guess around."""
    app = _app(tmp_path, "contoso-warehouse-planning-analyst-20250318", jd=(
        "URL: https://example.test/1\n"
        "Company: Contoso - maker of garden tools\n"
        "Role title: Warehouse Planning Analyst\n"
    ))
    assert o.company_and_role(app) == ("Contoso", "Warehouse Planning Analyst")


def test_the_description_after_a_company_name_is_dropped(tmp_path):
    app = _app(tmp_path, "fabrikam-pricing-analyst-20250402", jd=(
        "**Company:** Fabrikam (a Litware company)\n"
        "**Role title:** Pricing Analyst\n"
    ))
    assert o.company_and_role(app)[0] == "Fabrikam"


def test_an_unknown_company_is_treated_as_blank_not_as_a_name(tmp_path):
    app = _app(tmp_path, "adatum-data-steward-20250219", jd=(
        "**Company:** Unknown (Springfield-based)\n"
        "**Role title:** Data Steward\n"
    ))
    company, role = o.company_and_role(app)
    assert company == "Adatum"
    assert role == "Data Steward"


def test_a_heading_naming_the_company_last_is_split_by_the_folder(tmp_path):
    app = _app(
        tmp_path, "litware-quality-lead-20250527",
        jd=f"# Quality Lead {EM_DASH} Litware Industries\n",
    )
    assert o.company_and_role(app) == ("Litware Industries", "Quality Lead")


def test_a_heading_naming_the_company_first_is_split_the_other_way(tmp_path):
    app = _app(
        tmp_path, "contoso-field-service-coordinator-20250610",
        jd="# Contoso: Field Service Coordinator - Northern Region\n",
    )
    assert o.company_and_role(app) == ("Contoso", "Field Service Coordinator - Northern Region")


def test_a_company_in_brackets_at_the_end_is_found(tmp_path):
    app = _app(
        tmp_path, "fabrikam-support-team-captain-20250715",
        jd="# Support Team Captain, Customer Care (Fabrikam)\n",
    )
    assert o.company_and_role(app) == ("Fabrikam", "Support Team Captain, Customer Care")


def test_a_location_at_the_end_is_not_mistaken_for_the_employer(tmp_path):
    """
    "Senior Process Engineer - Springfield" names a place, not a company. The
    folder is the test: it starts with litware, not with springfield.
    """
    app = _app(
        tmp_path, "litware-senior-process-engineer-20250808",
        jd="# Senior Process Engineer - Springfield\n",
    )
    company, role = o.company_and_role(app)
    assert company == "Litware"
    assert "Springfield" in role


def test_a_company_named_nowhere_is_taken_from_the_folder(tmp_path):
    """
    "Adatum" appears in the folder and nowhere in the heading. What the folder
    has and the role does not is the company.
    """
    app = _app(
        tmp_path, "adatum-sensor-calibration-engineer-20250904",
        jd=f"# JD: Sensor Calibration Engineer {EM_DASH} Lab Equipment\n",
    )
    company, role = o.company_and_role(app)
    assert company == "Adatum"
    assert role.startswith("Sensor Calibration Engineer")


def test_a_folder_with_no_jd_still_yields_a_company(tmp_path):
    app = _app(tmp_path, "fabrikam-nightshift-forklift-supervisor-20251001", jd=None)
    company, role = o.company_and_role(app)
    assert company  # a guess, but never blank
    assert role


def test_no_company_column_is_ever_left_empty(tmp_path):
    for folder, jd in (
        ("contoso-regional-dispatcher-20250321", "**Company:** Contoso\n"),
        ("fabrikam-claims-handler-20250322", f"# Claims Handler {EM_DASH} Fabrikam Group\n"),
        ("adatum-lab-technician-20250323", None),
    ):
        _app(tmp_path, folder, jd=jd)
    rows = o.collect(tmp_path)
    assert len(rows) == 3
    assert all(row["company"] for row in rows), rows


# --- Statuses -----------------------------------------------------------------

def test_a_folder_with_no_status_line_is_named_rather_than_skipped_silently(tmp_path):
    _app(tmp_path, "contoso-regional-dispatcher-20250321", jd="**Company:** Contoso\n")
    _app(tmp_path, "litware-depot-manager-20250322", jd="**Company:** Litware\n",
         notes="No status here at all.")
    assert o.silent(tmp_path) == ["litware-depot-manager-20250322"]


def test_a_phrase_the_person_listed_is_not_read_as_a_status_word(tmp_path):
    """
    "interview prep" is a step of someone's own process. Unlisted, the word
    interview would make a draft look as if it had reached an employer.
    """
    app = _app(tmp_path, "contoso-regional-dispatcher-20250321",
               notes="**Status:** Interview prep complete")
    assert "interview" in (o.status_for(app) or "").lower()
    assert "interview" not in (o.status_for(app, ("interview prep",)) or "").lower()


def test_nothing_is_ignored_unless_the_person_listed_it(tmp_path):
    app = _app(tmp_path, "contoso-regional-dispatcher-20250321", notes="**Status:** drafted")
    assert o.status_for(app) == "drafted"
    assert o.status_for(app, ("",)) == "drafted", "a blank entry removes nothing"


def test_a_status_that_is_only_an_ignored_phrase_counts_as_no_status(tmp_path):
    _app(tmp_path, "contoso-regional-dispatcher-20250321",
         notes="**Status:** Interview prep")
    assert o.silent(tmp_path) == []
    assert o.silent(tmp_path, ("interview prep",)) == ["contoso-regional-dispatcher-20250321"]


def test_a_rejection_after_talking_to_them_is_recorded_as_such(tmp_path):
    app = _app(
        tmp_path, "adatum-sensor-calibration-engineer-20250904",
        notes="**Status:** rejected\n\nThey declined after the second round of conversations.",
    )
    assert o.status_for(app) == "rejected after interview"


def test_a_rejection_with_no_conversation_stays_a_plain_rejection(tmp_path):
    app = _app(
        tmp_path, "adatum-sensor-calibration-engineer-20250904",
        notes="**Status:** rejected\n\nA form email arrived two days later.",
    )
    assert o.status_for(app) == "rejected"


def test_a_status_line_can_be_a_list_item(tmp_path):
    app = _app(tmp_path, "contoso-planner-20250614", notes="# Notes\n\n- **Status:** submitted\n")
    assert o.status_for(app) == "submitted"


def test_a_notes_file_with_an_empty_status_counts_as_no_status(tmp_path):
    app = _app(tmp_path, "contoso-planner-20250614", notes="**Status:**   \n")
    assert o.status_for(app) is None


def test_the_documented_status_words_all_classify(tmp_path):
    """
    docs/applications.md lists these. Each one has to land in a class the
    scorer understands, or writing a status there would teach it nothing.
    """
    expected = {
        "drafted": "other",
        "submitted": "applied",
        "acknowledged": "applied",
        "screened": "interviewing",
        "interviewing": "interviewing",
        "offer": "offer",
        "rejected": "rejected",
        "withdrawn": "withdrawn",
    }
    for word, wanted in expected.items():
        assert track_record.classify(word) == wanted, word
    assert track_record.classify("no response") == "no_response"


# --- Which folders count ------------------------------------------------------

def test_folders_starting_with_a_dot_or_underscore_are_not_applications(tmp_path):
    _app(tmp_path, "_template", notes="**Status:** drafted")
    _app(tmp_path, ".archive", notes="**Status:** drafted")
    _app(tmp_path, "contoso-planner-20250614", notes="**Status:** drafted")
    assert [row["folder"] for row in o.collect(tmp_path)] == ["contoso-planner-20250614"]
    assert o.silent(tmp_path) == []


def test_a_loose_file_in_the_folder_is_not_an_application(tmp_path):
    (tmp_path / "README.md").write_text("notes", encoding="utf-8")
    assert o.collect(tmp_path) == []


def test_a_missing_directory_is_an_empty_list_not_an_error(tmp_path):
    assert o.collect(tmp_path / "nowhere") == []
    assert o.silent(tmp_path / "nowhere") == []


# --- The file ------------------------------------------------------------------

def test_the_header_is_exactly_the_documented_four_columns(tmp_path):
    _app(tmp_path / "apps", "contoso-planner-20250614", jd="**Company:** Contoso\n")
    target = tmp_path / "out" / "outcomes.csv"
    o.write(o.collect(tmp_path / "apps"), target)
    assert target.read_text(encoding="utf-8").splitlines()[0] == "title,company,status,folder"


def test_what_is_written_is_read_back_by_the_scorers_reader(tmp_path):
    """The contract between this module and track_record.py, run rather than asserted."""
    _app(tmp_path / "apps", "contoso-route-planner-20250614",
         jd="**Company:** Contoso\n**Role title:** Route Planner\n",
         notes="**Status:** interviewing")
    _app(tmp_path / "apps", "fabrikam-claims-reviewer-20250615",
         jd="**Company:** Fabrikam\n**Role title:** Claims Reviewer\n", notes="**Status:** rejected")
    target = tmp_path / "outcomes.csv"
    o.write(o.collect(tmp_path / "apps"), target)

    rows = track_record.read_outcomes(target)
    assert [(r["title"], r["company"], r["class"]) for r in rows] == [
        ("Route Planner", "Contoso", "interviewing"),
        ("Claims Reviewer", "Fabrikam", "rejected"),
    ]


def test_a_comma_or_quote_in_a_field_survives_the_round_trip(tmp_path):
    _app(tmp_path / "apps", "contoso-planner-20250614",
         jd='**Company:** Contoso\n**Role title:** Planner, "Depot"\n')
    target = tmp_path / "outcomes.csv"
    o.write(o.collect(tmp_path / "apps"), target)
    with open(target, encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["title"] == 'Planner, "Depot"'


def test_a_hand_kept_three_column_file_is_not_a_generated_one(tmp_path):
    hand = tmp_path / "outcomes.csv"
    hand.write_text("title,company,status\nClaims Reviewer,Contoso,offer\n", encoding="utf-8")
    assert not o.is_generated(hand)


def test_our_own_file_and_an_absent_one_are_safe_to_overwrite(tmp_path):
    ours = tmp_path / "outcomes.csv"
    o.write([], ours)
    assert o.is_generated(ours)
    assert o.is_generated(tmp_path / "absent.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert o.is_generated(empty)


# --- The command ---------------------------------------------------------------

class _Args:
    def __init__(self, **kwargs):
        self.applications_dir = None
        self.output = None
        self.show = False
        self.no_prompt = False
        self.__dict__.update(kwargs)


def _with_apps(config_dir):
    """Point the config at ./applications and put two folders in it."""
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    apps = config_dir / "applications"
    _app(apps, "contoso-route-planner-20250614",
         jd="**Company:** Contoso\n**Role title:** Route Planner\n",
         notes="**Status:** interviewing")
    _app(apps, "fabrikam-claims-reviewer-20250615", jd="**Company:** Fabrikam\n", notes="no status")
    return apps


def test_the_command_writes_the_file_and_names_the_silent_folders(config_dir):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))
    lines = []
    code = o.command(_Args(), settings, output_fn=lines.append)
    text = "\n".join(lines)

    assert code == 0
    assert settings.outcomes_path.exists()
    assert "Wrote 1 outcome(s)" in text
    assert "interviewing: 1" in text
    assert "fabrikam-claims-reviewer-20250615" in text


def test_print_writes_nothing(config_dir):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))
    lines = []
    assert o.command(_Args(show=True), settings, output_fn=lines.append) == 0
    assert not settings.outcomes_path.exists()
    assert "Route Planner at Contoso" in "\n".join(lines)


def test_without_applications_dir_the_command_says_what_to_set(config_dir):
    settings = load_settings(str(config_dir))
    lines = []
    assert o.command(_Args(), settings, output_fn=lines.append) == 2
    assert "applications_dir is not set" in lines[0]


def test_the_command_will_not_overwrite_a_hand_kept_file(config_dir):
    _with_apps(config_dir)
    hand = config_dir / "mine.csv"
    hand.write_text("title,company,status\nClaims Reviewer,Contoso,offer\n", encoding="utf-8")
    settings = load_settings(str(config_dir))
    lines = []
    code = o.command(_Args(output=str(hand)), settings, output_fn=lines.append)
    assert code == 1
    assert hand.read_text(encoding="utf-8").startswith("title,company,status\nClaims Reviewer")
    assert "hand-kept" in "\n".join(lines)


# --- Where the generated file goes ----------------------------------------------

def test_with_applications_dir_set_the_file_goes_to_the_data_directory(config_dir):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))
    assert settings.outcomes_path == settings.data_dir / "outcomes.csv"


def test_an_explicit_outcomes_file_still_wins(config_dir):
    _with_apps(config_dir)
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("outcomes_file: mine.csv\n")
    settings = load_settings(str(config_dir))
    assert settings.outcomes_path == config_dir / "mine.csv"


def test_without_applications_dir_the_default_location_is_unchanged(config_dir):
    settings = load_settings(str(config_dir))
    assert settings.applications_dir is None
    assert settings.outcomes_path == config_dir / "outcomes.csv"


# --- The run rebuilds it ---------------------------------------------------------

@pytest.fixture
def quiet_board(monkeypatch):
    from job_scout import sources

    monkeypatch.setattr(
        run_module.sources, "fetch_jobs",
        lambda searches, config, known=None: ([], sources.FetchReport()),
    )


def test_a_run_rebuilds_the_outcomes_file_first(config_dir, quiet_board):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))
    assert not settings.outcomes_path.exists()

    result = run_module.run_once(settings)

    assert result.ok
    rows = track_record.read_outcomes(settings.outcomes_path)
    assert [(r["company"], r["class"]) for r in rows] == [("Contoso", "interviewing")]


def test_a_dry_run_rebuilds_it_too_because_it_is_derived_not_recorded(config_dir, quiet_board):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))
    run_module.run_once(settings, dry_run=True)
    assert settings.outcomes_path.exists()


def test_a_run_with_a_missing_applications_folder_still_finishes_and_says_so(
    config_dir, quiet_board
):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: not-there\n")
    settings = load_settings(str(config_dir))

    result = run_module.run_once(settings)

    assert result.ok, "optional means optional"
    alert = (settings.data_dir / "matches.md").read_text(encoding="utf-8")
    assert "ALERT" in alert
    assert "not a directory" in alert


def test_a_run_never_overwrites_a_hand_kept_outcomes_file(config_dir, quiet_board):
    _with_apps(config_dir)
    hand = config_dir / "mine.csv"
    hand.write_text("title,company,status\nClaims Reviewer,Contoso,offer\n", encoding="utf-8")
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("outcomes_file: mine.csv\n")
    settings = load_settings(str(config_dir))

    result = run_module.run_once(settings)

    assert result.ok
    assert hand.read_text(encoding="utf-8") == "title,company,status\nClaims Reviewer,Contoso,offer\n"
    assert "hand-kept" in (settings.data_dir / "matches.md").read_text(encoding="utf-8")


def test_a_failure_while_rebuilding_alerts_and_does_not_stop_the_run(
    config_dir, quiet_board, monkeypatch
):
    _with_apps(config_dir)
    settings = load_settings(str(config_dir))

    def explode(directory, ignore=()):
        raise RuntimeError("the disk is on fire")

    monkeypatch.setattr(o, "collect", explode)
    result = run_module.run_once(settings)

    assert result.ok
    assert "the disk is on fire" in (settings.data_dir / "matches.md").read_text(encoding="utf-8")


def test_a_wrong_applications_dir_value_stops_the_run_with_a_fix(config_dir):
    from job_scout.config import ConfigError

    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: [one, two]\n")
    with pytest.raises(ConfigError, match="applications_dir must be a folder path"):
        load_settings(str(config_dir))
