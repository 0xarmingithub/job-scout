"""
job_scout is a job-hunting agent that runs once a day without supervision.

It searches job boards, throws away anything it has already seen, scores every
remaining posting from 0 to 100 against a written profile of the candidate, and
sends the good ones wherever you tell it to.

The candidate profile is a plain YAML file. Change the file, change what the
agent looks for. No code edits.
"""

__version__ = "1.2.3"
__all__ = ["__version__"]
