import argparse

from student_manager.models import Student
from student_manager.services import (
    add_student,
    calculate_group_average,
    filter_by_group,
    find_best_student,
)


def create_demo_students() -> list[Student]:
    return [
        Student("Олена", "Коваль", "ФеП-33", 91.5),
        Student("Іван", "Мельник", "ФеП-33", 84.0),
        Student("Ірина", "Бондар", "ФеП-32", 95.2),
        Student("Андрій", "Шевченко", "ФеП-33", 88.7),
    ]


def print_students(students: list[Student]) -> None:
    if not students:
        print("Студентів не знайдено.")
        return
    print(f"{'Ім’я та прізвище':<30} {'Група':<10} {'Середній бал':>12}")
    for student in students:
        print(
            f"{student.full_name:<30} {student.group:<10} "
            f"{student.average_grade:>12.2f}"
        )


def run_demo() -> None:
    students = create_demo_students()
    print_students(students)
    print("\nСтуденти групи ФеП-33:")
    print_students(filter_by_group(students, "ФеП-33"))
    average = calculate_group_average(students, "ФеП-33")
    if average is not None:
        print(f"\nСередній бал групи ФеП-33: {average:.2f}")
    best = find_best_student(students)
    if best is not None:
        print(f"Найкращий студент: {best.full_name} ({best.average_grade:.2f})")


def read_student(students: list[Student]) -> None:
    first_name = input("Ім'я: ")
    last_name = input("Прізвище: ")
    group = input("Група: ")
    try:
        grade = float(input("Середній бал (0-100): "))
        add_student(students, first_name, last_name, group, grade)
    except ValueError:
        print("Помилка: заповніть усі поля та введіть числовий бал від 0 до 100.")
        return
    print("Студента додано.")


def run_menu() -> None:
    students: list[Student] = []
    while True:
        print(
            "\n1. Додати студента\n2. Усі студенти\n3. Пошук за групою\n"
            "4. Найкращий студент\n5. Середній бал групи\n0. Вихід"
        )
        command = input("Команда: ").strip()
        if command == "0":
            return
        if command == "1":
            read_student(students)
        elif command == "2":
            print_students(students)
        elif command == "3":
            print_students(filter_by_group(students, input("Група: ")))
        elif command == "4":
            best = find_best_student(students)
            if best is None:
                print("Студентів не знайдено.")
            else:
                print(f"Найкращий студент: {best.full_name} ({best.average_grade:.2f})")
        elif command == "5":
            group = input("Група: ").strip()
            average = calculate_group_average(students, group)
            if average is None:
                print("Студентів не знайдено.")
            else:
                print(f"Середній бал групи {group}: {average:.2f}")
        else:
            print("Невідома команда.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Система обліку студентів")
    parser.add_argument("--demo", action="store_true", help="показати приклад роботи")
    parser.add_argument(
        "--lab2", action="store_true", help="показати аналітику колекцій"
    )
    parser.add_argument("--lab4", action="store_true", help="показати об'єктну модель")
    parser.add_argument("--lab3", metavar="CSV", help="потокова обробка CSV")
    parser.add_argument("--lab7", metavar="SQLITE", help="створити демонстраційну БД")
    parser.add_argument("--config", metavar="YAML", help="надійний імпорт та експорт")
    args = parser.parse_args()
    if args.lab2:
        from student_manager.demos import run_lab2

        run_lab2(create_demo_students())
    elif args.lab4:
        from student_manager.lab4_demo import run_demo as lab4_main

        lab4_main()
    elif args.lab3:
        from student_manager.lab3_demo import main as lab3_main

        raise SystemExit(lab3_main([args.lab3]))
    elif args.lab7:
        from student_manager.lab7_demo import main as lab7_main

        raise SystemExit(lab7_main(["--database", args.lab7]))
    elif args.config:
        from student_manager.lab5_demo import run_lab5_demo

        raise SystemExit(run_lab5_demo([args.config]))
    elif args.demo:
        run_demo()
    else:
        try:
            run_menu()
        except (EOFError, KeyboardInterrupt):
            print()


if __name__ == "__main__":
    main()
