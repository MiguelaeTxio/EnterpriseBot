# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_medical.py
"""
Medical leaves in the new interface (S163).

---

Bajas médicas en la nueva interfaz (S163), copiado de
panel/views_personal_medical_leave.py: en Personal › Salud se añade una
baja a la persona abierta y, sobre las bajas marcadas, se les da el
alta (fecha de fin) o se borran (registradas por error). Una baja
abierta deja al trabajador "de baja" (sin recordatorios de fichaje).
"""
import datetime

from django.http import JsonResponse
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.models import MedicalLeavePeriod
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def medical_context(section):
    if section != "per":
        return {}
    return {"contingency_choices": MedicalLeavePeriod.ContingencyType.choices}


class MedicalLeaveAddView(SuperuserRequiredMixin, View):
    """
    POST: add a medical leave to one person (the open one).

    ---

    POST: añade una baja a la persona abierta (`person_pk`): inicio,
    alta opcional y tipo de contingencia.
    """

    def post(self, request):
        person = PersonIdentity.objects.filter(
            pk=request.POST.get("person_pk") or 0).first()
        if person is None:
            return _error("Abre primero a la persona (pulsa su nombre en el "
                          "listado).")
        date_start = _date(request.POST.get("date_start"))
        date_end = _date(request.POST.get("date_end"))
        contingency = request.POST.get("contingency_type", "")
        if date_start is None or contingency not in dict(
                MedicalLeavePeriod.ContingencyType.choices):
            return _error("Indica la fecha de inicio y el tipo.")
        if date_end is not None and date_end < date_start:
            return _error("El alta no puede ser anterior al inicio.")
        MedicalLeavePeriod.objects.create(
            person=person, date_start=date_start, date_end=date_end,
            contingency_type=contingency)
        return _ok("Baja de %s %s desde el %s." % (
            person.given_name, person.first_surname,
            date_start.strftime("%d/%m/%Y")))


class MedicalLeaveRowsView(SuperuserRequiredMixin, View):
    """
    POST `action` on the marked leaves: close (date_end) or delete.

    ---

    POST sobre las bajas marcadas: `close` les da el alta en `date_end`
    (nunca antes de su inicio); `delete` borra las registradas por error.
    """

    def post(self, request):
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        leaves = list(MedicalLeavePeriod.objects.filter(pk__in=ids))
        if not leaves:
            return _error("Marca primero las bajas.")
        action = request.POST.get("action", "")
        if action == "close":
            date_end = _date(request.POST.get("date_end"))
            if date_end is None:
                return _error("Indica la fecha de alta.")
            closed, wrong = 0, []
            for leave in leaves:
                if date_end < leave.date_start:
                    wrong.append(leave.date_start.strftime("%d/%m/%Y"))
                    continue
                leave.date_end = date_end
                leave.save(update_fields=["date_end"])
                closed += 1
            message = "Alta el %s: %d baja(s) cerrada(s)." % (
                date_end.strftime("%d/%m/%Y"), closed)
            if wrong:
                message += " No se cierran (empiezan después): %s." % (
                    ", ".join(wrong))
            return _ok(message) if closed else _error(message)
        if action == "delete":
            for leave in leaves:
                leave.delete()
            return _ok("%d baja(s) borrada(s)." % len(leaves))
        return _error("Acción no válida.")
