# Deployment Checklist

## Pre-Deployment

### System Requirements
- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed
- [ ] npm or yarn available
- [ ] `uv` package manager installed (optional but recommended)
- [ ] Ports 3000 and 8000 available

### OpenClaw Gateway
- [ ] Gateway is running and accessible
- [ ] Gateway health check passes: `curl http://localhost:8080/health`
- [ ] `~/.openclaw/openclaw.json` exists
- [ ] Gateway URL configured in openclaw.json
- [ ] Gateway auth token configured
- [ ] Agent defaults configured (model, etc.)

### Project Setup
- [ ] Clone/download agentic-workflow project
- [ ] Copy `.env.example` to `.env`
- [ ] Set `OPENCLAW_CONFIG_PATH` in .env
- [ ] Set `OPENCLAW_WORKSPACE_DIR` in .env
- [ ] Set `DATABASE_URL` in .env (or use default SQLite)
- [ ] Configure `GITHUB_PROVIDER_TOKEN` if using GitHub intake

## Installation

- [ ] Run `./scripts/bootstrap.sh`
- [ ] Verify frontend dependencies installed
- [ ] Verify backend dependencies installed
- [ ] Verify worker dependencies installed
- [ ] Run `./scripts/migrate.sh` to initialize database

## First Run

- [ ] Start services: `./scripts/dev.sh`
- [ ] Verify frontend starts on port 3000
- [ ] Verify backend starts on port 8000
- [ ] Verify workers start without errors
- [ ] Check backend logs for Gateway connection

## Verification

### Frontend
- [ ] Access http://localhost:3000
- [ ] Dashboard loads without errors
- [ ] Navigation works (Overview, Repositories, Agents, Ideas)

### Backend API
- [ ] Access http://localhost:8000/docs
- [ ] Health check: `curl http://localhost:8000/health`
- [ ] Gateway runtime: `curl http://localhost:8000/api/v1/gateway/runtime`
- [ ] Settings summary: `curl http://localhost:8000/api/v1/settings/summary`

### Gateway Integration
- [ ] Backend connects to Gateway successfully
- [ ] Sessions endpoint returns data: `curl http://localhost:8000/api/v1/gateway/sessions`
- [ ] No auth errors in backend logs
- [ ] Multi-agent runtime mode active

### Database
- [ ] Database file created (if using SQLite)
- [ ] Migrations applied successfully
- [ ] No database errors in logs

## Post-Deployment

- [ ] Test repository intake workflow
- [ ] Verify agent status monitoring
- [ ] Check worker job execution
- [ ] Monitor logs for errors
- [ ] Test frontend-backend communication

## Troubleshooting Steps

If issues occur:
1. Check all services are running
2. Verify Gateway connectivity
3. Review backend logs for errors
4. Check database migrations status
5. Verify environment variables are set
6. Confirm ports are not in use by other services
