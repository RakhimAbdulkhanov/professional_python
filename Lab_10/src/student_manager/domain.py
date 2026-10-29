import math
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import TypedDict, TypeVar

from student_manager.models import Student

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Group:
    # валідована назва академічної групи
    name: str

    def __post_init__(self) -> None:
        cleaned = self.name.strip()
        if not cleaned:
            raise ValueError("Group name cannot be empty")
        object.__setattr__(self, "name", cleaned)

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Grade:
    # скінченна оцінка від 0 до 100 балів
    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool):
            raise TypeError("Grade value cannot be a boolean")
        try:
            val = float(self.value)
        except (TypeError, ValueError) as err:
            raise ValueError("Grade value must be a valid number") from err

        if not math.isfinite(val):
            raise ValueError("Grade must be a finite number")
        if not 0.0 <= val <= 100.0:
            raise ValueError("Grade must be between 0 and 100")
        object.__setattr__(self, "value", val)

    def __float__(self) -> float:
        return self.value

    def __str__(self) -> str:
        return f"{self.value:g}"


@dataclass(frozen=True, slots=True)
class AcademicRecord:
    # академічна картка студента з незмінним списком оцінок
    student_id: int
    grades: tuple[Grade, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            isinstance(self.student_id, bool)
            or not isinstance(self.student_id, int)
            or self.student_id <= 0
        ):
            raise ValueError("student_id must be a positive integer")

        cleaned_grades: list[Grade] = []
        for item in self.grades:
            if not isinstance(item, Grade):
                raise TypeError("grades must contain only Grade instances")
            cleaned_grades.append(item)
        object.__setattr__(self, "grades", tuple(cleaned_grades))

    @property
    def average(self) -> float | None:
        if not self.grades:
            return None
        return sum(float(g) for g in self.grades) / len(self.grades)

    def add_grade(self, grade: Grade) -> "AcademicRecord":
        if not isinstance(grade, Grade):
            raise TypeError("grade must be a Grade instance")
        return replace(self, grades=(*self.grades, grade))

    def __len__(self) -> int:
        return len(self.grades)

    def __iter__(self) -> Iterator[Grade]:
        return iter(self.grades)


class StudentPayload(TypedDict):
    # структура даних для експорту та api звітів
    student_id: int
    first_name: str
    last_name: str
    group: str
    average_grade: float


class RegistrySummary(TypedDict):
    # підсумкова статистика реєстру студентів
    total_students: int
    overall_average: float | None
    best_student_id: int | None
    best_student_name: str | None


def student_to_payload(student: Student, student_id: int) -> StudentPayload:
    # перетворює сутність студента у типізований словник
    return {
        "student_id": student_id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "group": student.group,
        "average_grade": student.average_grade,
    }
