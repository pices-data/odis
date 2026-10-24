"""Zenodo client and snapshot store, exercised with a fake HTTP opener (no network)."""

from __future__ import annotations

import io
import itertools
import json
import urllib.error
from email.message import Message

import pytest

from pices_odis.config import Settings
from pices_odis.zenodo import ZenodoClient, ZenodoError, fetch_snapshot, load_snapshot, page_url


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self._body = body
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError("https://zenodo.org/api/x", code, "err", message, io.BytesIO(b""))


class FakeOpener:
    """Serves scripted responses per URL; records requests and the headers sent."""

    def __init__(self, script: dict[str, list]) -> None:
        self.script = {url: list(responses) for url, responses in script.items()}
        self.requests: list = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        responses = self.script[request.full_url]
        response = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def page_body(hits: list[dict], total: int, next_page: bool) -> bytes:
    links = {"self": "x"}
    if next_page:
        links["next"] = "y"
    return json.dumps({"hits": {"hits": hits, "total": total}, "links": links}).encode()


def hit(record_id: int, concept: int | None = None, index: int = 1, updated: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "id": str(record_id),
        "parent": {"id": str(concept or record_id)},
        "versions": {"index": index, "is_latest": True},
        "updated": updated,
        "metadata": {"title": f"record {record_id}"},
    }


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings.create(root=tmp_path, min_request_interval=2.5)


def test_client_sends_user_agent_and_paces(settings):
    opener = FakeOpener({"https://zenodo.org/api/x": [FakeResponse(b"{}")]})
    sleeps: list[float] = []
    clock = iter([0.0, 0.5, 10.0])  # one clock read per request
    client = ZenodoClient(settings, sleep=sleeps.append, clock=lambda: next(clock), opener=opener)
    client.get("https://zenodo.org/api/x")
    client.get("https://zenodo.org/api/x")
    client.get("https://zenodo.org/api/x")
    sent = opener.requests[0]
    assert sent.get_header("User-agent") == "pices-odis/0.1 (+mailto:johnson@psc.org)"
    assert sent.get_header("Accept") == "application/vnd.inveniordm.v1+json"
    assert "Authorization" not in sent.headers
    # Second request came 0.5 s after the first: sleep the remaining 2.0 s; third was 9.5 s later: no sleep.
    assert sleeps == [2.0]


def test_client_retries_429_using_retry_after_and_5xx_with_backoff(settings):
    url = "https://zenodo.org/api/x"
    opener = FakeOpener({url: [http_error(429, {"Retry-After": "7"}), http_error(503), FakeResponse(b'{"ok": true}')]})
    sleeps: list[float] = []
    clock = itertools.count(0.0, 100.0)  # far apart, so pacing never sleeps
    client = ZenodoClient(settings, sleep=sleeps.append, clock=lambda: next(clock), opener=opener)
    assert client.get_json(url) == {"ok": True}
    assert sleeps == [8.0, 4.0]  # Retry-After + 1, then the doubled exponential fallback
    assert client.requests_made == 3


def test_client_gives_up_after_max_attempts(settings):
    url = "https://zenodo.org/api/x"
    opener = FakeOpener({url: [http_error(500)]})
    client = ZenodoClient(Settings.create(root=settings.root, max_attempts=3), sleep=lambda s: None, clock=lambda: 0.0, opener=opener)
    with pytest.raises(ZenodoError):
        client.get(url)
    assert len(opener.requests) == 3


def test_client_does_not_retry_client_errors(settings):
    url = "https://zenodo.org/api/x"
    opener = FakeOpener({url: [http_error(403)]})
    client = ZenodoClient(settings, sleep=lambda s: None, clock=lambda: 0.0, opener=opener)
    with pytest.raises(ZenodoError):
        client.get(url)
    assert len(opener.requests) == 1


def _scripted_client(settings: Settings, pages: list[list[dict]]):
    script = {settings.community_url: [FakeResponse(json.dumps({"id": settings.community_id, "metadata": {"title": "PICES"}}).encode())]}
    total = sum(len(p) for p in pages)
    for number, page_hits in enumerate(pages, start=1):
        script[page_url(settings, number)] = [FakeResponse(page_body(page_hits, total, number < len(pages)))]
    opener = FakeOpener(script)
    return ZenodoClient(settings, sleep=lambda s: None, clock=lambda: 0.0, opener=opener), opener


def test_fetch_snapshot_pages_until_no_next_and_caches(settings):
    pages = [[hit(1), hit(2)], [hit(3)]]
    client, opener = _scripted_client(settings, pages)
    manifest = fetch_snapshot(settings, client=client, log=lambda m: None)
    assert manifest.complete and manifest.pages == 2 and manifest.hits == 3 and manifest.total_hits == 3
    assert (settings.snapshot_dir / "pages" / "page-0001.json").exists()
    assert (settings.snapshot_dir / "pages" / "page-0002.json").exists()
    assert (settings.snapshot_dir / "community.json").exists()
    assert len(opener.requests) == 3  # community + 2 pages
    # Raw bytes are stored untouched.
    assert (settings.snapshot_dir / "pages" / "page-0001.json").read_bytes() == page_body(pages[0], 3, True)

    # A rerun without --refresh fetches nothing.
    client2, opener2 = _scripted_client(settings, pages)
    fetch_snapshot(settings, client=client2, log=lambda m: None)
    assert opener2.requests == []

    # --refresh refetches everything.
    client3, opener3 = _scripted_client(settings, pages)
    fetch_snapshot(settings, refresh=True, client=client3, log=lambda m: None)
    assert len(opener3.requests) == 3

    assert [h["id"] for h in load_snapshot(settings)] == ["1", "2", "3"]


def test_load_snapshot_deduplicates_ids_and_keeps_latest_version(settings):
    duplicate_old = hit(2, updated="2025-01-01T00:00:00+00:00")
    duplicate_new = hit(2, updated="2026-02-02T00:00:00+00:00")
    version1 = hit(10, concept=9, index=1)
    version2 = hit(11, concept=9, index=2)
    pages = [[hit(1), duplicate_old, version1], [duplicate_new, version2]]
    client, _ = _scripted_client(settings, pages)
    fetch_snapshot(settings, client=client, log=lambda m: None)
    hits = load_snapshot(settings)
    assert [h["id"] for h in hits] == ["1", "2", "11"]
    assert next(h for h in hits if h["id"] == "2")["updated"] == "2026-02-02T00:00:00+00:00"


def test_load_snapshot_requires_a_complete_manifest(settings):
    pages = [[hit(1)], [hit(2)]]
    client, _ = _scripted_client(settings, pages)
    manifest = fetch_snapshot(settings, client=client, max_pages=1, log=lambda m: None)
    assert manifest.complete is False
    with pytest.raises(RuntimeError):
        load_snapshot(settings)
    assert [h["id"] for h in load_snapshot(settings, allow_incomplete=True)] == ["1"]
