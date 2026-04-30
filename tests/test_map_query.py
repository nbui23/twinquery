from fastapi.testclient import TestClient

from api.main import app
from twinquery.agents.map_sql import build_high_retrofit_priority_query, build_top_energy_intensity_query
from twinquery.agents.sql_agent import answer_map_query, get_buildings_geojson


GEOMETRY_JSON = (
    '{"type":"Polygon","coordinates":[[[-75.7,45.4],[-75.69,45.4],'
    '[-75.69,45.41],[-75.7,45.41],[-75.7,45.4]]]}'
)


def test_answer_map_query_returns_feature_collection() -> None:
    def fake_llm(prompt: str) -> str:
        assert "ST_AsGeoJSON(geom) AS geometry_json" in prompt
        return (
            "SELECT id, name, building_type, retrofit_priority_score, "
            "estimated_energy_intensity_kwh_m2, height_m, "
            "ST_AsGeoJSON(geom) AS geometry_json FROM buildings LIMIT 100;"
        )

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        assert "geometry_json" in sql
        return [
            {
                "id": 1,
                "name": "School A",
                "building_type": "school",
                "retrofit_priority_score": 88.0,
                "estimated_energy_intensity_kwh_m2": 260.0,
                "height_m": 12.0,
                "geometry_json": GEOMETRY_JSON,
            }
        ]

    result = answer_map_query("Show schools with high retrofit priority", fake_llm, fake_query_runner)

    assert result["geojson"]["type"] == "FeatureCollection"
    assert result["geojson"]["features"][0]["properties"]["building_type"] == "school"
    assert result["highlight_ids"] == [1]
    assert result["bbox"] == [-75.7, 45.4, -75.69, 45.41]


def test_map_api_returns_feature_collection(monkeypatch) -> None:
    def fake_answer_map_query(question: str) -> dict[str, object]:
        return {
            "question": question,
            "sql": "SELECT id, name, ST_AsGeoJSON(geom) AS geometry_json FROM buildings LIMIT 100;",
            "rows": [{"id": 1, "name": "School A", "geometry_json": GEOMETRY_JSON}],
            "geojson": {"type": "FeatureCollection", "features": []},
            "bbox": None,
            "highlight_ids": [1],
            "fallback_used": False,
            "fallback_reason": None,
            "map_metrics_available": {
                "height_m": True,
                "estimated_energy_intensity_kwh_m2": True,
                "retrofit_priority_score": True,
            },
            "error": None,
        }

    monkeypatch.setattr("api.routes.query.answer_map_query", fake_answer_map_query)
    client = TestClient(app)

    response = client.post("/query/map", json={"question": "Show schools"})

    assert response.status_code == 200
    assert response.json()["geojson"]["type"] == "FeatureCollection"
    assert response.json()["highlight_ids"] == [1]


def test_get_buildings_geojson_falls_back_for_old_schema() -> None:
    executed_sql: list[str] = []

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        executed_sql.append(sql)
        if "information_schema.columns" in sql:
            return [
                {"column_name": "id"},
                {"column_name": "name"},
                {"column_name": "building_type"},
                {"column_name": "retrofit_priority_score"},
                {"column_name": "energy_use_kwh_year"},
                {"column_name": "floor_area_m2"},
                {"column_name": "geom"},
            ]
        assert "energy_use_kwh_year / NULLIF(floor_area_m2, 0)" in sql
        assert "0::numeric AS height_m" in sql
        return [
            {
                "id": 1,
                "source_id": None,
                "name": "Legacy Point Building",
                "building_type": "office",
                "retrofit_priority_score": 55.0,
                "estimated_energy_intensity_kwh_m2": 180.0,
                "height_m": 0.0,
                "geometry_json": '{"type":"Point","coordinates":[-75.7,45.4]}',
            }
        ]

    result = get_buildings_geojson(query_runner=fake_query_runner)

    assert result["error"] is None
    assert result["geojson"]["type"] == "FeatureCollection"
    assert result["geojson"]["features"][0]["geometry"]["type"] == "Point"
    assert len(executed_sql) == 2


def test_answer_map_query_retries_with_legacy_columns() -> None:
    calls: list[str] = []

    def fake_llm(prompt: str) -> str:
        return (
            "SELECT id, name, estimated_energy_intensity_kwh_m2, height_m, "
            "ST_AsGeoJSON(geom) AS geometry_json FROM buildings LIMIT 100;"
        )

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        calls.append(sql)
        if "information_schema.columns" in sql:
            return [
                {"column_name": "id"},
                {"column_name": "name"},
                {"column_name": "building_type"},
                {"column_name": "retrofit_priority_score"},
                {"column_name": "energy_use_kwh_year"},
                {"column_name": "floor_area_m2"},
                {"column_name": "geom"},
            ]
        if "estimated_energy_intensity_kwh_m2, height_m" in sql:
            raise RuntimeError('column "estimated_energy_intensity_kwh_m2" does not exist')
        return [
            {
                "id": 2,
                "source_id": None,
                "name": "Legacy School",
                "building_type": "school",
                "retrofit_priority_score": 75.0,
                "estimated_energy_intensity_kwh_m2": 210.0,
                "height_m": 0.0,
                "geometry_json": GEOMETRY_JSON,
            }
        ]

    result = answer_map_query("Show schools", fake_llm, fake_query_runner)

    assert result["error"] is None
    assert result["highlight_ids"] == [2]
    assert "energy_use_kwh_year / NULLIF(floor_area_m2, 0)" in result["sql"]
    assert len(calls) == 3


def test_deterministic_map_sql_includes_geometry_and_limit() -> None:
    sql = build_top_energy_intensity_query(limit=20)

    assert "ST_AsGeoJSON(geom) AS geometry_json" in sql
    assert "LIMIT 20" in sql


def test_deterministic_map_sql_clamps_limit() -> None:
    sql = build_high_retrofit_priority_query(limit=500)

    assert "ST_AsGeoJSON(geom) AS geometry_json" in sql
    assert "LIMIT 100" in sql


def test_answer_map_query_fallbacks_when_geometry_json_missing() -> None:
    calls: list[str] = []

    def fake_llm(prompt: str) -> str:
        return "SELECT id, name FROM buildings LIMIT 25;"

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        calls.append(sql)
        assert "ST_AsGeoJSON(geom) AS geometry_json" in sql
        return [
            {
                "id": 3,
                "name": "High EUI Building",
                "building_type": "office",
                "year_built": 1970,
                "floor_area_m2": 1000.0,
                "retrofit_priority_score": 90.0,
                "estimated_energy_intensity_kwh_m2": 300.0,
                "height_m": 20.0,
                "data_quality_note": "demo",
                "geometry_json": GEOMETRY_JSON,
            }
        ]

    result = answer_map_query("Show highest energy intensity buildings", fake_llm, fake_query_runner)

    assert result["fallback_used"] is True
    assert "geometry_json" in str(result["fallback_reason"])
    assert result["highlight_ids"] == [3]
    assert len(calls) == 1
