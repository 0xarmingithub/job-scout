"""CLI: python import_cv.py mycv.pdf --out resume.yaml

Reads an existing CV -- .txt, .md, .pdf, or .docx -- and drafts resume.yaml
from it via a model (see adapters/cv_import_adapter.py for what gets sent
where). This is a draft: a model reading free-text CVs will occasionally
misplace a date or merge two roles. Read the output before trusting it.
"""
import argparse
import sys

import yaml

from schema import validate
from adapters.cv_import_adapter import import_cv, CvImportError, DEFAULT_COMMAND


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cv_file")
    parser.add_argument("--command", default=DEFAULT_COMMAND,
                         help=f"model to run, prompt fed on stdin (default: {DEFAULT_COMMAND!r})")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    try:
        data = import_cv(args.cv_file, command=args.command)
    except CvImportError as e:
        print(f"Could not import {args.cv_file}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        validate(data)
    except ValueError as e:
        print(f"Model draft fails schema validation: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, width=100)

    print(f"Wrote {args.out} -- this is a model's draft of your CV. Read it before trusting it.")


if __name__ == "__main__":
    main()
