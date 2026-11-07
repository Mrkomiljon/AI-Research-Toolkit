"""Crossref REST API (https://api.crossref.org). Free; polite pool when a contact e-mail is set."""
from __future__ import annotations

from ..schemas import AccessLevel, SourceRecord, VerificationStatus, make_source_id, normalize_doi
from .base import ProviderResult, ScholarlyProvider


def _year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _authors(item: dict) -> list[str]:
    out = []
    for a in item.get("author") or []:
        fam, giv = a.get("family"), a.get("given")
        if fam and giv:
            out.append(f"{fam}, {giv}")
        elif fam or giv or a.get("name"):
            out.append(fam or giv or a.get("name"))
    return out


def crossref_to_record(item: dict, query_id: str | None = None) -> SourceRecord | None:
    titles = item.get("title") or []
    if not titles:
        return None
    title = " ".join(titles[0].split())
    doi = normalize_doi(item.get("DOI"))
    year = _year(item)
    abstract = item.get("abstract")
    return SourceRecord(
        source_id=make_source_id(doi, title, year),
        title=title,
        authors=_authors(item),
        year=year,
        doi=doi,
        external_ids={"crossref": doi} if doi else {},
        provider="crossref",
        access_level=AccessLevel.ABSTRACT_ONLY if abstract else AccessLevel.METADATA_ONLY,
        verification_status=VerificationStatus.VERIFIED if doi else VerificationStatus.UNVERIFIED,
        abstract=abstract,
        venue=(item.get("container-title") or [None])[0],
        url=item.get("URL"),
        cited_by_count=item.get("is-referenced-by-count"),
        query_id=query_id,
    )


class CrossrefProvider(ScholarlyProvider):
    name = "crossref"
    base_url = "https://api.crossref.org"
    min_interval_s = 1.0

    def search(self, query: str, *, year_from=None, year_to=None, limit: int = 20, query_id: str | None = None) -> ProviderResult:
        filters = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}")
        if year_to:
            filters.append(f"until-pub-date:{year_to}")
        params = {"query": query, "rows": min(limit, 100), "select": "DOI,title,author,issued,container-title,URL,is-referenced-by-count,abstract,published-print,published-online"}
        if filters:
            params["filter"] = ",".join(filters)
        if self.contact:
            params["mailto"] = self.contact
        data = self._get(f"{self.base_url}/works", params=params)
        msg = data.get("message") or {}
        records = [r for r in (crossref_to_record(i, query_id) for i in msg.get("items", [])) if r]
        return ProviderResult(self.name, query, records, msg.get("total-results"))

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        d = normalize_doi(doi)
        if not d:
            return None
        data = self._get(f"{self.base_url}/works/{d}")
        msg = data.get("message")
        return crossref_to_record(msg) if msg else None
