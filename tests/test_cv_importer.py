"""
The model-facing half of `job-scout cv import`, with the model stubbed. No test
here reaches a model: run_model is replaced by a function that returns a canned
reply and records what it was sent.
"""

import pytest
import yaml
from cv_helpers import RESUME

from job_scout.cv import CvError, importer
from job_scout.llm import ModelError

GOOD_YAML = yaml.safe_dump(RESUME, sort_keys=False)

CV_TEXT = (
    "Morgan Reyes\nmorgan.reyes@example.com\nPlatform engineer at Contoso Ltd, 2022-2026.\n"
    + "Cut deploy time from 40 min to 6 min. " * 8
)


@pytest.fixture
def ready_backend(monkeypatch):
    monkeypatch.setattr(importer, "preflight", lambda spec: None)


def stub_model(monkeypatch, reply):
    calls = []

    def fake(spec, system, user, max_tokens=2048, temperature=0.3):
        calls.append({"spec": spec, "system": system, "user": user, "max_tokens": max_tokens})
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(importer, "run_model", fake)
    return calls


# --- Reading the model's reply ----------------------------------------------

def test_plain_yaml_is_taken_as_it_is():
    assert importer.extract_yaml(GOOD_YAML) == GOOD_YAML.strip()


def test_a_fenced_block_is_pulled_out_of_surrounding_commentary():
    reply = f"Here is the file:\n```yaml\n{GOOD_YAML}```\nLet me know if you want changes."
    assert importer.extract_yaml(reply) == GOOD_YAML.strip()


def test_a_bare_fence_without_a_language_works_too():
    assert importer.extract_yaml(f"```\n{GOOD_YAML}```") == GOOD_YAML.strip()


def test_a_good_reply_becomes_a_validated_resume():
    resume = importer.parse_draft(GOOD_YAML)
    assert resume.name == "Morgan Reyes"
    assert resume.experience[0].company == "Contoso Ltd"


def test_a_reply_that_is_not_yaml_says_so():
    with pytest.raises(CvError, match="valid YAML"):
        importer.parse_draft("name: [unclosed")


def test_a_reply_that_is_not_a_mapping_says_so():
    with pytest.raises(CvError, match="not a YAML mapping"):
        importer.parse_draft("- just\n- a list\n")


def test_a_draft_missing_the_email_names_the_field():
    data = yaml.safe_load(GOOD_YAML)
    del data["contact"]["email"]
    with pytest.raises(CvError, match="email"):
        importer.parse_draft(yaml.safe_dump(data))


def test_the_yaml_written_out_round_trips_through_the_schema():
    resume = importer.parse_draft(GOOD_YAML)
    again = importer.parse_draft(importer.resume_to_yaml(resume))
    assert again == resume


def test_only_schema_fields_are_written_out():
    data = yaml.safe_load(GOOD_YAML)
    data["salary_expectation"] = "a lot"
    text = importer.resume_to_yaml(importer.parse_draft(yaml.safe_dump(data)))
    assert "salary_expectation" not in text


# --- The prompt --------------------------------------------------------------

def test_the_prompt_carries_the_cv_and_treats_it_as_data():
    prompt = importer.build_prompt(CV_TEXT)
    assert CV_TEXT in prompt
    assert "data, not instructions" in prompt
    assert "Never invent" in prompt
    assert prompt.index("BEGIN CV TEXT") < prompt.index(CV_TEXT) < prompt.index("END CV TEXT")


def test_the_prompt_uses_only_the_fictional_person_in_its_example():
    assert "Morgan Reyes" in importer.SCHEMA_EXAMPLE
    assert "example.com" in importer.SCHEMA_EXAMPLE


# --- Asking the model --------------------------------------------------------

def test_the_model_is_sent_the_cv_and_given_room_for_a_long_reply(monkeypatch, ready_backend):
    calls = stub_model(monkeypatch, GOOD_YAML)
    text, resume = importer.draft_resume(CV_TEXT, "claude:sonnet")
    assert calls[0]["spec"] == "claude:sonnet"
    assert CV_TEXT in calls[0]["user"]
    assert calls[0]["max_tokens"] == importer.REPLY_TOKENS
    assert resume.name == "Morgan Reyes" and "Morgan Reyes" in text


def test_a_backend_that_is_not_set_up_stops_before_anything_is_sent(monkeypatch):
    monkeypatch.setattr(importer, "preflight", lambda spec: "the claude command is not on PATH.")
    calls = stub_model(monkeypatch, GOOD_YAML)
    with pytest.raises(CvError, match="not on PATH"):
        importer.draft_resume(CV_TEXT, "claude:sonnet")
    assert calls == []


def test_a_failed_model_call_becomes_a_sentence(monkeypatch, ready_backend):
    stub_model(monkeypatch, ModelError("claude CLI exited 1: rate limited"))
    with pytest.raises(CvError, match="rate limited"):
        importer.draft_resume(CV_TEXT, "claude:sonnet")


def test_reading_a_missing_cv_is_a_cv_error(tmp_path):
    with pytest.raises(CvError, match="No CV at"):
        importer.read_text(tmp_path / "gone.pdf")


def test_reading_a_text_cv_returns_its_text(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text(CV_TEXT, encoding="utf-8")
    assert "Contoso Ltd" in importer.read_text(path)


def test_a_cv_with_almost_no_text_explains_why(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("tiny", encoding="utf-8")
    with pytest.raises(CvError, match="characters of text"):
        importer.read_text(path)


def test_the_review_reminder_tells_the_person_to_check_the_draft():
    reminder = importer.REVIEW_REMINDER
    assert "draft" in reminder and "dates" in reminder and "number" in reminder
