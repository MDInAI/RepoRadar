# Agentic-Workflow API

This is the FastAPI backend for the Agentic-Workflow local orchestration system.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
