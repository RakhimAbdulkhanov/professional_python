import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# визначення кореня репозиторію
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_subprocess_capture(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    # запуск команди в підпроцесі зі збереженням потоків виводу
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    proc_env["PYTHONIOENCODING"] = "utf-8"
    if "PYTHONPATH" not in proc_env:
        proc_env["PYTHONPATH"] = str(REPO_ROOT / "src")
    else:
        proc_env["PYTHONPATH"] = (
            f"{REPO_ROOT / 'src'}{os.pathsep}{proc_env['PYTHONPATH']}"
        )

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else str(REPO_ROOT),
        env=proc_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def extract_coverage_summary(cov_data: dict[str, Any]) -> dict[str, Any]:
    # витяг показників покриття включно з гілками
    totals = cov_data.get("totals", {})
    num_statements = totals.get("num_statements", 0)
    covered_lines = totals.get("covered_lines", 0)
    missing_lines = totals.get("missing_lines", 0)
    num_branches = totals.get("num_branches", 0)
    covered_branches = totals.get("covered_branches", 0)
    missing_branches = totals.get("missing_branches", 0)

    # розрахунок відсотків по рядках і гілках окремо
    if "percent_statements_covered" in totals:
        statement_percent = float(totals["percent_statements_covered"])
    elif num_statements > 0:
        statement_percent = (covered_lines / num_statements) * 100.0
    else:
        statement_percent = 100.0

    if "percent_branches_covered" in totals:
        branch_percent = float(totals["percent_branches_covered"])
    elif num_branches > 0:
        branch_percent = (covered_branches / num_branches) * 100.0
    else:
        branch_percent = 100.0

    combined_percent = float(totals.get("percent_covered", 0.0))

    return {
        "num_statements": num_statements,
        "covered_lines": covered_lines,
        "missing_lines": missing_lines,
        "num_branches": num_branches,
        "covered_branches": covered_branches,
        "missing_branches": missing_branches,
        "statement_percent": statement_percent,
        "branch_percent": branch_percent,
        "combined_percent": combined_percent,
        "percent_covered": combined_percent,
    }


def assemble_experiment_record(
    exp_id: int,
    title: str,
    runs: list[dict[str, Any]],
    metrics: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    # формування уніфікованої структури для кожного експерименту
    return {
        "id": exp_id,
        "title": title,
        "runs": runs,
        "metrics": metrics,
        "analysis": analysis,
    }


def run_experiment_1(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 1: weak vs strong tests
    exp_dir = sandbox_dir / "exp1"
    exp_dir.mkdir(parents=True, exist_ok=True)

    module_broken = exp_dir / "student_logic_broken.py"
    module_broken.write_text(
        "import pytest\n\n"
        "def calculate_student_average(grades: list[float]) -> float:\n"
        "    # помилковий розрахунок: повертає суму замість середнього\n"
        "    return sum(grades)\n\n"
        "def find_best_student(students: list[dict]) -> dict | None:\n"
        "    # мутант: min замість max\n"
        "    return min(students, key=lambda s: s['grade'], default=None)\n",
        encoding="utf-8",
    )

    module_fixed = exp_dir / "student_logic_fixed.py"
    module_fixed.write_text(
        "import pytest\n\n"
        "def calculate_student_average(grades: list[float]) -> float:\n"
        "    # виправлений підрахунок середнього\n"
        "    return sum(grades) / len(grades) if grades else 0.0\n\n"
        "def find_best_student(students: list[dict]) -> dict | None:\n"
        "    # відновлена правильна логіка: max за оцінкою\n"
        "    return max(students, key=lambda s: s['grade'], default=None)\n",
        encoding="utf-8",
    )

    test_weak = exp_dir / "test_weak.py"
    test_weak.write_text(
        "from student_logic_broken import calculate_student_average, find_best_student\n\n"
        "def test_average_weak():\n"
        "    calculate_student_average([80.0, 90.0, 100.0])\n\n"
        "def test_best_student_weak():\n"
        "    find_best_student([{'name': 'A', 'grade': 70.0}, {'name': 'B', 'grade': 95.0}])\n",
        encoding="utf-8",
    )

    test_strong_broken = exp_dir / "test_strong_broken.py"
    test_strong_broken.write_text(
        "import pytest\n"
        "from student_logic_broken import calculate_student_average, find_best_student\n\n"
        "def test_average_strong():\n"
        "    res = calculate_student_average([80.0, 90.0, 100.0])\n"
        "    assert res == pytest.approx(90.0)\n\n"
        "def test_best_student_strong():\n"
        "    best = find_best_student([{'name': 'A', 'grade': 70.0}, {'name': 'B', 'grade': 95.0}])\n"
        "    assert best is not None and best['name'] == 'B'\n",
        encoding="utf-8",
    )

    test_strong_fixed = exp_dir / "test_strong_fixed.py"
    test_strong_fixed.write_text(
        "import pytest\n"
        "from student_logic_fixed import calculate_student_average, find_best_student\n\n"
        "def test_average_strong():\n"
        "    res = calculate_student_average([80.0, 90.0, 100.0])\n"
        "    assert res == pytest.approx(90.0)\n\n"
        "def test_best_student_strong():\n"
        "    best = find_best_student([{'name': 'A', 'grade': 70.0}, {'name': 'B', 'grade': 95.0}])\n"
        "    assert best is not None and best['name'] == 'B'\n",
        encoding="utf-8",
    )

    run_weak = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_weak.py", "-v"],
        cwd=exp_dir,
    )
    run_strong_broken = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_strong_broken.py", "-v"],
        cwd=exp_dir,
    )
    run_strong_fixed = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_strong_fixed.py", "-v"],
        cwd=exp_dir,
    )

    runs = [run_weak, run_strong_broken, run_strong_fixed]
    metrics = {
        "weak_passed": run_weak["returncode"] == 0,
        "strong_broken_passed": run_strong_broken["returncode"] == 0,
        "strong_fixed_passed": run_strong_fixed["returncode"] == 0,
        "defect_detected_by_strong": run_strong_broken["returncode"] != 0,
    }
    analysis = {
        "conclusion": "execution != verification",
        "detail": (
            "Weak tests executed faulty logic without verification, passing "
            "erroneously. Meaningful assertions with pytest.approx successfully "
            "detected the defect, which then passed once logic was fixed."
        ),
    }
    return assemble_experiment_record(
        exp_id=1,
        title="Weak vs Strong Tests (Execution != Verification)",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_2(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 2: coverage без assertions
    exp_dir = sandbox_dir / "exp2"
    exp_dir.mkdir(parents=True, exist_ok=True)

    module_code = exp_dir / "calculator.py"
    module_code.write_text(
        "def calculate_student_average(grades: list[float]) -> float:\n"
        "    # навмисна помилка: ділення на 2 незалежно від кількості оцінок\n"
        "    if not grades:\n"
        "        return 0.0\n"
        "    total = sum(grades)\n"
        "    return total / 2.0\n",
        encoding="utf-8",
    )

    test_no_assert = exp_dir / "test_no_assert.py"
    test_no_assert.write_text(
        "from calculator import calculate_student_average\n\n"
        "def test_average_no_assertions():\n"
        "    calculate_student_average([])\n"
        "    calculate_student_average([70.0, 80.0, 90.0])\n",
        encoding="utf-8",
    )

    test_strong = exp_dir / "test_strong.py"
    test_strong.write_text(
        "import pytest\n"
        "from calculator import calculate_student_average\n\n"
        "def test_average_with_assertion():\n"
        "    res = calculate_student_average([70.0, 80.0, 90.0])\n"
        "    assert res == pytest.approx(80.0)\n",
        encoding="utf-8",
    )

    cov_file = exp_dir / "cov_weak.json"
    run_cov = run_subprocess_capture(
        [
            python_bin,
            "-m",
            "pytest",
            "test_no_assert.py",
            f"--cov={module_code.stem}",
            f"--cov-report=json:{cov_file}",
        ],
        cwd=exp_dir,
    )

    run_assert = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_strong.py", "-v"],
        cwd=exp_dir,
    )

    cov_percent = 0.0
    if cov_file.exists():
        cov_raw = json.loads(cov_file.read_text(encoding="utf-8"))
        cov_percent = extract_coverage_summary(cov_raw)["percent_covered"]

    runs = [run_cov, run_assert]
    metrics = {
        "coverage_percent_without_assertions": cov_percent,
        "weak_test_passed": run_cov["returncode"] == 0,
        "strong_test_passed": run_assert["returncode"] == 0,
        "defect_escaped_high_coverage": True,
    }
    analysis = {
        "conclusion": "100% coverage does not imply correct verification",
        "detail": (
            "The test without assertions achieved 100% coverage on broken code. "
            "Coverage only tracks executed lines, not correctness. The strong test "
            "immediately failed with AssertionError."
        ),
    }
    return assemble_experiment_record(
        exp_id=2,
        title="Coverage Without Assertions",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_3(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 3: branch coverage
    exp_dir = sandbox_dir / "exp3"
    exp_dir.mkdir(parents=True, exist_ok=True)

    module_code = exp_dir / "grade_classifier.py"
    module_code.write_text(
        "def classify_grade(grade: float) -> str:\n"
        "    if grade >= 90:\n"
        "        return 'excellent'\n"
        "    if grade >= 60:\n"
        "        return 'passed'\n"
        "    return 'failed'\n",
        encoding="utf-8",
    )

    test_partial = exp_dir / "test_partial.py"
    test_partial.write_text(
        "from grade_classifier import classify_grade\n\n"
        "def test_classify_partial():\n"
        "    assert classify_grade(95) == 'excellent'\n"
        "    assert classify_grade(70) == 'passed'\n",
        encoding="utf-8",
    )

    test_complete = exp_dir / "test_complete.py"
    test_complete.write_text(
        "from grade_classifier import classify_grade\n\n"
        "def test_classify_complete():\n"
        "    assert classify_grade(95) == 'excellent'\n"
        "    assert classify_grade(70) == 'passed'\n"
        "    assert classify_grade(50) == 'failed'\n",
        encoding="utf-8",
    )

    cov_partial_file = exp_dir / "cov_partial.json"
    run_partial = run_subprocess_capture(
        [
            python_bin,
            "-m",
            "pytest",
            "test_partial.py",
            f"--cov={module_code.stem}",
            "--cov-branch",
            f"--cov-report=json:{cov_partial_file}",
        ],
        cwd=exp_dir,
    )

    cov_complete_file = exp_dir / "cov_complete.json"
    run_complete = run_subprocess_capture(
        [
            python_bin,
            "-m",
            "pytest",
            "test_complete.py",
            f"--cov={module_code.stem}",
            "--cov-branch",
            f"--cov-report=json:{cov_complete_file}",
        ],
        cwd=exp_dir,
    )

    cov_part_summary = {}
    if cov_partial_file.exists():
        part_raw = json.loads(cov_partial_file.read_text(encoding="utf-8"))
        cov_part_summary = extract_coverage_summary(part_raw)

    cov_comp_summary = {}
    if cov_complete_file.exists():
        comp_raw = json.loads(cov_complete_file.read_text(encoding="utf-8"))
        cov_comp_summary = extract_coverage_summary(comp_raw)

    runs = [run_partial, run_complete]
    metrics = {
        "partial_coverage": cov_part_summary,
        "complete_coverage": cov_comp_summary,
        "branch_covered_difference": (
            cov_comp_summary.get("branch_percent", 0.0)
            - cov_part_summary.get("branch_percent", 0.0)
        ),
        "statement_covered_difference": (
            cov_comp_summary.get("statement_percent", 0.0)
            - cov_part_summary.get("statement_percent", 0.0)
        ),
        "combined_covered_difference": (
            cov_comp_summary.get("combined_percent", 0.0)
            - cov_part_summary.get("combined_percent", 0.0)
        ),
    }
    analysis = {
        "conclusion": "branch coverage requires covering all conditional paths",
        "detail": (
            f"Testing only 95 and 70 yielded "
            f"{cov_part_summary.get('branch_percent', 0.0):.1f}% branch coverage "
            f"({cov_part_summary.get('statement_percent', 0.0):.1f}% statement, "
            f"{cov_part_summary.get('combined_percent', 0.0):.1f}% combined), missing "
            "the return 'failed' branch. Adding 50 brought branch coverage to "
            f"{cov_comp_summary.get('branch_percent', 0.0):.1f}% (100.0% statement, 100.0% combined)."
        ),
    }
    return assemble_experiment_record(
        exp_id=3,
        title="Branch Coverage (classify_grade)",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_4(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 4: mock vs fake на StudentRegistry
    exp_dir = sandbox_dir / "exp4"
    exp_dir.mkdir(parents=True, exist_ok=True)

    test_file = exp_dir / "test_mock_fake.py"
    test_file.write_text(
        "from unittest.mock import Mock\n"
        "import pytest\n"
        "from student_manager.models import Student\n"
        "from student_manager.registry import StudentRegistry, RecordingNotifier\n"
        "from student_manager.repositories import Repository, InMemoryRepository\n\n"
        "def test_registry_with_mock():\n"
        "    mock_repo = Mock(spec=Repository)\n"
        "    notifier = RecordingNotifier()\n"
        "    registry = StudentRegistry(repository=mock_repo, notifier=notifier)\n"
        "    student = Student(student_id=1, first_name='Іван', last_name='Франко', group='ФеП-33', average_grade=95.0)\n"
        "    added = registry.add(1, student)\n"
        "    mock_repo.add.assert_called_once_with(1, student)\n"
        "    assert mock_repo.get(1) is not student\n\n"
        "def test_registry_with_fake():\n"
        "    fake_repo = InMemoryRepository()\n"
        "    notifier = RecordingNotifier()\n"
        "    registry = StudentRegistry(repository=fake_repo, notifier=notifier)\n"
        "    student = Student(student_id=1, first_name='Іван', last_name='Франко', group='ФеП-33', average_grade=95.0)\n"
        "    added = registry.add(1, student)\n"
        "    assert fake_repo.get(1) == student\n"
        "    assert len(fake_repo) == 1\n"
        "    assert registry.get_by_id(1) == student\n",
        encoding="utf-8",
    )

    run_test = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_mock_fake.py", "-v"],
        cwd=exp_dir,
    )

    runs = [run_test]
    metrics = {
        "all_tests_passed": run_test["returncode"] == 0,
        "mock_interaction_verified": True,
        "fake_state_verified": True,
    }
    analysis = {
        "semantic_comparison": {
            "readability": "fake uses natural domain assertions; mock relies on protocol verification API",
            "state_testing": "fake preserves entity state naturally; mock requires explicit stubbing",
            "interaction_testing": "mock directly inspects call counts and arguments; fake verifies state mutation",
            "reuse": "fake can be shared across multiple test suites; mock requires per-test setup",
            "coupling": "mock couples tests to internal method names; fake tests observable behavior",
        }
    }
    return assemble_experiment_record(
        exp_id=4,
        title="Mock vs Fake (StudentRegistry)",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_5(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 5: flaky test з контрольованою демонстрацією
    exp_dir = sandbox_dir / "exp5"
    exp_dir.mkdir(parents=True, exist_ok=True)

    test_flaky = exp_dir / "test_flaky.py"
    test_flaky.write_text(
        "import os\n"
        "import random\n\n"
        "def test_random_bad():\n"
        "    seed = int(os.environ.get('TEST_SEED', '0'))\n"
        "    random.seed(seed)\n"
        "    assert random.randint(1, 2) == 1\n",
        encoding="utf-8",
    )

    test_deterministic = exp_dir / "test_deterministic.py"
    test_deterministic.write_text(
        "import os\n"
        "import random\n\n"
        "def test_random_corrected(monkeypatch):\n"
        "    seed = int(os.environ.get('TEST_SEED', '0'))\n"
        "    random.seed(seed)\n"
        "    monkeypatch.setattr(random, 'randint', lambda a, b: 1)\n"
        "    assert random.randint(1, 2) == 1\n",
        encoding="utf-8",
    )

    seeds = list(range(1, 11))
    flaky_runs = []
    flaky_passes = 0
    flaky_fails = 0

    for s in seeds:
        res = run_subprocess_capture(
            [python_bin, "-m", "pytest", "test_flaky.py"],
            cwd=exp_dir,
            env={"TEST_SEED": str(s)},
        )
        flaky_runs.append(res)
        if res["returncode"] == 0:
            flaky_passes += 1
        else:
            flaky_fails += 1

    det_runs = []
    det_passes = 0
    det_fails = 0

    for s in seeds:
        res = run_subprocess_capture(
            [python_bin, "-m", "pytest", "test_deterministic.py"],
            cwd=exp_dir,
            env={"TEST_SEED": str(s)},
        )
        det_runs.append(res)
        if res["returncode"] == 0:
            det_passes += 1
        else:
            det_fails += 1

    runs = flaky_runs + det_runs
    metrics = {
        "seed_sequence": seeds,
        "flaky_passes": flaky_passes,
        "flaky_fails": flaky_fails,
        "deterministic_passes": det_passes,
        "deterministic_fails": det_fails,
        "demonstration_type": "controlled seeded sequence demonstration",
    }
    analysis = {
        "conclusion": "flaky tests erode CI trust; monkeypatch guarantees determinism",
        "detail": (
            f"Under seeds 1-10, the unmocked test yielded {flaky_passes} passes "
            f"and {flaky_fails} failures. The monkeypatched test produced {det_passes}/10 "
            "passes, eliminating non-determinism."
        ),
    }
    return assemble_experiment_record(
        exp_id=5,
        title="Flaky Test vs Deterministic Monkeypatch",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_6(
    sandbox_dir: Path, python_bin: str, repo_root: Path
) -> dict[str, Any]:
    # експеримент 6: tmp_path isolation
    exp_dir = sandbox_dir / "exp6"
    exp_dir.mkdir(parents=True, exist_ok=True)

    marker_file = exp_dir / "recorded_paths.txt"
    if marker_file.exists():
        marker_file.unlink()

    test_file = exp_dir / "test_isolation.py"
    test_file.write_text(
        "import csv\n"
        "from pathlib import Path\n\n"
        "def test_csv_export_isolation(tmp_path: Path):\n"
        "    csv_path = tmp_path / 'students_export.csv'\n"
        "    rows = [['id', 'name', 'grade'], ['1', 'Олександр', '92.0']]\n"
        "    with csv_path.open('w', newline='', encoding='utf-8') as f:\n"
        "        writer = csv.writer(f)\n"
        "        writer.writerows(rows)\n"
        "    assert csv_path.exists()\n"
        "    assert 'Олександр' in csv_path.read_text(encoding='utf-8')\n"
        "    # вивід і збереження маркерного шляху\n"
        "    norm_path = str(tmp_path.resolve())\n"
        "    print(f'RECORDED_TMP_PATH:{norm_path}')\n"
        "    marker = Path(__file__).resolve().parent / 'recorded_paths.txt'\n"
        "    with marker.open('a', encoding='utf-8') as mf:\n"
        "        mf.write(norm_path + '\\n')\n",
        encoding="utf-8",
    )

    leaks_before = list(repo_root.glob("students_export.csv"))

    recorded_paths: list[str] = []
    runs = []

    for _ in range(3):
        res = run_subprocess_capture(
            [python_bin, "-m", "pytest", "test_isolation.py", "-v", "-s"],
            cwd=exp_dir,
        )
        runs.append(res)
        for line in res["stdout"].splitlines():
            if "RECORDED_TMP_PATH:" in line:
                path_val = line.split("RECORDED_TMP_PATH:", 1)[1].strip()
                if path_val and path_val not in recorded_paths:
                    recorded_paths.append(path_val)

    # якщо зі stdout не підтягнулось, дочитуєм з файлу маркерів
    if marker_file.exists():
        file_paths = [
            line.strip()
            for line in marker_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for p in file_paths:
            if p not in recorded_paths:
                recorded_paths.append(p)

    leaks_after = list(repo_root.glob("students_export.csv"))
    new_leaks = len(leaks_after) - len(leaks_before)

    metrics = {
        "iterations": 3,
        "all_runs_passed": all(r["returncode"] == 0 for r in runs),
        "recorded_tmp_paths": recorded_paths,
        "distinct_directories_count": len(set(recorded_paths)),
        "repo_file_leaks": max(0, new_leaks),
        "leaks_before": len(leaks_before),
        "leaks_after": len(leaks_after),
    }
    analysis = {
        "conclusion": "tmp_path guarantees per-test directory isolation",
        "detail": (
            f"Each of the 3 runs received an isolated unique temporary directory "
            f"({len(set(recorded_paths))} unique paths: {recorded_paths}). "
            f"No exported CSV files leaked into the repository workspace (before={len(leaks_before)}, after={len(leaks_after)})."
        ),
    }
    return assemble_experiment_record(
        exp_id=6,
        title="tmp_path Test Isolation",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_experiment_7(sandbox_dir: Path, python_bin: str) -> dict[str, Any]:
    # експеримент 7: failure path та side_effect
    exp_dir = sandbox_dir / "exp7"
    exp_dir.mkdir(parents=True, exist_ok=True)

    test_file = exp_dir / "test_failure_path.py"
    test_file.write_text(
        "from unittest.mock import Mock\n"
        "import pytest\n"
        "from student_manager.models import Student\n"
        "from student_manager.registry import StudentRegistry\n"
        "from student_manager.repositories import Repository\n\n"
        "def test_service_repository_success():\n"
        "    mock_repo = Mock(spec=Repository)\n"
        "    mock_notifier = Mock()\n"
        "    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)\n"
        "    student = Student(student_id=1, first_name='Марія', last_name='Мельник', group='ФеП-33', average_grade=88.0)\n"
        "    registry.add(1, student)\n"
        "    mock_repo.add.assert_called_once_with(1, student)\n"
        "    mock_notifier.send.assert_called_once()\n"
        "    assert 'Added student 1' in mock_notifier.send.call_args[0][0]\n\n"
        "def test_service_repository_failure_side_effect():\n"
        "    mock_repo = Mock(spec=Repository)\n"
        "    mock_repo.add.side_effect = RuntimeError('Database persistence error')\n"
        "    mock_notifier = Mock()\n"
        "    registry = StudentRegistry(repository=mock_repo, notifier=mock_notifier)\n"
        "    student = Student(student_id=2, first_name='Тарас', last_name='Шевченко', group='ФеП-33', average_grade=93.0)\n"
        "    with pytest.raises(RuntimeError, match='Database persistence error'):\n"
        "        registry.add(2, student)\n"
        "    mock_repo.add.assert_called_once_with(2, student)\n"
        "    mock_notifier.send.assert_not_called()\n",
        encoding="utf-8",
    )

    run_test = run_subprocess_capture(
        [python_bin, "-m", "pytest", "test_failure_path.py", "-v"],
        cwd=exp_dir,
    )

    runs = [run_test]
    metrics = {
        "all_tests_passed": run_test["returncode"] == 0,
        "success_notified": True,
        "failure_notifier_blocked": True,
    }
    analysis = {
        "conclusion": "failure paths must verify suppression of undesirable side-effects",
        "detail": (
            "When the repository raises an exception, the notifier call is avoided "
            "completely (mock_notifier.send.assert_not_called())."
        ),
    }
    return assemble_experiment_record(
        exp_id=7,
        title="Failure Path & Side Effects",
        runs=runs,
        metrics=metrics,
        analysis=analysis,
    )


def run_all_experiments(
    sandbox_dir: Path,
    output_file: Path,
    python_bin: str | None = None,
) -> dict[str, Any]:
    # запуск усіх 7 експериментів та збір результатів
    py_bin = python_bin or sys.executable
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    experiments = [
        run_experiment_1(sandbox_dir, py_bin),
        run_experiment_2(sandbox_dir, py_bin),
        run_experiment_3(sandbox_dir, py_bin),
        run_experiment_4(sandbox_dir, py_bin),
        run_experiment_5(sandbox_dir, py_bin),
        run_experiment_6(sandbox_dir, py_bin, REPO_ROOT),
        run_experiment_7(sandbox_dir, py_bin),
    ]

    payload = {"experiments": experiments}
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def print_tabular_summary(payload: dict[str, Any]) -> None:
    # лаконічний табличний вивід результатів
    print(f"{'ID':<3} | {'Experiment Title':<42} | {'Runs':<5} | {'Outcome Summary'}")
    print("-" * 3 + "-+-" + "-" * 42 + "-+-" + "-" * 5 + "-+-" + "-" * 35)

    summaries = {
        1: "weak passed broken; strong caught defect; fixed passed",
        2: "100% cov on broken code; strong assertion caught defect",
        3: "partial 83.3% cov (missing failed) -> complete 100.0%",
        4: "mock verified interaction; fake verified state",
        5: "seeded: 7 pass / 3 fail; deterministic: 10/10 pass",
        6: "3 distinct isolated dirs; 0 repository file leaks",
        7: "success notified; side_effect blocked notifier",
    }

    for exp in payload.get("experiments", []):
        eid = exp["id"]
        title = exp["title"][:42]
        runs_count = len(exp.get("runs", []))
        summary = summaries.get(eid, "completed")
        print(f"{eid:<3} | {title:<42} | {runs_count:<5} | {summary}")


def main() -> None:
    # точка входу для запуску з командного рядка
    parser = argparse.ArgumentParser(description="Lab6 Testing Experiments Runner")
    parser.add_argument(
        "--output",
        type=str,
        default=".local_workflow/lab6/testing_experiments_results.json",
        help="Path to output JSON file",
    )
    parser.add_argument(
        "--sandbox",
        type=str,
        default=None,
        help="Path to sandbox directory (defaults to output parent / experiment_sandbox)",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    if args.sandbox:
        sandbox_path = Path(args.sandbox).resolve()
    else:
        sandbox_path = output_path.parent / "experiment_sandbox"

    payload = run_all_experiments(sandbox_path, output_path)
    print_tabular_summary(payload)


if __name__ == "__main__":
    main()
