from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from student_manager.models import Student


class Base(DeclarativeBase):
    # базовий декларативний клас для таблиць
    pass


@dataclass(frozen=True, slots=True)
class GroupDTO:
    # безпечний dto для передачі даних групи поза сесією
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class StudentDTO:
    # безпечний dto для студента включно з email і group_id
    id: int
    first_name: str
    last_name: str
    group_id: int
    group_name: str
    average_grade: float
    email: str | None = None

    def to_student(self) -> Student:
        # конвертація в стандартну доменну модель student
        return Student(
            first_name=self.first_name,
            last_name=self.last_name,
            group=self.group_name,
            average_grade=self.average_grade,
            student_id=self.id,
        )


class GroupRow(Base):
    # orm сутність таблиці groups
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="check_group_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    students: Mapped[list[StudentRow]] = relationship(
        back_populates="group", passive_deletes=True
    )

    def to_dto(self) -> GroupDTO:
        # створення незмінного dto об'єкта
        return GroupDTO(id=self.id, name=self.name)


class StudentRow(Base):
    # orm сутність таблиці students
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint(
            "average_grade >= 0.0 AND average_grade <= 100.0",
            name="check_student_average_grade_range",
        ),
        CheckConstraint(
            "length(trim(first_name)) > 0",
            name="check_student_first_name_nonempty",
        ),
        CheckConstraint(
            "length(trim(last_name)) > 0",
            name="check_student_last_name_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    average_grade: Mapped[float] = mapped_column(Float, nullable=False)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    group: Mapped[GroupRow] = relationship(back_populates="students")

    def to_student(self, group_name: str | None = None) -> Student:
        # конвертація orm рядка в доменний dataclass
        grp = (
            group_name
            if group_name is not None
            else (self.group.name if self.group else "")
        )
        return Student(
            first_name=self.first_name,
            last_name=self.last_name,
            group=grp,
            average_grade=self.average_grade,
            student_id=self.id,
        )

    def to_dto(self, group_name: str | None = None) -> StudentDTO:
        # конвертація orm рядка в деталізований dto
        grp = (
            group_name
            if group_name is not None
            else (self.group.name if self.group else "")
        )
        return StudentDTO(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            group_id=self.group_id,
            group_name=grp,
            average_grade=self.average_grade,
            email=self.email,
        )
