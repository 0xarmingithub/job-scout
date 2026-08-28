"""Format-neutral resume content model. No renderer imports this the other way around."""
from dataclasses import dataclass, field


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
    skill_groups: dict[str, list[str]] = field(default_factory=dict)  # optional: grouped skills win over flat `skills` when both present
    certifications: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)  # unrecognized "## Heading" sections, kept verbatim so nothing is silently dropped


REQUIRED_TOP_LEVEL = ["name", "contact", "summary", "experience", "education"]
REQUIRED_CONTACT = ["email"]
REQUIRED_EXPERIENCE = ["title", "company", "dates"]
REQUIRED_EDUCATION = ["degree", "institution", "dates"]


def validate(data: dict) -> Resume:
    """Parse a raw dict (as loaded from YAML) into a Resume, or raise ValueError
    naming the exact missing field. This is the one gate every renderer sits behind."""
    missing = [f for f in REQUIRED_TOP_LEVEL if f not in data]
    if missing:
        raise ValueError(f"resume.yaml is missing top-level field(s): {', '.join(missing)}")
    if not data.get("skills") and not data.get("skill_groups"):
        raise ValueError("resume.yaml needs at least one of: skills, skill_groups")

    contact_data = data["contact"]
    missing = [f for f in REQUIRED_CONTACT if f not in contact_data]
    if missing:
        raise ValueError(f"contact is missing field(s): {', '.join(missing)}")
    contact = Contact(
        email=contact_data["email"],
        phone=contact_data.get("phone", ""),
        location=contact_data.get("location", ""),
        links=contact_data.get("links", {}),
    )

    experience = []
    for i, entry in enumerate(data["experience"]):
        missing = [f for f in REQUIRED_EXPERIENCE if f not in entry]
        if missing:
            raise ValueError(f"experience[{i}] is missing field(s): {', '.join(missing)}")
        experience.append(ExperienceEntry(
            title=entry["title"],
            company=entry["company"],
            dates=entry["dates"],
            location=entry.get("location", ""),
            bullets=entry.get("bullets", []),
        ))

    education = []
    for i, entry in enumerate(data["education"]):
        missing = [f for f in REQUIRED_EDUCATION if f not in entry]
        if missing:
            raise ValueError(f"education[{i}] is missing field(s): {', '.join(missing)}")
        education.append(EducationEntry(
            degree=entry["degree"],
            institution=entry["institution"],
            dates=entry["dates"],
        ))

    return Resume(
        name=data["name"],
        contact=contact,
        summary=data["summary"],
        experience=experience,
        education=education,
        skills=data.get("skills", []),
        skill_groups=data.get("skill_groups", {}),
        certifications=data.get("certifications", []),
        projects=data.get("projects", []),
        interests=data.get("interests", []),
        extra=data.get("extra", {}),
    )
