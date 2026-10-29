import json
from pathlib import Path

import pytest

from student_manager.config import load_config
from student_manager.domain import Group
from student_manager.exceptions import RecordValidationError
from student_manager.models import Student
from student_manager.registry import (
    RecordingNotifier,
    ReportingService,
    StudentRegistry,
)
from student_manager.reliable_io import (
    close_logging_handlers,
    configure_logging,
    process_config,
)
from student_manager.repositories import InMemoryRepository


@pytest.mark.integration
def test_full_pipeline_csv_to_json_export_with_config(tmp_path: Path) -> None:
    # інтеграційний тест повного пайплайну: csv -> валідація -> фільтрація -> json
    input_csv = tmp_path / "students.csv"
    input_csv.write_text(
        "student_id,first_name,last_name,group,average_grade\n"
        "1,Остап,Бендер,ФеП-33,88.5\n"
        "2,Тарас,Шевченко,ФеП-31,94.0\n"
        "3,Леся,Українка,ФеП-33,91.5\n"
        "4,Іван,Франко,ФеП-32,76.0\n",
        encoding="utf-8",
    )
    output_json = tmp_path / "filtered_students.json"
    log_file = tmp_path / "execution.log"
    config_file = tmp_path / "pipeline_config.yaml"
    config_file.write_text(
        f"""
input:
  path: "{input_csv.name}"
output:
  path: "{output_json.name}"
processing:
  minimum_grade: 85.0
  skip_invalid: true
logging:
  level: "INFO"
  path: "{log_file.name}"
""",
        encoding="utf-8",
    )

    app_config = load_config(config_file)
    logger = configure_logging(app_config.logging, logger_name="test_pipeline_full")
    try:
        stats = process_config(app_config, logger=logger)
    finally:
        close_logging_handlers(logger)

    assert stats.total == 4
    assert stats.valid == 4
    assert stats.invalid == 0
    assert stats.exported == 3

    assert output_json.exists()
    exported_data = json.loads(output_json.read_text(encoding="utf-8"))
    assert len(exported_data) == 3

    exported_ids = [item["student_id"] for item in exported_data]
    assert exported_ids == [1, 2, 3]
    for item in exported_data:
        assert item["average_grade"] >= 85.0

    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "process_config" in log_content or "pipeline" in log_content.lower()


@pytest.mark.integration
def test_pipeline_tolerant_mode_skips_malformed_csv_rows(tmp_path: Path) -> None:
    # толерантний режим: пропускає биті рядки, логує помилки та зберігає валідні
    input_csv = tmp_path / "mixed_students.csv"
    input_csv.write_text(
        "student_id,first_name,last_name,group,average_grade\n"
        "1,Остап,Бендер,ФеП-33,90.0\n"
        "2,Пошкоджений,Рядок\n"
        "3,Тарас,Шевченко,ФеП-31,95.0\n"
        "4,Некоректна,Оцінка,ФеП-33,не_число\n"
        "-5,Від'ємний,Айді,ФеП-32,80.0\n"
        "6,Іван,Франко,ФеП-32,70.0\n",
        encoding="utf-8",
    )
    output_json = tmp_path / "tolerant_out.json"
    log_file = tmp_path / "tolerant.log"
    config_file = tmp_path / "tolerant_config.yaml"
    config_file.write_text(
        f"""
input:
  path: "{input_csv.name}"
output:
  path: "{output_json.name}"
processing:
  minimum_grade: 80.0
  skip_invalid: true
logging:
  level: "WARNING"
  path: "{log_file.name}"
""",
        encoding="utf-8",
    )

    app_config = load_config(config_file)
    logger = configure_logging(app_config.logging, logger_name="test_pipeline_tolerant")
    try:
        stats = process_config(app_config, logger=logger)
    finally:
        close_logging_handlers(logger)

    assert stats.total == 6
    assert stats.valid == 3
    assert stats.invalid == 3
    assert stats.exported == 2

    exported_data = json.loads(output_json.read_text(encoding="utf-8"))
    assert len(exported_data) == 2
    ids = {item["student_id"] for item in exported_data}
    assert ids == {1, 3}

    assert log_file.exists()
    logs = log_file.read_text(encoding="utf-8")
    assert "Invalid record at line" in logs


@pytest.mark.integration
def test_pipeline_strict_mode_aborts_on_malformed_csv(tmp_path: Path) -> None:
    # суворий режим: перериває роботу на першій помилці та не створює битих файлів
    input_csv = tmp_path / "corrupted.csv"
    input_csv.write_text(
        "student_id,first_name,last_name,group,average_grade\n"
        "1,Остап,Бендер,ФеП-33,90.0\n"
        "2,Тарас,Шевченко,ФеП-31,invalid_grade\n",
        encoding="utf-8",
    )
    output_json = tmp_path / "strict_out.json"
    log_file = tmp_path / "strict.log"
    config_file = tmp_path / "strict_config.yaml"
    config_file.write_text(
        f"""
input:
  path: "{input_csv.name}"
output:
  path: "{output_json.name}"
processing:
  minimum_grade: 60.0
  skip_invalid: false
logging:
  level: "INFO"
  path: "{log_file.name}"
""",
        encoding="utf-8",
    )

    app_config = load_config(config_file)
    logger = configure_logging(app_config.logging, logger_name="test_pipeline_strict")
    try:
        with pytest.raises(RecordValidationError) as exc_info:
            process_config(app_config, logger=logger)
    finally:
        close_logging_handlers(logger)

    assert exc_info.value.line_number == 3
    assert exc_info.value.field == "average_grade"
    assert not output_json.exists()


@pytest.mark.integration
def test_end_to_end_registry_workflow_with_export(tmp_path: Path) -> None:
    # взаємодія компонентів реєстру: операції, обчислення та експорт звіту
    repo: InMemoryRepository[Student] = InMemoryRepository()
    notifier = RecordingNotifier()
    registry = StudentRegistry(repository=repo, notifier=notifier)

    st1 = Student("Остап", "Бендер", "ФеП-33", 88.0, student_id=1)
    st2 = Student("Тарас", "Шевченко", "ФеП-31", 94.0, student_id=2)
    st3 = Student("Леся", "Українка", "ФеП-33", 90.0, student_id=3)

    registry.add(1, st1)
    registry.add(2, st2)
    registry.add(3, st3)

    assert len(notifier.messages) == 3
    assert "Added student 1: Остап" in notifier.messages[0]

    updated = registry.edit(1, average_grade=96.0)
    assert updated.average_grade == pytest.approx(96.0)
    assert len(notifier.messages) == 4
    assert "Updated student 1: Остап" in notifier.messages[3]

    best = registry.find_best_student()
    assert best is not None
    assert best.student_id == 1
    assert best.average_grade == pytest.approx(96.0)

    fep33_best = registry.find_best_student(Group("ФеП-33"))
    assert fep33_best is not None
    assert fep33_best.student_id == 1

    fep33_avg = registry.get_average_grade("ФеП-33")
    assert fep33_avg is not None
    assert fep33_avg == pytest.approx(93.0)

    service = ReportingService(registry)
    summary = service.get_summary()
    assert summary["total_students"] == 3
    assert summary["best_student_id"] == 1
    assert summary["overall_average"] == pytest.approx(
        round((96.0 + 94.0 + 90.0) / 3, 2)
    )

    payloads = service.export_students()
    report_file = tmp_path / "registry_report.json"
    report_file.write_text(json.dumps(payloads, ensure_ascii=False), encoding="utf-8")

    loaded = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(loaded) == 3
    assert loaded[0]["student_id"] == 1
    assert loaded[0]["average_grade"] == pytest.approx(96.0)
