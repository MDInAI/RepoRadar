#!/usr/bin/env bash
# dev.sh — Start all services for local development
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

echo "=== Agentic-Workflow Dev Server ==="
echo ""
echo "Starting services... (Ctrl+C to stop all)"
echo "OpenClaw-native secrets stay outside frontend env files and route components."
echo ""

# Trap to kill all child processes on exit
trap 'echo ""; echo "Shutting down..."; kill 0; exit 0' INT TERM

# Frontend
if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
  echo "[frontend] Starting Next.js dev server on port ${FRONTEND_PORT:-3000}..."
  (cd "$PROJECT_ROOT/frontend" && npm run dev) &
fi

# Backend
if [ -f "$PROJECT_ROOT/backend/pyproject.toml" ]; then
  echo "[backend]  Starting FastAPI server on port ${BACKEND_PORT:-8000}..."
  (cd "$PROJECT_ROOT/backend" && uvicorn app.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT:-8000}") &
fi

# Workers
if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
  echo "[workers]  Starting worker processes..."
  (cd "$PROJECT_ROOT/workers" && python -m agentic_workers.main) &
fi

echo ""
echo "All services started. Waiting..."
wait
