from __future__ import annotations

import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from student_manager.persistence.models import StudentDTO, StudentRow

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SQLITE_MAX_INT: int = 9_223_372_036_854_775_807


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Annotated[str, Field(min_length=1, max_length=100)]


class GroupResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, str_strip_whitespace=True
    )
    id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INT)]
    name: Annotated[str, Field(min_length=1, max_length=100)]


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    group_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INT)]
    average_grade: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)
    ]
    student_id: Annotated[
        int | None, Field(default=None, strict=True, gt=0, le=SQLITE_MAX_INT)
    ] = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError(f"Invalid email format: '{cleaned}'")
        return cleaned


class StudentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    first_name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=100)
    ] = None
    last_name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=100)
    ] = None
    group_id: Annotated[
        int | None, Field(default=None, strict=True, gt=0, le=SQLITE_MAX_INT)
    ] = None
    average_grade: Annotated[
        float | None,
        Field(default=None, strict=True, allow_inf_nan=False, ge=0.0, le=100.0),
    ] = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError(f"Invalid email format: '{cleaned}'")
        return cleaned

    @model_validator(mode="after")
    def validate_patch_non_empty(self) -> Self:
        fields_set = self.model_fields_set
        if not fields_set:
            raise ValueError("Patch payload cannot be empty")
        for field_name in ("first_name", "last_name", "group_id", "average_grade"):
            if field_name in fields_set and getattr(self, field_name) is None:
                raise ValueError(f"Field '{field_name}' cannot be explicitly null")
        return self


class StudentResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, str_strip_whitespace=True
    )
    student_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INT)]
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    group_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INT)]
    group: Annotated[str, Field(min_length=1, max_length=100)]
    average_grade: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)
    ]
    email: str | None = None

    @classmethod
    def from_dto_or_row(cls, obj: StudentDTO | StudentRow) -> StudentResponse:
        return cls(
            student_id=obj.id,
            first_name=obj.first_name,
            last_name=obj.last_name,
            group_id=obj.group_id,
            group=obj.group_name if isinstance(obj, StudentDTO) else obj.group.name,
            average_grade=obj.average_grade,
            email=obj.email,
        )


class GroupStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: Annotated[int, Field(strict=True, gt=0, le=SQLITE_MAX_INT)]
    count: Annotated[int, Field(strict=True, ge=0, le=SQLITE_MAX_INT)]
    average: Annotated[
        float | None, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)
    ] = None
    best_student: StudentResponse | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    environment: str
