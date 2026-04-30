from twinquery.db.geojson import bbox_from_features, highlight_ids_from_rows, rows_to_feature_collection


def test_rows_to_feature_collection_uses_geometry_json() -> None:
    rows = [
        {
            "id": 7,
            "name": "Library",
            "building_type": "library",
            "retrofit_priority_score": 81.5,
            "geometry_json": (
                '{"type":"Polygon","coordinates":[[[-75.7,45.4],[-75.69,45.4],'
                '[-75.69,45.41],[-75.7,45.41],[-75.7,45.4]]]}'
            ),
        }
    ]

    feature_collection = rows_to_feature_collection(rows)

    assert feature_collection["type"] == "FeatureCollection"
    assert feature_collection["features"][0]["id"] == 7
    assert feature_collection["features"][0]["geometry"]["type"] == "Polygon"
    assert feature_collection["features"][0]["properties"]["name"] == "Library"
    assert bbox_from_features(feature_collection["features"]) == [-75.7, 45.4, -75.69, 45.41]
    assert highlight_ids_from_rows(rows) == [7]


def test_rows_to_feature_collection_numeric_properties_are_numbers() -> None:
    rows = [
        {
            "id": "8",
            "name": "Office",
            "building_type": "office",
            "year_built": "1978",
            "floor_area_m2": "1234.5",
            "estimated_energy_intensity_kwh_m2": "245.7",
            "retrofit_priority_score": "82.1",
            "height_m": "18.5",
            "data_quality_note": "demo",
            "geometry_json": '{"type":"Point","coordinates":[-75.7,45.4]}',
        }
    ]

    properties = rows_to_feature_collection(rows)["features"][0]["properties"]

    assert isinstance(properties["year_built"], int)
    assert isinstance(properties["floor_area_m2"], float)
    assert isinstance(properties["estimated_energy_intensity_kwh_m2"], float)
    assert isinstance(properties["retrofit_priority_score"], float)
    assert isinstance(properties["height_m"], float)
