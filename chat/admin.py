# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/admin.py
"""
Django admin registration for the chat module models.
Registers ChatRoom, ChatMessage, BreakdownTicket and BreakdownConversationTurn
with sensible list_display, list_filter and search_fields configurations.
---
Registro en el admin de Django de los modelos del módulo chat.
Registra ChatRoom, ChatMessage, BreakdownTicket y BreakdownConversationTurn
con configuraciones razonables de list_display, list_filter y search_fields.
"""

from django.contrib import admin

from .models import (
    BreakdownConversationTurn,
    BreakdownTicket,
    ChatMessage,
    ChatRoom,
)


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    """
    Admin configuration for ChatRoom.
    ---
    Configuración del admin para ChatRoom.
    """
    list_display   = ("name", "company", "room_type", "section", "is_active", "created_at")
    list_filter    = ("room_type", "is_active", "company")
    search_fields  = ("name", "company__name", "section__name")
    ordering       = ("company__name", "room_type", "name")
    readonly_fields = ("created_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    Admin configuration for ChatMessage.
    ---
    Configuración del admin para ChatMessage.
    """
    list_display   = ("room", "direction", "sender_contact", "sender_user", "whatsapp_sid", "created_at")
    list_filter    = ("direction", "room__company", "room")
    search_fields  = ("body", "whatsapp_sid", "sender_contact__name", "sender_user__user__username")
    ordering       = ("-created_at",)
    readonly_fields = ("created_at",)


class BreakdownConversationTurnInline(admin.TabularInline):
    """
    Inline display of BreakdownConversationTurn inside BreakdownTicket admin.
    ---
    Vista inline de BreakdownConversationTurn dentro del admin de BreakdownTicket.
    """
    model           = BreakdownConversationTurn
    extra           = 0
    readonly_fields = ("role", "content", "created_at")
    can_delete      = False


@admin.register(BreakdownTicket)
class BreakdownTicketAdmin(admin.ModelAdmin):
    """
    Admin configuration for BreakdownTicket.
    Includes an inline for BreakdownConversationTurn to inspect the full
    dialogue history without leaving the ticket detail page.
    ---
    Configuración del admin para BreakdownTicket.
    Incluye un inline de BreakdownConversationTurn para inspeccionar el historial
    completo de diálogo sin salir de la página de detalle del ticket.
    """
    list_display   = ("contact", "room", "status", "urgency", "machine_raw", "resolved_by", "created_at")
    list_filter    = ("status", "urgency", "room__company")
    search_fields  = ("machine_raw", "fault_summary", "location", "contact__name", "contact__phone_number")
    ordering       = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines        = [BreakdownConversationTurnInline]


@admin.register(BreakdownConversationTurn)
class BreakdownConversationTurnAdmin(admin.ModelAdmin):
    """
    Admin configuration for BreakdownConversationTurn.
    Primarily for audit purposes — normal inspection is via the inline
    in BreakdownTicketAdmin.
    ---
    Configuración del admin para BreakdownConversationTurn.
    Principalmente para auditoría — la inspección habitual se hace mediante
    el inline en BreakdownTicketAdmin.
    """
    list_display   = ("ticket", "role", "created_at")
    list_filter    = ("role", "ticket__room__company")
    search_fields  = ("content", "ticket__contact__name")
    ordering       = ("ticket", "created_at")
    readonly_fields = ("created_at",)
