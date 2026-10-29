"""Demonstration CLI and runner for Lab 3 streaming operations."""

import argparse
import sys
from pathlib import Path

from student_manager.streaming import (
    StreamStats,
    StudentIterator,
    batch_students,
    calculate_statistics,
    chain_student_streams,
    filter_by_group,
    filter_by_min_grade,
    find_student,
    first_n_students,
    grade_differences,
    infinite_counter_slice,
    open_student_stream,
    top_students,
    transform_to_summary,
)


def run_demo(path: str | Path) -> int:
    csv_path = Path(path)
    if not csv_path.exists():
        print(f"Error: file not found at {csv_path}", file=sys.stderr)
        return 1

    print(f"Dataset path: {csv_path}")

    # 1. демонстрація власного ітератора та його вичерпання
    print("\n--- 1. Iterator exhaustion ---")
    with open_student_stream(csv_path) as stream:
        iterator = StudentIterator(stream)
        count_read = 0
        for student in iterator:
            count_read += 1
            if count_read <= 2:
                print(
                    f"Read: {student.student_id} {student.full_name} ({student.average_grade})"
                )
        print(f"Total read by iterator: {count_read}")
        try:
            next(iterator)
        except StopIteration:
            print("Next call correctly raised StopIteration (exhausted)")

    # 2. фільтрація за групою та мінімальним балом
    print("\n--- 2. Filter by group and grade ---")
    with open_student_stream(csv_path) as stream:
        filtered = list(filter_by_min_grade(filter_by_group(stream, "ФеП-33"), 85.0))
        print(
            f"Qualifying students in group ФеП-33 with grade >= 85.0: {len(filtered)}"
        )
        for s in filtered[:3]:
            print(f"  {s.student_id}: {s.full_name} - {s.average_grade}")

    # 3. лінивий пошук за id та прізвищем з раннім виходом
    print("\n--- 3. Lazy search with early termination ---")
    with open_student_stream(csv_path) as stream:
        found_by_id = find_student(stream, student_id=2)
        if found_by_id:
            print(f"Found ID 2: {found_by_id.full_name} ({found_by_id.group})")

    with open_student_stream(csv_path) as stream:
        found_by_surname = find_student(stream, surname="Шевченко")
        if found_by_surname:
            print(
                f"Found surname Шевченко: ID {found_by_surname.student_id}, {found_by_surname.full_name}"
            )

    # 4. різниця між першими n записами та top-n за балом
    print("\n--- 4. First matches vs Top-N ---")
    with open_student_stream(csv_path) as stream:
        first_3 = first_n_students(stream, 3)
        print("First 3 in stream arrival order:")
        for s in first_3:
            print(f"  ID {s.student_id}: {s.full_name} ({s.average_grade})")

    with open_student_stream(csv_path) as stream:
        top_3 = top_students(stream, 3)
        print("Top 3 by grade (highest):")
        for s in top_3:
            print(f"  ID {s.student_id}: {s.full_name} ({s.average_grade})")

    # 5. однопрохідна потокова статистика та трансформація
    print("\n--- 5. Statistics (single pass) ---")
    stats_tracker = StreamStats()
    with open_student_stream(csv_path, stats=stats_tracker) as stream:
        stats = calculate_statistics(stream)
        print(f"Count: {stats['count']}")
        avg_str = f"{stats['average']:.2f}" if stats["average"] is not None else "None"
        print(f"Average: {avg_str}")
        print(f"Min grade: {stats['min_grade']}")
        print(f"Max grade: {stats['max_grade']}")
        print(f"Groups: {stats['group_counts']}")
        print(f"Invalid records skipped: {stats_tracker.invalid_records}")

    print("\n--- Summary tuples (transformation) ---")
    with open_student_stream(csv_path) as stream:
        for item in list(transform_to_summary(stream))[:2]:
            print(f"  Summary tuple: {item}")

    # 6. пакетна обробка
    print("\n--- 6. Batches ---")
    with open_student_stream(csv_path) as stream:
        batch_size = 2
        batch_count = 0
        total_in_batches = 0
        for batch in batch_students(stream, batch_size):
            batch_count += 1
            total_in_batches += len(batch)
        print(
            f"Batch size: {batch_size}, total batches: {batch_count}, records processed: {total_in_batches}"
        )

    # 7. об'єднання декількох файлів через chain
    print("\n--- 7. Chain streams ---")
    with open_student_stream(csv_path) as s1, open_student_stream(csv_path) as s2:
        chained = list(first_n_students(chain_student_streams(s1, s2), 4))
        print(
            f"Chained 2 streams, read first 4 records: {[s.student_id for s in chained]}"
        )

    # 8. pairwise різниці оцінок
    print("\n--- 8. Pairwise grade differences ---")
    with open_student_stream(csv_path) as stream:
        first_few = first_n_students(stream, 4)
        diffs = list(grade_differences(first_few))
        print(f"Pairwise differences of first {len(first_few)} students: {diffs}")

    # 9. скінченний зріз нескінченної послідовності count через islice
    print("\n--- 9. Infinite slice (itertools.count + islice) ---")
    infinite_slice = infinite_counter_slice(start=100, step=10, count_limit=5)
    print(f"Generated bounded slice of count: {infinite_slice}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lab 3 streaming demo")
    parser.add_argument("path", help="Path to CSV dataset")
    args = parser.parse_args(argv)
    return run_demo(args.path)


if __name__ == "__main__":
    sys.exit(main())
