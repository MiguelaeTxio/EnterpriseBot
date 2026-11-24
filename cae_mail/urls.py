# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/urls.py
"""
URLs of the "Correos CAE" tab (S156), under /panel/cae/.
---
URLs de la pestaña «Correos CAE» (S156), bajo /panel/cae/.
"""
from django.urls import path

from . import views

app_name = "cae_mail"

urlpatterns = [
    path("", views.CaeTabView.as_view(), name="tab"),
    path("avisos/", views.CaeResultsView.as_view(), name="results"),
    path("avisos/<int:pk>/", views.CaeDetailView.as_view(), name="detail"),
    path(
        "avisos/<int:pk>/atendido/",
        views.CaeAttendView.as_view(),
        name="attend",
    ),
    path(
        "avisos/<int:pk>/releer/",
        views.CaeRereadView.as_view(),
        name="reread",
    ),
    path(
        "avisos/<int:pk>/descargar/",
        views.CaeDownloadView.as_view(),
        name="download",
    ),
]
