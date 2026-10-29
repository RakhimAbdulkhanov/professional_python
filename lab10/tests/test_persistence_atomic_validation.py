import pytest
from sqlalchemy.orm import Session

from student_manager.models import Student
from student_manager.persistence import (
    Base,
    GroupRepository,
    StudentRepository,
    create_database_engine,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"first_name": "Марія", "average_grade": 150.0},
        {"first_name": "Марія", "last_name": " "},
        {"first_name": "Марія", "group_id": 999},
        {"first_name": "Марія", "email": 123},
    ],
)
def test_invalid_repository_update_does_not_leave_partial_mutation(tmp_path, changes):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'atomic.sqlite'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            group = GroupRepository(session).create("ФеП-33")
            student = StudentRepository(session).create(
                Student("Олена", "Коваль", group.name, 90.0), group.id
            )
            session.commit()
            assert student.student_id is not None
            repository = StudentRepository(session)
            with pytest.raises((ValueError, TypeError)):
                repository.update(student.student_id, **changes)
            session.commit()
            actual = repository.get(student.student_id)
            assert actual is not None
            assert actual.first_name == "Олена"
            assert actual.average_grade == 90.0
    finally:
        engine.dispose()
