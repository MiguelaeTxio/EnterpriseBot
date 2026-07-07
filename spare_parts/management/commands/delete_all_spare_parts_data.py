# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/management/commands/delete_all_spare_parts_data.py
"""
Borra TODOS los DeliveryNote (+ sus DeliveryNoteLine en cascada) y
TODOS los SparePartEntry (+ sus StockMovement en cascada) -- comando
pedido por Miguel Ángel (2026-07-07) para dejar la base de datos
limpia antes de una prueba de campo real con los mecánicos.

Asunción no bloqueante, declarada aquí (a confirmar si no es lo que
Miguel Ángel quería): "repuestos, tickets, etcétera" se interpreta
como el circuito de almacén H10 -- DeliveryNote/DeliveryNoteLine y
SparePartEntry/StockMovement. NO se toca:
  - Supplier (catálogo de proveedores) -- es maestro de datos, no dato
    de prueba consumible, sigue intacto.
  - WorkOrder/WorkOrderEntry/WorkOrderEntryLine/SparePartLine (partes
    de trabajo ya guardados) -- son historial de parte real, no
    almacén; si Miguel Ángel también quiere limpiar partes de prueba,
    es un comando aparte a pedir explícitamente.

Dry-run por defecto (--apply para ejecutar), mismo patrón que
delete_all_breakdown_tickets. Todas las FK que otros modelos
mantienen hacia SparePartEntry son SET_NULL (verificado empíricamente:
DeliveryNoteLine.spare_part_entry, y
work_order_processor.SparePartLine.spare_part_entry) -- borrar
SparePartEntry nunca borra en cascada partes de trabajo ya guardados,
solo desvincula esa referencia.

---

Deletes ALL DeliveryNote (+ their DeliveryNoteLine, cascaded) and ALL
SparePartEntry (+ their StockMovement, cascaded) -- requested by
Miguel Ángel (2026-07-07) to leave the database clean before a real
field test with mechanics.

Non-blocking assumption, declared here (to confirm if it's not what
Miguel Ángel meant): "spare parts, tickets, etc." is interpreted as
the H10 warehouse circuit -- DeliveryNote/DeliveryNoteLine and
SparePartEntry/StockMovement. NOT touched:
  - Supplier (supplier catalogue) -- master data, not consumable test
    data, left intact.
  - WorkOrder/WorkOrderEntry/WorkOrderEntryLine/SparePartLine (already
    saved work-order parts) -- real part history, not warehouse; if
    Miguel Ángel also wants test parts cleaned, that's a separate
    command to request explicitly.

Dry-run by default (--apply to execute), same pattern as
delete_all_breakdown_tickets. Every FK other models keep towards
SparePartEntry is SET_NULL (empirically verified:
DeliveryNoteLine.spare_part_entry, and
work_order_processor.SparePartLine.spare_part_entry) -- deleting
SparePartEntry never cascade-deletes already-saved work-order parts,
it only nulls that reference.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Borra TODOS los DeliveryNote y SparePartEntry (datos de prueba "
        "del almacen H10). Dry-run por defecto -- usar --apply para "
        "ejecutar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true', default=False,
            help="Ejecuta el borrado de verdad. Sin este flag, solo informa.",
        )

    def handle(self, *args, **options):
        from spare_parts.models import DeliveryNote, SparePartEntry

        apply_mode = options['apply']

        self.stdout.write(f"# Modo: {'APLICAR' if apply_mode else 'DRY RUN'}")
        self.stdout.write(
            "# Alcance: DeliveryNote (+ DeliveryNoteLine en cascada) y "
            "SparePartEntry (+ StockMovement en cascada). Supplier y "
            "partes de trabajo NO se tocan."
        )

        dn_qs = DeliveryNote.objects.all()
        spe_qs = SparePartEntry.objects.all()

        dn_total = dn_qs.count()
        spe_total = spe_qs.count()

        self.stdout.write(f"# DeliveryNote a borrar: {dn_total}")
        for status_value, status_label in DeliveryNote.STATUS_CHOICES:
            n = dn_qs.filter(status=status_value).count()
            if n:
                self.stdout.write(f"#   - {status_label}: {n}")

        self.stdout.write(f"# SparePartEntry a borrar: {spe_total}")
        for status_value, status_label in SparePartEntry.STATUS_CHOICES:
            n = spe_qs.filter(status=status_value).count()
            if n:
                self.stdout.write(f"#   - {status_label}: {n}")

        if dn_total == 0 and spe_total == 0:
            self.stdout.write(self.style.SUCCESS("# Nada que borrar."))
            return

        if not apply_mode:
            self.stdout.write(self.style.WARNING(
                "# DRY RUN -- nada se ha borrado. Vuelve a ejecutar con "
                "--apply para borrar de verdad."
            ))
            return

        with transaction.atomic():
            dn_deleted, _ = dn_qs.delete()
            spe_deleted, _ = spe_qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"# Borrados: {dn_deleted} registro(s) de DeliveryNote (+ "
            f"cascada), {spe_deleted} registro(s) de SparePartEntry (+ "
            f"cascada)."
        ))
