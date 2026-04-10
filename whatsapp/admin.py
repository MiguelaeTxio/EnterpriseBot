# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/admin.py
"""
Django admin registration for the whatsapp channel app models.
Registers WhatsAppSession, WhatsAppMessage and WhatsAppTemplate with
display and filtering options optimised for development inspection and
debugging during the Hito 4 implementation and E2E validation phases.
---
Registro en el admin de Django de los modelos de la app del canal WhatsApp.
Registra WhatsAppSession, WhatsAppMessage y WhatsAppTemplate con opciones
de visualización y filtrado optimizadas para la inspección durante el
desarrollo y la depuración en las fases de implementación y validación
E2E del Hito 4.
"""

from django.contrib import admin

from .models import WhatsAppMessage, WhatsAppSession, WhatsAppTemplate


# ---------------------------------------------------------------------------
# WHATSAPP MESSAGE INLINE — Embedded message list within a session record.
# Listado de mensajes embebido dentro del registro de sesión.
# ---------------------------------------------------------------------------

class WhatsAppMessageInline(admin.TabularInline):
    """
    Inline display of WhatsAppMessage records within a WhatsAppSession admin view.
    Provides a chronological message history directly on the session detail page,
    eliminating the need to navigate to a separate message list during debugging.
    ---
    Visualización inline de registros WhatsAppMessage dentro de la vista admin
    de WhatsAppSession. Proporciona un historial de mensajes cronológico directamente
    en la página de detalle de la sesión, eliminando la necesidad de navegar a una
    lista de mensajes separada durante la depuración.
    """

    model        = WhatsAppMessage
    extra        = 0
    readonly_fields = (
        "direction",
        "body",
        "message_sid",
        "content_sid",
        "timestamp",
    )
    ordering     = ("timestamp",)
    can_delete   = False

    def has_add_permission(self, request, obj=None):
        """
        Disables inline message creation — messages are created exclusively
        by the webhook handler, never manually via the admin interface.
        ---
        Deshabilita la creación inline de mensajes — los mensajes se crean
        exclusivamente por el manejador del webhook, nunca manualmente a través
        del interfaz de administración.
        """
        return False


# ---------------------------------------------------------------------------
# WHATSAPP SESSION ADMIN
# ---------------------------------------------------------------------------

@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    """
    Admin configuration for WhatsAppSession.
    Displays session metadata and embeds the full message history inline
    for efficient debugging during E2E validation of the chatbot flow.
    ---
    Configuración de admin para WhatsAppSession.
    Muestra los metadatos de sesión e incrusta el historial completo de mensajes
    inline para una depuración eficiente durante la validación E2E del flujo
    del chatbot.
    """

    list_display  = (
        "id",
        "company",
        "phone_number",
        "session_start",
        "last_message_at",
        "is_active",
    )
    list_filter   = ("is_active", "company")
    search_fields = ("phone_number", "company__name")
    readonly_fields = (
        "company",
        "phone_number",
        "session_start",
        "last_message_at",
    )
    ordering      = ("-session_start",)
    inlines       = [WhatsAppMessageInline]


# ---------------------------------------------------------------------------
# WHATSAPP MESSAGE ADMIN
# ---------------------------------------------------------------------------

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    """
    Admin configuration for WhatsAppMessage.
    Provides a flat searchable and filterable view of all messages across
    all sessions — useful for cross-session debugging and audit trails.
    ---
    Configuración de admin para WhatsAppMessage.
    Proporciona una vista plana, buscable y filtrable de todos los mensajes
    de todas las sesiones — útil para la depuración entre sesiones y los
    registros de auditoría.
    """

    list_display  = (
        "id",
        "session",
        "direction",
        "short_body",
        "message_sid",
        "content_sid",
        "timestamp",
    )
    list_filter   = ("direction", "session__company")
    search_fields = ("body", "message_sid", "session__phone_number")
    readonly_fields = (
        "session",
        "direction",
        "body",
        "message_sid",
        "content_sid",
        "timestamp",
    )
    ordering      = ("-timestamp",)

    @admin.display(description="Cuerpo (extracto)")
    def short_body(self, obj):
        """
        Returns a truncated version of the message body for list display,
        preventing excessively wide columns in the admin message list view.
        ---
        Devuelve una versión truncada del cuerpo del mensaje para la vista de lista,
        evitando columnas excesivamente anchas en la vista de lista de mensajes del admin.
        """
        return obj.body[:80] + "…" if len(obj.body) > 80 else obj.body


# ---------------------------------------------------------------------------
# WHATSAPP TEMPLATE ADMIN
# ---------------------------------------------------------------------------

@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    """
    Admin configuration for WhatsAppTemplate.
    Allows inspection and manual management of Meta-approved templates,
    including their ContentSid values and approval status per company.
    ---
    Configuración de admin para WhatsAppTemplate.
    Permite la inspección y gestión manual de las plantillas aprobadas por Meta,
    incluyendo sus valores ContentSid y el estado de aprobación por empresa.
    """

    list_display  = (
        "id",
        "company",
        "name",
        "content_sid",
        "category",
        "language",
        "is_active",
        "created_at",
    )
    list_filter   = ("category", "language", "is_active", "company")
    search_fields = ("name", "content_sid", "company__name")
    readonly_fields = ("created_at",)
    ordering      = ("company__name", "name")
