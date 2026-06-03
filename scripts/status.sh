#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HOST="127.0.0.1"
PORT="8765"
PID_FILE="$PROJECT_ROOT/runtime/falcon-web.pid"
URL_FILE="$PROJECT_ROOT/runtime/falcon-web.url"
LOG_FILE="$PROJECT_ROOT/runtime/falcon-web.log"

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

URL="http://${HOST}:${PORT}"
if [[ -f "$URL_FILE" ]]; then
  URL_TEXT="$(tr -d '[:space:]' < "$URL_FILE")"
  if [[ -n "$URL_TEXT" ]]; then
    URL="$URL_TEXT"
  fi
fi

PID=""
PID_RUNNING=0
if [[ -f "$PID_FILE" ]]; then
  PID="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    PID_RUNNING=1
  fi
fi

LISTEN_PIDS="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
HTTP_STATUS=""
if command -v curl >/dev/null 2>&1; then
  HTTP_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null || true)"
fi

echo "Falcon web status"
echo "- URL: $URL"
echo "- PID file: $PID_FILE"
if [[ -n "$PID" ]]; then
  if [[ "$PID_RUNNING" -eq 1 ]]; then
    echo "- PID: $PID running"
  else
    echo "- PID: $PID not running"
  fi
else
  echo "- PID: none"
fi
if [[ -n "$LISTEN_PIDS" ]]; then
  echo "- Listening on port $PORT: $LISTEN_PIDS"
else
  echo "- Listening on port $PORT: no"
fi
if [[ -n "$HTTP_STATUS" && "$HTTP_STATUS" != "000" ]]; then
  echo "- HTTP: $HTTP_STATUS"
else
  echo "- HTTP: no response"
fi
echo "- Log: $LOG_FILE"

if [[ "$HTTP_STATUS" =~ ^[23][0-9][0-9]$ ]]; then
  exit 0
fi
exit 1
