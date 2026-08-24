"""
matcher.py. Score every posting from 0 to 100 against the profile.

Three tiers, cheapest first.

  Tier 0  Location. If the posting's location matches one of your
          hard_exclude_location_patterns, it is dropped. Costs nothing.

  Tier 1  Keyword pre-filter. The words from your search terms plus
          extra_pre_filter_keywords must appear somewhere in the title or the
          description, and the title must not match a hard_exclude_title_pattern.
          Costs nothing, and removes most of the noise.

  Tier 2  The model reads the posting and returns a structured verdict. This is
          the only step that costs money, and by this point most postings are
          already gone.

The prompt is built from profile.yaml at run time. Change the file, change what
the scorer looks for. There is nothing to edit in this module to retarget it at
a different candidate, a different country, or a different language.

Status written onto each job:

  new                          passed everything, has a score
  rejected_location            location matched an exclusion pattern
  rejected_prefilter           failed the keyword pre-filter
  rejected_language            posting requires a language the candidate lacks
  rejected_work_authorization  posting requires citizenship or clearance the
                               candidate does not have
  rejected_seniority           posting is aimed below the candidate's level
  scoring_error                the model call or the JSON parse failed
"""

import json
import logging
import re
import time
from pathlib import Path

from . import track_record
from .config import merge_advanced
from .llm import ModelError, label_for, preflight, run_model

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = (
    "You are a precise job-matching engine. You return only the JSON object "
    "asked for, with no commentary and no markdown fences."
)

# How much of a description the model sees. Long enough to carry the
# requirements section, short enough to keep the token bill flat.
DESCRIPTION_CHARS = 3500

# Room for the verdict. 512 was not enough: a model writing full sentences in
# key_matches runs past it and the JSON arrives with no closing brace, which
# turned real scores into scoring errors.
MAX_REPLY_TOKENS = 1024

# Words too common to be worth pre-filtering on.
_STOP_WORDS = frozenset([
    "a", "an", "the", "in", "at", "on", "for", "with", "and", "or",
    "to", "of", "by", "is", "are", "be", "as", "it", "its", "from",
    "that", "this", "not", "but", "has", "have", "was", "were", "will",
    "job", "jobs", "role", "roles", "position", "work", "remote",
])


class ScoringUnavailable(RuntimeError):
    """The chosen backend cannot run. The message says what to install or set."""


# ─── Pre-filter ───────────────────────────────────────────────────────────────

def build_prefilter_keywords(config: dict, profile: dict) -> frozenset:
    """Derive pre-filter words from the search terms plus the profile extras."""
    stop_words = set(_STOP_WORDS)
    stop_words.update(
        str(word).lower().strip()
        for word in profile.get("pre_filter_stop_words", [])
        if str(word).strip()
    )

    keywords: set[str] = set()
    for search in config.get("searches", []):
        for word in str(search.get("term", "")).lower().split():
            word = word.strip(".,;:()\"'")
            if len(word) >= 3 and word not in stop_words:
                keywords.add(word)
    for keyword in profile.get("extra_pre_filter_keywords", []):
        word = str(keyword).lower().strip()
        if word and word not in stop_words:
            keywords.add(word)

    logger.debug("Pre-filter: %d words", len(keywords))
    return frozenset(keywords)


def _lower_list(profile: dict, key: str) -> list[str]:
    return [str(pattern).lower() for pattern in profile.get(key, []) if str(pattern).strip()]


def passes_prefilter(job: dict, keywords: frozenset, exclude_title_patterns: list) -> bool:
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    if any(pattern in title for pattern in exclude_title_patterns):
        return False
    if not keywords:
        return True
    combined = f"{title} {description}"
    return any(keyword in combined for keyword in keywords)


def passes_location_filter(job: dict, exclude_location_patterns: list) -> bool:
    """False when the location matches an excluded region or city."""
    location = (job.get("location") or "").lower()
    if not location:
        return True  # No location given. Let the model judge it.
    return not any(pattern in location for pattern in exclude_location_patterns)


# ─── Prompt ───────────────────────────────────────────────────────────────────

def _escape_braces(text: str) -> str:
    """
    Protect user content from str.format().

    The prompt is assembled as a template and then formatted with the posting's
    title, company and description. Anything in profile.yaml that contains a
    brace would be read as a format field and blow the whole run up with a
    KeyError. Profiles are written by hand and drafted from CVs, so braces do
    turn up.
    """
    return str(text).replace("{", "{{").replace("}", "}}")


def _readable(item) -> str:
    """
    One profile list entry as a string.

    An entry containing ": " that was not quoted parses as a mapping rather
    than a string, so "Python (extensive: automation)" arrives here as a dict.
    Render it back into something the model can read instead of printing a
    Python repr into the prompt.
    """
    if isinstance(item, dict):
        return "; ".join(f"{key}: {value}" for key, value in item.items())
    if isinstance(item, (list, tuple)):
        return ", ".join(_readable(part) for part in item)
    return str(item)


def _bullets(items) -> str:
    lines = [f"  - {_escape_braces(_readable(item))}" for item in (items or [])]
    return "\n".join(lines) if lines else "  (none listed)"


def _languages(candidate: dict) -> str:
    langs = candidate.get("languages") or {}
    if isinstance(langs, dict):
        pairs = [f"{name} ({level})" for name, level in langs.items()]
    else:
        pairs = [str(item) for item in langs]
    return " | ".join(pairs) if pairs else "(not stated)"


def build_prompt_template(
    profile: dict,
    outcomes_path: Path | None = None,
    max_outcomes: int = track_record._MAX_LISTED,
) -> str:
    """
    Build the scoring prompt from profile.yaml.

    The returned string still contains {title}, {company}, {location} and
    {description} placeholders, filled in per posting.
    """
    candidate = profile.get("candidate") or {}
    gaps = profile.get("confirmed_gaps") or []

    outcomes = ""
    if outcomes_path is not None:
        outcomes = track_record.build_context(outcomes_path, max_outcomes)
    outcomes = outcomes or "(no application outcome data recorded yet)"

    gap_rule = ""
    if gaps:
        gap_rule = (
            "If a posting's core day-to-day work needs one or more of these "
            "confirmed gaps, treat that as a hard cap: score no higher than 40, "
            "even if other keywords overlap heavily. A posting that mentions a "
            "gap item only as a nice-to-have or a bonus is not affected.\n\n"
        )

    # Every value below comes from a file somebody wrote by hand or had drafted
    # from a CV, so all of it goes through _escape_braces. Without that, one
    # brace anywhere in the profile turns the whole run into a KeyError.
    def field(key: str, default: str = "not stated") -> str:
        return _escape_braces(_readable(candidate.get(key, default) or default))

    def joined(key: str, empty: str) -> str:
        values = [_readable(item) for item in (profile.get(key) or [])]
        return _escape_braces(", ".join(values)) if values else empty

    return (
        f"You are evaluating a job posting for {field('name', 'the candidate')}.\n\n"
        "CANDIDATE PROFILE:\n"
        f"- Experience: {field('years_experience')} years\n"
        f"- Current role: {field('current_role')}\n"
        f"- Seniority: {field('seniority')}\n"
        f"- Based in: {field('location')}\n"
        f"- Work authorisation: {field('work_authorization')}\n"
        f"- Will work in: {field('target_geography')}\n"
        f"- Languages: {_escape_braces(_languages(candidate))}\n"
        f"- Target roles: {joined('target_roles', 'not stated')}\n"
        f"- Preferred industries: {joined('industries_preferred', 'no preference')}\n"
        f"- Core skills:\n{_bullets(profile.get('core_skills'))}\n"
        f"- Secondary skills:\n{_bullets(profile.get('secondary_skills'))}\n\n"
        f"CONFIRMED GAPS (the candidate does NOT have these, no exceptions):\n"
        f"{_bullets(gaps)}\n"
        f"{gap_rule}"
        "REAL APPLICATION OUTCOMES. This is ground truth. Use it as a directional "
        "signal and work out the pattern yourself: which titles and domains "
        "actually convert for this candidate, and which do not.\n"
        f"{_escape_braces(outcomes)}\n\n"
        "JOB POSTING:\n"
        "Title: {title}\n"
        "Company: {company}\n"
        "Location: {location}\n"
        "Description:\n{description}\n\n"
        "Score this posting for this candidate. Judge fit, not enthusiasm. "
        "Return ONLY valid JSON, no markdown fences, no trailing commas:\n"
        "{{\n"
        '  "score": <integer 0-100>,\n'
        '  "language_barrier": <true if the posting requires fluent or '
        'professional command of a language the candidate does not have at that '
        'level>,\n'
        '  "work_authorization_barrier": <true if the posting requires '
        'citizenship, a security clearance, or a work permit the candidate does '
        'not hold>,\n'
        '  "seniority_match": <"match" | "too_junior" | "too_senior">,\n'
        '  "key_matches": [<up to 3 requirements the candidate genuinely meets, '
        'at most 6 words each>],\n'
        '  "gaps": [<up to 2 genuine gaps, at most 6 words each>],\n'
        '  "reasoning": "<one sentence, at most 25 words>"\n'
        "}}"
    )


def parse_response(text: str) -> dict | None:
    """Pull the JSON object out of a model reply. Returns None if there isn't one."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text or "").strip().rstrip("`").strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # A reply that ran out of tokens mid-sentence is still mostly good: the
    # score is the first field, and everything before the cut is complete JSON.
    # Throwing that away and calling it a scoring error would lose a real score
    # over a verbose sentence at the end.
    repaired = _repair_truncated(cleaned)
    if repaired is not None:
        logger.info(
            "Model reply was cut off; recovered the %d complete field(s) before the cut",
            len(repaired),
        )
        return repaired

    logger.warning("Could not parse scoring JSON from: %.200s", cleaned)
    return None


def _repair_truncated(text: str) -> dict | None:
    """
    Rescue an object that was cut off part-way through.

    Walks the text tracking string and bracket state, finds the last comma at
    the top level of the object. That is the last point where every field before
    it was complete, so the object can be closed there.
    """
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    last_safe: int | None = None

    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            if in_string:
                escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return None  # the object is closed, so it was not truncated
        elif char == "," and depth == 1:
            last_safe = index

    if last_safe is None:
        return None

    try:
        parsed = json.loads(text[start:last_safe] + "}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_score(value) -> int:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0


# ─── Main entry point ─────────────────────────────────────────────────────────

def score_jobs(
    jobs: list[dict],
    config: dict,
    profile: dict,
    outcomes_path: Path | None = None,
) -> list[dict]:
    """
    Score every job. Returns the same list with score, status and verdict added.

    config and profile are passed in, so this module never touches the file
    system except to read outcomes.csv when you give it a path.
    """
    if not jobs:
        return []

    model_spec = str(config.get("scoring_model") or "gemini:gemini-2.5-flash").strip()
    problem = preflight(model_spec)
    if problem:
        raise ScoringUnavailable(problem)

    logger.info("Scoring backend: %s", label_for(model_spec))

    advanced = merge_advanced(config)
    description_chars = int(advanced["description_chars"])
    reply_tokens = int(advanced["reply_tokens"])

    prompt_template = build_prompt_template(
        profile, outcomes_path, int(advanced["outcomes_listed"])
    )
    use_prefilter = bool(config.get("pre_filter", True))
    keywords = build_prefilter_keywords(config, profile) if use_prefilter else frozenset()
    exclude_titles = _lower_list(profile, "hard_exclude_title_patterns")
    exclude_locations = _lower_list(profile, "hard_exclude_location_patterns")
    reject_too_senior = bool(config.get("reject_too_senior", False))
    retries = max(0, int(config.get("scoring_retries", 1)))
    delay = float(config.get("scoring_delay_seconds", 0) or 0)

    result: list[dict] = []
    model_calls = 0

    for job in jobs:
        description = (job.get("description") or "")[:description_chars]

        if not passes_location_filter(job, exclude_locations):
            job.update(score=0, status="rejected_location")
            result.append(job)
            continue

        if use_prefilter and not passes_prefilter(job, keywords, exclude_titles):
            job.update(score=0, status="rejected_prefilter")
            result.append(job)
            continue
        if not use_prefilter and any(
            pattern in (job.get("title") or "").lower() for pattern in exclude_titles
        ):
            job.update(score=0, status="rejected_prefilter")
            result.append(job)
            continue

        prompt = prompt_template.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            description=description,
        )

        parsed = None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text = run_model(
                    model_spec, SCORING_SYSTEM_PROMPT, prompt, max_tokens=reply_tokens
                )
                model_calls += 1
                parsed = parse_response(text)
                if parsed:
                    break
                last_error = ValueError("model reply contained no JSON object")
            except ModelError as exc:
                last_error = exc
            except Exception as exc:  # a backend can fail in its own way
                last_error = exc
            if attempt < retries:
                time.sleep(min(5.0, 1.0 * (attempt + 1)))

        if not parsed:
            logger.error(
                "Scoring failed for '%s' at %s: %s",
                job.get("title", "?"), job.get("company", "?"), last_error,
            )
            job.update(score=0, status="scoring_error")
            result.append(job)
            if delay:
                time.sleep(delay)
            continue

        if parsed.get("language_barrier"):
            job.update(score=0, status="rejected_language", verdict=parsed)
        elif parsed.get("work_authorization_barrier"):
            job.update(score=0, status="rejected_work_authorization", verdict=parsed)
        elif parsed.get("seniority_match") == "too_junior":
            job.update(score=0, status="rejected_seniority", verdict=parsed)
        elif reject_too_senior and parsed.get("seniority_match") == "too_senior":
            job.update(score=0, status="rejected_seniority", verdict=parsed)
        else:
            job.update(score=_coerce_score(parsed.get("score")), status="new", verdict=parsed)

        result.append(job)

        if model_calls and model_calls % 10 == 0:
            logger.info(
                "Scoring progress: %d model calls, %d/%d jobs processed",
                model_calls, len(result), len(jobs),
            )
        if delay:
            time.sleep(delay)

    qualified = sum(1 for job in result if job.get("status") == "new" and job.get("score", 0) > 0)
    errors = sum(1 for job in result if job.get("status") == "scoring_error")
    logger.info(
        "Scoring done: %d model calls | %d/%d qualified | %d errors",
        model_calls, qualified, len(jobs), errors,
    )
    return result
