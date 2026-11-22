# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_crews.py
"""
Crews (vehicle + people), new interface.

---

Equipos (vehículo + persona) en la nueva interfaz (S163), copiado de
panel/views_crews.py (S153): en Centros de gasto › Equipos, alta de
equipos (la máquina abierta con una o varias personas desde una fecha)
y, sobre los marcados, terminarlos o borrarlos.
"""
import logging
from datetime import date

from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from fleet.models import Crew, MachineAsset
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


class CrewCreateView(SuperuserRequiredMixin, View):
    """
    POST: new crews (the open machine with one or more people).

    ---

    POST: alta de equipos: la máquina abierta con las personas marcadas
    en la lista desde la fecha indicada. Quien ya está en un equipo
    abierto de esa máquina no se repite.
    """

    def post(self, request):
        cu = request.user.company_user
        machine = MachineAsset.objects.filter(
            company=cu.company, pk=request.POST.get("machine_pk") or 0).first()
        people = list(PersonIdentity.objects.filter(
            company=cu.company,
            pk__in=[v for v in request.POST.getlist("person")
                    if v.isdigit()]))
        date_start = _date(request.POST.get("date_start"))
        if machine is None:
            return _error("Abre primero el centro de gasto.")
        if request.POST.getlist("person") and not people:
            return _error("Las personas marcadas no son de tu empresa.")
        if not people or date_start is None:
            return _error("Marca la persona o personas y la fecha.")
        notes = (request.POST.get("notes") or "").strip()[:255]
        created = 0
        for person in people:
            if Crew.objects.filter(machine=machine, person=person,
                                   date_end__isnull=True).exists():
                continue
            Crew.objects.create(
                company=cu.company, machine=machine, person=person,
                date_start=date_start, notes=notes, created_by=cu)
            created += 1
        skipped = len(people) - created
        return _ok("%d equipo(s) nuevo(s) en %s%s." % (
            created, machine.code,
            "; %d ya estaba(n) en un equipo abierto" % skipped
            if skipped else ""))


class CrewMassView(SuperuserRequiredMixin, View):
    """
    POST `action` (end | delete): end or delete the marked crews.

    ---

    POST: termina (con la fecha indicada o hoy) o borra los equipos
    marcados.
    """

    def post(self, request):
        cu = request.user.company_user
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        crews = Crew.objects.filter(company=cu.company, pk__in=ids)
        action = request.POST.get("action", "")
        if not crews.exists():
            return _error("Marca primero los equipos.")
        if action == "end":
            date_end = (_date(request.POST.get("date_end"))
                        or timezone.localdate())
            done = crews.update(date_end=date_end)
            return _ok("%d equipo(s) terminado(s) el %s." % (
                done, date_end.strftime("%d/%m/%Y")))
        if action == "delete":
            done = crews.count()
            logger.info("# [new_ui EQUIPOS] %s borra %d equipo(s)",
                        request.user.username, done)
            crews.delete()
            return _ok("%d equipo(s) borrado(s)." % done)
        return _error("Acción desconocida.")
