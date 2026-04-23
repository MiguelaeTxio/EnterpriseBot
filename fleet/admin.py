# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/admin.py

"""
Django admin configuration for the fleet application.
Currently registers MachineAsset only. MaintenanceLog and MaintenanceItem
admins are deferred until WorkOrderEntryLine exists in the database
(work_order_processor migration 0002), because MaintenanceLog carries a
ForeignKey to that model which Django's admin checks cannot resolve until
the model is migrated.

---

Configuración del admin Django para la aplicación fleet.
Actualmente registra únicamente MachineAsset. Los admins de MaintenanceLog
y MaintenanceItem están diferidos hasta que WorkOrderEntryLine exista en BD
(migración 0002 de work_order_processor), ya que MaintenanceLog tiene un
ForeignKey a ese modelo que los checks del admin de Django no pueden resolver
hasta que el modelo esté migrado.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import MachineAsset, MaintenanceItem, MaintenanceLog


# ---------------------------------------------------------------------------
# Inlines compartidos / Shared inlines
# ---------------------------------------------------------------------------

class MaintenanceItemInline(admin.TabularInline):
    """
    Inline editor for MaintenanceItem records within a MaintenanceLog.

    ---

    Editor inline para registros MaintenanceItem dentro de un MaintenanceLog.
    """

    model            = MaintenanceItem
    extra            = 1
    fields           = (
        "tipo",
        "descripcion",
        "referencia",
        "cantidad",
        "coste_unitario",
        "albaran_ref",
    )
    show_change_link = True


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
        "fecha",
        "operario",
        "horas_imputadas",
        "descripcion",
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
    MaintenanceLog inline is deferred until WorkOrderEntryLine is migrated.

    ---

    Vista admin para MachineAsset.
    Proporciona visualización de lista con campos de identificación clave,
    búsqueda por código y modelo, y filtros por empresa, familia y estado
    activo. El inline de MaintenanceLog está diferido hasta que
    WorkOrderEntryLine esté migrado.
    """

    list_display    = (
        "codigo",
        "marca_modelo",
        "empresa_codigo",
        "familia",
        "tipo_nombre",
        "matricula",
        "es_activo",
        "importado_en",
    )
    list_filter     = (
        "empresa_codigo",
        "familia",
        "es_activo",
        "company",
    )
    search_fields   = (
        "codigo",
        "matricula",
        "marca_modelo",
        "num_bastidor",
        "empresa_codigo",
        "empresa_nombre",
    )
    readonly_fields = (
        "importado_en",
        "actualizado_en",
    )
    fieldsets       = (
        (_("Identificación"), {
            "fields": (
                "company",
                "codigo",
                "matricula",
                "num_bastidor",
                "marca_modelo",
            ),
        }),
        (_("Clasificación Catálogo"), {
            "fields": (
                "empresa_codigo",
                "empresa_nombre",
                "familia",
                "tipo_codigo",
                "tipo_nombre",
            ),
        }),
        (_("Datos de Adquisición"), {
            "fields": (
                "fecha_compra",
                "kms",
                "horas",
            ),
        }),
        (_("Estado y Auditoría"), {
            "fields": (
                "es_activo",
                "importado_en",
                "actualizado_en",
            ),
        }),
    )
    inlines         = [MaintenanceLogInline]
    ordering        = ["empresa_codigo", "familia", "codigo"]


# ---------------------------------------------------------------------------
# MaintenanceLog admin — ACTIVO / ACTIVE
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
        "fecha",
        "operario",
        "horas_imputadas",
        "work_entry_line",
        "creado_en",
    )
    list_filter     = (
        "fecha",
        "machine_asset__empresa_codigo",
        "machine_asset__familia",
    )
    search_fields   = (
        "machine_asset__codigo",
        "machine_asset__marca_modelo",
        "operario",
        "descripcion",
    )
    readonly_fields = (
        "creado_en",
        "actualizado_en",
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
                "fecha",
                "operario",
                "horas_imputadas",
            ),
        }),
        (_("Detalle"), {
            "fields": (
                "descripcion",
                "observaciones",
            ),
        }),
        (_("Auditoría"), {
            "fields": (
                "creado_en",
                "actualizado_en",
            ),
        }),
    )
    inlines         = [MaintenanceItemInline]
    ordering        = ["-fecha", "machine_asset"]


@admin.register(MaintenanceItem)
class MaintenanceItemAdmin(admin.ModelAdmin):
    """
    Admin view for MaintenanceItem.

    ---

    Vista admin para MaintenanceItem.
    """

    list_display    = (
        "maintenance_log",
        "tipo",
        "descripcion",
        "referencia",
        "cantidad",
        "coste_unitario",
        "albaran_ref",
        "creado_en",
    )
    list_filter     = (
        "tipo",
        "maintenance_log__machine_asset__empresa_codigo",
    )
    search_fields   = (
        "descripcion",
        "referencia",
        "albaran_ref",
        "maintenance_log__machine_asset__codigo",
    )
    readonly_fields = ("creado_en",)
    raw_id_fields   = ("maintenance_log",)
    ordering        = ["-creado_en"]
