"""Unit tests for Lab 3 streaming pipeline and Student model extension."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from student_manager.lab3_demo import run_demo
from student_manager.models import Student
from student_manager.streaming import (
    StreamStats,
    StudentIterator,
    batch_students,
    calculate_statistics,
    chain_student_streams,
    clean_rows,
    filter_by_group,
    filter_by_min_grade,
    filter_students,
    find_student,
    first_n_students,
    flatten_batches,
    grade_differences,
    infinite_counter_slice,
    open_student_stream,
    parse_csv_raw,
    parse_students,
    read_lines,
    top_students,
    transform_to_summary,
)


class TestStudentModelExtension(unittest.TestCase):
    def test_student_positional_backward_compatibility(self) -> None:
        student = Student("Тарас", "Шевченко", "ФеП-33", 92.5)
        self.assertEqual(student.first_name, "Тарас")
        self.assertEqual(student.last_name, "Шевченко")
        self.assertEqual(student.group, "ФеП-33")
        self.assertEqual(student.average_grade, 92.5)
        self.assertIsNone(student.student_id)

    def test_student_with_valid_student_id(self) -> None:
        student = Student("Тарас", "Шевченко", "ФеП-33", 92.5, 42)
        self.assertEqual(student.student_id, 42)

        student_kw = Student(
            first_name="Іван",
            last_name="Франко",
            group="ФеП-33",
            average_grade=98.0,
            student_id=101,
        )
        self.assertEqual(student_kw.student_id, 101)

    def test_student_invalid_student_id(self) -> None:
        with self.assertRaises(ValueError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, 0)
        with self.assertRaises(ValueError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, -5)
        with self.assertRaises(TypeError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, True)
        with self.assertRaises(TypeError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, False)
        with self.assertRaises(TypeError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, "12")
        with self.assertRaises(TypeError):
            Student("Тарас", "Шевченко", "ФеП-33", 90.0, 12.5)


class TestStreamingReaderAndCleaner(unittest.TestCase):
    def test_read_lines_utf8_sig_and_resource_closure(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            path = Path(f.name)

        try:
            gen = read_lines(path)
            first = next(gen)
            self.assertEqual(first.strip(), "line1")
            # перевіряємо дострокове закриття
            gen.close()
            # файл на windows має видалятися без помилки доступу якщо закритий
            path.unlink()
        finally:
            if path.exists():
                path.unlink()

    def test_parse_csv_raw_handles_quoted_commas_and_newlines(self) -> None:
        csv_data = [
            "student_id,first_name,last_name,group,average_grade\n",
            '1,"Тарас, Молодший",Шевченко,ФеП-33,95.0\n',
            '2,Іван,"Франко\nПисьменник",ФеП-33,98.0\n',
        ]
        rows = list(parse_csv_raw(csv_data))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][1], "Тарас, Молодший")
        self.assertEqual(rows[2][2], "Франко\nПисьменник")

    def test_clean_rows_valid_header_and_strips_fields(self) -> None:
        raw_rows = [
            ["student_id", "first_name", "last_name", "group", "average_grade"],
            [" 1 ", " Тарас ", " Шевченко ", " ФеП-33 ", " 95.0 "],
        ]
        cleaned = list(clean_rows(raw_rows))
        self.assertEqual(cleaned, [["1", "Тарас", "Шевченко", "ФеП-33", "95.0"]])

    def test_clean_rows_invalid_header_raises_value_error(self) -> None:
        wrong_headers = [
            [],
            ["id", "name", "group", "grade"],
            ["student_id", "first_name", "last_name", "group"],
            ["student_id", "first_name", "last_name", "group", "wrong_grade"],
        ]
        for header in wrong_headers:
            with self.subTest(header=header), self.assertRaises(ValueError):
                list(clean_rows([header]))


class TestStudentParsingAndValidation(unittest.TestCase):
    def test_parse_students_valid_and_duplicate_surnames(self) -> None:
        rows = [
            ["1", "Тарас", "Шевченко", "ФеП-33", "95.5"],
            ["2", "Андрій", "Шевченко", "ФеП-31", "88.0"],
        ]
        stats = StreamStats()
        students = list(parse_students(rows, stats=stats))
        self.assertEqual(len(students), 2)
        self.assertEqual(stats.invalid_records, 0)
        self.assertEqual(students[0].last_name, "Шевченко")
        self.assertEqual(students[1].last_name, "Шевченко")
        self.assertEqual(students[0].student_id, 1)
        self.assertEqual(students[1].student_id, 2)

    def test_parse_students_skips_and_counts_invalid_records(self) -> None:
        # перевіряємо nan, inf, пусті тексти, непостійний id, missing/excess columns
        rows = [
            ["1", "Тарас", "Шевченко", "ФеП-33", "95.0"],  # valid
            ["2", "Іван", "Франко", "ФеП-33"],  # missing column (4 instead of 5)
            ["3", "Леся", "Українка", "ФеП-33", "90.0", "extra"],  # excess column (6)
            ["0", "Петро", "Котляревський", "ФеП-33", "80.0"],  # nonpositive id 0
            ["-5", "Ольга", "Кобилянська", "ФеП-33", "80.0"],  # negative id
            ["bad_id", "Василь", "Стус", "ФеП-33", "85.0"],  # non-int id
            ["7", "", "Тичина", "ФеП-33", "85.0"],  # empty first name
            ["8", "Павло", "", "ФеП-33", "85.0"],  # empty last name
            ["9", "Максим", "Рильський", "", "85.0"],  # empty group
            ["10", "Ліна", "Костенко", "ФеП-33", "NaN"],  # NaN grade
            ["11", "Григорій", "Сковорода", "ФеП-33", "inf"],  # inf grade
            ["12", "Микола", "Хвильовий", "ФеП-33", "-1.0"],  # grade < 0
            ["13", "Олександр", "Довженко", "ФеП-33", "101.0"],  # grade > 100
            ["14", "Олена", "Теліга", "ФеП-33", "bad_grade"],  # non-numeric grade
            ["15", "Юрій", "Андрухович", "ФеП-33", "91.0"],  # valid
        ]
        stats = StreamStats()
        students = list(parse_students(rows, stats=stats))
        self.assertEqual(len(students), 2)
        self.assertEqual(stats.invalid_records, 13)
        self.assertEqual([s.student_id for s in students], [1, 15])

    def test_parse_students_is_lazy(self) -> None:
        evaluated_indices = []

        def row_generator():
            for i in range(10):
                evaluated_indices.append(i)
                yield [str(i + 1), f"First{i}", f"Last{i}", "ФеП-33", "80.0"]

        stream = parse_students(row_generator())
        self.assertEqual(evaluated_indices, [])  # nothing evaluated yet
        first = next(stream)
        self.assertEqual(evaluated_indices, [0])
        self.assertEqual(first.student_id, 1)

    def test_open_student_stream_context_manager_early_closure(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", delete=False) as f:
            f.write("student_id,first_name,last_name,group,average_grade\n")
            f.write("1,Тарас,Шевченко,ФеП-33,95.0\n")
            f.write("2,Іван,Франко,ФеП-33,90.0\n")
            path = Path(f.name)

        try:
            with open_student_stream(path) as stream:
                first = next(stream)
                self.assertEqual(first.student_id, 1)
            # після виходу з with файл закритий і може бути видалений
            path.unlink()
        finally:
            if path.exists():
                path.unlink()

    def test_open_student_stream_closes_owned_read_lines_even_if_retained(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", delete=False) as f:
            f.write("student_id,first_name,last_name,group,average_grade\n")
            f.write("1,Тарас,Шевченко,ФеП-33,95.0\n")
            f.write("2,Іван,Франко,ФеП-33,90.0\n")
            path = Path(f.name)

        retained_stage = None
        try:
            with open_student_stream(path) as stream:
                first = next(stream)
                self.assertEqual(first.student_id, 1)
                # утримуємо посилання на проміжний генератор
                retained_stage = stream.gi_frame.f_locals.get("rows")

            # файл на Windows має видалятися без PermissionError завдяки closing(lines)
            self.assertIsNotNone(retained_stage)
            path.unlink()
        finally:
            if path.exists():
                path.unlink()


class TestFilteringSearchAnalyticsAndIterator(unittest.TestCase):
    def setUp(self) -> None:
        self.students = [
            Student("Тарас", "Шевченко", "ФеП-33", 95.0, 1),
            Student("Іван", "Франко", " феп-33 ", 88.5, 2),
            Student("Леся", "Українка", "ФеП-31", 91.0, 3),
            Student("Ольга", "Кобилянська", "ФеП-31", 72.0, 4),
        ]

    def test_filter_by_group_casefold_and_trim(self) -> None:
        filtered = list(filter_by_group(self.students, "  ФЕП-33  "))
        self.assertEqual(len(filtered), 2)
        self.assertEqual([s.student_id for s in filtered], [1, 2])

    def test_filter_by_min_grade(self) -> None:
        filtered = list(filter_by_min_grade(self.students, 90.0))
        self.assertEqual([s.student_id for s in filtered], [1, 3])

    def test_filter_students_combined(self) -> None:
        filtered = list(filter_students(self.students, group="ФеП-33", min_grade=90.0))
        self.assertEqual([s.student_id for s in filtered], [1])

    def test_find_student_early_termination(self) -> None:
        consumed = []

        def tracker():
            for s in self.students:
                consumed.append(s.student_id)
                yield s

        found = find_student(tracker(), student_id=2)
        self.assertIsNotNone(found)
        self.assertEqual(found.last_name, "Франко")
        # перевіряємо шо зупинилися на 2 і далі не читали
        self.assertEqual(consumed, [1, 2])

        consumed_by_name = []

        def name_tracker():
            for s in self.students:
                consumed_by_name.append(s.student_id)
                yield s

        found_by_name = find_student(name_tracker(), surname="шевченко")
        self.assertIsNotNone(found_by_name)
        self.assertEqual(found_by_name.student_id, 1)
        self.assertEqual(consumed_by_name, [1])

        # неіснуючий студент
        not_found = find_student(self.students, student_id=999)
        self.assertIsNone(not_found)

    def test_transform_to_summary(self) -> None:
        summaries = list(transform_to_summary(self.students[:2]))
        self.assertEqual(
            summaries,
            [
                (1, "Тарас Шевченко", "ФеП-33", 95.0),
                (2, "Іван Франко", "феп-33", 88.5),
            ],
        )

    def test_calculate_statistics_populated_and_empty(self) -> None:
        stats = calculate_statistics(self.students)
        self.assertEqual(stats["count"], 4)
        self.assertAlmostEqual(stats["average"], (95.0 + 88.5 + 91.0 + 72.0) / 4)
        self.assertEqual(stats["min_grade"], 72.0)
        self.assertEqual(stats["max_grade"], 95.0)
        self.assertEqual(stats["group_counts"], {"ФеП-33": 2, "ФеП-31": 2})

        empty_stats = calculate_statistics([])
        self.assertEqual(
            empty_stats,
            {
                "count": 0,
                "average": None,
                "min_grade": None,
                "max_grade": None,
                "group_counts": {},
            },
        )

    def test_student_iterator_protocol_and_exhaustion(self) -> None:
        iterator = StudentIterator(self.students[:2])
        self.assertIs(iter(iterator), iterator)
        first = next(iterator)
        self.assertEqual(first.student_id, 1)
        second = next(iterator)
        self.assertEqual(second.student_id, 2)

        # після вичерпання викликає StopIteration стабільно
        for _ in range(3):
            with self.assertRaises(StopIteration):
                next(iterator)


class TestTopStudentsBatchesAndItertools(unittest.TestCase):
    def setUp(self) -> None:
        self.students = [
            Student("Студент1", "Низький", "ФеП-33", 60.0, 1),
            Student("Студент2", "Середній", "ФеП-33", 75.0, 2),
            Student("Студент3", "Добре", "ФеП-33", 85.0, 3),
            Student("Студент4", "Відмінник", "ФеП-33", 99.0, 4),  # arrives last
        ]

    def test_top_students_and_distinction_from_first_n(self) -> None:
        # first_n бере перших двох у порядку надходження
        first_two = first_n_students(self.students, 2)
        self.assertEqual([s.student_id for s in first_two], [1, 2])

        # top_students знаходить двох найкращих (навіть якщо найкращий в кінці)
        best_two = top_students(self.students, 2)
        self.assertEqual([s.student_id for s in best_two], [4, 3])
        self.assertEqual([s.average_grade for s in best_two], [99.0, 85.0])

        # k=0 повертає пустий список
        self.assertEqual(top_students(self.students, 0), [])
        self.assertEqual(first_n_students(self.students, 0), [])

        # від'ємні k і n піднімають ValueError
        with self.assertRaises(ValueError):
            top_students(self.students, -1)
        with self.assertRaises(ValueError):
            first_n_students(self.students, -1)

    def test_batch_students_and_flatten_batches(self) -> None:
        # валідація розміру пакета
        with self.assertRaises(ValueError):
            list(batch_students(self.students, 0))
        with self.assertRaises(ValueError):
            list(batch_students(self.students, -2))

        # розбиття на батчі
        batches = list(batch_students(self.students, 2))
        self.assertEqual(len(batches), 2)
        self.assertEqual([s.student_id for s in batches[0]], [1, 2])
        self.assertEqual([s.student_id for s in batches[1]], [3, 4])

        # неповний останній батч
        batches_3 = list(batch_students(self.students, 3))
        self.assertEqual(len(batches_3), 2)
        self.assertEqual(len(batches_3[0]), 3)
        self.assertEqual(len(batches_3[1]), 1)

        # пустий потік
        self.assertEqual(list(batch_students([], 2)), [])

        # розгортання через yield from
        flattened = list(flatten_batches(batches_3))
        self.assertEqual([s.student_id for s in flattened], [1, 2, 3, 4])

    def test_itertools_chain_pairwise_and_infinite_count(self) -> None:
        stream1 = [Student("А", "Перший", "ФеП-33", 80.0, 1)]
        stream2 = [Student("Б", "Другий", "ФеП-33", 90.0, 2)]
        chained = list(chain_student_streams(stream1, stream2))
        self.assertEqual([s.student_id for s in chained], [1, 2])

        # pairwise різниці оцінок через генераторний вираз
        diffs = list(grade_differences(self.students))
        # [60.0, 75.0, 85.0, 99.0] -> [15.0, 10.0, 14.0]
        self.assertEqual(diffs, [15.0, 10.0, 14.0])

        # обмеження count через islice
        numbers = infinite_counter_slice(start=10, step=5, count_limit=4)
        self.assertEqual(numbers, [10, 15, 20, 25])


class TestLab3Demo(unittest.TestCase):
    def test_run_demo_executes_all_sections(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", delete=False) as f:
            f.write("student_id,first_name,last_name,group,average_grade\n")
            f.write("1,Тарас,Шевченко,ФеП-33,95.0\n")
            f.write("2,Іван,Франко,ФеП-33,88.0\n")
            f.write("3,Леся,Українка,ФеП-31,92.0\n")
            f.write("4,Ольга,Кобилянська,ФеП-31,75.0\n")
            f.write("5,Василь,Стус,ФеП-33,99.5\n")
            path = Path(f.name)

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = run_demo(path)
            self.assertEqual(exit_code, 0)
            output = buf.getvalue()
            # перевіряємо наявність ключових демонстрацій
            self.assertIn("Iterator exhaustion", output)
            self.assertIn("First matches", output)
            self.assertIn("Top-N", output)
            self.assertIn("Statistics", output)
            self.assertIn("Batches", output)
            self.assertIn("Chain", output)
            self.assertIn("Pairwise", output)
            self.assertIn("Infinite slice", output)
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
