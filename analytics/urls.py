# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/urls.py
"""
URL configuration for the analytics application.
All routes served under /panel/analytics/ via include('analytics.urls').
---
Configuracion de URLs para la aplicacion analytics.
Todas las rutas bajo /panel/analytics/ via include('analytics.urls').
"""
from django.urls import path

from analytics.views import (
    AnalyticsView,
    AnalyticsDataView,
    AnalyticsLabView,
    AnalyticsLabDataView,
    AnalyticsLabExportView,
    AnalyticsProfileListCreateView,
    AnalyticsProfileDeleteView,
    BotManagementView,
)

app_name = "analytics"

urlpatterns = [
    path(
        "",
        AnalyticsView.as_view(),
        name="analytics",
    ),
    path(
        "data/",
        AnalyticsDataView.as_view(),
        name="analytics_data",
    ),
    path(
        "profiles/",
        AnalyticsProfileListCreateView.as_view(),
        name="analytics_profile_list_create",
    ),
    path(
        "profiles/<int:pk>/",
        AnalyticsProfileDeleteView.as_view(),
        name="analytics_profile_delete",
    ),
    path(
        "lab/",
        AnalyticsLabView.as_view(),
        name="analytics_lab",
    ),
    path(
        "lab/data/",
        AnalyticsLabDataView.as_view(),
        name="analytics_lab_data",
    ),
    path(
        "lab/export/",
        AnalyticsLabExportView.as_view(),
        name="analytics_lab_export",
    ),
    path(
        "bot/",
        BotManagementView.as_view(),
        name="bot_management",
    ),
]
