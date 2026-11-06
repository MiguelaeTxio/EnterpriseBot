# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/person_groups.py
"""
Selection groups of the Personal tab as a tree (S147).

---

Grupos de selección de la pestaña Personal en árbol (S147, Miguel
Ángel): "grupos y subfamilias de grupos [...] desplegar Plataformas y
tener Administración, Comercial, Taller, Transportistas" y "puedes
seleccionar varios grupos hijos, como con casillero". Un grupo con
subgrupos no tiene miembros sueltos. Aquí se arma el árbol que pinta
_personal_pane.html y se validan los cambios que guarda
PersonGroupTemplateSaveView.
"""
from document_explorer.models import PersonGroupTemplate


class GroupError(ValueError):
    """
    A change that breaks the tree rules; the message is for the user.
    ---
    Un cambio que rompe las reglas del árbol; el mensaje es para el
    usuario.
    """


def _label(person):
    return "%s %s, %s" % (person.first_surname, person.second_surname,
                          person.given_name)


def group_tree():
    """
    Flat list of the groups in tree order, with depth and members.
    ---
    Lista plana en orden de árbol (padre y debajo sus subgrupos, por
    nombre). Cada nodo: group, depth, children (pks de los hijos
    directos), member_ids y member_names (los suyos; vacío si tiene
    subgrupos) y total (personas distintas, contando sus subgrupos).
    """
    groups = list(PersonGroupTemplate.objects.prefetch_related(
        "members").order_by("name"))
    by_parent = {}
    for group in groups:
        by_parent.setdefault(group.parent_id, []).append(group)
    nodes, totals = [], {}

    def members_of(group):
        if group.pk in totals:
            return totals[group.pk]
        ids = {p.pk for p in group.members.all()}
        for child in by_parent.get(group.pk, []):
            ids |= members_of(child)
        totals[group.pk] = ids
        return ids

    def walk(parent_id, depth, seen):
        for group in by_parent.get(parent_id, []):
            if group.pk in seen:
                continue
            seen.add(group.pk)
            people = sorted(group.members.all(), key=_label)
            nodes.append({
                "group": group,
                "depth": depth,
                "indent": depth * 1.1,
                "children": [c.pk for c in by_parent.get(group.pk, [])],
                "member_ids": [p.pk for p in people],
                "member_names": [_label(p) for p in people],
                "total": len(members_of(group)),
            })
            walk(group.pk, depth + 1, seen)

    walk(None, 0, set())
    return nodes


def parent_choices(exclude_pk=None):
    """
    Groups that can hold subgroups: those without loose members.
    ---
    Grupos que pueden tener subgrupos (los que no tienen miembros
    sueltos), con su ruta; sin el propio grupo ni sus subgrupos.
    """
    excluded = set()
    if exclude_pk:
        group = PersonGroupTemplate.objects.filter(pk=exclude_pk).first()
        if group is not None:
            excluded = group.descendant_ids()
    return [
        {"pk": g.pk, "label": g.path_label()}
        for g in sorted(
            PersonGroupTemplate.objects.filter(members__isnull=True)
            .exclude(pk__in=excluded).select_related("parent__parent"),
            key=lambda g: g.path_label().upper(),
        )
    ]


def save_group(group, name, parent_id, person_ids):
    """
    Validates and saves a group (name, parent and people).
    ---
    Valida y guarda un grupo: nombre, dónde va (parent) y sus personas.
    Reglas (S147): un grupo con subgrupos no tiene miembros sueltos; un
    grupo no se mete dentro de sí mismo ni de un subgrupo suyo; ni
    dentro de un grupo que tiene personas sueltas. Sin personas y sin
    subgrupos, el grupo queda como carpeta vacía para colgarle otros.
    """
    from document_explorer.models import PersonIdentity

    name = (name or "").strip()
    if not name:
        raise GroupError("Falta el nombre del grupo.")
    parent = None
    if parent_id:
        parent = PersonGroupTemplate.objects.filter(pk=parent_id).first()
        if parent is None:
            raise GroupError("No existe el grupo donde meterlo.")
        if group.pk and parent.pk in group.descendant_ids():
            raise GroupError(
                "Un grupo no puede ir dentro de sí mismo ni de un "
                "subgrupo suyo.")
        if parent.members.exists():
            raise GroupError(
                "«%s» tiene personas sueltas: no puede tener subgrupos."
                % parent.path_label())
    has_children = bool(group.pk) and group.children.exists()
    if has_children and person_ids:
        raise GroupError(
            "Este grupo tiene subgrupos: no puede tener personas sueltas. "
            "Guarda las personas en uno de sus subgrupos.")
    group.name = name
    group.parent = parent
    group.save()
    people = list(PersonIdentity.objects.filter(pk__in=person_ids))
    if not has_children:
        group.members.set(people)
    return group, people


def delete_group(group):
    """
    Deletes a group without subgroups.
    ---
    Borra un grupo que no tenga subgrupos (primero hay que borrar o
    sacar sus subgrupos). Nunca toca a las personas.
    """
    if group.children.exists():
        raise GroupError(
            "Tiene subgrupos: bórralos o sácalos antes de borrar el grupo.")
    group.delete()
