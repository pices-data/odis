"""Zenodo record (InvenioRDM JSON) to a schema.org JSON-LD document.

Purpose
    Produce one PICES-controlled JSON-LD description per Zenodo record,
    following the ODIS thematic patterns for Datasets and CreativeWorks:
    stable ``@id`` under the PICES base URL, DOI as ``identifier``
    (PropertyValue), Zenodo landing page as ``url``, DOI URL as ``sameAs``,
    PICES as ``publisher``/``provider``/``sdPublisher``, CC BY 4.0 as
    ``sdLicense`` (the licence of this JSON-LD, not of the record), Zenodo as
    the provider of the deposited files, spatial and temporal coverage, rights
    text as ``usageInfo`` when no licence exists, deposited files as
    ``distribution`` (datasets) or ``subjectOf`` (other works).

Invariants
    * The document is self-contained: the only remote reference in
      ``@context`` is the schema.org vocabulary IRI (no remote context fetch),
      and every embedded Organization node carries name, url and description.
    * Nothing is invented: values come from the Zenodo record or from the
      fixed PICES/Zenodo organisation facts. Text that Zenodo stores as HTML
      is converted to plain text; nothing else is rewritten.
    * ``url`` and ``sameAs`` are single values; ``identifier`` lists the
      version DOI first.
    * Records that are not public, deleted or not the latest version raise
      :class:`SkipRecord` with a reason instead of producing a file.

Assumptions
    * Input is the ``application/vnd.inveniordm.v1+json`` serialization.
    * Each record has one concept id (``parent.id``), used for the file name
      so the ``@id`` survives new versions.
    * Deposited files named ``FGDC-<n>.xml`` are the migrated PICES FGDC
      catalogue records; ``<n>`` is the PICES catalogue identifier.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from .catalog import SD_LICENSE, catalog_ref, jsonld_context, pices_ref, zenodo_ref
from .config import Settings
from .spatial import features_to_place
from .text import html_to_text, one_line

DOI_REGISTRY = "https://registry.identifiers.org/registry/doi"
ORCID_REGISTRY = "https://registry.identifiers.org/registry/orcid"
FGDC_FILE_RE = re.compile(r"^(FGDC-\d+)\.xml$", re.IGNORECASE)
FGDC_PROPERTY_ID = "PICES-FGDC"  # site-specific key: the former PICES FGDC/GeoNetwork catalogue
FGDC_FILE_NOTE = (
    "FGDC CSDGM metadata record deposited with the Zenodo record. Deposited content is "
    "descriptive metadata only; the underlying research data are not included."
)
DESCRIBED_RESOURCE_NOTE = "Online resource that this record describes (from the related identifiers of the Zenodo record)."

# Zenodo resource type id -> schema.org types. The first type is the specific one; a
# plain "CreativeWork" is added so ODIS tooling that targets CreativeWork (and does not
# load the schema.org class hierarchy) still recognises the node.
RESOURCE_TYPES: dict[str, list[str]] = {
    "dataset": ["Dataset"],
    "publication-report": ["Report", "CreativeWork"],
    "publication-technicalnote": ["Report", "CreativeWork"],
    "publication-deliverable": ["Report", "CreativeWork"],
    "publication-article": ["ScholarlyArticle", "CreativeWork"],
    "publication-conferencepaper": ["ScholarlyArticle", "CreativeWork"],
    "publication-preprint": ["ScholarlyArticle", "CreativeWork"],
    "publication-book": ["Book", "CreativeWork"],
    "publication-section": ["Chapter", "CreativeWork"],
    "publication-thesis": ["Thesis", "CreativeWork"],
    "publication-softwaredocumentation": ["TechArticle", "CreativeWork"],
    "image-map": ["Map", "CreativeWork"],
    "image-figure": ["ImageObject", "CreativeWork"],
    "image-plot": ["ImageObject", "CreativeWork"],
    "image-drawing": ["ImageObject", "CreativeWork"],
    "image-diagram": ["ImageObject", "CreativeWork"],
    "image-photo": ["ImageObject", "CreativeWork"],
    "image-other": ["ImageObject", "CreativeWork"],
    "video": ["VideoObject", "CreativeWork"],
    "software": ["SoftwareSourceCode", "CreativeWork"],
    "presentation": ["PresentationDigitalDocument", "CreativeWork"],
    "lesson": ["LearningResource", "CreativeWork"],
    "workflow": ["HowTo", "CreativeWork"],
}
DEFAULT_TYPES = ["CreativeWork"]

# DataCite relation type (lower-cased Zenodo id) -> schema.org property.
# "describes"/"documents" point at the resource this record is metadata for; they
# become a download/encoding node (see _related). Anything unmapped becomes a citation.
RELATION_PROPERTIES: dict[str, str] = {
    "cites": "citation",
    "references": "citation",
    "ispartof": "isPartOf",
    "ispublishedin": "isPartOf",
    "haspart": "hasPart",
    "isidenticalto": "sameAs",
    "isdescribedby": "subjectOf",
    "isdocumentedby": "subjectOf",
    "describes": "__described__",
    "documents": "__described__",
    "isderivedfrom": "isBasedOn",
}
DEFAULT_RELATION_PROPERTY = "citation"
# Identifier schemes that name one resource persistently; a "describes" target with one of
# these is also given as ``about`` (a plain URL, such as a data portal, is not).
PERSISTENT_SCHEMES = {"doi", "handle", "ark"}

# Zenodo language ids (ISO 639-3) -> BCP 47 tags for schema:inLanguage.
LANGUAGE_TAGS = {"eng": "en", "jpn": "ja", "kor": "ko", "rus": "ru", "zho": "zh", "fra": "fr", "spa": "es", "deu": "de"}


class SkipRecord(Exception):
    """The record must not be published; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class MappedRecord:
    record_id: str
    concept_id: str
    filename: str
    url: str
    title: str
    kind: str  # "Dataset" or "CreativeWork"
    updated: str
    doc: dict
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
def map_record(hit: dict, settings: Settings) -> MappedRecord:
    """Transform one InvenioRDM record into a MappedRecord (JSON-LD + facts)."""
    _check_publishable(hit)
    meta = hit.get("metadata", {})
    record_id = str(hit["id"])
    concept_id = str(hit.get("parent", {}).get("id") or record_id)
    notes: list[str] = []

    types = RESOURCE_TYPES.get(_resource_type_id(meta), DEFAULT_TYPES)
    is_dataset = types[0] == "Dataset"
    record_url = settings.record_url(concept_id)
    landing = hit.get("links", {}).get("self_html") or f"{settings.zenodo_html}/records/{record_id}"
    doi = _doi(hit)
    doi_url = f"https://doi.org/{doi}" if doi else None
    files = _file_entries(hit, settings)

    doc: dict = {"@context": jsonld_context(), "@id": record_url, "@type": types[0] if len(types) == 1 else types}
    title = one_line(meta.get("title")) or f"Zenodo record {record_id}"
    doc["name"] = title
    for alt in meta.get("additional_titles") or []:
        value = one_line(alt.get("title"))
        if value and value != title:
            doc.setdefault("alternateName", []).append(value)

    description, abstract, methods = _descriptions(meta)
    if methods and not is_dataset:
        description = f"{description}\n\n{methods}" if description else methods
        methods = ""
    if description:
        doc["description"] = description
    else:
        notes.append("no description")
    if abstract:
        doc["abstract"] = abstract

    doc["url"] = landing
    if doi_url:
        doc["sameAs"] = doi_url
    doc["identifier"] = _identifiers(hit, doi, files, notes)

    keywords = [one_line(s.get("subject")) for s in meta.get("subjects") or [] if one_line(s.get("subject"))]
    if keywords:
        doc["keywords"] = _dedupe(keywords)
    else:
        notes.append("no keywords")

    languages = [LANGUAGE_TAGS.get(lang.get("id", ""), lang.get("id")) for lang in meta.get("languages") or [] if lang.get("id")]
    if languages:
        doc["inLanguage"] = languages[0] if len(languages) == 1 else languages

    creators = [node for node in (_agent(c) for c in meta.get("creators") or []) if node]
    if creators:
        doc["creator"] = creators
    else:
        notes.append("no creators")
    contributors = [node for node in (_agent(c) for c in meta.get("contributors") or []) if node]
    if contributors:
        doc["contributor"] = contributors

    published = _edtf_start(meta.get("publication_date"))
    if published:
        doc["datePublished"] = published
    if hit.get("updated"):
        doc["dateModified"] = hit["updated"]
    if meta.get("version"):
        doc["version"] = one_line(meta["version"])

    doc["publisher"] = pices_ref(settings)
    doc["provider"] = pices_ref(settings)
    doc["sdPublisher"] = pices_ref(settings)
    doc["sdLicense"] = list(SD_LICENSE)
    if is_dataset:
        doc["includedInDataCatalog"] = catalog_ref(settings)
    else:
        doc["isPartOf"] = catalog_ref(settings)

    spatial = features_to_place(((meta.get("locations") or {}).get("features")) or [])
    notes.extend(spatial.notes)
    if spatial.place is not None:
        doc["spatialCoverage"] = spatial.place

    temporal = temporal_coverage(meta.get("dates") or [])
    if temporal:
        doc["temporalCoverage"] = temporal
    else:
        notes.append("no collected dates")

    if methods:
        doc["measurementTechnique"] = methods

    license_values, usage_values = _rights(meta.get("rights") or [])
    if license_values:
        doc["license"] = license_values[0] if len(license_values) == 1 else license_values
    if usage_values:
        doc["usageInfo"] = usage_values[0] if len(usage_values) == 1 else usage_values
    if not license_values and not usage_values:
        notes.append("no rights information")

    downloads = _downloads(hit, files, is_dataset, notes)
    if downloads:
        doc["distribution" if is_dataset else "subjectOf"] = downloads

    for prop, value in _related(meta.get("related_identifiers") or [], is_dataset, notes).items():
        _extend(doc, prop, value)

    citations = [one_line(r.get("reference")) for r in meta.get("references") or [] if one_line(r.get("reference"))]
    if citations:
        _extend(doc, "citation", citations)

    funding = _funding(meta.get("funding") or [])
    if funding:
        doc["funding"] = funding

    return MappedRecord(
        record_id=record_id,
        concept_id=concept_id,
        filename=settings.record_filename(concept_id),
        url=record_url,
        title=title,
        kind="Dataset" if is_dataset else "CreativeWork",
        updated=hit.get("updated") or hit.get("created") or "",
        doc=doc,
        notes=notes,
    )


# ----------------------------------------------------------------------
def _check_publishable(hit: dict) -> None:
    if hit.get("deletion_status", {}).get("is_deleted"):
        raise SkipRecord("deleted")
    if hit.get("is_draft") or not hit.get("is_published", True):
        raise SkipRecord("draft or unpublished")
    if hit.get("access", {}).get("record", "public") != "public":
        raise SkipRecord("record metadata not public")
    versions = hit.get("versions") or {}
    if versions and versions.get("is_latest") is False:
        raise SkipRecord("not the latest version")
    if not hit.get("metadata", {}).get("title"):
        raise SkipRecord("no title")


def _resource_type_id(meta: dict) -> str:
    return str((meta.get("resource_type") or {}).get("id") or "").lower()


def _doi(hit: dict) -> str | None:
    doi = (hit.get("pids") or {}).get("doi", {}).get("identifier")
    return doi or hit.get("metadata", {}).get("doi") or None


def _concept_doi(hit: dict) -> str | None:
    return ((hit.get("parent") or {}).get("pids") or {}).get("doi", {}).get("identifier")


def _descriptions(meta: dict) -> tuple[str, str, str]:
    """(description, abstract, methods) as plain text.

    The Zenodo description plus ``notes``-like additional descriptions form the
    search text. ``abstract`` is kept apart, ``methods`` becomes
    ``measurementTechnique`` for datasets, and ``technical-info`` (catalogue
    provenance boilerplate; its FGDC identifier is carried as an identifier
    instead) is left out of the JSON-LD.
    """
    parts = [html_to_text(meta.get("description"))]
    abstract = ""
    methods = ""
    for extra in meta.get("additional_descriptions") or []:
        text = html_to_text(extra.get("description"))
        if not text:
            continue
        kind = str((extra.get("type") or {}).get("id") or "")
        if kind == "abstract":
            abstract = text if not abstract else f"{abstract}\n\n{text}"
        elif kind == "methods":
            methods = text if not methods else f"{methods}\n\n{text}"
        elif kind == "technical-info":
            continue
        else:
            parts.append(text)
    return "\n\n".join(p for p in parts if p), abstract, methods


def _identifiers(hit: dict, doi: str | None, files: list[tuple[str, dict, str]], notes: list[str]) -> list:
    identifiers: list = []
    if doi:
        identifiers.append(
            {
                "@id": f"https://doi.org/{doi}",
                "@type": "PropertyValue",
                "name": "DOI",
                "propertyID": DOI_REGISTRY,
                "value": doi,
                "url": f"https://doi.org/{doi}",
            }
        )
    else:
        notes.append("no DOI")
    concept_doi = _concept_doi(hit)
    if concept_doi and concept_doi != doi:
        identifiers.append(
            {
                "@id": f"https://doi.org/{concept_doi}",
                "@type": "PropertyValue",
                "name": "Concept DOI (resolves to the latest version)",
                "propertyID": DOI_REGISTRY,
                "value": concept_doi,
                "url": f"https://doi.org/{concept_doi}",
            }
        )
    for key, _entry, content_url in files:
        match = FGDC_FILE_RE.match(key)
        if match:
            identifiers.append(
                {
                    "@type": "PropertyValue",
                    "name": "PICES metadata catalogue identifier (FGDC record)",
                    "propertyID": FGDC_PROPERTY_ID,
                    "value": match.group(1).upper(),
                    "url": content_url,
                }
            )
    for alt in hit.get("metadata", {}).get("identifiers") or []:
        scheme = str(alt.get("scheme") or "").lower()
        value = one_line(alt.get("identifier"))
        if not value:
            continue
        resolvable = resolve_identifier(scheme, value)
        if resolvable and resolvable.startswith("http"):
            identifiers.append(resolvable)
        else:
            identifiers.append(f"{scheme}:{value}" if scheme else value)
    return identifiers


def resolve_identifier(scheme: str, value: str) -> str | None:
    """Best-effort HTTP(S) URL or URN for a (scheme, value) pair; None if unknown."""
    scheme = scheme.lower()
    if scheme == "url":
        return value
    if scheme == "doi":
        return f"https://doi.org/{value.removeprefix('https://doi.org/').removeprefix('doi:')}"
    if scheme == "handle":
        return f"https://hdl.handle.net/{value.removeprefix('https://hdl.handle.net/')}"
    if scheme == "orcid":
        return f"https://orcid.org/{value.removeprefix('https://orcid.org/')}"
    if scheme == "ror":
        return f"https://ror.org/{value.removeprefix('https://ror.org/')}"
    if scheme == "arxiv":
        return f"https://arxiv.org/abs/{value.removeprefix('arXiv:')}"
    if scheme == "pmid":
        return f"https://pubmed.ncbi.nlm.nih.gov/{value}/"
    if scheme == "isbn":
        return f"urn:isbn:{value}"
    if scheme == "issn":
        return f"urn:issn:{value}"
    if scheme in ("urn", "purl"):
        return value
    if scheme == "ark":
        return value if value.startswith("http") else f"https://n2t.net/{value}"
    return None


def _agent(entry: dict) -> dict | None:
    """A Zenodo creator/contributor to a schema.org Person or Organization.

    Contributor roles (contact person, distributor, ...) are not carried: a
    flat ``contributor`` list keeps the graph simple for ODIS queries.
    """
    person = entry.get("person_or_org") or {}
    name = one_line(person.get("name"))
    if not name:
        return None
    if person.get("type") == "organizational":
        node: dict = {"@type": "Organization", "name": name}
    else:
        node = {"@type": "Person", "name": name}
        if person.get("given_name"):
            node["givenName"] = one_line(person["given_name"])
        if person.get("family_name"):
            node["familyName"] = one_line(person["family_name"])
    for ident in person.get("identifiers") or []:
        scheme = str(ident.get("scheme") or "").lower()
        value = one_line(ident.get("identifier"))
        if scheme == "orcid" and value:
            url = resolve_identifier("orcid", value)
            node["@id"] = url
            node["url"] = url
            node["identifier"] = {"@type": "PropertyValue", "name": "ORCID", "propertyID": ORCID_REGISTRY, "value": value, "url": url}
        elif scheme == "ror" and value:
            node["@id"] = resolve_identifier("ror", value)
    affiliations = []
    for aff in entry.get("affiliations") or []:
        aff_name = one_line(aff.get("name"))
        if not aff_name:
            continue
        aff_node = {"@type": "Organization", "name": aff_name}
        if aff.get("id"):
            aff_node["@id"] = resolve_identifier("ror", str(aff["id"]))
        affiliations.append(aff_node)
    if affiliations and node["@type"] == "Person":
        node["affiliation"] = affiliations[0] if len(affiliations) == 1 else affiliations
    return node


# ----------------------------------------------------------------------
def temporal_coverage(dates: list[dict]) -> str | None:
    """ISO 8601 interval (or single date) spanning all ``collected`` dates."""
    starts: list[str] = []
    ends: list[str] = []
    for entry in dates:
        if str((entry.get("type") or {}).get("id") or "").lower() != "collected":
            continue
        raw = one_line(entry.get("date"))
        if not raw:
            continue
        if "/" in raw:
            start, end = (part.strip() for part in raw.split("/", 1))
            end = end or start
        else:
            start = end = raw
        if _edtf_ok(start):
            starts.append(start)
        if _edtf_ok(end):
            ends.append(end)
    if not starts and not ends:
        return None
    start = min(starts, key=_lower_bound) if starts else None
    end = max(ends, key=_upper_bound) if ends else None
    if start and end and start != end:
        return f"{start}/{end}"
    return start or end


def _edtf_ok(value: str) -> bool:
    return re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value) is not None


def _edtf_start(value: str | None) -> str | None:
    if not value:
        return None
    start = str(value).split("/", 1)[0].strip()
    return start if _edtf_ok(start) else None


def _lower_bound(value: str) -> str:
    parts = value.split("-")
    while len(parts) < 3:
        parts.append("01")
    return "-".join(parts)


def _upper_bound(value: str) -> str:
    parts = value.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 12
    day = int(parts[2]) if len(parts) > 2 else calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{day:02d}"


# ----------------------------------------------------------------------
def _rights(rights: list[dict]) -> tuple[list, list]:
    """(licences, usage statements).

    A rights entry with an ``id`` is a licence: emitted as URL(s), the licence
    URL Zenodo gives plus the SPDX URL (ODIS "License as SPDX URL" pattern).
    An entry without ``id`` is free text and becomes a ``usageInfo``
    CreativeWork (ODIS "License as CreativeWork" pattern, under the property
    schema.org reserves for conditions that are not a licence).
    """
    licenses: list = []
    usage: list = []
    for right in rights:
        title = _lang_text(right.get("title"))
        description = _lang_text(right.get("description"))
        props = right.get("props") or {}
        url = props.get("url") or right.get("link")
        if right.get("id"):
            urls = [url] if url else []
            if str(props.get("scheme") or "").lower() == "spdx":
                urls.append(f"https://spdx.org/licenses/{spdx_identifier(str(right['id']))}")
            if urls:
                licenses.extend(urls)
            else:
                node = {"@type": "CreativeWork", "name": title or right["id"]}
                if description:
                    node["text"] = description
                licenses.append(node)
        else:
            node = {"@type": "CreativeWork"}
            if title:
                node["name"] = title
            if description:
                node["text"] = description
            if url:
                node["url"] = url
            if len(node) > 1:
                usage.append(node)
    return licenses, usage


def spdx_identifier(zenodo_id: str) -> str:
    """Zenodo's lower-cased licence id to the SPDX short identifier (CC family)."""
    if zenodo_id.lower().startswith("cc"):
        return zenodo_id.upper()
    return zenodo_id


def _lang_text(value) -> str:
    if isinstance(value, dict):
        return html_to_text(value.get("en") or next(iter(value.values()), ""))
    return html_to_text(value) if isinstance(value, str) else ""


def _file_entries(hit: dict, settings: Settings) -> list[tuple[str, dict, str]]:
    """(key, entry, content URL) for each deposited file, sorted by key."""
    files = hit.get("files") or {}
    if not files.get("enabled") or not files.get("entries"):
        return []
    record_id = hit["id"]
    return [
        (key, files["entries"][key], f"{settings.zenodo_api}/records/{record_id}/files/{quote(key)}/content")
        for key in sorted(files["entries"])
    ]


def _downloads(hit: dict, files: list[tuple[str, dict, str]], is_dataset: bool, notes: list[str]) -> list[dict]:
    """Deposited files as DataDownload (dataset) or MediaObject (other works)."""
    if not files:
        notes.append("no files")
        return []
    access = hit.get("access") or {}
    if access.get("files", "public") != "public" or (access.get("embargo") or {}).get("active"):
        notes.append("files not public; no file nodes emitted")
        return []
    nodes = []
    for key, entry, content_url in files:
        node = {
            "@type": "DataDownload" if is_dataset else "MediaObject",
            "name": key,
            "contentUrl": content_url,
            "encodingFormat": entry.get("mimetype") or "application/octet-stream",
        }
        if FGDC_FILE_RE.match(key):
            node["description"] = FGDC_FILE_NOTE
        if entry.get("size") is not None:
            node["contentSize"] = f"{entry['size']} bytes"
        node["provider"] = zenodo_ref()
        nodes.append(node)
    return nodes


def _related(related: list[dict], is_dataset: bool, notes: list[str]) -> dict[str, list]:
    """Group related identifiers by the schema.org property they map to."""
    grouped: dict[str, list] = {}
    for item in related:
        scheme = str(item.get("scheme") or "").lower()
        value = one_line(item.get("identifier"))
        relation = str((item.get("relation_type") or {}).get("id") or "").lower()
        if not value:
            continue
        prop = RELATION_PROPERTIES.get(relation, DEFAULT_RELATION_PROPERTY)
        if relation not in RELATION_PROPERTIES:
            notes.append(f"relation {relation or 'unknown'} mapped to citation")
        resolvable = resolve_identifier(scheme, value)
        if prop == "sameAs":
            grouped.setdefault(prop, []).append(resolvable or value)
            continue
        if prop == "__described__":
            # The record is metadata for this resource: point at it as a download/encoding.
            if resolvable and resolvable.startswith("http"):
                node = {
                    "@type": "DataDownload" if is_dataset else "MediaObject",
                    "contentUrl": resolvable,
                    "description": DESCRIBED_RESOURCE_NOTE,
                }
                grouped.setdefault("distribution" if is_dataset else "encoding", []).append(node)
                if scheme in PERSISTENT_SCHEMES:
                    # A link-only (Route A) record: name the described resource by its persistent
                    # identifier, so ODIS can join this record to the original repository's record.
                    # sameAs stays the record's own DOI (single value, as the ODIS book advises).
                    # The node is left untyped: typed as Dataset, the ODIS shapes would expect a full
                    # description of a resource this record only points at.
                    grouped.setdefault("about", []).append({
                        "@id": resolvable,
                        "url": resolvable,
                        "identifier": f"{scheme}:{value}",
                    })
            else:
                grouped.setdefault("about", []).append({"@type": "Thing", "identifier": f"{scheme}:{value}" if scheme else value})
            continue
        types = RESOURCE_TYPES.get(str((item.get("resource_type") or {}).get("id") or "").lower(), DEFAULT_TYPES)
        node = {"@type": types[0]}
        if resolvable:
            node["@id"] = resolvable
            if resolvable.startswith("http"):
                node["url"] = resolvable
        node["identifier"] = f"{scheme}:{value}" if scheme and scheme != "url" else value
        grouped.setdefault(prop, []).append(node)
    return grouped


def _funding(funding: list[dict]) -> list[dict]:
    grants = []
    for item in funding:
        funder = item.get("funder") or {}
        award = item.get("award") or {}
        grant: dict = {"@type": "MonetaryGrant"}
        title = _lang_text(award.get("title")) if isinstance(award.get("title"), dict) else one_line(award.get("title"))
        if title:
            grant["name"] = title
        if award.get("number"):
            grant["identifier"] = one_line(award["number"])
        if funder.get("name"):
            funder_node = {"@type": "Organization", "name": one_line(funder["name"])}
            if funder.get("id"):
                funder_node["@id"] = resolve_identifier("ror", str(funder["id"]))
            grant["funder"] = funder_node
        if len(grant) > 1:
            grants.append(grant)
    return grants


def _extend(doc: dict, prop: str, values: list) -> None:
    existing = doc.get(prop)
    if existing is None:
        doc[prop] = values[0] if len(values) == 1 else list(values)
        return
    doc[prop] = (existing if isinstance(existing, list) else [existing]) + list(values)


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
