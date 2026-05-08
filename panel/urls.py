# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/urls.py
"""
URL configuration for the panel application.
All routes are served under the /panel/ prefix defined in enterprise_core/urls.py.
---
Configuración de URLs para la aplicación panel.
Todas las rutas se sirven bajo el prefijo /panel/ definido en enterprise_core/urls.py.
"""

from django.urls import path

from panel.views import (
    PanelLoginView,
    PanelLogoutView,
    WorkerSignupView,
    PanelDashboardView,
    PresenceStatusUpdateView,
    CompanyUserListView,
    CompanyUserCreateView,
    CompanyUserUpdateView,
    SectionListView,
    SectionCreateView,
    SectionUpdateView,
    ContactListView,
    ContactCreateView,
    ContactUpdateView,
    CallFlowListView,
    CallFlowCreateView,
    CallFlowUpdateView,
    PhoneNumberListView,
    CorporateVoiceProfileUpdateView,
    BlockedCallerListView,
    BlockedCallerCreateView,
    BlockedCallerDeleteView,
    PanelPasswordChangeView,
    CallFlowRestoreView,
    VoiceProfileRestoreView,
    WhatsAppTemplateListView,
    WhatsAppActiveSessionListView,
    DataCaptureSetListView,
    DataCaptureSetCreateView,
    DataCaptureSetUpdateView,
    WorkOrderListView,
    WorkOrderUploadView,
    WorkOrderEditView,
    WorkOrderStatusFragmentView,
    WorkOrderLineSaveView,
    WorkOrderLineInsertView,
    WorkOrderLineReorderView,
    WorkOrderLineRestoreView,
    WorkOrderLineDeleteView,
    WorkOrderDeleteView,
    WorkOrderExportView,
    WorkOrderMarkReviewedView,
    WorkOrderDuplicateSearchView,
    WorkOrderDuplicateDeleteView,
    AnalyticsView,
    AnalyticsDataView,
    AnalyticsProfileListCreateView,
    AnalyticsProfileDeleteView,
    OperatorDashboardView,
    WorkshopAssetAutocompleteView,
    WorkshopAssetDetailView,
    WorkOrderEntryUploadView,
    WorkOrderEntryConfirmView,
    WorkOrderEntryFormView,
    WorkOrderEntrySTTView,
    WorkOrderEntrySTTExtractView,
    WorkOrderEntryHistoryView,
    MachineAssetListView,
    WorkOrderDescriptionAutocompleteView,
    MachineAssetCreateView,
    MachineAssetUpdateView,
    MachineAssetDeactivateView,
    MachineAssetReactivateView,
    MachineAssetDeleteView,
)

app_name = "panel"

urlpatterns = [
    # Authentication routes — Rutas de autenticación.
    # Worker public self-registration — Registro público de operarios de taller.
    # Hito 7 Primera Acción (2026-05-08)
    path("signup/", WorkerSignupView.as_view(), name="worker_signup"),
    path("login/", PanelLoginView.as_view(), name="login"),
    path("logout/", PanelLogoutView.as_view(), name="logout"),

    # Dashboard — Panel principal.
    path("", PanelDashboardView.as_view(), name="dashboard"),

    # Operator history — Historial de partes del operario (rol WORKSHOP y ADMIN).
    # Cuarta Accion — Hito 7 (2026-05-07)
    path("operator/history/", WorkOrderEntryHistoryView.as_view(), name="operator_history"),

    # Operator dashboard — Selector de vía de entrada de partes (rol WORKSHOP y ADMIN).
    # Paso 2 — Hito 7 (2026-04-27)
    path("operator/", OperatorDashboardView.as_view(), name="operator_dashboard"),

    # Presence management — Gestión de presencia propia.
    path("presence/", PresenceStatusUpdateView.as_view(), name="presence_status"),

    # User management — Gestión de usuarios de empresa.
    path("users/", CompanyUserListView.as_view(), name="user_list"),
    path("users/create/", CompanyUserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", CompanyUserUpdateView.as_view(), name="user_edit"),

    # Password management — Gestión de contraseña (todos los roles).
    path("password/change/", PanelPasswordChangeView.as_view(), name="password_change"),

    # Section management — Gestión de secciones.
    path("sections/", SectionListView.as_view(), name="section_list"),
    path("sections/create/", SectionCreateView.as_view(), name="section_create"),
    path("sections/<int:pk>/edit/", SectionUpdateView.as_view(), name="section_edit"),

    # Contact management — Gestión de contactos.
    path("contacts/", ContactListView.as_view(), name="contact_list"),
    path("contacts/create/", ContactCreateView.as_view(), name="contact_create"),
    path("contacts/<int:pk>/edit/", ContactUpdateView.as_view(), name="contact_edit"),

    # CallFlow management — Gestión de flujos IVR.
    path("callflows/", CallFlowListView.as_view(), name="callflow_list"),
    path("callflows/create/", CallFlowCreateView.as_view(), name="callflow_create"),
    path("callflows/<int:pk>/edit/", CallFlowUpdateView.as_view(), name="callflow_edit"),

    # PhoneNumber management — Gestión de números de teléfono (solo lectura).
    path("phonenumbers/", PhoneNumberListView.as_view(), name="phonenumber_list"),

    # CorporateVoiceProfile management — Gestión de perfil de voz corporativa.
    path("voiceprofile/", CorporateVoiceProfileUpdateView.as_view(), name="voiceprofile_detail"),
    path("voiceprofile/restore/", VoiceProfileRestoreView.as_view(), name="voiceprofile_restore"),

    # CallFlow restore — Restauración de flujo IVR a versión anterior.
    path("callflows/<int:pk>/restore/", CallFlowRestoreView.as_view(), name="callflow_restore"),

    # BlockedCaller management — Gestión de números bloqueados.
    path("blockedcallers/", BlockedCallerListView.as_view(), name="blockedcaller_list"),
    path("blockedcallers/create/", BlockedCallerCreateView.as_view(), name="blockedcaller_create"),
    path("blockedcallers/<int:pk>/delete/", BlockedCallerDeleteView.as_view(), name="blockedcaller_delete"),

    # WhatsApp template management — Gestión de plantillas WhatsApp (solo lectura, rol ADMIN).
    # Paso 24 — Hito 4 (2026-04-20)
    path("whatsapp/templates/", WhatsAppTemplateListView.as_view(), name="whatsapp_template_list"),

    # WhatsApp active sessions — Sesiones WhatsApp activas (rol ADMIN).
    # Paso 1 — Hito 5 (2026-04-20)
    path("whatsapp/sessions/", WhatsAppActiveSessionListView.as_view(), name="whatsapp_active_sessions"),

    # DataCaptureSet management — Gestión de conjuntos de captura de datos IVR (rol ADMIN).
    # Paso 8-pre — Hito 5 (2026-04-21)
    path("datacapturesets/", DataCaptureSetListView.as_view(), name="datacaptureset_list"),
    path("datacapturesets/create/", DataCaptureSetCreateView.as_view(), name="datacaptureset_create"),
    path("datacapturesets/<int:pk>/edit/", DataCaptureSetUpdateView.as_view(), name="datacaptureset_edit"),

    # Operator entry paths — Vías de entrada de partes del operario (rol WORKSHOP y ADMIN).
    # Paso 5 — Hito 7 (2026-04-29) | Paso 7 — Hito 7 (2026-04-30)
    path("operator/upload/", WorkOrderEntryUploadView.as_view(), name="operator_upload"),
    path("operator/confirm/", WorkOrderEntryConfirmView.as_view(), name="operator_confirm"),
    path("operator/assets/", WorkshopAssetAutocompleteView.as_view(), name="operator_assets"),
    path("operator/assets/detail/", WorkshopAssetDetailView.as_view(), name="operator_asset_detail"),  # PASO 4.1 — Hito 7 (sesión 011)
    path("operator/form/", WorkOrderEntryFormView.as_view(), name="operator_form"),
    path("operator/stt/",  WorkOrderEntrySTTView.as_view(),  name="operator_stt"),   # Paso 8 — Hito 7 (2026-04-30)
    path("operator/stt/extract/", WorkOrderEntrySTTExtractView.as_view(), name="operator_stt_extract"),  # Paso 8 — Hito 7 — Gemini extract

    # Description typeahead autocomplete — Autocompletado de descripciones (fault_description / repair_notes).
    # Tercer Fleco — Hito 7 (2026-05-05)
    path("operator/descriptions/", WorkOrderDescriptionAutocompleteView.as_view(), name="operator_descriptions"),

    # WorkOrder management — PDFs de partes de trabajo (rol SUPERVISOR y ADMIN).
    # Paso 7 — Hito 6 (2026-04-22) | Bloque G — Hito 8 (2026-04-28)
    path("work-orders/", WorkOrderListView.as_view(), name="work_order_list"),
    path("work-orders/upload/", WorkOrderUploadView.as_view(), name="work_order_upload"),
    path("work-orders/<int:pk>/edit/", WorkOrderEditView.as_view(), name="work_order_edit"),

    # WorkOrder delete — Eliminación de parte de trabajo (rol ADMIN).
    # Bugfix E2E — Hito 8 (2026-04-28)
    path("work-orders/<int:pk>/delete/", WorkOrderDeleteView.as_view(), name="work_order_delete"),

    # WorkOrder HTMX status fragment — Fragmento HTMX de estado de parte de trabajo.
    # Paso 1 — Hito 8 (2026-04-28)
    path("work-orders/<int:pk>/status/", WorkOrderStatusFragmentView.as_view(), name="work_order_status_fragment"),

    # WorkOrder HTMX line save — Guardado automático de línea por campo via HTMX.
    # Paso 2 — Hito 8 (2026-04-28)
    path("work-orders/<int:wo_pk>/lines/<int:line_pk>/save/", WorkOrderLineSaveView.as_view(), name="work_order_line_save"),

    # WorkOrder HTMX line insert — Inserción de línea vacía entre dos líneas existentes.
    # Paso 3 — Hito 8 (2026-04-28)
    path("work-orders/<int:wo_pk>/lines/insert/", WorkOrderLineInsertView.as_view(), name="work_order_line_insert"),

    # WorkOrder HTMX line reorder — Reordenado de líneas via drag & drop (SortableJS).
    # Paso 3 — Hito 8 (2026-04-28)
    path("work-orders/<int:wo_pk>/lines/reorder/", WorkOrderLineReorderView.as_view(), name="work_order_line_reorder"),

    # WorkOrder HTMX line restore — Restauración de grupo desde raw_gemini_response.
    # Paso 3 — Hito 8 (2026-04-28)
    path("work-orders/<int:wo_pk>/lines/<int:line_pk>/restore/", WorkOrderLineRestoreView.as_view(), name="work_order_line_restore"),

    # WorkOrder HTMX line delete — Eliminación de línea individual (rol ADMIN).
    # Bugfix E2E — Hito 8 (2026-04-28)
    path("work-orders/<int:wo_pk>/lines/<int:line_pk>/delete/", WorkOrderLineDeleteView.as_view(), name="work_order_line_delete"),

    # WorkOrder review toggle — Marcar/desmarcar revisión HTMX (rol SUPERVISOR y ADMIN).
    # Paso 7 — Hito 8 (2026-04-28)
    path("work-orders/<int:pk>/review/", WorkOrderMarkReviewedView.as_view(), name="work_order_review"),

    # WorkOrder duplicate search — Búsqueda HTMX de duplicados (rol SUPERVISOR y ADMIN).
    # Paso 13 — Hito 8 (2026-04-29)
    path("work-orders/duplicates/search/", WorkOrderDuplicateSearchView.as_view(), name="work_order_duplicates_search"),

    # WorkOrder duplicate delete — Eliminación HTMX de duplicado concreto (rol ADMIN).
    # Paso 13 — Hito 8 (2026-04-29)
    path("work-orders/duplicates/<int:pk>/delete/", WorkOrderDuplicateDeleteView.as_view(), name="work_order_duplicate_delete"),

    # WorkOrder Excel export — Concatenación de Excels de partes seleccionados (rol SUPERVISOR y ADMIN).
    # Paso 6/8 — Hito 8 (2026-04-28)
    path("work-orders/export/", WorkOrderExportView.as_view(), name="work_order_export"),

    # Analytics — Panel de analítica con gráficos Plotly (rol ADMIN).
    # Subtarea 9.6 — Hito 6 (2026-04-27)
    path("analytics/", AnalyticsView.as_view(), name="analytics"),

    # Analytics data endpoint — JSON payload para el constructor de gráficos client-side.
    # Subtarea 9.6 — Hito 6 (2026-04-27)
    path("analytics/data/", AnalyticsDataView.as_view(), name="analytics_data"),

    # Analytics profiles — Gestión de perfiles de gráfico guardados (rol ADMIN).
    # Subtarea 9.6.1 — Hito 6 (2026-04-27)
    path("analytics/profiles/", AnalyticsProfileListCreateView.as_view(), name="analytics_profile_list_create"),
    path("analytics/profiles/<int:pk>/", AnalyticsProfileDeleteView.as_view(), name="analytics_profile_delete"),

    # Fleet / Centros de gasto — Hito 12 Paso 4
    path("fleet/", MachineAssetListView.as_view(), name="fleet_list"),
    path("fleet/create/", MachineAssetCreateView.as_view(), name="fleet_create"),
    path("fleet/<int:pk>/update/", MachineAssetUpdateView.as_view(), name="fleet_update"),
    path("fleet/<int:pk>/deactivate/", MachineAssetDeactivateView.as_view(), name="fleet_deactivate"),
    path("fleet/<int:pk>/reactivate/", MachineAssetReactivateView.as_view(), name="fleet_reactivate"),
    path("fleet/<int:pk>/delete/", MachineAssetDeleteView.as_view(), name="fleet_delete"),
]
