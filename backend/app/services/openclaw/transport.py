from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.services.openclaw.config_service import (
    OpenClawConfigError,
    OpenClawConfigReadError,
    extract_default_model,
    extract_gateway_config,
    load_openclaw_config,
)

DEFAULT_GATEWAY_PORT = 18789
CONFIG_VALIDATION_STATUS_CODE = 422


def _raise_openclaw_config_validation_error(
    message: str,
    *,
    code: str = "openclaw_config_invalid_json",
    field: str = "OPENCLAW_CONFIG_PATH",
    owner: str = "openclaw",
) -> None:
    raise AppError(
        message="Configuration validation failed.",
        code="settings_validation_failed",
        status_code=CONFIG_VALIDATION_STATUS_CODE,
        details={
            "validation": {
                "valid": False,
                "issues": [
                    {
                        "severity": "error",
                        "field": field,
                        "owner": owner,
                        "code": code,
                        "message": message,
                        "source": "openclaw-config",
                    }
                ],
            }
        },
    )


@dataclass(frozen=True, slots=True)
class GatewayTargetResolution:
    configured: bool
    url: str | None
    scheme: str | None
    token_configured: bool
    allow_insecure_tls: bool
    source: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GatewayTargetInput:
    url: str | None
    token: str | None
    allow_insecure_tls: bool
    source: str
    placeholder_source: str
    placeholder_notes: tuple[str, ...] = ()
    configured_notes: tuple[str, ...] = ()


def normalize_gateway_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise AppError(
            message="Gateway URL cannot be empty.",
            code="gateway_url_missing",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
        )

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"ws", "wss"}:
        raise AppError(
            message="Gateway URL must use ws:// or wss://.",
            code="gateway_url_scheme_invalid",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"value": raw_url},
        )

    if not parsed.hostname:
        raise AppError(
            message="Gateway URL must include a hostname.",
            code="gateway_url_host_missing",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"value": raw_url},
        )

    if parsed.query or parsed.fragment:
        raise AppError(
            message="Gateway URL cannot include query parameters or fragments.",
            code="gateway_url_invalid_suffix",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"value": raw_url},
        )

    if parsed.username or parsed.password:
        raise AppError(
            message="Gateway URL must not embed credentials.",
            code="gateway_url_credentials_forbidden",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"value": raw_url},
        )

    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise AppError(
            message="Gateway URL must use a valid numeric port when one is provided.",
            code="gateway_url_port_invalid",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"value": raw_url},
        ) from exc

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    path = parsed.path.rstrip("/")
    port = parsed_port or DEFAULT_GATEWAY_PORT
    return f"{parsed.scheme}://{host}:{port}{path}"


def resolve_gateway_target_from_input(
    target_input: GatewayTargetInput,
) -> GatewayTargetResolution:
    raw_url = (target_input.url or "").strip()
    token_configured = bool((target_input.token or "").strip())

    if not raw_url:
        return GatewayTargetResolution(
            configured=False,
            url=None,
            scheme=None,
            token_configured=token_configured,
            allow_insecure_tls=target_input.allow_insecure_tls,
            source=target_input.placeholder_source,
            notes=target_input.placeholder_notes,
        )

    normalized = normalize_gateway_url(raw_url)
    return GatewayTargetResolution(
        configured=True,
        url=normalized,
        scheme=urlsplit(normalized).scheme,
        token_configured=token_configured,
        allow_insecure_tls=target_input.allow_insecure_tls,
        source=target_input.source,
        notes=target_input.configured_notes,
    )


def resolve_gateway_target(
    app_settings: Settings = settings,
) -> GatewayTargetResolution:
    if not app_settings.OPENCLAW_CONFIG_PATH:
        _raise_openclaw_config_validation_error(
            "OpenClaw config path is not configured.",
            code="openclaw_config_missing",
        )

    config_path = app_settings.OPENCLAW_CONFIG_PATH.expanduser()

    if not config_path.is_file():
        _raise_openclaw_config_validation_error(
            "OpenClaw config file was not found.",
            code="openclaw_config_missing",
        )

    try:
        payload = load_openclaw_config(config_path)
        gateway = extract_gateway_config(payload)
    except OpenClawConfigReadError as exc:
        _raise_openclaw_config_validation_error(
            f"OpenClaw config is unreadable: {exc}",
            code="openclaw_config_unreadable",
        )
    except OpenClawConfigError as exc:
        _raise_openclaw_config_validation_error(
            f"OpenClaw config is not valid JSON/JSON5: {exc}",
            code="openclaw_config_invalid_json",
        )

    if not gateway.url:
        _raise_openclaw_config_validation_error(
            "OpenClaw config must define gateway.url for backend mediation.",
            code="gateway_url_missing",
            field="gateway.url",
            owner="gateway",
        )

    if not gateway.token:
        _raise_openclaw_config_validation_error(
            "OpenClaw config must define gateway.auth.token.",
            code="gateway_token_missing",
            field="gateway.auth.token",
            owner="gateway",
        )

    default_model = extract_default_model(payload)
    if not default_model:
        _raise_openclaw_config_validation_error(
            "OpenClaw config must define agents.defaults.model.primary (or a legacy string model).",
            code="default_model_missing",
            field="agents.defaults.model.primary",
            owner="openclaw",
        )

    return resolve_gateway_target_from_input(
        GatewayTargetInput(
            url=gateway.url,
            token=gateway.token,
            allow_insecure_tls=gateway.allow_insecure_tls,
            source="openclaw-config",
            placeholder_source="openclaw-config-missing",
            placeholder_notes=(
                "Gateway transport details are owned by OpenClaw config.",
                "No live Gateway target is required to publish the Story 1.2 contract.",
            ),
            configured_notes=(
                "Gateway transport is normalized from OpenClaw-owned config.",
                "Frontend reads remain backend-mediated even when a Gateway URL is configured.",
            ),
        )
    )


def map_gateway_transport_error(
    error: Exception | str,
    *,
    status_code: int = 502,
) -> AppError:
    message = str(error).strip() or "Unknown Gateway transport error."
    return AppError(
        message="Gateway transport contract is unavailable.",
        code="gateway_transport_unavailable",
        status_code=status_code,
        details={"reason": message},
    )
