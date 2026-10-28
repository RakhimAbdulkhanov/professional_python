import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from student_manager.reliable_experiments import (
    generate_synthetic_dataset,
    main,
    run_all_experiments,
    run_atomic_rollback_experiment,
    run_config_errors_experiment,
    run_exception_chaining_experiment,
    run_streaming_vs_eager_experiment,
    run_strict_vs_tolerant_experiment,
)


class ReliableExperimentsSmallTests(unittest.TestCase):
    def test_generate_synthetic_dataset_deterministic_structure(self) -> None:
        # перевірка генерації датасету з детермінованими невалідними рядками
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "tiny_sample.csv"
            generate_synthetic_dataset(
                csv_path,
                valid_count=20,
                invalid_count=4,
                first_invalid_at=1,
            )
            self.assertTrue(csv_path.exists())
            lines = csv_path.read_text(encoding="utf-8").splitlines()

            # 1 заголовок + 24 рядки
            self.assertEqual(len(lines), 25)
            self.assertEqual(
                lines[0],
                "student_id,first_name,last_name,group,average_grade",
            )
            # перевірка наявності невалідного запису з оцінкою 150
            self.assertTrue(any("150.0" in line for line in lines))
            # перевірка наявності невалідного запису з від'ємним id
            self.assertTrue(any(line.startswith("-") for line in lines[1:]))
            # перевірка наявності невалідного запису з пустим ім'ям
            self.assertTrue(any(",," in line for line in lines))
            # перевірка наявності невалідного запису з нечисловою оцінкою
            self.assertTrue(any("wrong" in line for line in lines))

    def test_generate_synthetic_dataset_zero_invalid_rows(self) -> None:
        # генерація вибірки лише з валідними даними
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "only_valid.csv"
            generate_synthetic_dataset(csv_path, valid_count=8, invalid_count=0)
            lines = csv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 9)
            # жодного від'ємного id чи некоректної оцінки
            self.assertFalse(any(line.startswith("-") for line in lines[1:]))
            self.assertFalse(any("wrong" in line for line in lines))

    def test_run_strict_vs_tolerant_experiment(self) -> None:
        # порівняння строгого переривання та толерантного пропуску помилок
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            results = run_strict_vs_tolerant_experiment(work_dir)

            self.assertIn("strict", results)
            self.assertIn("tolerant", results)

            strict_data = results["strict"]
            self.assertTrue(strict_data["exit_status"].startswith("aborted:"))
            self.assertIn("RecordValidationError", strict_data["exit_status"])
            self.assertFalse(strict_data["file_committed"])
            self.assertEqual(strict_data["valid"], 104)
            self.assertEqual(strict_data["invalid"], 1)

            tolerant_data = results["tolerant"]
            self.assertEqual(tolerant_data["exit_status"], "success")
            self.assertTrue(tolerant_data["file_committed"])
            self.assertEqual(tolerant_data["valid"], 1000)
            self.assertEqual(tolerant_data["invalid"], 10)
            self.assertEqual(tolerant_data["exported"], 1000)
            self.assertEqual(tolerant_data["records_in_json"], 1000)

    def test_run_exception_chaining_experiment(self) -> None:
        # збереження першопричини помилки через ланцюжок винятків
        res = run_exception_chaining_experiment()
        self.assertTrue(res["has_chain"])
        self.assertIn("RecordValidationError", res["error"])
        self.assertIn("ValueError", res["cause"])
        self.assertIn("Traceback", res["traceback"])
        self.assertEqual(res["record"]["average_grade"], "wrong")

    def test_run_atomic_rollback_experiment(self) -> None:
        # атомарний захист цільового файлу при аварійній зупинці генератора
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            res = run_atomic_rollback_experiment(work_dir)

            self.assertEqual(res["exception_raised"], "RecordValidationError")
            self.assertTrue(res["content_preserved"])
            self.assertEqual(res["leftover_temporary_files"], [])

    def test_run_config_errors_experiment(self) -> None:
        # валідація конфігурацій та створення відсутніх каталогів
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            res = run_config_errors_experiment(work_dir)

            self.assertEqual(len(res), 6)
            cases = {item["case"]: item["status"] for item in res}

            self.assertEqual(cases["missing_config"], "rejected_as_expected")
            self.assertEqual(cases["malformed_yaml"], "rejected_as_expected")
            self.assertEqual(cases["missing_input_section"], "rejected_as_expected")
            self.assertEqual(cases["grade_out_of_range_150"], "rejected_as_expected")
            self.assertEqual(cases["missing_input_file"], "rejected_as_expected")
            self.assertEqual(
                cases["missing_output_dir"],
                "success_directory_created_True",
            )

    def test_run_streaming_vs_eager_experiment_small_sizes(self) -> None:
        # вимірювання eager проти streaming на компактних детермінованих вибірках
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            sizes = (20, 50)
            res = run_streaming_vs_eager_experiment(work_dir, sizes=sizes)

            self.assertEqual(len(res), 2)
            for row in res:
                self.assertEqual(
                    row["eager_filtered_count"],
                    row["stream_filtered_count"],
                )
                self.assertGreater(row["eager_peak_ram_bytes"], 0)
                self.assertGreater(row["streaming_peak_ram_bytes"], 0)
                self.assertGreaterEqual(row["ram_saving_factor"], 0.0)

            # перевірка що тимчасові csv файли бенчмарку видалені
            leftover_csv = list(work_dir.glob("bench_*.csv"))
            self.assertEqual(leftover_csv, [])

    def test_run_all_experiments_with_output_path(self) -> None:
        # виконання комплексу експериментів зі збереженням підсумкового json
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            out_file = work_dir / "all_summary.json"

            # використовуємо швидкий запуск streaming експерименту на маленьких розмірах
            with patch(
                "student_manager.reliable_experiments.run_streaming_vs_eager_experiment",
                side_effect=lambda wd: run_streaming_vs_eager_experiment(
                    wd, sizes=(10,)
                ),
            ):
                results = run_all_experiments(output_json_path=out_file)

            self.assertTrue(out_file.exists())
            self.assertEqual(results["variant"], 1)
            self.assertIn("experiment_1_strict_vs_tolerant", results)
            self.assertIn("experiment_2_streaming_vs_eager", results)
            self.assertIn("experiment_3_exception_chaining", results)
            self.assertIn("experiment_4_atomic_output", results)
            self.assertIn("experiment_5_configuration_errors", results)

            loaded = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(loaded["variant"], 1)

    def test_run_all_experiments_without_output_path(self) -> None:
        # запуск без запису у файл повертає коректний словник
        with patch(
            "student_manager.reliable_experiments.run_streaming_vs_eager_experiment",
            side_effect=lambda wd: run_streaming_vs_eager_experiment(wd, sizes=(10,)),
        ):
            results = run_all_experiments(output_json_path=None)

        self.assertEqual(results["variant"], 1)
        self.assertIn("experiment_1_strict_vs_tolerant", results)

    def test_reliable_experiments_main_prints_summary(self) -> None:
        # друк підсумків main без перезапису робочих звітів
        fake_results = {
            "variant": 1,
            "title": "Lab 5",
            "experiment_1_strict_vs_tolerant": {"status": "ok"},
            "experiment_2_streaming_vs_eager": [
                {
                    "dataset_records": 10,
                    "eager_time_sec": 0.01,
                    "eager_peak_ram_mb": 0.1,
                    "streaming_time_sec": 0.01,
                    "streaming_peak_ram_mb": 0.1,
                    "ram_saving_factor": 1.0,
                }
            ],
            "experiment_3_exception_chaining": {},
            "experiment_4_atomic_output": {"status": "ok"},
            "experiment_5_configuration_errors": [],
        }
        buf = io.StringIO()
        with (
            patch(
                "student_manager.reliable_experiments.run_all_experiments",
                return_value=fake_results,
            ) as mock_run_all,
            contextlib.redirect_stdout(buf),
        ):
            main()
            mock_run_all.assert_called_once()

        output = buf.getvalue()
        self.assertIn("Running Lab 5 experiments...", output)
        self.assertIn("=== Experiment 1: Strict vs Tolerant ===", output)
        self.assertIn("=== Experiment 2: Streaming vs Eager (RAM & Time) ===", output)
        self.assertIn("=== Experiment 4: Atomic output rollback ===", output)
