from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from student_manager.models import Student
from student_manager.persistence.models import (
    GroupDTO,
    GroupRow,
    StudentDTO,
    StudentRow,
)
from student_manager.persistence.repositories import (
    GroupRepository,
    StudentRepository,
    _validate_positive_int,
)


class StudentPersistenceService:
    # сервіс зберігання що керує межами транзакцій
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        session: Session | None = None,
    ) -> None:
        if (session_factory is None) == (session is None):
            raise ValueError("Provide exactly one of session_factory or session")
        self._session_factory = session_factory
        self._session = session

    @contextmanager
    def _read_session(self) -> Generator[Session, None, None]:
        # контекст сесії для операцій читання
        if self._session is not None:
            yield self._session
        elif self._session_factory is not None:
            with self._session_factory() as s:
                yield s

    @contextmanager
    def _write_session(self) -> Generator[Session, None, None]:
        # контекст сесії з фіксацією транзакції та відкатом при помилці
        if self._session_factory is not None:
            with self._session_factory() as s:
                try:
                    s.begin()
                    yield s
                    s.commit()
                except Exception:
                    if s.in_transaction():
                        s.rollback()
                    raise
        elif self._session is not None:
            s = self._session
            if not s.in_transaction():
                try:
                    s.begin()
                    yield s
                    s.commit()
                except Exception:
                    if s.in_transaction():
                        s.rollback()
                    raise
            else:
                with s.begin_nested():
                    yield s

    def create_group(self, name: str) -> GroupDTO:
        # створення групи в транзакції
        with self._write_session() as s:
            return GroupRepository(s).create(name)

    def get_group(self, group_id: int) -> GroupDTO | None:
        # отримання групи за id
        with self._read_session() as s:
            return GroupRepository(s).get(group_id)

    def list_groups(self) -> list[GroupDTO]:
        # список усіх груп
        with self._read_session() as s:
            return GroupRepository(s).list()

    def delete_group(self, group_id: int) -> bool:
        # видалення групи
        with self._write_session() as s:
            return GroupRepository(s).delete(group_id)

    def create_student(
        self,
        student: Student,
        group_id: int | None = None,
        email: str | None = None,
    ) -> Student:
        # створення студента в транзакції
        with self._write_session() as s:
            return StudentRepository(s).create(student, group_id=group_id, email=email)

    def get_student(self, student_id: int) -> Student | None:
        # пошук студента за id
        with self._read_session() as s:
            return StudentRepository(s).get(student_id)

    def get_student_dto(self, student_id: int) -> StudentDTO | None:
        # отримання dto студента
        with self._read_session() as s:
            return StudentRepository(s).get_dto(student_id)

    def list_students(self, offset: int = 0, limit: int = 100) -> list[Student]:
        # пагінований список студентів
        with self._read_session() as s:
            return StudentRepository(s).list(offset=offset, limit=limit)

    def search_students_by_last_name(self, surname: str) -> list[Student]:
        # пошук студентів за прізвищем
        with self._read_session() as s:
            return StudentRepository(s).search_by_last_name(surname)

    def filter_students_by_group(self, group_id: int) -> list[Student]:
        # фільтрація за id групи
        with self._read_session() as s:
            return StudentRepository(s).filter_by_group(group_id)

    def update_student(
        self,
        student_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        group_id: int | None = None,
        average_grade: float | None = None,
        email: str | None = None,
    ) -> Student | None:
        # оновлення студента в транзакції
        with self._write_session() as s:
            return StudentRepository(s).update(
                student_id,
                first_name=first_name,
                last_name=last_name,
                group_id=group_id,
                average_grade=average_grade,
                email=email,
            )

    def delete_student(self, student_id: int) -> bool:
        # видалення студента в транзакції
        with self._write_session() as s:
            return StudentRepository(s).delete(student_id)

    def get_best_student(self, group_id: int | None = None) -> Student | None:
        # пошук найкращого студента
        with self._read_session() as s:
            return StudentRepository(s).best(group_id=group_id)

    def get_group_average(self, group_id: int | None = None) -> float | None:
        # обчислення середнього балу
        with self._read_session() as s:
            return StudentRepository(s).average(group_id=group_id)

    def count_students(self, group_id: int | None = None) -> int:
        # підрахунок кількості студентів
        with self._read_session() as s:
            return StudentRepository(s).count(group_id=group_id)

    def transfer_students(
        self, student_ids: Sequence[int], target_group_id: int
    ) -> int:
        # масове атомарне переведення студентів до цільової групи
        _validate_positive_int(target_group_id, "target_group_id")
        if not student_ids:
            return 0

        # перевіряємо наявність дублікатів та валідність кожного id
        seen: set[int] = set()
        for sid in student_ids:
            _validate_positive_int(sid, "student_id")
            if sid in seen:
                raise ValueError(f"Duplicate student ID {sid} in transfer list")
            seen.add(sid)

        with self._write_session() as s:
            target_group = s.get(GroupRow, target_group_id)
            if target_group is None:
                raise ValueError(
                    f"Target group with ID {target_group_id} does not exist"
                )

            for sid in student_ids:
                row = s.get(StudentRow, sid)
                if row is None:
                    raise ValueError(f"Student with ID {sid} does not exist")
                row.group_id = target_group_id

            s.flush()
            return len(student_ids)
