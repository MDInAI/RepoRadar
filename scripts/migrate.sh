#!/usr/bin/env bash
# migrate.sh — Run Alembic database migrations
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "=== Agentic-Workflow Database Migrations ==="
echo ""

if [ ! -f "$BACKEND_DIR/alembic.ini" ]; then
  echo "ERROR: alembic.ini not found in backend/"
  exit 1
fi

cd "$BACKEND_DIR"

case "${1:-upgrade}" in
  upgrade)
    echo "Running upgrade to head..."
    alembic upgrade head
    echo "✓ Migrations applied"
    ;;
  downgrade)
    echo "Running downgrade by 1..."
    alembic downgrade -1
    echo "✓ Downgrade complete"
    ;;
  generate)
    if [ -z "${2:-}" ]; then
      echo "Usage: $0 generate <message>"
      exit 1
    fi
    echo "Generating migration: $2"
    alembic revision --autogenerate -m "$2"
    echo "✓ Migration generated"
    ;;
  *)
    echo "Usage: $0 [upgrade|downgrade|generate <message>]"
    exit 1
    ;;
esac
