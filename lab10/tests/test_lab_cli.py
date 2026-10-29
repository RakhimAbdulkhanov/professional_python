import os
import subprocess
import sys
import unittest


class LabCliTests(unittest.TestCase):
    def test_stream_mode_reads_csv(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "students.csv"
            path.write_text(
                "student_id,first_name,last_name,group,average_grade\n1,Anna,Koval,A,90\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "student_manager.main", "--lab3", str(path)],
                check=False,
                capture_output=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Anna", result.stdout)

    def test_config_mode_reports_missing_configuration(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "student_manager.main",
                "--config",
                "missing-config-fixture.yaml",
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Configuration file not found", result.stderr)

    def test_lab2_demo_shows_analytics(self):
        result = subprocess.run(
            [sys.executable, "-m", "student_manager.main", "--lab2"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Унікальні групи", result.stdout)
        self.assertIn("Рейтинг", result.stdout)
        self.assertIn("Коваль", result.stdout)

    def test_lab4_is_available_through_existing_entrypoint(self):
        result = subprocess.run(
            [sys.executable, "-m", "student_manager.main", "--lab4"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ReportingService", result.stdout)
