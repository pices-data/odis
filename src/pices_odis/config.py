"""Configuration for the PICES ODIS pipeline.

Purpose
    Hold every tunable in one frozen dataclass so the CLI, the library and the
    tests share a single source of truth. The most important value is
    ``base_url``: the public root under which the JSON-LD files will be served.
    Every ``@id``, every sitemap ``<loc>`` and every cross-reference is derived
    from it, so changing it once re-roots the whole site.

    Hosting decision (2026-10-23): the directory is served by GitHub Pages from
    the ``docs/`` folder of the public repository ``pices-data/odis``, i.e. at
    ``https://pices-data.github.io/odis/`` (the default). Once the w3id.org
    redirect ``https://w3id.org/pices/odis/`` exists (see ``w3id/``), the base
    URL switches to :data:`W3ID_BASE_URL` by setting the environment variable
    ``PICES_ODIS_BASE_URL`` (repository variable in GitHub Actions) and
    rebuilding. Note that the switch changes every ``@id`` once; do it before
    registering the sitemap in ODISCat if at all possible.

Invariants
    * ``base_url`` always ends with ``/``.
    * Directory settings are absolute paths.
    * Nothing here performs I/O.

Assumptions
    * The PICES community on production Zenodo is identified by its UUID; the
      slug ``pices`` is only used for human-facing links.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

# GitHub Pages of the public repository pices-data/odis (docs/ folder on main).
DEFAULT_BASE_URL = "https://pices-data.github.io/odis/"
# Persistent identifier namespace requested from w3id.org; becomes the base URL once
# the redirect to the GitHub Pages site is live.
W3ID_BASE_URL = "https://w3id.org/pices/odis/"
ENV_BASE_URL = "PICES_ODIS_BASE_URL"
GITHUB_OWNER = "pices-data"
GITHUB_REPOSITORY = "odis"

# Zenodo's firewall rejects requests with no User-Agent or Python's default one.
USER_AGENT = "pices-odis/0.1 (+mailto:johnson@psc.org)"

# InvenioRDM serialization: exposes GeoJSON locations, rights text, EDTF dates,
# the publisher field and file entries, which the legacy serialization lacks.
ACCEPT_RDM = "application/vnd.inveniordm.v1+json"


@dataclass(frozen=True)
class Settings:
    """All pipeline settings. Construct with :func:`Settings.create`."""

    # --- public URLs -------------------------------------------------------
    base_url: str = DEFAULT_BASE_URL
    records_dir_name: str = "records"
    record_file_prefix: str = "zenodo-"  # records/zenodo-<concept id>.jsonld
    organization_file: str = "organization.jsonld"
    catalog_file: str = "catalog.jsonld"
    sitemap_file: str = "sitemap.xml"
    sitemap_changefreq: str = "monthly"
    sitemap_max_urls: int = 50_000  # sitemaps.org limit per file

    # --- Zenodo ------------------------------------------------------------
    zenodo_api: str = "https://zenodo.org/api"
    zenodo_html: str = "https://zenodo.org"
    community_id: str = "92279449-f6e1-422d-8610-40802567c58b"
    community_slug: str = "pices"
    user_agent: str = USER_AGENT
    accept: str = ACCEPT_RDM
    page_size: int = 25  # anonymous listings are capped at 25 hits per page
    sort: str = "oldest"  # stable page boundaries while new records appear
    min_request_interval: float = 2.5  # seconds; anonymous limit is 30/min
    request_timeout: float = 60.0
    max_attempts: int = 6

    # --- local paths -------------------------------------------------------
    root: Path = field(default_factory=Path.cwd)
    snapshot_dir: Path | None = None
    site_dir: Path | None = None
    reports_dir: Path | None = None
    shapes_dir: Path | None = None

    # ----------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        root: Path | str | None = None,
        base_url: str | None = None,
        **overrides,
    ) -> "Settings":
        """Build settings from defaults, the environment and explicit overrides.

        Precedence for ``base_url``: explicit argument, then the
        ``PICES_ODIS_BASE_URL`` environment variable, then the default.
        """
        root_path = Path(root).resolve() if root else Path.cwd().resolve()
        url = base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL
        if not url.endswith("/"):
            url += "/"
        settings = cls(base_url=url, root=root_path, **overrides)
        # Resolve derived directories unless the caller supplied them.
        return replace(
            settings,
            snapshot_dir=_abs(root_path, settings.snapshot_dir, "data/snapshot"),
            site_dir=_abs(root_path, settings.site_dir, "docs"),
            reports_dir=_abs(root_path, settings.reports_dir, "reports"),
            shapes_dir=_abs(root_path, settings.shapes_dir, "shapes"),
        )

    # --- derived public URLs ----------------------------------------------
    def record_filename(self, concept_id: str | int) -> str:
        return f"{self.record_file_prefix}{concept_id}.jsonld"

    def record_url(self, concept_id: str | int) -> str:
        return f"{self.base_url}{self.records_dir_name}/{self.record_filename(concept_id)}"

    @property
    def organization_url(self) -> str:
        return self.base_url + self.organization_file

    @property
    def catalog_url(self) -> str:
        return self.base_url + self.catalog_file

    @property
    def sitemap_url(self) -> str:
        return self.base_url + self.sitemap_file

    # --- derived Zenodo URLs ----------------------------------------------
    @property
    def community_records_url(self) -> str:
        return f"{self.zenodo_api}/communities/{self.community_id}/records"

    @property
    def community_url(self) -> str:
        return f"{self.zenodo_api}/communities/{self.community_id}"

    @property
    def community_html_url(self) -> str:
        return f"{self.zenodo_html}/communities/{self.community_slug}/"

    # --- derived local paths ----------------------------------------------
    @property
    def records_dir(self) -> Path:
        assert self.site_dir is not None
        return self.site_dir / self.records_dir_name


def _abs(root: Path, value: Path | None, default_rel: str) -> Path:
    path = Path(value) if value is not None else root / default_rel
    return path if path.is_absolute() else (root / path).resolve()
