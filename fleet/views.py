# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/views.py
"""
Views for the fleet application.
CRUD views for MachineAsset (cost centres) and the analytics report.
Extracted from panel/views.py as part of the fleet-app split (H12/H21).

panel/views.py re-exports all classes defined here so that panel/urls.py
requires no changes until the URL namespace is migrated to fleet.urls.

---

Vistas de la aplicación fleet.
Vistas CRUD para MachineAsset (centros de gasto) e informe de analítica.
Extraídas de panel/views.py como parte del split de la app fleet (H12/H21).

panel/views.py re-exporta todas las clases definidas aquí para que
panel/urls.py no necesite cambios hasta que el espacio de nombres de URL
se migre a fleet.urls.
"""

import csv
import datetime as dt

from django.db.models import Count, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.views import View

from document_explorer.machine_folder_service import sync_machine_documents
from fleet.forms import MachineAssetForm
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser, PresenceStatus
from panel.mixins import (
    AdminRoleRequiredMixin,
    DocsUploadAccessMixin,
    FleetAccessMixin,
    FleetManageAccessMixin,
    SupervisorAccessMixin,
)
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.person_groups import (
    MACHINE_KIND,
    collapsed_state,
    group_tree,
    parent_choices,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_own_presence(company_user):
    """
    Returns the current active PresenceStatus for the given company_user,
    or None if the user has no active presence record.

    ---

    Retorna el PresenceStatus activo actual del company_user dado,
    o None si el usuario no tiene registro de presencia activo.
    """
    return (
        PresenceStatus.objects
        .filter(company_user=company_user, starts_at__lte=now())
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now()))
        .order_by("-starts_at")
        .first()
    )


def _get_families(company):
    """
    Families offered in the list filter: only those with at least one
    active machine (S117, fleet.family_service.active_families).

    ---

    Familias que ofrece el filtro del listado: solo las que tienen al
    menos una máquina activa (S117, fleet.family_service.active_families).
    """
    from fleet.family_service import active_families

    return active_families(company)


# ---------------------------------------------------------------------------
# Multi-column sorting (S117) / Ordenación múltiple (S117)
# ---------------------------------------------------------------------------

_SORTABLE_FIELDS = {
    "code": "code",
    "family": "family",
    "brand_model": "brand_model",
    "type_name": "type_name",
    "plate": "plate",
    "is_active": "is_active",
    "use_count": "use_count",  # anotado en _build_fragment_context
    # recuento en Python, ver _build_fragment_context
    "doc_count": "doc_count",
    # H30 (S123), punto 6: ordenar por requisito de documentación.
    "requirement": "document_requirement__name",
}
_MAX_SORT_KEYS = 4


def _parse_sort_param(raw):
    """
    Parses "key,-key,..." (priority order) into [(key, descending)],
    ignoring invalid or repeated keys, capped at _MAX_SORT_KEYS.
    ---
    Interpreta "clave,-clave,..." (orden de prioridad) como
    [(clave, descendente)], ignorando claves inválidas o repetidas,
    con un máximo de _MAX_SORT_KEYS.
    """
    keys = []
    seen = set()
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        desc = token.startswith("-")
        key = token.lstrip("-")
        if key in _SORTABLE_FIELDS and key not in seen:
            keys.append((key, desc))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _build_sort_controls(raw):
    """
    Resolves, for every sortable column, the "sort" value a click on
    its header must send, its arrow and its priority number -- same
    rules as S116 (H10): clicking a column promotes it to primary
    criterion keeping the others as tie-breakers; clicking the one
    that is already primary flips its direction. Resolved here, never
    in the template (dumb templates).
    ---
    Resuelve, para cada columna ordenable, el valor de "sort" que debe
    enviar un clic en su cabecera, su flecha y su número de prioridad
    -- mismas reglas que S116 (H10): clic en una columna la promueve a
    criterio principal conservando las demás como desempate; clic en
    la que ya es principal invierte su sentido. Resuelto aquí, nunca
    en la plantilla (plantillas tontas).
    """
    sort_keys = _parse_sort_param(raw)
    active_keys = [key for key, _desc in sort_keys]
    sort_next = {}
    sort_arrows = {}
    sort_priority = {}
    for key in _SORTABLE_FIELDS:
        if key in active_keys:
            idx = active_keys.index(key)
            desc = sort_keys[idx][1]
            sort_arrows[key] = "down" if desc else "up"
            sort_priority[key] = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            sort_arrows[key] = ""
            sort_priority[key] = ""
            new_keys = [(key, False)] + sort_keys
        new_keys = new_keys[:_MAX_SORT_KEYS]
        sort_next[key] = ",".join(
            ("-" if d else "") + k for k, d in new_keys
        )
    current_sort = ",".join(
        ("-" if d else "") + k for k, d in sort_keys
    )
    return {
        "sort_next": sort_next,
        "sort_arrows": sort_arrows,
        "sort_priority": sort_priority,
        "sort_active": bool(sort_keys),
        "current_sort": current_sort,
    }


def _sort_assets_in_python(assets, sort_keys):
    """
    Sorts already-loaded assets by [(key, descending)] in priority
    order (stable sorts applied from the least to the most important
    key), with "code" as final tie-breaker -- same result as the
    database ordering of _build_queryset.
    ---
    Ordena activos ya cargados por [(clave, descendente)] en orden de
    prioridad (ordenaciones estables de la clave menos a la más
    importante), con "code" como último desempate -- mismo resultado
    que el orden en BD de _build_queryset.
    """
    def value(asset, key):
        if key == "requirement":
            requirement = asset.document_requirement
            raw = requirement.name if requirement else None
        else:
            raw = getattr(asset, key, None)
        if raw is None:
            return (1, "")
        if isinstance(raw, str):
            return (0, raw.upper())
        return (0, raw)

    assets = sorted(assets, key=lambda asset: value(asset, "code"))
    for key, desc in reversed(sort_keys):
        assets = sorted(
            assets, key=lambda asset, k=key: value(asset, k), reverse=desc,
        )
    return assets


def _fleet_permissions(company_user):
    """
    Permission flags for the template (dumb templates): who can
    create/edit/deactivate (ADMIN, DOCS_SUPERVISOR) and who can delete
    permanently (ADMIN only) -- same matrix as FleetManageAccessMixin
    and AdminRoleRequiredMixin.
    ---
    Flags de permiso para la plantilla (plantillas tontas): quién puede
    dar de alta/editar/dar de baja (ADMIN, DOCS_SUPERVISOR) y quién
    puede borrar definitivamente (solo ADMIN) -- misma matriz que
    FleetManageAccessMixin y AdminRoleRequiredMixin.
    """
    role = company_user.role
    return {
        "can_manage": role in FleetManageAccessMixin.allowed_roles,
        "can_delete": role in CompanyUser.ADMIN_ROLES,
    }


def _build_queryset(company, request):
    """
    Builds and returns the filtered MachineAsset queryset for the given
    company from GET parameters.

    Supported filters:
      family    — exact match (case-insensitive).
      is_active — '1' active only, '0' inactive only, '' all.
      search    — case-insensitive icontains on code, brand_model, plate,
                  type_name and company_name.

    ---

    Construye y devuelve el queryset filtrado de MachineAsset para la empresa
    dada desde los parámetros GET.

    Filtros soportados:
      family    — coincidencia exacta (insensible a mayúsculas).
      is_active — '1' solo activos, '0' solo inactivos, '' todos.
      search    — icontains sobre code, brand_model, plate, type_name y
                  company_name.
    """
    qs = (
        MachineAsset.objects
        .filter(company=company)
        # H30 (S118): foto de la máquina en su fila, sin una query
        # extra por fila.
        .select_related("avatar_document", "document_requirement")
        .order_by("company_code", "family", "code")
    )

    def _gp(key, default=""):
        """Read from GET first, fall back to POST (mutation requests)."""
        return request.GET.get(key) or request.POST.get(f"_f_{key}", default)

    # S117 -- "Mostrar solo la selección actual" (mismo criterio que la
    # pestaña Personal, S113): con la casilla marcada, el listado se
    # limita EXACTAMENTE a los pks seleccionados y se saltan Familia y
    # Estado (nunca se combinan, para no ocultar nada de la selección);
    # la búsqueda de texto sí sigue aplicando.
    selected_ids = [
        pk for pk in request.GET.get("selected_ids", "").split(",")
        if pk.isdigit()
    ]
    if request.GET.get("only_selected") == "1" and selected_ids:
        qs = qs.filter(pk__in=selected_ids)
    else:
        family_filter = _gp("family").strip()
        if family_filter:
            qs = qs.filter(family__iexact=family_filter)

        # H30 (S123): filtro por requisito de documentación, mismo
        # criterio que Personal ("" todos, "none" sin requisito, pk).
        requirement_filter = _gp("requirement").strip()
        if requirement_filter == "none":
            qs = qs.filter(document_requirement__isnull=True)
        elif requirement_filter.isdigit():
            qs = qs.filter(document_requirement_id=int(requirement_filter))

        # Estado en casillas (S117): "" ambas, "1" solo activos, "0"
        # solo inactivos, "none" ninguna marcada -> ningún resultado
        # (semántica literal de casilla, mismo criterio que Personal).
        active_filter = _gp("is_active")
        if active_filter == "1":
            qs = qs.filter(is_active=True)
        elif active_filter == "0":
            qs = qs.filter(is_active=False)
        elif active_filter == "none":
            qs = qs.none()

    search_filter = _gp("search").strip()
    if search_filter:
        qs = qs.filter(
            Q(code__icontains=search_filter)
            | Q(brand_model__icontains=search_filter)
            | Q(plate__icontains=search_filter)
            | Q(type_name__icontains=search_filter)
            | Q(company_name__icontains=search_filter)
        )

    # ------------------------------------------------------------------
    # Column sorting / Ordenación por columna
    # ------------------------------------------------------------------
    # S117: orden MÚLTIPLE con prioridad, mismo formato ya implantado en
    # S116 para Albaranes/Almacén/Catálogo ("sort=clave,-clave", en
    # orden de prioridad) -- ver _parse_sort_param() y
    # _build_sort_controls(). Sin orden explícito se mantiene el
    # order_by inicial de arriba (empresa, familia, código).
    # "doc_count" no es columna de BD: si participa en el orden, el
    # orden completo lo aplica _sort_assets_in_python() después.
    sort_keys = _parse_sort_param(_gp("sort"))
    if any(key == "doc_count" for key, _desc in sort_keys):
        sort_keys = []
    if sort_keys:
        order_fields = [
            ("-" if desc else "") + _SORTABLE_FIELDS[key]
            for key, desc in sort_keys
        ]
        if "code" not in [key for key, _desc in sort_keys]:
            order_fields.append("code")
        qs = qs.order_by(*order_fields)

    return qs


# S117 -- directrices 4.15/4.24: filtros y orden persistidos por
# usuario con la pieza compartida panel.navigation_persistence.
_FLEET_FILTER_KEYS = ("search", "family", "is_active", "sort", "requirement")

# S117 -- decisión de Miguel Ángel (opción 2): UN solo componente de
# maquinaria con DOS puertas de entrada -- "taller" (Taller Mecánico >
# Centros de gasto: ADMIN gestiona, SUPERVISOR/WORKSHOPBOSS consultan) y
# "docs" (hub de Documentación > pestaña Centros de Gasto: gestionan
# DOCS_SUPERVISOR y ADMIN). Cada puerta guarda su propia navegación y
# su propio "Volver" de la ficha documental.
FLEET_DOOR_TALLER = "taller"
FLEET_DOOR_DOCS = "docs"
_FLEET_SCREEN_KEYS = {
    FLEET_DOOR_TALLER: "fleet_list",
    FLEET_DOOR_DOCS: "fleet_docs",
}


def _fleet_door(value):
    """
    Normalises the door parameter ("taller" by default).
    ---
    Normaliza el parámetro de puerta ("taller" por defecto).
    """
    return FLEET_DOOR_DOCS if value == FLEET_DOOR_DOCS else FLEET_DOOR_TALLER


def _fleet_back_url(door):
    """
    Where "Volver" of the machine documentation page must return.
    ---
    A dónde debe volver "Volver" de la ficha documental de máquina.
    """
    from django.urls import reverse

    if door == FLEET_DOOR_DOCS:
        return reverse("panel:documentation_hub")
    return reverse("panel:fleet_list")


def _build_fragment_context(company, company_user, request):
    """
    Builds the shared context dict used by the table fragment.
    Annotates each asset with use_count (number of associated
    WorkOrderEntryLine records) and preserves the current filter
    state so HTMX mutations do not reset the UI.

    Reads filter values from GET first; falls back to POST so that
    mutation views (create, update, deactivate, reactivate, delete)
    can preserve the active filters embedded as hidden inputs in the form.

    ---

    Construye el dict de contexto compartido para el fragmento de tabla.
    Anota cada activo con use_count y preserva el estado de los filtros.
    Lee de GET primero; recurre a POST para que las vistas de mutación
    puedan preservar los filtros embebidos como hidden inputs en el form.
    """
    def _p(key, default=""):
        """Read from GET, fall back to POST."""
        return request.GET.get(key) or request.POST.get(f"_f_{key}", default)

    # S117 -- lo que tenía la pestaña primitiva de Documentación y no
    # tenía esta vista (decisión de Miguel Ángel: Centros de gasto será
    # la vista única de maquinaria): nº de documentos vivos de cada
    # máquina y aviso de documentación caducada (helper compartido
    # _attach_required_document_alerts desde S119, misma regla que el
    # hub de Documentación -- antes _attach_alert_flags, genérico y
    # sin ceñirse al requisito de documentación de cada máquina).
    #
    # CORREGIDO S117 (incidente real: la pestaña de Documentación no
    # llegaba a cargar -- "OSError: write error" en el log, el
    # navegador abandonaba la petición): la primera versión anotaba el
    # recuento con una Subquery correlacionada POR MÁQUINA sobre
    # DocumentIndexEntry, y domain_object_id no tiene índice -- con las
    # ~560 máquinas del listado sin filtro, ~560 recorridos de la tabla.
    # Ahora es UNA sola consulta agrupada; si se ordena por
    # "Documentos", el orden completo se aplica en Python sobre la
    # lista ya resuelta (mismas reglas de prioridad que en BD).
    from django.contrib.contenttypes.models import ContentType

    from document_explorer.models import DocumentIndexEntry
    from panel.views_documentation_h30 import (
        BUCKET, _attach_required_document_alerts,
    )

    machine_ct = ContentType.objects.get_for_model(MachineAsset)
    doc_counts = dict(
        DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=machine_ct,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            domain_object_id__isnull=False,
        )
        .order_by()
        .values_list("domain_object_id")
        .annotate(n=Count("id"))
    )
    assets = list(
        _build_queryset(company, request).annotate(
            use_count=Count("work_order_lines", distinct=True),
        )
    )
    for asset in assets:
        asset.doc_count = doc_counts.get(asset.pk, 0)
    sort_keys = _parse_sort_param(_p("sort"))
    if any(key == "doc_count" for key, _desc in sort_keys):
        assets = _sort_assets_in_python(assets, sort_keys)
    # H30 (S119): mismo cálculo que Personal, ceñido al requisito de
    # documentación de CADA máquina (MachineAsset.document_requirement,
    # mismo catálogo único JobPosition) -- ver docstring completo en
    # _attach_required_document_alerts. Sin requisito asignado, la
    # máquina no avisa de nada.
    assets = _attach_required_document_alerts(
        assets, machine_ct, requirement_field="document_requirement",
    )
    return {
        "assets": assets,
        "families": _get_families(company),
        "company": company,
        "company_user": company_user,
        "filter_family": _p("family"),
        "filter_requirement": _p("requirement"),
        "filter_is_active": _p("is_active"),
        "filter_search": _p("search"),
        "only_selected": request.GET.get("only_selected") == "1",
        **_build_sort_controls(_p("sort")),
        **_fleet_permissions(company_user),
        "fleet_door": _fleet_door(_p("door")),
        "fleet_back_url": _fleet_back_url(_fleet_door(_p("door"))),
    }


# ---------------------------------------------------------------------------
# MachineAssetListView
# ---------------------------------------------------------------------------

def _build_pane_context(request, door):
    """
    Full context of the shared machine pane (_fleet_pane.html) for one
    door: table fragment context + create form + presence/nav.
    ---
    Contexto completo del panel compartido de maquinaria
    (_fleet_pane.html) para una puerta: contexto del fragmento de tabla
    + formulario de alta + presencia/navegación.
    """
    company_user = request.user.company_user
    company = company_user.company
    apply_list_navigation(
        request, _FLEET_SCREEN_KEYS[door], _FLEET_FILTER_KEYS,
    )
    mutable = request.GET.copy()
    mutable["door"] = door
    request.GET = mutable
    fragment_ctx = _build_fragment_context(company, company_user, request)
    # S117 -- incidente real de Miguel Ángel: con varios centros
    # marcados, ir a la ficha documental de uno y pulsar "Volver"
    # perdía la selección (vivía solo en memoria de la página). Ahora se
    # guarda por usuario y por puerta en PanelNavigationState (clave
    # "selection", endpoint genérico /panel/navegacion/estado/) y se
    # restaura aquí al volver a cargar el panel.
    saved_selection = get_saved_state_key(
        company_user, _FLEET_SCREEN_KEYS[door], "selection", [],
    )
    if not isinstance(saved_selection, list):
        saved_selection = []
    # H30 (S119): mismo catálogo ÚNICO de "Requisitos de
    # documentación" que Personal (JobPosition, sin modelo aparte para
    # máquina) -- para el desplegable de asignación masiva.
    from document_explorer.models import JobPosition, PersonalDossierTemplate

    return {
        **fragment_ctx,
        "own_presence": _get_own_presence(company_user),
        "form": MachineAssetForm(company=company),
        "fleet_screen_key": _FLEET_SCREEN_KEYS[door],
        "saved_selection": saved_selection,
        "job_positions": JobPosition.objects.order_by("name"),
        # S130: plantillas de dosier de maquinaria, para descargar o
        # enviar la documentación desde aquí igual que en Personal.
        "dossier_machine_templates": company.dossier_templates.filter(
            scope=PersonalDossierTemplate.SCOPE_MACHINE,
        ).order_by("name"),
        # H31 (S148): grupos de selección de máquinas, como en Personal.
        "machine_group_nodes": group_tree(company_user, MACHINE_KIND),
        "machine_groups_collapsed": collapsed_state(
            company_user, MACHINE_KIND),
        "machine_group_parents": parent_choices(
            editor=company_user, kind=MACHINE_KIND),
    }


class MachineAssetListView(SupervisorAccessMixin, View):
    """
    "Taller" door of the machine pane: Taller Mecánico > Centros de
    gasto, for ADMIN, SUPERVISOR and WORKSHOPBOSS (S117, option 2 of
    Miguel Ángel -- DOCS_SUPERVISOR works from the Documentation door).

    GET /panel/fleet/
    ---
    Puerta "taller" del panel de maquinaria: Taller Mecánico > Centros
    de gasto, para ADMIN, SUPERVISOR y WORKSHOPBOSS (S117, opción 2 de
    Miguel Ángel -- DOCS_SUPERVISOR trabaja desde la puerta de
    Documentación).

    GET /panel/fleet/
    """

    template_name = "panel/fleet/list.html"

    def get(self, request, *args, **kwargs):
        """
        Renders the full page with the shared pane.
        ---
        Renderiza la página completa con el panel compartido.
        """
        ctx = _build_pane_context(request, FLEET_DOOR_TALLER)
        ctx["active_nav"] = "fleet"
        return render(request, self.template_name, ctx)


class MachineAssetDocsPaneView(DocsUploadAccessMixin, View):
    """
    "Docs" door of the machine pane: loaded by htmx into the
    "Centros de Gasto" tab of the Documentation hub, replacing the
    primitive listing of S48-S50 (decision of Miguel Ángel, S117).
    ADMIN and DOCS_SUPERVISOR.

    GET /panel/fleet/documentacion/
    ---
    Puerta "docs" del panel de maquinaria: cargada por htmx en la
    pestaña "Centros de Gasto" del hub de Documentación, sustituyendo
    al listado primitivo de S48-S50 (decisión de Miguel Ángel, S117).
    ADMIN y DOCS_SUPERVISOR.

    GET /panel/fleet/documentacion/
    """

    def get(self, request, *args, **kwargs):
        """
        Renders only the pane (no page chrome).
        ---
        Renderiza solo el panel (sin la página alrededor).
        """
        ctx = _build_pane_context(request, FLEET_DOOR_DOCS)
        return render(request, "panel/fleet/_fleet_pane.html", ctx)


class MachineAssetFragmentView(FleetAccessMixin, View):
    """
    Table fragment of the machine pane (filters, sorting) for BOTH
    doors -- the "door" parameter decides which navigation state is
    stored and where "Volver" of the documentation page returns.

    GET /panel/fleet/tabla/
    ---
    Fragmento de tabla del panel de maquinaria (filtros, orden) para
    AMBAS puertas -- el parámetro "door" decide qué estado de
    navegación se guarda y a dónde vuelve "Volver" de la ficha
    documental.

    GET /panel/fleet/tabla/
    """

    def get(self, request, *args, **kwargs):
        """
        Stores the navigation of the door and returns the fragment.
        ---
        Guarda la navegación de la puerta y devuelve el fragmento.
        """
        company_user = request.user.company_user
        door = _fleet_door(request.GET.get("door"))
        apply_list_navigation(
            request, _FLEET_SCREEN_KEYS[door], _FLEET_FILTER_KEYS,
        )
        ctx = _build_fragment_context(
            company_user.company, company_user, request,
        )
        return render(request, "panel/fleet/_table_fragment.html", ctx)


# ---------------------------------------------------------------------------
# MachineAssetCreateView
# ---------------------------------------------------------------------------

class MachineAssetCreateView(FleetManageAccessMixin, View):
    """
    Creates a new MachineAsset for the authenticated user's company.
    Accepts HTMX POST requests and returns an updated table fragment on
    success, or a form fragment with validation errors on failure.

    POST /panel/fleet/create/

    ---

    Crea un nuevo MachineAsset para la empresa del usuario autenticado.
    Acepta peticiones POST HTMX y devuelve un fragmento de tabla actualizado
    en caso de éxito, o un fragmento de formulario con errores en caso de
    fallo.

    POST /panel/fleet/create/
    """

    def post(self, request, *args, **kwargs):
        """
        Validates the form and creates the MachineAsset. On success returns
        the updated table fragment. On failure returns the form with errors.

        ---

        Valida el formulario y crea el MachineAsset. En caso de éxito devuelve
        el fragmento de tabla actualizado. En caso de fallo devuelve el
        formulario con errores.
        """
        company_user = request.user.company_user
        company = company_user.company
        form = MachineAssetForm(request.POST, company=company)

        if form.is_valid():
            asset = form.save(commit=False)
            asset.company = company
            asset.code = asset.code.strip().upper()
            asset.save()
            fragment_ctx = _build_fragment_context(
                company, company_user, request
            )
            return render(
                request, "panel/fleet/_table_fragment.html", fragment_ctx
            )

        # S117: con errores de validación el formulario vuelve a su
        # propio modal -- antes se pintaba dentro del contenedor de la
        # tabla (hx-target del form) y el modal se cerraba solo.
        response = render(request, "panel/fleet/_form_fragment.html", {
            "form": form,
            "company_user": company_user,
            "company": company,
            "form_action": "create",
        })
        response["HX-Retarget"] = "#fleet-create-form-container"
        response["HX-Reswap"] = "innerHTML"
        return response


# ---------------------------------------------------------------------------
# MachineAssetDeactivateView
# ---------------------------------------------------------------------------

class MachineAssetDeactivateView(FleetManageAccessMixin, View):
    """
    Sets is_active=False on a MachineAsset belonging to the authenticated
    user's company. Does not delete the record — preserves historical data
    integrity. Returns an updated table fragment via HTMX.

    POST /panel/fleet/<pk>/deactivate/

    ---

    Establece is_active=False en un MachineAsset de la empresa del usuario
    autenticado. No elimina el registro — preserva la integridad del histórico.
    Devuelve un fragmento de tabla actualizado via HTMX.

    POST /panel/fleet/<pk>/deactivate/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Marks the asset as inactive and returns the updated table fragment.
        Returns 404 if the asset does not belong to the company.

        ---

        Marca el activo como inactivo y devuelve el fragmento de tabla.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        company_user = request.user.company_user
        company = company_user.company
        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        asset.is_active = False
        asset.save(update_fields=["is_active"])
        # H30 (S119), punto 3: la carpeta de documentos sigue al estado
        # real de la máquina (ACTIVAS/{FAMILIA}/{CÓDIGO} <->
        # INACTIVAS/{CÓDIGO}), solo virtual; al reactivarla, sus
        # documentos recuperan también el nombre canónico.
        sync_machine_documents(asset)

        fragment_ctx = _build_fragment_context(company, company_user, request)
        return render(
            request, "panel/fleet/_table_fragment.html", fragment_ctx
        )


# ---------------------------------------------------------------------------
# MachineAssetReactivateView
# ---------------------------------------------------------------------------

class MachineAssetReactivateView(FleetManageAccessMixin, View):
    """
    Sets is_active=True on a MachineAsset belonging to the authenticated
    user's company. Counterpart to MachineAssetDeactivateView.
    Returns an updated table fragment via HTMX.

    POST /panel/fleet/<pk>/reactivate/

    ---

    Establece is_active=True en un MachineAsset de la empresa del usuario
    autenticado. Contraparte de MachineAssetDeactivateView.
    Devuelve un fragmento de tabla actualizado via HTMX.

    POST /panel/fleet/<pk>/reactivate/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Marks the asset as active and returns the updated table fragment.
        Returns 404 if the asset does not belong to the company.

        ---

        Marca el activo como activo y devuelve el fragmento de tabla.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        company_user = request.user.company_user
        company = company_user.company
        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        asset.is_active = True
        asset.save(update_fields=["is_active"])
        # H30 (S119), punto 3: la carpeta de documentos sigue al estado
        # real de la máquina (ACTIVAS/{FAMILIA}/{CÓDIGO} <->
        # INACTIVAS/{CÓDIGO}), solo virtual; al reactivarla, sus
        # documentos recuperan también el nombre canónico.
        sync_machine_documents(asset)

        fragment_ctx = _build_fragment_context(company, company_user, request)
        return render(
            request, "panel/fleet/_table_fragment.html", fragment_ctx
        )


# ---------------------------------------------------------------------------
# MachineAssetDeleteView
# ---------------------------------------------------------------------------

class MachineAssetDeleteView(AdminRoleRequiredMixin, View):
    """
    Permanently deletes a MachineAsset only if it has no associated
    WorkOrderEntryLine records (referential integrity guard).
    Only available to ADMIN role.
    Returns an updated table fragment on success or a JSON 409 on failure.

    POST /panel/fleet/<pk>/delete/

    ---

    Elimina permanentemente un MachineAsset solo si no tiene registros
    WorkOrderEntryLine asociados (guardia de integridad referencial).
    Solo disponible para el rol ADMIN.
    Devuelve un fragmento de tabla en éxito o JSON 409 en fallo.

    POST /panel/fleet/<pk>/delete/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Deletes the asset if it has no linked work-order lines.
        Returns HTTP 409 with a JSON error message if linked lines exist.
        Returns 404 if the asset does not belong to the company.

        ---

        Elimina el activo si no tiene líneas de parte asociadas.
        Devuelve HTTP 409 con mensaje de error JSON si existen líneas
        vinculadas. Devuelve 404 si no pertenece a la empresa.
        """
        company_user = request.user.company_user
        company = company_user.company
        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        if asset.work_order_lines.exists():
            return JsonResponse(
                {
                    "error": (
                        f"No se puede eliminar '{asset.code}': tiene partes "
                        f"de trabajo asociados. Use 'Dar de baja' para "
                        f"desactivarlo."
                    )
                },
                status=409,
            )

        asset.delete()
        fragment_ctx = _build_fragment_context(company, company_user, request)
        return render(
            request, "panel/fleet/_table_fragment.html", fragment_ctx
        )


# ---------------------------------------------------------------------------
# Bulk actions (S117) / Acciones masivas (S117)
# ---------------------------------------------------------------------------

def _selected_assets(company, request):
    """
    MachineAsset queryset of the company restricted to the pks sent
    as "selected" (checkboxes of the list).
    ---
    Queryset de MachineAsset de la empresa restringido a los pks
    enviados como "selected" (casillas del listado).
    """
    pks = [pk for pk in request.POST.getlist("selected") if pk.isdigit()]
    return MachineAsset.objects.filter(company=company, pk__in=pks)


def _fragment_with_message(request, company, company_user, message):
    """
    Renders the table fragment and carries a user message in the
    X-Fleet-Message header (URL-encoded), shown by the page as a toast.
    ---
    Renderiza el fragmento de tabla y lleva un mensaje para el usuario
    en la cabecera X-Fleet-Message (codificada en URL), que la página
    muestra como aviso.
    """
    from urllib.parse import quote

    fragment_ctx = _build_fragment_context(company, company_user, request)
    response = render(
        request, "panel/fleet/_table_fragment.html", fragment_ctx
    )
    response["X-Fleet-Message"] = quote(message)
    return response


class MachineAssetBulkStatusView(FleetManageAccessMixin, View):
    """
    Deactivates or reactivates every selected MachineAsset at once
    (POST action=deactivate|reactivate, selected=<pk>...). Never
    deletes anything -- same semantics as the per-row buttons.

    POST /panel/fleet/bulk/status/
    ---
    Da de baja o reactiva a la vez todos los MachineAsset
    seleccionados (POST action=deactivate|reactivate, selected=<pk>...).
    Nunca borra nada -- misma semántica que los botones por fila.

    POST /panel/fleet/bulk/status/
    """

    def post(self, request, *args, **kwargs):
        """
        Applies the status change and returns the refreshed fragment.
        ---
        Aplica el cambio de estado y devuelve el fragmento refrescado.
        """
        company_user = request.user.company_user
        company = company_user.company
        action = request.POST.get("action", "")
        if action not in ("deactivate", "reactivate"):
            return HttpResponse("Acción no válida.", status=400)
        target_active = action == "reactivate"
        updated = (
            _selected_assets(company, request)
            .exclude(is_active=target_active)
            .update(is_active=target_active)
        )
        verb = "reactivado" if target_active else "dado de baja"
        message = (
            f"{updated} centro{'s' if updated != 1 else ''} de gasto "
            f"{verb}{'s' if updated != 1 else ''}."
        )
        return _fragment_with_message(
            request, company, company_user, message,
        )


class MachineAssetBulkSetDocumentRequirementView(FleetManageAccessMixin, View):
    """
    Assigns (or clears, with document_requirement_id empty) a
    document requirement to every selected MachineAsset at once.

    POST /panel/fleet/bulk/requisito/
    ---
    H30 (S119). Asigna (o desasigna, con `document_requirement_id`
    vacío) un requisito de documentación a la vez a todos los
    MachineAsset seleccionados -- mismo mecanismo que
    `MachineAssetBulkStatusView` y que
    `PersonMassSetJobPositionView` en Personal, sobre el mismo
    catálogo ÚNICO `JobPosition` (nunca un modelo aparte para máquina
    -- Miguel Ángel: "los requisitos documentales no son ni para
    personas ni para máquinas [...] la gestión es global"). Una
    asignación masiva nueva SIEMPRE sustituye el requisito anterior de
    cada máquina, nunca lo acumula (`ForeignKey`, no M2M -- una
    máquina tiene un único requisito a la vez).

    POST /panel/fleet/bulk/requisito/
    """

    def post(self, request, *args, **kwargs):
        from document_explorer.models import JobPosition

        company_user = request.user.company_user
        company = company_user.company
        requirement_id = request.POST.get(
            "document_requirement_id", "",
        ).strip()
        requirement = (
            get_object_or_404(JobPosition, pk=requirement_id)
            if requirement_id else None
        )
        updated = _selected_assets(company, request).update(
            document_requirement=requirement,
        )
        verb = (
            f"asignado el requisito «{requirement}»" if requirement
            else "quitado su requisito de documentación"
        )
        message = (
            f"{updated} centro{'s' if updated != 1 else ''} de gasto "
            f"con {verb}."
        )
        return _fragment_with_message(
            request, company, company_user, message,
        )


class MachineAssetBulkDeleteView(AdminRoleRequiredMixin, View):
    """
    Permanently deletes the selected MachineAssets that have no linked
    work-order lines (same integrity guard as MachineAssetDeleteView);
    the ones in use are skipped and reported. ADMIN only.

    POST /panel/fleet/bulk/delete/
    ---
    Borra definitivamente los MachineAsset seleccionados que no tienen
    líneas de parte asociadas (misma guardia de integridad que
    MachineAssetDeleteView); los que están en uso se saltan y se
    informa de ellos. Solo ADMIN.

    POST /panel/fleet/bulk/delete/
    """

    def post(self, request, *args, **kwargs):
        """
        Deletes the deletable ones and returns the refreshed fragment.
        ---
        Borra los borrables y devuelve el fragmento refrescado.
        """
        company_user = request.user.company_user
        company = company_user.company
        selected = _selected_assets(company, request)
        in_use = list(
            selected.filter(work_order_lines__isnull=False)
            .values_list("code", flat=True)
            .distinct()
        )
        deletable = selected.exclude(code__in=in_use)
        deleted = deletable.count()
        deletable.delete()
        message = (
            f"{deleted} centro{'s' if deleted != 1 else ''} de gasto "
            f"eliminado{'s' if deleted != 1 else ''}."
        )
        if in_use:
            message += (
                f" {len(in_use)} no se ha{'n' if len(in_use) != 1 else ''}"
                f" tocado por tener partes de trabajo asociados (usar "
                f"'Dar de baja'): {', '.join(sorted(in_use))}."
            )
        return _fragment_with_message(
            request, company, company_user, message,
        )


# ---------------------------------------------------------------------------
# Excel export of the selection (S117) / Exportación a Excel (S117)
# ---------------------------------------------------------------------------

# Mismas columnas y mismo orden que la hoja MAQUINARIA del Excel real de
# Yolanda (document_explorer/data_imports/EXCEL_TRABAJADORES.xlsx), y el
# mismo mapeo columna<->campo que ya usa import_worker_machine_excel.
_EXPORT_COLUMNS = (
    "CODIGO", "MATRICULA", "ITV", "CITA ITV", "SEGURO", "OCA", "EMPRESA",
)


def _short_company_name(company_name):
    """
    "GRUAS ADOLFO ALVAREZ, S.L. CIF B29405040" -> "GRUAS ADOLFO
    ALVAREZ": same short form as the EMPRESA column of the real Excel.
    ---
    "GRUAS ADOLFO ALVAREZ, S.L. CIF B29405040" -> "GRUAS ADOLFO
    ALVAREZ": misma forma corta que la columna EMPRESA del Excel real.
    """
    name = (company_name or "").strip()
    for separator in (",", " CIF"):
        if separator in name:
            name = name.split(separator, 1)[0]
    return name.strip()


class MachineAssetExportView(FleetAccessMixin, View):
    """
    Downloads the selected cost centres as an .xlsx with the columns of
    the MAQUINARIA sheet of Yolanda's real Excel (POST selected=<pk>...).
    Read-only: available to every role that can see the list.

    POST /panel/fleet/export/
    ---
    Descarga los centros de gasto seleccionados en un .xlsx con las
    columnas de la hoja MAQUINARIA del Excel real de Yolanda (POST
    selected=<pk>...). Solo lectura: disponible para todo rol que vea
    el listado.

    POST /panel/fleet/export/
    """

    def post(self, request, *args, **kwargs):
        """
        Builds and returns the workbook.
        ---
        Construye y devuelve el libro Excel.
        """
        from io import BytesIO

        from openpyxl import Workbook
        from openpyxl.styles import Font

        company = request.user.company_user.company
        assets = _selected_assets(company, request).order_by("code")
        if not assets.exists():
            return HttpResponse(
                "No hay ningún centro de gasto seleccionado.", status=400,
            )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "MAQUINARIA"
        sheet.append(list(_EXPORT_COLUMNS))
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for asset in assets:
            sheet.append([
                asset.code,
                asset.plate,
                asset.itv_date,
                asset.itv_next_appointment,
                asset.insurance_info,
                asset.oca_date,
                _short_company_name(asset.company_name),
            ])
        for column in ("C", "D", "F"):
            for cell in sheet[column][1:]:
                cell.number_format = "DD/MM/YYYY"
        widths = {"A": 12, "B": 16, "C": 12, "D": 12, "E": 24,
                  "F": 12, "G": 28}
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"

        buffer = BytesIO()
        workbook.save(buffer)
        filename = (
            f"centros_de_gasto_{now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
        response = HttpResponse(
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return response


# ---------------------------------------------------------------------------
# MachineAssetAnalyticsView
# ---------------------------------------------------------------------------

class MachineAssetAnalyticsView(SupervisorAccessMixin, View):
    """
    Displays an activity report grouped by cost centre (MachineAsset).
    Aggregates total hours worked and total associated work-order entry lines
    per asset, with optional filters for date range, family and active status.
    Supports CSV export via the `export` GET parameter.

    GET  /panel/fleet/analytics/
    GET  /panel/fleet/analytics/?export=csv

    ---

    Muestra un informe de actividad agrupado por centro de gasto
    (MachineAsset).
    Agrega el total de horas trabajadas y el total de líneas de parte asociadas
    por activo, con filtros opcionales por rango de fechas, familia y estado.
    Soporta exportación CSV mediante el parámetro GET `export`.

    GET  /panel/fleet/analytics/
    GET  /panel/fleet/analytics/?export=csv
    """

    template_name = "panel/fleet/analytics.html"

    def _parse_date(self, value):
        """
        Parses an ISO date string (YYYY-MM-DD) into a date object.
        Returns None if the value is absent or malformed.

        ---

        Parsea una cadena de fecha ISO (YYYY-MM-DD) en un objeto date.
        Devuelve None si el valor está ausente o mal formado.
        """
        if not value:
            return None
        try:
            parts = value.strip().split("-")
            return dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError, AttributeError):
            return None

    def _build_report(self, company, request):
        """
        Builds and returns the annotated analytics queryset and active
        filter values from GET parameters.

        Filters:
          date_from / date_to — filter by WorkOrderEntryLine entry work_date.
          family              — exact match on MachineAsset.family.
          is_active           — '1' active only, '0' inactive only, '' all.

        Annotations per MachineAsset row:
          total_hours   — SUM of delta_hours from associated lines.
          total_entries — COUNT of associated lines (distinct).

        ---

        Construye y devuelve el queryset analítico anotado y los valores de
        filtro activos desde los parámetros GET.
        """
        date_from_raw = request.GET.get("date_from", "").strip()
        date_to_raw = request.GET.get("date_to", "").strip()
        family_filter = request.GET.get("family", "").strip()
        active_filter = request.GET.get("is_active", "1")

        date_from = self._parse_date(date_from_raw)
        date_to = self._parse_date(date_to_raw)

        qs = MachineAsset.objects.filter(company=company)

        if family_filter:
            qs = qs.filter(family__iexact=family_filter)

        if active_filter == "1":
            qs = qs.filter(is_active=True)
        elif active_filter == "0":
            qs = qs.filter(is_active=False)

        line_filter_kwargs = {}
        if date_from:
            line_filter_kwargs[
                "work_order_lines__entry__work_date__gte"
            ] = date_from
        if date_to:
            line_filter_kwargs[
                "work_order_lines__entry__work_date__lte"
            ] = date_to

        if line_filter_kwargs:
            qs = qs.annotate(
                total_hours=Coalesce(
                    Sum(
                        "work_order_lines__delta_hours",
                        filter=Q(**line_filter_kwargs),
                    ),
                    0.0,
                    output_field=FloatField(),
                ),
                total_entries=Coalesce(
                    Count(
                        "work_order_lines",
                        filter=Q(**line_filter_kwargs),
                        distinct=True,
                    ),
                    0,
                ),
            )
        else:
            qs = qs.annotate(
                total_hours=Coalesce(
                    Sum("work_order_lines__delta_hours"),
                    0.0,
                    output_field=FloatField(),
                ),
                total_entries=Coalesce(
                    Count("work_order_lines", distinct=True),
                    0,
                ),
            )

        qs = qs.order_by("-total_hours", "code")

        return qs, {
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "filter_family": family_filter,
            "filter_is_active": active_filter,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the analytics page or exports a CSV file when the
        `export=csv` GET parameter is present.

        ---

        Renderiza la página de analítica o exporta un CSV cuando el parámetro
        GET `export=csv` está presente.
        """
        company_user = request.user.company_user
        company = company_user.company
        qs, filters = self._build_report(company, request)

        if request.GET.get("export") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                'attachment; filename="centros_de_gasto_actividad.csv"'
            )
            response.write("\ufeff")
            writer = csv.writer(response, delimiter=";")
            writer.writerow([
                "Código", "Familia", "Marca / Modelo", "Matrícula",
                "Estado", "Total horas", "Total partes",
            ])
            for asset in qs:
                writer.writerow([
                    asset.code,
                    asset.family,
                    asset.brand_model,
                    asset.plate,
                    "Activo" if asset.is_active else "Inactivo",
                    (
                        f"{asset.total_hours:.2f}" if asset.total_hours
                        else "0.00"
                    ),
                    asset.total_entries,
                ])
            return response

        ctx = {
            "company": company,
            "company_user": company_user,
            "own_presence": _get_own_presence(company_user),
            "active_nav": "fleet_analytics",
            "assets": qs,
            "families": _get_families(company),
            "total_hours_sum": sum(
                a.total_hours for a in qs if a.total_hours
            ),
            **filters,
        }
        return render(request, self.template_name, ctx)
