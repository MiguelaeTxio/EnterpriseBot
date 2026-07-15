# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/urls.py
"""
URL configuration for the hr_calendar application.
Served under /panel/vacaciones/ as defined in enterprise_core/urls.py.
---
Configuración de URLs para la aplicación hr_calendar.
Servida bajo /panel/vacaciones/ según enterprise_core/urls.py.
"""
from django.urls import path

from hr_calendar.views import (
    VacationCalendarView,
    VacationPeriodListView,
    VacationPeriodCreateView,
    VacationPeriodUpdateView,
    VacationPeriodDeleteView,
)

app_name = "hr_calendar"

urlpatterns = [
    path(
        "",
        VacationCalendarView.as_view(),
        name="calendar",
    ),
    path(
        "gestion/",
        VacationPeriodListView.as_view(),
        name="vacation_period_list",
    ),
    path(
        "crear/",
        VacationPeriodCreateView.as_view(),
        name="vacation_period_create",
    ),
    path(
        "<int:pk>/editar/",
        VacationPeriodUpdateView.as_view(),
        name="vacation_period_update",
    ),
    path(
        "<int:pk>/eliminar/",
        VacationPeriodDeleteView.as_view(),
        name="vacation_period_delete",
    ),
]
