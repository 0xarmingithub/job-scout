"""
doctor.py. Which of the optional CV tools are installed, and how to get the rest.

This installs nothing. It looks, and prints the command you would run for the
platform you are on. Every tool here is optional, and each one unlocks one job:

  latexmk     compile a .tex template to a PDF       (job-scout cv build)
  pandoc      write a .docx from your Word styles    (job-scout cv render --renderer docx)
  pypdf       read a PDF, and check one afterwards   (job-scout cv verify, cv import)
  pdftotext   a second opinion on a compiled PDF     (job-scout cv verify --extractor both)
  jinja2      fill a .tex template                   (job-scout cv render, cv build)
  python-docx read a Word CV                         (job-scout cv import)
"""

import importlib.util
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass

PLATFORMS = ("windows", "macos", "linux")


@dataclass
class Tool:
    name: str
    kind: str  # "command" or "python"
    needed_for: str
    installed: bool = False
    where: str = ""


# name, kind, what it is for. The module name differs from the package name for python-docx.
_TOOLS = (
    ("latexmk", "command", "compiling a .tex template to a PDF (cv build)"),
    ("pandoc", "command", "writing a .docx from your own Word styles (cv render --renderer docx)"),
    ("pypdf", "python", "reading a PDF, and checking a compiled one (cv verify, cv import)"),
    ("pdftotext", "command", "an optional second opinion when checking a PDF (cv verify --extractor both)"),
    ("jinja2", "python", "filling a .tex template (cv render, cv build)"),
    ("python-docx", "python", "reading a Word CV (cv import)"),
)
_MODULE_NAMES = {"pypdf": "pypdf", "jinja2": "jinja2", "python-docx": "docx"}

_INSTALL = {
    "latexmk": {
        "windows": (
            "Install TeX Live (https://tug.org/texlive/windows.html) or MiKTeX "
            "(https://miktex.org/download). Both include latexmk. MiKTeX also needs Perl "
            "for latexmk to run."
        ),
        "macos": "brew install --cask mactex-no-gui   (or the smaller: brew install --cask basictex, then sudo tlmgr install latexmk)",
        "linux": "sudo apt install latexmk texlive-latex-recommended texlive-latex-extra   (Debian and Ubuntu. Other distributions package TeX Live under their own names)",
    },
    "pandoc": {
        "windows": "winget install --id JohnMacFarlane.Pandoc",
        "macos": "brew install pandoc",
        "linux": "sudo apt install pandoc",
    },
    "pypdf": {p: "pip install pypdf" for p in PLATFORMS},
    "pdftotext": {
        "windows": "scoop install poppler   (or: choco install poppler)",
        "macos": "brew install poppler",
        "linux": "sudo apt install poppler-utils",
    },
    "jinja2": {p: "pip install jinja2" for p in PLATFORMS},
    "python-docx": {p: "pip install python-docx" for p in PLATFORMS},
}


def current_platform(name: str | None = None) -> str:
    """windows, macos or linux. Anything else is treated as linux."""
    name = name or sys.platform
    if name.startswith("win"):
        return "windows"
    if name == "darwin":
        return "macos"
    return "linux"


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - a broken install
        return False


def diagnose(
    which: Callable[[str], str | None] | None = None,
    has_module: Callable[[str], bool] | None = None,
) -> list[Tool]:
    """Look for every tool. The two lookups are injectable so a test needs neither TeX nor pip."""
    which = which or shutil.which
    has_module = has_module or _module_present
    found = []
    for name, kind, needed_for in _TOOLS:
        tool = Tool(name=name, kind=kind, needed_for=needed_for)
        if kind == "command":
            path = which(name)
            tool.installed = bool(path)
            tool.where = path or ""
        else:
            tool.installed = has_module(_MODULE_NAMES[name])
        found.append(tool)
    return found


def install_step(tool_name: str, platform: str) -> str:
    return _INSTALL[tool_name][platform]


def report(tools: list[Tool], platform: str) -> str:
    """The text `job-scout cv doctor` prints."""
    lines = [f"CV tools on this machine ({platform}). Every one is optional.", ""]
    for tool in tools:
        mark = "found  " if tool.installed else "missing"
        where = f" at {tool.where}" if tool.where else ""
        lines.append(f"  {mark}  {tool.name}{where}")
        lines.append(f"           for {tool.needed_for}")
    missing = [tool for tool in tools if not tool.installed]
    lines.append("")
    if not missing:
        lines.append("Nothing to install.")
        return "\n".join(lines)
    lines.append("To install what is missing (this command installs nothing itself):")
    for tool in missing:
        lines.append(f"  {tool.name}")
        lines.append(f"    {install_step(tool.name, platform)}")
    lines.append("")
    lines.append("You only need the ones for the commands you use. Markdown output needs none of them.")
    return "\n".join(lines)
