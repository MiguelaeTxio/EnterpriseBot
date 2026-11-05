# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_users_list.py
"""
Administration > Users with the panel's single list format (H24, S145).

---

Administración > Usuarios con el formato único de listados del panel
(H24, S145, directriz 4.24). Miguel Ángel: "cuando empezamos había 5 o
6 usuarios, pero esto cada vez hay más. Y ya urge la necesidad de meter
filtros por horario, por esto, por lo otro, casi como lo que tenemos en
personal [...] vamos a gestionar las cosas que tengan que ver con lo
que se está gestionando ahora mismo en usuarios, solo que con filtros y
con el tipo de interfaz que [...] estamos usando últimamente."

Panel fijo (buscar y filtrar: texto, Estado, Rol, Sección, Horario,
Base, Alta en el fichaje -- la de Personal, S145 --, Selección;
acciones masivas: activar, desactivar, rol, base,
eliminar, nuevo usuario), lista con orden múltiple, selección
persistida y visor "Selección actual". Lo de cada usuario se sigue
editando en su formulario de siempre (menú de tres puntos). La sección
es la vigente hoy de su ficha de Personal y el horario, el que le toca
(como en Horarios). Filtros, orden y selección persistidos por usuario
(screen_key "users_list").
"""
from urllib.parse import quote

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from ivr_config.models import CompanyUser
from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

SCREEN_KEY = "users_list"
FILTER_KEYS = (
    "search", "active", "role", "section", "schedule", "base",
    "onboarding", "sort",
)
# S145: "Alta en el fichaje" como en Personal, más los usuarios sin
# ficha de Personal (administradores, cuentas de prueba).
NO_CARD = "no_card"
NONE_VALUE = "none"
_MAX_SORT_KEYS = 4

_SORT_VALUES = {
    "username": lambda r: r.username.upper(),
    "name": lambda r: r.sort_name or None,
    "role": lambda r: r.role_label.upper(),
    "status": lambda r: r.status_label,
    "section": lambda r: r.section_name.upper() or None,
    "schedule": lambda r: r.schedule.label.upper() if r.schedule else None,
    "base": lambda r: r.base_name.upper() or None,
    "onboarding": lambda r: r.onboarding_rank,
    "phone": lambda r: r.phone or None,
    "last_login": lambda r: r.last_login,
}
_COLUMNS = (
    ("username", "Usuario"),
    ("name", "Apellidos, Nombre"),
    ("role", "Rol"),
    ("status", "Estado"),
    ("section", "Sección"),
    ("schedule", "Horario"),
    ("base", "Base"),
    ("onboarding", "Alta en el fichaje"),
    ("phone", "Teléfono"),
    ("last_login", "Último acceso"),
)


def _param(request, key, default=""):
    """
    GET value, or the _f_ copy posted by the mass actions.
    ---
    Valor de GET o, si no está, la copia _f_ que envían las acciones.
    """
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _csv(request, key):
    return [v for v in _param(request, key).split(",") if v]


class _Row:
    """
    One panel user with what the list shows of them.
    ---
    Un usuario del panel con lo que enseña la lista.
    """

    def __init__(self, cu, person, section, schedule, onboarding):
        user = cu.user
        self.cu = cu
        self.person = person
        self.username = user.username
        full = ("%s, %s" % (user.last_name, user.first_name)).strip(", ")
        self.label = full or user.username
        self.sort_name = full.upper()
        self.role_label = cu.get_role_display()
        if cu.pending_onboarding:
            self.status, self.status_label = "pending", "Pendiente de alta"
        elif cu.is_active:
            self.status, self.status_label = "active", "Activo"
        else:
            self.status, self.status_label = "inactive", "Inactivo"
        self.section = section
        self.section_name = section.name if section is not None else ""
        self.schedule = schedule
        self.base_name = cu.base.name if cu.base_id else ""
        # Estado del alta en el fichaje (el de Personal) o "Sin ficha".
        self.onboarding = onboarding
        self.onboarding_code = onboarding.code if onboarding else NO_CARD
        self.onboarding_rank = onboarding.rank if onboarding else 99
        self.phone = cu.phone
        self.last_login = user.last_login


def _rows(company, users):
    """
    Rows with section in force today and the schedule that applies.
    ---
    Filas con la sección vigente hoy (la de su ficha de Personal) y el
    horario que le toca (el mismo cálculo que la pestaña Horarios).
    """
    from document_explorer.models import PersonIdentity
    from hr_calendar.clock_settings import worker_states
    from panel.personal_access import onboarding_states
    from panel.views_operator import (
        _resolve_base_schedule_with_origin,
        resolve_person_schedule,
    )

    people = {
        p.company_user_id: p for p in PersonIdentity.objects.filter(
            company_user__in=users,
        ).select_related("company_user__workday_schedule")
    }
    states = worker_states(list(people.values()))
    onboarding = onboarding_states(list(people.values()))
    rows = []
    for cu in users:
        person = people.get(cu.pk)
        if person is not None:
            schedule, _origin = resolve_person_schedule(person, company)
            section = states[person.pk].section
            state = onboarding[person.pk]
        else:
            schedule, _origin = _resolve_base_schedule_with_origin(
                cu, company)
            section = None
            state = None
        rows.append(_Row(cu, person, section, schedule, state))
    return rows


def _filtered_users(request, company):
    """
    Users matching search, Estado and Rol (database filters).
    ---
    Usuarios que cumplen la búsqueda (cada palabra en algún campo:
    usuario, nombre, apellidos, DNI, teléfono), Estado y Rol.
    """
    qs = CompanyUser.objects.filter(company=company).select_related(
        "user", "base", "workday_schedule",
    )
    active = _csv(request, "active")
    status = Q(pk__in=[])
    if "true" in active:
        status |= Q(is_active=True)
    if "false" in active:
        status |= Q(is_active=False)
    qs = qs.filter(status)
    roles = _param(request, "role")
    if roles == NONE_VALUE:
        qs = qs.none()
    elif roles:
        qs = qs.filter(role__in=roles.split(","))
    base = _param(request, "base")
    if base == NONE_VALUE:
        qs = qs.filter(base__isnull=True)
    elif base.isdigit():
        qs = qs.filter(base_id=int(base))
    for word in _param(request, "search").split():
        match = (
            Q(user__username__icontains=word)
            | Q(user__first_name__icontains=word)
            | Q(user__last_name__icontains=word)
            | Q(dni__icontains=word) | Q(phone__icontains=word)
        )
        qs = qs.filter(match)
    return list(qs)


def _with_filters(request, rows):
    """
    "Sección" and "Horario" filters, computed in Python like Horarios.
    ---
    Filtros "Sección" (vigente hoy, o "Sin sección") y "Horario" (el que
    le toca, o "Sin horario"), en Python como en Horarios.
    """
    section = _param(request, "section")
    if section == NONE_VALUE:
        rows = [r for r in rows if r.section is None]
    elif section.isdigit():
        rows = [r for r in rows
                if r.section is not None and r.section.pk == int(section)]
    schedule = _param(request, "schedule")
    if schedule == NONE_VALUE:
        rows = [r for r in rows if r.schedule is None]
    elif schedule.isdigit():
        rows = [r for r in rows
                if r.schedule is not None and r.schedule.pk == int(schedule)]
    # "" = todos, "none" = ninguno, si no, los estados marcados.
    onboarding = _param(request, "onboarding")
    if onboarding:
        wanted = set(onboarding.split(","))
        rows = [r for r in rows if r.onboarding_code in wanted]
    return rows


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: (r.sort_name, r.username.upper()))
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _sort_controls(raw):
    """
    Header links, arrows and priorities (same rules as Horarios).
    ---
    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Horarios y Fichajes).
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(
                ("-" if d else "") + k
                for k, d in new_keys[:_MAX_SORT_KEYS]
            ),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


def _list_context(request):
    """
    Context of the table: filtered users with section and schedule.
    ---
    Contexto de la tabla: usuarios filtrados con su sección y horario,
    ordenados. Por defecto, solo los activos.
    """
    company = request.user.company_user.company
    if not _param(request, "active"):
        request.GET = request.GET.copy()
        request.GET["active"] = "true"
    only_selected = (request.GET.get("only_selected")
                     or request.POST.get("_f_only_selected")) == "1"
    if only_selected:
        wanted = [
            int(pk) for pk in (
                request.GET.get("selected_ids")
                or request.POST.get("_f_selected_ids", "")
            ).split(",") if pk.isdigit()
        ]
        users = list(CompanyUser.objects.filter(
            company=company, pk__in=wanted,
        ).select_related("user", "base", "workday_schedule"))
        rows = _rows(company, users)
    else:
        rows = _with_filters(
            request, _rows(company, _filtered_users(request, company)))
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "rows": rows,
        "own_pk": request.user.company_user.pk,
        "filter_search": _param(request, "search"),
        "filter_active": _csv(request, "active"),
        "filter_role": _param(request, "role"),
        "filter_section": _param(request, "section"),
        "filter_schedule": _param(request, "schedule"),
        "filter_base": _param(request, "base"),
        "filter_onboarding": _param(request, "onboarding"),
        **_sort_controls(_param(request, "sort")),
    }


def _choices(company):
    from budgets.models import Base
    from panel.personal_access import ONBOARDING_CHOICES
    from panel.views_worker_schedules import _schedules, _sections

    return {
        "role_choices": CompanyUser.ROLE_CHOICES,
        "sections": _sections(company),
        "schedules": _schedules(company),
        "bases": list(Base.objects.filter(company=company).order_by("name")),
        "none_value": NONE_VALUE,
        "onboarding_choices": ONBOARDING_CHOICES + (
            (NO_CARD, "Sin ficha de Personal"),),
    }


class UserListPageView(SupervisorAccessMixin, View):
    """
    GET: Users page (fixed panel, list, selection).
    ---
    GET: página Usuarios (panel fijo, listado y selección actual).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        company = request.user.company_user.company
        return render(request, "panel/users/list.html", {
            **_list_context(request),
            **_choices(company),
            "company": company,
            "active_nav": "users",
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
        })


class UserListResultsView(SupervisorAccessMixin, View):
    """
    GET: table only (filters and sort).
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/users/_table.html",
                      _list_context(request))


def _table_response(request, message, error=False):
    """
    The table with the filters that were on screen, and a message.
    ---
    La tabla con los filtros que se veían y el mensaje del aviso.
    """
    response = HttpResponse(render_to_string(
        "panel/users/_table.html", _list_context(request), request=request,
    ))
    response["X-Users-Message"] = quote(message)
    if error:
        response["X-Users-Error"] = "1"
    return response


class UserListMassActionView(SupervisorAccessMixin, View):
    """
    POST: activate, deactivate, change role or base of the marked users.
    ---
    POST: activa, desactiva, cambia el rol o la base de los marcados.
    La propia cuenta nunca se desactiva ni cambia de rol (S130: un
    administrador no puede quitarse el acceso por error). Un pre-registro
    pendiente de alta no se activa desde aquí: lo activa el propio
    trabajador al darse de alta por WhatsApp.
    """

    def post(self, request):
        company = request.user.company_user.company
        own_pk = request.user.company_user.pk
        ids = [int(pk) for pk in request.POST.getlist("selected")
               if pk.isdigit()]
        users = list(CompanyUser.objects.filter(
            company=company, pk__in=ids,
        ).select_related("user"))
        if not users:
            return _table_response(request, "Marca algún usuario.",
                                   error=True)
        action = request.POST.get("action", "")
        skipped_own = any(cu.pk == own_pk for cu in users)
        if action in ("activate", "deactivate", "role"):
            users = [cu for cu in users if cu.pk != own_pk]
        if action == "activate":
            pending = [cu for cu in users if cu.pending_onboarding]
            users = [cu for cu in users if not cu.pending_onboarding]
            count = CompanyUser.objects.filter(
                pk__in=[cu.pk for cu in users]).update(is_active=True)
            message = "%d usuario(s) activado(s)." % count
            if pending:
                message += (" %d pendiente(s) de alta sin tocar: se "
                            "activan al darse de alta por WhatsApp."
                            % len(pending))
        elif action == "deactivate":
            count = CompanyUser.objects.filter(
                pk__in=[cu.pk for cu in users]).update(is_active=False)
            message = "%d usuario(s) desactivado(s)." % count
        elif action == "role":
            role = request.POST.get("role", "")
            labels = dict(CompanyUser.ROLE_CHOICES)
            if role not in labels:
                return _table_response(request, "Rol desconocido.",
                                       error=True)
            count = CompanyUser.objects.filter(
                pk__in=[cu.pk for cu in users]).update(role=role)
            message = "Rol %s puesto a %d usuario(s)." % (
                labels[role], count)
        elif action == "base":
            from budgets.models import Base

            raw = request.POST.get("base_id", "")
            base = None
            if raw:
                base = Base.objects.filter(
                    pk=raw if raw.isdigit() else 0, company=company,
                ).first()
                if base is None:
                    return _table_response(request, "No existe esa base.",
                                           error=True)
            count = CompanyUser.objects.filter(
                pk__in=[cu.pk for cu in users]).update(base=base)
            message = ("Base %s puesta a %d usuario(s)." % (base.name, count)
                       if base else "Base quitada a %d usuario(s)." % count)
        else:
            return _table_response(request, "Acción desconocida.",
                                   error=True)
        if skipped_own and action in ("activate", "deactivate", "role"):
            message += " Tu propia cuenta no se toca."
        return _table_response(request, message)
