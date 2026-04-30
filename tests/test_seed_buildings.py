def test_seed_script_imports_without_running() -> None:
    from twinquery.db import seed_buildings

    buildings = seed_buildings.generate_buildings(count=3)

    assert len(buildings) == 3
    assert buildings[0]["name"].startswith("Synthetic ")

