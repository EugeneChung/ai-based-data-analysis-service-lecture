#!/usr/bin/env bash
# Serve the Deli data-gateway MCP server over HTTP so it can be added via
# Claude's "Add custom connector" dialog (Remote MCP server URL).
#
#   ./serve-http.sh                 # http://127.0.0.1:8001/mcp
#   DELI_MCP_PORT=9001 ./serve-http.sh
#
# Runs on 8001 so it can sit next to deli-db-mcp (8000): one agent, two
# connectors. Requires the disposable MySQL to be running
# (../deli-db-mcp/local-mysql.sh start), or override DELI_DB_* for another DB.
set -euo pipefail
cd "$(dirname "$0")"

export DELI_DB_SOCKET="${DELI_DB_SOCKET:-/tmp/deli-mcp-mysql.sock}"
export DELI_MCP_TRANSPORT=http
export DELI_MCP_HOST="${DELI_MCP_HOST:-127.0.0.1}"
export DELI_MCP_PORT="${DELI_MCP_PORT:-8001}"
export DELI_MCP_PATH="${DELI_MCP_PATH:-/mcp}"

echo "deli-gateway MCP (http) -> http://${DELI_MCP_HOST}:${DELI_MCP_PORT}${DELI_MCP_PATH}"
exec python3 server.py
