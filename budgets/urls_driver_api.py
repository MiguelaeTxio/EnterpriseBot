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
    path(
        "albaranes/<int:pk>/start/",
        api_driver.DriverAlbaranStartView.as_view(),
        name="albaran_start",
    ),
    path(
        "albaranes/<int:pk>/arrive/",
        api_driver.DriverAlbaranArriveView.as_view(),
        name="albaran_arrive",
    ),
    path(
        "albaranes/<int:pk>/photos/",
        api_driver.DriverAlbaranPhotoView.as_view(),
        name="albaran_photo",
    ),
    path(
        "albaranes/<int:pk>/close-base/",
        api_driver.DriverAlbaranCloseBaseView.as_view(),
        name="albaran_close_base",
    ),
    path(
        "albaranes/<int:pk>/return-estimate/",
        api_driver.DriverAlbaranReturnEstimateView.as_view(),
        name="albaran_return_estimate",
    ),
    path(
        "albaranes/<int:pk>/close-route/",
        api_driver.DriverAlbaranCloseRouteView.as_view(),
        name="albaran_close_route",
    ),
    path(
        "position/",
        api_driver.DriverPositionView.as_view(),
        name="position",
    ),
    path(
        "route-test/",
        api_driver.DriverRouteTestView.as_view(),
        name="route_test",
    ),
]
