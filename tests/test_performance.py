import importlib
import importlib.util
import math

import pytest

from student_manager import performance
from student_manager.models import Student


@pytest.mark.parametrize("rows", [[], [Student("A", "B", "G", 100.0, 1)]])
def test_loop_empty_and_singleton(rows: list[Student]) -> None:
    result = performance.statistics_python(iter(rows))
    assert result.count == len(rows)
    assert result.population_stddev == (0.0 if rows else None)
    assert result.average == (100.0 if rows else None)
    assert result.minimum == result.maximum == result.average
    assert result.ranking_ids == ((1,) if rows else ())
    assert result.group_averages == ((("g", 100.0),) if rows else ())


@pytest.mark.parametrize(
    "field,value",
    [
        ("student_id", None),
        ("student_id", True),
        ("student_id", 0),
        ("group", " "),
        ("group", 1),
        ("first_name", ""),
        ("last_name", None),
        ("average_grade", True),
        ("average_grade", "90"),
        ("average_grade", float("nan")),
        ("average_grade", float("inf")),
        ("average_grade", -1),
        ("average_grade", 101),
    ],
)
def test_snapshot_revalidates_mutable_students(field: str, value: object) -> None:
    student = sample()[0]
    setattr(student, field, value)
    with pytest.raises((TypeError, ValueError)):
        performance.snapshot([student])


def test_snapshot_rejects_duplicates_and_non_students() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        performance.snapshot([sample()[0], sample()[0]])
    with pytest.raises(TypeError):
        performance.snapshot([object()])


def test_group_search_is_normalized_and_detached() -> None:
    students = sample()
    rows = performance.snapshot(students)
    found = performance.search_group(students, " G1 ")
    assert tuple(row.student_id for row in found) == (8, 3)
    assert found == performance.search_group(rows, "g1")
    assert performance.search_group(rows, "missing") == ()
    students[0].average_grade = 0.0
    assert found[0].average_grade == 70.0
    with pytest.raises((TypeError, ValueError)):
        performance.search_group(rows, " ")
    with pytest.raises((TypeError, ValueError)):
        performance.search_group(rows, 1)


def assert_equivalent(
    actual: performance.Statistics, expected: performance.Statistics
) -> None:
    assert actual.count == expected.count
    assert actual.student_ids == expected.student_ids
    assert actual.ranking_ids == expected.ranking_ids
    assert actual.average == pytest.approx(expected.average, abs=1e-12)
    assert actual.minimum == expected.minimum
    assert actual.maximum == expected.maximum
    assert actual.population_stddev == pytest.approx(
        expected.population_stddev, abs=1e-12
    )
    assert dict(actual.group_averages) == pytest.approx(
        dict(expected.group_averages), abs=1e-12
    )


@pytest.mark.parametrize("kind", ["empty", "sample", "singleton", "constant"])
def test_numpy_matches_loop_operations(kind: str) -> None:
    rows = {
        "empty": [],
        "sample": sample(),
        "singleton": sample()[:1],
        "constant": [
            Student("A", "B", "G", 100.0, 1),
            Student("C", "D", "g", 100.0, 2),
        ],
    }[kind]
    assert_equivalent(
        performance.statistics_numpy(iter(rows)), performance.statistics_python(rows)
    )


@pytest.mark.parametrize("function", ["statistics_python", "statistics_numpy"])
@pytest.mark.parametrize("group", [" G1 ", "g2", "missing"])
def test_group_statistics_use_search_semantics(function: str, group: str) -> None:
    expected = performance.statistics_python(performance.search_group(sample(), group))
    assert_equivalent(getattr(performance, function)(sample(), group=group), expected)


def test_numpy_revalidates_input() -> None:
    student = sample()[0]
    student.average_grade = float("nan")
    with pytest.raises(ValueError):
        performance.statistics_numpy([student])


@pytest.mark.parametrize("backend", ["thread", "process"])
@pytest.mark.parametrize("workers", [1, 2, 4, 8])
@pytest.mark.parametrize("group", [None, " G1 ", "missing"])
def test_pools_match_full_loop_statistics(
    backend: str, workers: int, group: str | None
) -> None:
    rows = sample() + [Student("E", "Five", "G1", 0.0, 11)]
    actual = performance.statistics_parallel(
        rows, backend=backend, workers=workers, group=group
    )
    assert_equivalent(actual, performance.statistics_python(rows, group=group))


@pytest.mark.parametrize("backend", ["thread", "process"])
def test_parallel_merge_preserves_tiny_variance(backend: str) -> None:
    rows = [Student("A", "B", "G", 99.0 + (i % 3) * 1e-9, i + 1) for i in range(11)]
    assert_equivalent(
        performance.statistics_parallel(rows, backend=backend, workers=4),
        performance.statistics_python(rows),
    )
    assert (
        performance.statistics_parallel(
            rows[:1], backend=backend, workers=2
        ).population_stddev
        == 0.0
    )
    assert performance.statistics_parallel([], backend=backend).count == 0


@pytest.mark.parametrize("workers", [0, -1, True, 1.5, "2"])
def test_pools_reject_invalid_worker_counts_even_for_empty_data(
    workers: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        performance.statistics_parallel([], workers=workers)


def test_pools_reject_unknown_backend_and_invalid_rows() -> None:
    with pytest.raises(ValueError, match="backend"):
        performance.statistics_parallel([], backend="other")
    student = sample()[0]
    student.average_grade = float("inf")
    with pytest.raises(ValueError):
        performance.statistics_parallel([student])


def test_cache_hits_and_add_grade_invalidation() -> None:
    service = performance.StatisticsService(sample(), maxsize=2)
    first = service.statistics(" G1 ")
    assert service.statistics("g1") is first
    assert service.cache_info().hits == 1
    assert service.cache_info().misses == 1
    assert service.cache_info().currsize == 1
    added = service.add_student(Student("E", "Five", "G1", 20.0, 10))
    assert added.student_id == 10
    assert service.cache_info().version == 1
    assert service.cache_info().currsize == 0
    assert service.statistics("g1").average == 60.0
    changed = service.update_grade(10, 80.0)
    assert changed.average_grade == 80.0
    assert service.cache_info().version == 2
    assert service.statistics("g1").average == 80.0
    assert_equivalent(
        service.statistics(), performance.statistics_python(service.snapshot())
    )
    assert service.statistics("missing").count == 0


def test_cache_never_exposes_mutable_entities() -> None:
    from dataclasses import FrozenInstanceError

    rows = sample()
    service = performance.StatisticsService(rows)
    expected = service.statistics()
    rows[0].average_grade = 0.0
    rows.clear()
    assert service.statistics() is expected
    with pytest.raises(FrozenInstanceError):
        service.snapshot()[0].average_grade = 0.0
    with pytest.raises(FrozenInstanceError):
        expected.count = 0
    added = Student("E", "Five", "G1", 20.0, 10)
    service.add_student(added)
    added.average_grade = 100.0
    assert service.statistics().minimum == 20.0
    assert service.snapshot()[-1].average_grade == 20.0


def test_cache_is_bounded_lru() -> None:
    service = performance.StatisticsService(sample(), maxsize=2)
    g1 = service.statistics("g1")
    service.statistics("g2")
    assert service.statistics("G1") is g1
    service.statistics()
    assert service.cache_info().currsize == service.cache_info().maxsize == 2
    misses = service.cache_info().misses
    service.statistics("g2")
    assert service.cache_info().misses == misses + 1


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_cache_rejects_invalid_size(size: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        performance.StatisticsService([], maxsize=size)


def test_invalid_mutations_leave_snapshot_version_and_cache_unchanged() -> None:
    service = performance.StatisticsService(sample())
    cached = service.statistics()
    before = service.snapshot()
    for value in [float("nan"), float("inf"), -1, 101, True, "90"]:
        with pytest.raises((TypeError, ValueError)):
            service.update_grade(8, value)
    for identifier in [True, 0, None]:
        with pytest.raises((TypeError, ValueError)):
            service.update_grade(identifier, 90.0)
    with pytest.raises(KeyError):
        service.update_grade(100, 90.0)
    with pytest.raises(ValueError, match="Duplicate"):
        service.add_student(sample()[0])
    invalid = Student("E", "F", "G", 50.0, 10)
    invalid.group = ""
    with pytest.raises(ValueError):
        service.add_student(invalid)
    assert service.snapshot() == before
    assert service.cache_info().version == 0
    assert service.statistics() is cached


def test_cache_does_not_publish_calculation_from_an_old_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    service = performance.StatisticsService(sample())
    started, release = Event(), Event()
    calculate = performance._summarize

    def delayed(
        rows: tuple[performance.StudentSnapshot, ...],
    ) -> performance.Statistics:
        if rows[0].average_grade == 70.0:
            started.set()
            assert release.wait(5)
        return calculate(rows)

    monkeypatch.setattr(performance, "_summarize", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.statistics, "g1")
        try:
            assert started.wait(5)
            service.update_grade(8, 100.0)
        finally:
            release.set()
        assert future.result(timeout=5).average == 95.0
    assert service.statistics("g1").average == 95.0


def test_concurrent_mutations_and_reads_have_consistent_snapshots() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    service = performance.StatisticsService([])
    barrier = Barrier(4)

    def exercise(worker: int) -> None:
        barrier.wait(timeout=5)
        for index in range(10):
            identifier = worker * 10 + index + 1
            service.add_student(Student("A", "B", "G", 0.0, identifier))
            service.update_grade(identifier, 100.0)
            result = service.statistics()
            assert result.count == len(result.student_ids) == len(result.ranking_ids)
            assert len(set(result.student_ids)) == result.count
            assert result.average is not None and 0.0 <= result.average <= 100.0
            assert (
                result.population_stddev is not None and result.population_stddev >= 0.0
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(exercise, range(4)))
    result = service.statistics()
    assert result.count == 40
    assert result.average == 100.0
    assert result.population_stddev == 0.0
    assert service.cache_info().version == 80
    assert_equivalent(result, performance.statistics_python(service.snapshot()))


def sample() -> list[Student]:
    return [
        Student("A", "One", " G1 ", 70.0, 8),
        Student("B", "Two", "g1", 90.0, 3),
        Student("C", "Three", "G2", 90.0, 9),
        Student("D", "Four", "G2", 50.0, 1),
    ]


def test_loop_statistics_has_population_moments_and_stable_ranking() -> None:
    assert importlib.util.find_spec("student_manager.performance") is not None
    performance = importlib.import_module("student_manager.performance")
    result = performance.statistics_python(sample())
    assert result.count == 4
    assert result.average == 75.0
    assert result.minimum == 50.0
    assert result.maximum == 90.0
    assert result.population_stddev == pytest.approx(math.sqrt(275.0))
    assert dict(result.group_averages) == {"g1": 80.0, "g2": 70.0}
    assert result.student_ids == (8, 3, 9, 1)
    assert result.ranking_ids == (3, 9, 8, 1)
