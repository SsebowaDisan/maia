"""B4-03 — Postgres read-only query connector tool.

Tools: db.pg_list_tables, db.pg_describe_table, db.pg_query
Safety: only SELECT statements allowed; row limit enforced (max 500).
"""
from __future__ import annotations

import re
from typing import Any

_MAX_ROWS = 500
_BLOCKED_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def _connect(credentials: dict):
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        raise ImportError("psycopg2 is not installed. Run: pip install psycopg2-binary")

    return psycopg2.connect(
        host=credentials.get("host") or "localhost",
        port=int(credentials.get("port") or 5432),
        dbname=credentials.get("dbname") or credentials.get("database") or "postgres",
        user=credentials.get("username") or credentials.get("user") or "postgres",
        password=credentials.get("password") or "",
        connect_timeout=10,
    )


def _pg_list_tables(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    conn = _connect(credentials)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema') "
                "ORDER BY table_schema, table_name LIMIT 200;"
            )
            rows = cur.fetchall()
        return {"tables": [{"schema": r[0], "table": r[1]} for r in rows]}
    finally:
        conn.close()


def _pg_describe_table(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    table = str(params.get("table") or "")
    schema = str(params.get("schema") or "public")
    if not table:
        raise ValueError("db.pg_describe_table requires 'table'.")
    conn = _connect(credentials)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position;",
                (schema, table),
            )
            rows = cur.fetchall()
        return {"columns": [{"name": r[0], "type": r[1], "nullable": r[2]} for r in rows]}
    finally:
        conn.close()


def _pg_query(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    sql = str(params.get("sql") or "").strip()
    if not sql:
        raise ValueError("db.pg_query requires 'sql'.")
    if _BLOCKED_KEYWORDS.match(sql):
        raise PermissionError(
            "Only SELECT queries are allowed. "
            "Detected a write/DDL statement which is blocked for safety."
        )
    conn = _connect(credentials)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchmany(_MAX_ROWS)
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) == _MAX_ROWS,
        }
    finally:
        conn.close()


def register(registry: dict) -> None:
    registry["db.pg_list_tables"] = _pg_list_tables
    registry["db.pg_describe_table"] = _pg_describe_table
    registry["db.pg_query"] = _pg_query
