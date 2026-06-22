# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/admin.py
"""
Django admin registration for the chat module models.
H17 — Paso 1: ChatRoom, ChatMessage and BreakdownConversationTurn removed.
Registers BreakdownTicket with sensible list_display, list_filter and
search_fields configurations. References to room replaced by company.
---
Registro en el admin de Django de los modelos del módulo chat.
H17 — Paso 1: ChatRoom, ChatMessage y BreakdownConversationTurn eliminados.
Registra BreakdownTicket con configuraciones razonables de list_display,
list_filter y search_fields. Referencias a room sustituidas por company.
"""

from django.contrib import admin

from .models import BreakdownTicket


@admin.register(BreakdownTicket)
class BreakdownTicketAdmin(admin.ModelAdmin):
    """
    Admin configuration for BreakdownTicket.
    ---
    Configuración del admin para BreakdownTicket.
    """
    list_display    = ("ticket_date_code", "company", "contact", "status", "urgency", "machine_raw", "resolved_by", "created_at")
    list_filter     = ("status", "urgency", "company", "origin")
    search_fields   = ("ticket_date_code", "machine_raw", "fault_summary", "location", "contact__name", "contact__phone_number")
    ordering        = ("-created_at",)
    readonly_fields = ("ticket_date_code", "created_at", "updated_at")
