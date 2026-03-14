#!/usr/bin/env bash
# dev.sh — Start all services for local development
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
declare -a PIDS=()
declare -a SERVICE_NAMES=()
SHUTTING_DOWN=0

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

stop_services() {
  if [ "$SHUTTING_DOWN" -eq 1 ]; then
    return
  fi

  SHUTTING_DOWN=1
  echo ""
  echo "Shutting down..."

  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  local deadline=$((SECONDS + 5))
  while [ "${#PIDS[@]}" -gt 0 ] && [ "$SECONDS" -lt "$deadline" ]; do
    local remaining=()
    for pid in "${PIDS[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        remaining+=("$pid")
      fi
    done
    PIDS=("${remaining[@]}")
    [ "${#PIDS[@]}" -gt 0 ] && sleep 1
  done

  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

handle_signal() {
  stop_services
  exit 0
}

trap handle_signal INT TERM
trap stop_services EXIT

run_migrations() {
  echo "Running database migrations..."
  "$SCRIPT_DIR/migrate.sh" upgrade || {
    echo "Migration failed - check DATABASE_URL and migration files"
    exit 1
  }
}

start_service() {
  local name="$1"
  local cwd="$2"
  shift 2

  if [ ! -d "$cwd" ]; then
    echo "[$name] Skipping missing directory: $cwd"
    return
  fi

  echo "[$name] Starting..."
  (
    cd "$cwd"
    exec "$@"
  ) &

  PIDS+=("$!")
  SERVICE_NAMES+=("$name")
}

wait_for_services() {
  if [ "${#PIDS[@]}" -eq 0 ]; then
    echo "No services were started."
    exit 1
  fi

  echo ""
  echo "All services started. Waiting..."

  while true; do
    for index in "${!PIDS[@]}"; do
      local pid="${PIDS[$index]}"
      if ! kill -0 "$pid" 2>/dev/null; then
        local status=0
        if ! wait "$pid"; then
          status=$?
        fi

        if [ "$SHUTTING_DOWN" -eq 1 ]; then
          return
        fi

        local name="${SERVICE_NAMES[$index]}"
        if [ "$status" -eq 0 ]; then
          echo "[$name] exited unexpectedly."
          exit 1
        fi

        echo "[$name] exited with status $status."
        exit "$status"
      fi
    done

    sleep 1
  done
}

echo "=== Agentic-Workflow Dev Server ==="
echo ""
echo "Starting services... (Ctrl+C to stop all)"
echo "OpenClaw-native secrets stay outside frontend env files and route components."
echo ""

run_migrations

# Frontend
if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
  echo "[frontend] Starting Next.js dev server on port ${FRONTEND_PORT}..."
  start_service frontend "$PROJECT_ROOT/frontend" npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT"
fi

# Backend
if [ -f "$PROJECT_ROOT/backend/pyproject.toml" ]; then
  echo "[backend]  Starting FastAPI server on port ${BACKEND_PORT}..."
  start_service backend "$PROJECT_ROOT/backend" uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
fi

# Workers
if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
  echo "[workers]  Starting worker processes..."
  start_service workers "$PROJECT_ROOT/workers" uv run python -m agentic_workers.main
fi

wait_for_services
