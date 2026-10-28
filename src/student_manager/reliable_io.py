"""надійний модуль потокового введення та виведення даних"""

import csv
import json
import logging
import math
import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import IO, Any, Protocol, runtime_checkable

from student_manager.config import AppConfig, LoggingConfig
from student_manager.exceptions import (
    DataExportError,
    DataImportError,
    RecordValidationError,
)
from student_manager.models import Student

EXPECTED_CSV_HEADER = [
    "student_id",
    "first_name",
    "last_name",
    "group",
    "average_grade",
]


@dataclass
class ImportStatistics:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    exported: int = 0


def parse_student(row: dict[str, str], *, line_number: int) -> Student:
    # перевіряємо чи рядок мав правильну кількість колонок
    if "_width_error" in row:
        raise RecordValidationError(
            f"Malformed row width: {row['_width_error']}",
            line_number=line_number,
            field="row",
        )

    # перевірка student_id
    raw_id = row.get("student_id")
    if raw_id is None or not str(raw_id).strip():
        raise RecordValidationError(
            "Student ID cannot be empty",
            line_number=line_number,
            field="student_id",
        )
    try:
        student_id = int(str(raw_id).strip())
    except (ValueError, TypeError) as err:
        raise RecordValidationError(
            f"Invalid student ID '{raw_id}': must be an integer",
            line_number=line_number,
            field="student_id",
        ) from err
    if student_id <= 0:
        raise RecordValidationError(
            f"Student ID must be a positive integer, got {student_id}",
            line_number=line_number,
            field="student_id",
        )

    # перевірка first_name
    first_name = (row.get("first_name") or "").strip()
    if not first_name:
        raise RecordValidationError(
            "First name cannot be empty",
            line_number=line_number,
            field="first_name",
        )

    # перевірка last_name
    last_name = (row.get("last_name") or "").strip()
    if not last_name:
        raise RecordValidationError(
            "Last name cannot be empty",
            line_number=line_number,
            field="last_name",
        )

    # перевірка group
    group = (row.get("group") or "").strip()
    if not group:
        raise RecordValidationError(
            "Group cannot be empty",
            line_number=line_number,
            field="group",
        )

    # перевірка average_grade
    raw_grade = row.get("average_grade")
    if raw_grade is None or not str(raw_grade).strip():
        raise RecordValidationError(
            "Average grade cannot be empty",
            line_number=line_number,
            field="average_grade",
        )
    try:
        grade = float(str(raw_grade).strip())
    except (ValueError, TypeError) as err:
        raise RecordValidationError(
            f"Invalid grade '{raw_grade}': must be numeric",
            line_number=line_number,
            field="average_grade",
        ) from err

    if not math.isfinite(grade):
        raise RecordValidationError(
            f"Average grade must be a finite number, got {raw_grade}",
            line_number=line_number,
            field="average_grade",
        )
    if not 0.0 <= grade <= 100.0:
        raise RecordValidationError(
            f"Average grade must be between 0 and 100, got {grade}",
            line_number=line_number,
            field="average_grade",
        )

    return Student(
        first_name=first_name,
        last_name=last_name,
        group=group,
        average_grade=grade,
        student_id=student_id,
    )


def read_csv_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    try:
        file = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as err:
        raise DataImportError(f"Input file not found: {path}") from err
    except (OSError, PermissionError) as err:
        raise DataImportError(f"Cannot open input file {path}: {err}") from err

    with file:
        reader = csv.reader(file, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            raise DataImportError(f"CSV file is empty: {path}")
        except (UnicodeDecodeError, csv.Error, OSError) as err:
            raise DataImportError(
                f"Failed to read CSV header from {path}: {err}"
            ) from err

        if header != EXPECTED_CSV_HEADER:
            raise DataImportError(
                f"Invalid CSV header schema: expected {EXPECTED_CSV_HEADER}, got {header}"
            )

        try:
            for row in reader:
                line_num = reader.line_num
                if len(row) != len(EXPECTED_CSV_HEADER):
                    row_dict = {
                        "_width_error": f"expected {len(EXPECTED_CSV_HEADER)} columns, got {len(row)}"
                    }
                else:
                    row_dict = {
                        EXPECTED_CSV_HEADER[i]: row[i]
                        for i in range(len(EXPECTED_CSV_HEADER))
                    }
                yield (line_num, row_dict)
        except (UnicodeDecodeError, csv.Error, OSError) as err:
            current_line = getattr(reader, "line_num", "unknown")
            raise DataImportError(
                f"Error reading CSV {path} at line {current_line}: {err}"
            ) from err


def import_students(
    path: Path,
    *,
    skip_invalid: bool,
    statistics: ImportStatistics,
    logger: logging.Logger | None = None,
) -> Iterator[Student]:
    log = logger or logging.getLogger("student_manager")
    for line_number, row in read_csv_rows(path):
        statistics.total += 1
        try:
            student = parse_student(row, line_number=line_number)
        except RecordValidationError as error:
            statistics.invalid += 1
            log.warning(
                "Invalid record at line %s (field '%s'): %s",
                error.line_number,
                error.field,
                error,
            )
            if skip_invalid:
                continue
            raise
        statistics.valid += 1
        yield student


def filter_by_grade(
    students: Iterable[Student],
    minimum_grade: float,
) -> Iterator[Student]:
    for student in students:
        if student.average_grade >= minimum_grade:
            yield student


@contextmanager
def atomic_text_writer(path: Path) -> Iterator[IO[str]]:
    resolved_path = path.resolve()
    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise DataExportError(
            f"Cannot create output directory {resolved_path.parent}: {err}"
        ) from err

    temp_path: Path | None = None
    success = False
    committed = False
    try:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=resolved_path.parent,
                prefix=f".{resolved_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                yield temp_file
                temp_file.flush()
                os.fsync(temp_file.fileno())
                success = True
        except OSError as err:
            raise DataExportError(
                f"Cannot write temporary file in {resolved_path.parent}: {err}"
            ) from err

        if success and temp_path is not None:
            try:
                os.replace(temp_path, resolved_path)
                committed = True
            except OSError as err:
                raise DataExportError(
                    f"Cannot replace destination file {resolved_path}: {err}"
                ) from err
    finally:
        if not committed and temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger("student_manager").exception(
                    "Cannot remove incomplete temporary output %s", temp_path
                )


def student_to_dict(student: Student) -> dict[str, Any]:
    return {
        "student_id": student.student_id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "group": student.group,
        "average_grade": student.average_grade,
    }


def export_students_json(students: Iterable[Student], path: Path) -> int:
    count = 0
    with atomic_text_writer(path) as file:
        file.write("[\n")
        first = True
        for student in students:
            if not first:
                file.write(",\n")
            line = json.dumps(student_to_dict(student), ensure_ascii=False, indent=2)
            indented = "\n".join("  " + l for l in line.splitlines())
            file.write(indented)
            first = False
            count += 1
        file.write("\n]\n")
    return count


@runtime_checkable
class StudentExporter(Protocol):
    def export(self, students: Iterable[Student], path: Path) -> int: ...


class JsonStudentExporter:
    def export(self, students: Iterable[Student], path: Path) -> int:
        return export_students_json(students, path)


@contextmanager
def logged_operation(
    operation: str,
    logger: logging.Logger | None = None,
) -> Iterator[None]:
    log = logger or logging.getLogger("student_manager")
    log.info("%s started", operation)
    start = perf_counter()
    try:
        yield
    except BaseException:
        log.exception("%s failed", operation)
        raise
    else:
        elapsed = perf_counter() - start
        log.info("%s finished in %.6f s", operation, elapsed)
    finally:
        # гарантоване завершення контексту операції
        log.debug("%s context closed after %.6f s", operation, perf_counter() - start)


def close_logging_handlers(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        logger.removeHandler(h)
        with suppress(Exception):
            h.close()


def configure_logging(
    config: LoggingConfig,
    logger_name: str = "student_manager",
) -> logging.Logger:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    numeric_level = getattr(logging, config.level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    close_logging_handlers(logger)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(config.path, encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def process_config(
    config: AppConfig,
    logger: logging.Logger | None = None,
    statistics: ImportStatistics | None = None,
) -> ImportStatistics:
    log = logger or logging.getLogger("student_manager")
    stats = statistics if statistics is not None else ImportStatistics()

    with logged_operation("Student processing pipeline", logger=log):
        imported_gen = import_students(
            config.input_path,
            skip_invalid=config.processing.skip_invalid,
            statistics=stats,
            logger=log,
        )
        try:
            filtered_gen = filter_by_grade(
                imported_gen,
                config.processing.minimum_grade,
            )
            exporter = JsonStudentExporter()
            stats.exported = exporter.export(filtered_gen, config.output_path)
        finally:
            if hasattr(imported_gen, "close"):
                imported_gen.close()

    log.info(
        "Total=%s, valid=%s, invalid=%s, exported=%s",
        stats.total,
        stats.valid,
        stats.invalid,
        stats.exported,
    )
    return stats
