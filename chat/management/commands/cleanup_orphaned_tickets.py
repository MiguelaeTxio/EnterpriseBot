# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/management/commands/cleanup_orphaned_tickets.py
"""
Limpieza ÚNICA de BreakdownTicket huérfanos ya existentes en BD --
tickets sin ninguna WorkOrderEntryLine real en ningún parte, porque
el parte que los originó se borró ANTES del arreglo de S116-H07
(panel.views_workorders._delete_orphaned_tickets(), commit bda70cb),
que evita que esto vuelva a pasar hacia delante.

Petición explícita de Miguel Ángel: "borramos desde consola todos
los partes huérfanos [...] es decir, tickets". Caso real que lo
motivó: al borrar un parte, el ticket de avería que había originado
se quedaba huérfano (WorkOrderEntryLine.breakdown_ticket es
on_delete=SET_NULL, así que borrar la línea nunca tocaba el ticket
en sí) y seguía apareciendo como "¿es la misma avería?" en la
resolución de ticket de esa máquina, sin ningún parte real detrás.

Deliberadamente NO borra un ticket solo por estar CLOSED o por
antigüedad -- un ticket cerrado con una línea real en un parte
existente es historial legítimo, nunca se toca. El único criterio es
"cero WorkOrderEntryLine reales en cualquier parte, de cualquier
estado" -- exactamente el mismo criterio que ya usa
_delete_orphaned_tickets() para las bajas futuras, aplicado aquí una
vez sobre lo ya acumulado.

Dry-run por defecto (mismo patrón que purge_orphaned_gcs_blobs y
delete_all_breakdown_tickets) -- usar --confirm para borrar de
verdad.

Uso:
    python -m dotenv run python manage.py cleanup_orphaned_tickets
    python -m dotenv run python manage.py cleanup_orphaned_tickets --confirm

---

ONE-TIME cleanup of BreakdownTicket rows already orphaned in the DB
-- tickets with no real WorkOrderEntryLine in any work order at all,
because the work order that originated them was deleted BEFORE the
S116-H07 fix (panel.views_workorders._delete_orphaned_tickets(),
commit bda70cb) that prevents this from happening again going
forward.

Deliberately does NOT delete a ticket just for being CLOSED or old --
a closed ticket with a real line in an existing work order is
legitimate history, never touched. The only criterion is "zero real
WorkOrderEntryLine anywhere, in any status" -- the exact same
criterion _delete_orphaned_tickets() already uses for future
deletions, applied here once over what has already accumulated.

Dry-run by default -- use --confirm to actually delete.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Borra los BreakdownTicket ya huérfanos (sin ninguna "
        "WorkOrderEntryLine real en ningún parte) acumulados antes del "
        "arreglo de S116-H07. Dry-run por defecto -- usar --confirm "
        "para borrar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm", action="store_true",
            help="Borra de verdad. Sin este flag, solo lista lo que "
                 "se borraría (dry-run).",
        )

    def handle(self, *args, **options):
        from chat.models import BreakdownTicket

        confirm = options["confirm"]

        orphaned = BreakdownTicket.objects.filter(
            work_entry_lines__isnull=True,
        ).order_by("created_at")

        total = orphaned.count()
        self.stdout.write(f"# Modo: {'APLICAR' if confirm else 'DRY RUN'}")
        self.stdout.write(
            f"# BreakdownTicket huérfanos encontrados: {total}"
        )

        if total == 0:
            self.stdout.write(self.style.SUCCESS("# Nada que borrar."))
            return

        for ticket in orphaned:
            self.stdout.write(
                f"#   - pk={ticket.pk} "
                f"{ticket.ticket_date_code or ''} "
                f"({ticket.get_status_display()}) "
                f"máquina={ticket.machine_id or 'sin máquina'} "
                f"creado={ticket.created_at:%Y-%m-%d %H:%M}"
            )

        if not confirm:
            self.stdout.write(self.style.WARNING(
                "# DRY RUN -- nada se ha borrado. Vuelve a ejecutar con "
                "--confirm para borrar de verdad."
            ))
            return

        deleted_count, _ = orphaned.delete()
        self.stdout.write(self.style.SUCCESS(
            f"# Borrados {deleted_count} registro(s) (BreakdownTicket + "
            f"relaciones internas de Django, si las hubiera)."
        ))
