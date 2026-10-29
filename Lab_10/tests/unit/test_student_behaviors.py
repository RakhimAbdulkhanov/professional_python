import json
from pathlib import Path
from typing import Any

import pytest

from student_manager.config import load_config
from student_manager.domain import AcademicRecord, Grade
from student_manager.exceptions import (
    ConfigurationError,
    DataImportError,
    RecordValidationError,
)
from student_manager.models import Student
from student_manager.reliable_io import (
    export_students_json,
    parse_student,
    read_csv_rows,
)


@pytest.mark.unit
def test_student_valid_construction_and_full_name() -> None:
    # перевірка створення студента з валідними даними
    student = Student(
        first_name="Остап",
        last_name="Бендер",
        group="ФеП-33",
        average_grade=89.5,
        student_id=10,
    )
    assert student.first_name == "Остап"
    assert student.last_name == "Бендер"
    assert student.group == "ФеП-33"
    assert student.average_grade == pytest.approx(89.5)
    assert student.student_id == 10
    assert student.full_name == "Остап Бендер"


@pytest.mark.unit
@pytest.mark.parametrize(
    "first_name,last_name,group",
    [
        ("", "Бендер", "ФеП-33"),
        ("  ", "Бендер", "ФеП-33"),
        ("Остап", "", "ФеП-33"),
        ("Остап", "   ", "ФеП-33"),
        ("Остап", "Бендер", ""),
        ("Остап", "Бендер", "   "),
    ],
)
def test_student_required_fields_reject_empty(
    first_name: str, last_name: str, group: str
) -> None:
    # обов'язкові поля не можуть бути порожніми або складатись з пробілів
    with pytest.raises(ValueError, match="cannot be empty"):
        Student(
            first_name=first_name,
            last_name=last_name,
            group=group,
            average_grade=80.0,
            student_id=1,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "grade,is_valid",
    [
        (0.0, True),
        (100.0, True),
        (50.5, True),
        (-0.1, False),
        (100.1, False),
        (-25.0, False),
        (150.0, False),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
    ],
)
def test_student_grade_boundaries_and_invalid_values(
    grade: float, is_valid: bool
) -> None:
    # перевірка меж оцінки від 0 до 100 та відхилення нескінченних і nan значень
    if is_valid:
        st = Student("Тарас", "Шевченко", "ФеП-31", grade, student_id=2)
        assert st.average_grade == pytest.approx(grade)
    else:
        with pytest.raises(ValueError, match="Average grade must be between 0 and 100"):
            Student("Тарас", "Шевченко", "ФеП-31", grade, student_id=2)


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid_id,expected_error",
    [
        (0, ValueError),
        (-1, ValueError),
        (-100, ValueError),
        (True, TypeError),
        (False, TypeError),
        (1.5, TypeError),
    ],
)
def test_student_id_type_and_positivity_validation(
    invalid_id: Any, expected_error: type[Exception]
) -> None:
    # id студента має бути додатнім цілим числом і не bool
    with pytest.raises(expected_error):
        Student("Леся", "Українка", "ФеП-33", 95.0, student_id=invalid_id)


@pytest.mark.unit
def test_grade_finite_boundaries_and_rejections() -> None:
    # перевірка доменного об'єкта Grade
    g_min = Grade(0.0)
    g_max = Grade(100.0)
    assert float(g_min) == pytest.approx(0.0)
    assert float(g_max) == pytest.approx(100.0)

    with pytest.raises(TypeError, match="cannot be a boolean"):
        Grade(True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must be a finite number"):
        Grade(float("nan"))

    with pytest.raises(ValueError, match="must be a finite number"):
        Grade(float("inf"))

    with pytest.raises(ValueError, match="between 0 and 100"):
        Grade(-0.01)

    with pytest.raises(ValueError, match="between 0 and 100"):
        Grade(100.01)


@pytest.mark.unit
def test_academic_record_empty_grades_returns_none() -> None:
    # порожня картка студента повертає None для середнього бала
    rec = AcademicRecord(student_id=5)
    assert rec.average is None
    assert len(rec) == 0


@pytest.mark.unit
def test_academic_record_average_calculation_with_pytest_approx() -> None:
    # розрахунок середнього бала через pytest.approx для дійсних чисел
    grades = (Grade(85.5), Grade(92.3), Grade(78.1))
    rec = AcademicRecord(student_id=5, grades=grades)
    expected_avg = (85.5 + 92.3 + 78.1) / 3
    assert rec.average is not None
    assert rec.average == pytest.approx(expected_avg, abs=1e-6)
    assert len(rec) == 3


@pytest.mark.unit
def test_academic_record_add_grade_immutability() -> None:
    # додавання оцінки повертає новий незмінний об'єкт
    rec1 = AcademicRecord(student_id=1, grades=(Grade(80.0),))
    rec2 = rec1.add_grade(Grade(90.0))
    assert rec1 is not rec2
    assert len(rec1) == 1
    assert len(rec2) == 2
    assert rec2.average == pytest.approx(85.0)


@pytest.mark.unit
def test_academic_record_rejects_invalid_student_id() -> None:
    # картка блокує невалідні id
    with pytest.raises(ValueError, match="must be a positive integer"):
        AcademicRecord(student_id=0)
    with pytest.raises(ValueError, match="must be a positive integer"):
        AcademicRecord(student_id=-3)
    with pytest.raises(ValueError, match="must be a positive integer"):
        AcademicRecord(student_id=True)  # type: ignore[arg-type]


@pytest.mark.unit
def test_parse_student_malformed_csv_row_raises_record_validation_error() -> None:
    # кастомний виняток RecordValidationError для некоректних рядків csv
    bad_id_row = {
        "student_id": "-5",
        "first_name": "Іван",
        "last_name": "Франко",
        "group": "ФеП-32",
        "average_grade": "85.0",
    }
    with pytest.raises(RecordValidationError) as exc_info:
        parse_student(bad_id_row, line_number=3)
    assert exc_info.value.line_number == 3
    assert exc_info.value.field == "student_id"

    bad_width_row = {"_width_error": "expected 5 columns, got 3"}
    with pytest.raises(RecordValidationError) as exc_width:
        parse_student(bad_width_row, line_number=7)
    assert exc_width.value.line_number == 7
    assert exc_width.value.field == "row"

    nan_grade_row = {
        "student_id": "1",
        "first_name": "Іван",
        "last_name": "Франко",
        "group": "ФеП-32",
        "average_grade": "nan",
    }
    with pytest.raises(RecordValidationError) as exc_nan:
        parse_student(nan_grade_row, line_number=9)
    assert exc_nan.value.line_number == 9
    assert exc_nan.value.field == "average_grade"


@pytest.mark.unit
def test_read_csv_rows_header_schema_mismatch_raises_data_import_error(
    tmp_path: Path,
) -> None:
    # несумісний заголовок csv викидає DataImportError
    bad_csv = tmp_path / "invalid_header.csv"
    bad_csv.write_text("name,grade,email\nОстап,90,ostap@lnu.ua\n", encoding="utf-8")
    with pytest.raises(DataImportError, match="Invalid CSV header schema"):
        list(read_csv_rows(bad_csv))


@pytest.mark.unit
def test_read_csv_rows_missing_file_raises_data_import_error(
    tmp_path: Path,
) -> None:
    # відсутній файл викидає DataImportError
    missing_csv = tmp_path / "does_not_exist.csv"
    with pytest.raises(DataImportError, match="Input file not found"):
        list(read_csv_rows(missing_csv))


@pytest.mark.unit
def test_export_students_json_creates_valid_file(
    tmp_path: Path, sample_students: list[Student]
) -> None:
    # атомарний експорт списку студентів у json
    out_file = tmp_path / "exported.json"
    exported_count = export_students_json(sample_students, out_file)
    assert exported_count == len(sample_students)
    assert out_file.exists()

    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(loaded) == 4
    assert loaded[0]["first_name"] == "Остап"
    assert loaded[0]["average_grade"] == pytest.approx(88.5)


@pytest.mark.unit
def test_load_config_valid_yaml_creates_app_config(tmp_path: Path) -> None:
    # завантаження валідної конфігурації yaml
    input_file = tmp_path / "students.csv"
    input_file.write_text(
        "student_id,first_name,last_name,group,average_grade\n1,Остап,Бендер,ФеП-33,90.0\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "output.json"
    log_file = tmp_path / "app.log"
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
input:
  path: "{input_file.name}"
output:
  path: "{output_file.name}"
processing:
  minimum_grade: 85.0
  skip_invalid: true
logging:
  level: "INFO"
  path: "{log_file.name}"
""",
        encoding="utf-8",
    )

    cfg = load_config(config_file)
    assert cfg.processing.minimum_grade == pytest.approx(85.0)
    assert cfg.processing.skip_invalid is True
    assert cfg.logging.level == "INFO"
    assert cfg.input_path == input_file.resolve()


@pytest.mark.unit
def test_load_config_malformed_yaml_raises_configuration_error(
    tmp_path: Path,
) -> None:
    # синтаксично битий yaml викидає ConfigurationError
    broken_yaml = tmp_path / "broken.yaml"
    broken_yaml.write_text("input: [unclosed mapping\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_config(broken_yaml)


@pytest.mark.unit
def test_load_config_colliding_paths_raises_configuration_error(
    tmp_path: Path,
) -> None:
    # колізія шляхів вхідного та вихідного файлів викидає ConfigurationError
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("dummy", encoding="utf-8")
    config_file = tmp_path / "colliding.yaml"
    config_file.write_text(
        f"""
input:
  path: "{csv_file.name}"
output:
  path: "{csv_file.name}"
processing:
  minimum_grade: 60.0
  skip_invalid: false
logging:
  level: "INFO"
  path: "app.log"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="collide"):
        load_config(config_file)


@pytest.mark.unit
def test_config_with_monkeypatch_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # перевірка роботи з поточною робочою директорією через monkeypatch
    input_file = tmp_path / "in.csv"
    input_file.write_text(
        "student_id,first_name,last_name,group,average_grade\n1,Остап,Бендер,ФеП-33,90.0\n",
        encoding="utf-8",
    )
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
input:
  path: "in.csv"
output:
  path: "out.json"
processing:
  minimum_grade: 75.0
  skip_invalid: false
logging:
  level: "DEBUG"
  path: "test.log"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    cfg = load_config(Path("config.yaml"))
    assert cfg.input_path == input_file.resolve()
    assert cfg.processing.minimum_grade == pytest.approx(75.0)


@pytest.mark.unit
def test_monkeypatch_function_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_student: Student
) -> None:
    # підміна функції student_to_dict через monkeypatch
    def custom_to_dict(st: Student) -> dict[str, Any]:
        return {
            "custom_id": st.student_id,
            "display": f"{st.last_name.upper()}, {st.first_name}",
            "passed": st.average_grade >= 60.0,
        }

    monkeypatch.setattr("student_manager.reliable_io.student_to_dict", custom_to_dict)

    out_file = tmp_path / "custom_out.json"
    export_students_json([sample_student], out_file)

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["display"] == "БЕНДЕР, Остап"
    assert payload[0]["passed"] is True
    assert "custom_id" in payload[0]
