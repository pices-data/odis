"""Catalogue-level nodes: PICES as an Organization, the PICES Data Catalogue, Zenodo.

Purpose
    Provide the PICES-controlled identity nodes that every record references
    (``publisher``, ``provider``, ``sdPublisher``, ``includedInDataCatalog``)
    and the two stand-alone JSON-LD files (``organization.jsonld`` and
    ``catalog.jsonld``) listed in the sitemap.

Invariants
    * The PICES node's ``@id`` is under the PICES base URL (so it resolves to
      PICES-controlled JSON-LD); the ROR IRI is carried as ``identifier`` and
      ``sameAs``, following the ODIS institution pattern.
    * Inline references embedded in records carry name, url and description,
      which the ODIS search shape requires on every Organization node.
    * Zenodo is described honestly as the host of the records and the minter
      of the DOIs; DataCite lists "Zenodo" as publisher of each record.
    * The licence of the JSON-LD itself (CC BY 4.0, :data:`SD_LICENSE`) is
      stated with ``sdLicense``, never with ``license``: a record's
      ``license`` describes the described resource, not PICES's description.

Assumptions
    * Organisation facts (ROR 0205jhq31, GRID, ISNI, website) come from the
      Zenodo community record and ROR; they are stable.
"""

from __future__ import annotations

from .config import Settings
from .spatial import GEOSPARQL
from .text import html_to_text

PICES_ROR = "https://ror.org/0205jhq31"
PICES_ROR_ID = "0205jhq31"
PICES_GRID = "grid.448486.2"
PICES_ISNI = "0000 0000 9022 3718"
PICES_NAME = "North Pacific Marine Science Organization"
PICES_ALT_NAME = "PICES"
PICES_URL = "https://meetings.pices.int/"
PICES_DESCRIPTION = (
    "The North Pacific Marine Science Organization (PICES) is an intergovernmental "
    "scientific organization established in 1992 to promote and coordinate marine "
    "research in the northern North Pacific and adjacent seas. Its members are Canada, "
    "Japan, the People's Republic of China, the Republic of Korea, the Russian "
    "Federation and the United States of America."
)
PICES_SHORT_DESCRIPTION = (
    "Intergovernmental marine science organization for the northern North Pacific "
    "(Canada, China, Japan, Korea, Russia, USA); publisher and provider of the PICES Data Catalogue."
)

# Licence decision (2026-10-24): PICES publishes the JSON-LD descriptions in docs/ under
# CC BY 4.0 (LICENSE-DATA). Creative Commons URL plus SPDX URL, as in the ODIS book's
# licence pattern, so harvesters can look the licence up either way.
SD_LICENSE = ["https://creativecommons.org/licenses/by/4.0/", "https://spdx.org/licenses/CC-BY-4.0"]

ZENODO_ID = "https://zenodo.org/"
ZENODO_DESCRIPTION = (
    "General-purpose open research repository operated by CERN and OpenAIRE. "
    "Zenodo hosts the PICES Data Catalogue as a community, stores the deposited files "
    "and mints the records' DOIs; DataCite lists Zenodo as the publisher of each record."
)

CATALOG_NAME = "PICES Data Catalogue"
CATALOG_DESCRIPTION = (
    "The data catalogue of the North Pacific Marine Science Organization (PICES): "
    "descriptive metadata records for datasets and reports produced by PICES expert "
    "groups and their member-country partners, migrated from the former PICES FGDC "
    "metadata catalogue. The catalogue is hosted as a community on Zenodo, which stores "
    "the records and mints their DOIs; this JSON-LD description is published by PICES "
    "for the IOC Ocean Data and Information System (ODIS)."
)


def jsonld_context() -> dict:
    """The context shared by every file: schema.org vocabulary + GeoSPARQL prefix."""
    return {"@vocab": "https://schema.org/", "geosparql": GEOSPARQL}


# ----------------------------------------------------------------------
def pices_ref(settings: Settings) -> dict:
    """Compact PICES node embedded in each record (satisfies the ODIS search shape)."""
    return {
        "@id": settings.organization_url,
        "@type": "Organization",
        "name": PICES_NAME,
        "alternateName": PICES_ALT_NAME,
        "url": PICES_URL,
        "description": PICES_SHORT_DESCRIPTION,
        "sameAs": PICES_ROR,
    }


def zenodo_ref() -> dict:
    """Compact Zenodo node used as provider of each DataDownload."""
    return {
        "@id": ZENODO_ID,
        "@type": "Organization",
        "name": "Zenodo",
        "url": ZENODO_ID,
        "description": ZENODO_DESCRIPTION,
    }


def catalog_ref(settings: Settings) -> dict:
    """Compact DataCatalog node embedded in each record."""
    return {
        "@id": settings.catalog_url,
        "@type": "DataCatalog",
        "name": CATALOG_NAME,
        "url": settings.community_html_url,
    }


# ----------------------------------------------------------------------
def pices_organization_node(settings: Settings) -> dict:
    """Full PICES Organization document (organization.jsonld)."""
    return {
        "@context": jsonld_context(),
        "@id": settings.organization_url,
        "@type": "Organization",
        "name": PICES_NAME,
        "alternateName": PICES_ALT_NAME,
        "legalName": PICES_NAME,
        "description": PICES_DESCRIPTION,
        "url": PICES_URL,
        "foundingDate": "1992",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Sidney",
            "addressRegion": "British Columbia",
            "addressCountry": "CA",
        },
        # Identifier nodes carry no "@id": the ROR IRI denotes the organisation itself
        # (it is used as sameAs and as the @id of affiliations), not an identifier record.
        "identifier": [
            {
                "@type": "PropertyValue",
                "name": "ROR",
                "propertyID": "https://registry.identifiers.org/registry/ror",
                "value": PICES_ROR_ID,
                "url": PICES_ROR,
            },
            {
                "@type": "PropertyValue",
                "name": "GRID",
                "propertyID": "https://registry.identifiers.org/registry/grid",
                "value": PICES_GRID,
                "url": f"https://www.grid.ac/institutes/{PICES_GRID}",
            },
            {
                "@type": "PropertyValue",
                "name": "ISNI",
                "propertyID": "https://registry.identifiers.org/registry/isni",
                "value": PICES_ISNI,
                "url": "https://isni.org/isni/" + PICES_ISNI.replace(" ", ""),
            },
        ],
        "sameAs": PICES_ROR,
        "owns": {"@id": settings.catalog_url, "@type": "DataCatalog", "name": CATALOG_NAME},
    }


def data_catalog_node(settings: Settings, community: dict | None, *, date_modified: str | None = None) -> dict:
    """Full DataCatalog document (catalog.jsonld)."""
    meta = (community or {}).get("metadata", {}) if community else {}
    community_title = meta.get("title") or "PICES - North Pacific Marine Science Organization"
    community_description = html_to_text(meta.get("description") or "")
    description = CATALOG_DESCRIPTION
    if community_description:
        description = f"{description}\n\nZenodo community description: {community_description}"
    node: dict = {
        "@context": jsonld_context(),
        "@id": settings.catalog_url,
        "@type": "DataCatalog",
        "name": CATALOG_NAME,
        "alternateName": community_title,
        "description": description,
        "url": settings.community_html_url,
        "sameAs": settings.community_url,
        "inLanguage": "en",
        "publisher": pices_ref(settings),
        "provider": pices_ref(settings),
        "sdPublisher": pices_ref(settings),
        "sdLicense": list(SD_LICENSE),
        "keywords": ["North Pacific", "marine science", "PICES", "metadata catalogue", "FGDC"],
        "spatialCoverage": {
            "@type": "Place",
            "name": "North Pacific Ocean and adjacent seas",
        },
        "identifier": {
            "@type": "PropertyValue",
            "name": "Zenodo community identifier",
            "propertyID": "https://zenodo.org/api/communities",
            "value": settings.community_id,
            "url": settings.community_url,
        },
    }
    if date_modified:
        node["dateModified"] = date_modified
    return node
