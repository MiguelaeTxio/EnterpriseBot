# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/admin.py
"""
Django admin registration for the budgets application.
Provides read-friendly display of insurers, tariffs, tariff lines,
budgets and budget lines for superuser management.
---
Registro en el admin de Django para la aplicacion budgets.
Proporciona visualizacion legible de aseguradoras, tarifas, lineas
de tarifa, presupuestos y lineas de presupuesto para gestion superusuario.
"""

from django.contrib import admin

from budgets.models import (
    BudgetLine,
    Budget,
    Insurer,
    InsurerTariff,
    TariffLine,
    VehicleType,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class VehicleTypeInline(admin.TabularInline):
    """
    Inline editor for VehicleType records within an Insurer admin page.
    ---
    Editor inline de registros VehicleType dentro de la pagina admin de Insurer.
    """

    model = VehicleType
    extra = 0
    fields = ("name", "sort_order", "is_active")
    ordering = ("sort_order", "name")


class TariffLineInline(admin.TabularInline):
    """
    Inline editor for TariffLine records within an InsurerTariff admin page.
    ---
    Editor inline de registros TariffLine dentro de la pagina admin de InsurerTariff.
    """

    model = TariffLine
    extra = 0
    fields = (
        "vehicle_type",
        "concept",
        "unit",
        "price",
        "km_threshold",
        "min_units",
        "requires_authorization",
    )
    ordering = ("vehicle_type__sort_order", "concept")


class InsurerTariffInline(admin.TabularInline):
    """
    Inline editor for InsurerTariff records within an Insurer admin page.
    ---
    Editor inline de registros InsurerTariff dentro de la pagina admin de Insurer.
    """

    model = InsurerTariff
    extra = 0
    fields = ("year", "valid_from", "valid_to", "notes")
    ordering = ("-valid_from",)


class BudgetLineInline(admin.TabularInline):
    """
    Read-only inline for BudgetLine records within a Budget admin page.
    ---
    Inline de solo lectura de registros BudgetLine dentro de la pagina admin
    de Budget.
    """

    model = BudgetLine
    extra = 0
    readonly_fields = (
        "concept_code",
        "concept_label",
        "units",
        "unit_price",
        "subtotal",
        "is_surcharge",
        "sort_order",
    )
    fields = readonly_fields
    ordering = ("sort_order",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# ModelAdmin registrations
# ---------------------------------------------------------------------------

@admin.register(Insurer)
class InsurerAdmin(admin.ModelAdmin):
    """
    Admin view for Insurer model.
    ---
    Vista admin para el modelo Insurer.
    """

    list_display = (
        "name",
        "code",
        "company",
        "management_fee_percent",
        "surcharges_are_cumulative",
        "is_active",
    )
    list_filter = ("company", "is_active")
    search_fields = ("name", "code")
    inlines = [VehicleTypeInline, InsurerTariffInline]


@admin.register(InsurerTariff)
class InsurerTariffAdmin(admin.ModelAdmin):
    """
    Admin view for InsurerTariff model.
    ---
    Vista admin para el modelo InsurerTariff.
    """

    list_display = ("__str__", "insurer", "year", "valid_from", "valid_to")
    list_filter = ("insurer__company", "insurer", "year")
    search_fields = ("insurer__name",)
    inlines = [TariffLineInline]


@admin.register(TariffLine)
class TariffLineAdmin(admin.ModelAdmin):
    """
    Admin view for TariffLine model.
    ---
    Vista admin para el modelo TariffLine.
    """

    list_display = (
        "tariff",
        "vehicle_type",
        "concept",
        "unit",
        "price",
        "km_threshold",
        "min_units",
        "requires_authorization",
    )
    list_filter = ("tariff__insurer__company", "tariff__insurer", "concept")
    search_fields = ("tariff__insurer__name",)


@admin.register(VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    """
    Admin view for VehicleType model.
    ---
    Vista admin para el modelo VehicleType.
    """

    list_display = ("name", "insurer", "sort_order", "is_active")
    list_filter = ("insurer__company", "insurer", "is_active")
    search_fields = ("name", "insurer__name")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    """
    Admin view for Budget model with read-only breakdown inline.
    ---
    Vista admin para el modelo Budget con inline de desglose de solo lectura.
    """

    list_display = (
        "pk",
        "insurer",
        "vehicle_type",
        "service_date",
        "total_amount",
        "status",
        "operator",
        "created_at",
    )
    list_filter = (
        "company",
        "insurer",
        "status",
        "is_night_or_holiday",
        "is_loaded",
        "is_overnight",
    )
    search_fields = ("insurer__name", "operator__user__username")
    readonly_fields = (
        "total_amount",
        "km_total",
        "tariff",
        "created_at",
    )
    inlines = [BudgetLineInline]


@admin.register(BudgetLine)
class BudgetLineAdmin(admin.ModelAdmin):
    """
    Admin view for BudgetLine model (read-only).
    ---
    Vista admin para el modelo BudgetLine (solo lectura).
    """

    list_display = (
        "budget",
        "concept_label",
        "units",
        "unit_price",
        "subtotal",
        "is_surcharge",
    )
    list_filter = ("is_surcharge", "concept_code")
    search_fields = ("budget__insurer__name", "concept_label")
    readonly_fields = (
        "budget",
        "concept_code",
        "concept_label",
        "units",
        "unit_price",
        "subtotal",
        "is_surcharge",
        "sort_order",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
