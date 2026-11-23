# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clockin_urls.py
"""
URLs of the clock-in (H24, S129), served under /fichaje/
(enterprise_core/urls.py), outside /panel/ on purpose: a press queued
offline is sent with the trusted-device key, not the panel session.
---
URLs del fichaje (H24, S129), servidas bajo /fichaje/
(enterprise_core/urls.py), fuera de /panel/ a propósito: una pulsación
guardada sin cobertura se envía con la llave del dispositivo de
confianza, no con la sesión del panel.
"""
from django.urls import path

from hr_calendar import clockin

app_name = "clockin"

urlpatterns = [
    path("", clockin.page, name="page"),
    path("sw.js", clockin.service_worker, name="service_worker"),
    path("manifest.json", clockin.manifest, name="manifest"),
    path("enviar/", clockin.receive, name="receive"),
    path("estado/", clockin.status, name="status"),
    # S149: intentos de fichar que el móvil no guardó, y por qué.
    path("intento/", clockin.attempt, name="attempt"),
    # S143: qué avisos recibe el trabajador (casillas).
    path("avisos/", clockin.reminder_choices_view, name="reminders"),
    # S143: horario propio para los avisos (horario abierto).
    path("avisos/horario/", clockin.own_schedule_view, name="own_schedule"),
]
