"""Shared MySQL connection config for the Deli Text-to-SQL demo.

Reads connection settings from environment variables so the same code
works for the seeder and the MCP server. Defaults target a local
Homebrew MySQL with the default root user and no password.
"""

import os

import pymysql
from pymysql.cursors import DictCursor


def db_config() -> dict:
    cfg: dict[str, object] = {
        "user": os.environ.get("DELI_DB_USER", "root"),
        "password": os.environ.get("DELI_DB_PASSWORD", ""),
        "database": os.environ.get("DELI_DB_NAME", "deli"),
        "charset": "utf8mb4",
    }
    # Prefer a unix socket when given (used by the disposable local instance);
    # otherwise connect over TCP host/port.
    socket = os.environ.get("DELI_DB_SOCKET")
    if socket:
        cfg["unix_socket"] = socket
    else:
        cfg["host"] = os.environ.get("DELI_DB_HOST", "127.0.0.1")
        cfg["port"] = int(os.environ.get("DELI_DB_PORT", "3306"))
    return cfg


def connect(dict_rows: bool = False, autocommit: bool = True):
    cfg = db_config()
    if dict_rows:
        cfg["cursorclass"] = DictCursor
    cfg["autocommit"] = autocommit
    return pymysql.connect(**cfg)
