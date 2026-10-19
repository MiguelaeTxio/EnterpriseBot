
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/urls.py
"""
URL configuration for the panel application.
All routes are served under the /panel/ prefix defined in enterprise_core/urls.py.
---
Configuración de URLs para la aplicación panel.
Todas las rutas se sirven bajo el prefijo /panel/ definido en enterprise_core/urls.py.
"""

from django.urls import path

from panel.views_task_photos import (
    TaskPhotoDeleteView,
    TaskPhotoUploadView,
    TaskPhotoWidgetView,
)
from panel.views_worksites import WorksiteDeleteView, WorksiteListView
from panel.views_circulars_h31 import (
    CircularCreateView,
    CircularEditView,
    CircularExportPdfView,
    CircularExportWordView,
    CircularGeneratePersonSearchView,
    CircularGenerateView,
    CircularImportDocumentView,
    CircularBulkSignatureView,
    CircularListView,
    CircularSaveContentView,
    PersonalDocutenExportView,
)
from panel.views_document_alerts import (
    DocumentAlertRulesSaveView,
    DocumentAlertsPaneView,
    DocumentAlertWhatsAppToggleView,
    DocumentRequestCreateView,
    DocumentNoticesView,
    NoticeAppointmentView,
    NoticeScopeSaveView,
    NoticeUploadView,
)
from panel.views_inbox import (
    InboxResultsView,
    InboxRetryView,
    InboxStatusView,
    InboxTabView,
    InboxUploadView,
)
from panel.views_navigation_state import NavigationStateSaveView
from panel.views_dossier_bundle import DossierBundleEmailView
from panel.views_vacation_balance import (
    AbsencePeriodCreateView,
    AbsencePeriodRemoveView,
    VacationAdjustmentCreateView,
    VacationAdjustmentDeleteView,
    VacationBalanceDetailView,
    VacationBalanceResultsView,
    VacationBalanceTabView,
    VacationImportPaneView,
    VacationImportTemplateView,
    VacationImportUploadView,
    VacationPeriodEditView,
    VacationPeriodRemoveView,
    VacationRuleCreateView,
    VacationRuleDeleteView,
    VacationRowRegisterView,
    VacationRulesPaneView,
    VacationSectionAssignmentDeleteView,
    VacationSectionAssignView,
)
from panel.views_clock_events import (
    ClockEventsDetailView,
    ClockEventsExportView,
    ClockEventsResultsView,
    ClockEventsTabView,
)
from panel.views_lifting_accessories import (
    LiftingAccessoryAssignView,
    LiftingAccessoryBulkReviewView,
    LiftingAccessoryBulkStatusView,
    LiftingAccessoryBulkAssignView,
    LiftingAccessoryCertificateAddView,
    LiftingAccessoryCostCenterSearchView,
    LiftingAccessoryCreateView,
    LiftingAccessoryDetailView,
    LiftingAccessoryModelRemoveView,
    LiftingAccessoryModelSaveView,
    LiftingAccessoryModelUnitsView,
    LiftingAccessoryResultsView,
    LiftingAccessoryReturnView,
    LiftingAccessoryReviewCreateView,
    LiftingAccessoryReviewDeleteView,
    LiftingAccessoryTabView,
    LiftingAccessoryTypeRemoveView,
    LiftingAccessoryTypeSaveView,
)
from panel.views_personal_export import (
    PersonalExportTemplateDeleteView,
    PersonalExportTemplateListView,
    PersonalExportTemplateSaveView,
    PersonalExportView,
)
from panel.views_documentation_h30 import (
    CalendarResultsFragmentView,
    CalendarTabFragmentView,
    DocumentDeleteView,
    DocumentChangeTypeView,
    DocumentTypeQuickCreateView,
    DocumentViewView,
    DocumentationHubV2View,
    EpiBatchDeliveryExecuteView,
    EpiBatchTemplateDeleteView,
    EpiBatchTemplateSaveView,
    PersonGroupTemplateDeleteView,
    PersonGroupTemplateSaveView,
    PersonMassSetJobPositionView,
    EpiResultsFragmentView,
    EpiTabFragmentView,
    EpiTechnicalSheetUploadView,
    MachineDetailView,
    MachineDocumentSelectionPdfView,
    MachineDocumentSelectionPreviewView,
    MachineDocumentSelectionZipView,
    MachineDossierTemplateApplyView,
    MachineDossierTemplateListView,
    PersonalDetailView,
    PersonalDocumentSelectionPdfView,
    PersonalContractReviewedView,
    PersonalDocumentSelectionPreviewView,
    PersonalDocumentSelectionZipView,
    PersonalDocumentTypeHistoryView,
    MachineDocumentTypeHistoryView,
    MachineSetAvatarView,
    PersonalDossierEmailSendView,
    DossierTemplateBulkDeleteView,
    DossierTemplateManageView,
    DossierTemplateMissingCheckView,
    DossierTemplateSaveView,
    JobPositionBulkActiveView,
    JobPositionBulkDeleteView,
    JobPositionManageView,
    JobPositionSaveView,
    PersonalDossierMassGenerateView,
    PersonalDossierTemplateApplyView,
    PersonalDossierTemplateListView,
    PersonalEpiItemHistoryView,
    PersonalCreateView,
    PersonalTerminateView,
    PersonalReactivateView,
    PersonalIntakeExtractView,
    PersonalListFragmentView,
    PersonalNotificationMassSendView,
    PersonalNotificationSendView,
    PersonalResultsFragmentView,
    PersonalUpdateView,
    PersonalSetAvatarView,
    PersonalWorkdayDetailView,
    SubjectDocumentUploadView,
)
from panel.views import (
    PanelLoginView,
    PanelLogoutView,
    WorkerSignupView,
    InboundCallLogListView,
    InboundCallLogDetailView,
    InboundCallLogDeleteView,
    PanelDashboardView,
    GDriveAuthorizeView,
    GDriveOAuthCallbackView,
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
    WorkOrderEntryFormView,
    OperatorClockStretchesView,
    WorkOrderEntryPartsReviewView,
    WorkOrderDetailView,
    WorkOrderAdminHistoryView,
    WorkerAbsenceCreateView,
    MachineAssetListView,
    MachineAssetAnalyticsView,
    WorkOrderDescriptionAutocompleteView,
    WorkshopIntensiveToggleView,
    MachineAssetCreateView,
    MachineAssetDeactivateView,
    MachineAssetReactivateView,
    MachineAssetDeleteView,
    MachineAssetBulkStatusView,
    MachineAssetBulkDeleteView,
    MachineAssetBulkSetDocumentRequirementView,
    MachineAssetExportView,
    MachineAssetDocsPaneView,
    MachineAssetFragmentView,
    WorkerAbsenceUpdateView,
    WorkerAbsenceDeleteView,
    WorkOrderAdminExportView,
    WorkPeriodGroupDetailView,
    WorkPeriodGroupCloseView,
    WorkPeriodGroupLockView,
    WorkPeriodLockView,
    WorkOrderMachineFilterView,
    WorkOrderDraftListView,
    WorkdayScheduleView,
    AbsenceCategoryListView,
    AbsenceCategoryCreateView,
    AbsenceCategoryUpdateView,
    AbsenceCategoryToggleView,
    SectionDefaultRoleView,
    CompanyUserBulkDeleteView,
    WorkerScheduleUpdateView,
    OwnProfileView,
    MiBuzonListView,
    MiBuzonDetailView,
    OwnProfileSignatureSaveView,
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
    WorkOrderEntryAddView,
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
    # H24 (S129): tramos fichados del día para el formulario de partes.
    path("operator/form/fichajes/", OperatorClockStretchesView.as_view(), name="operator_form_clock"),
    # Operator form edit — Edición de parte digital no revisado desde Mi historial.
    # S019 — Hito 7 (2026-05-11)
    path("operator/form/<int:wo_pk>/edit/", WorkOrderEntryFormView.as_view(), name="operator_form_edit"),
    # Revisión de repuestos pre-asignados tras guardar el parte (H10 Paso 4-bis, bloque B).
    # Solo se visita si alguna tarea guardada quedó vinculada a un ticket de avería.
    path("operator/form/<int:entry_pk>/repuestos/", WorkOrderEntryPartsReviewView.as_view(), name="operator_parts_review"),

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
    # --- H7, S016: fotos opcionales de tarea ---
    path("work-orders/lines/<int:line_pk>/photos/", TaskPhotoWidgetView.as_view(), name="task_photo_widget"),
    path("work-orders/lines/<int:line_pk>/photos/subir/", TaskPhotoUploadView.as_view(), name="task_photo_upload"),
    path("work-orders/lines/<int:line_pk>/photos/<int:photo_pk>/eliminar/", TaskPhotoDeleteView.as_view(), name="task_photo_delete"),

    # WorkOrderEntry save date — Guardado de fecha de grupo via HTMX (incidencia S046).
    path("work-orders/<int:wo_pk>/entries/<int:entry_pk>/save-date/",
         WorkOrderEntrySaveDateView.as_view(),
         name="work_order_entry_save_date"),

    # WorkOrderEntry add day — Inserción de nuevo día en un parte PDF (H17/S056).
    path("work-orders/<int:wo_pk>/entries/add/",
         WorkOrderEntryAddView.as_view(),
         name="work_order_entry_add"),

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
    path("work-orders/<int:pk>/detail/", WorkOrderDetailView.as_view(), name="work_order_detail"),

    # Work period management — CRUD de periodos de trabajo para SUPERVISOR y ADMIN.
    # 1ª Acción — Hito 7 Sesión 017 (2026-05-08)
    path("work-periods/<int:pk>/", WorkPeriodGroupDetailView.as_view(), name="work_period_group_detail"),
    path("work-periods/<int:pk>/close/", WorkPeriodGroupCloseView.as_view(), name="work_period_group_close"),
    path("work-periods/<int:pk>/lock/", WorkPeriodGroupLockView.as_view(), name="work_period_group_lock"),
    path("work-periods/operator/<int:pk>/lock/", WorkPeriodLockView.as_view(), name="work_period_lock"),

    # Workday schedule management — Gestión de horarios de jornada (rol SUPERVISOR y ADMIN).
    # Paso G — CUARTA ACCION Hito 7 Sesion 029 (2026-05-14)
    path("workday-schedule/", WorkdayScheduleView.as_view(), name="workday_schedule"),

    # Draft (IN_PROGRESS) digital work orders — Borradores de partes digitales.
    # Superuser-only (S021) — ver panel/mixins.py SuperuserRequiredMixin.
    path("work-orders/drafts/", WorkOrderDraftListView.as_view(), name="work_order_drafts"),

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
    path("fleet/<int:pk>/deactivate/", MachineAssetDeactivateView.as_view(), name="fleet_deactivate"),
    path("fleet/<int:pk>/reactivate/", MachineAssetReactivateView.as_view(), name="fleet_reactivate"),
    path("fleet/<int:pk>/delete/", MachineAssetDeleteView.as_view(), name="fleet_delete"),
    path("fleet/bulk/status/", MachineAssetBulkStatusView.as_view(), name="fleet_bulk_status"),
    path("fleet/bulk/delete/", MachineAssetBulkDeleteView.as_view(), name="fleet_bulk_delete"),
    path("fleet/bulk/requisito/", MachineAssetBulkSetDocumentRequirementView.as_view(), name="fleet_bulk_set_document_requirement"),
    path("fleet/export/", MachineAssetExportView.as_view(), name="fleet_export"),
    path("fleet/tabla/", MachineAssetFragmentView.as_view(), name="fleet_fragment"),
    path("fleet/documentacion/", MachineAssetDocsPaneView.as_view(), name="fleet_docs_pane"),
    # Fleet analytics — Hito 12 Paso PRIORIDAD 2
    path("fleet/analytics/", MachineAssetAnalyticsView.as_view(), name="fleet_analytics"),

    # --- Documentación (H30, S48) -- contra DocumentIndexEntry (cubo unificado
    # cgs_grupo_alvarez). Sustituye por completo al flujo legado sobre
    # MachineDocument/PersonalDocument (30/39 filas residuales frente a 11.000+
    # ya clasificadas aquí -- ver anexo H30 sección "COMPLETADAS EN S48",
    # decisión explícita de Miguel Ángel de retirarlo sin más). ---
    path("documentacion/", DocumentationHubV2View.as_view(), name="documentation_hub"),
    # H31 (S75): persistencia de pestaña/filtros -- genérica por screen_key.
    path("navegacion/estado/<str:screen_key>/", NavigationStateSaveView.as_view(), name="navigation_state_save"),
    path("documentacion/maquinaria/<int:pk>/", MachineDetailView.as_view(), name="documentation_machine_detail"),
    # H30 (S118) punto 1: historial completo de un tipo documental de una máquina.
    path("documentacion/maquinaria/<int:pk>/historial/<str:type_code>/", MachineDocumentTypeHistoryView.as_view(), name="documentation_machine_type_history"),
    # H30 (S118): foto de la máquina (documento-imagen ya indexado).
    path("documentacion/maquinaria/<int:pk>/foto/", MachineSetAvatarView.as_view(), name="documentation_machine_set_avatar"),
    path("documentacion/personal/", PersonalListFragmentView.as_view(), name="documentation_personal_list"),
    # H31 (S100) Bloque 1: alta de trabajador nuevo desde el panel.
    path("documentacion/personal/alta/", PersonalCreateView.as_view(), name="documentation_personal_create"),
    path("documentacion/personal/baja/", PersonalTerminateView.as_view(), name="documentation_personal_terminate"),
    path("documentacion/personal/reactivar/", PersonalReactivateView.as_view(), name="documentation_personal_reactivate"),
    # H31 (S129): exportación a Excel del listado con plantillas -- panel/views_personal_export.py.
    path("documentacion/personal/exportar/", PersonalExportView.as_view(), name="documentation_personal_export"),
    path("documentacion/personal/exportar/plantillas/", PersonalExportTemplateListView.as_view(), name="documentation_personal_export_templates"),
    path("documentacion/personal/exportar/plantillas/guardar/", PersonalExportTemplateSaveView.as_view(), name="documentation_personal_export_template_save"),
    path("documentacion/personal/exportar/plantillas/<int:pk>/borrar/", PersonalExportTemplateDeleteView.as_view(), name="documentation_personal_export_template_delete"),
    # H31 (S100) Bloque 1, paso 1: extracción de datos de los documentos subidos para el alta.
    path("documentacion/personal/alta/extraer/", PersonalIntakeExtractView.as_view(), name="documentation_personal_intake_extract"),
    # H30 (S50): endpoint de solo-resultados -- el formulario de busqueda
    # nunca se vuelve a pintar tras la carga inicial (ver
    # _personal_search_form.html sobre el bug que esto corrige).
    path("documentacion/personal/resultados/", PersonalResultsFragmentView.as_view(), name="documentation_personal_results"),
    path("documentacion/personal/<int:pk>/", PersonalDetailView.as_view(), name="documentation_personal_detail"),
    # H31 (S76) punto 5: historial completo de un tipo documental, bajo demanda.
    path("documentacion/personal/<int:pk>/historial/<str:type_code>/", PersonalDocumentTypeHistoryView.as_view(), name="documentation_personal_type_history"),
    # H31 (S103): vista previa de la selección de documentos (checkboxes) para dossieres/adjuntos.
    path("documentacion/personal/<int:pk>/seleccion/", PersonalDocumentSelectionPreviewView.as_view(), name="documentation_personal_document_selection_preview"),
    # H30 (S125): el supervisor confirma el contrato vigente (aviso a cero).
    path("documentacion/personal/<int:pk>/contrato-revisado/", PersonalContractReviewedView.as_view(), name="documentation_personal_contract_reviewed"),
    # H30 (S119), punto 6: selección y plantillas de dossier en la ficha de máquina (mismo mecanismo que Personal).
    path("documentacion/maquinaria/<int:pk>/seleccion/", MachineDocumentSelectionPreviewView.as_view(), name="documentation_machine_document_selection_preview"),
    path("documentacion/maquinaria/<int:pk>/seleccion/pdf/", MachineDocumentSelectionPdfView.as_view(), name="documentation_machine_document_selection_pdf"),
    path("documentacion/maquinaria/<int:pk>/seleccion/zip/", MachineDocumentSelectionZipView.as_view(), name="documentation_machine_document_selection_zip"),
    path("documentacion/maquinaria/<int:pk>/plantillas/", MachineDossierTemplateListView.as_view(), name="documentation_machine_dossier_template_list"),
    path("documentacion/maquinaria/<int:pk>/plantillas/<int:template_pk>/aplicar/", MachineDossierTemplateApplyView.as_view(), name="documentation_machine_dossier_template_apply"),
    # H31 (S103): descarga del dossier de la selección como PDF único (portada + índice + documentos).
    path("documentacion/personal/<int:pk>/seleccion/pdf/", PersonalDocumentSelectionPdfView.as_view(), name="documentation_personal_document_selection_pdf"),
    # H31 (S103): descarga del dossier de la selección como ZIP (archivos originales, una carpeta por familia).
    path("documentacion/personal/<int:pk>/seleccion/zip/", PersonalDocumentSelectionZipView.as_view(), name="documentation_personal_document_selection_zip"),
    # H31 (S104): envío del dossier (selección o plantilla) como adjunto de un .eml, con cuerpo editable y firma del supervisor.
    path("documentacion/personal/<int:pk>/seleccion/email/", PersonalDossierEmailSendView.as_view(), name="documentation_personal_dossier_email_send"),
    # H31 (S103): gestor de plantillas de dossier de la empresa -- fragmento de solo "Descargar", abierto desde una ficha de persona concreta.
    path("documentacion/personal/<int:pk>/plantillas/", PersonalDossierTemplateListView.as_view(), name="documentation_personal_dossier_template_list"),
    # H31 (S103): aplicar una plantilla de empresa sobre esta persona -- resuelve el vigente de cada tipo + la selección actual, descarga en el formato guardado.
    path("documentacion/personal/<int:pk>/plantillas/<int:template_pk>/aplicar/", PersonalDossierTemplateApplyView.as_view(), name="documentation_personal_dossier_template_apply"),
    # (S106: duplicar quedó sin propósito al dejar de existir un formato por plantilla -- eliminado con PersonalDossierTemplateDuplicateView)
    # H30 (S128): borrar varias plantillas de dosier (modal con cuenta atrás); "Marcar como activa" retirada.
    path("documentacion/plantillas-dosier/eliminar/", DossierTemplateBulkDeleteView.as_view(), name="dossier_templates_bulk_delete"),
    # H35 (S105): página completa de gestión de plantillas -- crear/editar, todos los tipos agrupados por familia y coloreados.
    path("documentacion/plantillas-dosier/", DossierTemplateManageView.as_view(), name="dossier_templates_manage"),
    path("documentacion/plantillas-dosier/guardar/", DossierTemplateSaveView.as_view(), name="dossier_template_create"),
    path("documentacion/plantillas-dosier/<int:template_pk>/guardar/", DossierTemplateSaveView.as_view(), name="dossier_template_update"),
    # H31 (S109): gestión de puestos de trabajo -- "plantilla de puesto" (tipos documentales obligatorios por puesto).
    path("documentacion/puestos/", JobPositionManageView.as_view(), name="job_positions_manage"),
    # H30 (S122). Pestaña "Avisos": avisos por requisito e interruptor de WhatsApp.
    path("documentacion/avisos/", DocumentAlertsPaneView.as_view(), name="document_alerts_pane"),
    path("documentacion/avisos/requisito/<int:position_pk>/guardar/", DocumentAlertRulesSaveView.as_view(), name="document_alert_rules_save"),
    path("documentacion/avisos/pendientes/", DocumentNoticesView.as_view(), name="document_notices"),
    path("documentacion/avisos/destinatarios/<int:supervisor_pk>/guardar/", NoticeScopeSaveView.as_view(), name="notice_scope_save"),
    path("documentacion/avisos/whatsapp/", DocumentAlertWhatsAppToggleView.as_view(), name="document_alerts_whatsapp_toggle"),
    # H30 (S126), punto 2: subir desde el aviso lo que aporta la empresa y "Cita solicitada".
    path("documentacion/avisos/subir/", NoticeUploadView.as_view(), name="notice_upload"),
    path("documentacion/avisos/cita/", NoticeAppointmentView.as_view(), name="notice_appointment"),
    # H30 (S126). Pestaña "Bandeja de entrada": subida de firmados de Docuten y otros documentos.
    path("documentacion/bandeja/", InboxTabView.as_view(), name="inbox_tab"),
    path("documentacion/bandeja/resultados/", InboxResultsView.as_view(), name="inbox_results"),
    path("documentacion/bandeja/subir/", InboxUploadView.as_view(), name="inbox_upload"),
    path("documentacion/bandeja/estado/", InboxStatusView.as_view(), name="inbox_status"),
    path("documentacion/bandeja/reclasificar/", InboxRetryView.as_view(), name="inbox_retry"),
    # H30 (S125): pedir documentación al trabajador por WhatsApp.
    path("documentacion/avisos/pedir-al-trabajador/", DocumentRequestCreateView.as_view(), name="document_request_create"),
    path("documentacion/puestos/guardar/", JobPositionSaveView.as_view(), name="job_position_create"),
    path("documentacion/puestos/<int:position_pk>/guardar/", JobPositionSaveView.as_view(), name="job_position_update"),
    # H30 (S128), punto 1: borrar varios requisitos (cuenta atrás) y activar/desactivar.
    path("documentacion/puestos/eliminar/", JobPositionBulkDeleteView.as_view(), name="job_positions_bulk_delete"),
    path("documentacion/puestos/activar/", JobPositionBulkActiveView.as_view(), name="job_positions_bulk_active"),
    # H30 (S119): gestión de requisitos de documentación de máquina -- misma mecánica, filtro de tipos MACHINE/BOTH.
    # S130: un solo correo con la documentación de varios trabajadores y máquinas juntos.
    path("documentacion/dosieres/correo/", DossierBundleEmailView.as_view(), name="dossier_bundle_email"),
    # H35 (S105): generar dosieres para varios trabajadores seleccionados a la vez, a partir de una plantilla -- descarga o envío por correo.
    path("documentacion/personal/dosieres-masivo/", PersonalDossierMassGenerateView.as_view(), name="documentation_personal_dossier_mass_generate"),
    # H35 (S105): marca en el listado qué personas les falta algún documento de la plantilla elegida.
    path("documentacion/personal/dosieres-masivo/comprobar/", DossierTemplateMissingCheckView.as_view(), name="documentation_personal_dossier_missing_check"),
    path("documentacion/personal/<int:pk>/parte-dia/<str:date_iso>/", PersonalWorkdayDetailView.as_view(), name="documentation_personal_workday_detail"),
    # H31 (S76) punto EPIs: historial completo de un EPI, bajo demanda.
    path("documentacion/personal/<int:pk>/historial-epi/<int:epi_id>/", PersonalEpiItemHistoryView.as_view(), name="documentation_personal_epi_history"),
    # H31 (S76): manual de uso / ficha técnica de un EPI del catálogo.
    path("documentacion/epis/<int:epi_id>/ficha-tecnica/", EpiTechnicalSheetUploadView.as_view(), name="documentation_epi_technical_sheet_upload"),
    # H31 (S74): edición de ficha de persona (given_name/first_surname/second_surname/phone/email).
    path("documentacion/personal/<int:pk>/actualizar/", PersonalUpdateView.as_view(), name="documentation_personal_update"),
    path("documentacion/personal/<int:pk>/avatar/", PersonalSetAvatarView.as_view(), name="documentation_personal_set_avatar"),
    # H31 (S113): entrega real de EPIs (individual desde la ficha, o
    # masiva sobre la selección con casillero) -- sustituye a las
    # rutas separadas de S74/S75, unificadas porque el proceso real
    # es el mismo (una o varias personas, uno o varios EPIs a la vez).
    path("documentacion/personal/entregar-epi/", EpiBatchDeliveryExecuteView.as_view(), name="documentation_personal_epi_batch_delivery"),
    path("documentacion/personal/<int:pk>/notificar/", PersonalNotificationSendView.as_view(), name="documentation_personal_notify"),
    # H31 (S75) punto 1: acciones masivas sobre la selección con casillero del listado Personal.
    path("documentacion/personal/grupos/guardar/", PersonGroupTemplateSaveView.as_view(), name="documentation_personal_group_create"),
    path("documentacion/personal/grupos/<int:group_pk>/guardar/", PersonGroupTemplateSaveView.as_view(), name="documentation_personal_group_update"),
    path("documentacion/personal/grupos/<int:group_pk>/eliminar/", PersonGroupTemplateDeleteView.as_view(), name="documentation_personal_group_delete"),
    path("documentacion/personal/puesto-masivo/", PersonMassSetJobPositionView.as_view(), name="documentation_personal_job_position_mass_set"),
    path("documentacion/personal/notificar-masivo/", PersonalNotificationMassSendView.as_view(), name="documentation_personal_notify_mass"),
    # H30 (S124), punto 4: material para el envío masivo en Docuten.
    path("documentacion/personal/preparar-docuten/", PersonalDocutenExportView.as_view(), name="documentation_personal_docuten_export"),
    # H31 (S113): CRUD de lotes de EPIs -- centralizado en la propia
    # pestaña EPIs (ver EpiTabFragmentView / _epi_pane.html), sin
    # página aparte.
    path("documentacion/lotes-epi/guardar/", EpiBatchTemplateSaveView.as_view(), name="epi_batch_template_create"),
    path("documentacion/lotes-epi/<int:template_pk>/guardar/", EpiBatchTemplateSaveView.as_view(), name="epi_batch_template_update"),
    path("documentacion/lotes-epi/<int:template_pk>/eliminar/", EpiBatchTemplateDeleteView.as_view(), name="epi_batch_template_delete"),
    # H31 (S75) punto 2: CRUD de circulares/notificaciones.
    path("documentacion/circulares/", CircularListView.as_view(), name="circulars_list"),
    path("documentacion/circulares/firma/", CircularBulkSignatureView.as_view(), name="circulars_bulk_signature"),
    path("obras/", WorksiteListView.as_view(), name="worksites_list"),
    path("obras/<int:pk>/eliminar/", WorksiteDeleteView.as_view(), name="worksite_delete"),
    path("documentacion/circulares/nueva/", CircularCreateView.as_view(), name="circulars_create"),
    path("documentacion/circulares/<int:pk>/", CircularEditView.as_view(), name="circulars_edit"),
    path("documentacion/circulares/<int:pk>/guardar-contenido/", CircularSaveContentView.as_view(), name="circulars_save_content"),
    path("documentacion/circulares/<int:pk>/importar/", CircularImportDocumentView.as_view(), name="circulars_import"),
    path("documentacion/circulares/<int:pk>/descargar/pdf/", CircularExportPdfView.as_view(), name="circulars_export_pdf"),
    path("documentacion/circulares/<int:pk>/descargar/word/", CircularExportWordView.as_view(), name="circulars_export_word"),
    path("documentacion/circulares/<int:pk>/generar/", CircularGenerateView.as_view(), name="circulars_generate"),
    path("documentacion/circulares/generar/buscar-persona/", CircularGeneratePersonSearchView.as_view(), name="circulars_generate_person_search"),
    path("documentacion/epis/", EpiTabFragmentView.as_view(), name="documentation_epi_tab"),
    # H30 (S50): mismo motivo que documentation_personal_results.
    path("documentacion/epis/resultados/", EpiResultsFragmentView.as_view(), name="documentation_epi_results"),
    # H30 (S121). Pestaña "Accesorios de elevación" del hub -- CRUD
    # completo como el de los EPIs, ver panel/views_lifting_accessories.py.
    path("documentacion/accesorios/", LiftingAccessoryTabView.as_view(), name="lifting_accessory_tab"),
    path("documentacion/accesorios/resultados/", LiftingAccessoryResultsView.as_view(), name="lifting_accessory_results"),
    path("documentacion/accesorios/nuevo/", LiftingAccessoryCreateView.as_view(), name="lifting_accessory_create"),
    path("documentacion/accesorios/estado/", LiftingAccessoryBulkStatusView.as_view(), name="lifting_accessory_bulk_status"),
    path("documentacion/accesorios/revision-masiva/", LiftingAccessoryBulkReviewView.as_view(), name="lifting_accessory_bulk_review"),
    path("documentacion/accesorios/entrega-masiva/", LiftingAccessoryBulkAssignView.as_view(), name="lifting_accessory_bulk_assign"),
    path("documentacion/accesorios/centros-de-gasto/", LiftingAccessoryCostCenterSearchView.as_view(), name="lifting_accessory_cost_centers"),
    path("documentacion/accesorios/modelos/unidades/", LiftingAccessoryModelUnitsView.as_view(), name="lifting_accessory_model_units"),
    path("documentacion/accesorios/modelos/nuevo/", LiftingAccessoryModelSaveView.as_view(), name="lifting_accessory_model_create"),
    path("documentacion/accesorios/modelos/<int:model_pk>/", LiftingAccessoryModelSaveView.as_view(), name="lifting_accessory_model_update"),
    path("documentacion/accesorios/modelos/<int:model_pk>/quitar/", LiftingAccessoryModelRemoveView.as_view(), name="lifting_accessory_model_remove"),
    path("documentacion/accesorios/<int:pk>/", LiftingAccessoryDetailView.as_view(), name="lifting_accessory_detail"),
    path("documentacion/accesorios/<int:pk>/entrega/", LiftingAccessoryAssignView.as_view(), name="lifting_accessory_assign"),
    path("documentacion/accesorios/<int:pk>/devolucion/", LiftingAccessoryReturnView.as_view(), name="lifting_accessory_return"),
    path("documentacion/accesorios/<int:pk>/revision/", LiftingAccessoryReviewCreateView.as_view(), name="lifting_accessory_review_create"),
    path("documentacion/accesorios/<int:pk>/certificado/", LiftingAccessoryCertificateAddView.as_view(), name="lifting_accessory_certificate_add"),
    path("documentacion/accesorios/<int:pk>/revision/<int:review_pk>/eliminar/", LiftingAccessoryReviewDeleteView.as_view(), name="lifting_accessory_review_delete"),
    path("documentacion/accesorios/tipos/nuevo/", LiftingAccessoryTypeSaveView.as_view(), name="lifting_accessory_type_create"),
    path("documentacion/accesorios/tipos/<int:type_pk>/", LiftingAccessoryTypeSaveView.as_view(), name="lifting_accessory_type_update"),
    path("documentacion/accesorios/tipos/<int:type_pk>/quitar/", LiftingAccessoryTypeRemoveView.as_view(), name="lifting_accessory_type_remove"),
    # H24 (S129). Pestaña Vacaciones del hub: listado de trabajadores con su saldo, alta de periodos a los marcados,
    # secciones, ajustes, reglas e importación -- ver panel/views_vacation_balance.py. Sustituye al CRUD de S94.
    path("documentacion/vacaciones/", VacationBalanceTabView.as_view(), name="vacation_balance_tab"),
    path("documentacion/vacaciones/resultados/", VacationBalanceResultsView.as_view(), name="vacation_balance_results"),
    path("documentacion/vacaciones/<int:pk>/", VacationBalanceDetailView.as_view(), name="vacation_balance_detail"),
    path("documentacion/vacaciones/<int:pk>/alta/", VacationRowRegisterView.as_view(), name="vacation_row_register"),
    path("documentacion/vacaciones/periodo/<int:pk>/editar/", VacationPeriodEditView.as_view(), name="vacation_period_edit"),
    path("documentacion/vacaciones/periodo/<int:pk>/borrar/", VacationPeriodRemoveView.as_view(), name="vacation_period_remove"),
    # H24 (S130): ausencias que no son vacaciones ni baja, desde el desglose del trabajador.
    path("documentacion/vacaciones/<int:pk>/ausencia/", AbsencePeriodCreateView.as_view(), name="absence_period_create"),
    path("documentacion/vacaciones/ausencia/<int:pk>/borrar/", AbsencePeriodRemoveView.as_view(), name="absence_period_remove"),
    path("documentacion/vacaciones/asignar-seccion/", VacationSectionAssignView.as_view(), name="vacation_balance_assign_section"),
    path("documentacion/vacaciones/seccion/<int:pk>/borrar/", VacationSectionAssignmentDeleteView.as_view(), name="vacation_balance_assignment_delete"),
    path("documentacion/vacaciones/<int:pk>/ajuste/", VacationAdjustmentCreateView.as_view(), name="vacation_balance_adjustment_create"),
    path("documentacion/vacaciones/ajuste/<int:pk>/borrar/", VacationAdjustmentDeleteView.as_view(), name="vacation_balance_adjustment_delete"),
    path("documentacion/vacaciones/reglas/", VacationRulesPaneView.as_view(), name="vacation_rules_pane"),
    path("documentacion/vacaciones/reglas/nueva/", VacationRuleCreateView.as_view(), name="vacation_rule_create"),
    path("documentacion/vacaciones/reglas/<int:pk>/borrar/", VacationRuleDeleteView.as_view(), name="vacation_rule_delete"),
    path("documentacion/vacaciones/importar/", VacationImportPaneView.as_view(), name="vacation_import_pane"),
    path("documentacion/vacaciones/importar/plantilla/", VacationImportTemplateView.as_view(), name="vacation_import_template"),
    path("documentacion/vacaciones/importar/subir/", VacationImportUploadView.as_view(), name="vacation_import_upload"),
    # H24 (S129): pestaña Fichajes (supervisores) -- panel/views_clock_events.py.
    path("documentacion/fichajes/", ClockEventsTabView.as_view(), name="clock_events_tab"),
    path("documentacion/fichajes/resultados/", ClockEventsResultsView.as_view(), name="clock_events_results"),
    path("documentacion/fichajes/<int:pk>/", ClockEventsDetailView.as_view(), name="clock_events_detail"),
    path("documentacion/fichajes/exportar/", ClockEventsExportView.as_view(), name="clock_events_export"),
    # H31 (S94). Pestaña Calendario htmx del hub -- ver panel/views_documentation_h30.py.
    path("documentacion/calendario/", CalendarTabFragmentView.as_view(), name="documentation_calendar_tab"),
    path("documentacion/calendario/resultados/", CalendarResultsFragmentView.as_view(), name="documentation_calendar_results"),
    path("documentacion/<str:domain>/<int:subject_pk>/subir/", SubjectDocumentUploadView.as_view(), name="documentation_upload"),
    # H30 (S51): atajo de alta de tipo documental desde el propio flujo de
    # subida -- ver DocumentTypeQuickCreateView.
    path("documentacion/<str:domain>/tipos/crear/", DocumentTypeQuickCreateView.as_view(), name="documentation_type_quick_create"),
    path("documentacion/documento/<int:pk>/ver/", DocumentViewView.as_view(), name="documentation_document_view"),
    path("documentacion/documento/<int:pk>/eliminar/", DocumentDeleteView.as_view(), name="documentation_document_delete"),
    path("documentacion/documento/<int:pk>/cambiar-tipo/", DocumentChangeTypeView.as_view(), name="documentation_document_change_type"),

    # Section default role — Endpoint AJAX para pre-rellenar rol al crear usuario (H13).
    path("sections/<int:pk>/default-role/", SectionDefaultRoleView.as_view(), name="section_default_role"),

    # Breakdown tickets — Gestión de tickets de avería (H17 Paso 1).
    # ChatRoom routes removed in H17 Paso 1. Only ticket management routes remain.
    path("chat/breakdowns/tickets/", BreakdownTicketListView.as_view(), name="breakdown_ticket_list"),
    path("chat/breakdowns/tickets/<int:pk>/", BreakdownTicketDetailView.as_view(), name="breakdown_ticket_detail"),
    # Breakdown ticket create — Creación manual de ticket desde el panel (Hito 14 Paso 3).
    path("chat/breakdowns/tickets/create/", BreakdownTicketCreateView.as_view(), name="breakdown_ticket_create"),

    # Own profile — Perfil propio del operario: edición de alias de chat (Hito 14 Paso 6).
    path("profile/", OwnProfileView.as_view(), name="own_profile"),
    path("mi-buzon/", MiBuzonListView.as_view(), name="mi_buzon_list"),
    path("mi-buzon/<int:pk>/", MiBuzonDetailView.as_view(), name="mi_buzon_detail"),
    # H31 (S104): guardado de la firma de correo del propio CompanyUser.
    path("profile/signature/", OwnProfileSignatureSaveView.as_view(), name="own_profile_signature_save"),

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

    # Inbound call logs — Registro de llamadas IVR entrantes (H03).
    path("ivr/call-logs/", InboundCallLogListView.as_view(), name="inbound_call_log_list"),
    path("ivr/call-logs/<int:pk>/", InboundCallLogDetailView.as_view(), name="inbound_call_log_detail"),
    path("ivr/call-logs/<int:pk>/delete/", InboundCallLogDeleteView.as_view(), name="inbound_call_log_delete"),

    # Google Drive one-time OAuth setup — Autorización de un solo uso
    # para persistencia de fotos de albarán en Drive (Hito 10, S014).
    path("gdrive/authorize/", GDriveAuthorizeView.as_view(), name="gdrive_authorize"),
    path("gdrive/oauth-callback/", GDriveOAuthCallbackView.as_view(), name="gdrive_oauth_callback"),
]




