"""
The pre-filter and the prompt builder. Both run with no network and no keys —
the model call itself is stubbed out.
"""

import pytest
import yaml

from job_scout import matcher
from job_scout.config import TEMPLATE_DIR


@pytest.fixture
def profile() -> dict:
    return yaml.safe_load((TEMPLATE_DIR / "profile.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def config() -> dict:
    return yaml.safe_load((TEMPLATE_DIR / "config.yaml").read_text(encoding="utf-8"))


# ─── Pre-filter ───────────────────────────────────────────────────────────────

def test_keywords_come_from_search_terms_and_profile_extras():
    config = {"searches": [{"term": "platform engineer"}]}
    profile = {"extra_pre_filter_keywords": ["kubernetes", "sre"]}
    keywords = matcher.build_prefilter_keywords(config, profile)
    assert {"platform", "engineer", "kubernetes", "sre"} <= keywords


def test_short_words_and_stop_words_are_dropped():
    config = {"searches": [{"term": "a job in the cloud"}]}
    keywords = matcher.build_prefilter_keywords(config, {})
    assert "cloud" in keywords
    for dropped in ("a", "in", "the", "job"):
        assert dropped not in keywords


def test_extra_stop_words_can_be_added_from_the_profile():
    config = {"searches": [{"term": "engineer denmark"}]}
    profile = {"pre_filter_stop_words": ["denmark"]}
    keywords = matcher.build_prefilter_keywords(config, profile)
    assert "engineer" in keywords
    assert "denmark" not in keywords


def test_a_matching_keyword_passes():
    job = {"title": "Platform Engineer", "description": "we run kubernetes"}
    assert matcher.passes_prefilter(job, frozenset({"kubernetes"}), [])


def test_no_matching_keyword_fails():
    job = {"title": "Pastry Chef", "description": "croissants"}
    assert not matcher.passes_prefilter(job, frozenset({"kubernetes"}), [])


def test_an_excluded_title_fails_even_when_keywords_match():
    job = {"title": "Junior Platform Engineer", "description": "kubernetes"}
    assert not matcher.passes_prefilter(job, frozenset({"kubernetes"}), ["junior "])


def test_exclusion_looks_at_the_title_only():
    job = {"title": "Platform Engineer", "description": "you will mentor our junior team"}
    assert matcher.passes_prefilter(job, frozenset({"kubernetes"}), ["junior "]) is False
    # The keyword is not in this posting at all, so it fails for that reason.
    job["description"] = "kubernetes, and you will mentor our junior team"
    assert matcher.passes_prefilter(job, frozenset({"kubernetes"}), ["junior "]) is True


def test_no_keywords_means_everything_passes():
    job = {"title": "Anything", "description": ""}
    assert matcher.passes_prefilter(job, frozenset(), [])


# ─── Location filter ──────────────────────────────────────────────────────────

def test_excluded_location_is_rejected():
    assert not matcher.passes_location_filter({"location": "Munich, Germany"}, ["munich"])


def test_other_locations_pass():
    assert matcher.passes_location_filter({"location": "Berlin, Germany"}, ["munich"])


def test_a_missing_location_is_let_through():
    assert matcher.passes_location_filter({"location": ""}, ["munich"])


# ─── Prompt building ──────────────────────────────────────────────────────────

def test_prompt_carries_the_profile(profile):
    template = matcher.build_prompt_template(profile)
    assert profile["candidate"]["name"] in template
    assert "Kubernetes" in template
    assert "Frontend development" in template          # a confirmed gap
    assert "Platform Engineer" in template             # a target role
    assert "German" in template                        # a language


def test_prompt_asks_for_every_field_the_scorer_reads(profile):
    template = matcher.build_prompt_template(profile)
    for field in (
        "score", "language_barrier", "work_authorization_barrier",
        "seniority_match", "key_matches", "gaps", "reasoning",
    ):
        assert f'"{field}"' in template


def test_prompt_placeholders_survive_and_then_fill_in(profile):
    template = matcher.build_prompt_template(profile)
    for placeholder in ("{title}", "{company}", "{location}", "{description}"):
        assert placeholder in template
    filled = template.format(
        title="SRE", company="Acme", location="Berlin", description="k8s"
    )
    assert "Title: SRE" in filled
    assert "{" in filled and "}" in filled, "the JSON example must survive .format()"


def test_prompt_says_so_when_there_are_no_outcomes(profile, tmp_path):
    template = matcher.build_prompt_template(profile, tmp_path / "nothing-here.csv")
    assert "no application outcome data recorded yet" in template


def test_prompt_includes_outcomes_when_the_file_exists(profile, tmp_path):
    outcomes = tmp_path / "outcomes.csv"
    outcomes.write_text(
        "title,company,status\n"
        "Platform Engineer,Northwind Energy,offer\n",
        encoding="utf-8",
    )
    template = matcher.build_prompt_template(profile, outcomes)
    assert "Northwind Energy" in template
    assert "1 reached interview or offer" in template


def test_gap_rule_is_omitted_when_there_are_no_gaps():
    template = matcher.build_prompt_template({"candidate": {"name": "X"}})
    assert "hard cap" not in template


def test_prompt_survives_a_profile_with_almost_nothing_in_it():
    template = matcher.build_prompt_template({"candidate": {}})
    assert "{title}" in template
    assert "not stated" in template


# ─── Parsing the model's reply ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "reply",
    [
        '{"score": 80}',
        '```json\n{"score": 80}\n```',
        'Here you go:\n{"score": 80}\nHope that helps.',
        '```\n{"score": 80}\n```',
    ],
)
def test_parse_response_digs_the_json_out(reply):
    assert matcher.parse_response(reply) == {"score": 80}


def test_parse_response_handles_nested_objects():
    parsed = matcher.parse_response('{"score": 80, "nested": {"a": 1}}')
    assert parsed == {"score": 80, "nested": {"a": 1}}


@pytest.mark.parametrize("reply", ["", "no json here", "[1, 2, 3]", "null"])
def test_parse_response_returns_none_when_there_is_no_object(reply):
    assert matcher.parse_response(reply) is None


# ─── Replies that ran out of tokens ───────────────────────────────────────────

def test_a_reply_cut_off_mid_string_keeps_the_fields_before_the_cut():
    """Seen for real against OpenRouter: the score is there, the sentence is not."""
    reply = (
        '{"score": 20, "language_barrier": false, '
        '"work_authorization_barrier": false, "seniority_match": "match", '
        '"key_matches": ["Experience leading technical initiatives", "Strong w'
    )
    parsed = matcher.parse_response(reply)
    assert parsed == {
        "score": 20,
        "language_barrier": False,
        "work_authorization_barrier": False,
        "seniority_match": "match",
    }


def test_a_reply_cut_off_on_a_trailing_comma():
    parsed = matcher.parse_response('{\n  "score": 38,\n  "language_barrier": false,')
    assert parsed == {"score": 38, "language_barrier": False}


def test_a_reply_cut_off_before_the_first_complete_field_is_not_guessed_at():
    assert matcher.parse_response('{"score": 3') is None


def test_repair_leaves_a_complete_object_alone():
    assert matcher._repair_truncated('{"score": 80}') is None


def test_repair_handles_an_escaped_quote_inside_a_string():
    reply = '{"reasoning": "they said \\"no\\"", "score": 70, "gaps": ["truncat'
    parsed = matcher.parse_response(reply)
    assert parsed == {"reasoning": 'they said "no"', "score": 70}


def test_a_truncated_reply_still_produces_a_score(monkeypatch):
    _stub_model(
        monkeypatch,
        '{"score": 72, "seniority_match": "match", "key_matches": ["Kuber',
    )
    result = matcher.score_jobs(
        [{"title": "Platform Engineer", "description": "kubernetes",
          "location": "Berlin", "url": "https://a"}],
        config={"scoring_model": "gemini:x", "searches": [{"term": "platform"}],
                "scoring_retries": 0},
        profile={"candidate": {}},
    )
    assert result[0]["status"] == "new"
    assert result[0]["score"] == 72


def test_the_prompt_asks_for_short_answers(profile):
    """The reason replies were being truncated at all."""
    template = matcher.build_prompt_template(profile)
    assert "at most 6 words each" in template
    assert "at most 25 words" in template


def test_the_reply_budget_is_big_enough_to_be_worth_having():
    assert matcher.MAX_REPLY_TOKENS >= 1024


@pytest.mark.parametrize(
    "raw,expected",
    [(85, 85), ("85", 85), (85.6, 85), (-5, 0), (500, 100), (None, 0), ("abc", 0)],
)
def test_scores_are_clamped_to_0_100(raw, expected):
    assert matcher._coerce_score(raw) == expected


# ─── score_jobs, with the model stubbed ───────────────────────────────────────

def _stub_model(monkeypatch, reply: str):
    monkeypatch.setattr(matcher, "preflight", lambda spec: None)
    monkeypatch.setattr(matcher, "run_model", lambda *args, **kwargs: reply)


def test_score_jobs_refuses_to_start_when_the_backend_is_not_set_up(no_clis):
    with pytest.raises(matcher.ScoringUnavailable) as excinfo:
        matcher.score_jobs(
            [{"title": "SRE", "description": "kubernetes", "url": "https://a"}],
            config={"scoring_model": "gemini:gemini-3.7-flash", "searches": []},
            profile={"candidate": {}},
        )
    assert "google-genai" in str(excinfo.value) or "GOOGLE_API_KEY" in str(excinfo.value)


def test_score_jobs_attaches_score_and_verdict(monkeypatch):
    _stub_model(monkeypatch, '{"score": 82, "reasoning": "good fit", "key_matches": ["k8s"]}')
    jobs = [{"title": "Platform Engineer", "description": "kubernetes",
             "location": "Berlin", "url": "https://a"}]
    result = matcher.score_jobs(
        jobs,
        config={"scoring_model": "gemini:x", "searches": [{"term": "platform engineer"}],
                "scoring_retries": 0},
        profile={"candidate": {"name": "Test"}},
    )
    assert result[0]["score"] == 82
    assert result[0]["status"] == "new"
    assert result[0]["verdict"]["reasoning"] == "good fit"


@pytest.mark.parametrize(
    "reply,expected_status",
    [
        ('{"score": 90, "language_barrier": true}', "rejected_language"),
        ('{"score": 90, "work_authorization_barrier": true}', "rejected_work_authorization"),
        ('{"score": 90, "seniority_match": "too_junior"}', "rejected_seniority"),
    ],
)
def test_hard_rejections_win_over_a_high_score(monkeypatch, reply, expected_status):
    _stub_model(monkeypatch, reply)
    jobs = [{"title": "Platform Engineer", "description": "kubernetes",
             "location": "Berlin", "url": "https://a"}]
    result = matcher.score_jobs(
        jobs,
        config={"scoring_model": "gemini:x", "searches": [{"term": "platform"}],
                "scoring_retries": 0},
        profile={"candidate": {}},
    )
    assert result[0]["status"] == expected_status
    assert result[0]["score"] == 0


def test_too_senior_is_only_rejected_when_you_ask_for_it(monkeypatch):
    _stub_model(monkeypatch, '{"score": 70, "seniority_match": "too_senior"}')
    jobs = [{"title": "Platform Engineer", "description": "kubernetes",
             "location": "Berlin", "url": "https://a"}]
    base = {"scoring_model": "gemini:x", "searches": [{"term": "platform"}],
            "scoring_retries": 0}

    kept = matcher.score_jobs(list(jobs), config=base, profile={"candidate": {}})
    assert kept[0]["status"] == "new"

    rejected = matcher.score_jobs(
        [dict(jobs[0])], config={**base, "reject_too_senior": True},
        profile={"candidate": {}},
    )
    assert rejected[0]["status"] == "rejected_seniority"


def test_a_broken_model_reply_becomes_a_scoring_error_not_a_crash(monkeypatch):
    _stub_model(monkeypatch, "the model said something unhelpful")
    jobs = [{"title": "Platform Engineer", "description": "kubernetes",
             "location": "Berlin", "url": "https://a"}]
    result = matcher.score_jobs(
        jobs,
        config={"scoring_model": "gemini:x", "searches": [{"term": "platform"}],
                "scoring_retries": 0},
        profile={"candidate": {}},
    )
    assert result[0]["status"] == "scoring_error"


def test_the_cheap_filters_run_before_the_model(monkeypatch):
    calls = []
    monkeypatch.setattr(matcher, "preflight", lambda spec: None)
    monkeypatch.setattr(
        matcher, "run_model",
        lambda *args, **kwargs: calls.append(1) or '{"score": 50}',
    )
    jobs = [
        {"title": "Platform Engineer", "location": "Munich", "description": "kubernetes",
         "url": "https://a"},                                    # excluded location
        {"title": "Junior Platform Engineer", "location": "Berlin",
         "description": "kubernetes", "url": "https://b"},        # excluded title
        {"title": "Pastry Chef", "location": "Berlin", "description": "cake",
         "url": "https://c"},                                     # no keyword
        {"title": "Platform Engineer", "location": "Berlin", "description": "kubernetes",
         "url": "https://d"},                                     # the only one that costs
    ]
    result = matcher.score_jobs(
        jobs,
        config={"scoring_model": "gemini:x", "searches": [{"term": "platform engineer"}],
                "scoring_retries": 0},
        profile={
            "candidate": {},
            "hard_exclude_location_patterns": ["munich"],
            "hard_exclude_title_patterns": ["junior "],
            "extra_pre_filter_keywords": ["kubernetes"],
        },
    )
    assert len(calls) == 1, "only one posting should have reached the model"
    assert [job["status"] for job in result] == [
        "rejected_location", "rejected_prefilter", "rejected_prefilter", "new",
    ]


def test_empty_input_costs_nothing():
    assert matcher.score_jobs([], config={}, profile={}) == []
