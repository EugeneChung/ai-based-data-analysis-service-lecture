"""Executor — runs the rendered SQL read-only and caps the result.

Same guardrails as deli-db-mcp: a read-only transaction, a server-side
execution-time limit, and a hard row cap (fetch limit+1 to detect
truncation).
"""

from __future__ import annotations

from dataclasses import dataclass

from db import connect


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool


def execute(sql: str, *, timeout_seconds: int, limit: int) -> ExecutionResult:
    conn = connect(dict_rows=False, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(f"SET SESSION MAX_EXECUTION_TIME={int(timeout_seconds) * 1000}")
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(limit + 1)
        truncated = len(fetched) > limit
        rows = list(fetched[:limit])
        cur.close()
    finally:
        conn.close()
    return ExecutionResult(columns, rows, len(rows), truncated)
