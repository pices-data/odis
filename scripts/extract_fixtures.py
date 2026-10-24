"""Copy a handful of raw Zenodo hits from the local snapshot into tests/fixtures.

Purpose
    The test-suite must run offline. This script selects records that exercise
    each mapping branch and stores them, unmodified, as individual JSON files
    under ``tests/fixtures/records/`` together with the community metadata.

Usage
    .venv/bin/python scripts/extract_fixtures.py            # uses data/snapshot
    .venv/bin/python scripts/extract_fixtures.py 123 456    # add/refresh specific ids

Invariants
    * Hits are written byte-for-byte as JSON (re-serialised with indent for
      readable diffs; values untouched).
    * The selection below documents WHY each record is a fixture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pices_odis.config import Settings  # noqa: E402
from pices_odis.zenodo import load_community, load_snapshot  # noqa: E402

# record id -> reason it is a fixture
SELECTION: dict[str, str] = {
    "23606272": "dataset; single bounding box; one collected interval; FGDC file; free-text rights",
    "23201173": "report; bounding box split at the date line (two polygon parts)",
    "23605621": "dataset; no location and no collected dates",
    "23508633": "dataset; point location (W=E, N=S)",
    "15046283": "dataset; CC-BY licence, ORCID, related identifiers (isbn/issn/handle), funding, language, version, xlsx files",
    "17317855": "dataset; restricted files (no file nodes may be emitted)",
    "17317857": "dataset; no Zenodo description, only a notes paragraph",
    "23571296": "report; two FGDC files (merged duplicate catalogue records)",
    "23570900": "dataset; 'describes' relation to a data-portal URL",
}


def main(extra_ids: list[str]) -> int:
    settings = Settings.create(root=ROOT)
    wanted = dict(SELECTION)
    for record_id in extra_ids:
        wanted.setdefault(record_id, "added on the command line")
    hits = {str(h["id"]): h for h in load_snapshot(settings)}
    out_dir = ROOT / "tests" / "fixtures" / "records"
    out_dir.mkdir(parents=True, exist_ok=True)
    missing = []
    for record_id, reason in wanted.items():
        hit = hits.get(record_id)
        if hit is None:
            missing.append(record_id)
            continue
        (out_dir / f"{record_id}.json").write_text(json.dumps(hit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{record_id}: {reason}")
    community = load_community(settings)
    if community is not None:
        (ROOT / "tests" / "fixtures" / "community.json").write_text(json.dumps(community, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if missing:
        print(f"not in snapshot: {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
