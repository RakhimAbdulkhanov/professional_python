from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from student_manager.models import Student
from student_manager.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from student_manager.persistence.service import (
    StudentPersistenceService,
)


def apply_migrations(db_path: Path | str) -> None:
    # програмне застосування міграцій alembic через ресурси пакета
    resolved_path = Path(db_path).resolve()
    db_url = f"sqlite:///{resolved_path.as_posix()}"
    cfg = Config()
    cfg.set_main_option("script_location", "student_manager.persistence:migrations")
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.attributes["target_url"] = db_url
    command.upgrade(cfg, "head")


def run_demo(
    database: str | Path,
    *,
    migrations: bool = True,
    refuse_existing: bool = True,
) -> dict[str, Any]:
    # запуск повного демонстраційного сценарію роботи з бд
    db_path = Path(database).resolve()
    if refuse_existing and db_path.exists():
        raise FileExistsError(
            f"Файл бази даних '{db_path}' вже існує. Перезапис заборонено."
        )

    # застосовуємо міграції alembic до чистої бд
    if migrations:
        apply_migrations(db_path)

    db_url = f"sqlite:///{db_path.as_posix()}"
    engine = create_database_engine(db_url)
    session_factory = create_session_factory(engine)
    service = StudentPersistenceService(session_factory=session_factory)

    try:
        # 1. створення груп
        grp_fep33 = service.create_group("ФеП-33")
        grp_fep34 = service.create_group("ФеП-34")

        # 2. додавання трьох фіктивних студентів
        s1 = service.create_student(
            Student("Тарас", "Шевченко", "ФеП-33", 94.5, student_id=1),
            group_id=grp_fep33.id,
            email="shevchenko@lnu.edu.ua",
        )
        s2 = service.create_student(
            Student("Леся", "Українка", "ФеП-33", 96.0, student_id=2),
            group_id=grp_fep33.id,
            email="ukrainka@lnu.edu.ua",
        )
        s3 = service.create_student(
            Student("Іван", "Франко", "ФеП-34", 91.0, student_id=3),
            group_id=grp_fep34.id,
            email="franko@lnu.edu.ua",
        )

        # 3. отримання за id та пагінований список
        fetched_s1 = service.get_student(s1.student_id or 1)
        all_students = service.list_students(offset=0, limit=100)

        # 4. пошук за прізвищем та фільтрація за групою
        by_surname = service.search_students_by_last_name("Шевченко")
        by_group = service.filter_students_by_group(grp_fep33.id)

        # 5. аналітика: найкращий студент та середній бал групи
        best_student = service.get_best_student()
        group_avg = service.get_group_average(grp_fep33.id)

        # 6. оновлення оцінки
        updated_s3 = service.update_student(s3.student_id or 3, average_grade=93.5)

        # 7. переведення студента
        transferred_count = service.transfer_students(
            [s3.student_id or 3], grp_fep33.id
        )

        # 8. демонстрація відкату транзакції при недійсному id
        s1_before = service.get_student(s1.student_id or 1)
        group_before_rollback = s1_before.group if s1_before else None
        rollback_success = False
        try:
            # передаємо валідний id разом із неіснуючим
            service.transfer_students([s1.student_id or 1, 9999], grp_fep34.id)
        except ValueError:
            rollback_success = True

        # перевіряємо свіжим читанням шо стан студента 1 не змінився
        s1_after = service.get_student(s1.student_id or 1)
        assert s1_after is not None
        assert s1_after.group == group_before_rollback

        # 9. видалення студента та підрахунок залишку
        deleted = service.delete_student(s3.student_id or 3)
        remaining_count = service.count_students()

        return {
            "database": str(database),
            "groups": [
                {"id": grp_fep33.id, "name": grp_fep33.name},
                {"id": grp_fep34.id, "name": grp_fep34.name},
            ],
            "students_created": [
                {
                    "student_id": s1.student_id,
                    "full_name": s1.full_name,
                    "group": s1.group,
                    "average_grade": s1.average_grade,
                },
                {
                    "student_id": s2.student_id,
                    "full_name": s2.full_name,
                    "group": s2.group,
                    "average_grade": s2.average_grade,
                },
                {
                    "student_id": s3.student_id,
                    "full_name": s3.full_name,
                    "group": s3.group,
                    "average_grade": s3.average_grade,
                },
            ],
            "student_fetched": {
                "student_id": fetched_s1.student_id if fetched_s1 else None,
                "full_name": fetched_s1.full_name if fetched_s1 else None,
                "group": fetched_s1.group if fetched_s1 else None,
            },
            "total_listed": len(all_students),
            "surname_search": [
                {"student_id": s.student_id, "full_name": s.full_name}
                for s in by_surname
            ],
            "group_filter": [
                {"student_id": s.student_id, "full_name": s.full_name} for s in by_group
            ],
            "best_student": {
                "full_name": best_student.full_name if best_student else None,
                "average_grade": best_student.average_grade if best_student else None,
            },
            "group_average": group_avg,
            "grade_updated": {
                "student_id": updated_s3.student_id if updated_s3 else None,
                "average_grade": updated_s3.average_grade if updated_s3 else None,
            },
            "transfer_success": transferred_count == 1,
            "rollback_demonstrated": rollback_success,
            "deleted": deleted,
            "remaining_count": remaining_count,
        }
    finally:
        # закриваємо пул з'єднань рушія
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    # точка входу командного рядка
    parser = argparse.ArgumentParser(
        description="Демонстрація persistence layer лабораторної роботи 7"
    )
    parser.add_argument(
        "--database",
        required=True,
        type=str,
        help="Шлях до нового файлу бази даних SQLite",
    )
    parser.add_argument(
        "--migrations",
        action="store_true",
        default=True,
        help="Застосувати міграції alembic перед виконанням",
    )

    args = parser.parse_args(argv)

    try:
        data = run_demo(
            database=args.database,
            migrations=args.migrations,
            refuse_existing=True,
        )

        # лаконічний вивід результатів українською мовою
        print(f"[Міграції] Застосовано alembic head для {data['database']}")
        print(
            f"[Групи] Створено: {data['groups'][0]['id']} ({data['groups'][0]['name']}), "
            f"{data['groups'][1]['id']} ({data['groups'][1]['name']})"
        )
        print("[Студенти] Додано:")
        for s in data["students_created"]:
            print(
                f"- {s['student_id']}: {s['full_name']}, група {s['group']}, "
                f"сер. бал: {s['average_grade']:.2f}"
            )
        print(
            f"[Отримання] Студент {data['student_fetched']['student_id']}: "
            f"{data['student_fetched']['full_name']} ({data['student_fetched']['group']})"
        )
        print(f"[Список] Всього студентів: {data['total_listed']}")
        print(
            f"[Пошук] За прізвищем 'Шевченко': {len(data['surname_search'])} запис(ів)"
        )
        print(f"[Фільтр] Студенти групи ФеП-33: {len(data['group_filter'])} запис(ів)")
        print(
            f"[Аналітика] Найкращий студент: {data['best_student']['full_name']} "
            f"({data['best_student']['average_grade']:.2f})"
        )
        if data["group_average"] is not None:
            print(f"[Аналітика] Середній бал групи ФеП-33: {data['group_average']:.2f}")
        print(
            f"[Оновлення] Студента {data['grade_updated']['student_id']} оновлено бал: "
            f"{data['grade_updated']['average_grade']:.2f}"
        )
        print(
            f"[Переведення] Переведення студента в нову групу: "
            f"{'успішно' if data['transfer_success'] else 'невдало'}"
        )
        print(
            "[Транзакція] Спроба масового переводу з недійсним ID (9999): помилку перехоплено"
        )
        print(
            f"[Атомарність] Стан студента не змінився після збою: "
            f"{'відкат підтверджено' if data['rollback_demonstrated'] else 'помилка'}"
        )
        print(
            f"[Видалення] Видалення студента: {data['deleted']}, "
            f"залишилось студентів: {data['remaining_count']}"
        )
        return 0
    except (RuntimeError, ValueError, TypeError, FileExistsError, OSError) as exc:
        sys.stderr.write(f"Помилка виконання: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
