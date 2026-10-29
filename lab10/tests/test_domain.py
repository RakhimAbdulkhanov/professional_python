import dataclasses
import math
import unittest


class GroupTests(unittest.TestCase):
    def test_group_creation_and_stripping(self) -> None:
        from student_manager.domain import Group

        group = Group("  ФеП-33  ")
        self.assertEqual(group.name, "ФеП-33")
        self.assertEqual(str(group), "ФеП-33")

    def test_group_rejects_empty_name(self) -> None:
        from student_manager.domain import Group

        for invalid in ("", "   ", "\t\n"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Group(invalid)

    def test_group_is_frozen(self) -> None:
        from student_manager.domain import Group

        group = Group("ФеП-33")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            group.name = "ФеП-34"  # type: ignore[misc]


class GradeTests(unittest.TestCase):
    def test_grade_valid_values(self) -> None:
        from student_manager.domain import Grade

        grade = Grade(95.5)
        self.assertEqual(float(grade), 95.5)
        self.assertEqual(str(grade), "95.5")

        boundary_low = Grade(0.0)
        self.assertEqual(float(boundary_low), 0.0)

        boundary_high = Grade(100.0)
        self.assertEqual(float(boundary_high), 100.0)

    def test_grade_rejects_out_of_bounds_and_non_finite(self) -> None:
        from student_manager.domain import Grade

        invalid_values = [
            -0.1,
            100.1,
            -50.0,
            150.0,
            float("nan"),
            float("inf"),
            float("-inf"),
            math.nan,
        ]
        for val in invalid_values:
            with self.subTest(val=val), self.assertRaises(ValueError):
                Grade(val)

    def test_grade_rejects_bool(self) -> None:
        from student_manager.domain import Grade

        with self.assertRaises((TypeError, ValueError)):
            Grade(True)  # type: ignore[arg-type]

    def test_grade_is_frozen(self) -> None:
        from student_manager.domain import Grade

        grade = Grade(85.0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            grade.value = 90.0  # type: ignore[misc]


class AcademicRecordTests(unittest.TestCase):
    def test_academic_record_empty_average_is_none(self) -> None:
        from student_manager.domain import AcademicRecord

        record = AcademicRecord(student_id=1)
        self.assertEqual(record.student_id, 1)
        self.assertEqual(record.grades, ())
        self.assertIsNone(record.average)
        self.assertEqual(len(record), 0)

    def test_academic_record_with_grades_calculates_average(self) -> None:
        from student_manager.domain import AcademicRecord, Grade

        record = AcademicRecord(
            student_id=1,
            grades=(Grade(90.0), Grade(80.0), Grade(100.0)),
        )
        self.assertEqual(len(record), 3)
        self.assertAlmostEqual(record.average, 90.0)
        self.assertEqual([float(g) for g in record], [90.0, 80.0, 100.0])

    def test_academic_record_add_grade_returns_new_record(self) -> None:
        from student_manager.domain import AcademicRecord, Grade

        record1 = AcademicRecord(student_id=1, grades=(Grade(90.0),))
        record2 = record1.add_grade(Grade(100.0))
        self.assertEqual(len(record1), 1)
        self.assertEqual(len(record2), 2)
        self.assertAlmostEqual(record2.average, 95.0)

    def test_academic_record_independent_defaults(self) -> None:
        from student_manager.domain import AcademicRecord, Grade

        r1 = AcademicRecord(student_id=1)
        r2 = AcademicRecord(student_id=2)
        r3 = r1.add_grade(Grade(75.0))
        self.assertEqual(r1.grades, ())
        self.assertEqual(r2.grades, ())
        self.assertEqual(len(r3.grades), 1)

    def test_academic_record_rejects_invalid_student_id(self) -> None:
        from student_manager.domain import AcademicRecord

        invalid_ids = [0, -1, -10, True, False, "1", 3.14]
        for sid in invalid_ids:
            with self.subTest(sid=sid), self.assertRaises((ValueError, TypeError)):
                AcademicRecord(student_id=sid)  # type: ignore[arg-type]

    def test_academic_record_is_frozen(self) -> None:
        from student_manager.domain import AcademicRecord, Grade

        record = AcademicRecord(student_id=1, grades=(Grade(90.0),))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.student_id = 2  # type: ignore[misc]


class PayloadTests(unittest.TestCase):
    def test_student_to_payload(self) -> None:
        from student_manager.domain import student_to_payload
        from student_manager.models import Student

        student = Student("Тарас", "Шевченко", "ФеП-33", 94.678)
        payload = student_to_payload(student, student_id=42)
        self.assertEqual(
            payload,
            {
                "student_id": 42,
                "first_name": "Тарас",
                "last_name": "Шевченко",
                "group": "ФеП-33",
                "average_grade": 94.678,
            },
        )


class DesignExperimentTests(unittest.TestCase):
    def test_experiment_1_same_behavior_internal_vs_injected_notifier(self) -> None:
        from student_manager.design_experiments import (
            HardcodedNotifierService,
            InjectedNotifierService,
        )
        from student_manager.registry import RecordingNotifier

        svc_internal = HardcodedNotifierService()
        audit_internal = svc_internal.register_student(1, "Олена Коваль")

        recorder = RecordingNotifier()
        svc_injected = InjectedNotifierService(recorder)
        audit_injected = svc_injected.register_student(1, "Олена Коваль")

        # identical output asserted
        self.assertEqual(audit_internal, audit_injected)
        self.assertEqual(recorder.messages, [audit_injected])

    def test_experiment_2_same_behavior_inheritance_vs_composition(self) -> None:
        from student_manager.design_experiments import (
            CompositeStudentCardProcessor,
            TemplateStudentCardFormatter,
            default_parse,
            default_render,
            default_validate,
        )

        raw = "10,Ірина,Бондар,ФеП-33,95.5"

        # inheritance
        inheritance_fmt = TemplateStudentCardFormatter()
        result_inheritance = inheritance_fmt.format_record(raw)

        # composition
        composite_proc = CompositeStudentCardProcessor(
            parser=default_parse,
            validator=default_validate,
            renderer=default_render,
        )
        result_composite = composite_proc.process(raw)

        # identical output asserted
        self.assertEqual(result_inheritance, result_composite)
        self.assertIn("Ірина Бондар", result_composite)
        self.assertIn("ФеП-33", result_composite)
        self.assertIn("95.5", result_composite)

    def test_design_experiments_runner(self) -> None:
        from student_manager.design_experiments import run_design_experiments

        results = run_design_experiments()
        self.assertTrue(results["notifier_match"])
        self.assertTrue(results["formatter_match"])
