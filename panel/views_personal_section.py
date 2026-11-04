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
from panel.mixins import DocsUploadAccessMixin, SupervisorAccessMixin

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


class PersonalMassScheduleView(SupervisorAccessMixin, View):
    """
    POST selected, schedule_id: own schedule of the marked workers.
    ---
    POST selected (pks), schedule_id: pone a los marcados del listado de
    Personal un horario propio o se lo quita (schedule_id vacío: les
    toca el de su sección o el de por defecto). S144 (Miguel Ángel):
    "copiamos el pipeline de horarios [...] y lo replicamos en la
    pestaña de personal". La misma acción que la pestaña Horarios
    (hr_calendar.clock_settings.set_worker_schedule). Responde JSON
    {message, error}.
    """

    def post(self, request):
        from django.http import JsonResponse

        from hr_calendar.clock_settings import set_worker_schedule
        from ivr_config.models import WorkdaySchedule
        from panel.views_worker_schedules import _marked_people

        company = request.user.company_user.company
        people = _marked_people(request, company)
        if not people:
            return JsonResponse({"error": "Marca algún trabajador."})
        raw = request.POST.get("schedule_id", "")
        schedule = None
        if raw:
            schedule = WorkdaySchedule.objects.filter(
                pk=raw if raw.isdigit() else 0, company=company,
            ).first()
            if schedule is None:
                return JsonResponse({"error": "No existe ese horario."})
        count = set_worker_schedule(people, schedule,
                                    request.user.company_user)
        if schedule is not None:
            message = "Horario %s puesto a %d trabajador(es)." % (
                schedule.label, count)
        else:
            message = ("Horario propio quitado a %d trabajador(es): les "
                       "toca el de su sección o el de por defecto."
                       % count)
        return JsonResponse({"message": message})


class PersonalMassSectionView(SupervisorAccessMixin, View):
    """
    POST selected, section_id, valid_from: section of the marked.
    ---
    POST selected, section_id, valid_from (hoy si no viene): pone a los
    marcados del listado de Personal en esa sección desde esa fecha,
    conservando el historial (la misma acción que Horarios y Vacaciones,
    hr_calendar.balance.assign_section). Responde JSON {message, error}.
    """

    def post(self, request):
        from django.http import JsonResponse

        from hr_calendar.balance import assign_section
        from panel.views_vacation_balance import _parse_date
        from panel.views_worker_schedules import _marked_people

        company = request.user.company_user.company
        people = _marked_people(request, company)
        raw = request.POST.get("section_id", "")
        section = Section.objects.filter(
            pk=raw if raw.isdigit() else 0, company=company,
        ).first()
        valid_from = (_parse_date(request.POST.get("valid_from"))
                      or timezone.localdate())
        if section is None or not people:
            return JsonResponse(
                {"error": "Elige la sección y marca algún trabajador."})
        assign_section(people, section, valid_from,
                       request.user.company_user)
        return JsonResponse({"message": "Sección %s desde el %s para %d "
                             "trabajador(es)." % (
                                 section.name,
                                 valid_from.strftime("%d/%m/%Y"),
                                 len(people))})


class PersonalMassEmployerView(DocsUploadAccessMixin, View):
    """
    POST selected, employer: employer company of the marked workers.
    ---
    POST selected (pks), employer (slug de COMPANY_FILTER_CHOICES):
    pone a los marcados esa empresa (H24, S144; Miguel Ángel: "poder
    asignar a empresas desde ahí", pestaña Alta y baja de Personal). El
    texto es el canónico de esa empresa (el mismo del alta y de los
    contratos) y, si está activo, su documentación pasa a
    ACTIVOS/{EMPRESA}/ como cuando la empresa cambia por contrato
    (person_folder_service.relocate_if_needed, solo índice). Mismos
    roles que dar de alta y de baja (DocsUploadAccessMixin). JSON
    {message, error}.
    """

    def post(self, request):
        from django.http import JsonResponse

        from document_explorer.person_folder_service import (
            relocate_if_needed,
        )
        from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES

        choices = {slug: (label, raws[0])
                   for slug, label, raws in COMPANY_FILTER_CHOICES}
        slug = request.POST.get("employer", "")
        if slug not in choices:
            return JsonResponse({"error": "Elige la empresa."})
        label, text = choices[slug]
        wanted = [int(pk) for pk in request.POST.getlist("selected")
                  if pk.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=wanted))
        if not people:
            return JsonResponse({"error": "Marca algún trabajador."})
        changed = moved = 0
        for person in people:
            if (person.employer_company or "") == text:
                continue
            person.employer_company = text
            person.save(update_fields=["employer_company", "updated_at"])
            changed += 1
            if person.is_active_employee:
                relocated, _folder, _count = relocate_if_needed(person)
                moved += int(relocated)
        message = "%s para %d trabajador(es)" % (label, changed)
        if changed < len(people):
            message += " (%d ya la tenían)" % (len(people) - changed)
        if moved:
            message += "; documentación de %d trasladada a su carpeta" % moved
        return JsonResponse({"message": message + "."})
