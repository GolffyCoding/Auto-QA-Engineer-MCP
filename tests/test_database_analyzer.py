"""Unit tests for qa_mcp.analyzers.database_analyzer - runs against a real
throwaway SQLite database (no mocks needed, SQLAlchemy+sqlite3 are already
hard dependencies of this project). Covers the two things this analyzer
exists for: finding real orphaned foreign keys, and blocking SQL injection
through table/column identifiers.
"""
import sqlite3

import pytest

from qa_mcp.analyzers.database_analyzer import DatabaseAnalyzer


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER);
        INSERT INTO users (id, name) VALUES (1, 'alice'), (2, 'bob');
        INSERT INTO orders (id, user_id) VALUES (1, 1), (2, 2), (3, 999);
        """
    )
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def analyzer(db_path):
    return DatabaseAnalyzer(f"sqlite:///{db_path}")


@pytest.mark.asyncio
async def test_get_table_state_returns_real_row_count_and_columns(analyzer):
    state = await analyzer.get_table_state("users")
    assert state["row_count"] == 2
    assert set(state["columns"]) == {"id", "name"}
    assert len(state["sample_rows"]) == 2


@pytest.mark.asyncio
async def test_get_table_state_reports_missing_table(analyzer):
    state = await analyzer.get_table_state("does_not_exist")
    assert "error" in state
    assert state["row_count"] == 0


@pytest.mark.asyncio
async def test_check_fk_integrity_finds_real_orphaned_reference(analyzer):
    result = await analyzer.check_fk_integrity("orders", "user_id", "users", "id")
    assert result["invalid_references"] == 1
    assert result["status"] == "broken"


@pytest.mark.asyncio
async def test_check_fk_integrity_reports_ok_when_no_orphans(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM orders WHERE user_id = 999")
    conn.commit()
    conn.close()

    analyzer = DatabaseAnalyzer(f"sqlite:///{db_path}")
    result = await analyzer.check_fk_integrity("orders", "user_id", "users", "id")
    assert result["invalid_references"] == 0
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_query_rejects_non_select_statements(analyzer):
    with pytest.raises(ValueError):
        await analyzer.query("DROP TABLE users")


@pytest.mark.asyncio
async def test_query_runs_real_select(analyzer):
    result = await analyzer.query("SELECT name FROM users WHERE id = :id", {"id": 1})
    assert result["row_count"] == 1
    assert result["rows"][0]["name"] == "alice"


@pytest.mark.asyncio
async def test_get_table_state_blocks_sql_injection_via_table_name(analyzer):
    with pytest.raises(ValueError):
        await analyzer.get_table_state('users"; DROP TABLE users; --')


@pytest.mark.asyncio
async def test_check_fk_integrity_blocks_sql_injection_via_column_name(analyzer):
    with pytest.raises(ValueError):
        await analyzer.check_fk_integrity("orders", 'user_id"; DROP TABLE orders; --', "users", "id")
