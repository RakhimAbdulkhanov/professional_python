"""модуль проведення обов'язкових експериментів лабораторної роботи 5"""

import gc
import json
import tempfile
import traceback
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Any

from student_manager.config import (
    AppConfig,
    LoggingConfig,
    ProcessingConfig,
    load_config,
)
from student_manager.exceptions import (
    ApplicationError,
    ConfigurationError,
    RecordValidationError,
)
from student_manager.models import Student
from student_manager.reliable_io import (
    ImportStatistics,
    close_logging_handlers,
    configure_logging,
    export_students_json,
    filter_by_grade,
    import_students,
    parse_student,
    process_config,
    read_csv_rows,
)


def generate_synthetic_dataset(
    file_path: Path,
    valid_count: int = 1000,
    invalid_count: int = 10,
    first_invalid_at: int = 100,
) -> None:
    # детермінована генерація для повторюваності результатів
    first_names = [
        "Олена",
        "Іван",
        "Марія",
        "Тарас",
        "Оксана",
        "Андрій",
        "Софія",
        "Максим",
    ]
    last_names = [
        "Коваль",
        "Франко",
        "Шевченко",
        "Бойко",
        "Мельник",
        "Кравченко",
        "Лисенко",
    ]
    groups = ["ФеП-31", "ФеП-32", "ФеП-33", "ФеП-34"]

    invalid_indices = set()
    if invalid_count > 0:
        invalid_indices.add(first_invalid_at)
        step = max(1, (valid_count + invalid_count - first_invalid_at) // invalid_count)
        for i in range(1, invalid_count):
            invalid_indices.add(first_invalid_at + i * step)

    total_rows = valid_count + invalid_count

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8", newline="") as f:
        f.write("student_id,first_name,last_name,group,average_grade\n")
        student_id = 1
        for row_idx in range(1, total_rows + 1):
            fn = first_names[(row_idx - 1) % len(first_names)]
            ln = last_names[(row_idx - 1) % len(last_names)]
            grp = groups[(row_idx - 1) % len(groups)]

            if row_idx in invalid_indices:
                # різноманітні невалідні записи
                kind = row_idx % 4
                if kind == 0:
                    f.write(f"{student_id},{fn},{ln},{grp},150.0\n")  # оцінка > 100
                elif kind == 1:
                    f.write(f"-{student_id},{fn},{ln},{grp},85.0\n")  # від'ємний id
                elif kind == 2:
                    f.write(f"{student_id},,{ln},{grp},90.0\n")  # пусте ім'я
                else:
                    f.write(f"{student_id},{fn},{ln},{grp},wrong\n")  # нечислова оцінка
            else:
                grade = round(60.0 + (row_idx * 17 % 40) + ((row_idx % 10) * 0.1), 2)
                f.write(f"{student_id},{fn},{ln},{grp},{grade}\n")
                student_id += 1


def run_strict_vs_tolerant_experiment(work_dir: Path) -> dict[str, Any]:
    csv_path = work_dir / "strict_vs_tolerant_input.csv"
    generate_synthetic_dataset(
        csv_path,
        valid_count=1000,
        invalid_count=10,
        first_invalid_at=105,
    )

    out_strict = work_dir / "out_strict.json"
    log_strict = work_dir / "strict.log"
    out_tolerant = work_dir / "out_tolerant.json"
    log_tolerant = work_dir / "tolerant.log"

    # 1. суворий режим
    cfg_strict = AppConfig(
        input_path=csv_path,
        output_path=out_strict,
        processing=ProcessingConfig(minimum_grade=0.0, skip_invalid=False),
        logging=LoggingConfig(level="INFO", path=log_strict),
    )
    logger_strict = configure_logging(cfg_strict.logging, logger_name="strict_test")
    strict_error_msg = None
    strict_exit = "success"
    stats_strict = ImportStatistics()
    try:
        process_config(cfg_strict, logger=logger_strict, statistics=stats_strict)
    except ApplicationError as err:
        strict_exit = f"aborted: {err.__class__.__name__}"
        strict_error_msg = str(err)
    finally:
        close_logging_handlers(logger_strict)

    strict_committed = out_strict.exists()

    # 2. толерантний режим
    cfg_tolerant = AppConfig(
        input_path=csv_path,
        output_path=out_tolerant,
        processing=ProcessingConfig(minimum_grade=0.0, skip_invalid=True),
        logging=LoggingConfig(level="INFO", path=log_tolerant),
    )
    logger_tolerant = configure_logging(
        cfg_tolerant.logging, logger_name="tolerant_test"
    )
    stats_tolerant = ImportStatistics()
    tolerant_exit = "success"
    try:
        process_config(cfg_tolerant, logger=logger_tolerant, statistics=stats_tolerant)
    except ApplicationError as err:
        tolerant_exit = f"aborted: {err}"
    finally:
        close_logging_handlers(logger_tolerant)

    tolerant_committed = out_tolerant.exists()
    tolerant_json_count = 0
    if tolerant_committed:
        with out_tolerant.open("r", encoding="utf-8") as f:
            tolerant_json_count = len(json.load(f))

    return {
        "strict": {
            "processed_total": stats_strict.total,
            "valid": stats_strict.valid,
            "invalid": stats_strict.invalid,
            "exported": stats_strict.exported,
            "exit_status": strict_exit,
            "error_message": strict_error_msg,
            "file_committed": strict_committed,
        },
        "tolerant": {
            "processed_total": stats_tolerant.total,
            "valid": stats_tolerant.valid,
            "invalid": stats_tolerant.invalid,
            "exported": stats_tolerant.exported,
            "exit_status": tolerant_exit,
            "file_committed": tolerant_committed,
            "records_in_json": tolerant_json_count,
        },
    }


def run_exception_chaining_experiment() -> dict[str, Any]:
    row = {
        "student_id": "1",
        "first_name": "Anna",
        "last_name": "Koval",
        "group": "PI-21",
        "average_grade": "wrong",
    }
    captured_traceback = ""
    cause_repr = ""
    error_repr = ""

    try:
        parse_student(row, line_number=14)
    except RecordValidationError as error:
        error_repr = repr(error)
        cause_repr = repr(error.__cause__)
        captured_traceback = "".join(traceback.format_exception(error))

    return {
        "record": row,
        "error": error_repr,
        "cause": cause_repr,
        "has_chain": cause_repr != "None",
        "traceback": captured_traceback,
    }


def run_atomic_rollback_experiment(work_dir: Path) -> dict[str, Any]:
    out_file = work_dir / "atomic_target.json"
    original_content = '{"protected": "original data should not be corrupted"}'
    out_file.write_text(original_content, encoding="utf-8")

    def failing_stream() -> Iterator[Student]:
        yield Student(
            first_name="Олена",
            last_name="Коваль",
            group="ФеП-33",
            average_grade=95.0,
            student_id=1,
        )
        # штучна помилка всередині генератора
        raise RecordValidationError(
            "Fatal lazy stream error", line_number=2, field="generator"
        )

    error_name = ""
    try:
        export_students_json(failing_stream(), out_file)
    except ApplicationError as err:
        error_name = err.__class__.__name__

    after_content = out_file.read_text(encoding="utf-8")
    leftover_tmps = [p.name for p in out_file.parent.glob("*.tmp")]

    return {
        "target_file": str(out_file),
        "exception_raised": error_name,
        "content_preserved": after_content == original_content,
        "leftover_temporary_files": leftover_tmps,
    }


def run_config_errors_experiment(work_dir: Path) -> list[dict[str, Any]]:
    valid_csv = work_dir / "valid_students.csv"
    valid_csv.write_text(
        "student_id,first_name,last_name,group,average_grade\n1,A,B,C,90\n",
        encoding="utf-8",
    )

    cases = [
        ("missing_config", work_dir / "absent_config.yaml", None),
        ("malformed_yaml", work_dir / "malformed.yaml", "input: [unclosed"),
        (
            "missing_input_section",
            work_dir / "no_input.yaml",
            "output:\n  path: out.json\nprocessing:\n  minimum_grade: 60\n  skip_invalid: true\nlogging:\n  level: INFO\n  path: app.log\n",
        ),
        (
            "grade_out_of_range_150",
            work_dir / "grade_150.yaml",
            f"input:\n  path: {valid_csv.name}\noutput:\n  path: out.json\nprocessing:\n  minimum_grade: 150.0\n  skip_invalid: true\nlogging:\n  level: INFO\n  path: app.log\n",
        ),
        (
            "missing_input_file",
            work_dir / "absent_data.yaml",
            "input:\n  path: not_found.csv\noutput:\n  path: out.json\nprocessing:\n  minimum_grade: 60.0\n  skip_invalid: true\nlogging:\n  level: INFO\n  path: app.log\n",
        ),
        (
            "missing_output_dir",
            work_dir / "create_out_dir.yaml",
            f"input:\n  path: {valid_csv.name}\noutput:\n  path: deep/nested/dir/out.json\nprocessing:\n  minimum_grade: 60.0\n  skip_invalid: true\nlogging:\n  level: INFO\n  path: app.log\n",
        ),
    ]

    results = []
    for label, cfg_path, content in cases:
        if content is not None:
            cfg_path.write_text(content, encoding="utf-8")

        status = ""
        error_type = ""
        try:
            cfg = load_config(cfg_path)
            # перевіряємо чи для missing_output_dir процес створення каталогу проходить успішно
            if label == "missing_output_dir":
                logger = configure_logging(cfg.logging, logger_name="cfg_test")
                try:
                    process_config(cfg, logger=logger)
                    status = (
                        f"success_directory_created_{cfg.output_path.parent.exists()}"
                    )
                finally:
                    close_logging_handlers(logger)
            else:
                status = "loaded_unexpectedly"
        except ConfigurationError as err:
            status = "rejected_as_expected"
            error_type = f"{err.__class__.__name__}: {err}"

        results.append(
            {
                "case": label,
                "config_file": cfg_path.name,
                "status": status,
                "error_diagnostic": error_type,
            }
        )
    return results


def run_streaming_vs_eager_experiment(
    work_dir: Path,
    sizes: tuple[int, ...] = (10_000, 100_000, 500_000),
) -> list[dict[str, Any]]:
    results = []

    for size in sizes:
        csv_path = work_dir / f"bench_{size}.csv"
        # генерація за межами вимірювань
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            f.write("student_id,first_name,last_name,group,average_grade\n")
            batch = []
            for i in range(1, size + 1):
                batch.append(
                    f"{i},Студент{i % 100},Прізвище{i % 100},ФеП-33,{(60 + i % 40):.1f}\n"
                )
                if len(batch) >= 10_000:
                    f.writelines(batch)
                    batch.clear()
            if batch:
                f.writelines(batch)
                batch.clear()

        # 1. Eager вимірювання
        gc.collect()
        tracemalloc.start()
        t0 = perf_counter()

        # eager завантажує весь список у пам'ять
        raw_rows = []
        for line_num, r in read_csv_rows(csv_path):
            raw_rows.append((line_num, r))
        eager_students = [parse_student(r, line_number=ln) for ln, r in raw_rows]
        eager_filtered = [s for s in eager_students if s.average_grade >= 75.0]
        eager_count = len(eager_filtered)

        t_eager = perf_counter() - t0
        _, peak_eager = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 2. Streaming вимірювання
        del raw_rows, eager_students, eager_filtered
        gc.collect()
        tracemalloc.start()
        t0 = perf_counter()

        # streaming обробляє елементи по одному через генератор
        stats = ImportStatistics()
        stream_gen = import_students(csv_path, skip_invalid=True, statistics=stats)
        filtered_gen = filter_by_grade(stream_gen, 75.0)
        stream_count = sum(1 for _ in filtered_gen)

        t_stream = perf_counter() - t0
        _, peak_stream = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # видаляємо великий тестовий csv шоб не займати дисковий простір
        csv_path.unlink(missing_ok=True)

        results.append(
            {
                "dataset_records": size,
                "eager_filtered_count": eager_count,
                "stream_filtered_count": stream_count,
                "eager_time_sec": round(t_eager, 4),
                "streaming_time_sec": round(t_stream, 4),
                "eager_peak_ram_bytes": peak_eager,
                "streaming_peak_ram_bytes": peak_stream,
                "eager_peak_ram_mb": round(peak_eager / (1024 * 1024), 2),
                "streaming_peak_ram_mb": round(peak_stream / (1024 * 1024), 2),
                "ram_saving_factor": round(peak_eager / max(1, peak_stream), 2),
            }
        )

    return results


def run_all_experiments(output_json_path: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)

        exp1 = run_strict_vs_tolerant_experiment(work_dir)
        exp3 = run_exception_chaining_experiment()
        exp4 = run_atomic_rollback_experiment(work_dir)
        exp5 = run_config_errors_experiment(work_dir)
        exp2 = run_streaming_vs_eager_experiment(work_dir)

        all_results = {
            "variant": 1,
            "title": "Lab 5 - Error handling, files and serialization",
            "experiment_1_strict_vs_tolerant": exp1,
            "experiment_2_streaming_vs_eager": exp2,
            "experiment_3_exception_chaining": exp3,
            "experiment_4_atomic_output": exp4,
            "experiment_5_configuration_errors": exp5,
        }

        if output_json_path is not None:
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            output_json_path.write_text(
                json.dumps(all_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return all_results


def main() -> None:
    evidence_dir = Path(".local_workflow/lab5")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / "experiment_results.json"

    print("Running Lab 5 experiments...")
    results = run_all_experiments(output_json_path=json_path)
    print(f"Experiments successfully completed! Genuine results saved to {json_path}")
    print("\n=== Experiment 1: Strict vs Tolerant ===")
    print(
        json.dumps(
            results["experiment_1_strict_vs_tolerant"], indent=2, ensure_ascii=False
        )
    )
    print("\n=== Experiment 2: Streaming vs Eager (RAM & Time) ===")
    for row in results["experiment_2_streaming_vs_eager"]:
        print(
            f"Size: {row['dataset_records']:>7} rows | "
            f"Eager: {row['eager_time_sec']:>6.2f}s, {row['eager_peak_ram_mb']:>6.2f} MB | "
            f"Stream: {row['streaming_time_sec']:>6.2f}s, {row['streaming_peak_ram_mb']:>6.2f} MB | "
            f"RAM saved: {row['ram_saving_factor']}x"
        )
    print("\n=== Experiment 4: Atomic output rollback ===")
    print(
        json.dumps(results["experiment_4_atomic_output"], indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
