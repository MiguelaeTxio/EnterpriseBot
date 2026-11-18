# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/set_out_round_up_s149.py
"""
Round a worker's OUT presses up from N minutes, and recompute the past.

---

S149 (Miguel Ángel, 18/11, Rocío Macías): "quiere que la empresa sepa
la hora real, que le cuente si echa 20 minutos más que le cuente como
media hora más". Decidido: solo ella, desde 15 minutos, y "todo lo
fichado menos lo visado". Pone out_round_up_minutes al trabajador y
recalcula la hora redondeada (rounded_at) de sus salidas ya fichadas,
salvo en los días visados o corregidos a mano (day_locked). La hora
real (pressed_at) no se toca nunca. Sin --apply solo dice lo que haría.
Log propio (com-standards 0bis).
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = ("Sube la salida de un trabajador a la media hora siguiente "
            "desde N minutos y recalcula lo fichado no visado.")

    def add_arguments(self, parser):
        parser.add_argument("--person", type=int, required=True,
                            help="Id de la persona (PersonIdentity).")
        parser.add_argument("--minutes", type=int, default=15)
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
            self._run(options["person"], options["minutes"],
                      options["apply"])

    def _run(self, person_id, minutes, apply):
        from document_explorer.models import PersonIdentity
        from hr_calendar.albaran_check import day_locked
        from hr_calendar.clock_rounding import round_pressed_at
        from hr_calendar.models import ClockEvent, WorkerClockSetting

        if not 6 <= minutes <= 25:
            raise CommandError("Los minutos van de 6 a 25.")
        person = PersonIdentity.objects.filter(pk=person_id).first()
        if person is None or person.company_user_id is None:
            raise CommandError("No existe esa persona o no ficha.")
        name = "%s %s, %s" % (person.first_surname,
                              person.second_surname or "",
                              person.given_name)
        self._log("%s: la salida sube a la media hora siguiente desde %d "
                  "min (%s)" % (name, minutes, "APLICANDO" if apply
                                else "simulación, sin cambios"))
        if apply:
            setting, _ = WorkerClockSetting.objects.get_or_create(
                person=person)
            setting.out_round_up_minutes = minutes
            setting.save(update_fields=["out_round_up_minutes",
                                        "updated_at"])
        locked_days, changed, kept = {}, 0, 0
        gained = 0
        for event in ClockEvent.objects.current().filter(
                company_user_id=person.company_user_id,
                kind=ClockEvent.Kind.OUT,
        ).order_by("pressed_at"):
            new = round_pressed_at(event.pressed_at, event.kind, minutes)
            old = event.rounded_at or round_pressed_at(event.pressed_at,
                                                       event.kind)
            if new == old:
                continue
            day = timezone.localtime(event.pressed_at).date()
            if day not in locked_days:
                locked_days[day] = day_locked(person.company_user, day)
            line = "%s salida %s: contaba %s, pasa a %s" % (
                day.strftime("%d/%m/%Y"),
                timezone.localtime(event.pressed_at).strftime("%H:%M"),
                timezone.localtime(old).strftime("%H:%M"),
                timezone.localtime(new).strftime("%H:%M"))
            if locked_days[day]:
                kept += 1
                self._log("  SIN TOCAR %s (%s)" % (line, locked_days[day]))
                continue
            changed += 1
            gained += int((new - old).total_seconds() // 60)
            self._log("  " + line)
            if apply:
                ClockEvent.objects.filter(pk=event.pk).update(
                    rounded_at=new)
        self._log("Fin: %d salida/s %s (+%d:%02d h), %d sin tocar por "
                  "estar visadas." % (
                      changed, "recalculada/s" if apply else "a recalcular",
                      gained // 60, gained % 60, kept))
