"""Streaming pipeline and iterator utilities for student management."""

import csv
import heapq
import itertools
import math
from collections.abc import Generator, Iterable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from student_manager.models import Student

T = TypeVar("T")

PRESCRIBED_HEADERS: tuple[str, ...] = (
    "student_id",
    "first_name",
    "last_name",
    "group",
    "average_grade",
)


@dataclass
class StreamStats:
    invalid_records: int = 0


def read_lines(path: str | Path) -> Generator[str, None, None]:
    # читаєм файл потоково з підтримкою bom через utf-8-sig
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        yield from file


def parse_csv_raw(lines: Iterable[str]) -> Iterator[list[str]]:
    # парсимо csv стандартним рідером шоб не ламати переноси у лапках
    reader = csv.reader(lines)
    yield from reader


def clean_rows(rows: Iterable[Sequence[str]]) -> Iterator[list[str]]:
    # зачищаєм пробіли та перевіряємо точний заголовок
    it = iter(rows)
    try:
        header_row = next(it)
    except StopIteration:
        raise ValueError("CSV is empty, missing header")

    cleaned_header = [field.strip() for field in header_row]
    if tuple(cleaned_header) != PRESCRIBED_HEADERS:
        raise ValueError(
            f"Invalid CSV header: expected {list(PRESCRIBED_HEADERS)}, got {cleaned_header}"
        )

    for row in it:
        yield [field.strip() for field in row]


def parse_students(
    rows: Iterable[Sequence[str]],
    *,
    stats: StreamStats | None = None,
    invalid_counter: list[int] | None = None,
) -> Generator[Student, None, None]:
    # валідуємо поля студента і рахуємо пропущені некоректні рядки
    for row in rows:
        if len(row) != 5:
            if stats is not None:
                stats.invalid_records += 1
            if invalid_counter is not None:
                invalid_counter[0] += 1
            continue

        id_str, first_name, last_name, group, grade_str = (
            row[0].strip(),
            row[1].strip(),
            row[2].strip(),
            row[3].strip(),
            row[4].strip(),
        )

        try:
            student_id = int(id_str)
            if student_id <= 0:
                raise ValueError("ID must be positive")
            if not first_name or not last_name or not group:
                raise ValueError("Text fields cannot be empty")
            grade = float(grade_str)
            if math.isnan(grade) or math.isinf(grade) or not (0 <= grade <= 100):
                raise ValueError("Grade out of range or nan/inf")
            student = Student(
                first_name=first_name,
                last_name=last_name,
                group=group,
                average_grade=grade,
                student_id=student_id,
            )
        except (ValueError, TypeError):
            if stats is not None:
                stats.invalid_records += 1
            if invalid_counter is not None:
                invalid_counter[0] += 1
            continue

        yield student


@contextmanager
def open_student_stream(
    path: str | Path, *, stats: StreamStats | None = None
) -> Iterator[Iterator[Student]]:
    # контекстний менеджер для коректного закриття файлу після стріму
    lines = read_lines(path)
    with closing(lines):
        gen = parse_students(clean_rows(parse_csv_raw(lines)), stats=stats)
        try:
            yield gen
        finally:
            gen.close()


class StudentIterator:
    def __init__(self, iterable: Iterable[Student]) -> None:
        # огортаєм ітероване джерело ліниво
        self._source = iter(iterable)
        self._exhausted = False

    def __iter__(self) -> "StudentIterator":
        return self

    def __next__(self) -> Student:
        if self._exhausted:
            raise StopIteration
        try:
            return next(self._source)
        except StopIteration:
            self._exhausted = True
            raise


def filter_by_group(students: Iterable[Student], group: str) -> Iterator[Student]:
    # фільтруємо за групою без урахування регістру та зайвих пробілів
    target = group.strip().casefold()
    for student in students:
        if student.group.strip().casefold() == target:
            yield student


def filter_by_min_grade(
    students: Iterable[Student], min_grade: float
) -> Iterator[Student]:
    # фільтруємо за мінімальним балом
    for student in students:
        if student.average_grade >= min_grade:
            yield student


def filter_students(
    students: Iterable[Student],
    *,
    group: str | None = None,
    min_grade: float | None = None,
) -> Iterator[Student]:
    # комбінована лінива фільтрація
    target_group = group.strip().casefold() if group is not None else None
    for student in students:
        if (
            target_group is not None
            and student.group.strip().casefold() != target_group
        ):
            continue
        if min_grade is not None and student.average_grade < min_grade:
            continue
        yield student


def find_student(
    students: Iterable[Student],
    *,
    student_id: int | None = None,
    surname: str | None = None,
) -> Student | None:
    # пошук з раннім виходом шоб не обробляти весь файл
    target_surname = surname.strip().casefold() if surname is not None else None
    for student in students:
        if student_id is not None and student.student_id == student_id:
            return student
        if (
            target_surname is not None
            and student.last_name.strip().casefold() == target_surname
        ):
            return student
    return None


def transform_to_summary(
    students: Iterable[Student],
) -> Iterator[tuple[int | None, str, str, float]]:
    # перетворюємо студентів у короткі кортежі
    for student in students:
        yield (
            student.student_id,
            student.full_name,
            student.group.strip(),
            student.average_grade,
        )


def calculate_statistics(students: Iterable[Student]) -> dict[str, Any]:
    # однопрохідний підрахунок статистики без списку в пам'яті
    count = 0
    total = 0.0
    min_grade: float | None = None
    max_grade: float | None = None
    group_counts: dict[str, int] = {}
    canonical_groups: dict[str, str] = {}

    for student in students:
        count += 1
        grade = student.average_grade
        total += grade
        if min_grade is None or grade < min_grade:
            min_grade = grade
        if max_grade is None or grade > max_grade:
            max_grade = grade
        grp = student.group.strip()
        key = grp.casefold()
        if key not in canonical_groups:
            canonical_groups[key] = grp
        display_grp = canonical_groups[key]
        group_counts[display_grp] = group_counts.get(display_grp, 0) + 1

    return {
        "count": count,
        "average": (total / count) if count > 0 else None,
        "min_grade": min_grade,
        "max_grade": max_grade,
        "group_counts": group_counts,
    }


def top_students(students: Iterable[Student], k: int) -> list[Student]:
    # знаходимо k найкращих за O(k) пам'яті через heapq
    if k < 0:
        raise ValueError("k must be non-negative")
    if k == 0:
        return []
    return heapq.nlargest(k, students, key=lambda s: s.average_grade)


def first_n_students(students: Iterable[Student], n: int) -> list[Student]:
    # перші n записів у порядку надходження через islice
    if n < 0:
        raise ValueError("n must be non-negative")
    return list(itertools.islice(students, n))


def batch_students(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    # генератор пакетів фіксованого розміру
    if size <= 0:
        raise ValueError("Batch size must be positive")
    source = iter(iterable)
    while True:
        batch = list(itertools.islice(source, size))
        if not batch:
            break
        yield batch


def flatten_batches(batches: Iterable[Iterable[T]]) -> Iterator[T]:
    # розгортаємо пакети через yield from
    for batch in batches:
        yield from batch


def chain_student_streams(*streams: Iterable[Student]) -> Iterator[Student]:
    # об'єднуємо потоки декількох файлів через itertools.chain
    yield from itertools.chain(*streams)


def grade_differences(students: Iterable[Student]) -> Iterator[float]:
    # обчислюємо різниці сусідніх оцінок генераторним виразом
    grades = (s.average_grade for s in students)
    return (round(curr - prev, 4) for prev, curr in itertools.pairwise(grades))


def infinite_counter_slice(
    start: int = 1, step: int = 1, count_limit: int = 10
) -> list[int]:
    # демонструємо скінченний зріз нескінченної послідовності count через islice
    return list(itertools.islice(itertools.count(start, step), count_limit))
