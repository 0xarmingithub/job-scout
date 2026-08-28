from schema import Resume


def to_markdown(resume: Resume) -> str:
    """The shared content layout -- used directly by this renderer, and fed to
    Pandoc by the docx renderer so both stay in sync with one definition."""
    lines = [f"# {resume.name}", ""]

    contact_bits = [resume.contact.email]
    if resume.contact.phone:
        contact_bits.append(resume.contact.phone)
    if resume.contact.location:
        contact_bits.append(resume.contact.location)
    lines.append(" | ".join(contact_bits))
    for label, url in resume.contact.links.items():
        lines.append(f"[{label}]({url})")
    lines.append("")

    lines.append("## Summary")
    lines.append(resume.summary.strip())
    lines.append("")

    lines.append("## Experience")
    for entry in resume.experience:
        where = f"{entry.company}, {entry.location}" if entry.location else entry.company
        lines.append(f"### {entry.title} — {where} ({entry.dates})")
        for bullet in entry.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    lines.append("## Skills")
    if resume.skill_groups:
        for group, items in resume.skill_groups.items():
            lines.append(f"**{group}:** {', '.join(items)}")
    else:
        lines.append(", ".join(resume.skills))
    lines.append("")

    lines.append("## Education")
    for entry in resume.education:
        lines.append(f"- **{entry.degree}**, {entry.institution} ({entry.dates})")

    if resume.certifications:
        lines.append("")
        lines.append("## Certifications")
        for cert in resume.certifications:
            lines.append(f"- {cert}")

    if resume.projects:
        lines.append("")
        lines.append("## Projects")
        for p in resume.projects:
            lines.append(f"- {p}")

    if resume.interests:
        lines.append("")
        lines.append("## Interests")
        lines.append("; ".join(resume.interests))

    for heading, body in resume.extra.items():
        lines.append("")
        lines.append(f"## {heading}")
        lines.append(body)

    return "\n".join(lines) + "\n"


def render(resume: Resume, template_path: str | None, out_path: str) -> None:
    """No template needed — this renderer always produces the same clean layout.
    Anyone with no LaTeX, no Word, no template at all still gets a usable file
    they can paste into Google Docs, Word, or a job site's text box."""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(resume))
