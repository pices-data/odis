"""sitemap.xml generation and parsing.

Purpose
    Tell ODIS (and any other harvester) which JSON-LD files exist and when
    each one last changed, following https://www.sitemaps.org/protocol.html
    and the ODIS book's advice to include ``<lastmod>`` and ``<changefreq>``.

Invariants
    * Every ``<loc>`` is an absolute URL under the configured base URL.
    * ``<lastmod>`` is the Zenodo record's ``updated`` time (W3C datetime,
      UTC), so a harvester sees exactly when the metadata last changed.
    * At most ``sitemap_max_urls`` URLs per file; beyond that a sitemap index
      is written as ``sitemap.xml`` and the parts as ``sitemap-N.xml``.
    * Output is deterministic: entries are sorted by URL.

Assumptions
    * The sitemap is served from the same base URL as the files it lists
      (sitemaps.org requires the listed URLs to share the sitemap's prefix).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .config import Settings

# The protocol's namespace is an http:// name, not a fetched URL; an https://
# variant is a different namespace, and strict parsers then find no <url> entries.
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: str | None = None


def normalise_lastmod(value: str | None) -> str | None:
    """Zenodo ``updated`` ("2026-10-23T23:14:26.608045+00:00") -> W3C datetime without microseconds."""
    if not value:
        return None
    value = value.strip()
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?)?", value)
    if not match:
        return None
    date, clock, zone = match.groups()
    if not clock:
        return date
    zone = "+00:00" if zone in (None, "Z") else zone
    return f"{date}T{clock}{zone}"


def render_urlset(entries: list[SitemapEntry], changefreq: str | None) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="{SITEMAP_NS}">']
    for entry in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(entry.loc)}</loc>")
        if entry.lastmod:
            lines.append(f"    <lastmod>{escape(entry.lastmod)}</lastmod>")
        if changefreq:
            lines.append(f"    <changefreq>{escape(changefreq)}</changefreq>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_index(parts: list[SitemapEntry]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<sitemapindex xmlns="{SITEMAP_NS}">']
    for part in parts:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{escape(part.loc)}</loc>")
        if part.lastmod:
            lines.append(f"    <lastmod>{escape(part.lastmod)}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"


def write_sitemap(entries: list[SitemapEntry], settings: Settings) -> list[Path]:
    """Write sitemap.xml (plus parts when needed) into the site dir; return the files written."""
    site_dir = settings.site_dir
    assert site_dir is not None
    site_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(set(entries), key=lambda e: e.loc)
    for entry in ordered:
        if not entry.loc.startswith(settings.base_url):
            raise ValueError(f"sitemap entry {entry.loc} is not under base URL {settings.base_url}")
    main = site_dir / settings.sitemap_file
    # Remove parts from an earlier, larger build so stale files do not linger.
    for stale in site_dir.glob("sitemap-*.xml"):
        stale.unlink()
    if len(ordered) <= settings.sitemap_max_urls:
        main.write_text(render_urlset(ordered, settings.sitemap_changefreq), encoding="utf-8")
        return [main]
    written: list[Path] = []
    parts: list[SitemapEntry] = []
    for index, start in enumerate(range(0, len(ordered), settings.sitemap_max_urls), start=1):
        chunk = ordered[start : start + settings.sitemap_max_urls]
        part_name = f"sitemap-{index}.xml"
        part_path = site_dir / part_name
        part_path.write_text(render_urlset(chunk, settings.sitemap_changefreq), encoding="utf-8")
        written.append(part_path)
        lastmods = [e.lastmod for e in chunk if e.lastmod]
        parts.append(SitemapEntry(settings.base_url + part_name, max(lastmods) if lastmods else None))
    main.write_text(render_index(parts), encoding="utf-8")
    return [main] + written


def parse_sitemap(text: str) -> tuple[str, list[SitemapEntry]]:
    """Parse a sitemap or sitemap index; returns (kind, entries) with kind 'urlset' or 'sitemapindex'."""
    root = ET.fromstring(text)
    kind = root.tag.split("}", 1)[-1]
    item_tag = "url" if kind == "urlset" else "sitemap"
    entries = []
    for item in root.findall(f"{{{SITEMAP_NS}}}{item_tag}"):
        loc = item.findtext(f"{{{SITEMAP_NS}}}loc")
        lastmod = item.findtext(f"{{{SITEMAP_NS}}}lastmod")
        entries.append(SitemapEntry(loc or "", lastmod))
    return kind, entries
