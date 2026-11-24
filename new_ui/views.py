# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views.py
"""
New interface (S163): one Documentation view with five panels.

---

Nueva interfaz (S163, sesión invasora de UX). Miguel Ángel: "Para no
cortar producción. Creamos una entrada en la sidebar a la cuál solo
tengo acceso yo, llamada nueva interfaz. A documentos, personal, y
centros de gasto, añades una que se llame permisos, solo visible para
mí [...] con los usuarios y grupos de usuarios y los permisos para las
diferentes vistas, para poder configurar desde esa vista."

- `NewUiView`: la vista única. Selector de qué se gestiona
  (Documentos, Personal, Centros de gasto, Permisos) y los cinco
  paneles comunes (directriz 4.27, punto 4bis): arriba filtros,
  grupos de selección y acciones; abajo el listado de filtrados y el
  de seleccionados. Tamaños, pestañas, sección y selección se guardan
  por usuario (PanelNavigationState, pantalla "nui").
- Permisos: listado de usuarios, grupos de usuarios y vistas; editor
  de permisos por usuario, grupo o rol; acciones en bloque sobre los
  seleccionados.
De momento todo es solo para el superusuario (SuperuserRequiredMixin);
Documentos, Personal y Centros de gasto se van llenando por fases.
"""
import re

from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import DocumentTypeCatalog
from ivr_config.models import Company, CompanyUser
from new_ui.views_dossiers import dossier_context
from new_ui.views_schedules import schedules_context
from new_ui.views_doc_actions import doc_types_context
from new_ui.views_requirements import requirements_context
from new_ui.views_notify import notify_context
from new_ui.views_personnel import personnel_context
from new_ui.views_access import access_context
from new_ui.views_medical import absences_context, medical_context
from new_ui.views_payslips_nui import payslips_context
from new_ui.views_safety import safety_context
from new_ui.views_pay import pay_context
from new_ui.views_partes import partes_context
from new_ui.views_signatures_nui import signatures_context
from new_ui.views_epis import epis_context
from new_ui.views_accessories import accessories_context
from new_ui.views_vacations import vacations_context
from new_ui.views_logbook import logbook_context
from new_ui.views_machines import machines_context
from new_ui.mixins import SuperuserRequiredMixin
from new_ui.models import UiUserGroup, UiViewGrant
from new_ui.state import apply_list_navigation
from new_ui.state import get_key as get_saved_state_key
from new_ui.state import save_keys as _save_keys
from new_ui.catalog import (
    ENTITY_TABS, FICHA, PERMISSIONS, SECTIONS, TAB_NOUNS, all_view_keys,
    label_of, view_groups, view_mode,
)
from new_ui.filters import (
    period_context, period_range, sort_headers, sort_rows,
)
from new_ui.permissions import (
    LABELS, RANK, effective_levels, set_grant,
)

SCREEN_KEY = "nui"
# Filtros de Permisos, guardados por usuario (4.15).
PERM_SCREEN_KEY = "nui_permisos"
PERM_FILTER_KEYS = ("q", "periodo", "cual", "desde", "hasta", "estado",
                    "empresa", "grupo", "seccion", "sort")
DEFAULT_SECTION = "cdg"
# Fases (ver anexo V31, COMPLETADAS EN S163): lo que aún no está hecho
# en cada sección.
PENDING = {
    "doc": "Fase 5: Circulares, Dosieres, Avisos, Pedir documentos, "
           "Firmas, Seguros, Bandeja de entrada y Calendario.",
    "per": "Fase 3: Personal, con la tarjeta del trabajador en el panel "
           "de seleccionados.",
    "cdg": "Fase 2: Centros de gasto, con la tarjeta técnica en el panel "
           "de seleccionados.",
}
USER_COLUMNS = (
    ("usuario", "Usuario", "username"),
    ("nombre", "Nombre", "name"),
    ("rol", "Rol", "role"),
    ("grupos", "Grupos de usuarios", ""),
    ("estado", "Estado", "active"),
    ("acceso", "Último acceso", "last_login"),
    ("vistas", "Vistas con acceso", "views"),
)
USER_SORT = {
    "username": lambda u: u.user.username.lower(),
    "name": lambda u: (u.user.get_full_name() or "").lower(),
    "role": lambda u: u.get_role_display(),
    "active": lambda u: u.is_active,
    "last_login": lambda u: u.user.last_login,
    "views": lambda u: u.views_count,
}


def _company_user(request):
    # S163 (23/11): quién mira, para las listas que dependen de él (las
    # nóminas: solo las entregas que ve, hr_calendar/payslip_access).
    from new_ui.lists import CURRENT_USER

    CURRENT_USER.set(request.user.company_user)
    return request.user.company_user


def _visible_sections(company_user):
    """
    [(key, label, icon)] the user can open in the selector.

    ---

    Las secciones del selector que puede abrir el usuario: Permisos,
    solo el superusuario; las demás, con permiso de ver la sección.
    """
    keys = [k for k in SECTIONS if k != PERMISSIONS]
    levels = effective_levels(company_user, keys)
    out = []
    for key, (label, icon, _tabs) in SECTIONS.items():
        if key == PERMISSIONS:
            if company_user.user.is_superuser:
                out.append((key, label, icon))
        elif RANK[levels[key][0]] >= 1:
            out.append((key, label, icon))
    return out


def _filter_users(request):
    """
    Panel users of the filters (search, period, state, company, group,
    role), before sorting.

    ---

    Usuarios del panel según el bloque común de filtros. El periodo se
    aplica al último acceso; "Sección" en usuarios es el rol (el
    criterio más cercano, directriz 4.27 4bis). Con "solo la selección
    actual", solo los marcados.
    """
    params = request.GET
    company_user = _company_user(request)
    users = CompanyUser.objects.filter(
        company=company_user.company, pending_onboarding=False,
    ).select_related("user").prefetch_related("new_ui_user_groups")
    selected = [pk for pk in params.get("selected_ids", "").split(",")
                if pk.isdigit()]
    if params.get("only_selected") == "1" and selected:
        return list(users.filter(pk__in=selected))
    search = params.get("q", "").strip()
    if search:
        users = users.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(dni__icontains=search)
            | Q(phone__icontains=search)
        )
    state = params.get("estado", "1")
    if state == "1":
        users = users.filter(is_active=True)
    elif state == "0":
        users = users.filter(is_active=False)
    company = params.get("empresa", "")
    if company.isdigit():
        users = users.filter(company_id=int(company))
    group = params.get("grupo", "")
    if group == "none":
        users = users.filter(new_ui_user_groups__isnull=True)
    elif group.isdigit():
        users = users.filter(new_ui_user_groups__pk=int(group))
    role = params.get("seccion", "")
    if role:
        users = users.filter(role=role)
    start, end = period_range(params)
    if start:
        users = users.filter(user__last_login__date__gte=start)
    if end:
        users = users.filter(user__last_login__date__lte=end)
    return list(users.distinct())


def _annotate_users(users):
    keys = [k for k, _l, _d in all_view_keys()]
    for user in users:
        levels = effective_levels(user, keys)
        user.views_count = sum(
            1 for key in keys if RANK[levels[key][0]] >= 1)
        user.group_names = ", ".join(
            g.name for g in user.new_ui_user_groups.all())
        user.display_name = (user.user.get_full_name()
                             or user.user.username)
    return users


def _groups(company):
    return list(UiUserGroup.objects.filter(company=company)
                .prefetch_related("members", "grants"))


def _list_context(request):
    """
    The three lists of Permisos (users, user groups, views).

    ---

    Los tres listados de Permisos, con sus filtros y orden.
    """
    company_user = _company_user(request)
    company = company_user.company
    users = _annotate_users(_filter_users(request))
    headers, current = sort_headers(request.GET.get("sort", ""),
                                    USER_COLUMNS)
    users = sort_rows(users, current, USER_SORT, "username")
    groups = _groups(company)
    grants = list(UiViewGrant.objects.filter(company=company)
                  .select_related("user_group", "company_user__user"))
    roles = dict(CompanyUser.ROLE_CHOICES)
    views = []
    for key, label, depth in all_view_keys():
        own = [g for g in grants if g.view_key == key]
        views.append({
            "key": key, "label": label, "depth": depth,
            "roles": ", ".join(
                "%s (%s)" % (roles.get(g.role, g.role), LABELS[g.level])
                for g in own if g.role and not g.user_group_id
                and not g.company_user_id),
            "groups": ", ".join(
                "%s (%s)" % (g.user_group.name, LABELS[g.level])
                for g in own if g.user_group_id),
            "users": ", ".join(
                "%s (%s)" % (g.company_user.user.username, LABELS[g.level])
                for g in own if g.company_user_id),
        })
    return {
        "users": users,
        "user_headers": headers,
        "sort_active": bool(current),
        "current_sort": request.GET.get("sort", ""),
        "groups": groups,
        "views": views,
        "count": len(users),
    }


VIEW_FILTER_KEYS = ("q", "periodo", "cual", "desde", "hasta", "estado",
                    "empresa", "grupo", "seccion")


def _view_filters(company_user, section):
    """
    Common filters saved per tab of a section: {tab: {key: value}}.

    ---

    Los filtros comunes guardados por pestaña (vista) de una sección.
    """
    views = get_saved_state_key(company_user, "nui_filters_" + section,
                                "views", {})
    if not isinstance(views, dict):
        return {}
    return {tab: values for tab, values in views.items()
            if isinstance(values, dict)}


def _save_view_filters(request, section, tab):
    """
    Save the common filters of the request under its tab, and the
    tab's own filters ("x_<tab>_<filter>") as before.

    ---

    Guarda los filtros comunes de la petición en su pestaña (cada vista
    los suyos) y los propios de las pestañas como hasta ahora.
    """
    if "q" not in request.GET or not tab or len(tab) > 60:
        return
    company_user = _company_user(request)
    views = _view_filters(company_user, section)
    views[tab] = {k: request.GET.get(k, "")[:100]
                  for k in VIEW_FILTER_KEYS}
    own = get_saved_state_key(company_user, "nui_filters_" + section,
                              "filters", {})
    own = {k: v for k, v in (own if isinstance(own, dict) else {}).items()
           if k.startswith("x_")}
    own.update({k: v for k, v in request.GET.items()
                if k.startswith("x_") and len(v) < 100})
    _save_keys(company_user, "nui_filters_" + section, {
        "filters": own, "views": views})


def _section_context(company_user, section):
    """
    Context of Documentos, Personal or Centros de gasto in the shell.

    ---

    Lo que pinta el armazón para una sección con listados: opciones del
    bloque común, filtros guardados, columnas de cada pestaña (elegidas
    por el usuario), selecciones, la persona/máquina que se está viendo
    sola (`scope`) y los grupos de selección de siempre.
    """
    from new_ui.lists import (
        extra_param, extras_for, filter_options, list_def, visible_columns,
    )
    from new_ui.groups import (
        MACHINE_KIND, PERSON_KIND, collapsed_state, group_tree,
        parent_choices,
    )

    saved = get_saved_state_key(company_user, "nui_filters_" + section,
                                "filters", {})
    saved = saved if isinstance(saved, dict) else {}
    # S163 (24/11, Miguel Ángel: «los filtros tienen que ser por vista»):
    # buscar, periodo, estado, empresa, grupo y sección se guardan por
    # pestaña; al entrar se pintan los de la pestaña que estaba abierta.
    views = _view_filters(company_user, section)
    tabs_saved = get_saved_state_key(company_user, SCREEN_KEY, "tabs", {})
    open_tab = (tabs_saved or {}).get(section + ":listado", "") if \
        isinstance(tabs_saved, dict) else ""
    current = views.get(open_tab) or {}
    cols = get_saved_state_key(company_user, SCREEN_KEY,
                                   "cols_" + section, {}) or {}
    tabs_cols = []
    for tab_key, tab_label in SECTIONS[section][2]:
        definition = list_def(section, tab_key)
        if definition is None:
            # "Ficha" no es un listado: sin columnas ni filtros propios.
            continue
        visible = {c.key for c in visible_columns(
            definition, cols.get("%s.%s" % (section, tab_key)))}
        tabs_cols.append({
            "key": tab_key, "label": tab_label, "note": definition.note,
            "columns": [{"key": c.key, "label": c.label,
                         "on": c.key in visible, "fixed": c.entity}
                        for c in definition.columns],
            "extras": [{
                "name": extra_param(tab_key, extra), "label": extra.label,
                "value": saved.get(extra_param(tab_key, extra), ""),
                "options": extra.options(company_user.company),
            } for extra in extras_for(definition, company_user.company)],
        })
    selections = get_saved_state_key(company_user, SCREEN_KEY,
                                     "sel_" + section, {})
    selections = {k: v for k, v in (selections or {}).items()
                  if isinstance(v, list)}
    scope = get_saved_state_key(company_user, SCREEN_KEY,
                                "scope_" + section, None)
    kind = MACHINE_KIND if section == "cdg" else PERSON_KIND
    return {
        "f": current,
        "view_filters": views,
        "period": period_context(current),
        "opts": filter_options(section, company_user.company, company_user),
        "tabs_cols": tabs_cols,
        "entity_tabs": ENTITY_TABS.get(section, ()),
        "tab_nouns": TAB_NOUNS.get(section, {}),
        # Acciones › De la vista (new_ui/actions/<sección>.html).
        "circular_families": DocumentTypeCatalog.FAMILY_CHOICES,
        "circular_domains": [
            (code, label) for code, label in DocumentTypeCatalog.DOMAIN_CHOICES
            if code in (DocumentTypeCatalog.DOMAIN_PERSONAL,
                        DocumentTypeCatalog.DOMAIN_BOTH,
                        DocumentTypeCatalog.DOMAIN_COMPANY)],
        **dossier_context(section, company_user.company),
        **schedules_context(section, company_user.company),
        **doc_types_context(section),
        **requirements_context(section),
        **notify_context(section),
        **personnel_context(section),
        **access_context(section, company_user.company),
        **medical_context(section),
        **absences_context(section, company_user.company),
        **payslips_context(section, company_user),
        **safety_context(section),
        **pay_context(section, company_user.company),
        **partes_context(section, company_user),
        **signatures_context(section, company_user),
        "ins_can": section == "doc" and bool(getattr(
            company_user, "insurance_access", False)),
        **epis_context(section),
        **machines_context(section, company_user.company),
        **(logbook_context() if section == "cdg" else {}),
        **accessories_context(section),
        **vacations_context(section, company_user.company),
        "selections": selections,
        # S163: plantillas de columnas de cada vista (como las plantillas
        # de exportación antiguas de Personal).
        "col_templates": get_saved_state_key(
            company_user, SCREEN_KEY, "coltpl_" + section, {}) or {},
        # S163 (23/11): plantillas de columnas de serie de cada vista
        # (p. ej. «Informe de alta en el fichaje»), para todos.
        # «Estándar» (las de entrada) en todas, la primera.
        "col_templates_builtin": {
            tab_key: dict(
                [("Estándar", list(definition.default_cols or [
                    c.key for c in definition.columns]))]
                + list(definition.col_templates.items()))
            for tab_key, definition in (
                (k, list_def(section, k)) for k, _l in SECTIONS[section][2])
            if definition is not None},
        "scope": scope if isinstance(scope, dict) and scope.get("pk")
        else None,
        "group_nodes": group_tree(company_user, kind),
        "groups_collapsed": collapsed_state(company_user, kind),
        "group_parents": parent_choices(editor=company_user, kind=kind),
    }


def _asset_version():
    """
    Version tag of the new interface's JS (latest file change).

    ---

    Huella de la versión del JS de la nueva interfaz (la fecha del más
    reciente), para pedirlo como "?v=..." y que el navegador no use una
    copia vieja tras desplegar (S163: se vio servir el JS anterior).
    """
    import hashlib
    import os

    # S163 (23/11): por contenido, no por fecha: tras un despliegue la
    # fecha no cambió y el navegador siguió con el JS anterior.
    folder = os.path.join(os.path.dirname(__file__), "static", "new_ui")
    digest = hashlib.md5()
    try:
        for sub in ("js", "css"):
            path = os.path.join(folder, sub)
            if not os.path.isdir(path):
                continue
            for name in sorted(os.listdir(path)):
                with open(os.path.join(path, name), "rb") as handle:
                    digest.update(handle.read())
    except OSError:
        return "1"
    return digest.hexdigest()[:10]


class NewUiView(SuperuserRequiredMixin, View):
    """
    GET: the single Documentation view of the new interface.

    ---

    GET: la vista única. `?s=` elige sección (y se guarda); sin él, la
    última que usó el usuario. `?fragment=1` devuelve solo los
    listados de Permisos (al cambiar filtros u orden).
    """

    def get(self, request):
        company_user = _company_user(request)
        sections = _visible_sections(company_user)
        keys = [k for k, _l, _i in sections]
        section = request.GET.get("s") or get_saved_state_key(
            company_user, SCREEN_KEY, "section", DEFAULT_SECTION)
        if section not in keys:
            section = keys[0] if keys else DEFAULT_SECTION
        if request.GET.get("s"):
            _save_keys(company_user, SCREEN_KEY, {"section": section})
        if section == PERMISSIONS:
            apply_list_navigation(request, PERM_SCREEN_KEY, PERM_FILTER_KEYS)
        if section == PERMISSIONS and request.GET.get("fragment") == "1":
            return render(request, "new_ui/permisos/_lists.html",
                          _list_context(request))
        layout = get_saved_state_key(company_user, SCREEN_KEY, "layout", {})
        tabs = get_saved_state_key(company_user, SCREEN_KEY, "tabs", {})
        selection = get_saved_state_key(
            company_user, SCREEN_KEY, "selection_" + section, [])
        context = {
            "active_nav": "new_ui",
            "sections": sections,
            "section": section,
            "section_label": SECTIONS[section][0],
            "list_tabs": SECTIONS[section][2],
            # S163 (23/11): un nivel más en «Qué ver» (Fichaje › ...).
            # S163 (23/11): de la lista de todos o de la ficha de uno.
            "view_groups": [
                (label, [(key, tab_label, view_mode(section, key))
                         for key, tab_label in members])
                for label, members in view_groups(
                    section, SECTIONS[section][2])],
            "list_tab_rows": [(key, label, view_mode(section, key))
                              for key, label in SECTIONS[section][2]],
            "pending": PENDING.get(section, ""),
            "layout": layout if isinstance(layout, dict) else {},
            "tabs": tabs if isinstance(tabs, dict) else {},
            "selection": (
                [str(pk) for pk in selection if str(pk).isdigit()]
                if isinstance(selection, list) else []),
            "period": period_context(request.GET),
            "companies": Company.objects.filter(
                pk=company_user.company_id),
            "user_groups": UiUserGroup.objects.filter(
                company=company_user.company),
            "roles": CompanyUser.ROLE_CHOICES,
            "levels": UiViewGrant.LEVEL_CHOICES,
            "view_keys": all_view_keys(),
        }
        if section == PERMISSIONS:
            context.update(_list_context(request))
            context["f"] = request.GET
            context["opts"] = {
                "companies": [(str(c.pk), c.name)
                              for c in context["companies"]],
                "groups": [("none", "Sin grupo", True)] + [
                    (str(g.pk), g.name, True)
                    for g in context["user_groups"]],
                "families": list(CompanyUser.ROLE_CHOICES),
                "family_label": "Sección (rol)",
            }
        else:
            context.update(_section_context(company_user, section))
        context["asset_v"] = _asset_version()
        return render(request, "new_ui/shell.html", context)


def _subject(company, raw):
    """
    ("user"|"group"|"role", object or role code, label) from "user:12".

    ---

    El sujeto de un editor de permisos a partir de "user:12",
    "group:3" o "role:ADMIN"; None si no existe o no es de la empresa.
    """
    kind, _sep, value = (raw or "").partition(":")
    if kind == "user" and value.isdigit():
        user = CompanyUser.objects.filter(
            company=company, pk=int(value)).select_related("user").first()
        if user:
            return ("user", user, user.user.get_full_name()
                    or user.user.username)
    if kind == "group" and value.isdigit():
        group = UiUserGroup.objects.filter(
            company=company, pk=int(value)).first()
        if group:
            return ("group", group, "Grupo «%s»" % group.name)
    if kind == "role" and value in dict(CompanyUser.ROLE_CHOICES):
        return ("role", value,
                "Rol «%s»" % dict(CompanyUser.ROLE_CHOICES)[value])
    return None


def _grant_filter(kind, obj):
    if kind == "user":
        return {"company_user": obj}
    if kind == "group":
        return {"user_group": obj}
    return {"role": obj, "company_user": None, "user_group": None}


class PermEditorView(SuperuserRequiredMixin, View):
    """
    GET: permission editor of one subject. POST: set one view's level.

    ---

    GET ?subject=user:12|group:3|role:ADMIN: una fila por vista con el
    permiso propio del sujeto (o "Heredado") y, para un usuario, el
    efectivo y de dónde sale. POST (subject, view_key, level): lo
    guarda; level vacío lo quita (vuelve a heredar).
    """

    def get(self, request):
        company = _company_user(request).company
        subject = _subject(company, request.GET.get("subject"))
        if subject is None:
            return render(request, "new_ui/permisos/_editor.html",
                          {"subject": None})
        kind, obj, label = subject
        own = {g.view_key: g.level for g in UiViewGrant.objects.filter(
            company=company, **_grant_filter(kind, obj))}
        keys = [k for k, _l, _d in all_view_keys()]
        effective = effective_levels(obj, keys) if kind == "user" else {}
        rows = []
        for key, view_label, depth in all_view_keys():
            level, origin = effective.get(key, ("", ""))
            rows.append({
                "key": key, "label": view_label, "depth": depth,
                "own": own.get(key, ""),
                "effective": LABELS.get(level, ""),
                "effective_rank": RANK.get(level, 0),
                "origin": origin,
            })
        return render(request, "new_ui/permisos/_editor.html", {
            "subject": request.GET.get("subject"),
            "subject_kind": kind,
            "subject_label": label,
            "rows": rows,
            "levels": UiViewGrant.LEVEL_CHOICES,
        })

    def post(self, request):
        company_user = _company_user(request)
        subject = _subject(company_user.company, request.POST.get("subject"))
        view_key = request.POST.get("view_key", "")
        level = request.POST.get("level", "")
        valid_keys = {k for k, _l, _d in all_view_keys()}
        if (subject is None or view_key not in valid_keys
                or level not in ("",) + tuple(LABELS)):
            return HttpResponseBadRequest("Datos no válidos.")
        kind, obj, label = subject
        set_grant(company_user.company, view_key, level, company_user,
                  **{"role": obj} if kind == "role" else
                  {"user_group": obj} if kind == "group" else
                  {"company_user": obj})
        return JsonResponse({
            "ok": True,
            "message": "%s: %s → %s" % (
                label, label_of(view_key),
                LABELS.get(level, "heredado")),
        })


class PermBulkView(SuperuserRequiredMixin, View):
    """
    POST: one level on one view for every selected user, or group work.

    ---

    POST `action`:
    - "grant": `view_key` + `level` a todos los usuarios marcados.
    - "group_create": grupo nuevo `name` con los marcados.
    - "group_add" / "group_remove": añade o quita los marcados del grupo
      `group`.
    - "group_delete": borra el grupo `group` (y sus permisos).
    """

    def post(self, request):
        company_user = _company_user(request)
        company = company_user.company
        action = request.POST.get("action", "")
        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        users = list(CompanyUser.objects.filter(company=company, pk__in=ids))
        if action == "grant":
            view_key = request.POST.get("view_key", "")
            level = request.POST.get("level", "")
            if (not users or view_key not in
                    {k for k, _l, _d in all_view_keys()}
                    or level not in ("",) + tuple(LABELS)):
                return HttpResponseBadRequest(
                    "Marca usuarios y elige vista y nivel.")
            for user in users:
                set_grant(company, view_key, level, company_user,
                          company_user=user)
            return JsonResponse({"ok": True, "message": (
                "%s → %s para %d usuario%s." % (
                    label_of(view_key), LABELS.get(level, "heredado"),
                    len(users), "" if len(users) == 1 else "s"))})
        if action == "group_create":
            name = request.POST.get("name", "").strip()[:120]
            if not name:
                return HttpResponseBadRequest("Escribe el nombre del grupo.")
            group, created = UiUserGroup.objects.get_or_create(
                company=company, name=name,
                defaults={"created_by": company_user})
            group.members.add(*users)
            return JsonResponse({"ok": True, "message": (
                "Grupo «%s» %s con %d usuario%s." % (
                    name, "creado" if created else "ampliado", len(users),
                    "" if len(users) == 1 else "s"))})
        group = UiUserGroup.objects.filter(
            company=company, pk=request.POST.get("group") or 0).first()
        if group is None:
            return HttpResponseBadRequest("Elige un grupo.")
        if action == "group_add":
            group.members.add(*users)
            text = "Añadidos %d a «%s»." % (len(users), group.name)
        elif action == "group_remove":
            group.members.remove(*users)
            text = "Quitados %d de «%s»." % (len(users), group.name)
        elif action == "group_delete":
            text = "Grupo «%s» borrado." % group.name
            group.delete()
        else:
            return HttpResponseBadRequest("Acción no válida.")
        return JsonResponse({"ok": True, "message": text})


class PermGroupMembersView(SuperuserRequiredMixin, View):
    """
    GET ?groups=1,2: the members of those user groups (their sum).

    ---

    GET: los usuarios de los grupos marcados (la suma), para cargarlos
    como selección, como los grupos de selección del resto del panel.
    """

    def get(self, request):
        company = _company_user(request).company
        ids = [pk for pk in request.GET.get("groups", "").split(",")
               if pk.isdigit()]
        users = CompanyUser.objects.filter(
            company=company, new_ui_user_groups__pk__in=ids,
        ).select_related("user").distinct()
        return JsonResponse({"users": [
            [str(u.pk), u.user.get_full_name() or u.user.username]
            for u in users]})


# ======================================================================
# Documentos, Personal y Centros de gasto (S163, "Termina todo")
# ======================================================================
def _scope_pk(request):
    raw = request.GET.get("scope", "")
    return int(raw) if raw.isdigit() else None


def _check_view(request, section, tab):
    from new_ui.permissions import can_view

    return can_view(_company_user(request), "%s.%s" % (section, tab))


class NewUiListView(SuperuserRequiredMixin, View):
    """
    GET ?s=&t=&filters...: one list tab of a section (table fragment).

    ---

    GET: el listado de una pestaña con el bloque común de filtros, la
    vista de una sola persona/máquina (`scope`), el orden por cabecera
    y las columnas elegidas por el usuario. Pinta como mucho
    ROW_LIMIT filas y dice cuántas hay en total.
    """

    def get(self, request):
        from new_ui.lists import (
            ROW_LIMIT, apply_extras, filtered, headers, list_def,
            materialize, rows_for, sorted_qs, visible_columns,
        )

        section = request.GET.get("s", "")
        tab = request.GET.get("t", "")
        if section in SECTIONS and section != PERMISSIONS:
            _save_view_filters(request, section, tab)
        if (section, tab) == ("per", "alta_fichaje") and _check_view(
                request, section, tab):
            # Vista propia (no es un listado de modelo): S163.
            from new_ui.views_onboarding import render_report

            return render_report(request)
        if (section, tab) == ("doc", "avisos_pendientes") and _check_view(
                request, section, tab):
            # S163 (23/11): avisos pendientes y su configuración.
            from new_ui.views_notices import render_pending

            return render_pending(request)
        if (section, tab) == ("doc", "avisos_config") and _check_view(
                request, section, tab):
            from new_ui.views_notices import render_config

            return render_config(request)
        if (section, tab) == ("doc", "seguros"):
            # S163 (24/11): solo con acceso a los seguros (como la antigua).
            from new_ui.views_insurance_nui import can_use_insurance

            if not can_use_insurance(_company_user(request)):
                return HttpResponse(
                    '<p class="p-2 text-muted small mb-0">Los informes de '
                    'seguros no son para tu usuario.</p>')
        if section == "doc" and tab in ("firmas", "firmas_guardadas",
                                        "certificados", "agentes_firma"):
            # S163 (24/11): las firmas, solo para quien tiene acceso a
            # ellas (como en la antigua).
            from new_ui.views_signatures_nui import (
                can_sign, render_certificates,
            )

            if not can_sign(_company_user(request)):
                return HttpResponse(
                    '<p class="p-2 text-muted small mb-0">Las firmas no '
                    'son para tu usuario.</p>')
            if tab == "certificados" and _check_view(request, section,
                                                     tab):
                return render_certificates(request)
        if (section, tab) == ("doc", "pagos_config") and _check_view(
                request, section, tab):
            # S163 (23/11): Horas y pagos › Qué se paga.
            from new_ui.views_pay import render_settings

            return render_settings(request)
        if (section, tab) == ("per", "saldo_vacaciones") and _check_view(
                request, section, tab):
            from new_ui.views_vacations import render_balance

            return render_balance(request)
        definition = list_def(section, tab)
        if definition is None or not _check_view(request, section, tab):
            return HttpResponseBadRequest("Listado no disponible.")
        company_user = _company_user(request)
        cols = get_saved_state_key(company_user, SCREEN_KEY,
                                   "cols_" + section, {})
        columns = visible_columns(
            definition, (cols or {}).get("%s.%s" % (section, tab)))
        scope_pk = _scope_pk(request)
        qs = filtered(definition, company_user.company, request.GET,
                      scope_pk)
        if scope_pk and definition.entity:
            # Viendo la ficha de una persona o máquina, su columna se
            # repetiría en todas las filas (Miguel Ángel, S163): fuera.
            # La exportación la conserva, para que el archivo diga de
            # quién es.
            columns = [c for c in columns if not c.entity] or columns
        qs, post = apply_extras(definition, company_user.company, qs,
                                request.GET, tab)
        qs, current = sorted_qs(definition, qs, request.GET.get("sort", ""))
        # Sin orden elegido por el usuario: los vigentes primero (como la
        # ficha de siempre), con la vigencia real, no solo la marcada en
        # BD; dentro de cada grupo, el orden de siempre.
        objects, total = materialize(
            definition, qs, post, ROW_LIMIT,
            state_first=bool(definition.prepare) and not current)
        rows = rows_for(definition, objects, columns)
        # S163 (23/11): la fila TOTAL, fija abajo (de todo lo filtrado).
        totals_row = None
        if definition.totals and total:
            values = definition.totals(qs)
            totals_row = [{"value": values.get(c.key, ""), "css": c.css}
                          for c in columns]
        from new_ui.filters import period_summary

        return render(request, "new_ui/_list.html", {
            "period_summary": period_summary(*period_range(request.GET)),
            "totals_row": totals_row,
            "section": section,
            "tab": tab,
            "definition": definition,
            "headers": headers(definition, columns, current),
            "rows": rows,
            "total": total,
            "shown": len(rows),
            "limited": total > len(rows),
            "sort_active": bool(current),
        })


class NewUiExportView(SuperuserRequiredMixin, View):
    """
    GET ?s=&t=&export_format=xlsx|pdf|html|print: the list, exported.

    ---

    GET: exporta el listado con sus filtros, su orden y sus columnas
    (o solo las filas marcadas, `selected`), sin límite de filas, a
    Excel, PDF, HTML o impresión (panel/export_formats).
    """

    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        from new_ui.export_formats import workbook_response
        from new_ui.lists import (
            apply_extras, filtered, list_def, materialize, rows_for,
            sorted_qs, visible_columns,
        )

        section = request.GET.get("s", "")
        tab = request.GET.get("t", "")
        definition = list_def(section, tab)
        if definition is None or not _check_view(request, section, tab):
            return HttpResponseBadRequest("Listado no disponible.")
        company_user = _company_user(request)
        cols = get_saved_state_key(company_user, SCREEN_KEY,
                                   "cols_" + section, {})
        columns = visible_columns(
            definition, (cols or {}).get("%s.%s" % (section, tab)))
        qs = filtered(definition, company_user.company, request.GET,
                      _scope_pk(request))
        selected = [pk for pk in request.GET.getlist("selected")
                    if pk.isdigit()]
        if selected:
            qs = qs.filter(pk__in=selected)
        qs, post = apply_extras(definition, company_user.company, qs,
                                request.GET, tab)
        qs, _current = sorted_qs(definition, qs, request.GET.get("sort", ""))
        objects, _total = materialize(definition, qs, post, 20000)
        rows = rows_for(definition, objects, columns)
        workbook = Workbook()
        # S163 (como la exportación antigua de Personal, «Separar por»):
        # una hoja por cada valor de la columna elegida (empresa,
        # sección...); sin elegir, una sola hoja.
        split_key = request.GET.get("split_col", "")
        keys = [c.key for c in columns]
        groups = [(definition.label, rows)]
        if split_key == "__grupos" and definition.entity:
            groups = _split_by_groups(company_user, section, rows,
                                      request.GET.get("split_groups", ""))
        elif split_key in keys:
            position = keys.index(split_key)
            buckets = {}
            for row in rows:
                value = str(row["cells"][position]["value"] or "").strip()
                buckets.setdefault(value, []).append(row)
            groups = [(value or "Sin %s" % columns[position].label.lower(),
                       buckets[value])
                      for value in sorted(buckets, key=lambda v: (not v, v))]
        used = set()
        for number, (title, group_rows) in enumerate(groups):
            sheet = workbook.active if number == 0 else workbook.create_sheet()
            name = "".join(ch for ch in str(title).upper()
                           if ch not in '[]:*?/\\')[:28] or "HOJA"
            while name in used:
                name = name[:25] + "_%d" % number
            used.add(name)
            sheet.title = name
            _fill_sheet(sheet, columns, group_rows, Font, PatternFill)
        return workbook_response(
            request, workbook,
            "%s_%s" % (SECTIONS[section][0], definition.label))


def _split_by_groups(company_user, section, rows, raw_groups):
    """
    [(group name, rows)] for the chosen selection groups.

    ---

    S163 (como «Separar por grupos de selección» de la exportación
    antigua): una hoja por cada grupo marcado en Selección, contando sus
    subgrupos; una persona o máquina sale en cada grupo en el que esté y
    lo que no cae en ninguno va al final como «Sin grupo».
    """
    from new_ui.groups import MACHINE_KIND, PERSON_KIND, group_tree

    kind = MACHINE_KIND if section == "cdg" else PERSON_KIND
    nodes = {node["group"].pk: node
             for node in group_tree(company_user, kind)
             if node["kind"] == "group"}

    def members(pk, seen):
        if pk in seen or pk not in nodes:
            return set()
        seen.add(pk)
        ids = set(nodes[pk]["member_ids"])
        for child in nodes[pk]["children"]:
            ids |= members(child, seen)
        return ids

    wanted = [int(v) for v in raw_groups.split(",") if v.isdigit()]
    groups, placed = [], set()
    for pk in wanted:
        if pk not in nodes:
            continue
        ids = members(pk, set())
        placed |= ids
        groups.append((nodes[pk]["group"].name,
                       [r for r in rows if r["entity_pk"] in ids]))
    rest = [r for r in rows if r["entity_pk"] not in placed]
    if rest or not groups:
        groups.append(("Sin grupo", rest))
    return groups


def _fill_sheet(sheet, columns, rows, Font, PatternFill):
    """
    Header, banded rows and widths of one exported sheet.

    ---

    Cabecera, filas en bandas y anchos de una hoja exportada.
    """
    sheet.append([c.label for c in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0D6EFD")
    band = PatternFill("solid", fgColor="EEF4FF")
    for index, row in enumerate(rows):
        sheet.append([c["value"] for c in row["cells"]])
        if index % 2:
            for cell in sheet[sheet.max_row]:
                cell.fill = band
    for column_cells in sheet.columns:
        width = max(len(str(c.value or "")) for c in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = (
            min(max(width + 2, 8), 60))


def _ficha_item(label, display, name="", value="", kind="text"):
    """
    One row of a ficha box: label, shown value and (if editable) input.

    ---

    Una fila de un apartado de la ficha: rótulo, valor que se ve y,
    si se puede modificar, el nombre y el valor del campo (`kind`:
    text, date o textarea).
    """
    return {"label": label, "display": display, "name": name,
            "value": value, "kind": kind}


def _scalable_svg(svg):
    """
    Give a fixed-size SVG a viewBox so CSS can resize it.

    ---

    El SVG del QR trae ancho y alto fijos y sin viewBox: al encajarlo en
    su caja de la ficha se cortaba o tapaba el texto (S163). Con viewBox
    se escala entero al tamaño de la caja.
    """
    match = re.search(r'<svg[^>]*\swidth="(\d+)"\s+height="(\d+)"', svg)
    if not match or "viewBox" in svg[:300]:
        return svg
    width, height = match.groups()
    return svg.replace(
        "<svg ", '<svg viewBox="0 0 %s %s" ' % (width, height), 1)


def _machine_ficha_context(request, machine):
    """
    Ficha of a cost centre: photo, technical card boxes and its form.

    ---

    La ficha del centro de gasto en la pestaña "Ficha": foto, los
    apartados de la tarjeta técnica (como cajas, todas a la vista) y,
    al pulsar "Modificar", su formulario real (MachineAssetForm), que
    se guarda por la vista real de la ficha (NewUiMachineSaveView).
    """
    from django.urls import reverse

    from fleet import qr_sheet_service as qr
    from new_ui.forms import MachineAssetForm
    from new_ui.machine_card import (
        EXPORT_CHOICES, card_sections, machine_title,
    )

    avatar = machine.avatar_document
    boxes = [{"title": title, "items": [_ficha_item(label, value)
                                        for label, value in rows]}
             for title, rows in card_sections(machine)]
    if machine.specs_read_at or machine.specs_source:
        boxes.append({"title": "Origen de los datos", "items": [
            _ficha_item("Leídos de", machine.specs_source or "—"),
            _ficha_item("Fecha", machine.specs_read_at.strftime(
                "%d/%m/%Y %H:%M") if machine.specs_read_at else "—"),
        ]})
    return {
        "kind": "machine",
        "obj": machine,
        "title": machine_title(machine),
        "subtitle": " · ".join(p for p in (machine.type_name, machine.family,
                                            machine.company_name) if p),
        "active": machine.is_active,
        "boxes": boxes,
        "photo_url": (reverse("new_ui:document_file", args=[avatar.pk])
                      if avatar is not None and not avatar.deleted_at
                      else ""),
        "export_url": reverse("new_ui:machine_card_export",
                              args=[machine.pk]),
        "export_formats": EXPORT_CHOICES,
        "form": MachineAssetForm(instance=machine, company=machine.company),
        # H23 (S154): el QR que se pega en el vehículo; S163: a la vista
        # en la ficha, con su página (observaciones, fotos, vídeos) y la
        # descarga para imprimir. Miguel Ángel: "no encuentro el QR".
        "qr_svg": _scalable_svg(qr.qr_image(
            qr.public_url(request, qr.sheet_for(machine)), "svg", scale=4)),
        "qr_public_url": qr.public_url(request, qr.sheet_for(machine)),
        "qr_image_url": reverse("new_ui:machine_qr_image",
                                args=[machine.pk]),
        "save_url": reverse("new_ui:machine_save", args=[machine.pk]),
    }


def _person_ficha_context(request, person):
    """
    Ficha of a worker: photo, every datum in boxes, employment, kit.

    ---

    La ficha del trabajador en la pestaña "Ficha": foto y todos sus
    datos en cajas a la vista (datos personales, contacto, empresa y
    puesto, caducidades, observaciones), sus periodos de contratación y
    los accesorios de elevación que tiene entregados. "Modificar" deja
    editables en el sitio los mismos campos que la ficha de siempre y
    guarda por su misma vista (documentation_personal_update); lo que
    trae el Excel de personal (DNI, empresa, caducidades) se queda de
    solo lectura, como allí.
    """
    from django.urls import reverse

    from document_explorer.models import JobPosition, PersonIdPhoto
    from new_ui.lists import fmt_date, person_name, persons_base
    from new_ui.docs_core import (
        _person_employment_periods, _person_lifting_accessories,
    )

    id_photo = PersonIdPhoto.objects.filter(person=person).values(
        "extracted_at").first()
    avatar = person.avatar_document
    if id_photo:
        photo_url = "%s?v=%s" % (
            reverse("new_ui:person_photo", args=[person.pk]),
            int(id_photo["extracted_at"].timestamp()))
    elif avatar is not None and not avatar.deleted_at:
        photo_url = reverse("new_ui:document_file",
                            args=[avatar.pk])
    else:
        photo_url = ""

    def text(label, field, kind="text"):
        value = getattr(person, field) or ""
        return _ficha_item(label, value, field, value, kind)

    def day(label, field, editable=False):
        value = getattr(person, field)
        return _ficha_item(label, fmt_date(value),
                           field if editable else "",
                           value.isoformat() if value else "", "date")

    section = persons_base().filter(pk=person.pk).values_list(
        "current_section_name", flat=True).first()
    user = person.company_user
    requirements = list(person.document_requirements.order_by("name"))
    boxes = [
        {"title": "Datos personales", "items": [
            text("Nombre", "given_name"),
            text("Primer apellido", "first_surname"),
            text("Segundo apellido", "second_surname"),
            text("Apodo", "nickname"),
            _ficha_item("DNI/NIE", person.dni),
            day("Fecha de nacimiento", "birth_date"),
        ]},
        {"title": "Contacto", "items": [
            text("Teléfono", "phone"),
            text("Teléfono 2", "phone_secondary"),
            text("Correo", "email"),
            text("Domicilio", "address_street"),
            text("C.P.", "postal_code"),
            text("Población", "city"),
            text("Provincia", "province"),
            text("Contacto de emergencia", "emergency_contact"),
            text("Teléfono de emergencia", "phone_emergency"),
        ]},
        {"title": "Empresa y puesto", "items": [
            _ficha_item("Empresa", person.employer_company),
            text("Categoría profesional", "professional_category"),
            _ficha_item("Sección (SIME)", section or ""),
            _ficha_item("Requisitos de documentación", ", ".join(
                r.name for r in requirements), "document_requirements",
                [r.pk for r in requirements], "requirements"),
            day("Fecha de alta", "hire_date", True),
            day("Fecha de baja", "termination_date", True),
            text("Nº de afiliación a la S.S.", "ss_affiliation_number"),
            _ficha_item("Usuario del panel", "%s (%s)" % (
                user.user.username, user.get_role_display())
                if user is not None else ""),
        ]},
        {"title": "Caducidades", "items": [
            day("DNI", "dni_expiry_date"),
            day("Carné de conducir", "driving_license_expiry_date"),
            day("Carné de gruista", "crane_operator_card_expiry_date"),
            day("CAP", "driver_qualification_card_expiry_date"),
            day("Tarjeta de tacógrafo", "tachograph_card_expiry_date"),
            day("Reconocimiento médico", "medical_exam_date"),
        ]},
        {"title": "Observaciones", "wide": True, "items": [
            text("Observaciones", "notes", "textarea"),
        ]},
    ]
    return {
        "kind": "person",
        "obj": person,
        "title": person_name(person),
        "subtitle": " · ".join(p for p in (person.professional_category,
                                            person.employer_company) if p),
        "active": person.is_active_employee,
        "boxes": boxes,
        "positions": JobPosition.objects.order_by("name"),
        "employment": _person_employment_periods(person),
        "accessories": _person_lifting_accessories(
            person, _company_user(request).company),
        "photo_url": photo_url,
        "save_url": reverse("new_ui:person_update",
                            args=[person.pk]),
    }


def _machine_qr_context(request, machine):
    """
    "QR" tab of a cost centre: what the worker sees when reading it.

    ---

    La pestaña "QR" del centro de gasto (H23, S154; copia de la página
    MachineQrSheetView de la antigua): el QR, el enlace, la revisión y
    la ficha técnica que salen en él, observaciones, fotos y vídeos, y
    la contraseña del editor QR del fichaje.
    """
    from django.urls import reverse

    from fleet import qr_sheet_service as qr

    sheet = qr.sheet_for(machine)
    url = qr.public_url(request, sheet)
    return {
        "machine": machine,
        "sheet": sheet,
        "public_url": url,
        "qr_svg": qr.qr_image(url, "svg", scale=6),
        "media": qr.media_rows(sheet),
        "specs": qr.spec_rows(machine),
        "service_lines": qr.service_lines(machine),
        "max_photo_mb": qr.MAX_PHOTO_BYTES // (1024 * 1024),
        "max_video_mb": qr.MAX_VIDEO_BYTES // (1024 * 1024),
        "editor_password_set": qr.editor_password_set(machine.company),
        "min_password_length": qr.MIN_PASSWORD_LENGTH,
        "image_url": reverse("new_ui:machine_qr_image", args=[machine.pk]),
        "action_url": reverse("new_ui:machine_qr_action", args=[machine.pk]),
    }


class NewUiCardView(SuperuserRequiredMixin, View):
    """
    GET ?s=cdg|per&pk=: the "Ficha" tab of one machine or person.

    ---

    GET: la pestaña "Ficha" de la máquina o la persona que se está
    viendo sola, en el panel del listado y con el mismo formato que el
    resto de la vista (S163, Miguel Ángel: "no quiero la organización
    por acordeones [...] parece que estamos dentro de una aplicación
    diferente"). Sustituye, dentro de la nueva interfaz, a las fichas
    de acordeones de siempre, que siguen igual en producción.
    """

    def get(self, request):
        from document_explorer.models import PersonIdentity
        from fleet.models import MachineAsset

        section = request.GET.get("s", "")
        pk = request.GET.get("pk", "")
        tab = request.GET.get("t", FICHA)
        company_user = _company_user(request)
        if not pk.isdigit():
            return HttpResponseBadRequest("Falta la persona o máquina.")
        if (tab not in ENTITY_TABS.get(section, ())
                or not _check_view(request, section, tab)):
            return HttpResponseBadRequest("Ficha no disponible.")
        if section == "cdg" and tab == "qr":
            machine = MachineAsset.objects.filter(
                company=company_user.company, pk=int(pk)).first()
            if machine is None:
                return HttpResponseBadRequest("No existe.")
            return render(request, "new_ui/_qr.html",
                          _machine_qr_context(request, machine))
        if section == "per" and tab == "desglose_vacaciones":
            from new_ui.views_vacations import render_detail

            person = PersonIdentity.objects.filter(pk=int(pk)).select_related(
                "company_user__base", "company_user__company").first()
            if person is None:
                return HttpResponseBadRequest("No existe.")
            return render_detail(request, person)
        if section == "per" and tab == "pagos":
            from new_ui.views_pay import render_worker

            person = PersonIdentity.objects.filter(pk=int(pk)).select_related(
                "company_user__company").first()
            if person is None:
                return HttpResponseBadRequest("No existe.")
            return render_worker(request, person)
        if section == "per" and tab == "jornadas":
            from new_ui.views_clock import render_jornadas

            person = PersonIdentity.objects.filter(pk=int(pk)).select_related(
                "company_user__company").first()
            if person is None:
                return HttpResponseBadRequest("No existe.")
            return render_jornadas(request, person)
        if section == "cdg":
            machine = MachineAsset.objects.filter(
                company=company_user.company, pk=int(pk)).first()
            if machine is None:
                return HttpResponseBadRequest("No existe.")
            context = _machine_ficha_context(request, machine)
        elif section == "per":
            person = PersonIdentity.objects.filter(pk=int(pk)).select_related(
                "company_user__user").first()
            if person is None:
                return HttpResponseBadRequest("No existe.")
            context = _person_ficha_context(request, person)
        else:
            return HttpResponseBadRequest("Sin ficha.")
        return render(request, "new_ui/_ficha.html", context)


class NewUiMachineSaveView(SuperuserRequiredMixin, View):
    """
    POST: save the machine form of the "Ficha" tab.

    ---

    POST: guarda el formulario de la máquina de la pestaña "Ficha".
    Copia de lo que hace MachineDetailView.post de la antigua (S163):
    código en mayúsculas y, si cambian familia o código, su carpeta y
    los nombres de sus documentos le siguen (sync_machine_documents) y
    el agente mueve la carpeta local. Errores del formulario, en JSON.
    """

    def post(self, request, pk):
        from document_explorer import machine_local_folder_service
        from document_explorer.machine_folder_service import (
            sync_machine_documents,
        )
        from fleet.models import MachineAsset
        from new_ui.forms import MachineAssetForm

        company_user = _company_user(request)
        machine = MachineAsset.objects.filter(
            company=company_user.company, pk=pk).first()
        if machine is None:
            return JsonResponse({"ok": False, "message": "No existe."},
                                status=404)
        previous_local = machine_local_folder_service.current_local_folder(
            machine)
        form = MachineAssetForm(request.POST, instance=machine,
                                company=machine.company)
        if not form.is_valid():
            errors = "; ".join(
                "%s: %s" % (form.fields[f].label if f in form.fields else f,
                            " ".join(e)) for f, e in form.errors.items())
            return JsonResponse({"ok": False, "message": errors
                                 or "No se ha podido guardar."}, status=400)
        updated = form.save(commit=False)
        updated.code = updated.code.strip().upper()
        updated.save()
        sync_machine_documents(updated)
        machine_local_folder_service.follow_change(
            updated, previous_local, requested_by=company_user)
        return JsonResponse({"ok": True, "message": "Guardado."})


class NewUiMenuView(SuperuserRequiredMixin, View):
    """
    GET ?kind=person|machine&pk=: right-click menu of one entity (JSON).

    ---

    GET: el menú del botón derecho de una persona o máquina en la nueva
    interfaz (new_ui_context_menu.js): su nombre y sus pestañas de la
    nueva interfaz que este usuario puede ver, para abrirlas aquí.
    """

    ICONS = {
        "ficha": "bi-person-vcard", "qr": "bi-qr-code",
        "documentos": "bi-folder2-open", "laboral": "bi-briefcase",
        "partes": "bi-clipboard-check", "fichajes": "bi-clock-history",
        "repostajes": "bi-fuel-pump", "vacaciones": "bi-sun",
        "salud": "bi-heart-pulse", "ausencias": "bi-calendar-x",
        "solicitudes": "bi-envelope-paper", "horarios": "bi-clock",
        "nominas": "bi-cash-stack", "epis": "bi-cone-striped",
        "requisitos": "bi-list-check", "especificaciones": "bi-rulers",
        "avisos": "bi-exclamation-triangle", "revisiones": "bi-wrench",
        "accesorios": "bi-link-45deg", "taller": "bi-tools",
        "averias": "bi-cone", "libro": "bi-journal-text",
        "equipos": "bi-people",
    }

    def get(self, request):
        from document_explorer.models import PersonIdentity
        from fleet.models import MachineAsset
        from new_ui.lists import machine_label, person_name

        kind = request.GET.get("kind", "")
        pk = request.GET.get("pk", "")
        if not pk.isdigit() or kind not in ("person", "machine"):
            return HttpResponseBadRequest("Falta la persona o máquina.")
        section = "per" if kind == "person" else "cdg"
        if kind == "person":
            obj = PersonIdentity.objects.filter(pk=int(pk)).first()
            name = person_name(obj) if obj else ""
        else:
            obj = MachineAsset.objects.filter(
                company=_company_user(request).company, pk=int(pk)).first()
            name = machine_label(obj) if obj else ""
        if obj is None:
            return HttpResponseBadRequest("No existe.")
        items = []
        for key, label in SECTIONS[section][2]:
            if key == "general" or not _check_view(request, section, key):
                continue
            items.append({"code": key, "label": label,
                          "icon": self.ICONS.get(key, "bi-list")})
        return JsonResponse({"name": name, "items": items})
