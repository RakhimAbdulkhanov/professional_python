from student_manager import analytics
from student_manager.decorators import measure_time
from student_manager.models import Student


def run_lab2(students: list[Student]) -> None:
    timings: list[float] = []
    summary = measure_time(timings.append)(analytics.summarize)(students)
    print("Унікальні групи:", sorted(analytics.unique_groups(students)))
    print("Середній бал:", summary["average"])
    print("Найкращий студент:", summary["best"])
    print("Кількість за групами:", summary["counts"])
    print("Групування:", summary["grouped"])
    print("Рейтинг:")
    for student in analytics.sort_students(students):
        print(student.full_name, student.group, student.average_grade)
    print("Бал строго вище 90:", analytics.above_grade(students, 90))
    print("Пошук Коваль:", analytics.surname_index(students).get("коваль", []))
    print("*args:", analytics.average_values(80, 90, 100))
    print("**kwargs:", analytics.create_record(group="ФеП-33", count=3))
    print("Час аналітики, с:", timings[0])
