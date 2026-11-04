# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_personal_medical_leave.py
"""
Medical leaves of one worker from their Personal file (H24, S144).

---

Bajas médicas de un trabajador desde su ficha de Personal (H24, S144).
Miguel Ángel: "¿Cómo quito la baja? Que no encuentro cómo quitarla". No
había ninguna pantalla para MedicalLeavePeriod: la única baja de la base
de datos (de un parte de 2021, sin fecha de alta) dejaba al trabajador
"de baja" hasta hoy y no le llegaban los recordatorios de fichaje
(hr_calendar/clock_reminders._away). Aquí se ven sus bajas y, para quien
puede, se añade una, se le da el alta (fecha de fin) o se borra una
registrada por error. El bloque se pinta dentro del acordeón Laboral de
la ficha y se repinta solo.
"""
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.models import MedicalLeavePeriod
from ivr_config.models import CompanyUser
from panel.mixins import SupervisorAccessMixin

TEMPLATE = "panel/documentation_h30/_personal_medical_leave_block.html"
_EDIT_ROLES = (
    CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
    CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
)


def medical_leave_block_context(request, person, message="", error=False):
    """
    Context of the medical leave block of a Personal file.
    ---
    Contexto del bloque Bajas médicas de la ficha: las bajas (la más
    reciente arriba), si alguna sigue abierta y, para quien puede
    editar, los tipos de contingencia.
    """
    today = timezone.localdate()
    leaves = list(MedicalLeavePeriod.objects.filter(
        person=person,
    ).select_related("source_document").order_by("-date_start", "-pk"))
    return {
        "person": person,
        "medical_leaves": leaves,
        "medical_leave_open": any(
            leave.date_start <= today
            and (leave.date_end is None or leave.date_end >= today)
            for leave in leaves),
        "medical_leave_today": today,
        "contingency_choices": MedicalLeavePeriod.ContingencyType.choices,
        "can_edit_medical_leave": (
            request.user.company_user.role in _EDIT_ROLES),
        "medical_leave_message": message,
        "medical_leave_error": error,
    }


class PersonalMedicalLeaveView(SupervisorAccessMixin, View):
    """
    POST action=add|close|delete: change this worker's medical leaves.
    ---
    POST action: "add" (date_start, date_end opcional, contingency_type),
    "close" (leave_id, date_end: le da el alta) o "delete" (leave_id:
    una registrada por error). Devuelve el bloque repintado.
    """

    def post(self, request, pk):
        from panel.views_vacation_balance import _parse_date

        person = PersonIdentity.objects.filter(pk=pk).first()
        if person is None:
            raise Http404
        action = request.POST.get("action", "")
        leave = None
        raw_id = request.POST.get("leave_id", "")
        if raw_id.isdigit():
            leave = MedicalLeavePeriod.objects.filter(
                pk=int(raw_id), person=person).first()
        date_end = _parse_date(request.POST.get("date_end"))

        def reply(message, error=False):
            # S144: con la cabecera del acordeón fuera de banda (el
            # contador y "Abierta" se quedaban sin cambiar).
            return render(request, TEMPLATE, {
                **medical_leave_block_context(request, person, message,
                                              error),
                "medical_leave_oob": True,
            })

        if action == "add":
            date_start = _parse_date(request.POST.get("date_start"))
            contingency = request.POST.get("contingency_type", "")
            if date_start is None or contingency not in dict(
                    MedicalLeavePeriod.ContingencyType.choices):
                return reply("Indica la fecha de inicio y el tipo.", True)
            if date_end is not None and date_end < date_start:
                return reply("El alta no puede ser anterior al inicio.",
                             True)
            MedicalLeavePeriod.objects.create(
                person=person, date_start=date_start, date_end=date_end,
                contingency_type=contingency,
            )
            return reply("Baja añadida desde el %s." % date_start.strftime(
                "%d/%m/%Y"))
        if leave is None:
            return reply("No existe esa baja.", True)
        if action == "close":
            if date_end is None:
                return reply("Indica la fecha de alta.", True)
            if date_end < leave.date_start:
                return reply("El alta no puede ser anterior al inicio "
                             "(%s)." % leave.date_start.strftime(
                                 "%d/%m/%Y"), True)
            leave.date_end = date_end
            leave.save(update_fields=["date_end"])
            return reply("Alta el %s: la baja queda cerrada." %
                         date_end.strftime("%d/%m/%Y"))
        if action == "delete":
            start = leave.date_start.strftime("%d/%m/%Y")
            leave.delete()
            return reply("Baja del %s borrada." % start)
        return reply("Acción no válida.", True)
