# Deployment Documentation Index

## Getting Started

1. **[QUICKSTART.md](QUICKSTART.md)** - 5-minute setup guide
2. **[README.md](README.md)** - Complete deployment guide
3. **[DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)** - Step-by-step checklist

## Integration

4. **[GATEWAY-INTEGRATION.md](GATEWAY-INTEGRATION.md)** - OpenClaw Gateway integration guide
5. **[API-REFERENCE.md](API-REFERENCE.md)** - Backend API documentation

## Quick Commands

### Install
```bash
cd workspace/agentic-workflow
cp .env.example .env
# Edit .env with your settings
./scripts/bootstrap.sh
```

### Run
```bash
./scripts/dev.sh
```

### Access
- Dashboard: http://localhost:3000
- API Docs: http://localhost:8000/docs

## Key Files

- `.env` - Environment configuration
- `~/.openclaw/openclaw.json` - OpenClaw Gateway config
- `scripts/bootstrap.sh` - Dependency installer
- `scripts/dev.sh` - Development server launcher
- `scripts/migrate.sh` - Database migration tool

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Browser   │─────▶│  Agentic-Workflow│─────▶│ OpenClaw Gateway│
│             │      │     Backend      │      │                 │
└─────────────┘      └──────────────────┘      └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Worker Agents  │
                     │  (Background)   │
                     └─────────────────┘
```

## Support

For detailed information, see the individual guides above.
