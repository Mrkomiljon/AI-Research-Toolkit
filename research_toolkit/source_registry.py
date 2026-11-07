"""sources/sources.json registry with DOI/title deduplication and BibTeX export."""
from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path

from . import SCHEMA_VERSION
from .schemas import SourceRecord, VerificationStatus, make_source_id, normalize_doi, normalize_title

TITLE_SIMILARITY_THRESHOLD = 0.92


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(str(o))


class SourceRegistry:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.path = self.workspace / "sources" / "sources.json"
        self.bib_path = self.workspace / "sources" / "references.bib"
        self._sources: dict[str, SourceRecord] = {}
        self.queries: list[dict] = []
        if self.path.exists():
            self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._sources = {s["source_id"]: SourceRecord.model_validate(s) for s in data.get("sources", [])}
        self.queries = data.get("queries", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "sources": [s.model_dump(mode="json") for s in self._sources.values()],
            "queries": self.queries,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8"
        )
        self.bib_path.write_text(to_bibtex(list(self._sources.values())), encoding="utf-8")

    # ---- access ------------------------------------------------------
    def __len__(self) -> int:
        return len(self._sources)

    def all(self) -> list[SourceRecord]:
        return list(self._sources.values())

    def ids(self) -> set[str]:
        return set(self._sources)

    def get(self, source_id: str) -> SourceRecord | None:
        return self._sources.get(source_id)

    def by_doi(self, doi: str) -> SourceRecord | None:
        d = normalize_doi(doi)
        if not d:
            return None
        for s in self._sources.values():
            if s.doi == d:
                return s
        return None

    def find_duplicate(self, candidate: SourceRecord) -> SourceRecord | None:
        """DOI exact match first; otherwise high title similarity with a compatible year."""
        if candidate.doi:
            hit = self.by_doi(candidate.doi)
            if hit:
                return hit
        ct = normalize_title(candidate.title)
        for s in self._sources.values():
            if s.source_id == candidate.source_id:
                return s
            if candidate.doi and s.doi and candidate.doi != s.doi:
                continue  # two different DOIs are two different works, however similar the titles
            st = normalize_title(s.title)
            if ct == st or difflib.SequenceMatcher(None, ct, st).ratio() >= TITLE_SIMILARITY_THRESHOLD:
                if candidate.year is None or s.year is None or abs(candidate.year - s.year) <= 1:
                    return s
        return None

    def add(self, candidate: SourceRecord) -> tuple[SourceRecord, bool]:
        """Insert or merge. Returns (record, created). Merging never downgrades verification/access."""
        existing = self.find_duplicate(candidate)
        if existing is None:
            self._sources[candidate.source_id] = candidate
            return candidate, True
        merged = merge_records(existing, candidate)
        self._sources[existing.source_id] = merged
        return merged, False

    def upsert(self, record: SourceRecord) -> None:
        self._sources[record.source_id] = record

    def remove(self, source_id: str) -> bool:
        return self._sources.pop(source_id, None) is not None

    def record_query(self, query: dict) -> None:
        self.queries.append(query)

    def stats(self) -> dict:
        srcs = list(self._sources.values())
        return {
            "total": len(srcs),
            "verified": sum(1 for s in srcs if s.verification_status == VerificationStatus.VERIFIED),
            "with_doi": sum(1 for s in srcs if s.doi),
            "full_text": sum(1 for s in srcs if s.access_level.value == "FULL_TEXT"),
            "abstract_only": sum(1 for s in srcs if s.access_level.value == "ABSTRACT_ONLY"),
            "metadata_only": sum(1 for s in srcs if s.access_level.value == "METADATA_ONLY"),
        }


_ACCESS_RANK = {"METADATA_ONLY": 0, "ABSTRACT_ONLY": 1, "FULL_TEXT": 2}
_VERIF_RANK = {"failed": 0, "unverified": 1, "mismatch": 1, "partial": 2, "verified": 3}


def merge_records(a: SourceRecord, b: SourceRecord) -> SourceRecord:
    data = a.model_dump()
    for key in ("doi", "year", "abstract", "venue", "url", "pdf_path", "cited_by_count"):
        if data.get(key) in (None, "", []) and getattr(b, key) not in (None, "", []):
            data[key] = getattr(b, key)
    if not data["authors"] and b.authors:
        data["authors"] = b.authors
    data["external_ids"] = {**b.external_ids, **a.external_ids}
    if _ACCESS_RANK[b.access_level.value] > _ACCESS_RANK[a.access_level.value]:
        data["access_level"] = b.access_level
    if _VERIF_RANK[b.verification_status.value] > _VERIF_RANK[a.verification_status.value]:
        data["verification_status"] = b.verification_status
    if a.provider != b.provider:
        note = data.get("notes") or ""
        tag = f"also found via {b.provider}"
        if tag not in note:
            data["notes"] = (note + " " + tag).strip()
    return SourceRecord.model_validate(data)


def new_source(title: str, *, authors=None, year=None, doi=None, **kw) -> SourceRecord:
    doi_n = normalize_doi(doi)
    return SourceRecord(
        source_id=make_source_id(doi_n, title, year),
        title=title,
        authors=authors or [],
        year=year,
        doi=doi_n,
        **kw,
    )


def bib_key(s: SourceRecord) -> str:
    first = s.authors[0].split(",")[0].split()[-1] if s.authors else "anon"
    first = "".join(ch for ch in first if ch.isalnum()).lower() or "anon"
    return f"{first}{s.year or 'nd'}_{s.source_id[-6:]}"


def to_bibtex(sources: list[SourceRecord]) -> str:
    out = ["% Generated by AI Research Toolkit from sources/sources.json - verify before submission\n"]
    for s in sources:
        fields = [f"  title = {{{s.title}}}"]
        if s.authors:
            fields.append("  author = {" + " and ".join(s.authors) + "}")
        if s.year:
            fields.append(f"  year = {{{s.year}}}")
        if s.venue:
            fields.append(f"  journal = {{{s.venue}}}")
        if s.doi:
            fields.append(f"  doi = {{{s.doi}}}")
        if s.url:
            fields.append(f"  url = {{{s.url}}}")
        fields.append(
            f"  note = {{source_id: {s.source_id}; access: {s.access_level.value}; "
            f"verification: {s.verification_status.value}}}"
        )
        out.append(f"@article{{{bib_key(s)},\n" + ",\n".join(fields) + "\n}\n")
    return "\n".join(out)


def parse_bibtex(text: str) -> list[dict]:
    """Minimal BibTeX parser (enough for audits): returns dicts with key, type and fields."""
    entries = []
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        brace = text.find("{", at)
        if brace < 0:
            break
        etype = text[at + 1 : brace].strip().lower()
        depth, j = 1, brace + 1
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[brace + 1 : j - 1]
        i = j
        if etype in ("comment", "preamble", "string"):
            continue
        key, _, rest = body.partition(",")
        fields: dict[str, str] = {}
        for name, value in _iter_fields(rest):
            fields[name.lower()] = value
        entries.append({"key": key.strip(), "type": etype, "fields": fields})
    return entries


def _iter_fields(rest: str):
    k = 0
    n = len(rest)
    while k < n:
        eq = rest.find("=", k)
        if eq < 0:
            break
        name = rest[k:eq].strip().strip(",").strip()
        p = eq + 1
        while p < n and rest[p] in " \t\r\n":
            p += 1
        if p >= n:
            break
        if rest[p] == "{":
            depth, q = 1, p + 1
            while q < n and depth:
                if rest[q] == "{":
                    depth += 1
                elif rest[q] == "}":
                    depth -= 1
                q += 1
            value = rest[p + 1 : q - 1]
            k = q
        elif rest[p] == '"':
            q = rest.find('"', p + 1)
            if q < 0:
                q = n
            value = rest[p + 1 : q]
            k = q + 1
        else:
            q = rest.find(",", p)
            if q < 0:
                q = n
            value = rest[p:q]
            k = q
        if name:
            yield name, " ".join(value.split())
        comma = rest.find(",", k)
        k = comma + 1 if comma >= 0 else n
