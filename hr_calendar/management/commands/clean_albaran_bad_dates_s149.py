# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/clean_albaran_bad_dates_s149.py
"""
Undo the clock-ins the AI made on albaranes whose date was misread.

---

S149 (17/11): Gemini leyó fechas imposibles en algunos albaranes
(2020, 2021, 2024, enero de 2026) y el cotejo por IA creó días de
fichaje enteros en esas fechas. Para cada albarán leído con una fecha
que no cabe (albaran_check.plausible_day):
1. Si TODO lo que hay fichado ese día lo puso la IA (pulsaciones
   añadidas o cambiadas por una corrección de origen IA), se anula
   (edit_presses, origen IA, motivo con la fecha mal leída) y se quita
   la marca «Comparado/Corregido por IA» de ese día.
   Si hay algo fichado por el trabajador o corregido a mano, no se toca
   y se lista.
2. El albarán queda «Ilegible» con la nota «Fecha dudosa (...)» para
   que el supervisor lo revise (su fecha real queda por cotejar).
Sin --apply solo dice lo que haría. Log propio (com-standards 0bis).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


def _name(person):
    return " ".join(filter(None, (person.first_surname,
                                  person.second_surname))) + ", " + (
        person.given_name or "")


class Command(BaseCommand):
    """
    Undo the AI clock-ins made on misread albarán dates.
    ---
    Anula los fichajes que creó la IA en fechas de albarán mal leídas.
    """

    help = ("Anula los fichajes que la IA creó en albaranes con la fecha "
            "mal leída y deja esos albaranes como fecha dudosa.")

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
            self._run(options["apply"])

    def _run(self, apply):
        import datetime

        from hr_calendar.albaran_check import day_locked, plausible_day
        from hr_calendar.clock_corrections import edit_presses
        from hr_calendar.models import (
            AlbaranSheet, ClockCorrection, ClockDayAiCheck, ClockEvent,
        )

        bad = defaultdict(list)
        for sheet in AlbaranSheet.objects.filter(
                status=AlbaranSheet.Status.READ, day__isnull=False,
                person__isnull=False,
        ).select_related("batch", "person__company_user"):
            if not plausible_day(sheet.day, sheet.batch.created_at):
                bad[(sheet.person_id, sheet.day)].append(sheet)
        self._log("Albaranes con fecha imposible: %d, en %d días (%s)" % (
            sum(len(v) for v in bad.values()), len(bad),
            "APLICANDO" if apply else "simulación, sin cambios"))
        tz = timezone.get_current_timezone()
        undone, kept = 0, []
        for (_person_id, day), sheets in sorted(
                bad.items(), key=lambda item: item[0][1]):
            person = sheets[0].person
            company_user = person.company_user
            numbers = ", ".join(s.number or s.original_name for s in sheets)
            label = "%s %s (albarán %s)" % (
                _name(person), day.strftime("%d/%m/%Y"), numbers)
            events = []
            if company_user is not None:
                start = timezone.make_aware(
                    datetime.datetime.combine(day, datetime.time.min), tz)
                events = list(ClockEvent.objects.current().filter(
                    company_user=company_user, pressed_at__gte=start,
                    pressed_at__lt=start + datetime.timedelta(days=1),
                ).order_by("pressed_at"))
            by_ai = set(ClockCorrection.objects.filter(
                source=ClockCorrection.Source.AI,
                replacement__in=events,
            ).values_list("replacement_id", flat=True))
            foreign = [e for e in events if e.pk not in by_ai]
            # S149 (Miguel Ángel, 17/11): lo visado se deja tal cual.
            locked = (day_locked(company_user, day)
                      if company_user is not None else "")
            if locked:
                kept.append("%s: %s" % (label, locked))
                continue
            if foreign:
                kept.append("%s: hay %d pulsación/es que no puso la IA"
                            % (label, len(foreign)))
            elif events:
                self._log("  %s: se anulan %d pulsación/es de la IA (%s)" % (
                    label, len(events), ", ".join(
                        timezone.localtime(e.pressed_at).strftime("%H:%M")
                        for e in events)))
            else:
                self._log("  %s: sin fichajes ese día" % label)
            if not apply:
                continue
            with transaction.atomic():
                if events and not foreign:
                    edit_presses(
                        company_user, person, sheets[0].batch.created_by,
                        "Anulado: la IA leyó mal la fecha del albarán %s "
                        "(%s); no es un día trabajado." % (
                            numbers, day.strftime("%d/%m/%Y")),
                        [{"id": e.pk, "delete": True} for e in events],
                        source=ClockCorrection.Source.AI,
                    )
                    undone += 1
                if not foreign and company_user is not None:
                    ClockDayAiCheck.objects.filter(
                        company_user=company_user, day=day).delete()
                for sheet in sheets:
                    sheet.status = AlbaranSheet.Status.UNREADABLE
                    sheet.note = ("Fecha dudosa (%s): revísala; no se coteja."
                                  " %s" % (day.strftime("%d/%m/%Y"),
                                           sheet.note or "")).strip()[:255]
                    sheet.save(update_fields=["status", "note"])
        for line in kept:
            self._log("  SIN TOCAR (revisar a mano) %s" % line)
        self._log("Fin: %d día/s anulado/s, %d sin tocar." % (
            undone, len(kept)))
