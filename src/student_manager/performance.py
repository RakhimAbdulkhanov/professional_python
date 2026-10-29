"""Comparable statistics over detached Student snapshots.

Group keys use strip/casefold; tied grades retain input order. Population
standard deviation uses ddof=0. Public results contain no mutable entities.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, replace
from multiprocessing import get_context
from threading import Lock

from student_manager.models import Student


@dataclass(frozen=True, slots=True)
class StudentSnapshot:
    student_id: int
    first_name: str
    last_name: str
    group: str
    average_grade: float


@dataclass(frozen=True, slots=True)
class Statistics:
    count: int
    average: float | None
    minimum: float | None
    maximum: float | None
    population_stddev: float | None
    group_averages: tuple[tuple[str, float], ...]
    student_ids: tuple[int, ...]
    ranking_ids: tuple[int, ...]


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Text fields must be strings")
    if not value.strip():
        raise ValueError("Text fields cannot be empty")
    return value.strip()


def _grade(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Grade must be numeric, not bool")
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Grade must be finite and between 0 and 100")
    return float(value)


def _student_id(value: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Student ID must be an integer")
    if value <= 0:
        raise ValueError("Student ID must be positive")
    return value


def snapshot(
    students: Iterable[Student | StudentSnapshot],
) -> tuple[StudentSnapshot, ...]:
    """Detach and validate inputs; IDs are mandatory and unique within a dataset."""
    rows: list[StudentSnapshot] = []
    seen: set[int] = set()
    for student in students:
        if not isinstance(student, (Student, StudentSnapshot)):
            raise TypeError("Expected Student or StudentSnapshot")
        identifier = _student_id(student.student_id)
        if identifier in seen:
            raise ValueError(f"Duplicate student ID: {identifier}")
        seen.add(identifier)
        rows.append(
            StudentSnapshot(
                identifier,
                _text(student.first_name),
                _text(student.last_name),
                _text(student.group).casefold(),
                _grade(student.average_grade),
            )
        )
    return tuple(rows)


def search_group(
    students: Iterable[Student | StudentSnapshot], group: str
) -> tuple[StudentSnapshot, ...]:
    """Return detached matches in input order with the same group normalization."""
    key = _text(group).casefold()
    return tuple(row for row in snapshot(students) if row.group == key)


def _summarize(rows: tuple[StudentSnapshot, ...]) -> Statistics:
    if not rows:
        return Statistics(0, None, None, None, None, (), (), ())
    count = 0
    total = 0.0
    minimum = math.inf
    maximum = -math.inf
    groups: dict[str, tuple[int, float]] = {}
    for row in rows:
        value = row.average_grade
        count += 1
        total += value
        minimum = min(minimum, value)
        maximum = max(maximum, value)
        size, subtotal = groups.get(row.group, (0, 0.0))
        groups[row.group] = size + 1, subtotal + value
    average = total / count
    squared = 0.0
    for row in rows:
        squared += (row.average_grade - average) ** 2
    return Statistics(
        count,
        average,
        minimum,
        maximum,
        math.sqrt(squared / count),
        tuple((key, subtotal / size) for key, (size, subtotal) in groups.items()),
        tuple(row.student_id for row in rows),
        tuple(
            row.student_id for row in sorted(rows, key=lambda row: -row.average_grade)
        ),
    )


def _select(
    students: Iterable[Student | StudentSnapshot], group: str | None
) -> tuple[StudentSnapshot, ...]:
    rows = snapshot(students)
    if group is None:
        return rows
    key = _text(group).casefold()
    return tuple(row for row in rows if row.group == key)


def statistics_python(
    students: Iterable[Student | StudentSnapshot], *, group: str | None = None
) -> Statistics:
    """Explicit-loop baseline, including snapshot conversion and global ranking."""
    return _summarize(_select(students, group))


def statistics_numpy(
    students: Iterable[Student | StudentSnapshot], *, group: str | None = None
) -> Statistics:
    """Vectorized moments, group reductions and stable ranking, conversion included."""
    import numpy as np

    rows = _select(students, group)
    if not rows:
        return _summarize(rows)
    grades = np.asarray([row.average_grade for row in rows], dtype=np.float64)
    group_names = tuple(dict.fromkeys(row.group for row in rows))
    codes_by_name = {name: code for code, name in enumerate(group_names)}
    codes = np.asarray([codes_by_name[row.group] for row in rows], dtype=np.intp)
    counts = np.bincount(codes)
    totals = np.bincount(codes, weights=grades)
    return Statistics(
        len(rows),
        float(grades.mean()),
        float(np.min(grades)),
        float(np.max(grades)),
        float(grades.std(ddof=0)),
        tuple(
            (name, float(totals[code] / counts[code]))
            for code, name in enumerate(group_names)
        ),
        tuple(row.student_id for row in rows),
        tuple(
            rows[int(index)].student_id for index in np.argsort(-grades, kind="stable")
        ),
    )


@dataclass(frozen=True, slots=True)
class _Moments:
    count: int
    average: float
    m2: float
    minimum: float
    maximum: float
    groups: tuple[tuple[str, int, float], ...]


def _partial_moments(rows: tuple[StudentSnapshot, ...]) -> _Moments:
    # центровані моменти не гублять малу дисперсію біля великих оцінок
    total = 0.0
    groups: dict[str, tuple[int, float]] = {}
    minimum = math.inf
    maximum = -math.inf
    for row in rows:
        total += row.average_grade
        minimum = min(minimum, row.average_grade)
        maximum = max(maximum, row.average_grade)
        size, subtotal = groups.get(row.group, (0, 0.0))
        groups[row.group] = size + 1, subtotal + row.average_grade
    average = total / len(rows)
    m2 = 0.0
    for row in rows:
        m2 += (row.average_grade - average) ** 2
    return _Moments(
        len(rows),
        average,
        m2,
        minimum,
        maximum,
        tuple((key, size, subtotal) for key, (size, subtotal) in groups.items()),
    )


def statistics_parallel(
    students: Iterable[Student | StudentSnapshot],
    *,
    backend: str = "thread",
    workers: int = 4,
    group: str | None = None,
) -> Statistics:
    """Merge centered chunk moments; rank globally with stable input-order ties.

    Process execution uses spawn and top-level pickleable workers. The caller's
    executable entry point must use an if __name__ == '__main__' guard.
    Pool startup, conversion, serialization and final ranking are included.
    """
    if backend not in ("thread", "process"):
        raise ValueError("backend must be 'thread' or 'process'")
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise TypeError("workers must be an integer")
    if workers <= 0:
        raise ValueError("workers must be positive")
    rows = _select(students, group)
    if not rows:
        return _summarize(rows)
    width = (len(rows) + workers - 1) // workers
    chunks = [rows[start : start + width] for start in range(0, len(rows), width)]
    executor = (
        ThreadPoolExecutor(max_workers=workers)
        if backend == "thread"
        else ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
    )
    with executor:
        partials = list(executor.map(_partial_moments, chunks))
    count = 0
    average = 0.0
    m2 = 0.0
    minimum = math.inf
    maximum = -math.inf
    groups: dict[str, tuple[int, float]] = {}
    for part in partials:
        combined = count + part.count
        delta = part.average - average
        m2 += part.m2 + delta * delta * count * part.count / combined
        average += delta * part.count / combined
        count = combined
        minimum = min(minimum, part.minimum)
        maximum = max(maximum, part.maximum)
        for key, size, subtotal in part.groups:
            old_size, old_total = groups.get(key, (0, 0.0))
            groups[key] = old_size + size, old_total + subtotal
    return Statistics(
        count,
        average,
        minimum,
        maximum,
        math.sqrt(max(0.0, m2 / count)),
        tuple((key, subtotal / size) for key, (size, subtotal) in groups.items()),
        tuple(row.student_id for row in rows),
        tuple(
            row.student_id for row in sorted(rows, key=lambda row: -row.average_grade)
        ),
    )


@dataclass(frozen=True, slots=True)
class CacheInfo:
    hits: int
    misses: int
    maxsize: int
    currsize: int
    version: int


class StatisticsService:
    """Thread-safe bounded LRU over privately owned immutable Student snapshots.

    All mutations go through add_student/update_grade and clear cached entries.
    A computation racing with a mutation retries instead of publishing old data.
    Misses count actual computations, including retries; counters are cumulative.
    """

    def __init__(
        self, students: Iterable[Student | StudentSnapshot] = (), *, maxsize: int = 128
    ) -> None:
        if isinstance(maxsize, bool) or not isinstance(maxsize, int):
            raise TypeError("maxsize must be an integer")
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._rows = {row.student_id: row for row in snapshot(students)}
        self._lock = Lock()
        self._version = 0
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
        self._cache: OrderedDict[tuple[int, str | None], Statistics] = OrderedDict()

    def snapshot(self) -> tuple[StudentSnapshot, ...]:
        with self._lock:
            return tuple(self._rows.values())

    def cache_info(self) -> CacheInfo:
        with self._lock:
            return CacheInfo(
                self._hits, self._misses, self._maxsize, len(self._cache), self._version
            )

    def add_student(self, student: Student | StudentSnapshot) -> StudentSnapshot:
        row = snapshot((student,))[0]
        with self._lock:
            if row.student_id in self._rows:
                raise ValueError(f"Duplicate student ID: {row.student_id}")
            self._rows[row.student_id] = row
            self._version += 1
            self._cache.clear()
        return row

    def update_grade(self, student_id: int, average_grade: float) -> StudentSnapshot:
        identifier = _student_id(student_id)
        value = _grade(average_grade)
        with self._lock:
            row = replace(self._rows[identifier], average_grade=value)
            self._rows[identifier] = row
            self._version += 1
            self._cache.clear()
        return row

    def statistics(self, group: str | None = None) -> Statistics:
        normalized = None if group is None else _text(group).casefold()
        while True:
            with self._lock:
                version = self._version
                key = (version, normalized)
                cached = self._cache.get(key)
                if cached is not None:
                    self._hits += 1
                    self._cache.move_to_end(key)
                    return cached
                rows = tuple(self._rows.values())
                self._misses += 1
            if normalized is not None:
                rows = tuple(row for row in rows if row.group == normalized)
            result = _summarize(rows)
            with self._lock:
                if self._version != version:
                    continue
                self._cache[key] = result
                self._cache.move_to_end(key)
                while len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)
                return result
