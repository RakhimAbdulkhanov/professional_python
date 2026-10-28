import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from student_manager.registry import ConsoleNotifier, Notifier, RecordingNotifier

# --- Експеримент 1: Внутрішня залежність проти Dependency Injection ---


class HardcodedNotifierService:
    # варіант a: сервіс створює конкретну залежність всередині
    def __init__(self) -> None:
        self._notifier: Notifier = ConsoleNotifier()

    def register_student(self, student_id: int, full_name: str) -> str:
        # реєстрація з жорстко прив'язаним сповіщувачем
        message = f"Audit: student {student_id} ({full_name}) registered"
        self._notifier.send(message)
        return message


class InjectedNotifierService:
    # варіант b: сервіс отримує абстракцію через конструктор (DIP)
    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def register_student(self, student_id: int, full_name: str) -> str:
        # реєстрація з інжектованим сповіщувачем
        message = f"Audit: student {student_id} ({full_name}) registered"
        self._notifier.send(message)
        return message


# --- Експеримент 2: Наслідування проти Композиції ---


def default_parse(raw: str) -> dict[str, str]:
    # парсинг csv-рядка на складові поля
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 5:
        raise ValueError(f"Expected 5 fields, got {len(parts)}")
    return {
        "id": parts[0],
        "first": parts[1],
        "last": parts[2],
        "group": parts[3],
        "grade": parts[4],
    }


def default_validate(data: dict[str, str]) -> dict[str, str]:
    # валідація полів картки студента
    if not data["id"].isdigit() or int(data["id"]) <= 0:
        raise ValueError("Invalid student id")
    if not data["first"] or not data["last"] or not data["group"]:
        raise ValueError("Names and group cannot be empty")
    try:
        val = float(data["grade"])
    except ValueError as err:
        raise ValueError("Grade must be float") from err
    if not math.isfinite(val) or not 0.0 <= val <= 100.0:
        raise ValueError("Grade out of bounds")
    return data


def default_render(data: dict[str, str]) -> str:
    # форматування картки для відображення
    return f"STUDENT#{data['id']}: {data['first']} {data['last']} [{data['group']}] - {data['grade']} балів"


class BaseStudentCardFormatter(ABC):
    # варіант a: базовий клас із шаблоном обробки (наслідування)
    def format_record(self, raw: str) -> str:
        parsed = self.parse(raw)
        validated = self.validate(parsed)
        return self.render(validated)

    def parse(self, raw: str) -> dict[str, str]:
        return default_parse(raw)

    def validate(self, data: dict[str, str]) -> dict[str, str]:
        return default_validate(data)

    @abstractmethod
    def render(self, data: dict[str, str]) -> str: ...


class TemplateStudentCardFormatter(BaseStudentCardFormatter):
    # конкретна реалізація рендерингу в ієрархії наслідування
    def render(self, data: dict[str, str]) -> str:
        return default_render(data)


class CompositeStudentCardProcessor:
    # варіант b: композиція з незалежних функцій-кроків
    def __init__(
        self,
        parser: Callable[[str], dict[str, str]],
        validator: Callable[[dict[str, str]], dict[str, str]],
        renderer: Callable[[dict[str, str]], str],
    ) -> None:
        self._parser = parser
        self._validator = validator
        self._renderer = renderer

    def process(self, raw: str) -> str:
        # послідовне застосування переданих компонентів
        return self._renderer(self._validator(self._parser(raw)))


def run_design_experiments() -> dict[str, Any]:
    # запуск порівняльних сценаріїв для отримання доказів
    # 1. порівняння notifier
    hardcoded = HardcodedNotifierService()
    msg_a = hardcoded.register_student(1, "Олена Коваль")

    recorder = RecordingNotifier()
    injected = InjectedNotifierService(recorder)
    msg_b = injected.register_student(1, "Олена Коваль")
    notifier_match = msg_a == msg_b and recorder.messages == [msg_b]

    # 2. порівняння форматування
    sample_raw = "10,Ірина,Бондар,ФеП-33,95.5"
    fmt_inheritance = TemplateStudentCardFormatter()
    res_inheritance = fmt_inheritance.format_record(sample_raw)

    fmt_composite = CompositeStudentCardProcessor(
        parser=default_parse,
        validator=default_validate,
        renderer=default_render,
    )
    res_composite = fmt_composite.process(sample_raw)
    formatter_match = res_inheritance == res_composite

    return {
        "notifier_match": notifier_match,
        "notifier_output": msg_a,
        "formatter_match": formatter_match,
        "formatter_output": res_composite,
    }
