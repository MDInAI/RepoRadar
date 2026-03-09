from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

import pyjson5


class OpenClawConfigError(ValueError):
    """Raised when the OpenClaw config cannot be parsed or normalized."""


class OpenClawConfigReadError(OpenClawConfigError):
    """Raised when the OpenClaw config cannot be read from disk."""


@dataclass(frozen=True, slots=True)
class OpenClawGatewayConfig:
    url: str | None
    token: str | None
    allow_insecure_tls: bool


class OpenClawGatewayAuthSection(TypedDict, total=False):
    token: str


class OpenClawGatewayRemoteSection(TypedDict, total=False):
    url: str
    allowInsecureTls: bool


class OpenClawGatewaySection(TypedDict, total=False):
    url: str
    auth: OpenClawGatewayAuthSection
    remote: OpenClawGatewayRemoteSection
    allowInsecureTls: bool


class OpenClawModelSection(TypedDict, total=False):
    primary: str


class OpenClawAgentDefaultsSection(TypedDict, total=False):
    model: str | OpenClawModelSection


class OpenClawAgentsSection(TypedDict, total=False):
    defaults: OpenClawAgentDefaultsSection


def load_openclaw_config(config_path: Path) -> dict[str, Any]:
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpenClawConfigReadError(str(exc)) from exc

    if not raw_text.strip():
        return {}
    return parse_openclaw_config(raw_text)


def parse_openclaw_config(raw_text: str) -> dict[str, Any]:
    try:
        loaded = pyjson5.loads(raw_text)
    except Exception as exc:
        raise OpenClawConfigError(str(exc)) from exc

    if not isinstance(loaded, dict):
        raise OpenClawConfigError("Top-level config must evaluate to an object.")

    return loaded


def extract_gateway_config(payload: dict[str, Any]) -> OpenClawGatewayConfig:
    gateway_config = _gateway_section(payload)
    auth_config = _gateway_auth_section(gateway_config)

    return OpenClawGatewayConfig(
        url=extract_gateway_url(gateway_config),
        token=_as_string(auth_config.get("token")),
        allow_insecure_tls=extract_gateway_allow_insecure_tls(gateway_config),
    )


def extract_default_model(payload: dict[str, Any]) -> str | None:
    agent_defaults = _agents_defaults_section(payload)
    return _normalize_model_value(agent_defaults.get("model"))


def extract_gateway_url(gateway_config: dict[str, Any]) -> str | None:
    direct_url = _as_string(gateway_config.get("url"))
    if direct_url:
        return direct_url

    remote_config = _gateway_remote_section(gateway_config)
    return _as_string(remote_config.get("url"))


def extract_gateway_allow_insecure_tls(gateway_config: dict[str, Any]) -> bool:
    if "allowInsecureTls" in gateway_config:
        return _as_bool(gateway_config.get("allowInsecureTls"))

    remote_config = _gateway_remote_section(gateway_config)
    return _as_bool(remote_config.get("allowInsecureTls"))


def _gateway_section(payload: dict[str, Any]) -> OpenClawGatewaySection:
    return cast(OpenClawGatewaySection, _as_dict(payload.get("gateway")))


def _gateway_auth_section(
    gateway_config: OpenClawGatewaySection | dict[str, Any],
) -> OpenClawGatewayAuthSection:
    return cast(OpenClawGatewayAuthSection, _as_dict(gateway_config.get("auth")))


def _gateway_remote_section(
    gateway_config: OpenClawGatewaySection | dict[str, Any],
) -> OpenClawGatewayRemoteSection:
    return cast(OpenClawGatewayRemoteSection, _as_dict(gateway_config.get("remote")))


def _agents_defaults_section(payload: dict[str, Any]) -> OpenClawAgentDefaultsSection:
    agents = cast(OpenClawAgentsSection, _as_dict(payload.get("agents")))
    return cast(OpenClawAgentDefaultsSection, _as_dict(agents.get("defaults")))


def _normalize_model_value(value: Any) -> str | None:
    result = _as_string(value)
    if result is not None:
        return result
    if isinstance(value, dict):
        model_config = cast(OpenClawModelSection, value)
        return _as_string(model_config.get("primary"))
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_string(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return False
