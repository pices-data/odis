"""Minimal human-readable index page for the published directory.

Purpose
    GitHub Pages needs an ``index.html`` and humans landing on the base URL
    need to understand what the directory is. The page lists counts, the
    sitemap and catalogue nodes, and every record file. It also embeds the
    DataCatalog JSON-LD in a ``<script type="application/ld+json">`` tag, the
    embedding form the ODIS book describes, so the landing page itself is
    machine-readable. The sitemap lists the ``.jsonld`` files, not this page.

Invariants
    * Static HTML, no scripts other than the JSON-LD block, no external assets.
    * Deterministic for a given build (the refresh time shown is the
      snapshot's fetch time, not the build time).
"""

from __future__ import annotations

import json
from html import escape

from .catalog import SD_LICENSE
from .config import Settings


def render_index(
    settings: Settings,
    records: list[dict],
    *,
    datasets: int,
    creative_works: int,
    fetched_at: str | None,
    catalog_node: dict,
    sitemap_files: list[str],
) -> str:
    rows = "\n".join(
        f'      <li><a href="{escape(r["href"])}">{escape(r["title"])}</a> '
        f'<span class="meta">({escape(r["kind"])}; Zenodo record <a href="{escape(r["zenodo"])}">{escape(r["record_id"])}</a>)</span></li>'
        for r in records
    )
    sitemaps = " ".join(f'<a href="{escape(name)}">{escape(name)}</a>' for name in sitemap_files)
    jsonld = json.dumps(catalog_node, ensure_ascii=False, indent=2).replace("</", "<\\/")
    refreshed = escape(fetched_at or "unknown")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PICES Data Catalogue: ODIS JSON-LD directory</title>
  <meta name="description" content="schema.org JSON-LD descriptions of the PICES Data Catalogue (Zenodo community 'pices'), published by PICES for the IOC Ocean Data and Information System (ODIS).">
  <script type="application/ld+json">
{jsonld}
  </script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }}
    h1 {{ font-size: 1.6rem; }}
    .meta {{ color: #555; font-size: 0.9em; }}
    ul {{ padding-left: 1.2rem; }}
    code {{ background: #f3f3f3; padding: 0 0.2em; }}
  </style>
</head>
<body>
  <h1>PICES Data Catalogue: ODIS JSON-LD directory</h1>
  <p>This directory holds one <a href="https://json-ld.org/">JSON-LD</a> file per record of the
  <a href="{escape(settings.community_html_url)}">PICES Data Catalogue</a> (a community on Zenodo),
  expressed with <a href="https://schema.org/">schema.org</a> following the
  <a href="https://book.odis.org/">ODIS book</a> patterns. It is published by the
  North Pacific Marine Science Organization (PICES) so that the IOC Ocean Data and Information
  System (ODIS) can harvest a PICES-controlled description of the catalogue. Zenodo hosts the
  records and mints their DOIs.</p>
  <ul>
    <li>Records: <strong>{datasets + creative_works}</strong> ({datasets} datasets, {creative_works} reports and other works)</li>
    <li>Last refreshed from Zenodo: {refreshed}</li>
    <li>Sitemap for harvesters: {sitemaps}</li>
    <li>Catalogue node: <a href="{escape(settings.catalog_file)}">{escape(settings.catalog_file)}</a>;
        organisation node: <a href="{escape(settings.organization_file)}">{escape(settings.organization_file)}</a></li>
    <li>Base URL of this directory: <code>{escape(settings.base_url)}</code></li>
    <li>Licence of these JSON-LD descriptions: <a href="{escape(SD_LICENSE[0])}">CC BY 4.0</a>.
        Each described record keeps its own licence or use constraints, given in its
        <code>license</code> or <code>usageInfo</code>.</li>
  </ul>
  <h2>Records</h2>
  <ul>
{rows}
  </ul>
</body>
</html>
"""
