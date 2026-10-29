from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from student_manager.api_schemas import (
    SQLITE_MAX_INT,
    GroupCreate,
    GroupResponse,
    GroupStatistics,
    HealthResponse,
    StudentCreate,
    StudentPatch,
    StudentResponse,
)
from student_manager.models import Student
from student_manager.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from student_manager.persistence.service import StudentPersistenceService


def get_session(request: Request) -> Generator[Session, None, None]:
    """Mutations commit before responding; reads and failed requests roll back."""
    lock = getattr(request.app.state, "db_lock", None)
    if lock is not None:
        lock.acquire()
    session = request.app.state.session_factory()
    try:
        session.begin()
        if (
            request.method in {"POST", "PATCH", "PUT", "DELETE"}
            and request.app.state.engine.dialect.name == "sqlite"
        ):
            session.connection(execution_options={"sqlite_immediate": True})
        yield session
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            session.commit()
        else:
            session.rollback()
    except BaseException:
        session.rollback()
        raise
    finally:
        try:
            session.close()
        finally:
            if lock is not None:
                lock.release()


SESSION_DEPENDENCY = Depends(get_session, scope="function")


def _student(service: StudentPersistenceService, student_id: int) -> StudentResponse:
    dto = service.get_student_dto(student_id)
    if dto is None:
        raise HTTPException(404, "Student not found")
    return StudentResponse.from_dto_or_row(dto)


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        url = (
            database_url
            if database_url is not None
            else os.environ.get("DATABASE_URL", "sqlite:///students.sqlite")
        )
        parsed = make_url(url)
        options: dict[str, Any] = {}
        if parsed.get_backend_name() == "sqlite":
            options["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
            if parsed.database in (None, "", ":memory:"):
                options["poolclass"] = StaticPool
        engine = create_database_engine(url, **options)
        application.state.engine = engine
        application.state.db_lock = (
            threading.Lock() if isinstance(engine.pool, StaticPool) else None
        )
        try:
            if engine.dialect.name == "sqlite":
                # без явного begin sqlite може закомітити savepoint раніше за запит
                # стартуєм як immediate шоб не ловити upgrade deadlock

                @event.listens_for(engine, "connect")
                def explicit_transactions(connection: Any, record: Any) -> None:
                    connection.isolation_level = None
                    cursor = connection.cursor()
                    cursor.execute("PRAGMA busy_timeout = 30000")
                    if parsed.database not in (None, "", ":memory:"):
                        cursor.execute("PRAGMA journal_mode = WAL")
                    cursor.close()

                @event.listens_for(engine, "begin")
                def begin(connection: Any) -> None:
                    if connection.get_execution_options().get(
                        "sqlite_immediate", False
                    ):
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                    else:
                        connection.exec_driver_sql("BEGIN")

            config = Config()
            config.set_main_option(
                "script_location", "student_manager.persistence:migrations"
            )
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            application.state.session_factory = create_session_factory(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="Student Manager API", version="0.8.0", lifespan=lifespan
    )

    @application.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "Resource conflict"})

    @application.exception_handler(ValueError)
    async def invalid_value(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": "Invalid resource data"}
        )

    @application.exception_handler(OverflowError)
    async def integer_overflow(request: Request, exc: OverflowError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Integer overflow"})

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    @application.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        engine = getattr(request.app.state, "engine", None)
        if engine is not None:
            lock = getattr(request.app.state, "db_lock", None)
            try:
                if lock is not None:
                    with lock, engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
                else:
                    with engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
            except SQLAlchemyError:
                raise HTTPException(503, "Database unavailable") from None
        return HealthResponse(
            status="ok", environment=os.getenv("ENVIRONMENT", "development")
        )

    @application.post("/groups", response_model=GroupResponse, status_code=201)
    def create_group(
        data: GroupCreate, session: Session = SESSION_DEPENDENCY
    ) -> GroupResponse:
        return GroupResponse.model_validate(
            StudentPersistenceService(session=session).create_group(data.name)
        )

    @application.get("/groups", response_model=list[GroupResponse])
    def list_groups(session: Session = SESSION_DEPENDENCY) -> list[GroupResponse]:
        return [
            GroupResponse.model_validate(group)
            for group in StudentPersistenceService(session=session).list_groups()
        ]

    @application.post("/students", response_model=StudentResponse, status_code=201)
    def create_student(
        data: StudentCreate, session: Session = SESSION_DEPENDENCY
    ) -> StudentResponse:
        service = StudentPersistenceService(session=session)
        group = service.get_group(data.group_id)
        if group is None:
            raise HTTPException(404, "Group not found")
        student = Student(
            data.first_name,
            data.last_name,
            group.name,
            data.average_grade,
            data.student_id,
        )
        created = service.create_student(
            student, group_id=data.group_id, email=data.email
        )
        assert created.student_id is not None
        return _student(service, created.student_id)

    @application.get("/students/{student_id}", response_model=StudentResponse)
    def get_student(
        student_id: int = Path(gt=0, le=SQLITE_MAX_INT),
        session: Session = SESSION_DEPENDENCY,
    ) -> StudentResponse:
        return _student(StudentPersistenceService(session=session), student_id)

    @application.get("/students", response_model=list[StudentResponse])
    def list_students(
        group_id: int | None = Query(default=None, gt=0, le=SQLITE_MAX_INT),
        last_name: str | None = Query(default=None, min_length=1),
        offset: int = Query(default=0, ge=0, le=SQLITE_MAX_INT),
        limit: int = Query(default=100, gt=0, le=1000),
        session: Session = SESSION_DEPENDENCY,
    ) -> list[StudentResponse]:
        service = StudentPersistenceService(session=session)
        if last_name is not None:
            students = service.search_students_by_last_name(last_name)
            if group_id is not None:
                ids = {
                    student.student_id
                    for student in service.filter_students_by_group(group_id)
                }
                students = [
                    student for student in students if student.student_id in ids
                ]
            students = students[offset : offset + limit]
        elif group_id is not None:
            students = service.filter_students_by_group(group_id)[
                offset : offset + limit
            ]
        else:
            students = service.list_students(offset=offset, limit=limit)
        return [
            _student(service, student.student_id)
            for student in students
            if student.student_id is not None
        ]

    @application.get(
        "/groups/{group_id}/students", response_model=list[StudentResponse]
    )
    def group_students(
        group_id: int = Path(gt=0, le=SQLITE_MAX_INT),
        offset: int = Query(default=0, ge=0, le=SQLITE_MAX_INT),
        limit: int = Query(default=100, gt=0, le=1000),
        session: Session = SESSION_DEPENDENCY,
    ) -> list[StudentResponse]:
        if StudentPersistenceService(session=session).get_group(group_id) is None:
            raise HTTPException(404, "Group not found")
        return list_students(group_id, None, offset, limit, session)

    @application.get("/groups/{group_id}/statistics", response_model=GroupStatistics)
    def group_statistics(
        group_id: int = Path(gt=0, le=SQLITE_MAX_INT),
        session: Session = SESSION_DEPENDENCY,
    ) -> GroupStatistics:
        service = StudentPersistenceService(session=session)
        if service.get_group(group_id) is None:
            raise HTTPException(404, "Group not found")
        best = service.get_best_student(group_id)
        return GroupStatistics(
            group_id=group_id,
            count=service.count_students(group_id),
            average=service.get_group_average(group_id),
            best_student=_student(service, best.student_id)
            if best is not None and best.student_id is not None
            else None,
        )

    @application.patch("/students/{student_id}", response_model=StudentResponse)
    def patch_student(
        data: StudentPatch,
        student_id: int = Path(gt=0, le=SQLITE_MAX_INT),
        session: Session = SESSION_DEPENDENCY,
    ) -> StudentResponse:
        service = StudentPersistenceService(session=session)
        _student(service, student_id)
        if data.group_id is not None and service.get_group(data.group_id) is None:
            raise HTTPException(404, "Group not found")
        # у lab7 порожній рядок чистить email, а none лишає попередній
        email = data.email
        if "email" in data.model_fields_set and email is None:
            email = ""
        service.update_student(
            student_id,
            first_name=data.first_name,
            last_name=data.last_name,
            group_id=data.group_id,
            average_grade=data.average_grade,
            email=email,
        )
        return _student(service, student_id)

    @application.delete("/students/{student_id}", status_code=204)
    def delete_student(
        student_id: int = Path(gt=0, le=SQLITE_MAX_INT),
        session: Session = SESSION_DEPENDENCY,
    ) -> Response:
        if not StudentPersistenceService(session=session).delete_student(student_id):
            raise HTTPException(404, "Student not found")
        return Response(status_code=204)

    return application


app = create_app()
