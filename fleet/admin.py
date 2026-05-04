# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/admin.py

"""
Django admin configuration for the fleet application.
Registers MachineAsset, MaintenanceLog and MaintenanceItem with customised
list displays, filters, search fields and inline editors.

---

Configuración del admin de Django para la aplicación fleet.
Registra MachineAsset, MaintenanceLog y MaintenanceItem con visualizaciones
de lista, filtros, campos de búsqueda y editores inline personalizados.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from fleet.models import MachineAsset, MaintenanceLog, MaintenanceItem


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class MaintenanceItemInline(admin.TabularInline):
    """
    Inline editor for MaintenanceItem records within a MaintenanceLog.
    Provides compact access to spare parts and labour items from the
    intervention detail view.

    ---

    Editor inline para registros MaintenanceItem dentro de un MaintenanceLog.
    Proporciona acceso compacto a repuestos y conceptos de mano de obra desde
    la vista de detalle de la intervención.
    """

    model  = MaintenanceItem
    extra  = 0
    fields = (
        "item_type",
        "description",
        "reference",
        "quantity",
        "unit_cost",
        "delivery_note_ref",
    )


class MaintenanceLogInline(admin.TabularInline):
    """
    Inline editor for MaintenanceLog records within a MachineAsset.
    Provides a compact summary of interventions from the machine detail view.

    ---

    Editor inline para registros MaintenanceLog dentro de un MachineAsset.
    Proporciona un resumen compacto de intervenciones desde la vista de
    detalle de la máquina.
    """

    model            = MaintenanceLog
    extra            = 0
    fields           = (
        "date",
        "worker",
        "charged_hours",
        "description",
        "work_entry_line",
    )
    readonly_fields  = ("work_entry_line",)
    show_change_link = True


# ---------------------------------------------------------------------------
# MachineAsset admin / Admin de MachineAsset
# ---------------------------------------------------------------------------

@admin.register(MachineAsset)
class MachineAssetAdmin(admin.ModelAdmin):
    """
    Admin view for MachineAsset.
    Provides list display with key identification fields, search by code
    and model, and filters by company, family and active status.

    ---

    Vista admin para MachineAsset.
    Proporciona visualización de lista con campos de identificación clave,
    búsqueda por código y modelo, y filtros por empresa, familia y estado activo.
    """

    list_display    = (
        "code",
        "brand_model",
        "company_code",
        "family",
        "type_name",
        "plate",
        "is_active",
        "imported_at",
    )
    list_filter     = (
        "company_code",
        "family",
        "is_active",
        "company",
    )
    search_fields   = (
        "code",
        "plate",
        "brand_model",
        "chassis_number",
        "company_code",
        "company_name",
    )
    readonly_fields = (
        "imported_at",
        "updated_at",
    )
    fieldsets       = (
        (_("Identificación"), {
            "fields": (
                "company",
                "code",
                "plate",
                "chassis_number",
                "brand_model",
            ),
        }),
        (_("Clasificación Catálogo"), {
            "fields": (
                "company_code",
                "company_name",
                "family",
                "type_code",
                "type_name",
            ),
        }),
        (_("Datos de Adquisición"), {
            "fields": (
                "purchase_date",
                "mileage",
                "hours",
            ),
        }),
        (_("Estado y Auditoría"), {
            "fields": (
                "is_active",
                "imported_at",
                "updated_at",
            ),
        }),
    )
    inlines         = [MaintenanceLogInline]
    ordering        = ["company_code", "family", "code"]


# ---------------------------------------------------------------------------
# MaintenanceLog admin / Admin de MaintenanceLog
# ---------------------------------------------------------------------------

@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    """
    Admin view for MaintenanceLog.

    ---

    Vista admin para MaintenanceLog.
    """

    list_display    = (
        "machine_asset",
        "date",
        "worker",
        "charged_hours",
        "work_entry_line",
        "created_at",
    )
    list_filter     = (
        "date",
        "machine_asset__company_code",
        "machine_asset__family",
    )
    search_fields   = (
        "machine_asset__code",
        "machine_asset__brand_model",
        "worker",
        "description",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    raw_id_fields   = (
        "machine_asset",
        "work_entry_line",
    )
    fieldsets       = (
        (_("Máquina e Intervención"), {
            "fields": (
                "machine_asset",
                "work_entry_line",
                "date",
                "worker",
                "charged_hours",
            ),
        }),
        (_("Detalle"), {
            "fields": (
                "description",
                "notes",
            ),
        }),
        (_("Auditoría"), {
            "fields": (
                "created_at",
                "updated_at",
            ),
        }),
    )
    inlines         = [MaintenanceItemInline]
    ordering        = ["-date", "machine_asset"]


# ---------------------------------------------------------------------------
# MaintenanceItem admin / Admin de MaintenanceItem
# ---------------------------------------------------------------------------

@admin.register(MaintenanceItem)
class MaintenanceItemAdmin(admin.ModelAdmin):
    """
    Admin view for MaintenanceItem.

    ---

    Vista admin para MaintenanceItem.
    """

    list_display    = (
        "maintenance_log",
        "item_type",
        "description",
        "reference",
        "quantity",
        "unit_cost",
        "delivery_note_ref",
        "created_at",
    )
    list_filter     = (
        "item_type",
        "maintenance_log__machine_asset__company_code",
    )
    search_fields   = (
        "description",
        "reference",
        "delivery_note_ref",
        "maintenance_log__machine_asset__code",
    )
    readonly_fields = ("created_at",)
    raw_id_fields   = ("maintenance_log",)
    ordering        = ["-created_at"]
