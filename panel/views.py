# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py
"""
Punto de entrada unico de panel.views tras H21 (split arquitectonico).
Solo imports y re-exports -- panel/urls.py sigue important desde aqui
sin cambios. Logica real en views_operator.py, views_workorders.py,
views_ivr.py y views_auth.py.
"""

# --- Re-exports Fase B: views_operator ---
from panel.views_operator import (
    OperatorDashboardView,
    WorkerSignupView,
    WorkshopAssetAutocompleteView,
    WorkOrderEntryUploadView,
    WorkOrderEntryConfirmView,
    WorkOrderEntryFormView,
    WorkOrderEntryPartsReviewView,
    WorkshopAssetDetailView,
    WorkOrderDescriptionAutocompleteView,
    WorkshopIntensiveToggleView,
)

# --- Re-exports Fase C: views_workorders ---
from panel.views_workorders import (
    WorkOrderListView,
    WorkOrderUploadView,
    WorkOrderEditView,
    WorkOrderStatusFragmentView,
    WorkOrderLineSaveView,
    WorkOrderEntrySaveDateView,
    MachineAssetAutocompleteView,
    WorkOrderEntryAddView,
    WorkOrderLineInsertView,
    WorkOrderLineReorderView,
    WorkOrderLineRestoreView,
    WorkOrderLineDeleteView,
    WorkOrderDeleteView,
    WorkOrderMarkReviewedView,
    WorkOrderExportView,
    WorkOrderDuplicateSearchView,
    WorkOrderDuplicateDeleteView,
    WorkerAbsenceCreateView,
    WorkerAbsenceUpdateView,
    WorkerAbsenceDeleteView,
    WorkdayScheduleView,
    AbsenceCategoryListView,
    AbsenceCategoryCreateView,
    AbsenceCategoryUpdateView,
    AbsenceCategoryToggleView,
    WorkOrderAdminHistoryView,
    WorkOrderDetailView,
    WorkPeriodLockView,
    WorkPeriodGroupDetailView,
    WorkPeriodGroupCloseView,
    WorkPeriodGroupLockView,
    WorkOrderAdminExportView,
    WorkOrderMachineFilterView,
    WorkOrderDraftListView,
    ExportTemplateListView,
    ExportTemplateCreateView,
    ExportTemplateUpdateView,
    ExportTemplateDeleteView,
    WorkOrderAdminExportByTemplateView,
)

# --- Re-exports Fase E: views_ivr ---
from panel.views_ivr import (
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
    CallFlowRestoreView,
    VoiceProfileRestoreView,
    BlockedCallerListView,
    BlockedCallerCreateView,
    BlockedCallerDeleteView,
    DataCaptureSetListView,
    DataCaptureSetCreateView,
    DataCaptureSetUpdateView,
    SectionDefaultRoleView,
    InboundCallLogListView,
    InboundCallLogDetailView,
    InboundCallLogDeleteView,
)

# --- Re-exports Fase F: views_auth ---
from panel.views_auth import (
    CompanyUserCreateView,
    CompanyUserListView,
    CompanyUserUpdateView,
    CompanyUserBulkDeleteView,
    CompanyUserSectionUnlinkView,
    WorkerScheduleUpdateView,
    PanelLoginView,
    TrustDeviceQuickLoginView,
    TrustDeviceView,
    TrustDeviceToggleView,
    PresenceStatusUpdateView,
    PanelLogoutView,
    PanelDashboardView,
    PanelPasswordChangeView,
    WhatsAppTemplateListView,
    WhatsAppActiveSessionListView,
    OwnProfileView,
    CompanySettingsView,
)

# --- Fleet views — re-exported from fleet.views (H12/H21 split) ---
# Recuperado el 2026-07-06: este re-export vivia originalmente entre dos
# clases IVR (efecto colateral de una extraccion de Fase E basada solo en
# limites de "class ", que no detecto este import suelto). Restaurado a
# panel/views.py, que es su sitio real -- panel/urls.py importa estas 7
# vistas de aqui sin cambios.
from fleet.views import (
    MachineAssetListView,
    MachineAssetCreateView,
    MachineAssetUpdateView,
    MachineAssetDeactivateView,
    MachineAssetReactivateView,
    MachineAssetDeleteView,
    MachineAssetAnalyticsView,
)

# --- Google Drive one-time OAuth setup (S014-H10) ---
from panel.views_gdrive_setup import (
    GDriveAuthorizeView,
    GDriveOAuthCallbackView,
)
