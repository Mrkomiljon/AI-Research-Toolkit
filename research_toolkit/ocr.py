"""Optional OCR for scanned PDF pages (pages without a text layer).

Nothing here is a hard dependency. Backends are looked up at call time:

- ``docling``   : ``pip install "ai-research-toolkit[ocr]"`` (layout-aware, tables; downloads models on first use)
- ``tesseract`` : PyMuPDF's built-in bridge; needs a Tesseract install (``tesseract`` on PATH or ``TESSDATA_PREFIX``)

OCR output is machine-read text: it can contain recognition errors, so the engine labels every OCR'd page and the
skills tell the author to check quotes from those pages against the scan.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Callable
from pathlib import Path

OcrBackend = Callable[[Path, list[int]], dict[int, str]]

INSTALL_HINT = ('no OCR backend available: install Docling (`python -m pip install "ai-research-toolkit[ocr]"`) '
                "or Tesseract (and put `tesseract` on PATH)")


class OcrUnavailable(RuntimeError):
    """No usable OCR backend; the caller reports this instead of pretending the pages were read."""


def _docling_pipeline_options():
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.do_table_structure = True
    # Pages reach this backend because they have no usable text layer, so OCR the whole page bitmap.
    try:
        opts.ocr_options.force_full_page_ocr = True
    except (AttributeError, ValueError):
        pass
    return opts


def _docling(path: Path, pages: list[int]) -> dict[int, str]:
    import html
    import mimetypes
    import re

    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Some Windows installs map .pdf to a vendor MIME type in the registry (e.g. application/haansoftpdf);
    # Docling then rejects its own "application/pdf" origin. Registering the standard type is harmless elsewhere.
    mimetypes.add_type("application/pdf", ".pdf")
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=_docling_pipeline_options())})
    out: dict[int, str] = {}
    # Convert only the page span that is needed; Docling page numbers are 1-based like ours.
    result = converter.convert(str(path), page_range=(min(pages), max(pages)))
    doc = result.document
    for n in pages:
        text = html.unescape(doc.export_to_markdown(page_no=n) or "")
        # Keep tables as Markdown, but drop image placeholders and heading marks so section detection sees plain headings.
        lines = [re.sub(r"^#+\s*", "", ln) for ln in text.splitlines() if ln.strip() != "<!-- image -->"]
        text = "\n".join(lines).strip()
        if text:
            out[n] = text
    return out


def _tesseract(path: Path, pages: list[int]) -> dict[int, str]:
    import pymupdf

    lang = os.environ.get("RTK_OCR_LANG", "eng")
    out: dict[int, str] = {}
    with pymupdf.open(path) as doc:
        for n in pages:
            page = doc[n - 1]
            tp = page.get_textpage_ocr(dpi=300, full=True, language=lang)
            text = page.get_text("text", textpage=tp) or ""
            if text.strip():
                out[n] = text
    return out


def _has_docling() -> bool:
    return importlib.util.find_spec("docling") is not None


def _has_tesseract() -> bool:
    return bool(shutil.which("tesseract") or os.environ.get("TESSDATA_PREFIX"))


# name -> (availability probe, implementation). Tests and integrators may register their own backend.
BACKENDS: dict[str, tuple[Callable[[], bool], OcrBackend]] = {
    "docling": (_has_docling, _docling),
    "tesseract": (_has_tesseract, _tesseract),
}


def register_backend(name: str, fn: OcrBackend, available: Callable[[], bool] = lambda: True) -> None:
    BACKENDS[name] = (available, fn)


def available_backends() -> dict[str, bool]:
    return {name: bool(probe()) for name, (probe, _) in BACKENDS.items()}


def pick_backend(preferred: str | None = None) -> str:
    preferred = preferred or os.environ.get("RTK_OCR_BACKEND") or None
    avail = available_backends()
    if preferred:
        if preferred not in BACKENDS:
            raise OcrUnavailable(f"unknown OCR backend {preferred!r}; choose from {sorted(BACKENDS)}")
        if not avail[preferred]:
            raise OcrUnavailable(f"OCR backend {preferred!r} is not installed; {INSTALL_HINT}")
        return preferred
    for name, ok in avail.items():
        if ok:
            return name
    raise OcrUnavailable(INSTALL_HINT)


def ocr_pages(path: Path, pages: list[int], backend: str | None = None) -> tuple[dict[int, str], str]:
    """OCR the given 1-based pages. Returns ({page: text}, backend name). Pages that yield no text are omitted."""
    name = pick_backend(backend)
    return BACKENDS[name][1](Path(path), sorted(pages)), name


def status() -> dict:
    avail = available_backends()
    try:
        chosen = pick_backend()
    except OcrUnavailable:
        chosen = None
    return {"backends": avail, "selected": chosen, "language": os.environ.get("RTK_OCR_LANG", "eng"),
            "hint": None if chosen else INSTALL_HINT,
            "note": "OCR text is machine-read and may contain recognition errors; quotes from OCR'd pages must be checked against the scan."}
