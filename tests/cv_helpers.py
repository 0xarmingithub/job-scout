"""
Helpers for the `job-scout cv` tests.

make_pdf builds a real, minimal PDF by hand: a catalog, a page tree, the built-in
Helvetica font and one content stream per page. No LaTeX and no PDF library is
needed to make it, so the text extractors are tested against a file whose exact
contents are known.
"""

from pathlib import Path

RESUME = {
    "name": "Morgan Reyes",
    "contact": {
        "email": "morgan.reyes@example.com",
        "phone": "+45 12 34 56 78",
        "location": "Odense, Denmark",
        "links": {"LinkedIn": "https://linkedin.example/in/morgan-reyes"},
    },
    "summary": "Platform engineer with eight years of experience.",
    "experience": [
        {
            "title": "Senior Platform Engineer",
            "company": "Contoso Ltd",
            "location": "Odense",
            "dates": "2022-2026",
            "bullets": ["Cut deploy time from 40 min to 6 min", "Wrote the on-call runbooks"],
        },
    ],
    "education": [
        {"degree": "BSc Computer Science", "institution": "Example University", "dates": "2015-2019"},
    ],
    "skills": ["Python", "Kubernetes"],
}


def _escape(line: str) -> bytes:
    raw = line.encode("latin-1")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """A PDF with one page per inner list, one line of text per string."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(count))
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for index, lines in enumerate(pages):
        page_id, content_id = 4 + 2 * index, 5 + 2 * index
        stream = b"BT /F1 11 Tf 14 TL 50 780 Td " + b" ".join(
            b"(" + _escape(line) + b") Tj T*" for line in lines
        ) + b" ET"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("ascii") + objects[number] + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii") + b"0000000000 65535 f \n"
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def write_pdf(path: Path, pages: list[list[str]]) -> Path:
    path.write_bytes(make_pdf(pages))
    return path


def good_cv_lines() -> list[str]:
    """A page of CV-shaped text that passes every check against RESUME."""
    return [
        "Morgan Reyes",
        "morgan.reyes@example.com | +45 12 34 56 78 | Odense, Denmark",
        "Summary",
        "Platform engineer with eight years of experience running Kubernetes clusters.",
        "Experience",
        "Senior Platform Engineer, Contoso Ltd, Odense (2022-2026)",
        "Cut deploy time from 40 min to 6 min by rebuilding the CI pipeline on GitHub Actions",
        "Led the migration of 12 services from virtual machines to Kubernetes",
        "Wrote the on-call runbooks that the whole platform team still uses",
        "Education",
        "BSc Computer Science, Example University (2015-2019)",
        "Skills",
        "Python, Kubernetes, Terraform, PostgreSQL, GitHub Actions, Azure, Linux, Docker",
        "Built the payments service, which handled fifty thousand transactions a day",
        "Moved the nightly reconciliation job from cron to a queue-based worker",
        "Mentored four junior engineers and ran the weekly architecture review",
        "Reduced cloud spend by consolidating idle clusters and right-sizing nodes",
        "Introduced structured logging and distributed tracing across services",
    ]
