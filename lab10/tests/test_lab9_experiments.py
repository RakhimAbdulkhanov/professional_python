import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


def runner() -> ModuleType:
    assert importlib.util.find_spec("lab9.experiments") is not None
    return importlib.import_module("lab9.experiments")


def test_deterministic_rows_and_validated_parameters() -> None:
    module = runner()
    rows = module.generate_students(17, seed=42, groups=3)
    assert rows == module.generate_students(17, seed=42, groups=3)
    assert rows != module.generate_students(17, seed=43, groups=3)
    assert [row.student_id for row in rows] == list(range(1, 18))
    assert len({row.group for row in rows}) == 3
    assert all(0 <= row.average_grade <= 100 for row in rows)
    config = module.Parameters()
    assert config.sizes == (10_000, 100_000, 300_000)
    assert config.workers == (1, 2, 4)
    assert config.repeats == 5
    for kwargs in (
        {"repeats": 0},
        {"sizes": ()},
        {"workers": (0,)},
        {"groups": 0},
        {"shards": 0},
    ):
        with pytest.raises(ValueError):
            module.Parameters(**kwargs)
    for kwargs in ({"count": 0}, {"count": 3, "groups": 0}):
        with pytest.raises(ValueError):
            module.generate_students(**kwargs)


def test_measurements_record_real_outputs_and_reject_incorrect_results() -> None:
    module = runner()
    from dataclasses import replace

    from student_manager import performance

    rows = module.generate_students(19, groups=3)
    expected = performance.statistics_python(rows)
    measured = module.measure(
        "numpy",
        lambda: performance.statistics_numpy(rows),
        expected,
        repeats=2,
    )
    assert len(measured["raw_seconds"]) == len(measured["outputs"]) == 2
    assert all(value > 0 for value in measured["raw_seconds"])
    assert measured["mean_seconds"] == pytest.approx(sum(measured["raw_seconds"]) / 2)
    assert measured["outputs"][0]["ranking_ids"] == list(expected.ranking_ids)
    assert measured["outputs"][0]["group_averages"] == dict(expected.group_averages)
    for invalid in (
        replace(expected, count=3),
        replace(expected, ranking_ids=()),
        replace(expected, average=999),
        replace(expected, group_averages=()),
    ):
        with pytest.raises(AssertionError):
            module.measure("bad", lambda invalid=invalid: invalid, expected, repeats=1)
    with pytest.raises(ValueError):
        module.measure("bad", lambda: expected, expected, repeats=0)
    module.add_speedups([measured], measured["mean_seconds"] / 2)
    assert measured["speedup"] == pytest.approx(0.5)


def test_csv_shards_real_sequential_and_threaded_reads(tmp_path: Path) -> None:
    module = runner()
    rows = module.generate_students(23, groups=3)
    paths = module.write_shards(rows, tmp_path, shards=4)
    assert len(paths) == 4
    assert all(path.is_file() for path in paths)
    assert (
        paths[0].read_text(encoding="utf-8").splitlines()[0]
        == "student_id,first_name,last_name,group,average_grade"
    )
    assert module.read_shards(paths) == rows
    for workers in (1, 2, 4):
        assert module.read_shards(paths, workers=workers) == rows
    result = module.io_experiment(rows, tmp_path / "io", (1, 2, 4), repeats=2, shards=4)
    assert len(result["measurements"]) == 4
    assert all(len(item["raw_seconds"]) == 2 for item in result["measurements"])
    assert all(item["parity"] for item in result["measurements"])
    assert result["filesystem_cache"] == "uncontrolled; repeated reads may use OS cache"
    paths[0].write_text("broken\n", encoding="utf-8")
    with pytest.raises(ValueError):
        module.read_shards(paths)


def test_cache_experiment_measures_hits_and_both_invalidations() -> None:
    module = runner()
    result = module.cache_experiment(module.generate_students(23, groups=3), repeats=2)
    assert len(result["cold"]["raw_seconds"]) == len(result["warm"]["raw_seconds"]) == 2
    assert all(
        item["hits"] == 1 and item["misses"] == 1 for item in result["hit_miss_checks"]
    )
    assert result["after_add"]["cache_info"]["version"] == 1
    assert result["after_update"]["cache_info"]["version"] == 2
    assert result["after_add"]["output"]["count"] == result["before"]["count"] + 1
    assert (
        result["after_add"]["output"]["average"]
        != result["after_update"]["output"]["average"]
    )
    assert result["after_update"]["parity"] is True


def test_real_profile_and_tracemalloc_artifacts(tmp_path: Path) -> None:
    module = runner()
    import pstats

    from student_manager import performance

    rows = module.generate_students(31, groups=3)
    expected = performance.statistics_python(rows)
    result = module.profile_operation(
        lambda: performance.statistics_python(rows),
        expected,
        tmp_path / "baseline.prof",
    )
    assert (
        pstats.Stats(str(tmp_path / "baseline.prof")).get_stats_profile().func_profiles
    )
    assert result["total_calls"] > 0
    assert result["total_seconds"] > 0
    assert any(
        "statistics_python" in entry["function"] for entry in result["functions"]
    )
    assert 0 <= result["bottleneck"]["self_time_fraction"] <= 1
    assert result["memory"]["peak_bytes"] >= result["memory"]["current_bytes"] > 0
    assert result["memory"]["top_allocations"]
    assert "child processes" in result["memory"]["scope"]


def test_quick_cli_runs_same_real_spawn_pipeline_and_versioned_json(
    tmp_path: Path,
) -> None:
    import json
    import subprocess

    output = tmp_path / "results.json"
    command = [
        sys.executable,
        "-m",
        "lab9.experiments",
        "--quick",
        "--repeats",
        "2",
        "--python",
        sys.executable,
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["status"] == "complete"
    assert result["parameters"]["sizes"] == [24, 48, 96]
    assert result["parameters"]["repeats"] == 2
    assert result["runtime"]["spawn_executable"] == str(Path(sys.executable).resolve())
    assert (
        Path(result["runtime"]["probe"]["executable"]).resolve()
        == Path(sys.executable).resolve()
    )
    assert result["runtime"]["probe_command"][0] == str(Path(sys.executable).resolve())
    assert len(result["datasets"]) == 3
    for dataset in result["datasets"]:
        assert len(dataset["measurements"]) == 16
        assert len(dataset["search"]["raw_seconds"]) == 2
        assert dataset["search"]["parity"]
        for measurement in dataset["measurements"]:
            assert len(measurement["raw_seconds"]) == 2
            assert len(measurement["outputs"]) == 2
            assert measurement["speedup"] > 0
            assert measurement["profile"]["memory"]["peak_bytes"] > 0
            assert Path(measurement["profile"]["profile_path"]).is_file()
        assert {
            item["workers"]
            for item in dataset["measurements"]
            if item["method"] == "process"
        } == {1, 2, 4}
    assert "size=" in completed.stdout


def test_cli_rejects_missing_runtime_without_success_artifact(tmp_path: Path) -> None:
    import subprocess

    output = tmp_path / "absent.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "lab9.experiments",
            "--quick",
            "--python",
            str(tmp_path / "absent.exe"),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode != 0
    assert not output.exists()
