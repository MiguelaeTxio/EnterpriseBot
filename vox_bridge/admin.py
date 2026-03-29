# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/admin.py
from django.contrib import admin
from .models import CallInteraction

@admin.register(CallInteraction)
class CallInteractionAdmin(admin.ModelAdmin):
    """
    Admin configuration for Twilio Voice Interactions.
    ---
    Configuración administrativa para las interacciones de voz de Twilio.
    """
    
    # List view configuration / Configuración de la vista de lista
    list_display = (
        'call_sid', 
        'from_number', 
        'status', 
        'department_detected', 
        'created_at'
    )
    
    # Filter configuration / Configuración de filtros
    list_filter = ('status', 'direction', 'created_at')
    
    # Search configuration / Configuración de búsqueda
    search_fields = ('call_sid', 'from_number', 'stream_sid', 'full_transcript')
    
    # Read-only fields / Campos de solo lectura para auditoría
    readonly_fields = ('created_at', 'updated_at', 'call_sid', 'stream_sid', 'account_sid')
    
    # Detailed view organization / Organización de la vista de detalle
    fieldsets = (
        ('Identificadores de Red (Twilio)', {
            'fields': ('call_sid', 'stream_sid', 'account_sid')
        }),
        ('Detalles de la Comunicación', {
            'fields': ('from_number', 'to_number', 'direction', 'status')
        }),
        ('Inteligencia de Datos y Transcripción', {
            'fields': ('department_detected', 'full_transcript')
        }),
        ('Métricas y Auditoría', {
            'fields': ('duration', 'price', 'created_at', 'updated_at')
        }),
    )

