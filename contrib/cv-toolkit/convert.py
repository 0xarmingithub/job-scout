"""CLI: python convert.py CV-ats.md --out resume.yaml"""
import argparse
import sys

import yaml

from schema import validate
from adapters import ats_markdown_adapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_file")
    parser.add_argument("--format", choices=["ats-markdown"], default="ats-markdown")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.source_file, encoding="utf-8") as f:
        text = f.read()

    data = ats_markdown_adapter.parse(text)

    try:
        validate(data)
    except ValueError as e:
        print(f"Parsed but the result fails schema validation: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, width=100)

    print(f"Wrote {args.out} -- check the education dates before trusting them")


if __name__ == "__main__":
    main()
