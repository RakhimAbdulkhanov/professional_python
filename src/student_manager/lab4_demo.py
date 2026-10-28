from student_manager.design_experiments import run_design_experiments
from student_manager.domain import AcademicRecord, Grade, Group
from student_manager.models import Student
from student_manager.registry import (
    ConsoleNotifier,
    RecordingNotifier,
    ReportingService,
    StudentRegistry,
)
from student_manager.repositories import InMemoryRepository


def run_demo() -> None:
    # 1. ініціалізація компонентів через dependency injection
    print("--- 1. Ініціалізація репозиторію та реєстру ---")
    repo = InMemoryRepository[Student]()
    console_notifier = ConsoleNotifier()
    registry = StudentRegistry(repository=repo, notifier=console_notifier)

    # 2. додавання студентів
    print("\n--- 2. Додавання студентів із числовими ID ---")
    s1 = Student("Олена", "Коваль", "ФеП-33", 91.5)
    s2 = Student("Іван", "Франко", "ФеП-33", 88.0)
    s3 = Student("Тарас", "Шевченко", "ФеП-34", 96.5)
    s4 = Student("Леся", "Українка", "ФеП-34", 94.0)

    registry.add(1, s1)
    registry.add(2, s2)
    registry.add(3, s3)
    registry.add(4, s4)

    # 3. редагування та атомарний захист
    print("\n--- 3. Редагування та атомарна валідація ---")
    updated = registry.edit(2, average_grade=89.5)
    print(
        f"Успішно оновлено студента 2: {updated.full_name}, новий бал: {updated.average_grade}"
    )

    # перевірка атомарності при некоректних даних
    try:
        registry.edit(2, average_grade=150.0)
    except ValueError as err:
        print(f"Спроба некоректного редагування відхилена: {err}")
    current_s2 = registry.get_by_id(2)
    print(
        f"Стан студента 2 після помилки: бал {current_s2.average_grade if current_s2 else 'None'} (не змінився)"
    )

    # 4. пошук за прізвищем та групою
    print("\n--- 4. Пошук за прізвищем та групою ---")
    kowals = registry.search_by_last_name("  коваль ")
    print(f"Знайдено за прізвищем 'коваль': {len(kowals)} студент(ів)")

    fep33_group = Group("ФеП-33")
    group_students = registry.search_by_group(fep33_group)
    print(f"Студенти групи {fep33_group}: {[s.full_name for s in group_students]}")

    # 5. середній бал та найкращий студент
    print("\n--- 5. Аналітика реєстру ---")
    avg_total = registry.get_average_grade()
    avg_fep33 = registry.get_average_grade(fep33_group)
    best_student = registry.find_best_student()
    best_fep33 = registry.find_best_student(fep33_group)

    print(
        f"Загальний середній бал: {avg_total:.2f}"
        if avg_total is not None
        else "Немає даних"
    )
    print(
        f"Середній бал групи ФеП-33: {avg_fep33:.2f}"
        if avg_fep33 is not None
        else "Немає даних"
    )
    print(
        f"Найкращий студент загалом: {best_student.full_name} ({best_student.average_grade})"
        if best_student
        else "Немає"
    )
    print(
        f"Найкращий студент ФеП-33: {best_fep33.full_name} ({best_fep33.average_grade})"
        if best_fep33
        else "Немає"
    )

    # 6. робота з Grade та AcademicRecord
    print("\n--- 6. Доменні об'єкти Grade та AcademicRecord ---")
    g1 = Grade(92.0)
    g2 = Grade(95.5)
    g3 = Grade(88.0)
    record = AcademicRecord(student_id=1, grades=(g1, g2))
    print(
        f"Академічна картка студента 1: оцінок {len(record)}, середній бал: {record.average:.2f}"
        if record.average
        else ""
    )

    record_extended = record.add_grade(g3)
    print(
        f"Після додавання оцінки {float(g3)}: оцінок {len(record_extended)}, середній: {record_extended.average:.2f}"
        if record_extended.average
        else ""
    )

    # 7. поліморфізм та заміна Notifier
    print("\n--- 7. Заміна сповіщувача через Dependency Injection ---")
    audit_recorder = RecordingNotifier()
    audit_registry = StudentRegistry(repository=repo, notifier=audit_recorder)
    audit_registry.edit(1, average_grade=93.0)
    print(f"Записано сповіщень аудиту: {len(audit_recorder.messages)}")
    for msg in audit_recorder.messages:
        print(f"  [audit log]: {msg}")

    # 8. колекційні dunder-методи реєстру
    print("\n--- 8. Колекційні dunder-методи реєстру ---")
    print(f"len(registry): {len(registry)}")
    print(f"1 in registry: {1 in registry}")
    print(f"99 in registry: {99 in registry}")
    print(f"registry[1]: {registry[1].full_name}")

    # 9. звітність через ReportingService та TypedDict
    print("\n--- 9. Генерація типізованих звітів (ReportingService) ---")
    reporter = ReportingService(registry)
    summary = reporter.get_summary()
    print("Підсумок реєстру (RegistrySummary):")
    for key, val in summary.items():
        print(f"  {key}: {val}")

    payloads = reporter.export_students()
    print(f"\nЕкспортовано записів TypedDict: {len(payloads)}")
    for p in payloads[:2]:
        print(f"  {p}")

    # 10. результати експериментів з дизайну
    print("\n--- 10. Порівняльні архітектурні експерименти ---")
    exp_results = run_design_experiments()
    print(
        f"Експеримент 1 (Hardcoded vs Injected Notifier) - вивід ідентичний: {exp_results['notifier_match']}"
    )
    print(f"  Зразок повідомлення: {exp_results['notifier_output']}")
    print(
        f"Експеримент 2 (Inheritance vs Composition) - вивід ідентичний: {exp_results['formatter_match']}"
    )
    print(f"  Зразок рядка: {exp_results['formatter_output']}")


if __name__ == "__main__":
    run_demo()
