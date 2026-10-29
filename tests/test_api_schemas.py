from typing import Any

import pytest
from pydantic import ValidationError

from student_manager.api_schemas import (
    GroupCreate,
    GroupResponse,
    GroupStatistics,
    HealthResponse,
    StudentCreate,
    StudentPatch,
    StudentResponse,
)
from student_manager.persistence.models import (
    GroupDTO,
    GroupRow,
    StudentDTO,
    StudentRow,
)


def student_source(kind: str, **overrides: Any) -> StudentDTO | StudentRow:
    fields: dict[str, Any] = {
        "id": 7,
        "first_name": "Іван",
        "last_name": "Франко",
        "group_id": 1,
        "average_grade": 88.5,
        "email": "ivan@lnu.edu.ua",
    }
    fields.update(overrides)
    if kind == "dto":
        return StudentDTO(group_name="ФеП-33", **fields)
    return StudentRow(group=GroupRow(id=1, name="ФеП-33"), **fields)


@pytest.mark.parametrize("kind", ["dto", "row"])
def test_student_response_conversion(kind):
    response = StudentResponse.from_dto_or_row(student_source(kind))
    assert response.model_dump() == {
        "student_id": 7,
        "first_name": "Іван",
        "last_name": "Франко",
        "group_id": 1,
        "group": "ФеП-33",
        "average_grade": 88.5,
        "email": "ivan@lnu.edu.ua",
    }


@pytest.mark.parametrize("kind", ["dto", "row"])
@pytest.mark.parametrize("grade", [True, False, float("nan"), float("inf"), -1, 101])
def test_conversion_rejects_invalid_grades(kind, grade):
    with pytest.raises(ValidationError):
        StudentResponse.from_dto_or_row(student_source(kind, average_grade=grade))


def test_response_text_validation():
    group = GroupResponse(id=1, name="  ФеП-33  ")
    assert group.name == "ФеП-33"
    payload = StudentResponse.from_dto_or_row(student_source("dto")).model_dump()
    payload.update(first_name="  Іван  ", last_name="  Франко  ", group="  ФеП-33  ")
    response = StudentResponse.model_validate(payload)
    assert (response.first_name, response.last_name, response.group) == (
        "Іван",
        "Франко",
        "ФеП-33",
    )
    for field in ("first_name", "last_name", "group"):
        with pytest.raises(ValidationError):
            StudentResponse.model_validate({**payload, field: "   "})
    with pytest.raises(ValidationError):
        GroupResponse(id=1, name="   ")


def test_health_status_contract():
    assert HealthResponse(status="ok", environment="development").status == "ok"
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(
            {"status": "broken", "environment": "development"}
        )


def test_group_response_conversion():
    assert GroupResponse.model_validate(GroupDTO(id=1, name="ФеП-33")) == (
        GroupResponse.model_validate(GroupRow(id=1, name="ФеП-33"))
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1", None])
@pytest.mark.parametrize("field", ["group_id", "student_id"])
def test_create_rejects_invalid_ids(field, value):
    if field == "student_id" and value is None:
        assert (
            StudentCreate(
                first_name="Іван",
                last_name="Франко",
                group_id=1,
                average_grade=88,
                student_id=None,
            ).student_id
            is None
        )
        return
    payload = {
        "first_name": "Іван",
        "last_name": "Франко",
        "group_id": 1,
        "average_grade": 88,
    }
    with pytest.raises(ValidationError):
        StudentCreate.model_validate({**payload, field: value})


@pytest.mark.parametrize(
    "field", ["first_name", "last_name", "group_id", "average_grade"]
)
def test_patch_rejects_explicit_null(field):
    with pytest.raises(ValidationError, match="cannot be explicitly null"):
        StudentPatch.model_validate({field: None})


@pytest.mark.parametrize("grade", [0, 100, 88.5])
def test_valid_grade_boundaries(grade):
    create = StudentCreate(
        first_name="  Іван ",
        last_name=" Франко ",
        group_id=1,
        average_grade=grade,
        email=" ivan@lnu.edu.ua ",
    )
    assert create.first_name == "Іван"
    assert create.last_name == "Франко"
    assert create.email == "ivan@lnu.edu.ua"
    assert create.average_grade == grade
    patch = StudentPatch(average_grade=grade)
    assert patch.model_dump(exclude_unset=True) == {"average_grade": grade}
    assert StudentPatch(email=None).model_dump(exclude_unset=True) == {"email": None}


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "  "},
        {"last_name": "  "},
        {"group_id": True},
        {"group_id": 0},
        {"unknown": "value"},
        {"email": "invalid"},
    ],
)
def test_patch_rejects_invalid_fields(payload):
    with pytest.raises(ValidationError):
        StudentPatch.model_validate(payload)


def test_group_create_validation():
    g = GroupCreate(name="  ФеП-33  ")
    assert g.name == "ФеП-33"

    with pytest.raises(ValidationError):
        GroupCreate(name="   ")

    with pytest.raises(ValidationError):
        GroupCreate(name="ФеП-33", extra_field="forbidden")


def test_student_create_validation():
    s = StudentCreate(
        first_name="Остап",
        last_name="Бендер",
        group_id=1,
        average_grade=85.5,
        email="ostap@lnu.edu.ua",
    )
    assert s.first_name == "Остап"
    assert s.email == "ostap@lnu.edu.ua"

    with pytest.raises(ValidationError):
        StudentCreate(
            first_name="Остап",
            last_name="Бендер",
            group_id=True,
            average_grade=85.5,
        )

    with pytest.raises(ValidationError):
        StudentCreate(
            first_name="Остап",
            last_name="Бендер",
            group_id=1,
            average_grade=-1.0,
        )

    with pytest.raises(ValidationError):
        StudentCreate(
            first_name="Остап",
            last_name="Бендер",
            group_id=1,
            average_grade=85.0,
            email="invalid_email_string",
        )


def test_student_patch_validation():
    p = StudentPatch(first_name="Тарас")
    assert p.first_name == "Тарас"
    assert "first_name" in p.model_fields_set
    assert "last_name" not in p.model_fields_set

    p_email = StudentPatch(email=None)
    assert p_email.email is None
    assert "email" in p_email.model_fields_set

    with pytest.raises(ValidationError, match="Patch payload cannot be empty"):
        StudentPatch()

    with pytest.raises(ValidationError, match="cannot be explicitly null"):
        StudentPatch(first_name=None)


def test_group_statistics_validation():
    student = StudentResponse(
        student_id=7,
        first_name="Іван",
        last_name="Франко",
        group_id=1,
        group="ФеП-33",
        average_grade=88.5,
        email=None,
    )
    stats = GroupStatistics(
        group_id=1,
        count=5,
        average=88.5,
        best_student=student,
    )
    assert stats.count == 5
    assert stats.average == 88.5
    assert stats.best_student == student
    assert stats.model_dump()["best_student"] == student.model_dump()
    assert GroupStatistics.model_validate_json(stats.model_dump_json()) == stats
    with pytest.raises(ValidationError):
        GroupStatistics(group_id=1, count=5, average=88.5, best_student="Іван Франко")

    empty_stats = GroupStatistics(
        group_id=2,
        count=0,
        average=None,
        best_student=None,
    )
    assert empty_stats.average is None
    assert empty_stats.best_student is None


@pytest.mark.parametrize(
    "grade", [True, False, float("nan"), float("inf"), -float("inf"), -1, 101]
)
@pytest.mark.parametrize(
    "schema", [StudentCreate, StudentPatch, StudentResponse, GroupStatistics]
)
def test_schemas_reject_invalid_grades(schema, grade):
    if schema is GroupStatistics:
        payload = {"group_id": 1, "count": 1, "average": grade}
    elif schema is StudentPatch:
        payload = {"average_grade": grade}
    else:
        payload = {
            "first_name": "Іван",
            "last_name": "Франко",
            "group_id": 1,
            "average_grade": grade,
        }
        if schema is StudentResponse:
            payload.update(student_id=7, group="ФеП-33")
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_schemas_reject_integer_overflow() -> None:
    from student_manager.api_schemas import SQLITE_MAX_INT

    # перевіряєм шо граничне значення проходить а переповнення відхиляється
    assert GroupResponse(id=SQLITE_MAX_INT, name="ФеП-33").id == SQLITE_MAX_INT
    assert (
        StudentCreate(
            first_name="Іван",
            last_name="Франко",
            group_id=SQLITE_MAX_INT,
            student_id=SQLITE_MAX_INT,
            average_grade=90.0,
        ).group_id
        == SQLITE_MAX_INT
    )
    assert StudentPatch(group_id=SQLITE_MAX_INT).group_id == SQLITE_MAX_INT
    assert (
        StudentResponse(
            student_id=SQLITE_MAX_INT,
            first_name="Іван",
            last_name="Франко",
            group_id=SQLITE_MAX_INT,
            group="ФеП-33",
            average_grade=90.0,
        ).student_id
        == SQLITE_MAX_INT
    )
    assert (
        GroupStatistics(
            group_id=SQLITE_MAX_INT,
            count=SQLITE_MAX_INT,
            average=90.0,
        ).count
        == SQLITE_MAX_INT
    )

    overflow = SQLITE_MAX_INT + 1
    with pytest.raises(ValidationError):
        GroupResponse(id=overflow, name="ФеП-33")
    with pytest.raises(ValidationError):
        StudentCreate(
            first_name="Іван",
            last_name="Франко",
            group_id=overflow,
            average_grade=90.0,
        )
    with pytest.raises(ValidationError):
        StudentCreate(
            first_name="Іван",
            last_name="Франко",
            group_id=1,
            student_id=overflow,
            average_grade=90.0,
        )
    with pytest.raises(ValidationError):
        StudentPatch(group_id=overflow)
    with pytest.raises(ValidationError):
        StudentResponse(
            student_id=overflow,
            first_name="Іван",
            last_name="Франко",
            group_id=1,
            group="ФеП-33",
            average_grade=90.0,
        )
    with pytest.raises(ValidationError):
        StudentResponse(
            student_id=1,
            first_name="Іван",
            last_name="Франко",
            group_id=overflow,
            group="ФеП-33",
            average_grade=90.0,
        )
    with pytest.raises(ValidationError):
        GroupStatistics(group_id=overflow, count=1)
    with pytest.raises(ValidationError):
        GroupStatistics(group_id=1, count=overflow)
