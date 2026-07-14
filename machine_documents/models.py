# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/models.py
"""
Data models for the machine_documents app (Hito 23).

MachineDocument stores a pointer to a single official document of a
MachineAsset (technical sheet, ITV card, inspection certificate,
insurance receipt, registry inscription, CE declaration, etc.). The
actual file lives in Google Drive (same pattern as
work_order_processor.TaskPhoto / spare_parts.DeliveryNote); this model
only keeps the Drive reference plus metadata produced by the Gemini
Vision classification service (machine_documents/document_classification_service.py,
to be added in a later step of this milestone).

document_type is intentionally a free CharField, not a closed
`choices` list: per Miguel Ángel's explicit decision (S016 session
that opened this milestone), Gemini may propose new categories on its
own when none of the known ones fit, instead of forcing everything
into a generic "OTRO" bucket.

---

Modelos de datos para la app machine_documents (Hito 23).

MachineDocument almacena un puntero a un único documento oficial de un
MachineAsset (ficha técnica, tarjeta ITV, certificado de inspección,
recibo de seguro, inscripción de registro, declaración CE, etc.). El
archivo real vive en Google Drive (mismo patrón que
work_order_processor.TaskPhoto / spare_parts.DeliveryNote); este
modelo solo guarda la referencia de Drive más los metadatos producidos
por el servicio de clasificación Gemini Vision
(machine_documents/document_classification_service.py, a añadir en un
paso posterior de este hito).

document_type es deliberadamente un CharField libre, no una lista
`choices` cerrada: por decisión explícita de Miguel Ángel (sesión S016
que abrió este hito), Gemini puede proponer categorías nuevas por su
cuenta cuando ninguna de las conocidas encaja, en vez de forzar todo
a un cajón genérico "OTRO".
"""
from django.db import models

from fleet.models import MachineAsset
from ivr_config.models import Company, CompanyUser


class MachineDocument(models.Model):
    """
    A single official document belonging to a MachineAsset (cost
    centre), classified by content via Gemini Vision and persisted in
    Google Drive.
    ---
    Un documento oficial de un MachineAsset (centro de gasto),
    clasificado por contenido vía Gemini Vision y persistido en Google
    Drive.
    """

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    machine_asset = models.ForeignKey(
        MachineAsset,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Máquina / Centro de gasto",
        help_text="Máquina o centro de gasto al que pertenece este "
                  "documento.",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="machine_documents",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este documento, "
                  "denormalizada desde machine_asset.company en el "
                  "momento de creación (mismo patrón que TaskPhoto).",
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machine_documents_uploaded",
        verbose_name="Subido por",
        help_text="Usuario del panel (ADMIN o DOCS_SUPERVISOR) que "
                  "subió este documento.",
    )

    # ------------------------------------------------------------------
    # Classification (Gemini Vision) / Clasificación (Gemini Vision)
    # ------------------------------------------------------------------
    document_type = models.CharField(
        max_length=100,
        verbose_name="Tipo de documento",
        help_text="Categoría propuesta por Gemini a partir del "
                  "contenido del documento (ficha técnica, tarjeta "
                  "ITV, certificado de inspección, recibo de seguro, "
                  "inscripción de registro, declaración CE, u otra "
                  "categoría que Gemini proponga libremente — sin "
                  "lista cerrada).",
    )
    display_name = models.CharField(
        max_length=255,
        verbose_name="Nombre legible",
        help_text="Nombre legible generado a partir del contenido "
                  "(ej. \"Certificado OCA 2025-2026 (vigente)\"), "
                  "usado tanto en BD como en el propio archivo "
                  "persistido en Drive.",
    )
    source_master_hint = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Origen (documento maestro)",
        help_text="Si este documento se extrajo de un PDF maestro en "
                  "vez de subirse ya como archivo individual, nombre "
                  "del archivo maestro de procedencia (trazabilidad). "
                  "Vacío cuando el documento se subió directamente "
                  "como individual.",
    )

    # ------------------------------------------------------------------
    # Cloud persistence — same fields/rationale as
    # work_order_processor.TaskPhoto.drive_file_id / drive_web_link.
    # Persistencia en la nube — mismos campos/razón de ser que
    # work_order_processor.TaskPhoto.drive_file_id / drive_web_link.
    # ------------------------------------------------------------------
    drive_file_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="ID de archivo en Google Drive",
    )
    drive_web_link = models.URLField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Enlace de Google Drive",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Documento de centro de gasto"
        verbose_name_plural = "Documentos de centros de gasto"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.display_name} — {self.machine_asset}"
