import unittest

from student_manager.models import Student
from student_manager.registry import RecordingNotifier, StudentRegistry
from student_manager.repositories import InMemoryRepository


class RegistryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.registry = StudentRegistry(InMemoryRepository(), RecordingNotifier())
        self.registry.add(1, Student("Anna", "Koval", "A", 90))

    def test_bool_id_does_not_alias_student_one(self):
        with self.assertRaises((TypeError, ValueError)):
            self.registry.get_by_id(True)
        with self.assertRaises((TypeError, ValueError)):
            self.registry.edit(True, average_grade=0)
        self.assertEqual(self.registry[1].average_grade, 90)

    def test_export_preserves_grade_precision(self):
        from student_manager.registry import ReportingService

        self.registry.edit(1, average_grade=90.125)
        self.assertEqual(
            ReportingService(self.registry).export_students()[0]["average_grade"],
            90.125,
        )
