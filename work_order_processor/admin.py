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
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import TaskPhoto, WorkOrder, WorkOrderEntry, WorkOrderEntryLine


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
        "machine_raw",
        "machine_norm",
        "fault_description",
        "repair_notes",
        "hc",
        "hf",
        "or_val",
        "delta_hours",
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
        "uncertain_date",
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
        "uncertain_date",
        "extraction_confidence",
    )
    list_filter     = ("extraction_confidence", "work_date", "uncertain_date")
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
                "uncertain_date",
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
        "machine_norm",
        "machine_asset",
        "hc",
        "hf",
        "delta_hours",
        "extraction_confidence_display",
    )
    list_filter     = (
        "entry__extraction_confidence",
        "machine_asset__company_code",
        "machine_asset__family",
    )
    search_fields   = (
        "machine_raw",
        "machine_norm",
        "fault_description",
        "entry__worker_name",
        "entry__work_order__company__name",
    )
    readonly_fields = (
        "entry",
        "line_number",
        "machine_raw",
        "machine_norm",
        "machine_asset",
        "delta_hours",
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
                "machine_raw",
                "machine_norm",
            ),
        }),
        (_("Trabajo"), {
            "fields": (
                "fault_description",
                "repair_notes",
                "hc",
                "hf",
                "or_val",
                "delta_hours",
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


@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    """
    Admin configuration for TaskPhoto (H7, S016). Read-only view for
    audit/support purposes -- photos are created exclusively from the
    operator form widget (panel.views_task_photos), never from the admin.

    ---

    Configuración del admin para TaskPhoto (H7, S016). Vista de solo
    lectura para auditoría/soporte -- las fotos se crean exclusivamente
    desde el widget del formulario de operario (panel.views_task_photos),
    nunca desde el admin.
    """

    list_display = (
        "id",
        "line",
        "machine_asset",
        "breakdown_ticket",
        "uploaded_by",
        "gcs_blob_name",
        "drive_web_link",
        "created_at",
    )
    list_filter = ("company", "machine_asset__company_code")
    search_fields = (
        "line__machine_raw",
        "machine_asset__company_code",
        "breakdown_ticket__ticket_date_code",
        "caption",
    )
    readonly_fields = (
        "line",
        "company",
        "breakdown_ticket",
        "machine_asset",
        "uploaded_by",
        "image",
        "drive_file_id",
        "drive_web_link",
        "gcs_blob_name",
        "descargar_gcs",
        "created_at",
    )
    raw_id_fields = ("line", "breakdown_ticket", "machine_asset", "uploaded_by")
    ordering = ("-created_at",)

    @admin.display(description="Descarga (GCS, URL firmada temporal)")
    def descargar_gcs(self, obj) -> str:
        """
        Genera una URL firmada V4 bajo demanda solo en la vista de
        detalle (nunca en list_display, para no firmar N URLs en cada
        carga del listado). Si el objeto no tiene gcs_blob_name (aún
        no migrado o legado en Drive) o si GCS no está configurado, se
        muestra un texto informativo en vez de un enlace roto.
        ---
        Generates a V4 signed URL on demand, only in the detail view
        (never in list_display, to avoid signing N URLs on every list
        page load). If the object has no gcs_blob_name (not migrated
        yet, or Drive legacy) or GCS isn't configured, shows an
        informational text instead of a broken link.
        """
        if not obj.gcs_blob_name:
            return "(sin archivo en GCS -- ver drive_web_link si es legado)"
        try:
            from spare_parts.gcs_service import (
                TASK_PHOTOS_BUCKET,
                generate_signed_url,
            )
            url = generate_signed_url(TASK_PHOTOS_BUCKET, obj.gcs_blob_name)
            return format_html('<a href="{}" target="_blank">Descargar</a>', url)
        except Exception as exc:
            return f"(error generando URL firmada: {exc})"
