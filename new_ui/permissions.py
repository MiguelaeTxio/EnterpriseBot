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
# Modo «muchos usuarios a la vez» (árbol de Permisos): perfiles y
# permisos leídos una sola vez.
_BULK = {}


def start_bulk(company):
    """Load profiles and grants once (see access_rules.bulk_mode)."""
    from new_ui.models import UiUserGroup

    groups = list(UiUserGroup.objects.filter(company=company)
                  .prefetch_related("members"))
    _BULK["groups"] = groups
    _BULK["members"] = {}
    for group in groups:
        for member in group.members.all():
            _BULK["members"].setdefault(member.pk, []).append(group.pk)
    _BULK["grants"] = list(UiViewGrant.objects.filter(
        company=company).select_related("user_group"))


def stop_bulk():
    """Back to one query per user. --- Vuelve a consultar por usuario."""
    _BULK.clear()


def profile_ids(company_user):
    """
    Ids of this user's permission profiles (user groups).

    ---

    Perfiles de permisos (grupos) del usuario: aquellos en los que está;
    si no está en ninguno, los que tienen su puesto como perfil por
    defecto (S163, 26/11).
    """
    from new_ui.models import UiUserGroup

    if _BULK:
        ids = _BULK["members"].get(company_user.pk, [])
        groups = _BULK["groups"]
    else:
        ids = list(company_user.new_ui_user_groups.values_list(
            "pk", flat=True))
        groups = None
    if ids:
        return ids
    if groups is None:
        groups = UiUserGroup.objects.filter(
            company_id=company_user.company_id)
    return [group.pk for group in groups
            if company_user.role in (group.default_roles or [])]


def _grants_for(company_user, keys):
    group_ids = profile_ids(company_user)
    if _BULK:
        keys = set(keys)
        grants = [g for g in _BULK["grants"] if g.view_key in keys]
    else:
        grants = UiViewGrant.objects.filter(
            company_id=company_user.company_id, view_key__in=keys,
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
            origin = ("Perfil «%s»" % grant.user_group.name
                      if grant.user_group_id else "Puesto")
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
    from panel.access_rules import bulk_mode

    with bulk_mode(company):
        return _permission_tree(company)


def _permission_tree(company):
    """The work of permission_tree. --- El cálculo del árbol."""
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
        from panel.access_rules import ENFORCE

        roles.append({
            "enforce": ENFORCE,
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
    from panel.access_rules import panel_area_list

    role_labels = dict(CompanyUser.ROLE_CHOICES)
    area_labels = dict(panel_area_list())
    groups = []
    explicit = {}
    all_groups = list(UiUserGroup.objects.filter(
        company=company).prefetch_related("members__user"))
    for group in all_groups:
        for member in group.members.all():
            explicit.setdefault(member.pk, []).append(group.pk)
    for group in all_groups:
        group_grants = [g for g in grants if g.user_group_id == group.pk]
        group_views = views_of(group_grants)
        panel_grants = sorted(
            ({"label": ("Todo el panel" if g.view_key == PANEL_KEY else
                        area_labels.get(g.view_key.split(".", 1)[1],
                                        g.view_key)),
              "level": g.level, "rank": RANK[g.level]}
             for g in group_grants
             if section_key(g.view_key) == PANEL_KEY),
            key=lambda a: a["label"])
        defaults = group.default_roles or []
        people = []
        for cu in users:
            if cu.pk in explicit:
                if group.pk not in explicit[cu.pk]:
                    continue
                how = "Puesto a mano"
            elif cu.role in defaults:
                how = "Por su puesto"
            else:
                continue
            change = legacy["user_change"].get(cu.pk, {})
            people.append({
                "pk": cu.pk,
                "name": cu.user.get_full_name() or cu.user.username,
                "username": cu.user.username,
                "role": role_labels.get(cu.role, cu.role),
                "active": cu.is_active,
                "superuser": cu.user.is_superuser,
                "how": "metido a mano" if how == "Puesto a mano" else
                       "por su puesto",
                "gains": change.get("gains", []),
                "losses": change.get("losses", []),
                "preview_count": change.get("count", 0),
            })
        groups.append({
            "pk": group.pk, "name": group.name, "views": group_views,
            "access": sum(s["open"] for s in group_views),
            "panel_grants": panel_grants,
            "default_roles": [role_labels.get(r, r) for r in defaults],
            "people": people,
            "members": [m.user.get_full_name() or m.user.username
                        for m in group.members.all()],
        })
    no_profile = [
        {"pk": cu.pk, "name": cu.user.get_full_name() or cu.user.username,
         "role": role_labels.get(cu.role, cu.role)}
        for cu in users if cu.is_active and not cu.user.is_superuser
        and cu.pk not in explicit and not any(
            cu.role in (g.default_roles or []) for g in all_groups)]
    return {"roles": roles, "groups": groups, "no_profile": no_profile}


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

    key = "nui_legacy_panel_v2_%s" % company.pk
    cached = cache.get(key)
    if cached is not None:
        return cached
    from panel.access_rules import bulk_mode

    with bulk_mode(company):
        result = _legacy_panel(company, users)
    cache.set(key, result, 120)
    return result


def _legacy_panel(company, users):
    """The work of legacy_panel. --- El cálculo de legacy_panel."""
    from ivr_config.models import CompanyUser
    from panel.access_rules import panel_areas, role_stand_in

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
    user_change = {}
    for cu in users:
        if not cu.is_active:
            continue
        today = {a["label"] for a in panel_areas(cu).values()
                 if a["allowed"]}
        after = {a["label"] for a in panel_areas(cu, preview=True).values()
                 if a["allowed"]}
        user_change[cu.pk] = {"gains": sorted(after - today),
                              "losses": sorted(today - after),
                              "count": len(after)}
    result = {
        "user_change": user_change,
        "preview": preview,
        "roles": {code: ordered(areas) for code, areas in roles.items()},
        "user_diffs": user_diffs,
        "user_count": user_count,
    }
    return result
