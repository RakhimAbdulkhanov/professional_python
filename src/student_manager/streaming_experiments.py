"""Benchmark experiments comparing eager vs lazy stream evaluation."""

import argparse
import csv
import json
import random
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

from student_manager.streaming import (
    PRESCRIBED_HEADERS,
    calculate_statistics,
    filter_by_group,
    filter_by_min_grade,
    open_student_stream,
)

FIRST_NAMES = (
    "Олександр",
    "Андрій",
    "Максим",
    "Іван",
    "Тарас",
    "Ольга",
    "Олена",
    "Марія",
    "Ірина",
    "Леся",
)

LAST_NAMES = (
    "Шевченко",
    "Франко",
    "Українка",
    "Мельник",
    "Коваль",
    "Бондар",
    "Бойко",
    "Кравченко",
    "Ткаченко",
    "Поліщук",
)

GROUPS = ("ФеП-31", "ФеП-32", "ФеП-33", "ФеП-34")


def generate_synthetic_csv(path: Path, count: int, seed: int = 42) -> None:
    # детермінована генерація синтетичних студентів пакетами
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)

    chunk_size = 50_000
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(list(PRESCRIBED_HEADERS))

        current_id = 1
        while current_id <= count:
            batch_limit = min(current_id + chunk_size, count + 1)
            rows = []
            for idx in range(current_id, batch_limit):
                fn = rng.choice(FIRST_NAMES)
                ln = rng.choice(LAST_NAMES)
                grp = rng.choice(GROUPS)
                grade = round(rng.uniform(50.0, 100.0), 2)
                rows.append([idx, fn, ln, grp, grade])
            writer.writerows(rows)
            current_id = batch_limit


def measure_time_to_first_lazy(
    path: Path, target_group: str, min_grade: float
) -> float:
    # вимірюємо час до отримання першого збігу у lazy режимі
    t0 = time.perf_counter()
    with open_student_stream(path) as stream:
        filtered = filter_by_min_grade(filter_by_group(stream, target_group), min_grade)
        _ = next(filtered, None)
    t1 = time.perf_counter()
    return t1 - t0


def measure_time_to_first_eager(
    path: Path, target_group: str, min_grade: float
) -> float:
    # вимірюємо час до отримання першого збігу у eager режимі через спільний парсер
    t0 = time.perf_counter()
    with open_student_stream(path) as stream:
        all_students = list(stream)

    target_group_clean = target_group.strip().casefold()
    matching = [
        s
        for s in all_students
        if s.group.strip().casefold() == target_group_clean
        and s.average_grade >= min_grade
    ]
    _ = matching[0] if matching else None
    t1 = time.perf_counter()
    return t1 - t0


def measure_eager_pipeline(
    path: Path, target_group: str = "ФеП-33", min_grade: float = 75.0
) -> dict[str, Any]:
    # повна матеріалізація даних у пам'яті з використанням тих самих примітивів
    ttfr = measure_time_to_first_eager(path, target_group, min_grade)

    tracemalloc.start()
    t0 = time.perf_counter()

    with open_student_stream(path) as stream:
        all_students = list(stream)

    target_group_clean = target_group.strip().casefold()
    filtered = [
        s
        for s in all_students
        if s.group.strip().casefold() == target_group_clean
        and s.average_grade >= min_grade
    ]

    stats = calculate_statistics(filtered)

    t1 = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "elapsed_seconds": round(t1 - t0, 5),
        "peak_memory_bytes": peak,
        "time_to_first_result_seconds": round(ttfr, 6),
        "stats": stats,
    }

    t1 = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "elapsed_seconds": round(t1 - t0, 5),
        "peak_memory_bytes": peak,
        "time_to_first_result_seconds": round(ttfr, 6),
        "stats": stats,
    }


def measure_lazy_pipeline(
    path: Path, target_group: str = "ФеП-33", min_grade: float = 75.0
) -> dict[str, Any]:
    # потокова обробка через генераторний конвеєр
    ttfr = measure_time_to_first_lazy(path, target_group, min_grade)

    tracemalloc.start()
    t0 = time.perf_counter()

    with open_student_stream(path) as stream:
        filtered = filter_by_min_grade(filter_by_group(stream, target_group), min_grade)
        stats = calculate_statistics(filtered)

    t1 = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "elapsed_seconds": round(t1 - t0, 5),
        "peak_memory_bytes": peak,
        "time_to_first_result_seconds": round(ttfr, 6),
        "stats": stats,
    }


def measure_early_termination(
    path: Path, target_student_id: int = 500
) -> dict[str, Any]:
    # порівняння раннього виходу lazy vs повної матеріалізації eager
    # 1. lazy early termination
    tracemalloc.start()
    t0_lazy = time.perf_counter()
    consumed_lazy = 0
    found_lazy = None

    with open_student_stream(path) as stream:
        for s in stream:
            consumed_lazy += 1
            if s.student_id == target_student_id:
                found_lazy = s
                break

    t1_lazy = time.perf_counter()
    _, peak_lazy = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # 2. eager full materialization
    tracemalloc.start()
    t0_eager = time.perf_counter()

    with open_student_stream(path) as stream:
        all_students = list(stream)

    consumed_eager = len(all_students)
    matching = [s for s in all_students if s.student_id == target_student_id]
    found_eager = matching[0] if matching else None

    t1_eager = time.perf_counter()
    _, peak_eager = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "lazy": {
            "elapsed_seconds": round(t1_lazy - t0_lazy, 6),
            "peak_memory_bytes": peak_lazy,
            "records_consumed": consumed_lazy,
            "found_id": found_lazy.student_id if found_lazy else None,
        },
        "eager": {
            "elapsed_seconds": round(t1_eager - t0_eager, 6),
            "peak_memory_bytes": peak_eager,
            "records_consumed": consumed_eager,
            "found_id": found_eager.student_id if found_eager else None,
        },
    }


def run_experiments(
    work_dir: Path,
    sizes: list[int] | None = None,
    run_million: bool = True,
    output_json: Path | None = None,
) -> int:
    if sizes is None:
        sizes = [10_000, 100_000, 500_000]

    work_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"experiments": []}

    for size in sizes:
        csv_file = work_dir / f"dataset_{size}.csv"
        generate_synthetic_csv(csv_file, count=size, seed=42)

        eager_metric = measure_eager_pipeline(csv_file)
        lazy_metric = measure_lazy_pipeline(csv_file)
        assert eager_metric["stats"] == lazy_metric["stats"], (
            "Eager and lazy stats must match"
        )

        results["experiments"].append(
            {
                "size": size,
                "eager_time_sec": eager_metric["elapsed_seconds"],
                "lazy_time_sec": lazy_metric["elapsed_seconds"],
                "eager_peak_bytes": eager_metric["peak_memory_bytes"],
                "lazy_peak_bytes": lazy_metric["peak_memory_bytes"],
                "eager_time_to_first_sec": eager_metric["time_to_first_result_seconds"],
                "lazy_time_to_first_sec": lazy_metric["time_to_first_result_seconds"],
                "records_matched": lazy_metric["stats"]["count"],
                "average_grade": round(lazy_metric["stats"]["average"], 2)
                if lazy_metric["stats"]["average"]
                else None,
            }
        )

        if csv_file.exists():
            csv_file.unlink()

    if run_million:
        million_file = work_dir / "dataset_1000000.csv"
        generate_synthetic_csv(million_file, count=1_000_000, seed=42)
        early_term = measure_early_termination(million_file, target_student_id=500)
        results["million_records_early_termination"] = early_term
        if million_file.exists():
            million_file.unlink()

    json_str = json.dumps(results, indent=2, ensure_ascii=False)
    print(json_str)

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json_str, encoding="utf-8")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Streaming benchmark experiments")
    parser.add_argument(
        "--work-dir",
        default=".local_workflow/lab3/scratch",
        help="Directory for temporary benchmark files",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[10_000, 100_000, 500_000],
        help="Dataset sizes to benchmark",
    )
    parser.add_argument(
        "--million",
        action="store_true",
        default=True,
        help="Run 1M early termination benchmark",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional path to save JSON results",
    )
    args = parser.parse_args(argv)

    out_path = Path(args.output) if args.output else None
    return run_experiments(
        work_dir=Path(args.work_dir),
        sizes=args.sizes,
        run_million=args.million,
        output_json=out_path,
    )


if __name__ == "__main__":
    sys.exit(main())
