# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_service.py
"""
Services, meter readings and logbook of a cost centre, new interface.

---

Revisiones, lecturas de contador y libro historial de un centro de
gasto en la nueva interfaz (S163), copiado de
panel/views_machine_service.py y panel/views_machine_logbook.py:
- Acciones › «Del centro de gasto»: estado de sus revisiones (vencida,
  próxima...), generar su libro historial (grúas A y H) y descargar el
  libro para externos.
- Centros de gasto › Revisiones y › Lecturas: anotar una (a la máquina
  abierta) y borrar las marcadas.
"""
import logging
from datetime import date

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from fleet import service_plan_service as plan
from fleet.models import MachineAsset, MachineMeterReading, MachineServiceRecord
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _count(raw, label):
    """Entero no negativo ("1.650" vale); vacío -> None."""
    raw = (raw or "").strip().replace(".", "").replace(" ", "")
    if not raw:
        return None
    if not raw.isdigit():
        raise ValueError("%s debe ser un número entero." % label)
    return int(raw)


def _date(raw, label):
    """Fecha obligatoria y no futura."""
    try:
        value = date.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValueError("Indica la %s." % label)
    if value > date.today():
        raise ValueError("La %s no puede ser futura." % label)
    return value


def _machine(request):
    return MachineAsset.objects.filter(
        pk=request.POST.get("machine_pk") or 0).first()


def service_statuses(machine):
    """
    State of each configured service of the machine.

    ---

    Estado de cada revisión configurada (vencida, próxima o al día),
    con el mismo cálculo que la ficha antigua.
    """
    records = list(MachineServiceRecord.objects.filter(machine=machine))
    readings = list(MachineMeterReading.objects.filter(machine=machine))
    advance = plan.advance_by_company().get(machine.company_id)
    statuses = plan.schedule_statuses(machine, records, readings, advance)
    for status in statuses:
        status.css_class = {
            plan.STATE_OVERDUE: "text-danger fw-bold",
            plan.STATE_UPCOMING: "text-warning-emphasis fw-bold",
        }.get(status.state, "text-muted")
    return statuses


class MachinePanelView(SuperuserRequiredMixin, View):
    """
    GET: the «Del centro de gasto» block of the open machine.

    ---

    GET: el bloque «Del centro de gasto»: estado de sus revisiones y el
    libro historial (si es grúa A o H).
    """

    def get(self, request, pk):
        from fleet.logbook_service import is_logbook_machine

        machine = get_object_or_404(MachineAsset, pk=pk)
        return render(request, "new_ui/_machine_panel.html", {
            "machine": machine,
            "has_service_plan": machine.has_service_plan,
            "service_statuses": service_statuses(machine)
            if machine.has_service_plan else [],
            "is_logbook": is_logbook_machine(machine),
        })


class ServiceRecordAddView(SuperuserRequiredMixin, View):
    """
    POST: record a service done on the open machine.

    ---

    POST: anota una revisión hecha (fecha obligatoria; horas, horas de
    grúa y km opcionales) a la máquina abierta.
    """

    def post(self, request):
        machine = _machine(request)
        if machine is None:
            return _error("Abre primero el centro de gasto.")
        try:
            service_date = _date(request.POST.get("service_date"),
                                 "fecha de la revisión")
            hours = _count(request.POST.get("hours"), "Las horas")
            crane_hours = _count(request.POST.get("crane_hours"),
                                 "Las horas de grúa")
            km = _count(request.POST.get("km"), "Los kilómetros")
        except ValueError as exc:
            return _error(str(exc))
        MachineServiceRecord.objects.create(
            machine=machine, service_date=service_date, hours=hours,
            crane_hours=crane_hours, km=km,
            notes=(request.POST.get("notes") or "").strip()[:255],
            created_by=request.user.company_user)
        return _ok("Revisión de %s anotada." % machine.code)


class ReadingAddView(SuperuserRequiredMixin, View):
    """
    POST: record an hours/km reading of the open machine.

    ---

    POST: anota una lectura de horas, horas de grúa y/o km (al menos
    una) con su fecha a la máquina abierta.
    """

    def post(self, request):
        machine = _machine(request)
        if machine is None:
            return _error("Abre primero el centro de gasto.")
        try:
            reading_date = _date(request.POST.get("reading_date"),
                                 "fecha de la lectura")
            hours = _count(request.POST.get("hours"), "Las horas")
            crane_hours = _count(request.POST.get("crane_hours"),
                                 "Las horas de grúa")
            km = _count(request.POST.get("km"), "Los kilómetros")
            if hours is None and km is None and crane_hours is None:
                raise ValueError("Indica las horas, los km o los dos.")
        except ValueError as exc:
            return _error(str(exc))
        MachineMeterReading.objects.create(
            machine=machine, reading_date=reading_date, hours=hours,
            crane_hours=crane_hours, km=km,
            created_by=request.user.company_user)
        return _ok("Lectura de %s anotada." % machine.code)


class ServiceRowsDeleteView(SuperuserRequiredMixin, View):
    """
    POST `selected`, `kind` (records | readings): delete the marked.

    ---

    POST: borra las revisiones o lecturas marcadas (anotadas por
    error).
    """

    def post(self, request):
        model = {"records": MachineServiceRecord,
                 "readings": MachineMeterReading}.get(
            request.POST.get("kind", ""))
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if model is None or not ids:
            return _error("Marca primero lo que quieres borrar.")
        deleted, _detail = model.objects.filter(pk__in=ids).delete()
        return _ok("%d borrada(s)." % deleted)


class LogbookGenerateView(SuperuserRequiredMixin, View):
    """
    POST: generate and store the logbook of the open A/H crane.

    ---

    POST: genera y guarda el libro historial de la grúa A/H abierta
    (queda como su documento «Libro historial»).
    """

    def post(self, request):
        from fleet.logbook_service import (
            LogbookReadError, generate_logbook, is_logbook_machine,
        )

        machine = _machine(request)
        if machine is None:
            return _error("Abre primero el centro de gasto.")
        if not is_logbook_machine(machine):
            return _error("Solo las grúas móviles A y H llevan libro "
                          "historial.")
        try:
            entry = generate_logbook(machine, request.user.company_user)
        except LogbookReadError as exc:
            return _error(str(exc))
        except Exception:  # noqa: BLE001 -- se registra y se avisa
            logger.exception("# [new_ui LogbookGenerateView] %s",
                             machine.code)
            return _error("No se pudo generar el libro historial. Inténtalo "
                          "de nuevo y, si se repite, avisa al "
                          "administrador.")
        return _ok("Libro historial generado y guardado: %s." % entry.name)


class LogbookExternalView(SuperuserRequiredMixin, View):
    """
    GET: download the logbook for external companies (not stored).

    ---

    GET: el libro para compartir con empresas de fuera (sin nombres de
    mecánicos); no se guarda en el cubo.
    """

    def get(self, request, pk):
        from fleet.logbook_service import (
            is_logbook_machine, render_logbook_pdf,
        )

        machine = get_object_or_404(MachineAsset, pk=pk)
        if not is_logbook_machine(machine):
            return HttpResponse("Solo las grúas A y H llevan libro "
                                "historial.", status=400)
        data = render_logbook_pdf(machine, external=True)
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = (
            'attachment; filename="%s_LIBRO_HISTORIAL_EXTERNO_%s.pdf"' % (
                machine.code, timezone.localdate().strftime("%Y%m%d")))
        return response
