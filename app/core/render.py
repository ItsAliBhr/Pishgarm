"""Render the company's Word templates with docxtpl (doc 05). The template owns all fixed text;
we only provide the context."""
from __future__ import annotations

from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2 import Environment, StrictUndefined

# Context keys that may carry an image path and are turned into InlineImage objects.
IMAGE_KEYS = {"signature_image": Mm(30), "stamp_image": Mm(35)}


class RenderError(Exception):
    pass


def _prepare(tpl: DocxTemplate, context: dict) -> dict:
    ctx = dict(context)
    for key, width in IMAGE_KEYS.items():
        value = ctx.get(key)
        if isinstance(value, (str, Path)):
            p = Path(value) if value else None
            ctx[key] = InlineImage(tpl, str(p), width=width) if p and p.is_file() else None
    return ctx


def render_docx(template: Path, context: dict, out_path: Path, overwrite: bool = False) -> Path:
    """Render `template` with `context` into `out_path`.

    StrictUndefined makes a missing context key an error instead of an empty gap in the
    document. Existing files are never overwritten unless asked (versioning lives in core.files).
    """
    template, out_path = Path(template), Path(out_path)
    if out_path.exists() and not overwrite:
        raise FileExistsError(out_path)
    tpl = DocxTemplate(str(template))
    try:
        tpl.render(_prepare(tpl, context), Environment(undefined=StrictUndefined), autoescape=True)
    except Exception as e:  # jinja errors carry the missing name; surface it plainly
        raise RenderError(f"{template.name}: {e}") from e
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out_path))
    return out_path


def template_variables(template: Path) -> set[str]:
    return set(DocxTemplate(str(template)).get_undeclared_template_variables())
