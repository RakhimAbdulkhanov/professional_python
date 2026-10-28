"""ієрархія винятків для надійної обробки даних"""

from typing import Any


class ApplicationError(Exception):
    """базовий клас для всіх винятків застосунку"""


class ConfigurationError(ApplicationError):
    """помилка завантаження або валідації конфігурації"""


class DataError(ApplicationError):
    """базовий виняток для проблем із даними"""


class DataImportError(DataError):
    """помилка відкриття або читання вхідного файлу"""


class RecordValidationError(DataError):
    """помилка валідації конкретного рядка даних"""

    def __init__(
        self,
        message: str,
        *,
        line_number: int | None = None,
        field: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.line_number = line_number
        self.field = field


class DataExportError(DataError):
    """помилка запису або заміни вихідного файлу"""
