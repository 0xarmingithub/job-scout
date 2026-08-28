"""Every renderer exposes: render(resume: Resume, template_path: str | None, out_path: str) -> None
Renderers are looked up by name in render.py's RENDERERS dict — add a module and one entry
to support a new output format, no changes needed elsewhere in the pipeline."""
