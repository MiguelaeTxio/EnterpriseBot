# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/views_services.py
"""
H37 (S132). Services page: the assistance service management hub.

---

H37 (S132). Página Servicios: centro de gestión del servicio de
asistencia, con pestañas en el formato de Documentación. Solo la ven
los administradores y los supervisores de asistencia
(`AssistanceSupervisorAccessMixin`). La pestaña activa se guarda por
usuario (directriz 4.15, `PanelNavigationState`, screen_key
`services_hub`).
"""
import logging
import os

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from budgets.forms_services import WorkOrderAssistanceForm
from budgets.models import (
    Insurer,
    ServiceEvaluation,
    WorkOrderAssistance,
)
from budgets.views import _build_base_context
from chat import room_service
from panel.mixins import (
    AdminRoleRequiredMixin,
    AssistanceSupervisorAccessMixin,
    AssistanceWorkOrderAccessMixin,
)
from panel.models import PanelNavigationState

logger = logging.getLogger(__name__)

SCREEN_KEY = "services_hub"
# H37 (S133): the traffic panel is the main tab (dossier, 4.4).
# El panel de tráfico es la pestaña principal (dossier, 4.4).
TABS = ("trafico", "albaranes", "servicios")
DEFAULT_TAB = "trafico"


def _nav_state(company_user):
    """
    Saved navigation state of the Services page for the user.

    ---

    Estado de navegación guardado de la página Servicios del usuario
    (directriz 4.15), siempre como diccionario.
    """
    nav_state = PanelNavigationState.objects.filter(
        company_user=company_user, screen_key=SCREEN_KEY,
    ).first()
    state = nav_state.state if nav_state else {}
    return state if isinstance(state, dict) else {}


class ServicesHubView(AssistanceSupervisorAccessMixin, View):
    """
    Services page with its tabs.

    ---

    Página Servicios con sus pestañas. Abre en la pestaña que el
    usuario dejó activa.
    """

    template_name = "budgets/services/hub.html"

    def get(self, request):
        """
        Render the page on the persisted tab.

        ---

        Pinta la página en la pestaña guardada.
        """
        state = _nav_state(request.user.company_user)
        active_tab = state.get("active_tab")
        if active_tab not in TABS:
            active_tab = DEFAULT_TAB
        ctx = _build_base_context(request, {
            "active_nav": "services_hub",
            "active_tab": active_tab,
            "screen_key": SCREEN_KEY,
        })
        return render(request, self.template_name, ctx)


ALBARANES_SCREEN_KEY = "services_albaranes"


def _albaranes_params(request):
    """
    Filters of the albaranes list: GET, then POST (_f_ prefix).

    ---

    Filtros del listado de albaranes: los de GET y, en las acciones por
    POST, los vigentes con el prefijo _f_ (mismo criterio que Centros
    de gasto).
    """
    from budgets.assistance_albaranes import FILTER_KEYS

    return {
        key: request.GET.get(key) or request.POST.get("_f_" + key, "")
        for key in FILTER_KEYS
    }


def _albaranes_context(request):
    """
    Context of the albaranes table fragment.

    ---

    Contexto del fragmento de tabla de albaranes: filas, filtros
    vigentes y controles de orden, resueltos aquí (plantillas tontas).
    """
    from budgets import assistance_albaranes as albaranes

    company = request.user.company_user.company
    params = _albaranes_params(request)
    only_selected = request.GET.get("only_selected") == "1"
    only_keys = None
    if only_selected:
        only_keys = {
            key for key in request.GET.get("selected_ids", "").split(",")
            if key
        }
    rows = albaranes.build_rows(company, params, only_keys=only_keys)
    return {
        "rows": rows,
        "filter_search": params["search"],
        "filter_state": params["state"],
        "filter_insurer": params["insurer"],
        "filter_date_from": params["date_from"],
        "filter_date_to": params["date_to"],
        "only_selected": only_selected,
        "is_filtered": bool(
            params["search"] or params["state"] or params["insurer"]
            or params["date_from"] or params["date_to"] or only_selected
        ),
        **albaranes.sort_controls(params["sort"]),
    }


class ServicesDeliveryNotesPaneView(AssistanceSupervisorAccessMixin, View):
    """
    Albaranes tab: every assistance albarán, open and closed.

    ---

    Pestaña Albaranes: todos los albaranes de asistencia, abiertos y
    cerrados, con el formato de la directriz 4.24 (panel fijo con
    filtros y acciones, lista con scroll propio, orden múltiple,
    casillas y visor de selección), filtros y selección guardados por
    usuario (directriz 4.15).
    """

    template_name = "budgets/services/_delivery_notes_pane.html"

    def get(self, request):
        """
        Render the tab content.

        ---

        Pinta el contenido de la pestaña.
        """
        from budgets.assistance_albaranes import FILTER_KEYS
        from panel.navigation_persistence import (
            apply_list_navigation,
            get_saved_state_key,
        )

        company_user = request.user.company_user
        apply_list_navigation(request, ALBARANES_SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            company_user, ALBARANES_SCREEN_KEY, "selection", [],
        )
        return render(request, self.template_name, {
            **_albaranes_context(request),
            "insurers": Insurer.objects.filter(
                company=company_user.company,
            ).order_by("name"),
            "screen_key": ALBARANES_SCREEN_KEY,
            "saved_selection": (
                saved_selection if isinstance(saved_selection, list) else []
            ),
        })


class ServicesDeliveryNotesFragmentView(
    AssistanceSupervisorAccessMixin, View,
):
    """
    Albaranes table fragment (filters, order, selection).

    ---

    Fragmento de tabla de albaranes, para filtros, orden y "mostrar
    solo la selección". Guarda filtros y orden por usuario.
    """

    def get(self, request):
        """
        Return the table fragment.

        ---

        Devuelve el fragmento de tabla.
        """
        from budgets.assistance_albaranes import FILTER_KEYS
        from panel.navigation_persistence import apply_list_navigation

        apply_list_navigation(request, ALBARANES_SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "budgets/services/_delivery_notes_table.html",
            _albaranes_context(request),
        )


class ServicesDeliveryNotesZipView(AssistanceSupervisorAccessMixin, View):
    """
    PDF of the selected albaranes, in one ZIP.

    ---

    PDF de los albaranes seleccionados en un ZIP (POST selected=u<pk>),
    el mismo PDF que la descarga individual (albaran_pdf.html).
    """

    def post(self, request):
        """
        Build and return the ZIP.

        ---

        Construye y devuelve el ZIP.
        """
        import io
        import zipfile

        import weasyprint
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.utils import timezone

        from budgets.assistance_albaranes import selected_units

        company = request.user.company_user.company
        units = list(selected_units(
            company, request.POST.getlist("selected"),
        ))
        if not units:
            return HttpResponse(
                "No hay ningún albarán seleccionado.", status=400,
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for unit in units:
                html = render_to_string("budgets/albaran_pdf.html", {
                    "unit": unit,
                    "work_order": unit.work_order,
                    "company": company,
                }, request=request)
                archive.writestr(
                    "albaran_%s.pdf" % unit.albaran_number,
                    weasyprint.HTML(string=html).write_pdf(),
                )
        filename = "albaranes_%s.zip" % (
            timezone.localtime().strftime("%Y%m%d_%H%M")
        )
        response = HttpResponse(
            buffer.getvalue(), content_type="application/zip",
        )
        response["Content-Disposition"] = (
            'attachment; filename="%s"' % filename
        )
        return response


class WorkOrderSummaryPdfView(AssistanceWorkOrderAccessMixin, View):
    """
    Summary albarán of an order, as a PDF.

    ---

    Albarán resumen de la orden en PDF (Miguel Ángel, S133): todos sus
    albaranes con conductor, ayudantes, máquina, km, horas y la firma
    de cada uno. Se saca en cualquier momento; dice si está completo o
    parcial.
    """

    def get(self, request, pk):
        """
        Render and return the PDF.

        ---

        Pinta y devuelve el PDF.
        """
        import weasyprint
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.utils import timezone

        from budgets.assistance_albaranes import summary_context

        company = request.user.company_user.company
        work_order = get_object_or_404(
            WorkOrderAssistance.objects.select_related("insurer"),
            pk=pk, company=company,
        )
        html = render_to_string("budgets/albaran_resumen_pdf.html", {
            **summary_context(work_order),
            "work_order": work_order,
            "company": company,
            "generated_at": timezone.localtime(),
        }, request=request)
        response = HttpResponse(
            weasyprint.HTML(string=html).write_pdf(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            'attachment; filename="albaran_resumen_%s.pdf"'
            % work_order.work_order_number
        )
        return response


ALBARANES_EXPORT_COLUMNS = (
    "Albarán", "Fecha", "Aseguradora", "Expediente", "Matrícula",
    "Cliente", "Recogida", "Destino", "Conductor", "Máquina", "Estado",
    "Km albarán", "Km estimados", "Gasoil estimado (l)", "Cerrado en base",
)


class ServicesDeliveryNotesExportView(
    AssistanceSupervisorAccessMixin, View,
):
    """
    Selected albaranes as an Excel workbook.

    ---

    Los albaranes seleccionados en un Excel (POST selected=u<pk>), una
    fila por albarán.
    """

    def post(self, request):
        """
        Build and return the workbook.

        ---

        Construye y devuelve el libro.
        """
        import io

        from django.http import HttpResponse
        from django.utils import timezone
        from openpyxl import Workbook
        from openpyxl.styles import Font

        from budgets.assistance_albaranes import selected_units

        company = request.user.company_user.company
        units = list(selected_units(
            company, request.POST.getlist("selected"),
        ))
        if not units:
            return HttpResponse(
                "No hay ningún albarán seleccionado.", status=400,
            )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ALBARANES"
        sheet.append(list(ALBARANES_EXPORT_COLUMNS))
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for unit in units:
            order = unit.work_order
            user = unit.operator.user if unit.operator_id else None
            km = [k for k in (unit.phase1_km, unit.phase2_km) if k]
            sheet.append([
                unit.albaran_number,
                order.service_date,
                order.insurer.name if order.insurer else "",
                order.expediente or "",
                order.vehicle_plate or "",
                order.client_name or "",
                order.pickup_location or "",
                order.destination or "",
                (user.get_full_name() or user.username) if user else "",
                unit.machine or "",
                unit.get_status_display(),
                float(sum(km)) if km else None,
                float(unit.estimated_km) if unit.estimated_km else None,
                (
                    float(unit.estimated_fuel_liters)
                    if unit.estimated_fuel_liters else None
                ),
                (
                    timezone.localtime(unit.base_closed_at).replace(
                        tzinfo=None,
                    ) if unit.base_closed_at else None
                ),
            ])
        for cell in sheet["B"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for cell in sheet["O"][1:]:
            cell.number_format = "DD/MM/YYYY HH:MM"
        sheet.freeze_panes = "A2"
        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            'attachment; filename="albaranes_%s.xlsx"'
            % timezone.localtime().strftime("%Y%m%d_%H%M")
        )
        return response


# ---------------------------------------------------------------------------
# H37 (S133). Traffic panel: drivers, machines and open albaranes, with
# drag-and-drop assignment and sending (dossier phase 2).
# Panel de tráfico: conductores, máquinas y albaranes abiertos, con
# asignación arrastrando y envío (fase 2 del dossier).
# ---------------------------------------------------------------------------

TRAFFIC_ACTIONS = (
    "pair", "separate", "assign", "unassign", "send", "close",
    "add_helper", "remove_helper", "cancel", "queue_mode",
)


def _traffic_filters(request):
    """
    Category and order of the board: request first, then saved state.

    ---

    Categoría de máquina y orden del panel: los de la petición si
    llegan; si no, los guardados del usuario (directriz 4.15).
    """
    from budgets.assistance_traffic import SORT_AVAILABILITY, SORT_OPTIONS

    saved = _nav_state(request.user.company_user).get("traffic")
    saved = saved if isinstance(saved, dict) else {}
    if "sort" in request.GET:
        source = request.GET
    elif "sort" in request.POST:
        source = request.POST
    else:
        source = saved
    category = str(source.get("category") or "")
    sort = source.get("sort")
    if sort not in dict(SORT_OPTIONS):
        sort = SORT_AVAILABILITY
    return category, sort


def _render_board(request, message="", error=""):
    """
    Render the board fragment with the current data.

    ---

    Pinta el fragmento del panel con los datos del momento.
    """
    from budgets.assistance_traffic import build_board

    category, sort = _traffic_filters(request)
    ctx = build_board(
        request.user.company_user.company, category=category, sort=sort,
    )
    ctx.update({"board_message": message, "board_error": error})
    return render(request, "budgets/services/_traffic_board.html", ctx)


class ServicesTrafficPaneView(AssistanceSupervisorAccessMixin, View):
    """
    Traffic tab: fixed top bar and the board below.

    ---

    Pestaña Tráfico: barra fija arriba (altas, categoría, orden) y el
    panel de tres columnas debajo, que se refresca solo.
    """

    template_name = "budgets/services/_traffic_pane.html"

    def get(self, request):
        """
        Render the tab.

        ---

        Pinta la pestaña.
        """
        from budgets.assistance_traffic import SORT_OPTIONS, build_board

        category, sort = _traffic_filters(request)
        ctx = build_board(
            request.user.company_user.company,
            category=category, sort=sort,
        )
        ctx.update({
            "sort_options": SORT_OPTIONS,
            "screen_key": SCREEN_KEY,
            "board_message": "",
            "board_error": "",
            "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            "google_maps_map_id": os.environ.get("GOOGLE_MAPS_MAP_ID", ""),
        })
        return render(request, self.template_name, ctx)


class ServicesTrafficBoardView(AssistanceSupervisorAccessMixin, View):
    """
    Board fragment, for the periodic refresh and the filters.

    ---

    Fragmento del panel, para el refresco periódico y los filtros.
    """

    def get(self, request):
        """
        Return the board fragment.

        ---

        Devuelve el fragmento del panel.
        """
        return _render_board(request)


class ServicesTrafficMapView(AssistanceSupervisorAccessMixin, View):
    """
    Data of the traffic map, as JSON.

    ---

    Datos del mapa de tráfico en JSON: bases con sus equipos, equipos
    fuera con su última posición y recogidas de los albaranes abiertos
    (`assistance_traffic.build_map`).
    """

    def get(self, request):
        """
        Return the map data.

        ---

        Devuelve los datos del mapa.
        """
        from budgets.assistance_traffic import build_map

        return JsonResponse(build_map(request.user.company_user.company))


class ServicesTrafficActionView(AssistanceSupervisorAccessMixin, View):
    """
    Crew changes, assignment and sending from the board.

    ---

    Acciones del panel: formar o cambiar un equipo (conductor soltado
    sobre una máquina o un equipo), separarlo, asignar un equipo a un
    albarán o a una orden, quitarlo, añadir o quitar ayudantes, enviar
    el albarán y cerrarlo en
    base con los km y el gasoil estimados. Las reglas
    están en `assistance_traffic`; si no se cumplen, el panel lo dice.
    Devuelve el panel actualizado.
    """

    def post(self, request, action):
        """
        Apply the action and return the board.

        ---

        Aplica la acción y devuelve el panel.
        """
        from budgets import assistance_traffic as traffic

        company_user = request.user.company_user
        company = company_user.company
        data = request.POST
        try:
            if action not in TRAFFIC_ACTIONS:
                raise traffic.TrafficError("Acción desconocida.")
            if action == "pair":
                message = traffic.pair(
                    company, company_user,
                    driver_pk=_int(data.get("driver")),
                    machine_pk=_int(data.get("machine")),
                )
            elif action == "separate":
                message = traffic.separate(
                    company, company_user, _int(data.get("crew")),
                )
            elif action == "assign":
                unit = traffic.assign(
                    company, company_user,
                    crew_pk=_int(data.get("crew")),
                    unit_pk=_int(data.get("unit")),
                    order_pk=_int(data.get("order")),
                )
                message = (
                    "Equipo en cola en el albarán %s: se enviará solo "
                    "cuando termine el servicio en curso."
                    if unit.queued_at else "Equipo asignado al albarán %s."
                ) % unit.albaran_number
            elif action == "unassign":
                unit = traffic.unassign(
                    company, company_user, _int(data.get("unit")),
                )
                message = "Equipo retirado del albarán %s." % (
                    unit.albaran_number
                )
            elif action == "add_helper":
                unit = traffic.add_helper(
                    company, company_user, _int(data.get("unit")),
                    _int(data.get("driver")),
                )
                message = "Ayudante añadido al albarán %s." % (
                    unit.albaran_number
                )
            elif action == "remove_helper":
                unit = traffic.remove_helper(
                    company, company_user, _int(data.get("unit")),
                    _int(data.get("driver")),
                )
                message = "Ayudante retirado del albarán %s." % (
                    unit.albaran_number
                )
            elif action == "close":
                unit = traffic.close_base(
                    company, company_user, _int(data.get("unit")),
                    data.get("km"), data.get("liters"),
                )
                message = "Albarán %s cerrado en base." % (
                    unit.albaran_number
                )
            elif action == "queue_mode":
                unit = traffic.set_queue_mode(
                    company, company_user, _int(data.get("unit")),
                    data.get("mode"),
                )
                message = "Albarán %s en cola %s." % (
                    unit.albaran_number,
                    unit.get_queue_mode_display().lower(),
                )
            elif action == "cancel":
                unit = traffic.cancel(
                    company, company_user, _int(data.get("unit")),
                    data.get("reason"),
                )
                message = "Albarán %s anulado." % unit.albaran_number
            else:
                unit = traffic.send(
                    company, company_user, _int(data.get("unit")),
                    os.environ.get("TWILIO_WHATSAPP_SENDER", ""),
                )
                message = (
                    "Albarán %s enviado. Falta que WhatsApp confirme la "
                    "entrega." % unit.albaran_number
                )
        except traffic.TrafficError as exc:
            return _render_board(request, error=str(exc))
        return _render_board(request, message=message)


def _int(value):
    """
    Integer from a form value, or None.

    ---

    Entero de un valor de formulario, o None.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# H37 (S132). Order entry from the TIREA photo, manual entry and editing.
# Alta de la orden desde la foto de TIREA, alta a mano y edición.
# ---------------------------------------------------------------------------

ACCEPTED_UPLOAD_TYPES = (
    "image/jpeg", "image/png", "image/webp", "application/pdf",
)
# Keys of the extraction that are not model fields (hints for the form).
# Claves de la extracción que no son campos del modelo (pistas).
_HINT_KEYS = ("insurer_name", "company_tax_id", "client_company",
              "tirea_driver",
              "tirea_machine", "service_datetime", "ris_motive")


def _match_insurer(company, name):
    """
    Insurer of the company whose name matches the TIREA company.

    ---

    Aseguradora de la empresa que corresponde a la "Compañía" de TIREA:
    primero igualdad exacta (sin mayúsculas) en cualquiera de sus
    nombres, después que uno contenga al otro. None si no hay una única
    candidata (nunca se adivina).
    """
    if not name:
        return None
    insurers = Insurer.objects.filter(company=company, is_active=True)
    exact = insurers.filter(
        Q(name__iexact=name)
        | Q(insurer_company_name__iexact=name)
        | Q(service_company_name__iexact=name)
    )
    if exact.count() == 1:
        return exact.first()
    partial = insurers.filter(
        Q(name__icontains=name)
        | Q(insurer_company_name__icontains=name)
        | Q(service_company_name__icontains=name)
    )
    if partial.count() == 1:
        return partial.first()
    return None


# Names under which an insurer appears in the service documents, when
# they are not the one of the catalogue (S133: TIREA shows "ALLIANZ
# PARTNERS" for the Mondial insurers).
# Nombres con que aparece una aseguradora en los documentos del servicio
# cuando no son los del catálogo (S133: TIREA pone "ALLIANZ PARTNERS"
# para las aseguradoras Mondial).
INSURER_NAME_ALIASES = {
    "allianz partners": "mondial",
    "allianz global assistance": "mondial",
    "awp": "mondial",
}


def _plain(text):
    """
    Lower case without accents or punctuation, for name matching.

    ---

    Minúsculas sin tildes ni signos, para comparar nombres.
    """
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def own_company_for_tax_id(tax_id):
    """
    Group company (fiscal profile) of a CIF, or None.

    ---

    Empresa del grupo (perfil fiscal) que tiene ese CIF, o None.
    """
    import re

    from document_explorer.models import CompanyFiscalProfile

    # The extraction returns every CIF it reads, separated by commas.
    # La extracción devuelve todos los CIF que lee, separados por comas.
    wanted = {
        _plain(part).replace(" ", "")
        for part in re.split(r"[,;/\s]+", str(tax_id or ""))
    } - {""}
    if not wanted:
        return None
    for profile in CompanyFiscalProfile.objects.all():
        if _plain(profile.tax_id).replace(" ", "") in wanted:
            return profile
    return None


def _match_insurer_by_tax_id(company, tax_id, insurer_name):
    """
    Insurer card of the service by the CIF of the document.

    ---

    Ficha de aseguradora del servicio según el CIF del documento
    (reunión con Pepe, S133: "va por el CIF"). Cada aseguradora tiene
    una ficha por empresa del grupo ("Mondial / Gruas Alvarez",
    "Mondial / Transgrual"...): el CIF dice la empresa y el nombre leído
    dice la aseguradora. None si no hay una sola ficha que encaje.
    """
    profile = own_company_for_tax_id(tax_id)
    if profile is None:
        return None
    own_names = [_plain(profile.legal_name)] + [
        _plain(alias) for alias in profile.name_aliases.splitlines()
        if alias.strip()
    ]
    stop = {"y", "s", "l", "sl", "sa", "slu"}

    def is_ours(service_name):
        for alternative in str(service_name or "").split("/"):
            words = [w for w in _plain(alternative).split() if w not in stop]
            if words and any(
                all(word in own.split() for word in words)
                for own in own_names
            ):
                return True
        return False

    candidates = [
        insurer for insurer in Insurer.objects.filter(
            company=company, is_active=True,
        )
        if is_ours(insurer.service_company_name)
    ]
    read = _plain(insurer_name)
    for alias, catalogue_name in INSURER_NAME_ALIASES.items():
        if alias in read:
            read = catalogue_name
    if read:
        candidates = [
            insurer for insurer in candidates
            if _plain(insurer.insurer_company_name) in read
            or read in _plain(insurer.insurer_company_name)
        ]
    return candidates[0] if len(candidates) == 1 else None


def _match_vehicle_type(insurer, label):
    """
    Vehicle type of the insurer named like the TIREA vehicle type.

    ---

    Tipo de vehículo de la aseguradora cuyo nombre contiene el "Tipo
    Vehículo" de TIREA (o al revés). None si no hay uno solo.
    """
    if not insurer or not label:
        return None
    types = insurer.vehicle_types.filter(is_active=True)
    matches = [
        vehicle_type for vehicle_type in types
        if label.lower() in vehicle_type.name.lower()
        or vehicle_type.name.lower() in label.lower()
    ]
    return matches[0] if len(matches) == 1 else None


def _initial_from_extraction(company, data):
    """
    Initial form values from the TIREA extraction.

    ---

    Valores iniciales del formulario a partir de la extracción de TIREA.
    """
    initial = {
        key: value for key, value in data.items() if key not in _HINT_KEYS
    }
    insurer = _match_insurer_by_tax_id(
        company, data.get("company_tax_id"), data.get("insurer_name"),
    ) or _match_insurer(company, data.get("insurer_name"))
    if insurer:
        initial["insurer"] = insurer.pk
        vehicle_type = _match_vehicle_type(
            insurer, data.get("vehicle_type_label"),
        )
        if vehicle_type:
            initial["vehicle_type"] = vehicle_type.pk
    if data.get("service_datetime"):
        initial["service_date"] = data["service_datetime"].date()
    if data.get("ris_motive"):
        initial["ris_motive_text"] = data["ris_motive"]
    return initial


def _render_order_form(request, form, title, action_url, hints=None,
                       origin="", source_token="", evaluation_pk=""):
    """
    Render the order form page.

    ---

    Pinta la página del formulario de la orden.
    """
    return render(request, "budgets/services/work_order_form.html",
                  _build_base_context(request, {
                      "active_nav": "services_hub",
                      "form": form,
                      "page_heading": title,
                      "form_action": reverse(action_url),
                      "hints": hints or {},
                      "origin": origin,
                      # H37 (S138): documento de TIREA ya guardado en
                      # GCS, para que el bot lo publique en la sala.
                      "source_token": source_token,
                      # H37 (S142): servicio valorado del que sale la
                      # orden, para enlazarlo al guardarla.
                      "evaluation_pk": evaluation_pk,
                  }))


class ServicesTireaUploadView(AssistanceSupervisorAccessMixin, View):
    """
    Upload the TIREA photo and review the extracted data.

    ---

    Subida de la foto del albarán de TIREA (GET: formulario de subida;
    POST: extracción con Gemini y formulario de alta ya relleno para
    que el supervisor lo revise). No se guarda nada hasta que el
    supervisor confirma el formulario (WorkOrderSaveView).
    """

    template_name = "budgets/services/tirea_upload.html"

    def get(self, request):
        """
        Render the upload form.

        ---

        Pinta el formulario de subida.
        """
        return render(request, self.template_name, _build_base_context(
            request, {"active_nav": "services_hub"},
        ))

    def post(self, request):
        """
        Extract the data and render the prefilled order form.

        ---

        Extrae los datos y pinta el formulario de alta relleno.
        """
        from budgets.tirea_extraction import extract_tirea_albaran

        upload = request.FILES.get("photo")
        if upload is None or upload.content_type not in ACCEPTED_UPLOAD_TYPES:
            messages.error(
                request,
                "Sube una foto (JPG, PNG o WEBP) o un PDF del albarán de "
                "TIREA.",
            )
            return redirect("budgets:services_tirea_upload")
        company = request.user.company_user.company
        content = upload.read()
        try:
            data = extract_tirea_albaran(content, upload.content_type)
        except Exception:
            logger.exception("# [TIREA] Error en la extracción.")
            messages.error(
                request,
                "No se han podido leer los datos de la foto. Prueba con "
                "otra foto o da de alta la orden a mano.",
            )
            return redirect("budgets:services_tirea_upload")
        form = WorkOrderAssistanceForm(
            initial=_initial_from_extraction(company, data), company=company,
        )
        hints = {key: data[key] for key in _HINT_KEYS if key in data}
        # H37 (S138): the TIREA document is kept so the room bot posts
        # it with the service once it is saved.
        # Se guarda el documento de TIREA para que el bot lo publique
        # en la sala con el servicio cuando se guarde.
        source_token = room_service.sign_source(
            room_service.store_source_document(
                company, content, upload.content_type,
            ),
            upload.content_type,
        )
        return _render_order_form(
            request, form, "Nueva orden desde TIREA",
            "budgets:work_order_save", hints,
            origin=WorkOrderAssistance.ORIGIN_PHOTO,
            source_token=source_token,
        )


class WorkOrderSaveView(AssistanceSupervisorAccessMixin, View):
    """
    Create the work order from the reviewed form.

    ---

    Crea la orden de trabajo con el formulario revisado (desde TIREA o
    a mano, GET pinta el formulario vacío).
    """

    def get(self, request):
        """
        Render the empty order form (manual entry).

        ---

        Pinta el formulario vacío (alta a mano).
        """
        form = WorkOrderAssistanceForm(
            company=request.user.company_user.company,
        )
        return _render_order_form(
            request, form, "Nueva orden", "budgets:work_order_save",
        )

    def post(self, request):
        """
        Validate and create the order.

        ---

        Valida y crea la orden.
        """
        company_user = request.user.company_user
        form = WorkOrderAssistanceForm(
            request.POST, company=company_user.company,
        )
        origin = request.POST.get("origin", "")
        if origin not in dict(WorkOrderAssistance.ORIGIN_CHOICES):
            origin = WorkOrderAssistance.ORIGIN_PANEL
        source_token = request.POST.get("source_token", "")
        evaluation_pk = request.POST.get("evaluation", "")
        if not form.is_valid():
            return _render_order_form(
                request, form, "Nueva orden", "budgets:work_order_save",
                origin=origin, source_token=source_token,
                evaluation_pk=evaluation_pk,
            )
        work_order = form.save(commit=False)
        work_order.origin = origin
        (
            work_order.source_document_blob,
            work_order.source_document_type,
        ) = room_service.unsign_source(source_token)
        work_order.company = company_user.company
        work_order.operator = company_user
        work_order.created_by = company_user
        form.save()
        if evaluation_pk.isdigit():
            # H37 (S142): the valued service now has its order.
            # El servicio valorado ya tiene su orden.
            ServiceEvaluation.objects.filter(
                pk=int(evaluation_pk), company=company_user.company,
            ).update(work_order=work_order)
        messages.success(
            request,
            "Orden de trabajo %s creada." % work_order.work_order_number,
        )
        return redirect("budgets:work_order_detail", pk=work_order.pk)


class WorkOrderEditView(AssistanceWorkOrderAccessMixin, View):
    """
    Edit the data of an existing work order.

    ---

    Edición de los datos de una orden de trabajo existente.
    """

    def get(self, request, pk):
        """
        Render the order form with its data.

        ---

        Pinta el formulario con los datos de la orden.
        """
        work_order = self._work_order(request, pk)
        form = WorkOrderAssistanceForm(
            instance=work_order, company=work_order.company,
        )
        return self._render(request, form, work_order)

    def post(self, request, pk):
        """
        Validate and save the changes.

        ---

        Valida y guarda los cambios.
        """
        work_order = self._work_order(request, pk)
        form = WorkOrderAssistanceForm(
            request.POST, instance=work_order, company=work_order.company,
        )
        if not form.is_valid():
            return self._render(request, form, work_order)
        form.save()
        messages.success(request, "Datos de la orden guardados.")
        return redirect("budgets:work_order_detail", pk=work_order.pk)

    @staticmethod
    def _work_order(request, pk):
        """
        The order of the user's company, or 404.

        ---

        La orden de la empresa del usuario, o 404.
        """
        return get_object_or_404(
            WorkOrderAssistance,
            pk=pk,
            company=request.user.company_user.company,
        )

    @staticmethod
    def _render(request, form, work_order):
        """
        Render the form page for this order.

        ---

        Pinta el formulario de esta orden.
        """
        return render(
            request, "budgets/services/work_order_form.html",
            _build_base_context(request, {
                "active_nav": "services_hub",
                "form": form,
                "page_heading": (
                    "Orden %s" % work_order.work_order_number
                ),
                "form_action": reverse(
                    "budgets:work_order_edit", args=[work_order.pk],
                ),
                "hints": {},
            }),
        )


CHAIN_WINDOW_HOURS = 24


def _chain(earlier, later):
    """
    How two albaranes of the same driver were chained.

    ---

    Cómo se encadenaron dos albaranes del mismo conductor: "en ruta" si
    el siguiente salió antes de cerrar el anterior en base (salió desde
    donde estaba), "en base" si salió después.
    """
    if earlier.base_closed_at is None or (
        earlier.base_closed_at > later.started_at
    ):
        return "en ruta"
    return "en base"


def _chained_units(unit):
    """
    (previous, next) albarán of the same driver, each with its chaining.

    ---

    El albarán anterior y el siguiente del mismo conductor (S138, rutas
    encadenadas), salidos a menos de CHAIN_WINDOW_HOURS, cada uno como
    (albarán, "en ruta" | "en base"); None si no hay.
    """
    import datetime

    from budgets.models import WorkOrderAssistanceUnit

    if not unit.operator_id or unit.started_at is None:
        return None, None
    window = datetime.timedelta(hours=CHAIN_WINDOW_HOURS)
    others = WorkOrderAssistanceUnit.objects.filter(
        operator_id=unit.operator_id,
        started_at__isnull=False,
        started_at__gte=unit.started_at - window,
        started_at__lte=unit.started_at + window,
    ).exclude(pk=unit.pk).exclude(
        status=WorkOrderAssistanceUnit.STATUS_CANCELLED,
    ).select_related("work_order")
    before = [o for o in others if o.started_at < unit.started_at]
    after = [o for o in others if o.started_at > unit.started_at]
    previous = max(before, key=lambda o: o.started_at) if before else None
    following = min(after, key=lambda o: o.started_at) if after else None
    return (
        (previous, _chain(previous, unit)) if previous else None,
        (following, _chain(unit, following)) if following else None,
    )


class UnitRouteView(AssistanceSupervisorAccessMixin, View):
    """
    Route of an albarán on the map, with its stops.

    ---

    Ruta de un albarán en el mapa con las detenciones del vehículo
    (H37, S138; budgets.service_route).
    """

    template_name = "budgets/services/unit_route.html"

    def get(self, request, pk):
        """
        Render the route page.

        ---

        Pinta la página de la ruta.
        """
        from budgets.models import WorkOrderAssistanceUnit
        from budgets.service_route import (
            STOP_MIN_MINUTES, STOP_RADIUS_M, build_route,
        )

        unit = get_object_or_404(
            WorkOrderAssistanceUnit.objects.select_related(
                "work_order", "work_order__insurer", "operator__user",
            ),
            pk=pk,
            work_order__company=request.user.company_user.company,
        )
        operator = unit.operator.user if unit.operator_id else None
        previous, following = _chained_units(unit)
        return render(request, self.template_name, {
            "previous": previous,
            "following": following,
            "unit": unit,
            "work_order": unit.work_order,
            "driver": (
                (operator.get_full_name() or operator.username)
                if operator else ""
            ),
            "route": build_route(unit),
            "stop_minutes": STOP_MIN_MINUTES,
            "stop_radius": STOP_RADIUS_M,
            "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            "google_maps_map_id": os.environ.get("GOOGLE_MAPS_MAP_ID", ""),
        })


class ServicesChainedView(AssistanceSupervisorAccessMixin, View):
    """
    Internal summary of the services chained on the road.

    ---

    Resumen interno de los servicios encadenados en ruta (H37, S138,
    Miguel Ángel: "a final de año, ¿cuántos kilómetros nos hemos
    ahorrado que hemos facturado sin tener que hacerlos al encadenar?").
    Entre dos fechas (por defecto, el año en curso): cada encadenamiento
    con los km del chófer, los hechos hasta el cambio y los cobrados sin
    hacer, y los totales. Solo oficina.
    """

    template_name = "budgets/services/chained.html"

    def get(self, request):
        """
        Render the summary.

        ---

        Pinta el resumen.
        """
        import datetime

        from django.utils import timezone

        from budgets.models import WorkOrderAssistanceUnit

        today = timezone.localdate()
        try:
            since = datetime.date.fromisoformat(request.GET.get("desde", ""))
        except ValueError:
            since = today.replace(month=1, day=1)
        try:
            until = datetime.date.fromisoformat(request.GET.get("hasta", ""))
        except ValueError:
            until = today
        units = list(WorkOrderAssistanceUnit.objects.filter(
            work_order__company=request.user.company_user.company,
            chained_to__isnull=False,
            chain_at__date__gte=since,
            chain_at__date__lte=until,
        ).select_related(
            "work_order__insurer", "chained_to", "operator__user",
        ).order_by("chain_at"))
        saved = [u.chain_saved_km for u in units]
        estimated = [u.chain_return_minutes_est for u in units]
        return render(request, self.template_name, {
            "units": units,
            "since": since,
            "until": until,
            "total_saved": sum(km for km in saved if km is not None),
            "total_billed": sum(
                u.billed_km for u in units if u.billed_km is not None
            ),
            "total_minutes": sum(m for m in estimated if m is not None),
            "without_km": sum(1 for km in saved if km is None),
        })


class RouteTestListView(AssistanceSupervisorAccessMixin, View):
    """
    Routes recorded with the test button of the driver app.

    ---

    Rutas grabadas con el botón de prueba de la app (H37, S140), las
    más nuevas primero.
    """

    template_name = "budgets/services/route_tests.html"

    def get(self, request):
        """
        Render the list.

        ---

        Pinta la lista.
        """
        from django.db.models import Count

        from budgets.models import RouteTest

        routes = RouteTest.objects.filter(
            company_user__company=request.user.company_user.company,
        ).select_related("company_user__user").annotate(
            point_count=Count("points"),
        )[:100]
        return render(request, self.template_name, {"routes": routes})


class RouteTestView(AssistanceSupervisorAccessMixin, View):
    """
    One test route on the map, point by point.

    ---

    Una prueba de ruta en el mapa, punto a punto, con su precisión y
    los huecos entre puntos, para ver cómo graba el móvil.
    """

    template_name = "budgets/services/route_test.html"

    def get(self, request, pk):
        """
        Render the route.

        ---

        Pinta la ruta.
        """
        from django.utils import timezone

        from budgets.models import RouteTest
        from budgets.service_route import distance_m

        route = get_object_or_404(
            RouteTest.objects.select_related("company_user__user"),
            pk=pk,
            company_user__company=request.user.company_user.company,
        )
        rows = list(route.points.values_list(
            "latitude", "longitude", "accuracy_m", "recorded_at",
        ))
        points = []
        meters = 0.0
        max_gap = 0
        previous = None
        for lat, lng, accuracy, at in rows:
            point = (float(lat), float(lng))
            if previous is not None:
                meters += distance_m(previous[0], point)
                max_gap = max(
                    max_gap, int((at - previous[1]).total_seconds()),
                )
            previous = (point, at)
            points.append({
                "lat": point[0],
                "lng": point[1],
                "acc": accuracy,
                "t": timezone.localtime(at).strftime("%H:%M:%S"),
            })
        accuracies = [p["acc"] for p in points if p["acc"] is not None]
        user = route.company_user.user
        return render(request, self.template_name, {
            "route": route,
            "driver": user.get_full_name() or user.username,
            "points": points,
            "count": len(points),
            "km": round(meters / 1000, 2),
            "minutes": round(
                (route.finished_at - route.started_at).total_seconds() / 60,
                1,
            ),
            "max_gap": max_gap,
            "mean_accuracy": (
                round(sum(accuracies) / len(accuracies)) if accuracies
                else None
            ),
            "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            "google_maps_map_id": os.environ.get("GOOGLE_MAPS_MAP_ID", ""),
        })


class WorkOrderInvoiceSimulationView(AssistanceSupervisorAccessMixin, View):
    """
    Invoice simulation of a finished order with the insurer tariff.

    ---

    Simulación de factura de una orden terminada con la tarifa de la
    aseguradora (S140). No guarda nada.
    """

    template_name = "budgets/services/invoice_simulation.html"

    def get(self, request, pk):
        """
        Price the closed albaranes and show the lines.

        ---

        Valora los albaranes cerrados y muestra las líneas.
        """
        from budgets.service_invoice import simulate_order

        work_order = get_object_or_404(
            WorkOrderAssistance.objects.select_related(
                "insurer", "vehicle_type",
            ),
            pk=pk,
            company=request.user.company_user.company,
        )
        ctx = _build_base_context(request, {
            "work_order": work_order,
            "simulation": simulate_order(work_order),
            "active_nav": "work_orders",
        })
        return render(request, self.template_name, ctx)


def _xlsx_response(workbook, filename):
    """
    Workbook as a download.

    ---

    El libro como descarga.
    """
    import io

    from django.http import HttpResponse

    buffer = io.BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


_MONEY_FORMAT = "#,##0.00"


class WorkOrderInvoiceSimulationExcelView(
    AssistanceSupervisorAccessMixin, View,
):
    """
    Invoice simulation of the order as an Excel workbook.

    ---

    La simulación de factura de la orden en un Excel (S140): una fila
    por concepto, con unidades, precio e importe.
    """

    def get(self, request, pk):
        """
        Build and return the workbook.

        ---

        Construye y devuelve el libro.
        """
        from decimal import Decimal

        from openpyxl import Workbook
        from openpyxl.styles import Font

        from budgets.service_invoice import simulate_order

        work_order = get_object_or_404(
            WorkOrderAssistance.objects.select_related("insurer"),
            pk=pk,
            company=request.user.company_user.company,
        )
        simulation = simulate_order(work_order)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "SIMULACION FACTURA"
        bold = Font(bold=True)
        sheet.append(["Orden", work_order.work_order_number])
        sheet.append([
            "Aseguradora",
            work_order.insurer.name if work_order.insurer else "",
        ])
        sheet.append(["Expediente", work_order.expediente or ""])
        sheet.append([])
        sheet.append(["Albarán", "Concepto", "Unidades", "Precio", "%", "Importe"])
        for cell in sheet[sheet.max_row]:
            cell.font = bold
        for row in simulation["results"]:
            # S140: the albarán number only on the first row of its block.
            # El número de albarán solo en la primera fila de su bloque.
            first = [row["unit"].albaran_number]

            def label():
                return first.pop() if first else None

            number = None
            if row["error"]:
                number = label()
                sheet.append([number, row["error"]])
                continue
            for line in row["lines"]:
                number = label()
                if line.is_surcharge:
                    sheet.append([
                        number, line.concept_label, None, None,
                        float(line.unit_price * Decimal("100")),
                        float(line.subtotal),
                    ])
                else:
                    sheet.append([
                        number, line.concept_label, float(line.units),
                        float(line.unit_price), None, float(line.subtotal),
                    ])
            sheet.append([label(), "Total sin IVA", None, None, None, float(row["total"])])
            sheet[sheet.max_row][1].font = bold
            iva = row["iva_line"]
            if iva is not None:
                sheet.append([
                    label(), iva.concept_label, None, None,
                    float(iva.unit_price * Decimal("100")),
                    float(iva.subtotal),
                ])
            if row["total_with_iva"] is not None:
                sheet.append([
                    label(), "Total con IVA", None, None, None,
                    float(row["total_with_iva"]),
                ])
                sheet[sheet.max_row][1].font = bold
        if len(simulation["results"]) > 1:
            sheet.append([])
            sheet.append(["", "Total de la orden sin IVA", None, None, None, float(simulation["total"])])
            if simulation["total_with_iva"] is not None:
                sheet.append([
                    "", "Total de la orden con IVA", None, None, None,
                    float(simulation["total_with_iva"]),
                ])
        for column in ("C", "D", "E", "F"):
            for cell in sheet[column][5:]:
                cell.number_format = _MONEY_FORMAT
        sheet.column_dimensions["A"].width = 16
        sheet.column_dimensions["B"].width = 42
        for column in ("C", "D", "E", "F"):
            sheet.column_dimensions[column].width = 12
        return _xlsx_response(
            workbook,
            f"simulacion_factura_{work_order.work_order_number}.xlsx",
        )


class UnitAlbaranExcelView(AssistanceSupervisorAccessMixin, View):
    """
    One albarán as an Excel workbook (field and value).

    ---

    Un albarán en Excel (S140): una fila por dato, campo y valor, para
    pasarlo a otro programa.
    """

    def get(self, request, pk):
        """
        Build and return the workbook.

        ---

        Construye y devuelve el libro.
        """
        from django.utils import timezone
        from openpyxl import Workbook
        from openpyxl.styles import Font

        from budgets.models import WorkOrderAssistanceUnit

        unit = get_object_or_404(
            WorkOrderAssistanceUnit.objects.select_related(
                "work_order__insurer", "operator__user", "departure_base",
                "arrival_base",
            ),
            pk=pk,
            work_order__company=request.user.company_user.company,
        )
        order = unit.work_order
        user = unit.operator.user if unit.operator_id else None
        signature = getattr(unit, "signature", None)

        def when(value):
            if value is None:
                return None
            return timezone.localtime(value).replace(tzinfo=None)

        def num(value):
            return float(value) if value is not None else None

        def yes_no(value):
            return "Sí" if value else "No"

        rows = [
            ("Albarán", unit.albaran_number),
            ("Fecha del servicio", order.service_date),
            ("Aseguradora", order.insurer.name if order.insurer else ""),
            ("Expediente", order.expediente or ""),
            ("Cliente", order.client_name or ""),
            ("Matrícula", order.vehicle_plate or ""),
            ("Vehículo", " ".join(
                part for part in (order.vehicle_brand, order.vehicle_model)
                if part
            )),
            ("Avería", order.breakdown_description or ""),
            ("Recogida", order.pickup_location or ""),
            ("Destino", order.destination or ""),
            ("Conductor", (
                (user.get_full_name() or user.username) if user else ""
            )),
            ("Máquina", unit.machine or ""),
            ("Ayudantes", ", ".join(unit.helper_names)),
            ("Estado", unit.get_status_display()),
            ("Base de salida", (
                unit.departure_base.name if unit.departure_base else ""
            )),
            ("Hora salida base", when(unit.started_at)),
            ("Km salida", num(unit.km_start)),
            ("Hora llegada al servicio", when(unit.arrived_at)),
            ("Km llegada al servicio", num(unit.km_arrival)),
            ("Km en la entrega", num(unit.km_delivery)),
            ("Km de vuelta a base", num(unit.km_return)),
            ("Km 1.º tramo", num(unit.phase1_km)),
            ("Km 2.º tramo", num(unit.phase2_km)),
            ("Horas de trabajo", num(unit.work_hours)),
            ("Horas de espera", num(unit.wait_hours)),
            ("Horas de rescate", num(unit.rescue_hours)),
            ("Nocturno", yes_no(unit.is_night)),
            ("Pernocta", yes_no(unit.is_overnight)),
            ("Firmado por", signature.signer_name if signature else ""),
            ("Fecha de la firma", when(signature.signed_at) if signature else None),
            ("Motivo sin firma", unit.unsigned_reason or ""),
            ("Cierre", (
                "En ruta" if unit.closed_in_route
                else "En base" if unit.base_arrived_at else ""
            )),
            ("Hora de cierre en ruta", when(unit.chain_at) if unit.closed_in_route else None),
            ("Base de llegada", (
                unit.arrival_base.name if unit.arrival_base else ""
            )),
            ("Hora llegada base", when(unit.base_arrived_at)),
            ("Km llegada base", num(unit.base_km_end)),
            ("Litros repostados", num(unit.refuel_liters)),
            ("Notas del conductor", unit.driver_notes or ""),
        ]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ALBARAN"
        sheet.append(["Dato", "Valor"])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for label, value in rows:
            sheet.append([label, value])
            cell = sheet.cell(row=sheet.max_row, column=2)
            if label == "Fecha del servicio":
                cell.number_format = "DD/MM/YYYY"
            elif label.startswith(("Hora", "Fecha de la")):
                cell.number_format = "DD/MM/YYYY HH:MM"
        sheet.column_dimensions["A"].width = 26
        sheet.column_dimensions["B"].width = 60
        return _xlsx_response(
            workbook, f"albaran_{unit.albaran_number}.xlsx",
        )


class WorkOrderInvoicedView(AssistanceSupervisorAccessMixin, View):
    """
    Mark a completed order as invoiced, or undo it.

    ---

    Marca como facturada una orden completada, o lo deshace (S140,
    Miguel Ángel: al cerrar el albarán "no sale ningún sitio donde
    ponerlo como facturado").
    """

    def post(self, request, pk):
        """
        Change the status and go back to the order.

        ---

        Cambia el estado y vuelve a la orden.
        """
        work_order = get_object_or_404(
            WorkOrderAssistance,
            pk=pk,
            company=request.user.company_user.company,
        )
        if request.POST.get("undo"):
            if work_order.status == WorkOrderAssistance.STATUS_INVOICED:
                work_order.status = WorkOrderAssistance.STATUS_COMPLETED
                work_order.save(update_fields=["status", "updated_at"])
                work_order.refresh_status()
                messages.success(request, "Orden ya no está facturada.")
        elif work_order.status == WorkOrderAssistance.STATUS_COMPLETED:
            work_order.status = WorkOrderAssistance.STATUS_INVOICED
            work_order.save(update_fields=["status", "updated_at"])
            messages.success(
                request,
                "Orden %s marcada como facturada."
                % work_order.work_order_number,
            )
        else:
            messages.error(
                request,
                "Solo se puede facturar una orden completada (todos sus "
                "albaranes cerrados).",
            )
        return redirect("budgets:work_order_detail", pk=work_order.pk)


# ---------------------------------------------------------------------------
# H37 (S142, invasive session). Services tab: services uploaded from a
# folder, valued (estimated budget by tariff, cost and yield).
# Pestaña Servicios: servicios subidos desde una carpeta y valorados.
# ---------------------------------------------------------------------------

EVALUATIONS_SCREEN_KEY = "services_evaluations"


def _evaluations_params(request):
    """
    Filters of the Services list: GET, then POST (_f_ prefix).

    ---

    Filtros del listado de Servicios: los de GET y, en las acciones por
    POST, los vigentes con el prefijo _f_.
    """
    from budgets.service_evaluation import FILTER_KEYS

    return {
        key: request.GET.get(key) or request.POST.get("_f_" + key, "")
        for key in FILTER_KEYS
    }


def _evaluations_context(request):
    """
    Context of the Services table fragment.

    ---

    Contexto del fragmento de tabla de Servicios: filas, filtros
    vigentes, controles de orden y si queda alguno por valorar (para
    refrescar la tabla sola), resueltos aquí (plantillas tontas).
    """
    from budgets import service_evaluation

    company = request.user.company_user.company
    params = _evaluations_params(request)
    only_selected = request.GET.get("only_selected") == "1"
    only_keys = None
    if only_selected:
        only_keys = {
            key for key in request.GET.get("selected_ids", "").split(",")
            if key
        }
    rows = service_evaluation.build_rows(company, params, only_keys)
    return {
        "rows": rows,
        "has_waiting": any(row.is_waiting for row in rows),
        "filter_search": params["search"],
        "filter_state": params["state"],
        "filter_insurer": params["insurer"],
        "filter_date_from": params["date_from"],
        "filter_date_to": params["date_to"],
        "only_selected": only_selected,
        "is_filtered": bool(
            params["search"] or params["state"] or params["insurer"]
            or params["date_from"] or params["date_to"] or only_selected
        ),
        **service_evaluation.sort_controls(params["sort"]),
    }


def _open_services_tab(company_user):
    """
    Leave the Services tab active for the user (directive 4.15).

    ---

    Deja activa la pestaña Servicios del usuario, para volver a ella
    tras subir una carpeta o lanzar una acción.
    """
    nav_state, _created = PanelNavigationState.objects.get_or_create(
        company_user=company_user, screen_key=SCREEN_KEY,
        defaults={"state": {}},
    )
    state = nav_state.state if isinstance(nav_state.state, dict) else {}
    state["active_tab"] = "servicios"
    nav_state.state = state
    nav_state.save(update_fields=["state"])


class ServicesEvaluationsPaneView(AssistanceSupervisorAccessMixin, View):
    """
    Services tab: uploaded services, valued and sorted.

    ---

    Pestaña Servicios: los servicios subidos desde una carpeta con su
    presupuesto estimado según tarifa, su coste estimado y su
    rendimiento, con el formato de la directriz 4.24 (filtros, orden y
    selección guardados por usuario, directriz 4.15).
    """

    template_name = "budgets/services/_evaluations_pane.html"

    def get(self, request):
        """
        Render the tab content.

        ---

        Pinta el contenido de la pestaña.
        """
        from budgets.service_evaluation import FILTER_KEYS
        from panel.navigation_persistence import (
            apply_list_navigation,
            get_saved_state_key,
        )

        company_user = request.user.company_user
        apply_list_navigation(request, EVALUATIONS_SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            company_user, EVALUATIONS_SCREEN_KEY, "selection", [],
        )
        return render(request, self.template_name, {
            **_evaluations_context(request),
            "insurers": Insurer.objects.filter(
                company=company_user.company,
            ).order_by("name"),
            "can_edit_costs": company_user.is_admin_level,
            "screen_key": EVALUATIONS_SCREEN_KEY,
            "saved_selection": (
                saved_selection if isinstance(saved_selection, list) else []
            ),
        })


class ServicesEvaluationsFragmentView(AssistanceSupervisorAccessMixin, View):
    """
    Services table fragment (filters, order, selection, refresh).

    ---

    Fragmento de tabla de Servicios, para filtros, orden, "mostrar solo
    la selección" y el refresco mientras hay servicios por valorar.
    """

    def get(self, request):
        """
        Return the table fragment.

        ---

        Devuelve el fragmento de tabla.
        """
        from budgets.service_evaluation import FILTER_KEYS
        from panel.navigation_persistence import apply_list_navigation

        apply_list_navigation(request, EVALUATIONS_SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "budgets/services/_evaluations_table.html",
            _evaluations_context(request),
        )


class ServicesEvaluationsUploadView(AssistanceSupervisorAccessMixin, View):
    """
    Upload a folder of service documents to value them.

    ---

    Sube una carpeta de documentos de servicios (fotos o PDF de TIREA):
    cada uno se guarda y se manda a valorar al worker. Lo que no es
    foto ni PDF se salta. La pestaña la manda por tandas (fetch, cabecera
    X-Requested-With: fetch) y recibe los contadores en JSON, para no
    pasar del límite de archivos por petición de Django (100) ni del
    tiempo de una petición; sin JavaScript, vuelve a la pestaña.
    """

    def post(self, request):
        """
        Queue every accepted file of the folder.

        ---

        Encola cada archivo aceptado de la carpeta.
        """
        from budgets.service_evaluation import content_type_of, queue_upload

        company_user = request.user.company_user
        queued, skipped, failed = 0, 0, 0
        for upload in request.FILES.getlist("documents"):
            content_type = content_type_of(upload)
            if not content_type:
                skipped += 1
                continue
            if queue_upload(company_user, upload, content_type) is None:
                failed += 1
            else:
                queued += 1
        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({
                "queued": queued, "skipped": skipped, "failed": failed,
            })
        if queued:
            messages.success(
                request,
                "%d documento(s) en cola para valorar. La tabla se "
                "actualiza sola." % queued,
            )
        if skipped:
            messages.warning(
                request,
                "%d archivo(s) saltados: no son foto (JPG, PNG, WEBP) ni "
                "PDF." % skipped,
            )
        if failed:
            messages.error(
                request,
                "%d documento(s) no se pudieron guardar. Vuelve a "
                "subirlos." % failed,
            )
        if not (queued or skipped or failed):
            messages.error(request, "La carpeta no tiene archivos.")
        _open_services_tab(company_user)
        return redirect("budgets:services_hub")


class ServicesEvaluationsActionView(AssistanceSupervisorAccessMixin, View):
    """
    Mass actions on the selected services: value again or delete.

    ---

    Acciones sobre los servicios seleccionados: volver a valorarlos
    (leer el documento y calcular de nuevo) o borrarlos. Al borrar, su
    documento se borra del cubo salvo que ya sea el de una orden.
    """

    def post(self, request, action):
        """
        Run the action on the selection.

        ---

        Ejecuta la acción sobre la selección.
        """
        from budgets.service_evaluation import requeue
        from chat.room_service import ATTACHMENT_BUCKET
        from spare_parts.gcs_service import delete_file

        company_user = request.user.company_user
        pks = [
            int(key[1:]) for key in request.POST.getlist("selected")
            if key.startswith("e") and key[1:].isdigit()
        ]
        evaluations = ServiceEvaluation.objects.filter(
            company=company_user.company, pk__in=pks,
        )
        if action == "requeue":
            count = 0
            for evaluation in evaluations:
                requeue(evaluation)
                count += 1
            messages.success(
                request, "%d servicio(s) en cola para valorar de nuevo." % (
                    count,
                ),
            )
        elif action == "delete":
            count = 0
            for evaluation in evaluations:
                blob = evaluation.source_document_blob
                if blob and not WorkOrderAssistance.objects.filter(
                    source_document_blob=blob,
                ).exists():
                    try:
                        delete_file(ATTACHMENT_BUCKET, blob)
                    except Exception:  # noqa: BLE001 -- se borra la fila
                        logger.exception(
                            "# [VALORACION] No se pudo borrar %s.", blob,
                        )
                evaluation.delete()
                count += 1
            messages.success(request, "%d servicio(s) borrados." % count)
        else:
            messages.error(request, "Acción no válida.")
        _open_services_tab(company_user)
        return redirect("budgets:services_hub")


class ServiceEvaluationDocumentView(AssistanceSupervisorAccessMixin, View):
    """
    Open the document of an uploaded service.

    ---

    Abre el documento de un servicio subido (enlace firmado al cubo).
    """

    def get(self, request, pk):
        """
        Redirect to the signed URL of the document.

        ---

        Redirige al enlace firmado del documento.
        """
        from chat.room_service import ATTACHMENT_BUCKET
        from spare_parts.gcs_service import generate_signed_url

        evaluation = get_object_or_404(
            ServiceEvaluation, pk=pk,
            company=request.user.company_user.company,
        )
        if not evaluation.source_document_blob:
            messages.error(request, "Este servicio no tiene documento.")
            return redirect("budgets:services_hub")
        return redirect(generate_signed_url(
            ATTACHMENT_BUCKET, evaluation.source_document_blob,
        ))


class ServiceEvaluationOrderView(AssistanceSupervisorAccessMixin, View):
    """
    Create the order of a valued service.

    ---

    Crea la orden de un servicio valorado: abre el formulario de alta
    relleno con los datos leídos (como la foto de TIREA), con su
    documento, para revisarlo y guardarlo. Al guardar, el servicio
    queda enlazado a su orden.
    """

    def get(self, request, pk):
        """
        Render the prefilled order form.

        ---

        Pinta el formulario de alta relleno.
        """
        from budgets.service_evaluation import restore_data

        company = request.user.company_user.company
        evaluation = get_object_or_404(
            ServiceEvaluation, pk=pk, company=company,
            status=ServiceEvaluation.STATUS_DONE,
        )
        if evaluation.work_order_id:
            messages.info(request, "Este servicio ya tiene su orden.")
            return redirect(
                "budgets:work_order_detail", pk=evaluation.work_order_id,
            )
        data = restore_data(evaluation.data)
        form = WorkOrderAssistanceForm(
            initial=_initial_from_extraction(company, data), company=company,
        )
        hints = {key: data[key] for key in _HINT_KEYS if key in data}
        return _render_order_form(
            request, form, "Nueva orden desde un servicio valorado",
            "budgets:work_order_save", hints,
            origin=WorkOrderAssistance.ORIGIN_PHOTO,
            source_token=room_service.sign_source(
                evaluation.source_document_blob,
                evaluation.source_document_type,
            ),
            evaluation_pk=str(evaluation.pk),
        )


class ServicesCostSettingsView(AdminRoleRequiredMixin, View):
    """
    Average costs used to value the services.

    ---

    Medias de coste para valorar los servicios (solo administración):
    precio del gasoil, coste por hora de operario y, por clase de
    vehículo, consumo, coste por km y tipos de máquina. Al guardar se
    recalcula el coste de todos los servicios valorados.
    """

    template_name = "budgets/services/cost_settings.html"

    def _context(self, request, settings, vehicles, errors=None):
        """
        Context of the page, with the machine types already marked and
        the real averages of the GasoGes refuels.

        ---

        Contexto de la página, con los tipos de máquina ya marcados por
        clase y las medias reales de los repostajes de GasoGes por clase
        y por vehículo (plantillas tontas).
        """
        from budgets.dispatch_vehicle import MACHINE_USES
        from budgets.fleet_fuel_averages import fleet_averages

        real = fleet_averages(request.user.company_user.company)
        type_names = list(MACHINE_USES)
        rows = []
        for vehicle in vehicles:
            marked = set(vehicle.type_names())
            rows.append({
                "vehicle": vehicle,
                "real": real["classes"].get(vehicle.name),
                "types": [
                    {"name": name, "checked": name in marked}
                    for name in type_names
                ],
            })
        return _build_base_context(request, {
            "active_nav": "services_hub",
            "settings": settings,
            "vehicle_rows": rows,
            "real": real,
            "has_real": bool(real["classes"] or real["fuel_price"]),
            "errors": errors or [],
        })

    def _use_real(self, request, company):
        """
        Copy the real averages into the settings and recompute.

        ---

        Copia las medias reales de los repostajes: consumo de cada clase
        que tenga datos y precio medio del gasoil. Las clases sin datos
        (las grúas apuntan horas) se quedan como estaban.
        """
        from budgets.fleet_fuel_averages import fleet_averages
        from budgets.models import AssistanceCostSettings
        from budgets.service_evaluation import recompute_company

        real = fleet_averages(company)
        settings = AssistanceCostSettings.for_company(company)
        if real["fuel_price"] is not None:
            settings.fuel_price_per_liter = real["fuel_price"]
            settings.save(update_fields=["fuel_price_per_liter",
                                         "updated_at"])
        applied = []
        for vehicle in company.assistance_vehicle_costs.all():
            averages = real["classes"].get(vehicle.name)
            if averages and averages["l_100km"] is not None:
                vehicle.fuel_liters_per_100km = averages["l_100km"]
                vehicle.save(update_fields=["fuel_liters_per_100km"])
                applied.append("%s %s l/100 km" % (
                    vehicle.name, averages["l_100km"],
                ))
        recompute_company(company)
        messages.success(
            request,
            "Medias reales aplicadas: %s%s. Coste y rendimiento "
            "recalculados." % (
                ", ".join(applied) or "ningún consumo",
                "; gasoil %s €/l" % real["fuel_price"]
                if real["fuel_price"] is not None else "",
            ),
        )
        return redirect("budgets:services_cost_settings")

    def get(self, request):
        """
        Render the averages.

        ---

        Pinta las medias.
        """
        from budgets.models import AssistanceCostSettings

        company = request.user.company_user.company
        settings = AssistanceCostSettings.for_company(company)
        vehicles = company.assistance_vehicle_costs.all()
        return render(
            request, self.template_name,
            self._context(request, settings, vehicles),
        )

    def post(self, request):
        """
        Save the averages and recompute the costs.

        ---

        Guarda las medias y recalcula los costes de los servicios.
        """
        from decimal import Decimal, InvalidOperation

        from budgets.models import AssistanceCostSettings
        from budgets.service_evaluation import recompute_company

        company = request.user.company_user.company
        if request.POST.get("action") == "use_real":
            return self._use_real(request, company)
        settings = AssistanceCostSettings.for_company(company)
        vehicles = list(company.assistance_vehicle_costs.all())
        errors = []

        def amount(name, label, required=False):
            raw = (request.POST.get(name) or "").strip().replace(",", ".")
            if not raw:
                if required:
                    errors.append("%s: falta el valor." % label)
                return None
            try:
                value = Decimal(raw)
            except InvalidOperation:
                errors.append("%s: «%s» no es un número." % (label, raw))
                return None
            if value < 0:
                errors.append("%s: no puede ser negativo." % label)
                return None
            return value

        settings.fuel_price_per_liter = amount(
            "fuel_price_per_liter", "Precio del gasoil",
        )
        settings.operator_cost_per_hour = amount(
            "operator_cost_per_hour", "Coste por operario",
        )
        for vehicle in vehicles:
            liters = amount(
                "liters_%d" % vehicle.pk, "Consumo de %s" % vehicle.name,
                required=True,
            )
            if liters is not None:
                vehicle.fuel_liters_per_100km = liters
            vehicle.cost_per_km = amount(
                "cost_km_%d" % vehicle.pk,
                "Coste por km de %s" % vehicle.name,
            )
            vehicle.machine_types = "\n".join(
                request.POST.getlist("types_%d" % vehicle.pk),
            )
        if errors:
            return render(
                request, self.template_name,
                self._context(request, settings, vehicles, errors),
            )
        settings.save()
        for vehicle in vehicles:
            vehicle.save()
        recompute_company(company)
        messages.success(
            request,
            "Medias guardadas. Coste y rendimiento recalculados en todos "
            "los servicios valorados.",
        )
        _open_services_tab(request.user.company_user)
        return redirect("budgets:services_hub")
