"""Shared test fixtures: offline Zenodo hits and a throw-away project layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pices_odis.config import Settings
from pices_odis.zenodo import COMMUNITY_FILE, MANIFEST_FILE, PAGES_SUBDIR, Manifest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
BASE_URL = "https://example.org/odis/"


def load_hit(record_id: str) -> dict:
    return json.loads((FIXTURES / "records" / f"{record_id}.json").read_text(encoding="utf-8"))


def all_hits() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((FIXTURES / "records").glob("*.json"))]


def load_community() -> dict:
    return json.loads((FIXTURES / "community.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings rooted in a temp dir, using the repository's vendored SHACL shapes."""
    return Settings.create(root=tmp_path, base_url=BASE_URL, shapes_dir=REPO / "shapes")


def make_snapshot(settings: Settings, hits: list[dict], community: dict | None = None, page_size: int = 25) -> None:
    """Write a complete snapshot (pages + manifest + community) from the given hits."""
    snapshot_dir = settings.snapshot_dir
    assert snapshot_dir is not None
    (snapshot_dir / PAGES_SUBDIR).mkdir(parents=True, exist_ok=True)
    pages = [hits[i : i + page_size] for i in range(0, len(hits), page_size)] or [[]]
    for number, page_hits in enumerate(pages, start=1):
        links = {"self": f"https://zenodo.org/api/x?page={number}"}
        if number < len(pages):
            links["next"] = f"https://zenodo.org/api/x?page={number + 1}"
        body = {"hits": {"hits": page_hits, "total": len(hits)}, "links": links}
        (snapshot_dir / PAGES_SUBDIR / f"page-{number:04d}.json").write_text(json.dumps(body), encoding="utf-8")
    manifest = Manifest(
        fetched_at="2026-10-24T04:00:32+00:00",
        api_url=settings.community_records_url,
        community_id=settings.community_id,
        accept=settings.accept,
        user_agent=settings.user_agent,
        sort=settings.sort,
        page_size=page_size,
        total_hits=len(hits),
        pages=len(pages),
        hits=len(hits),
        complete=True,
        elapsed_seconds=0.0,
        requests_made=0,
    )
    (snapshot_dir / MANIFEST_FILE).write_text(manifest.to_json(), encoding="utf-8")
    if community is not None:
        (snapshot_dir / COMMUNITY_FILE).write_text(json.dumps(community), encoding="utf-8")


@pytest.fixture
def built_site(settings: Settings):
    """A full build of the fixture records into the temp project; returns (settings, summary)."""
    from pices_odis.build import build_site

    make_snapshot(settings, all_hits(), load_community())
    summary = build_site(settings, log=lambda message: None)
    return settings, summary
