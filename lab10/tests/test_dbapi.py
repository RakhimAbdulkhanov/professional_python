from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from student_manager.models import Student
from student_manager.persistence.dbapi import (
    find_students_by_group,
    get_connection,
)


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    # тимчасова бд для тестів dbapi
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_dbapi.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL CHECK (length(trim(first_name)) > 0),
                last_name TEXT NOT NULL CHECK (length(trim(last_name)) > 0),
                average_grade REAL NOT NULL CHECK (average_grade >= 0.0 AND average_grade <= 100.0),
                group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE RESTRICT,
                email TEXT
            )
            """
        )
        conn.execute("INSERT INTO groups (name) VALUES ('ФеП-33')")
        conn.execute("INSERT INTO groups (name) VALUES ('ФеП-34')")
        conn.execute("INSERT INTO groups (name) VALUES ('special''--group')")

        conn.execute(
            """
            INSERT INTO students (first_name, last_name, average_grade, group_id, email)
            VALUES ('Остап', 'Бендер', 88.5, 1, 'ostap@example.com')
            """
        )
        conn.execute(
            """
            INSERT INTO students (first_name, last_name, average_grade, group_id, email)
            VALUES ('Тарас', 'Шевченко', 95.0, 1, 'taras@example.com')
            """
        )
        conn.execute(
            """
            INSERT INTO students (first_name, last_name, average_grade, group_id, email)
            VALUES ('Леся', 'Українка', 98.0, 2, 'lesya@example.com')
            """
        )
        conn.execute(
            """
            INSERT INTO students (first_name, last_name, average_grade, group_id, email)
            VALUES ('Іван', 'Франко', 99.0, 3, 'ivan@example.com')
            """
        )
        conn.commit()
        conn.close()
        yield db_file


def test_find_students_by_group_exact(temp_db_path: Path) -> None:
    # базовий пошук студентів за точною назвою групи
    students = find_students_by_group(temp_db_path, "ФеП-33")
    assert len(students) == 2
    assert all(isinstance(s, Student) for s in students)
    assert [s.first_name for s in students] == ["Остап", "Тарас"]
    assert students[0].group == "ФеП-33"
    assert students[0].average_grade == 88.5
    assert students[0].student_id == 1


def test_find_students_by_group_unicode_casefold(temp_db_path: Path) -> None:
    # юнікодний регістронезалежний пошук збігається з orm casefold
    lower_res = find_students_by_group(temp_db_path, "феп-33")
    upper_res = find_students_by_group(temp_db_path, "ФЕП-33")
    assert len(lower_res) == 2
    assert len(upper_res) == 2
    assert [s.first_name for s in lower_res] == ["Остап", "Тарас"]
    assert [s.first_name for s in upper_res] == ["Остап", "Тарас"]


def test_find_students_by_group_sql_injection_safe(temp_db_path: Path) -> None:
    # параметризація захищає від ін'єкцій у запиті
    injection_query = "' OR '1'='1"
    students = find_students_by_group(temp_db_path, injection_query)
    assert students == []

    drop_query = "ФеП-33'; DROP TABLE students; --"
    students = find_students_by_group(temp_db_path, drop_query)
    assert students == []

    # перевіряємо шо таблиця не дропнулась
    valid_students = find_students_by_group(temp_db_path, "ФеП-33")
    assert len(valid_students) == 2


def test_find_students_by_group_special_characters(temp_db_path: Path) -> None:
    # пошук групи зі спецсимволами та лапками
    students = find_students_by_group(temp_db_path, "special'--group")
    assert len(students) == 1
    assert students[0].first_name == "Іван"


def test_find_students_by_group_nonexistent_or_empty(temp_db_path: Path) -> None:
    # пошук неіснуючої або порожньої групи вертає пустий список
    assert find_students_by_group(temp_db_path, "Невідома") == []
    assert find_students_by_group(temp_db_path, "") == []
    assert find_students_by_group(temp_db_path, "   ") == []


def test_find_students_by_group_invalid_type(temp_db_path: Path) -> None:
    # перевірка типу аргументу назви групи
    with pytest.raises(TypeError, match="Group name must be a string"):
        find_students_by_group(temp_db_path, None)  # type: ignore[arg-type]


def test_find_students_by_group_closes_connection(temp_db_path: Path) -> None:
    # перевірка шо з'єднання sqlite закривається за будь-яких умов
    real_connect = sqlite3.connect
    opened_conns: list[sqlite3.Connection] = []

    def mock_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        c = cast(sqlite3.Connection, real_connect(*args, **kwargs))
        opened_conns.append(c)
        return c

    with patch("sqlite3.connect", side_effect=mock_connect):
        find_students_by_group(temp_db_path, "ФеП-33")

    assert len(opened_conns) == 1
    # перевіряємо чи з'єднання закрите (спроба виконати запит кине помилку)
    with pytest.raises(
        sqlite3.ProgrammingError, match="Cannot operate on a closed database"
    ):
        opened_conns[0].execute("SELECT 1")


def test_find_students_by_group_closes_on_query_error(temp_db_path: Path) -> None:
    # з'єднання закривається навіть якщо сталася помилка виконання запиту
    # видаляємо таблицю щоб викликати помилку виконання у запиті
    raw_conn = sqlite3.connect(str(temp_db_path))
    raw_conn.execute("DROP TABLE students")
    raw_conn.commit()
    raw_conn.close()

    real_connect = sqlite3.connect
    opened_conns: list[sqlite3.Connection] = []

    def mock_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        c = cast(sqlite3.Connection, real_connect(*args, **kwargs))
        opened_conns.append(c)
        return c

    with (
        patch("sqlite3.connect", side_effect=mock_connect),
        pytest.raises(sqlite3.OperationalError, match="no such table"),
    ):
        find_students_by_group(temp_db_path, "ФеП-33")

    assert len(opened_conns) == 1
    with pytest.raises(
        sqlite3.ProgrammingError, match="Cannot operate on a closed database"
    ):
        opened_conns[0].execute("SELECT 1")


def test_get_connection_enforces_foreign_keys_and_casefold(temp_db_path: Path) -> None:
    # допоміжна функція відкриття з'єднання вмикає foreign keys та lower
    conn = get_connection(temp_db_path)
    try:
        cur = conn.cursor()
        fk = cur.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        casefolded = cur.execute("SELECT lower(?)", ("ТЕСТ",)).fetchone()[0]
        assert casefolded == "тест"
    finally:
        conn.close()
