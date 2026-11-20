# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/platforms_meal_schedule_s149.py
"""
Plataformas: single button with the meal box and their own schedule.

---

S149 (Miguel Ángel, 20/11): "los de plataformas [...] fichan sin tipo,
pero ellos no rellenan las partes [...] se les está descontando siempre
la hora de la comida [...] incluirle el casillero de no he parado a
comer [...] el horario de plataforma sería exactamente igual que el del
taller, pero la salida es a las 6:30 de la tarde".

1. La sección que se llama --section (nombre exacto) pasa al
   botón único con «No he parado para comer» (SectionClockSetting.
   meal_check).
2. Horario «Plataformas»: copia del de invierno del taller (--from)
   con la salida de la tarde a --end. Si ya existe, solo se ajusta la
   salida. El de verano sigue siendo el intensivo de todos.
3. Se lo pone a los trabajadores activos de esa sección (horario
   propio), con la nota del motivo, quién y cuándo.

Lo ya visado no cambia (las horas de los días visados no se recalculan
en ningún proceso); el resto de días se calcula con el horario nuevo.
Sin --apply, simulación (no cambia nada). Log propio (com-standards
0bis).
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class _Rollback(Exception):
    pass


class Command(BaseCommand):
    help = ("Plataformas: botón único con «No he parado para comer» y "
            "horario del taller con salida a las 18:30.")

    def add_arguments(self, parser):
        # S149: el nombre exacto ("plataforma" a secas cogía también
        # "Administración-Plataformas").
        parser.add_argument("--section", default="Plataformas")
        parser.add_argument("--from", dest="source", default="Taller")
        parser.add_argument("--label", default="Plataformas")
        parser.add_argument("--end", default="18:30")
        parser.add_argument("--by", required=True,
                            help="Usuario del panel que hace el cambio.")
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
            mode = ("APLICAR" if options["apply"]
                    else "SIMULACIÓN (no cambia nada)")
            self._log("MODO: %s" % mode)
            try:
                with transaction.atomic():
                    self._run(options)
                    if not options["apply"]:
                        raise _Rollback()
            except _Rollback:
                self._log("Simulación: deshecho todo.")

    def _run(self, options):
        from django.contrib.auth.models import User

        from document_explorer.models import PersonIdentity
        from hr_calendar.clock_settings import (
            current_sections, set_section_meal, set_worker_schedule,
        )
        from hr_calendar.models import WorkerClockSetting
        from ivr_config.models import Section, WorkdaySchedule

        user = User.objects.filter(username=options["by"]).first()
        by = getattr(user, "company_user", None) if user else None
        if by is None:
            raise CommandError("No existe el usuario %s." % options["by"])
        company = by.company
        end = datetime.datetime.strptime(options["end"], "%H:%M").time()

        sections = list(Section.objects.filter(
            company=company, name__iexact=options["section"]))
        if not sections:
            raise CommandError("No hay sección con «%s»." % options["section"])
        for section in sections:
            set_section_meal(section, True, by)
            self._log("Sección %s: botón único con «No he parado para "
                      "comer»." % section.name)

        source = WorkdaySchedule.objects.filter(
            company=company, label=options["source"],
            season=WorkdaySchedule.Season.WINTER).first()
        if source is None or source.varies_by_day:
            raise CommandError("No existe el horario de invierno «%s» "
                               "igual toda la semana." % options["source"])
        schedule = WorkdaySchedule.objects.filter(
            company=company, label=options["label"]).first()
        if schedule is None:
            schedule = WorkdaySchedule(company=company, label=options["label"])
            for field in ("season", "start_time_morning", "end_time_morning",
                          "start_time_afternoon", "is_intensive",
                          "tolerance_minutes", "varies_by_day", "is_open",
                          "works_holidays"):
                setattr(schedule, field, getattr(source, field))
            self._log("Horario nuevo «%s» (copia de «%s»)." % (
                schedule.label, source.label))
        else:
            self._log("Horario «%s» ya existía (id %d): se ajusta la salida."
                      % (schedule.label, schedule.pk))
        schedule.end_time_afternoon = end
        schedule.is_default = False
        schedule.save()
        self._log("  %s-%s / %s-%s, cortesía %s min" % (
            schedule.start_time_morning.strftime("%H:%M"),
            schedule.end_time_morning.strftime("%H:%M"),
            schedule.start_time_afternoon.strftime("%H:%M")
            if schedule.start_time_afternoon else "—",
            schedule.end_time_afternoon.strftime("%H:%M"),
            schedule.tolerance_minutes))

        people = list(PersonIdentity.objects.filter(
            company=company, is_active_employee=True))
        in_section = current_sections([p.pk for p in people])
        ids = {s.pk for s in sections}
        chosen = [p for p in people
                  if in_section.get(p.pk) is not None
                  and in_section[p.pk].pk in ids]
        settings = {s.person_id: s for s in WorkerClockSetting.objects.filter(
            person__in=chosen).select_related("workday_schedule")}
        self._log("Trabajadores activos de la sección: %d" % len(chosen))
        for n, person in enumerate(sorted(
                chosen, key=lambda p: (p.first_surname, p.given_name)), 1):
            setting = settings.get(person.pk)
            before = (setting.workday_schedule.label
                      if setting and setting.workday_schedule else "—")
            mode = setting.clock_mode if setting else ""
            warning = ("; OJO: tipo de fichaje propio «%s», manda sobre el "
                       "de la sección" % mode if mode else "")
            self._log("  [%d] %s %s, %s (persona %d, %s): horario %s → %s%s"
                      % (n, person.first_surname, person.second_surname or "",
                         person.given_name, person.pk,
                         in_section[person.pk].name, before, schedule.label,
                         warning))
        set_worker_schedule(chosen, schedule, by)
        note = ("%s: horario «%s» (taller con salida a las %s) y botón "
                "único con «No he parado para comer»; por %s." % (
                    timezone.localtime().strftime("%d/%m/%Y %H:%M"),
                    schedule.label, options["end"], by.user.username))
        WorkerClockSetting.objects.filter(person__in=chosen).update(
            schedule_note=note[:255])
        self._log("Hecho: %d trabajadores." % len(chosen))
