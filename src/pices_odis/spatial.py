"""Spatial coverage: Zenodo GeoJSON locations to schema.org and GeoSPARQL.

Purpose
    Express each record's ``metadata.locations.features`` the way the ODIS
    book recommends: a ``schema:Place`` with ``schema:geo`` (``GeoShape`` box
    or polygon, ``GeoCoordinates`` for points; latitude-longitude order) and,
    alongside it, an OGC GeoSPARQL ``hasGeometry``/``asWKT`` literal in CRS84
    (longitude-latitude order), which ODIS names as its preferred geometry
    encoding.

Invariants
    * schema.org coordinates are written latitude first; WKT is written
      longitude first. Both are derived from the same GeoJSON ring, so they
      cannot disagree.
    * An axis-aligned rectangle becomes a ``GeoShape.box`` ("south west north
      east"); any other ring becomes ``GeoShape.polygon``.
    * A location made of several features (the way the source pipeline
      encodes a bounding box that crosses the date line: a part west of the
      line and a part east of it) becomes ONE Place with several ``geo``
      shapes and one WKT MULTIPOLYGON. Nothing is merged across the date line.
    * A feature without geometry (a bounding box that Zenodo carries only as
      text) becomes a Place with a description and no ``geo``. The text is
      never parsed back into coordinates: that was a deliberate curation
      decision upstream.
    * Pure functions; no I/O.

Assumptions
    * GeoJSON coordinates are WGS 84 longitude/latitude (RFC 7946).
"""

from __future__ import annotations

from dataclasses import dataclass, field

GEOSPARQL = "http://www.opengis.net/ont/geosparql#"
SF = "http://www.opengis.net/ont/sf#"
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

# ODIS dataset template: declares the spatial reference system of the schema.org shapes.
SRS_PROPERTY = {
    "@type": "PropertyValue",
    "propertyID": "https://dbpedia.org/page/Spatial_reference_system",
    "value": "https://www.w3.org/2003/01/geo/wgs84_pos",
    "url": "https://www.w3.org/2003/01/geo/wgs84_pos",
}

DATE_LINE_SUFFIXES = ("; part west of the date line", "; part east of the date line")


@dataclass
class SpatialResult:
    """A schema.org Place (or None) plus notes about how it was derived."""

    place: dict | None
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
def features_to_place(features: list[dict]) -> SpatialResult:
    """Map the GeoJSON-like features of one Zenodo record to a single Place."""
    features = [f for f in (features or []) if isinstance(f, dict)]
    if not features:
        return SpatialResult(None, ["no location"])

    notes: list[str] = []
    shapes: list[dict] = []
    wkts: list[str] = []
    descriptions = [one_line(f.get("description")) for f in features]
    names = [one_line(f.get("place")) for f in features]

    shared, remainders = _split_shared_description(descriptions)
    if len(features) > 1 and all(d.endswith(DATE_LINE_SUFFIXES) for d in descriptions if d):
        notes.append("date-line split: several parts kept as one Place")
    for feature, remainder in zip(features, remainders):
        geometry = feature.get("geometry")
        if not geometry:
            notes.append("feature without geometry kept as text only")
            continue
        shape = geometry_to_geoshape(geometry)
        if shape is None:
            notes.append(f"unsupported geometry type {geometry.get('type')!r} skipped")
            continue
        if remainder:
            shape["description"] = remainder
        shapes.append(shape)
        wkts.append(geometry_to_wkt(geometry))

    place: dict = {"@type": "Place"}
    name = next((n for n in names if n), "")
    if name:
        place["name"] = name
    if shared:
        place["description"] = shared
    if shapes:
        place["geo"] = shapes[0] if len(shapes) == 1 else shapes
        place["additionalProperty"] = dict(SRS_PROPERTY)
        place[f"geosparql:hasGeometry"] = _geometry_node(wkts)
    elif not shared and not name:
        return SpatialResult(None, notes + ["location had neither geometry nor text"])
    return SpatialResult(place, notes)


# ----------------------------------------------------------------------
def geometry_to_geoshape(geometry: dict) -> dict | None:
    """One GeoJSON geometry to a schema.org GeoShape / GeoCoordinates node."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Point":
        lon, lat = coords[0], coords[1]
        return {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}
    if kind == "Polygon":
        ring = coords[0]
        box = axis_aligned_box(ring)
        if box is not None:
            south, west, north, east = box
            return {"@type": "GeoShape", "box": f"{_num(south)} {_num(west)} {_num(north)} {_num(east)}"}
        return {"@type": "GeoShape", "polygon": _latlon_list(ring)}
    if kind == "LineString":
        return {"@type": "GeoShape", "line": _latlon_list(coords)}
    if kind == "MultiPolygon":
        # Rare in this catalogue; represent as one polygon string per part is not
        # possible on a single GeoShape, so use the outer ring of the first part
        # and let the WKT carry the full geometry.
        first = geometry_to_geoshape({"type": "Polygon", "coordinates": coords[0]})
        if first is not None:
            first["description"] = "first part of a multi-polygon; see the WKT geometry for all parts"
        return first
    return None


def axis_aligned_box(ring: list[list[float]]) -> tuple[float, float, float, float] | None:
    """(south, west, north, east) when ``ring`` is a closed axis-aligned rectangle, else None."""
    points = [tuple(p[:2]) for p in ring]
    if len(points) == 5 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) != 4:
        return None
    lons = {p[0] for p in points}
    lats = {p[1] for p in points}
    if len(lons) != 2 or len(lats) != 2:
        return None
    # Each consecutive pair must share a longitude or a latitude (rectangle edges).
    for a, b in zip(points, points[1:] + points[:1]):
        if a[0] != b[0] and a[1] != b[1]:
            return None
    return (min(lats), min(lons), max(lats), max(lons))


def split_box_at_antimeridian(west: float, east: float, south: float, north: float) -> list[tuple[float, float, float, float]]:
    """Split a (west, east, south, north) box that crosses the date line (west > east).

    Returns one or two boxes as (west, east, south, north). This mirrors how the
    source pipeline encodes such boxes before they reach Zenodo; it is exposed
    so tests and downstream tools can reproduce the split.
    """
    if west <= east:
        return [(west, east, south, north)]
    return [(west, 180.0, south, north), (-180.0, east, south, north)]


# ----------------------------------------------------------------------
def geometry_to_wkt(geometry: dict) -> str:
    """GeoJSON geometry to WKT (CRS84, longitude latitude)."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Point":
        return f"POINT({_num(coords[0])} {_num(coords[1])})"
    if kind == "LineString":
        return f"LINESTRING({_ring(coords)})"
    if kind == "Polygon":
        return f"POLYGON({', '.join('(' + _ring(r) + ')' for r in coords)})"
    if kind == "MultiPolygon":
        return "MULTIPOLYGON(" + ", ".join("(" + ", ".join("(" + _ring(r) + ")" for r in poly) + ")" for poly in coords) + ")"
    if kind == "MultiPoint":
        return "MULTIPOINT(" + ", ".join(f"({_num(p[0])} {_num(p[1])})" for p in coords) + ")"
    raise ValueError(f"unsupported geometry type {kind!r}")


def combine_wkt(wkts: list[str]) -> tuple[str, str]:
    """Combine several WKT strings into one; returns (wkt, simple-features type IRI)."""
    if len(wkts) == 1:
        wkt = wkts[0]
        return wkt, SF + wkt.split("(", 1)[0].strip().title().replace("string", "String").replace("polygon", "Polygon").replace("point", "Point")
    if all(w.startswith("POLYGON") for w in wkts):
        return "MULTIPOLYGON(" + ", ".join(w[len("POLYGON"):] for w in wkts) + ")", SF + "MultiPolygon"
    if all(w.startswith("POINT") for w in wkts):
        return "MULTIPOINT(" + ", ".join(w[len("POINT"):] for w in wkts) + ")", SF + "MultiPoint"
    return "GEOMETRYCOLLECTION(" + ", ".join(wkts) + ")", SF + "GeometryCollection"


def _geometry_node(wkts: list[str]) -> dict:
    wkt, sf_type = combine_wkt(wkts)
    return {
        "@type": sf_type,
        "geosparql:asWKT": {"@type": GEOSPARQL + "wktLiteral", "@value": wkt},
        "geosparql:crs": {"@id": CRS84},
    }


# ----------------------------------------------------------------------
def _split_shared_description(descriptions: list[str]) -> tuple[str, list[str]]:
    """Factor a description shared by all features out of per-feature remainders.

    "Bounding coordinates: …; part west of the date line" and "…; part east of
    the date line" share the text before "; ", which becomes the Place
    description; the remainders become the per-shape descriptions.
    """
    non_empty = [d for d in descriptions if d]
    if not non_empty:
        return "", [""] * len(descriptions)
    if len(descriptions) == 1:
        return descriptions[0], [""]
    heads = {d.split("; ", 1)[0] for d in non_empty}
    if len(heads) == 1 and len(non_empty) == len(descriptions):
        head = heads.pop()
        return head, [d.split("; ", 1)[1] if "; " in d else "" for d in descriptions]
    unique: list[str] = []
    for d in non_empty:
        if d not in unique:
            unique.append(d)
    return " | ".join(unique), [""] * len(descriptions)


def _ring(points: list[list[float]]) -> str:
    return ", ".join(f"{_num(p[0])} {_num(p[1])}" for p in points)


def _latlon_list(points: list[list[float]]) -> str:
    # ODIS dataset template format: "lat lon,lat lon,…" (pairs comma-separated).
    return ",".join(f"{_num(p[1])} {_num(p[0])}" for p in points)


def _num(value: float) -> str:
    """Compact decimal rendering: 54.0 -> "54", -157.25 -> "-157.25"."""
    if isinstance(value, bool):
        raise TypeError("boolean is not a coordinate")
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def one_line(value) -> str:
    return " ".join(str(value or "").split())
