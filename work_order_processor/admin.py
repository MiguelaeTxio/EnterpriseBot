# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/admin.py

"""
Django admin registration for the work_order_processor application.
Registers WorkOrder, WorkOrderEntry and WorkOrderEntryLine with enhanced
display, filtering and inline editors to facilitate supervision of
extraction results and error diagnosis.

---

Registro en el admin de Django para la aplicación work_order_processor.
Registra WorkOrder, WorkOrderEntry y WorkOrderEntryLine con visualización,
filtrado y editores inline mejorados para facilitar la supervisión de los
resultados de extracción y el diagnóstico de errores.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine


# ---------------------------------------------------------------------------
# WorkOrderEntryLine inline / Inline de WorkOrderEntryLine
# ---------------------------------------------------------------------------

class WorkOrderEntryLineInline(admin.TabularInline):
    """
    Inline display of WorkOrderEntryLine records within the WorkOrderEntry
    admin. Shows all work block fields for quick review of each extracted
    line within a page.

    ---

    Visualización inline de los registros WorkOrderEntryLine dentro del admin
    de WorkOrderEntry. Muestra todos los campos del bloque de trabajo para
    revisión rápida de cada línea extraída dentro de una página.
    """

    model            = WorkOrderEntryLine
    extra            = 0
    can_delete       = False
    show_change_link = True
    readonly_fields  = (
        "line_number",
        "machine_asset",
        "maquina_raw",
        "maquina_norm",
        "descripcion_averia",
        "reparacion",
        "hc",
        "hf",
        "or_val",
        "delta_horas",
        "flags",
    )
    fields = readonly_fields


# ---------------------------------------------------------------------------
# WorkOrderEntry inline / Inline de WorkOrderEntry
# ---------------------------------------------------------------------------

class WorkOrderEntryInline(admin.TabularInline):
    """
    Inline display of WorkOrderEntry records within the WorkOrder admin.
    Shows page-level fields and confidence for quick review.

    ---

    Visualización inline de los registros WorkOrderEntry dentro del admin
    de WorkOrder. Muestra los campos a nivel de página y la confianza
    para revisión rápida.
    """

    model            = WorkOrderEntry
    extra            = 0
    can_delete       = False
    show_change_link = True
    readonly_fields  = (
        "page_number",
        "worker_name",
        "work_date",
        "fecha_incierta",
        "extraction_confidence",
    )
    fields = readonly_fields


# ---------------------------------------------------------------------------
# WorkOrder admin / Admin de WorkOrder
# ---------------------------------------------------------------------------

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

    list_display    = (
        "id",
        "company",
        "uploaded_by",
        "status",
        "total_pages",
        "processed_pages",
        "upload_date",
    )
    list_filter     = ("status", "company")
    search_fields   = ("uploaded_by__user__username", "company__name")
    readonly_fields = (
        "upload_date",
        "total_pages",
        "processed_pages",
        "status",
        "error_log",
        "excel_file",
    )
    ordering        = ("-upload_date",)
    inlines         = [WorkOrderEntryInline]
    fieldsets       = (
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


# ---------------------------------------------------------------------------
# WorkOrderEntry admin / Admin de WorkOrderEntry
# ---------------------------------------------------------------------------

@admin.register(WorkOrderEntry)
class WorkOrderEntryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WorkOrderEntry model.
    Provides detailed view of each extracted page with filtering by
    confidence level and date, and search by worker name.
    Includes WorkOrderEntryLine inline for full block-level detail.

    ---

    Configuración del admin para el modelo WorkOrderEntry.
    Proporciona vista detallada de cada página extraída con filtrado por
    nivel de confianza y fecha, y búsqueda por nombre de operario.
    Incluye el inline WorkOrderEntryLine para detalle completo a nivel
    de bloque.
    """

    list_display    = (
        "id",
        "work_order",
        "page_number",
        "worker_name",
        "work_date",
        "fecha_incierta",
        "extraction_confidence",
    )
    list_filter     = ("extraction_confidence", "work_date", "fecha_incierta")
    search_fields   = ("worker_name", "work_order__company__name")
    readonly_fields = (
        "work_order",
        "page_number",
        "raw_gemini_response",
        "extraction_confidence",
    )
    ordering        = ("work_order", "page_number")
    inlines         = [WorkOrderEntryLineInline]
    fieldsets       = (
        (_("Ubicación"), {
            "fields": ("work_order", "page_number"),
        }),
        (_("Datos de Página"), {
            "fields": (
                "worker_name",
                "work_date",
                "fecha_incierta",
            ),
        }),
        (_("Auditoría de Extracción"), {
            "fields": ("extraction_confidence", "raw_gemini_response"),
            "classes": ("collapse",),
        }),
    )


# ---------------------------------------------------------------------------
# WorkOrderEntryLine admin / Admin de WorkOrderEntryLine
# ---------------------------------------------------------------------------

@admin.register(WorkOrderEntryLine)
class WorkOrderEntryLineAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WorkOrderEntryLine model.
    Provides direct access to individual work blocks for search, filtering
    and correction without navigating through the parent WorkOrderEntry.

    ---

    Configuración del admin para el modelo WorkOrderEntryLine.
    Proporciona acceso directo a bloques de trabajo individuales para
    búsqueda, filtrado y corrección sin navegar a través del
    WorkOrderEntry padre.
    """

    list_display    = (
        "id",
        "entry",
        "line_number",
        "maquina_norm",
        "machine_asset",
        "hc",
        "hf",
        "delta_horas",
        "extraction_confidence_display",
    )
    list_filter     = (
        "entry__extraction_confidence",
        "machine_asset__empresa_codigo",
        "machine_asset__familia",
    )
    search_fields   = (
        "maquina_raw",
        "maquina_norm",
        "descripcion_averia",
        "entry__worker_name",
        "entry__work_order__company__name",
    )
    readonly_fields = (
        "entry",
        "line_number",
        "maquina_raw",
        "maquina_norm",
        "machine_asset",
        "delta_horas",
        "flags",
    )
    raw_id_fields   = ("machine_asset",)
    ordering        = ("entry__work_order", "entry__page_number", "line_number")
    fieldsets       = (
        (_("Ubicación"), {
            "fields": ("entry", "line_number"),
        }),
        (_("Máquina"), {
            "fields": (
                "machine_asset",
                "maquina_raw",
                "maquina_norm",
            ),
        }),
        (_("Trabajo"), {
            "fields": (
                "descripcion_averia",
                "reparacion",
                "hc",
                "hf",
                "or_val",
                "delta_horas",
            ),
        }),
        (_("Flags de Incidencia"), {
            "fields": ("flags",),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Confianza"))
    def extraction_confidence_display(self, obj: WorkOrderEntryLine) -> str:
        """
        Returns the extraction confidence of the parent WorkOrderEntry
        for display in the WorkOrderEntryLine list view.

        ---

        Devuelve la confianza de extracción del WorkOrderEntry padre
        para visualización en la lista de WorkOrderEntryLine.
        """
        return obj.entry.get_extraction_confidence_display()
