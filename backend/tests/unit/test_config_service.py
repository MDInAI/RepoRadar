"""Unit tests for JSON5 config parsing and TLS warning behavior."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

import app.services.openclaw.transport as transport_module
from app.core.config import Settings
from app.services.openclaw.config_service import (
    OpenClawConfigError,
    extract_default_model,
    parse_openclaw_config,
)
from app.services.openclaw.transport import GatewayTargetInput, resolve_gateway_target_from_input


def test_parse_openclaw_config_accepts_standard_json() -> None:
    raw = '{"gateway": {"url": "wss://gateway.local", "auth": {"token": "abc"}}}'
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"


def test_parse_openclaw_config_strips_single_line_comments() -> None:
    raw = """
    {
      // This is a comment
      "gateway": {
        "url": "wss://gateway.local" // inline comment
      }
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"


def test_parse_openclaw_config_strips_block_comments() -> None:
    raw = """
    {
      /* Multi-line block
         comment here */
      "gateway": {
        "url": "wss://gateway.local"
      }
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"


def test_parse_openclaw_config_handles_unquoted_keys() -> None:
    raw = """
    {
      gateway: {
        url: "wss://gateway.local",
        auth: { token: "secret" }
      }
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"
    assert result["gateway"]["auth"]["token"] == "secret"


def test_parse_openclaw_config_handles_trailing_commas_in_objects() -> None:
    raw = """
    {
      "gateway": {
        "url": "wss://gateway.local",
        "auth": { "token": "abc" },
      },
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"


def test_parse_openclaw_config_handles_trailing_commas_in_arrays() -> None:
    raw = """
    {
      "channels": ["telegram", "slack",],
      "gateway": {"url": "wss://g.local", "auth": {"token": "t"}}
    }
    """
    result = parse_openclaw_config(raw)
    assert result["channels"] == ["telegram", "slack"]


def test_parse_openclaw_config_handles_single_quoted_strings() -> None:
    raw = """
    {
      'gateway': {
        'url': 'wss://gateway.local',
        'auth': { 'token': 'my-token' }
      }
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://gateway.local"


def test_parse_openclaw_config_preserves_comment_chars_inside_strings() -> None:
    """Comments inside string values must not be stripped."""
    raw = """
    {
      "note": "this // is not a comment",
      "gateway": {"url": "wss://g.local", "auth": {"token": "t"}}
    }
    """
    result = parse_openclaw_config(raw)
    assert result["note"] == "this // is not a comment"


def test_parse_openclaw_config_handles_nested_block_comment_outside_strings() -> None:
    raw = """
    {
      /* comment with "quoted content" inside */
      "gateway": {"url": "wss://g.local", "auth": {"token": "t"}}
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["url"] == "wss://g.local"


def test_extract_default_model_accepts_legacy_string() -> None:
    payload = {"agents": {"defaults": {"model": " openai/gpt-5-mini "}}}
    assert extract_default_model(payload) == "openai/gpt-5-mini"


def test_extract_default_model_reads_primary_from_model_object() -> None:
    payload = {"agents": {"defaults": {"model": {"primary": " openai/gpt-5-mini "}}}}
    assert extract_default_model(payload) == "openai/gpt-5-mini"


def test_extract_default_model_returns_none_for_blank_or_missing_values() -> None:
    assert extract_default_model({"agents": {"defaults": {"model": "   "}}}) is None
    assert extract_default_model({"agents": {"defaults": {"model": {"primary": "   "}}}}) is None
    assert extract_default_model({"agents": {"defaults": {}}}) is None


def test_parse_openclaw_config_raises_on_invalid_json5() -> None:
    with pytest.raises(OpenClawConfigError):
        parse_openclaw_config("not json at all }{")


def test_parse_openclaw_config_raises_on_non_object_top_level() -> None:
    with pytest.raises(OpenClawConfigError, match="Top-level config must evaluate to an object"):
        parse_openclaw_config("[1, 2, 3]")


def test_parse_openclaw_config_full_openclaw_style_config() -> None:
    """Validate a realistic full OpenClaw JSON5 config parses correctly."""
    raw = """
    {
      // OpenClaw config
      gateway: {
        auth: { token: "my-gateway-token" },
        remote: {
          url: "wss://gateway.local",
          allowInsecureTls: false,
        },
      },
      agents: {
        defaults: {
          model: {
            primary: "openai/gpt-5-mini",
            fallbacks: ["openai/gpt-5-nano"],
          },
        },
      },
      channels: {
        telegram: { enabled: true },
      },
    }
    """
    result = parse_openclaw_config(raw)
    assert result["gateway"]["auth"]["token"] == "my-gateway-token"
    assert result["gateway"]["remote"]["url"] == "wss://gateway.local"
    assert result["agents"]["defaults"]["model"]["primary"] == "openai/gpt-5-mini"
    assert result["channels"]["telegram"]["enabled"] is True


# ---------------------------------------------------------------------------
# TLS bypass warning tests
# ---------------------------------------------------------------------------


def test_allow_insecure_tls_warning_logged_in_non_local_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transport_module,
        "settings",
        Settings(ENVIRONMENT="production"),
    )
    with patch.object(transport_module.logger, "warning") as mock_warning:
        resolve_gateway_target_from_input(
            GatewayTargetInput(
                url="wss://gateway.example.com",
                token="token",
                allow_insecure_tls=True,
                source="test",
                placeholder_source="test-missing",
            )
        )

    assert mock_warning.called
    assert any("allow_insecure_tls" in str(call) for call in mock_warning.call_args_list)


def test_allow_insecure_tls_no_warning_in_local_environment(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        transport_module,
        "settings",
        Settings(ENVIRONMENT="local"),
    )
    with caplog.at_level(logging.WARNING):
        resolve_gateway_target_from_input(
            GatewayTargetInput(
                url="wss://gateway.example.com",
                token="token",
                allow_insecure_tls=True,
                source="test",
                placeholder_source="test-missing",
            )
        )

    tls_warnings = [
        r
        for r in caplog.records
        if "allow_insecure_tls" in r.message and r.levelno == logging.WARNING
    ]
    assert len(tls_warnings) == 0


def test_allow_insecure_tls_false_produces_no_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        transport_module,
        "settings",
        Settings(ENVIRONMENT="production"),
    )
    with caplog.at_level(logging.WARNING):
        resolve_gateway_target_from_input(
            GatewayTargetInput(
                url="wss://gateway.example.com",
                token="token",
                allow_insecure_tls=False,
                source="test",
                placeholder_source="test-missing",
            )
        )

    tls_warnings = [
        r
        for r in caplog.records
        if "allow_insecure_tls" in r.message and r.levelno == logging.WARNING
    ]
    assert len(tls_warnings) == 0
