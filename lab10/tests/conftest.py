from collections.abc import Iterator
from pathlib import Path

import pytest

from student_manager.models import Student
from student_manager.registry import RecordingNotifier, StudentRegistry
from student_manager.repositories import InMemoryRepository


@pytest.fixture
def sample_student() -> Student:
    # базовий тестовий студент
    return Student(
        first_name="Остап",
        last_name="Бендер",
        group="ФеП-33",
        average_grade=88.5,
        student_id=1,
    )


@pytest.fixture
def sample_students() -> list[Student]:
    # набір студентів для тестування пошуку та агрегацій
    return [
        Student(
            first_name="Остап",
            last_name="Бендер",
            group="ФеП-33",
            average_grade=88.5,
            student_id=1,
        ),
        Student(
            first_name="Тарас",
            last_name="Шевченко",
            group="ФеП-31",
            average_grade=94.0,
            student_id=2,
        ),
        Student(
            first_name="Леся",
            last_name="Українка",
            group="ФеП-33",
            average_grade=91.5,
            student_id=3,
        ),
        Student(
            first_name="Іван",
            last_name="Франко",
            group="ФеП-32",
            average_grade=76.0,
            student_id=4,
        ),
    ]


@pytest.fixture
def sample_csv_text() -> str:
    # валідний csv вміст із чотирма записами
    return (
        "student_id,first_name,last_name,group,average_grade\n"
        "1,Остап,Бендер,ФеП-33,88.5\n"
        "2,Тарас,Шевченко,ФеП-31,94.0\n"
        "3,Леся,Українка,ФеП-33,91.5\n"
        "4,Іван,Франко,ФеП-32,76.0\n"
    )


@pytest.fixture
def recording_notifier() -> Iterator[RecordingNotifier]:
    # фікстура нотифікатора із очищенням повідомлень на teardown
    notifier = RecordingNotifier()
    yield notifier
    notifier.messages.clear()


@pytest.fixture
def in_memory_repository() -> Iterator[InMemoryRepository[Student]]:
    # фікстура репозиторію з очищенням сховища на teardown
    repo: InMemoryRepository[Student] = InMemoryRepository()
    yield repo
    repo._items.clear()


@pytest.fixture
def populated_registry(
    sample_students: list[Student],
    recording_notifier: RecordingNotifier,
) -> Iterator[tuple[StudentRegistry, InMemoryRepository[Student], RecordingNotifier]]:
    # наповнений реєстр із перевіркою та teardown очищенням
    repo: InMemoryRepository[Student] = InMemoryRepository()
    registry = StudentRegistry(repository=repo, notifier=recording_notifier)
    for st in sample_students:
        assert st.student_id is not None
        registry.add(st.student_id, st)
    yield registry, repo, recording_notifier
    repo._items.clear()
    recording_notifier.messages.clear()


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # ізоляція робочої директорії через monkeypatch з teardown відновленням
    monkeypatch.chdir(tmp_path)
    yield tmp_path
