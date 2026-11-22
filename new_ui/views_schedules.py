# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_schedules.py
"""
Workday schedules and clock types in the new interface (S163).

---

Horarios y tipos de fichaje en la nueva interfaz (S163), desde el panel
Acciones de Personal:
- «Lista de horarios»: crear, modificar y borrar horarios de jornada
  (iguales toda la semana o distintos según el día, abiertos,
  festivos...).
- «Tipos de fichaje»: crear y modificar tipos (no se borran: se
  desactivan, los fichajes hechos los conservan).
- «Horarios» y «Fichajes»: a los trabajadores marcados, horario propio
  (o quitarlo), sección desde una fecha, tipo de fichaje, ficha o no,
  recordatorios y desde qué día fichan.

Copiado de la interfaz antigua (panel/views_workorders.py
WorkdayScheduleView, panel/views_clock_events.py ClockTypeSaveView y
ClockWorkerSettingsView, panel/views_worker_schedules.py); los cambios
se hacen con los servicios de hr_calendar, como allí.
"""
import datetime

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.models import ClockType, WorkerClockSetting
from ivr_config.models import (
    CompanyUser, Section, WorkdaySchedule, WorkdayScheduleDay,
)
from new_ui.mixins import SuperuserRequiredMixin

WEEKDAY_NAMES = [
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado",
    "Domingo", "Festivos",
]
HOLIDAY_ROW = len(WEEKDAY_NAMES)

# Iconos de los tipos de fichaje (los del botón del trabajador).
TYPE_ICONS = [
    ("bi-box-arrow-in-right", "Entrada"),
    ("bi-truck", "Camión"),
    ("bi-people", "Personas"),
    ("bi-star", "Estrella"),
    ("bi-arrow-bar-right", "Flecha"),
    ("bi-tools", "Herramientas"),
    ("bi-hourglass-split", "Espera"),
    ("bi-clock", "Reloj"),
    ("bi-cup-hot", "Pausa"),
    ("bi-briefcase", "Maletín"),
    ("bi-geo-alt", "Ubicación"),
    ("bi-telephone", "Teléfono"),
]


def _company_user(request):
    return request.user.company_user


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _hm(value):
    return value.strftime("%H:%M") if value else ""


def _time(value):
    try:
        return datetime.datetime.strptime((value or "").strip(),
                                          "%H:%M").time()
    except ValueError:
        return None


def schedule_day_rows(sched):
    """
    [{number, name, works, sm, em, sa, ea}] of a schedule, Monday first.

    ---

    Las horas de cada día de un horario, de lunes a domingo y festivos,
    como texto HH:MM. Sin "distinto según el día", todos los días con
    las horas del horario.
    """
    by_day = {d.weekday: d for d in sched.days.all()}
    rows = []
    for number, name in enumerate(WEEKDAY_NAMES, start=1):
        day = by_day.get(number - 1)
        if (sched.varies_by_day and number == HOLIDAY_ROW
                and (day is None or not sched.works_holidays)):
            rows.append({"number": number, "name": name, "works": False,
                         "sm": "", "em": "", "sa": "", "ea": ""})
        elif sched.varies_by_day and day is not None:
            rows.append({
                "number": number, "name": name, "works": day.works,
                "sm": _hm(day.start_time_morning),
                "em": _hm(day.end_time_morning),
                "sa": _hm(day.start_time_afternoon),
                "ea": _hm(day.end_time_afternoon),
            })
        else:
            rows.append({
                "number": number, "name": name, "works": True,
                "sm": _hm(sched.start_time_morning),
                "em": _hm(sched.end_time_morning),
                "sa": "" if sched.is_intensive
                else _hm(sched.start_time_afternoon),
                "ea": "" if sched.is_intensive
                else _hm(sched.end_time_afternoon),
            })
    return rows


def days_summary(sched):
    """
    "L–J 08:00–13:30 / 15:00–18:00 · V 08:00–14:00" of a schedule.

    ---

    Resumen del horario: los días seguidos con las mismas horas, juntos;
    "(+1)" cuando la salida es del día siguiente; festivos aparte y solo
    si se trabajan.
    """
    if sched.is_open:
        return "Abierto (sin horas que comparar)"

    def hours(row):
        if not row["works"]:
            return "no se trabaja"
        return " / ".join(
            "%s–%s%s" % (row[a], row[b], " (+1)" if row[b] < row[a] else "")
            for a, b in (("sm", "em"), ("sa", "ea")) if row[a])

    groups, holiday = [], None
    for row in schedule_day_rows(sched):
        if row["number"] == HOLIDAY_ROW:
            holiday = row
            continue
        text = hours(row)
        if groups and groups[-1][2] == text:
            groups[-1][1] = row["name"]
        else:
            groups.append([row["name"], row["name"], text])
    parts = [
        "%s %s" % (first[:2] if first == last
                   else "%s–%s" % (first[:2], last[:2]), text)
        for first, last, text in groups
    ]
    if holiday is not None and holiday["works"] and sched.varies_by_day:
        parts.append("Festivos %s" % hours(holiday))
    return " · ".join(parts)


# ------------------------------------------------------------- horarios
def _parse_days(post):
    """
    ([{weekday, works, sm, em, sa, ea}], errors) of the day rows.

    ---

    Las horas de cada día del formulario y los errores. Cada tramo va
    entero o vacío; un día que se trabaja necesita al menos uno; el
    último tramo puede acabar al día siguiente (20:00-08:00).
    """
    days, errors = [], []
    works_holidays = bool(post.get("works_holidays"))
    for number, name in enumerate(WEEKDAY_NAMES, start=1):
        prefix = "day_%d_" % number
        works = bool(post.get(prefix + "works"))
        if number == HOLIDAY_ROW and not works_holidays:
            works = False
        values = {key: _time(post.get(prefix + key, ""))
                  for key in ("sm", "em", "sa", "ea")}
        if not works:
            days.append({"weekday": number - 1, "works": False,
                         "sm": None, "em": None, "sa": None, "ea": None})
            continue
        if (values["sm"] is None) != (values["em"] is None):
            errors.append("%s: la mañana necesita la entrada y la salida "
                          "(o ninguna)." % name)
        elif values["sm"] is not None and (
                values["em"] == values["sm"]
                or (values["em"] < values["sm"]
                    and values["sa"] is not None)):
            errors.append("%s: la salida de la mañana debe ser posterior "
                          "a la entrada." % name)
        if (values["sa"] is None) != (values["ea"] is None):
            errors.append("%s: la tarde necesita la entrada y la salida "
                          "(o ninguna)." % name)
        elif values["sm"] is None and values["sa"] is None:
            errors.append("%s: pon el horario de mañana, el de tarde o los "
                          "dos (o desmarca «Se trabaja»)." % name)
        elif values["sa"] is not None:
            if values["em"] and values["sa"] <= values["em"]:
                errors.append("%s: la entrada de la tarde debe ser "
                              "posterior a la salida de la mañana." % name)
            if values["ea"] == values["sa"]:
                errors.append("%s: la salida de la tarde no puede ser igual "
                              "que la entrada." % name)
        days.append({"weekday": number - 1, "works": True, **values})
    return days, errors


class ScheduleDataView(SuperuserRequiredMixin, View):
    """
    GET: one schedule as form fields, to load it in the editor.

    ---

    GET: un horario como campos del formulario («Esta fila» ›
    Modificar).
    """

    def get(self, request, pk):
        sched = get_object_or_404(
            WorkdaySchedule, pk=pk, company=_company_user(request).company)
        fields = {
            "schedule_pk": str(sched.pk), "label": sched.label,
            "season": sched.season, "is_intensive": sched.is_intensive,
            "start_time_morning": _hm(sched.start_time_morning),
            "end_time_morning": _hm(sched.end_time_morning),
            "start_time_afternoon": _hm(sched.start_time_afternoon),
            "end_time_afternoon": _hm(sched.end_time_afternoon),
            "tolerance_minutes": str(sched.tolerance_minutes),
            "is_default": sched.is_default,
            "varies_by_day": sched.varies_by_day,
            "is_open": sched.is_open, "works_holidays": sched.works_holidays,
        }
        for row in schedule_day_rows(sched):
            prefix = "day_%d_" % row["number"]
            fields[prefix + "works"] = row["works"]
            for key in ("sm", "em", "sa", "ea"):
                fields[prefix + key] = row[key]
        return JsonResponse({"ok": True, "title": sched.label,
                             "fields": fields})


class ScheduleSaveView(SuperuserRequiredMixin, View):
    """
    POST: create a schedule, or change one (`schedule_pk`).

    ---

    POST: crea un horario o modifica uno (`schedule_pk`), con las mismas
    comprobaciones que la gestión de horarios antigua. Un horario
    distinto según el día toma como horas generales las del primer día
    que se trabaja; uno abierto no compara el fichaje ni manda
    recordatorios (guarda 07:00-15:00 solo para los partes).
    """

    def post(self, request):
        company = _company_user(request).company
        post = request.POST
        sched = None
        raw_pk = post.get("schedule_pk", "").strip()
        if raw_pk:
            sched = WorkdaySchedule.objects.filter(
                pk=raw_pk if raw_pk.isdigit() else 0, company=company,
            ).first()
            if sched is None:
                return _error("No existe ese horario.")
        label = post.get("label", "").strip()
        season = post.get("season", WorkdaySchedule.Season.WINTER).strip()
        is_intensive = bool(post.get("is_intensive"))
        sm = post.get("start_time_morning", "").strip()
        em = post.get("end_time_morning", "").strip()
        sa = post.get("start_time_afternoon", "").strip()
        ea = post.get("end_time_afternoon", "").strip()
        varies = bool(post.get("varies_by_day"))
        is_open = bool(post.get("is_open"))
        works_holidays = bool(post.get("works_holidays"))
        if is_open:
            varies = False
            is_intensive = True
            sa = ea = ""
            if not sm or not em:
                sm, em = "07:00", "15:00"
        errors = []
        if not label:
            errors.append("El nombre del horario es obligatorio.")
        day_values = []
        if varies:
            day_values, day_errors = _parse_days(post)
            errors.extend(day_errors)
            first = next((d for d in day_values if d["works"]
                          and d["weekday"] < HOLIDAY_ROW - 1), None)
            if first is None and not day_errors:
                errors.append("Marca al menos un día que se trabaje.")
            elif first is not None:
                tracts = [(a, b) for a, b in (
                    (first["sm"], first["em"]), (first["sa"], first["ea"]),
                ) if a is not None]
                sm = tracts[0][0].strftime("%H:%M")
                em = tracts[0][1].strftime("%H:%M")
                is_intensive = len(tracts) == 1
                sa = tracts[1][0].strftime("%H:%M") if len(tracts) > 1 else ""
                ea = tracts[1][1].strftime("%H:%M") if len(tracts) > 1 else ""
            else:
                sm, em, is_intensive = "00:00", "00:01", True
        if season not in dict(WorkdaySchedule.Season.choices):
            errors.append("La temporada no es válida.")
        start_morning, end_morning = _time(sm), _time(em)
        if start_morning is None:
            errors.append("La entrada de la mañana debe ser HH:MM.")
        if end_morning is None:
            errors.append("La salida de la mañana debe ser HH:MM.")
        if start_morning and end_morning and (
                end_morning == start_morning
                or (end_morning < start_morning and not is_intensive)):
            errors.append("La salida de la mañana debe ser posterior a la "
                          "entrada.")
        start_afternoon = end_afternoon = None
        if not is_intensive:
            start_afternoon, end_afternoon = _time(sa), _time(ea)
            if start_afternoon is None or end_afternoon is None:
                errors.append("En jornada partida hacen falta la entrada y "
                              "la salida de la tarde.")
            if start_afternoon and end_morning and \
                    start_afternoon <= end_morning:
                errors.append("La entrada de la tarde debe ser posterior a "
                              "la salida de la mañana.")
            if start_afternoon and end_afternoon and \
                    end_afternoon == start_afternoon:
                errors.append("La salida de la tarde no puede ser igual que "
                              "la entrada.")
        try:
            tolerance = int(post.get("tolerance_minutes", "15").strip())
            if tolerance < 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append("La tolerancia debe ser un número entero "
                          "positivo.")
            tolerance = 15
        if errors:
            return _error(" ".join(errors))
        created = sched is None
        if created:
            sched = WorkdaySchedule(company=company)
        sched.label = label
        sched.season = season
        sched.is_intensive = is_intensive
        sched.start_time_morning = start_morning
        sched.end_time_morning = end_morning
        sched.start_time_afternoon = start_afternoon
        sched.end_time_afternoon = end_afternoon
        sched.tolerance_minutes = tolerance
        sched.is_default = bool(post.get("is_default"))
        sched.varies_by_day = varies
        sched.is_open = is_open
        sched.works_holidays = works_holidays
        sched.save()
        sched.days.all().delete()
        if sched.varies_by_day:
            WorkdayScheduleDay.objects.bulk_create([
                WorkdayScheduleDay(
                    schedule=sched, weekday=d["weekday"], works=d["works"],
                    start_time_morning=d["sm"], end_time_morning=d["em"],
                    start_time_afternoon=d["sa"],
                    end_time_afternoon=d["ea"],
                ) for d in day_values
            ])
        return _ok("Horario «%s» %s." % (
            label, "creado" if created else "guardado"), id=sched.pk)


class ScheduleDeleteView(SuperuserRequiredMixin, View):
    """
    POST `selected`: delete the marked schedules.

    ---

    POST `selected`: borra los horarios marcados; a quien los tenía en
    su usuario del panel se le quitan (como en la gestión antigua).
    """

    def post(self, request):
        company = _company_user(request).company
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        schedules = WorkdaySchedule.objects.filter(company=company,
                                                   pk__in=ids)
        labels = list(schedules.values_list("label", flat=True))
        if not labels:
            return _error("Marca primero los horarios a borrar.")
        CompanyUser.objects.filter(
            company=company, workday_schedule__in=schedules,
        ).update(workday_schedule=None)
        schedules.delete()
        return _ok("Horarios borrados: %s." % ", ".join(labels))


# ------------------------------------------------------- tipos de fichaje
class ClockTypeDataView(SuperuserRequiredMixin, View):
    """
    GET: one clock type as form fields.

    ---

    GET: un tipo de fichaje como campos del formulario.
    """

    def get(self, request, pk):
        clock_type = get_object_or_404(
            ClockType, pk=pk, company=_company_user(request).company)
        return JsonResponse({"ok": True, "title": clock_type.name, "fields": {
            "type_id": str(clock_type.pk), "name": clock_type.name,
            "icon": clock_type.icon, "role": clock_type.role,
            "counts_as_work": clock_type.counts_as_work,
            "is_active": clock_type.is_active,
            "order": str(clock_type.order),
        }})


class ClockTypeSaveView(SuperuserRequiredMixin, View):
    """
    POST: create or change one clock type.

    ---

    POST: crea o cambia un tipo de fichaje (nombre, icono, función,
    cuenta como jornada, activo, orden). El de por defecto no se
    desactiva; presencia y fuerza mayor no son jornada (van a la
    bolsa).
    """

    def post(self, request):
        company_user = _company_user(request)
        company = company_user.company
        raw = request.POST.get("type_id") or ""
        clock_type = None
        if raw:
            clock_type = ClockType.objects.filter(
                pk=raw if raw.isdigit() else 0, company=company).first()
            if clock_type is None:
                return _error("No existe ese tipo de fichaje.")
        name = " ".join((request.POST.get("name") or "").split())[:60]
        if not name:
            return _error("El tipo de fichaje necesita un nombre.")
        same = ClockType.objects.filter(company=company, name__iexact=name)
        if clock_type is not None:
            same = same.exclude(pk=clock_type.pk)
        if same.exists():
            return _error("Ya hay un tipo de fichaje llamado %s." % name)
        active = bool(request.POST.get("is_active"))
        if clock_type is not None and clock_type.is_default and not active:
            return _error("%s es el tipo por defecto y no se puede "
                          "desactivar." % clock_type.name)
        icon = request.POST.get("icon") or ""
        if icon not in dict(TYPE_ICONS):
            icon = TYPE_ICONS[0][0]
        try:
            order = max(0, min(int(request.POST.get("order") or 0), 999))
        except ValueError:
            order = 0
        created = clock_type is None
        if created:
            clock_type = ClockType(company=company)
        clock_type.name = name
        clock_type.icon = icon
        clock_type.counts_as_work = bool(request.POST.get("counts_as_work"))
        role = request.POST.get("role")
        if role in dict(ClockType.ROLE_CHOICES):
            clock_type.role = role
        if clock_type.role in ClockType.BAG_ROLES:
            clock_type.counts_as_work = False
        clock_type.is_active = active
        clock_type.order = order
        clock_type.updated_by = company_user
        clock_type.save()
        return _ok("Tipo de fichaje %s %s." % (
            name, "creado" if created else "guardado"), id=clock_type.pk)


# ------------------------------------------------ a los trabajadores marcados
def _marked_people(request):
    company = _company_user(request).company
    ids = [int(v) for v in request.POST.getlist("selected") if v.isdigit()]
    return list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=ids,
    ).select_related("company_user"))


class WorkerClockView(SuperuserRequiredMixin, View):
    """
    POST `action`: change schedule or clock-in settings of the marked.

    ---

    POST: a los trabajadores marcados (`action`):
    - schedule: horario propio (`schedule_id`; vacío lo quita y les toca
      el de su sección o el de por defecto).
    - section: sección desde una fecha (hoy si no se dice).
    - clock_mode: tipo de fichaje (como su sección, normal, normal con
      «No he parado para comer», por tipos).
    - clocks_on / clocks_off, reminders_on / reminders_off.
    - clocks_from: fichan desde un día (antes, ni avisos ni fichajes).
    """

    FLAGS = {
        "clocks_on": ("clocks", True, "obligados a fichar"),
        "clocks_off": ("clocks", False, "sin obligación de fichar"),
        "reminders_on": ("reminders", True, "con recordatorios"),
        "reminders_off": ("reminders", False, "sin recordatorios"),
    }

    def post(self, request):
        from hr_calendar import clock_settings

        company_user = _company_user(request)
        company = company_user.company
        people = _marked_people(request)
        if not people:
            return _error("Marca primero en el listado a los trabajadores.")
        ids = [p.pk for p in people]
        action = request.POST.get("action", "")
        if action == "schedule":
            raw = request.POST.get("schedule_id", "")
            schedule = None
            if raw:
                schedule = WorkdaySchedule.objects.filter(
                    pk=raw if raw.isdigit() else 0, company=company).first()
                if schedule is None:
                    return _error("No existe ese horario.")
            count = clock_settings.set_worker_schedule(
                people, schedule, company_user)
            if schedule is None:
                return _ok("%d trabajador(es) sin horario propio: les toca "
                           "el de su sección o el de por defecto." % count)
            return _ok("Horario %s puesto a %d trabajador(es)." % (
                schedule.label, count))
        if action == "section":
            from hr_calendar.balance import assign_section

            raw = request.POST.get("section_id", "")
            section = Section.objects.filter(
                pk=raw if raw.isdigit() else 0, company=company).first()
            if section is None:
                return _error("Elige la sección.")
            try:
                valid_from = datetime.date.fromisoformat(
                    request.POST.get("valid_from") or "")
            except ValueError:
                valid_from = timezone.localdate()
            assign_section(people, section, valid_from, company_user)
            return _ok("Sección %s desde el %s para %d trabajador(es)." % (
                section.name, valid_from.strftime("%d/%m/%Y"), len(people)))
        if action == "clock_mode":
            mode = request.POST.get("mode", "")
            labels = dict(WorkerClockSetting.CLOCK_MODE_CHOICES)
            if mode not in labels:
                return _error("Elige el tipo de fichaje.")
            count = clock_settings.set_worker_clock_mode(
                ids, mode, company_user)
            return _ok("%d trabajador(es): %s." % (
                count, labels[mode].lower()))
        if action == "clocks_from":
            try:
                day = datetime.date.fromisoformat(
                    request.POST.get("day") or "")
            except ValueError:
                return _error("Elige el día desde el que fichan.")
            count = clock_settings.set_worker_clocks_from(
                ids, day if day > timezone.localdate() else None,
                company_user)
            return _ok("%d trabajador(es) fichan desde el %s: antes, ni "
                       "avisos ni fichajes." % (
                           count, day.strftime("%d/%m/%Y")))
        flag = self.FLAGS.get(action)
        if flag is None:
            return _error("Acción no válida.")
        field, value, label = flag
        count = clock_settings.set_worker_flag(ids, field, value,
                                               company_user)
        return _ok("%d trabajador(es) %s." % (count, label))


def schedules_context(section, company):
    """
    Context of the schedule and clock actions (Personal only).

    ---

    Contexto de las acciones de horarios y fichaje (solo Personal).
    """
    if section != "per":
        return {}
    schedules = list(WorkdaySchedule.objects.filter(
        company=company).order_by("label"))
    return {
        "nui_schedules": schedules,
        "nui_sections": list(Section.objects.filter(
            company=company).order_by("name")),
        "nui_seasons": WorkdaySchedule.Season.choices,
        "nui_weekdays": list(enumerate(WEEKDAY_NAMES, start=1)),
        "nui_clock_modes": WorkerClockSetting.CLOCK_MODE_CHOICES,
        "nui_type_icons": TYPE_ICONS,
        "nui_type_roles": ClockType.ROLE_CHOICES,
        "nui_today": timezone.localdate().isoformat(),
    }
