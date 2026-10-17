# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clockin_test_urls.py
"""
URLs of the offline clock-in test (H24, S129), served under
/fichaje-prueba/ (enterprise_core/urls.py). Removed with the test.
---
URLs de la prueba de fichaje sin cobertura (H24, S129), servidas bajo
/fichaje-prueba/ (enterprise_core/urls.py). Se retiran con la prueba.
"""
from django.urls import path

from hr_calendar import clockin_test

urlpatterns = [
    path("", clockin_test.page, name="clockin_test_page"),
    path("sw.js", clockin_test.service_worker, name="clockin_test_sw"),
    path("manifest.json", clockin_test.manifest,
         name="clockin_test_manifest"),
    path("enviar/", clockin_test.receive, name="clockin_test_receive"),
]
