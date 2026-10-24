"""Validation: JSON-LD well-formedness and the ODIS SHACL shapes.

Purpose
    Check every published file the way a harvester would read it, then run
    the SHACL shapes ODIS publishes in ``iodepo/odis-arch/validation/SHACL``
    (vendored under ``shapes/``) over the combined graph, exactly as the ODIS
    validation workflow does with a node's whole graph. Write a machine-
    readable report (``reports/validation-report.json``) and return whether
    the gate passed.

Gate (what makes ``validate`` exit non-zero)
    * any file that is not valid JSON, does not expand as JSON-LD (PyLD), or
      yields no triples (rdflib);
    * any record file whose ``@id`` is not the URL the file is served at;
    * any sh:Violation from ``oih_search.ttl`` (the shape the ODIS validation
      workflow uses) whose focus node is a record, the catalogue or the PICES
      organisation.

    Results on embedded nodes (authors as Person/Organization without their
    own IRI, url or description) and all results from the dataset and spatial
    shapes are reported as advisory: they describe information Zenodo does
    not hold, and inventing it would be worse than reporting it.

Invariants
    * Validation never touches the network: contexts are inline and the
      shapes are local files.
    * The report groups results by shape, severity, message and focus kind so
      3,900 records produce a readable summary; per-record detail is kept for
      record-level violations.

Assumptions
    * ``pyshacl`` without inference (``inference='none'``), like ODIS.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pyld import jsonld
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef

from .config import Settings

SH = Namespace("http://www.w3.org/ns/shacl#")
SCHEMA = Namespace("https://schema.org/")
GATE_SHAPE = "oih_search.ttl"
VALIDATION_REPORT_FILE = "validation-report.json"
MAX_DETAIL = 200


@dataclass
class ShapeReport:
    shape: str
    conforms: bool
    results: int
    by_severity: dict[str, int] = field(default_factory=dict)
    by_message: dict[str, int] = field(default_factory=dict)
    by_focus_kind: dict[str, int] = field(default_factory=dict)
    # severity -> focus kind -> message -> count
    matrix: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    record_level_violations: int = 0
    records_with_violations: int = 0
    record_violation_details: list[dict] = field(default_factory=list)


@dataclass
class ValidationReport:
    generated_at: str
    site_dir: str
    gate_definition: str
    files_checked: int = 0
    records_checked: int = 0
    well_formed: int = 0
    malformed: list[dict] = field(default_factory=list)
    id_mismatches: list[dict] = field(default_factory=list)
    triples: int = 0
    types: dict[str, int] = field(default_factory=dict)
    shapes: list[ShapeReport] = field(default_factory=list)
    shacl_skipped: bool = False
    gate_passed: bool = False
    gate_failures: dict[str, int] = field(default_factory=dict)
    failures_by_reason: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"

    def summary_text(self) -> str:
        lines = [
            f"validation: {self.files_checked} files ({self.records_checked} records), "
            f"{self.well_formed} well-formed, {len(self.malformed)} malformed, {len(self.id_mismatches)} @id mismatches, "
            f"{self.triples} triples",
        ]
        for shape in self.shapes:
            lines.append(
                f"  {shape.shape}: conforms={shape.conforms}, results={shape.results} {shape.by_severity}; "
                f"record-level violations={shape.record_level_violations} on {shape.records_with_violations} records"
            )
        lines.append(f"gate {'PASSED' if self.gate_passed else 'FAILED'}: {self.gate_failures}")
        return "\n".join(lines)


# ----------------------------------------------------------------------
def validate_site(
    settings: Settings,
    *,
    limit: int | None = None,
    shacl: bool = True,
    log: Callable[[str], None] = print,
) -> ValidationReport:
    site_dir = settings.site_dir
    assert site_dir is not None
    report = ValidationReport(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        site_dir=str(site_dir),
        gate_definition=(
            "all files parse as JSON and expand as JSON-LD with at least one triple; record @id equals the served URL; "
            f"no sh:Violation from {GATE_SHAPE} on a record, the catalogue or the organisation node"
        ),
    )

    record_files = sorted(settings.records_dir.glob("*.jsonld"))
    if limit is not None:
        record_files = record_files[:limit]
    top_files = [site_dir / settings.organization_file, site_dir / settings.catalog_file]
    files = [p for p in top_files if p.exists()] + record_files
    report.records_checked = len(record_files)

    data_graph = Graph()
    record_ids: set[str] = set()
    catalogue_ids = {settings.organization_url, settings.catalog_url}
    type_counter: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()

    for index, path in enumerate(files, start=1):
        report.files_checked += 1
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            jsonld.expand(doc)  # strict JSON-LD processing, offline (inline context)
            graph = Graph().parse(data=json.dumps(doc), format="json-ld")
            if len(graph) == 0:
                raise ValueError("JSON-LD produced no triples")
        except Exception as error:  # noqa: BLE001 - any failure is a validation finding
            report.malformed.append({"file": str(path.relative_to(site_dir)), "error": f"{type(error).__name__}: {error}"})
            failure_reasons["malformed JSON-LD"] += 1
            continue
        report.well_formed += 1
        doc_id = doc.get("@id")
        expected = _expected_id(path, settings)
        if expected and doc_id != expected:
            report.id_mismatches.append({"file": str(path.relative_to(site_dir)), "@id": doc_id, "expected": expected})
            failure_reasons["@id does not match served URL"] += 1
        if path.parent == settings.records_dir and doc_id:
            record_ids.add(doc_id)
        types = doc.get("@type")
        for t in types if isinstance(types, list) else [types]:
            type_counter[str(t)] += 1
        if shacl:
            data_graph += graph
        if index % 500 == 0:
            log(f"parsed {index}/{len(files)} files")
    report.triples = len(data_graph) if shacl else 0
    report.types = dict(sorted(type_counter.items()))

    if shacl:
        shape_files = sorted(settings.shapes_dir.glob("*.ttl")) if settings.shapes_dir and settings.shapes_dir.exists() else []
        if not shape_files:
            report.shacl_skipped = True
            log(f"no SHACL shapes found under {settings.shapes_dir}; skipping SHACL")
        # The gate shape runs first so a failing report shows the decisive results on top.
        shape_files.sort(key=lambda p: (p.name != GATE_SHAPE, p.name))
        for shape_path in shape_files:
            log(f"SHACL: {shape_path.name} over {len(data_graph)} triples")
            report.shapes.append(run_shape(data_graph, shape_path, record_ids, catalogue_ids))
    else:
        report.shacl_skipped = True

    gate = {"malformed files": len(report.malformed), "@id mismatches": len(report.id_mismatches)}
    for shape in report.shapes:
        if shape.shape == GATE_SHAPE:
            gate[f"{GATE_SHAPE} record-level violations"] = shape.record_level_violations
            if shape.record_level_violations:
                failure_reasons[f"{GATE_SHAPE} violation on record/catalogue node"] += shape.records_with_violations
    report.gate_failures = gate
    report.gate_passed = all(v == 0 for v in gate.values())
    report.failures_by_reason = dict(sorted(failure_reasons.items()))

    reports_dir = settings.reports_dir
    assert reports_dir is not None
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / VALIDATION_REPORT_FILE).write_text(report.to_json(), encoding="utf-8")
    return report


# ----------------------------------------------------------------------
def run_shape(data_graph: Graph, shape_path: Path, record_ids: set[str], catalogue_ids: set[str]) -> ShapeReport:
    """Validate ``data_graph`` with one shapes file and summarise the results graph."""
    from pyshacl import validate as shacl_validate

    shapes_graph = Graph().parse(str(shape_path), format="turtle")
    conforms, results_graph, _text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
        meta_shacl=False,
        advanced=False,
        debug=False,
    )
    report = ShapeReport(shape=shape_path.name, conforms=bool(conforms), results=0)
    severity_counter: Counter[str] = Counter()
    message_counter: Counter[str] = Counter()
    focus_counter: Counter[str] = Counter()
    matrix: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    violating_records: set[str] = set()

    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        report.results += 1
        focus = results_graph.value(result, SH.focusNode)
        severity = _local(results_graph.value(result, SH.resultSeverity))
        message = str(results_graph.value(result, SH.resultMessage) or "").strip()
        path = results_graph.value(result, SH.resultPath)
        kind = _focus_kind(focus, data_graph, record_ids, catalogue_ids)
        severity_counter[severity] += 1
        message_counter[message] += 1
        focus_counter[kind] += 1
        matrix[severity][kind][message] += 1
        if severity == "Violation" and kind in ("record", "catalogue"):
            report.record_level_violations += 1
            violating_records.add(str(focus))
            if len(report.record_violation_details) < MAX_DETAIL:
                report.record_violation_details.append(
                    {"focus": str(focus), "message": message, "path": _local(path) if path is not None else None}
                )

    report.by_severity = dict(sorted(severity_counter.items()))
    report.by_message = dict(sorted(message_counter.items()))
    report.by_focus_kind = dict(sorted(focus_counter.items()))
    report.matrix = {s: {k: dict(sorted(m.items())) for k, m in sorted(kinds.items())} for s, kinds in sorted(matrix.items())}
    report.records_with_violations = len(violating_records)
    return report


def _focus_kind(focus, data_graph: Graph, record_ids: set[str], catalogue_ids: set[str]) -> str:
    """'record', 'catalogue', or 'embedded:<Type>' for blank/other nodes."""
    if isinstance(focus, URIRef):
        if str(focus) in record_ids:
            return "record"
        if str(focus) in catalogue_ids:
            return "catalogue"
    types = sorted(_local(t) for t in data_graph.objects(focus, RDF.type))
    label = "/".join(types) if types else "untyped"
    if isinstance(focus, BNode):
        return f"embedded:{label}"
    return f"other-iri:{label}"


def _expected_id(path: Path, settings: Settings) -> str | None:
    if path.parent == settings.records_dir:
        if not path.name.startswith(settings.record_file_prefix):
            return None
        concept = path.name[len(settings.record_file_prefix) : -len(".jsonld")]
        return settings.record_url(concept)
    if path.name == settings.organization_file:
        return settings.organization_url
    if path.name == settings.catalog_file:
        return settings.catalog_url
    return None


def _local(node) -> str:
    if node is None:
        return ""
    if isinstance(node, Literal):
        return str(node)
    text = str(node)
    for sep in ("#", "/"):
        if sep in text:
            text = text.rsplit(sep, 1)[-1]
            break
    return text
