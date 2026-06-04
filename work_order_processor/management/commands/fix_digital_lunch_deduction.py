# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/fix_digital_lunch_deduction.py
"""
Management command: fix_digital_lunch_deduction
================================================
Audits and optionally corrects WorkOrderEntryLine.delta_hours for DIGITAL
and GENERATED work orders where the lunch break deduction was not applied.

The bug: the save_blocks handler in WorkOrderEntryFormView did not inject
lunch_overlap_N hidden inputs before submitting, so the backend received
overlap=0 for all progressive saves and persisted gross delta_hours instead
of net (lunch-deducted) values.

This command identifies all affected lines and either reports them (--dry-run,
default) or corrects them in-place.

Affected lines criteria:
  - WorkOrder.source in (DIGITAL, GENERATED)
  - WorkOrder.status == DONE
  - WorkOrderEntry.no_lunch_break == False
  - WorkOrderEntry.lunch_break_start and lunch_break_end are set
  - WorkOrderEntryLine.hc and hf are set
  - The block [hc, hf] overlaps with [lunch_break_start, lunch_break_end]
  - The overlap (in minutes) > 0
  - The stored delta_hours equals the gross duration (hf - hc) rather than
    the net duration (gross - overlap)

Usage:
  python3 -m dotenv run python3 manage.py fix_digital_lunch_deduction --dry-run
  python3 -m dotenv run python3 manage.py fix_digital_lunch_deduction --apply

---

Comando de gestión: fix_digital_lunch_deduction
================================================
Audita y opcionalmente corrige WorkOrderEntryLine.delta_hours para partes
DIGITAL y GENERATED donde no se aplicó el descuento de pausa de comida.

El bug: el handler save_blocks en WorkOrderEntryFormView no inyectaba los
inputs ocultos lunch_overlap_N antes del submit, por lo que el backend recibía
overlap=0 en todos los guardados progresivos y persistía delta_hours bruto
en lugar del neto (con descuento de comida).

Este comando identifica todas las líneas afectadas y las reporta (--dry-run,
por defecto) o las corrige en sitio (--apply).

Criterios de líneas afectadas:
  - WorkOrder.source en (DIGITAL, GENERATED)
  - WorkOrder.status == DONE
  - WorkOrderEntry.no_lunch_break == False
  - WorkOrderEntry.lunch_break_start y lunch_break_end están definidos
  - WorkOrderEntryLine.hc y hf están definidos
  - El bloque [hc, hf] solapa con [lunch_break_start, lunch_break_end]
  - El solapamiento (en minutos) > 0
  - El delta_hours almacenado coincide con la duración bruta (hf - hc) y
    no con la neta (bruto - solapamiento)

Uso:
  python3 -m dotenv run python3 manage.py fix_digital_lunch_deduction --dry-run
  python3 -m dotenv run python3 manage.py fix_digital_lunch_deduction --apply
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine


def _to_minutes(t):
    """
    Converts a time object to total minutes since midnight.
    ---
    Convierte un objeto time a minutos totales desde medianoche.
    """
    return t.hour * 60 + t.minute


def _compute_overlap_minutes(hc, hf, lb_start, lb_end):
    """
    Returns the overlap in minutes between work block [hc, hf] and lunch
    break window [lb_start, lb_end]. Returns 0 if there is no overlap or
    any argument is None.
    ---
    Devuelve el solapamiento en minutos entre el bloque [hc, hf] y la
    ventana de pausa [lb_start, lb_end]. Devuelve 0 si no hay solapamiento
    o algún argumento es None.
    """
    if not hc or not hf or not lb_start or not lb_end:
        return 0
    hc_min  = _to_minutes(hc)
    hf_min  = _to_minutes(hf)
    lb_s    = _to_minutes(lb_start)
    lb_e    = _to_minutes(lb_end)
    overlap = max(0, min(hf_min, lb_e) - max(hc_min, lb_s))
    return overlap


def _compute_net_delta(hc, hf, overlap_min):
    """
    Returns the net delta_hours as a Decimal rounded to 2 decimal places,
    subtracting the lunch overlap from the gross duration.
    ---
    Devuelve el delta_hours neto como Decimal redondeado a 2 decimales,
    restando el solapamiento de comida de la duración bruta.
    """
    gross_min = _to_minutes(hf) - _to_minutes(hc)
    net_min   = max(0, gross_min - overlap_min)
    return (Decimal(net_min) / Decimal(60)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


class Command(BaseCommand):
    """
    Audits or corrects lunch deduction on digital work order entry lines.
    ---
    Audita o corrige el descuento de comida en líneas de partes digitales.
    """

    help = (
        "Audita y corrige el descuento de pausa de comida en líneas de "
        "partes DIGITAL/GENERATED donde save_blocks no aplicó el descuento."
    )

    def add_arguments(self, parser):
        """
        Registers --dry-run (default) and --apply flags.
        ---
        Registra los flags --dry-run (por defecto) y --apply.
        """
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Solo reportar líneas afectadas sin modificar la BD (por defecto).",
        )
        group.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Aplicar correcciones en la BD.",
        )

    def handle(self, *args, **options):
        """
        Main entry point. Queries affected lines and reports or corrects them.
        ---
        Punto de entrada principal. Consulta las líneas afectadas y las
        reporta o corrige.
        """
        apply_mode = options.get("apply", False)
        mode_label = "APLICAR" if apply_mode else "DRY RUN"

        self.stdout.write(f"# [fix_digital_lunch_deduction] Modo: {mode_label}")
        self.stdout.write("# Buscando líneas afectadas...")

        # Query: DIGITAL/GENERATED DONE work orders with split-shift lunch set.
        # Consulta: partes DIGITAL/GENERATED DONE con pausa de comida definida.
        candidate_entries = (
            WorkOrderEntry.objects
            .filter(
                work_order__source__in=[
                    WorkOrder.Source.DIGITAL,
                    WorkOrder.Source.GENERATED,
                ],
                work_order__status=WorkOrder.Status.DONE,
                no_lunch_break=False,
                lunch_break_start__isnull=False,
                lunch_break_end__isnull=False,
            )
            .select_related("work_order")
            .prefetch_related("lines")
        )

        total_affected = 0
        total_corrected = 0
        report_rows = []

        for entry in candidate_entries:
            lb_start = entry.lunch_break_start
            lb_end   = entry.lunch_break_end

            for line in entry.lines.all():
                if not line.hc or not line.hf or line.delta_hours is None:
                    continue

                overlap_min = _compute_overlap_minutes(
                    line.hc, line.hf, lb_start, lb_end
                )
                if overlap_min == 0:
                    continue

                gross_min   = _to_minutes(line.hf) - _to_minutes(line.hc)
                gross_delta = (Decimal(gross_min) / Decimal(60)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                net_delta   = _compute_net_delta(line.hc, line.hf, overlap_min)

                # Only flag lines where stored delta equals gross (not yet deducted).
                # Solo marcar líneas donde el delta almacenado coincide con el bruto.
                if line.delta_hours != gross_delta:
                    continue

                total_affected += 1
                report_rows.append({
                    "wo_pk":       entry.work_order.pk,
                    "entry_pk":    entry.pk,
                    "line_pk":     line.pk,
                    "worker":      entry.worker_name,
                    "work_date":   entry.work_date,
                    "hc":          line.hc.strftime("%H:%M") if line.hc else "--",
                    "hf":          line.hf.strftime("%H:%M") if line.hf else "--",
                    "lb_start":    lb_start.strftime("%H:%M"),
                    "lb_end":      lb_end.strftime("%H:%M"),
                    "overlap_min": overlap_min,
                    "delta_gross": gross_delta,
                    "delta_net":   net_delta,
                    "line_obj":    line if apply_mode else None,
                })

        # Report.
        # Informe.
        self.stdout.write(
            f"\n# Líneas afectadas encontradas: {total_affected}"
        )
        if total_affected == 0:
            self.stdout.write("# No hay líneas que corregir. BD consistente.")
            return

        self.stdout.write(
            "\n{:<8} {:<10} {:<8} {:<24} {:<12} {:<6} {:<6} {:<8} {:<8} "
            "{:<8} {:<10} {:<10}".format(
                "WO_PK", "ENTRY_PK", "LINE_PK", "OPERARIO",
                "FECHA", "HC", "HF", "LB_INI", "LB_FIN",
                "SOLAP_M", "DELTA_BRUTO", "DELTA_NETO",
            )
        )
        self.stdout.write("-" * 120)

        for row in report_rows:
            self.stdout.write(
                "{:<8} {:<10} {:<8} {:<24} {:<12} {:<6} {:<6} {:<8} {:<8} "
                "{:<8} {:<10} {:<10}".format(
                    row["wo_pk"],
                    row["entry_pk"],
                    row["line_pk"],
                    (row["worker"] or "")[:24],
                    str(row["work_date"]) if row["work_date"] else "",
                    row["hc"],
                    row["hf"],
                    row["lb_start"],
                    row["lb_end"],
                    row["overlap_min"],
                    str(row["delta_gross"]),
                    str(row["delta_net"]),
                )
            )

        if not apply_mode:
            self.stdout.write(
                f"\n# DRY RUN completado. {total_affected} línea(s) requieren "
                "corrección. Ejecutar con --apply para aplicar."
            )
            return

        # Apply corrections.
        # Aplicar correcciones.
        self.stdout.write("\n# Aplicando correcciones...")
        with transaction.atomic():
            for row in report_rows:
                line = row["line_obj"]
                line.delta_hours = row["delta_net"]
                line.save(update_fields=["delta_hours"])
                total_corrected += 1

        self.stdout.write(
            f"# Corrección completada. {total_corrected} línea(s) actualizadas."
        )
