#!/usr/bin/env bash
# Disposable MySQL 8.0 instance for the Deli demo.
#
# Runs a dedicated mysqld with its own datadir + socket under ./.mysql,
# so it never touches your Homebrew-managed MySQL or its data. Use this
# when the default 3306 server is unavailable or on a different version.
#
#   ./local-mysql.sh start    # init (first time) + start, prints env exports
#   ./local-mysql.sh stop
#   ./local-mysql.sh wipe      # stop + delete ./.mysql (full reset)
#
# After `start`, export the printed vars (DELI_DB_SOCKET, DELI_DB_PASSWORD)
# then run ./setup.sh and python3 server.py.
set -euo pipefail
cd "$(dirname "$0")"

BASEDIR=/opt/homebrew/opt/mysql@8.0
MYSQLD="$BASEDIR/bin/mysqld"
DIR="$PWD/.mysql"
DATADIR="$DIR/data"
SOCK="/tmp/deli-mcp-mysql.sock"   # short path: unix sockets cap at ~104 chars
PID="$DIR/mysqld.pid"
ERRLOG="$DIR/error.log"

case "${1:-start}" in
  start)
    mkdir -p "$DIR"
    if [ ! -d "$DATADIR/mysql" ]; then
      echo "==> initializing datadir (root has no password)"
      "$MYSQLD" --no-defaults --initialize-insecure \
        --basedir="$BASEDIR" --datadir="$DATADIR"
    fi
    if mysqladmin --socket="$SOCK" ping >/dev/null 2>&1; then
      echo "==> already running"
    else
      echo "==> starting mysqld"
      "$MYSQLD" --no-defaults --basedir="$BASEDIR" --datadir="$DATADIR" \
        --socket="$SOCK" --pid-file="$PID" --log-error="$ERRLOG" \
        --skip-networking --mysqlx=OFF >/dev/null 2>&1 &
      for _ in $(seq 1 30); do
        mysqladmin --socket="$SOCK" ping >/dev/null 2>&1 && break; sleep 1
      done
      mysqladmin --socket="$SOCK" ping >/dev/null 2>&1 \
        || { echo "failed to start; see $ERRLOG"; tail -20 "$ERRLOG"; exit 1; }
      echo "==> up (socket-only)"
    fi
    echo
    echo "# run these, then ./setup.sh:"
    echo "export DELI_DB_SOCKET=$SOCK"
    echo "export DELI_DB_PASSWORD="
    ;;
  stop)
    mysqladmin --socket="$SOCK" -uroot shutdown 2>/dev/null || true
    echo "==> stopped"
    ;;
  wipe)
    mysqladmin --socket="$SOCK" -uroot shutdown 2>/dev/null || true
    rm -rf "$DIR"
    echo "==> wiped $DIR"
    ;;
  *)
    echo "usage: $0 {start|stop|wipe}"; exit 1 ;;
esac
