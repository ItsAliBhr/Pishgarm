"""Acceptance (phase 0): every template renders with its test context using real docxtpl."""
import json
import re
import zipfile
from pathlib import Path

import pytest

from app import paths
from app.core.render import RenderError, render_docx, template_variables

CONTEXTS = sorted((paths.bundled_templates_dir() / "test_contexts").glob("*.json"))
TEMPLATES = ["attachment_list", "letter_company", "letter_personal", "proforma_company",
             "proforma_personal"]


def _text(docx: Path) -> str:
    with zipfile.ZipFile(docx) as z:
        xml = "".join(z.read(n).decode("utf-8") for n in z.namelist()
                      if n.startswith("word/") and n.endswith(".xml"))
    return re.sub(r"<[^>]+>", "", xml)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_all_five_templates_have_contexts():
    assert sorted(p.stem for p in CONTEXTS) == TEMPLATES


@pytest.mark.parametrize("ctx_file", CONTEXTS, ids=lambda p: p.stem)
def test_render_template(ctx_file, tmp_path):
    ctx = json.loads(ctx_file.read_text(encoding="utf-8"))
    template = paths.template_path(f"{ctx_file.stem}.docx")
    out = render_docx(template, ctx, tmp_path / "out.docx")
    text = _text(out)
    used = {k: v for k, v in ctx.items() if k in template_variables(template)}
    assert "{{" not in text and "{%" not in text, "unrendered docxtpl tag left in output"
    # every non-trivial string in the context must appear in the document
    missing = [s for s in _strings(used) if len(s) > 3 and not s.endswith((".png", ".jpg"))
               and s not in text]
    if ctx_file.stem == "attachment_list" and not any(i.get("buyer_supplied") for i in ctx["items"]):
        missing = [m for m in missing if m != ctx.get("footer_note")]
    assert not missing, f"context values not in output: {missing[:5]}"


def test_personal_letter_with_signature_image(tmp_path):
    ctx = json.loads((paths.bundled_templates_dir() / "test_contexts/letter_personal.json")
                     .read_text(encoding="utf-8"))
    ctx["signature_image"] = str(paths.bundled_assets_dir() / "signature_bahrami.png")
    out = render_docx(paths.template_path("letter_personal.docx"), ctx, tmp_path / "sig.docx")
    with zipfile.ZipFile(out) as z:
        assert any(n.startswith("word/media/") for n in z.namelist())


def test_missing_context_key_is_an_error(tmp_path):
    ctx = json.loads((paths.bundled_templates_dir() / "test_contexts/letter_company.json")
                     .read_text(encoding="utf-8"))
    del ctx["subject"]
    with pytest.raises(RenderError):
        render_docx(paths.template_path("letter_company.docx"), ctx, tmp_path / "x.docx")


def test_never_overwrites_silently(tmp_path):
    ctx = json.loads((paths.bundled_templates_dir() / "test_contexts/letter_company.json")
                     .read_text(encoding="utf-8"))
    out = tmp_path / "a.docx"
    render_docx(paths.template_path("letter_company.docx"), ctx, out)
    with pytest.raises(FileExistsError):
        render_docx(paths.template_path("letter_company.docx"), ctx, out)


def test_user_template_copy_wins(tmp_path):
    import shutil
    user = paths.user_templates_dir() / "letter_company.docx"
    shutil.copy2(paths.bundled_templates_dir() / "letter_company.docx", user)
    assert paths.template_path("letter_company.docx") == user
