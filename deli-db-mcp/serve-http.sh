#!/usr/bin/env bash
# Serve the Deli MCP server over HTTP so it can be added via Claude's
# "Add custom connector" dialog (Remote MCP server URL).
#
#   ./serve-http.sh                 # http://127.0.0.1:8000/mcp
#   DELI_MCP_PORT=9000 ./serve-http.sh
#
# Requires the disposable MySQL to be running (./local-mysql.sh start),
# or override DELI_DB_SOCKET / DELI_DB_HOST etc. for another DB.
set -euo pipefail
cd "$(dirname "$0")"

export DELI_DB_SOCKET="${DELI_DB_SOCKET:-/tmp/deli-mcp-mysql.sock}"
export DELI_MCP_TRANSPORT=http
export DELI_MCP_HOST="${DELI_MCP_HOST:-127.0.0.1}"
export DELI_MCP_PORT="${DELI_MCP_PORT:-8000}"
export DELI_MCP_PATH="${DELI_MCP_PATH:-/mcp}"

echo "MCP (http) -> http://${DELI_MCP_HOST}:${DELI_MCP_PORT}${DELI_MCP_PATH}"
exec python3 server.py
