"""Core data structures for the special machine builder ERP system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum, IntEnum
from typing import List, Optional, Sequence, Set, Tuple


class ManufacturingProcess(str, Enum):
    """Enumeration of the manufacturing processes used in the shop."""

    TURNING = "Turning"
    MILLING = "Milling"
    LASER_CUTTING = "Laser Cutting"
    BENDING = "Bending"
    WELDING = "Welding"
    GRINDING = "Grinding"
    SAWING = "Sawing"


class OrderStatus(str, Enum):
    """Lifecycle stages for a production order."""

    PLANNED = "Planned"
    RELEASED = "Released"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class OrderPriority(IntEnum):
    """Priority levels for production orders used during planning."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return {
            OrderPriority.LOW: "Low",
            OrderPriority.NORMAL: "Normal",
            OrderPriority.HIGH: "High",
            OrderPriority.CRITICAL: "Critical",
        }[self]


@dataclass(slots=True)
class Customer:
    """Customer master data."""

    id: str
    name: str
    address: str
    contact_person: str
    contact_email: str = ""
    contact_phone: str = ""
    industry: str = ""


@dataclass(slots=True)
class Machine:
    """A machine resource that can execute one or more processes."""

    id: str
    name: str
    processes: Sequence[ManufacturingProcess]
    capacity_hours_per_week: float
    location: str = ""
    manufacturer: str = ""
    notes: str = ""
    shift_calendar_id: Optional[str] = None


@dataclass(slots=True)
class InventoryItem:
    """Simple material master for procurement and stock management."""

    id: str
    name: str
    unit_of_measure: str
    quantity_on_hand: float
    safety_stock: float = 0.0
    reorder_point: float = 0.0
    lead_time_days: int = 0


@dataclass(slots=True)
class MaterialRequirement:
    """A material requirement for a specific operation."""

    item_id: str
    quantity: float


@dataclass(slots=True)
class Operation:
    """An individual manufacturing step required for an order."""

    id: str
    name: str
    process: ManufacturingProcess
    duration_hours: float
    setup_time_hours: float = 0.0
    description: str = ""
    materials: List[MaterialRequirement] = field(default_factory=list)


@dataclass(slots=True)
class OperationPlan:
    """Scheduling metadata for a specific operation instance."""

    operation: Operation
    assigned_machine_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: str = ""


@dataclass(slots=True)
class ProductionOrder:
    """Represents a confirmed order with a sequence of operations."""

    id: str
    customer_id: str
    reference: str
    due_date: date
    status: OrderStatus = OrderStatus.PLANNED
    priority: OrderPriority = OrderPriority.NORMAL
    operations: List[OperationPlan] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    remarks: str = ""


@dataclass(slots=True)
class PurchaseOrder:
    """Basic purchase order model for procuring external materials."""

    id: str
    supplier_id: str
    item_id: str
    quantity: float
    expected_receipt: date
    status: str = "Open"
    supplier_name: str = ""
    price_per_unit: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""


@dataclass(slots=True)
class TimeTrackingEntry:
    """Actual production time feedback from the shop floor."""

    id: str
    order_id: str
    operation_id: str
    employee: str
    start_time: datetime
    end_time: datetime
    remarks: str = ""


@dataclass(slots=True)
class Shift:
    """Definition of a daily working shift."""

    name: str
    start_time: time
    end_time: time
    weekdays: Tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.weekdays:
            raise ValueError("A shift must define at least one weekday")
        for weekday in self.weekdays:
            if weekday < 0 or weekday > 6:
                raise ValueError("Weekday indices must be in range 0..6")
        if self.end_time == self.start_time:
            raise ValueError("Shift end time must differ from start time")


@dataclass(slots=True)
class ShiftCalendar:
    """Collection of shifts and non-working days for capacity planning."""

    id: str
    name: str
    shifts: List[Shift]
    non_working_days: Set[date] = field(default_factory=set)

    def add_non_working_day(self, day: date) -> None:
        self.non_working_days.add(day)


@dataclass(slots=True)
class Supplier:
    """Supplier master data including capability and rating information."""

    id: str
    name: str
    address: str
    contact_person: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    rating: float = 0.0
    rating_count: int = 0
    process_capabilities: Tuple[ManufacturingProcess, ...] = tuple()
    material_item_ids: Tuple[str, ...] = tuple()


@dataclass(slots=True)
class SupplierEvaluation:
    """Evaluation entry for a supplier performance review."""

    id: str
    supplier_id: str
    evaluated_on: date
    quality_score: float
    delivery_reliability_score: float
    communication_score: float
    overall_score: float
    notes: str = ""


__all__ = [
    "ManufacturingProcess",
    "OrderStatus",
    "OrderPriority",
    "Customer",
    "Machine",
    "InventoryItem",
    "MaterialRequirement",
    "Operation",
    "OperationPlan",
    "ProductionOrder",
    "PurchaseOrder",
    "TimeTrackingEntry",
    "Shift",
    "ShiftCalendar",
    "Supplier",
    "SupplierEvaluation",
]
