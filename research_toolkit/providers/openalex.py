"""OpenAlex API (https://api.openalex.org). Free; add contact e-mail for the polite pool."""
from __future__ import annotations

from ..schemas import AccessLevel, SourceRecord, VerificationStatus, make_source_id, normalize_doi
from .base import ProviderResult, ScholarlyProvider


def _abstract_from_index(idx: dict | None) -> str | None:
    if not idx:
        return None
    positions: list[tuple[int, str]] = []
    for word, locs in idx.items():
        for pos in locs:
            positions.append((pos, word))
    positions.sort()
    return " ".join(w for _, w in positions) or None


def openalex_to_record(item: dict, query_id: str | None = None) -> SourceRecord | None:
    title = item.get("display_name") or item.get("title")
    if not title:
        return None
    doi = normalize_doi(item.get("doi"))
    year = item.get("publication_year")
    abstract = _abstract_from_index(item.get("abstract_inverted_index"))
    authors = []
    for a in item.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    oa = item.get("open_access") or {}
    pdf_url = (item.get("best_oa_location") or {}).get("pdf_url")
    ext = {"openalex": (item.get("id") or "").rsplit("/", 1)[-1]}
    if doi:
        ext["doi"] = doi
    venue = ((item.get("primary_location") or {}).get("source") or {}).get("display_name")
    return SourceRecord(
        source_id=make_source_id(doi, title, year),
        title=" ".join(title.split()),
        authors=authors,
        year=year,
        doi=doi,
        external_ids=ext,
        provider="openalex",
        access_level=AccessLevel.ABSTRACT_ONLY if abstract else AccessLevel.METADATA_ONLY,
        verification_status=VerificationStatus.VERIFIED if doi else VerificationStatus.UNVERIFIED,
        abstract=abstract,
        venue=venue,
        url=pdf_url or (f"https://doi.org/{doi}" if doi else item.get("id")),
        cited_by_count=item.get("cited_by_count"),
        query_id=query_id,
        notes=("open access PDF link available (not downloaded)" if oa.get("is_oa") and pdf_url else None),
    )


class OpenAlexProvider(ScholarlyProvider):
    name = "openalex"
    base_url = "https://api.openalex.org"
    min_interval_s = 0.2

    def search(self, query: str, *, year_from=None, year_to=None, limit: int = 20, query_id: str | None = None) -> ProviderResult:
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        params = {"search": query, "per-page": min(limit, 200), "sort": "relevance_score:desc"}
        if filters:
            params["filter"] = ",".join(filters)
        if self.contact:
            params["mailto"] = self.contact
        data = self._get(f"{self.base_url}/works", params=params)
        records = [r for r in (openalex_to_record(i, query_id) for i in data.get("results", [])) if r]
        return ProviderResult(self.name, query, records, (data.get("meta") or {}).get("count"))

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        d = normalize_doi(doi)
        if not d:
            return None
        params = {"mailto": self.contact} if self.contact else None
        data = self._get(f"{self.base_url}/works/doi:{d}", params=params)
        return openalex_to_record(data) if data else None
