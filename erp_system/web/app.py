"""FastAPI-based web interface for the ERP system."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..domain import (
    ManufacturingProcess,
    OrderPriority,
    OrderStatus,
    Shift,
)
from ..repository import RecordNotFoundError
from ..services import ERPService
from ..storage import ERPDatabase

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app(database_path: str = "erp.sqlite3") -> FastAPI:
    database = ERPDatabase(database_path)
    service = ERPService(
        customer_repo=database.customers,
        machine_repo=database.machines,
        order_repo=database.orders,
        inventory_repo=database.inventory,
        time_tracking_repo=database.time_tracking,
        supplier_repo=database.suppliers,
        purchase_order_repo=database.purchase_orders,
        supplier_evaluation_repo=database.supplier_evaluations,
        shift_calendar_repo=database.shift_calendars,
    )
    ensure_demo_data(service)

    app = FastAPI(title="Sondermaschinenbau ERP")
    app.state.erp_service = service
    app.state.database = database

    @app.on_event("shutdown")
    async def shutdown_event() -> None:  # pragma: no cover - framework hook
        database.close()

    @app.get("/")
    async def dashboard(request: Request):
        service: ERPService = request.app.state.erp_service
        orders = sorted(
            service.orders.list(),
            key=lambda order: (order.due_date, -int(order.priority)),
        )
        customers = service.customers.list()
        machines = service.machines.list()
        calendars = service.shift_calendars.list()
        inventory = service.inventory.list()
        purchase_orders = sorted(
            service.purchase_orders.list(), key=lambda po: po.expected_receipt
        )
        suppliers = service.suppliers.list()
        shortages = []
        for order in orders:
            if order.status in {OrderStatus.PLANNED, OrderStatus.RELEASED}:
                shortages.extend(service.material_shortage_report(order.id))
        upcoming = service.get_upcoming_operations(limit=10)
        backlog_preview = sorted(
            (
                (
                    order,
                    max(
                        (plan for plan in order.operations if plan.scheduled_end),
                        key=lambda plan: plan.scheduled_end,
                        default=None,
                    ),
                )
                for order in orders
                if any(plan.scheduled_start for plan in order.operations)
            ),
            key=lambda entry: entry[1].scheduled_end if entry[1] else datetime.max,
        )
        low_stock = [
            item
            for item in inventory
            if item.quantity_on_hand < max(item.reorder_point, item.safety_stock)
        ]
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "orders": orders,
                "customers": customers,
                "machines": machines,
                "inventory": inventory,
                "purchase_orders": purchase_orders,
                "suppliers": suppliers,
                "shortages": shortages,
                "upcoming": upcoming,
                "backlog_preview": backlog_preview,
                "low_stock": low_stock,
            },
        )

    @app.post("/schedule/backlog")
    async def schedule_backlog(request: Request):
        service: ERPService = request.app.state.erp_service
        service.schedule_backlog()
        return RedirectResponse("/", status_code=303)

    @app.get("/planning")
    async def planning_overview(request: Request):
        service: ERPService = request.app.state.erp_service
        options = service.planning_options
        procurement_options = service.procurement_options
        all_orders = service.orders.list()
        orders = [
            order
            for order in all_orders
            if order.status not in {OrderStatus.COMPLETED, OrderStatus.CANCELLED}
        ]
        orders.sort(
            key=lambda order: (-int(order.priority), order.due_date, order.created_at)
        )
        customers = service.customers.list()
        machines = service.machines.list()
        calendars = service.shift_calendars.list()
        upcoming = service.get_upcoming_operations(limit=25)
        query = request.query_params
        scheduled_count = query.get("scheduled")
        operations_planned = query.get("operations")
        overloaded_count = query.get("overloads")
        purchase_created = query.get("purchases")
        return templates.TemplateResponse(
            "planning.html",
            {
                "request": request,
                "planning_options": options,
                "orders": orders,
                "all_orders": all_orders,
                "customers": customers,
                "machines": machines,
                "calendars": calendars,
                "upcoming": upcoming,
                "procurement_options": procurement_options,
                "scheduled_count": int(scheduled_count)
                if scheduled_count
                else None,
                "operations_planned": int(operations_planned)
                if operations_planned
                else None,
                "overloaded_count": int(overloaded_count)
                if overloaded_count
                else None,
                "purchase_created": int(purchase_created)
                if purchase_created
                else None,
                "options_updated": "options" in query,
            },
        )

    @app.post("/planning/options")
    async def update_planning_options(
        request: Request,
        priority_weight: float = Form(...),
        due_date_weight: float = Form(...),
        horizon_days: int = Form(0),
        max_orders_per_cycle: int = Form(0),
        default_start_time: str = Form("06:00"),
        setup_time_factor: float = Form(1.0),
        gap_between_operations_minutes: int = Form(0),
        auto_release_orders: Optional[str] = Form(None),
    ):
        service: ERPService = request.app.state.erp_service
        try:
            start_time = datetime.strptime(default_start_time, "%H:%M").time()
        except ValueError:
            start_time = service.planning_options.default_start_time
        service.update_planning_options(
            priority_weight=priority_weight,
            due_date_weight=due_date_weight,
            horizon_days=horizon_days,
            max_orders_per_cycle=max_orders_per_cycle,
            auto_release_orders=auto_release_orders is not None,
            default_start_time=start_time,
            setup_time_factor=setup_time_factor,
            gap_between_operations_minutes=gap_between_operations_minutes,
        )
        redirect = "/planning?" + urlencode({"options": "updated"})
        return RedirectResponse(redirect, status_code=303)

    @app.post("/planning/run")
    async def run_planning(
        request: Request,
        start_date: Optional[str] = Form(None),
        start_time_value: Optional[str] = Form(None),
        horizon_override: Optional[str] = Form(None),
        max_orders: Optional[str] = Form(None),
        plan_purchases: Optional[str] = Form(None),
        auto_create_purchases: Optional[str] = Form(None),
    ):
        service: ERPService = request.app.state.erp_service
        start_reference: Optional[datetime] = None
        if start_date:
            try:
                date_part = datetime.strptime(start_date, "%Y-%m-%d").date()
                time_text = (
                    start_time_value
                    if start_time_value
                    else service.planning_options.default_start_time.strftime("%H:%M")
                )
                time_part = datetime.strptime(time_text, "%H:%M").time()
                start_reference = datetime.combine(date_part, time_part)
            except ValueError:
                start_reference = None
        horizon_value: Optional[int] = None
        if horizon_override:
            try:
                horizon_value = max(int(horizon_override), 0)
            except ValueError:
                horizon_value = None
        max_orders_value: Optional[int] = None
        if max_orders:
            try:
                max_orders_value = max(int(max_orders), 0)
            except ValueError:
                max_orders_value = None
        summaries = service.schedule_backlog(
            start_reference=start_reference,
            horizon_days=horizon_value,
            max_orders=max_orders_value,
        )
        scheduled_count = len(summaries)
        operations_planned = sum(
            len(summary.scheduled_operations) for summary in summaries.values()
        )
        overloaded_machines = {
            machine_id
            for summary in summaries.values()
            for machine_id in summary.overloaded_machines
        }
        purchase_created = 0
        if plan_purchases is not None:
            auto_create_flag = (
                auto_create_purchases is not None
            )
            for summary in summaries.values():
                planned = service.plan_material_purchases(
                    summary.order_id,
                    auto_create=auto_create_flag,
                )
                purchase_created += len(planned)
        params = {
            "scheduled": scheduled_count,
            "operations": operations_planned,
        }
        if overloaded_machines:
            params["overloads"] = len(overloaded_machines)
        if purchase_created:
            params["purchases"] = purchase_created
        redirect = "/planning"
        if params:
            redirect += "?" + urlencode(params)
        return RedirectResponse(redirect, status_code=303)

    @app.post("/orders/{order_id}/schedule")
    async def schedule_order(order_id: str, request: Request):
        service: ERPService = request.app.state.erp_service
        service.schedule_operations(order_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/orders/{order_id}/plan-purchase")
    async def plan_purchase(order_id: str, request: Request):
        service: ERPService = request.app.state.erp_service
        service.plan_material_purchases(order_id, auto_create=True)
        return RedirectResponse("/", status_code=303)

    @app.get("/suppliers")
    async def supplier_overview(request: Request):
        service: ERPService = request.app.state.erp_service
        suppliers = sorted(
            service.suppliers.list(), key=lambda supplier: supplier.name.lower()
        )
        default_supplier_id = suppliers[0].id if suppliers else ""
        inventory = service.inventory.list()
        evaluations = sorted(
            service.supplier_evaluations.list(),
            key=lambda evaluation: evaluation.evaluated_on,
            reverse=True,
        )
        return templates.TemplateResponse(
            "suppliers.html",
            {
                "request": request,
                "suppliers": suppliers,
                "default_supplier_id": default_supplier_id,
                "inventory": inventory,
                "evaluations": evaluations,
                "processes": ManufacturingProcess,
            },
        )

    @app.post("/suppliers")
    async def create_supplier(
        request: Request,
        name: str = Form(...),
        address: str = Form(...),
        contact_person: str = Form(""),
        contact_email: str = Form(""),
        contact_phone: str = Form(""),
        process_capabilities: str = Form(""),
        material_item_ids: str = Form(""),
    ):
        service: ERPService = request.app.state.erp_service
        processes = parse_processes(process_capabilities)
        materials = [item_id for item_id in split_csv(material_item_ids)]
        service.register_supplier(
            name=name,
            address=address,
            contact_person=contact_person,
            contact_email=contact_email,
            contact_phone=contact_phone,
            process_capabilities=processes,
            material_item_ids=materials,
        )
        return RedirectResponse("/suppliers", status_code=303)

    @app.post("/suppliers/{supplier_id}/evaluation")
    async def add_supplier_evaluation(
        supplier_id: str,
        request: Request,
        quality_score: float = Form(...),
        delivery_reliability_score: float = Form(...),
        communication_score: float = Form(...),
        evaluated_on: Optional[str] = Form(None),
        notes: str = Form(""),
    ):
        service: ERPService = request.app.state.erp_service
        evaluation_date = (
            datetime.strptime(evaluated_on, "%Y-%m-%d").date()
            if evaluated_on
            else None
        )
        service.record_supplier_evaluation(
            supplier_id=supplier_id,
            quality_score=quality_score,
            delivery_reliability_score=delivery_reliability_score,
            communication_score=communication_score,
            evaluated_on=evaluation_date,
            notes=notes,
        )
        return RedirectResponse("/suppliers", status_code=303)

    @app.post("/suppliers/{supplier_id}/materials")
    async def add_supplier_material(
        supplier_id: str,
        request: Request,
        item_id: str = Form(...),
    ):
        service: ERPService = request.app.state.erp_service
        try:
            service.link_supplier_to_material(supplier_id, item_id)
        except RecordNotFoundError:
            pass
        return RedirectResponse("/suppliers", status_code=303)

    @app.get("/procurement")
    async def procurement_overview(request: Request):
        service: ERPService = request.app.state.erp_service
        options = service.procurement_options
        orders = [
            order
            for order in service.orders.list()
            if order.status != OrderStatus.CANCELLED
        ]
        orders.sort(key=lambda order: (order.due_date, -int(order.priority)))
        selected_order_id = request.query_params.get("order_id")
        if not selected_order_id and orders:
            selected_order_id = orders[0].id
        shortages: List = []
        selected_order = None
        if selected_order_id:
            try:
                selected_order = service.orders.get(selected_order_id)
                shortages = service.material_shortage_report(selected_order_id)
            except RecordNotFoundError:
                selected_order = None
                shortages = []
        purchase_orders = sorted(
            service.purchase_orders.list(), key=lambda po: po.expected_receipt
        )
        inventory = service.inventory.list()
        query = request.query_params
        planned_count = query.get("planned")
        created_count = query.get("created")
        return templates.TemplateResponse(
            "procurement.html",
            {
                "request": request,
                "procurement_options": options,
                "orders": orders,
                "selected_order_id": selected_order_id,
                "selected_order": selected_order,
                "shortages": shortages,
                "purchase_orders": purchase_orders,
                "inventory": inventory,
                "planned_count": int(planned_count) if planned_count else None,
                "created_count": int(created_count) if created_count else None,
                "options_updated": "options" in query,
            },
        )

    @app.post("/procurement/options")
    async def update_procurement_options(
        request: Request,
        reorder_multiplier: float = Form(...),
        include_safety_stock: Optional[str] = Form(None),
        expedite_high_priority_days: int = Form(0),
        default_lead_time_days: int = Form(0),
        auto_create_orders: Optional[str] = Form(None),
    ):
        service: ERPService = request.app.state.erp_service
        service.update_procurement_options(
            reorder_multiplier=reorder_multiplier,
            include_safety_stock_gap=include_safety_stock is not None,
            expedite_high_priority_days=expedite_high_priority_days,
            default_lead_time_days=default_lead_time_days,
            auto_create_orders=auto_create_orders is not None,
        )
        redirect = "/procurement?" + urlencode({"options": "updated"})
        return RedirectResponse(redirect, status_code=303)

    @app.post("/procurement/order/{order_id}/plan")
    async def plan_procurement_for_order(
        order_id: str,
        request: Request,
        reorder_multiplier: str = Form(""),
        include_safety_stock_override: str = Form("inherit"),
        expedite_high_priority_days: str = Form(""),
        auto_create_override: str = Form("inherit"),
    ):
        service: ERPService = request.app.state.erp_service
        try:
            service.orders.get(order_id)
        except RecordNotFoundError:
            return RedirectResponse("/procurement", status_code=303)
        multiplier_value: Optional[float] = None
        if reorder_multiplier:
            try:
                multiplier_value = float(reorder_multiplier)
            except ValueError:
                multiplier_value = None
        include_value: Optional[bool]
        if include_safety_stock_override == "inherit":
            include_value = None
        else:
            include_value = include_safety_stock_override == "yes"
        auto_create_value: Optional[bool]
        if auto_create_override == "inherit":
            auto_create_value = None
        else:
            auto_create_value = auto_create_override == "yes"
        expedite_value: Optional[int] = None
        if expedite_high_priority_days:
            try:
                expedite_value = max(int(expedite_high_priority_days), 0)
            except ValueError:
                expedite_value = None
        planned = service.plan_material_purchases(
            order_id,
            auto_create=auto_create_value,
            reorder_multiplier=multiplier_value,
            include_safety_stock=include_value,
            expedite_high_priority_days=expedite_value,
        )
        options = service.procurement_options
        actual_auto_create = (
            auto_create_value if auto_create_value is not None else options.auto_create_orders
        )
        params = {
            "order_id": order_id,
            "planned": len(planned),
        }
        if actual_auto_create and planned:
            params["created"] = len(planned)
        redirect = "/procurement"
        if params:
            redirect += "?" + urlencode(params)
        return RedirectResponse(redirect, status_code=303)

    @app.get("/calendars")
    async def calendar_overview(request: Request):
        service: ERPService = request.app.state.erp_service
        calendars = service.shift_calendars.list()
        machines = service.machines.list()
        return templates.TemplateResponse(
            "calendars.html",
            {
                "request": request,
                "calendars": calendars,
                "machines": machines,
            },
        )

    @app.post("/calendars")
    async def create_calendar(
        request: Request,
        name: str = Form(...),
        shift_definitions: str = Form(...),
        non_working_days: str = Form(""),
    ):
        service: ERPService = request.app.state.erp_service
        shifts = parse_shift_definitions(shift_definitions)
        if not shifts:
            return RedirectResponse("/calendars", status_code=303)
        days = []
        for token in split_csv(non_working_days):
            try:
                days.append(datetime.strptime(token, "%Y-%m-%d").date())
            except ValueError:
                continue
        service.create_shift_calendar(name=name, shifts=shifts, non_working_days=days)
        return RedirectResponse("/calendars", status_code=303)

    @app.post("/machines/{machine_id}/calendar")
    async def assign_calendar(machine_id: str, request: Request, calendar_id: str = Form(...)):
        service: ERPService = request.app.state.erp_service
        try:
            service.assign_shift_calendar(machine_id, calendar_id)
        except RecordNotFoundError:
            pass
        return RedirectResponse("/calendars", status_code=303)

    @app.post("/calendars/{calendar_id}/non-working-day")
    async def add_holiday(calendar_id: str, request: Request, day: str = Form(...)):
        service: ERPService = request.app.state.erp_service
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").date()
            service.add_non_working_day(calendar_id, parsed)
        except (ValueError, RecordNotFoundError):
            pass
        return RedirectResponse("/calendars", status_code=303)

    return app


def split_csv(values: str) -> List[str]:
    return [value.strip() for value in values.split(",") if value.strip()]


def parse_processes(value: str) -> Sequence[ManufacturingProcess]:
    processes: List[ManufacturingProcess] = []
    for token in split_csv(value):
        for process in ManufacturingProcess:
            if token.lower() in {process.value.lower(), process.name.lower()}:
                processes.append(process)
                break
    return processes


def parse_shift_definitions(definitions: str) -> List[Shift]:
    shifts: List[Shift] = []
    for line in definitions.splitlines():
        if not line.strip():
            continue
        try:
            name, start_str, end_str, weekdays_str = [part.strip() for part in line.split("|")]
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            weekdays = tuple(int(value) for value in weekdays_str.split(",") if value)
            shifts.append(Shift(name=name, start_time=start_time, end_time=end_time, weekdays=weekdays))
        except ValueError:
            continue
    return shifts


def ensure_demo_data(service: ERPService) -> None:
    if len(service.customers) > 0:
        return

    day_shift = service.create_shift_calendar(
        name="Standard Zweischicht",
        shifts=[
            Shift(
                name="Frühschicht",
                start_time=time(6, 0),
                end_time=time(14, 0),
                weekdays=tuple(range(0, 5)),
            ),
            Shift(
                name="Spätschicht",
                start_time=time(14, 0),
                end_time=time(22, 0),
                weekdays=tuple(range(0, 5)),
            ),
        ],
    )

    customer = service.create_customer(
        name="Sondermaschinen Müller GmbH",
        address="Werkstraße 12, 32547 Bad Oeynhausen",
        contact_person="Sabine Hartmann",
        contact_email="s.hartmann@sondermueller.de",
        contact_phone="+49 5731 12345",
        industry="Automotive",
    )

    machines = [
        service.register_machine(
            name="DMG MORI CTX beta 800",
            processes=[ManufacturingProcess.TURNING],
            capacity_hours_per_week=45,
            location="Fertigungshalle A",
            manufacturer="DMG MORI",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Hermle C 42 U",
            processes=[ManufacturingProcess.MILLING],
            capacity_hours_per_week=50,
            location="Fertigungshalle A",
            manufacturer="Hermle",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Trumpf TruLaser 3030",
            processes=[ManufacturingProcess.LASER_CUTTING],
            capacity_hours_per_week=60,
            location="Blechzentrum",
            manufacturer="Trumpf",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Trumpf TruBend 5230",
            processes=[ManufacturingProcess.BENDING],
            capacity_hours_per_week=40,
            location="Blechzentrum",
            manufacturer="Trumpf",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Fronius TPSi 400",
            processes=[ManufacturingProcess.WELDING],
            capacity_hours_per_week=38,
            location="Schweißerei",
            manufacturer="Fronius",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Jung J630",
            processes=[ManufacturingProcess.GRINDING],
            capacity_hours_per_week=32,
            location="Finish-Bereich",
            manufacturer="Jung",
            shift_calendar_id=day_shift.id,
        ),
        service.register_machine(
            name="Behringer HBP 413 A",
            processes=[ManufacturingProcess.SAWING],
            capacity_hours_per_week=28,
            location="Sägezentrum",
            manufacturer="Behringer",
            shift_calendar_id=day_shift.id,
        ),
    ]

    sheet_steel = service.register_inventory_item(
        name="Feinblech S355",
        unit_of_measure="kg",
        quantity_on_hand=180.0,
        safety_stock=80.0,
        reorder_point=100.0,
        lead_time_days=5,
    )
    round_stock = service.register_inventory_item(
        name="Rundmaterial 42CrMo4",
        unit_of_measure="kg",
        quantity_on_hand=120.0,
        safety_stock=60.0,
        reorder_point=90.0,
        lead_time_days=7,
    )
    welding_wire = service.register_inventory_item(
        name="Schweißdraht G3Si1",
        unit_of_measure="kg",
        quantity_on_hand=35.0,
        safety_stock=20.0,
        reorder_point=25.0,
        lead_time_days=3,
    )

    steel_supplier = service.register_supplier(
        name="Stahlhandel Westfalen GmbH",
        address="Industriestraße 5, 44147 Dortmund",
        contact_person="Peter König",
        contact_email="verkauf@stahlwestfalen.de",
        contact_phone="+49 231 98765",
        material_item_ids=[sheet_steel.id, round_stock.id],
    )
    service.record_supplier_evaluation(
        supplier_id=steel_supplier.id,
        quality_score=4.5,
        delivery_reliability_score=4.7,
        communication_score=4.2,
        notes="Zuverlässige Lieferungen",
    )
    welding_supplier = service.register_supplier(
        name="Schweißtechnik OWL",
        address="Im Gewerbepark 7, 32760 Detmold",
        contact_person="Anja Krüger",
        contact_email="service@schweisstechnik-owl.de",
        contact_phone="+49 5231 445566",
        material_item_ids=[welding_wire.id],
    )
    service.record_supplier_evaluation(
        supplier_id=welding_supplier.id,
        quality_score=4.8,
        delivery_reliability_score=4.6,
        communication_score=4.9,
        notes="Gute Kommunikation",
    )

    operations_primary = [
        service.build_operation(
            name="Zuschnitt sägen",
            process=ManufacturingProcess.SAWING,
            duration_hours=1.5,
            setup_time_hours=0.25,
            description="Rohmaterial auf Länge bringen",
            materials=[(round_stock.id, 45.0)],
        ),
        service.build_operation(
            name="Drehen",
            process=ManufacturingProcess.TURNING,
            duration_hours=5.0,
            setup_time_hours=0.5,
            description="Alle Drehoperationen laut Zeichnung",
        ),
        service.build_operation(
            name="Fräsen",
            process=ManufacturingProcess.MILLING,
            duration_hours=4.0,
            setup_time_hours=0.75,
            description="Bearbeitung prismatischer Konturen",
        ),
        service.build_operation(
            name="Laserzuschnitt Blech",
            process=ManufacturingProcess.LASER_CUTTING,
            duration_hours=2.0,
            setup_time_hours=0.25,
            description="Laserschneiden von Blechkomponenten",
            materials=[(sheet_steel.id, 60.0)],
        ),
        service.build_operation(
            name="Kanten",
            process=ManufacturingProcess.BENDING,
            duration_hours=1.0,
            setup_time_hours=0.25,
            description="Abkanten der Blechsegmente",
        ),
        service.build_operation(
            name="Schweißen",
            process=ManufacturingProcess.WELDING,
            duration_hours=3.5,
            setup_time_hours=0.5,
            description="Schweißen der Unterbaugruppen",
            materials=[(welding_wire.id, 8.0)],
        ),
        service.build_operation(
            name="Schleifen",
            process=ManufacturingProcess.GRINDING,
            duration_hours=2.5,
            setup_time_hours=0.25,
            description="Finish der Funktionsflächen",
        ),
    ]

    operations_secondary = [
        service.build_operation(
            name="Rohling sägen",
            process=ManufacturingProcess.SAWING,
            duration_hours=1.0,
            setup_time_hours=0.2,
            description="Zuschnitt für Ersatzteilserie",
            materials=[(round_stock.id, 20.0)],
        ),
        service.build_operation(
            name="Fräsen Kleinteil",
            process=ManufacturingProcess.MILLING,
            duration_hours=2.5,
            setup_time_hours=0.5,
            description="Bearbeitung prismatischer Aufnahmen",
        ),
        service.build_operation(
            name="Schweißen Unterbau",
            process=ManufacturingProcess.WELDING,
            duration_hours=1.0,
            setup_time_hours=0.25,
            description="Heften und Schweißen kleiner Baugruppe",
            materials=[(welding_wire.id, 3.0)],
        ),
    ]

    order_primary = service.create_production_order(
        customer_id=customer.id,
        reference="SO-2024-015",
        due_date=date.today() + timedelta(days=14),
        operations=operations_primary,
        remarks="Komplexer Maschinenträger mit hoher Maßhaltigkeit",
        priority=OrderPriority.HIGH,
    )
    order_secondary = service.create_production_order(
        customer_id=customer.id,
        reference="SO-2024-016",
        due_date=date.today() + timedelta(days=10),
        operations=operations_secondary,
        remarks="Ersatzteilserie für Bestandsmaschine",
        priority=OrderPriority.NORMAL,
    )

    service.schedule_backlog()
    service.plan_material_purchases(order_primary.id, auto_create=True)

