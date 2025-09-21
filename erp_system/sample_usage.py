"""Demonstration script for the special machine builder ERP system."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pprint import pprint
from typing import Dict

from . import ERPService, ManufacturingProcess, OrderPriority, Shift


def main() -> None:
    erp = ERPService()

    day_shift = erp.create_shift_calendar(
        name="Zwei-Schicht-System",
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
    erp.add_non_working_day(day_shift.id, date.today() + timedelta(days=7))

    erp.update_planning_options(
        priority_weight=1.1,
        due_date_weight=0.9,
        horizon_days=21,
        max_orders_per_cycle=0,
        auto_release_orders=True,
        default_start_time=time(6, 0),
        setup_time_factor=1.1,
        gap_between_operations_minutes=15,
    )
    erp.update_procurement_options(
        reorder_multiplier=1.1,
        include_safety_stock_gap=True,
        expedite_high_priority_days=2,
        default_lead_time_days=3,
        auto_create_orders=True,
    )
    print("Planungsparameter:", erp.planning_options)
    print("Beschaffungsparameter:", erp.procurement_options)

    # Stammdaten
    customer = erp.create_customer(
        name="Sondermaschinen Müller GmbH",
        address="Werkstraße 12, 32547 Bad Oeynhausen",
        contact_person="Sabine Hartmann",
        contact_email="s.hartmann@sondermueller.de",
        contact_phone="+49 5731 12345",
        industry="Automotive",
    )

    turning_machine = erp.register_machine(
        name="DMG MORI CTX beta 800",
        processes=[ManufacturingProcess.TURNING],
        capacity_hours_per_week=45,
        location="Fertigungshalle A",
        manufacturer="DMG MORI",
        shift_calendar_id=day_shift.id,
    )
    milling_machine = erp.register_machine(
        name="Hermle C 42 U",
        processes=[ManufacturingProcess.MILLING],
        capacity_hours_per_week=50,
        location="Fertigungshalle A",
        manufacturer="Hermle",
        shift_calendar_id=day_shift.id,
    )
    laser_machine = erp.register_machine(
        name="Trumpf TruLaser 3030",
        processes=[ManufacturingProcess.LASER_CUTTING],
        capacity_hours_per_week=60,
        location="Blechzentrum",
        manufacturer="Trumpf",
        shift_calendar_id=day_shift.id,
    )
    bending_machine = erp.register_machine(
        name="Trumpf TruBend 5230",
        processes=[ManufacturingProcess.BENDING],
        capacity_hours_per_week=40,
        location="Blechzentrum",
        manufacturer="Trumpf",
        shift_calendar_id=day_shift.id,
    )
    welding_station = erp.register_machine(
        name="Fronius TPSi 400",
        processes=[ManufacturingProcess.WELDING],
        capacity_hours_per_week=38,
        location="Schweißerei",
        manufacturer="Fronius",
        shift_calendar_id=day_shift.id,
    )
    grinding_machine = erp.register_machine(
        name="Jung J630",
        processes=[ManufacturingProcess.GRINDING],
        capacity_hours_per_week=32,
        location="Finish-Bereich",
        manufacturer="Jung",
        shift_calendar_id=day_shift.id,
    )
    sawing_center = erp.register_machine(
        name="Behringer HBP 413 A",
        processes=[ManufacturingProcess.SAWING],
        capacity_hours_per_week=28,
        location="Sägezentrum",
        manufacturer="Behringer",
        shift_calendar_id=day_shift.id,
    )

    # Materialstamm
    sheet_steel = erp.register_inventory_item(
        name="Feinblech S355",
        unit_of_measure="kg",
        quantity_on_hand=180.0,
        safety_stock=80.0,
        reorder_point=100.0,
        lead_time_days=5,
    )
    round_stock = erp.register_inventory_item(
        name="Rundmaterial 42CrMo4",
        unit_of_measure="kg",
        quantity_on_hand=120.0,
        safety_stock=60.0,
        reorder_point=90.0,
        lead_time_days=7,
    )
    welding_wire = erp.register_inventory_item(
        name="Schweißdraht G3Si1",
        unit_of_measure="kg",
        quantity_on_hand=35.0,
        safety_stock=20.0,
        reorder_point=25.0,
        lead_time_days=3,
    )

    steel_supplier = erp.register_supplier(
        name="Stahlhandel Westfalen GmbH",
        address="Industriestraße 5, 44147 Dortmund",
        contact_person="Peter König",
        contact_email="verkauf@stahlwestfalen.de",
        contact_phone="+49 231 98765",
        material_item_ids=[sheet_steel.id, round_stock.id],
    )
    erp.record_supplier_evaluation(
        supplier_id=steel_supplier.id,
        quality_score=4.5,
        delivery_reliability_score=4.7,
        communication_score=4.2,
        notes="Sehr zuverlässige Lieferungen und faire Preise.",
    )

    welding_supplier = erp.register_supplier(
        name="Schweißtechnik OWL",
        address="Im Gewerbepark 7, 32760 Detmold",
        contact_person="Anja Krüger",
        contact_email="service@schweisstechnik-owl.de",
        contact_phone="+49 5231 445566",
        material_item_ids=[welding_wire.id],
    )
    erp.record_supplier_evaluation(
        supplier_id=welding_supplier.id,
        quality_score=4.8,
        delivery_reliability_score=4.6,
        communication_score=4.9,
        notes="Gute Kommunikation und flexible Liefertermine.",
    )

    # Fertigungsablauf definieren
    operations = [
        erp.build_operation(
            name="Zuschnitt sägen",
            process=ManufacturingProcess.SAWING,
            duration_hours=1.5,
            setup_time_hours=0.25,
            description="Rohmaterial auf Länge bringen",
            materials=[(round_stock.id, 45.0)],
        ),
        erp.build_operation(
            name="Drehen",
            process=ManufacturingProcess.TURNING,
            duration_hours=5.0,
            setup_time_hours=0.5,
            description="Alle Drehoperationen laut Zeichnung",
        ),
        erp.build_operation(
            name="Fräsen",
            process=ManufacturingProcess.MILLING,
            duration_hours=4.0,
            setup_time_hours=0.75,
            description="Bearbeitung prismatischer Konturen",
        ),
        erp.build_operation(
            name="Laserzuschnitt Blech",
            process=ManufacturingProcess.LASER_CUTTING,
            duration_hours=2.0,
            setup_time_hours=0.25,
            description="Laserschneiden von Blechkomponenten",
            materials=[(sheet_steel.id, 60.0)],
        ),
        erp.build_operation(
            name="Kanten",
            process=ManufacturingProcess.BENDING,
            duration_hours=1.0,
            setup_time_hours=0.25,
            description="Abkanten der Blechsegmente",
        ),
        erp.build_operation(
            name="Schweißen",
            process=ManufacturingProcess.WELDING,
            duration_hours=3.5,
            setup_time_hours=0.5,
            description="Schweißen der Unterbaugruppen",
            materials=[(welding_wire.id, 8.0)],
        ),
        erp.build_operation(
            name="Schleifen",
            process=ManufacturingProcess.GRINDING,
            duration_hours=2.5,
            setup_time_hours=0.25,
            description="Finish der Funktionsflächen",
        ),
    ]

    order = erp.create_production_order(
        customer_id=customer.id,
        reference="SO-2024-015",
        due_date=date.today() + timedelta(days=14),
        operations=operations,
        remarks="Komplexer Maschinenträger mit hoher Maßhaltigkeit",
        priority=OrderPriority.HIGH,
    )

    repeat_operations = [
        erp.build_operation(
            name="Rohling sägen",
            process=ManufacturingProcess.SAWING,
            duration_hours=1.0,
            setup_time_hours=0.2,
            description="Zuschnitt für Ersatzteilserie",
            materials=[(round_stock.id, 20.0)],
        ),
        erp.build_operation(
            name="Fräsen Kleinteil",
            process=ManufacturingProcess.MILLING,
            duration_hours=2.5,
            setup_time_hours=0.5,
            description="Bearbeitung prismatischer Aufnahmen",
        ),
        erp.build_operation(
            name="Schweißen Unterbau",
            process=ManufacturingProcess.WELDING,
            duration_hours=1.0,
            setup_time_hours=0.25,
            description="Heften und Schweißen kleiner Baugruppe",
            materials=[(welding_wire.id, 3.0)],
        ),
    ]

    follow_up_order = erp.create_production_order(
        customer_id=customer.id,
        reference="SO-2024-016",
        due_date=date.today() + timedelta(days=10),
        operations=repeat_operations,
        remarks="Ersatzteilserie für Bestandsmaschine",
        priority=OrderPriority.NORMAL,
    )

    # Planung und Auswertung
    backlog = dict(erp.schedule_backlog())
    schedule = backlog[order.id]

    print("Arbeitsplan")
    for scheduled in schedule.scheduled_operations:
        machine = erp.machines.get(scheduled.machine_id)
        operation = next(
            plan.operation
            for plan in order.operations
            if plan.operation.id == scheduled.operation_id
        )
        print(
            f" - {operation.name} auf {machine.name}: {scheduled.start:%d.%m %H:%M}"
            f" - {scheduled.end:%H:%M}"
        )

    print("\nKapazitätsauslastung")
    combined_loads: Dict[str, float] = {}
    combined_overloads: Dict[str, float] = {}
    for summary in backlog.values():
        combined_loads.update(summary.machine_loads)
        combined_overloads.update(summary.overloaded_machines)
    for machine_id, load in combined_loads.items():
        machine = erp.machines.get(machine_id)
        overload = combined_overloads.get(machine_id, 0.0)
        message = f"   {machine.name}: {load:.2f}h von {machine.capacity_hours_per_week:.2f}h"
        if overload > 0:
            message += f"  -> Überlastung {overload:.2f}h"
        print(message)

    print("\nPriorisierte Aufträge")
    for summary in backlog.values():
        current_order = erp.orders.get(summary.order_id)
        last_operation = max(
            (plan for plan in current_order.operations if plan.scheduled_end),
            key=lambda plan: plan.scheduled_end,
        )
        print(
            f" - {current_order.reference} ({current_order.priority.label})"
            f" -> Fertigstellung {last_operation.scheduled_end:%d.%m %H:%M}"
        )

    shortages = erp.material_shortage_report(order.id)
    if shortages:
        print("\nMaterialdisposition")
        for shortage in shortages:
            print(
                f" - {shortage.name}: Bedarf {shortage.required_quantity:.1f} {shortage.projected_on_hand:+.1f} Bestandsprognose"
            )
            if shortage.reorder_recommendation > 0:
                print(
                    f"   Bestellung empfohlen: {shortage.reorder_recommendation:.1f} Einheiten"
                )
            if shortage.recommended_supplier_name:
                print(
                    f"   Empfohlener Lieferant: {shortage.recommended_supplier_name}"
                )
            else:
                print("   Kein bewerteter Lieferant verfügbar")
    else:
        print("\nMaterialdisposition: Bestand ausreichend")

    planned_orders = erp.plan_material_purchases(
        order.id,
        auto_create=True,
        reorder_multiplier=1.05,
        include_safety_stock=True,
        expedite_high_priority_days=1,
    )
    if planned_orders:
        print("\nEinkaufsplanung")
        for purchase_order in planned_orders:
            item = erp.inventory.get(purchase_order.item_id)
            print(
                f" - Bestellung {purchase_order.id[:8]}: {item.name} bei {purchase_order.supplier_name}"
                f" ({purchase_order.quantity:.1f} {item.unit_of_measure}) bis {purchase_order.expected_receipt:%d.%m.%Y}"
            )

    print("\nLieferantenbewertungen")
    for supplier in erp.suppliers:
        print(
            f" - {supplier.name}: {supplier.rating:.2f} Punkte aus {supplier.rating_count} Bewertung(en)"
        )

    upcoming = erp.get_upcoming_operations(limit=5)
    print("\nNächste Operationen")
    for entry in upcoming:
        related_order = erp.orders.get(entry.order_id)
        operation = next(
            plan.operation
            for plan in related_order.operations
            if plan.operation.id == entry.operation_id
        )
        machine = erp.machines.get(entry.machine_id)
        print(
            f" - {operation.name} ({related_order.reference}, {related_order.priority.label})"
            f" auf {machine.name} am {entry.start:%d.%m %H:%M}"
        )

    # Beispielhafte Rückmeldung von Ist-Zeiten
    first_operation = order.operations[0].operation
    erp.record_time_tracking(
        order_id=order.id,
        operation_id=first_operation.id,
        employee="M. Schneider",
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1.75),
        remarks="Zuschnitt lief störungsfrei",
    )

    variance = erp.calculate_actual_vs_plan(order.id)
    print("\nSoll-/Ist-Vergleich")
    pprint(variance)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
