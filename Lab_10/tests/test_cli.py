import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_app(
        self, *args: str, input_text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "student_manager.main", *args],
            check=False,
            input=input_text,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            cwd=ROOT,
            timeout=10,
        )

    def test_demo_lists_students_and_prints_group_statistics(self) -> None:
        result = self.run_app("--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Олена Коваль", result.stdout)
        self.assertIn("Ірина Бондар", result.stdout)
        self.assertIn("88.07", result.stdout)
        self.assertIn("95.20", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_menu_adds_a_student_from_keyboard(self) -> None:
        result = self.run_app(input_text="1\nТарас\nНовак\nФеП-33\n90\n2\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Студента додано.", result.stdout)
        self.assertIn("Тарас Новак", result.stdout)
        self.assertIn("90.00", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_menu_searches_group_and_displays_best_and_average(self) -> None:
        result = self.run_app(
            input_text="1\nТарас\nНовак\nФеП-33\n90\n"
            "1\nОлена\nКоваль\nФеП-32\n80\n3\nфеп-33\n4\n5\nФеП-33\n0\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Найкращий студент: Тарас Новак (90.00)", result.stdout)
        self.assertIn("Середній бал групи ФеП-33: 90.00", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_menu_recovers_from_bad_input_without_adding_invalid_students(self) -> None:
        result = self.run_app(
            input_text="9\n1\nТарас\nНовак\nФеП-33\nabc\n"
            "1\nТарас\nНовак\nФеП-33\n101\n2\n3\nФеП-99\n4\n5\nФеП-99\n0\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Невідома команда.", result.stdout)
        self.assertIn("Помилка:", result.stdout)
        self.assertIn("Студентів не знайдено.", result.stdout)
        self.assertNotIn("Студента додано.", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_menu_exits_cleanly_at_end_of_input(self) -> None:
        result = self.run_app()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_import_does_not_start_the_application(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import student_manager.main"],
            check=False,
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
