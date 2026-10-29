from __future__ import annotations

import builtins
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from student_manager.models import Student
from student_manager.persistence.models import (
    GroupDTO,
    GroupRow,
    StudentDTO,
    StudentRow,
)


def _validate_positive_int(val: Any, name: str = "ID") -> int:
    # перевірка шо ідентифікатор є додатнім цілим числом і не bool
    if type(val) is bool or not isinstance(val, int):
        raise TypeError(f"{name} must be an integer")
    if val <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return val


class GroupRepository:
    # репозиторій для роботи з групами через caller-owned session
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str) -> GroupDTO:
        # створення нової групи
        if not isinstance(name, str):
            raise TypeError("Group name must be a string")
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("Group name cannot be empty")

        row = GroupRow(name=trimmed)
        self.session.add(row)
        self.session.flush()
        return row.to_dto()

    def get(self, group_id: int) -> GroupDTO | None:
        # пошук групи за числовим id
        _validate_positive_int(group_id, "group_id")
        row = self.session.get(GroupRow, group_id)
        return row.to_dto() if row is not None else None

    def get_by_name(self, name: str) -> GroupDTO | None:
        # пошук групи за назвою без урахування регістру
        if not isinstance(name, str):
            raise TypeError("Group name must be a string")
        trimmed = name.strip()
        if not trimmed:
            return None
        stmt = select(GroupRow).where(func.lower(GroupRow.name) == trimmed.casefold())
        row = self.session.execute(stmt).scalar_one_or_none()
        return row.to_dto() if row is not None else None

    def list(self) -> builtins.list[GroupDTO]:
        # повертає список усіх груп з детермінованим сортуванням
        stmt = select(GroupRow).order_by(GroupRow.name.asc(), GroupRow.id.asc())
        rows = self.session.execute(stmt).scalars().all()
        return [row.to_dto() for row in rows]

    def delete(self, group_id: int) -> bool:
        # видалення групи за id
        _validate_positive_int(group_id, "group_id")
        row = self.session.get(GroupRow, group_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True


class StudentRepository:
    # репозиторій для роботи зі студентами
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        student: Student,
        group_id: int | None = None,
        email: str | None = None,
    ) -> Student:
        # створення нового студента в прив'язці до групи
        if not isinstance(student, Student):
            raise TypeError("student must be an instance of Student")

        if group_id is None:
            group_row = self.session.execute(
                select(GroupRow).where(
                    func.lower(GroupRow.name) == student.group.strip().casefold()
                )
            ).scalar_one_or_none()
            if group_row is None:
                raise ValueError(f"Group '{student.group}' not found")
        else:
            _validate_positive_int(group_id, "group_id")
            group_row = self.session.get(GroupRow, group_id)
            if group_row is None:
                raise ValueError(f"Group with id {group_id} not found")

        email_val: str | None = None
        if email is not None:
            if not isinstance(email, str):
                raise TypeError("email must be a string")
            email_val = email.strip() or None

        row = StudentRow(
            first_name=student.first_name,
            last_name=student.last_name,
            average_grade=float(student.average_grade),
            group_id=group_row.id,
            email=email_val,
        )
        if student.student_id is not None:
            _validate_positive_int(student.student_id, "student_id")
            row.id = student.student_id

        self.session.add(row)
        self.session.flush()
        return row.to_student(group_row.name)

    def get(self, student_id: int) -> Student | None:
        # отримання доменного об'єкта студента за id
        _validate_positive_int(student_id, "student_id")
        stmt = (
            select(StudentRow)
            .options(joinedload(StudentRow.group))
            .where(StudentRow.id == student_id)
        )
        row = self.session.execute(stmt).unique().scalar_one_or_none()
        return row.to_student() if row is not None else None

    def get_dto(self, student_id: int) -> StudentDTO | None:
        # отримання деталізованого dto включно з email та group_id
        _validate_positive_int(student_id, "student_id")
        stmt = (
            select(StudentRow)
            .options(joinedload(StudentRow.group))
            .where(StudentRow.id == student_id)
        )
        row = self.session.execute(stmt).unique().scalar_one_or_none()
        return row.to_dto() if row is not None else None

    def list(self, offset: int = 0, limit: int = 100) -> builtins.list[Student]:
        # пагінований список студентів за зростанням id
        if type(offset) is bool or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        if type(limit) is bool or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")

        stmt = (
            select(StudentRow)
            .options(joinedload(StudentRow.group))
            .order_by(StudentRow.id.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = self.session.execute(stmt).unique().scalars().all()
        return [row.to_student() for row in rows]

    def search_by_last_name(self, surname: str) -> builtins.list[Student]:
        # пошук за прізвищем без урахування регістру та зайвих пробілів
        if not isinstance(surname, str):
            raise TypeError("surname must be a string")
        trimmed = surname.strip()
        if not trimmed:
            raise ValueError("surname cannot be empty")

        stmt = (
            select(StudentRow)
            .options(joinedload(StudentRow.group))
            .where(func.lower(func.trim(StudentRow.last_name)) == trimmed.casefold())
            .order_by(StudentRow.id.asc())
        )
        rows = self.session.execute(stmt).unique().scalars().all()
        return [row.to_student() for row in rows]

    def filter_by_group(self, group_id: int) -> builtins.list[Student]:
        # фільтрація студентів конкретної групи
        _validate_positive_int(group_id, "group_id")
        stmt = (
            select(StudentRow)
            .options(joinedload(StudentRow.group))
            .where(StudentRow.group_id == group_id)
            .order_by(StudentRow.id.asc())
        )
        rows = self.session.execute(stmt).unique().scalars().all()
        return [row.to_student() for row in rows]

    def update(
        self,
        student_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        group_id: int | None = None,
        average_grade: float | None = None,
        email: str | None = None,
    ) -> Student | None:
        # оновлення окремих полів студента
        _validate_positive_int(student_id, "student_id")
        row = self.session.get(StudentRow, student_id)
        if row is None:
            return None

        validated_first = row.first_name
        validated_last = row.last_name
        validated_group = row.group_id
        validated_grade = row.average_grade
        validated_email = row.email
        if first_name is not None:
            if not isinstance(first_name, str):
                raise TypeError("first_name must be a string")
            validated_first = first_name.strip()
            if not validated_first:
                raise ValueError("first_name cannot be empty")
        if last_name is not None:
            if not isinstance(last_name, str):
                raise TypeError("last_name must be a string")
            validated_last = last_name.strip()
            if not validated_last:
                raise ValueError("last_name cannot be empty")
        if group_id is not None:
            _validate_positive_int(group_id, "group_id")
            if self.session.get(GroupRow, group_id) is None:
                raise ValueError(f"Group with id {group_id} not found")
            validated_group = group_id
        if average_grade is not None:
            if type(average_grade) is bool or not isinstance(
                average_grade, (int, float)
            ):
                raise TypeError("average_grade must be a number")
            validated_grade = float(average_grade)
            if not 0.0 <= validated_grade <= 100.0:
                raise ValueError("Average grade must be between 0 and 100")
        if email is not None:
            if not isinstance(email, str):
                raise TypeError("email must be a string")
            validated_email = email.strip() or None

        row.first_name = validated_first
        row.last_name = validated_last
        row.group_id = validated_group
        row.average_grade = validated_grade
        row.email = validated_email

        self.session.flush()
        target_grp = self.session.get(GroupRow, row.group_id)
        grp_name = target_grp.name if target_grp is not None else ""
        return row.to_student(grp_name)

    def delete(self, student_id: int) -> bool:
        # видалення студента за id
        _validate_positive_int(student_id, "student_id")
        row = self.session.get(StudentRow, student_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def best(self, group_id: int | None = None) -> Student | None:
        # найкращий студент з детермінованим tie-breaker
        if group_id is not None:
            _validate_positive_int(group_id, "group_id")
        stmt = select(StudentRow).options(joinedload(StudentRow.group))
        if group_id is not None:
            stmt = stmt.where(StudentRow.group_id == group_id)
        stmt = stmt.order_by(
            StudentRow.average_grade.desc(), StudentRow.id.asc()
        ).limit(1)
        row = self.session.execute(stmt).unique().scalar_one_or_none()
        return row.to_student() if row is not None else None

    def average(self, group_id: int | None = None) -> float | None:
        # обчислення середнього балу через sql avg
        if group_id is not None:
            _validate_positive_int(group_id, "group_id")
        stmt = select(func.avg(StudentRow.average_grade))
        if group_id is not None:
            stmt = stmt.where(StudentRow.group_id == group_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return float(result) if result is not None else None

    def count(self, group_id: int | None = None) -> int:
        # кількість студентів через sql count
        if group_id is not None:
            _validate_positive_int(group_id, "group_id")
        stmt = select(func.count(StudentRow.id))
        if group_id is not None:
            stmt = stmt.where(StudentRow.group_id == group_id)
        return int(self.session.execute(stmt).scalar_one_or_none() or 0)
