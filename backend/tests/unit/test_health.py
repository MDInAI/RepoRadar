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
