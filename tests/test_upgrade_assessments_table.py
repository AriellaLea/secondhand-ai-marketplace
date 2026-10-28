"""scripts/upgrade_assessments_table.py adds market_price_new to an existing table (fix K)."""

from sqlalchemy import create_engine, inspect, text

from scripts.upgrade_assessments_table import upgrade


def test_upgrade_adds_the_new_price_column_and_can_run_twice(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:  # the table as it was before fix K
        connection.execute(text(
            "CREATE TABLE assessments (listing_id VARCHAR(36) PRIMARY KEY, "
            "market_price_min NUMERIC(10, 2) NOT NULL, market_price_max NUMERIC(10, 2) NOT NULL)"
        ))
        connection.execute(text("INSERT INTO assessments VALUES ('a', 400, 700)"))

    assert upgrade(engine) == ["added market_price_new"]
    assert upgrade(engine) == []

    assert "market_price_new" in {column["name"] for column in inspect(engine).get_columns("assessments")}
    with engine.connect() as connection:
        row = connection.execute(text("SELECT market_price_min, market_price_new FROM assessments")).one()
    assert (row[0], row[1]) == (400, None)  # old assessments keep their values
