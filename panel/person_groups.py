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

S147 (Miguel Ángel): "Los grupos [...] son globales a todas las vistas.
También pueden ser usados, pero nunca modificados, por otros usuarios":
solo quien creó un grupo lo cambia o lo borra, y solo dentro de un
grupo suyo se cuelgan subgrupos. Los demás lo usan (Personal, Avisos y
el recuadro "Grupos de selección" de Fichajes, Vacaciones,
Solicitudes, Horarios, Usuarios y Partes digitales, que selecciona a
sus personas como en Personal).
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


def can_edit(group, editor):
    """
    True when `editor` (CompanyUser) created the group (S147).
    ---
    True si `editor` creó el grupo: solo él lo cambia o lo borra.
    """
    return editor is not None and group.created_by_id == editor.pk


def owner_label(group):
    """
    Name of who created the group ("" if nobody).
    ---
    Nombre de quien creó el grupo.
    """
    user = group.created_by.user if group.created_by_id else None
    if user is None:
        return ""
    return user.get_full_name() or user.username


def group_tree(editor=None):
    """
    Flat list of the groups in tree order, with depth and members.
    ---
    Lista plana en orden de árbol (padre y debajo sus subgrupos, por
    nombre). Cada nodo: group, depth, children (pks de los hijos
    directos), member_ids y member_names (los suyos; vacío si tiene
    subgrupos), total (personas distintas, contando sus subgrupos),
    can_edit (si `editor` lo creó) y owner (quién lo creó).
    """
    groups = list(PersonGroupTemplate.objects.select_related(
        "created_by__user").prefetch_related("members").order_by("name"))
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
                "member_user_ids": [p.company_user_id or "" for p in people],
                "total": len(members_of(group)),
                "can_edit": can_edit(group, editor),
                "owner": owner_label(group),
            })
            walk(group.pk, depth + 1, seen)

    walk(None, 0, set())
    return nodes


def parent_choices(exclude_pk=None, editor=None):
    """
    Groups that can hold subgroups: those without loose members.
    ---
    Grupos que pueden tener subgrupos (los que no tienen miembros
    sueltos), con su ruta; sin el propio grupo ni sus subgrupos. Con
    `editor`, solo los suyos (en uno ajeno no se cuelgan subgrupos).
    """
    excluded = set()
    if exclude_pk:
        group = PersonGroupTemplate.objects.filter(pk=exclude_pk).first()
        if group is not None:
            excluded = group.descendant_ids()
    groups = PersonGroupTemplate.objects.filter(members__isnull=True)
    if editor is not None:
        groups = groups.filter(created_by=editor)
    return [
        {"pk": g.pk, "label": g.path_label()}
        for g in sorted(
            groups.exclude(pk__in=excluded).select_related("parent__parent"),
            key=lambda g: g.path_label().upper(),
        )
    ]


def save_group(group, name, parent_id, person_ids, editor=None):
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

    if group.pk and not can_edit(group, editor):
        raise GroupError(_not_yours(group))
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
        if not can_edit(parent, editor):
            raise GroupError(
                "«%s» es de %s: solo puedes meterlo dentro de un grupo "
                "tuyo." % (parent.path_label(),
                           owner_label(parent) or "otro usuario"))
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


def _not_yours(group):
    return ("«%s» es de %s: puedes usarlo, pero solo quien lo creó lo "
            "cambia o lo borra." % (group.path_label(),
                                    owner_label(group) or "otro usuario"))


def delete_group(group, editor=None):
    """
    Deletes a group without subgroups.
    ---
    Borra un grupo que no tenga subgrupos (primero hay que borrar o
    sacar sus subgrupos). Nunca toca a las personas.
    """
    if not can_edit(group, editor):
        raise GroupError(_not_yours(group))
    if group.children.exists():
        raise GroupError(
            "Tiene subgrupos: bórralos o sácalos antes de borrar el grupo.")
    group.delete()


def group_filter_context(request):
    """
    Context of the "Grupos de selección" box (_person_group_filter.html).
    ---
    Contexto del recuadro "Grupos de selección" de las vistas de
    personal: el árbol (con quién lo creó) y lo plegado por el usuario.
    """
    from panel.navigation_persistence import get_saved_state_key

    editor = request.user.company_user
    collapsed = get_saved_state_key(editor, "person_groups", "collapsed", [])
    return {
        "person_group_nodes": group_tree(editor),
        "person_groups_collapsed": (
            [str(pk) for pk in collapsed] if isinstance(collapsed, list)
            else []
        ),
    }
