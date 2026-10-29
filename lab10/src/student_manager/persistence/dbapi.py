from __future__ import annotations

import sqlite3
from pathlib import Path

from student_manager.models import Student


def _casefold_str(value: str | None) -> str | None:
    # юнікодний регістронезалежний переклад для sqlite
    return value.casefold() if value is not None else None


def get_connection(database: str | Path) -> sqlite3.Connection:
    # створення sqlite з'єднання з активними fk та функцією lower
    conn = sqlite3.connect(str(database))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("lower", 1, _casefold_str)
    return conn


def find_students_by_group(
    database: str | Path | sqlite3.Connection,
    group_name: str,
) -> list[Student]:
    # параметризований пошук студентів за назвою групи через db-api
    if not isinstance(group_name, str):
        raise TypeError("Group name must be a string")

    trimmed = group_name.strip()
    if not trimmed:
        return []

    owns_connection = False
    if isinstance(database, (str, Path)):
        conn = get_connection(database)
        owns_connection = True
    else:
        conn = database
        try:
            conn.create_function("lower", 1, _casefold_str)
        except sqlite3.OperationalError:
            # функція вже могла бути зареєстрована раніше
            pass

    try:
        cursor = conn.cursor()
        try:
            query = """
                SELECT s.id, s.first_name, s.last_name, g.name, s.average_grade
                FROM students s
                JOIN groups g ON s.group_id = g.id
                WHERE lower(g.name) = lower(?)
                ORDER BY s.id ASC
            """
            cursor.execute(query, (trimmed,))
            rows = cursor.fetchall()
            return [
                Student(
                    student_id=row[0],
                    first_name=row[1],
                    last_name=row[2],
                    group=row[3],
                    average_grade=float(row[4]),
                )
                for row in rows
            ]
        finally:
            cursor.close()
    finally:
        if owns_connection:
            conn.close()
