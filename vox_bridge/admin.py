# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/admin.py
from django.contrib import admin
from .models import CallInteraction

@admin.register(CallInteraction)
class CallInteractionAdmin(admin.ModelAdmin):
    """
    Administration configuration for CallInteraction model.
    ---
    Configuración de administración para el modelo CallInteraction.
    """
    # Columnas visibles en la lista / Visible columns in list
    list_display = (
        'phone_number', 
        'department_detected', 
        'created_at'
    )
    
    # Filtros laterales / Sidebar filters
    list_filter = (
        'department_detected', 
        'created_at'
    )
    
    # Campos de búsqueda / Search fields
    search_fields = (
        'phone_number', 
        'call_id'
    )
    
    # Orden predeterminado / Default ordering
    ordering = ('-created_at',)
    
    # Campos de solo lectura para integridad / Read-only fields
    readonly_fields = ('created_at',)
