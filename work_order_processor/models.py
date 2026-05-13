# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/models.py

"""
Models for the work_order_processor application.
Defines three models that form the complete work-order processing pipeline:

  WorkOrder       — PDF upload and its full processing lifecycle. Includes
                    review workflow fields (reviewed, reviewed_by, reviewed_at)
                    for the SUPERVISOR role introduced in Hito 8 / Bloque G.
  WorkOrderEntry  — One record per PDF page (header: date, worker, confidence).
  WorkOrderEntryLine — One record per work block within a page (up to 4 per page).
                       Carries the actual work data: machine, description,
                       repair notes, start/end times and the resolved MachineAsset FK.

Two auxiliary TextChoices classes are also defined at module level:

  FaultCategory    — 8 top-level fault groups for automatic classification
                     (Hito 7 / S023).
  FaultSubcategory — ~30 fault subgroups, one subset per FaultCategory
                     (Hito 7 / S023).

---

Modelos de la aplicación work_order_processor.
Define tres modelos que forman el pipeline completo de procesamiento de partes:

  WorkOrder          — Carga del PDF y ciclo de vida completo del procesamiento.
                       Incluye los campos del flujo de revisión (reviewed,
                       reviewed_by, reviewed_at) para el rol SUPERVISOR
                       introducido en el Hito 8 / Bloque G.
  WorkOrderEntry     — Un registro por página del PDF (cabecera: fecha, operario,
                       confianza).
  WorkOrderEntryLine — Un registro por bloque de trabajo dentro de una página
                       (hasta 4 por página). Contiene los datos reales del trabajo:
                       máquina, descripción, notas de reparación, horas de inicio/fin
                       y el FK resuelto a MachineAsset.

También se definen dos clases TextChoices a nivel de módulo:

  FaultCategory    — 8 grupos principales de avería para clasificación automática
                     (Hito 7 / S023).
  FaultSubcategory — ~30 subgrupos de avería, un subconjunto por FaultCategory
                     (Hito 7 / S023).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from fleet.models import MachineAsset
from ivr_config.models import Company, CompanyUser


# ---------------------------------------------------------------------------
# FaultCategory — top-level fault groups for automatic classification
# FaultCategory — grupos principales de avería para clasificación automática
# ---------------------------------------------------------------------------

class FaultCategory(models.TextChoices):
    """
    Top-level fault groups used for automatic classification of work-order
    entry lines via Gemini Flash (classify_fault task). Stored in
    WorkOrderEntryLine.fault_category. Used exclusively for analytics and
    filtering — never shown to the operator in any form or view.

    ---

    Grupos principales de avería para la clasificación automática de líneas
    de parte vía Gemini Flash (tarea classify_fault). Se almacena en
    WorkOrderEntryLine.fault_category. Exclusivamente para analítica y
    filtrado — nunca se muestra al operario en ningún formulario ni vista.
    """

    ENGINE_TRANSMISSION        = "ENGINE_TRANSMISSION",        _("Motor y transmisión")
    HYDRAULIC                  = "HYDRAULIC",                  _("Sistema hidráulico")
    ELECTRICAL_ELECTRONIC      = "ELECTRICAL_ELECTRONIC",      _("Eléctrico y electrónico")
    BRAKES_STEERING_SUSPENSION = "BRAKES_STEERING_SUSPENSION", _("Frenos, dirección y suspensión")
    TYRES_RUNNING_GEAR         = "TYRES_RUNNING_GEAR",         _("Neumáticos y rodadura")
    LIFTING_STRUCTURE          = "LIFTING_STRUCTURE",          _("Estructura y sistemas de elevación")
    BODYWORK_CHASSIS           = "BODYWORK_CHASSIS",           _("Carrocería y chasis")
    OTHER                      = "OTHER",                      _("Otras averías")


# ---------------------------------------------------------------------------
# FaultSubcategory — fault subgroups for fine-grained classification
# FaultSubcategory — subgrupos de avería para clasificación detallada
# ---------------------------------------------------------------------------

class FaultSubcategory(models.TextChoices):
    """
    Fine-grained fault subgroups grouped under FaultCategory. Stored in
    WorkOrderEntryLine.fault_subcategory. Used exclusively for analytics
    and filtering — never shown to the operator in any form or view.

    Subgroup prefixes map to their parent FaultCategory:
      ET_  → ENGINE_TRANSMISSION
      HY_  → HYDRAULIC
      EE_  → ELECTRICAL_ELECTRONIC
      BSS_ → BRAKES_STEERING_SUSPENSION
      TRG_ → TYRES_RUNNING_GEAR
      LS_  → LIFTING_STRUCTURE
      BC_  → BODYWORK_CHASSIS
      OT_  → OTHER

    ---

    Subgrupos detallados de avería agrupados bajo FaultCategory. Se almacena en
    WorkOrderEntryLine.fault_subcategory. Exclusivamente para analítica y
    filtrado — nunca se muestra al operario en ningún formulario ni vista.

    Los prefijos de subgrupo se corresponden con su FaultCategory padre:
      ET_  → ENGINE_TRANSMISSION
      HY_  → HYDRAULIC
      EE_  → ELECTRICAL_ELECTRONIC
      BSS_ → BRAKES_STEERING_SUSPENSION
      TRG_ → TYRES_RUNNING_GEAR
      LS_  → LIFTING_STRUCTURE
      BC_  → BODYWORK_CHASSIS
      OT_  → OTHER
    """

    # ENGINE_TRANSMISSION subgroups / Subgrupos de Motor y transmisión
    ET_ENGINE      = "ET_ENGINE",      _("Motor")
    ET_TRANSMISSION = "ET_TRANSMISSION", _("Transmisión")
    ET_PTO         = "ET_PTO",         _("Toma de fuerza (PTO)")
    ET_COOLING     = "ET_COOLING",     _("Sistema de refrigeración")
    ET_FUEL        = "ET_FUEL",        _("Sistema de combustible")

    # HYDRAULIC subgroups / Subgrupos de Sistema hidráulico
    HY_PUMP        = "HY_PUMP",        _("Bomba hidráulica")
    HY_CYLINDERS   = "HY_CYLINDERS",   _("Cilindros hidráulicos")
    HY_VALVES      = "HY_VALVES",      _("Válvulas hidráulicas")
    HY_OIL         = "HY_OIL",        _("Aceite y circuito hidráulico")
    HY_CENTRAL     = "HY_CENTRAL",     _("Central hidráulica")

    # ELECTRICAL_ELECTRONIC subgroups / Subgrupos de Eléctrico y electrónico
    EE_WIRING      = "EE_WIRING",      _("Cableado y conectores")
    EE_SENSORS     = "EE_SENSORS",     _("Sensores y sondas")
    EE_CONTROLS    = "EE_CONTROLS",    _("Mandos y controles")
    EE_LIGHTS      = "EE_LIGHTS",      _("Iluminación")
    EE_BATTERY     = "EE_BATTERY",     _("Batería y sistema de carga")

    # BRAKES_STEERING_SUSPENSION subgroups / Subgrupos de Frenos, dirección y suspensión
    BSS_BRAKES     = "BSS_BRAKES",     _("Frenos")
    BSS_STEERING   = "BSS_STEERING",   _("Dirección")
    BSS_SUSPENSION = "BSS_SUSPENSION", _("Suspensión")

    # TYRES_RUNNING_GEAR subgroups / Subgrupos de Neumáticos y rodadura
    TRG_TYRES      = "TRG_TYRES",      _("Neumáticos")
    TRG_AXLES      = "TRG_AXLES",      _("Ejes y transmisión de rueda")
    TRG_TRACKS     = "TRG_TRACKS",     _("Cadenas y rodadura oruga")

    # LIFTING_STRUCTURE subgroups / Subgrupos de Estructura y sistemas de elevación
    LS_BOOM        = "LS_BOOM",        _("Pluma y brazo")
    LS_HOOK_PULLEYS = "LS_HOOK_PULLEYS", _("Gancho y poleas")
    LS_CABLE       = "LS_CABLE",       _("Cable de elevación")
    LS_ROTATION    = "LS_ROTATION",    _("Sistema de rotación")
    LS_STABILIZERS = "LS_STABILIZERS", _("Estabilizadores y apoyos")
    LS_MAST        = "LS_MAST",        _("Mástil y horquillas")
    LS_PLATFORM    = "LS_PLATFORM",    _("Plataforma elevadora")
    LS_FIFTH_WHEEL = "LS_FIFTH_WHEEL", _("Quinta rueda")
    LS_CHASSIS_TRAILER = "LS_CHASSIS_TRAILER", _("Chasis de semirremolque")

    # BODYWORK_CHASSIS subgroups / Subgrupos de Carrocería y chasis
    BC_BODYWORK    = "BC_BODYWORK",    _("Carrocería")
    BC_CHASSIS     = "BC_CHASSIS",     _("Chasis estructural")

    # OTHER subgroups / Subgrupos de Otras averías
    OT_OTHER       = "OT_OTHER",       _("Otra avería no clasificada")


class WorkOrder(models.Model):
    """
    Represents a work-order record in the platform. Tracks the full lifecycle:
    pending → processing → done / error. Stores the original PDF (if any) and,
    once processing is complete, the generated Excel report.

    Origin classification (Hito 7 / S016):
      source = PDF_UPLOAD — created via the classic PDF upload pipeline.
      source = DIGITAL    — created directly by a WORKSHOP operator via
                            Form (Via A), STT (Via B) or Upload (Via C).
      source = GENERATED  — created automatically from a WorkerAbsence range.

    Review workflow (Hito 8 / Bloque G):
      reviewed    — boolean flag set by a SUPERVISOR after inspecting the part.
      reviewed_by — FK to the CompanyUser who performed the review.
      reviewed_at — UTC timestamp of the review action.

    ---

    Representa un registro de parte de trabajo en la plataforma. Registra el
    ciclo de vida completo: pendiente → procesando → hecho / error. Almacena
    el PDF original (si lo hay) y, una vez completado, el informe Excel generado.

    Clasificación de origen (Hito 7 / S016):
      source = PDF_UPLOAD — creado via el pipeline clásico de carga de PDF.
      source = DIGITAL    — creado directamente por un operario WORKSHOP via
                            Form (Via A), STT (Via B) o Upload (Via C).
      source = GENERATED  — creado automáticamente desde un rango WorkerAbsence.

    Flujo de revisión (Hito 8 / Bloque G):
      reviewed    — flag booleano establecido por un SUPERVISOR tras inspeccionar
                    el parte.
      reviewed_by — FK al CompanyUser que realizó la revisión.
      reviewed_at — timestamp UTC del momento de la revisión.
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
    # Source choices — origin classification (Hito 7 / S016)
    # Opciones de origen — clasificación del parte (Hito 7 / S016)
    # ------------------------------------------------------------------
    class Source(models.TextChoices):
        PDF_UPLOAD = "PDF_UPLOAD", _("Subida PDF (pipeline clásico)")
        DIGITAL    = "DIGITAL",    _("Digital (operario — Form / STT / Upload)")
        GENERATED  = "GENERATED",  _("Generado automáticamente (ausencia)")

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
    # Origin source field — Hito 7 / S016
    # Campo de origen del parte — Hito 7 / S016
    # ------------------------------------------------------------------
    source = models.CharField(
        _("Origen"),
        max_length=20,
        choices=Source.choices,
        default=Source.PDF_UPLOAD,
        db_index=True,
        help_text=_(
            "Clasificación del origen del parte: PDF_UPLOAD (pipeline clásico de "
            "subida de PDF), DIGITAL (entrada directa del operario via Form/STT/Upload) "
            "o GENERATED (generado automáticamente desde un registro de ausencia)."
        ),
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

    # ------------------------------------------------------------------
    # Review workflow — Hito 8 / Bloque G
    # Flujo de revisión — Hito 8 / Bloque G
    # ------------------------------------------------------------------
    reviewed = models.BooleanField(
        _("Revisado"),
        default=False,
        db_index=True,
        help_text=_(
            "Indica si un Supervisor ha revisado y validado este parte de trabajo. "
            "Se activa mediante WorkOrderMarkReviewedView."
        ),
    )
    reviewed_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_work_orders",
        verbose_name=_("Revisado por"),
        help_text=_(
            "Usuario de empresa (rol SUPERVISOR o ADMIN) que marcó el parte "
            "como revisado. Se limpia automáticamente al desmarcar la revisión."
        ),
    )
    reviewed_at = models.DateTimeField(
        _("Fecha de revisión"),
        null=True,
        blank=True,
        help_text=_(
            "Timestamp UTC en que el Supervisor marcó el parte como revisado. "
            "Se limpia automáticamente al desmarcar la revisión."
        ),
    )

    # ------------------------------------------------------------------
    # Overlap incident flag — Hito 7 / Validaciones
    # Flag de incidencia por solapamiento — Hito 7 / Validaciones
    # ------------------------------------------------------------------
    has_overlap_incident = models.BooleanField(
        _("Incidencia de solapamiento"),
        default=False,
        db_index=True,
        help_text=_(
            "Indica que este parte presenta solapamiento de franjas horarias "
            "con otro parte del mismo operario y misma fecha. Se activa "
            "automáticamente al guardar y debe resolverse editando los "
            "partes en conflicto hasta eliminar el solapamiento."
        ),
    )

    # ------------------------------------------------------------------
    # Cost-centre incident flag — Hito 7 / PRIMERA ACCIÓN (sesión 010)
    # Flag de incidencia de centro de gasto — Hito 7 / PRIMERA ACCIÓN (sesión 010)
    # ------------------------------------------------------------------
    has_cg_incident = models.BooleanField(
        _("Incidencia de CdG"),
        default=False,
        db_index=True,
        help_text=_(
            "El operario ha asignado un repuesto a un centro de gasto que no "
            "existe en el catálogo de MachineAsset mediante la opción 'Otro'. "
            "Requiere revisión por parte de un SUPERVISOR o ADMIN para crear "
            "el centro de gasto correspondiente en la base de datos."
        ),
    )

    # ------------------------------------------------------------------
    # Generated-by field — Hito 7 / TERCERA ACCIÓN (sesión 016)
    # Campo generado-por — Hito 7 / TERCERA ACCIÓN (sesión 016)
    #
    # Tracks which SUPERVISOR or ADMIN triggered the automatic generation
    # of synthetic WorkOrder records from a WorkerAbsence period range.
    # Null for all manually uploaded or operator-submitted work orders.
    #
    # Registra qué SUPERVISOR o ADMIN disparó la generación automática de
    # registros WorkOrder sintéticos a partir de un rango de WorkerAbsence.
    # Nulo para todos los partes subidos manualmente o enviados por operarios.
    # ------------------------------------------------------------------
    generated_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_work_orders",
        verbose_name=_("Generado por"),
        help_text=_(
            "Supervisor o ADMIN que generó este parte sintético desde un registro "
            "de ausencia (WorkerAbsence). Nulo en partes subidos manualmente "
            "o enviados por el propio operario desde el panel."
        ),
    )

    # ------------------------------------------------------------------
    # Duplicate detection — Hito 8 / Bloque I
    # Detección de duplicados — Hito 8 / Bloque I
    # ------------------------------------------------------------------
    source_pdf_hash = models.CharField(
        _("Hash SHA-256 del PDF"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_(
            "Hash SHA-256 del fichero PDF original calculado en el momento "
            "de la carga. Permite detectar duplicados exactos con independencia "
            "del nombre del fichero. Vacío en registros anteriores a la "
            "implantación del Bloque I — rellenable mediante el comando de "
            "gestión backfill_pdf_hashes."
        ),
    )

    class Meta:
        verbose_name        = _("Parte de Trabajo")
        verbose_name_plural = _("Partes de Trabajo")
        ordering            = ["-upload_date"]
        constraints         = [
            # Prevents duplicate uploads of the exact same PDF file per company.
            # A partial index is used to exclude synthetic work orders created
            # via the operator Upload view (Via C), which have an empty hash.
            #
            # Impide cargas duplicadas del mismo fichero PDF exacto por empresa.
            # Se usa un índice parcial para excluir los partes sintéticos creados
            # desde la vista Upload del operario (Vía C), que tienen hash vacío.
            models.UniqueConstraint(
                fields     = ["company", "source_pdf_hash"],
                condition  = ~models.Q(source_pdf_hash=""),
                name       = "unique_pdf_hash_per_company",
            ),
        ]

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
    uncertain_date = models.BooleanField(
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
      - machine_raw:  exactly as extracted by Gemini Vision from the manuscript.
      - machine_norm: normalised according to D4 rules (uppercase, hyphen,
                      zero-padding) used for catalogue lookup.

    The resolved MachineAsset FK is set during processing if the normalised
    code matches a record in the fleet catalogue. It is left null if no match
    is found (generates an incidence in the Excel manifest).

    delta_hours stores the net hours for this block after applying the lunch
    break deduction rule (13:30–15:00, 90 min) defined in the skill.

    ---

    Representa un bloque de trabajo individual dentro de una página del PDF
    (hasta 4 por página). Cada línea corresponde a una fila del formulario
    impreso: referencia de máquina, descripción de avería, notas de reparación,
    horas de inicio y fin, y una referencia O.R. opcional.

    La referencia de máquina se almacena en dos formas:
      - machine_raw:  tal como la extrae Gemini Vision del manuscrito.
      - machine_norm: normalizada según las reglas D4 (mayúsculas, guion,
                      relleno de ceros) usada para la búsqueda en el catálogo.

    El FK resuelto a MachineAsset se establece durante el procesamiento si el
    código normalizado coincide con un registro del catálogo de flota. Se deja
    nulo si no se encuentra coincidencia (genera incidencia en el manifiesto Excel).

    delta_hours almacena las horas netas de este bloque tras aplicar la regla de
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
            "Máquina del catálogo de flota resuelta a partir de machine_norm. "
            "Nulo si el código no se encontró en el catálogo tras aplicar D4."
        ),
    )
    machine_raw = models.CharField(
        _("Máquina (Raw)"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia de máquina tal como la extrae Gemini Vision del manuscrito. "
            "Se preserva sin modificar para auditoría."
        ),
    )
    machine_norm = models.CharField(
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
    fault_description = models.TextField(
        _("Descripción de Avería"),
        blank=True,
        help_text=_(
            "Descripción de la avería o tarea anotada en el parte. "
            "Interpretada en contexto de vehículos pesados industriales (D7)."
        ),
    )
    repair_notes = models.TextField(
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
    delta_hours = models.DecimalField(
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
    # Instrumentation readings — Hito 7 / SEGUNDA ACCIÓN (sesión 010)
    # Lecturas de instrumentación — Hito 7 / SEGUNDA ACCIÓN (sesión 010)
    #
    # Optional readings supplied by the operator at the time of the work
    # block. Only required when the associated MachineAsset has the
    # corresponding flag set (has_odometer / has_engine_hours /
    # has_crane_hours). Validated by rules R6/R7/R8 in validators.py.
    #
    # Lecturas opcionales aportadas por el operario en el momento del
    # bloque de trabajo. Solo obligatorias cuando el MachineAsset asociado
    # tiene el flag correspondiente activo (has_odometer / has_engine_hours
    # / has_crane_hours). Validadas por las reglas R6/R7/R8 en validators.py.
    # ------------------------------------------------------------------
    odometer_reading = models.DecimalField(
        _("Lectura km"),
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text=_(
            "Lectura del odómetro (kilómetros) en el momento del bloque "
            "de trabajo. Obligatoria si MachineAsset.has_odometer=True."
        ),
    )
    engine_hours_reading = models.DecimalField(
        _("Lectura horómetro motor"),
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text=_(
            "Lectura del horómetro de motor (horas) en el momento del "
            "bloque de trabajo. Obligatoria si MachineAsset.has_engine_hours=True."
        ),
    )
    crane_hours_reading = models.DecimalField(
        _("Lectura horómetro grúa"),
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text=_(
            "Lectura del horómetro de grúa (horas) en el momento del "
            "bloque de trabajo. Obligatoria si MachineAsset.has_crane_hours=True."
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

    # ------------------------------------------------------------------
    # Fault classification — Hito 7 / S023
    # Clasificación de avería — Hito 7 / S023
    #
    # Populated automatically after INSERT by the Celery task
    # classify_fault_line (high_priority queue). Never filled by the
    # operator. Used exclusively for analytics and filtering.
    #
    # Poblados automáticamente tras el INSERT por la tarea Celery
    # classify_fault_line (cola high_priority). Nunca los rellena el
    # operario. Exclusivamente para analítica y filtrado.
    # ------------------------------------------------------------------
    fault_category = models.CharField(
        _("Categoría de avería"),
        max_length=40,
        choices=FaultCategory.choices,
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "Grupo principal de avería asignado automáticamente por Gemini Flash "
            "tras el guardado del bloque. No lo rellena el operario. "
            "Vacío hasta que la tarea Celery classify_fault_line lo procese."
        ),
    )
    fault_subcategory = models.CharField(
        _("Subcategoría de avería"),
        max_length=60,
        choices=FaultSubcategory.choices,
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "Subgrupo detallado de avería asignado automáticamente por Gemini Flash "
            "tras el guardado del bloque. No lo rellena el operario. "
            "Vacío hasta que la tarea Celery classify_fault_line lo procese."
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
        maq = self.machine_norm or self.machine_raw or "Sin máquina"
        return (
            f"Bloque {self.line_number} | {maq} | "
            f"{hc}–{hf}"
            + (f" ({self.delta_hours}h)" if self.delta_hours is not None else "")
        )


# ---------------------------------------------------------------------------
# SparePartLine — spare parts / materials used in a work block
# SparePartLine — repuestos / materiales usados en un bloque de trabajo
# ---------------------------------------------------------------------------

class SparePartLine(models.Model):
    """
    Represents a single spare part or material consumed during a work block
    (WorkOrderEntryLine). Each work block may have zero or more associated
    spare part lines, forming the reverse side of the physical repair form.

    The source field indicates whether the material was sourced from an
    external supplier (SUPPLIER) or drawn from internal warehouse stock
    (WAREHOUSE).

    ---

    Representa un repuesto o material individual consumido durante un bloque
    de trabajo (WorkOrderEntryLine). Cada bloque puede tener cero o más líneas
    de repuesto asociadas, formando la cara trasera del formulario físico de
    reparación.

    El campo source indica si el material provino de un proveedor externo
    (SUPPLIER) o se extrajo del stock del almacén interno (WAREHOUSE).
    """

    # ------------------------------------------------------------------
    # Source choices / Opciones de procedencia
    # ------------------------------------------------------------------
    class Source(models.TextChoices):
        SUPPLIER  = "SUPPLIER",  _("Proveedor")
        WAREHOUSE = "WAREHOUSE", _("Almacén")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    entry_line = models.ForeignKey(
        WorkOrderEntryLine,
        on_delete=models.CASCADE,
        related_name="spare_parts",
        verbose_name=_("Línea de Bloque de Trabajo"),
        help_text=_(
            "Bloque de trabajo al que pertenece este repuesto. "
            "Un bloque puede tener varios repuestos asociados."
        ),
    )

    # ------------------------------------------------------------------
    # Ordering / Ordenación
    # ------------------------------------------------------------------
    line_number = models.PositiveSmallIntegerField(
        _("Número de Línea"),
        help_text=_(
            "Posición de esta línea de repuesto dentro del bloque "
            "de trabajo (base 1)."
        ),
    )

    # ------------------------------------------------------------------
    # Part identification / Identificación del repuesto
    # ------------------------------------------------------------------
    reference = models.CharField(
        _("Referencia"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia del repuesto tal como aparece en el albarán del "
            "proveedor. Se usa como clave de identificación y puede usarse "
            "para inferir la descripción del material."
        ),
    )
    material = models.CharField(
        _("Material"),
        max_length=200,
        blank=True,
        help_text=_(
            "Descripción del material o repuesto. Puede inferirse de la "
            "referencia del albarán cuando el operario no la especifica "
            "explícitamente."
        ),
    )

    # ------------------------------------------------------------------
    # Vehicle / Centro de gasto
    # ------------------------------------------------------------------
    vehicle = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spare_part_lines",
        verbose_name=_("Vehículo / Centro de Gasto"),
        help_text=_(
            "Vehículo o máquina al que se imputa este repuesto. "
            "Suele coincidir con la máquina del bloque de trabajo, "
            "pero puede diferir si el repuesto se aplica a otra unidad."
        ),
    )

    # ------------------------------------------------------------------
    # Quantity / Cantidad
    # ------------------------------------------------------------------
    quantity = models.DecimalField(
        _("Unidades"),
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Número de unidades consumidas del repuesto. "
            "Admite decimales para materiales vendidos por peso o longitud."
        ),
    )

    # ------------------------------------------------------------------
    # Unit price — Hito 7 / sesión 012
    # Precio unitario — Hito 7 / sesión 012
    #
    # Optional field intentionally left blank by the operator. Populated
    # later by a SUPERVISOR or during the supplier delivery note processing
    # pipeline (Hito 10). Stored here to avoid a schema migration once data
    # is already in production.
    #
    # Campo opcional que el operario no rellena. Lo cumplimenta posteriormente
    # un SUPERVISOR o el pipeline de albaranes de proveedor (Hito 10).
    # Se añade ahora para evitar una migración de esquema con datos en producción.
    # ------------------------------------------------------------------
    unit_price = models.DecimalField(
        _("Precio unitario"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Precio unitario del repuesto en el momento de la imputación. "
            "No lo rellena el operario — lo cumplimenta un SUPERVISOR o el "
            "pipeline de albaranes de proveedor (Hito 10). "
            "Permite calcular el coste de materiales por máquina en los "
            "informes de analítica cruzada (Hito 9)."
        ),
    )

    # ------------------------------------------------------------------
    # Source / Procedencia
    # ------------------------------------------------------------------
    source = models.CharField(
        _("Procedencia"),
        max_length=10,
        choices=Source.choices,
        default=Source.WAREHOUSE,
        help_text=_(
            "Indica si el material llegó directamente de un proveedor externo "
            "(Proveedor) o se extrajo del stock del almacén interno (Almacén)."
        ),
    )
    supplier = models.CharField(
        _("Proveedor"),
        max_length=200,
        blank=True,
        help_text=_(
            "Nombre del proveedor externo. Se cumplimenta únicamente cuando "
            "source = SUPPLIER. Se deja vacío si el material es de almacén."
        ),
    )

    # ------------------------------------------------------------------
    # Extraction flags / Flags de extracción Gemini
    # ------------------------------------------------------------------
    flags = models.JSONField(
        _("Flags de Incidencia"),
        default=list,
        blank=True,
        help_text=_(
            "Lista de campos con lectura incierta extraídos por Gemini Vision "
            "de la parte trasera del formulario. Valores posibles: "
            "'REFERENCIA', 'MATERIAL', 'UNIDADES', 'VEHICULO', 'PROCEDENCIA'. "
            "Vacío para líneas introducidas manualmente (Form / STT)."
        ),
    )

    class Meta:
        verbose_name        = _("Línea de Repuesto")
        verbose_name_plural = _("Líneas de Repuesto")
        ordering            = ["entry_line", "line_number"]
        unique_together     = [("entry_line", "line_number")]

    def __str__(self) -> str:
        ref = self.reference or "Sin ref."
        mat = self.material  or "Sin descripción"
        qty = f"{self.quantity}" if self.quantity is not None else "?"
        return (
            f"Repuesto {self.line_number} | {ref} — {mat} "
            f"× {qty} | {self.get_source_display()}"
        )

