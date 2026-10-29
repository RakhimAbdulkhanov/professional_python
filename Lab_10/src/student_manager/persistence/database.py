from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(url: str, echo: bool = False, **kwargs: Any) -> Engine:
    # створення рушія sqlalchemy з налаштуванням sqlite foreign keys
    engine = create_engine(url, echo=echo, **kwargs)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection: Any, connection_record: Any
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            if hasattr(dbapi_connection, "create_function"):
                dbapi_connection.create_function(
                    "lower",
                    1,
                    lambda s: s.casefold() if s is not None else None,
                )

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # створення фабрики сесій без застарівання об'єктів після коміту
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    # контекстний менеджер життєвого циклу сесії з транзакцією
    session = session_factory()
    try:
        yield session
        if session.in_transaction():
            session.commit()
    except Exception:
        if session.in_transaction():
            session.rollback()
        raise
    finally:
        session.close()
