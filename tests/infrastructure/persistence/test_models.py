from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from src.infrastructure.persistence.models import Base

EXPECTED_TABLES = {
    "teams",
    "leagues",
    "bookmakers",
    "matches",
    "odds_quotes",
    "team_forms",
    "value_bets",
}


def test_metadata_registers_every_expected_table() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


async def test_create_all_creates_every_expected_table_in_the_database(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())

    assert set(table_names) == EXPECTED_TABLES


def _indexed_column_names(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    names: set[str] = set()
    for index in table.indexes:
        names.update(column.name for column in index.columns)
    return names


def test_frequently_queried_columns_are_indexed() -> None:
    assert "kickoff_utc" in _indexed_column_names("matches")
    assert "match_id" in _indexed_column_names("odds_quotes")
    assert "bookmaker_id" in _indexed_column_names("odds_quotes")
    assert "match_id" in _indexed_column_names("value_bets")
    assert "team_id" in _indexed_column_names("team_forms")


def test_bookmaker_name_is_unique() -> None:
    table = Base.metadata.tables["bookmakers"]
    assert table.columns["name"].unique or any(
        "name" in constraint.columns for constraint in table.constraints if hasattr(constraint, "columns")
    )
