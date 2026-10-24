"""Command-line interface: ``pices-odis fetch|build|sitemap|validate|all``.

Purpose
    One entry point for the whole pipeline so that the local run, the tests
    and the GitHub Actions workflow execute exactly the same code.

Invariants
    * Every command accepts ``--base-url`` (or ``PICES_ODIS_BASE_URL``) and
      ``--root``; nothing else decides where files go or what URLs look like.
    * Exit status is non-zero when a step fails or when ``validate`` finds
      gate failures, so CI can block a deploy.

Assumptions
    * Commands run from the repository root unless ``--root`` is given.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pices-odis",
        description="Build the PICES Data Catalogue ODIS node (JSON-LD + sitemap) from Zenodo.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", type=Path, default=None, help="project root (default: current directory)")
    parser.add_argument("--base-url", default=None, help="public base URL of the site (default: $PICES_ODIS_BASE_URL or https://w3id.org/pices/odis/)")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="snapshot the PICES community via the Zenodo REST API (read-only, paced)")
    fetch.add_argument("--refresh", action="store_true", help="discard cached pages and refetch everything")
    fetch.add_argument("--max-pages", type=int, default=None, help="stop after N pages (smoke tests)")

    build = sub.add_parser("build", help="transform the snapshot into one JSON-LD file per record plus catalogue nodes")
    build.add_argument("--limit", type=int, default=None, help="only build the first N records")
    build.add_argument("--allow-incomplete", action="store_true", help="build from an incomplete snapshot")

    sub.add_parser("sitemap", help="write sitemap.xml (and a sitemap index if needed) for the built files")

    validate = sub.add_parser("validate", help="check JSON-LD well-formedness and run the ODIS SHACL shapes")
    validate.add_argument("--limit", type=int, default=None, help="only validate the first N record files")
    validate.add_argument("--no-shacl", action="store_true", help="skip SHACL (well-formedness only)")

    run_all = sub.add_parser("all", help="fetch (if needed), build, sitemap and validate in one go")
    run_all.add_argument("--refresh", action="store_true", help="refetch the snapshot first")
    run_all.add_argument("--limit", type=int, default=None, help="only build/validate the first N records")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.create(root=args.root, base_url=args.base_url)
    started = time.monotonic()
    try:
        if args.command == "fetch":
            code = cmd_fetch(settings, refresh=args.refresh, max_pages=args.max_pages)
        elif args.command == "build":
            code = cmd_build(settings, limit=args.limit, allow_incomplete=args.allow_incomplete)
        elif args.command == "sitemap":
            code = cmd_sitemap(settings)
        elif args.command == "validate":
            code = cmd_validate(settings, limit=args.limit, shacl=not args.no_shacl)
        elif args.command == "all":
            code = cmd_all(settings, refresh=args.refresh, limit=args.limit)
        else:  # pragma: no cover - argparse enforces choices
            code = 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    print(f"[{args.command}] done in {time.monotonic() - started:.1f}s", file=sys.stderr)
    return code


# ----------------------------------------------------------------------
def cmd_fetch(settings: Settings, *, refresh: bool, max_pages: int | None) -> int:
    from .zenodo import fetch_snapshot

    manifest = fetch_snapshot(settings, refresh=refresh, max_pages=max_pages, log=_log)
    _log(
        f"snapshot: {manifest.hits} hits on {manifest.pages} pages (total reported {manifest.total_hits}); "
        f"complete={manifest.complete}; {manifest.requests_made} requests in {manifest.elapsed_seconds}s"
    )
    return 0 if manifest.complete or max_pages is not None else 1


def cmd_build(settings: Settings, *, limit: int | None, allow_incomplete: bool) -> int:
    from .build import build_site

    summary = build_site(settings, limit=limit, allow_incomplete=allow_incomplete, log=_log)
    _log(
        f"built {summary.built} record files ({summary.datasets} datasets, {summary.creative_works} other works); "
        f"skipped {summary.skipped}: {summary.skip_reasons}"
    )
    return 0


def cmd_sitemap(settings: Settings) -> int:
    from .build import write_sitemap_for_site

    count, files = write_sitemap_for_site(settings)
    _log(f"sitemap: {count} URLs in {', '.join(str(f.relative_to(settings.site_dir)) for f in files)}")
    return 0


def cmd_validate(settings: Settings, *, limit: int | None, shacl: bool) -> int:
    from .validate import validate_site

    report = validate_site(settings, limit=limit, shacl=shacl, log=_log)
    _log(report.summary_text())
    return 0 if report.gate_passed else 1


def cmd_all(settings: Settings, *, refresh: bool, limit: int | None) -> int:
    code = cmd_fetch(settings, refresh=refresh, max_pages=None)
    if code:
        return code
    code = cmd_build(settings, limit=limit, allow_incomplete=False)
    if code:
        return code
    code = cmd_sitemap(settings)
    if code:
        return code
    return cmd_validate(settings, limit=limit, shacl=True)


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
