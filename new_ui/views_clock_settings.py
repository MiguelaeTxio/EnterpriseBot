# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_clock_settings.py
"""
Company clock-in settings and mass review, new interface.

---

Ajustes de fichaje de la empresa y visado en masa en la nueva interfaz
(S163), copiado de panel/views_clock_events.py (ClockRemindersSwitchView,
ClockOvertimeCapView, ClockSectionSettingView, _mass_review y
_settings_context):
- Envío de recordatorios de la empresa (activar o desactivar).
- Tope de horas extra al mes (lo que pasa va a horas acumuladas).
- Cada sección: si ficha con la plataforma, si ficha por tipos o con el
  botón único y si ve la casilla «No he parado para comer».
- Visar (o quitar el visado de) los días con incidencias o procesados
  por la IA de los marcados, en unas fechas.
"""
import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.models import ClockEvent
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _sections(company):
    from ivr_config.models import Section

    return list(Section.objects.filter(company=company).order_by("name"))


def _parse_minutes(raw):
    """"7", "7,5" or "7:30" hours -> minutes; None if not valid."""
    raw = (raw or "").strip().replace(",", ".")
    try:
        if ":" in raw:
            hours, minutes = raw.split(":", 1)
            total = int(hours or 0) * 60 + int(minutes or 0)
        else:
            total = int(round(float(raw) * 60))
    except ValueError:
        return None
    return total if total > 0 else None


class ClockSettingsBlockView(SuperuserRequiredMixin, View):
    """
    GET: the company clock-in settings block (asked apart, repainted).

    ---

    GET: el bloque de ajustes de fichaje de la empresa: recordatorios,
    tope de horas extra y las secciones con sus tres ajustes.
    """

    def get(self, request):
        from hr_calendar.clock_extras import monthly_cap_seconds
        from hr_calendar.clock_settings import (
            reminders_enabled, section_clocks_map, section_meal_map,
            section_types_map,
        )

        company = request.user.company_user.company
        sections = _sections(company)
        ids = [s.pk for s in sections]
        clocks = section_clocks_map(ids)
        by_types = section_types_map(ids)
        by_meal = section_meal_map(ids)
        cap = monthly_cap_seconds(company) // 60
        return render(request, "new_ui/_clock_settings.html", {
            "reminders_on": reminders_enabled(company),
            "overtime_cap": "%d:%02d" % (cap // 60, cap % 60),
            "section_settings": [
                {"section": s, "clocks": clocks[s.pk],
                 "uses_types": by_types[s.pk], "meal_check": by_meal[s.pk]}
                for s in sections],
        })


class ClockSettingsSaveView(SuperuserRequiredMixin, View):
    """
    POST `what` (reminders | cap | section): one company setting.

    ---

    POST: guarda un ajuste: «reminders» (enabled), «cap» (hours: "7",
    "7,5" o "7:30"; 0 sin tope) o «section» (section_id con clocks,
    uses_types o meal_check).
    """

    def post(self, request):
        from hr_calendar import clock_settings

        company_user = request.user.company_user
        company = company_user.company
        what = request.POST.get("what", "")
        if what == "reminders":
            enabled = request.POST.get("enabled") == "1"
            clock_settings.set_reminders_enabled(company, enabled,
                                                 company_user)
            return _ok("Envío de recordatorios %s." % (
                "activado" if enabled else "desactivado"))
        if what == "cap":
            from hr_calendar.models import ClockSettings

            raw = (request.POST.get("hours") or "").strip()
            minutes = 0 if raw in ("0", "0:00") else _parse_minutes(raw)
            if minutes is None or minutes > 200 * 60:
                return _error("Escribe el tope en horas, por ejemplo 7 o "
                              "7:30.")
            settings, _created = ClockSettings.objects.get_or_create(
                company=company)
            settings.overtime_monthly_cap_minutes = minutes
            settings.updated_by = company_user
            settings.save()
            return _ok("Tope de horas extra: %d:%02d h al mes." % (
                minutes // 60, minutes % 60))
        if what == "section":
            from ivr_config.models import Section

            section = Section.objects.filter(
                pk=request.POST.get("section_id") or 0,
                company=company).first()
            if section is None:
                return _error("No existe esa sección.")
            if "uses_types" in request.POST:
                value = request.POST.get("uses_types") == "1"
                clock_settings.set_section_types(section, value,
                                                 company_user)
                return _ok("%s %s." % (section.name, "ficha por tipos"
                                       if value else
                                       "ficha con el botón único"))
            if "meal_check" in request.POST:
                value = request.POST.get("meal_check") == "1"
                clock_settings.set_section_meal(section, value,
                                                company_user)
                return _ok("%s %s." % (
                    section.name,
                    "ve la casilla «No he parado para comer»" if value
                    else "ya no ve la casilla «No he parado para comer»"))
            clocks = request.POST.get("clocks") == "1"
            clock_settings.set_section_clocks(section, clocks, company_user)
            return _ok("%s %s con la plataforma." % (
                section.name, "ficha" if clocks else "ya no ficha"))
        return _error("Ajuste desconocido.")


class MassReviewView(SuperuserRequiredMixin, View):
    """
    POST `action` (review | unreview), `desde`, `hasta`: the marked.

    ---

    POST: visa los días con incidencias o procesados por la IA
    (albaranes) de los marcados (personas o, en Fichajes, las de los
    fichajes marcados) entre dos fechas, o les quita el visado. Lo mismo
    que «Visar» de cada día en Jornadas.
    """

    def post(self, request):
        from hr_calendar.clock_report import reports_by_user
        from hr_calendar.models import ClockDayAiCheck, ClockDayReview

        company_user = request.user.company_user
        company = company_user.company
        ids = [int(v) for v in request.POST.getlist("selected")
               if v.isdigit()]
        if request.POST.get("tab") == "fichajes":
            users = sorted(set(ClockEvent.objects.filter(
                company=company, pk__in=ids).values_list(
                "company_user_id", flat=True)))
        else:
            users = list(PersonIdentity.objects.filter(
                pk__in=ids, company_user__isnull=False,
            ).values_list("company_user_id", flat=True))
        if not users:
            return _error("Marca algún trabajador (con cuenta del panel).")
        try:
            date_from = datetime.date.fromisoformat(
                request.POST.get("desde") or "")
            date_to = datetime.date.fromisoformat(
                request.POST.get("hasta") or "")
        except ValueError:
            return _error("Indica desde y hasta.")
        if date_to < date_from:
            return _error("Hasta no puede ser anterior a desde.")
        period = "del %s al %s" % (date_from.strftime("%d/%m/%Y"),
                                   date_to.strftime("%d/%m/%Y"))
        if request.POST.get("action") == "unreview":
            deleted, _detail = ClockDayReview.objects.filter(
                company_user_id__in=users, day__gte=date_from,
                day__lte=date_to).delete()
            return _ok("Quitado el visado de %d día(s) de %d trabajador(es) "
                       "(%s)." % (deleted, len(users), period))
        reports = reports_by_user(company, users, date_from, date_to)
        ai_days = set(ClockDayAiCheck.objects.filter(
            company_user_id__in=users, day__gte=date_from,
            day__lte=date_to).values_list("company_user_id", "day"))
        created = 0
        for user_id, report in reports.items():
            for day in {shift.day for shift in report.shifts
                        if shift.incidents
                        or (user_id, shift.day) in ai_days}:
                _review, new = ClockDayReview.objects.get_or_create(
                    company_user_id=user_id, day=day,
                    defaults={"reviewed_by": company_user})
                created += int(new)
        return _ok("Visados %d día(s) con incidencias o procesados por la "
                   "IA de %d trabajador(es) (%s)." % (
                       created, len(users), period))
