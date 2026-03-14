# OpenClaw Gateway Integration Guide

## Overview

Agentic-Workflow integrates with OpenClaw Gateway as its control-plane backend. The integration follows a strict boundary:

**Frontend → Agentic-Workflow Backend → OpenClaw Gateway**

## Gateway Configuration

### 1. OpenClaw Config File

Location: `~/.openclaw/openclaw.json`

Required structure:
```json
{
  "gateway": {
    "url": "http://localhost:8080",
    "auth": {
      "token": "your-gateway-auth-token"
    },
    "tls": {
      "enabled": false
    }
  },
  "agents": {
    "defaults": {
      "model": "claude-opus-4",
      "temperature": 0.7
    }
  },
  "channels": {
    "default": "general"
  }
}
```

### 2. Environment Variables

In `workspace/agentic-workflow/.env`:
```bash
OPENCLAW_CONFIG_PATH=~/.openclaw/openclaw.json
OPENCLAW_WORKSPACE_DIR=/path/to/openclaw/workspace
```

## Integration Points

### Backend API Routes

The backend exposes Gateway functionality through:

| Route | Purpose |
|-------|---------|
| `/api/v1/gateway/contract` | Integration contract verification |
| `/api/v1/gateway/runtime` | Runtime status and health |
| `/api/v1/gateway/sessions` | Session discovery and listing |
| `/api/v1/gateway/sessions/{id}` | Session details |
| `/api/v1/gateway/sessions/{id}/history` | Session history |
| `/api/v1/gateway/events/envelope` | Real-time event stream |

### Settings Inspection

Check configuration status:
```bash
curl http://localhost:8000/api/v1/settings/summary
```

Returns:
- Gateway connectivity status
- Configuration validation results
- Masked settings (no secrets exposed)

## Multi-Agent Runtime

### Named Agents

The system supports these agents:

1. **Overlord** - Orchestration coordinator
2. **Firehose** - Real-time repository intake
3. **Backfill** - Historical data processing
4. **Bouncer** - Repository filtering/triage
5. **Analyst** - Repository analysis
6. **Combiner** - (Reserved)
7. **Obsession** - (Reserved)

### Agent Sessions

Each agent can have multiple sessions tracked through Gateway. Sessions are:
- Created by Gateway
- Discovered via `/api/v1/gateway/sessions`
- Filtered by agent name
- Tracked with full history

## Security Model

### What's Protected

- Gateway auth tokens (never sent to browser)
- Provider credentials (backend-only)
- Raw OpenClaw config (masked in API responses)

### What's Exposed

- Session metadata (IDs, timestamps, status)
- Runtime health status
- Validation results (without secrets)

## Testing Integration

### 1. Verify Gateway is Running
```bash
curl http://localhost:8080/health
```

### 2. Check Backend Connection
```bash
curl http://localhost:8000/api/v1/gateway/runtime
```

Expected response:
```json
{
  "status": "connected",
  "gateway_url": "http://localhost:8080",
  "runtime_mode": "multi-agent",
  "agents": ["Overlord", "Firehose", "Backfill", "Bouncer", "Analyst"]
}
```

### 3. List Sessions
```bash
curl http://localhost:8000/api/v1/gateway/sessions
```

## Troubleshooting

### Gateway Not Reachable

**Symptom**: Backend logs show connection errors

**Solutions**:
1. Verify Gateway is running: `curl http://localhost:8080/health`
2. Check `~/.openclaw/openclaw.json` has correct URL
3. Verify no firewall blocking localhost:8080

### Invalid Token

**Symptom**: 401/403 errors in backend logs

**Solutions**:
1. Check `gateway.auth.token` in `~/.openclaw/openclaw.json`
2. Regenerate token in Gateway if needed
3. Restart backend after config changes

### Configuration Not Found

**Symptom**: Backend fails to start with config errors

**Solutions**:
1. Verify `~/.openclaw/openclaw.json` exists
2. Check JSON syntax is valid
3. Ensure `OPENCLAW_CONFIG_PATH` in `.env` is correct

## Configuration Ownership

### OpenClaw Owns
- Gateway URL and auth credentials
- Agent/model defaults
- Channel conventions
- Session management

### Agentic-Workflow Owns
- Local database paths
- Provider API tokens (GitHub, etc.)
- Rate limiting thresholds
- Worker scheduling intervals

### Never Mix
- Don't put Gateway secrets in Agentic-Workflow `.env`
- Don't put provider tokens in OpenClaw config
- Don't expose raw config to frontend

## Advanced Configuration

### Custom Gateway Port
```json
{
  "gateway": {
    "url": "http://localhost:9000"
  }
}
```

### TLS/HTTPS
```json
{
  "gateway": {
    "url": "https://gateway.example.com",
    "tls": {
      "enabled": true,
      "verify": true
    }
  }
}
```

### Multiple Workspaces
Set per-deployment in `.env`:
```bash
OPENCLAW_WORKSPACE_DIR=/path/to/workspace-1
```

## Event Streaming (Future)

Real-time Gateway events will be normalized through:
```
Gateway Events → Backend Normalization → Frontend WebSocket
```

Event envelope structure:
```json
{
  "event_id": "uuid",
  "event_type": "session.created",
  "session_id": "session-uuid",
  "route_key": "agent.overlord",
  "occurred_at": "2026-03-14T15:52:23Z",
  "payload": {}
}
```
