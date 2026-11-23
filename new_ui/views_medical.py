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


def absences_context(section, company):
    """Tipos de ausencia para «Registrar una ausencia» (Personal)."""
    if section != "per":
        return {}
    from hr_calendar.services import absence_categories

    return {"nui_absence_categories": list(absence_categories(company))}


class MedicalLeaveAddView(SuperuserRequiredMixin, View):
    """
    POST: add a medical leave to one person (the open one).

    ---

    POST: añade una baja a la persona abierta (`person_pk`): inicio,
    alta opcional y tipo de contingencia.
    """

    def post(self, request):
        # S163 (23/11): a los marcados (`selected`) o a la persona abierta.
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if not ids and (request.POST.get("person_pk") or "").isdigit():
            ids = [request.POST["person_pk"]]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if not people:
            return _error("Marca primero a los trabajadores.")
        date_start = _date(request.POST.get("date_start"))
        date_end = _date(request.POST.get("date_end"))
        contingency = request.POST.get("contingency_type", "")
        if date_start is None or contingency not in dict(
                MedicalLeavePeriod.ContingencyType.choices):
            return _error("Indica la fecha de inicio y el tipo.")
        if date_end is not None and date_end < date_start:
            return _error("El alta no puede ser anterior al inicio.")
        for person in people:
            MedicalLeavePeriod.objects.create(
                person=person, date_start=date_start, date_end=date_end,
                contingency_type=contingency)
        if len(people) == 1:
            return _ok("Baja de %s %s desde el %s." % (
                people[0].given_name, people[0].first_surname,
                date_start.strftime("%d/%m/%Y")))
        return _ok("Baja desde el %s a %d trabajadores." % (
            date_start.strftime("%d/%m/%Y"), len(people)))


class AbsenceAddView(SuperuserRequiredMixin, View):
    """
    POST: register the same absence to the marked workers.

    ---

    POST (S163, 23/11): registra la misma ausencia (tipo, del… al…,
    nota y horas opcionales) a los trabajadores marcados, con
    hr_calendar.services.create_absence_period (como el desglose).
    """

    def post(self, request):
        from hr_calendar.services import create_absence_period

        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if not people:
            return _error("Marca primero a los trabajadores.")
        date_start = _date(request.POST.get("date_start"))
        date_end = _date(request.POST.get("date_end")) or date_start
        if date_start is None:
            return _error("Indica la fecha de inicio.")
        category = request.POST.get("category_id") or ""
        cu = request.user.company_user
        done = 0
        for person in people:
            try:
                create_absence_period(
                    person, cu.company, cu,
                    int(category) if category.isdigit() else 0,
                    date_start, date_end, request.POST.get("note"))
            except ValueError as exc:
                return _error("%s (%d registradas antes)." % (exc, done)
                              if done else str(exc))
            done += 1
        return _ok("Ausencia del %s al %s a %d trabajador(es)." % (
            date_start.strftime("%d/%m/%Y"), date_end.strftime("%d/%m/%Y"),
            done))


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
