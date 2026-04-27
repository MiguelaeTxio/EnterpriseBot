# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/models.py

"""
Models for the work_order_processor application.
Defines three models that form the complete work-order processing pipeline:

  WorkOrder       — PDF upload and its full processing lifecycle.
  WorkOrderEntry  — One record per PDF page (header: date, worker, confidence).
  WorkOrderEntryLine — One record per work block within a page (up to 4 per page).
                       Carries the actual work data: machine, description,
                       repair notes, start/end times and the resolved MachineAsset FK.

---

Modelos de la aplicación work_order_processor.
Define tres modelos que forman el pipeline completo de procesamiento de partes:

  WorkOrder          — Carga del PDF y ciclo de vida completo del procesamiento.
  WorkOrderEntry     — Un registro por página del PDF (cabecera: fecha, operario,
                       confianza).
  WorkOrderEntryLine — Un registro por bloque de trabajo dentro de una página
                       (hasta 4 por página). Contiene los datos reales del trabajo:
                       máquina, descripción, notas de reparación, horas de inicio/fin
                       y el FK resuelto a MachineAsset.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from fleet.models import MachineAsset
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

    @property
    def pdf_display_name(self) -> str:
        """
        Returns the PDF filename with the Django random suffix stripped.
        The suffix pattern is an underscore followed by exactly seven
        alphanumeric characters immediately before the file extension
        (e.g. ``OPERARIO 01-01-25 AL 31-01-25_bVofaFF.pdf`` ->
        ``OPERARIO 01-01-25 AL 31-01-25``).
        Falls back to the raw basename if the field has no value.

        ---

        Devuelve el nombre del fichero PDF sin el sufijo aleatorio de Django.
        El patrón del sufijo es un guión bajo seguido de exactamente siete
        caracteres alfanuméricos inmediatamente antes de la extensión
        (p. ej. ``OPERARIO 01-01-25 AL 31-01-25_bVofaFF.pdf`` ->
        ``OPERARIO 01-01-25 AL 31-01-25``).
        Cae de vuelta al nombre base sin procesar si el campo no tiene valor.
        """
        import re
        if not self.source_pdf:
            return f"Parte #{self.pk}"
        basename = self.source_pdf.name.split("/")[-1]
        # Strip Django random suffix: _XXXXXXX before the extension.
        # Eliminar sufijo aleatorio de Django: _XXXXXXX antes de la extensión.
        return re.sub(r'_[A-Za-z0-9]{7}(\.[^.]+)$', r'', basename)


class WorkOrderEntry(models.Model):
    """
    Represents the header of a single PDF page in a work-order document.
    Stores page-level data: the worker name (derived from the PDF filename,
    not from the handwritten text), the work date, the raw Gemini response
    for the full page, and the overall extraction confidence.

    Individual work blocks within the page (up to 4 per page) are stored
    as WorkOrderEntryLine records linked via FK to this model.

    ---

    Representa la cabecera de una página individual del PDF de partes de trabajo.
    Almacena datos a nivel de página: nombre del operario (derivado del nombre
    del fichero PDF, no del texto manuscrito), fecha del parte, respuesta cruda
    de Gemini para la página completa y confianza global de extracción.

    Los bloques de trabajo individuales dentro de la página (hasta 4 por página)
    se almacenan como registros WorkOrderEntryLine vinculados mediante FK a este
    modelo.
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
        help_text=_("Parte de trabajo al que pertenece esta entrada de página."),
    )

    # ------------------------------------------------------------------
    # Positioning / Posicionamiento
    # ------------------------------------------------------------------
    page_number = models.IntegerField(
        _("Número de Página"),
        help_text=_("Número de página en el PDF original (base 1)."),
    )

    # ------------------------------------------------------------------
    # Page-level extracted fields / Campos extraídos a nivel de página
    # ------------------------------------------------------------------
    worker_name = models.CharField(
        _("Nombre del Operario"),
        max_length=200,
        blank=True,
        help_text=_(
            "Nombre del operario derivado del nombre del fichero PDF fuente. "
            "Formato: NOMBRE APELLIDO1 APELLIDO2 en mayúsculas. "
            "No se extrae del texto manuscrito para evitar variantes ortográficas."
        ),
    )
    work_date = models.DateField(
        _("Fecha del Parte"),
        null=True,
        blank=True,
        help_text=_(
            "Fecha de la jornada registrada en el parte. "
            "Puede ser deducida por contexto calendario (directriz D2)."
        ),
    )
    fecha_incierta = models.BooleanField(
        _("Fecha Incierta"),
        default=False,
        help_text=_(
            "Indica si la fecha de esta página es dudosa y requiere "
            "verificación humana (directriz D1 de la skill partes-trabajo)."
        ),
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


# ---------------------------------------------------------------------------
# WorkOrderEntryLine — one record per work block / un registro por bloque
# ---------------------------------------------------------------------------

class WorkOrderEntryLine(models.Model):
    """
    Represents a single work block within a PDF page (up to 4 per page).
    Each line corresponds to one row of the printed form: a machine reference,
    a fault description, repair notes, start and end times, and an optional
    O.R. reference.

    The machine reference is stored in two forms:
      - maquina_raw:  exactly as extracted by Gemini Vision from the manuscript.
      - maquina_norm: normalised according to D4 rules (uppercase, hyphen,
                      zero-padding) used for catalogue lookup.

    The resolved MachineAsset FK is set during processing if the normalised
    code matches a record in the fleet catalogue. It is left null if no match
    is found (generates an incidence in the Excel manifest).

    delta_horas stores the net hours for this block after applying the lunch
    break deduction rule (13:30–15:00, 90 min) defined in the skill.

    ---

    Representa un bloque de trabajo individual dentro de una página del PDF
    (hasta 4 por página). Cada línea corresponde a una fila del formulario
    impreso: referencia de máquina, descripción de avería, notas de reparación,
    horas de inicio y fin, y una referencia O.R. opcional.

    La referencia de máquina se almacena en dos formas:
      - maquina_raw:  tal como la extrae Gemini Vision del manuscrito.
      - maquina_norm: normalizada según las reglas D4 (mayúsculas, guion,
                      relleno de ceros) usada para la búsqueda en el catálogo.

    El FK resuelto a MachineAsset se establece durante el procesamiento si el
    código normalizado coincide con un registro del catálogo de flota. Se deja
    nulo si no se encuentra coincidencia (genera incidencia en el manifiesto Excel).

    delta_horas almacena las horas netas de este bloque tras aplicar la regla de
    descuento de la pausa de comida (13:30–15:00, 90 min) definida en la skill.
    """

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    entry = models.ForeignKey(
        WorkOrderEntry,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Entrada de Página"),
        help_text=_("Página del parte a la que pertenece este bloque de trabajo."),
    )

    # ------------------------------------------------------------------
    # Block positioning / Posicionamiento del bloque
    # ------------------------------------------------------------------
    line_number = models.IntegerField(
        _("Número de Bloque"),
        help_text=_(
            "Posición del bloque dentro de la página (1–4). "
            "Refleja el orden de aparición en el formulario impreso."
        ),
    )

    # ------------------------------------------------------------------
    # Machine reference / Referencia de máquina
    # ------------------------------------------------------------------
    machine_asset = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_order_lines",
        verbose_name=_("Activo de Flota"),
        help_text=_(
            "Máquina del catálogo de flota resuelta a partir de maquina_norm. "
            "Nulo si el código no se encontró en el catálogo tras aplicar D4."
        ),
    )
    maquina_raw = models.CharField(
        _("Máquina (Raw)"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia de máquina tal como la extrae Gemini Vision del manuscrito. "
            "Se preserva sin modificar para auditoría."
        ),
    )
    maquina_norm = models.CharField(
        _("Máquina (Normalizada)"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia de máquina normalizada según directriz D4: mayúsculas, "
            "guion entre letra y número, relleno de ceros. "
            "Clave usada para la búsqueda en MachineAsset."
        ),
    )

    # ------------------------------------------------------------------
    # Work description / Descripción del trabajo
    # ------------------------------------------------------------------
    descripcion_averia = models.TextField(
        _("Descripción de Avería"),
        blank=True,
        help_text=_(
            "Descripción de la avería o tarea anotada en el parte. "
            "Interpretada en contexto de vehículos pesados industriales (D7)."
        ),
    )
    reparacion = models.TextField(
        _("Reparación"),
        blank=True,
        help_text=_(
            "Descripción de la reparación o intervención realizada, "
            "tal como figura en la columna REPARACION del formulario."
        ),
    )

    # ------------------------------------------------------------------
    # Time fields / Campos horarios
    # ------------------------------------------------------------------
    hc = models.TimeField(
        _("H.C. (Hora de Comienzo)"),
        null=True,
        blank=True,
        help_text=_(
            "Hora de inicio del bloque de trabajo. "
            "Redondeada a fracción de media hora según directriz D3."
        ),
    )
    hf = models.TimeField(
        _("H.F. (Hora de Finalización)"),
        null=True,
        blank=True,
        help_text=_(
            "Hora de fin del bloque de trabajo. "
            "Redondeada a fracción de media hora según directriz D3."
        ),
    )
    or_val = models.CharField(
        _("O.R."),
        max_length=50,
        blank=True,
        help_text=_(
            "Referencia de Orden de Reparación anotada en el parte, si existe."
        ),
    )

    # ------------------------------------------------------------------
    # Computed / Calculado
    # ------------------------------------------------------------------
    delta_horas = models.DecimalField(
        _("Δ Horas (Netas)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Horas netas del bloque tras descontar la pausa de comida "
            "(13:30–15:00, 90 min) si el tramo la cubre. "
            "Calculado automáticamente durante el procesamiento."
        ),
    )

    # ------------------------------------------------------------------
    # Extraction flags / Flags de extracción
    # ------------------------------------------------------------------
    flags = models.JSONField(
        _("Flags de Incidencia"),
        default=list,
        blank=True,
        help_text=_(
            "Lista de campos con lectura incierta en este bloque. "
            "Valores posibles: 'H.C.', 'H.F.', 'DESCRIPCION', 'MAQUINA'. "
            "Se usa para generar el Manifiesto de Incidencias en el Excel."
        ),
    )

    class Meta:
        verbose_name        = _("Línea de Bloque de Trabajo")
        verbose_name_plural = _("Líneas de Bloque de Trabajo")
        ordering            = ["entry", "line_number"]
        unique_together     = [("entry", "line_number")]

    def __str__(self) -> str:
        hc  = self.hc.strftime("%H:%M")  if self.hc else "--:--"
        hf  = self.hf.strftime("%H:%M")  if self.hf else "--:--"
        maq = self.maquina_norm or self.maquina_raw or "Sin máquina"
        return (
            f"Bloque {self.line_number} | {maq} | "
            f"{hc}–{hf}"
            + (f" ({self.delta_horas}h)" if self.delta_horas is not None else "")
        )
