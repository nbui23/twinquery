def test_ingestion_module_imports_cleanly() -> None:
    from twinquery.db import ingest_buildings_geo
    from twinquery.db import ingest_ottawa_footprints

    assert callable(ingest_buildings_geo.ingest_buildings_geo)
    assert callable(ingest_ottawa_footprints.ingest_ottawa_footprints)
