import argparse
import json
from time import perf_counter

from student_manager.models import Student


def lookup_benchmark(
    sizes: tuple[int, ...] = (1000, 10000, 100000), *, repeats: int = 200
) -> list[dict[str, float | int]]:
    if repeats <= 0 or any(size <= 0 for size in sizes):
        raise ValueError("Sizes and repeats must be positive")
    results = []
    for size in sizes:
        records = [
            (number, Student("Student", str(number), "A", 80)) for number in range(size)
        ]
        start = perf_counter()
        index = {number: student for number, student in records}
        build = perf_counter() - start
        target = size - 1
        linear: Student | None = None
        indexed: Student | None = None
        start = perf_counter()
        for _ in range(repeats):
            linear = next(
                (student for number, student in records if number == target), None
            )
        linear_time = (perf_counter() - start) / repeats
        start = perf_counter()
        for _ in range(repeats):
            indexed = index.get(target)
        indexed_time = (perf_counter() - start) / repeats
        assert linear is indexed
        results.append(
            {
                "records": size,
                "list_seconds": linear_time,
                "dict_seconds": indexed_time,
                "build_seconds": build,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=["lookup"])
    parser.parse_args()
    print(json.dumps(lookup_benchmark(), indent=2))


if __name__ == "__main__":
    main()
