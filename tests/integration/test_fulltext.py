"""Open-access full-text fetching with mocked arXiv / Europe PMC / Unpaywall / OpenAlex responses."""
import httpx
import pytest

from research_toolkit import pipelines
from research_toolkit.fulltext import FullTextFetcher, fetch_full_text
from research_toolkit.project_manager import ApprovalRequired
from research_toolkit.schemas import AccessLevel
from research_toolkit.source_registry import SourceRegistry, new_source
from tests.conftest import FULL_TEXT_PAGES, make_pdf


def _pdf_bytes(tmp_path) -> bytes:
    p = make_pdf(tmp_path / "oa.pdf", FULL_TEXT_PAGES)
    return p.read_bytes()


ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2302.03020v2</id>
    <title>RLSbench: Domain Adaptation Under Relaxed Label Shift</title>
    <link title="pdf" href="https://arxiv.org/pdf/2302.03020v2" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/9999.00001v1</id>
    <title>Something completely different about volcanoes</title>
  </entry>
</feed>"""


def make_transport(pdf: bytes, *, openalex_oa=True, epmc_oa=True, unpaywall=True, pdf_ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.openalex.org/works/doi:" in url:
            if not openalex_oa:
                return httpx.Response(200, json={"best_oa_location": None, "locations": []})
            return httpx.Response(200, json={"best_oa_location": {"is_oa": True, "pdf_url": "https://oa.example/paper.pdf", "license": "cc-by", "source": {"display_name": "OA Journal"}}, "locations": []})
        if "export.arxiv.org/api/query" in url:
            return httpx.Response(200, text=ARXIV_ATOM)
        if "webservices/rest/search" in url:
            res = [{"pmcid": "PMC123", "isOpenAccess": "Y", "license": "cc-by"}] if epmc_oa else []
            return httpx.Response(200, json={"resultList": {"result": res}})
        if "/fullTextXML" in url:
            return httpx.Response(200, text='<article><front><article-meta><abstract><p>Abstract text here.</p></abstract></article-meta></front>'
                                           '<body><sec><title>Methods</title><p>We trained a random forest on 2,400 field observations.</p></sec>'
                                           '<sec><title>Results</title><p>The model reached an RMSE of 0.41 t/ha.</p></sec></body></article>')
        if "api.unpaywall.org" in url:
            if not unpaywall:
                return httpx.Response(404)
            return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": "https://unpaywall.example/p.pdf", "license": "cc-by-nc", "host_type": "repository"}, "oa_locations": []})
        if url.endswith(".pdf") or "arxiv.org/pdf" in url or "pdf=render" in url:
            if not pdf_ok:
                return httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"})
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(500, text="unexpected " + url)
    return httpx.MockTransport(handler)


def _fetcher(transport, contact=None):
    f = FullTextFetcher(transport=transport, contact=contact)
    f.min_interval_s = 0
    return f


def test_fetch_downloads_oa_pdf_and_upgrades_access(workspace, tmp_path):
    pdf = _pdf_bytes(tmp_path)
    reg = SourceRegistry(workspace.workspace)
    src = new_source("RLSbench: Domain Adaptation Under Relaxed Label Shift", year=2023, doi="10.1000/oa.1", abstract="abs")
    reg.add(src)
    reg.save()
    res = fetch_full_text(workspace, [src.source_id], fetcher=_fetcher(make_transport(pdf)))
    r = res["results"][0]
    assert r["status"] == "downloaded" and r["provider"] == "openalex" and r["license"] == "cc-by"
    assert (workspace.workspace / "papers" / "PDFs" / f"{src.source_id}.pdf").read_bytes().startswith(b"%PDF")
    rec = SourceRegistry(workspace.workspace).get(src.source_id)
    assert rec.access_level == AccessLevel.FULL_TEXT and rec.pdf_path == f"papers/PDFs/{src.source_id}.pdf"
    assert (workspace.workspace / "literature" / "fulltext-log.json").exists() and res["counts"]["downloaded"] == 1
    # second call: already present, nothing re-downloaded
    res2 = fetch_full_text(workspace, [src.source_id], fetcher=_fetcher(make_transport(pdf)))
    assert res2["results"][0]["status"] == "already_present"
    # analyzer now sees full text with sections
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert prep["access_level"] == "FULL_TEXT" and prep["pages"] == 3 and "methods" in prep["sections_detected"]


def test_fetch_falls_back_to_arxiv_then_europepmc(workspace, tmp_path):
    pdf = _pdf_bytes(tmp_path)
    reg = SourceRegistry(workspace.workspace)
    arx = new_source("RLSbench: Domain Adaptation Under Relaxed Label Shift", year=2023, doi="10.1000/no-oa-on-openalex")
    reg.add(arx)
    reg.save()
    res = fetch_full_text(workspace, [arx.source_id], fetcher=_fetcher(make_transport(pdf, openalex_oa=False)))
    r = res["results"][0]
    assert r["status"] == "downloaded" and r["provider"] == "arxiv" and "2302.03020" in r["url"]
    other = new_source("A paper only on Europe PMC", year=2022, doi="10.1000/epmc")
    reg = SourceRegistry(workspace.workspace)
    reg.add(other)
    reg.save()
    res = fetch_full_text(workspace, [other.source_id], fetcher=_fetcher(make_transport(pdf, openalex_oa=False)))
    assert res["results"][0]["provider"] == "europepmc"


def test_unpaywall_requires_contact_and_paywalled_is_reported(workspace, tmp_path):
    pdf = _pdf_bytes(tmp_path)
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Paywalled study", year=2021, doi="10.1000/paywall")
    reg.add(src)
    reg.save()
    no_contact = _fetcher(make_transport(pdf, openalex_oa=False, epmc_oa=False))
    res = fetch_full_text(workspace, [src.source_id], fetcher=no_contact)
    assert res["results"][0]["status"] == "no_open_access" and res["contact_email_set"] is False
    with_contact = _fetcher(make_transport(pdf, openalex_oa=False, epmc_oa=False), contact="dev@example.org")
    res = fetch_full_text(workspace, [src.source_id], fetcher=with_contact)
    assert res["results"][0]["provider"] == "unpaywall"
    # html instead of pdf -> failed, access stays abstract/metadata
    bad = new_source("Looks open but serves html", year=2020, doi="10.1000/html")
    reg = SourceRegistry(workspace.workspace)
    reg.add(bad)
    reg.save()
    res = fetch_full_text(workspace, [bad.source_id], fetcher=_fetcher(make_transport(pdf, pdf_ok=False, epmc_oa=False)))
    assert res["results"][0]["status"] == "failed" and "not a PDF" in res["results"][0]["error"]
    assert SourceRegistry(workspace.workspace).get(bad.source_id).access_level != AccessLevel.FULL_TEXT


def test_europepmc_xml_fallback_when_pdf_is_html(workspace, tmp_path):
    pdf = _pdf_bytes(tmp_path)
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Open on PMC but publisher serves html", year=2022, doi="10.1000/pmc-xml")
    reg.add(src)
    reg.save()
    res = fetch_full_text(workspace, [src.source_id], fetcher=_fetcher(make_transport(pdf, openalex_oa=False, pdf_ok=False)))
    r = res["results"][0]
    assert r["status"] == "downloaded" and r["provider"] == "europepmc-xml" and r["path"].endswith(".xml")
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert prep["access_level"] == "FULL_TEXT" and "methods" in prep["sections_detected"] and "results" in prep["sections_detected"]
    from research_toolkit.exporters import read_json

    ext = read_json(workspace.workspace / "analysis" / src.source_id / "extracted-text.json")
    assert "RMSE of 0.41" in ext["sections"]["results"]


def test_fetch_respects_privacy_setting(workspace, tmp_path):
    cfg = workspace.load_config()
    cfg.privacy.allow_external_apis = False
    workspace.save_config(cfg)
    with pytest.raises(ApprovalRequired):
        fetch_full_text(workspace, fetcher=_fetcher(make_transport(_pdf_bytes(tmp_path))))


def test_prepare_with_fetch_flag(workspace, tmp_path):
    pdf = _pdf_bytes(tmp_path)
    reg = SourceRegistry(workspace.workspace)
    src = new_source("RLSbench: Domain Adaptation Under Relaxed Label Shift", year=2023, doi="10.1000/oa.2")
    reg.add(src)
    reg.save()
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id, fetch=True, fetcher=_fetcher(make_transport(pdf)))
    assert prep["fetch"]["status"] == "downloaded" and prep["access_level"] == "FULL_TEXT"
