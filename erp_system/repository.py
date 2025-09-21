"""Simple in-memory repositories used by the ERP service layer."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Generic, Iterable, Iterator, List, MutableMapping, TypeVar

T = TypeVar("T")


class RepositoryError(RuntimeError):
    """Base exception for repository errors."""


class DuplicateRecordError(RepositoryError):
    """Raised when attempting to insert a record that already exists."""


class RecordNotFoundError(RepositoryError):
    """Raised when a requested record is missing."""


class InMemoryRepository(Generic[T]):
    """Generic repository backed by a simple dictionary."""

    def __init__(self) -> None:
        self._items: MutableMapping[str, T] = {}

    def __contains__(self, item_id: object) -> bool:  # pragma: no cover - convenience
        return item_id in self._items

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self._items)

    def add(self, item_id: str, item: T) -> None:
        if item_id in self._items:
            raise DuplicateRecordError(f"Record with id {item_id!r} already exists")
        self._items[item_id] = item

    def upsert(self, item_id: str, item: T) -> None:
        self._items[item_id] = item

    def get(self, item_id: str) -> T:
        try:
            return self._items[item_id]
        except KeyError as exc:  # pragma: no cover - trivial
            raise RecordNotFoundError(f"Record with id {item_id!r} not found") from exc

    def remove(self, item_id: str) -> None:
        if item_id not in self._items:
            raise RecordNotFoundError(f"Record with id {item_id!r} not found")
        del self._items[item_id]

    def list(self) -> List[T]:
        return list(self._items.values())

    def as_dicts(self) -> Iterable[Dict]:  # pragma: no cover - convenience
        for item in self._items.values():
            yield asdict(item)

    def __iter__(self) -> Iterator[T]:  # pragma: no cover - convenience
        return iter(self._items.values())


__all__ = [
    "InMemoryRepository",
    "RepositoryError",
    "DuplicateRecordError",
    "RecordNotFoundError",
]
