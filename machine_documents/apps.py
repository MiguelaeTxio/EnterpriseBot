# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/apps.py
"""
App configuration for machine_documents (Hito 23).

Dedicated app for cost-center documentation ingestion and
classification, kept separate from `fleet` to avoid bloating an
existing app with a new functional domain — same architectural
directive applied in H22 (see that annex, section 3.1).

---

Configuración de la app machine_documents (Hito 23).

App dedicada para la ingesta y clasificación de documentación de
centros de gasto, mantenida separada de `fleet` para no engordar una
app existente con un dominio funcional nuevo — misma directriz
arquitectónica aplicada en H22 (ver ese anexo, sección 3.1).
"""
from django.apps import AppConfig


class MachineDocumentsConfig(AppConfig):
    """
    AppConfig for the machine_documents application.
    ---
    AppConfig para la aplicación machine_documents.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "machine_documents"
    verbose_name = "Documentación de Centros de Gasto"
