"""PDF: Word → PDF, image → PDF, «erase region», and same-size merging (doc 05 §5.6)."""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PageObject, PdfReader, PdfWriter, Transformation

log = logging.getLogger(__name__)

A4 = (595.28, 841.89)
IMAGE_MARGIN_PT = 18
RENDER_DPI = 300


class PdfUnavailable(Exception):
    """Neither Word nor LibreOffice is available to convert DOCX to PDF."""


# ----------------------------------------------------------------- DOCX → PDF

def _word_convert(docx: Path, pdf: Path) -> None:
    import pythoncom  # pywin32
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(docx), ReadOnly=True, AddToRecentFiles=False)
        try:
            doc.ExportAsFixedFormat(str(pdf), 17)  # wdExportFormatPDF
        finally:
            doc.Close(False)
    finally:
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def _find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    if sys.platform == "win32":
        for base in (r"C:\Program Files\LibreOffice\program", r"C:\Program Files (x86)\LibreOffice\program"):
            p = Path(base) / "soffice.exe"
            if p.exists():
                return str(p)
    return None


def _soffice_convert(docx: Path, pdf: Path, soffice: str) -> None:
    outdir = pdf.parent
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(docx)],
                   check=True, capture_output=True, timeout=180)
    produced = outdir / (docx.stem + ".pdf")
    if produced != pdf:
        produced.replace(pdf)


def docx_to_pdf(docx: Path, pdf: Path) -> str:
    """Convert with Word (preferred) or LibreOffice. Returns the engine used."""
    docx, pdf = Path(docx).resolve(), Path(pdf).resolve()
    errors = []
    if sys.platform == "win32":
        try:
            _word_convert(docx, pdf)
            return "word"
        except Exception as e:  # Word missing or COM failure → try LibreOffice
            errors.append(f"Word: {e}")
            log.warning("Word PDF export failed: %s", e)
    soffice = _find_soffice()
    if soffice:
        try:
            _soffice_convert(docx, pdf, soffice)
            return "libreoffice"
        except Exception as e:
            errors.append(f"LibreOffice: {e}")
    raise PdfUnavailable("; ".join(errors) or "no converter")


def pdf_available() -> bool:
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            return True
        except ImportError:
            pass
    return _find_soffice() is not None


# ----------------------------------------------------------------- images

def image_to_pdf(image: Path, out: Path, margin_pt: float = IMAGE_MARGIN_PT, dpi: int = 200) -> Path:
    """One A4 page (orientation follows the image) with the image fitted inside an 18pt margin."""
    img = Image.open(image)
    img = img.convert("RGB")
    landscape = img.width > img.height
    w_pt, h_pt = (A4[1], A4[0]) if landscape else A4
    px = lambda pt: int(round(pt / 72 * dpi))  # noqa: E731
    W, H, M = px(w_pt), px(h_pt), px(margin_pt)
    scale = min((W - 2 * M) / img.width, (H - 2 * M) / img.height)
    resized = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    page = Image.new("RGB", (W, H), "white")
    page.paste(resized, ((W - resized.width) // 2, (H - resized.height) // 2))
    out = Path(out)
    page.save(out, "PDF", resolution=dpi)
    return out


def render_page(pdf: Path, page_index: int = 0, dpi: int = 100) -> Image.Image:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return doc[page_index].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        doc.close()


def page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf)).pages)


def erase_regions(pdf: Path, out: Path, regions: dict[int, list[tuple[float, float, float, float]]],
                  dpi: int = RENDER_DPI) -> Path:
    """White-out rectangles. `regions` maps page index → [(x0, y0, x1, y1)] as fractions (0..1)
    of the page, origin top-left. Edited pages become images (so the hidden content is gone)."""
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        rects = regions.get(i)
        if not rects:
            writer.add_page(page)
            continue
        img = render_page(pdf, i, dpi)
        draw = ImageDraw.Draw(img)
        for x0, y0, x1, y1 in rects:
            draw.rectangle([min(x0, x1) * img.width, min(y0, y1) * img.height,
                            max(x0, x1) * img.width, max(y0, y1) * img.height], fill="white")
        buf = io.BytesIO()
        img.save(buf, "PDF", resolution=dpi)
        buf.seek(0)
        writer.add_page(PdfReader(buf).pages[0])
    out = Path(out)
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ----------------------------------------------------------------- merge

def _size(page) -> tuple[float, float]:
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    if (page.get("/Rotate") or 0) % 180:
        w, h = h, w
    return w, h


def merge_same_size(parts: list[Path], out: Path) -> Path:
    """Concatenate PDFs. The first file's first page sets the size; every other page is scaled
    and centred onto a page of that size, keeping its own orientation (portrait/landscape)."""
    readers = [PdfReader(str(p)) for p in parts]
    if not readers or not readers[0].pages:
        raise ValueError("no pages")
    base_w, base_h = _size(readers[0].pages[0])
    writer = PdfWriter()
    for ri, reader in enumerate(readers):
        for page in reader.pages:
            if ri == 0:
                writer.add_page(page)
                continue
            if page.get("/Rotate"):
                page.transfer_rotation_to_content()
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            tw, th = (max(base_w, base_h), min(base_w, base_h)) if w > h else (min(base_w, base_h), max(base_w, base_h))
            s = min(tw / w, th / h)
            tx = (tw - w * s) / 2 - float(page.mediabox.left) * s
            ty = (th - h * s) / 2 - float(page.mediabox.bottom) * s
            blank = PageObject.create_blank_page(width=tw, height=th)
            blank.merge_transformed_page(page, Transformation().scale(s).translate(tx, ty))
            writer.add_page(blank)
    out = Path(out)
    with open(out, "wb") as f:
        writer.write(f)
    return out
