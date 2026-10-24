"""Build step: snapshot -> JSON-LD directory, catalogue nodes, index page, sitemap.

Purpose
    Orchestrate the transformation of every snapshot record into the
    publishable directory (``docs/`` by default) and write a build summary
    (``reports/build-summary.json``) that counts what was built, what was
    skipped and why, and which mapping notes occurred.

Invariants
    * Record files are written as ``records/zenodo-<concept id>.jsonld`` with
      stable key order and a trailing newline; a rebuild from the same
      snapshot is byte-identical.
    * Record files that no longer correspond to a snapshot record are removed,
      so the directory never lists records that left the community.
    * The sitemap is derived from the files on disk (``@id`` and
      ``dateModified``), so ``pices-odis sitemap`` can run on its own.

Assumptions
    * The snapshot is complete unless the caller allows an incomplete one.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .catalog import data_catalog_node, pices_organization_node
from .config import Settings
from .mapping import MappedRecord, SkipRecord, map_record
from .pages import render_index
from .sitemap import SitemapEntry, normalise_lastmod, write_sitemap
from .zenodo import MANIFEST_FILE, Manifest, load_community, load_snapshot

BUILD_SUMMARY_FILE = "build-summary.json"


@dataclass
class BuildSummary:
    built: int = 0
    datasets: int = 0
    creative_works: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    notes: dict[str, int] = field(default_factory=dict)
    removed_stale_files: int = 0
    snapshot_fetched_at: str | None = None
    built_at: str | None = None
    base_url: str = ""
    site_dir: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"


def dump_jsonld(doc: dict) -> str:
    """Canonical serialization for every file we publish."""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ----------------------------------------------------------------------
def build_site(
    settings: Settings,
    *,
    limit: int | None = None,
    allow_incomplete: bool = False,
    log: Callable[[str], None] = print,
) -> BuildSummary:
    hits = load_snapshot(settings, allow_incomplete=allow_incomplete)
    if limit is not None:
        hits = hits[:limit]
    community = load_community(settings)
    manifest = _manifest(settings)

    site_dir = settings.site_dir
    assert site_dir is not None
    records_dir = settings.records_dir
    records_dir.mkdir(parents=True, exist_ok=True)

    summary = BuildSummary(
        snapshot_fetched_at=manifest.fetched_at if manifest else None,
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        base_url=settings.base_url,
        site_dir=str(site_dir),
    )
    skip_reasons: Counter[str] = Counter()
    notes: Counter[str] = Counter()
    written: set[Path] = set()
    index_rows: list[dict] = []
    latest_updated = ""

    for hit in hits:
        try:
            mapped = map_record(hit, settings)
        except SkipRecord as skip:
            skip_reasons[skip.reason] += 1
            log(f"skip {hit.get('id')}: {skip.reason}")
            continue
        path = records_dir / mapped.filename
        path.write_text(dump_jsonld(mapped.doc), encoding="utf-8")
        written.add(path)
        notes.update(mapped.notes)
        summary.built += 1
        if mapped.kind == "Dataset":
            summary.datasets += 1
        else:
            summary.creative_works += 1
        latest_updated = max(latest_updated, mapped.updated)
        index_rows.append(
            {
                "title": mapped.title,
                "href": f"{settings.records_dir_name}/{mapped.filename}",
                "kind": "Dataset" if mapped.kind == "Dataset" else _kind_label(mapped),
                "zenodo": mapped.doc.get("url", ""),
                "record_id": mapped.record_id,
            }
        )

    # Remove record files that are no longer part of the snapshot (only our own pattern).
    if limit is None:
        for stale in records_dir.glob(f"{settings.record_file_prefix}*.jsonld"):
            if stale not in written:
                stale.unlink()
                summary.removed_stale_files += 1

    summary.skipped = sum(skip_reasons.values())
    summary.skip_reasons = dict(sorted(skip_reasons.items()))
    summary.notes = dict(sorted(notes.items()))

    # Catalogue-level nodes.
    (site_dir / settings.organization_file).write_text(dump_jsonld(pices_organization_node(settings)), encoding="utf-8")
    catalog = data_catalog_node(settings, community, date_modified=normalise_lastmod(latest_updated))
    (site_dir / settings.catalog_file).write_text(dump_jsonld(catalog), encoding="utf-8")
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    # Sitemap and index page (the index links the sitemap files, so write the sitemap first).
    _count, sitemap_files = write_sitemap_for_site(settings)
    index_rows.sort(key=lambda r: (r["title"].lower(), r["record_id"]))
    (site_dir / "index.html").write_text(
        render_index(
            settings,
            index_rows,
            datasets=summary.datasets,
            creative_works=summary.creative_works,
            fetched_at=summary.snapshot_fetched_at,
            catalog_node=catalog,
            sitemap_files=[f.name for f in sitemap_files],
        ),
        encoding="utf-8",
    )

    reports_dir = settings.reports_dir
    assert reports_dir is not None
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / BUILD_SUMMARY_FILE).write_text(summary.to_json(), encoding="utf-8")
    return summary


# ----------------------------------------------------------------------
def collect_sitemap_entries(settings: Settings) -> list[SitemapEntry]:
    """Sitemap entries from the JSON-LD files on disk (``@id`` + ``dateModified``)."""
    site_dir = settings.site_dir
    assert site_dir is not None
    entries: list[SitemapEntry] = []
    latest: str | None = None
    for path in sorted(settings.records_dir.glob("*.jsonld")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        lastmod = normalise_lastmod(doc.get("dateModified"))
        entries.append(SitemapEntry(doc["@id"], lastmod))
        if lastmod and (latest is None or lastmod > latest):
            latest = lastmod
    if (site_dir / settings.catalog_file).exists():
        entries.append(SitemapEntry(settings.catalog_url, latest))
    if (site_dir / settings.organization_file).exists():
        entries.append(SitemapEntry(settings.organization_url, None))
    return entries


def write_sitemap_for_site(settings: Settings) -> tuple[int, list[Path]]:
    entries = collect_sitemap_entries(settings)
    files = write_sitemap(entries, settings)
    return len(entries), files


def _manifest(settings: Settings) -> Manifest | None:
    assert settings.snapshot_dir is not None
    path = settings.snapshot_dir / MANIFEST_FILE
    return Manifest.read(path) if path.exists() else None


def _kind_label(mapped: MappedRecord) -> str:
    types = mapped.doc.get("@type")
    if isinstance(types, list):
        return types[0]
    return str(types)
