"""SQLite-backed persistence helpers for the ERP system."""

from __future__ import annotations

import pickle
import sqlite3
from typing import Generic, Iterator, List, Optional, TypeVar

from .domain import (
    Customer,
    InventoryItem,
    Machine,
    ProductionOrder,
    PurchaseOrder,
    ShiftCalendar,
    Supplier,
    SupplierEvaluation,
    TimeTrackingEntry,
    User,
)
from .repository import DuplicateRecordError, RecordNotFoundError

T = TypeVar("T")


class SQLiteRepository(Generic[T]):
    """Repository implementation that persists records inside SQLite."""

    def __init__(self, connection: sqlite3.Connection, table: str) -> None:
        self._connection = connection
        self._table = table
        self._connection.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ("  # nosec - static table names
            "id TEXT PRIMARY KEY, payload BLOB NOT NULL)"
        )
        self._connection.commit()

    def __contains__(self, item_id: object) -> bool:
        if not isinstance(item_id, str):  # pragma: no cover - defensive
            return False
        cursor = self._connection.execute(
            f"SELECT 1 FROM {self._table} WHERE id = ? LIMIT 1", (item_id,)
        )
        return cursor.fetchone() is not None

    def __iter__(self) -> Iterator[T]:
        return iter(self.list())

    def __len__(self) -> int:  # pragma: no cover - simple delegation
        cursor = self._connection.execute(
            f"SELECT COUNT(1) FROM {self._table}"
        )
        value = cursor.fetchone()
        return int(value[0]) if value else 0

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def add(self, item_id: str, item: T) -> None:
        if item_id in self:
            raise DuplicateRecordError(f"Record with id {item_id!r} already exists")
        payload = pickle.dumps(item)
        self._connection.execute(
            f"INSERT INTO {self._table} (id, payload) VALUES (?, ?)",
            (item_id, payload),
        )
        self._connection.commit()

    def upsert(self, item_id: str, item: T) -> None:
        payload = pickle.dumps(item)
        self._connection.execute(
            f"INSERT INTO {self._table} (id, payload) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (item_id, payload),
        )
        self._connection.commit()

    def get(self, item_id: str) -> T:
        cursor = self._connection.execute(
            f"SELECT payload FROM {self._table} WHERE id = ?", (item_id,)
        )
        row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Record with id {item_id!r} not found")
        return pickle.loads(row[0])

    def remove(self, item_id: str) -> None:
        cursor = self._connection.execute(
            f"DELETE FROM {self._table} WHERE id = ?", (item_id,)
        )
        if cursor.rowcount == 0:
            raise RecordNotFoundError(f"Record with id {item_id!r} not found")
        self._connection.commit()

    def list(self) -> List[T]:
        cursor = self._connection.execute(
            f"SELECT payload FROM {self._table} ORDER BY id"
        )
        return [pickle.loads(row[0]) for row in cursor.fetchall()]


class ERPDatabase:
    """Convenience facade bundling SQLite repositories for all aggregates."""

    def __init__(self, path: str) -> None:
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        self._connection = connection
        self.customers = SQLiteRepository[Customer](connection, "customers")
        self.machines = SQLiteRepository[Machine](connection, "machines")
        self.orders = SQLiteRepository[ProductionOrder](connection, "orders")
        self.inventory = SQLiteRepository[InventoryItem](connection, "inventory")
        self.time_tracking = SQLiteRepository[TimeTrackingEntry](connection, "time_tracking")
        self.suppliers = SQLiteRepository[Supplier](connection, "suppliers")
        self.purchase_orders = SQLiteRepository[PurchaseOrder](connection, "purchase_orders")
        self.supplier_evaluations = SQLiteRepository[SupplierEvaluation](
            connection, "supplier_evaluations"
        )
        self.shift_calendars = SQLiteRepository[ShiftCalendar](
            connection, "shift_calendars"
        )
        self.users = SQLiteRepository[User](connection, "users")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ERPDatabase":  # pragma: no cover - convenience
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[BaseException],
    ) -> None:  # pragma: no cover - convenience
        self.close()


__all__ = ["SQLiteRepository", "ERPDatabase"]
