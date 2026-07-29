# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/apps.py
"""
App configuration for document_explorer (H29 -- S037).

Database-backed index over every Google Cloud Storage bucket the
platform owns or governs, plus the folder-level permission model and
the two-tier deletion (per-user trash + administrator purge) that the
panel explorer is built on. Kept separate from document_management
(H26: expiry alerts, PDF merging, email templates) because the
responsibilities do not overlap: that app is about what a document
means to the business, this one is about where the object lives and
who may see or remove it.

---

Configuración de la app document_explorer (H29 -- S037).

Índice en base de datos de todos los cubos de Google Cloud Storage que
la plataforma posee o gobierna, junto con el modelo de permisos por
carpeta y el borrado en dos niveles (papelera por usuario + vaciado
del administrador) sobre los que se construye el explorador del panel.
Separada de document_management (H26: alertas de vencimiento, fusión
de PDF, plantillas de correo) porque las responsabilidades no se
solapan: aquella app trata de qué significa un documento para el
negocio, esta de dónde vive el objeto y quién puede verlo o retirarlo.
"""
from django.apps import AppConfig


class DocumentExplorerConfig(AppConfig):
    """
    AppConfig for the document_explorer application.

    ---

    AppConfig de la aplicación document_explorer.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "document_explorer"
    verbose_name = "Explorador de Archivos y Gobierno Documental"
