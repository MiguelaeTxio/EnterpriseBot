# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/common_filters.py
"""
Common filter block of every people tab (directive 4.27).

---

S153, directriz 4.27 del documento maestro (Miguel Ángel: "Queremos
filtrar por grupos en todas las pestañas. Queremos filtrar por sección
en todas las pestañas"). Contexto y filtrado del bloque común de
"Buscar y filtrar" de las pestañas de personas
(panel/_person_common_filters.html): Estado, Empresa, Grupo y Sección.
"""

NO_SECTION = "none"


def person_filter_context(request):
    """
    Context of the common people filter block.
    ---
    Contexto del bloque común (secciones, sección elegida, grupos y
    empresas). Estado y Empresa elegidos los da cada vista
    (filter_active, filter_company).
    """
    from ivr_config.models import Section
    from panel.person_groups import group_filter_select_context
    from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES

    company = request.user.company_user.company
    return {
        "sections": Section.objects.filter(
            company=company).order_by("name"),
        "no_section": NO_SECTION,
        "filter_section": request.GET.get("section", ""),
        "company_filter_choices": COMPANY_FILTER_CHOICES,
        **group_filter_select_context(request),
    }


def filter_people_by_section(people, company, section):
    """
    Keeps the people whose current section is `section`.
    ---
    Deja a las personas cuya sección vigente hoy es `section` (la misma
    regla que Horarios y Personal); NO_SECTION, las que no tienen;
    vacío, todas.
    """
    if not section:
        return list(people)
    from panel.views_worker_schedules import _rows

    keep = []
    for row in _rows(company, list(people)):
        current = row.state.section
        if section == NO_SECTION and current is None:
            keep.append(row.person)
        elif section.isdigit() and current is not None \
                and current.pk == int(section):
            keep.append(row.person)
    return keep


def common_people(request):
    """
    People that pass Estado, Empresa, Grupo and Sección (no search).
    ---
    Personas que cumplen el bloque común (Estado, Empresa, Grupo y
    Sección), sin la búsqueda de texto: para las pestañas cuyas filas
    no son personas (Solicitudes: una fila por solicitud) y filtran por
    la persona de cada fila. Devuelve (personas, estado, empresas).
    """
    from django.http import QueryDict

    from document_explorer.models import PersonIdentity
    from panel.views_documentation_h30 import (
        COMPANY_FILTER_CHOICES,
        _apply_personal_filters,
    )
    from panel.views_vacation_balance import _csv_param, _param

    active = _csv_param(request, "active", ["true"])
    companies = _csv_param(
        request, "company",
        [slug for slug, _l, _r in COMPANY_FILTER_CHOICES],
    )
    fake = QueryDict(mutable=True)
    fake.setlist("active", active)
    fake.setlist("company", companies)
    fake["group"] = _param(request, "group")
    proxy = type("FilterRequest", (), {"GET": fake})()
    people = _apply_personal_filters(
        PersonIdentity.objects.select_related("company_user__base"), proxy)
    people = filter_people_by_section(
        people, request.user.company_user.company,
        _param(request, "section"))
    return people, active, companies
