"""
Dedup is what keeps the daily bill flat, so it gets tested hard. Two of these
are the smoke tests that used to live inside deploy_vm.sh.
"""

from job_scout.dedup import (
    DEFAULT_SITE_PRIORITY,
    JobStore,
    content_key,
    dedup_by_content,
    make_job_id,
)

# ─── Job ids ──────────────────────────────────────────────────────────────────

def test_job_id_is_stable_and_short():
    first = make_job_id("https://example.com/job/1")
    assert first == make_job_id("https://example.com/job/1")
    assert len(first) == 16
    assert first != make_job_id("https://example.com/job/2")


# ─── Cross-source dedup (smoke test 2 from deploy_vm.sh) ──────────────────────

def test_cross_source_dedup_keeps_the_higher_priority_board(sample_jobs):
    result = dedup_by_content(sample_jobs)
    assert len(result) == 2
    architect = next(job for job in result if job["title"] == "Solution Architect")
    assert architect["site"] == "linkedin", "LinkedIn outranks Careerjet"


def test_cross_source_dedup_prefers_the_longer_description():
    jobs = [
        {"title": "SRE", "company": "Acme", "site": "linkedin",
         "url": "https://a", "description": "short"},
        {"title": "SRE", "company": "Acme", "site": "linkedin",
         "url": "https://b", "description": "a considerably longer description"},
    ]
    result = dedup_by_content(jobs)
    assert len(result) == 1
    assert result[0]["url"] == "https://b"


def test_cross_source_dedup_honours_a_custom_priority():
    jobs = [
        {"title": "SRE", "company": "Acme", "site": "linkedin",
         "url": "https://a", "description": "x"},
        {"title": "SRE", "company": "Acme", "site": "careerjet",
         "url": "https://b", "description": "x"},
    ]
    result = dedup_by_content(jobs, {"careerjet": 0, "linkedin": 1})
    assert result[0]["site"] == "careerjet"


def test_unknown_site_sorts_last():
    jobs = [
        {"title": "SRE", "company": "Acme", "site": "somethingnew",
         "url": "https://a", "description": "x"},
        {"title": "SRE", "company": "Acme", "site": "indeed",
         "url": "https://b", "description": "x"},
    ]
    assert dedup_by_content(jobs)[0]["site"] == "indeed"


def test_jobs_without_a_usable_key_are_always_kept():
    jobs = [
        {"title": "", "company": "", "site": "linkedin", "url": "https://a", "description": ""},
        {"title": "", "company": "", "site": "linkedin", "url": "https://b", "description": ""},
    ]
    assert len(dedup_by_content(jobs)) == 2


def test_dedup_does_not_modify_its_input(sample_jobs):
    before = [dict(job) for job in sample_jobs]
    dedup_by_content(sample_jobs)
    assert sample_jobs == before


def test_empty_input():
    assert dedup_by_content([]) == []


def test_content_key_normalises_punctuation_and_case():
    left = {"title": "Senior  SRE!", "company": "Acme, Inc."}
    right = {"title": "senior sre", "company": "acme inc"}
    assert content_key(left) == content_key(right)


def test_content_key_is_empty_without_both_parts():
    assert content_key({"title": "SRE", "company": ""}) == ""
    assert content_key({"title": "", "company": "Acme"}) == ""


def test_default_priority_puts_linkedin_first():
    assert DEFAULT_SITE_PRIORITY["linkedin"] == min(DEFAULT_SITE_PRIORITY.values())


# ─── The SQLite store ─────────────────────────────────────────────────────────

def test_store_filters_out_jobs_it_has_seen(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    assert len(store.filter_new(sample_jobs)) == 3

    store.mark_seen(sample_jobs)
    assert store.count() == 3
    assert store.filter_new(sample_jobs) == []


def test_store_catches_a_repost_under_a_new_url(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen(sample_jobs[:1])

    repost = dict(sample_jobs[0])
    repost["url"] = "https://tracking.example/rotated-url-12345"
    assert store.filter_new([repost]) == []


def test_store_creates_its_own_directory(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "nested" / "deeper" / "jobs.db")
    store.mark_seen(sample_jobs)
    assert store.count() == 3


def test_store_handles_an_empty_list(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    assert store.filter_new([]) == []
    store.mark_seen([])
    assert store.count() == 0


def test_marking_the_same_job_twice_is_harmless(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen(sample_jobs)
    store.mark_seen(sample_jobs)
    assert store.count() == 3


# ─── Postings that failed to score get more runs ──────────────────────────────

def _failed(job: dict) -> dict:
    return {**job, "status": "scoring_error", "score": 0}


def _status(store: JobStore, job: dict) -> tuple:
    conn = store.connect()
    try:
        return conn.execute(
            "SELECT status, score, attempts FROM seen_jobs WHERE job_id = ?",
            (make_job_id(job["url"]),),
        ).fetchone()
    finally:
        conn.close()


def test_a_scoring_error_is_offered_again_next_run(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    job = sample_jobs[0]
    store.mark_seen([_failed(job)])
    assert store.filter_new([job]) == [job]


def test_a_successful_retry_replaces_the_error(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    job = sample_jobs[0]
    store.mark_seen([_failed(job)])
    store.mark_seen([{**job, "status": "new", "score": 82}])
    assert _status(store, job) == ("new", 82, 2)
    assert store.filter_new([job]) == []


def test_retries_run_out(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db", error_retries=2)
    job = sample_jobs[0]
    for _ in range(3):                     # the first attempt plus two retries
        assert store.filter_new([job]) == [job]
        store.mark_seen([_failed(job)])
    assert _status(store, job)[2] == 3
    assert store.filter_new([job]) == []


def test_zero_retries_gives_up_at_once(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db", error_retries=0)
    store.mark_seen([_failed(sample_jobs[0])])
    assert store.filter_new([sample_jobs[0]]) == []


def test_a_failed_posting_is_not_blocked_by_its_own_title_and_company(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    store.mark_seen([_failed(sample_jobs[0])])
    repost = {**sample_jobs[0], "url": "https://tracking.example/rotated-2"}
    assert store.filter_new([repost]) == [repost]


def test_an_ordinary_row_is_never_overwritten(tmp_path, sample_jobs):
    store = JobStore(tmp_path / "jobs.db")
    job = sample_jobs[0]
    store.mark_seen([{**job, "status": "new", "score": 55}])
    store.mark_seen([{**job, "status": "new", "score": 99}])
    assert _status(store, job) == ("new", 55, 1)


def test_a_database_from_before_attempts_existed_is_upgraded(tmp_path, sample_jobs):
    import sqlite3

    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE seen_jobs (job_id TEXT PRIMARY KEY, url TEXT NOT NULL, "
        "title TEXT, company TEXT, location TEXT, site TEXT, score REAL, "
        "status TEXT DEFAULT 'new', first_seen TEXT, date_posted TEXT, "
        "search_term TEXT, verdict_json TEXT)"
    )
    job = sample_jobs[0]
    conn.execute(
        "INSERT INTO seen_jobs (job_id, url, title, company, status, first_seen) "
        "VALUES (?, ?, ?, ?, 'scoring_error', date('now'))",
        (make_job_id(job["url"]), job["url"], job["title"], job["company"]),
    )
    conn.commit()
    conn.close()

    store = JobStore(path)
    assert store.filter_new([job]) == [job]   # an old failure gets its retries
