from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app.core.config import settings


def _create_engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "echo": settings.ENVIRONMENT == "local" and settings.LOG_LEVEL == "DEBUG"
    }
    try:
        if make_url(database_url).get_backend_name() == "sqlite":
            kwargs["connect_args"] = {"timeout": 30, "check_same_thread": False}
    except Exception:
        pass
    return kwargs


engine = create_engine(settings.DATABASE_URL, **_create_engine_kwargs(settings.DATABASE_URL))


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    del connection_record
    if engine.dialect.name == "sqlite":
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            # Some ephemeral sqlite test databases cannot switch journal modes.
            pass
        cursor.close()


def get_session():
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
