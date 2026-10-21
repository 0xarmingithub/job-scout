"""
validate_cv.py. A second opinion on a finished CV, from one or more models.

Opt-in. Nothing in `job-scout run` calls this. You give it a job description and a
CV as text or markdown. It sends the same analysis prompt to each model you chose,
and writes one report with each model's score and analysis.

One model call per model per run. Each model is paid for by its own backend, a
CLI on this machine or an API with a key of yours.
"""

import concurrent.futures
import logging
import re
from datetime import datetime
from pathlib import Path

from .llm import ModelError, run_model

logger = logging.getLogger(__name__)

MAX_MODELS = 4

ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior technical recruiter and career coach with deep expertise in "
    "the field of the job description. Your task: perform a rigorous, honest analysis "
    "of how well this candidate's CV matches the provided job description. Be critical "
    "and specific. Platitudes are not useful. Every observation must reference specific "
    "text from either the CV or the JD."
)

ANALYSIS_USER_TEMPLATE = """\
## JOB DESCRIPTION

{jd}

---

## CANDIDATE CV

{cv}

---

## YOUR ANALYSIS

Structure your response exactly as follows, using these headings:

### MATCH SCORE
A single percentage (0-100) on its own line, followed by one sentence justifying it.

### KEYWORD COVERAGE
- **WELL COVERED**: JD keywords and requirements present and strongly shown
- **WEAKLY COVERED**: present but vague, buried, or not quantified
- **MISSING**: absent from the CV

### EXPERIENCE ALIGNMENT
For each major JD requirement: Strong, Partial, Weak or None, with one line of evidence.

### BULLET QUALITY
Up to 5 bullets that are generic, unquantified, or weakly worded. For each, state the
problem and a concrete fix. Do not invent facts. Mark a needed metric as [NEEDS OWNER INPUT].

### POSITIONING
Two or three sentences: does the profile summary land for this role?

### TOP 5 PRIORITISED IMPROVEMENTS
A numbered list, most impactful first. Name the section, what is wrong, and the fix.
"""

_SCORE_LINE = re.compile(r"(\d{1,3})\s*%?")


def extract_score(analysis: str) -> str:
    """The number under MATCH SCORE, as '72%'. 'N/A' when none can be found."""
    if "MATCH SCORE" not in analysis:
        return "N/A"
    after = analysis.split("MATCH SCORE", 1)[1]
    for line in after.splitlines():
        line = line.strip().strip("*").strip()
        if not line or line.startswith("#"):
            continue
        match = _SCORE_LINE.match(line)
        if match and 0 <= int(match.group(1)) <= 100:
            return f"{int(match.group(1))}%"
        break
    return "N/A"


def call_model(spec: str, jd: str, cv: str) -> dict:
    """One model's analysis. Never raises: a failure is recorded in the result."""
    try:
        analysis = run_model(
            spec,
            ANALYSIS_SYSTEM_PROMPT,
            ANALYSIS_USER_TEMPLATE.format(jd=jd, cv=cv),
            max_tokens=2048,
            temperature=0.3,
        )
        return {"model": spec, "analysis": analysis, "error": None}
    except (ModelError, Exception) as exc:  # a backend can fail in its own way
        logger.warning("%s could not analyse the CV: %s", spec, exc)
        return {"model": spec, "analysis": "", "error": str(exc)[:400]}


def validate(jd: str, cv: str, specs: list[str]) -> list[dict]:
    """Ask each model, in parallel. Results come back in the order of `specs`."""
    if not specs:
        raise ValueError("no models chosen")
    if len(specs) > MAX_MODELS:
        raise ValueError(f"at most {MAX_MODELS} models, got {len(specs)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(specs)) as pool:
        return list(pool.map(lambda spec: call_model(spec, jd, cv), specs))


def build_report(results: list[dict], jd_path: str, cv_path: str) -> str:
    """The report as markdown: one section per model, and the average score."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# CV validator report",
        "",
        f"- Job description: `{jd_path}`",
        f"- CV: `{cv_path}`",
        f"- Written: {stamp}",
        "",
    ]
    scores = []
    for result in results:
        score = extract_score(result["analysis"]) if not result["error"] else "N/A"
        scores.append(score)
        lines += [f"## {result['model']}", "", f"**Match score:** {score}", ""]
        if result["error"]:
            lines += [f"The model did not answer: {result['error']}", ""]
        else:
            lines += [result["analysis"].strip(), ""]

    numbers = [int(s.rstrip("%")) for s in scores if s != "N/A"]
    if numbers:
        average = sum(numbers) / len(numbers)
        lines += [f"**Average across {len(numbers)} model(s):** {average:.0f}%", ""]
    lines += [
        "A model's score is its opinion of this CV for this job. Two models often",
        "disagree by a lot. Read the analyses before you act on any number.",
        "",
    ]
    return "\n".join(lines)


def write_report(output: Path, text: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return output
