# CV toolkit has moved

This folder used to hold a stand-alone CV toolkit. It is now part of the
package, as the `job-scout cv` command, and lives in `job_scout/cv/`.

| You used to run | Now run |
|---|---|
| `python import_cv.py my-cv.pdf --out resume.yaml` | `job-scout cv import my-cv.pdf` |
| `python convert.py CV-ats.md --out resume.yaml` | `job-scout cv convert CV-ats.md` |
| `python render.py resume.yaml --template t.tex --out cv.tex` | `job-scout cv render resume.yaml --template t.tex --out cv.tex` |
| `latexmk -pdf cv.tex` | `job-scout cv build resume.yaml --template t.tex` |

New: `job-scout cv verify cv.pdf` checks what an applicant tracking system will
read out of the finished PDF, and `job-scout cv doctor` reports which of the
optional tools are installed.

Read [docs/cv.md](../../docs/cv.md).
