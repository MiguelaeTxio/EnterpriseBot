# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/urls_driver_api.py
"""
H37 (S133). URLs of the driver app API, under /api/driver/.

---

H37 (S133). URLs de la API de la app del conductor, bajo /api/driver/.
"""
from django.urls import path

from budgets import api_driver

app_name = "driver_api"

urlpatterns = [
    path("login/", api_driver.DriverLoginView.as_view(), name="login"),
    path("logout/", api_driver.DriverLogoutView.as_view(), name="logout"),
    path(
        "albaranes/",
        api_driver.DriverAlbaranesView.as_view(),
        name="albaranes",
    ),
    path(
        "albaranes/<int:pk>/",
        api_driver.DriverAlbaranDetailView.as_view(),
        name="albaran_detail",
    ),
    path(
        "albaranes/<int:pk>/submit/",
        api_driver.DriverAlbaranSubmitView.as_view(),
        name="albaran_submit",
    ),
]
