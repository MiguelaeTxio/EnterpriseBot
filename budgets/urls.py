# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/urls.py
"""
URL configuration for the budgets application.
All routes are prefixed with /panel/budgets/ via enterprise_core/urls.py.
---
Configuracion de URLs para la aplicacion budgets.
Todas las rutas tienen el prefijo /panel/budgets/ via enterprise_core/urls.py.
"""

from django.urls import path

from budgets import views

app_name = "budgets"

urlpatterns = [
    # Budget wizard — formulario secuencial guiado paso a paso.
    # Paso 1: seleccion de aseguradora.
    # Accessible to ASSISTANCE and ADMIN roles.
    # Accesible para los roles ASSISTANCE y ADMIN.
    path(
        "",
        views.BudgetWizardView.as_view(),
        name="wizard",
    ),

    # HTMX endpoint — resuelve pasos 3-9 del wizard server-side y devuelve
    # el fragmento completo de pasos segun insurer_id, base_id y vehicle_type_id.
    # HTMX endpoint — resolves wizard steps 3-9 server-side and returns
    # the full steps fragment based on insurer_id, base_id and vehicle_type_id.
    path(
        "steps/",
        views.BudgetStepsView.as_view(),
        name="steps",
    ),

    # HTMX endpoint — calcula la ruta desde la base hasta el punto kilometrico
    # via Routes API. Devuelve el fragmento de resultado al wizard.
    # HTMX endpoint — calculates route from base to kilometre point
    # via Routes API. Returns the result fragment to the wizard.
    path(
        "route-calc/",
        views.BudgetRouteCalcView.as_view(),
        name="route_calc",
    ),

    # HTMX endpoint — devuelve los tipos de vehiculo para la aseguradora
    # seleccionada en el paso 1. Usado por el formulario secuencial.
    # HTMX endpoint — returns vehicle types for the selected insurer (step 1).
    path(
        "vehicle-types/",
        views.BudgetVehicleTypesView.as_view(),
        name="vehicle_types",
    ),

    # HTMX endpoint — devuelve el selector de bases para la aseguradora
    # seleccionada en el paso 1. Usado por el formulario secuencial.
    # HTMX endpoint — returns base selector for the selected insurer (step 1).
    path(
        "bases/",
        views.BudgetBasesView.as_view(),
        name="bases",
    ),

    # HTMX endpoint — devuelve los conceptos opcionales disponibles para la
    # combinacion aseguradora + tipo de vehiculo seleccionados.
    # HTMX endpoint — returns available optional concepts for the selected
    # insurer + vehicle type combination.
    path(
        "optional-concepts/",
        views.BudgetOptionalConceptsView.as_view(),
        name="optional_concepts",
    ),

    # Budget result — muestra el total al operario tras el calculo.
    # Budget result — shows the total to the operator after calculation.
    path(
        "<int:pk>/result/",
        views.BudgetResultView.as_view(),
        name="result",
    ),

    # Budget status update — acepta o rechaza el presupuesto (ACCEPTED/REJECTED).
    # Budget status update — accepts or rejects the budget (ACCEPTED/REJECTED).
    path(
        "<int:pk>/status/",
        views.BudgetStatusUpdateView.as_view(),
        name="status_update",
    ),

    # Budget history — listado de presupuestos generados.
    # Solo visible para ADMIN. El operario ASSISTANCE no tiene acceso.
    # Budget history — list of generated budgets. ADMIN only.
    path(
        "history/",
        views.BudgetHistoryView.as_view(),
        name="history",
    ),

    # Budget bulk delete — elimina multiples presupuestos seleccionados. Solo ADMIN.
    # Excluye presupuestos en estado ACCEPTED.
    # Budget bulk delete — deletes multiple selected budgets. ADMIN only.
    # Excludes budgets with ACCEPTED status.
    path(
        "history/bulk-delete/",
        views.BudgetBulkDeleteView.as_view(),
        name="budget_bulk_delete",
    ),

    # Budget detail — desglose completo de un presupuesto. Solo ADMIN.
    # Budget detail — full breakdown of a budget. ADMIN only.
    path(
        "<int:pk>/detail/",
        views.BudgetDetailView.as_view(),
        name="detail",
    ),

    # ---------------------------------------------------------------------------
    # Insurer management routes — ADMIN only
    # Rutas de gestion de aseguradoras — solo ADMIN
    # ---------------------------------------------------------------------------

    # Insurer list — listado con busqueda live HTMX y filtro de estado.
    # Insurer list — list with HTMX live search and status filter.
    path(
        "insurers/",
        views.InsurerListView.as_view(),
        name="insurer_list",
    ),

    # Insurer create — formulario de alta de nueva aseguradora.
    # Insurer create — new insurer creation form.
    path(
        "insurers/new/",
        views.InsurerCreateView.as_view(),
        name="insurer_create",
    ),

    # Insurer detail — vista de solo lectura de tarifa completa. Solo ADMIN.
    # Insurer detail — read-only full tariff view. ADMIN only.
    path(
        "insurers/<int:pk>/detail/",
        views.InsurerDetailView.as_view(),
        name="insurer_detail",
    ),

    # Insurer update — formulario de edicion de aseguradora existente.
    # Insurer update — edit form for an existing insurer.
    path(
        "insurers/<int:pk>/edit/",
        views.InsurerUpdateView.as_view(),
        name="insurer_update",
    ),

    # Insurer toggle — HTMX POST, alterna is_active, devuelve badge.
    # Insurer toggle — HTMX POST, toggles is_active, returns badge fragment.
    path(
        "insurers/<int:pk>/toggle/",
        views.InsurerToggleView.as_view(),
        name="insurer_toggle",
    ),

    # Insurer delete — POST con confirmacion modal, elimina en cascada.
    # Insurer delete — POST with modal confirmation, deletes via CASCADE.
    path(
        "insurers/<int:pk>/delete/",
        views.InsurerDeleteView.as_view(),
        name="insurer_delete",
    ),

    # ---------------------------------------------------------------------------
    # Tariff management routes — ADMIN only
    # Rutas de gestion de tarifas y lineas — solo ADMIN
    # ---------------------------------------------------------------------------

    # Insurer tariff create — crea nueva version de tarifa, cierra la activa.
    # Insurer tariff create — creates new tariff version, closes active one.
    path(
        "insurers/<int:pk>/tariffs/new/",
        views.InsurerTariffCreateView.as_view(),
        name="tariff_create",
    ),

    # Tariff save notes — guarda el campo notes de la tarifa activa.
    # Tariff save notes — saves the notes field of the active tariff.
    path(
        "tariffs/<int:pk>/notes/",
        views.TariffSaveNotesView.as_view(),
        name="tariff_save_notes",
    ),

    # Tariff line add form — HTMX GET, devuelve formulario inline de nueva linea.
    # Tariff line add form — HTMX GET, returns inline add-line form fragment.
    path(
        "tariffs/<int:pk>/lines/add-form/",
        views.TariffLineAddFormView.as_view(),
        name="tariff_line_add_form",
    ),

    # Tariff line add — HTMX POST, crea nueva linea y devuelve fragmento de fila.
    # Tariff line add — HTMX POST, creates new line and returns row fragment.
    path(
        "tariffs/<int:pk>/lines/add/",
        views.TariffLineAddView.as_view(),
        name="tariff_line_add",
    ),

    # Tariff line save — HTMX POST, guarda campo editado y devuelve fila.
    # Tariff line save — HTMX POST, saves edited field and returns row fragment.
    path(
        "lines/<int:pk>/save/",
        views.TariffLineSaveView.as_view(),
        name="tariff_line_save",
    ),

    # Tariff line delete — HTMX POST, elimina linea y devuelve respuesta vacia.
    # Tariff line delete — HTMX POST, deletes line and returns empty response.
    path(
        "lines/<int:pk>/delete/",
        views.TariffLineDeleteView.as_view(),
        name="tariff_line_delete",
    ),

    # ---------------------------------------------------------------------------
    # Base management routes — ADMIN only
    # Rutas de gestion de bases — solo ADMIN
    # ---------------------------------------------------------------------------

    # Base manage — vista dedicada de gestion de bases de una aseguradora.
    # Base manage — dedicated base management view for an insurer.
    path(
        "insurers/<int:pk>/bases/",
        views.BaseManageView.as_view(),
        name="base_manage",
    ),

    # Base create — nueva base para una aseguradora.
    # Base create — new base for an insurer.
    path(
        "insurers/<int:pk>/bases/new/",
        views.BaseCreateView.as_view(),
        name="base_create",
    ),

    # Base update — edicion de base existente (GET form + POST save).
    # Base update — edit existing base (GET form + POST save).
    path(
        "bases/<int:pk>/edit/",
        views.BaseUpdateView.as_view(),
        name="base_update",
    ),

    # Base toggle — HTMX POST, alterna is_active, devuelve fila.
    # Base toggle — HTMX POST, toggles is_active, returns row fragment.
    path(
        "bases/<int:pk>/toggle/",
        views.BaseToggleView.as_view(),
        name="base_toggle",
    ),

    # Base delete — POST con confirmacion modal, elimina si no hay presupuestos.
    # Base delete — POST with modal confirmation, deletes if no linked budgets.
    path(
        "bases/<int:pk>/delete/",
        views.BaseDeleteView.as_view(),
        name="base_delete",
    ),

    # InsurerBase toggle — HTMX POST, alterna InsurerBase.is_active por aseguradora.
    # InsurerBase toggle — HTMX POST, toggles InsurerBase.is_active per insurer.
    path(
        "insurers/<int:insurer_pk>/bases/<int:base_pk>/toggle/",
        views.InsurerBaseToggleView.as_view(),
        name="insurerbase_toggle",
    ),

    # Base global — listado global de bases de la empresa. Solo ADMIN.
    # Base global — global company base list. ADMIN only.
    path(
        "bases/global/",
        views.BaseGlobalView.as_view(),
        name="base_global",
    ),

    # Base sync calendars — HTMX POST, sincroniza calendarios laborales de todas
    # las bases activas de la empresa via calendariosnacionales.com. Solo ADMIN.
    # Base sync calendars — HTMX POST, syncs labour calendars for all active
    # company bases via calendariosnacionales.com. ADMIN only.
    path(
        "bases/sync-calendars/",
        views.BaseSyncCalendarsView.as_view(),
        name="base_sync_calendars",
    ),

    # Base clear coords — HTMX POST, limpia coordenadas de las bases seleccionadas.
    # Recibe lista de PKs via POST. Pone latitude/longitude a null. Solo ADMIN.
    # Base clear coords — HTMX POST, clears coordinates of selected bases.
    # Receives list of PKs via POST. Sets latitude/longitude to null. ADMIN only.
    path(
        "bases/clear-coords/",
        views.BaseClearCoordsView.as_view(),
        name="base_clear_coords",
    ),

    # ---------------------------------------------------------------------------
    # Export routes — Insurer tariff and budget history exports
    # Rutas de exportacion — tarifas de aseguradora e historial de presupuestos
    # ---------------------------------------------------------------------------

    # Insurer tariff exports — CSV, Excel, PDF, Word. ADMIN only.
    path(
        "insurers/<int:pk>/export/tariff/csv/",
        views.InsurerTariffExportCsvView.as_view(),
        name="insurer_tariff_export_csv",
    ),
    path(
        "insurers/<int:pk>/export/tariff/excel/",
        views.InsurerTariffExportExcelView.as_view(),
        name="insurer_tariff_export_excel",
    ),
    path(
        "insurers/<int:pk>/export/tariff/pdf/",
        views.InsurerTariffExportPdfView.as_view(),
        name="insurer_tariff_export_pdf",
    ),
    path(
        "insurers/<int:pk>/export/tariff/word/",
        views.InsurerTariffExportWordView.as_view(),
        name="insurer_tariff_export_word",
    ),

    # Budget history exports — CSV, Excel, PDF, Word. ADMIN only.
    # Respetan los mismos filtros GET que BudgetHistoryView.
    path(
        "history/export/csv/",
        views.BudgetExportCsvView.as_view(),
        name="budget_export_csv",
    ),
    path(
        "history/export/excel/",
        views.BudgetExportExcelView.as_view(),
        name="budget_export_excel",
    ),
    path(
        "history/export/pdf/",
        views.BudgetExportPdfView.as_view(),
        name="budget_export_pdf",
    ),
    path(
        "history/export/word/",
        views.BudgetExportWordView.as_view(),
        name="budget_export_word",
    ),
]
