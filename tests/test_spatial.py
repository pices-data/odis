"""Spatial mapping: boxes, polygons, points, the date-line split, text-only places."""

from __future__ import annotations

from conftest import load_hit
from pices_odis.spatial import (
    CRS84,
    axis_aligned_box,
    features_to_place,
    geometry_to_geoshape,
    geometry_to_wkt,
    split_box_at_antimeridian,
)


def _features(record_id: str) -> list[dict]:
    return load_hit(record_id)["metadata"]["locations"]["features"]


def test_bounding_box_becomes_box_and_wkt_polygon():
    result = features_to_place(_features("23606272"))
    place = result.place
    assert place["@type"] == "Place"
    assert place["description"] == "Bounding coordinates: W -157, E -145, N 61, S 54"
    # schema.org box is "south west north east" (latitude first).
    assert place["geo"] == {"@type": "GeoShape", "box": "54 -157 61 -145"}
    geometry = place["geosparql:hasGeometry"]
    assert geometry["@type"] == "http://www.opengis.net/ont/sf#Polygon"
    # WKT is longitude first (CRS84), same ring as the GeoJSON.
    assert geometry["geosparql:asWKT"]["@value"] == "POLYGON((-157 54, -145 54, -145 61, -157 61, -157 54))"
    assert geometry["geosparql:asWKT"]["@type"] == "http://www.opengis.net/ont/geosparql#wktLiteral"
    assert geometry["geosparql:crs"]["@id"] == CRS84
    assert place["additionalProperty"]["propertyID"].endswith("Spatial_reference_system")


def test_date_line_split_stays_one_place_with_two_parts():
    result = features_to_place(_features("23201173"))
    place = result.place
    assert "date-line split: several parts kept as one Place" in result.notes
    assert place["description"] == "Bounding coordinates: W 125, E -122, N 77, S 30"
    west, east = place["geo"]
    assert west == {"@type": "GeoShape", "box": "30 125 77 180", "description": "part west of the date line"}
    assert east == {"@type": "GeoShape", "box": "30 -180 77 -122", "description": "part east of the date line"}
    geometry = place["geosparql:hasGeometry"]
    assert geometry["@type"] == "http://www.opengis.net/ont/sf#MultiPolygon"
    assert geometry["geosparql:asWKT"]["@value"] == (
        "MULTIPOLYGON(((125 30, 180 30, 180 77, 125 77, 125 30)), ((-180 30, -122 30, -122 77, -180 77, -180 30)))"
    )


def test_point_location():
    result = features_to_place(_features("23508633"))
    place = result.place
    assert place["geo"] == {"@type": "GeoCoordinates", "latitude": 0.0, "longitude": -140.0}
    assert place["geosparql:hasGeometry"]["geosparql:asWKT"]["@value"] == "POINT(-140 0)"
    assert place["geosparql:hasGeometry"]["@type"] == "http://www.opengis.net/ont/sf#Point"


def test_text_only_location_is_kept_as_text_not_parsed():
    result = features_to_place([{"description": "Bounding coordinates as given: W 10, E 350, N 80, S 70"}])
    assert result.place == {"@type": "Place", "description": "Bounding coordinates as given: W 10, E 350, N 80, S 70"}
    assert "feature without geometry kept as text only" in result.notes


def test_place_name_and_empty_cases():
    assert features_to_place([]).place is None
    assert features_to_place([{"geometry": None}]).place is None
    result = features_to_place([{"place": "Bering Sea", "geometry": {"type": "Point", "coordinates": [-170.5, 58.25]}}])
    assert result.place["name"] == "Bering Sea"
    assert result.place["geo"] == {"@type": "GeoCoordinates", "latitude": 58.25, "longitude": -170.5}


def test_non_rectangular_polygon_uses_polygon_property_in_lat_lon_order():
    ring = [[140.0, 40.0], [150.0, 42.0], [145.0, 50.0], [140.0, 40.0]]
    shape = geometry_to_geoshape({"type": "Polygon", "coordinates": [ring]})
    assert shape == {"@type": "GeoShape", "polygon": "40 140,42 150,50 145,40 140"}
    assert geometry_to_wkt({"type": "Polygon", "coordinates": [ring]}) == "POLYGON((140 40, 150 42, 145 50, 140 40))"


def test_axis_aligned_box_detection():
    assert axis_aligned_box([[-157, 54], [-145, 54], [-145, 61], [-157, 61], [-157, 54]]) == (54, -157, 61, -145)
    assert axis_aligned_box([[0, 0], [1, 1], [2, 0], [0, 0]]) is None
    # Any vertex order of a rectangle is accepted.
    assert axis_aligned_box([[-157, 61], [-157, 54], [-145, 54], [-145, 61], [-157, 61]]) == (54, -157, 61, -145)


def test_split_box_at_antimeridian():
    assert split_box_at_antimeridian(125, -122, 30, 77) == [(125, 180.0, 30, 77), (-180.0, -122, 30, 77)]
    assert split_box_at_antimeridian(-170, -160, 55, 60) == [(-170, -160, 55, 60)]
