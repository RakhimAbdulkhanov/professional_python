from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


def test_create_student_commits_and_preserves_domain(tmp_path: Path) -> None:
    from student_manager.api import create_app
    from student_manager.models import Student
    from student_manager.persistence.service import StudentPersistenceService

    app = create_app(f"sqlite:///{(tmp_path / 'crud.sqlite').as_posix()}")
    with TestClient(app) as client:
        group = client.post("/groups", json={"name": " ФеП-33 "})
        assert group.status_code == 201
        assert client.get("/groups").json() == [{"id": 1, "name": "ФеП-33"}]
        payload = {
            "student_id": 7,
            "first_name": " Анна ",
            "last_name": "Коваль",
            "group_id": 1,
            "average_grade": 91.5,
            "email": "anna@example.org",
        }
        response = client.post("/students", json=payload)
        assert response.status_code == 201
        assert response.json() == {**payload, "first_name": "Анна", "group": "ФеП-33"}
        assert client.get("/students/7").json() == response.json()
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM students")) == 1
        service = StudentPersistenceService(session_factory=app.state.session_factory)
        assert service.get_student(7) == Student("Анна", "Коваль", "ФеП-33", 91.5, 7)


def test_filter_search_pagination_and_statistics() -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        for name in ("ФеП-33", "ФеП-34", "empty"):
            assert client.post("/groups", json={"name": name}).status_code == 201
        for sid, gid, surname, grade in (
            (8, 1, "Коваль", 80),
            (3, 1, "Коваль", 90),
            (6, 1, "Інший", 90),
            (2, 2, "Коваль", 95),
        ):
            assert (
                client.post(
                    "/students",
                    json={
                        "student_id": sid,
                        "first_name": "Анна",
                        "last_name": surname,
                        "group_id": gid,
                        "average_grade": grade,
                    },
                ).status_code
                == 201
            )
        assert [row["student_id"] for row in client.get("/students").json()] == [
            2,
            3,
            6,
            8,
        ]
        assert [
            row["student_id"]
            for row in client.get(
                "/students?group_id=1&last_name=%20коваль%20&offset=1&limit=1"
            ).json()
        ] == [8]
        assert [
            row["student_id"]
            for row in client.get("/groups/1/students?offset=1&limit=1").json()
        ] == [6]
        stats = client.get("/groups/1/statistics").json()
        assert stats["count"] == 3
        assert stats["average"] == 260 / 3
        assert stats["best_student"] == client.get("/students/3").json()
        assert client.get("/groups/3/statistics").json() == {
            "group_id": 3,
            "count": 0,
            "average": None,
            "best_student": None,
        }


def test_patch_transfer_email_null_and_delete() -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        for name in ("old", "new"):
            client.post("/groups", json={"name": name})
        original = client.post(
            "/students",
            json={
                "first_name": "Ann",
                "last_name": "Koval",
                "group_id": 1,
                "average_grade": 80,
                "email": "ann@example.org",
            },
        ).json()
        response = client.patch(
            "/students/1", json={"group_id": 2, "average_grade": 95}
        )
        assert response.status_code == 200
        assert response.json() == {
            **original,
            "group_id": 2,
            "group": "new",
            "average_grade": 95,
        }
        assert client.patch("/students/1", json={"email": None}).json()["email"] is None
        assert client.get("/students/1").json()["email"] is None
        assert client.get("/groups/1/statistics").json()["count"] == 0
        assert client.delete("/students/1").status_code == 204
        assert client.get("/students/1").status_code == 404
        assert client.delete("/students/1").status_code == 404
        assert client.get("/groups/2/statistics").json()["best_student"] is None


def test_conflicts_are_safe_and_roll_back(tmp_path: Path) -> None:
    from student_manager.api import create_app

    app = create_app(f"sqlite:///{(tmp_path / 'conflict.sqlite').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/groups", json={"name": "one"}).status_code == 201
        response = client.post("/groups", json={"name": "one"})
        assert response.status_code == 409
        assert response.json() == {"detail": "Resource conflict"}
        payload = {
            "student_id": 4,
            "first_name": "Ann",
            "last_name": "Koval",
            "group_id": 1,
            "average_grade": 80,
        }
        assert client.post("/students", json=payload).status_code == 201
        assert client.post("/students", json=payload).status_code == 409
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM students")) == 1
        assert client.post("/groups", json={"name": "two"}).status_code == 201


def test_request_outer_transaction_controls_service_writes(tmp_path: Path) -> None:
    from student_manager.api import create_app, get_session
    from student_manager.persistence.service import StudentPersistenceService

    app = create_app(f"sqlite:///{(tmp_path / 'atomic.sqlite').as_posix()}")

    dependency = Depends(get_session, scope="function")

    @app.post("/probe")
    def probe(session: Session = dependency) -> None:
        StudentPersistenceService(session=session).create_group("must rollback")
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM groups")) == 0
        raise RuntimeError("private credentials")

    @app.get("/read-probe")
    def read_probe(session: Session = dependency) -> dict[str, str]:
        StudentPersistenceService(session=session).create_group("read must rollback")
        return {"status": "ok"}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/probe")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert client.get("/read-probe").status_code == 200
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM groups")) == 0


@pytest.mark.parametrize(
    "path", ["/students/999", "/groups/999/students", "/groups/999/statistics"]
)
def test_missing_get_resources(path: str) -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        assert client.get(path).status_code == 404
        assert (
            client.patch("/students/999", json={"average_grade": 90}).status_code == 404
        )
        assert (
            client.post(
                "/students",
                json={
                    "first_name": "Ann",
                    "last_name": "Koval",
                    "group_id": 999,
                    "average_grade": 80,
                },
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "path",
    [
        "/students/0",
        "/students/-1",
        "/students/no",
        "/groups/0/students",
        "/groups/no/statistics",
        "/students?offset=-1",
        "/students?limit=0",
        "/students?limit=1001",
        "/students?group_id=0",
        "/students?last_name=",
        "/students?last_name=%20%20",
        "/groups/1/students?offset=-1",
    ],
)
def test_invalid_paths_and_queries(path: str) -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "updates",
    [
        {"first_name": " "},
        {"last_name": ""},
        {"group_id": True},
        {"group_id": "1"},
        {"average_grade": True},
        {"average_grade": 101},
        {"average_grade": -1},
        {"average_grade": "NaN"},
        {"average_grade": "Infinity"},
        {"email": "bad"},
        {"unknown": 4},
    ],
)
def test_invalid_student_creation(updates: dict[str, object]) -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        payload = {
            "first_name": "Ann",
            "last_name": "Koval",
            "group_id": 1,
            "average_grade": 80,
        }
        assert client.post("/students", json={**payload, **updates}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"first_name": None},
        {"last_name": None},
        {"average_grade": None},
        {"group_id": None},
        {"average_grade": True},
        {"extra": 1},
    ],
)
def test_invalid_patch(payload: dict[str, object]) -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        assert client.patch("/students/1", json=payload).status_code == 422


def test_missing_transfer_does_not_partially_update() -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        client.post("/groups", json={"name": "one"})
        original = client.post(
            "/students",
            json={
                "first_name": "Ann",
                "last_name": "Koval",
                "group_id": 1,
                "average_grade": 80,
            },
        ).json()
        assert (
            client.patch(
                "/students/1", json={"first_name": "changed", "group_id": 999}
            ).status_code
            == 404
        )
        assert client.get("/students/1").json() == original
        response = client.delete("/students/1")
        assert response.status_code == 204
        assert response.content == b""


def test_openapi_and_documentation() -> None:
    from student_manager.api import create_app

    with TestClient(create_app("sqlite://")) as client:
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "Student Manager API"
        expected = {
            "/health": {"get"},
            "/groups": {"get", "post"},
            "/students": {"get", "post"},
            "/students/{student_id}": {"get", "patch", "delete"},
            "/groups/{group_id}/students": {"get"},
            "/groups/{group_id}/statistics": {"get"},
        }
        for path, methods in expected.items():
            assert methods <= schema["paths"][path].keys()
        assert "StudentResponse" in schema["components"]["schemas"]
        assert "204" in schema["paths"]["/students/{student_id}"]["delete"]["responses"]
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200


def test_factory_environment_precedence_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from student_manager.api import create_app

    requested = tmp_path / "requested.sqlite"
    unrelated = tmp_path / "unrelated.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{unrelated.as_posix()}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    for iteration in range(2):
        app = create_app(f"sqlite:///{requested.as_posix()}")
        with TestClient(app) as client:
            assert client.get("/health").json()["environment"] == "test"
            if iteration == 0:
                assert (
                    client.post("/groups", json={"name": "persistent"}).status_code
                    == 201
                )
            else:
                assert client.get("/groups").json() == [{"id": 1, "name": "persistent"}]
    assert not unrelated.exists()
    with TestClient(create_app()) as client:
        assert client.get("/groups").json() == []
    assert unrelated.exists()


def test_health_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.exc import OperationalError

    from student_manager.api import create_app

    app = create_app("sqlite://")
    with TestClient(app) as client:

        def unavailable() -> None:
            raise OperationalError(
                "secret database path", {}, RuntimeError("credentials")
            )

        monkeypatch.setattr(app.state.engine, "connect", unavailable)
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}


def test_commit_failure_rolls_back_before_response(tmp_path: Path) -> None:
    from sqlalchemy.exc import IntegrityError

    from student_manager.api import create_app

    app = create_app(f"sqlite:///{(tmp_path / 'commit.sqlite').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as client:

        def reject_commit(session: Session) -> None:
            raise IntegrityError("private SQL", {}, RuntimeError("constraint"))

        event.listen(app.state.session_factory, "before_commit", reject_commit)
        try:
            response = client.post("/groups", json={"name": "never committed"})
            assert response.status_code == 409
            assert response.json() == {"detail": "Resource conflict"}
        finally:
            event.remove(app.state.session_factory, "before_commit", reject_commit)
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM groups")) == 0
        assert client.post("/groups", json={"name": "works"}).status_code == 201


def test_startup_failure_disposes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from alembic import command
    from sqlalchemy import Engine

    from student_manager import api
    from student_manager.persistence.database import create_database_engine

    engine = create_database_engine(
        f"sqlite:///{(tmp_path / 'broken.sqlite').as_posix()}"
    )
    pool = engine.pool

    def provided_engine(url: str, **options: object) -> Engine:
        return engine

    def fail_upgrade(*args: object, **kwargs: object) -> None:
        raise RuntimeError("migration failed")

    monkeypatch.setattr(api, "create_database_engine", provided_engine)
    monkeypatch.setattr(command, "upgrade", fail_upgrade)
    with (
        pytest.raises(RuntimeError, match="migration failed"),
        TestClient(api.create_app("sqlite://")),
    ):
        pass
    assert engine.pool is not pool


def test_multiple_service_writes_commit_only_at_request_boundary(
    tmp_path: Path,
) -> None:
    from student_manager.api import create_app, get_session
    from student_manager.persistence.service import StudentPersistenceService

    app = create_app(f"sqlite:///{(tmp_path / 'outer.sqlite').as_posix()}")
    dependency = Depends(get_session, scope="function")

    @app.post("/atomic-success")
    def write_two(session: Session = dependency) -> dict[str, int]:
        service = StudentPersistenceService(session=session)
        service.create_group("first")
        service.create_group("second")
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM groups")) == 0
        return {"count": 2}

    with TestClient(app) as client:
        assert client.post("/atomic-success").json() == {"count": 2}
        with app.state.engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM groups")) == 2


def test_factory_migrates_health_and_disposes(tmp_path: Path) -> None:
    assert importlib.util.find_spec("student_manager.api") is not None
    from student_manager.api import create_app

    path = tmp_path / "api.sqlite"
    app = create_app(f"sqlite:///{path.as_posix()}")
    assert not path.exists()
    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "environment": os.getenv("ENVIRONMENT", "development"),
        }
        assert {"students", "groups", "alembic_version"} <= set(
            inspect(app.state.engine).get_table_names()
        )
        pool = app.state.engine.pool
    assert app.state.engine.pool is not pool


def test_file_sqlite_concurrent_writes_and_upgrades(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from student_manager.api import create_app

    # тестуєм конкурентні оновлення у файловому sqlite
    db_file = tmp_path / "concurrent_file.sqlite"
    app = create_app(f"sqlite:///{db_file.as_posix()}")
    with TestClient(app) as client:
        group_resp = client.post("/groups", json={"name": "ФеП-33"})
        assert group_resp.status_code == 201

        def create_student_task(idx: int) -> int:
            resp = client.post(
                "/students",
                json={
                    "student_id": 100 + idx,
                    "first_name": f"Студент{idx}",
                    "last_name": "Тест",
                    "group_id": 1,
                    "average_grade": 85.0,
                },
            )
            return int(resp.status_code)

        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(create_student_task, range(12)))

        assert all(status == 201 for status in statuses)
        assert len(client.get("/students").json()) == 12


def test_memory_sqlite_static_pool_concurrent_requests() -> None:
    from concurrent.futures import ThreadPoolExecutor

    from student_manager.api import create_app

    # тестуєм паралельні запити в пам'яті зі static pool
    app = create_app("sqlite://")
    with TestClient(app) as client:
        group_resp = client.post("/groups", json={"name": "ФеП-33"})
        assert group_resp.status_code == 201

        def create_student_task(idx: int) -> int:
            resp = client.post(
                "/students",
                json={
                    "student_id": 200 + idx,
                    "first_name": f"Студент{idx}",
                    "last_name": "Тест",
                    "group_id": 1,
                    "average_grade": 90.0,
                },
            )
            return int(resp.status_code)

        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(create_student_task, range(12)))

        assert all(status == 201 for status in statuses)
        assert len(client.get("/students").json()) == 12


def test_extremely_large_integer_ids_return_422() -> None:
    from student_manager.api import create_app

    # великі числа мають валідуватись як 422 без падіння sqlite
    app = create_app("sqlite://")
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post("/groups", json={"name": "ФеП-33"})
        client.post(
            "/students",
            json={
                "student_id": 1,
                "first_name": "Анна",
                "last_name": "Коваль",
                "group_id": 1,
                "average_grade": 95.0,
            },
        )
        overflow_id = 10**25

        assert client.get(f"/students/{overflow_id}").status_code == 422
        assert client.get(f"/groups/{overflow_id}/students").status_code == 422
        assert client.get(f"/groups/{overflow_id}/statistics").status_code == 422
        assert (
            client.patch(
                f"/students/{overflow_id}", json={"first_name": "Оновлено"}
            ).status_code
            == 422
        )
        assert client.delete(f"/students/{overflow_id}").status_code == 422
        assert client.get(f"/students?group_id={overflow_id}").status_code == 422
        assert (
            client.post(
                "/students",
                json={
                    "first_name": "Тест",
                    "last_name": "Тест",
                    "group_id": overflow_id,
                    "average_grade": 80.0,
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/students",
                json={
                    "student_id": overflow_id,
                    "first_name": "Тест",
                    "last_name": "Тест",
                    "group_id": 1,
                    "average_grade": 80.0,
                },
            ).status_code
            == 422
        )
        assert (
            client.patch("/students/1", json={"group_id": overflow_id}).status_code
            == 422
        )


def test_health() -> None:
    from student_manager.api import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
