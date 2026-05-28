"""Deli Text-to-SQL — read-only MySQL MCP server (FastMCP).

Exposes the simulated Deli database to an LLM as MCP tools. The query
tool is SELECT-only: it rejects anything that is not a single read
statement, runs inside a read-only transaction, caps execution time,
and caps returned rows. Intended to be paired with
deli-simple-text2sql-system-prompt.md.

Run (stdio):  python3 server.py
Register:     claude mcp add deli-sql -- python3 /abs/path/to/server.py
"""

import os
import re

from fastmcp import FastMCP

from db import connect

mcp = FastMCP(name="deli-sql")

MAX_ROWS = 200
MAX_EXEC_MS = 5000

# statements that must never run through this server
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|"
    r"grant|revoke|call|load|handler|lock|unlock|set|use|rename|"
    r"into\s+outfile|into\s+dumpfile)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(--[^\n]*|#[^\n]*)")


def _strip(sql: str) -> str:
    return _LINE_COMMENT.sub("", _COMMENT.sub("", sql)).strip()


def _validate(sql: str) -> str:
    """Return cleaned SQL or raise ValueError if not a single SELECT."""
    clean = _strip(sql)
    if not clean:
        raise ValueError("empty query")
    body = clean.rstrip(";").strip()
    if ";" in body:
        raise ValueError("only a single statement is allowed (no ';')")
    if not re.match(r"^(select|with)\b", body, re.IGNORECASE):
        raise ValueError("only SELECT / WITH queries are allowed")
    if _FORBIDDEN.search(body):
        raise ValueError("query contains a forbidden (write/DDL) keyword")
    return body


def _render(columns, rows) -> str:
    if not columns:
        return "(no result)"
    if not rows:
        return "columns: " + ", ".join(columns) + "\n(0 rows)"

    def cell(v):
        s = "NULL" if v is None else str(v)
        return s if len(s) <= 60 else s[:57] + "..."

    cols = list(columns)
    widths = [len(c) for c in cols]
    srows = []
    for r in rows:
        sr = [cell(v) for v in r]
        srows.append(sr)
        for i, s in enumerate(sr):
            widths[i] = max(widths[i], len(s))
    head = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    sep = "-+-".join("-" * widths[i] for i in range(len(cols)))
    lines = [head, sep]
    lines += [" | ".join(s.ljust(widths[i]) for i, s in enumerate(sr)) for sr in srows]
    return "\n".join(lines)


@mcp.tool
def run_select(sql: str, max_rows: int = MAX_ROWS) -> str:
    """Run a single read-only SELECT/WITH query against the Deli MySQL
    database and return the result as a text table.

    Only SELECT and WITH queries are permitted; any write or DDL is
    rejected. At most `max_rows` rows are returned (hard cap 1000).
    Use MySQL 8 dialect (DATE_SUB, INTERVAL, DATE_FORMAT, LIMIT).
    """
    try:
        body = _validate(sql)
    except ValueError as e:
        return f"ERROR: {e}"

    limit = max(1, min(int(max_rows), 1000))
    conn = connect(dict_rows=False, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(f"SET SESSION MAX_EXECUTION_TIME={MAX_EXEC_MS}")
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute(body)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit + 1)
        truncated = len(rows) > limit
        rows = rows[:limit]
        cur.close()
    except Exception as e:  # surface DB errors back to the model
        return f"SQL ERROR: {e}"
    finally:
        conn.close()

    out = _render(columns, rows)
    note = f"\n\n({len(rows)} row(s)" + (f", truncated at {limit}" if truncated else "") + ")"
    return out + note


@mcp.tool
def list_tables() -> str:
    """List the tables in the Deli database with their row-count estimate
    and table comment."""
    conn = connect(dict_rows=False, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return _render(["table", "approx_rows", "comment"], rows)


@mcp.tool
def describe_table(table: str) -> str:
    """Show CREATE TABLE for one Deli table, including column COMMENTs and
    indexes. Use this to learn the exact columns and value domains before
    writing a query."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        return "ERROR: invalid table name"
    conn = connect(dict_rows=False, autocommit=True)
    try:
        cur = conn.cursor()
        try:
            cur.execute(f"SHOW CREATE TABLE `{table}`")
            row = cur.fetchone()
        except Exception as e:
            return f"SQL ERROR: {e}"
        cur.close()
    finally:
        conn.close()
    return row[1] if row else f"ERROR: table '{table}' not found"


@mcp.tool
def get_schema() -> str:
    """Return CREATE TABLE for every Deli table (full schema with COMMENTs).
    Feed this to the model as context for Text-to-SQL."""
    conn = connect(dict_rows=False, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
        )
        names = [r[0] for r in cur.fetchall()]
        ddls = []
        for n in names:
            cur.execute(f"SHOW CREATE TABLE `{n}`")
            ddls.append(cur.fetchone()[1])
        cur.close()
    finally:
        conn.close()
    return "\n\n".join(ddls)


if __name__ == "__main__":
    # stdio by default (Claude Desktop config-file route). Set
    # DELI_MCP_TRANSPORT=http to expose a URL for the "Add custom
    # connector" dialog: http://{host}:{port}{path}
    if os.environ.get("DELI_MCP_TRANSPORT") == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("DELI_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("DELI_MCP_PORT", "8000")),
            path=os.environ.get("DELI_MCP_PATH", "/mcp"),
        )
    else:
        mcp.run()
