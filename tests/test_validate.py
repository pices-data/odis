"""Validation: well-formedness, @id check and the ODIS SHACL gate on the fixture build."""

from __future__ import annotations

import json

from pices_odis.validate import validate_site


def test_fixture_build_passes_the_gate(built_site):
    settings, summary = built_site
    report = validate_site(settings, log=lambda m: None)
    assert report.files_checked == summary.built + 2
    assert report.well_formed == report.files_checked
    assert report.malformed == [] and report.id_mismatches == []
    assert report.triples > 0
    assert report.types["Dataset"] >= 1 and report.types["Report"] >= 1 and report.types["DataCatalog"] == 1
    shapes = {s.shape: s for s in report.shapes}
    assert set(shapes) == {"oih_search.ttl", "oih_dataset.ttl", "oih_spatial0.ttl"}
    gate = shapes["oih_search.ttl"]
    assert gate.record_level_violations == 0
    # Embedded author nodes have no IRI/url/description: reported, not gating.
    assert any(kind.startswith("embedded:") for kind in gate.by_focus_kind)
    assert report.gate_passed is True
    written = json.loads((settings.reports_dir / "validation-report.json").read_text())
    assert written["gate_passed"] is True
    assert written["gate_failures"]["oih_search.ttl record-level violations"] == 0


def test_malformed_file_and_wrong_id_fail_the_gate(built_site):
    settings, _summary = built_site
    broken = settings.records_dir / "zenodo-1.jsonld"
    broken.write_text("{not json", encoding="utf-8")
    wrong = settings.records_dir / "zenodo-2.jsonld"
    wrong.write_text(
        json.dumps({"@context": {"@vocab": "https://schema.org/"}, "@id": "https://example.org/odis/records/other.jsonld",
                    "@type": "Dataset", "name": "x", "description": "y", "url": "https://zenodo.org/records/2"}),
        encoding="utf-8",
    )
    report = validate_site(settings, log=lambda m: None)
    assert report.gate_passed is False
    assert [m["file"] for m in report.malformed] == ["records/zenodo-1.jsonld"]
    assert [m["file"] for m in report.id_mismatches] == ["records/zenodo-2.jsonld"]
    assert report.failures_by_reason == {"@id does not match served URL": 1, "malformed JSON-LD": 1}


def test_record_level_violation_is_counted(built_site):
    settings, _summary = built_site
    # A Dataset without a description violates the ODIS search shape on the record itself.
    path = settings.records_dir / "zenodo-3.jsonld"
    path.write_text(
        json.dumps({"@context": {"@vocab": "https://schema.org/"}, "@id": settings.record_url(3), "@type": "Dataset",
                    "name": "No description", "url": "https://zenodo.org/records/3"}),
        encoding="utf-8",
    )
    report = validate_site(settings, log=lambda m: None)
    gate = next(s for s in report.shapes if s.shape == "oih_search.ttl")
    assert gate.record_level_violations == 1 and gate.records_with_violations == 1
    assert gate.record_violation_details[0]["focus"] == settings.record_url(3)
    assert gate.record_violation_details[0]["path"] == "description"
    assert report.gate_passed is False
