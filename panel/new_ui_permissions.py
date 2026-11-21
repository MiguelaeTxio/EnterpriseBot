# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/new_ui_permissions.py
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
from panel.models import PanelViewGrant
from panel.new_ui_catalog import PERMISSIONS, section_key

RANK = {
    PanelViewGrant.LEVEL_NONE: 0,
    PanelViewGrant.LEVEL_VIEW: 1,
    PanelViewGrant.LEVEL_EDIT: 2,
}
LABELS = dict(PanelViewGrant.LEVEL_CHOICES)


def _grants_for(company_user, keys):
    group_ids = list(company_user.panel_user_groups.values_list(
        "pk", flat=True))
    grants = PanelViewGrant.objects.filter(
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
        return {key: (PanelViewGrant.LEVEL_EDIT, "Superusuario")
                for key in keys}
    sections = {section_key(key) for key in keys}
    grants = _grants_for(company_user, set(keys) | sections)
    result = {}
    for key in keys:
        if section_key(key) == PERMISSIONS:
            result[key] = (PanelViewGrant.LEVEL_NONE, "Solo superusuario")
            continue
        level, origin = _resolve(grants, company_user, key)
        if level is None and key != section_key(key):
            level, origin = _resolve(grants, company_user, section_key(key))
            if level is not None:
                origin = "%s (heredado de la sección)" % origin
        if level is None:
            level, origin = PanelViewGrant.LEVEL_NONE, "Sin permiso"
        result[key] = (level, origin)
    return result


def can_view(company_user, key):
    """
    True if the user can at least see the view.

    ---

    True si el usuario puede al menos ver la vista.
    """
    level, _origin = effective_levels(company_user, [key])[key]
    return RANK[level] >= RANK[PanelViewGrant.LEVEL_VIEW]


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
    existing = PanelViewGrant.objects.filter(**filters)
    if not level:
        existing.delete()
        return None
    grant = existing.first()
    if grant is None:
        grant = PanelViewGrant(**filters)
    grant.level = level
    grant.updated_by = updated_by
    grant.save()
    existing.exclude(pk=grant.pk).delete()
    return grant
