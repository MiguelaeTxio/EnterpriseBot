# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/permissions.py
"""
Effective permission of a user on a view of the new interface.

---

Permiso efectivo de un usuario sobre una vista de la nueva interfaz
(S163). Reglas:

1. El superusuario (Miguel Ángel) lo ve y lo modifica todo, y es el
   único que entra en Permisos.
2. Un permiso puesto al propio usuario manda sobre todo lo demás (así
   se puede quitar a una persona algo que le da su rol o su grupo).
3. Si no, el mayor entre los de sus grupos de usuarios y el de su rol.
4. Un listado sin permisos propios hereda los de su sección
   (`cdg.documentos` hereda de `cdg`).
5. Sin ningún permiso: sin acceso.
"""
from new_ui.models import UiViewGrant
from new_ui.catalog import PERMISSIONS, section_key

RANK = {
    UiViewGrant.LEVEL_NONE: 0,
    UiViewGrant.LEVEL_VIEW: 1,
    UiViewGrant.LEVEL_EDIT: 2,
}
LABELS = dict(UiViewGrant.LEVEL_CHOICES)


def _grants_for(company_user, keys):
    group_ids = list(company_user.new_ui_user_groups.values_list(
        "pk", flat=True))
    grants = UiViewGrant.objects.filter(
        company=company_user.company, view_key__in=keys,
    ).select_related("user_group")
    out = []
    for grant in grants:
        if grant.company_user_id == company_user.pk:
            out.append(grant)
        elif grant.user_group_id in group_ids:
            out.append(grant)
        elif (grant.role and grant.role == company_user.role
              and not grant.company_user_id and not grant.user_group_id):
            out.append(grant)
    return out


def _resolve(grants, company_user, key):
    """(level, origin text) from the grants of exactly one key."""
    own = [g for g in grants
           if g.view_key == key and g.company_user_id == company_user.pk]
    if own:
        return own[0].level, "Usuario"
    best, origin = None, ""
    for grant in grants:
        if grant.view_key != key or grant.company_user_id:
            continue
        if best is None or RANK[grant.level] > RANK[best]:
            best = grant.level
            origin = ("Grupo «%s»" % grant.user_group.name
                      if grant.user_group_id else "Rol")
    return best, origin


def effective_levels(company_user, keys):
    """
    {key: (level, origin)} for several keys, with section inheritance.

    ---

    Nivel efectivo y de dónde sale ("Usuario", "Grupo «X»", "Rol",
    "Heredado de la sección", "Superusuario" o "Sin permiso") para cada
    clave, con una sola consulta.
    """
    if company_user.user.is_superuser:
        return {key: (UiViewGrant.LEVEL_EDIT, "Superusuario")
                for key in keys}
    sections = {section_key(key) for key in keys}
    grants = _grants_for(company_user, set(keys) | sections)
    result = {}
    for key in keys:
        if section_key(key) == PERMISSIONS:
            result[key] = (UiViewGrant.LEVEL_NONE, "Solo superusuario")
            continue
        level, origin = _resolve(grants, company_user, key)
        if level is None and key != section_key(key):
            level, origin = _resolve(grants, company_user, section_key(key))
            if level is not None:
                origin = "%s (heredado de la sección)" % origin
        if level is None:
            level, origin = UiViewGrant.LEVEL_NONE, "Sin permiso"
        result[key] = (level, origin)
    return result


def can_view(company_user, key):
    """
    True if the user can at least see the view.

    ---

    True si el usuario puede al menos ver la vista.
    """
    level, _origin = effective_levels(company_user, [key])[key]
    return RANK[level] >= RANK[UiViewGrant.LEVEL_VIEW]


def set_grant(company, view_key, level, updated_by, role="",
              user_group=None, company_user=None):
    """
    Create, change or remove (level "") one subject's grant on a view.

    ---

    Crea, cambia o quita (nivel vacío = "heredado") el permiso de un
    sujeto (rol, grupo o usuario: uno solo) sobre una vista.
    """
    filters = {
        "company": company, "view_key": view_key,
        "role": role if not (user_group or company_user) else "",
        "user_group": user_group, "company_user": company_user,
    }
    existing = UiViewGrant.objects.filter(**filters)
    if not level:
        existing.delete()
        return None
    grant = existing.first()
    if grant is None:
        grant = UiViewGrant(**filters)
    grant.level = level
    grant.updated_by = updated_by
    grant.save()
    existing.exclude(pk=grant.pk).delete()
    return grant


def subject_levels(grants, key, section):
    """Nivel propio de un sujeto (sus grants) en una vista, con herencia."""
    own = {g.view_key: g.level for g in grants}
    if key in own:
        return own[key], False
    if key != section and section in own:
        return own[section], True
    return UiViewGrant.LEVEL_NONE, False


def permission_tree(company):
    """
    The permissions tree: roles (their views and their users) and user
    groups, with the effective level of every view.

    ---

    S163 (26/11, Miguel Ángel: «una gráfica en árbol de los permisos de
    cada operario y rol»): por cada rol, sus vistas (sección › listado)
    con su nivel, y sus usuarios con lo que les queda de verdad; lo que
    no coincide con el rol lleva su origen. Después, los grupos.
    """
    from ivr_config.models import CompanyUser
    from new_ui.catalog import all_view_keys
    from new_ui.models import UiUserGroup

    from new_ui.catalog import PANEL_KEY

    keys = [(k, label, depth) for k, label, depth in all_view_keys()
            if section_key(k) != PANEL_KEY]
    plain = [k for k, _l, _d in keys]
    grants = list(UiViewGrant.objects.filter(company=company))

    def views_of(subject_grants):
        sections, current = [], None
        for key, label, depth in keys:
            level, inherited = subject_levels(subject_grants, key,
                                              section_key(key))
            node = {"key": key, "label": label, "level": level,
                    "rank": RANK[level], "level_label": LABELS[level],
                    "inherited": inherited}
            if depth == 0:
                current = dict(node, views=[])
                sections.append(current)
            elif current is not None:
                current["views"].append(node)
        for section in sections:
            section["open"] = sum(1 for v in section["views"] if v["rank"])
        return sections

    users = list(CompanyUser.objects.filter(company=company).select_related(
        "user").order_by("user__first_name", "user__last_name",
                         "user__username"))
    legacy = legacy_panel(company, users)
    roles = []
    for code, label in CompanyUser.ROLE_CHOICES:
        role_grants = [g for g in grants if g.role == code
                       and not g.user_group_id and not g.company_user_id]
        role_views = views_of(role_grants)
        role_rank = {v["key"]: v["rank"] for s in role_views
                     for v in [s] + s["views"]}
        members = []
        for cu in users:
            if cu.role != code:
                continue
            effective = effective_levels(cu, plain)
            diffs = []
            for key, view_label, depth in keys:
                level, origin = effective[key]
                if RANK[level] != role_rank.get(key, 0):
                    diffs.append({
                        "label": ("%s (toda la sección)" % view_label
                                  if depth == 0 else view_label),
                        "level_label": LABELS[level], "rank": RANK[level],
                        "origin": origin})
            members.append({
                "panel_diffs": legacy["user_diffs"].get(cu.pk, []),
                "panel_access": legacy["user_count"].get(cu.pk, 0),
                "pk": cu.pk,
                "name": cu.user.get_full_name() or cu.user.username,
                "username": cu.user.username,
                "active": cu.is_active,
                "superuser": cu.user.is_superuser,
                "access": sum(1 for k in plain
                              if RANK[effective[k][0]] and "." in k),
                "diffs": diffs,
            })
        from panel import access_profiles
        from panel.access_rules import ENFORCE

        moving_in = [
            name for (pk, name), new_role in
            access_profiles.ROLE_CHANGES.items()
            if new_role == code and not any(
                m.pk == pk and m.role == code for m in users)]
        moving_out = [
            name for (pk, name), new_role in
            access_profiles.ROLE_CHANGES.items()
            if new_role != code and any(
                m.pk == pk and m.role == code for m in users)]
        roles.append({
            "enforce": ENFORCE,
            "moving_in": moving_in,
            "moving_out": moving_out,
            "preview": legacy["preview"][code],
            "preview_access": sum(1 for a in legacy["preview"][code]
                                  if a["allowed"]),
            "preview_mismatch": [a["label"] for a in legacy["preview"][code]
                                 if a["menu_mismatch"]],
            "panel": legacy["roles"][code],
            "panel_access": sum(1 for a in legacy["roles"][code]
                                if a["allowed"]),
            "code": code, "label": label, "views": role_views,
            "access": sum(s["open"] for s in role_views),
            "members": members,
        })
    groups = []
    for group in UiUserGroup.objects.filter(company=company).prefetch_related(
            "members__user"):
        group_grants = [g for g in grants if g.user_group_id == group.pk]
        group_views = views_of(group_grants)
        groups.append({
            "pk": group.pk, "name": group.name, "views": group_views,
            "access": sum(s["open"] for s in group_views),
            "members": [m.user.get_full_name() or m.user.username
                        for m in group.members.all()],
        })
    return {"roles": roles, "groups": groups}


def legacy_panel(company, users):
    """
    What each role and each user can enter in the current panel.

    ---

    S163 (26/11): lo que deja entrar el panel actual a cada rol (por sí
    mismo) y a cada usuario (con sus accesos propios: firmas, seguros,
    nóminas compartidas, carpetas del Explorador...), por área, leído
    de las reglas del propio panel (panel/access_rules.py). Se guarda
    dos minutos en caché: pinta el menú y pregunta a cada regla por
    cada usuario.
    """
    from django.core.cache import cache

    from ivr_config.models import CompanyUser
    from panel.access_rules import panel_areas, role_stand_in

    key = "nui_legacy_panel_%s" % company.pk
    cached = cache.get(key)
    if cached is not None:
        return cached

    def ordered(areas):
        return sorted(areas.values(), key=lambda a: a["label"])

    roles = {code: panel_areas(role_stand_in(company, code))
             for code, _label in CompanyUser.ROLE_CHOICES}
    preview = {code: ordered(panel_areas(role_stand_in(company, code),
                                         preview=True))
               for code, _label in CompanyUser.ROLE_CHOICES}
    user_diffs, user_count = {}, {}
    for cu in users:
        mine = panel_areas(cu)
        base = roles.get(cu.role, {})
        user_count[cu.pk] = sum(1 for a in mine.values() if a["allowed"])
        diffs = []
        for area in ordered(mine):
            other = base.get(area["key"])
            if other and (other["allowed"], other["in_menu"]) == (
                    area["allowed"], area["in_menu"]):
                continue
            diffs.append(dict(area, role_allowed=(
                other["allowed"] if other else 0)))
        user_diffs[cu.pk] = diffs
    result = {
        "preview": preview,
        "roles": {code: ordered(areas) for code, areas in roles.items()},
        "user_diffs": user_diffs,
        "user_count": user_count,
    }
    cache.set(key, result, 120)
    return result
