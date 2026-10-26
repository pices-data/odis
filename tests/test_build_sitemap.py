"""Build + sitemap: files on disk, stable output, sitemap correctness and chunking."""

from __future__ import annotations

import json
from dataclasses import replace

from conftest import all_hits, load_community, make_snapshot
from pices_odis.build import build_site, write_sitemap_for_site
from pices_odis.sitemap import SitemapEntry, normalise_lastmod, parse_sitemap, render_urlset, write_sitemap


def test_build_writes_every_public_record_and_catalogue_nodes(built_site):
    settings, summary = built_site
    hits = all_hits()
    assert summary.built == len(hits)
    assert summary.skipped == 0
    assert summary.datasets + summary.creative_works == summary.built
    records = sorted(settings.records_dir.glob("*.jsonld"))
    assert len(records) == len(hits)
    assert {p.name for p in records} == {f"zenodo-{h['parent']['id']}.jsonld" for h in hits}
    for name in ("organization.jsonld", "catalog.jsonld", "index.html", "sitemap.xml", ".nojekyll"):
        assert (settings.site_dir / name).exists(), name
    summary_file = json.loads((settings.reports_dir / "build-summary.json").read_text())
    assert summary_file["built"] == len(hits)
    assert summary_file["snapshot_fetched_at"] == "2026-10-24T04:00:32+00:00"
    index = (settings.site_dir / "index.html").read_text()
    assert '<script type="application/ld+json">' in index
    assert "records/zenodo-23606271.jsonld" in index
    assert 'href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>' in index


def test_build_is_deterministic_and_removes_stale_files(settings):
    make_snapshot(settings, all_hits(), load_community())
    build_site(settings, log=lambda m: None)
    first = {p.name: p.read_bytes() for p in settings.records_dir.glob("*.jsonld")}
    stale = settings.records_dir / "zenodo-999999.jsonld"
    stale.write_text("{}", encoding="utf-8")
    summary = build_site(settings, log=lambda m: None)
    second = {p.name: p.read_bytes() for p in settings.records_dir.glob("*.jsonld")}
    assert first == second
    assert not stale.exists() and summary.removed_stale_files == 1


def test_sitemap_lists_every_file_with_lastmod_from_zenodo(built_site):
    settings, summary = built_site
    kind, entries = parse_sitemap((settings.site_dir / "sitemap.xml").read_text())
    assert kind == "urlset"
    locs = [e.loc for e in entries]
    assert len(entries) == summary.built + 2
    assert all(loc.startswith("https://example.org/odis/") for loc in locs)
    assert settings.catalog_url in locs and settings.organization_url in locs
    assert locs == sorted(locs)
    by_loc = {e.loc: e for e in entries}
    for hit in all_hits():
        entry = by_loc[settings.record_url(hit["parent"]["id"])]
        assert entry.lastmod == normalise_lastmod(hit["updated"])
        assert entry.lastmod and entry.lastmod.endswith("+00:00") and "." not in entry.lastmod
    record_lastmods = [e.lastmod for e in entries if "/records/" in e.loc]
    assert by_loc[settings.catalog_url].lastmod == max(record_lastmods)
    assert by_loc[settings.organization_url].lastmod is None
    text = (settings.site_dir / "sitemap.xml").read_text()
    assert "<changefreq>monthly</changefreq>" in text
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')


def test_sitemap_index_when_over_the_limit(built_site):
    settings, summary = built_site
    small = replace(settings, sitemap_max_urls=4)
    count, files = write_sitemap_for_site(small)
    assert count == summary.built + 2
    kind, parts = parse_sitemap((small.site_dir / "sitemap.xml").read_text())
    assert kind == "sitemapindex"
    assert len(parts) == -(-count // 4)
    assert [p.loc for p in parts] == [f"https://example.org/odis/sitemap-{i}.xml" for i in range(1, len(parts) + 1)]
    listed = []
    for part in parts:
        part_kind, part_entries = parse_sitemap((small.site_dir / part.loc.rsplit("/", 1)[1]).read_text())
        assert part_kind == "urlset" and len(part_entries) <= 4
        listed.extend(e.loc for e in part_entries)
    assert len(listed) == count and len(set(listed)) == count
    # Rebuilding with the normal limit removes the parts again.
    write_sitemap_for_site(settings)
    assert not list(settings.site_dir.glob("sitemap-*.xml"))


def test_sitemap_rejects_urls_outside_the_base(settings):
    settings.site_dir.mkdir(parents=True)
    try:
        write_sitemap([SitemapEntry("https://elsewhere.org/x.jsonld", None)], settings)
    except ValueError as error:
        assert "not under base URL" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_normalise_lastmod_and_escaping():
    assert normalise_lastmod("2026-10-23T23:14:26.608045+00:00") == "2026-10-23T23:14:26+00:00"
    assert normalise_lastmod("2026-10-23T23:14:26Z") == "2026-10-23T23:14:26+00:00"
    assert normalise_lastmod("2026-10-23") == "2026-10-23"
    assert normalise_lastmod("garbage") is None
    xml = render_urlset([SitemapEntry("https://example.org/a?b=1&c=2", "2026-01-01")], None)
    assert "&amp;" in xml and "<changefreq>" not in xml
