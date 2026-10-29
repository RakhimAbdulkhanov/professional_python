"""демонстраційний запуск надійного конвеєра лабораторної роботи 5"""

import argparse
import sys
from collections.abc import Sequence

from student_manager.config import load_config
from student_manager.exceptions import ApplicationError
from student_manager.reliable_io import (
    close_logging_handlers,
    configure_logging,
    process_config,
)


def run_lab5_demo(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m student_manager.lab5_demo",
        description="Run reliable student CSV import and JSON export pipeline",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.yaml",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        logger = configure_logging(config.logging)
        stats = process_config(config, logger=logger)
        print(
            f"Pipeline completed: total={stats.total}, valid={stats.valid}, "
            f"invalid={stats.invalid}, exported={stats.exported}"
        )
        print(f"Output: {config.output_path}")
        return 0
    except ApplicationError as err:
        sys.stderr.write(f"Application error: {err}\n")
        return 1
    finally:
        # закриваємо хендлери шоб уникнути блокування файлу логів
        import logging

        close_logging_handlers(logging.getLogger("student_manager"))


def main() -> None:
    code = run_lab5_demo()
    sys.exit(code)


if __name__ == "__main__":
    main()
