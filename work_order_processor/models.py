# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/models.py

"""
Models for the work_order_processor application.
Defines WorkOrder (PDF upload and processing lifecycle) and WorkOrderEntry
(one record per extracted page/work-order slip).

---

Modelos de la aplicación work_order_processor.
Define WorkOrder (ciclo de vida de la carga y procesamiento del PDF) y
WorkOrderEntry (un registro por página/parte extraído del PDF).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from ivr_config.models import Company, CompanyUser


class WorkOrder(models.Model):
    """
    Represents a PDF upload submitted by a company user for processing.
    Tracks the full lifecycle: pending → processing → done / error.
    Stores the original PDF and, once processing is complete, the generated
    Excel report.

    ---

    Representa una carga de PDF enviada por un usuario de empresa para su
    procesamiento. Registra el ciclo de vida completo: pendiente → procesando
    → hecho / error. Almacena el PDF original y, una vez completado el
    procesamiento, el informe Excel generado.
    """

    # ------------------------------------------------------------------
    # Status choices / Opciones de estado
    # ------------------------------------------------------------------
    class Status(models.TextChoices):
        PENDING    = "PENDING",    _("Pendiente")
        PROCESSING = "PROCESSING", _("Procesando")
        DONE       = "DONE",       _("Completado")
        ERROR      = "ERROR",      _("Error")

    # ------------------------------------------------------------------
    # Relations / Relaciones
    # ------------------------------------------------------------------
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="work_orders",
        verbose_name=_("Empresa"),
        help_text=_("Empresa propietaria de este parte de trabajo."),
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="work_orders",
        verbose_name=_("Subido por"),
        help_text=_("Usuario de empresa que realizó la carga del PDF."),
    )

    # ------------------------------------------------------------------
    # File fields / Campos de archivo
    # ------------------------------------------------------------------
    source_pdf = models.FileField(
        _("PDF Original"),
        upload_to="work_orders/pdf/%Y/%m/",
        help_text=_("Archivo PDF con las fotografías de los partes de trabajo."),
    )
    excel_file = models.FileField(
        _("Informe Excel"),
        upload_to="work_orders/excel/%Y/%m/",
        null=True,
        blank=True,
        help_text=_(
            "Informe Excel generado automáticamente. "
            "Disponible únicamente cuando el estado es DONE."
        ),
    )

    # ------------------------------------------------------------------
    # Lifecycle fields / Campos de ciclo de vida
    # ------------------------------------------------------------------
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text=_("Estado actual del procesamiento del PDF."),
    )
    upload_date = models.DateTimeField(
        _("Fecha de Carga"),
        auto_now_add=True,
        help_text=_("Fecha y hora en que se subió el PDF al sistema."),
    )

    # ------------------------------------------------------------------
    # Progress counters / Contadores de progreso
    # ------------------------------------------------------------------
    total_pages = models.IntegerField(
        _("Total de Páginas"),
        default=0,
        help_text=_("Número total de páginas detectadas en el PDF original."),
    )
    processed_pages = models.IntegerField(
        _("Páginas Procesadas"),
        default=0,
        help_text=_("Número de páginas procesadas correctamente por Gemini Vision."),
    )

    # ------------------------------------------------------------------
    # Error tracking / Registro de errores
    # ------------------------------------------------------------------
    error_log = models.TextField(
        _("Registro de Errores"),
        blank=True,
        help_text=_(
            "Detalle de errores producidos durante el procesamiento. "
            "Se cumplimenta únicamente cuando el estado es ERROR."
        ),
    )

    class Meta:
        verbose_name        = _("Parte de Trabajo")
        verbose_name_plural = _("Partes de Trabajo")
        ordering            = ["-upload_date"]

    def __str__(self):
        return (
            f"Parte #{self.pk} — {self.company} "
            f"[{self.get_status_display()}] "
            f"({self.processed_pages}/{self.total_pages} págs.)"
        )


class WorkOrderEntry(models.Model):
    """
    Represents a single extracted work-order slip (one PDF page).
    Each field maps directly to the structured data extracted by Gemini Vision
    from the scanned photograph of a handwritten work-order form.
    The raw Gemini response is preserved for auditing purposes.

    ---

    Representa un parte de trabajo individual extraído (una página del PDF).
    Cada campo corresponde directamente a los datos estructurados extraídos por
    Gemini Vision de la fotografía escaneada del parte manuscrito.
    La respuesta cruda de Gemini se conserva para auditoría.
    """

    # ------------------------------------------------------------------
    # Extraction confidence / Confianza de extracción
    # ------------------------------------------------------------------
    class Confidence(models.TextChoices):
        HIGH   = "HIGH",   _("Alta")
        MEDIUM = "MEDIUM", _("Media")
        LOW    = "LOW",    _("Baja")
        FAILED = "FAILED", _("Fallida")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Parte de Trabajo"),
        help_text=_("Parte de trabajo al que pertenece esta entrada."),
    )

    # ------------------------------------------------------------------
    # Positioning / Posicionamiento
    # ------------------------------------------------------------------
    page_number = models.IntegerField(
        _("Número de Página"),
        help_text=_("Número de página en el PDF original (base 1)."),
    )

    # ------------------------------------------------------------------
    # Extracted fields — section 2.3 of annex V06
    # Campos extraídos — sección 2.3 del anexo V06
    # ------------------------------------------------------------------
    worker_name = models.CharField(
        _("Nombre del Operario"),
        max_length=200,
        blank=True,
        help_text=_("Nombre completo del operario tal como aparece en el parte."),
    )
    work_date = models.DateField(
        _("Fecha del Parte"),
        null=True,
        blank=True,
        help_text=_("Fecha de la jornada registrada en el parte."),
    )
    start_time = models.TimeField(
        _("Hora de Inicio"),
        null=True,
        blank=True,
        help_text=_("Hora de inicio de la jornada (H.C.)."),
    )
    end_time = models.TimeField(
        _("Hora de Fin"),
        null=True,
        blank=True,
        help_text=_("Hora de fin de la jornada (H.F.)."),
    )
    vehicle_ref = models.CharField(
        _("Referencia de Vehículo"),
        max_length=100,
        blank=True,
        help_text=_(
            "Código o matrícula del vehículo tal como aparece en el parte. "
            "Se normaliza según directriz D4 antes de cruzar con el catálogo."
        ),
    )
    work_description = models.TextField(
        _("Descripción de los Trabajos"),
        blank=True,
        help_text=_(
            "Descripción de las tareas realizadas durante la jornada. "
            "Interpretada en contexto de vehículos pesados industriales (D7)."
        ),
    )
    location = models.CharField(
        _("Lugar de Intervención"),
        max_length=300,
        blank=True,
        help_text=_("Lugar o dirección donde se realizaron los trabajos."),
    )
    observations = models.TextField(
        _("Observaciones"),
        blank=True,
        help_text=_("Observaciones adicionales anotadas por el operario."),
    )

    # ------------------------------------------------------------------
    # Gemini audit fields / Campos de auditoría Gemini
    # ------------------------------------------------------------------
    raw_gemini_response = models.JSONField(
        _("Respuesta Cruda de Gemini"),
        null=True,
        blank=True,
        help_text=_(
            "Respuesta JSON completa devuelta por Gemini Vision para esta página. "
            "Se conserva íntegra para auditoría y trazabilidad de la extracción."
        ),
    )
    extraction_confidence = models.CharField(
        _("Confianza de Extracción"),
        max_length=10,
        choices=Confidence.choices,
        default=Confidence.MEDIUM,
        help_text=_(
            "Nivel de confianza global de la extracción para esta página, "
            "evaluado por Gemini Vision."
        ),
    )

    class Meta:
        verbose_name        = _("Entrada de Parte")
        verbose_name_plural = _("Entradas de Parte")
        ordering            = ["work_order", "page_number"]
        unique_together     = [("work_order", "page_number")]

    def __str__(self):
        fecha = self.work_date.strftime("%d/%m/%Y") if self.work_date else "sin fecha"
        return (
            f"Entrada pág. {self.page_number} — "
            f"{self.worker_name or 'Operario desconocido'} — "
            f"{fecha}"
        )
