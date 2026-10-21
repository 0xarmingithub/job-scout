"""
schema.py. The format-neutral resume content model.

`validate()` is the one gate every renderer sits behind. Nothing else in this
package reads a raw resume.yaml dict directly, except `verify`, which only needs
the name, email and phone and must work on a file that is not quite complete.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contact:
    email: str
    phone: str = ""
    location: str = ""
    links: dict[str, str] = field(default_factory=dict)  # e.g. {"LinkedIn": "https://..."}


@dataclass
class ExperienceEntry:
    title: str
    company: str
    dates: str
    location: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass
class EducationEntry:
    degree: str
    institution: str
    dates: str


@dataclass
class Resume:
    name: str
    contact: Contact
    summary: str
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    skills: list[str] = field(default_factory=list)
    # Optional. Grouped skills win over the flat `skills` list when both are present.
    skill_groups: dict[str, list[str]] = field(default_factory=dict)
    certifications: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    # Headings the importer did not recognise, kept verbatim so nothing is silently dropped.
    extra: dict[str, str] = field(default_factory=dict)


REQUIRED_TOP_LEVEL = ["name", "contact", "summary", "experience", "education"]
REQUIRED_CONTACT = ["email"]
REQUIRED_EXPERIENCE = ["title", "company", "dates"]
REQUIRED_EDUCATION = ["degree", "institution", "dates"]


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping of field names to values.")
    return value


def _entries(value: Any, label: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    return [_mapping(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _text_list(value: Any) -> list[str]:
    """A list of strings. A bare string becomes a one-item list, and None becomes empty."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def validate(data: Any) -> Resume:
    """
    Parse a raw dict (as loaded from YAML) into a Resume, or raise ValueError
    naming the exact missing field.
    """
    data = _mapping(data, "resume.yaml")
    missing = [name for name in REQUIRED_TOP_LEVEL if name not in data]
    if missing:
        raise ValueError(f"resume.yaml is missing top-level field(s): {', '.join(missing)}")
    if not data.get("skills") and not data.get("skill_groups"):
        raise ValueError("resume.yaml needs at least one of: skills, skill_groups")

    contact_data = _mapping(data["contact"], "contact")
    missing = [name for name in REQUIRED_CONTACT if name not in contact_data]
    if missing:
        raise ValueError(f"contact is missing field(s): {', '.join(missing)}")
    contact = Contact(
        email=str(contact_data["email"]),
        phone=str(contact_data.get("phone") or ""),
        location=str(contact_data.get("location") or ""),
        links={str(k): str(v) for k, v in _mapping(contact_data.get("links") or {}, "contact.links").items()},
    )

    experience = []
    for index, entry in enumerate(_entries(data["experience"], "experience")):
        missing = [name for name in REQUIRED_EXPERIENCE if name not in entry]
        if missing:
            raise ValueError(f"experience[{index}] is missing field(s): {', '.join(missing)}")
        experience.append(ExperienceEntry(
            title=str(entry["title"]),
            company=str(entry["company"]),
            dates=str(entry["dates"]),
            location=str(entry.get("location") or ""),
            bullets=_text_list(entry.get("bullets")),
        ))

    education = []
    for index, entry in enumerate(_entries(data["education"], "education")):
        missing = [name for name in REQUIRED_EDUCATION if name not in entry]
        if missing:
            raise ValueError(f"education[{index}] is missing field(s): {', '.join(missing)}")
        education.append(EducationEntry(
            degree=str(entry["degree"]),
            institution=str(entry["institution"]),
            dates=str(entry["dates"]),
        ))

    groups = _mapping(data.get("skill_groups") or {}, "skill_groups")
    return Resume(
        name=str(data["name"]),
        contact=contact,
        summary=str(data["summary"] or ""),
        experience=experience,
        education=education,
        skills=_text_list(data.get("skills")),
        skill_groups={str(group): _text_list(items) for group, items in groups.items()},
        certifications=_text_list(data.get("certifications")),
        projects=_text_list(data.get("projects")),
        interests=_text_list(data.get("interests")),
        extra={str(k): str(v) for k, v in _mapping(data.get("extra") or {}, "extra").items()},
    )
