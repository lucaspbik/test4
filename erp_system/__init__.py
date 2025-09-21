"""Domain-specific ERP system for a special machine builder.

This package provides data models, in-memory persistence, and scheduling
services tailored to manufacturing processes like turning, milling, laser
cutting, bending, welding, grinding, and sawing.
"""

from .domain import (
    ChecklistItem,
    ManufacturingProcess,
    Customer,
    Machine,
    Operation,
    OperationPlan,
    ProductionOrder,
    OrderStatus,
    OrderPriority,
    PlanningScenario,
    PurchaseOrder,
    Shift,
    ShiftCalendar,
    Supplier,
    SupplierEvaluation,
    User,
    UserRole,
    WorkInstruction,
)
from .services import (
    ERPService,
    MaterialShortage,
    PlanningOptions,
    ProcurementOptions,
    ScheduleSummary,
    ScenarioSimulationResult,
)

__all__ = [
    "ChecklistItem",
    "ManufacturingProcess",
    "Customer",
    "Machine",
    "Operation",
    "OperationPlan",
    "ProductionOrder",
    "OrderStatus",
    "OrderPriority",
    "PlanningScenario",
    "PurchaseOrder",
    "Shift",
    "ShiftCalendar",
    "Supplier",
    "SupplierEvaluation",
    "User",
    "UserRole",
    "WorkInstruction",
    "ERPService",
    "ScheduleSummary",
    "ScenarioSimulationResult",
    "MaterialShortage",
    "PlanningOptions",
    "ProcurementOptions",
]
