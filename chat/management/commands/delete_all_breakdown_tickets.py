# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/management/commands/delete_all_breakdown_tickets.py
"""
Borra TODOS los registros BreakdownTicket -- comando pedido por Miguel
Ángel (2026-07-07) para limpiar los tickets de prueba acumulados
durante el desarrollo de H10/H14/H17 antes de empezar a usar la
plataforma en real.

Dry-run por defecto (--apply para ejecutar de verdad), mismo patrón
que work_order_processor.fix_all_digital. Todas las FK que apuntan a
BreakdownTicket son SET_NULL (verificado empíricamente en:
ivr_config.InboundCallLog.breakdown_ticket,
spare_parts.SparePartEntry.breakdown_ticket,
spare_parts.StockMovement.breakdown_ticket,
work_order_processor.WorkOrderEntryLine.breakdown_ticket) -- borrar
tickets NUNCA borra en cascada partes de trabajo, repuestos, ni
movimientos de stock, solo desvincula esa referencia.

AVISO IMPORTANTE, sin resolver aquí a propósito (fuera del alcance de
lo pedido -- "borrar los tickets", no "los repuestos"): cualquier
SparePartEntry en estado PRE_ASSIGNED cuyo `machine` sea NULL porque
en su momento se ancló solo al ticket (rama `machine=None if ticket
else line.machine` de confirm_delivery_note(), anexo H10 sección 3.1)
quedará, tras el borrado, sin `machine` NI `breakdown_ticket` -- sin
ninguna referencia a qué máquina pertenece. El comando cuenta y lista
estos casos en el dry-run para que Miguel Ángel decida aparte qué
hacer con ellos (reasignar a mano, o un comando de limpieza propio) --
nunca se tocan aquí.

---

Deletes ALL BreakdownTicket records -- requested by Miguel Ángel
(2026-07-07) to clean up test tickets accumulated during H10/H14/H17
development before real usage begins.

Dry-run by default (--apply to actually execute), same pattern as
work_order_processor.fix_all_digital. Every FK pointing to
BreakdownTicket is SET_NULL (empirically verified in:
ivr_config.InboundCallLog.breakdown_ticket,
spare_parts.SparePartEntry.breakdown_ticket,
spare_parts.StockMovement.breakdown_ticket,
work_order_processor.WorkOrderEntryLine.breakdown_ticket) -- deleting
tickets NEVER cascade-deletes work orders, spare parts, or stock
movements, it only nulls that reference.

IMPORTANT WARNING, deliberately left unresolved here (out of scope of
what was asked -- "delete the tickets", not "the spare parts"): any
SparePartEntry in PRE_ASSIGNED status whose `machine` is NULL because
it was anchored only to the ticket at the time (the `machine=None if
ticket else line.machine` branch of confirm_delivery_note(), annex
H10 section 3.1) will end up, after deletion, with neither `machine`
NOR `breakdown_ticket` -- no reference at all to which machine it
belongs to. The command counts and lists these cases in the dry-run
so Miguel Ángel can decide separately what to do with them (manual
reassignment, or a dedicated cleanup command) -- never touched here.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Borra TODOS los BreakdownTicket (datos de prueba). "
        "Dry-run por defecto -- usar --apply para ejecutar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true', default=False,
            help="Ejecuta el borrado de verdad. Sin este flag, solo informa.",
        )

    def handle(self, *args, **options):
        from chat.models import BreakdownTicket
        from spare_parts.models import SparePartEntry

        apply_mode = options['apply']

        self.stdout.write(f"# Modo: {'APLICAR' if apply_mode else 'DRY RUN'}")

        qs = BreakdownTicket.objects.all()
        self.stdout.write("# Sin acotar por empresa -- Company no tiene campo de código corto "
                           "(verificado: name/slug/logo/is_active/... sin code/tax_id). "
                           "Borra TODOS los BreakdownTicket de la instalación.")

        total = qs.count()
        self.stdout.write(f"# BreakdownTicket a borrar: {total}")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("# Nada que borrar."))
            return

        by_status = {}
        for status_value, status_label in BreakdownTicket.STATUS_CHOICES:
            n = qs.filter(status=status_value).count()
            if n:
                by_status[status_label] = n
        for label, n in by_status.items():
            self.stdout.write(f"#   - {label}: {n}")

        # Aviso: SparePartEntry PRE_ASSIGNED que quedarian sin machine
        # ni breakdown_ticket tras el borrado (ver docstring del
        # comando). Solo se informa -- nunca se toca aqui.
        orphan_risk_qs = SparePartEntry.objects.filter(
            breakdown_ticket__in=qs,
            status=SparePartEntry.STATUS_PRE_ASSIGNED,
            machine__isnull=True,
        )
        orphan_count = orphan_risk_qs.count()
        if orphan_count:
            self.stdout.write(self.style.WARNING(
                f"# AVISO: {orphan_count} SparePartEntry(s) PRE_ASSIGNED "
                f"sin 'machine' quedarán SIN NINGUNA referencia de "
                f"máquina tras el borrado (solo tenían el ticket como "
                f"ancla). No se tocan aquí -- revisar aparte:"
            ))
            for entry in orphan_risk_qs[:20]:
                self.stdout.write(
                    f"#   - SparePartEntry pk={entry.pk} "
                    f"({entry.internal_reference or 'sin ref. interna'}) "
                    f"-- ticket pk={entry.breakdown_ticket_id}"
                )
            if orphan_count > 20:
                self.stdout.write(f"#   ... y {orphan_count - 20} más.")

        if not apply_mode:
            self.stdout.write(self.style.WARNING(
                "# DRY RUN -- nada se ha borrado. Vuelve a ejecutar con "
                "--apply para borrar de verdad."
            ))
            return

        with transaction.atomic():
            deleted_count, _ = qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"# Borrados {deleted_count} registro(s) (BreakdownTicket + "
            f"relaciones internas de Django, si las hubiera)."
        ))
