"""
Tests for patterns.py.

The two things that can go wrong quietly. A report that ranks generic words at
the top reads as insight and is noise, and a report that states a conversion
rate over five applications reads as evidence and is not.

Every name here is fictional.
"""

from datetime import date

import pytest

from job_scout import patterns as p
from job_scout.config import ConfigError, load_settings

TABLE_HEADER = (
    "| JD requirement | Priority | Coverage | Evidence | Action |\n"
    "|---|---|---|---|---|\n"
)


def _app(root, folder, status="**Status:** rejected", coverage=(), cv=True):
    app = root / folder
    app.mkdir(parents=True)
    (app / "notes.md").write_text(status, encoding="utf-8")
    (app / "jd.md").write_text(f"**Company:** {folder.split('-')[0]}\n", encoding="utf-8")
    if cv:
        (app / "CV.tex").write_text("%", encoding="utf-8")
    if coverage:
        rows = "".join(
            f"| {requirement} | P0 | {verdict} | evidence | action |\n"
            for requirement, verdict in coverage
        )
        (app / "gap-analysis.md").write_text(
            "# Gap Analysis\n\n## Coverage table\n\n" + TABLE_HEADER + rows,
            encoding="utf-8",
        )
    return app


@pytest.fixture
def apps(tmp_path):
    return tmp_path


def _records(apps):
    return p.collect(apps)


# --- Reading a coverage table ---------------------------------------------------------

def test_the_header_and_separator_rows_are_not_requirements(apps):
    app = _app(apps, "contoso-architect-20250611", coverage=[("Zephyrdb", "Not Covered")])
    assert [row["requirement"] for row in p.coverage_rows(app)] == ["Zephyrdb"]


def test_bold_markers_inside_a_cell_are_removed(apps):
    app = _app(apps, "contoso-architect-20250611",
               coverage=[("File-based integration: **Wickerlink**", "**Not Covered**")])
    assert p.coverage_rows(app)[0]["requirement"] == "File-based integration: Wickerlink"


def test_a_folder_with_no_gap_analysis_is_not_an_error(apps):
    app = _app(apps, "contoso-architect-20250611")
    assert p.coverage_rows(app) == []


# --- Recurring gaps ---------------------------------------------------------------------

def test_a_term_missing_from_two_applications_is_reported(apps):
    _app(apps, "contoso-architect-20250611", coverage=[("Quillcad", "Not Covered")])
    _app(apps, "fabrikam-architect-20250612", coverage=[("Quillcad modelling", "Not Covered")])
    out = "\n".join(p.section_recurring_gaps(_records(apps)))
    assert "`quillcad` | 2" in out


def test_a_one_off_gap_is_not_a_pattern(apps):
    _app(apps, "contoso-architect-20250611", coverage=[("Frobnitz", "Not Covered")])
    _app(apps, "fabrikam-architect-20250612", coverage=[("Gleamlang", "Not Covered")])
    out = "\n".join(p.section_recurring_gaps(_records(apps)))
    assert "Nothing recurs" in out


def test_a_word_covered_elsewhere_is_not_called_a_gap(apps):
    """
    "Architecture" turns up in Not Covered rows inside qualified requirements
    like "architecture workshops facilitation". Ranking on raw counts put it at
    the top of a list about things the candidate does every day.
    """
    _app(apps, "contoso-architect-20250611", coverage=[
        ("Architecture workshops facilitation", "Not Covered"),
        ("Quillcad", "Not Covered"),
    ])
    _app(apps, "fabrikam-architect-20250612", coverage=[
        ("Architecture governance", "Not Covered"),
        ("Quillcad", "Not Covered"),
    ])
    _app(apps, "adatum-architect-20250613", coverage=[
        ("Solution architecture ownership", "Strongly"),
        ("Architecture standards", "Strongly Covered"),
    ])
    out = "\n".join(p.section_recurring_gaps(_records(apps)))
    assert "`quillcad`" in out
    assert "`architecture`" not in out


def test_filler_never_reaches_the_table(apps):
    for folder in ("contoso-architect-20250611", "fabrikam-architect-20250612"):
        _app(apps, folder, coverage=[
            ("Hands-on experience with strong proven track record", "Not Covered"),
        ])
    out = "\n".join(p.section_recurring_gaps(_records(apps)))
    assert "`experience`" not in out
    assert "`hands-on`" not in out
    assert "`proven`" not in out


def test_a_posting_repeating_a_term_still_counts_once(apps):
    _app(apps, "contoso-architect-20250611", coverage=[
        ("Wickerlink", "Not Covered"),
        ("Wickerlink mapping", "Not Covered"),
        ("Wickerlink onboarding", "Not Covered"),
    ])
    _app(apps, "fabrikam-architect-20250612", coverage=[("Wickerlink", "Not Covered")])
    out = "\n".join(p.section_recurring_gaps(_records(apps)))
    assert "`wickerlink` | 2" in out


# --- The funnel ----------------------------------------------------------------------------

def test_no_rate_is_stated_on_too_few_applications(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** rejected")
    _app(apps, "fabrikam-architect-20250612", status="**Status:** interviewing")
    out = "\n".join(p.section_funnel(_records(apps)))
    assert "No conversion rate is stated" in out
    assert "%" not in out


def test_folders_with_no_status_are_counted_as_a_leak(apps):
    _app(apps, "contoso-architect-20250611", status="no status here")
    _app(apps, "fabrikam-architect-20250612", status="**Status:** drafted")
    _app(apps, "adatum-architect-20250613", status="**Status:** interviewing")
    out = "\n".join(p.section_funnel(_records(apps)))
    assert "2 of 3 never reached an employer" in out
    assert "docs/applications.md" in out


def test_an_acknowledged_application_counts_as_sent_not_as_a_draft(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** acknowledged")
    out = "\n".join(p.section_funnel(_records(apps)))
    assert "Sent, no answer yet | 1" in out
    assert "never reached an employer" not in out


def test_the_floor_is_the_one_calibrate_uses():
    from job_scout import calibrate

    assert p.MIN_SENT_FOR_RATES == calibrate._MIN_DECIDED


# --- Role families --------------------------------------------------------------------------------

PROFILE = {
    "target_roles": [
        "Platform Engineer",
        "Site Reliability Engineer",
        "Solution Architect",
        "Engineering Lead (Infrastructure)",
    ]
}


def test_without_role_families_there_is_one_family_per_target_role():
    families = p.families_from_profile(PROFILE)
    assert [f.name for f in families] == PROFILE["target_roles"]


def test_a_derived_family_is_recognised_by_its_specific_words_not_by_engineer():
    families = p.families_from_profile(PROFILE)
    assert p.families_for("Senior Platform Engineer", families) == ["Platform Engineer"]
    assert p.families_for("Cloud Engineer", families) == []
    assert p.families_for("Staff Site Reliability Engineer II", families) == [
        "Site Reliability Engineer"
    ]


def test_a_derived_family_needs_all_of_its_specific_words():
    families = p.families_from_profile(PROFILE)
    assert p.families_for("Site Manager", families) == []
    assert p.families_for("Reliability Analyst", families) == []


def test_a_word_and_its_longer_form_are_the_same_word():
    families = p.families_from_profile(PROFILE)
    assert p.families_for("Solution Architecture Lead", families) == ["Solution Architect"]


def test_a_title_can_belong_to_several_families():
    families = p.families_from_profile(PROFILE)
    found = p.families_for("Platform Architect, Solution Architect", families)
    assert "Solution Architect" in found and "Platform Engineer" in found


def test_a_target_role_made_only_of_generic_words_still_makes_a_family():
    (family,) = p.families_from_profile({"target_roles": ["Lead Engineer"]})
    assert family.terms == ("lead", "engineer")


def test_no_target_roles_and_no_families_gives_an_honest_note(apps):
    _app(apps, "contoso-platform-engineer-20250611")
    out = "\n".join(p.section_families(_records(apps), []))
    assert "unclassified" in out
    assert "no role_families and no target_roles" in out


def test_declared_role_families_replace_the_derived_ones():
    profile = {
        **PROFILE,
        "role_families": [
            {"name": "Platform and SRE", "keywords": ["platform", "sre", "reliability"]},
            "Architecture",
        ],
    }
    families = p.families_from_profile(profile)
    assert [f.name for f in families] == ["Platform and SRE", "Architecture"]
    assert p.families_for("Senior SRE", families) == ["Platform and SRE"]
    assert p.families_for("Platform Architecture Owner", families) == ["Platform and SRE", "Architecture"]


def test_a_keyword_with_a_space_matches_as_a_phrase():
    families = p.families_from_profile(
        {"role_families": [{"name": "Data", "keywords": ["machine learning"]}]}
    )
    assert p.families_for("Machine Learning Engineer", families) == ["Data"]
    assert p.families_for("Learning Machine Operator", families) == []


@pytest.mark.parametrize(
    "bad",
    [
        "not a list",
        [{"name": "No keywords"}],
        [{"keywords": ["a-keyword"]}],
        [{"name": "Empty", "keywords": []}],
        [{"name": "Wrong", "keywords": [1, 2]}],
        [42],
        [""],
    ],
)
def test_a_role_families_value_it_cannot_read_is_an_error_with_a_fix(bad):
    with pytest.raises(ConfigError, match="role_families"):
        p.families_from_profile({"role_families": bad})


def test_the_family_table_says_the_columns_overlap(apps):
    _app(apps, "contoso-platform-solution-architect-20250611")
    out = "\n".join(p.section_families(_records(apps), p.families_from_profile(PROFILE)))
    assert "sum to more than the number of applications" in out
    assert "| Solution Architect | 1 |" in out


def test_a_title_matching_nothing_is_counted_as_unclassified(apps):
    _app(apps, "contoso-chocolatier-20250611")
    out = "\n".join(p.section_families(_records(apps), p.families_from_profile(PROFILE)))
    assert "| unclassified | 1 |" in out


# --- Stale drafts ------------------------------------------------------------------------------------

def test_an_old_untouched_draft_is_named(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** drafted, waiting on a final read")
    out = "\n".join(p.section_stale(_records(apps), 21, date(2025, 10, 2)))
    assert "contoso-architect-20250611" in out
    assert "| 113 |" in out


def test_a_finished_application_is_not_stale(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** rejected")
    out = "\n".join(p.section_stale(_records(apps), 21, date(2025, 10, 2)))
    assert "Nothing." in out


def test_a_folder_with_no_cv_is_not_called_a_wasted_draft(apps):
    """The section is about finished work sitting unused. No CV, no work."""
    _app(apps, "contoso-architect-20250611", status="**Status:** drafted", cv=False)
    out = "\n".join(p.section_stale(_records(apps), 21, date(2025, 10, 2)))
    assert "Nothing." in out


# --- The whole thing ------------------------------------------------------------------------------------

def test_the_report_renders_every_section(apps):
    _app(apps, "contoso-platform-engineer-20250611", coverage=[("Zephyrdb", "Not Covered")])
    text = p.render(apps, PROFILE, today=date(2025, 10, 2))
    assert text.startswith("# Application patterns, 2025-10-02")
    for heading in ("Where applications stop", "What keeps coming back as a gap",
                    "Which kinds of role get furthest", "Drafted, tailored"):
        assert heading in text


def test_an_empty_folder_says_so_instead_of_rendering_empty_tables(apps):
    assert "No application folders" in p.render(apps, PROFILE)


def test_the_report_writes_nothing(apps):
    _app(apps, "contoso-architect-20250611")
    before = {f: f.stat().st_mtime_ns for f in sorted(apps.rglob("*")) if f.is_file()}
    p.render(apps, PROFILE, today=date(2025, 10, 2))
    after = {f: f.stat().st_mtime_ns for f in sorted(apps.rglob("*")) if f.is_file()}
    assert before == after


def test_the_report_points_only_at_the_public_docs_for_guidance(apps):
    """It is for any user: the one place it sends you is the documented Status convention."""
    _app(apps, "contoso-architect-20250611", status="no status here")
    text = p.render(apps, PROFILE, today=date(2025, 10, 2))
    assert "docs/applications.md" in text
    assert "AGENTS" not in text


def test_a_listed_phrase_is_ignored_when_the_status_is_read(apps):
    _app(apps, "contoso-architect-20250611", status="**Status:** interview prep done")
    plain = {record["class"] for record in p.collect(apps)}
    ignoring = {record["class"] for record in p.collect(apps, ("interview prep",))}
    assert plain == {"interviewing"}, "the word interview is read as an employer interview without the setting"
    assert ignoring == {"other"}


# --- Through the command ------------------------------------------------------------------------------------

class _Args:
    stale_days = 21
    top = 15
    output = None


def _settings_with_apps(config_dir):
    with open(config_dir / "config.yaml", "a", encoding="utf-8") as handle:
        handle.write("\napplications_dir: applications\n")
    apps = config_dir / "applications"
    _app(apps, "contoso-platform-engineer-20250611")
    return load_settings(str(config_dir))


def test_the_command_reads_the_profile_target_roles(config_dir):
    settings = _settings_with_apps(config_dir)
    lines = []
    assert p.command(_Args(), settings, lines.append) == 0
    assert "| Platform Engineer | 1 |" in "\n".join(lines)


def test_the_command_can_write_the_report_to_a_file(config_dir, tmp_path):
    settings = _settings_with_apps(config_dir)
    args = _Args()
    args.output = str(tmp_path / "reports" / "patterns.md")
    lines = []
    assert p.command(args, settings, lines.append) == 0
    assert (tmp_path / "reports" / "patterns.md").read_text(encoding="utf-8").startswith("# Application")


def test_the_command_without_applications_dir_says_what_to_set(config_dir):
    settings = load_settings(str(config_dir))
    lines = []
    assert p.command(_Args(), settings, lines.append) == 2
    assert "applications_dir is not set" in lines[0]


def test_a_bad_role_families_value_stops_only_this_command(config_dir):
    settings = _settings_with_apps(config_dir)
    settings.profile["role_families"] = "oops"
    lines = []
    assert p.command(_Args(), settings, lines.append) == 2
    assert "role_families" in lines[0]
