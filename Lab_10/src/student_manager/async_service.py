from typing import Protocol, runtime_checkable

from student_manager.models import Student
from student_manager.registry import Notifier


@runtime_checkable
class AsyncStudentRepository(Protocol):
    # протокол для асинхронного сховища студентів
    async def get(self, student_id: int) -> Student | None: ...


class AsyncStudentService:
    # асинхронний сервіс завантаження студентів із нотифікацією
    def __init__(self, repository: AsyncStudentRepository, notifier: Notifier) -> None:
        self._repository = repository
        self._notifier = notifier

    async def load(self, student_id: int) -> Student | None:
        # валідуєм ідентифікатор студента
        if (
            isinstance(student_id, bool)
            or not isinstance(student_id, int)
            or student_id <= 0
        ):
            raise ValueError("student_id must be a positive integer")

        student = await self._repository.get(student_id)
        if student is not None:
            self._notifier.send(f"Loaded student {student_id}: {student.full_name}")
        return student
