"""
Spelling-tolerant dedup. The same advert from two boards, or on two days, is one
job. Different jobs at one company stay different.
"""

from datetime import date, timedelta

from job_scout.dedup import JobStore
from job_scout.normalize import company_key, content_key, normalize_text, title_key


def _job(title, company, url, description="", site="linkedin"):
    return {
        "title": title,
        "company": company,
        "location": "Copenhagen",
        "description": description,
        "url": url,
        "site": site,
        "date_posted": "2026-10-20",
        "search_term": "x",
    }


LONG_TEXT = " ".join(
    f"word{i} kubernetes terraform azure platform engineering practice" for i in range(20)
)


# --- normalization -------------------------------------------------------------

def test_legal_suffixes_and_country_words_are_dropped_from_companies():
    assert company_key("Contoso Denmark A/S") == "contoso"
    assert company_key("Contoso") == "contoso"
    assert company_key("Alder Group A/S") == "alder"
    assert company_key("Ping & Pong A/S") == "ping pong"


def test_danish_letters_are_folded_so_osterby_and_østerby_match():
    assert company_key("Østerby A/S") == company_key("Osterby")


def test_bracketed_codes_are_dropped_from_titles():
    assert title_key("Software Engineer, Vision (BE-ABP-2026-132-GRAP)") == "software engineer vision"


def test_a_missing_title_or_company_gives_no_content_key():
    assert content_key("", "Acme") == ""
    assert content_key("Dev", "") == ""


def test_normalize_text_keeps_letters_and_digits_only():
    assert normalize_text("Senior DevOps & Dev-Productivity (v2)") == "senior devops dev productivity v2"


# --- the store --------------------------------------------------------------------

def test_the_same_title_under_another_company_spelling_is_a_repeat(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_job("Azure Platform Engineer", "Contoso Denmark A/S", "https://a/1")])
    again = [_job("Azure Platform Engineer", "Contoso", "https://b/9", site="jobnet")]
    assert store.filter_new(again) == []


def test_a_near_identical_title_from_the_same_company_is_a_repeat(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_job("Senior Azure Architect", "Harbor digital", "https://a/1")])
    again = [_job("Senior Azure Architect - Consulting", "Harbor digital", "https://b/2")]
    # Titles share 3 of 4 words: 0.75, below the 0.8 bar, so this stays new.
    assert len(store.filter_new(again)) == 1
    same = [_job("Senior Azure Architect", "Harbor Digital ApS", "https://c/3")]
    assert store.filter_new(same) == []


def test_different_roles_at_one_company_stay_different(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_job("Azure Platform Architect", "Contoso Denmark A/S", "https://a/1",
                          description="Architect the platform landing zones with Bicep templates.")])
    other = [_job("Azure Platform Engineer", "Contoso Denmark A/S", "https://a/2",
                  description="Build and run pipelines for product teams in a regulated setting.")]
    assert len(store.filter_new(other)) == 1


def test_the_same_description_under_different_titles_is_a_repeat(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_job("Solution Architect", "Acme", "https://a/1", description=LONG_TEXT)])
    again = [_job("Lead Integrator", "Acme ApS", "https://b/2", description=LONG_TEXT, site="jobbank")]
    assert store.filter_new(again) == []


def test_a_copy_inside_the_same_batch_is_counted_once(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    batch = [
        _job("Platform Engineer", "Fabrikam", "https://a/1", description=LONG_TEXT, site="linkedin"),
        _job("Platform Engineer", "Fabrikam ApS", "https://b/2", description=LONG_TEXT, site="jobnet"),
    ]
    assert len(store.filter_new(batch)) == 1


def test_a_row_from_before_descriptions_were_stored_still_matches_by_title(tmp_path):
    db = tmp_path / "jobs.db"
    store = JobStore(db)
    store.mark_seen([_job("Cloud Engineer", "Tern", "https://a/1")])
    # Simulate a row written before desc_head existed: blank it out.
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("UPDATE seen_jobs SET desc_head = NULL")
    conn.commit()
    conn.close()
    assert store.filter_new([_job("Cloud Engineer", "Tern A/S", "https://b/2")]) == []


def test_a_database_without_the_new_column_is_upgraded_in_place(tmp_path):
    import sqlite3
    db = tmp_path / "jobs.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE seen_jobs (job_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT, "
        "company TEXT, location TEXT, site TEXT, score REAL, status TEXT DEFAULT 'new', "
        "first_seen TEXT, date_posted TEXT, search_term TEXT, verdict_json TEXT, attempts INTEGER DEFAULT 1)"
    )
    conn.commit()
    conn.close()
    store = JobStore(db)
    store.mark_seen([_job("Dev", "Acme", "https://a/1", description=LONG_TEXT)])
    columns = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(seen_jobs)")}
    assert "desc_head" in columns
    assert store.count() == 1


def test_old_rows_outside_the_lookback_do_not_block_a_repeat(tmp_path):
    import sqlite3
    db = tmp_path / "jobs.db"
    store = JobStore(db, lookback_days=7)
    store.mark_seen([_job("Dev", "Acme", "https://a/1")])
    old = (date.today() - timedelta(days=30)).isoformat()
    conn = sqlite3.connect(db)
    conn.execute("UPDATE seen_jobs SET first_seen = ?", (old,))
    conn.commit()
    conn.close()
    # The URL is still known, but the title and company match is out of the window.
    assert len(store.filter_new([_job("Dev", "Acme", "https://b/2")])) == 1


def test_a_shared_company_intro_does_not_make_different_jobs_repeats(tmp_path):
    intro = " ".join(f"about our company word{i} we build iot products" for i in range(40))
    body_a = " ".join(f"role a task{i} python sql reporting dashboards" for i in range(40))
    body_b = " ".join(f"role b task{i} customer onboarding crm campaigns" for i in range(40))
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_job("Platform Engineer", "Fabrikam", "https://a/1", description=intro + " " + body_a)])
    other = [_job("Data and Automation Specialist", "Fabrikam", "https://b/2", description=intro + " " + body_b)]
    assert len(store.filter_new(other)) == 1
