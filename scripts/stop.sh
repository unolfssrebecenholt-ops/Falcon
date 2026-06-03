#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HOST="127.0.0.1"
PORT="8765"
PID_FILE="$PROJECT_ROOT/runtime/falcon-web.pid"
URL_FILE="$PROJECT_ROOT/runtime/falcon-web.url"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --pid-file)
      PID_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  echo "Stopping Falcon web process $pid"
  kill "$pid" 2>/dev/null || true
  for _ in {1..30}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  echo "Falcon web process $pid did not exit; forcing stop"
  kill -9 "$pid" 2>/dev/null || true
}

STOPPED=0
if [[ -f "$PID_FILE" ]]; then
  PID="$(tr -d '[:space:]' < "$PID_FILE")"
  if stop_pid "$PID"; then
    STOPPED=1
  fi
  rm -f "$PID_FILE"
fi

while IFS= read -r PID; do
  [[ -z "$PID" ]] && continue
  if ps -p "$PID" -o command= | grep -Eq "falcon .*web|falcon.*--host .*--port"; then
    stop_pid "$PID" || true
    STOPPED=1
  fi
done < <(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

if [[ "$STOPPED" -eq 0 ]]; then
  echo "No Falcon web process found on ${HOST}:${PORT}"
else
  rm -f "$URL_FILE"
  echo "Falcon web stopped."
fi
