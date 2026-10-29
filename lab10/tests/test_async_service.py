import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from student_manager.async_service import (
    AsyncStudentRepository,
    AsyncStudentService,
)
from student_manager.models import Student
from student_manager.registry import Notifier, RecordingNotifier


class InMemoryAsyncStudentRepository:
    # проста асинхронна пам'ять для тесту реального циклу подій
    def __init__(self, data: dict[int, Student] | None = None) -> None:
        self._data = dict(data) if data else {}

    async def get(self, student_id: int) -> Student | None:
        await asyncio.sleep(0)
        return self._data.get(student_id)


class AsyncStudentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AsyncMock(spec=AsyncStudentRepository)
        self.notifier = Mock(spec=Notifier)
        self.service = AsyncStudentService(self.repository, self.notifier)
        self.sample_student = Student(
            student_id=1,
            first_name="Олена",
            last_name="Коваль",
            group="ФеП-33",
            average_grade=92.5,
        )

    def test_load_success_returns_student_and_notifies(self) -> None:
        # успішне завантаження з сповіщенням
        self.repository.get.return_value = self.sample_student

        result = asyncio.run(self.service.load(1))

        self.assertEqual(result, self.sample_student)
        self.repository.get.assert_awaited_once_with(1)
        self.notifier.send.assert_called_once_with("Loaded student 1: Олена Коваль")

    def test_load_missing_student_returns_none_and_does_not_notify(self) -> None:
        # відсутній студент повертає None і не шле повідомлення
        self.repository.get.return_value = None

        result = asyncio.run(self.service.load(42))

        self.assertIsNone(result)
        self.repository.get.assert_awaited_once_with(42)
        self.notifier.send.assert_not_called()

    def test_load_repository_failure_propagates_and_does_not_notify(self) -> None:
        # помилка репозиторію прокидається наверх
        self.repository.get.side_effect = RuntimeError("database connection failed")

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(self.service.load(1))

        self.assertEqual(str(ctx.exception), "database connection failed")
        self.repository.get.assert_awaited_once_with(1)
        self.notifier.send.assert_not_called()

    def test_load_invalid_ids_raise_value_error_without_awaiting(self) -> None:
        # некоректні id кидають ValueError без звернення до репозиторію
        invalid_ids = [0, -1, -50, True, False, "1", 2.5, None, [1]]
        for bad_id in invalid_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ValueError) as ctx:
                    asyncio.run(self.service.load(bad_id))  # type: ignore[arg-type]
                self.assertEqual(
                    str(ctx.exception), "student_id must be a positive integer"
                )

        self.repository.get.assert_not_awaited()
        self.notifier.send.assert_not_called()

    def test_load_notifier_failure_propagates(self) -> None:
        # помилка нотифікатора не глушиться
        self.repository.get.return_value = self.sample_student
        self.notifier.send.side_effect = ConnectionResetError("network unavailable")

        with self.assertRaises(ConnectionResetError) as ctx:
            asyncio.run(self.service.load(1))

        self.assertEqual(str(ctx.exception), "network unavailable")
        self.repository.get.assert_awaited_once_with(1)
        self.notifier.send.assert_called_once_with("Loaded student 1: Олена Коваль")

    def test_real_async_repository_flow(self) -> None:
        # повний сценарій із реальною асинхронною імплементацією
        repo = InMemoryAsyncStudentRepository({1: self.sample_student})
        notifier = RecordingNotifier()
        service = AsyncStudentService(repo, notifier)

        loaded = asyncio.run(service.load(1))
        self.assertEqual(loaded, self.sample_student)
        self.assertEqual(notifier.messages, ["Loaded student 1: Олена Коваль"])

        missing = asyncio.run(service.load(99))
        self.assertIsNone(missing)
        self.assertEqual(notifier.messages, ["Loaded student 1: Олена Коваль"])


if __name__ == "__main__":
    unittest.main()
