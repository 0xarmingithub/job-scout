"""
`job-scout cv doctor` looks at six tools, installs none, and tells you the step
for the platform you are on.
"""

import pytest

from job_scout.cv import doctor as d


def _diagnose(commands=(), modules=()):
    return d.diagnose(
        which=lambda name: f"/usr/bin/{name}" if name in commands else None,
        has_module=lambda name: name in modules,
    )


def test_it_looks_for_the_four_named_tools_and_two_more():
    names = [tool.name for tool in _diagnose()]
    assert names == ["latexmk", "pandoc", "pypdf", "pdftotext", "jinja2", "python-docx"]


def test_nothing_installed_means_everything_is_missing():
    assert not any(tool.installed for tool in _diagnose())


def test_what_is_found_is_marked_found_and_the_rest_is_not():
    tools = {t.name: t for t in _diagnose(commands={"latexmk", "pdftotext"}, modules={"pypdf", "docx"})}
    assert tools["latexmk"].installed and tools["latexmk"].where == "/usr/bin/latexmk"
    assert tools["pdftotext"].installed
    assert tools["pypdf"].installed and tools["python-docx"].installed
    assert not tools["pandoc"].installed
    assert not tools["jinja2"].installed


def test_python_docx_is_looked_up_by_its_module_name():
    asked = []
    d.diagnose(which=lambda name: None, has_module=lambda name: asked.append(name) or False)
    assert "docx" in asked and "python-docx" not in asked


@pytest.mark.parametrize("platform", d.PLATFORMS)
def test_every_tool_has_an_install_step_on_every_platform(platform):
    for tool in _diagnose():
        assert d.install_step(tool.name, platform).strip()


def test_the_steps_differ_by_platform():
    assert "winget" in d.install_step("pandoc", "windows")
    assert "brew" in d.install_step("pandoc", "macos")
    assert "apt" in d.install_step("pandoc", "linux")
    assert "MiKTeX" in d.install_step("latexmk", "windows")
    assert "poppler" in d.install_step("pdftotext", "macos")


@pytest.mark.parametrize(
    "reported, expected",
    [("win32", "windows"), ("cygwin", "linux"), ("darwin", "macos"), ("linux", "linux"), ("freebsd14", "linux")],
)
def test_the_platform_is_named_plainly(reported, expected):
    assert d.current_platform(reported) == expected


def test_the_report_lists_the_steps_only_for_what_is_missing():
    text = d.report(_diagnose(commands={"latexmk"}, modules={"pypdf", "jinja2", "docx"}), "linux")
    assert "found    latexmk" in text
    assert "sudo apt install pandoc" in text
    assert "sudo apt install poppler-utils" in text
    assert "pip install pypdf" not in text, "pypdf is installed, so no step is printed for it"


def test_the_report_says_when_there_is_nothing_to_do():
    everything = _diagnose(
        commands={"latexmk", "pandoc", "pdftotext"}, modules={"pypdf", "jinja2", "docx"}
    )
    text = d.report(everything, "windows")
    assert "Nothing to install." in text
    assert "winget" not in text


def test_the_report_says_that_it_installs_nothing():
    assert "installs nothing" in d.report(_diagnose(), "linux")


def test_the_command_runs_and_exits_zero_even_with_tools_missing(monkeypatch, capsys):
    from job_scout import cli

    monkeypatch.setattr(d.shutil, "which", lambda name: None)
    assert cli.main(["cv", "doctor"]) == 0
    out = capsys.readouterr().out
    assert "missing" in out and "Every one is optional" in out
