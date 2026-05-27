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

    # HTMX endpoint — devuelve los tipos de vehiculo para la aseguradora
    # seleccionada en el paso 1. Usado por el formulario secuencial.
    # HTMX endpoint — returns vehicle types for the selected insurer (step 1).
    path(
        "vehicle-types/",
        views.BudgetVehicleTypesView.as_view(),
        name="vehicle_types",
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
]
