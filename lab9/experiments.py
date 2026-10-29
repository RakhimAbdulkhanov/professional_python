"""Real Lab 9 measurements; execute with python -m lab9.experiments."""

from __future__ import annotations

import argparse
import cProfile
import csv
import hashlib
import json
import math
import multiprocessing
import os
import platform
import pstats
import random
import subprocess
import sys
import tracemalloc
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from student_manager.performance import Statistics, StudentSnapshot


def statistics_output(result: Statistics) -> dict[str, Any]:
    return {
        "count": result.count,
        "average": result.average,
        "minimum": result.minimum,
        "maximum": result.maximum,
        "population_stddev": result.population_stddev,
        "group_averages": dict(result.group_averages),
        "student_ids": list(result.student_ids),
        "ranking_ids": list(result.ranking_ids),
    }


def assert_parity(actual: Statistics, expected: Statistics) -> None:
    if (actual.count, actual.student_ids, actual.ranking_ids) != (
        expected.count,
        expected.student_ids,
        expected.ranking_ids,
    ):
        raise AssertionError("count, IDs or stable ranking mismatch")
    for field in ("average", "minimum", "maximum", "population_stddev"):
        left, right = getattr(actual, field), getattr(expected, field)
        if left is None or right is None:
            if left != right:
                raise AssertionError(f"{field} mismatch")
        elif not math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-9):
            raise AssertionError(f"{field} mismatch")
    left_groups, right_groups = (
        dict(actual.group_averages),
        dict(expected.group_averages),
    )
    if left_groups.keys() != right_groups.keys() or any(
        not math.isclose(value, right_groups[key], rel_tol=1e-10, abs_tol=1e-9)
        for key, value in left_groups.items()
    ):
        raise AssertionError("group averages mismatch")


def measure(
    method: str,
    function: Callable[[], Statistics],
    expected: Statistics,
    *,
    repeats: int,
    workers: int = 1,
) -> dict[str, Any]:
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    times, outputs = [], []
    for _ in range(repeats):
        start = perf_counter()
        result = function()
        times.append(perf_counter() - start)
        assert_parity(result, expected)
        outputs.append(statistics_output(result))
    return {
        "method": method,
        "workers": workers,
        "raw_seconds": times,
        "mean_seconds": mean(times),
        "outputs": outputs,
        "parity": True,
    }


def add_speedups(rows: Iterable[dict[str, Any]], baseline: float) -> None:
    for row in rows:
        row["speedup"] = baseline / row["mean_seconds"]


CSV_FIELDS = ("student_id", "first_name", "last_name", "group", "average_grade")


def write_shards(
    rows: tuple[StudentSnapshot, ...], directory: Path, *, shards: int
) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    width = max(1, math.ceil(len(rows) / shards))
    paths = []
    for index, start in enumerate(range(0, len(rows), width)):
        path = directory / f"students_{index:03d}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_FIELDS)
            for row in rows[start : start + width]:
                writer.writerow(
                    (
                        row.student_id,
                        row.first_name,
                        row.last_name,
                        row.group,
                        row.average_grade,
                    )
                )
        paths.append(path)
    return tuple(paths)


def _read_shard(path: Path) -> tuple[StudentSnapshot, ...]:
    from student_manager.performance import snapshot
    from student_manager.streaming import open_student_stream

    with path.open(encoding="utf-8", newline="") as stream:
        if next(csv.reader(stream), None) != list(CSV_FIELDS):
            raise ValueError(f"invalid CSV header: {path}")
    with open_student_stream(path) as students:
        return snapshot(students)


def read_shards(
    paths: tuple[Path, ...], *, workers: int | None = None
) -> tuple[StudentSnapshot, ...]:
    if workers is None:
        batches = [_read_shard(path) for path in paths]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            batches = list(pool.map(_read_shard, paths))
    return tuple(row for batch in batches for row in batch)


def io_experiment(
    rows: tuple[StudentSnapshot, ...],
    directory: Path,
    workers: tuple[int, ...],
    *,
    repeats: int,
    shards: int,
) -> dict[str, Any]:
    paths = write_shards(rows, directory, shards=shards)
    measurements: list[dict[str, Any]] = []
    for count in (None, *workers):
        times = []
        for _ in range(repeats):
            start = perf_counter()
            actual = read_shards(paths, workers=count)
            times.append(perf_counter() - start)
            if actual != rows:
                raise AssertionError("CSV records differ from deterministic input")
        measurements.append(
            {
                "method": "sequential" if count is None else "thread",
                "workers": count or 1,
                "raw_seconds": times,
                "mean_seconds": mean(times),
                "parity": True,
                "record_count": len(rows),
            }
        )
    add_speedups(measurements, measurements[0]["mean_seconds"])
    return {
        "paths": [str(path.resolve()) for path in paths],
        "measurements": measurements,
        "filesystem_cache": "uncontrolled; repeated reads may use OS cache",
        "timing_scope": "open/read/CSV parse/validate/materialize/pool startup; writes excluded",
    }


def cache_experiment(
    rows: tuple[StudentSnapshot, ...], *, repeats: int
) -> dict[str, Any]:
    from student_manager.performance import StatisticsService, statistics_python

    group = rows[0].group
    expected = statistics_python(rows, group=group)
    cold_times, warm_times, checks = [], [], []
    for _ in range(repeats):
        service = StatisticsService(rows)
        cold = measure("cold", partial(service.statistics, group), expected, repeats=1)
        warm = measure("warm", partial(service.statistics, group), expected, repeats=1)
        cold_times.extend(cold["raw_seconds"])
        warm_times.extend(warm["raw_seconds"])
        checks.append(asdict(service.cache_info()))
        if checks[-1]["hits"] != 1 or checks[-1]["misses"] != 1:
            raise AssertionError("expected one actual cache hit and miss")
    service = StatisticsService(rows)
    before = service.statistics(group)
    service.add_student(
        StudentSnapshot(
            max(row.student_id for row in rows) + 1, "New", "Student", group, 0.0
        )
    )
    after_add = service.statistics(group)
    assert_parity(after_add, statistics_python(service.snapshot(), group=group))
    added = {
        "output": statistics_output(after_add),
        "cache_info": asdict(service.cache_info()),
        "parity": True,
    }
    service.update_grade(max(row.student_id for row in service.snapshot()), 100.0)
    after_update = service.statistics(group)
    assert_parity(after_update, statistics_python(service.snapshot(), group=group))
    cold_mean, warm_mean = mean(cold_times), mean(warm_times)
    return {
        "group": group,
        "cold": {"raw_seconds": cold_times, "mean_seconds": cold_mean},
        "warm": {
            "raw_seconds": warm_times,
            "mean_seconds": warm_mean,
            "speedup": cold_mean / warm_mean,
        },
        "hit_miss_checks": checks,
        "before": statistics_output(before),
        "after_add": added,
        "after_update": {
            "output": statistics_output(after_update),
            "cache_info": asdict(service.cache_info()),
            "parity": True,
        },
        "timing_scope": "statistics call only; service construction and mutation excluded",
    }


def profile_operation(
    function: Callable[[], Statistics],
    expected: Statistics,
    path: Path,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    result = profiler.runcall(function)
    assert_parity(result, expected)
    profiler.dump_stats(str(path))
    stats: Any = pstats.Stats(profiler)
    entries = [
        {
            "function": f"{filename}:{line}:{name}",
            "primitive_calls": values[0],
            "calls": values[1],
            "self_seconds": values[2],
            "cumulative_seconds": values[3],
        }
        for (filename, line, name), values in stats.stats.items()
    ]
    total = stats.total_tt
    entries.sort(key=lambda item: item["cumulative_seconds"], reverse=True)
    bottleneck = dict(max(entries, key=lambda item: item["self_seconds"]))
    bottleneck["self_time_fraction"] = (
        bottleneck["self_seconds"] / total if total else 0.0
    )
    tracemalloc.start()
    try:
        memory_result = function()
        current, peak = tracemalloc.get_traced_memory()
        allocations = tracemalloc.take_snapshot().statistics("lineno")[:10]
    finally:
        tracemalloc.stop()
    assert_parity(memory_result, expected)
    return {
        "profile_path": str(path.resolve()),
        "total_calls": stats.total_calls,
        "total_seconds": total,
        "functions": entries,
        "bottleneck": bottleneck,
        "memory": {
            "current_bytes": current,
            "peak_bytes": peak,
            "top_allocations": [str(item) for item in allocations],
            "scope": "parent traced Python allocations only; child processes and native RAM excluded",
        },
        "profiling_scope": "one separate instrumented call; not benchmark timing; cProfile covers calling thread only, not pool worker threads/processes",
    }


@dataclass(frozen=True)
class Parameters:
    sizes: tuple[int, ...] = (10_000, 100_000, 300_000)
    workers: tuple[int, ...] = (1, 2, 4)
    repeats: int = 5
    seed: int = 42
    groups: int = 12
    shards: int = 8

    def __post_init__(self) -> None:
        values = (*self.sizes, *self.workers, self.repeats, self.groups, self.shards)
        if (
            not self.sizes
            or not self.workers
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in values
            )
        ):
            raise ValueError(
                "sizes, workers, repeats, groups and shards must be positive"
            )


def generate_students(
    count: int, *, seed: int = 42, groups: int = 12
) -> tuple[StudentSnapshot, ...]:
    if count <= 0 or groups <= 0:
        raise ValueError("count and groups must be positive")
    rng = random.Random(seed)
    return tuple(
        StudentSnapshot(
            index + 1,
            f"Name{index}",
            f"Surname{index}",
            f"g{index % groups}",
            rng.randrange(10_001) / 100,
        )
        for index in range(count)
    )


def run_experiments(
    parameters: Parameters, output: Path, executable: Path
) -> dict[str, Any]:
    import numpy as np

    from student_manager import performance

    executable = executable.resolve(strict=True)
    probe_command = [
        str(executable),
        "-c",
        "import json,sys; print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:3])}))",
    ]
    probe_run = subprocess.run(
        probe_command, check=True, capture_output=True, text=True, timeout=20
    )
    probe = json.loads(probe_run.stdout)
    if probe["version"][:2] != list(sys.version_info[:2]):
        raise ValueError("spawn runtime must match current Python major/minor")
    multiprocessing.set_executable(str(executable))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = output.parent / f"{output.stem}_artifacts"
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "parameters": asdict(parameters),
        "runtime": {
            "executable": sys.executable,
            "spawn_executable": str(executable),
            "probe_command": probe_command,
            "probe": probe,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "numpy": np.__version__,
            "start_method": "spawn",
        },
        "timing_scope": "complete statistics calls include validation/snapshot, NumPy conversion, pool creation/shutdown, serialization, merging and global ranking; dataset creation/checking/JSON excluded",
        "comparison": "mean baseline seconds / mean method seconds within same dataset and group scope; below 1 is slowdown",
        "floating_tolerance": {"relative": 1e-10, "absolute": 1e-9},
        "datasets": [],
    }
    for size in parameters.sizes:
        rows = generate_students(size, seed=parameters.seed, groups=parameters.groups)
        dataset: dict[str, Any] = {"size": size, "measurements": []}
        for scope, group in (("all", None), ("group", rows[0].group)):
            expected = performance.statistics_python(rows, group=group)
            methods: list[tuple[str, int, Callable[[], Statistics]]] = [
                (
                    "baseline",
                    1,
                    partial(performance.statistics_python, rows, group=group),
                ),
                ("numpy", 1, partial(performance.statistics_numpy, rows, group=group)),
            ]
            for backend in ("thread", "process"):
                for workers in parameters.workers:
                    methods.append(
                        (
                            backend,
                            workers,
                            partial(
                                performance.statistics_parallel,
                                rows,
                                backend=backend,
                                workers=workers,
                                group=group,
                            ),
                        )
                    )
            scoped = []
            for method, workers, function in methods:
                item = measure(
                    method,
                    function,
                    expected,
                    repeats=parameters.repeats,
                    workers=workers,
                )
                item["scope"], item["group"] = scope, group
                item["profile"] = profile_operation(
                    function,
                    expected,
                    artifact_dir / str(size) / f"{scope}_{method}_{workers}.prof",
                )
                scoped.append(item)
            add_speedups(scoped, scoped[0]["mean_seconds"])
            dataset["measurements"].extend(scoped)
        expected_ids = [row.student_id for row in rows if row.group == rows[0].group]
        search_times, search_outputs = [], []
        for _ in range(parameters.repeats):
            start = perf_counter()
            found = performance.search_group(rows, f" {rows[0].group.upper()} ")
            search_times.append(perf_counter() - start)
            ids = [row.student_id for row in found]
            if ids != expected_ids:
                raise AssertionError("normalized group search mismatch")
            search_outputs.append(ids)
        dataset["search"] = {
            "group": rows[0].group,
            "raw_seconds": search_times,
            "mean_seconds": mean(search_times),
            "outputs": search_outputs,
            "parity": True,
        }
        dataset["io"] = io_experiment(
            rows,
            artifact_dir / str(size) / "csv",
            parameters.workers,
            repeats=parameters.repeats,
            shards=parameters.shards,
        )
        dataset["cache"] = cache_experiment(rows, repeats=parameters.repeats)
        dataset["data_sha256"] = hashlib.sha256(
            json.dumps([asdict(row) for row in rows], sort_keys=True).encode()
        ).hexdigest()
        result["datasets"].append(dataset)
        output.write_text(
            json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
        )
        print(
            f"size={size} measurements={len(dataset['measurements'])} parity=ok",
            flush=True,
        )
    result["status"] = "complete"
    result["finished_at"] = datetime.now(UTC).isoformat()
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick", action="store_true", help="same operations on 24/48/96 rows"
    )
    parser.add_argument("--sizes", type=int, nargs="+")
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--groups", type=int, default=12)
    parser.add_argument("--shards", type=int, default=8)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="existing matching Python runtime for spawn and recorded probe",
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".local_workflow/lab9/results_v1.json")
    )
    args = parser.parse_args()
    parameters = Parameters(
        sizes=tuple(
            args.sizes or ((24, 48, 96) if args.quick else (10_000, 100_000, 300_000))
        ),
        workers=tuple(args.workers),
        repeats=args.repeats,
        seed=args.seed,
        groups=args.groups,
        shards=args.shards,
    )
    run_experiments(parameters, args.output, args.python)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
