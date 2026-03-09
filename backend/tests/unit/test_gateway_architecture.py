# ruff: noqa: S101
from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _iter_code_files(root: Path) -> list[Path]:
    extensions = {".py", ".ts", ".tsx"}
    return [path for path in root.rglob("*") if path.suffix in extensions]


def test_api_routes_do_not_import_low_level_gateway_transport_helpers() -> None:
    repo_root = _project_root()
    api_root = repo_root / "backend" / "app" / "api" / "routes"

    violations: list[str] = []
    forbidden_prefixes = (
        "from app.services.openclaw.transport import ",
        "import app.services.openclaw.transport",
    )

    for path in api_root.rglob("*.py"):
        rel = path.relative_to(repo_root)
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if any(line.startswith(prefix) for prefix in forbidden_prefixes):
                violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "API routes must depend on typed Gateway service methods instead of low-level "
        f"transport helpers. Violations: {', '.join(violations)}"
    )


def test_runtime_code_does_not_parse_session_files_as_primary_contract() -> None:
    repo_root = _project_root()
    targets = [
        repo_root / "backend" / "app",
        repo_root / "frontend" / "src",
    ]
    forbidden_fragments = (
        "sessions.json",
        ".jsonl",
        ".openclaw/agents/",
        "/sessions/sessions.json",
        "/sessions/*.jsonl",
    )
    file_access_markers = (
        "=",
        "open(",
        "read_text(",
        "write_text(",
        "Path(",
        "glob(",
        "rglob(",
        "iterdir(",
        ".exists(",
        "json.load",
        "json.loads",
        "os.path",
    )

    violations: list[str] = []
    for root in targets:
        for path in _iter_code_files(root):
            rel = path.relative_to(repo_root)
            for lineno, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if any(fragment in raw_line for fragment in forbidden_fragments) and any(
                    marker in raw_line for marker in file_access_markers
                ):
                    violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "Runtime code must not treat OpenClaw session files as the primary contract. "
        f"Violations: {', '.join(violations)}"
    )


def test_runtime_routes_do_not_read_openclaw_config_directly() -> None:
    repo_root = _project_root()
    targets = [
        repo_root / "backend" / "app" / "api" / "routes",
        repo_root / "frontend" / "src" / "app",
    ]
    forbidden_fragments = (
        "openclaw.json",
        "~/.openclaw",
        ".openclaw/openclaw.json",
    )
    file_access_markers = (
        "open(",
        "read_text(",
        "Path(",
        "os.path",
        "json.load",
        "json.loads",
    )

    violations: list[str] = []
    for root in targets:
        for path in _iter_code_files(root):
            rel = path.relative_to(repo_root)
            for lineno, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if any(fragment in raw_line for fragment in forbidden_fragments) and any(
                    marker in raw_line for marker in file_access_markers
                ):
                    violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "Route-entry runtime code must consume OpenClaw config through backend services, "
        f"not direct file reads. Violations: {', '.join(violations)}"
    )


def test_frontend_routes_do_not_open_gateway_websockets_directly() -> None:
    repo_root = _project_root()
    app_root = repo_root / "frontend" / "src" / "app"
    forbidden_fragments = ("ws://", "wss://", "new WebSocket(")

    violations: list[str] = []
    for path in _iter_code_files(app_root):
        rel = path.relative_to(repo_root)
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(fragment in raw_line for fragment in forbidden_fragments):
                violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "Frontend routes must consume Gateway data through the backend contract, not "
        f"direct websocket calls. Violations: {', '.join(violations)}"
    )


def test_frontend_examples_and_code_do_not_expose_gateway_or_provider_secrets() -> None:
    repo_root = _project_root()
    targets = [
        repo_root / "frontend" / ".env.local.example",
        repo_root / "frontend" / "src",
    ]
    forbidden_tokens = (
        "NEXT_PUBLIC_WS_URL",
        "NEXT_PUBLIC_OPENCLAW",
        "NEXT_PUBLIC_GATEWAY_TOKEN",
        "OPENCLAW_CONFIG_PATH",
        "OPENCLAW_GATEWAY_TOKEN",
        "GITHUB_PROVIDER_TOKEN",
    )

    violations: list[str] = []
    for target in targets:
        files = _iter_code_files(target) if target.is_dir() else [target]
        for file_path in files:
            rel = file_path.relative_to(repo_root)
            for lineno, raw_line in enumerate(
                file_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if any(token in raw_line for token in forbidden_tokens):
                    violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "Frontend code and examples must stay limited to app-facing configuration only. "
        f"Violations: {', '.join(violations)}"
    )


def test_gateway_contract_files_encode_explicit_multi_agent_runtime_mode() -> None:
    repo_root = _project_root()
    targets = {
        "schema": repo_root / "backend" / "app" / "schemas" / "gateway_contract.py",
        "service": repo_root / "backend" / "app" / "services" / "openclaw" / "contract_service.py",
        "frontend": repo_root / "frontend" / "src" / "lib" / "gateway-contract.ts",
        "route": repo_root / "backend" / "app" / "api" / "routes" / "gateway.py",
    }
    loaded = {name: path.read_text(encoding="utf-8") for name, path in targets.items()}

    assert 'Literal["multi-agent"]' in loaded["schema"]
    assert "runtime_mode" in loaded["schema"]
    assert "named_agents" in loaded["schema"]
    assert "agent_states" in loaded["schema"]
    assert "agent_context" in loaded["schema"]
    assert "runtime_mode" in loaded["service"]
    assert "named_agents" in loaded["service"]
    assert "agent_context" in loaded["service"]
    assert "runtime_mode" in loaded["frontend"]
    assert "named_agents" in loaded["frontend"]
    assert "agent_context" in loaded["frontend"]
    assert "GatewaySessionSurfaceResponse" in loaded["route"]
    for display_name in (
        "Overlord",
        "Firehose",
        "Backfill",
        "Bouncer",
        "Analyst",
        "Combiner",
        "Obsession",
    ):
        assert display_name in loaded["service"]


def test_gateway_contract_does_not_reintroduce_single_agent_only_fields() -> None:
    repo_root = _project_root()
    targets = [
        repo_root / "backend" / "app" / "schemas",
        repo_root / "backend" / "app" / "services" / "openclaw",
        repo_root / "backend" / "app" / "api" / "routes" / "gateway.py",
        repo_root / "frontend" / "src" / "lib",
    ]
    forbidden_tokens = (
        "current_agent",
        "currentAgent",
        "agent_status",
        "agentStatus",
        "active_agent",
        "activeAgent",
        "primary_agent",
        "primaryAgent",
        "sole_agent",
        "soleAgent",
    )

    violations: list[str] = []
    for path in targets:
        if path.is_dir():
            files = _iter_code_files(path)
        else:
            files = [path]

        for file_path in files:
            rel = file_path.relative_to(repo_root)
            for lineno, raw_line in enumerate(
                file_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if any(token in raw_line for token in forbidden_tokens):
                    violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "Gateway contract surfaces must remain multi-agent aware and avoid singular-only "
        f"fields. Violations: {', '.join(violations)}"
    )


def test_env_examples_do_not_ship_machine_specific_workspace_paths() -> None:
    repo_root = _project_root()
    targets = [
        repo_root / ".env.example",
        repo_root / "backend" / ".env.example",
        repo_root / "workers" / ".env.example",
    ]

    violations: list[str] = []
    for file_path in targets:
        for lineno, raw_line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "/Users/" in raw_line and "OPENCLAW_WORKSPACE_DIR" in raw_line:
                violations.append(f"{file_path.relative_to(repo_root)}:{lineno}")

    assert not violations, (
        "Env examples must not hardcode one developer's workspace path. "
        f"Violations: {', '.join(violations)}"
    )
