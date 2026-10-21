---
name: ats-compatibility-check
description: Check a tailored CV's plain-text version and its PDF text layer for known applicant-tracking-system parse risks, and recommend specific fixes. Covers keyword coverage, headings, tables, acronyms and PDF extraction.
---

# ATS compatibility check

An applicant tracking system reads the text layer of your file, not what you
see. A CV can look perfect and extract as scrambled columns, missing contact
details or garbled ligatures. This skill checks what a parser would read back.

Doing this by hand instead? Extract the text from your PDF (`pdftotext -layout
CV.pdf -`) and read it top to bottom as if you were a machine. The checklist
below says what to look for.

Where things live: [docs/cv-workflow.md](../../../docs/cv-workflow.md#where-things-live).

## When to use

- After `resume-tailor` has produced the CV, its plain-text variant and a built PDF.
- When the user asks "will this parse" or "is it ATS safe".

## Inputs

- `CV-ats.md` in the application folder: the plain version meant for text fields
  and for portals that parse badly.
- The CV source file (LaTeX, Word, or whatever the user uses) for structural risks.
- The built PDF, if one exists, for a text-layer check.
- `analysis.md`: the top-10 keywords and the acronym map.

## The PDF text-layer check

Available from 1.10.0: `job-scout cv verify` runs this check for you and exits
non-zero when something fails (run `job-scout cv verify --help` for its options).
`job-scout cv doctor`, also from 1.10.0, checks that the tools it needs are installed.

Until then, do it by hand:

```bash
pdftotext -layout CV.pdf -
```

Read the output and confirm:

- The name comes first, and email, phone and location extract on readable lines,
  not split or interleaved with other text.
- Section headings survive as plain lines: Summary, Skills, Experience,
  Education, Certifications.
- Reading order is right. Two-column layouts often serialise one column after
  the other, or worse, line by line across both.
- Bullet characters survive or degrade to `-` or `*`. They do not turn into
  stray symbols.
- Ligatures and accented letters extract correctly: "fi" is not a single odd
  glyph, and a name such as "Ødegaard" keeps its first letter.
- No leftover markup from the source format (backslashes, braces, `%`).
- Page count matches what you intended.

A clean build proves only that the document exists. The extracted text is the
only version an ATS ever sees.

## Output

Append to `notes.md` in the application folder, under a heading with today's date:

```markdown
## ATS compatibility, YYYY-MM-DD

**Likely ATS:** {name if the posting URL shows it, else "unknown"}
**Verdict:** safe / minor risk / blocking

### Keyword coverage against the top 10

| Keyword | In CV-ats.md | In the PDF text | Note |
|---------|--------------|-----------------|------|

Missing from the top 10: ...

### Parse risks
- Headings: standard or not
- Tables used for layout: none / where
- Images or icons that carry meaning: none / where
- Multi-column sections: where, and whether the extract keeps order
- Header or footer text that lands in the middle of the extract

### Acronyms
- Paired with the full term at first use: ...
- Missing pairing: ...

### PDF text layer
{Result of `job-scout cv verify`, or what the manual read showed}

### Recommended actions
- A concrete fix or an accepted risk, per finding
```

## Workflow

1. Read the top-10 keywords and the acronym map in `analysis.md`. They set the
   bar for coverage.
2. Scan `CV-ats.md`:
   - Standard headings only: Professional Summary, Skills, Experience (or Work
     Experience), Education, Certifications. Flag any invented heading.
   - Layout tables are a risk. A small skills table is tolerable, a comma list is safer.
   - No images, emojis or decorative separators.
   - Acronym and full term together at first mention.
3. Scan the CV source structurally. Flag multi-column blocks, running headers
   and footers, and any image carrying content. Note them. Do not rebuild the
   layout to please a parser: the designed version exists for people.
4. Run the PDF text-layer check above, if a PDF exists.
5. Count each top-10 keyword in both versions. A P0 keyword that is entirely
   missing means the tailoring step missed it. Report it. Do not add the term if
   the master content file does not support it: keyword coverage is never a
   reason to claim something the user has not done.
6. Write the audit block and the verdict:
   - **Safe:** no blocking findings and at most two minor ones.
   - **Minor risk:** one or two blocking-type findings, or many minor ones.
   - **Blocking:** three or more, or a P0 keyword entirely absent.

## Rules

- The designed PDF is for human readers, so layout comes first there. The plain
  `CV-ats.md` is the ATS version: strip every risk from it.
- Some portals parse Word documents better than PDFs. If the posting URL points
  to one, say so in `notes.md` so the user can plan the upload format.
- Platforms that show a "paste your CV" text box are best served by `CV-ats.md`.
- Never trade honesty for coverage. A missing keyword is a finding, not an order
  to add the word.

## Spotting the ATS from the posting URL

| URL contains | Likely system |
|--------------|---------------|
| `myworkdayjobs.com` | Workday |
| `greenhouse.io` | Greenhouse |
| `lever.co` | Lever |
| `taleo.net` | Taleo |
| `successfactors.com` | SAP SuccessFactors |
| the company's own domain | unknown, assume the strictest parser |
