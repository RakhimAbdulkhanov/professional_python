import shutil
import sys
from pathlib import Path

import pytest

# додаєм корінь проекту для імпорту lab6
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab6.experiments import (
    assemble_experiment_record,
    extract_coverage_summary,
    run_experiment_3,
    run_experiment_6,
    run_subprocess_capture,
)


def test_run_subprocess_capture_basic():
    # перевірка базового запуску та структури результату
    cmd = [
        sys.executable,
        "-c",
        "import sys; print('test_stdout'); sys.stderr.write('test_stderr')",
    ]
    result = run_subprocess_capture(cmd)

    assert result["command"] == cmd
    assert result["returncode"] == 0
    assert "test_stdout" in result["stdout"]
    assert "test_stderr" in result["stderr"]


def test_extract_coverage_summary_valid():
    # витяг метрик покриття з json звіту coverage
    mock_cov_data = {
        "totals": {
            "num_statements": 10,
            "covered_lines": 8,
            "missing_lines": 2,
            "percent_covered": 80.0,
        }
    }
    summary = extract_coverage_summary(mock_cov_data)
    assert summary["num_statements"] == 10
    assert summary["covered_lines"] == 8
    assert summary["missing_lines"] == 2
    assert summary["percent_covered"] == pytest.approx(80.0)


def test_extract_coverage_summary_branch_counters_and_percentages():
    # перевірка витягу окремих показників statement, branch та combined покриття
    cov_data = {
        "totals": {
            "num_statements": 6,
            "covered_lines": 5,
            "missing_lines": 1,
            "percent_covered": 80.0,
            "percent_statements_covered": 83.33333333333333,
            "num_branches": 4,
            "covered_branches": 3,
            "missing_branches": 1,
            "percent_branches_covered": 75.0,
        }
    }
    summary = extract_coverage_summary(cov_data)
    assert summary["num_statements"] == 6
    assert summary["covered_lines"] == 5
    assert summary["missing_lines"] == 1
    assert summary["num_branches"] == 4
    assert summary["covered_branches"] == 3
    assert summary["missing_branches"] == 1
    assert summary["statement_percent"] == pytest.approx(83.333333)
    assert summary["branch_percent"] == pytest.approx(75.0)
    assert summary["combined_percent"] == pytest.approx(80.0)


def test_assemble_experiment_record_schema():
    # перевірка структури запису експерименту
    record = assemble_experiment_record(
        exp_id=1,
        title="Test Experiment",
        runs=[{"command": ["pytest"], "returncode": 0, "stdout": "ok", "stderr": ""}],
        metrics={"passed": 1},
        analysis={"conclusion": "execution != verification"},
    )
    assert record["id"] == 1
    assert record["title"] == "Test Experiment"
    assert len(record["runs"]) == 1
    assert record["runs"][0]["returncode"] == 0
    assert "passed" in record["metrics"]
    assert "conclusion" in record["analysis"]


def test_experiment_3_branch_coverage_calculation():
    # тестування запуску експерименту 3 в ізольованому каталозі
    test_sandbox = (
        PROJECT_ROOT
        / ".local_workflow"
        / "lab6"
        / "experiment_sandbox"
        / "test_unit_sb3"
    )
    test_sandbox.mkdir(parents=True, exist_ok=True)
    try:
        record = run_experiment_3(test_sandbox, sys.executable)
        assert record["id"] == 3
        part_summary = record["metrics"]["partial_coverage"]
        comp_summary = record["metrics"]["complete_coverage"]
        assert "num_branches" in part_summary
        assert "covered_branches" in part_summary
        assert "branch_percent" in part_summary
        assert "statement_percent" in part_summary
        assert "combined_percent" in part_summary
        assert part_summary["branch_percent"] == pytest.approx(75.0)
        assert part_summary["statement_percent"] == pytest.approx(83.333333)
        assert part_summary["combined_percent"] == pytest.approx(80.0)
        assert comp_summary["branch_percent"] == pytest.approx(100.0)
        assert record["metrics"]["branch_covered_difference"] == pytest.approx(25.0)
    finally:
        shutil.rmtree(test_sandbox, ignore_errors=True)


def test_experiment_6_tmp_path_isolation_actual_paths(tmp_path: Path):
    # перевірка коректного збору реальних ізольованих шляхів у експерименті 6
    test_sandbox = tmp_path / "exp6_test_sb"
    record = run_experiment_6(test_sandbox, sys.executable, PROJECT_ROOT)
    assert record["id"] == 6
    assert record["metrics"]["all_runs_passed"] is True
    assert record["metrics"]["iterations"] == 3
    paths = record["metrics"]["recorded_tmp_paths"]
    assert len(paths) == 3
    assert record["metrics"]["distinct_directories_count"] == 3
    assert len(set(paths)) == 3
    for p in paths:
        assert isinstance(p, str) and len(p.strip()) > 0
    assert record["metrics"]["repo_file_leaks"] == 0
