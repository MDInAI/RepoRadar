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

# Backend
echo "[2/3] Installing backend dependencies..."
if [ -f "$PROJECT_ROOT/backend/pyproject.toml" ]; then
  (cd "$PROJECT_ROOT/backend" && pip install -e ".[dev]" 2>/dev/null || pip install -e .)
  echo "  ✓ Backend dependencies installed"
else
  echo "  ⚠ backend/pyproject.toml not found — skipping"
fi

# Workers
echo "[3/3] Installing worker dependencies..."
if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
  (cd "$PROJECT_ROOT/workers" && pip install -e ".[dev]" 2>/dev/null || pip install -e .)
  echo "  ✓ Worker dependencies installed"
else
  echo "  ⚠ workers/pyproject.toml not found — skipping"
fi

echo ""
echo "Copy the example env files for backend/workers as needed."
echo "Keep OpenClaw-owned secrets in ~/.openclaw/openclaw.json or local shell env."
echo "=== Bootstrap complete ==="
