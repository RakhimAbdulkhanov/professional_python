import contextlib
import io
import runpy
import unittest
import warnings
from unittest.mock import patch

from student_manager import demos, lab4_demo
from student_manager.main import (
    create_demo_students,
    main,
    print_students,
    read_student,
    run_demo,
    run_menu,
)
from student_manager.models import Student


class DemosCoverageTests(unittest.TestCase):
    def test_run_lab2_outputs_all_analytics(self) -> None:
        # перевірка демонстрації аналітики для лабораторної 2
        students = create_demo_students()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            demos.run_lab2(students)
        output = buf.getvalue()

        self.assertIn("Унікальні групи: ['ФеП-32', 'ФеП-33']", output)
        self.assertIn("Середній бал: 89.85", output)
        self.assertIn("Найкращий студент: Student", output)
        self.assertIn(
            "Кількість за групами: Counter({'ФеП-33': 3, 'ФеП-32': 1})", output
        )
        self.assertIn("Рейтинг:", output)
        self.assertIn("Ірина Бондар ФеП-32 95.2", output)
        self.assertIn("Бал строго вище 90:", output)
        self.assertIn("Пошук Коваль:", output)
        self.assertIn("*args: 90.0", output)
        self.assertIn("**kwargs: {'group': 'ФеП-33', 'count': 3}", output)
        self.assertIn("Час аналітики, с:", output)

    def test_run_lab2_handles_empty_student_list(self) -> None:
        # виклик з пустим списком студентів
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            demos.run_lab2([])
        output = buf.getvalue()

        self.assertIn("Унікальні групи: []", output)
        self.assertIn("Середній бал: None", output)
        self.assertIn("Найкращий студент: None", output)


class Lab4DemoCoverageTests(unittest.TestCase):
    def test_run_demo_executes_successfully(self) -> None:
        # повний запуск демонстраційного сценарію лабораторної 4
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            lab4_demo.run_demo()
        output = buf.getvalue()

        self.assertIn("--- 1. Ініціалізація репозиторію та реєстру ---", output)
        self.assertIn("--- 2. Додавання студентів із числовими ID ---", output)
        self.assertIn("--- 3. Редагування та атомарна валідація ---", output)
        self.assertIn("--- 4. Пошук за прізвищем та групою ---", output)
        self.assertIn("--- 5. Аналітика реєстру ---", output)
        self.assertIn("--- 6. Доменні об'єкти Grade та AcademicRecord ---", output)
        self.assertIn(
            "--- 7. Заміна сповіщувача через Dependency Injection ---", output
        )
        self.assertIn("--- 8. Колекційні dunder-методи реєстру ---", output)
        self.assertIn(
            "--- 9. Генерація типізованих звітів (ReportingService) ---", output
        )
        self.assertIn("--- 10. Порівняльні архітектурні експерименти ---", output)
        self.assertIn(
            "Експеримент 1 (Hardcoded vs Injected Notifier) - вивід ідентичний: True",
            output,
        )
        self.assertIn(
            "Експеримент 2 (Inheritance vs Composition) - вивід ідентичний: True",
            output,
        )

    def test_lab4_demo_main_block(self) -> None:
        # перевірка точки входу модуля при запуску як __main__
        buf = io.StringIO()
        with (
            warnings.catch_warnings(),
            contextlib.redirect_stdout(buf),
        ):
            warnings.simplefilter("ignore")
            runpy.run_module("student_manager.lab4_demo", run_name="__main__")
        self.assertIn("--- 1. Ініціалізація репозиторію та реєстру ---", buf.getvalue())


class MainApplicationCoverageTests(unittest.TestCase):
    def test_create_demo_students(self) -> None:
        # перевірка створення базових демо-студентів
        students = create_demo_students()
        self.assertEqual(len(students), 4)
        self.assertEqual(students[0].full_name, "Олена Коваль")
        self.assertEqual(students[0].group, "ФеП-33")
        self.assertEqual(students[0].average_grade, 91.5)

    def test_print_students_when_empty(self) -> None:
        # вивід порожнього списку студентів
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_students([])
        self.assertEqual(buf.getvalue().strip(), "Студентів не знайдено.")

    def test_print_students_with_records(self) -> None:
        # вивід таблиці із записами студентів
        students = [Student("Тарас", "Шевченко", "ФеП-33", 95.0)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_students(students)
        output = buf.getvalue()
        self.assertIn("Ім’я та прізвище", output)
        self.assertIn("Тарас Шевченко", output)
        self.assertIn("95.00", output)

    def test_run_demo_outputs_expected_results(self) -> None:
        # базовий демо-режим cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_demo()
        output = buf.getvalue()
        self.assertIn("Студенти групи ФеП-33:", output)
        self.assertIn("Середній бал групи ФеП-33: 88.07", output)
        self.assertIn("Найкращий студент: Ірина Бондар (95.20)", output)

    def test_run_demo_with_empty_dataset(self) -> None:
        # виклик демо при відсутності записів у системі
        buf = io.StringIO()
        with (
            patch("student_manager.main.create_demo_students", return_value=[]),
            contextlib.redirect_stdout(buf),
        ):
            run_demo()
        self.assertIn("Студентів не знайдено.", buf.getvalue())

    def test_read_student_valid_entry(self) -> None:
        # успішне додавання студента через клавіатурне введення
        inputs = ["Микола", "Лисенко", "ФеП-31", "87.5"]
        students: list[Student] = []
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            contextlib.redirect_stdout(buf),
        ):
            read_student(students)

        self.assertEqual(len(students), 1)
        self.assertEqual(students[0].full_name, "Микола Лисенко")
        self.assertEqual(students[0].average_grade, 87.5)
        self.assertIn("Студента додано.", buf.getvalue())

    def test_read_student_invalid_non_numeric_grade(self) -> None:
        # відхилення нечислового значення балу
        inputs = ["Микола", "Лисенко", "ФеП-31", "не_число"]
        students: list[Student] = []
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            contextlib.redirect_stdout(buf),
        ):
            read_student(students)

        self.assertEqual(len(students), 0)
        self.assertIn(
            "Помилка: заповніть усі поля та введіть числовий бал від 0 до 100.",
            buf.getvalue(),
        )

    def test_read_student_invalid_out_of_range_grade(self) -> None:
        # відхилення балу за межами діапазону 0-100
        inputs = ["Микола", "Лисенко", "ФеП-31", "150.0"]
        students: list[Student] = []
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            contextlib.redirect_stdout(buf),
        ):
            read_student(students)

        self.assertEqual(len(students), 0)
        self.assertIn(
            "Помилка: заповніть усі поля та введіть числовий бал від 0 до 100.",
            buf.getvalue(),
        )

    def test_read_student_invalid_empty_field(self) -> None:
        # відхилення порожнього обов'язкового поля
        inputs = ["", "Лисенко", "ФеП-31", "90.0"]
        students: list[Student] = []
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            contextlib.redirect_stdout(buf),
        ):
            read_student(students)

        self.assertEqual(len(students), 0)
        self.assertIn(
            "Помилка: заповніть усі поля та введіть числовий бал від 0 до 100.",
            buf.getvalue(),
        )

    def test_run_menu_full_interactive_workflow(self) -> None:
        # сценарій інтерактивного меню з послідовним викликом усіх дій
        menu_inputs = [
            "1",
            "Олена",
            "Коваль",
            "ФеП-33",
            "95.0",
            "2",
            "3",
            "ФеП-33",
            "4",
            "5",
            "ФеП-33",
            "unknown_command",
            "0",
        ]
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=menu_inputs),
            contextlib.redirect_stdout(buf),
        ):
            run_menu()
        output = buf.getvalue()

        self.assertIn("Студента додано.", output)
        self.assertIn("Олена Коваль", output)
        self.assertIn("Найкращий студент: Олена Коваль (95.00)", output)
        self.assertIn("Середній бал групи ФеП-33: 95.00", output)
        self.assertIn("Невідома команда.", output)

    def test_run_menu_queries_on_empty_state(self) -> None:
        # запити до меню коли жодного студента ще не додано
        menu_inputs = ["4", "5", "ФеП-33", "0"]
        buf = io.StringIO()
        with (
            patch("builtins.input", side_effect=menu_inputs),
            contextlib.redirect_stdout(buf),
        ):
            run_menu()
        output = buf.getvalue()

        self.assertIn("Студентів не знайдено.", output)

    def test_main_cli_dispatch_lab2(self) -> None:
        # диспетчеризація прапорця --lab2
        with (
            patch("sys.argv", ["main.py", "--lab2"]),
            patch("student_manager.demos.run_lab2") as mock_run_lab2,
        ):
            main()
            mock_run_lab2.assert_called_once()

    def test_main_cli_dispatch_lab4(self) -> None:
        # диспетчеризація прапорця --lab4
        with (
            patch("sys.argv", ["main.py", "--lab4"]),
            patch("student_manager.lab4_demo.run_demo") as mock_run_lab4,
        ):
            main()
            mock_run_lab4.assert_called_once()

    def test_main_cli_dispatch_lab3(self) -> None:
        # диспетчеризація прапорця --lab3 із перевіркою SystemExit
        with (
            patch("sys.argv", ["main.py", "--lab3", "students.csv"]),
            patch("student_manager.lab3_demo.main", return_value=0) as mock_lab3,
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 0)
        mock_lab3.assert_called_once_with(["students.csv"])

    def test_main_cli_dispatch_config(self) -> None:
        # диспетчеризація прапорця --config із перевіркою SystemExit
        with (
            patch("sys.argv", ["main.py", "--config", "config.yaml"]),
            patch(
                "student_manager.lab5_demo.run_lab5_demo", return_value=0
            ) as mock_lab5,
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 0)
        mock_lab5.assert_called_once_with(["config.yaml"])

    def test_main_cli_dispatch_demo(self) -> None:
        # диспетчеризація прапорця --demo
        with (
            patch("sys.argv", ["main.py", "--demo"]),
            patch("student_manager.main.run_demo") as mock_demo,
        ):
            main()
            mock_demo.assert_called_once()

    def test_main_cli_default_exits_cleanly_on_zero(self) -> None:
        # запуск без аргументів із виходом з меню
        with (
            patch("sys.argv", ["main.py"]),
            patch("builtins.input", side_effect=["0"]),
        ):
            main()

    def test_main_cli_default_catches_eof_error(self) -> None:
        # коректна обробка переривання введення через eof
        buf = io.StringIO()
        with (
            patch("sys.argv", ["main.py"]),
            patch("builtins.input", side_effect=EOFError),
            contextlib.redirect_stdout(buf),
        ):
            main()
        self.assertIn("1. Додати студента", buf.getvalue())
        self.assertTrue(buf.getvalue().endswith("\n\n"))

    def test_main_cli_default_catches_keyboard_interrupt(self) -> None:
        # коректна обробка сигналу keyboard interrupt
        buf = io.StringIO()
        with (
            patch("sys.argv", ["main.py"]),
            patch("builtins.input", side_effect=KeyboardInterrupt),
            contextlib.redirect_stdout(buf),
        ):
            main()
        self.assertIn("1. Додати студента", buf.getvalue())
        self.assertTrue(buf.getvalue().endswith("\n\n"))

    def test_main_module_execution(self) -> None:
        # перевірка виконання main при прямому виклику модуля
        buf = io.StringIO()
        with (
            warnings.catch_warnings(),
            patch("sys.argv", ["main.py", "--demo"]),
            contextlib.redirect_stdout(buf),
        ):
            warnings.simplefilter("ignore")
            runpy.run_module("student_manager.main", run_name="__main__")
        self.assertIn("Ім’я та прізвище", buf.getvalue())
