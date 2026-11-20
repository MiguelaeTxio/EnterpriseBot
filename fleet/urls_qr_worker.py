# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/urls_qr_worker.py
"""
H23 (S154, invasora) -- editor de fichas QR dentro del fichaje
(/fichaje/qr/).
"""
from django.urls import path

from fleet import views_qr_worker as worker

urlpatterns = [
    path("", worker.worker_list, name="fleet_qr_worker_list"),
    path("<int:pk>/", worker.worker_vehicle, name="fleet_qr_worker_vehicle"),
]
