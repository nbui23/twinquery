from twinquery.agents.validator import validate_readonly_sql, validate_sql


def test_validate_allows_single_select() -> None:
    is_valid, error = validate_sql("SELECT id, name FROM buildings LIMIT 10;")
    assert is_valid is True
    assert error is None


def test_validate_allows_readonly_cte() -> None:
    sql = """
    WITH high_priority AS (
        SELECT id, name FROM buildings WHERE retrofit_priority_score > 70 LIMIT 25
    )
    SELECT id, name FROM high_priority LIMIT 25;
    """
    is_valid, message = validate_readonly_sql(sql)
    assert is_valid is True
    assert message == "SQL is read-only and safe to execute."


def test_validate_blocks_mutation() -> None:
    is_valid, error = validate_sql("DROP TABLE buildings;")
    assert is_valid is False
    assert error is not None


def test_validate_blocks_destructive_keywords_inside_select() -> None:
    is_valid, error = validate_sql("SELECT id FROM buildings WHERE notes = 'drop table' LIMIT 10;")
    assert is_valid is False
    assert error == "Destructive or unsafe SQL keyword blocked: drop."


def test_validate_blocks_multiple_statements() -> None:
    is_valid, error = validate_sql("SELECT * FROM buildings LIMIT 5; SELECT * FROM users LIMIT 5;")
    assert is_valid is False
    assert error == "Multiple SQL statements are not allowed."


def test_validate_blocks_comments() -> None:
    is_valid, error = validate_sql("SELECT id FROM buildings LIMIT 10; -- DROP TABLE buildings")
    assert is_valid is False
    assert error == "SQL comments are not allowed."


def test_validate_requires_limit_for_non_aggregate() -> None:
    is_valid, error = validate_sql("SELECT id, name FROM buildings;")
    assert is_valid is False
    assert error == "Non-aggregate SELECT queries must include LIMIT."


def test_validate_allows_aggregate_without_limit() -> None:
    is_valid, error = validate_sql("SELECT building_type, AVG(energy_use_kwh_year) FROM buildings GROUP BY building_type;")
    assert is_valid is True
    assert error is None


def test_validate_allows_postgis_functions() -> None:
    sql = """
    SELECT id, name
    FROM buildings
    WHERE ST_DWithin(centroid::geography, ST_SetSRID(ST_MakePoint(-75.6972, 45.4215), 4326)::geography, 3000)
    LIMIT 25;
    """
    is_valid, error = validate_sql(sql)
    assert is_valid is True
    assert error is None
