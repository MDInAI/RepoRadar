# Agentic-Workflow Deployment Guide

## Overview

Agentic-Workflow is a local-first orchestration dashboard for intelligent repository discovery, analysis, and idea synthesis. It integrates with OpenClaw Gateway to provide multi-agent workflow capabilities.

## Architecture

The system consists of three main components:

1. **Frontend** - Next.js dashboard (port 3000)
2. **Backend** - FastAPI control-plane API (port 8000)
3. **Workers** - Python background processes for agent tasks

**Integration Flow**: `Frontend → Backend → OpenClaw Gateway`

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm or yarn
- OpenClaw Gateway running and configured
- `uv` Python package manager (recommended)

## Quick Start

### 1. Initial Setup

```bash
cd workspace/agentic-workflow

# Copy environment configuration
cp .env.example .env

# Edit .env with your settings
nano .env
```

### 2. Configure Environment

Edit `.env` and set:

```bash
# Service ports
FRONTEND_PORT=3000
BACKEND_PORT=8000

# Database (SQLite by default)
DATABASE_URL=sqlite:///../runtime/data/sqlite/agentic_workflow.db

# Runtime directories
AGENTIC_RUNTIME_DIR=../runtime
OPENCLAW_WORKSPACE_DIR=/path/to/your/openclaw/workspace
OPENCLAW_CONFIG_PATH=~/.openclaw/openclaw.json

# GitHub provider (optional)
GITHUB_PROVIDER_TOKEN=your_github_token_here
GITHUB_REQUESTS_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
```

### 3. Install Dependencies

```bash
./scripts/bootstrap.sh
```

This installs:
- Frontend dependencies (npm)
- Backend dependencies (Python)
- Worker dependencies (Python)

### 4. Run Database Migrations

```bash
./scripts/migrate.sh
```

### 5. Start All Services

```bash
./scripts/dev.sh
```

This starts:
- Frontend at http://localhost:3000
- Backend API at http://localhost:8000
- Worker processes in background

Press `Ctrl+C` to stop all services.

## OpenClaw Gateway Integration

### Configuration Requirements

Agentic-Workflow reads OpenClaw Gateway configuration from `~/.openclaw/openclaw.json`. Ensure this file contains:

```json
{
  "gateway": {
    "url": "http://localhost:8080",
    "auth": {
      "token": "your-gateway-token"
    }
  },
  "agents": {
    "defaults": {
      "model": "claude-opus-4"
    }
  }
}
```

### Gateway Endpoints Used

The backend communicates with Gateway via:
- `/api/v1/gateway/contract` - Integration contract
- `/api/v1/gateway/runtime` - Runtime status
- `/api/v1/gateway/sessions` - Session management
- `/api/v1/gateway/events/envelope` - Real-time events

### Multi-Agent Runtime

The system supports multiple named agents:
- **Overlord** - Orchestration and coordination
- **Firehose** - Real-time repository intake
- **Backfill** - Historical data processing
- **Bouncer** - Repository filtering and triage
- **Analyst** - Repository analysis
- **Combiner** - (Reserved for future)
- **Obsession** - (Reserved for future)

## Accessing the Application

Once running:

- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Project Structure

```
agentic-workflow/
├── frontend/          # Next.js dashboard
│   ├── src/
│   │   ├── app/      # App Router pages
│   │   └── components/
│   └── package.json
├── backend/           # FastAPI API
│   ├── app/
│   │   ├── api/      # Route handlers
│   │   ├── core/     # Core utilities
│   │   ├── models/   # Database models
│   │   ├── schemas/  # Pydantic schemas
│   │   └── services/ # Business logic
│   ├── migrations/   # Alembic migrations
│   └── pyproject.toml
├── workers/           # Background workers
│   ├── agentic_workers/
│   │   ├── core/     # Worker core
│   │   ├── jobs/     # Job definitions
│   │   ├── schedulers/
│   │   └── providers/
│   └── pyproject.toml
├── docs/              # Documentation
├── scripts/           # Operational scripts
└── runtime/           # Generated data (gitignored)
```

## Configuration Ownership

### OpenClaw Owns
- `~/.openclaw/openclaw.json` - Gateway auth, channels, model defaults
- Agent definitions and session management

### Agentic-Workflow Owns
- Local runtime paths (`DATABASE_URL`, `AGENTIC_RUNTIME_DIR`)
- Provider credentials (`GITHUB_PROVIDER_TOKEN`)
- Pacing/rate limits (`GITHUB_REQUESTS_PER_MINUTE`)
- Frontend API URL (`NEXT_PUBLIC_API_URL`)

### Security Model
- Localhost-only for MVP
- No authentication/RBAC in this phase
- Secrets never exposed to browser
- Backend masks sensitive config

## Troubleshooting

### Services won't start

Check that ports 3000 and 8000 are available:
```bash
lsof -i :3000
lsof -i :8000
```

### Database errors

Reset the database:
```bash
rm runtime/data/sqlite/agentic_workflow.db
./scripts/migrate.sh
```

### Gateway connection issues

Verify Gateway is running and accessible:
```bash
curl http://localhost:8080/health
```

Check `~/.openclaw/openclaw.json` has correct Gateway URL and token.

### Worker errors

Check worker logs in the terminal where `dev.sh` is running. Verify environment variables are set correctly.

## Development Commands

### Frontend
```bash
cd frontend
npm run dev          # Start dev server
npm run build        # Production build
npm run lint         # Run linter
npm test             # Run tests
```

### Backend
```bash
cd backend
uv run uvicorn app.main:app --reload  # Start API
uv run pytest                          # Run tests
uv run ruff check .                    # Lint
```

### Workers
```bash
cd workers
uv run python -m agentic_workers.main  # Start workers
uv run pytest                          # Run tests
```

## Production Considerations

For production deployment:

1. Use PostgreSQL instead of SQLite
2. Set up proper process management (systemd, supervisor)
3. Configure reverse proxy (nginx, caddy)
4. Enable HTTPS/TLS
5. Implement authentication/authorization
6. Set up monitoring and logging
7. Configure backup strategy for database

## Support

For issues or questions:
- Check `docs/` for detailed documentation
- Review `_bmad-output/planning-artifacts/` for architecture details
- Consult Gateway integration contract in `docs/gateway-integration-contract.md`
