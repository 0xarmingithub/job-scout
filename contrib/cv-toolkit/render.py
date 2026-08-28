"""CLI: python render.py resume.yaml --renderer markdown --out cv.md"""
import argparse
import sys

import yaml

from schema import validate
from renderers import markdown_renderer, latex_renderer, docx_renderer

RENDERERS = {
    "markdown": markdown_renderer.render,
    "latex": latex_renderer.render,
    "docx": docx_renderer.render,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("resume_yaml")
    parser.add_argument("--renderer", choices=RENDERERS.keys(), default="markdown")
    parser.add_argument("--template", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.resume_yaml, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    try:
        resume = validate(data)
    except ValueError as e:
        print(f"Invalid resume.yaml: {e}", file=sys.stderr)
        sys.exit(1)

    RENDERERS[args.renderer](resume, args.template, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
