from collections import Counter, defaultdict
from collections.abc import Callable, Sequence

from student_manager.models import Student


def unique_groups(students: Sequence[Student]) -> set[str]:
    return {student.group for student in students}


def average_values(*values: float) -> float | None:
    return sum(values) / len(values) if values else None


def create_record(**fields: object) -> dict[str, object]:
    return dict(fields)


def filter_students(
    students: Sequence[Student], predicate: Callable[[Student], bool]
) -> list[Student]:
    return [student for student in students if predicate(student)]


def grade_filter(threshold: float) -> Callable[[Student], bool]:
    if not 0 <= threshold <= 100:
        raise ValueError("Threshold must be between 0 and 100")

    def predicate(student: Student) -> bool:
        return student.average_grade > threshold

    return predicate


def above_grade(students: Sequence[Student], threshold: float) -> list[Student]:
    return filter_students(students, grade_filter(threshold))


def sort_students(
    students: Sequence[Student],
    key: Callable[[Student], float | str] = lambda student: student.average_grade,
    *,
    reverse: bool = True,
) -> list[Student]:
    return sorted(students, key=key, reverse=reverse)


def group_students(students: Sequence[Student]) -> dict[str, list[Student]]:
    groups: defaultdict[str, list[Student]] = defaultdict(list)
    for student in students:
        groups[student.group].append(student)
    return dict(groups)


def surname_index(students: Sequence[Student]) -> dict[str, list[Student]]:
    names: defaultdict[str, list[Student]] = defaultdict(list)
    for student in students:
        names[student.last_name.casefold()].append(student)
    return {name: members for name, members in names.items()}


def summarize(students: Sequence[Student]) -> dict[str, object]:
    return {
        "groups": unique_groups(students),
        "average": (
            sum(student.average_grade for student in students) / len(students)
            if students
            else None
        ),
        "best": max(students, key=lambda student: student.average_grade, default=None),
        "counts": Counter(student.group for student in students),
        "ranking": sort_students(students),
        "grouped": group_students(students),
    }
