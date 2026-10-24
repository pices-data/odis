"""Catalogue-level nodes: PICES Organization and the DataCatalog."""

from __future__ import annotations

from conftest import load_community
from pices_odis.catalog import PICES_ROR, data_catalog_node, pices_organization_node, pices_ref, zenodo_ref
from pices_odis.config import Settings


def test_organization_node(settings):
    node = pices_organization_node(settings)
    assert node["@id"] == "https://example.org/odis/organization.jsonld"
    assert node["@type"] == "Organization"
    assert node["name"] == "North Pacific Marine Science Organization"
    ror = node["identifier"][0]
    assert ror["propertyID"] == "https://registry.identifiers.org/registry/ror"
    assert ror["value"] == "0205jhq31" and ror["url"] == PICES_ROR
    assert "@id" not in ror  # the ROR IRI denotes the organisation, not an identifier record
    assert node["sameAs"] == PICES_ROR
    assert node["url"] == "https://meetings.pices.int/"
    assert node["owns"]["@id"] == "https://example.org/odis/catalog.jsonld"
    assert "email" not in node


def test_embedded_refs_satisfy_odis_search_shape_needs(settings):
    for ref in (pices_ref(settings), zenodo_ref()):
        assert ref["@id"].startswith("http")
        assert ref["name"] and ref["url"] and ref["description"]


def test_default_base_url_is_the_github_pages_site(tmp_path, monkeypatch):
    monkeypatch.delenv("PICES_ODIS_BASE_URL", raising=False)
    default = Settings.create(root=tmp_path)
    assert default.base_url == "https://pices-data.github.io/odis/"
    assert default.record_url("7") == "https://pices-data.github.io/odis/records/zenodo-7.jsonld"
    monkeypatch.setenv("PICES_ODIS_BASE_URL", "https://w3id.org/pices/odis")
    switched = Settings.create(root=tmp_path)
    assert switched.base_url == "https://w3id.org/pices/odis/"  # trailing slash normalised
    assert switched.sitemap_url == "https://w3id.org/pices/odis/sitemap.xml"


def test_data_catalog_node(settings):
    node = data_catalog_node(settings, load_community(), date_modified="2026-10-23T23:14:26+00:00")
    assert node["@id"] == "https://example.org/odis/catalog.jsonld"
    assert node["@type"] == "DataCatalog"
    assert node["url"] == "https://zenodo.org/communities/pices/"
    assert node["publisher"]["sameAs"] == PICES_ROR
    assert node["provider"]["@id"] == node["publisher"]["@id"] == "https://example.org/odis/organization.jsonld"
    assert node["dateModified"] == "2026-10-23T23:14:26+00:00"
    assert "Zenodo" in node["description"]
    assert "official data catalogue for data produced by PICES expert groups" in node["description"]
    assert node["identifier"]["value"] == settings.community_id
