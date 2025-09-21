"""Service layer that implements core ERP logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid4

from .domain import (
    Customer,
    InventoryItem,
    Machine,
    ManufacturingProcess,
    MaterialRequirement,
    Operation,
    OperationPlan,
    OrderStatus,
    ProductionOrder,
    TimeTrackingEntry,
)
from .repository import InMemoryRepository, RecordNotFoundError

DEFAULT_SHIFT_START = time(6, 0)


@dataclass(slots=True)
class ScheduledOperation:
    """Represents a single scheduled execution of an operation."""

    order_id: str
    operation_id: str
    machine_id: str
    start: datetime
    end: datetime
    exceeds_capacity: bool = False


@dataclass(slots=True)
class MachineSchedule:
    """Keeps track of bookings for a single machine."""

    machine: Machine
    next_available: datetime
    total_allocated_hours: float = 0.0
    operations: List[ScheduledOperation] = field(default_factory=list)

    def allocate(self, order_id: str, operation: Operation, earliest_start: datetime) -> ScheduledOperation:
        start_time = max(self.next_available, earliest_start)
        duration = operation.duration_hours + operation.setup_time_hours
        end_time = start_time + timedelta(hours=duration)
        self.next_available = end_time
        self.total_allocated_hours += duration
        scheduled = ScheduledOperation(
            order_id=order_id,
            operation_id=operation.id,
            machine_id=self.machine.id,
            start=start_time,
            end=end_time,
            exceeds_capacity=self.total_allocated_hours > self.machine.capacity_hours_per_week,
        )
        self.operations.append(scheduled)
        return scheduled


@dataclass(slots=True)
class MaterialShortage:
    """Summary of required purchasing action for a material."""

    item_id: str
    name: str
    required_quantity: float
    projected_on_hand: float
    shortage: float
    reorder_recommendation: float


@dataclass(slots=True)
class ScheduleSummary:
    """Aggregate result returned after scheduling an order."""

    order_id: str
    scheduled_operations: List[ScheduledOperation]
    machine_loads: Mapping[str, float]
    overloaded_machines: Mapping[str, float]


class ERPService:
    """Facade that exposes ERP use-cases to clients."""

    def __init__(
        self,
        customer_repo: Optional[InMemoryRepository[Customer]] = None,
        machine_repo: Optional[InMemoryRepository[Machine]] = None,
        order_repo: Optional[InMemoryRepository[ProductionOrder]] = None,
        inventory_repo: Optional[InMemoryRepository[InventoryItem]] = None,
        time_tracking_repo: Optional[InMemoryRepository[TimeTrackingEntry]] = None,
    ) -> None:
        self.customers = customer_repo or InMemoryRepository()
        self.machines = machine_repo or InMemoryRepository()
        self.orders = order_repo or InMemoryRepository()
        self.inventory = inventory_repo or InMemoryRepository()
        self.time_tracking = time_tracking_repo or InMemoryRepository()
        self._machine_schedules: Dict[str, MachineSchedule] = {}

    # ------------------------------------------------------------------
    # Master data
    # ------------------------------------------------------------------
    def create_customer(
        self,
        name: str,
        address: str,
        contact_person: str,
        *,
        contact_email: str = "",
        contact_phone: str = "",
        industry: str = "",
    ) -> Customer:
        customer = Customer(
            id=str(uuid4()),
            name=name,
            address=address,
            contact_person=contact_person,
            contact_email=contact_email,
            contact_phone=contact_phone,
            industry=industry,
        )
        self.customers.add(customer.id, customer)
        return customer

    def register_machine(
        self,
        name: str,
        processes: Sequence[ManufacturingProcess],
        *,
        capacity_hours_per_week: float,
        location: str = "",
        manufacturer: str = "",
        notes: str = "",
    ) -> Machine:
        if not processes:
            raise ValueError("A machine must support at least one manufacturing process")
        machine = Machine(
            id=str(uuid4()),
            name=name,
            processes=tuple(dict.fromkeys(processes)),
            capacity_hours_per_week=capacity_hours_per_week,
            location=location,
            manufacturer=manufacturer,
            notes=notes,
        )
        self.machines.add(machine.id, machine)
        return machine

    def register_inventory_item(
        self,
        name: str,
        unit_of_measure: str,
        *,
        quantity_on_hand: float,
        safety_stock: float = 0.0,
        reorder_point: float = 0.0,
        lead_time_days: int = 0,
    ) -> InventoryItem:
        item = InventoryItem(
            id=str(uuid4()),
            name=name,
            unit_of_measure=unit_of_measure,
            quantity_on_hand=quantity_on_hand,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            lead_time_days=lead_time_days,
        )
        self.inventory.add(item.id, item)
        return item

    # ------------------------------------------------------------------
    # Production orders
    # ------------------------------------------------------------------
    @staticmethod
    def build_operation(
        name: str,
        process: ManufacturingProcess,
        *,
        duration_hours: float,
        setup_time_hours: float = 0.0,
        description: str = "",
        materials: Optional[Iterable[Tuple[str, float]]] = None,
    ) -> Operation:
        material_requirements = [
            MaterialRequirement(item_id=item_id, quantity=quantity)
            for item_id, quantity in (materials or [])
        ]
        return Operation(
            id=str(uuid4()),
            name=name,
            process=process,
            duration_hours=duration_hours,
            setup_time_hours=setup_time_hours,
            description=description,
            materials=material_requirements,
        )

    def create_production_order(
        self,
        customer_id: str,
        reference: str,
        due_date: date,
        operations: Sequence[Operation],
        *,
        remarks: str = "",
    ) -> ProductionOrder:
        if customer_id not in self.customers:
            raise RecordNotFoundError(f"Customer {customer_id!r} does not exist")
        if not operations:
            raise ValueError("Production orders must contain at least one operation")
        order = ProductionOrder(
            id=str(uuid4()),
            customer_id=customer_id,
            reference=reference,
            due_date=due_date,
            operations=[OperationPlan(operation=operation) for operation in operations],
            remarks=remarks,
        )
        self.orders.add(order.id, order)
        return order

    def add_operation_to_order(self, order_id: str, operation: Operation) -> ProductionOrder:
        order = self.orders.get(order_id)
        order.operations.append(OperationPlan(operation=operation))
        self.orders.upsert(order.id, order)
        return order

    def update_order_status(self, order_id: str, status: OrderStatus) -> ProductionOrder:
        order = self.orders.get(order_id)
        order.status = status
        self.orders.upsert(order.id, order)
        return order

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def _eligible_machines(self, process: ManufacturingProcess) -> List[Machine]:
        machines = [machine for machine in self.machines if process in machine.processes]
        if not machines:
            raise RecordNotFoundError(
                f"No machines configured for process {process.value}"
            )
        return machines

    def _get_machine_schedule(self, machine_id: str, start_reference: datetime) -> MachineSchedule:
        schedule = self._machine_schedules.get(machine_id)
        if schedule is None:
            machine = self.machines.get(machine_id)
            schedule = MachineSchedule(machine=machine, next_available=start_reference)
            self._machine_schedules[machine_id] = schedule
        return schedule

    def schedule_operations(
        self,
        order_id: str,
        *,
        start_reference: Optional[datetime] = None,
    ) -> ScheduleSummary:
        order = self.orders.get(order_id)
        start_reference = start_reference or datetime.combine(date.today(), DEFAULT_SHIFT_START)
        earliest_start = start_reference
        scheduled_operations: List[ScheduledOperation] = []
        used_machine_ids: List[str] = []

        for plan in order.operations:
            machines = self._eligible_machines(plan.operation.process)
            candidate_schedules = [
                self._get_machine_schedule(machine.id, start_reference) for machine in machines
            ]
            candidate_schedules.sort(key=lambda schedule: schedule.total_allocated_hours)
            schedule = candidate_schedules[0]
            scheduled = schedule.allocate(order.id, plan.operation, earliest_start)
            plan.assigned_machine_id = scheduled.machine_id
            plan.scheduled_start = scheduled.start
            plan.scheduled_end = scheduled.end
            scheduled_operations.append(scheduled)
            used_machine_ids.append(schedule.machine.id)
            earliest_start = scheduled.end

        self.orders.upsert(order.id, order)
        if order.status == OrderStatus.PLANNED:
            order.status = OrderStatus.RELEASED
            self.orders.upsert(order.id, order)

        machine_loads = {
            machine_id: self._machine_schedules[machine_id].total_allocated_hours
            for machine_id in used_machine_ids
        }
        overloaded = {
            machine_id: max(
                0.0,
                self._machine_schedules[machine_id].total_allocated_hours
                - self._machine_schedules[machine_id].machine.capacity_hours_per_week,
            )
            for machine_id in used_machine_ids
            if self._machine_schedules[machine_id].total_allocated_hours
            > self._machine_schedules[machine_id].machine.capacity_hours_per_week
        }

        return ScheduleSummary(
            order_id=order.id,
            scheduled_operations=scheduled_operations,
            machine_loads=machine_loads,
            overloaded_machines=overloaded,
        )

    # ------------------------------------------------------------------
    # Material management
    # ------------------------------------------------------------------
    def material_shortage_report(self, order_id: str) -> List[MaterialShortage]:
        order = self.orders.get(order_id)
        aggregated_requirements: Dict[str, float] = {}
        for plan in order.operations:
            for requirement in plan.operation.materials:
                aggregated_requirements[requirement.item_id] = aggregated_requirements.get(
                    requirement.item_id, 0.0
                ) + requirement.quantity

        shortages: List[MaterialShortage] = []
        for item_id, required_quantity in aggregated_requirements.items():
            try:
                item = self.inventory.get(item_id)
            except RecordNotFoundError:
                shortages.append(
                    MaterialShortage(
                        item_id=item_id,
                        name="Unbekannte Position",
                        required_quantity=required_quantity,
                        projected_on_hand=-required_quantity,
                        shortage=required_quantity,
                        reorder_recommendation=required_quantity,
                    )
                )
                continue

            projected_on_hand = item.quantity_on_hand - required_quantity
            shortage = max(0.0, item.safety_stock - projected_on_hand)
            reorder_recommendation = max(shortage, item.reorder_point - projected_on_hand, 0.0)
            if shortage > 0 or projected_on_hand < item.reorder_point:
                shortages.append(
                    MaterialShortage(
                        item_id=item.id,
                        name=item.name,
                        required_quantity=required_quantity,
                        projected_on_hand=projected_on_hand,
                        shortage=shortage,
                        reorder_recommendation=reorder_recommendation,
                    )
                )
        return shortages

    def consume_materials(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        for plan in order.operations:
            for requirement in plan.operation.materials:
                try:
                    item = self.inventory.get(requirement.item_id)
                except RecordNotFoundError as exc:
                    raise RecordNotFoundError(
                        f"Material {requirement.item_id!r} is not present in inventory"
                    ) from exc
                item.quantity_on_hand -= requirement.quantity
                self.inventory.upsert(item.id, item)

    # ------------------------------------------------------------------
    # Time tracking
    # ------------------------------------------------------------------
    def record_time_tracking(
        self,
        order_id: str,
        operation_id: str,
        employee: str,
        *,
        start_time: datetime,
        end_time: datetime,
        remarks: str = "",
    ) -> TimeTrackingEntry:
        entry = TimeTrackingEntry(
            id=str(uuid4()),
            order_id=order_id,
            operation_id=operation_id,
            employee=employee,
            start_time=start_time,
            end_time=end_time,
            remarks=remarks,
        )
        self.time_tracking.add(entry.id, entry)
        return entry

    def calculate_actual_vs_plan(self, order_id: str) -> Dict[str, float]:
        """Compare planned vs. actual hours for the given order."""

        order = self.orders.get(order_id)
        planned_hours = sum(
            plan.operation.duration_hours + plan.operation.setup_time_hours
            for plan in order.operations
        )
        actual_hours = 0.0
        for entry in self.time_tracking:
            if entry.order_id == order_id:
                delta = entry.end_time - entry.start_time
                actual_hours += delta.total_seconds() / 3600
        return {"planned_hours": planned_hours, "actual_hours": actual_hours}


__all__ = [
    "ERPService",
    "ScheduleSummary",
    "ScheduledOperation",
    "MaterialShortage",
]
