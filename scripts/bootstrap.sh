#!/usr/bin/env bash
# bootstrap.sh — Install dependencies for all services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Agentic-Workflow Bootstrap ==="
echo ""

# Frontend
echo "[1/3] Installing frontend dependencies..."
if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
  (cd "$PROJECT_ROOT/frontend" && npm install)
  echo "  ✓ Frontend dependencies installed"
else
  echo "  ⚠ frontend/ not found or missing package.json — skipping"
fi

# Backend (uses uv — same as dev.sh / migrate.sh)
echo "[2/3] Installing backend dependencies..."
if [ -f "$PROJECT_ROOT/backend/pyproject.toml" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "  ✗ uv is required for backend. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
  (cd "$PROJECT_ROOT/backend" && uv sync --extra dev)
  echo "  ✓ Backend dependencies installed"
else
  echo "  ⚠ backend/pyproject.toml not found — skipping"
fi

# Workers (uses uv — same as dev.sh)
echo "[3/3] Installing worker dependencies..."
if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "  ✗ uv is required for workers. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
  (cd "$PROJECT_ROOT/workers" && uv sync --extra dev)
  echo "  ✓ Worker dependencies installed"
else
  echo "  ⚠ workers/pyproject.toml not found — skipping"
fi

echo ""
echo "Copy the example env files for backend/workers as needed."
echo "Keep OpenClaw-owned secrets in ~/.openclaw/openclaw.json or local shell env."
echo "=== Bootstrap complete ==="
