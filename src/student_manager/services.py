from student_manager.models import Student


def add_student(
    students: list[Student],
    first_name: str,
    last_name: str,
    group: str,
    average_grade: float,
) -> Student:
    student = Student(first_name, last_name, group, average_grade)
    students.append(student)
    return student


def filter_by_group(students: list[Student], group: str) -> list[Student]:
    group = group.strip().casefold()
    return [student for student in students if student.group.casefold() == group]


def find_best_student(students: list[Student]) -> Student | None:
    return max(students, key=lambda student: student.average_grade, default=None)


def calculate_group_average(students: list[Student], group: str) -> float | None:
    members = filter_by_group(students, group)
    if not members:
        return None
    return sum(student.average_grade for student in members) / len(members)
