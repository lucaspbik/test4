"""Demonstration script for the special machine builder ERP system."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pprint import pprint

from . import ERPService, ManufacturingProcess


def main() -> None:
    erp = ERPService()

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
    )
    milling_machine = erp.register_machine(
        name="Hermle C 42 U",
        processes=[ManufacturingProcess.MILLING],
        capacity_hours_per_week=50,
        location="Fertigungshalle A",
        manufacturer="Hermle",
    )
    laser_machine = erp.register_machine(
        name="Trumpf TruLaser 3030",
        processes=[ManufacturingProcess.LASER_CUTTING],
        capacity_hours_per_week=60,
        location="Blechzentrum",
        manufacturer="Trumpf",
    )
    bending_machine = erp.register_machine(
        name="Trumpf TruBend 5230",
        processes=[ManufacturingProcess.BENDING],
        capacity_hours_per_week=40,
        location="Blechzentrum",
        manufacturer="Trumpf",
    )
    welding_station = erp.register_machine(
        name="Fronius TPSi 400",
        processes=[ManufacturingProcess.WELDING],
        capacity_hours_per_week=38,
        location="Schweißerei",
        manufacturer="Fronius",
    )
    grinding_machine = erp.register_machine(
        name="Jung J630",
        processes=[ManufacturingProcess.GRINDING],
        capacity_hours_per_week=32,
        location="Finish-Bereich",
        manufacturer="Jung",
    )
    sawing_center = erp.register_machine(
        name="Behringer HBP 413 A",
        processes=[ManufacturingProcess.SAWING],
        capacity_hours_per_week=28,
        location="Sägezentrum",
        manufacturer="Behringer",
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
    )

    # Planung und Auswertung
    schedule = erp.schedule_operations(order.id)

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
    for machine_id, load in schedule.machine_loads.items():
        machine = erp.machines.get(machine_id)
        overload = schedule.overloaded_machines.get(machine_id, 0.0)
        message = f"   {machine.name}: {load:.2f}h von {machine.capacity_hours_per_week:.2f}h"
        if overload > 0:
            message += f"  -> Überlastung {overload:.2f}h"
        print(message)

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
    else:
        print("\nMaterialdisposition: Bestand ausreichend")

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
