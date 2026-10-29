import importlib
import importlib.util
import unittest

from student_manager.models import Student


class AnalyticsTests(unittest.TestCase):
    def test_summary_keeps_duplicate_surnames_and_strict_threshold(self):
        self.assertIsNotNone(importlib.util.find_spec("student_manager.analytics"))
        analytics = importlib.import_module("student_manager.analytics")
        students = [
            Student("Anna", "Koval", "A", 90),
            Student("Oleh", "Koval", "B", 85),
            Student("Ira", "Bondar", "A", 95),
        ]
        summary = analytics.summarize(students)
        self.assertEqual(summary["groups"], {"A", "B"})
        self.assertEqual(summary["average"], 90)
        self.assertEqual(summary["counts"], {"A": 2, "B": 1})
        self.assertEqual(summary["ranking"], [students[2], students[0], students[1]])
        self.assertEqual(analytics.surname_index(students)["koval"], students[:2])
        self.assertEqual(analytics.above_grade(students, 90), [students[2]])
        self.assertIsNone(analytics.summarize([])["average"])

    def test_timing_decorator_preserves_result_and_metadata(self):
        self.assertIsNotNone(importlib.util.find_spec("student_manager.decorators"))
        module = importlib.import_module("student_manager.decorators")
        measurements = []

        @module.measure_time(measurements.append)
        def total(*values, scale=1):
            return sum(values) * scale

        self.assertEqual(total(2, 3, scale=2), 10)
        self.assertEqual(total.__name__, "total")
        self.assertEqual(len(measurements), 1)
        self.assertGreaterEqual(measurements[0], 0)

    def test_functional_extensions(self):
        analytics = importlib.import_module("student_manager.analytics")
        students = [Student("A", "Z", "A", 80), Student("B", "Y", "B", 90)]
        self.assertEqual(analytics.average_values(80, 90), 85)
        self.assertIsNone(analytics.average_values())
        self.assertEqual(analytics.create_record(group="A"), {"group": "A"})
        self.assertEqual(
            analytics.filter_students(students, lambda s: s.group == "B"), students[1:]
        )
        self.assertEqual(
            analytics.sort_students(students, lambda s: s.last_name, reverse=False),
            students[::-1],
        )
        with self.assertRaises(ValueError):
            analytics.grade_filter(float("nan"))


if __name__ == "__main__":
    unittest.main()
