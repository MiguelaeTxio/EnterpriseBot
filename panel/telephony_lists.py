# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/telephony_lists.py
"""
Telephony and Sections lists with the panel's single list format (S155).
---
Listados de Telefonía (Secciones en la centralita, Flujos IVR, Conjuntos
de captura, Números de teléfono, Bloqueados) y de Administración →
Secciones con el formato único del panel (directrices 4.24 y 4.27):
panel fijo con Buscar y filtrar y Acciones («N seleccionados · Limpiar ·
Solo los filtrados» y las propias), lista con orden múltiple y casillas,
visor «Selección actual», menú de tres puntos por fila, pantalla
completa y navegación persistida por usuario. Miguel Ángel (S155):
"falta que las vistas antiguas se adhieran al nuevo formato [...]
filtros, grupos de selección y acciones, todo adaptado a las
funcionalidades de las vistas y con la misma filosofía de scrolls".
Los grupos de selección son de personas o máquinas: estos listados no
los llevan, como Copias de seguridad.

Una sola pieza para los seis (4.27): cada listado es un ListSpec con
sus columnas, filtros de casillas, filas y acciones; las vistas, la
plantilla (panel/telephony_lists/) y el script
(panel/static/panel/js/telephony_list.js) son comunes.
"""

from urllib.parse import quote

from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View

from ivr_config.models import (
    BlockedCaller,
    CallFlow,
    CompanyUser,
    DataCaptureSet,
    PhoneNumber,
    Section,
)
from panel.machine_workshop import parse_sort, sort_controls
from panel.mixins import AdminRoleRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)


class Row:
    """
    One row of a list.
    ---
    Una fila: pk, etiqueta (para la selección), celdas en el orden de las
    columnas, códigos de cada filtro de casillas, texto de búsqueda,
    valores de orden y menú de tres puntos [(texto, url, icono)].
    """

    def __init__(self, pk, label, cells, groups, search, sort, menu=()):
        self.pk = pk
        self.label = label
        self.cells = cells
        self.groups = groups
        self.search = search.lower()
        self.sort = sort
        self.menu = list(menu)


def cell(text, badge=None, notes=(), muted=False, center=False):
    """
    One cell: text, optional badge ("active"/"inactive") and notes.
    ---
    Una celda: texto, insignia opcional y líneas de aviso debajo.
    """
    return {"text": text, "badge": badge, "notes": list(notes),
            "muted": muted, "center": center}


class ListSpec:
    """
    Definition of one list.
    ---
    Definición de un listado. `groups`: filtros de casillas
    [(nombre, título, [(código, texto)], códigos por defecto)].
    `actions`: [(código, texto, icono, estilo, explicación, pregunta)],
    resueltas por `run_action(request, company, ids, code)`. `create`:
    (texto, nombre de url) del alta, que va en el panel de acciones.
    """

    slug = ""
    title = ""
    prefix = ""
    nav = ""
    noun = "elemento(s)"
    search_placeholder = "Buscar…"
    intro = ""
    columns = ()
    groups = ()
    actions = ()
    create = None
    default_sort = ()

    def rows(self, company):
        raise NotImplementedError

    def run_action(self, request, company, ids, code):
        return "Acción desconocida.", True

    @property
    def screen_key(self):
        return f"telephony_list_{self.slug}"

    @property
    def filter_keys(self):
        return ("search", "sort") + tuple(g[0] for g in self.groups)


# ---------------------------------------------------------------------------
# The six lists / Los seis listados
# ---------------------------------------------------------------------------

def _active_badge(active, yes="Activa", no="Inactiva"):
    return cell(yes if active else no,
                badge="active" if active else "inactive", center=True)


def _set_active(model_qs, ids, value, noun_one, noun_many):
    """
    Saves is_active one by one (signals run) and returns the message.
    ---
    Guarda is_active uno a uno (para que corran las señales) y devuelve
    el mensaje del aviso.
    """
    changed = 0
    for obj in model_qs.filter(pk__in=ids):
        if obj.is_active != value:
            obj.is_active = value
            obj.save()
            changed += 1
    state = "activado" if value else "desactivado"
    return f"{changed} {noun_one if changed == 1 else noun_many} " \
           f"{state}(s).", False


class IvrSectionsSpec(ListSpec):
    """
    Telephony → Sections in the switchboard.
    ---
    Telefonía → Secciones en la centralita.
    """

    slug = "ivr_sections"
    title = "Secciones en la centralita"
    prefix = "ivs"
    nav = "ivr_sections"
    noun = "sección(es)"
    search_placeholder = "Buscar por sección, descripción o contacto…"
    intro = ("Qué secciones ofrece la centralita y cómo las atiende. Lo que "
             "define cada sección está en Administración → Secciones.")
    columns = (
        ("name", "Sección"),
        ("ivr", "Centralita"),
        ("breakdown", "Averías"),
        ("capture", "Captura de datos"),
        ("hours", "Horario de atención"),
        ("contacts", "Contactos con teléfono"),
    )
    groups = (
        ("state", "Estado", [("active", "Activas"),
                             ("inactive", "Inactivas")], ["active",
                                                          "inactive"]),
        ("ivr", "Centralita", [("yes", "La ofrece"),
                               ("no", "No la ofrece")], ["yes", "no"]),
    )
    actions = (
        ("offer", "Ofrecer en la centralita", "bi-telephone-plus",
         "outline-success",
         "Marca la casilla de la centralita en las secciones marcadas "
         "(hace falta además que estén activas).",
         "Ofrecer en la centralita"),
        ("withdraw", "Quitar de la centralita", "bi-telephone-x",
         "outline-secondary",
         "Desmarca la casilla de la centralita: deja de ofrecerlas.",
         "Quitar de la centralita"),
    )

    def rows(self, company):
        from panel.views_ivr_telephony import section_ivr_status

        sections = (
            Section.objects.filter(company=company)
            .select_related("call_flow", "data_capture_set",
                            "attention_schedule")
            .prefetch_related("schedules")
        )
        rows = []
        for s in sections:
            status = section_ivr_status(s)
            names = " ".join(sc.contact.name for sc in status["contacts"])
            rows.append(Row(
                s.pk, s.name,
                [
                    cell(s.name, notes=[] if s.is_active else ["Inactiva"]),
                    cell("Sí" if status["in_ivr"] else "No",
                         badge="active" if status["in_ivr"] else "inactive",
                         notes=status["reasons"] + status["warnings"]),
                    cell("Sí" if s.ivr_breakdown_enabled else "—",
                         center=True),
                    cell(s.data_capture_set.name if s.data_capture_set_id
                         else "—"),
                    cell(status["hours"]),
                    cell(str(status["contacts_with_phone"]), center=True),
                ],
                {"state": "active" if s.is_active else "inactive",
                 "ivr": "yes" if status["in_ivr"] else "no"},
                f"{s.name} {s.description} {names}",
                {"name": s.name.upper(), "ivr": status["in_ivr"],
                 "breakdown": s.ivr_breakdown_enabled,
                 "capture": (s.data_capture_set.name.upper()
                             if s.data_capture_set_id else None),
                 "hours": status["hours"].upper(),
                 "contacts": status["contacts_with_phone"]},
                [("Configurar", reverse("panel:ivr_section_edit",
                                        args=[s.pk]), "bi-telephone"),
                 ("Ficha de la sección", reverse("panel:section_edit",
                                                 args=[s.pk]),
                  "bi-diagram-3")],
            ))
        return rows

    def run_action(self, request, company, ids, code):
        if code not in ("offer", "withdraw"):
            return "Acción desconocida.", True
        value = code == "offer"
        changed = 0
        for s in Section.objects.filter(company=company, pk__in=ids):
            if s.ivr_transfer_enabled != value:
                s.ivr_transfer_enabled = value
                s.save()
                changed += 1
        verb = "ofrecida(s)" if value else "quitada(s)"
        return f"{changed} sección(es) {verb} en la centralita.", False


class SectionsSpec(ListSpec):
    """
    Administration → Sections.
    ---
    Administración → Secciones.
    """

    slug = "sections"
    title = "Secciones"
    prefix = "sec"
    nav = "sections"
    noun = "sección(es)"
    search_placeholder = "Buscar por nombre o descripción…"
    columns = (
        ("name", "Nombre"),
        ("description", "Descripción"),
        ("contacts", "Contactos"),
        ("workers", "Trabajadores"),
        ("ivr", "Centralita"),
        ("state", "Estado"),
    )
    groups = (
        ("state", "Estado", [("active", "Activas"),
                             ("inactive", "Inactivas")], ["active",
                                                          "inactive"]),
    )
    actions = (
        ("activate", "Activar", "bi-check-circle", "outline-success",
         "Activa las secciones marcadas.", "Activar"),
        ("deactivate", "Desactivar", "bi-slash-circle", "outline-secondary",
         "Desactiva las secciones marcadas (no aparecen en el dashboard ni "
         "en la centralita).", "Desactivar"),
    )
    create = ("Nueva sección", "panel:section_create")

    def rows(self, company):
        from panel.views_ivr_telephony import section_ivr_status

        workers = Q(contacts__company_user__role__in=list(
            CompanyUser.WORKER_ROLES))
        sections = (
            Section.objects.filter(company=company)
            .select_related("call_flow", "attention_schedule")
            .prefetch_related("schedules")
            .annotate(
                ivr_contacts=Count("contacts", filter=~workers,
                                   distinct=True),
                n_workers=Count("contacts", filter=workers, distinct=True),
            )
        )
        rows = []
        for s in sections:
            in_ivr = section_ivr_status(s)["in_ivr"]
            rows.append(Row(
                s.pk, s.name,
                [
                    cell(s.name),
                    cell(s.description or "—", muted=True),
                    cell(str(s.ivr_contacts), center=True),
                    cell(str(s.n_workers), center=True),
                    cell("Sí" if in_ivr else "No",
                         badge="active" if in_ivr else "inactive"),
                    _active_badge(s.is_active),
                ],
                {"state": "active" if s.is_active else "inactive"},
                f"{s.name} {s.description}",
                {"name": s.name.upper(),
                 "description": (s.description or "").upper() or None,
                 "contacts": s.ivr_contacts, "workers": s.n_workers,
                 "ivr": in_ivr, "state": s.is_active},
                [("Editar", reverse("panel:section_edit", args=[s.pk]),
                  "bi-pencil"),
                 ("Centralita", reverse("panel:ivr_section_edit",
                                        args=[s.pk]), "bi-telephone")],
            ))
        return rows

    def run_action(self, request, company, ids, code):
        if code not in ("activate", "deactivate"):
            return "Acción desconocida.", True
        return _set_active(Section.objects.filter(company=company), ids,
                           code == "activate", "sección", "secciones")


class CallFlowsSpec(ListSpec):
    """
    Telephony → IVR flows.
    ---
    Telefonía → Flujos IVR.
    """

    slug = "callflows"
    title = "Flujos IVR"
    prefix = "cfl"
    nav = "callflows"
    noun = "flujo(s)"
    search_placeholder = "Buscar por nombre, saludo o sección…"
    intro = ("El flujo de cada sección se regenera solo al guardar la "
             "sección; la recepción principal se edita aquí.")
    columns = (
        ("name", "Nombre"),
        ("used_by", "Lo usa"),
        ("greeting", "Saludo inicial"),
        ("state", "Estado"),
    )
    groups = (
        ("state", "Estado", [("active", "Activos"),
                             ("inactive", "Inactivos")], ["active",
                                                          "inactive"]),
    )
    actions = (
        ("activate", "Activar", "bi-check-circle", "outline-success",
         "Activa los flujos marcados.", "Activar"),
        ("deactivate", "Desactivar", "bi-slash-circle", "outline-secondary",
         "Desactiva los flujos marcados: su sección sale de la centralita.",
         "Desactivar"),
    )
    create = ("Nuevo flujo IVR", "panel:callflow_create")

    def rows(self, company):
        flows = CallFlow.objects.filter(company=company).prefetch_related(
            "sections", "phone_numbers")
        rows = []
        for f in flows:
            users = ([f"Sección {s.name}" for s in f.sections.all()]
                     + [f"Número {p.number}" for p in f.phone_numbers.all()])
            used = ", ".join(users) or "—"
            rows.append(Row(
                f.pk, f.name,
                [cell(f.name), cell(used, muted=not users),
                 cell((f.initial_greeting or "—")[:90], muted=True),
                 _active_badge(f.is_active, "Activo", "Inactivo")],
                {"state": "active" if f.is_active else "inactive"},
                f"{f.name} {f.initial_greeting} {used}",
                {"name": f.name.upper(), "used_by": used.upper(),
                 "greeting": (f.initial_greeting or "").upper() or None,
                 "state": f.is_active},
                [("Editar", reverse("panel:callflow_edit", args=[f.pk]),
                  "bi-pencil")],
            ))
        return rows

    def run_action(self, request, company, ids, code):
        if code not in ("activate", "deactivate"):
            return "Acción desconocida.", True
        return _set_active(CallFlow.objects.filter(company=company), ids,
                           code == "activate", "flujo", "flujos")


class CaptureSetsSpec(ListSpec):
    """
    Telephony → Data capture sets.
    ---
    Telefonía → Conjuntos de captura.
    """

    slug = "datacapturesets"
    title = "Conjuntos de captura"
    prefix = "dcs"
    nav = "datacapturesets"
    noun = "conjunto(s)"
    search_placeholder = "Buscar por nombre, campo o sección…"
    intro = ("Datos que Alia pide a quien llama antes de pasarle la "
             "llamada. Cada sección elige el suyo en Secciones en la "
             "centralita.")
    columns = (
        ("name", "Nombre"),
        ("fields", "Campos"),
        ("sections", "Secciones que lo usan"),
    )
    groups = (
        ("use", "Uso", [("used", "En uso"), ("unused", "Sin usar")],
         ["used", "unused"]),
    )
    create = ("Nuevo conjunto", "panel:datacaptureset_create")

    def rows(self, company):
        sets = DataCaptureSet.objects.filter(
            company=company).prefetch_related("sections")
        rows = []
        for d in sets:
            labels = [f.get("label") or f.get("key") or ""
                      for f in (d.fields or []) if isinstance(f, dict)]
            sections = [s.name for s in d.sections.all()]
            rows.append(Row(
                d.pk, d.name,
                [cell(d.name),
                 cell(", ".join(labels) or "—", muted=not labels),
                 cell(", ".join(sections) or "—", muted=not sections)],
                {"use": "used" if sections else "unused"},
                f"{d.name} {' '.join(labels)} {' '.join(sections)}",
                {"name": d.name.upper(), "fields": len(labels),
                 "sections": ", ".join(sections).upper() or None},
                [("Editar", reverse("panel:datacaptureset_edit",
                                    args=[d.pk]), "bi-pencil")],
            ))
        return rows


class PhoneNumbersSpec(ListSpec):
    """
    Telephony → Phone numbers.
    ---
    Telefonía → Números de teléfono.
    """

    slug = "phonenumbers"
    title = "Números de teléfono"
    prefix = "phn"
    nav = "phonenumbers"
    noun = "número(s)"
    search_placeholder = "Buscar por número, nombre o flujo…"
    columns = (
        ("number", "Número"),
        ("friendly", "Nombre"),
        ("flow", "Flujo IVR"),
        ("capabilities", "Capacidades"),
        ("state", "Estado"),
    )
    groups = (
        ("state", "Estado", [("active", "Activos"),
                             ("inactive", "Inactivos")], ["active",
                                                          "inactive"]),
    )

    def rows(self, company):
        numbers = PhoneNumber.objects.filter(
            company=company).select_related("call_flow")
        rows = []
        for n in numbers:
            flow = n.call_flow.name if n.call_flow_id else "—"
            rows.append(Row(
                n.pk, n.number,
                [cell(n.number), cell(n.friendly_name or "—"),
                 cell(flow, muted=not n.call_flow_id),
                 cell(n.capabilities or "—", muted=True),
                 _active_badge(n.is_active, "Activo", "Inactivo")],
                {"state": "active" if n.is_active else "inactive"},
                f"{n.number} {n.friendly_name} {flow}",
                {"number": n.number, "friendly": (n.friendly_name or
                                                  "").upper() or None,
                 "flow": flow.upper() if n.call_flow_id else None,
                 "capabilities": n.capabilities or None,
                 "state": n.is_active},
                [("Ver su flujo", reverse("panel:callflow_edit",
                                          args=[n.call_flow_id]),
                  "bi-gear-wide-connected")] if n.call_flow_id else [],
            ))
        return rows


class BlockedCallersSpec(ListSpec):
    """
    Telephony → Blocked callers.
    ---
    Telefonía → Bloqueados. Los expirados siguen en la lista (directriz
    4.24, punto 8), filtrables por Estado.
    """

    slug = "blockedcallers"
    title = "Llamantes bloqueados"
    prefix = "blk"
    nav = "blockedcallers"
    noun = "número(s)"
    search_placeholder = "Buscar por número, motivo o quién lo bloqueó…"
    columns = (
        ("number", "Número"),
        ("reason", "Motivo"),
        ("by", "Bloqueado por"),
        ("at", "Bloqueado el"),
        ("until", "Expira"),
        ("state", "Estado"),
    )
    groups = (
        ("state", "Estado", [("active", "Activos"),
                             ("expired", "Expirados")], ["active"]),
    )
    actions = (
        ("unblock", "Desbloquear", "bi-unlock", "outline-danger",
         "Borra el bloqueo de los números marcados: vuelven a poder llamar.",
         "Desbloquear"),
    )
    create = ("Bloquear número", "panel:blockedcaller_create")
    default_sort = (("at", True),)

    def rows(self, company):
        now = timezone.now()
        blocks = BlockedCaller.objects.filter(
            company=company).select_related("blocked_by")
        rows = []
        for b in blocks:
            active = b.blocked_until is not None and b.blocked_until > now
            by = b.blocked_by.username if b.blocked_by_id else "Sistema"
            at = timezone.localtime(b.blocked_at) if b.blocked_at else None
            until = (timezone.localtime(b.blocked_until)
                     if b.blocked_until else None)
            rows.append(Row(
                b.pk, b.phone_number,
                [cell(b.phone_number), cell(b.reason or "—", muted=True),
                 cell(by), cell(f"{at:%d/%m/%Y %H:%M}" if at else "—"),
                 cell(f"{until:%d/%m/%Y %H:%M}" if until else "—"),
                 _active_badge(active, "Activo", "Expirado")],
                {"state": "active" if active else "expired"},
                f"{b.phone_number} {b.reason} {by}",
                {"number": b.phone_number,
                 "reason": (b.reason or "").upper() or None,
                 "by": by.upper(), "at": at, "until": until,
                 "state": active},
                [("Desbloquear", reverse("panel:blockedcaller_delete",
                                         args=[b.pk]), "bi-unlock")],
            ))
        return rows

    def run_action(self, request, company, ids, code):
        if code != "unblock":
            return "Acción desconocida.", True
        deleted, _detail = BlockedCaller.objects.filter(
            company=company, pk__in=ids).delete()
        return f"{deleted} número(s) desbloqueado(s).", False


SPECS = {spec.slug: spec for spec in (
    IvrSectionsSpec(), SectionsSpec(), CallFlowsSpec(), CaptureSetsSpec(),
    PhoneNumbersSpec(), BlockedCallersSpec(),
)}


# ---------------------------------------------------------------------------
# Common views / Vistas comunes
# ---------------------------------------------------------------------------

def _param(request, key):
    """
    GET value, or the _f_ copy posted by the mass actions.
    ---
    Valor GET, o la copia _f_ que mandan las acciones masivas.
    """
    return request.GET.get(key, request.POST.get(f"_f_{key}", "")) or ""


def _list_context(request, spec):
    """
    Rows filtered and sorted, with the filter and sort state.
    ---
    Filas filtradas y ordenadas, con el estado de filtros y orden. Las
    casillas de un filtro: "" = todas, "none" = ninguna, si no, las
    marcadas separadas por comas (semántica literal).
    """
    company = request.user.company_user.company
    rows = spec.rows(company)
    selected_ids = {pk for pk in _param(request, "selected_ids").split(",")
                    if pk.isdigit()}
    group_state = []
    if _param(request, "only_selected") == "1":
        rows = [r for r in rows if str(r.pk) in selected_ids]
    else:
        for name, title, options, default in spec.groups:
            raw = request.GET.get(name, request.POST.get(f"_f_{name}"))
            if raw is None:
                wanted = list(default)
            elif raw == "none":
                wanted = []
            elif raw == "":
                wanted = [code for code, _label in options]
            else:
                wanted = raw.split(",")
            rows = [r for r in rows if r.groups.get(name) in wanted]
            group_state.append({
                "name": name, "title": title, "wanted": wanted,
                "options": options,
                "value": ("" if len(wanted) == len(options)
                          else ",".join(wanted) or "none"),
            })
        for word in _param(request, "search").lower().split():
            rows = [r for r in rows if word in r.search]
    sortable = {key: key for key, _label in spec.columns}
    keys = parse_sort(_param(request, "sort"), sortable) or list(
        spec.default_sort)
    rows.sort(key=lambda r: r.label.upper())
    for key, desc in reversed(keys):
        present = [r for r in rows if r.sort.get(key) is not None]
        missing = [r for r in rows if r.sort.get(key) is None]
        present.sort(key=lambda r: r.sort[key], reverse=desc)
        rows = present + missing
    controls = sort_controls(_param(request, "sort"), sortable)
    return {
        "spec": spec,
        "rows": rows,
        "columns": [
            {"key": key, "label": label, **controls["sort_cols"][key]}
            for key, label in spec.columns
        ],
        "sort_active": controls["sort_active"],
        "current_sort": controls["current_sort"],
        "filter_search": _param(request, "search"),
        "group_state": group_state,
        "results_url": reverse("panel:telephony_list_results",
                               args=[spec.slug]),
    }


def _spec(slug):
    spec = SPECS.get(slug)
    if spec is None:
        raise Http404
    return spec


class TelephonyListPageView(AdminRoleRequiredMixin, View):
    """
    GET: the list page (fixed panel, list, current selection).
    ---
    GET: la página del listado (panel fijo, lista y selección actual).
    """

    slug = ""

    def get(self, request):
        spec = _spec(self.slug)
        apply_list_navigation(request, spec.screen_key, spec.filter_keys)
        saved = get_saved_state_key(
            request.user.company_user, spec.screen_key, "selection", [])
        return render(request, "panel/telephony_lists/page.html", {
            **_list_context(request, spec),
            "company": request.user.company_user.company,
            "company_user": request.user.company_user,
            "active_nav": spec.nav,
            "saved_selection": saved if isinstance(saved, list) else [],
            "action_url": reverse("panel:telephony_list_action",
                                  args=[spec.slug]),
            "create_url": reverse(spec.create[1]) if spec.create else "",
        })


class TelephonyListResultsView(AdminRoleRequiredMixin, View):
    """
    GET: table only (filters and sort).
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request, slug):
        spec = _spec(slug)
        apply_list_navigation(request, spec.screen_key, spec.filter_keys)
        return render(request, "panel/telephony_lists/_table.html",
                      _list_context(request, spec))


class TelephonyListActionView(AdminRoleRequiredMixin, View):
    """
    POST: mass action on the marked rows; returns the table.
    ---
    POST: acción masiva sobre los marcados; devuelve la tabla con los
    filtros que se veían y el aviso en X-List-Message.
    """

    def post(self, request, slug):
        spec = _spec(slug)
        company = request.user.company_user.company
        ids = [int(pk) for pk in request.POST.getlist("selected")
               if pk.isdigit()]
        if not ids:
            message, error = "No hay nada marcado.", True
        else:
            message, error = spec.run_action(
                request, company, ids, request.POST.get("action", ""))
        response = HttpResponse(render_to_string(
            "panel/telephony_lists/_table.html",
            _list_context(request, spec), request=request))
        response["X-List-Message"] = quote(message)
        if error:
            response["X-List-Error"] = "1"
        return response
