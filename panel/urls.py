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
)

app_name = "panel"

urlpatterns = [
    # Authentication routes — Rutas de autenticación.
    path("login/", PanelLoginView.as_view(), name="login"),
    path("logout/", PanelLogoutView.as_view(), name="logout"),

    # Dashboard — Panel principal.
    path("", PanelDashboardView.as_view(), name="dashboard"),

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
]
