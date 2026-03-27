#!/usr/bin/env bash
# dev.sh — Start all services for local development
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_RELOAD="${BACKEND_RELOAD:-1}"
WORKER_LOCK_PATH="${PROJECT_ROOT}/runtime/locks/agentic-workers-main.lock"
declare -a PIDS=()
declare -a SERVICE_PGIDS=()
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

  if ! declare -p PIDS >/dev/null 2>&1; then
    return
  fi

  for index in "${!PIDS[@]-}"; do
    local pid="${PIDS[$index]}"
    local pgid="${SERVICE_PGIDS[$index]-}"
    if [ -n "$pgid" ]; then
      kill -TERM -- "-$pgid" 2>/dev/null || true
    elif kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  local deadline=$((SECONDS + 5))
  while [ "${#PIDS[@]}" -gt 0 ] && [ "$SECONDS" -lt "$deadline" ]; do
    local remaining=()
    local remaining_pgids=()
    for index in "${!PIDS[@]-}"; do
      local pid="${PIDS[$index]}"
      if kill -0 "$pid" 2>/dev/null; then
        remaining+=("$pid")
        remaining_pgids+=("${SERVICE_PGIDS[$index]-}")
      fi
    done
    if [ "${#remaining[@]}" -gt 0 ]; then
      PIDS=("${remaining[@]}")
      SERVICE_PGIDS=("${remaining_pgids[@]}")
    else
      PIDS=()
      SERVICE_PGIDS=()
    fi
    [ "${#PIDS[@]}" -gt 0 ] && sleep 1
  done

  for index in "${!PIDS[@]-}"; do
    local pid="${PIDS[$index]}"
    local pgid="${SERVICE_PGIDS[$index]-}"
    if [ -n "$pgid" ]; then
      kill -KILL -- "-$pgid" 2>/dev/null || true
    elif kill -0 "$pid" 2>/dev/null; then
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

port_listener() {
  local port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 1
  fi

  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sed -n '2p'
}

ensure_port_available() {
  local service="$1"
  local port="$2"
  local env_var="$3"
  local listener

  listener="$(port_listener "$port" || true)"
  if [ -z "$listener" ]; then
    return
  fi

  echo "[$service] Port ${port} is already in use."
  echo "[$service] Listener: ${listener}"
  echo "[$service] Stop the existing process or set ${env_var} to a different port."
  exit 1
}

worker_lock_holder_pid() {
  if [ ! -f "$WORKER_LOCK_PATH" ]; then
    return 1
  fi

  sed -n 's/.*"pid"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$WORKER_LOCK_PATH" | head -n 1
}

worker_process_running() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

worker_process_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//'
}

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
  local use_setsid=0
  if command -v setsid >/dev/null 2>&1; then
    use_setsid=1
  fi

  (
    cd "$cwd"
    if [ "$use_setsid" -eq 1 ]; then
      exec setsid "$@"
    fi
    exec "$@"
  ) &

  local pid="$!"
  local pgid=""
  if [ "$use_setsid" -eq 1 ]; then
    pgid="$pid"
  fi

  PIDS+=("$pid")
  SERVICE_PGIDS+=("$pgid")
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

ensure_port_available frontend "$FRONTEND_PORT" FRONTEND_PORT
ensure_port_available backend "$BACKEND_PORT" BACKEND_PORT

# Frontend
if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
  echo "[frontend] Starting Next.js dev server on port ${FRONTEND_PORT}..."
  start_service frontend "$PROJECT_ROOT/frontend" npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT"
fi

# Backend
if [ -f "$PROJECT_ROOT/backend/pyproject.toml" ]; then
  echo "[backend]  Starting FastAPI server on port ${BACKEND_PORT}..."
  backend_cmd=(uv run uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT")
  if [ "$BACKEND_RELOAD" = "1" ]; then
    backend_cmd=(uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT")
  fi
  start_service backend "$PROJECT_ROOT/backend" "${backend_cmd[@]}"
fi

# Workers
if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
  existing_worker_pid="$(worker_lock_holder_pid || true)"
  if worker_process_running "$existing_worker_pid"; then
    echo "[workers] Reusing existing worker process (pid ${existing_worker_pid})."
    existing_worker_cmd="$(worker_process_command "$existing_worker_pid")"
    if [ -n "$existing_worker_cmd" ]; then
      echo "[workers] Existing process: ${existing_worker_cmd}"
    fi
  else
    echo "[workers]  Starting worker processes..."
    start_service workers "$PROJECT_ROOT/workers" uv run python -m agentic_workers.main
  fi
fi

wait_for_services
