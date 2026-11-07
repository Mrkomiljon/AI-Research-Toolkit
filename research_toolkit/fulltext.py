"""Open-access full-text retrieval: arXiv, Europe PMC, Unpaywall, OpenAlex OA locations.

Only open-access copies are fetched (no paywall circumvention, no institutional logins). Every attempt is logged
in literature/fulltext-log.json so the provenance of each PDF is traceable.
"""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .exporters import write_json
from .project_manager import ApprovalRequired, ProjectManager
from .providers.base import ExternalAccessDisabled, external_apis_allowed
from .schemas import AccessLevel, SourceRecord, ValidationStatus, normalize_doi, utcnow
from .source_registry import SourceRegistry
from .validation import titles_match

MAX_PDF_BYTES = 60 * 1024 * 1024
ARXIV_API = "https://export.arxiv.org/api/query"
EUROPEPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
OPENALEX_API = "https://api.openalex.org"
DEFAULT_ORDER = ("openalex", "arxiv", "europepmc", "unpaywall")
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Candidate:
    provider: str
    url: str
    license: str | None = None
    note: str | None = None


@dataclass
class FetchResult:
    source_id: str
    status: str  # downloaded | already_present | no_open_access | failed | skipped
    provider: str | None = None
    url: str | None = None
    path: str | None = None
    bytes: int = 0
    license: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class FullTextFetcher:
    def __init__(self, *, transport: httpx.BaseTransport | None = None, contact: str | None = None, timeout: float = 60.0, min_interval_s: float = 1.0):
        self.contact = contact or os.environ.get("RTK_CONTACT_EMAIL") or None
        ua = "ai-research-toolkit/1.3 (https://github.com/Mrkomiljon/AI-Research-Toolkit" + (f"; mailto:{self.contact})" if self.contact else ")")
        self._client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True, headers={"User-Agent": ua})
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        if not external_apis_allowed():
            raise ExternalAccessDisabled("RTK_ALLOW_EXTERNAL_APIS=0: outbound calls are disabled")
        self._throttle()
        return self._client.get(url, params=params)

    # ---- candidate discovery -----------------------------------------------------------------
    def openalex_candidates(self, src: SourceRecord) -> list[Candidate]:
        if not src.doi:
            return []
        try:
            r = self._get(f"{OPENALEX_API}/works/doi:{src.doi}", params={"mailto": self.contact} if self.contact else None)
        except httpx.HTTPError as exc:
            return [Candidate("openalex", "", note=f"error: {exc}")]
        if r.status_code != 200:
            return []
        data = r.json()
        out: list[Candidate] = []
        seen: set[str] = set()
        for loc in [data.get("best_oa_location")] + (data.get("locations") or []):
            if not loc:
                continue
            url = loc.get("pdf_url")
            if url and loc.get("is_oa") and url not in seen:
                seen.add(url)
                out.append(Candidate("openalex", url, license=loc.get("license"), note=(loc.get("source") or {}).get("display_name")))
        return out

    def arxiv_candidates(self, src: SourceRecord) -> list[Candidate]:
        arxiv_id = None
        if src.doi and src.doi.startswith("10.48550/arxiv."):
            arxiv_id = src.doi.split("arxiv.", 1)[1]
        for key in ("arxiv", "arXiv"):
            if src.external_ids.get(key):
                arxiv_id = src.external_ids[key]
        if arxiv_id:
            return [Candidate("arxiv", f"https://arxiv.org/pdf/{arxiv_id}", license="arXiv (open access)", note=arxiv_id)]
        # title search (arXiv has no DOI index for journal DOIs)
        q = re.sub(r"[^A-Za-z0-9 ]+", " ", src.title)
        q = " ".join(q.split()[:12])
        try:
            r = self._get(ARXIV_API, params={"search_query": f'ti:"{q}"', "max_results": 5})
        except httpx.HTTPError as exc:
            return [Candidate("arxiv", "", note=f"error: {exc}")]
        if r.status_code != 200:
            return []
        out: list[Candidate] = []
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            return []
        for entry in root.findall(f"{ATOM}entry"):
            title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
            ok, ratio = titles_match(src.title, title, threshold=0.9)
            if not ok:
                continue
            ident = (entry.findtext(f"{ATOM}id") or "").rsplit("/abs/", 1)[-1]
            pdf = next((ln.get("href") for ln in entry.findall(f"{ATOM}link") if ln.get("title") == "pdf"), None) or f"https://arxiv.org/pdf/{ident}"
            out.append(Candidate("arxiv", pdf, license="arXiv (open access)", note=f"title match {ratio}; {ident}"))
        return out

    def europepmc_candidates(self, src: SourceRecord) -> list[Candidate]:
        if not src.doi:
            return []
        try:
            r = self._get(f"{EUROPEPMC_API}/search", params={"query": f'DOI:"{src.doi}"', "format": "json", "resultType": "lite"})
        except httpx.HTTPError as exc:
            return [Candidate("europepmc", "", note=f"error: {exc}")]
        if r.status_code != 200:
            return []
        out: list[Candidate] = []
        for item in (r.json().get("resultList") or {}).get("result") or []:
            pmcid = item.get("pmcid")
            if pmcid and item.get("isOpenAccess") == "Y":
                out.append(Candidate("europepmc", f"https://europepmc.org/articles/{pmcid}?pdf=render", license=item.get("license"), note=pmcid))
        return out

    def unpaywall_candidates(self, src: SourceRecord) -> list[Candidate]:
        if not src.doi or not self.contact:
            return [] if src.doi else []
        try:
            r = self._get(f"{UNPAYWALL_API}/{src.doi}", params={"email": self.contact})
        except httpx.HTTPError as exc:
            return [Candidate("unpaywall", "", note=f"error: {exc}")]
        if r.status_code != 200:
            return []
        data = r.json()
        out: list[Candidate] = []
        for loc in [data.get("best_oa_location")] + (data.get("oa_locations") or []):
            if loc and loc.get("url_for_pdf"):
                out.append(Candidate("unpaywall", loc["url_for_pdf"], license=loc.get("license"), note=loc.get("host_type")))
        return out

    def europepmc_xml(self, src: SourceRecord, dest: Path) -> tuple[bool, str, str | None]:
        """Fallback: Europe PMC full-text JATS XML for open-access PMC articles (no PDF needed)."""
        if not src.doi:
            return False, "no DOI", None
        try:
            r = self._get(f"{EUROPEPMC_API}/search", params={"query": f'DOI:"{src.doi}"', "format": "json", "resultType": "lite"})
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}", None
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}", None
        items = (r.json().get("resultList") or {}).get("result") or []
        pmcid = next((i.get("pmcid") for i in items if i.get("pmcid") and i.get("isOpenAccess") == "Y"), None)
        if not pmcid:
            return False, "no open-access PMC record", None
        try:
            x = self._get(f"{EUROPEPMC_API}/{pmcid}/fullTextXML")
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}", None
        if x.status_code != 200 or not x.text.lstrip().startswith("<"):
            return False, f"fullTextXML HTTP {x.status_code}", None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(x.text, encoding="utf-8")
        return True, f"{len(x.text)} chars", pmcid

    def candidates(self, src: SourceRecord, order: tuple[str, ...] = DEFAULT_ORDER) -> list[Candidate]:
        finders = {"openalex": self.openalex_candidates, "arxiv": self.arxiv_candidates, "europepmc": self.europepmc_candidates, "unpaywall": self.unpaywall_candidates}
        out: list[Candidate] = []
        seen: set[str] = set()
        for name in order:
            for c in finders[name](src):
                if c.url and c.url not in seen:
                    seen.add(c.url)
                    out.append(c)
                elif not c.url:
                    out.append(c)  # error note
        return out

    # ---- download ---------------------------------------------------------------------------
    def download_pdf(self, url: str, dest: Path) -> tuple[bool, str]:
        try:
            r = self._get(url)
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        body = r.content
        if not body.startswith(b"%PDF"):
            return False, f"not a PDF (content-type {r.headers.get('content-type', '?')})"
        if len(body) > MAX_PDF_BYTES:
            return False, f"PDF too large ({len(body)} bytes)"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return True, f"{len(body)} bytes"


def fetch_full_text(
    pm: ProjectManager,
    source_ids: list[str] | None = None,
    *,
    fetcher: FullTextFetcher | None = None,
    order: tuple[str, ...] = DEFAULT_ORDER,
    limit: int | None = None,
    overwrite: bool = False,
    run_id: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    """Try to obtain an open-access PDF for each source; attach it to the registry and log every attempt."""
    cfg = pm.load_config()
    if not cfg.privacy.allow_external_apis:
        raise ApprovalRequired("privacy.allow_external_apis is false; full-text fetching needs explicit user approval")
    registry = SourceRegistry(pm.workspace)
    targets = [registry.get(s) for s in source_ids] if source_ids else registry.all()
    targets = [t for t in targets if t is not None]
    if limit:
        targets = targets[:limit]
    own = fetcher is None
    fetcher = fetcher or FullTextFetcher()
    results: list[FetchResult] = []
    try:
        for src in targets:
            dest_rel = f"papers/PDFs/{src.source_id}.pdf"
            dest = pm.workspace / dest_rel
            existing = pm.workspace / src.pdf_path if src.pdf_path else None
            if not overwrite and ((existing and existing.exists()) or dest.exists()):
                if not src.pdf_path:
                    src.pdf_path = dest_rel
                    registry.upsert(src)
                results.append(FetchResult(src.source_id, "already_present", path=src.pdf_path))
                continue
            cands = fetcher.candidates(src, order)
            res = FetchResult(src.source_id, "no_open_access", candidates=[asdict(c) for c in cands])
            for c in cands:
                if not c.url:
                    continue
                ok, msg = fetcher.download_pdf(c.url, dest)
                if ok:
                    res.status, res.provider, res.url, res.path, res.license = "downloaded", c.provider, c.url, dest_rel, c.license
                    res.bytes = dest.stat().st_size
                    src.pdf_path = dest_rel
                    src.access_level = AccessLevel.FULL_TEXT
                    note = f"full text fetched from {c.provider} ({c.license or 'license unknown'})"
                    src.notes = (src.notes + "; " if src.notes else "") + note
                    registry.upsert(src)
                    pm.register_artifact(dest, artifact_type="paper.pdf", skill="literature-search", run_id=run_id, step_id=step_id,
                                         source_ids=[src.source_id], validation_status=ValidationStatus.VALID, notes=f"{c.provider}: {c.url}")
                    break
                res.error = (res.error + " | " if res.error else "") + f"{c.provider}: {msg}"
            if res.status != "downloaded" and "europepmc" in order:
                xml_rel = f"papers/fulltext/{src.source_id}.xml"
                ok, msg, pmcid = fetcher.europepmc_xml(src, pm.workspace / xml_rel)
                if ok:
                    res.status, res.provider, res.url, res.path, res.license = "downloaded", "europepmc-xml", f"{EUROPEPMC_API}/{pmcid}/fullTextXML", xml_rel, "PMC open access"
                    res.bytes = (pm.workspace / xml_rel).stat().st_size
                    src.pdf_path = xml_rel
                    src.access_level = AccessLevel.FULL_TEXT
                    src.notes = (src.notes + "; " if src.notes else "") + f"full text (JATS XML) fetched from Europe PMC {pmcid}"
                    registry.upsert(src)
                    pm.register_artifact(pm.workspace / xml_rel, artifact_type="paper.xml", skill="literature-search", run_id=run_id, step_id=step_id,
                                         source_ids=[src.source_id], validation_status=ValidationStatus.VALID, notes=f"europepmc: {pmcid}")
                else:
                    res.error = (res.error + " | " if res.error else "") + f"europepmc-xml: {msg}"
            if res.status != "downloaded" and any(c.url for c in cands):
                res.status = "failed"
            results.append(res)
    finally:
        if own:
            fetcher.close()
    registry.save()
    summary = {
        "fetched_at": utcnow().isoformat(),
        "order": list(order),
        "contact_email_set": bool(fetcher.contact),
        "note": "Only open-access locations are used. Unpaywall is skipped unless RTK_CONTACT_EMAIL is set (its API requires an e-mail).",
        "counts": {k: sum(1 for r in results if r.status == k) for k in ("downloaded", "already_present", "no_open_access", "failed")},
        "results": [asdict(r) for r in results],
    }
    log_path = write_json(pm.workspace / "literature" / "fulltext-log.json", summary)
    pm.register_artifact(log_path, skill="literature-search", run_id=run_id, step_id=step_id, validation_status=ValidationStatus.VALID)
    summary["log"] = str(log_path)
    return summary


__all__ = ["FullTextFetcher", "fetch_full_text", "FetchResult", "Candidate", "DEFAULT_ORDER", "normalize_doi"]
