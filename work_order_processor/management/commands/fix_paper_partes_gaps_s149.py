# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/fix_paper_partes_gaps_s149.py
"""
Close the breakfast gap of the loaded paper partes (S149).

---

Partes en papel de Plataformas cargados con import_paper_partes_s149
(nº 892-905). Miguel Ángel, 27/11: "ellos han descontado el hueco del
desayuno y no deben descontarlo" y "esa media hora de los fallos se los
vamos a poner a la tarea siguiente". Cada hueco entre dos tareas (que
no sea la comida) se cierra: la tarea siguiente empieza cuando acaba la
anterior, con sus horas recalculadas.

Zafra Balbuena 23/11 (parte 893): "en vez de poner finaliza a las 18:30
puso 13:30. Hay que descontarle la hora y media de comida": la tarea de
Taller acaba a las 18:30, con la comida descontada.

Nicolás 24/11 (parte 899, el de la dieta): "no paró a comer [...] hay
que sumarle la hora y media de comida que se le había descontado": sin
pausa de comida.

Los dos días se comparan después con sus fichajes, como al cargarlos
(salvo visado o corrección a mano).

Excel del parte regenerado. Sin --apply, simulación. Log propio.
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

WORK_ORDERS = range(892, 906)
ZAFRA_DAY = (893, datetime.time(11, 0), datetime.time(13, 30),
             datetime.time(18, 30))
NO_LUNCH = 899


class _Rollback(Exception):
    pass


def _minutes(value):
    return value.hour * 60 + value.minute


def _hours(line, entry):
    gross = _minutes(line.hf) - _minutes(line.hc)
    overlap = 0
    if entry.lunch_break_start and entry.lunch_break_end:
        overlap = max(0, min(_minutes(line.hf),
                             _minutes(entry.lunch_break_end))
                      - max(_minutes(line.hc),
                            _minutes(entry.lunch_break_start)))
    return (Decimal(gross - overlap) / Decimal(60)).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = ("Quita el hueco del desayuno (10:00-10:30) de los partes en "
            "papel de Plataformas cargados el 27/11.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._log("MODO: %s" % ("APLICAR" if options["apply"]
                                    else "SIMULACIÓN (no cambia nada)"))
            self._changed = set()
            try:
                with transaction.atomic():
                    self._run(options["apply"])
                    if not options["apply"]:
                        raise _Rollback()
            except _Rollback:
                self._log("Simulación: deshecho todo.")
                return
            from work_order_processor.services import (
                generate_work_order_excel,
            )
            for number in sorted(self._changed):
                try:
                    generate_work_order_excel(number)
                except Exception as exc:
                    self._log("   Excel del parte %d: %s" % (number, exc))
            self._log("Hecho: %d partes cambiados." % len(self._changed))

    def _run(self, apply):
        from work_order_processor.models import WorkOrderEntry

        before_total = after_total = Decimal("0")
        self._clock_days = []
        for entry in WorkOrderEntry.objects.filter(
                work_order_id__in=WORK_ORDERS).select_related(
                "work_order__uploaded_by").order_by("worker_name",
                                                    "work_date"):
            lines = list(entry.lines.order_by("hc", "line_number"))
            before = sum((line.delta_hours or 0 for line in lines),
                         Decimal("0"))
            notes = []
            if (entry.work_order_id == NO_LUNCH
                    and not entry.no_lunch_break):
                entry.no_lunch_break = True
                entry.lunch_break_start = entry.lunch_break_end = None
                entry.save(update_fields=["no_lunch_break",
                                          "lunch_break_start",
                                          "lunch_break_end"])
                self._clock_days.append(entry)
                notes.append("   sin pausa de comida (no paró a comer)")
            previous_end = None
            for line in lines:
                old = (line.hc, line.hf, line.delta_hours)
                if (previous_end is not None and line.hc
                        and previous_end < line.hc
                        and not self._is_lunch(entry, previous_end,
                                               line.hc)):
                    line.hc = previous_end
                number, start, end, new_end = ZAFRA_DAY
                if (entry.work_order_id == number and line.hc == start
                        and line.hf == end):
                    line.hf = new_end
                    self._clock_days.append(entry)
                if line.hf:
                    previous_end = max(previous_end or line.hf, line.hf)
                new_hours = _hours(line, entry)
                if (line.hc, line.hf) == old[:2] and new_hours == old[2]:
                    continue
                line.delta_hours = new_hours
                line.save(update_fields=["hc", "hf", "delta_hours"])
                self._changed.add(entry.work_order_id)
                notes.append("   %d. %s %s-%s (%sh) -> %s-%s (%sh)" % (
                    line.line_number, line.machine_norm,
                    old[0].strftime("%H:%M"), old[1].strftime("%H:%M"),
                    old[2], line.hc.strftime("%H:%M"),
                    line.hf.strftime("%H:%M"), line.delta_hours))
            after = sum((line.delta_hours or 0 for line in lines),
                        Decimal("0"))
            before_total += before
            after_total += after
            self._log("== %s %s (parte %d): %sh -> %sh%s" % (
                entry.worker_name, entry.work_date.strftime("%d/%m"),
                entry.work_order_id, before, after,
                "" if notes else " (sin cambios)"))
            for note in notes:
                self._log(note)
        self._log("TOTAL: %sh -> %sh" % (before_total, after_total))
        for entry in self._clock_days:
            self._clock(entry, apply)

    @staticmethod
    def _is_lunch(entry, gap_start, gap_end):
        """El hueco es la comida del parte (ese no se cierra)."""
        if entry.no_lunch_break or not entry.lunch_break_start:
            return False
        return (gap_start <= entry.lunch_break_start
                and gap_end >= entry.lunch_break_end)

    def _clock(self, entry, apply):
        from hr_calendar.albaran_check import day_locked
        from hr_calendar.parte_clock import correct_day

        company_user = entry.work_order.uploaded_by
        day = entry.work_date
        if day_locked(company_user, day):
            self._log("Fichajes %s: visado o corregido a mano: no se toca."
                      % day.strftime("%d/%m"))
            return
        # La simulación deshace los cambios del parte al final: se mira
        # con el parte ya cambiado (dentro de la transacción).
        result = correct_day(company_user, day, dry_run=not apply)
        self._log("Fichajes %s %s: %s" % (
            company_user.user.username, day.strftime("%d/%m"),
            result.text or "sin cambios"))
