"""Semantic Scholar Graph API. Public tier is rate limited; an API key (optional) raises limits."""
from __future__ import annotations

import os

from ..schemas import AccessLevel, SourceRecord, VerificationStatus, make_source_id, normalize_doi
from .base import ProviderResult, ScholarlyProvider

FIELDS = "title,authors,year,externalIds,abstract,venue,url,citationCount,openAccessPdf"


def s2_to_record(item: dict, query_id: str | None = None) -> SourceRecord | None:
    title = item.get("title")
    if not title:
        return None
    ext_raw = item.get("externalIds") or {}
    doi = normalize_doi(ext_raw.get("DOI"))
    year = item.get("year")
    abstract = item.get("abstract")
    ext = {k.lower(): str(v) for k, v in ext_raw.items()}
    if item.get("paperId"):
        ext["s2"] = item["paperId"]
    pdf = (item.get("openAccessPdf") or {}).get("url")
    return SourceRecord(
        source_id=make_source_id(doi, title, year),
        title=" ".join(title.split()),
        authors=[a.get("name") for a in item.get("authors") or [] if a.get("name")],
        year=year,
        doi=doi,
        external_ids=ext,
        provider="semantic_scholar",
        access_level=AccessLevel.ABSTRACT_ONLY if abstract else AccessLevel.METADATA_ONLY,
        verification_status=VerificationStatus.VERIFIED if doi else VerificationStatus.UNVERIFIED,
        abstract=abstract,
        venue=item.get("venue") or None,
        url=pdf or item.get("url"),
        cited_by_count=item.get("citationCount"),
        query_id=query_id,
        notes="open access PDF link available (not downloaded)" if pdf else None,
    )


class SemanticScholarProvider(ScholarlyProvider):
    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"
    min_interval_s = 1.1  # public limit ~1 req/s

    def __init__(self, *, api_key: str | None = None, **kw):
        super().__init__(**kw)
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None

    def _headers(self) -> dict | None:
        return {"x-api-key": self.api_key} if self.api_key else None

    def search(self, query: str, *, year_from=None, year_to=None, limit: int = 20, query_id: str | None = None) -> ProviderResult:
        params = {"query": query, "limit": min(limit, 100), "fields": FIELDS}
        if year_from or year_to:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        data = self._get(f"{self.base_url}/paper/search", params=params, headers=self._headers())
        records = [r for r in (s2_to_record(i, query_id) for i in data.get("data", [])) if r]
        return ProviderResult(self.name, query, records, data.get("total"))

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        d = normalize_doi(doi)
        if not d:
            return None
        data = self._get(f"{self.base_url}/paper/DOI:{d}", params={"fields": FIELDS}, headers=self._headers())
        return s2_to_record(data) if data else None
