# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_personal_section.py
"""
Section of one worker from their Personal file (H24, S144).

---

Sección de un trabajador desde su propia ficha de Personal (H24,
S144). Miguel Ángel: "que se pueda añadir la sección a un trabajador en
concreto, no solamente desde el listado, sino también desde la propia
ficha de personal". Misma asignación que Vacaciones y Horarios
(hr_calendar.balance.assign_section: una fila PersonSectionAssignment
desde una fecha, conservando el historial). El bloque se pinta dentro
de la ficha y se repinta solo al asignar.
"""
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from ivr_config.models import CompanyUser, Section
from panel.mixins import SupervisorAccessMixin

TEMPLATE = "panel/documentation_h30/_personal_section_block.html"
_ASSIGN_ROLES = (
    CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
    CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
)


def section_block_context(request, person, message="", error=False):
    """
    Context of the section block of a Personal file.
    ---
    Contexto del bloque Sección de la ficha: la sección vigente hoy y de
    dónde sale (asignación de Personal o, sin ella, la centralita), el
    historial de asignaciones y, para quien puede asignar, las secciones
    activas de la empresa.
    """
    from hr_calendar.clock_settings import current_sections
    from hr_calendar.models import PersonSectionAssignment

    company_user = request.user.company_user
    today = timezone.localdate()
    assignments = list(PersonSectionAssignment.objects.filter(
        person=person,
    ).select_related("section", "created_by__user").order_by(
        "-valid_from", "-pk"))
    in_force = next(
        (a for a in assignments if a.valid_from <= today), None)
    current = current_sections([person.pk]).get(person.pk)
    return {
        "person": person,
        "section_current": current,
        "section_assignment": in_force,
        "section_from_ivr": current is not None and in_force is None,
        "section_assignments": assignments,
        "section_choices": Section.objects.filter(
            company=company_user.company, is_active=True,
        ).order_by("name"),
        "section_today": today,
        "can_assign_section": company_user.role in _ASSIGN_ROLES,
        "section_message": message,
        "section_error": error,
    }


class PersonalSectionAssignView(SupervisorAccessMixin, View):
    """
    POST section_id, valid_from: assign the section to this worker.
    ---
    POST section_id, valid_from (hoy si no viene): asigna la sección a
    este trabajador desde esa fecha y devuelve el bloque repintado.
    """

    def post(self, request, pk):
        from hr_calendar.balance import assign_section
        from panel.views_vacation_balance import _parse_date

        person = PersonIdentity.objects.filter(pk=pk).first()
        if person is None:
            raise Http404
        raw = request.POST.get("section_id", "")
        section = Section.objects.filter(
            pk=raw if raw.isdigit() else 0,
            company=request.user.company_user.company,
        ).first()
        valid_from = (_parse_date(request.POST.get("valid_from"))
                      or timezone.localdate())
        if section is None:
            return render(request, TEMPLATE, section_block_context(
                request, person, "Elige la sección.", error=True))
        assign_section([person], section, valid_from,
                       request.user.company_user)
        return render(request, TEMPLATE, section_block_context(
            request, person, "Sección %s desde el %s." % (
                section.name, valid_from.strftime("%d/%m/%Y"))))
