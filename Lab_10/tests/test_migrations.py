from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from student_manager.persistence.models import Base


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    # тимчасовий sqlite файл для міграцій
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_migration.db"
        yield db_file


@pytest.fixture
def alembic_config(temp_db_path: Path) -> Config:
    # конфігурація alembic з ізольованим url тестової бд
    project_root = Path(__file__).resolve().parent.parent
    ini_path = project_root / "alembic.ini"
    cfg = Config(str(ini_path))
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_lifecycle_upgrade_downgrade_preserves_data(
    alembic_config: Config, temp_db_path: Path
) -> None:
    # тестуємо повний цикл міграцій 0001 -> 0002 -> 0001 -> 0002 зі збереженням даних
    # 1. апгрейд до базової ревізії 0001_initial
    command.upgrade(alembic_config, "0001_initial")

    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "groups" in tables
        assert "students" in tables

        # перевіряємо відсутність колонки email у базовій ревізії
        student_cols = [c["name"] for c in inspector.get_columns("students")]
        assert "id" in student_cols
        assert "first_name" in student_cols
        assert "last_name" in student_cols
        assert "average_grade" in student_cols
        assert "group_id" in student_cols
        assert "email" not in student_cols

        # вставляємо початкові дані у версії 0001
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.execute(text("INSERT INTO groups (id, name) VALUES (1, 'ФеП-33')"))
            conn.execute(
                text(
                    "INSERT INTO students (id, first_name, last_name, average_grade, group_id) "
                    "VALUES (1, 'Тарас', 'Шевченко', 95.5, 1)"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    # 2. апгрейд до 0002_student_email
    command.upgrade(alembic_config, "0002_student_email")

    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        student_cols_v2 = [c["name"] for c in inspector.get_columns("students")]
        assert "email" in student_cols_v2

        # перевіряємо збереження існуючих даних та значення email=None
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, first_name, last_name, average_grade, group_id, email FROM students WHERE id = 1"
                )
            ).fetchone()
            assert row is not None
            assert row[0] == 1
            assert row[1] == "Тарас"
            assert row[2] == "Шевченко"
            assert row[3] == 95.5
            assert row[4] == 1
            assert row[5] is None

            # додаємо студента з email у версії 0002
            conn.execute(
                text(
                    "INSERT INTO students (id, first_name, last_name, average_grade, group_id, email) "
                    "VALUES (2, 'Леся', 'Українка', 98.0, 1, 'lesya@lnu.edu.ua')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    # 3. даунгрейд назад до 0001_initial
    command.downgrade(alembic_config, "0001_initial")

    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        student_cols_v1_again = [c["name"] for c in inspector.get_columns("students")]
        assert "email" not in student_cols_v1_again

        # перевіряємо збереження записів після даунгрейду
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, first_name, last_name, average_grade, group_id FROM students ORDER BY id"
                )
            ).fetchall()
            assert len(rows) == 2
            assert rows[0][:3] == (1, "Тарас", "Шевченко")
            assert rows[1][:3] == (2, "Леся", "Українка")
    finally:
        engine.dispose()

    # 4. повторний апгрейд до head (0002_student_email)
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "email" in [c["name"] for c in inspector.get_columns("students")]

        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM students")).scalar_one()
            assert count == 2
    finally:
        engine.dispose()


def test_schema_constraints_and_foreign_keys(
    alembic_config: Config, temp_db_path: Path
) -> None:
    # перевірка обмежень бази даних: unique, check, restrict foreign key
    command.upgrade(alembic_config, "head")
    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")

    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.execute(text("INSERT INTO groups (id, name) VALUES (1, 'ФеП-33')"))
            conn.commit()

            # унікальність назви групи
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO groups (id, name) VALUES (2, 'ФеП-33')"))
                conn.commit()
            conn.rollback()

            # check constraint: непорожня назва групи
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO groups (id, name) VALUES (2, '   ')"))
                conn.commit()
            conn.rollback()

            # check constraint: діапазон оцінки [0, 100]
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO students (first_name, last_name, average_grade, group_id) "
                        "VALUES ('Іван', 'Франко', 105.0, 1)"
                    )
                )
                conn.commit()
            conn.rollback()

            # foreign key constraint: неіснуюча група
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO students (first_name, last_name, average_grade, group_id) "
                        "VALUES ('Іван', 'Франко', 90.0, 999)"
                    )
                )
                conn.commit()
            conn.rollback()

            # RESTRICT foreign key: не можна видалити групу зі студентами
            conn.execute(
                text(
                    "INSERT INTO students (id, first_name, last_name, average_grade, group_id) "
                    "VALUES (1, 'Іван', 'Франко', 90.0, 1)"
                )
            )
            conn.commit()

            with pytest.raises(IntegrityError):
                conn.execute(text("DELETE FROM groups WHERE id = 1"))
                conn.commit()
            conn.rollback()
    finally:
        engine.dispose()


def test_schema_matches_orm_metadata_at_head(
    alembic_config: Config, temp_db_path: Path
) -> None:
    # перевіряємо повну відповідність структури міграції head з orm Base.metadata
    command.upgrade(alembic_config, "head")
    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")

    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            diff = compare_metadata(ctx, Base.metadata)
            # diff має бути порожнім: відсутні розбіжності між orm та базою
            assert diff == []
    finally:
        engine.dispose()


def test_env_database_url_override(alembic_config: Config, temp_db_path: Path) -> None:
    # перевіряємо шо змінна середовища DATABASE_URL перекриває конфіг
    override_file = temp_db_path.parent / "override.db"
    override_url = f"sqlite:///{override_file.as_posix()}"

    with patch.dict(os.environ, {"DATABASE_URL": override_url}):
        command.upgrade(alembic_config, "head")

    # файл override_file має бути створений і містити таблиці
    assert override_file.exists()
    eng = create_engine(override_url)
    try:
        tables = inspect(eng).get_table_names()
        assert "groups" in tables
        assert "students" in tables
    finally:
        eng.dispose()
