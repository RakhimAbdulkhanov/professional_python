import importlib
import importlib.util
import unittest


class StudentTests(unittest.TestCase):
    def test_student_stores_the_required_fields(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("student_manager.models"))
        models = importlib.import_module("student_manager.models")
        student = models.Student("Олена", "Коваль", "ФеП-33", 91.5)
        self.assertEqual(student.first_name, "Олена")
        self.assertEqual(student.last_name, "Коваль")
        self.assertEqual(student.group, "ФеП-33")
        self.assertEqual(student.average_grade, 91.5)
        self.assertEqual(student.full_name, "Олена Коваль")

    def test_student_rejects_empty_fields_and_invalid_grades(self) -> None:
        from student_manager.models import Student

        invalid_fields = [
            (" ", "Коваль", "ФеП-33", 80.0),
            ("Олена", " ", "ФеП-33", 80.0),
            ("Олена", "Коваль", " ", 80.0),
            ("Олена", "Коваль", "ФеП-33", -1.0),
            ("Олена", "Коваль", "ФеП-33", 100.1),
            ("Олена", "Коваль", "ФеП-33", float("nan")),
            ("Олена", "Коваль", "ФеП-33", float("inf")),
        ]
        for fields in invalid_fields:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                Student(*fields)

    def test_student_strips_whitespace_and_accepts_grade_boundaries(self) -> None:
        from student_manager.models import Student

        for grade in (0.0, 100.0):
            with self.subTest(grade=grade):
                student = Student(" Олена ", " Коваль ", " ФеП-33 ", grade)
                self.assertEqual(student.full_name, "Олена Коваль")
                self.assertEqual(student.group, "ФеП-33")
