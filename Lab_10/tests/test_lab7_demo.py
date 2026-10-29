from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from student_manager.lab7_demo import main, run_demo
from student_manager.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from student_manager.persistence.service import StudentPersistenceService


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    # ізольований шлях до бд з ручним прибиранням
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "demo_test.db"
        yield db_file


def test_run_demo_creates_data_and_returns_dict(temp_db_path: Path) -> None:
    # перевіряємо повний цикл запуску демо та структуру звіту
    result = run_demo(temp_db_path)
    assert isinstance(result, dict)
    assert result["database"] == str(temp_db_path)
    assert len(result["groups"]) == 2
    assert len(result["students_created"]) == 3
    assert result["student_fetched"]["student_id"] == 1
    assert len(result["surname_search"]) >= 1
    assert len(result["group_filter"]) >= 1
    assert result["best_student"] is not None
    assert result["group_average"] is not None
    assert result["grade_updated"]["average_grade"] == 93.5
    assert result["transfer_success"] is True
    assert result["rollback_demonstrated"] is True
    assert result["deleted"] is True
    assert result["remaining_count"] == 2

    # перевіряємо шо дані реально записалися на диск у sqlite
    engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            row_count = conn.execute(text("SELECT count(*) FROM students")).scalar()
            assert row_count == 2
    finally:
        engine.dispose()


def test_run_demo_refuses_existing_file(temp_db_path: Path) -> None:
    # захист від випадкового перезапису існуючої бд
    temp_db_path.write_text("existing content", encoding="utf-8")
    with pytest.raises(FileExistsError, match="вже існує"):
        run_demo(temp_db_path)


def test_main_cli_success(
    temp_db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # перевірка успішного запуску через cli аргументи
    exit_code = main(["--database", str(temp_db_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[Міграції]" in captured.out
    assert "[Групи]" in captured.out
    assert "[Студенти]" in captured.out
    assert "[Атомарність]" in captured.out
    assert captured.err == ""


def test_main_cli_refuses_existing_file(
    temp_db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # перевірка відмови перезапису і повернення коду 1
    temp_db_path.write_text("existing", encoding="utf-8")
    exit_code = main(["--database", str(temp_db_path)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "вже існує" in captured.err


def test_main_cli_missing_database_arg() -> None:
    # перевірка обов'язковості параметра --database
    with pytest.raises(SystemExit):
        main([])


def test_atomic_rollback_verification(temp_db_path: Path) -> None:
    # окрема детальна перевірка збереження цілісності при відкаті транзакції
    run_demo(temp_db_path)

    engine = create_database_engine(f"sqlite:///{temp_db_path.as_posix()}")
    factory = create_session_factory(engine)
    service = StudentPersistenceService(session_factory=factory)
    try:
        # студент 1 має групу ФеП-33
        s1 = service.get_student(1)
        assert s1 is not None
        assert s1.group == "ФеП-33"

        # робимо спробу переведення студента 1 та неіснуючого 99999
        with pytest.raises(ValueError):
            service.transfer_students([1, 99999], target_group_id=2)

        # повторно перевіряємо свіжою сесією шо студент 1 не переведений
        s1_after = service.get_student(1)
        assert s1_after is not None
        assert s1_after.group == "ФеП-33"
    finally:
        engine.dispose()
