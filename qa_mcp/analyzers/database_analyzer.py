"""
Analyzer: Database State Analysis
ตรวจสอบ database state จริงผ่าน SQLAlchemy (รองรับ Postgres/MySQL/SQLite/...
ตาม connection_string ที่ SQLAlchemy รองรับ) - ใช้เพื่อ verify ข้อมูลหลังทำ
E2E test เช่น เช็คว่า record ถูกสร้างจริงในระบบหลัง submit form, หรือหา
orphaned foreign key ที่เป็นสาเหตุของ failure
"""
import asyncio
import re
from typing import Dict, List, Optional, Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """กัน SQL injection ผ่านชื่อ table/column - อนุญาตแค่ alnum+underscore"""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid identifier: {name!r} (ต้องเป็นตัวอักษร/ตัวเลข/underscore เท่านั้น)")
    return name


class DatabaseAnalyzer:
    """วิเคราะห์ database state ผ่าน SQLAlchemy - รัน query จริง ไม่ใช่ค่าคงที่"""

    # cache engine ต่อ connection_string ในโปรเซสเดียวกัน กัน reconnect ทุกครั้ง
    _engines: Dict[str, Engine] = {}

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        if connection_string not in DatabaseAnalyzer._engines:
            DatabaseAnalyzer._engines[connection_string] = create_engine(connection_string)
        self._engine = DatabaseAnalyzer._engines[connection_string]

    async def get_table_state(self, table: str, limit: int = 10) -> Dict[str, Any]:
        """ดึง state ของ table จริง: row count, columns, sample rows"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_table_state_sync, table, limit)

    def _get_table_state_sync(self, table: str, limit: int) -> Dict[str, Any]:
        _validate_identifier(table)
        inspector = inspect(self._engine)
        if table not in inspector.get_table_names():
            return {"table": table, "error": f"Table '{table}' not found", "row_count": 0, "sample_rows": [], "columns": []}

        columns = [c["name"] for c in inspector.get_columns(table)]
        with self._engine.connect() as conn:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            rows = conn.execute(text(f'SELECT * FROM "{table}" LIMIT :limit'), {"limit": limit}).mappings().all()

        return {
            "table": table,
            "row_count": count,
            "columns": columns,
            "sample_rows": [dict(r) for r in rows],
        }

    async def check_fk_integrity(
        self, table: str, fk_column: str, ref_table: str, ref_column: str = "id"
    ) -> Dict[str, Any]:
        """ตรวจสอบ foreign key integrity จริง: หา orphaned reference และ NULL FK"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._check_fk_sync, table, fk_column, ref_table, ref_column
        )

    def _check_fk_sync(self, table: str, fk_column: str, ref_table: str, ref_column: str) -> Dict[str, Any]:
        for identifier in (table, fk_column, ref_table, ref_column):
            _validate_identifier(identifier)

        with self._engine.connect() as conn:
            null_count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE "{fk_column}" IS NULL')
            ).scalar()
            orphan_sql = (
                f'SELECT COUNT(*) FROM "{table}" t '
                f'LEFT JOIN "{ref_table}" r ON t."{fk_column}" = r."{ref_column}" '
                f'WHERE t."{fk_column}" IS NOT NULL AND r."{ref_column}" IS NULL'
            )
            orphan_count = conn.execute(text(orphan_sql)).scalar()

        return {
            "table": table,
            "fk_column": fk_column,
            "ref_table": ref_table,
            "ref_column": ref_column,
            "invalid_references": orphan_count,
            "null_values": null_count,
            "status": "ok" if orphan_count == 0 else "broken",
        }

    async def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """รัน SELECT ตรง ๆ (read-only เท่านั้น) สำหรับกรณีที่ query ที่มีไม่พอ"""
        if not sql.strip().lower().startswith("select"):
            raise ValueError("db.query รองรับเฉพาะ SELECT statement (read-only) เท่านั้น")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._query_sync, sql, params or {})

    def _query_sync(self, sql: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.mappings().all()
        return {"row_count": len(rows), "rows": [dict(r) for r in rows]}


# MCP Tools
async def db_get_table_state(connection_string: str, table: str, limit: int = 10) -> Dict[str, Any]:
    """MCP tool: db.get_table_state"""
    analyzer = DatabaseAnalyzer(connection_string)
    return await analyzer.get_table_state(table, limit)


async def db_check_fk_integrity(
    connection_string: str, table: str, fk_column: str, ref_table: str, ref_column: str = "id"
) -> Dict[str, Any]:
    """MCP tool: db.check_fk_integrity"""
    analyzer = DatabaseAnalyzer(connection_string)
    return await analyzer.check_fk_integrity(table, fk_column, ref_table, ref_column)


async def db_query(connection_string: str, sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """MCP tool: db.query - รัน SELECT ตรง ๆ (read-only)"""
    analyzer = DatabaseAnalyzer(connection_string)
    return await analyzer.query(sql, params)
