# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/admin.py
"""
Django admin registration for the spare parts and delivery note
module.
---
Registro en el admin de Django para el módulo de albaranes y
repuestos.
"""
from django.contrib import admin

from .models import DeliveryNote, DeliveryNoteLine, SparePartEntry, StockMovement


class DeliveryNoteLineInline(admin.TabularInline):
    """
    Inline editor for delivery note lines within the delivery note
    admin page.
    ---
    Editor inline de líneas de albarán dentro de la página de admin
    del albarán.
    """

    model = DeliveryNoteLine
    extra = 0
    fields = (
        'line_number',
        'reference',
        'description',
        'quantity',
        'unit_price',
        'total_price',
        'assignment_type',
        'machine',
        'spare_part_entry',
    )


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    """
    Admin configuration for DeliveryNote.
    ---
    Configuración de admin para DeliveryNote.
    """

    list_display = (
        'id',
        'company',
        'supplier_name',
        'delivery_number',
        'delivery_date',
        'status',
        'source_type',
        'created_at',
    )
    list_filter = ('company', 'status', 'source_type')
    search_fields = ('supplier_name', 'supplier_tax_id', 'delivery_number')
    date_hierarchy = 'delivery_date'
    inlines = [DeliveryNoteLineInline]


@admin.register(SparePartEntry)
class SparePartEntryAdmin(admin.ModelAdmin):
    """
    Admin configuration for SparePartEntry. Includes status and
    origin_type as primary filters, since these are the two axes
    governing the spare part lifecycle (annex H10, sections 2.2 and
    3.6).
    ---
    Configuración de admin para SparePartEntry. Incluye status y
    origin_type como filtros principales, ya que son los dos ejes
    que gobiernan el ciclo de vida del repuesto (anexo H10,
    secciones 2.2 y 3.6).
    """

    list_display = (
        'id',
        'description',
        'reference',
        'company',
        'status',
        'origin_type',
        'machine',
        'breakdown_ticket',
        'stock_quantity',
        'stock_level',
        'pre_assigned_at',
        'consumed_at',
    )
    list_filter = ('company', 'status', 'origin_type', 'is_uncountable')
    search_fields = ('description', 'reference', 'supplier_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """
    Admin configuration for StockMovement.
    ---
    Configuración de admin para StockMovement.
    """

    list_display = (
        'id',
        'spare_part_entry',
        'movement_type',
        'quantity',
        'machine',
        'breakdown_ticket',
        'spare_part_line',
        'created_by',
        'created_at',
    )
    list_filter = ('movement_type', 'created_by')
    search_fields = ('spare_part_entry__description', 'notes')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
