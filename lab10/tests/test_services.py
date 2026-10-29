import importlib
import importlib.util
import unittest

from student_manager.models import Student


class ServiceTests(unittest.TestCase):
    def test_add_student_preserves_all_fields(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("student_manager.services"))
        services = importlib.import_module("student_manager.services")
        students: list[Student] = []
        student = services.add_student(students, "Олена", "Коваль", "ФеП-33", 91.5)
        self.assertEqual(students, [student])
        self.assertEqual(student.full_name, "Олена Коваль")

    def test_filter_by_group_handles_case_whitespace_and_missing_group(self) -> None:
        services = importlib.import_module("student_manager.services")
        self.assertTrue(hasattr(services, "filter_by_group"))
        students = [
            Student("Олена", "Коваль", "ФеП-33", 91.5),
            Student("Іван", "Мельник", "ФеП-32", 84.0),
        ]
        self.assertEqual(services.filter_by_group(students, " феп-33 "), students[:1])
        self.assertEqual(services.filter_by_group(students, "ФеП-99"), [])
        self.assertEqual(services.filter_by_group([], "ФеП-33"), [])

    def test_best_student_handles_empty_input_and_ties(self) -> None:
        services = importlib.import_module("student_manager.services")
        self.assertTrue(hasattr(services, "find_best_student"))
        students = [
            Student("Олена", "Коваль", "ФеП-33", 91.5),
            Student("Іван", "Мельник", "ФеП-32", 84.0),
            Student("Ірина", "Бондар", "ФеП-33", 91.5),
        ]
        self.assertIs(services.find_best_student(students), students[0])
        self.assertIsNone(services.find_best_student([]))

    def test_group_average_uses_only_the_requested_group(self) -> None:
        services = importlib.import_module("student_manager.services")
        self.assertTrue(hasattr(services, "calculate_group_average"))
        students = [
            Student("Олена", "Коваль", "ФеП-33", 90.0),
            Student("Іван", "Мельник", "ФеП-33", 80.0),
            Student("Ірина", "Бондар", "ФеП-32", 100.0),
        ]
        self.assertAlmostEqual(
            services.calculate_group_average(students, " феп-33 "), 85.0
        )
        self.assertIsNone(services.calculate_group_average(students, "ФеП-99"))
        self.assertIsNone(services.calculate_group_average([], "ФеП-33"))
