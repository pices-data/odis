"""Record mapping: each schema.org property is derived from the right Zenodo field."""

from __future__ import annotations

import copy
import re

import pytest

from conftest import load_hit
from pices_odis.catalog import PICES_ROR
from pices_odis.mapping import DOI_REGISTRY, SkipRecord, map_record, temporal_coverage
from pices_odis.text import html_to_text


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _email_like_values(node) -> list[str]:
    """String values (not keys) that look like e-mail addresses, anywhere in ``node``."""
    found: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_email_like_values(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_email_like_values(value))
    elif isinstance(node, str) and re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", node):
        found.append(node)
    return found


def test_dataset_core_fields(settings):
    hit = load_hit("23606272")
    mapped = map_record(hit, settings)
    doc = mapped.doc

    assert mapped.kind == "Dataset"
    assert doc["@type"] == "Dataset"
    assert doc["@context"]["@vocab"] == "https://schema.org/"
    # Stable PICES-controlled @id built from the concept id, under the base URL.
    assert doc["@id"] == f"https://example.org/odis/records/zenodo-{hit['parent']['id']}.jsonld"
    assert mapped.filename == f"zenodo-{hit['parent']['id']}.jsonld"
    assert doc["name"] == hit["metadata"]["title"]
    # Plain text: the Zenodo <p> markup is gone, the notes paragraph is appended.
    assert "<" not in doc["description"]
    assert doc["description"].startswith("A set of nested")
    assert "Deposited content: descriptive metadata only" in doc["description"]
    assert "Purpose: To investigate residence time" in doc["description"]
    assert "Catalogue record: FGDC metadata" not in doc["description"]  # technical-info stays out
    # Landing page and DOI.
    assert doc["url"] == "https://zenodo.org/records/23606272"
    assert doc["sameAs"] == "https://doi.org/10.5281/zenodo.23606272"
    doi = doc["identifier"][0]
    assert doi["@type"] == "PropertyValue"
    assert doi["propertyID"] == DOI_REGISTRY
    assert doi["value"] == "10.5281/zenodo.23606272"
    assert doi["url"] == "https://doi.org/10.5281/zenodo.23606272"
    concept = doc["identifier"][1]
    assert concept["value"] == "10.5281/zenodo.23606271"
    fgdc = doc["identifier"][2]
    assert fgdc["propertyID"] == "PICES-FGDC" and fgdc["value"] == "FGDC-3851"
    assert fgdc["url"].endswith("/files/FGDC-3851.xml/content")
    # Keywords, people, dates.
    assert doc["keywords"][:2] == ["Oceanography", "Plankton"]
    creator = doc["creator"][0]
    assert creator == {"@type": "Person", "name": "Hermann, Albert J.", "givenName": "Albert J.", "familyName": "Hermann"}
    assert doc["contributor"][0]["@type"] == "Person"
    assert not _email_like_values(doc["creator"] + doc["contributor"])
    assert doc["datePublished"] == "2005-03-21"
    assert doc["dateModified"] == hit["updated"]
    assert doc["temporalCoverage"] == "2001-03-06/2001-09-12"
    # PICES owns publisher, provider and the structured data; the catalogue node is referenced.
    for prop in ("publisher", "provider", "sdPublisher"):
        org = doc[prop]
        assert org["@id"] == "https://example.org/odis/organization.jsonld"
        assert org["sameAs"] == PICES_ROR
        assert org["name"] == "North Pacific Marine Science Organization"
        assert org["url"] and org["description"]
    assert doc["includedInDataCatalog"]["@id"] == "https://example.org/odis/catalog.jsonld"
    assert "isPartOf" not in doc
    # Free-text rights: usageInfo, no license.
    assert "license" not in doc
    usage = doc["usageInfo"]
    assert usage["@type"] == "CreativeWork"
    assert usage["name"].startswith("Use and access constraints")
    assert "Distribution liability" in usage["text"]
    # Deposited FGDC file as a DataDownload hosted by Zenodo.
    download = _as_list(doc["distribution"])[0]
    assert download["@type"] == "DataDownload"
    assert download["contentUrl"] == "https://zenodo.org/api/records/23606272/files/FGDC-3851.xml/content"
    assert download["encodingFormat"] == "text/xml"
    assert download["contentSize"] == "5128 bytes"
    assert download["provider"]["name"] == "Zenodo"
    assert "descriptive metadata only" in download["description"]


def test_report_is_creative_work_with_subject_of(settings):
    doc = map_record(load_hit("23201173"), settings).doc
    assert doc["@type"] == ["Report", "CreativeWork"]
    assert doc["isPartOf"]["@type"] == "DataCatalog"
    assert "includedInDataCatalog" not in doc
    assert "distribution" not in doc
    media = _as_list(doc["subjectOf"])
    assert media[0]["@type"] == "MediaObject"
    assert media[0]["contentUrl"].endswith("/content")
    assert doc["creator"][0]["@type"] == "Organization"


def test_record_without_location_or_dates(settings):
    mapped = map_record(load_hit("23605621"), settings)
    assert "spatialCoverage" not in mapped.doc
    assert "temporalCoverage" not in mapped.doc
    assert "no location" in mapped.notes
    assert "no collected dates" in mapped.notes


def test_licensed_record_with_related_identifiers(settings):
    doc = map_record(load_hit("15046283"), settings).doc
    licenses = _as_list(doc["license"])
    assert "https://creativecommons.org/licenses/by/4.0/legalcode" in licenses
    assert "https://spdx.org/licenses/CC-BY-4.0" in licenses
    assert "usageInfo" not in doc
    assert doc["inLanguage"] == "en"
    assert doc["version"]
    # issupplementto is not a core relation: it becomes a citation node with a typed target.
    citations = _as_list(doc["citation"])
    handle = next(c for c in citations if c.get("identifier") == "handle:1834/41140")
    assert handle["@id"] == "https://hdl.handle.net/1834/41140"
    assert handle["url"] == handle["@id"]
    assert handle["@type"] == "Report"
    isbn = next(c for c in citations if c.get("identifier", "").startswith("isbn:"))
    assert isbn["@id"].startswith("urn:isbn:") and "url" not in isbn
    # ORCID (on a creator here): IRI @id, url and an identifier PropertyValue.
    orcid = next(c for c in doc["creator"] + doc["contributor"] if "orcid.org" in c.get("@id", ""))
    assert orcid["@id"] == orcid["url"] == "https://orcid.org/0000-0002-2805-6546"
    assert orcid["identifier"]["propertyID"].endswith("/orcid")
    assert orcid["affiliation"]["name"] == "University of Tokyo"
    # Non-FGDC files: no FGDC identifier, no FGDC note.
    assert all(i.get("propertyID") != "PICES-FGDC" for i in doc["identifier"])
    downloads = _as_list(doc["distribution"])
    assert len(downloads) == 3 and all("description" not in d for d in downloads)
    assert doc["funding"][0]["@type"] == "MonetaryGrant"


def test_restricted_files_emit_no_file_nodes(settings):
    mapped = map_record(load_hit("17317855"), settings)
    assert "distribution" not in mapped.doc and "subjectOf" not in mapped.doc
    assert "no files" in mapped.notes


def test_missing_description_falls_back_to_notes(settings):
    hit = load_hit("17317857")
    assert not hit["metadata"].get("description")
    doc = map_record(hit, settings).doc
    assert doc["description"] == "To report distribution of dissolved LMW hydrocarbons in Bristol Bay, Alaska."


def test_two_fgdc_files_give_two_identifiers_and_two_file_nodes(settings):
    doc = map_record(load_hit("23571296"), settings).doc
    fgdc = [i for i in doc["identifier"] if i.get("propertyID") == "PICES-FGDC"]
    assert sorted(i["value"] for i in fgdc) == ["FGDC-2953", "FGDC-3181"]
    files = _as_list(doc.get("distribution") or doc.get("subjectOf"))
    assert sorted(f["name"] for f in files) == ["FGDC-2953.xml", "FGDC-3181.xml"]


def test_describes_relation_becomes_a_download(settings):
    doc = map_record(load_hit("23570900"), settings).doc
    downloads = _as_list(doc["distribution"])
    portal = next(d for d in downloads if d["contentUrl"] == "http://near-goos.coi.gov.cn/")
    assert portal["@type"] == "DataDownload"
    assert "describes" in portal["description"]
    assert "about" not in doc


@pytest.mark.parametrize(
    "mutation, reason",
    [
        (lambda h: h["deletion_status"].update(is_deleted=True), "deleted"),
        (lambda h: h["access"].update(record="restricted"), "record metadata not public"),
        (lambda h: h["versions"].update(is_latest=False), "not the latest version"),
        (lambda h: h.update(is_draft=True), "draft or unpublished"),
    ],
)
def test_skip_rules(settings, mutation, reason):
    hit = copy.deepcopy(load_hit("23606272"))
    mutation(hit)
    with pytest.raises(SkipRecord) as excinfo:
        map_record(hit, settings)
    assert excinfo.value.reason == reason


def test_temporal_coverage_envelopes_collected_dates():
    collected = {"id": "collected"}
    assert temporal_coverage([]) is None
    assert temporal_coverage([{"date": "1988-08-04", "type": collected}]) == "1988-08-04"
    assert temporal_coverage([{"date": "2001-03-06/2001-09-12", "type": collected}]) == "2001-03-06/2001-09-12"
    # Two collected dates: earliest start to latest end, mixed precision handled.
    assert temporal_coverage(
        [{"date": "2001-03-06/2001-09-12", "type": collected}, {"date": "1999", "type": collected}]
    ) == "1999/2001-09-12"
    # A year envelops a sub-interval of the same year.
    assert temporal_coverage([{"date": "2001-03-06/2001-09-12", "type": collected}, {"date": "2001", "type": collected}]) == "2001"
    # Other date types are ignored.
    assert temporal_coverage([{"date": "2017-08", "type": {"id": "available"}}]) is None


def test_html_to_text():
    assert html_to_text("<p>One &amp; two</p><p>Three<br>four</p>") == "One & two\n\nThree\n\nfour"
    assert html_to_text("plain   text\n\n\nsecond") == "plain text\n\nsecond"
    assert html_to_text(None) == ""
    assert html_to_text("<ul><li>a</li><li>b</li></ul>") == "- a\n\n- b"
