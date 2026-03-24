from __future__ import annotations

from app.core import database


def test_create_engine_kwargs_adds_sqlite_connect_args() -> None:
    kwargs = database._create_engine_kwargs("sqlite:///../runtime/data/sqlite/agentic_workflow.db")

    assert kwargs["connect_args"] == {"timeout": 30, "check_same_thread": False}


def test_create_engine_kwargs_leaves_non_sqlite_urls_unchanged() -> None:
    kwargs = database._create_engine_kwargs("postgresql://user:pass@localhost/app")

    assert "connect_args" not in kwargs
