# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_service.py
"""
H30 (S131). Services and hour/km readings of a cost centre, entered
by hand from its detail page, and the advance of the service notices.

---

H30 (S131). Revisiones y lecturas de horas/km de un centro de gasto,
introducidas a mano desde su ficha (apartado "Revisiones"), y la
antelación de los avisos de revisión (Avisos > Configuración). Miguel
Ángel: "introducción manual de revisiones hechas: fecha, horas y
kilómetros de la revisión [...] introducción manual de lecturas de
horas y kilómetros, con fecha" -- el enlace con el programa del
surtidor queda para más adelante.
"""
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from fleet import service_plan_service as plan
from fleet.models import (
    MachineAsset, MachineMeterReading, MachineServiceAlertSettings,
    MachineServiceRecord,
)
from panel.mixins import CompanyUserRequiredMixin

# Roles que anotan revisiones y lecturas: los que editan la ficha
# (ADMIN, DOCS_SUPERVISOR) y los de taller (SUPERVISOR, WORKSHOPBOSS).
SERVICE_EDIT_ROLES = {
    "ADMIN", "DOCS_SUPERVISOR", "SUPERVISOR", "WORKSHOPBOSS",
}
# La antelación de los avisos la fija quien configura los avisos.
SERVICE_SETTINGS_ROLES = {"ADMIN", "DOCS_SUPERVISOR"}
SERVICE_LIST_LIMIT = 20
SERVICE_ANCHOR = "#machineServicePlan"


def can_edit_service(company_user):
    """
    True if the user may record services and readings.

    ---

    True si el usuario puede anotar revisiones y lecturas.
    """
    return company_user.role in SERVICE_EDIT_ROLES


def machine_service_context(machine, company_user):
    """
    Context of the "Revisiones" section of the machine detail page.

    ---

    Contexto del apartado "Revisiones" de la ficha: estado de cada
    revisión configurada, últimas revisiones y lecturas, y permisos.
    Todo resuelto aquí; la plantilla solo pinta.
    """
    records = list(
        MachineServiceRecord.objects.filter(machine=machine)
        .select_related("created_by__user"),
    )
    readings = list(
        MachineMeterReading.objects.filter(machine=machine)
        .select_related("created_by__user"),
    )
    advance = plan.advance_by_company().get(machine.company_id)
    statuses = plan.schedule_statuses(machine, records, readings, advance)
    for status in statuses:
        status.css_class = {
            plan.STATE_OVERDUE: "text-danger fw-bold",
            plan.STATE_UPCOMING: "text-warning-emphasis fw-bold",
        }.get(status.state, "text-muted")
    enabled = {
        schedule.key for schedule, _interval
        in plan.enabled_schedules(machine)
    }
    return {
        "service_statuses": statuses,
        "service_records": records[:SERVICE_LIST_LIMIT],
        "service_records_count": len(records),
        "meter_readings": readings[:SERVICE_LIST_LIMIT],
        "meter_readings_count": len(readings),
        "service_list_limit": SERVICE_LIST_LIMIT,
        "has_service_plan": machine.has_service_plan,
        "service_has_hours": plan.KEY_HOURS in enabled,
        "service_has_km": plan.KEY_KM in enabled,
        "can_edit_service": can_edit_service(company_user),
        "service_today": date.today().isoformat(),
    }


def _parse_count(raw, label):
    """
    Non-negative integer from a form value ("" -> None).

    ---

    Entero no negativo de un campo del formulario ("" -> None). Admite
    el punto de miles ("1.650"). Lanza ValueError con el mensaje.
    """
    raw = (raw or "").strip().replace(".", "").replace(" ", "")
    if not raw:
        return None
    if not raw.isdigit():
        raise ValueError("%s debe ser un número entero." % label)
    return int(raw)


def _parse_date(raw, label):
    """
    ISO date from a form value; required and not in the future.

    ---

    Fecha del formulario (AAAA-MM-DD), obligatoria y no futura.
    """
    try:
        value = date.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValueError("Indica la %s." % label)
    if value > date.today():
        raise ValueError("La %s no puede ser futura." % label)
    return value


def _back_to_machine(request, machine):
    """
    Redirect to the machine detail page, at the "Revisiones" section.

    ---

    Vuelve a la ficha, al apartado "Revisiones", conservando back_url.
    """
    params = {"service_open": "1"}
    back_url = request.POST.get("back_url") or request.GET.get("back_url")
    if back_url:
        params["back_url"] = back_url
    return redirect("%s?%s%s" % (
        reverse("panel:documentation_machine_detail", args=[machine.pk]),
        urlencode(params), SERVICE_ANCHOR,
    ))


class _ServiceEditMixin(CompanyUserRequiredMixin):
    """
    Common permission check of the service write views.

    ---

    Comprobación de permiso común de las vistas que escriben.
    """

    def _forbidden(self, request):
        if can_edit_service(request.user.company_user):
            return None
        return HttpResponse(
            "No tienes permiso para anotar revisiones ni lecturas.",
            status=403,
        )


class MachineServiceRecordCreateView(_ServiceEditMixin, View):
    """
    POST: record one service already done (date, hours, km).

    ---

    POST: anota una revisión hecha. Fecha obligatoria; horas y km
    opcionales (S131, Miguel Ángel: hay que poder poner las fechas de
    revisión aunque no estén las horas). Con horas cuenta para la
    revisión por horas y con km para la de km; solo con fecha, no
    avisa hasta que se anoten.
    """

    def post(self, request, pk):
        forbidden = self._forbidden(request)
        if forbidden is not None:
            return forbidden
        machine = get_object_or_404(MachineAsset, pk=pk)
        try:
            service_date = _parse_date(
                request.POST.get("service_date"), "fecha de la revisión",
            )
            hours = _parse_count(request.POST.get("hours"), "Las horas")
            crane_hours = _parse_count(
                request.POST.get("crane_hours"), "Las horas de grúa",
            )
            km = _parse_count(request.POST.get("km"), "Los kilómetros")
        except ValueError as exc:
            messages.error(request, str(exc))
            return _back_to_machine(request, machine)
        MachineServiceRecord.objects.create(
            machine=machine, service_date=service_date, hours=hours,
            crane_hours=crane_hours, km=km,
            notes=(request.POST.get("notes") or "").strip()[:255],
            created_by=request.user.company_user,
        )
        messages.success(request, "Revisión anotada.")
        return _back_to_machine(request, machine)


class MachineServiceRecordDeleteView(_ServiceEditMixin, View):
    """
    POST: delete one recorded service (entered by mistake).

    ---

    POST: borra una revisión anotada por error.
    """

    def post(self, request, pk, record_pk):
        forbidden = self._forbidden(request)
        if forbidden is not None:
            return forbidden
        record = get_object_or_404(
            MachineServiceRecord, pk=record_pk, machine_id=pk,
        )
        machine = record.machine
        record.delete()
        messages.success(request, "Revisión borrada.")
        return _back_to_machine(request, machine)


class MachineMeterReadingCreateView(_ServiceEditMixin, View):
    """
    POST: record one hours/km reading with its date.

    ---

    POST: anota una lectura de horas y/o kilómetros con su fecha (al
    menos uno de los dos).
    """

    def post(self, request, pk):
        forbidden = self._forbidden(request)
        if forbidden is not None:
            return forbidden
        machine = get_object_or_404(MachineAsset, pk=pk)
        try:
            reading_date = _parse_date(
                request.POST.get("reading_date"), "fecha de la lectura",
            )
            hours = _parse_count(request.POST.get("hours"), "Las horas")
            crane_hours = _parse_count(
                request.POST.get("crane_hours"), "Las horas de grúa",
            )
            km = _parse_count(request.POST.get("km"), "Los kilómetros")
            if hours is None and km is None and crane_hours is None:
                raise ValueError("Indica las horas, los km o los dos.")
        except ValueError as exc:
            messages.error(request, str(exc))
            return _back_to_machine(request, machine)
        MachineMeterReading.objects.create(
            machine=machine, reading_date=reading_date, hours=hours,
            crane_hours=crane_hours, km=km,
            created_by=request.user.company_user,
        )
        messages.success(request, "Lectura anotada.")
        return _back_to_machine(request, machine)


class MachineMeterReadingDeleteView(_ServiceEditMixin, View):
    """
    POST: delete one reading (entered by mistake).

    ---

    POST: borra una lectura anotada por error.
    """

    def post(self, request, pk, reading_pk):
        forbidden = self._forbidden(request)
        if forbidden is not None:
            return forbidden
        reading = get_object_or_404(
            MachineMeterReading, pk=reading_pk, machine_id=pk,
        )
        machine = reading.machine
        reading.delete()
        messages.success(request, "Lectura borrada.")
        return _back_to_machine(request, machine)


def service_alert_settings_dict(company):
    """
    Advance settings of the company, for the client.

    ---

    Antelación de los avisos de revisión de la empresa (None = sin
    antelación: solo vencidas).
    """
    settings = MachineServiceAlertSettings.objects.filter(
        company=company,
    ).first()
    return {
        "hours_advance": settings.hours_advance if settings else None,
        "km_advance": settings.km_advance if settings else None,
    }


class MachineServiceAlertSettingsSaveView(CompanyUserRequiredMixin, View):
    """
    POST: save the advance (hours, km) of the service notices.

    ---

    POST: guarda la antelación de los avisos de revisión, en horas y
    en km. Vacío = solo se avisa de vencidas.
    """

    def post(self, request):
        company_user = request.user.company_user
        if company_user.role not in SERVICE_SETTINGS_ROLES:
            return JsonResponse(
                {"ok": False, "error": "Solo los supervisores de "
                 "documentación y los administradores configuran los "
                 "avisos."},
                status=403,
            )
        try:
            hours = _parse_count(
                request.POST.get("hours_advance"), "La antelación en horas",
            )
            km = _parse_count(
                request.POST.get("km_advance"), "La antelación en km",
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        with transaction.atomic():
            settings, _created = (
                MachineServiceAlertSettings.objects.get_or_create(
                    company=company_user.company,
                )
            )
            settings.hours_advance = hours or None
            settings.km_advance = km or None
            settings.updated_by = company_user
            settings.save()
        return JsonResponse({
            "ok": True,
            "settings": service_alert_settings_dict(company_user.company),
        })
