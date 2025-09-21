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
    OrderPriority,
    OrderStatus,
    PurchaseOrder,
    ProductionOrder,
    Shift,
    ShiftCalendar,
    Supplier,
    SupplierEvaluation,
    TimeTrackingEntry,
)
from .repository import InMemoryRepository, RecordNotFoundError

DEFAULT_SHIFT_START = time(6, 0)


@dataclass(slots=True)
class PlanningOptions:
    """Fine-tuning parameters used by the scheduling engine."""

    priority_weight: float = 1.0
    due_date_weight: float = 1.0
    horizon_days: int = 0
    max_orders_per_cycle: int = 0
    auto_release_orders: bool = True
    default_start_time: time = field(default_factory=lambda: DEFAULT_SHIFT_START)
    setup_time_factor: float = 1.0
    gap_between_operations_minutes: int = 0


@dataclass(slots=True)
class ProcurementOptions:
    """Configuration values controlling purchase planning."""

    reorder_multiplier: float = 1.0
    include_safety_stock_gap: bool = True
    expedite_high_priority_days: int = 0
    default_lead_time_days: int = 0
    auto_create_orders: bool = False


def _next_shift_window(
    calendar: ShiftCalendar, reference: datetime
) -> Optional[Tuple[datetime, datetime]]:
    """Return the next usable shift window starting at or after reference."""

    for day_offset in range(0, 60):
        candidate_day = reference.date() + timedelta(days=day_offset)
        if candidate_day in calendar.non_working_days:
            continue
        weekday = candidate_day.weekday()
        matching = [
            shift for shift in calendar.shifts if weekday in shift.weekdays
        ]
        if not matching:
            continue
        matching.sort(key=lambda shift: shift.start_time)
        for shift in matching:
            shift_start = datetime.combine(candidate_day, shift.start_time)
            shift_end = datetime.combine(candidate_day, shift.end_time)
            if shift_end <= shift_start:
                shift_end += timedelta(days=1)
            if shift_end <= reference:
                continue
            start_point = max(reference, shift_start)
            return start_point, shift_end
    return None


def _allocate_with_calendar(
    calendar: ShiftCalendar, reference: datetime, duration_hours: float
) -> Tuple[datetime, datetime]:
    """Find the next available slot respecting the configured shift calendar."""

    remaining = timedelta(hours=duration_hours)
    if remaining <= timedelta(0):
        raise ValueError("Duration must be positive")
    start_time: Optional[datetime] = None
    cursor = reference

    while remaining > timedelta(0):
        window = _next_shift_window(calendar, cursor)
        if window is None:
            raise RuntimeError("No shift capacity available for scheduling")
        window_start, window_end = window
        cursor = max(cursor, window_start)
        available = window_end - cursor
        if available <= timedelta(0):
            cursor = window_end + timedelta(minutes=1)
            continue
        if start_time is None:
            start_time = cursor
        allocation = min(available, remaining)
        cursor += allocation
        remaining -= allocation
        if remaining <= timedelta(0):
            return start_time, cursor
        cursor = window_end + timedelta(minutes=1)
    assert start_time is not None  # pragma: no cover - defensive
    return start_time, cursor


@dataclass(slots=True)
class ScheduledOperation:
    """Represents a single scheduled execution of an operation."""

    order_id: str
    operation_id: str
    machine_id: str
    start: datetime
    end: datetime
    exceeds_capacity: bool = False
    order_priority: OrderPriority = OrderPriority.NORMAL


@dataclass(slots=True)
class MachineSchedule:
    """Keeps track of bookings for a single machine."""

    machine: Machine
    calendar: Optional[ShiftCalendar]
    next_available: datetime
    total_allocated_hours: float = 0.0
    operations: List[ScheduledOperation] = field(default_factory=list)

    def allocate(
        self,
        order_id: str,
        operation: Operation,
        earliest_start: datetime,
        priority: OrderPriority,
        *,
        setup_time_factor: float = 1.0,
        gap_minutes: int = 0,
    ) -> ScheduledOperation:
        start_candidate = max(self.next_available, earliest_start)
        setup_hours = max(operation.setup_time_hours * setup_time_factor, 0.0)
        duration = operation.duration_hours + setup_hours
        if duration <= 0:
            raise ValueError("Operation duration must be positive")
        if self.calendar is not None:
            start_time, end_time = _allocate_with_calendar(
                self.calendar, start_candidate, duration
            )
        else:
            start_time = start_candidate
            end_time = start_time + timedelta(hours=duration)
        gap_delta = timedelta(minutes=gap_minutes) if gap_minutes > 0 else timedelta(0)
        self.next_available = end_time + gap_delta
        self.total_allocated_hours += duration
        scheduled = ScheduledOperation(
            order_id=order_id,
            operation_id=operation.id,
            machine_id=self.machine.id,
            start=start_time,
            end=end_time,
            exceeds_capacity=self.total_allocated_hours > self.machine.capacity_hours_per_week,
            order_priority=priority,
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
    recommended_supplier_id: Optional[str] = None
    recommended_supplier_name: str = ""


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
        supplier_repo: Optional[InMemoryRepository[Supplier]] = None,
        purchase_order_repo: Optional[InMemoryRepository[PurchaseOrder]] = None,
        supplier_evaluation_repo: Optional[
            InMemoryRepository[SupplierEvaluation]
        ] = None,
        shift_calendar_repo: Optional[InMemoryRepository[ShiftCalendar]] = None,
    ) -> None:
        self.customers = customer_repo or InMemoryRepository()
        self.machines = machine_repo or InMemoryRepository()
        self.orders = order_repo or InMemoryRepository()
        self.inventory = inventory_repo or InMemoryRepository()
        self.time_tracking = time_tracking_repo or InMemoryRepository()
        self.suppliers = supplier_repo or InMemoryRepository()
        self.purchase_orders = purchase_order_repo or InMemoryRepository()
        self.supplier_evaluations = (
            supplier_evaluation_repo or InMemoryRepository()
        )
        self.shift_calendars = shift_calendar_repo or InMemoryRepository()
        self._machine_schedules: Dict[str, MachineSchedule] = {}
        self.planning_options = PlanningOptions()
        self.procurement_options = ProcurementOptions()

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
        shift_calendar_id: Optional[str] = None,
    ) -> Machine:
        if not processes:
            raise ValueError("A machine must support at least one manufacturing process")
        if shift_calendar_id is not None and shift_calendar_id not in self.shift_calendars:
            raise RecordNotFoundError(
                f"Shift calendar {shift_calendar_id!r} does not exist"
            )
        machine = Machine(
            id=str(uuid4()),
            name=name,
            processes=tuple(dict.fromkeys(processes)),
            capacity_hours_per_week=capacity_hours_per_week,
            location=location,
            manufacturer=manufacturer,
            notes=notes,
            shift_calendar_id=shift_calendar_id,
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
    # Shift calendar management
    # ------------------------------------------------------------------
    def create_shift_calendar(
        self,
        name: str,
        shifts: Sequence[Shift],
        *,
        non_working_days: Optional[Sequence[date]] = None,
    ) -> ShiftCalendar:
        if not shifts:
            raise ValueError("A shift calendar must contain at least one shift")
        calendar = ShiftCalendar(
            id=str(uuid4()),
            name=name,
            shifts=list(shifts),
            non_working_days=set(non_working_days or ()),
        )
        self.shift_calendars.add(calendar.id, calendar)
        return calendar

    def assign_shift_calendar(self, machine_id: str, calendar_id: str) -> Machine:
        machine = self.machines.get(machine_id)
        calendar = self.shift_calendars.get(calendar_id)
        machine.shift_calendar_id = calendar.id
        self.machines.upsert(machine.id, machine)
        schedule = self._machine_schedules.get(machine_id)
        if schedule is not None:
            schedule.calendar = calendar
        return machine

    def add_non_working_day(self, calendar_id: str, day: date) -> ShiftCalendar:
        calendar = self.shift_calendars.get(calendar_id)
        calendar.non_working_days.add(day)
        self.shift_calendars.upsert(calendar.id, calendar)
        for schedule in self._machine_schedules.values():
            if schedule.machine.shift_calendar_id == calendar_id:
                schedule.calendar = calendar
        return calendar

    # ------------------------------------------------------------------
    # Supplier management and purchasing
    # ------------------------------------------------------------------
    def register_supplier(
        self,
        name: str,
        address: str,
        *,
        contact_person: str = "",
        contact_email: str = "",
        contact_phone: str = "",
        process_capabilities: Optional[Sequence[ManufacturingProcess]] = None,
        material_item_ids: Optional[Sequence[str]] = None,
    ) -> Supplier:
        supplier = Supplier(
            id=str(uuid4()),
            name=name,
            address=address,
            contact_person=contact_person,
            contact_email=contact_email,
            contact_phone=contact_phone,
            process_capabilities=tuple(dict.fromkeys(process_capabilities or ())),
            material_item_ids=tuple(dict.fromkeys(material_item_ids or ())),
        )
        self.suppliers.add(supplier.id, supplier)
        return supplier

    def link_supplier_to_material(self, supplier_id: str, item_id: str) -> Supplier:
        supplier = self.suppliers.get(supplier_id)
        if item_id not in self.inventory:
            raise RecordNotFoundError(f"Inventory item {item_id!r} not found")
        if item_id in supplier.material_item_ids:
            return supplier
        supplier.material_item_ids = tuple((*supplier.material_item_ids, item_id))
        self.suppliers.upsert(supplier.id, supplier)
        return supplier

    def record_supplier_evaluation(
        self,
        supplier_id: str,
        quality_score: float,
        delivery_reliability_score: float,
        communication_score: float,
        *,
        evaluated_on: Optional[date] = None,
        notes: str = "",
    ) -> SupplierEvaluation:
        supplier = self.suppliers.get(supplier_id)
        evaluated_on = evaluated_on or date.today()
        overall = (
            quality_score + delivery_reliability_score + communication_score
        ) / 3.0
        evaluation = SupplierEvaluation(
            id=str(uuid4()),
            supplier_id=supplier_id,
            evaluated_on=evaluated_on,
            quality_score=quality_score,
            delivery_reliability_score=delivery_reliability_score,
            communication_score=communication_score,
            overall_score=overall,
            notes=notes,
        )
        self.supplier_evaluations.add(evaluation.id, evaluation)
        total = supplier.rating * supplier.rating_count + overall
        supplier.rating_count += 1
        supplier.rating = total / float(supplier.rating_count)
        self.suppliers.upsert(supplier.id, supplier)
        return evaluation

    def recommend_supplier_for_item(self, item_id: str) -> Optional[Supplier]:
        candidates = [
            supplier
            for supplier in self.suppliers
            if item_id in supplier.material_item_ids
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda supplier: supplier.rating, reverse=True)
        return candidates[0]

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
        priority: OrderPriority = OrderPriority.NORMAL,
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
            priority=priority,
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
    def reset_machine_schedules(self) -> None:
        """Clear cached machine schedules to rebuild planning from scratch."""

        self._machine_schedules.clear()

    def update_planning_options(
        self,
        *,
        priority_weight: float,
        due_date_weight: float,
        horizon_days: int,
        max_orders_per_cycle: int,
        auto_release_orders: bool,
        default_start_time: time,
        setup_time_factor: float,
        gap_between_operations_minutes: int,
    ) -> PlanningOptions:
        """Apply new fine-tuning parameters for scheduling."""

        self.planning_options = PlanningOptions(
            priority_weight=max(priority_weight, 0.01),
            due_date_weight=max(due_date_weight, 0.0),
            horizon_days=max(horizon_days, 0),
            max_orders_per_cycle=max(max_orders_per_cycle, 0),
            auto_release_orders=auto_release_orders,
            default_start_time=default_start_time,
            setup_time_factor=max(setup_time_factor, 0.0),
            gap_between_operations_minutes=max(gap_between_operations_minutes, 0),
        )
        self.reset_machine_schedules()
        return self.planning_options

    def update_procurement_options(
        self,
        *,
        reorder_multiplier: float,
        include_safety_stock_gap: bool,
        expedite_high_priority_days: int,
        default_lead_time_days: int,
        auto_create_orders: bool,
    ) -> ProcurementOptions:
        """Persist procurement configuration."""

        self.procurement_options = ProcurementOptions(
            reorder_multiplier=max(reorder_multiplier, 0.0),
            include_safety_stock_gap=include_safety_stock_gap,
            expedite_high_priority_days=max(expedite_high_priority_days, 0),
            default_lead_time_days=max(default_lead_time_days, 0),
            auto_create_orders=auto_create_orders,
        )
        return self.procurement_options

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
            calendar = None
            if machine.shift_calendar_id:
                try:
                    calendar = self.shift_calendars.get(machine.shift_calendar_id)
                except RecordNotFoundError:
                    calendar = None
            schedule = MachineSchedule(
                machine=machine,
                calendar=calendar,
                next_available=start_reference,
            )
            self._machine_schedules[machine_id] = schedule
        return schedule

    def schedule_operations(
        self,
        order_id: str,
        *,
        start_reference: Optional[datetime] = None,
    ) -> ScheduleSummary:
        order = self.orders.get(order_id)
        options = self.planning_options
        default_start = options.default_start_time or DEFAULT_SHIFT_START
        start_reference = start_reference or datetime.combine(date.today(), default_start)
        earliest_start = start_reference
        setup_factor = max(options.setup_time_factor, 0.0)
        gap_minutes = max(options.gap_between_operations_minutes, 0)
        gap_delta = timedelta(minutes=gap_minutes) if gap_minutes > 0 else timedelta(0)
        scheduled_operations: List[ScheduledOperation] = []
        used_machine_ids: List[str] = []

        for plan in order.operations:
            machines = self._eligible_machines(plan.operation.process)
            candidate_schedules = [
                self._get_machine_schedule(machine.id, start_reference) for machine in machines
            ]
            candidate_schedules.sort(key=lambda schedule: schedule.total_allocated_hours)
            schedule = candidate_schedules[0]
            scheduled = schedule.allocate(
                order.id,
                plan.operation,
                earliest_start,
                order.priority,
                setup_time_factor=setup_factor,
                gap_minutes=gap_minutes,
            )
            plan.assigned_machine_id = scheduled.machine_id
            plan.scheduled_start = scheduled.start
            plan.scheduled_end = scheduled.end
            scheduled_operations.append(scheduled)
            used_machine_ids.append(schedule.machine.id)
            earliest_start = scheduled.end + gap_delta

        self.orders.upsert(order.id, order)
        if options.auto_release_orders and order.status == OrderStatus.PLANNED:
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

    def schedule_backlog(
        self,
        *,
        start_reference: Optional[datetime] = None,
        horizon_days: Optional[int] = None,
        max_orders: Optional[int] = None,
    ) -> Mapping[str, ScheduleSummary]:
        """Schedule all open orders using the configured planning options."""

        self.reset_machine_schedules()
        options = self.planning_options
        default_start = options.default_start_time or DEFAULT_SHIFT_START
        start_reference = start_reference or datetime.combine(
            date.today(), default_start
        )
        horizon = (
            options.horizon_days if horizon_days is None else max(horizon_days, 0)
        )
        limit = (
            options.max_orders_per_cycle
            if max_orders is None
            else max(max_orders, 0)
        )
        priority_weight = max(options.priority_weight, 0.01)
        due_weight = max(options.due_date_weight, 0.0)
        backlog_orders = [
            order
            for order in self.orders
            if order.status not in {OrderStatus.COMPLETED, OrderStatus.CANCELLED}
        ]
        if horizon > 0:
            horizon_date = date.today() + timedelta(days=horizon)
            backlog_orders = [
                order
                for order in backlog_orders
                if order.due_date <= horizon_date
                or order.priority >= OrderPriority.HIGH
            ]

        def backlog_key(order: ProductionOrder) -> Tuple[float, float, datetime]:
            priority_score = -int(order.priority) * priority_weight
            due_date_score = order.due_date.toordinal() * due_weight
            return (priority_score, due_date_score, order.created_at)

        backlog_orders.sort(key=backlog_key)
        if limit > 0:
            backlog_orders = backlog_orders[:limit]
        summaries: Dict[str, ScheduleSummary] = {}
        for order in backlog_orders:
            summaries[order.id] = self.schedule_operations(
                order.id, start_reference=start_reference
            )
        return summaries

    def get_upcoming_operations(self, *, limit: int = 10) -> List[ScheduledOperation]:
        """Return upcoming scheduled operations ordered by start time."""

        operations: List[ScheduledOperation] = []
        for order in self.orders:
            for plan in order.operations:
                if (
                    plan.scheduled_start is not None
                    and plan.scheduled_end is not None
                    and plan.assigned_machine_id is not None
                ):
                    operations.append(
                        ScheduledOperation(
                            order_id=order.id,
                            operation_id=plan.operation.id,
                            machine_id=plan.assigned_machine_id,
                            start=plan.scheduled_start,
                            end=plan.scheduled_end,
                            exceeds_capacity=False,
                            order_priority=order.priority,
                        )
                    )
        operations.sort(key=lambda op: op.start)
        return operations[:limit] if limit else operations

    # ------------------------------------------------------------------
    # Material management
    # ------------------------------------------------------------------
    def material_shortage_report(
        self,
        order_id: str,
        *,
        include_safety_stock: Optional[bool] = None,
        reorder_multiplier: Optional[float] = None,
    ) -> List[MaterialShortage]:
        order = self.orders.get(order_id)
        aggregated_requirements: Dict[str, float] = {}
        for plan in order.operations:
            for requirement in plan.operation.materials:
                aggregated_requirements[requirement.item_id] = aggregated_requirements.get(
                    requirement.item_id, 0.0
                ) + requirement.quantity

        shortages: List[MaterialShortage] = []
        options = self.procurement_options
        include_safety = (
            options.include_safety_stock_gap
            if include_safety_stock is None
            else include_safety_stock
        )
        multiplier = (
            options.reorder_multiplier
            if reorder_multiplier is None
            else reorder_multiplier
        )
        multiplier = max(multiplier, 0.0)
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
            safety_gap = item.safety_stock - projected_on_hand if include_safety else 0.0
            shortage = max(0.0, safety_gap)
            reorder_trigger = item.reorder_point - projected_on_hand
            reorder_recommendation = max(shortage, reorder_trigger, 0.0) * multiplier
            if shortage > 0 or projected_on_hand < item.reorder_point:
                supplier = self.recommend_supplier_for_item(item.id)
                shortages.append(
                    MaterialShortage(
                        item_id=item.id,
                        name=item.name,
                        required_quantity=required_quantity,
                        projected_on_hand=projected_on_hand,
                        shortage=shortage,
                        reorder_recommendation=reorder_recommendation,
                        recommended_supplier_id=supplier.id if supplier else None,
                        recommended_supplier_name=supplier.name if supplier else "",
                    )
                )
        return shortages

    def plan_material_purchases(
        self,
        order_id: str,
        *,
        auto_create: Optional[bool] = None,
        reorder_multiplier: Optional[float] = None,
        include_safety_stock: Optional[bool] = None,
        expedite_high_priority_days: Optional[int] = None,
    ) -> List[PurchaseOrder]:
        order = self.orders.get(order_id)
        options = self.procurement_options
        auto_create_flag = (
            options.auto_create_orders if auto_create is None else auto_create
        )
        multiplier = (
            options.reorder_multiplier
            if reorder_multiplier is None
            else reorder_multiplier
        )
        multiplier = max(multiplier, 0.0)
        include_safety = (
            options.include_safety_stock_gap
            if include_safety_stock is None
            else include_safety_stock
        )
        expedite_days = (
            options.expedite_high_priority_days
            if expedite_high_priority_days is None
            else max(expedite_high_priority_days, 0)
        )
        default_lead_time = max(options.default_lead_time_days, 0)
        shortages = self.material_shortage_report(
            order_id,
            include_safety_stock=include_safety,
            reorder_multiplier=multiplier,
        )
        planned: List[PurchaseOrder] = []
        for shortage in shortages:
            if shortage.reorder_recommendation <= 0 and shortage.shortage <= 0:
                continue
            try:
                item = self.inventory.get(shortage.item_id)
            except RecordNotFoundError:
                continue
            supplier = None
            if shortage.recommended_supplier_id:
                try:
                    supplier = self.suppliers.get(shortage.recommended_supplier_id)
                except RecordNotFoundError:
                    supplier = None
            if supplier is None:
                supplier = self.recommend_supplier_for_item(item.id)
            if supplier is None:
                continue
            quantity = max(shortage.reorder_recommendation, shortage.shortage)
            base_lead_time = item.lead_time_days or default_lead_time
            base_lead_time = max(base_lead_time, 1)
            if order.priority >= OrderPriority.HIGH and expedite_days > 0:
                base_lead_time = max(1, base_lead_time - expedite_days)
            expected_receipt = date.today() + timedelta(days=base_lead_time)
            purchase_order = PurchaseOrder(
                id=str(uuid4()),
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                item_id=item.id,
                quantity=quantity,
                expected_receipt=expected_receipt,
                status="Open" if auto_create_flag else "Planned",
                notes=f"Automatisch geplant für Auftrag {order.reference}",
            )
            if auto_create_flag:
                self.purchase_orders.add(purchase_order.id, purchase_order)
            planned.append(purchase_order)
        return planned

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
    "PlanningOptions",
    "ProcurementOptions",
]
