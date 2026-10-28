"""Unit tests for Lab 3 streaming experiments."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from student_manager.streaming_experiments import (
    generate_synthetic_csv,
    measure_eager_pipeline,
    measure_early_termination,
    measure_lazy_pipeline,
    run_experiments,
)


class TestStreamingExperiments(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_synthetic_csv(self) -> None:
        csv_path = self.work_dir / "test_50.csv"
        generate_synthetic_csv(csv_path, count=50, seed=42)
        self.assertTrue(csv_path.exists())

        with csv_path.open("r", encoding="utf-8-sig") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertEqual(len(lines), 51)  # 1 header + 50 records
        self.assertEqual(
            lines[0],
            "student_id,first_name,last_name,group,average_grade",
        )

    def test_eager_vs_lazy_pipeline_results_match(self) -> None:
        csv_path = self.work_dir / "test_500.csv"
        generate_synthetic_csv(csv_path, count=500, seed=42)

        eager_res = measure_eager_pipeline(
            csv_path, target_group="ФеП-33", min_grade=70.0
        )
        lazy_res = measure_lazy_pipeline(
            csv_path, target_group="ФеП-33", min_grade=70.0
        )

        # результати агрегації мають бути ідентичними
        self.assertEqual(eager_res["stats"]["count"], lazy_res["stats"]["count"])
        self.assertAlmostEqual(
            eager_res["stats"]["average"], lazy_res["stats"]["average"], places=4
        )
        self.assertEqual(
            eager_res["stats"]["min_grade"], lazy_res["stats"]["min_grade"]
        )
        self.assertEqual(
            eager_res["stats"]["max_grade"], lazy_res["stats"]["max_grade"]
        )
        self.assertEqual(
            eager_res["stats"]["group_counts"], lazy_res["stats"]["group_counts"]
        )

        # пам'ять у lazy має бути суттєво меншою
        self.assertLess(lazy_res["peak_memory_bytes"], eager_res["peak_memory_bytes"])

    def test_early_termination_consumption(self) -> None:
        csv_path = self.work_dir / "test_early.csv"
        generate_synthetic_csv(csv_path, count=1000, seed=42)

        # шукаємо студента з student_id=25
        result = measure_early_termination(csv_path, target_student_id=25)
        self.assertEqual(result["lazy"]["records_consumed"], 25)
        self.assertEqual(result["eager"]["records_consumed"], 1000)
        self.assertLess(
            result["lazy"]["records_consumed"], result["eager"]["records_consumed"]
        )

    def test_run_experiments_cli_json_output(self) -> None:
        out_json = self.work_dir / "results.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = run_experiments(
                work_dir=self.work_dir,
                sizes=[50, 100],
                run_million=False,
                output_json=out_json,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(out_json.exists())

        data = json.loads(buf.getvalue())
        self.assertIn("experiments", data)
        self.assertEqual(len(data["experiments"]), 2)
        self.assertEqual(data["experiments"][0]["size"], 50)
        self.assertEqual(data["experiments"][1]["size"], 100)


if __name__ == "__main__":
    unittest.main()
