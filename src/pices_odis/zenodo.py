"""Zenodo REST API client and raw snapshot store.

Purpose
    Fetch every public record of the PICES community, page by page, and keep
    the raw responses on disk (``data/snapshot/``) so that the build step and
    reruns work offline and never refetch what is already cached.

Invariants
    * Every request carries the project User-Agent (Zenodo's firewall drops
      requests with no User-Agent or Python's default one) and the InvenioRDM
      ``Accept`` header. Only GET is ever used and no token is ever sent.
    * Requests are paced at least ``min_request_interval`` seconds apart.
      HTTP 429 and 5xx responses are retried with backoff that honours
      ``Retry-After`` / ``X-RateLimit-Reset`` when present.
    * Page bodies are stored byte-for-byte as returned; nothing is rewritten.
    * ``load_snapshot`` returns at most one hit per record id and at most one
      version per concept (the latest), sorted by record id.

Assumptions
    * Anonymous listings return at most 25 hits per page (``size=25``).
    * ``sort=oldest`` keeps page boundaries stable while records are being
      published during a long fetch; a newly published record appears on the
      last page instead of shifting earlier pages.
    * The listing omits ``links.next`` on the last page.
"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .config import Settings

PAGES_SUBDIR = "pages"
MANIFEST_FILE = "manifest.json"
COMMUNITY_FILE = "community.json"


class ZenodoError(RuntimeError):
    """Raised when Zenodo keeps failing after all retry attempts."""


@dataclass
class Manifest:
    """What a snapshot contains; written to ``data/snapshot/manifest.json``."""

    fetched_at: str
    api_url: str
    community_id: str
    accept: str
    user_agent: str
    sort: str
    page_size: int
    total_hits: int
    pages: int
    hits: int
    complete: bool
    elapsed_seconds: float
    requests_made: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"

    @classmethod
    def read(cls, path: Path) -> "Manifest":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


class ZenodoClient:
    """Minimal paced GET client on top of urllib (no third-party HTTP stack)."""

    def __init__(
        self,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        opener: Callable = urllib.request.urlopen,
        log: Callable[[str], None] = lambda message: None,
    ) -> None:
        self.settings = settings
        self._sleep = sleep
        self._clock = clock
        self._open = opener
        self._log = log
        self._last_request: float | None = None
        self.requests_made = 0

    # ------------------------------------------------------------------
    def get(self, url: str) -> tuple[bytes, dict[str, str]]:
        """GET ``url`` and return (body, lower-cased headers), with pacing and backoff."""
        attempt = 0
        delay = 2.0
        while True:
            attempt += 1
            self._pace()
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.settings.user_agent,
                    "Accept": self.settings.accept,
                },
                method="GET",
            )
            try:
                self.requests_made += 1
                with self._open(request, timeout=self.settings.request_timeout) as response:
                    body = response.read()
                    headers = {k.lower(): v for k, v in response.headers.items()}
                return body, headers
            except urllib.error.HTTPError as error:
                status = error.code
                headers = {k.lower(): v for k, v in (error.headers.items() if error.headers else [])}
                retryable = status == 429 or 500 <= status < 600
                if not retryable or attempt >= self.settings.max_attempts:
                    raise ZenodoError(f"GET {url} failed with HTTP {status} after {attempt} attempt(s)") from error
                wait = self._retry_wait(headers, delay)
                self._log(f"HTTP {status} from Zenodo; waiting {wait:.0f}s before attempt {attempt + 1}")
                self._sleep(wait)
                delay = min(delay * 2, 120.0)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt >= self.settings.max_attempts:
                    raise ZenodoError(f"GET {url} failed after {attempt} attempt(s): {error}") from error
                self._log(f"network error ({error}); waiting {delay:.0f}s before attempt {attempt + 1}")
                self._sleep(delay)
                delay = min(delay * 2, 120.0)

    def get_json(self, url: str) -> dict:
        body, _ = self.get(url)
        return json.loads(body.decode("utf-8"))

    # ------------------------------------------------------------------
    def _pace(self) -> None:
        """Sleep so that consecutive requests are ≥ min_request_interval apart."""
        now = self._clock()
        if self._last_request is not None:
            remaining = self.settings.min_request_interval - (now - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
                now += remaining
        self._last_request = now

    @staticmethod
    def _retry_wait(headers: dict[str, str], fallback: float) -> float:
        """Wait time from Retry-After (seconds) or X-RateLimit-Reset (epoch), else fallback."""
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return max(1.0, float(retry_after)) + 1.0
            except ValueError:
                pass
        reset = headers.get("x-ratelimit-reset")
        if reset:
            try:
                until = float(reset) - time.time()
                if 0 < until < 600:
                    return until + 1.0
            except ValueError:
                pass
        return fallback


# ----------------------------------------------------------------------
def page_url(settings: Settings, page: int) -> str:
    query = urllib.parse.urlencode({"size": settings.page_size, "page": page, "sort": settings.sort})
    return f"{settings.community_records_url}?{query}"


def page_path(snapshot_dir: Path, page: int) -> Path:
    return snapshot_dir / PAGES_SUBDIR / f"page-{page:04d}.json"


def fetch_snapshot(
    settings: Settings,
    *,
    refresh: bool = False,
    max_pages: int | None = None,
    client: ZenodoClient | None = None,
    log: Callable[[str], None] = print,
) -> Manifest:
    """Fetch (or complete) the community snapshot. Returns the manifest.

    * With an existing complete snapshot and ``refresh=False`` nothing is
      fetched. Pages already on disk are reused, so an interrupted fetch
      resumes where it stopped.
    * ``refresh=True`` discards the cached pages first so that records removed
      from Zenodo do not linger in stale pages.
    * ``max_pages`` limits the fetch for smoke tests; the manifest is then
      marked incomplete.
    """
    snapshot_dir = settings.snapshot_dir
    assert snapshot_dir is not None
    manifest_path = snapshot_dir / MANIFEST_FILE
    if not refresh and manifest_path.exists():
        manifest = Manifest.read(manifest_path)
        if manifest.complete and max_pages is None:
            log(f"snapshot already complete ({manifest.hits} hits, {manifest.pages} pages); use --refresh to refetch")
            return manifest
    if refresh and (snapshot_dir / PAGES_SUBDIR).exists():
        shutil.rmtree(snapshot_dir / PAGES_SUBDIR)
    (snapshot_dir / PAGES_SUBDIR).mkdir(parents=True, exist_ok=True)

    client = client or ZenodoClient(settings, log=log)
    started = time.monotonic()

    # Community metadata (title, description, website, ROR) feeds the DataCatalog node.
    community_path = snapshot_dir / COMMUNITY_FILE
    if refresh or not community_path.exists():
        body, _ = client.get(settings.community_url)
        community_path.write_bytes(body)

    page = 0
    total_hits = 0
    hits = 0
    complete = False
    while True:
        page += 1
        if max_pages is not None and page > max_pages:
            break
        path = page_path(snapshot_dir, page)
        if path.exists() and not refresh:
            body = path.read_bytes()
            source = "cache"
        else:
            body, _ = client.get(page_url(settings, page))
            path.write_bytes(body)
            source = "fetched"
        data = json.loads(body.decode("utf-8"))
        page_hits = data.get("hits", {}).get("hits", [])
        total_hits = int(data.get("hits", {}).get("total", total_hits))
        hits += len(page_hits)
        log(f"page {page}: {len(page_hits)} hits ({source}); {hits}/{total_hits}")
        if not data.get("links", {}).get("next") or not page_hits:
            complete = True
            break

    manifest = Manifest(
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        api_url=settings.community_records_url,
        community_id=settings.community_id,
        accept=settings.accept,
        user_agent=settings.user_agent,
        sort=settings.sort,
        page_size=settings.page_size,
        total_hits=total_hits,
        pages=page if complete else page - 1,
        hits=hits,
        complete=complete,
        elapsed_seconds=round(time.monotonic() - started, 1),
        requests_made=client.requests_made,
    )
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------
def iter_pages(snapshot_dir: Path) -> Iterable[dict]:
    """Yield each stored page (parsed) in page order."""
    pages_dir = snapshot_dir / PAGES_SUBDIR
    for path in sorted(pages_dir.glob("page-*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def load_snapshot(settings: Settings, *, allow_incomplete: bool = False) -> list[dict]:
    """Return the deduplicated hits of the snapshot, sorted by record id.

    Duplicates can arise when a record is published while paging (it shows up
    on two pages) or when two versions of a concept are both listed. The hit
    with the greatest ``updated`` wins for a record id; the highest
    ``versions.index`` wins for a concept.
    """
    snapshot_dir = settings.snapshot_dir
    assert snapshot_dir is not None
    manifest_path = snapshot_dir / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"no snapshot manifest at {manifest_path}; run `pices-odis fetch` first")
    manifest = Manifest.read(manifest_path)
    if not manifest.complete and not allow_incomplete:
        raise RuntimeError("snapshot is incomplete; rerun `pices-odis fetch` (it resumes) or pass --allow-incomplete")

    by_id: dict[str, dict] = {}
    for page in iter_pages(snapshot_dir):
        for hit in page.get("hits", {}).get("hits", []):
            key = str(hit["id"])
            if key not in by_id or hit.get("updated", "") > by_id[key].get("updated", ""):
                by_id[key] = hit

    by_concept: dict[str, dict] = {}
    for hit in by_id.values():
        concept = str(hit.get("parent", {}).get("id") or hit["id"])
        current = by_concept.get(concept)
        if current is None or _version_index(hit) > _version_index(current):
            by_concept[concept] = hit
    return sorted(by_concept.values(), key=lambda h: int(h["id"]))


def load_community(settings: Settings) -> dict | None:
    """The community metadata captured at fetch time, if present."""
    assert settings.snapshot_dir is not None
    path = settings.snapshot_dir / COMMUNITY_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _version_index(hit: dict) -> int:
    try:
        return int(hit.get("versions", {}).get("index") or 0)
    except (TypeError, ValueError):
        return 0
