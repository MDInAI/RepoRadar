from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_JSON5_KEY_PATTERN = re.compile(r'([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)(\s*:)')
_JSON5_CONSTANTS = {
    "true": "True",
    "false": "False",
    "null": "None",
}


class OpenClawConfigError(ValueError):
    """Raised when the OpenClaw config cannot be parsed or normalized."""


class OpenClawConfigReadError(OpenClawConfigError):
    """Raised when the OpenClaw config cannot be read from disk."""


@dataclass(frozen=True, slots=True)
class OpenClawGatewayConfig:
    url: str | None
    token: str | None
    allow_insecure_tls: bool


def load_openclaw_config(config_path: Path) -> dict[str, Any]:
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpenClawConfigReadError(str(exc)) from exc

    return parse_openclaw_config(raw_text)


def parse_openclaw_config(raw_text: str) -> dict[str, Any]:
    normalized = _strip_json5_comments(raw_text)
    normalized = _transform_outside_strings(
        normalized,
        _normalize_json5_segment,
    ).strip()

    try:
        loaded = ast.literal_eval(normalized)
    except (SyntaxError, ValueError) as exc:
        raise OpenClawConfigError(str(exc)) from exc

    if not isinstance(loaded, dict):
        raise OpenClawConfigError("Top-level config must evaluate to an object.")

    return loaded


def extract_gateway_config(payload: dict[str, Any]) -> OpenClawGatewayConfig:
    gateway_config = _as_dict(payload.get("gateway"))
    auth_config = _as_dict(gateway_config.get("auth"))

    return OpenClawGatewayConfig(
        url=extract_gateway_url(gateway_config),
        token=_as_string(auth_config.get("token")),
        allow_insecure_tls=extract_gateway_allow_insecure_tls(gateway_config),
    )


def extract_default_model(payload: dict[str, Any]) -> str | None:
    agent_defaults = _as_dict(_as_dict(payload.get("agents")).get("defaults"))
    value = agent_defaults.get("model")

    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None

    if isinstance(value, dict):
        primary = value.get("primary")
        if isinstance(primary, str):
            candidate = primary.strip()
            return candidate or None

    return None


def extract_gateway_url(gateway_config: dict[str, Any]) -> str | None:
    direct_url = _as_string(gateway_config.get("url"))
    if direct_url:
        return direct_url

    remote_config = _as_dict(gateway_config.get("remote"))
    return _as_string(remote_config.get("url"))


def extract_gateway_allow_insecure_tls(gateway_config: dict[str, Any]) -> bool:
    if "allowInsecureTls" in gateway_config:
        return _as_bool(gateway_config.get("allowInsecureTls"))

    remote_config = _as_dict(gateway_config.get("remote"))
    return _as_bool(remote_config.get("allowInsecureTls"))


def _strip_json5_comments(raw_text: str) -> str:
    result: list[str] = []
    index = 0
    in_string: str | None = None
    escaping = False

    while index < len(raw_text):
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < len(raw_text) else ""

        if in_string is not None:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == in_string:
                in_string = None
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = char
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(raw_text) and raw_text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(raw_text):
                if raw_text[index] == "*" and raw_text[index + 1] == "/":
                    index += 2
                    break
                index += 1
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _transform_outside_strings(raw_text: str, transform: Any) -> str:
    result: list[str] = []
    segment: list[str] = []
    in_string: str | None = None
    escaping = False

    for char in raw_text:
        if in_string is None:
            if char in {'"', "'"}:
                if segment:
                    result.append(transform("".join(segment)))
                    segment = []
                in_string = char
                segment.append(char)
            else:
                segment.append(char)
            continue

        segment.append(char)
        if escaping:
            escaping = False
        elif char == "\\":
            escaping = True
        elif char == in_string:
            result.append("".join(segment))
            segment = []
            in_string = None

    if segment:
        if in_string is None:
            result.append(transform("".join(segment)))
        else:
            result.append("".join(segment))

    return "".join(result)


def _normalize_json5_segment(segment: str) -> str:
    segment = _JSON5_KEY_PATTERN.sub(r'\1"\2"\3', segment)
    for source, target in _JSON5_CONSTANTS.items():
        segment = re.sub(rf"\b{source}\b", target, segment)
    return segment


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
