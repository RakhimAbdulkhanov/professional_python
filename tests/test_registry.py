import unittest


class RepositoryTests(unittest.TestCase):
    def test_repository_abc_cannot_be_instantiated(self) -> None:
        from student_manager.repositories import Repository

        with self.assertRaises(TypeError):
            Repository()  # type: ignore[abstract]

    def test_in_memory_repository_crud_flow(self) -> None:
        from student_manager.models import Student
        from student_manager.repositories import InMemoryRepository

        repo: InMemoryRepository[Student] = InMemoryRepository()
        student1 = Student("Олена", "Коваль", "ФеП-33", 90.0)
        repo.add(1, student1)

        self.assertEqual(repo.get(1), student1)
        self.assertIsNone(repo.get(999))
        self.assertEqual(repo.all(), (student1,))
        self.assertEqual(len(repo), 1)
        self.assertIn(1, repo)
        self.assertNotIn(2, repo)

        student1_updated = Student("Олена", "Коваль", "ФеП-33", 95.0)
        repo.update(1, student1_updated)
        self.assertEqual(repo.get(1), student1_updated)

    def test_in_memory_repository_rejects_duplicate_key(self) -> None:
        from student_manager.models import Student
        from student_manager.repositories import InMemoryRepository

        repo: InMemoryRepository[Student] = InMemoryRepository()
        s1 = Student("Олена", "Коваль", "ФеП-33", 90.0)
        s2 = Student("Іван", "Франко", "ФеП-33", 92.0)
        repo.add(1, s1)
        with self.assertRaises(ValueError):
            repo.add(1, s2)

    def test_in_memory_repository_update_missing_raises_key_error(self) -> None:
        from student_manager.models import Student
        from student_manager.repositories import InMemoryRepository

        repo: InMemoryRepository[Student] = InMemoryRepository()
        s1 = Student("Олена", "Коваль", "ФеП-33", 90.0)
        with self.assertRaises(KeyError):
            repo.update(404, s1)


class NotifierTests(unittest.TestCase):
    def test_notifiers_satisfy_runtime_checkable_protocol(self) -> None:
        from student_manager.registry import (
            ConsoleNotifier,
            Notifier,
            RecordingNotifier,
        )

        console = ConsoleNotifier()
        recorder = RecordingNotifier()

        self.assertIsInstance(console, Notifier)
        self.assertIsInstance(recorder, Notifier)

    def test_recording_notifier_records_messages(self) -> None:
        from student_manager.registry import RecordingNotifier

        recorder = RecordingNotifier()
        recorder.send("привіт")
        recorder.send("тест")
        self.assertEqual(recorder.messages, ["привіт", "тест"])


class StudentRegistryAddEditTests(unittest.TestCase):
    def test_registry_add_valid_student_notifies_and_stores(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        repo: InMemoryRepository[Student] = InMemoryRepository()
        notifier = RecordingNotifier()
        registry = StudentRegistry(repository=repo, notifier=notifier)

        student = Student("Олена", "Коваль", "ФеП-33", 92.5)
        added = registry.add(1, student)

        self.assertEqual(added.first_name, "Олена")
        self.assertEqual(getattr(added, "student_id", 1), 1)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("1", notifier.messages[0])
        self.assertEqual(registry.get_by_id(1), added)

    def test_registry_add_rejects_non_positive_or_bool_id(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        student = Student("Олена", "Коваль", "ФеП-33", 92.5)

        for invalid_id in (0, -1, -99, True, False, 1.5, "1"):
            with self.subTest(invalid_id=invalid_id), self.assertRaises(ValueError):
                registry.add(invalid_id, student)  # type: ignore[arg-type]

    def test_registry_add_rejects_duplicate_id(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        s1 = Student("Олена", "Коваль", "ФеП-33", 92.5)
        s2 = Student("Іван", "Франко", "ФеП-33", 85.0)

        registry.add(1, s1)
        with self.assertRaises(ValueError):
            registry.add(1, s2)

    def test_registry_add_rejects_inconsistent_student_id(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        s = Student("Олена", "Коваль", "ФеП-33", 92.5)
        s.student_id = 10  # type: ignore[attr-defined]

        with self.assertRaises(ValueError):
            registry.add(2, s)

    def test_registry_edit_successful_update(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        notifier = RecordingNotifier()
        registry = StudentRegistry(repository=InMemoryRepository(), notifier=notifier)
        registry.add(1, Student("Олена", "Коваль", "ФеП-33", 90.0))

        updated = registry.edit(1, group="ФеП-34", average_grade=98.0)
        self.assertEqual(updated.group, "ФеП-34")
        self.assertEqual(updated.average_grade, 98.0)
        self.assertEqual(updated.first_name, "Олена")
        self.assertEqual(len(notifier.messages), 2)

    def test_registry_edit_missing_student_raises_key_error(self) -> None:
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        with self.assertRaises(KeyError):
            registry.edit(404, group="ФеП-33")

    def test_registry_edit_atomic_failure_preserves_original_record(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        original = registry.add(1, Student("Олена", "Коваль", "ФеП-33", 90.0))

        with self.assertRaises(ValueError):
            registry.edit(1, average_grade=150.0)

        stored = registry.get_by_id(1)
        self.assertIsNotNone(stored)
        self.assertEqual(stored, original)
        self.assertEqual(stored.average_grade, 90.0)  # type: ignore[union-attr]
        self.assertEqual(stored.group, "ФеП-33")  # type: ignore[union-attr]


class StudentRegistryQueryAndDunderTests(unittest.TestCase):
    def setUp(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import RecordingNotifier, StudentRegistry
        from student_manager.repositories import InMemoryRepository

        self.registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        self.s1 = self.registry.add(1, Student("Олена", "Коваль", "ФеП-33", 90.0))
        self.s2 = self.registry.add(2, Student("Максим", "Коваль", "ФеП-34", 95.0))
        self.s3 = self.registry.add(3, Student("Ірина", "Бондар", "ФеП-33", 85.0))

    def test_search_by_last_name_casefold_and_trim(self) -> None:
        matches = self.registry.search_by_last_name("  коваль  ")
        self.assertEqual(matches, (self.s1, self.s2))

        no_match = self.registry.search_by_last_name("Шевченко")
        self.assertEqual(no_match, ())

    def test_search_by_group_string_and_group_object(self) -> None:
        from student_manager.domain import Group

        by_str = self.registry.search_by_group("  феп-33 ")
        self.assertEqual(by_str, (self.s1, self.s3))

        by_obj = self.registry.search_by_group(Group("ФеП-34"))
        self.assertEqual(by_obj, (self.s2,))

    def test_averages_and_best_student(self) -> None:
        from student_manager.domain import Group

        # overall average: (90 + 95 + 85) / 3 = 90.0
        self.assertAlmostEqual(self.registry.get_average_grade(), 90.0)  # type: ignore[arg-type]
        # group average
        self.assertAlmostEqual(self.registry.get_average_grade("ФеП-33"), 87.5)  # type: ignore[arg-type]
        self.assertAlmostEqual(self.registry.get_average_grade(Group("ФеП-34")), 95.0)  # type: ignore[arg-type]
        # empty group returns None
        self.assertIsNone(self.registry.get_average_grade("Невідома"))

        # best student overall
        self.assertEqual(self.registry.find_best_student(), self.s2)
        # best student in group
        self.assertEqual(self.registry.find_best_student("ФеП-33"), self.s1)
        self.assertIsNone(self.registry.find_best_student("Порожня"))

    def test_collection_dunders(self) -> None:
        # __len__
        self.assertEqual(len(self.registry), 3)

        # __iter__
        students = list(self.registry)
        self.assertEqual(students, [self.s1, self.s2, self.s3])

        # __contains__ with int id
        self.assertIn(1, self.registry)
        self.assertNotIn(99, self.registry)
        self.assertNotIn(True, self.registry)

        # __contains__ with Student instance
        self.assertIn(self.s1, self.registry)
        from student_manager.models import Student

        other = Student("Чужий", "Студент", "ФеП-33", 60.0)
        self.assertNotIn(other, self.registry)

        # __getitem__
        self.assertEqual(self.registry[1], self.s1)
        with self.assertRaises(KeyError):
            _ = self.registry[404]


class ReportingServiceTests(unittest.TestCase):
    def test_reporting_service_export_and_summary(self) -> None:
        from student_manager.models import Student
        from student_manager.registry import (
            RecordingNotifier,
            ReportingService,
            StudentRegistry,
        )
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        registry.add(10, Student("Олена", "Коваль", "ФеП-33", 92.456))
        registry.add(20, Student("Ігор", "Шевченко", "ФеП-34", 88.0))

        reporter = ReportingService(registry)
        payloads = reporter.export_students()

        self.assertEqual(len(payloads), 2)
        self.assertEqual(
            payloads[0],
            {
                "student_id": 10,
                "first_name": "Олена",
                "last_name": "Коваль",
                "group": "ФеП-33",
                "average_grade": 92.456,
            },
        )
        self.assertEqual(
            payloads[1],
            {
                "student_id": 20,
                "first_name": "Ігор",
                "last_name": "Шевченко",
                "group": "ФеП-34",
                "average_grade": 88.0,
            },
        )

        summary = reporter.get_summary()
        self.assertEqual(summary["total_students"], 2)
        self.assertAlmostEqual(summary["overall_average"], 90.23)  # type: ignore[arg-type]
        self.assertEqual(summary["best_student_id"], 10)
        self.assertEqual(summary["best_student_name"], "Олена Коваль")

    def test_reporting_service_empty_registry_summary(self) -> None:
        from student_manager.registry import (
            RecordingNotifier,
            ReportingService,
            StudentRegistry,
        )
        from student_manager.repositories import InMemoryRepository

        registry = StudentRegistry(
            repository=InMemoryRepository(), notifier=RecordingNotifier()
        )
        reporter = ReportingService(registry)

        summary = reporter.get_summary()
        self.assertEqual(summary["total_students"], 0)
        self.assertIsNone(summary["overall_average"])
        self.assertIsNone(summary["best_student_id"])
        self.assertIsNone(summary["best_student_name"])
