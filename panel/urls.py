
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
    CompanyUserSectionUnlinkView,
    SectionListView,
    SectionCreateView,
    SectionUpdateView,
    ContactListView,
    ContactCreateView,
    ContactUpdateView,
    ContactDeleteView,
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
    OperatorDashboardView,
    WorkshopAssetAutocompleteView,
    WorkshopAssetDetailView,
    WorkOrderEntryUploadView,
    WorkOrderEntryConfirmView,
    WorkOrderEntryFormView,
    WorkOrderEntryHistoryView,
    WorkOrderAdminHistoryView,
    WorkerAbsenceCreateView,
    MachineAssetListView,
    MachineAssetAnalyticsView,
    WorkOrderDescriptionAutocompleteView,
    WorkshopIntensiveToggleView,
    MachineAssetCreateView,
    MachineAssetUpdateView,
    MachineAssetDeactivateView,
    MachineAssetReactivateView,
    MachineAssetDeleteView,
    WorkerAbsenceUpdateView,
    WorkerAbsenceDeleteView,
    WorkOrderAdminExportView,
    WorkPeriodListView,
    WorkPeriodCreateView,
    WorkPeriodCloseView,
    WorkOrderMachineFilterView,
    DigitalWorkOrderListView,
    WorkdayScheduleView,
    AbsenceCategoryListView,
    AbsenceCategoryCreateView,
    AbsenceCategoryUpdateView,
    AbsenceCategoryToggleView,
    SectionDefaultRoleView,
    CompanyUserBulkDeleteView,
    WorkerScheduleUpdateView,
    OwnProfileView,
    TrustDeviceView,
    TrustDeviceToggleView,
    TrustDeviceQuickLoginView,
    CompanySettingsView,
    ExportTemplateListView,
    ExportTemplateCreateView,
    ExportTemplateUpdateView,
    ExportTemplateDeleteView,
    WorkOrderAdminExportByTemplateView,
    WorkOrderEntrySaveDateView,
    MachineAssetAutocompleteView,
)

from chat.views import (
    ChatRoomListView,
    ChatRoomView,
    ChatMessagesPollingView,
    ChatSendView,
    ChatAliasSetView,
    BreakdownRoomManageView,
)
from chat.views_tickets import (
    BreakdownTicketListView,
    BreakdownTicketDetailView,
    BreakdownTicketCreateView,
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

    # Worker absence create — Alta de ausencia de operario desde admin history (rol SUPERVISOR y ADMIN).
    # Cuarta Accion — Hito 7 (2026-05-08)
    path("worker-absences/create/", WorkerAbsenceCreateView.as_view(), name="worker_absence_create"),

    # WorkerAbsence update and delete — Edición y baja de ausencias (rol SUPERVISOR y ADMIN).
    # 2ª Acción — Hito 7 Sesión 017 (2026-05-08)
    path("worker-absences/<int:pk>/update/", WorkerAbsenceUpdateView.as_view(), name="worker_absence_update"),
    path("worker-absences/<int:pk>/delete/", WorkerAbsenceDeleteView.as_view(), name="worker_absence_delete"),

    # Operator dashboard — Selector de vía de entrada de partes (rol WORKSHOP y ADMIN).
    # Paso 2 — Hito 7 (2026-04-27)
    path("operator/", OperatorDashboardView.as_view(), name="operator_dashboard"),

    # Presence management — Gestión de presencia propia.
    path("presence/", PresenceStatusUpdateView.as_view(), name="presence_status"),

    # User management — Gestión de usuarios de empresa.
    path("users/", CompanyUserListView.as_view(), name="user_list"),
    path("users/create/", CompanyUserCreateView.as_view(), name="user_create"),
    path("users/bulk-delete/", CompanyUserBulkDeleteView.as_view(), name="user_bulk_delete"),
    path("users/<int:pk>/edit/", CompanyUserUpdateView.as_view(), name="user_edit"),
    path("users/<int:pk>/schedule/", WorkerScheduleUpdateView.as_view(), name="worker_schedule_update"),
    path("users/<int:pk>/unlink-section/", CompanyUserSectionUnlinkView.as_view(), name="user_unlink_section"),

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
    path("contacts/<int:pk>/delete/", ContactDeleteView.as_view(), name="contact_delete"),

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
    # Vía C (Upload + Confirm) desactivada en H07/S051 — código preservado para reactivación.
    # path("operator/upload/", WorkOrderEntryUploadView.as_view(), name="operator_upload"),
    # path("operator/confirm/", WorkOrderEntryConfirmView.as_view(), name="operator_confirm"),
    path("operator/assets/", WorkshopAssetAutocompleteView.as_view(), name="operator_assets"),
    path("operator/assets/detail/", WorkshopAssetDetailView.as_view(), name="operator_asset_detail"),  # PASO 4.1 — Hito 7 (sesión 011)
    path("operator/form/", WorkOrderEntryFormView.as_view(), name="operator_form"),
    # Operator form edit — Edición de parte digital no revisado desde Mi historial.
    # S019 — Hito 7 (2026-05-11)
    path("operator/form/<int:wo_pk>/edit/", WorkOrderEntryFormView.as_view(), name="operator_form_edit"),

    # Operator merge — Resolucion de conflicto de parte duplicado (rol WORKSHOP y ADMIN).
    # Primera Accion — Hito 7 Sesion 018 (2026-05-11)

    # Operator gap resolution — Justificación de lagunas de jornada detectadas por Gate 4.
    # Paso E — CUARTA ACCION Hito 7 Sesion 029 (2026-05-14)

    # Description typeahead autocomplete — Autocompletado de descripciones (fault_description / repair_notes).
    # Tercer Fleco — Hito 7 (2026-05-05)
    path("operator/descriptions/", WorkOrderDescriptionAutocompleteView.as_view(), name="operator_descriptions"),
    path("operator/intensive-toggle/", WorkshopIntensiveToggleView.as_view(), name="operator_intensive_toggle"),

    # WorkOrder management — PDFs de partes de trabajo (rol SUPERVISOR y ADMIN).
    # Paso 7 — Hito 6 (2026-04-22) | Bloque G — Hito 8 (2026-04-28)
    path("work-orders/", WorkOrderListView.as_view(), name="work_order_list"),
    # Digital work-order list — Partes digitales (DIGITAL + GENERATED) para SUPERVISOR y ADMIN.
    # PRIMERA ACCION — Hito 7 Sesion 026 (2026-05-13)
    path("work-orders/digital/", DigitalWorkOrderListView.as_view(), name="digital_work_order_list"),
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

    # WorkOrderEntry save date — Guardado de fecha de grupo via HTMX (incidencia S046).
    path("work-orders/<int:wo_pk>/entries/<int:entry_pk>/save-date/",
         WorkOrderEntrySaveDateView.as_view(),
         name="work_order_entry_save_date"),

    # MachineAsset autocomplete JSON — Autocompletado de activo en editor inline (incidencia S046).
    path("fleet/autocomplete/", MachineAssetAutocompleteView.as_view(), name="fleet_autocomplete"),

    # WorkOrder review toggle — Marcar/desmarcar revisión HTMX (rol SUPERVISOR y ADMIN).
    # Paso 7 — Hito 8 (2026-04-28)
    path("work-orders/<int:pk>/review/", WorkOrderMarkReviewedView.as_view(), name="work_order_review"),
    path("work-orders/<int:pk>/review-badge/", WorkOrderMarkReviewedView.as_view(), name="work_order_review_badge"),

    # WorkOrder duplicate search — Búsqueda HTMX de duplicados (rol SUPERVISOR y ADMIN).
    # Paso 13 — Hito 8 (2026-04-29)
    path("work-orders/machines/",
         WorkOrderMachineFilterView.as_view(),
         name="work_order_machine_filter"),
    path("work-orders/duplicates/search/", WorkOrderDuplicateSearchView.as_view(), name="work_order_duplicates_search"),

    # WorkOrder duplicate delete — Eliminación HTMX de duplicado concreto (rol ADMIN).
    # Paso 13 — Hito 8 (2026-04-29)
    path("work-orders/duplicates/<int:pk>/delete/", WorkOrderDuplicateDeleteView.as_view(), name="work_order_duplicate_delete"),

    # WorkOrder Excel export — Concatenación de Excels de partes seleccionados (rol SUPERVISOR y ADMIN).
    # Paso 6/8 — Hito 8 (2026-04-28)
    path("work-orders/export/", WorkOrderExportView.as_view(), name="work_order_export"),

    # WorkOrder admin export — Exportación Excel de partes digitales/generados (rol SUPERVISOR y ADMIN).
    # 4ª Acción — Hito 7 Sesión 017 (2026-05-08)
    path("work-orders/admin-export/", WorkOrderAdminExportView.as_view(), name="work_order_admin_export"),

    # WorkOrder admin history — Historial de gestión para ADMIN y SUPERVISOR (cuatro pestañas).
    # 1ª Acción — Hito 7 Sesión 016 (2026-05-08)
    path("work-orders/history/", WorkOrderAdminHistoryView.as_view(), name="work_order_admin_history"),

    # Work period management — CRUD de periodos de trabajo para SUPERVISOR y ADMIN.
    # 1ª Acción — Hito 7 Sesión 017 (2026-05-08)
    path("work-periods/", WorkPeriodListView.as_view(), name="work_period_list"),
    path("work-periods/create/", WorkPeriodCreateView.as_view(), name="work_period_create"),
    path("work-periods/close/", WorkPeriodCloseView.as_view(), name="work_period_close"),

    # Workday schedule management — Gestión de horarios de jornada (rol SUPERVISOR y ADMIN).
    # Paso G — CUARTA ACCION Hito 7 Sesion 029 (2026-05-14)
    path("workday-schedule/", WorkdayScheduleView.as_view(), name="workday_schedule"),

    # Absence category management — Gestión de categorías de ausencia (rol SUPERVISOR y ADMIN).
    # Paso G — CUARTA ACCION Hito 7 Sesion 029 (2026-05-14)
    path("absence-categories/", AbsenceCategoryListView.as_view(), name="absence_category_list"),
    path("absence-categories/create/", AbsenceCategoryCreateView.as_view(), name="absence_category_create"),
    path("absence-categories/<int:pk>/update/", AbsenceCategoryUpdateView.as_view(), name="absence_category_update"),
    path("absence-categories/<int:pk>/toggle/", AbsenceCategoryToggleView.as_view(), name="absence_category_toggle"),

    # Subtarea 9.6 — Hito 6 (2026-04-27)

    # Subtarea 9.6 — Hito 6 (2026-04-27)

    # Subtarea 9.6.1 — Hito 6 (2026-04-27)


    # Fleet / Centros de gasto — Hito 12 Paso 4
    path("fleet/", MachineAssetListView.as_view(), name="fleet_list"),
    path("fleet/create/", MachineAssetCreateView.as_view(), name="fleet_create"),
    path("fleet/<int:pk>/update/", MachineAssetUpdateView.as_view(), name="fleet_update"),
    path("fleet/<int:pk>/deactivate/", MachineAssetDeactivateView.as_view(), name="fleet_deactivate"),
    path("fleet/<int:pk>/reactivate/", MachineAssetReactivateView.as_view(), name="fleet_reactivate"),
    path("fleet/<int:pk>/delete/", MachineAssetDeleteView.as_view(), name="fleet_delete"),
    # Fleet analytics — Hito 12 Paso PRIORIDAD 2
    path("fleet/analytics/", MachineAssetAnalyticsView.as_view(), name="fleet_analytics"),

    # Section default role — Endpoint AJAX para pre-rellenar rol al crear usuario (H13).
    path("sections/<int:pk>/default-role/", SectionDefaultRoleView.as_view(), name="section_default_role"),

    # Chat IRC — Salas de chat por sección (Hito 13 Paso 4).
    path("chat/", ChatRoomListView.as_view(), name="chat_room_list"),
    path("chat/<int:room_pk>/", ChatRoomView.as_view(), name="chat_room_detail"),
    path("chat/<int:room_pk>/messages/", ChatMessagesPollingView.as_view(), name="chat_room_messages"),
    path("chat/<int:room_pk>/send/", ChatSendView.as_view(), name="chat_room_send"),
    path("chat/alias/set/", ChatAliasSetView.as_view(), name="chat_alias_set"),

    # Breakdown tickets — Gestión de tickets de avería (Hito 13 Paso 12).
    path("chat/breakdowns/tickets/", BreakdownTicketListView.as_view(), name="breakdown_ticket_list"),
    path("chat/breakdowns/tickets/<int:pk>/", BreakdownTicketDetailView.as_view(), name="breakdown_ticket_detail"),
    # Breakdown ticket create — Creación manual de ticket desde el panel (Hito 14 Paso 3).
    path("chat/breakdowns/tickets/create/", BreakdownTicketCreateView.as_view(), name="breakdown_ticket_create"),
    path("chat/breakdowns/manage/", BreakdownRoomManageView.as_view(), name="breakdown_room_manage"),

    # Own profile — Perfil propio del operario: edición de alias de chat (Hito 14 Paso 6).
    path("profile/", OwnProfileView.as_view(), name="own_profile"),

    # Trust device — Pregunta de confianza de dispositivo tras login (S039).
    path("trust-device/", TrustDeviceView.as_view(), name="trust_device"),

    # Trust device toggle — Dar/quitar confianza al dispositivo desde el perfil (S039).
    path("trust-device/toggle/", TrustDeviceToggleView.as_view(), name="trust_device_toggle"),

    # Trust device quick login — Acceso rápido desde login con cookie (S039).
    path("trust-device/quick-login/", TrustDeviceQuickLoginView.as_view(), name="trust_device_quick_login"),

    # Bot management — Panel de gestión del bot WhatsApp (Hito 13 Paso 17+).

    # Company settings — Configuración de empresa (bases operación, calendario laboral).
    # Hito 16 Paso 8 (2026-05-28)
    path("company/settings/", CompanySettingsView.as_view(), name="company_settings"),

    # Export templates CRUD — Plantillas de exportación Excel (Hito 19 / P6).
    path("export-templates/", ExportTemplateListView.as_view(), name="export_template_list"),
    path("export-templates/create/", ExportTemplateCreateView.as_view(), name="export_template_create"),
    path("export-templates/<int:pk>/update/", ExportTemplateUpdateView.as_view(), name="export_template_update"),
    path("export-templates/<int:pk>/delete/", ExportTemplateDeleteView.as_view(), name="export_template_delete"),

    # Export by template — Generación de Excel desde plantilla (Hito 19 / P6).
    path("work-orders/export-by-template/", WorkOrderAdminExportByTemplateView.as_view(), name="work_order_export_by_template"),
]
