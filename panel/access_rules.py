# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/access_rules.py
"""
Who can enter each screen of the current panel, read from the same rules
that decide it.

---

S163 (26/11, Miguel Ángel: «ya lo aplicamos para controlar todo el
panel [...] de ese modo veo claramente quien y a qué puede acceder»).
Quién entra a cada pantalla del panel actual, leído de las mismas
reglas que lo deciden: los mixins de acceso (sus `allowed_roles` o sus
funciones `can_...`) y las pestañas de Documentación
(`documentation_tabs`, que usa la propia vista). Lo lee Permisos ›
Árbol de la nueva interfaz.
"""

from ivr_config.models import CompanyUser


def documentation_tabs(company_user):
    """
    Tabs of the Documentation hub this user can see.

    ---

    Pestañas del hub de Documentación que ve este usuario (antes, dentro
    de DocumentationHubV2View; misma lógica).
    """
    from panel.views_payslips import can_send_payslips

    valid_tabs = (
        "maquinaria", "personal", "equipos", "epis", "accesorios",
        "vacaciones",
        "fichajes", "horarios", "calendario", "requisitos", "avisos",
        "circulares",
        "plantillas", "bandeja", "revisiones", "repostajes",
        "especificaciones",
        "solicitudes", "nominas", "pedir", "firmas", "seguros",
        "cae",
    )
    # H30 (S126): "Bandeja de entrada" solo para quien puede subir
    # documentación (mismos roles que DocsUploadAccessMixin).
    can_use_inbox = company_user.role in (
        CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_DOCS_SUPERVISOR,
    )
    if not can_use_inbox:
        valid_tabs = tuple(t for t in valid_tabs if t != "bandeja")
    # S148: "Pedir documentos", mismos roles que pedir desde Avisos.
    from panel.views_document_alerts import DOC_REQUEST_ROLES

    can_request_docs = (
        company_user.role in DOC_REQUEST_ROLES)
    if not can_request_docs:
        valid_tabs = tuple(t for t in valid_tabs if t != "pedir")
    # H24 (S129): "Fichajes" lleva posiciones GPS -- solo los roles
    # de SupervisorAccessMixin.
    can_view_clock_events = company_user.role in (
        CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
    )
    if not can_view_clock_events:
        valid_tabs = tuple(
            t for t in valid_tabs
            if t not in ("fichajes", "horarios", "solicitudes")
        )
    # S149: pestaña "Nóminas" (entrega de nóminas).
    if not can_send_payslips(company_user):
        valid_tabs = tuple(t for t in valid_tabs if t != "nominas")
    # S153: pestaña "Firmas", solo con acceso a las firmas (Yolanda).
    from panel.views_signatures import can_use_signatures

    can_sign = can_use_signatures(company_user)
    if not can_sign:
        valid_tabs = tuple(t for t in valid_tabs if t != "firmas")
    # S152: pestaña "Seguros", solo con acceso a los informes de
    # seguros (Yolanda, Alejandro y Miguel Ángel).
    from panel.views_insurance import can_use_insurance

    can_insure = can_use_insurance(company_user)
    if not can_insure:
        valid_tabs = tuple(t for t in valid_tabs if t != "seguros")
    # S156: pestaña "Correos CAE" (avisos de las plataformas de
    # coordinación), para administración y supervisión.
    from cae_mail.views import can_use_cae

    can_cae = can_use_cae(company_user)
    if not can_cae:
        valid_tabs = tuple(t for t in valid_tabs if t != "cae")
    return valid_tabs


# Plumbing routes, not screens anyone "enters" (session, navigation
# state, export templates, device trust...).
# ---
# Rutas de fontanería, no pantallas a las que «se entra».
SKIP_AREAS = {
    "navegacion", "password", "presence", "trust-device", "vista",
    "exportar", "export-templates", "",
}

AREA_LABELS = {
    "absence-categories": "Tipos de ausencia",
    "albaranes": "Albaranes",
    "analytics": "Análisis",
    "budgets": "Asistencia",
    "cae": "Correos CAE",
    "chat": "Chat y averías",
    "company": "Empresa",
    "copias-seguridad": "Copias de seguridad",
    "documentacion-centros-gasto": "Centros de gasto",
    "explorador": "Explorador de archivos",
    "fleet": "Centros de gasto",
    "gdrive": "Google Drive",
    "gruas": "Grúas",
    "history": "Historial",
    "mi-buzon": "Mi buzón",
    "mis-solicitudes": "Mis solicitudes",
    "nominas": "Nóminas",
    "obras": "Obras",
    "operator": "Mis partes",
    "profile": "Mi perfil",
    "repuestos": "Repuestos",
    "spare-parts": "Repuestos",
    "solicitudes": "Solicitudes",
    "taller": "Taller",
    "users": "Usuarios del panel",
    "vacaciones": "Vacaciones",
    "whatsapp": "WhatsApp",
    "work-orders": "Partes de trabajo",
    "work-periods": "Partes de trabajo",
    "workday-schedule": "Horarios",
    "worker-absences": "Ausencias",
}
# The switchboard screens, one area.
# ---
# Las pantallas de la centralita, en un área.
SWITCHBOARD = {
    "blockedcallers", "callflows", "contacts", "datacapturesets", "ivr",
    "phonenumbers", "sections", "telefonia", "voiceprofile",
}
DOC_LABELS = {
    "accesorios": ("Accesorios de elevación", "accesorios"),
    "avisos": ("Avisos", "avisos"),
    "bandeja": ("Bandeja de entrada", "bandeja"),
    "calendario": ("Calendario", "calendario"),
    "circulares": ("Circulares", "circulares"),
    "dosieres": ("Dosieres", ""),
    "epis": ("EPIs", "epis"),
    "lotes-epi": ("EPIs", "epis"),
    "equipos": ("Equipos", "equipos"),
    "especificaciones": ("Especificaciones", "especificaciones"),
    "fichajes": ("Fichajes", "fichajes"),
    "firmas": ("Firmas", "firmas"),
    "horarios": ("Horarios", "horarios"),
    "maquinaria": ("Maquinaria", "maquinaria"),
    "nominas": ("Nóminas", "nominas"),
    "pedir-documentos": ("Pedir documentos", "pedir"),
    "personal": ("Personal", "personal"),
    "plantillas-dosier": ("Plantillas de dosier", "plantillas"),
    "puestos": ("Puestos de trabajo", ""),
    "repostajes": ("Repostajes", "repostajes"),
    "revisiones": ("Revisiones", "revisiones"),
    "seguros": ("Seguros", "seguros"),
    "solicitudes": ("Solicitudes", "solicitudes"),
    "vacaciones": ("Vacaciones", "vacaciones"),
}


def _area_of(route):
    """
    (key, label, documentation tab or "") of a panel route, or None.

    ---

    Área de una ruta del panel: clave, nombre de negocio y, si es de
    Documentación, la pestaña del hub que la muestra. None si es
    fontanería.
    """
    parts = route.split("/")
    first = parts[1] if len(parts) > 1 else ""
    if first in SKIP_AREAS:
        return None
    if first in SWITCHBOARD:
        return ("centralita", "Centralita", "")
    if first == "documentacion":
        sub = parts[2].split("<")[0] if len(parts) > 2 else ""
        label, tab = DOC_LABELS.get(sub, ("General", ""))
        key = "doc:" + (tab or (sub if sub in DOC_LABELS else "general"))
        return (key, "Documentación › " + label, tab)
    if first == "cae":
        return ("cae", "Documentación › Correos CAE", "cae")
    if first == "nominas":
        return ("doc:nominas", "Documentación › Nóminas", "nominas")
    label = AREA_LABELS.get(first, first.replace("-", " ").capitalize())
    return (label, label, "")


def _rules():
    """
    [(class, label, check(company_user), per_person)] of every access
    gate of the panel, most specific first.

    ---

    Cada puerta de acceso del panel: la clase (mixin), su nombre, la
    comprobación (la misma función o lista de roles que usa el mixin) y
    si depende de la persona y no solo del rol. Una clase que no esté
    aquí sale como «sin catalogar», para que se vea.
    """
    from cae_mail.views import CaeAccessMixin, can_use_cae
    from crane_albaranes.views_panel import CraneAccessMixin, can_access
    from document_explorer.permissions import readable_buckets
    from document_explorer.views import ExplorerAccessMixin
    from panel import mixins
    from panel.views_db_backups import AdminOnlyMixin
    from panel.views_insurance import (
        InsuranceAccessMixin, can_use_insurance,
    )
    from panel.views_machine_service import (
        _ServiceEditMixin, can_edit_service,
    )
    from panel.views_payslips import PayslipAccessMixin, can_send_payslips
    from panel.views_signatures import (
        SignatureAccessMixin, can_use_signatures,
    )
    from workorder_spare_parts.views import CatalogReadAccessMixin

    def roles(cls, attr="allowed_roles"):
        return lambda cu: cu.role in getattr(cls, attr)

    def budget_audit(cu):
        return (cu.role in (CompanyUser.ROLE_ADMIN,
                            CompanyUser.ROLE_ASSIST_SUPERVISOR)
                or (cu.role == CompanyUser.ROLE_ASSISTANCE
                    and cu.can_view_budget_breakdown))

    m = mixins
    return [
        (m.SuperuserRequiredMixin, "Solo superusuario",
         lambda cu: cu.user.is_superuser, True),
        (m.FleetManageAccessMixin, "Centros de gasto: cambiar",
         roles(m.FleetManageAccessMixin), False),
        (m.FleetAccessMixin, "Centros de gasto: ver",
         roles(m.FleetAccessMixin), False),
        (m.AdminRoleRequiredMixin, "Administradores",
         roles(m.AdminRoleRequiredMixin), False),
        (AdminOnlyMixin, "Solo el rol Administrador",
         lambda cu: cu.role == CompanyUser.ROLE_ADMIN, False),
        (m.WorkshopRequiredMixin, "Taller", roles(m.WorkshopRequiredMixin),
         False),
        (m.WorkOrderFormAccessMixin, "Formulario de partes",
         roles(m.WorkOrderFormAccessMixin), False),
        (m.SupervisorAccessMixin, "Supervisión",
         roles(m.SupervisorAccessMixin), False),
        (m.DocsUploadAccessMixin, "Subir documentación",
         roles(m.DocsUploadAccessMixin), False),
        (m.AssistanceSupervisorAccessMixin, "Supervisión de asistencia",
         roles(m.AssistanceSupervisorAccessMixin), False),
        (m.BaseCalendarAccessMixin, "Bases y calendarios",
         roles(m.BaseCalendarAccessMixin), False),
        (m.AssistanceWorkOrderAccessMixin, "Órdenes de asistencia",
         roles(m.AssistanceWorkOrderAccessMixin), False),
        (m.AssistanceAlbaranAccessMixin,
         "Albaranes de asistencia (y su conductor)",
         roles(m.AssistanceAlbaranAccessMixin), False),
        (m.AssistanceRequiredMixin, "Asistencia",
         roles(m.AssistanceRequiredMixin), False),
        (m.BudgetAuditAccessMixin, "Historial de presupuestos",
         budget_audit, True),
        (CatalogReadAccessMixin, "Catálogo de repuestos",
         roles(CatalogReadAccessMixin, "_allowed_roles"), False),
        (CaeAccessMixin, "Correos CAE", can_use_cae, False),
        (CraneAccessMixin, "Grúas", can_access, False),
        (_ServiceEditMixin, "Anotar revisiones", can_edit_service, False),
        (SignatureAccessMixin, "Firmas (acceso propio)",
         can_use_signatures, True),
        (InsuranceAccessMixin, "Seguros (acceso propio)",
         can_use_insurance, True),
        (PayslipAccessMixin, "Nóminas (quien sube o se le comparten)",
         can_send_payslips, True),
        (ExplorerAccessMixin, "Explorador (según sus carpetas)",
         lambda cu: bool(readable_buckets(cu)), True),
        (m.CompanyUserRequiredMixin, "Cualquier usuario del panel",
         lambda cu: True, False),
    ]


def _walk(patterns, prefix=""):
    from django.urls import URLResolver

    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns,
                             prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern


_SCREENS = None


def panel_screens():
    """
    [(area key, area label, tab, rule index, route)] of the panel.

    ---

    Las pantallas del panel actual (rutas /panel/, sin la nueva
    interfaz), con su área y la puerta que las guarda. Se calcula una
    vez por proceso: las rutas solo cambian al desplegar.
    """
    global _SCREENS
    if _SCREENS is not None:
        return _SCREENS
    from django.urls import get_resolver

    from panel.mixins import CompanyUserRequiredMixin

    rules = _rules()
    screens, seen = [], set()
    for route, pattern in _walk(get_resolver().url_patterns):
        cls = getattr(pattern.callback, "view_class", None)
        if (not route.startswith("panel/") or cls is None
                or route.startswith("panel/nueva-interfaz/")
                or not issubclass(cls, CompanyUserRequiredMixin)
                or route in seen):
            continue
        seen.add(route)
        area = _area_of(route)
        if area is None:
            continue
        index = next(i for i, rule in enumerate(rules)
                     if issubclass(cls, rule[0]))
        screens.append(area + (index, route))
    _SCREENS = (rules, screens)
    return _SCREENS


def _passes(check, company_user):
    try:
        return bool(check(company_user))
    except Exception:  # noqa: BLE001 -- un fallo no da acceso
        return False


def panel_areas(company_user):
    """
    {area key: {...}} of what this user can enter in the current panel.

    ---

    Por área del panel actual: cuántas pantallas tiene, a cuántas entra
    este usuario, qué puertas las guardan, si alguna depende de la
    persona y si la pestaña de Documentación se le oculta.
    """
    rules, screens = panel_screens()
    ok = [_passes(rule[2], company_user) for rule in rules]
    menu = menu_areas(company_user)
    try:
        tabs = set(documentation_tabs(company_user))
    except Exception:  # noqa: BLE001
        tabs = set()
    areas = {}
    for key, label, tab, index, _route in screens:
        area = areas.setdefault(key, {
            "key": key, "label": label, "total": 0, "allowed": 0,
            "rules": [], "per_person": False,
            "hidden_tab": bool(tab) and tab not in tabs,
            "in_menu": key in menu or (
                key.startswith("doc:") and "doc:general" in menu
                and (not tab or tab in tabs)),
        })
        area["total"] += 1
        area["allowed"] += 1 if ok[index] else 0
        if rules[index][1] not in area["rules"]:
            area["rules"].append(rules[index][1])
        area["per_person"] = area["per_person"] or rules[index][3]
    for area in areas.values():
        area["rank"] = (2 if area["allowed"] == area["total"]
                        else 1 if area["allowed"] else 0)
    return areas


def role_stand_in(company, role):
    """
    An unsaved CompanyUser with only this role, to ask the rules.

    ---

    Un CompanyUser sin guardar, solo con el rol, para preguntar a las
    reglas qué deja el rol por sí mismo (sin accesos propios).
    """
    from django.contrib.auth.models import User

    # pk 0: las consultas de las reglas (nóminas compartidas, carpetas
    # del Explorador) no encuentran nada en vez de fallar por objeto sin
    # guardar. Nunca se guarda.
    stand_in = CompanyUser(pk=0, company=company, role=role,
                           is_active=True)
    stand_in.user = User(pk=0, username="", is_superuser=False)
    return stand_in


def menu_areas(company_user):
    """
    Area keys linked from this user's sidebar menu.

    ---

    Áreas a las que lleva el menú lateral de este usuario: se pinta el
    propio menú (_nav_items.html) como lo vería él y se miran sus
    enlaces, así no hay una segunda lista que mantener.
    """
    import re
    from types import SimpleNamespace

    from django.template.loader import render_to_string
    from django.urls import Resolver404, resolve, reverse

    try:
        html = render_to_string("panel/_nav_items.html", {
            "company_user": company_user,
            "request": SimpleNamespace(user=company_user.user, path="/"),
            "documentation_hub_href": reverse("panel:documentation_hub"),
        })
    except Exception:  # noqa: BLE001
        return set()
    keys = set()
    for href in re.findall(r'href="(/[^"#?]*)', html):
        try:
            route = resolve(href).route
        except Resolver404:
            continue
        if not route.startswith("panel/"):
            continue
        area = _area_of(route)
        if area is not None:
            keys.add(area[0])
    return keys
