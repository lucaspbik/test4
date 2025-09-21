"""Core data structures for the special machine builder ERP system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Sequence


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
    operations: List[OperationPlan] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    remarks: str = ""


@dataclass(slots=True)
class PurchaseOrder:
    """Basic purchase order model for procuring external materials."""

    id: str
    supplier_name: str
    item_id: str
    quantity: float
    expected_receipt: date
    status: str = "Open"


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


__all__ = [
    "ManufacturingProcess",
    "OrderStatus",
    "Customer",
    "Machine",
    "InventoryItem",
    "MaterialRequirement",
    "Operation",
    "OperationPlan",
    "ProductionOrder",
    "PurchaseOrder",
    "TimeTrackingEntry",
]
