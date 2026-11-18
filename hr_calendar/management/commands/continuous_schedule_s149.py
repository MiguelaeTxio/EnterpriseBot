# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/continuous_schedule_s149.py
"""
Turn a worker's split days into one continuous tract, with effect on the past.

---

S149 (Miguel Ángel, 18/11, Yolanda Bandera): "tenemos puesto el horario
como partido [...] La realidad no es, a ella no para comer [...]
modificar su horario para quitarle esa pausa de comida, dejarlo como
jornada intensiva y además hacer un cambio retroactivo, aunque quede
registrado por la causa por la que es y quede registrado a mi nombre".

En el horario propio del trabajador (solo si no lo comparte nadie), los
días con mañana y tarde pasan a un solo tramo (--start a --end); los
días de un tramo y los que no se trabaja no cambian. Las horas se
calculan siempre con el horario vigente, así que lo ya fichado se
recalcula solo (sin la hora de comida descontada): el comando lo lista
día a día, antes y después. Queda anotado en su ficha de fichajes el
motivo, quién y cuándo (WorkerClockSetting.schedule_note y
updated_by). Sin --apply, simulación (no cambia nada). Log propio
(com-standards 0bis).
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

DAYS = "LMXJVSD"


class _Rollback(Exception):
    pass


class Command(BaseCommand):
    help = ("Pasa los días partidos del horario propio de un trabajador a "
            "jornada continua, con efecto en lo ya fichado.")

    def add_arguments(self, parser):
        parser.add_argument("--person", type=int, required=True)
        parser.add_argument("--start", default="09:00")
        parser.add_argument("--end", default="18:00")
        parser.add_argument("--by", required=True,
                            help="Usuario del panel que hace el cambio.")
        parser.add_argument("--reason", required=True)
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
            try:
                with transaction.atomic():
                    self._run(options)
                    if not options["apply"]:
                        raise _Rollback
            except _Rollback:
                self._log("Simulación: no se ha guardado nada.")

    def _report(self, company, user_id, date_from, date_to):
        from hr_calendar.clock_report import reports_by_user

        report = reports_by_user(company, [user_id], date_from,
                                 date_to).get(user_id)
        days = {}
        for shift in getattr(report, "shifts", []):
            if shift.clock_in is None or shift.clock_out is None:
                continue
            day = days.setdefault(shift.day, [0, 0])
            day[0] += shift.seconds
            day[1] += shift.auto_meal_seconds
        return days

    def _run(self, options):
        from document_explorer.models import PersonIdentity
        from hr_calendar.clock_report import format_duration
        from hr_calendar.models import ClockEvent, WorkerClockSetting
        from ivr_config.models import CompanyUser, WorkdayScheduleDay

        start = datetime.time.fromisoformat(options["start"])
        end = datetime.time.fromisoformat(options["end"])
        if start >= end:
            raise CommandError("La entrada tiene que ser antes que la "
                               "salida.")
        person = PersonIdentity.objects.filter(pk=options["person"]).first()
        if person is None or person.company_user_id is None:
            raise CommandError("No existe esa persona o no ficha.")
        by = CompanyUser.objects.filter(
            user__username=options["by"]).select_related("user").first()
        if by is None:
            raise CommandError("No existe el usuario %s." % options["by"])
        setting = WorkerClockSetting.objects.filter(
            person=person).select_related("workday_schedule").first()
        schedule = getattr(setting, "workday_schedule", None)
        if schedule is None:
            raise CommandError("No tiene horario asignado.")
        shared = WorkerClockSetting.objects.filter(
            workday_schedule=schedule).exclude(pk=setting.pk).count()
        if shared:
            raise CommandError("El horario «%s» lo tienen %d trabajador/es "
                               "más: no se cambia." % (schedule.label,
                                                       shared))
        name = "%s, %s" % (" ".join(filter(None, (
            person.first_surname, person.second_surname))),
            person.given_name)
        self._log("%s, horario «%s» (%s)" % (
            name, schedule.label,
            "APLICANDO" if options["apply"] else "simulación, sin cambios"))
        company = person.company_user.company
        user_id = person.company_user_id
        first = ClockEvent.objects.filter(company_user_id=user_id).order_by(
            "pressed_at").values_list("pressed_at", flat=True).first()
        if first is None:
            raise CommandError("No tiene fichajes.")
        date_from = timezone.localtime(first).date()
        date_to = timezone.localdate()
        before = self._report(company, user_id, date_from, date_to)

        def tracts(row):
            return " / ".join(
                "%s-%s" % (a.strftime("%H:%M"), b.strftime("%H:%M"))
                for a, b in ((row.start_time_morning, row.end_time_morning),
                             (row.start_time_afternoon,
                              row.end_time_afternoon))
                if a is not None and b is not None) or "no trabaja"

        new = "%s-%s" % (start.strftime("%H:%M"), end.strftime("%H:%M"))
        changed = []
        if schedule.varies_by_day:
            for row in schedule.days.all().order_by("weekday"):
                label = (DAYS[row.weekday] if row.weekday < 7
                         else "Festivos")
                split = (row.works and row.start_time_afternoon is not None
                         and row.end_time_afternoon is not None)
                if not split:
                    self._log("  %s: %s (no cambia)" % (label, tracts(row)))
                    continue
                self._log("  %s: %s -> %s" % (label, tracts(row), new))
                changed.append(label)
                WorkdayScheduleDay.objects.filter(pk=row.pk).update(
                    start_time_morning=start, end_time_morning=end,
                    start_time_afternoon=None, end_time_afternoon=None)
        if not schedule.is_intensive:
            self._log("  Horario base: %s -> %s (jornada intensiva)" % (
                tracts(schedule), new))
            changed.append("base")
        # Sin save(): sus validaciones son las del formulario del panel.
        type(schedule).objects.filter(pk=schedule.pk).update(
            start_time_morning=start, end_time_morning=end,
            start_time_afternoon=None, end_time_afternoon=None,
            is_intensive=True, updated_at=timezone.now())
        if not changed:
            raise CommandError("No tiene ningún día partido: nada que "
                               "cambiar.")
        who = by.user.get_full_name() or by.user.username
        note = ("%s: horario cambiado a jornada continua %s (%s), con "
                "efecto en todo lo fichado, por %s. Motivo: %s" % (
                    timezone.localdate().strftime("%d/%m/%Y"), new,
                    ", ".join(c for c in changed if c != "base")
                    or "todos los días", who, options["reason"]))[:255]
        WorkerClockSetting.objects.filter(pk=setting.pk).update(
            schedule_note=note, updated_by=by, updated_at=timezone.now())
        self._log("Nota en su ficha: %s" % note)
        after = self._report(company, user_id, date_from, date_to)
        gained = 0
        for day in sorted(set(before) | set(after)):
            old = before.get(day, [0, 0])
            now = after.get(day, [0, 0])
            if old == now:
                continue
            gained += now[0] - old[0]
            self._log("  %s %s: trabajado %s -> %s%s" % (
                DAYS[day.weekday()], day.strftime("%d/%m/%Y"),
                format_duration(old[0]), format_duration(now[0]),
                " (ya no se descuenta la comida)"
                if old[1] and not now[1] else ""))
        self._log("Fin: %s más en lo fichado desde el %s." % (
            format_duration(gained), date_from.strftime("%d/%m/%Y")))
