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
]
