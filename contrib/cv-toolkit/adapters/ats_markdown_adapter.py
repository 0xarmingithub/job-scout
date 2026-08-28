"""Parses the ATS-safe Markdown CV format (# Name, a pipe-separated contact line,
then `## Heading` sections) into resume.yaml's dict shape. This is the format
job-scout's tailoring step writes today -- see job-scout/tailor/prompt.md's
"Output" section for the spec this parser follows.

Best-effort: education dates are pulled out of free-text bullets with a regex,
not a real parser. Check the education entries in the generated resume.yaml
before trusting the dates."""
import re

DATE_RE = re.compile(r'([A-Z][a-z]+ \d{4}|\d{4})\s*-\s*(Present|[A-Z][a-z]+ \d{4}|\d{4})')

SUMMARY_HEADINGS = {"summary", "professional summary"}
SKILLS_HEADINGS = {"skills"}
EXPERIENCE_HEADINGS = {"experience"}
EDUCATION_HEADINGS = {"education"}
CERT_HEADINGS = {"certifications"}
PROJECT_HEADINGS = {"projects", "personal projects"}
INTEREST_HEADINGS = {"interests"}


def _parse_contact_line(line: str) -> dict:
    contact = {"links": {}}
    for part in (p.strip() for p in line.split("|")):
        if not part:
            continue
        low = part.lower()
        if "@" in part:
            contact["email"] = part
        elif "linkedin" in low:
            contact["links"]["LinkedIn"] = part
        elif "github" in low:
            contact["links"]["GitHub"] = part
        elif low.startswith(("http", "www.")):
            contact["links"]["Link"] = part
        elif sum(ch.isdigit() for ch in part) >= 5:
            contact["phone"] = part
        else:
            contact["location"] = part
    return contact


def _split_outside_parens(text: str, sep: str = ",") -> list[str]:
    """Split on `sep`, but not on a `sep` that falls inside ( ) -- so
    "agile delivery (Scrum, Kanban)" and "1,000+ endpoints" stay intact."""
    parts = []
    depth = 0
    current = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _parse_skills(body: str) -> tuple[list[str], dict[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    flat: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            group, items = line.split(":", 1)
            groups[group.strip()] = [i.strip() for i in _split_outside_parens(items.strip().rstrip(".")) if i.strip()]
        else:
            flat.extend(i.strip() for i in _split_outside_parens(line.rstrip(".")) if i.strip())
    return flat, groups


def _parse_experience(body: str) -> list[dict]:
    entries = []
    for block in re.split(r'\n(?=### )', body.strip()):
        block = block.strip()
        if not block.startswith("### "):
            continue
        lines = block.splitlines()
        header = lines[0][4:].strip()
        title, _, rest = header.partition(" - ")
        if "," in rest:
            company, location = rest.rsplit(",", 1)
        else:
            company, location = rest, ""

        dates = ""
        bullets = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                bullets.append(line[2:].strip())
            elif not dates:
                dates = line

        entries.append({
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "dates": dates,
            "bullets": bullets,
        })
    return entries


def _parse_education(body: str) -> list[dict]:
    entries = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        line = line[2:].strip()
        degree, _, rest = line.partition(" - ")
        m = DATE_RE.search(rest)
        if m:
            dates = m.group(0)
            institution = rest[:m.start()] + rest[m.end():]
        else:
            dates = ""
            institution = rest
        institution = re.sub(r',\s*\.', '.', institution)
        institution = re.sub(r'\s{2,}', ' ', institution).strip(' ,.')
        entries.append({"degree": degree.strip(), "institution": institution, "dates": dates})
    return entries


def _parse_bullets(body: str) -> list[str]:
    return [line.strip()[2:].strip() for line in body.splitlines() if line.strip().startswith("- ")]


def parse(markdown_text: str) -> dict:
    lines = markdown_text.strip().splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError("expected the file to start with '# Name'")
    name = lines[0][2:].strip()

    contact_line = ""
    rest_start = 1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip():
            contact_line = line.strip()
            rest_start = i + 1
            break
    contact = _parse_contact_line(contact_line)
    if "email" not in contact:
        raise ValueError(f"could not find an email address in the contact line: {contact_line!r}")

    body = "\n" + "\n".join(lines[rest_start:])
    sections = [s for s in re.split(r'\n##\s+', body) if s.strip()]

    data = {
        "name": name,
        "contact": contact,
        "summary": "",
        "experience": [],
        "education": [],
        "skills": [],
        "skill_groups": {},
        "certifications": [],
        "projects": [],
        "interests": [],
        "extra": {},
    }
    for raw_section in sections:
        heading, _, section_body = raw_section.partition("\n")
        heading_key = heading.strip().lower()
        section_body = section_body.strip()

        if heading_key in SUMMARY_HEADINGS:
            data["summary"] = section_body
        elif heading_key in SKILLS_HEADINGS:
            data["skills"], data["skill_groups"] = _parse_skills(section_body)
        elif heading_key in EXPERIENCE_HEADINGS:
            data["experience"] = _parse_experience(section_body)
        elif heading_key in EDUCATION_HEADINGS:
            data["education"] = _parse_education(section_body)
        elif heading_key in CERT_HEADINGS:
            data["certifications"] = _parse_bullets(section_body)
        elif heading_key in PROJECT_HEADINGS:
            data["projects"] = _parse_bullets(section_body)
        elif heading_key in INTEREST_HEADINGS:
            data["interests"] = _parse_bullets(section_body)
        else:
            data["extra"][heading.strip()] = section_body

    return data
