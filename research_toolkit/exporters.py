"""Structured export helpers: CSV, XLSX, DOCX, Markdown, JSON. All writers are deterministic."""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .schemas import SourceRecord


def _cell(v: Any) -> Any:
    if isinstance(v, (list, tuple, set)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "value"):  # Enum
        return v.value
    return v


def write_csv(rows: Iterable[dict], path: Path, columns: list[str] | None = None) -> Path:
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = columns or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r.get(k)) for k in cols})
    return path


def write_xlsx(sheets: dict[str, list[dict]], path: Path, columns: dict[str, list[str]] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheets.items():
        ws = wb.create_sheet(title=sheet_name[:31])
        cols = (columns or {}).get(sheet_name) or (list(rows[0].keys()) if rows else ["(empty)"])
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDEBF7")
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in rows:
            ws.append([_cell(r.get(k)) for k in cols])
        for i, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [min(60, len(str(_cell(r.get(col)) or ""))) for r in rows[:200]])
            ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, width + 2))
        ws.freeze_panes = "A2"
    wb.save(path)
    return path


def read_xlsx(path: Path, sheet: str | None = None) -> list[dict]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h) if h is not None else "" for h in rows[0]]
    return [dict(zip(header, r, strict=False)) for r in rows[1:] if any(v is not None for v in r)]


def write_docx(path: Path, title: str, sections: list[tuple[str, str]], *, metadata_note: str | None = None) -> Path:
    """sections: list of (heading, body). Body paragraphs are split on blank lines; '- ' lines become bullets."""
    from docx import Document

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading(title, level=0)
    if metadata_note:
        p = doc.add_paragraph()
        run = p.add_run(metadata_note)
        run.italic = True
    for heading, body in sections:
        if heading:
            doc.add_heading(heading, level=1)
        for block in (body or "").split("\n\n"):
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            if all(ln.lstrip().startswith(("- ", "* ")) for ln in lines):
                for ln in lines:
                    doc.add_paragraph(ln.lstrip()[2:], style="List Bullet")
            else:
                doc.add_paragraph(" ".join(ln.strip() for ln in lines))
    doc.save(path)
    return path


def read_docx_text(path: Path) -> str:
    from docx import Document

    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(c.text for c in row.cells))
    return "\n".join(parts)


def write_markdown(path: Path, title: str, sections: list[tuple[str, str]], *, front_note: str | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [f"# {title}", ""]
    if front_note:
        out += [f"> {front_note}", ""]
    for heading, body in sections:
        if heading:
            out += [f"## {heading}", ""]
        out += [body.rstrip(), ""]
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def write_json(path: Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_cell), encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_text_any(path: Path) -> str:
    """Read md/txt/docx (and PDF via documents module) as plain text."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".docx":
        return read_docx_text(p)
    if suf == ".pdf":
        from .documents import extract_pdf_text

        return "\n".join(pg.text for pg in extract_pdf_text(p).pages)
    return p.read_text(encoding="utf-8", errors="replace")


SOURCE_COLUMNS = [
    "source_id", "title", "authors", "year", "venue", "doi", "url", "provider", "access_level",
    "verification_status", "cited_by_count", "query_id", "retrieved_at", "notes",
]


def sources_to_rows(sources: list[SourceRecord]) -> list[dict]:
    return [{k: _cell(getattr(s, k)) for k in SOURCE_COLUMNS} for s in sources]
