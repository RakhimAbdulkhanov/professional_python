from unittest.mock import Mock

import pytest

from student_manager.domain import Group
from student_manager.models import Student
from student_manager.registry import Notifier, ReportingService, StudentRegistry
from student_manager.repositories import InMemoryRepository, Repository


@pytest.mark.unit
def test_search_by_last_name_trims_and_ignores_case(
    populated_registry: tuple[StudentRegistry, InMemoryRepository[Student], Notifier],
) -> None:
    # пошук за прізвищем без урахування регістру та зайвих пробілів
    registry, _, _ = populated_registry
    results = registry.search_by_last_name("  бендер  ")
    assert len(results) == 1
    assert results[0].full_name == "Остап Бендер"

    upper_results = registry.search_by_last_name("ШЕВЧЕНКО")
    assert len(upper_results) == 1
    assert upper_results[0].student_id == 2

    missing = registry.search_by_last_name("Невідомий")
    assert len(missing) == 0


@pytest.mark.unit
def test_search_by_id_and_group(
    populated_registry: tuple[StudentRegistry, InMemoryRepository[Student], Notifier],
) -> None:
    # пошук за id та фільтрація за групою (стрічка і доменний об'єкт Group)
    registry, _, _ = populated_registry

    st = registry.get_by_id(1)
    assert st is not None
    assert st.last_name == "Бендер"
    assert registry.get_by_id(999) is None

    group_str = registry.search_by_group("ФеП-33")
    assert len(group_str) == 2
    ids = {s.student_id for s in group_str}
    assert ids == {1, 3}

    group_obj = registry.search_by_group(Group("феп-33"))
    assert len(group_obj) == 2

    empty_group = registry.search_by_group("Невідома-99")
    assert len(empty_group) == 0


@pytest.mark.unit
def test_find_best_student_and_average_empty_registry(
    in_memory_repository: InMemoryRepository[Student],
    recording_notifier: Notifier,
) -> None:
    # порожній реєстр повертає None для середніх балів і лідера
    empty_reg = StudentRegistry(
        repository=in_memory_repository, notifier=recording_notifier
    )
    assert empty_reg.find_best_student() is None
    assert empty_reg.get_average_grade() is None
    assert empty_reg.find_best_student("ФеП-33") is None
    assert empty_reg.get_average_grade("ФеП-33") is None


@pytest.mark.unit
def test_find_best_student_and_average_with_students(
    populated_registry: tuple[StudentRegistry, InMemoryRepository[Student], Notifier],
) -> None:
    # перевірка пошуку найкращого студента та середнього бала із pytest.approx
    registry, _, _ = populated_registry

    best = registry.find_best_student()
    assert best is not None
    assert best.student_id == 2
    assert best.average_grade == pytest.approx(94.0)

    best_group = registry.find_best_student("ФеП-33")
    assert best_group is not None
    assert best_group.student_id == 3
    assert best_group.last_name == "Українка"

    overall_avg = registry.get_average_grade()
    assert overall_avg is not None
    assert overall_avg == pytest.approx(87.5)

    group_avg = registry.get_average_grade("ФеП-33")
    assert group_avg is not None
    assert group_avg == pytest.approx(90.0)


@pytest.mark.unit
def test_registry_repository_mock_return_value(sample_student: Student) -> None:
    # використання Mock із налаштованим return_value для ізоляції репозиторію
    mock_repo = Mock(spec=Repository)
    mock_repo.get.return_value = sample_student
    mock_notifier = Mock(spec=Notifier)

    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)
    student = registry.get_by_id(1)

    assert student == sample_student
    mock_repo.get.assert_called_once_with(1)

    mock_repo.all.return_value = (sample_student,)
    all_students = list(iter(registry))
    assert all_students == [sample_student]
    mock_repo.all.assert_called_once()


@pytest.mark.unit
def test_registry_add_notifier_mock_interactions(sample_student: Student) -> None:
    # перевірка взаємодії з нотифікатором через Mock interaction assertions
    mock_repo = Mock(spec=Repository)
    mock_notifier = Mock(spec=Notifier)

    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)
    added = registry.add(1, sample_student)

    assert added.student_id == 1
    mock_repo.add.assert_called_once_with(1, added)
    mock_notifier.send.assert_called_once_with("Added student 1: Остап Бендер")


@pytest.mark.unit
def test_registry_edit_notifier_mock_interactions(sample_student: Student) -> None:
    # перевірка сповіщення при редагуванні запису
    mock_repo = Mock(spec=Repository)
    mock_repo.get.return_value = sample_student
    mock_notifier = Mock(spec=Notifier)

    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)
    updated = registry.edit(1, average_grade=95.0)

    assert updated.average_grade == pytest.approx(95.0)
    mock_repo.update.assert_called_once_with(1, updated)
    mock_notifier.send.assert_called_once_with("Updated student 1: Остап Бендер")


@pytest.mark.unit
def test_registry_add_dependency_side_effect_failure_assert_notifier_not_called(
    sample_student: Student,
) -> None:
    # збій зовнішньої залежності через side_effect блокує виклик нотифікатора
    mock_repo = Mock(spec=Repository)
    mock_repo.add.side_effect = RuntimeError("Storage connection failed")
    mock_notifier = Mock(spec=Notifier)

    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)

    with pytest.raises(RuntimeError, match="Storage connection failed"):
        registry.add(1, sample_student)

    mock_notifier.send.assert_not_called()


@pytest.mark.unit
def test_registry_edit_dependency_side_effect_failure_assert_notifier_not_called(
    sample_student: Student,
) -> None:
    # збій оновлення у репозиторії не повинен надсилати сповіщення
    mock_repo = Mock(spec=Repository)
    mock_repo.get.return_value = sample_student
    mock_repo.update.side_effect = OSError("Disk write error")
    mock_notifier = Mock(spec=Notifier)

    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)

    with pytest.raises(OSError, match="Disk write error"):
        registry.edit(1, average_grade=99.0)

    mock_notifier.send.assert_not_called()


@pytest.mark.unit
def test_reporting_service_summary_and_export(
    populated_registry: tuple[StudentRegistry, InMemoryRepository[Student], Notifier],
) -> None:
    # перевірка сервісу звітів на заповненому реєстрі
    registry, _, _ = populated_registry
    service = ReportingService(registry)

    summary = service.get_summary()
    assert summary["total_students"] == 4
    assert summary["overall_average"] == pytest.approx(87.5)
    assert summary["best_student_id"] == 2
    assert summary["best_student_name"] == "Тарас Шевченко"

    payloads = service.export_students()
    assert len(payloads) == 4
    assert payloads[0]["student_id"] == 1
    assert payloads[0]["first_name"] == "Остап"


@pytest.mark.unit
def test_registry_contains_and_getitem_dunders(
    populated_registry: tuple[StudentRegistry, InMemoryRepository[Student], Notifier],
    sample_student: Student,
) -> None:
    # перевірка магічних методів __contains__ та __getitem__
    registry, _, _ = populated_registry
    assert 1 in registry
    assert 999 not in registry
    assert sample_student in registry
    assert registry[1].full_name == "Остап Бендер"

    with pytest.raises(KeyError, match="not found"):
        _ = registry[999]
