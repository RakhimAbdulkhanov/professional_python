"""Unit tests for repository layer."""

from __future__ import annotations

import pytest

from student_manager.models import Student
from student_manager.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from student_manager.persistence.models import Base
from student_manager.persistence.repositories import GroupRepository, StudentRepository
from student_manager.repositories import InMemoryRepository


def test_in_memory_repository() -> None:
    repo: InMemoryRepository[str] = InMemoryRepository()
    assert len(repo) == 0
    repo.add(1, "item1")
    assert repo.get(1) == "item1"
    assert 1 in repo
    assert repo.all() == ("item1",)
    repo.update(1, "item1_updated")
    assert repo.get(1) == "item1_updated"

    with pytest.raises(ValueError):
        repo.add(1, "duplicate")
    with pytest.raises(KeyError):
        repo.update(999, "missing")


def test_sqlalchemy_repositories() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        groups = GroupRepository(session)
        students = StudentRepository(session)

        g = groups.create(name="ФеП-33")
        assert g.id is not None
        assert g.name == "ФеП-33"

        s_domain = Student(
            first_name="Рахім",
            last_name="Абдулханов",
            group="ФеП-33",
            average_grade=95.5,
        )
        s = students.create(
            student=s_domain,
            group_id=g.id,
        )
        assert s.first_name == "Рахім"
        assert s.last_name == "Абдулханов"
        assert s.group == "ФеП-33"
        assert s.average_grade == 95.5

        loaded_s = students.get(1)
        assert loaded_s is not None
        assert loaded_s.first_name == "Рахім"
        session.commit()
