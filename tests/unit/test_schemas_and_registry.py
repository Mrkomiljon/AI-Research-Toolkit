import pytest
from pydantic import ValidationError

from research_toolkit.evidence_store import EvidenceStore
from research_toolkit.schemas import (
    AccessLevel,
    EvidenceRecord,
    SourceRecord,
    VerificationStatus,
    VerifiedBy,
    is_valid_doi_format,
    make_source_id,
    normalize_doi,
    normalize_title,
)
from research_toolkit.source_registry import SourceRegistry, new_source, parse_bibtex, to_bibtex


@pytest.mark.parametrize("raw,expected", [
    ("https://doi.org/10.1038/S41586-020-2649-2", "10.1038/s41586-020-2649-2"),
    ("doi:10.1000/ABC.", "10.1000/abc"),
    ("http://dx.doi.org/10.1000/x/y", "10.1000/x/y"),
    ("", None), (None, None), ("   ", None),
])
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize("doi,ok", [
    ("10.1038/s41586-020-2649-2", True), ("10.1000/abc", True), ("11.1000/abc", False), ("10.12/abc", False),
    ("not a doi", False), (None, False), ("10.1000/", False),
])
def test_doi_format(doi, ok):
    assert is_valid_doi_format(doi) is ok


def test_normalize_title_and_source_id_stability():
    assert normalize_title("  Machine-Learning:  Crop Yield!! ") == "machine learning crop yield"
    a = make_source_id("10.1000/x", "Anything", 2020)
    b = make_source_id("HTTPS://DOI.ORG/10.1000/X", "Other", 1999)
    assert a == b  # DOI dominates
    assert make_source_id(None, "Same Title", 2020) == make_source_id(None, "same title.", 2020)


def test_source_record_validation():
    with pytest.raises(ValidationError):
        SourceRecord(source_id="bad", title="x")
    with pytest.raises(ValidationError):
        SourceRecord(source_id="src-abcdef123456", title="   ")
    with pytest.raises(ValidationError):
        SourceRecord(source_id="src-abcdef123456", title="t", pdf_path="../../etc/passwd")
    with pytest.raises(ValidationError):
        SourceRecord(source_id="src-abcdef123456", title="t", pdf_path="C:\\secret.pdf")
    rec = SourceRecord(source_id="src-abcdef123456", title="t", doi="DOI:10.1000/X", pdf_path="papers\\PDFs\\a.pdf")
    assert rec.doi == "10.1000/x" and rec.pdf_path == "papers/PDFs/a.pdf"


def test_registry_dedup_by_doi_and_title(tmp_path):
    reg = SourceRegistry(tmp_path)
    a, created = reg.add(new_source("Deep learning for wheat yield", year=2022, doi="10.1000/a", provider="openalex"))
    assert created
    b, created = reg.add(new_source("Deep Learning for Wheat Yield.", year=2022, doi=None, provider="crossref",
                                    access_level=AccessLevel.ABSTRACT_ONLY, abstract="abs"))
    assert not created and b.source_id == a.source_id
    assert b.access_level == AccessLevel.ABSTRACT_ONLY and b.abstract == "abs"  # merge upgrades access, keeps DOI
    c, created = reg.add(new_source("Deep learning for wheat yield", year=2010, doi=None))
    assert created  # year too far apart -> different paper
    d, created = reg.add(new_source("Unrelated title", doi="https://doi.org/10.1000/A"))
    assert not created and d.source_id == a.source_id
    assert len(reg) == 2
    reg.save()
    reg2 = SourceRegistry(tmp_path)
    assert len(reg2) == 2 and reg2.bib_path.exists()
    assert "also found via crossref" in (reg2.get(a.source_id).notes or "")


def test_merge_never_downgrades_verification(tmp_path):
    reg = SourceRegistry(tmp_path)
    reg.add(new_source("T", doi="10.1000/v", verification_status=VerificationStatus.VERIFIED))
    merged, _ = reg.add(new_source("T", doi="10.1000/v", verification_status=VerificationStatus.UNVERIFIED))
    assert merged.verification_status == VerificationStatus.VERIFIED


def test_bibtex_roundtrip():
    srcs = [new_source("A title, with comma", authors=["Smith, John", "Doe, Jane"], year=2021, doi="10.1000/b", venue="J {Test}")]
    text = to_bibtex(srcs)
    entries = parse_bibtex(text)
    assert len(entries) == 1
    e = entries[0]
    assert e["fields"]["doi"] == "10.1000/b" and e["fields"]["title"] == "A title, with comma"
    assert e["fields"]["author"] == "Smith, John and Doe, Jane"
    assert e["key"].startswith("smith2021_")


def test_parse_bibtex_quoted_and_bare():
    text = '@article{k1, title = "Quoted", year = 2020, doi = {10.1000/q}}\n@comment{ignored}\n@book{k2, title={Nested {Braces} ok}}'
    entries = parse_bibtex(text)
    assert [e["key"] for e in entries] == ["k1", "k2"]
    assert entries[0]["fields"]["year"] == "2020" and entries[1]["fields"]["title"] == "Nested {Braces} ok"


def test_evidence_store_rules(tmp_path):
    store = EvidenceStore(tmp_path)
    rec = EvidenceRecord(evidence_id="ev-1", source_id="src-abcdef123456", claim="c", locator="p.1",
                         verified_by=VerifiedBy.LLM, verification_status=VerificationStatus.VERIFIED)
    with pytest.raises(ValueError):
        store.append(rec, known_source_ids={"src-other"})
    saved = store.append(rec, known_source_ids={"src-abcdef123456"})
    assert saved.verification_status == VerificationStatus.UNVERIFIED  # LLM cannot self-verify
    store.append(rec, known_source_ids={"src-abcdef123456"})  # idempotent
    assert len(store.all()) == 1
    with pytest.raises(ValidationError):
        EvidenceRecord(evidence_id="ev-2", source_id="src-abcdef123456", claim=" ", locator="p.1")
