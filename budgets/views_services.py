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
from django.shortcuts import render
from django.views import View

from budgets.views import _build_base_context
from panel.mixins import AssistanceSupervisorAccessMixin
from panel.models import PanelNavigationState

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
        from budgets.models import WorkOrderAssistance

        company_user = request.user.company_user
        work_orders = WorkOrderAssistance.objects.filter(
            company=company_user.company,
        ).select_related("insurer").order_by(
            "-service_date", "-work_order_number",
        )
        return render(request, self.template_name, {
            "work_orders": work_orders,
        })
