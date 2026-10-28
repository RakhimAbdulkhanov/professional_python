from collections.abc import Iterator
from dataclasses import replace
from typing import Protocol, runtime_checkable

from student_manager.domain import (
    Group,
    RegistrySummary,
    StudentPayload,
    student_to_payload,
)
from student_manager.models import Student
from student_manager.repositories import Repository


@runtime_checkable
class Notifier(Protocol):
    # протокол для відправки сповіщень
    def send(self, message: str) -> None: ...


class ConsoleNotifier:
    # вивід сповіщень у стандартну консоль
    def send(self, message: str) -> None:
        print(message)


class RecordingNotifier:
    # запис повідомлень для тестів та аудиту
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


class StudentRegistry:
    # реєстр студентів із контролем цілісності та сповіщеннями
    def __init__(self, repository: Repository[Student], notifier: Notifier) -> None:
        self._repository = repository
        self._notifier = notifier

    def add(self, student_id: int, student: Student) -> Student:
        # валідуєм id і додаєм копію студента з узгодженим id
        if (
            isinstance(student_id, bool)
            or not isinstance(student_id, int)
            or student_id <= 0
        ):
            raise ValueError("student_id must be a positive integer")

        existing_id = student.student_id
        if existing_id is not None and existing_id != student_id:
            raise ValueError("Inconsistent student_id between entity and registry key")

        stored_student = replace(student, student_id=student_id)

        self._repository.add(student_id, stored_student)
        self._notifier.send(f"Added student {student_id}: {stored_student.full_name}")
        return stored_student

    def edit(
        self,
        student_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        group: str | None = None,
        average_grade: float | None = None,
    ) -> Student:
        # атомарне оновлення студента через replace
        existing = self.get_by_id(student_id)
        if existing is None:
            raise KeyError(f"Student with ID {student_id} not found")

        # валідація спрацює в __post_init__, оригінал не пошкодиться при помилці
        updated = replace(
            existing,
            first_name=existing.first_name if first_name is None else first_name,
            last_name=existing.last_name if last_name is None else last_name,
            group=existing.group if group is None else group,
            average_grade=existing.average_grade
            if average_grade is None
            else average_grade,
        )

        self._repository.update(student_id, updated)
        self._notifier.send(f"Updated student {student_id}: {updated.full_name}")
        return updated

    def get_by_id(self, student_id: int) -> Student | None:
        # пошук за числовим ідентифікатором
        if type(student_id) is not int or student_id <= 0:
            raise ValueError("student_id must be a positive integer")
        return self._repository.get(student_id)

    def search_by_last_name(self, surname: str) -> tuple[Student, ...]:
        # точний пошук за прізвищем без урахування регістру та пробілів
        target = surname.strip().casefold()
        return tuple(
            s
            for s in self._repository.all()
            if s.last_name.strip().casefold() == target
        )

    def search_by_group(self, group: str | Group) -> tuple[Student, ...]:
        # пошук за групою через рядок або об'єкт Group
        group_str = group.name if isinstance(group, Group) else str(group)
        target = group_str.strip().casefold()
        return tuple(
            s for s in self._repository.all() if s.group.strip().casefold() == target
        )

    def get_average_grade(self, group: str | Group | None = None) -> float | None:
        # обчислення середнього балу для групи або всього реєстру
        students = (
            self.search_by_group(group) if group is not None else self._repository.all()
        )
        if not students:
            return None
        return sum(s.average_grade for s in students) / len(students)

    def find_best_student(self, group: str | Group | None = None) -> Student | None:
        # пошук студента з найвищим середнім балом
        students = (
            self.search_by_group(group) if group is not None else self._repository.all()
        )
        if not students:
            return None
        return max(students, key=lambda s: s.average_grade)

    def __len__(self) -> int:
        return len(self._repository.all())

    def __iter__(self) -> Iterator[Student]:
        return iter(self._repository.all())

    def __contains__(self, item: object) -> bool:
        # перевірка наявності id або сутності студента
        if isinstance(item, bool):
            return False
        if isinstance(item, int):
            return self._repository.get(item) is not None
        if isinstance(item, Student):
            sid = getattr(item, "student_id", None)
            if sid is not None:
                return self._repository.get(sid) == item
            return item in self._repository.all()
        return False

    def __getitem__(self, key: int) -> Student:
        # доступ за індексом через квадратні дужки
        if isinstance(key, bool) or not isinstance(key, int):
            raise TypeError("Key must be an integer ID")
        student = self._repository.get(key)
        if student is None:
            raise KeyError(f"Student with ID {key} not found")
        return student


class ReportingService:
    # сервіс генерації типізованих звітів
    def __init__(self, registry: StudentRegistry) -> None:
        self._registry = registry

    def export_students(self) -> tuple[StudentPayload, ...]:
        # експорт усіх студентів у форматі TypedDict
        result: list[StudentPayload] = []
        for student in self._registry:
            sid = student.student_id
            if sid is None:
                raise ValueError("Registered student must have an ID")
            result.append(student_to_payload(student, sid))
        return tuple(result)

    def get_summary(self) -> RegistrySummary:
        # коротке числове резюме по реєстру
        avg = self._registry.get_average_grade()
        best = self._registry.find_best_student()
        return {
            "total_students": len(self._registry),
            "overall_average": round(avg, 2) if avg is not None else None,
            "best_student_id": getattr(best, "student_id", None) if best else None,
            "best_student_name": best.full_name if best else None,
        }
