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

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from budgets.forms_services import WorkOrderAssistanceForm
from budgets.models import Insurer, WorkOrderAssistance
from budgets.views import _build_base_context
from panel.mixins import (
    AssistanceSupervisorAccessMixin,
    AssistanceWorkOrderAccessMixin,
)
from panel.models import PanelNavigationState

logger = logging.getLogger(__name__)

SCREEN_KEY = "services_hub"
TABS = ("albaranes",)
DEFAULT_TAB = "albaranes"


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
        company_user = request.user.company_user
        nav_state = PanelNavigationState.objects.filter(
            company_user=company_user, screen_key=SCREEN_KEY,
        ).first()
        state = nav_state.state if nav_state else {}
        if not isinstance(state, dict):
            state = {}
        active_tab = state.get("active_tab")
        if active_tab not in TABS:
            active_tab = DEFAULT_TAB
        ctx = _build_base_context(request, {
            "active_nav": "services_hub",
            "active_tab": active_tab,
            "screen_key": SCREEN_KEY,
        })
        return render(request, self.template_name, ctx)


class ServicesDeliveryNotesPaneView(AssistanceSupervisorAccessMixin, View):
    """
    Delivery notes tab: the assistance work orders.

    ---

    Pestaña Albaranes: las órdenes de trabajo de asistencia de la
    empresa, de la más reciente a la más antigua, con enlace a su
    detalle (alta de unidades y aviso al operario).
    """

    template_name = "budgets/services/_delivery_notes_pane.html"

    def get(self, request):
        """
        Render the tab content.

        ---

        Pinta el contenido de la pestaña.
        """
        company_user = request.user.company_user
        work_orders = WorkOrderAssistance.objects.filter(
            company=company_user.company,
        ).select_related("insurer").order_by(
            "-service_date", "-work_order_number",
        )
        return render(request, self.template_name, {
            "work_orders": work_orders,
        })


# ---------------------------------------------------------------------------
# H37 (S132). Order entry from the TIREA photo, manual entry and editing.
# Alta de la orden desde la foto de TIREA, alta a mano y edición.
# ---------------------------------------------------------------------------

ACCEPTED_UPLOAD_TYPES = (
    "image/jpeg", "image/png", "image/webp", "application/pdf",
)
# Keys of the extraction that are not model fields (hints for the form).
# Claves de la extracción que no son campos del modelo (pistas).
_HINT_KEYS = ("insurer_name", "client_company", "tirea_driver",
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
    insurer = _match_insurer(company, data.get("insurer_name"))
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


def _render_order_form(request, form, title, action_url, hints=None):
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
        try:
            data = extract_tirea_albaran(upload.read(), upload.content_type)
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
        return _render_order_form(
            request, form, "Nueva orden desde TIREA",
            "budgets:work_order_save", hints,
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
        if not form.is_valid():
            return _render_order_form(
                request, form, "Nueva orden", "budgets:work_order_save",
            )
        work_order = form.save(commit=False)
        work_order.company = company_user.company
        work_order.operator = company_user
        work_order.created_by = company_user
        form.save()
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
