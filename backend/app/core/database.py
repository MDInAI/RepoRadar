from sqlalchemy import event
from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL, echo=settings.ENVIRONMENT == "local" and settings.LOG_LEVEL == "DEBUG"
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session():
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
