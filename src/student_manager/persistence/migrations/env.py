from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, event, pool, text

from student_manager.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # безпечне отримання url з підтримкою target_url або override через DATABASE_URL
    target = getattr(config, "attributes", {}).get("target_url")
    if target:
        return str(target)
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return "sqlite:///student_manager.db"


def run_migrations_offline() -> None:
    # запуск міграцій в офлайн режимі без підключення до бд
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # запуск міграцій онлайн з контролем sqlite foreign keys
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        url = get_url()
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = url
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        if connectable.dialect.name == "sqlite":

            @event.listens_for(connectable, "connect")
            def _enable_sqlite_fk(
                dbapi_connection: Any, connection_record: Any
            ) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        with connectable.connect() as connection:
            if connection.dialect.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys=ON"))
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )

            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        connectable.dispose()
    else:
        if connectable.dialect.name == "sqlite":
            connectable.execute(text("PRAGMA foreign_keys=ON"))
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()
        if hasattr(connectable, "commit"):
            connectable.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
