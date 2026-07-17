# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/models.py
"""
IngestedFile -- staging de un archivo subido en la ingesta automática
de carpeta (H23/H25, S024) ANTES de saber a qué dominio (MACHINE/
PERSONAL) ni a qué entidad concreta pertenece. La vista de subida crea
una fila por PDF (status=PENDING_ROUTING) y encola
document_ingestion.tasks.route_ingested_files; esa tarea resuelve el
dominio+entidad (entity_matching_service.classify_and_route +
match_machine_asset/match_company_user), crea el
MachineDocument/PersonalDocument correspondiente (asignado o
UNASSIGNED según haya habido coincidencia), y encola el pipeline de
clasificación completo de ese dominio
(machine_documents.tasks.process_machine_document_batch /
personal_documents.tasks.process_personal_document_batch) -- esta fila
de IngestedFile se marca ROUTED y su source_file se copia (no se
comparte) al MachineDocument/PersonalDocument nuevo, así que se puede
borrar sin perder nada una vez enrutada.

Domain-agnostic a propósito -- vive en document_ingestion, no en
machine_documents ni en personal_documents, por el mismo motivo que
entity_matching_service.py (ver ese módulo).
"""
from django.db import models

from ivr_config.models import Company, CompanyUser


class IngestedFile(models.Model):
    """
    Un archivo subido en la ingesta automática de carpeta, todavía sin
    dominio ni entidad resueltos.
    """

    class Status(models.TextChoices):
        PENDING_ROUTING = "PENDING_ROUTING", "Pendiente de enrutar"
        ROUTED = "ROUTED", "Enrutado"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Dominio no identificado -- revisar a mano"
        ERROR = "ERROR", "Error"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="ingested_files",
        verbose_name="Empresa",
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingested_files_uploaded",
        verbose_name="Subido por",
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre de archivo original",
    )
    source_file = models.FileField(
        upload_to="document_ingestion/%Y/%m/",
        blank=True,
        verbose_name="Archivo",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Hash de contenido (SHA-256)",
        help_text="Calculado en la vista de subida (S024) -- se "
                  "propaga al MachineDocument/PersonalDocument "
                  "resultante al enrutar, sin recalcular.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_ROUTING,
        verbose_name="Estado",
    )
    error_message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )
    routed_domain = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Dominio resuelto",
        help_text="MACHINE/PERSONAL/UNKNOWN (ver "
                  "document_ingestion.entity_matching_service) -- "
                  "trazabilidad, no se usa para enrutar de nuevo.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de subida",
    )

    class Meta:
        verbose_name = "Archivo en ingesta (sin enrutar)"
        verbose_name_plural = "Archivos en ingesta (sin enrutar)"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename or '(sin nombre)'} — {self.status}"
