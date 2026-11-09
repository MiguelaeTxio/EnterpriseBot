# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/fix_garcia_luque_s146.py
"""
Management command: fix_garcia_luque_s146.

One-off fix (H24, S146) of Alejandro García Luque's days 05/11 and
06/11/2026, as Miguel Ángel stated them: both days he worked from 8:00
to 17:30 on the same task (the gate for Santa Águeda).

---

Comando de gestión: fix_garcia_luque_s146 (H24, S146).

Arreglo puntual de los días 05/11 y 06/11/2026 de Alejandro García
Luque, según Miguel Ángel: los dos días trabajó de 8:00 a 17:30 en la
misma tarea (el portón de Santa Águeda).
- 05/11: se olvidó de fichar a las 8 y fichó a las 10. Se corrige la
  entrada (#179) a las 8:00 y el parte se ajusta con ella (la tarea
  empieza a las 8:00).
- 06/11: fichó la entrada a las 8 y la comida (13:30 a 15:00), pero no
  la salida. Solo se añade la salida a las 17:30; el parte lo hará él.
Las correcciones van firmadas por alvarez_admin y con el motivo. Sin
--apply solo dice lo que haría.
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hr_calendar.clock_corrections import add_event, correct_event
from hr_calendar.clock_parts import (
    day_bounds,
    resync_parte_after_correction,
)
from hr_calendar.models import ClockCorrection, ClockEvent
from ivr_config.models import CompanyUser
from work_order_processor.models import WorkOrderEntry, WorkOrderEntryLine

WORKER_ID = 14
AUTHOR_ID = 1
DAY5 = datetime.date(2026, 11, 5)
DAY6 = datetime.date(2026, 11, 6)
IN_EVENT_DAY5 = 179
REASON_IN = ("Se olvidó de fichar la entrada a las 8:00 y fichó a las "
             "10:00; trabajó desde las 8:00 (lo indica Miguel Ángel).")
REASON_OUT = ("Se olvidó de fichar la salida; salió a las 17:30 (lo "
              "indica Miguel Ángel).")


def _aware(day, hour, minute):
    return timezone.make_aware(
        datetime.datetime.combine(day, datetime.time(hour, minute)),
        timezone.get_current_timezone(),
    )


class Command(BaseCommand):
    help = "Arreglo de los días 05/11 y 06/11 de Alejandro García Luque."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        log = open(options["log_file"], "a", encoding="utf-8") \
            if options["log_file"] else None

        def say(text):
            line = "[%s] %s" % (
                timezone.localtime().strftime("%H:%M:%S"), text)
            self.stdout.write(line)
            self.stdout.flush()
            if log:
                log.write(line + "\n")
                log.flush()

        apply = options["apply"]
        worker = CompanyUser.objects.filter(pk=WORKER_ID).first()
        author = CompanyUser.objects.filter(pk=AUTHOR_ID).first()
        if worker is None or author is None:
            raise CommandError("Falta el usuario #%d o #%d."
                               % (WORKER_ID, AUTHOR_ID))
        person = getattr(worker, "person_identity", None)
        say("# fix_garcia_luque_s146 %s: usuario #%d (%s), firma %s"
            % ("APLICANDO" if apply else "SIMULACIÓN", worker.pk,
               worker.user.username, author.user.username))
        self._day5(worker, author, apply, say)
        self._day6(worker, person, author, apply, say)
        say("# Fin%s." % ("" if apply else " (simulación: nada escrito)"))

    def _show(self, worker, day, say):
        for event in ClockEvent.objects.current().filter(
                company_user=worker,
                pressed_at__gte=_aware(day, 0, 0),
                pressed_at__lt=_aware(day + datetime.timedelta(days=1),
                                      0, 0)).order_by("pressed_at"):
            say("    fichaje #%d %s %s (%s)" % (
                event.pk, event.kind,
                timezone.localtime(event.pressed_at).strftime("%H:%M"),
                event.sent_by))
        for entry in WorkOrderEntry.objects.filter(
                work_order__uploaded_by=worker, work_date=day):
            say("    parte WO #%d (%s) comida %s-%s" % (
                entry.work_order_id, entry.work_order.status,
                entry.lunch_break_start, entry.lunch_break_end))
            for line in WorkOrderEntryLine.objects.filter(
                    entry=entry).order_by("line_number"):
                say("      tarea %d: %s-%s (%s h) %s" % (
                    line.line_number, line.hc, line.hf, line.delta_hours,
                    (line.fault_description or "")[:60]))

    def _day5(self, worker, author, apply, say):
        say("## 05/11 antes:")
        self._show(worker, DAY5, say)
        event = ClockEvent.objects.filter(
            pk=IN_EVENT_DAY5, company_user=worker,
            kind=ClockEvent.Kind.IN).first()
        if event is None:
            raise CommandError("No existe la entrada #%d del usuario."
                               % IN_EVENT_DAY5)
        if ClockCorrection.objects.filter(event=event).exists():
            say("   La entrada #%d ya está corregida: no se toca."
                % event.pk)
            return
        say("   Corregir entrada #%d de %s a 08:00." % (
            event.pk,
            timezone.localtime(event.pressed_at).strftime("%H:%M")))
        if not apply:
            return
        before = day_bounds(worker, DAY5)
        with transaction.atomic():
            correct_event(event.pk, author, ClockCorrection.Action.CHANGE,
                          REASON_IN, new_kind=ClockEvent.Kind.IN,
                          new_pressed_at=_aware(DAY5, 8, 0),
                          new_clock_type_id=event.clock_type_id)
        outcome = resync_parte_after_correction(worker, DAY5, before)
        say("   Parte: %s" % (outcome.text or "sin cambios"))
        say("## 05/11 después:")
        self._show(worker, DAY5, say)

    def _day6(self, worker, person, author, apply, say):
        say("## 06/11 antes:")
        self._show(worker, DAY6, say)
        has_out = ClockEvent.objects.current().filter(
            company_user=worker, kind=ClockEvent.Kind.OUT,
            pressed_at__gte=_aware(DAY6, 16, 0),
            pressed_at__lt=_aware(DAY6, 23, 59)).exists()
        if has_out:
            say("   Ya tiene salida por la tarde: no se añade.")
            return
        say("   Añadir salida a las 17:30.")
        if not apply:
            return
        before = day_bounds(worker, DAY6)
        add_event(worker, person, author, ClockEvent.Kind.OUT,
                  _aware(DAY6, 17, 30), REASON_OUT)
        outcome = resync_parte_after_correction(worker, DAY6, before)
        say("   Parte: %s" % (outcome.text or "sin cambios"))
        say("## 06/11 después:")
        self._show(worker, DAY6, say)
