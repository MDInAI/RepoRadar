# API Reference

Base URL: `http://localhost:8000`

## Health & Status

### GET /health
System health check

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-14T15:52:48Z"
}
```

## Gateway Integration

### GET /api/v1/gateway/contract
Gateway integration contract details

### GET /api/v1/gateway/runtime
Gateway runtime status and multi-agent info

**Response:**
```json
{
  "status": "connected",
  "gateway_url": "http://localhost:8080",
  "runtime_mode": "multi-agent",
  "agents": ["Overlord", "Firehose", "Backfill", "Bouncer", "Analyst"]
}
```

### GET /api/v1/gateway/sessions
List all Gateway sessions

**Query Parameters:**
- `agent_name` (optional) - Filter by agent
- `limit` (optional) - Max results
- `offset` (optional) - Pagination offset

### GET /api/v1/gateway/sessions/{session_id}
Get session details

### GET /api/v1/gateway/sessions/{session_id}/history
Get session history

### GET /api/v1/gateway/events/envelope
Real-time event stream (SSE)

## Settings

### GET /api/v1/settings/summary
Configuration summary with validation

**Response:**
```json
{
  "openclaw": {
    "config_path": "~/.openclaw/openclaw.json",
    "gateway_url": "http://localhost:8080",
    "status": "valid"
  },
  "project": {
    "database_url": "sqlite:///../runtime/data/sqlite/agentic_workflow.db",
    "runtime_dir": "../runtime"
  },
  "validation": {
    "errors": [],
    "warnings": []
  }
}
```

## Repositories

### GET /api/v1/repositories
List repositories

### GET /api/v1/repositories/{repository_id}
Get repository details

### POST /api/v1/repositories
Create repository intake

### PATCH /api/v1/repositories/{repository_id}
Update repository

## Agents

### GET /api/v1/agents
List agent status

### GET /api/v1/agents/{agent_name}
Get agent details

### POST /api/v1/agents/{agent_name}/pause
Pause agent

### POST /api/v1/agents/{agent_name}/resume
Resume agent

## Ideas & Synthesis

### GET /api/v1/ideas
List synthesized ideas

### GET /api/v1/ideas/{idea_id}
Get idea details

### GET /api/v1/synthesis/runs
List synthesis runs

## System Events

### GET /api/v1/events
List system events

**Query Parameters:**
- `severity` - Filter by severity (info, warning, error, critical)
- `agent_name` - Filter by agent
- `limit` - Max results

## Interactive Documentation

Full interactive API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
