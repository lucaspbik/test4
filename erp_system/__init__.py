"""Domain-specific ERP system for a special machine builder.

This package provides data models, in-memory persistence, and scheduling
services tailored to manufacturing processes like turning, milling, laser
cutting, bending, welding, grinding, and sawing.
"""

from .domain import (
    ManufacturingProcess,
    Customer,
    Machine,
    Operation,
    OperationPlan,
    ProductionOrder,
    OrderStatus,
)
from .services import ERPService, ScheduleSummary

__all__ = [
    "ManufacturingProcess",
    "Customer",
    "Machine",
    "Operation",
    "OperationPlan",
    "ProductionOrder",
    "OrderStatus",
    "ERPService",
    "ScheduleSummary",
]
