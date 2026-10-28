from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    # абстрактний базовий клас репозиторію
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def add(self, key: int, item: T) -> None:
        # додавання сутності за ключем
        ...

    @abstractmethod
    def get(self, key: int) -> T | None:
        # отримання сутності за ключем
        ...

    @abstractmethod
    def all(self) -> tuple[T, ...]:
        # повертає всі збережені сутності
        ...

    @abstractmethod
    def update(self, key: int, item: T) -> None:
        # оновлення наявної сутності
        ...


class InMemoryRepository(Repository[T]):
    # збереження сутностей у пам'яті
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[int, T] = {}

    def add(self, key: int, item: T) -> None:
        # додаєм новий запис і блокуєм дублікати ключів
        if key in self._items:
            raise ValueError(f"Key {key} already exists")
        self._items[key] = item

    def get(self, key: int) -> T | None:
        # дістаєм запис за ключем
        return self._items.get(key)

    def all(self) -> tuple[T, ...]:
        # незмінний кортеж усіх записів
        return tuple(self._items.values())

    def update(self, key: int, item: T) -> None:
        # оновлюєм існуючий запис
        if key not in self._items:
            raise KeyError(f"Key {key} not found")
        self._items[key] = item

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: int) -> bool:
        return key in self._items
