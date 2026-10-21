# CV templates

Three blank files the CV skills in `.claude/skills/` read. Everything in them is
a fictional placeholder (Morgan Reyes, Contoso, Fabrikam, Odense). Copy them out
of this folder and make them yours.

| File | Copy it to | What it is |
|------|------------|------------|
| `master-content.md` | `master-resume.md` | Everything true about your work, in more detail than any CV. The only source of facts. |
| `voice-and-tone.md` | `voice-and-tone.md` | How your CVs and letters should sound, and the patterns to strip. |
| `best-practices.md` | `resume-best-practices.md` | A short playbook the skills use for judgement calls. |

The destination names are defaults. The skills call the first file "the master
content file" and accept any name; say which one you use at the start of a run.

```bash
cp templates/cv/master-content.md master-resume.md
cp templates/cv/voice-and-tone.md voice-and-tone.md
cp templates/cv/best-practices.md resume-best-practices.md
```

The copies in your workspace may contain personal details. Do not commit them to
a public repository. `job-scout`'s own `.gitignore` does not know their names, so
check `git status` before you push.

Why these files exist, and how the steps fit together:
[docs/cv-workflow.md](../../docs/cv-workflow.md).
