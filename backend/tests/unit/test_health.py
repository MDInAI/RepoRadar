from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_backend_settings_expose_frontend_origins_from_configured_port():
    settings = Settings(FRONTEND_PORT=3105)

    assert settings.frontend_origins == [
        "http://localhost:3105",
        "http://127.0.0.1:3105",
    ]


def test_backend_settings_allow_configuring_event_bridge_poll_interval():
    settings = Settings(EVENT_BRIDGE_POLL_INTERVAL_SECONDS=4.5)

    assert settings.EVENT_BRIDGE_POLL_INTERVAL_SECONDS == 4.5


def test_backend_settings_allow_configuring_event_stream_limits():
    settings = Settings(
        EVENT_STREAM_PING_INTERVAL_SECONDS=8.0,
        EVENT_STREAM_MAX_SUBSCRIBERS=32,
        EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE=64,
    )

    assert settings.EVENT_STREAM_PING_INTERVAL_SECONDS == 8.0
    assert settings.EVENT_STREAM_MAX_SUBSCRIBERS == 32
    assert settings.EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE == 64
