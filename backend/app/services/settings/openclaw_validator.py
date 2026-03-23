from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.schemas.settings import (
    ConfigurationValidationIssue,
    MaskedSettingSummary,
)
from app.services.openclaw.config_service import (
    OpenClawConfigError,
    OpenClawConfigReadError,
    extract_default_model,
    extract_gateway_allow_insecure_tls,
    extract_gateway_config,
    load_openclaw_config,
)
from app.services.openclaw.transport import (
    GatewayTargetInput,
    GatewayTargetResolution,
    resolve_gateway_target_from_input,
)
from app.services.settings.common import _as_dict, _as_string, _raise_validation_error

logger = logging.getLogger(__name__)


def load_openclaw_payload(
    app_settings: Settings,
    issues: list[ConfigurationValidationIssue],
) -> dict[str, Any]:
    if not app_settings.OPENCLAW_CONFIG_PATH:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_CONFIG_PATH",
                owner="openclaw",
                code="openclaw_config_missing",
                message="OpenClaw config path is not configured.",
                source="openclaw-config",
            )
        )
        _raise_validation_error(issues)

    config_path = app_settings.OPENCLAW_CONFIG_PATH.expanduser()
    logger.debug("Loading OpenClaw config from %s", config_path)

    if not config_path.is_file():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_CONFIG_PATH",
                owner="openclaw",
                code="openclaw_config_missing",
                message="OpenClaw config file was not found.",
                source="openclaw-config",
            )
        )
        _raise_validation_error(issues)

    try:
        loaded = load_openclaw_config(config_path)
    except OpenClawConfigReadError as exc:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_CONFIG_PATH",
                owner="openclaw",
                code="openclaw_config_unreadable",
                message=f"OpenClaw config is unreadable: {exc}",
                source="openclaw-config",
            )
        )
        _raise_validation_error(issues)
    except OpenClawConfigError as exc:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_CONFIG_PATH",
                owner="openclaw",
                code="openclaw_config_invalid_json",
                message=f"OpenClaw config is not valid JSON/JSON5: {exc}",
                source="openclaw-config",
            )
        )
        _raise_validation_error(issues)

    if not isinstance(loaded, dict):
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_CONFIG_PATH",
                owner="openclaw",
                code="openclaw_config_invalid_shape",
                message="OpenClaw config must be a JSON object.",
                source="openclaw-config",
            )
        )
        _raise_validation_error(issues)

    gateway = extract_gateway_config(loaded)
    default_model = extract_default_model(loaded)
    allow_insecure_tls = extract_gateway_allow_insecure_tls(_as_dict(loaded.get("gateway")))

    logger.debug(
        "OpenClaw config loaded: gateway.url configured=%s, default_model=%s",
        bool(gateway.url),
        default_model or "not set",
    )

    if allow_insecure_tls:
        logger.warning("OpenClaw config has allow_insecure_tls enabled")

    if not gateway.url:
        issues.append(
            ConfigurationValidationIssue(
                severity="warning",
                field="gateway.url",
                owner="gateway",
                code="gateway_url_missing",
                message=(
                    "OpenClaw config does not currently define gateway.url. Gateway-backed "
                    "transport is unavailable, but local settings summaries should still remain visible."
                ),
                source="openclaw-config",
            )
        )

    if not gateway.token:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="gateway.auth.token",
                owner="gateway",
                code="gateway_token_missing",
                message="OpenClaw config must define gateway.auth.token.",
                source="openclaw-config",
            )
        )

    if not default_model:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="agents.defaults.model.primary",
                owner="openclaw",
                code="default_model_missing",
                message=(
                    "OpenClaw config must define agents.defaults.model.primary "
                    "(or a legacy string model)."
                ),
                source="openclaw-config",
            )
        )

    if any(issue.severity == "error" for issue in issues):
        _raise_validation_error(issues)

    logger.info("OpenClaw config validation passed")
    return loaded  # type: ignore[return-value]


def resolve_openclaw_gateway_target(
    payload: dict[str, Any],
) -> GatewayTargetResolution:
    gateway = extract_gateway_config(payload)
    return resolve_gateway_target_from_input(
        GatewayTargetInput(
            url=gateway.url,
            token=gateway.token,
            allow_insecure_tls=gateway.allow_insecure_tls,
            source="openclaw-config",
            placeholder_source="openclaw-config-missing",
            configured_notes=(
                "Gateway transport is normalized from OpenClaw-owned config and exposed as a masked summary only.",
            ),
        )
    )


def build_openclaw_setting_summaries(
    payload: dict[str, Any],
    gateway_target: GatewayTargetResolution,
) -> list[MaskedSettingSummary]:
    gateway_config = _as_dict(payload.get("gateway"))
    auth_config = _as_dict(gateway_config.get("auth"))
    default_model = extract_default_model(payload)
    channels = _as_dict(payload.get("channels"))
    configured_channels = sorted(channels.keys())
    remote_config = _as_dict(gateway_config.get("remote"))

    logger.debug(
        "Building OpenClaw setting summaries: channels=%s, default_model=%s",
        configured_channels or "none",
        default_model or "not set",
    )

    return [
        MaskedSettingSummary(
            key="gateway.url",
            label="Gateway URL",
            owner="gateway",
            source="openclaw-config",
            configured=gateway_target.configured,
            required=True,
            value=gateway_target.url,
            notes=["Normalized with shared Gateway URL validation logic."],
        ),
        MaskedSettingSummary(
            key="gateway.auth.token",
            label="Gateway auth token",
            owner="gateway",
            source="openclaw-config",
            configured=bool(_as_string(auth_config.get("token"))),
            required=True,
            secret=True,
            value="configured" if _as_string(auth_config.get("token")) else "missing",
            notes=["Gateway credentials stay OpenClaw-owned and backend-masked."],
        ),
        MaskedSettingSummary(
            key="gateway.allowInsecureTls",
            label="Gateway insecure TLS flag",
            owner="gateway",
            source="openclaw-config",
            configured=(
                "allowInsecureTls" in gateway_config or "allowInsecureTls" in remote_config
            ),
            required=False,
            value=str(extract_gateway_allow_insecure_tls(gateway_config)).lower(),
            notes=[
                "Transport flags are summarized for inspection but not editable from the browser."
            ],
        ),
        MaskedSettingSummary(
            key="agents.defaults.model",
            label="Default agent model",
            owner="openclaw",
            source="openclaw-config",
            configured=bool(default_model),
            required=True,
            value=default_model,
            notes=[
                "Model defaults remain OpenClaw-native conventions rather than project env.",
                "Object-shaped defaults use agents.defaults.model.primary as the displayed value.",
            ],
        ),
        MaskedSettingSummary(
            key="channels",
            label="Configured OpenClaw channels",
            owner="openclaw",
            source="openclaw-config",
            configured=bool(configured_channels),
            required=False,
            value=", ".join(configured_channels) if configured_channels else "none",
            notes=["Only channel names are surfaced; channel secrets remain hidden."],
        ),
    ]
