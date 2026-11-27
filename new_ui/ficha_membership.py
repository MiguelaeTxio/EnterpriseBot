# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/ficha_membership.py
"""
Section (SIME) and selection groups of a worker, from their own file.

---

Sección (SIME) y grupos de selección de un trabajador desde su propia
ficha de la nueva interfaz (S149, Miguel Ángel, 27/11, con la ficha de
Rogerio: "Ni le puedo asignar sección del SIME, ni nada [...] en la
antigua la teníamos" y "Debería de poder asignarlo en la ficha de forma
fácil. Y en la ficha de cada trabajador indicar a qué grupos pertenece
[...] puede pertenecer a un grupo determinado y además estar en la
administración").

La sección se asigna como en la antigua (panel/views_personal_section):
hr_calendar.balance.assign_section, una fila desde una fecha, con el
historial intacto. Los grupos siguen la regla de S147: se ven todos a
los que pertenece, pero solo se le mete o se le saca de los grupos que
creó quien guarda (new_ui.groups.can_edit).
"""
from datetime import date

from django.utils import timezone


def _group_path(group, by_pk):
    names = [group.name]
    parent = by_pk.get(group.parent_id)
    while parent is not None and len(names) < 10:
        names.insert(0, parent.name)
        parent = by_pk.get(parent.parent_id)
    return " › ".join(names)


def ficha_items(person, company_user):
    """
    The two ficha rows: (section item, groups item), for _ficha_item.
    ---
    Las dos filas de la ficha, ya armadas como _ficha_item.
    """
    from document_explorer.models import PersonGroupTemplate
    from hr_calendar.clock_settings import current_sections
    from hr_calendar.models import PersonSectionAssignment
    from ivr_config.models import Section
    from new_ui.groups import can_edit, owner_label

    today = timezone.localdate()
    in_force = PersonSectionAssignment.objects.filter(
        person=person, valid_from__lte=today,
    ).select_related("section").order_by("-valid_from", "-pk").first()
    current = current_sections([person.pk]).get(person.pk)
    if in_force is not None:
        shown = "%s (desde el %s)" % (
            in_force.section.name, in_force.valid_from.strftime("%d/%m/%Y"))
    elif current is not None:
        shown = "%s (de la centralita)" % current.name
    else:
        shown = ""
    section = {
        "label": "Sección (SIME)", "display": shown, "name": "section_id",
        "kind": "section",
        "value": current.pk if current is not None else "",
        "choices": list(Section.objects.filter(
            company=company_user.company).order_by("name")),
        "today": today.isoformat(),
    }
    groups = list(PersonGroupTemplate.objects.select_related(
        "created_by__user").order_by("name"))
    by_pk = {g.pk: g for g in groups}
    mine = set(person.group_templates.values_list("pk", flat=True))
    options = sorted((
        {"pk": g.pk, "path": _group_path(g, by_pk), "checked": g.pk in mine,
         "editable": can_edit(g, company_user), "owner": owner_label(g)}
        for g in groups), key=lambda o: o["path"].upper())
    group_item = {
        "label": "Grupos de selección",
        "display": ", ".join(o["path"] for o in options if o["checked"]),
        "name": "groups", "kind": "groups", "value": sorted(mine),
        "choices": [o for o in options if o["editable"] or o["checked"]],
    }
    return section, group_item


def save(request, person):
    """
    Apply the section and groups sent by the ficha; list of changes.
    ---
    Aplica la sección y los grupos que manda la ficha. Devuelve la lista
    de cambios hechos (vacía si no venía nada de esto) o lanza
    ValueError con el mensaje para el usuario.
    """
    from document_explorer.models import PersonGroupTemplate
    from hr_calendar.balance import assign_section
    from hr_calendar.clock_settings import current_sections
    from ivr_config.models import Section
    from new_ui.groups import can_edit

    company_user = request.user.company_user
    done = []
    raw = request.POST.get("section_id", "")
    if "section_sent" in request.POST and raw.isdigit():
        section = Section.objects.filter(
            pk=int(raw), company=company_user.company).first()
        if section is None:
            raise ValueError("Esa sección ya no existe.")
        valid_from = timezone.localdate()
        raw_day = request.POST.get("section_from", "").strip()
        if raw_day:
            try:
                valid_from = date.fromisoformat(raw_day)
            except ValueError:
                raise ValueError("Fecha de la sección no válida.")
        current = current_sections([person.pk], valid_from).get(person.pk)
        if current is None or current.pk != section.pk:
            assign_section([person], section, valid_from, company_user)
            done.append("sección %s desde el %s" % (
                section.name, valid_from.strftime("%d/%m/%Y")))
    if "groups_sent" in request.POST:
        wanted = {int(v) for v in request.POST.getlist("groups")
                  if v.isdigit()}
        mine = set(person.group_templates.values_list("pk", flat=True))
        for group in PersonGroupTemplate.objects.filter(
                pk__in=wanted ^ mine):
            if not can_edit(group, company_user):
                continue
            if group.pk in wanted:
                group.members.add(person)
                done.append("entra en %s" % group.name)
            else:
                group.members.remove(person)
                done.append("sale de %s" % group.name)
    return done
