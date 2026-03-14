# Quick Start Guide

## 5-Minute Setup

### 1. Configure Environment
```bash
cd workspace/agentic-workflow
cp .env.example .env
```

Edit `.env` - minimum required:
```bash
OPENCLAW_CONFIG_PATH=~/.openclaw/openclaw.json
OPENCLAW_WORKSPACE_DIR=/path/to/openclaw/workspace
```

### 2. Install & Run
```bash
./scripts/bootstrap.sh
./scripts/dev.sh
```

### 3. Access
- Dashboard: http://localhost:3000
- API: http://localhost:8000/docs

## Stop Services
Press `Ctrl+C` in the terminal running `dev.sh`

## Common Issues

**Port already in use?**
```bash
# Change ports in .env
FRONTEND_PORT=3001
BACKEND_PORT=8001
```

**Gateway not connecting?**
Check `~/.openclaw/openclaw.json` has:
```json
{
  "gateway": {
    "url": "http://localhost:8080",
    "auth": { "token": "your-token" }
  }
}
```

**Database errors?**
```bash
./scripts/migrate.sh
```
