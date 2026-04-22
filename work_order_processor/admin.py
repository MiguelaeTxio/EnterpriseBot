# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/admin.py

"""
Django admin registration for the work_order_processor application.
Registers WorkOrder and WorkOrderEntry with enhanced display and filtering
to facilitate supervision of extraction results and error diagnosis.

---

Registro en el admin de Django para la aplicación work_order_processor.
Registra WorkOrder y WorkOrderEntry con visualización y filtrado mejorados
para facilitar la supervisión de los resultados de extracción y el
diagnóstico de errores.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import WorkOrder, WorkOrderEntry


class WorkOrderEntryInline(admin.TabularInline):
    """
    Inline display of WorkOrderEntry records within the WorkOrder admin.
    Shows key extracted fields and confidence level for quick review.

    ---

    Visualización inline de los registros WorkOrderEntry dentro del admin
    de WorkOrder. Muestra los campos extraídos clave y el nivel de confianza
    para revisión rápida.
    """

    model          = WorkOrderEntry
    extra          = 0
    can_delete     = False
    show_change_link = True
    readonly_fields = (
        "page_number",
        "worker_name",
        "work_date",
        "start_time",
        "end_time",
        "vehicle_ref",
        "location",
        "extraction_confidence",
    )
    fields = readonly_fields


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WorkOrder model.
    Provides list display, filtering by status and company, search by
    uploader, and inline access to extracted entries.

    ---

    Configuración del admin para el modelo WorkOrder.
    Proporciona visualización de lista, filtrado por estado y empresa,
    búsqueda por usuario que subió el archivo, y acceso inline a las
    entradas extraídas.
    """

    list_display = (
        "id",
        "company",
        "uploaded_by",
        "status",
        "total_pages",
        "processed_pages",
        "upload_date",
    )
    list_filter       = ("status", "company")
    search_fields     = ("uploaded_by__user__username", "company__name")
    readonly_fields   = (
        "upload_date",
        "total_pages",
        "processed_pages",
        "status",
        "error_log",
        "excel_file",
    )
    ordering          = ("-upload_date",)
    inlines           = [WorkOrderEntryInline]

    fieldsets = (
        (_("Identificación"), {
            "fields": ("company", "uploaded_by", "source_pdf"),
        }),
        (_("Estado del Procesamiento"), {
            "fields": (
                "status",
                "total_pages",
                "processed_pages",
                "upload_date",
                "error_log",
            ),
        }),
        (_("Resultado"), {
            "fields": ("excel_file",),
        }),
    )


@admin.register(WorkOrderEntry)
class WorkOrderEntryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WorkOrderEntry model.
    Provides detailed view of each extracted page with filtering by
    confidence level and date, and search by worker name and vehicle
    reference.

    ---

    Configuración del admin para el modelo WorkOrderEntry.
    Proporciona vista detallada de cada página extraída con filtrado por
    nivel de confianza y fecha, y búsqueda por nombre de operario y
    referencia de vehículo.
    """

    list_display = (
        "id",
        "work_order",
        "page_number",
        "worker_name",
        "work_date",
        "start_time",
        "end_time",
        "vehicle_ref",
        "extraction_confidence",
    )
    list_filter   = ("extraction_confidence", "work_date")
    search_fields = ("worker_name", "vehicle_ref", "work_order__company__name")
    readonly_fields = (
        "work_order",
        "page_number",
        "raw_gemini_response",
        "extraction_confidence",
    )
    ordering      = ("work_order", "page_number")

    fieldsets = (
        (_("Ubicación"), {
            "fields": ("work_order", "page_number"),
        }),
        (_("Datos Extraídos"), {
            "fields": (
                "worker_name",
                "work_date",
                "start_time",
                "end_time",
                "vehicle_ref",
                "location",
                "work_description",
                "observations",
            ),
        }),
        (_("Auditoría de Extracción"), {
            "fields": ("extraction_confidence", "raw_gemini_response"),
            "classes": ("collapse",),
        }),
    )
