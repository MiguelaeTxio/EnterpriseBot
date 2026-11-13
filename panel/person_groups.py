# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/person_groups.py
"""
Selection groups of the Personal tab as a tree (S147).

---

Grupos de selección de la pestaña Personal en árbol (S147, Miguel
Ángel): "grupos y subfamilias de grupos [...] desplegar Plataformas y
tener Administración, Comercial, Taller, Transportistas" y "puedes
seleccionar varios grupos hijos, como con casillero". Un grupo puede
tener sus personas y subgrupos dentro ("Mecánicos" dentro de
"Taller"); con otro nombre, guardar crea un grupo nuevo (el marcado no
se toca). Aquí se arma el árbol que pinta
_personal_pane.html y se validan los cambios que guarda
PersonGroupTemplateSaveView.

S147 (Miguel Ángel): "Los grupos [...] son globales a todas las vistas.
También pueden ser usados, pero nunca modificados, por otros usuarios":
solo quien creó un grupo lo cambia o lo borra, y solo dentro de un
grupo suyo se cuelgan subgrupos. Los demás lo usan (Personal, Avisos y
el recuadro "Grupos de selección" de Fichajes, Vacaciones,
Solicitudes, Horarios, Usuarios y Partes digitales, que selecciona a
sus personas como en Personal).

H31 (S148): los grupos de máquinas de Centros de Gasto
(fleet.MachineGroupTemplate) usan estas mismas funciones con
`kind=MACHINE_KIND`; sin `kind`, todo sigue siendo de personas.
"""
from collections import namedtuple


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


def _machine_label(machine):
    return " ".join(part for part in (machine.code, machine.plate,
                                      machine.brand_model) if part)


# H31 (S148): los grupos de máquinas (fleet.MachineGroupTemplate) siguen
# exactamente las mismas reglas que los de personas; lo que cambia es
# el modelo, cómo se nombra a cada uno y dónde se recuerda el plegado.
GroupKind = namedtuple("GroupKind", [
    "model_path", "member_path", "label", "user_id", "collapsed_key",
    "one", "many",
])
PERSON_KIND = GroupKind(
    "document_explorer.PersonGroupTemplate",
    "document_explorer.PersonIdentity", _label,
    lambda person: person.company_user_id or "", "person_groups",
    "Una persona", "Quítalas",
)
MACHINE_KIND = GroupKind(
    "fleet.MachineGroupTemplate", "fleet.MachineAsset", _machine_label,
    lambda machine: "", "machine_groups",
    "Una máquina", "Quítalas",
)


def _model(path):
    from django.apps import apps

    return apps.get_model(path)


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


# S147 (Miguel Ángel): los grupos que crea él son los "Generales".
GENERAL_USERNAME = "alvarez_admin"
# Plegados la primera vez (luego manda lo que pliegue cada uno).
FOLDERS_COLLAPSED_BY_DEFAULT = ("f-usr",)
FOLDERS_INIT_MARK = "f-init"


def _is_general(group):
    user = group.created_by.user if group.created_by_id else None
    return user is None or user.username == GENERAL_USERNAME


def can_delete(group, editor):
    """
    True when `editor` may delete the group (S148).
    ---
    True si `editor` puede borrar el grupo: quien lo creó y, además, los
    administradores (rol ADMIN) cualquiera que no sea de los Generales
    (Miguel Ángel, S148: "los administradores sí puedan borrar cualquier
    grupo, excepto los grupos generales").
    """
    if can_edit(group, editor):
        return True
    from ivr_config.models import CompanyUser

    return (editor is not None and editor.role == CompanyUser.ROLE_ADMIN
            and not _is_general(group))


def group_tree(editor=None, kind=PERSON_KIND):
    """
    Flat list of the groups in tree order, under the creator folders.
    ---
    Lista plana en orden de árbol, repartida en carpetas por quién creó
    cada grupo (S147, Miguel Ángel): "Generales" (los de alvarez_admin),
    "Usuarios" (los de los demás, una carpeta por usuario) y "Propios"
    (los de quien mira; alvarez_admin no la tiene: los suyos son los
    Generales). Las carpetas sin grupos no salen.
    Nodo de carpeta: kind "folder", key, label, depth, indent, folder
    (la carpeta de encima) y count (grupos principales dentro).
    Nodo de grupo: kind "group", group, depth, indent, folder (su
    carpeta), children (pks de los hijos directos), member_ids y
    member_names (los suyos), total (personas distintas, contando sus
    subgrupos), can_edit (si `editor` lo creó) y owner (quién lo creó).
    """
    groups = list(_model(kind.model_path).objects.select_related(
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

    def walk(siblings, depth, folder, seen):
        for group in siblings:
            if group.pk in seen:
                continue
            seen.add(group.pk)
            people = sorted(group.members.all(), key=kind.label)
            nodes.append({
                "kind": "group",
                "group": group,
                "depth": depth,
                "indent": depth * 1.1,
                "folder": folder,
                "children": [c.pk for c in by_parent.get(group.pk, [])],
                "member_ids": [p.pk for p in people],
                "member_names": [kind.label(p) for p in people],
                "member_user_ids": [kind.user_id(p) for p in people],
                "total": len(members_of(group)),
                "can_edit": can_edit(group, editor),
                "can_delete": can_delete(group, editor),
                "owner": owner_label(group),
            })
            walk(by_parent.get(group.pk, []), depth + 1, folder, seen)

    def folder_node(key, label, depth, parent, count):
        nodes.append({
            "kind": "folder", "key": key, "label": label, "depth": depth,
            "indent": depth * 1.1, "folder": parent, "count": count,
        })

    general, own, others = [], [], {}
    for group in by_parent.get(None, []):
        if _is_general(group):
            general.append(group)
        elif editor is not None and group.created_by_id == editor.pk:
            own.append(group)
        else:
            others.setdefault(group.created_by_id, []).append(group)
    seen = set()
    if general:
        folder_node("f-gen", "Generales", 0, "", len(general))
        walk(general, 1, "f-gen", seen)
    if others:
        folder_node("f-usr", "Usuarios", 0, "",
                    sum(len(v) for v in others.values()))
        for roots in sorted(others.values(),
                            key=lambda g: owner_label(g[0]).upper()):
            key = "f-u%s" % roots[0].created_by_id
            folder_node(key, owner_label(roots[0]) or "Sin usuario", 1,
                        "f-usr", len(roots))
            walk(roots, 2, key, seen)
    if own:
        folder_node("f-own", "Propios", 0, "", len(own))
        walk(own, 1, "f-own", seen)
    return nodes


def collapsed_state(editor, kind=PERSON_KIND):
    """
    Folded tree rows of `editor` ("person_groups" screen state).
    ---
    Lo que `editor` tiene plegado en el árbol; la primera vez, la
    carpeta "Usuarios" plegada (los Generales y los Propios abiertos).
    """
    from panel.navigation_persistence import get_saved_state_key

    collapsed = get_saved_state_key(
        editor, kind.collapsed_key, "collapsed", [])
    collapsed = ([str(pk) for pk in collapsed]
                 if isinstance(collapsed, list) else [])
    if FOLDERS_INIT_MARK not in collapsed:
        collapsed += list(FOLDERS_COLLAPSED_BY_DEFAULT) + [FOLDERS_INIT_MARK]
    return collapsed


def parent_choices(exclude_pk=None, editor=None, kind=PERSON_KIND):
    """
    Groups that can hold subgroups: those without loose members.
    ---
    Grupos donde se puede meter otro, con su ruta; sin el propio grupo
    ni sus subgrupos. S147 (Miguel Ángel, "creo Mecánicos dentro de
    Taller"): cualquiera, tenga personas o no. Con `editor`, solo los
    suyos (en uno ajeno no se cuelgan subgrupos).
    """
    model = _model(kind.model_path)
    excluded = set()
    if exclude_pk:
        group = model.objects.filter(pk=exclude_pk).first()
        if group is not None:
            excluded = group.descendant_ids()
    groups = model.objects.all()
    if editor is not None:
        groups = groups.filter(created_by=editor)
    return [
        {"pk": g.pk, "label": g.path_label(), "name": g.name,
         "parent": g.parent_id or ""}
        for g in sorted(
            groups.exclude(pk__in=excluded).select_related("parent__parent"),
            key=lambda g: g.path_label().upper(),
        )
    ]


def save_group(group, name, parent_id, person_ids, editor=None,
               kind=PERSON_KIND):
    """
    Validates and saves a group (name, parent and people).
    ---
    Valida y guarda un grupo: nombre, dónde va (parent) y sus personas.
    Reglas (S147): un grupo no se mete dentro de sí mismo ni de un
    subgrupo suyo, y solo dentro de un grupo de quien lo guarda. Un
    grupo puede tener sus personas y además subgrupos (p. ej. Taller con
    los suyos y, dentro, Mecánicos y Limpiadores, que son parte de
    ellos): marcarlo selecciona las suyas y las de sus subgrupos. Quien
    entra en un subgrupo entra también en todos los grupos de encima.
    Sin personas, queda como carpeta para colgarle otros.
    """
    if group.pk and not can_edit(group, editor):
        raise GroupError(_not_yours(group))
    name = (name or "").strip()
    if not name:
        raise GroupError("Falta el nombre del grupo.")
    parent = None
    if parent_id:
        parent = _model(kind.model_path).objects.filter(
            pk=parent_id).first()
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
    people = list(_model(kind.member_path).objects.filter(
        pk__in=person_ids))
    # S147 (Miguel Ángel): "si un grupo tiene x subgrupos con y elementos,
    # x tiene que ser igual a la sumatoria": una persona solo está en un
    # subgrupo de cada grupo (los grupos principales sí mezclan).
    if parent is not None and people:
        siblings = parent.children.exclude(pk=group.pk) if group.pk \
            else parent.children.all()
        wanted = {p.pk for p in people}
        clashes = []
        for sibling in siblings.prefetch_related("members"):
            inside = [p for p in sibling.members.all() if p.pk in wanted]
            if inside:
                clashes.append("%s (ya en «%s»)" % (
                    "; ".join(sorted(kind.label(p) for p in inside)),
                    sibling.name))
        if clashes:
            raise GroupError(
                "%s solo puede estar en un subgrupo de «%s»: %s. "
                "%s de la selección o de ese subgrupo."
                % (kind.one, parent.path_label(), " · ".join(clashes),
                   kind.many))
    group.name = name
    group.parent = parent
    group.save()
    group.members.set(people)
    # S147 (Miguel Ángel): "si una persona entra nueva y lo asignamos a
    # un subgrupo, automáticamente se asigna al grupo padre" -- y a
    # todos los de encima (Mecánicos -> Taller -> ...).
    ancestor = parent
    seen = {group.pk}
    while ancestor is not None and ancestor.pk not in seen:
        seen.add(ancestor.pk)
        ancestor.members.add(*people)
        ancestor = ancestor.parent
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
    sacar sus subgrupos). Nunca toca a las personas. S148: quien lo
    creó o un administrador si no es de los Generales (can_delete).
    """
    if not can_delete(group, editor):
        from ivr_config.models import CompanyUser

        if editor is not None and editor.role == CompanyUser.ROLE_ADMIN:
            raise GroupError("«%s» es de los Generales: solo lo borra "
                             "quien lo creó." % group.path_label())
        raise GroupError(_not_yours(group))
    if group.children.exists():
        raise GroupError(
            "Tiene subgrupos: bórralos o sácalos antes de borrar el grupo.")
    group.delete()


def group_filter_context(request, kind=PERSON_KIND):
    """
    Context of the "Grupos de selección" box (_person_group_filter.html).
    ---
    Contexto del recuadro "Grupos de selección" de las vistas de
    personal: el árbol (con quién lo creó) y lo plegado por el usuario.
    """
    editor = request.user.company_user
    return {
        "person_group_nodes": group_tree(editor, kind),
        "person_groups_collapsed": collapsed_state(editor, kind),
        # S153: el recuadro es el de Personal ("Dentro de" por niveles).
        "person_group_parents": parent_choices(editor=editor, kind=kind),
    }


# S153 (Miguel Ángel: "Queremos filtrar por grupos en todas las
# pestañas"): el filtro "Grupo" de "Buscar y filtrar", el mismo en todas
# las pestañas (de personas y de máquinas). Plantilla:
# panel/_group_filter_select.html.
GROUP_FILTER_NONE = "none"


def group_filter_options(editor=None, kind=PERSON_KIND):
    """
    Options of the "Grupo" filter, in tree order.
    ---
    Opciones del filtro "Grupo" en el orden del árbol (las carpetas
    Generales / Usuarios / Propios, como rótulos no elegibles):
    (valor, rótulo, elegible).
    """
    options = []
    for node in group_tree(editor, kind):
        pad = "   " * node["depth"]
        if node["kind"] == "folder":
            options.append(("", pad + node["label"], False))
        else:
            options.append((str(node["group"].pk), "%s%s (%d)" % (
                pad, node["group"].name, node["total"]), True))
    return options


def filter_by_group(queryset, value, kind=PERSON_KIND):
    """
    Filters people or machines by a selection group.
    ---
    Deja las personas o máquinas del grupo elegido y de todos sus
    subgrupos; GROUP_FILTER_NONE, las que no están en ningún grupo;
    vacío, todas.
    """
    if value == GROUP_FILTER_NONE:
        return queryset.filter(group_templates__isnull=True)
    if not str(value).isdigit():
        return queryset
    children = {}
    for pk, parent_id in _model(kind.model_path).objects.values_list(
            "pk", "parent_id"):
        children.setdefault(parent_id, []).append(pk)
    wanted, pending = set(), [int(value)]
    while pending:
        current = pending.pop()
        if current in wanted:
            continue
        wanted.add(current)
        pending.extend(children.get(current, []))
    members = _model(kind.member_path).objects.filter(
        group_templates__in=wanted).values("pk")
    return queryset.filter(pk__in=members)


def group_filter_select_context(request, kind=PERSON_KIND):
    """
    Context of the shared "Grupo" filter select.
    ---
    Contexto del desplegable "Grupo" común (_group_filter_select.html).
    """
    return {
        "group_filter": request.GET.get("group", ""),
        "group_filter_none": GROUP_FILTER_NONE,
        "group_filter_options": group_filter_options(
            request.user.company_user, kind),
    }
