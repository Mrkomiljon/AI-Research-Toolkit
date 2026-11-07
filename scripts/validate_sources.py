#!/usr/bin/env python3
"""Validate sources/sources.json of a workspace: schema, DOI format, duplicates, and (optionally) live DOI resolution.

  python scripts/validate_sources.py --project workspace/my-project [--online] [--providers crossref,openalex]
Exit 0 when every record is schema-valid and no DOI is malformed; 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_toolkit.project_manager import ProjectManager  # noqa: E402
from research_toolkit.providers import make_providers  # noqa: E402
from research_toolkit.schemas import SourceRecord, normalize_title  # noqa: E402
from research_toolkit.source_registry import SourceRegistry  # noqa: E402
from research_toolkit.validation import check_doi_format, titles_match  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", "-p", default=".")
    ap.add_argument("--online", action="store_true", help="resolve DOIs against providers")
    ap.add_argument("--providers", default="crossref,openalex")
    a = ap.parse_args()
    pm = ProjectManager.find(Path(a.project))
    raw = json.loads((pm.workspace / "sources" / "sources.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    records: list[SourceRecord] = []
    for item in raw.get("sources", []):
        try:
            records.append(SourceRecord.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"schema: {item.get('source_id')}: {exc}")
    for r in records:
        if r.doi:
            ok, msg = check_doi_format(r.doi)
            if not ok:
                problems.append(f"doi: {r.source_id}: {msg}")
    dois = Counter(r.doi for r in records if r.doi)
    for d, n in dois.items():
        if n > 1:
            problems.append(f"duplicate DOI {d} appears {n} times")
    titles = Counter(normalize_title(r.title) for r in records)
    for t, n in titles.items():
        if n > 1:
            problems.append(f"duplicate normalized title '{t[:60]}' appears {n} times")
    online: list[dict] = []
    if a.online:
        provs = make_providers(tuple(a.providers.split(",")))
        reg = SourceRegistry(pm.workspace)
        for r in records:
            if not r.doi:
                online.append({"source_id": r.source_id, "result": "no DOI"})
                continue
            resolved = None
            for p in provs:
                try:
                    resolved = p.lookup_doi(r.doi)
                    if resolved:
                        break
                except Exception as exc:  # noqa: BLE001
                    online.append({"source_id": r.source_id, "provider": p.name, "error": str(exc)})
            if resolved is None:
                online.append({"source_id": r.source_id, "result": "DOI not resolved"})
                problems.append(f"resolve: {r.source_id}: DOI {r.doi} not found")
            else:
                ok, ratio = titles_match(r.title, resolved.title)
                online.append({"source_id": r.source_id, "result": "match" if ok else "title mismatch", "similarity": ratio})
                if not ok:
                    problems.append(f"mismatch: {r.source_id}: title similarity {ratio}")
        reg.save()
    print(json.dumps({"records": len(records), "problems": problems, "online": online}, indent=2, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
