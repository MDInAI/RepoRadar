import pytest
from collections.abc import Iterator
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
