"""
job_scout.cv. The CV pipeline behind `job-scout cv`.

Content and layout are kept apart. `resume.yaml` holds what the CV says, in a
plain format that belongs to nobody. A template you own decides how it looks.

    import    an existing CV (Word, PDF, text, markdown) to resume.yaml, using a model
    render    resume.yaml into your own template (.tex, .docx) or plain markdown
    build     render a .tex template and compile it to a PDF with latexmk
    verify    read the compiled PDF the way an applicant tracking system will
    doctor    report which of the optional tools are installed

Everything here is optional. Importing the package runs nothing; the daily run never calls it.
"""


class CvError(RuntimeError):
    """Something in the CV pipeline failed. The message says what to do next."""
