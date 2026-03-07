from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import app


@contextmanager
def scaffold_test_routes() -> Iterator[None]:
    router = APIRouter()

    @router.get("/__test__/app-error")
    def app_error_route():
        raise AppError(
            message="Scaffold validation failed.",
            code="scaffold_validation_failed",
            status_code=400,
            details={"surface": "api"},
        )

    @router.get("/__test__/crash")
    def crash_route():
        raise RuntimeError("Unexpected scaffold crash.")

    original_routes = list(app.router.routes)
    original_openapi = app.openapi_schema
    app.include_router(router)
    app.openapi_schema = None
    try:
        yield
    finally:
        app.router.routes[:] = original_routes
        app.openapi_schema = original_openapi


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_app_error_returns_structured_envelope() -> None:
    with scaffold_test_routes():
        client = TestClient(app)

        response = client.get("/__test__/app-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "scaffold_validation_failed",
            "message": "Scaffold validation failed.",
            "details": {"surface": "api"},
        }
    }


def test_unhandled_error_returns_internal_error_envelope() -> None:
    with scaffold_test_routes():
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/__test__/crash")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected internal error occurred.",
            "details": None,
        }
    }
