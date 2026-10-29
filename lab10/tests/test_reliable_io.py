import json
import logging
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

from student_manager.config import AppConfig, LoggingConfig, ProcessingConfig
from student_manager.exceptions import (
    DataImportError,
    RecordValidationError,
)
from student_manager.lab5_demo import run_lab5_demo
from student_manager.models import Student
from student_manager.reliable_io import (
    ImportStatistics,
    JsonStudentExporter,
    StudentExporter,
    close_logging_handlers,
    configure_logging,
    export_students_json,
    import_students,
    parse_student,
    process_config,
    read_csv_rows,
)


class TestParseStudent(unittest.TestCase):
    def test_valid_row(self) -> None:
        row = {
            "student_id": "101",
            "first_name": "Іван",
            "last_name": "Франко",
            "group": "ФеП-33",
            "average_grade": "92.5",
        }
        student = parse_student(row, line_number=2)
        self.assertEqual(student.student_id, 101)
        self.assertEqual(student.first_name, "Іван")
        self.assertEqual(student.last_name, "Франко")
        self.assertEqual(student.group, "ФеП-33")
        self.assertEqual(student.average_grade, 92.5)

    def test_invalid_id_not_int(self) -> None:
        row = {
            "student_id": "abc",
            "first_name": "Іван",
            "last_name": "Франко",
            "group": "ФеП-33",
            "average_grade": "92.5",
        }
        with self.assertRaises(RecordValidationError) as ctx:
            parse_student(row, line_number=5)
        self.assertEqual(ctx.exception.line_number, 5)
        self.assertEqual(ctx.exception.field, "student_id")
        self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_invalid_id_non_positive(self) -> None:
        for bad_id in ["0", "-5"]:
            row = {
                "student_id": bad_id,
                "first_name": "Іван",
                "last_name": "Франко",
                "group": "ФеП-33",
                "average_grade": "92.5",
            }
            with self.assertRaises(RecordValidationError) as ctx:
                parse_student(row, line_number=6)
            self.assertEqual(ctx.exception.field, "student_id")

    def test_empty_text_fields(self) -> None:
        for field_name in ["first_name", "last_name", "group"]:
            row = {
                "student_id": "1",
                "first_name": "Іван",
                "last_name": "Франко",
                "group": "ФеП-33",
                "average_grade": "90.0",
            }
            row[field_name] = "   "
            with self.assertRaises(RecordValidationError) as ctx:
                parse_student(row, line_number=7)
            self.assertEqual(ctx.exception.field, field_name)

    def test_invalid_grade_non_numeric(self) -> None:
        row = {
            "student_id": "1",
            "first_name": "Іван",
            "last_name": "Франко",
            "group": "ФеП-33",
            "average_grade": "wrong",
        }
        with self.assertRaises(RecordValidationError) as ctx:
            parse_student(row, line_number=8)
        self.assertEqual(ctx.exception.field, "average_grade")
        self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_invalid_grade_range_and_non_finite(self) -> None:
        for bad_grade in ["-0.5", "100.1", "150", "nan", "inf", "-inf"]:
            row = {
                "student_id": "1",
                "first_name": "Іван",
                "last_name": "Франко",
                "group": "ФеП-33",
                "average_grade": bad_grade,
            }
            with self.assertRaises(RecordValidationError) as ctx:
                parse_student(row, line_number=9)
            self.assertEqual(ctx.exception.field, "average_grade")


class TestCsvReader(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_header_schema_failure_raises_fatal_data_import_error(self) -> None:
        # застарілі або неправильні колонки
        bad_csv = self.dir_path / "bad_headers.csv"
        bad_csv.write_text(
            "student_id,name,group,grade,email\n1,Anna,ФеП-33,90,a@b.com\n",
            encoding="utf-8",
        )
        with self.assertRaises(DataImportError) as ctx:
            list(read_csv_rows(bad_csv))
        self.assertIn("header", str(ctx.exception).lower())

    def test_quoted_multiline_csv(self) -> None:
        csv_file = self.dir_path / "multiline.csv"
        content = (
            "student_id,first_name,last_name,group,average_grade\n"
            '1,"Тарас\nГригорович",Шевченко,ФеП-33,98.5\n'
            "2,Леся,Українка,ФеП-33,99.0\n"
        )
        with csv_file.open("w", encoding="utf-8-sig", newline="") as f:
            f.write(content)
        rows = list(read_csv_rows(csv_file))
        self.assertEqual(len(rows), 2)
        # перший запис закінчується на фізичному рядку 3
        self.assertEqual(rows[0][0], 3)
        self.assertEqual(rows[0][1]["first_name"], "Тарас\nГригорович")
        self.assertEqual(rows[1][0], 4)

    def test_malformed_width_row(self) -> None:
        csv_file = self.dir_path / "bad_width.csv"
        # 4 колонки замість 5
        content = (
            "student_id,first_name,last_name,group,average_grade\n"
            "1,Іван,Франко,ФеП-33\n"
        )
        csv_file.write_text(content, encoding="utf-8")
        rows = list(read_csv_rows(csv_file))
        self.assertEqual(len(rows), 1)
        line_num, row_dict = rows[0]
        with self.assertRaises(RecordValidationError) as ctx:
            parse_student(row_dict, line_number=line_num)
        self.assertEqual(ctx.exception.field, "row")

    def test_missing_input_file_raises_data_import_error(self) -> None:
        with self.assertRaises(DataImportError):
            list(read_csv_rows(self.dir_path / "missing.csv"))

    def test_decode_error_raises_data_import_error(self) -> None:
        bad_bytes = self.dir_path / "invalid_utf8.csv"
        bad_bytes.write_bytes(
            b"student_id,first_name,last_name,group,average_grade\n1,\xff\xfe,Franko,Group,90\n"
        )
        with self.assertRaises(DataImportError):
            list(read_csv_rows(bad_bytes))


class TestImportStudents(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.csv_file = self.dir_path / "students.csv"
        # 3 записи: 1 валідний, 1 невалідний (оцінка 150), 1 валідний
        content = (
            "student_id,first_name,last_name,group,average_grade\n"
            "1,Олена,Коваль,ФеП-33,91.0\n"
            "2,Петро,Новак,ФеП-33,150.0\n"
            "3,Марія,Бойко,ФеП-33,85.5\n"
        )
        self.csv_file.write_text(content, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_strict_mode_aborts_at_first_invalid(self) -> None:
        stats = ImportStatistics()
        with self.assertRaises(RecordValidationError) as ctx:
            gen = import_students(self.csv_file, skip_invalid=False, statistics=stats)
            list(gen)

        self.assertEqual(ctx.exception.line_number, 3)
        self.assertEqual(ctx.exception.field, "average_grade")
        self.assertEqual(stats.total, 2)
        self.assertEqual(stats.valid, 1)
        self.assertEqual(stats.invalid, 1)

    def test_tolerant_mode_skips_invalid_and_logs_without_pii(self) -> None:
        stats = ImportStatistics()
        logger = logging.getLogger("test_tolerant")
        logger.setLevel(logging.WARNING)

        log_records: list[logging.LogRecord] = []

        class Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        handler = Handler()
        logger.addHandler(handler)
        try:
            students = list(
                import_students(
                    self.csv_file, skip_invalid=True, statistics=stats, logger=logger
                )
            )
            self.assertEqual(len(students), 2)
            self.assertEqual(stats.total, 3)
            self.assertEqual(stats.valid, 2)
            self.assertEqual(stats.invalid, 1)

            # перевіряємо лог: містить номер рядка та поле, але не повні PII
            self.assertEqual(len(log_records), 1)
            msg = log_records[0].getMessage()
            self.assertIn("line 3", msg)
            self.assertIn("average_grade", msg)
            self.assertNotIn("Петро", msg)
        finally:
            logger.removeHandler(handler)


class TestAtomicWriterAndExport(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_file = self.dir_path / "out" / "result.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_atomic_export_success_and_json_roundtrip(self) -> None:
        students = [
            Student(
                first_name="Олена",
                last_name="Коваль",
                group="ФеП-33",
                average_grade=91.0,
                student_id=1,
            ),
            Student(
                first_name="Марія",
                last_name="Бойко",
                group="ФеП-33",
                average_grade=85.5,
                student_id=2,
            ),
        ]
        exported_count = export_students_json(students, self.output_file)
        self.assertEqual(exported_count, 2)
        self.assertTrue(self.output_file.exists())

        # перевіряємо відсутність залишкових тимчасових файлів
        tmp_files = list(self.output_file.parent.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

        # круглий цикл читання JSON
        with self.output_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["student_id"], 1)
        self.assertEqual(data[0]["first_name"], "Олена")
        self.assertEqual(data[0]["last_name"], "Коваль")
        self.assertEqual(data[0]["group"], "ФеП-33")
        self.assertEqual(data[0]["average_grade"], 91.0)

    def test_atomic_rollback_on_lazy_generator_exception_preserves_existing_output(
        self,
    ) -> None:
        # створюємо старий файл
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        old_content = '{"existing": "data"}'
        self.output_file.write_text(old_content, encoding="utf-8")

        def failing_generator() -> Iterator[Student]:
            yield Student(
                first_name="Олена",
                last_name="Коваль",
                group="ФеП-33",
                average_grade=91.0,
                student_id=1,
            )
            # під час другого елемента генератор падає з RecordValidationError
            raise RecordValidationError("Corrupt stream", line_number=42, field="data")

        with self.assertRaises(RecordValidationError):
            export_students_json(failing_generator(), self.output_file)

        # старий файл не повинен змінитися
        self.assertEqual(self.output_file.read_text(encoding="utf-8"), old_content)
        # тимчасовий файл видалено
        tmp_files = list(self.output_file.parent.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_exporter_protocol(self) -> None:
        exporter = JsonStudentExporter()
        self.assertTrue(isinstance(exporter, StudentExporter))


class TestPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.csv_file = self.dir_path / "students.csv"
        content = (
            "student_id,first_name,last_name,group,average_grade\n"
            "1,Олена,Коваль,ФеП-33,91.0\n"
            "2,Петро,Новак,ФеП-33,55.0\n"  # нижче порогу 60
            "3,Іван,Франко,ФеП-33,88.0\n"
        )
        self.csv_file.write_text(content, encoding="utf-8")
        self.output_file = self.dir_path / "out" / "filtered.json"
        self.log_file = self.dir_path / "logs" / "app.log"

    def tearDown(self) -> None:
        close_logging_handlers(logging.getLogger("student_manager"))
        self.temp_dir.cleanup()

    def test_process_config_success(self) -> None:
        cfg = AppConfig(
            input_path=self.csv_file,
            output_path=self.output_file,
            processing=ProcessingConfig(minimum_grade=60.0, skip_invalid=True),
            logging=LoggingConfig(level="INFO", path=self.log_file),
        )
        logger = configure_logging(cfg.logging)
        stats = process_config(cfg, logger=logger)

        self.assertEqual(stats.total, 3)
        self.assertEqual(stats.valid, 3)
        self.assertEqual(stats.invalid, 0)
        self.assertEqual(stats.exported, 2)  # Петро відфільтрований

        with self.output_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 2)
        names = [d["first_name"] for d in data]
        self.assertEqual(names, ["Олена", "Іван"])
        self.assertTrue(self.log_file.exists())


class TestLab5Demo(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.csv_file = self.dir_path / "students.csv"
        content = (
            "student_id,first_name,last_name,group,average_grade\n"
            "1,Олена,Коваль,ФеП-33,91.0\n"
            "2,Петро,Новак,ФеП-33,85.0\n"
        )
        self.csv_file.write_text(content, encoding="utf-8")
        self.yaml_file = self.dir_path / "config.yaml"
        self.yaml_file.write_text(
            """
input:
  path: students.csv
output:
  path: out.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: app.log
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        close_logging_handlers(logging.getLogger("student_manager"))
        self.temp_dir.cleanup()

    def test_run_lab5_demo_success(self) -> None:
        exit_code = run_lab5_demo([str(self.yaml_file)])
        self.assertEqual(exit_code, 0)
        out_json = self.dir_path / "out.json"
        self.assertTrue(out_json.exists())

    def test_run_lab5_demo_failure_exit_nonzero(self) -> None:
        exit_code = run_lab5_demo([str(self.dir_path / "missing.yaml")])
        self.assertEqual(exit_code, 1)
