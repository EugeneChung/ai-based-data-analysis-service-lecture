#!/usr/bin/env bash
# Bootstrap the local Deli demo: start MySQL, create DB, load schema, seed data.
# Idempotent — re-running re-seeds from scratch.
set -euo pipefail
cd "$(dirname "$0")"

DB="${DELI_DB_NAME:-deli}"
USER="${DELI_DB_USER:-root}"
PASS="${DELI_DB_PASSWORD:-}"
SOCK="${DELI_DB_SOCKET:-}"

# build mysql client connection flags (socket if provided, else host/port)
CONN=(-u"$USER")
[ -n "$PASS" ] && CONN+=(-p"$PASS")
if [ -n "$SOCK" ]; then
  CONN+=(--socket="$SOCK")
else
  CONN+=(-h"${DELI_DB_HOST:-127.0.0.1}" -P"${DELI_DB_PORT:-3306}")
fi

if [ -z "$SOCK" ]; then
  echo "==> ensuring MySQL is running"
  if ! mysqladmin ping --silent 2>/dev/null; then
    brew services start mysql 2>/dev/null || brew services start mysql@8.0
    for _ in $(seq 1 30); do mysqladmin ping --silent 2>/dev/null && break; sleep 1; done
  fi
else
  echo "==> using socket $SOCK"
fi

echo "==> creating database '$DB'"
mysql "${CONN[@]}" -e \
  "CREATE DATABASE IF NOT EXISTS \`$DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "==> applying schema"
mysql "${CONN[@]}" "$DB" < schema.sql

echo "==> installing python deps"
python3 -m pip install -q -r requirements.txt

echo "==> seeding data"
python3 seed.py

echo "==> done. Register the MCP server with:"
echo "    claude mcp add deli-sql -- python3 $(pwd)/server.py"
