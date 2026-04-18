# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/admin.py
"""
Django admin registration for all ivr_config models.
Provides internal platform management exclusively for superusers via /admin/.
Each ModelAdmin is configured with list_display, list_filter and search_fields
appropriate to each entity's role in the IVR multicompany system.
---
Registro en el admin de Django de todos los modelos de ivr_config.
Proporciona gestión interna de la plataforma exclusivamente para superusuarios vía /admin/.
Cada ModelAdmin está configurado con list_display, list_filter y search_fields
apropiados al rol de cada entidad en el sistema IVR multiempresa.
"""

from django.contrib import admin

from .models import (
    CallFlow,
    Company,
    CompanyUser,
    Contact,
    CorporateVoiceProfile,
    DataCaptureSet,
    PhoneNumber,
    PresenceStatus,
    Section,
)


# ---------------------------------------------------------------------------
# COMPANY
# ---------------------------------------------------------------------------

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    Admin interface for the Company model.
    Displays key identification and operational status fields.
    ---
    Interfaz de administración para el modelo Company.
    Muestra los campos clave de identificación y estado operativo.
    """

    list_display = ("name", "slug", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("name",)


# ---------------------------------------------------------------------------
# COMPANY USER
# ---------------------------------------------------------------------------

@admin.register(CompanyUser)
class CompanyUserAdmin(admin.ModelAdmin):
    """
    Admin interface for the CompanyUser model.
    Displays company association, linked Django user, role and active status.
    ---
    Interfaz de administración para el modelo CompanyUser.
    Muestra la empresa asociada, el usuario Django vinculado, el rol y el estado activo.
    """

    list_display = ("__str__", "company", "user", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "company")
    search_fields = ("user__username", "user__email", "company__name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name", "user__username")


# ---------------------------------------------------------------------------
# CORPORATE VOICE PROFILE
# ---------------------------------------------------------------------------

@admin.register(CorporateVoiceProfile)
class CorporateVoiceProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for the CorporateVoiceProfile model.
    Displays the company and active status. Tone guidelines are shown in detail view.
    ---
    Interfaz de administración para el modelo CorporateVoiceProfile.
    Muestra la empresa y el estado activo. Las directrices de tono se muestran en la vista de detalle.
    """

    list_display = ("company", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "company")
    search_fields = ("company__name", "tone_guidelines")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name",)


# ---------------------------------------------------------------------------
# DATA CAPTURE SET
# ---------------------------------------------------------------------------

@admin.register(DataCaptureSet)
class DataCaptureSetAdmin(admin.ModelAdmin):
    """
    Admin interface for the DataCaptureSet model.
    Displays company association and capture set name.
    ---
    Interfaz de administración para el modelo DataCaptureSet.
    Muestra la empresa asociada y el nombre del conjunto de captura.
    """

    list_display = ("name", "company", "created_at", "updated_at")
    list_filter = ("company",)
    search_fields = ("name", "company__name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name", "name")


# ---------------------------------------------------------------------------
# SECTION
# ---------------------------------------------------------------------------

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    """
    Admin interface for the Section model.
    Displays company, name, data capture set assignment, section-level call flow
    and active status. The M2M contacts field is shown via filter_horizontal
    for usability.
    The call_flow field (added in Paso 18, 2026-04-16) designates the specific
    IVR CallFlow loaded by the engine when the caller's intent maps to this
    section (Estrategia B — dynamic intent-based loading).
    ---
    Interfaz de administración para el modelo Section.
    Muestra la empresa, el nombre, la asignación de conjunto de captura, el flujo
    IVR de sección y el estado activo. El campo M2M de contactos se muestra
    mediante filter_horizontal para mejor usabilidad.
    El campo call_flow (añadido en el Paso 18, 2026-04-16) designa el CallFlow
    IVR específico que el motor carga cuando la intención del llamante se mapea
    a esta sección (Estrategia B — carga dinámica por intención).
    """

    list_display = ("name", "company", "data_capture_set", "call_flow", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("name", "company__name", "description")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ()
    ordering = ("company__name", "name")


# ---------------------------------------------------------------------------
# CONTACT
# ---------------------------------------------------------------------------

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """
    Admin interface for the Contact model.
    Displays company, name, phone number, internal flag and linked company user.
    ---
    Interfaz de administración para el modelo Contact.
    Muestra la empresa, el nombre, el número de teléfono, el indicador interno
    y el usuario de empresa vinculado.
    """

    list_display = ("name", "company", "phone_number", "is_internal", "company_user", "created_at")
    list_filter = ("is_internal", "company")
    search_fields = ("name", "phone_number", "company__name", "company_user__user__username")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name", "name")


# ---------------------------------------------------------------------------
# CALL FLOW
# ---------------------------------------------------------------------------

@admin.register(CallFlow)
class CallFlowAdmin(admin.ModelAdmin):
    """
    Admin interface for the CallFlow model.
    Displays company, flow name, fallback section and active status.
    System instruction and initial greeting are available in the detail view.
    The fallback_section field (added in Paso 18, 2026-04-16) designates the
    section of last resort for this flow: when no active section can attend the
    caller, the agent transfers the call to the human responsible for this section.
    Each PhoneNumber (and therefore each CallFlow) can have its own independent
    fallback section, allowing per-number responsibility delegation.
    ---
    Interfaz de administración para el modelo CallFlow.
    Muestra la empresa, el nombre del flujo, la sección de fallback y el estado activo.
    La instrucción de sistema y el saludo inicial están disponibles en la vista de detalle.
    El campo fallback_section (añadido en el Paso 18, 2026-04-16) designa la sección
    de último recurso para este flujo: cuando ninguna sección activa puede atender al
    llamante, el agente transfiere la llamada al responsable humano de esa sección.
    Cada PhoneNumber (y por tanto cada CallFlow) puede tener su propia sección de
    fallback independiente, permitiendo la delegación de responsabilidades por número.
    """

    list_display = ("name", "company", "fallback_section", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "company")
    search_fields = ("name", "company__name", "system_instruction")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name", "name")


# ---------------------------------------------------------------------------
# PHONE NUMBER
# ---------------------------------------------------------------------------

@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    """
    Admin interface for the PhoneNumber model.
    Displays company, E.164 number, friendly name, assigned call flow and active status.
    ---
    Interfaz de administración para el modelo PhoneNumber.
    Muestra la empresa, el número E.164, el nombre amigable, el flujo IVR asignado
    y el estado activo.
    """

    list_display = ("number", "company", "friendly_name", "call_flow", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("number", "friendly_name", "company__name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("company__name", "number")


# ---------------------------------------------------------------------------
# PRESENCE STATUS
# ---------------------------------------------------------------------------

@admin.register(PresenceStatus)
class PresenceStatusAdmin(admin.ModelAdmin):
    """
    Admin interface for the PresenceStatus model.
    Displays company user, current status, start and end times,
    and whether a reminder has been sent.
    ---
    Interfaz de administración para el modelo PresenceStatus.
    Muestra el usuario de empresa, el estado actual, los tiempos de inicio y fin,
    y si se ha enviado un recordatorio.
    """

    list_display = ("company_user", "status", "starts_at", "ends_at", "reminder_sent_at", "created_at")
    list_filter = ("status", "company_user__company")
    search_fields = ("company_user__user__username", "company_user__company__name")
    readonly_fields = ("created_at",)
    ordering = ("-starts_at",)
