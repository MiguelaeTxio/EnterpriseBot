# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/personal_documents/apps.py
"""
App configuration for personal_documents (Hito 25).

Dedicated app for personnel documentation ingestion and
classification, kept separate from `machine_documents` (H23) even
though both share the same design principles -- explicit decision of
Miguel Ángel in S022 ("la modularidad ya es importante porque el
proyecto tiene una dimensión gigantesca"), same architectural
directive already applied between `fleet`/`machine_documents` (H22/H23
precedent).

---

Configuración de la app personal_documents (Hito 25).

App dedicada para la ingesta y clasificación de documentación de
personal, mantenida separada de `machine_documents` (H23) aunque
ambas compartan los mismos principios de diseño -- decisión explícita
de Miguel Ángel en S022 ("la modularidad ya es importante porque el
proyecto tiene una dimensión gigantesca"), misma directriz
arquitectónica ya aplicada entre `fleet`/`machine_documents`
(precedente H22/H23).
"""
from django.apps import AppConfig


class PersonalDocumentsConfig(AppConfig):
    """
    AppConfig for the personal_documents application.
    ---
    AppConfig para la aplicación personal_documents.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "personal_documents"
    verbose_name = "Documentación de Personal"
