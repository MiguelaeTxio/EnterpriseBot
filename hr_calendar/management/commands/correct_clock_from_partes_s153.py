# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/correct_clock_from_partes_s153.py
"""
S153. Correct the clock-in days of the pay period in progress from the
closed digital partes already made.

---

S153. Corrige con los partes digitales cerrados los fichajes de los días
del periodo de pago en curso (del 21 al 20) que ya tienen parte: lo que
se hizo antes de que el parte corrigiera solo los fichajes
(hr_calendar/parte_clock.py). Sin --apply solo dice qué haría. Log
propio con pantalla y archivo a la vez (com-standards 0bis).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    """
    Correct the period's clock-in days from their partes (dry run).
    ---
    Corrige los fichajes del periodo con sus partes.
    """

    help = "Corrige los fichajes del periodo en curso con los partes (S153)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        stamp = timezone.localtime().strftime("%H:%M:%S")
        line = "[%s] %s" % (stamp, text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def _plain(self, text=""):
        print(text, flush=True)
        self._out.write(text + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _run(self, apply_changes):
        from hr_calendar.parte_clock import correct_day, period_start
        from work_order_processor.models import WorkOrder, WorkOrderEntry

        start = period_start()
        self._log("Fichajes corregidos con los partes desde el %s (%s)" % (
            start.strftime("%d/%m/%Y"),
            "APLICANDO" if apply_changes else "simulación, sin cambios"))
        pairs = sorted(set(WorkOrderEntry.objects.filter(
            work_date__gte=start, work_date__lte=timezone.localdate(),
            work_order__source=WorkOrder.Source.DIGITAL,
            work_order__status=WorkOrder.Status.DONE,
            work_order__uploaded_by__isnull=False,
        ).values_list("work_order__uploaded_by_id", "work_date")))
        from ivr_config.models import CompanyUser

        users = CompanyUser.objects.select_related("user").in_bulk(
            {u for u, _d in pairs})
        total = len(pairs)
        self._log("Días con parte cerrado: %d" % total)
        counts = {"corregidos": 0, "coinciden": 0, "sin mirar": 0}
        lines = []
        for index, (user_id, day) in enumerate(pairs, 1):
            user = users[user_id]
            result = correct_day(user, day, dry_run=not apply_changes)
            name = user.user.get_full_name() or user.user.username
            if result.skipped:
                counts["sin mirar"] += 1
                lines.append("%s %s -- sin mirar: %s" % (
                    day.strftime("%d/%m"), name, result.skipped))
            elif result.corrected:
                counts["corregidos"] += 1
                lines.append("%s %s -- %s" % (
                    day.strftime("%d/%m"), name, result.text))
            else:
                counts["coinciden"] += 1
            if index % 20 == 0:
                self._log("Progreso: %d/%d" % (index, total))
        self._plain("")
        self._plain("RESUMEN")
        self._plain("Corregidos%s: %d; coinciden: %d; sin mirar: %d" % (
            "" if apply_changes else " (se corregirían)",
            counts["corregidos"], counts["coinciden"], counts["sin mirar"]))
        for line in lines:
            self._plain(line)
        self._plain("Aplicado." if apply_changes
                    else "Simulación: no se ha cambiado nada.")
