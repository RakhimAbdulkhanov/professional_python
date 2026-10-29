from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from student_manager.models import Student
from student_manager.persistence.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from student_manager.persistence.models import (
    Base,
    GroupDTO,
    StudentDTO,
    StudentRow,
)
from student_manager.persistence.repositories import (
    GroupRepository,
    StudentRepository,
)
from student_manager.persistence.service import (
    StudentPersistenceService,
)


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    # тимчасовий ізольований sqlite файл для кожного тесту
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink(missing_ok=True)


@pytest.fixture
def engine(temp_db_path: Path) -> Generator[Engine, None, None]:
    # створюємо рушій бд з обов'язковим увімкненням fk
    eng = create_database_engine(f"sqlite:///{temp_db_path}")
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    # фабрика сесій для тестів
    return create_session_factory(engine)


def test_sqlite_foreign_keys_enforced(engine: Engine) -> None:
    # перевіряємо шо pragma foreign_keys реально активна
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert res == 1


def test_session_scope_commit_and_rollback(
    session_factory: sessionmaker[Session],
) -> None:
    # перевіряємо автокоміт та відкат транзакції в контекстному менеджері
    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        repo.create("ФеП-31")

    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        assert repo.get(1) is not None

    with pytest.raises(RuntimeError), session_scope(session_factory) as session:
        repo = GroupRepository(session)
        repo.create("ФеП-32")
        raise RuntimeError("навмисний збій")

    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        # друга група не збереглась через відкат
        assert repo.get(2) is None


def test_group_crud_and_constraints(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка crud операцій та обмежень груп
    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        g1 = repo.create("ФеП-33")
        assert isinstance(g1, GroupDTO)
        assert g1.id == 1
        assert g1.name == "ФеП-33"

    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        fetched = repo.get(1)
        assert fetched is not None
        assert fetched.name == "ФеП-33"

        groups = repo.list()
        assert len(groups) == 1
        assert groups[0].name == "ФеП-33"

    # заборона порожньої назви
    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        with pytest.raises(ValueError):
            repo.create("   ")

    # заборона дублікатів назви групи (unique constraint)
    with pytest.raises(IntegrityError), session_scope(session_factory) as session:
        repo = GroupRepository(session)
        repo.create("ФеП-33")

    # успішне видалення порожньої групи
    with session_scope(session_factory) as session:
        repo = GroupRepository(session)
        g2 = repo.create("ФеП-34")
        assert repo.delete(g2.id) is True
        assert repo.get(g2.id) is None


def test_group_deletion_restricted_when_populated(
    session_factory: sessionmaker[Session],
) -> None:
    # заборона видалення групи, до якої прив'язані студенти (fk restrict)
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        s_repo = StudentRepository(session)
        group = g_repo.create("ФеП-33")
        student = Student("Тарас", "Шевченко", "ФеП-33", 95.0)
        s_repo.create(student, group_id=group.id)

    with pytest.raises(IntegrityError), session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        g_repo.delete(group.id)


def test_student_crud_and_validation(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка збереження, читання, оновлення і видалення студента
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        group = g_repo.create("ФеП-33")
        s_repo = StudentRepository(session)

        st = Student("Іван", "Франко", "ФеП-33", 92.5)
        created = s_repo.create(st, group_id=group.id, email="franko@lnu.edu.ua")
        assert created.student_id == 1
        assert created.first_name == "Іван"
        assert created.last_name == "Франко"

    with session_scope(session_factory) as session:
        s_repo = StudentRepository(session)
        loaded = s_repo.get(1)
        assert loaded is not None
        assert loaded.student_id == 1
        assert loaded.last_name == "Франко"
        assert loaded.group == "ФеП-33"

        dto = s_repo.get_dto(1)
        assert dto is not None
        assert isinstance(dto, StudentDTO)
        assert dto.email == "franko@lnu.edu.ua"

        # оновлення студента
        updated = s_repo.update(1, average_grade=98.0, email="new_franko@lnu.edu.ua")
        assert updated is not None
        assert updated.average_grade == 98.0

    with session_scope(session_factory) as session:
        s_repo = StudentRepository(session)
        after_update = s_repo.get_dto(1)
        assert after_update is not None
        assert after_update.average_grade == 98.0
        assert after_update.email == "new_franko@lnu.edu.ua"

        # видалення студента
        deleted = s_repo.delete(1)
        assert deleted is True
        assert s_repo.get(1) is None


def test_student_identifier_rejections(
    session_factory: sessionmaker[Session],
) -> None:
    # відхилення некоректних ідентифікаторів (bool, <= 0)
    with session_scope(session_factory) as session:
        s_repo = StudentRepository(session)
        with pytest.raises(TypeError):
            s_repo.get(cast(int, True))

        with pytest.raises(ValueError):
            s_repo.get(0)

        with pytest.raises(ValueError):
            s_repo.get(-5)


def test_student_check_constraints(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка бд check constraints на рівні таблиці
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        group = g_repo.create("ФеП-33")

    with pytest.raises(IntegrityError), session_scope(session_factory) as session:
        # вставляємо некоректний бал в обхід моделі через raw row
        bad_row = StudentRow(
            first_name="Олег",
            last_name="Коваль",
            average_grade=150.0,
            group_id=group.id,
        )
        session.add(bad_row)


def test_student_queries_and_pagination(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка пошуку за прізвищем, фільтрації та пагінації
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        g1 = g_repo.create("ФеП-33")
        g2 = g_repo.create("ФеП-34")
        s_repo = StudentRepository(session)

        s_repo.create(Student("Ольга", "Коваль", "ФеП-33", 88.0), group_id=g1.id)
        s_repo.create(Student("Микола", "Мельник", "ФеП-33", 94.0), group_id=g1.id)
        s_repo.create(Student("Ірина", "коваль", "ФеП-34", 91.0), group_id=g2.id)

    with session_scope(session_factory) as session:
        s_repo = StudentRepository(session)

        # пошук за прізвищем незалежно від регістру
        kovals = s_repo.search_by_last_name("  КОВАЛЬ  ")
        assert len(kovals) == 2
        assert {s.student_id for s in kovals} == {1, 3}

        # фільтрація за групою
        fep33_students = s_repo.filter_by_group(g1.id)
        assert len(fep33_students) == 2
        assert fep33_students[0].first_name == "Ольга"

        # пагінація
        page1 = s_repo.list(offset=0, limit=2)
        assert len(page1) == 2
        page2 = s_repo.list(offset=2, limit=2)
        assert len(page2) == 1
        assert page2[0].student_id == 3


def test_student_aggregates_and_deterministic_ties(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка агрегацій: середній бал, найкращий студент, tie-breaker
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        g1 = g_repo.create("ФеП-33")
        g_repo.create("ФеП-34")
        s_repo = StudentRepository(session)

        # для порожньої групи агрегати повертають None
        assert s_repo.average(g1.id) is None
        assert s_repo.best(g1.id) is None
        assert s_repo.count(g1.id) == 0

        # додаємо студентів з однаковим найвищим балом для перевірки детермінізму
        s_repo.create(Student("Анна", "Білик", "ФеП-33", 95.0), group_id=g1.id)  # id 1
        s_repo.create(Student("Богдан", "Вовк", "ФеП-33", 95.0), group_id=g1.id)  # id 2
        s_repo.create(Student("Віктор", "Гай", "ФеП-33", 80.0), group_id=g1.id)  # id 3

        avg = s_repo.average(g1.id)
        assert avg is not None
        assert round(avg, 2) == 90.0

        assert s_repo.count(g1.id) == 3

        # детермінований вибір найкращого при однаковому балі (за id asc)
        best_student = s_repo.best(g1.id)
        assert best_student is not None
        assert best_student.student_id == 1
        assert best_student.average_grade == 95.0


def test_two_students_with_same_name_allowed(
    session_factory: sessionmaker[Session],
) -> None:
    # дозволено існування двох різних студентів з однаковим іменем і прізвищем
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        g = g_repo.create("ФеП-33")
        s_repo = StudentRepository(session)

        s1 = s_repo.create(Student("Олег", "Петренко", "ФеП-33", 85.0), group_id=g.id)
        s2 = s_repo.create(Student("Олег", "Петренко", "ФеП-33", 90.0), group_id=g.id)

        assert s1.student_id != s2.student_id
        assert s_repo.count(g.id) == 2


def test_service_rejects_session_and_factory_together(
    session_factory: sessionmaker[Session],
) -> None:
    with (
        session_factory() as session,
        pytest.raises(ValueError, match="session_factory or session"),
    ):
        StudentPersistenceService(session_factory=session_factory, session=session)


def test_service_successful_bulk_transfer(
    session_factory: sessionmaker[Session],
) -> None:
    # успішне масове переведення студентів між групами через сервіс
    service = StudentPersistenceService(session_factory=session_factory)
    g1 = service.create_group("ФеП-33")
    g2 = service.create_group("ФеП-34")

    s1 = service.create_student(Student("Студент1", "Тест", "ФеП-33", 80.0), g1.id)
    s2 = service.create_student(Student("Студент2", "Тест", "ФеП-33", 85.0), g1.id)
    assert s1.student_id is not None
    assert s2.student_id is not None

    count = service.transfer_students([s1.student_id, s2.student_id], g2.id)
    assert count == 2

    # перевіряємо шо студенти тепер у новій групі
    in_g2 = service.filter_students_by_group(g2.id)
    assert len(in_g2) == 2
    assert in_g2[0].group == "ФеП-34"
    assert in_g2[1].group == "ФеП-34"

    in_g1 = service.filter_students_by_group(g1.id)
    assert len(in_g1) == 0


def test_service_bulk_transfer_atomic_rollback_on_failure(
    session_factory: sessionmaker[Session],
) -> None:
    # перевірка атомарного відкату при збої всередині переведення
    service = StudentPersistenceService(session_factory=session_factory)
    g1 = service.create_group("ФеП-33")
    g2 = service.create_group("ФеП-34")

    s1 = service.create_student(Student("Студент1", "Тест", "ФеП-33", 80.0), g1.id)
    assert s1.student_id is not None

    # передаємо валідний s1 і неіснуючий id 9999
    with pytest.raises(ValueError):
        service.transfer_students([s1.student_id, 9999], g2.id)

    # s1 не повинен бути переведений - транзакція відкотилась повністю
    after_failed = service.get_student(s1.student_id)
    assert after_failed is not None
    assert after_failed.group == "ФеП-33"

    # група ФеП-34 залишається порожньою
    assert len(service.filter_students_by_group(g2.id)) == 0


def test_service_bulk_transfer_duplicate_ids_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    # відхилення списку з дублями id перед транзакцією
    service = StudentPersistenceService(session_factory=session_factory)
    g1 = service.create_group("ФеП-33")
    g2 = service.create_group("ФеП-34")
    s1 = service.create_student(Student("Студент1", "Тест", "ФеП-33", 80.0), g1.id)
    assert s1.student_id is not None

    with pytest.raises(ValueError):
        service.transfer_students([s1.student_id, s1.student_id], g2.id)


def test_detached_dto_access_after_session_closed(
    session_factory: sessionmaker[Session],
) -> None:
    # перевіряємо безпечний доступ до полів після закриття сесії
    with session_scope(session_factory) as session:
        g_repo = GroupRepository(session)
        g = g_repo.create("ФеП-33")
        s_repo = StudentRepository(session)
        st = s_repo.create(Student("Леся", "Українка", "ФеП-33", 99.0), group_id=g.id)
        assert st.student_id is not None
        student_id = st.student_id

    # відкриваємо нову сесію, читаємо DTO і Student, закриваємо
    with session_scope(session_factory) as session:
        s_repo = StudentRepository(session)
        detached_student = s_repo.get(student_id)
        detached_dto = s_repo.get_dto(student_id)

    # поза межами сесії доступ до атрибутів працює без помилок detached
    assert detached_student is not None
    assert detached_student.first_name == "Леся"
    assert detached_student.group == "ФеП-33"

    assert detached_dto is not None
    assert detached_dto.first_name == "Леся"
    assert detached_dto.group_name == "ФеП-33"
    assert detached_dto.to_student().full_name == "Леся Українка"
