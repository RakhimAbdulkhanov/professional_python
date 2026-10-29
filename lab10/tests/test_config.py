import tempfile
import unittest
from pathlib import Path

from student_manager.config import (
    AppConfig,
    LoggingConfig,
    ProcessingConfig,
    load_config,
)
from student_manager.exceptions import (
    ApplicationError,
    ConfigurationError,
    DataError,
    DataExportError,
    DataImportError,
    RecordValidationError,
)


class TestExceptions(unittest.TestCase):
    def test_hierarchy(self) -> None:
        self.assertTrue(issubclass(ConfigurationError, ApplicationError))
        self.assertTrue(issubclass(DataError, ApplicationError))
        self.assertTrue(issubclass(DataImportError, DataError))
        self.assertTrue(issubclass(RecordValidationError, DataError))
        self.assertTrue(issubclass(DataExportError, DataError))

    def test_record_validation_error_attributes(self) -> None:
        err = RecordValidationError("Bad grade", line_number=12, field="average_grade")
        self.assertEqual(err.line_number, 12)
        self.assertEqual(err.field, "average_grade")
        self.assertIn("Bad grade", str(err))

    def test_exception_chaining(self) -> None:
        cause = ValueError("invalid literal for int(): abc")
        try:
            try:
                raise cause
            except ValueError as e:
                raise RecordValidationError(
                    "Invalid ID", line_number=2, field="student_id"
                ) from e
        except RecordValidationError as caught:
            self.assertIs(caught.__cause__, cause)


class TestConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        # створюємо вхідний файл
        self.input_file = self.dir_path / "students.csv"
        self.input_file.write_text(
            "student_id,first_name,last_name,group,average_grade\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_yaml(self, content: str, filename: str = "config.yaml") -> Path:
        cfg_path = self.dir_path / filename
        cfg_path.write_text(content, encoding="utf-8")
        return cfg_path

    def test_load_valid_config(self) -> None:
        yaml_content = """
input:
  path: students.csv
output:
  path: output/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        config = load_config(cfg_path)

        self.assertIsInstance(config, AppConfig)
        self.assertIsInstance(config.processing, ProcessingConfig)
        self.assertIsInstance(config.logging, LoggingConfig)

        # перевіряємо відносні шляхи до папки конфіга
        self.assertEqual(config.input_path, (self.dir_path / "students.csv").resolve())
        self.assertEqual(
            config.output_path, (self.dir_path / "output" / "students.json").resolve()
        )
        self.assertEqual(
            config.logging.path, (self.dir_path / "logs" / "app.log").resolve()
        )

        self.assertEqual(config.processing.minimum_grade, 60.0)
        self.assertTrue(config.processing.skip_invalid)
        self.assertEqual(config.logging.level, "INFO")

    def test_missing_config_file_raises_configuration_error(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            load_config(self.dir_path / "nonexistent.yaml")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_malformed_yaml_raises_configuration_error(self) -> None:
        cfg_path = self._write_yaml("input: [unclosed")
        with self.assertRaises(ConfigurationError) as ctx:
            load_config(cfg_path)
        self.assertIsNotNone(ctx.exception.__cause__)

    def test_non_dict_yaml_raises_configuration_error(self) -> None:
        cfg_path = self._write_yaml("- item 1\n- item 2\n")
        with self.assertRaises(ConfigurationError):
            load_config(cfg_path)

    def test_missing_required_sections(self) -> None:
        yaml_content = """
input:
  path: students.csv
output:
  path: output/students.json
"""
        cfg_path = self._write_yaml(yaml_content)
        with self.assertRaises(ConfigurationError):
            load_config(cfg_path)

    def test_strict_bool_not_coerced(self) -> None:
        # рядки не повинні автоматично перетворюватися на bool
        for bad_val in ['"true"', '"false"', '"yes"', '"no"', "1", "0", '"1"']:
            yaml_content = f"""
input:
  path: students.csv
output:
  path: output/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: {bad_val}
logging:
  level: INFO
  path: logs/app.log
"""
            cfg_path = self._write_yaml(yaml_content, filename="cfg_bad_bool.yaml")
            with self.assertRaises(
                ConfigurationError, msg=f"Should reject {bad_val} as bool"
            ):
                load_config(cfg_path)

    def test_boolean_not_accepted_as_minimum_grade(self) -> None:
        yaml_content = """
input:
  path: students.csv
output:
  path: output/students.json
processing:
  minimum_grade: true
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        with self.assertRaises(ConfigurationError):
            load_config(cfg_path)

    def test_minimum_grade_range_and_finite(self) -> None:
        for bad_grade in [-1.0, 100.1, 150.0]:
            yaml_content = f"""
input:
  path: students.csv
output:
  path: output/students.json
processing:
  minimum_grade: {bad_grade}
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
            cfg_path = self._write_yaml(yaml_content, filename=f"cfg_{bad_grade}.yaml")
            with self.assertRaises(ConfigurationError):
                load_config(cfg_path)

    def test_logging_level_validation(self) -> None:
        for bad_level in ["VERBOSE", "UNKNOWN", "", 123]:
            yaml_content = f"""
input:
  path: students.csv
output:
  path: output/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: {bad_level}
  path: logs/app.log
"""
            cfg_path = self._write_yaml(yaml_content, filename=f"cfg_{bad_level}.yaml")
            with self.assertRaises(ConfigurationError):
                load_config(cfg_path)

    def test_input_file_must_exist(self) -> None:
        yaml_content = """
input:
  path: missing_students.csv
output:
  path: output/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        with self.assertRaises(ConfigurationError) as ctx:
            load_config(cfg_path)
        self.assertIn("exist", str(ctx.exception).lower())

    def test_input_file_cannot_be_directory(self) -> None:
        sub_dir = self.dir_path / "some_dir"
        sub_dir.mkdir()
        yaml_content = f"""
input:
  path: {sub_dir.name}
output:
  path: output/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        with self.assertRaises(ConfigurationError):
            load_config(cfg_path)

    def test_missing_output_dir_is_allowed_in_config(self) -> None:
        yaml_content = """
input:
  path: students.csv
output:
  path: nested/deep/dir/students.json
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        config = load_config(cfg_path)
        self.assertFalse(config.output_path.parent.exists())

    def test_prohibit_colliding_paths(self) -> None:
        # input і output вказують на один файл
        yaml_content = """
input:
  path: students.csv
output:
  path: students.csv
processing:
  minimum_grade: 60.0
  skip_invalid: true
logging:
  level: INFO
  path: logs/app.log
"""
        cfg_path = self._write_yaml(yaml_content)
        with self.assertRaises(ConfigurationError):
            load_config(cfg_path)


def test_default_settings() -> None:
    from student_manager.config import Settings

    settings = Settings()
    assert settings.environment in {
        "development",
        "test",
        "production",
    }
