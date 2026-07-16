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
from ivr_config.models import Company, CompanyUser, WorkPeriod


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


# ---------------------------------------------------------------------------
# TipoTarea — mirrors chat.models.BreakdownTicket.TIPO_TAREA_CHOICES exactly.
# Hardcoded here (not imported) for the same reason documented in
# work_order_processor/services.py::_VALID_TIPO_TAREA: chat.models has no
# dependency on work_order_processor, and this file stays free of
# cross-app import-order assumptions at module level.
# ---
# TipoTarea — refleja exactamente chat.models.BreakdownTicket.TIPO_TAREA_CHOICES.
# Fijado aquí (sin import) por la misma razon documentada en
# work_order_processor/services.py::_VALID_TIPO_TAREA: chat.models no
# depende de work_order_processor, y este archivo se mantiene libre de
# suposiciones de orden de import entre apps a nivel de modulo.
# ---------------------------------------------------------------------------

class TipoTarea(models.TextChoices):
    """
    Nature of the work block: a real fault (AVERIA) or something else
    (MEJORA/MANTENIMIENTO/FABRICACION). Stored on WorkOrderEntryLine.
    tipo_tarea -- H10 Paso 4-bis. See TipoTarea usage note on the field
    itself for why this is persisted at line level, not only on the
    linked BreakdownTicket.
    ---
    Naturaleza del bloque de trabajo: una averia real (AVERIA) o algo
    distinto (MEJORA/MANTENIMIENTO/FABRICACION). Se almacena en
    WorkOrderEntryLine.tipo_tarea -- H10 Paso 4-bis. Ver la nota de uso
    en el propio campo sobre por que se persiste a nivel de linea y no
    solo en el BreakdownTicket vinculado.
    """

    AVERIA        = "AVERIA",        _("Avería")
    MEJORA        = "MEJORA",        _("Mejora")
    MANTENIMIENTO = "MANTENIMIENTO", _("Mantenimiento")
    FABRICACION   = "FABRICACION",   _("Fabricación")


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
        PENDING      = "PENDING",      _("Pendiente")
        PROCESSING   = "PROCESSING",   _("Procesando")
        DONE         = "DONE",         _("Completado")
        ERROR        = "ERROR",        _("Error")
        PENDING_GAPS = "PENDING_GAPS", _("Pendiente de justificación de jornada")
        IN_PROGRESS  = "IN_PROGRESS",  _("En curso (guardado progresivo)")

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
    # Original PDF filename — S028
    # Nombre original del fichero PDF — S028
    #
    # Persists the original PDF filename at upload time so that
    # pdf_display_name remains accurate after the pipeline deletes the
    # physical file and clears source_pdf (Paso 5 of process_work_order_pdf).
    # Empty for DIGITAL and GENERATED work orders (no PDF involved).
    #
    # Persiste el nombre original del fichero PDF en el momento de la
    # carga para que pdf_display_name siga siendo correcto después de
    # que el pipeline elimine el fichero físico y vacíe source_pdf
    # (Paso 5 de process_work_order_pdf). Vacío en partes DIGITAL y
    # GENERATED (sin PDF implicado).
    # ------------------------------------------------------------------
    source_pdf_name = models.CharField(
        _("Nombre original del PDF"),
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "Nombre del fichero PDF original tal como fue subido por el usuario. "
            "Se persiste en el momento de la carga y sobrevive al borrado del "
            "fichero físico ejecutado por el pipeline Celery (Paso 5). "
            "Vacío en partes de origen DIGITAL o GENERATED."
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
        Returns the human-readable PDF filename for display purposes.

        Priority:
          1. source_pdf_name (persisted at upload time, survives PDF deletion).
          2. source_pdf.name (legacy — file still on disk, pre-S028 records).
          3. Fallback: "Parte #<pk>" (no filename information available).

        The Django random suffix (_XXXXXXX before the extension) is stripped
        from both sources so the display name matches the original filename.

        ---

        Devuelve el nombre legible del fichero PDF para mostrar en la UI.

        Prioridad:
          1. source_pdf_name (persistido en la carga, sobrevive al borrado).
          2. source_pdf.name (legado — fichero en disco, registros pre-S028).
          3. Fallback: "Parte #<pk>" (sin información de nombre disponible).

        El sufijo aleatorio de Django (_XXXXXXX antes de la extensión) se
        elimina de ambas fuentes para coincidir con el fichero original.
        """
        import re
        _SUFFIX_RE = re.compile(r'_[A-Za-z0-9]{7}(\.[^.]+)$')

        if self.source_pdf_name:
            # Strip Django suffix from the persisted name if present.
            # Eliminar sufijo Django del nombre persistido si está presente.
            basename = self.source_pdf_name.split("/")[-1]
            cleaned  = _SUFFIX_RE.sub(r'', basename)
            return cleaned if cleaned else self.source_pdf_name

        if self.source_pdf:
            # Legacy path: file still on disk (pre-S028 records).
            # Ruta legado: fichero aún en disco (registros pre-S028).
            basename = self.source_pdf.name.split("/")[-1]
            return _SUFFIX_RE.sub(r'', basename)

        return f"Parte #{self.pk}"


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

    # ------------------------------------------------------------------
    # Lunch break / Pausa de comida
    #
    # Optional lunch break interval recorded by the operator on the part.
    # Pre-filled from the operator's WorkdaySchedule when the shift is
    # split (is_intensive=False). Left null for intensive shifts.
    # Used by the backend to deduct the overlapping portion of the break
    # from each WorkOrderEntryLine.delta_hours that spans this interval.
    #
    # Pausa de comida opcional registrada por el operario en el parte.
    # Prerrellenada desde el WorkdaySchedule del operario cuando la jornada
    # es partida (is_intensive=False). Nula para jornadas intensivas.
    # Usada por el backend para descontar la porción solapada de la pausa
    # de cada WorkOrderEntryLine.delta_hours que cubre ese intervalo.
    # ------------------------------------------------------------------
    lunch_break_start = models.TimeField(
        _("Inicio pausa de comida"),
        null=True,
        blank=True,
        help_text=_(
            "Hora de inicio de la pausa de comida del operario. "
            "Prerrellenada desde el WorkdaySchedule (end_time_morning) "
            "cuando la jornada es partida. Nula si no ha parado a comer."
        ),
    )
    lunch_break_end = models.TimeField(
        _("Fin pausa de comida"),
        null=True,
        blank=True,
        help_text=_(
            "Hora de fin de la pausa de comida del operario. "
            "Prerrellenada desde el WorkdaySchedule (start_time_afternoon) "
            "cuando la jornada es partida. Nula si no ha parado a comer."
        ),
    )

    # ------------------------------------------------------------------
    # No lunch break flag / Indicador de no pausa de comida
    #
    # Set by the operator when they did not stop for lunch. When True:
    #   - Gate 4 (_detect_workday_gaps) skips LUNCH_BREAK detection.
    #   - validators.py (validate_intra_gaps) skips the lunch exception.
    #   - lunch_break_start / lunch_break_end are ignored for delta_hours.
    #   - EARLY_END check still applies against the full workday end time.
    #
    # Activado por el operario cuando no ha parado a comer. Cuando True:
    #   - Gate 4 (_detect_workday_gaps) omite la detección de LUNCH_BREAK.
    #   - validators.py (validate_intra_gaps) omite la excepción de comida.
    #   - lunch_break_start / lunch_break_end se ignoran para delta_hours.
    #   - La comprobación EARLY_END sigue aplicando sobre la hora fin real.
    # ------------------------------------------------------------------
    no_lunch_break = models.BooleanField(
        _("No he parado a comer"),
        default=False,
        help_text=_(
            "Indica que el operario no ha realizado pausa de comida. "
            "Cuando está activo, el sistema no descuenta la pausa de comida "
            "del cálculo de horas ni valida la ventana de mediodía como "
            "laguna de jornada."
        ),
    )

    # ------------------------------------------------------------------
    # Diet flag / Indicador de dieta
    #
    # Set by the operator when they are entitled to a meal allowance
    # for the workday (e.g. working away from their usual base).
    # Part-level flag: one value per WorkOrderEntry, not per line.
    #
    # Activado por el operario cuando tiene derecho a dieta por la
    # jornada (p.ej. trabajo fuera de su base habitual).
    # Flag a nivel de parte: un valor por WorkOrderEntry, no por línea.
    # ------------------------------------------------------------------
    has_diet = models.BooleanField(
        _("Dieta"),
        default=False,
        help_text=_(
            "Indica que el operario ha percibido dieta en esta jornada "
            "(trabajo fuera de la base habitual). Se informa a nivel de "
            "parte, no de tarea individual."
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

    # ------------------------------------------------------------------
    # Task type -- H10 Paso 4-bis, persistencia también a nivel de línea
    # Tipo de tarea -- H10 Paso 4-bis, persistencia también a nivel de línea
    #
    # tipo_tarea/task_category_free ya existían en chat.BreakdownTicket, pero
    # ese campo solo se rellena cuando la línea tiene breakdown_ticket
    # vinculado. Las líneas legacy (partes PDF anteriores a H14, o cualquier
    # bloque sin ticket) nunca tenían dónde guardar esta clasificación --
    # aquí se persiste siempre, en la propia línea, con independencia de si
    # existe breakdown_ticket, para poder calcular volumen de mantenimiento/
    # mejoras/fabricación directamente sobre WorkOrderEntryLine sin depender
    # de un join a BreakdownTicket.
    #
    # tipo_tarea/task_category_free ya existian en chat.BreakdownTicket, pero
    # ese campo solo se rellena cuando la linea tiene breakdown_ticket
    # vinculado. Las lineas legacy (partes PDF anteriores a H14, o cualquier
    # bloque sin ticket) nunca tenian donde guardar esta clasificacion --
    # aqui se persiste siempre, en la propia linea, con independencia de si
    # existe breakdown_ticket, para poder calcular volumen de mantenimiento/
    # mejoras/fabricacion directamente sobre WorkOrderEntryLine sin depender
    # de un join a BreakdownTicket.
    # ------------------------------------------------------------------
    tipo_tarea = models.CharField(
        _("Tipo de tarea"),
        max_length=15,
        choices=TipoTarea.choices,
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "Naturaleza de este bloque de trabajo (avería, mejora, "
            "mantenimiento, fabricación). Poblado automáticamente por "
            "classify_fault_line junto con fault_category/fault_subcategory "
            "(solo si AVERIA) o task_category_free (el resto). No lo "
            "rellena el operario."
        ),
    )
    task_category_free = models.CharField(
        _("Categoría de tarea (libre)"),
        max_length=200,
        blank=True,
        default="",
        help_text=_(
            "Categorización libre generada por Gemini para bloques con "
            "tipo_tarea distinto de AVERIA (mejora, mantenimiento, "
            "fabricación...), sin taxonomía rígida. Vacío cuando "
            "tipo_tarea=AVERIA (se usa fault_category/fault_subcategory "
            "en su lugar) o cuando el bloque todavía no se ha clasificado."
        ),
    )

    # ------------------------------------------------------------------
    # Breakdown ticket link — H17
    # Vinculación con ticket de avería — H17
    # ------------------------------------------------------------------
    breakdown_ticket = models.ForeignKey(
        "chat.BreakdownTicket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_entry_lines",
        verbose_name=_("Ticket de avería"),
        help_text=_(
            "Ticket de avería al que corresponde este bloque de trabajo. "
            "Proporciona trazabilidad completa de horas invertidas por avería. "
            "Opcional — solo se informa cuando el bloque es una orden de reparación."
        ),
    )
    ticket_closed = models.BooleanField(
        _("Ticket cerrado"),
        default=False,
        help_text=_(
            "Marcar para cerrar el ticket de avería vinculado al guardar este bloque. "
            "El sistema establece BreakdownTicket.status=CLOSED automáticamente. "
            "Solo aplica cuando breakdown_ticket está informado."
        ),
    )

    # ------------------------------------------------------------------
    # On-site work flag / Indicador de trabajo in situ
    #
    # Set by the operator when the mechanic travelled to the machine's
    # location to carry out the repair, rather than the machine coming
    # to the workshop. Block-level flag: one value per entry line.
    #
    # Activado por el operario cuando el mecánico se desplazó hasta
    # donde se encontraba la máquina para realizar la reparación, en
    # lugar de que la máquina viniera al taller.
    # Flag a nivel de bloque: un valor por WorkOrderEntryLine.
    # ------------------------------------------------------------------
    is_on_site = models.BooleanField(
        _("Trabajo in situ"),
        default=False,
        help_text=_(
            "Indica que el mecánico se desplazó al lugar donde se "
            "encontraba la máquina para realizar la reparación "
            "(fuera del taller)."
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

    # ------------------------------------------------------------------
    # Spare parts warehouse link — Hito 10 / sesión S001
    # Vínculo con el almacén de repuestos — Hito 10 / sesión S001
    #
    # Points to the SparePartEntry that materialised this line at work
    # order closing time (see spare_parts app, annex H10 section 3.4).
    # Uses a string reference to avoid a circular import: spare_parts
    # already imports SparePartLine from this module.
    # Null for historic lines populated by OCR before this hito and
    # for lines entered manually outside the spare_parts circuit.
    #
    # Apunta a la SparePartEntry que materializó esta línea al cerrar
    # el parte (ver app spare_parts, anexo H10 sección 3.4). Usa
    # referencia de string para evitar import circular: spare_parts ya
    # importa SparePartLine de este módulo.
    # Nulo para líneas históricas pobladas por OCR antes de este hito
    # y para líneas introducidas manualmente fuera del circuito de
    # spare_parts.
    # ------------------------------------------------------------------
    spare_part_entry = models.ForeignKey(
        "spare_parts.SparePartEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resulting_spare_part_lines",
        verbose_name=_("Entrada de Almacén Origen"),
        help_text=_(
            "Repuesto del almacén digital (app spare_parts) que originó "
            "esta línea al cerrar el parte de trabajo. Nulo para líneas "
            "históricas o introducidas manualmente sin pasar por el "
            "circuito de almacén del Hito 10."
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


# ---------------------------------------------------------------------------
# WorkdayGap — Detected gap or deviation in a digital work order's workday.
# WorkdayGap — Laguna o desviación detectada en la jornada de un parte digital.
# ---------------------------------------------------------------------------

class WorkdayGap(models.Model):
    """
    Records each gap or workday deviation detected by Gate 4 in a digital
    work order. One record per detected gap/deviation per work order.
    Each record must be resolved before the work order can be promoted from
    PENDING_GAPS to DONE.

    Gap types:
      GAP         — uncovered time between two consecutive work blocks.
      LATE_START  — first block starts later than schedule + tolerance.
      EARLY_END   — last block ends earlier than schedule - tolerance.
      LUNCH_BREAK — midday window between morning and afternoon tracts
                    (split shift only). Resolved via a simplified lunch
                    confirmation: did the operator stop for lunch? If yes,
                    the gap is resolved; if no, a free-text note is required
                    explaining why (e.g. "urgencia en obra").

    Resolution rules per gap type:
      GAP / LATE_START / EARLY_END → absence_category required.
                                     note required if category.requires_note=True.
      LUNCH_BREAK                  → lunch_had (True/False) required.
                                     lunch_time (optional).
                                     note required when lunch_had=False.

    ---

    Registra cada laguna o desviación de jornada detectada por Gate 4 en un
    parte digital. Un registro por laguna/desviación detectada por parte.
    Cada registro debe resolverse antes de que el parte pueda pasar de
    PENDING_GAPS a DONE.

    Tipos de gap:
      GAP         — tiempo sin cubrir entre dos bloques de trabajo consecutivos.
      LATE_START  — el primer bloque empieza más tarde que el horario + tolerancia.
      EARLY_END   — el último bloque termina antes que el horario - tolerancia.
      LUNCH_BREAK — ventana de mediodía entre el tramo de mañana y el de tarde
                    (solo turno partido). Se resuelve con una confirmación simplificada
                    de comida: ¿ha parado el operario a comer? Si sí, el gap queda
                    resuelto; si no, se requiere nota libre explicando el motivo
                    (p. ej. "urgencia en obra").

    Reglas de resolución por tipo:
      GAP / LATE_START / EARLY_END → absence_category obligatoria.
                                     note obligatoria si category.requires_note=True.
      LUNCH_BREAK                  → lunch_had (True/False) obligatorio.
                                     lunch_time (opcional).
                                     note obligatoria cuando lunch_had=False.
    """

    # ------------------------------------------------------------------
    # Gap type choices / Opciones de tipo de laguna
    # ------------------------------------------------------------------
    class GapType(models.TextChoices):
        GAP          = "GAP",          _("Laguna entre bloques")
        LATE_START   = "LATE_START",   _("Inicio tardío")
        EARLY_END    = "EARLY_END",    _("Cierre anticipado")
        LUNCH_BREAK  = "LUNCH_BREAK",  _("Pausa de mediodía")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="workday_gaps",
        verbose_name=_("Parte de trabajo"),
        help_text=_(
            "Parte digital al que pertenece esta laguna de jornada. "
            "El parte debe tener status=PENDING_GAPS mientras tenga gaps no resueltos."
        ),
    )

    # ------------------------------------------------------------------
    # Gap identification / Identificación de la laguna
    # ------------------------------------------------------------------
    gap_type = models.CharField(
        _("Tipo"),
        max_length=15,
        choices=GapType.choices,
        help_text=_("Tipo de desviación de jornada detectada por Gate 4."),
    )
    gap_start = models.TimeField(
        _("Inicio de laguna"),
        help_text=_("Hora de inicio del intervalo sin cubrir o de la desviación detectada."),
    )
    gap_end = models.TimeField(
        _("Fin de laguna"),
        help_text=_("Hora de fin del intervalo sin cubrir o de la desviación detectada."),
    )
    duration_minutes = models.PositiveSmallIntegerField(
        _("Duración (minutos)"),
        help_text=_(
            "Duración de la laguna en minutos. "
            "Campo calculado — no editar manualmente."
        ),
    )

    # ------------------------------------------------------------------
    # Resolution — standard gaps / Resolución — gaps estándar
    # ------------------------------------------------------------------
    absence_category = models.ForeignKey(
        "ivr_config.AbsenceCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workday_gaps",
        verbose_name=_("Categoría de ausencia"),
        help_text=_(
            "Categoría de ausencia seleccionada por el operario para justificar "
            "esta laguna. Obligatoria para gaps de tipo GAP, LATE_START y EARLY_END. "
            "No aplica para LUNCH_BREAK."
        ),
    )
    note = models.TextField(
        _("Nota"),
        blank=True,
        default="",
        help_text=_(
            "Nota libre del operario para justificar la laguna. "
            "Obligatoria cuando AbsenceCategory.requires_note=True (gaps estándar) "
            "o cuando lunch_had=False (LUNCH_BREAK)."
        ),
    )
    resolved = models.BooleanField(
        _("Resuelto"),
        default=False,
        help_text=_(
            "True cuando el operario ha completado la resolución del gap según "
            "las reglas de su tipo. Gate 4 requiere que todos los gaps de un "
            "WorkOrder estén resueltos antes de promoverlo a DONE."
        ),
    )

    # ------------------------------------------------------------------
    # Resolution — lunch break / Resolución — pausa de mediodía
    # ------------------------------------------------------------------
    lunch_had = models.BooleanField(
        _("¿Ha comido?"),
        null=True,
        blank=True,
        default=None,
        help_text=_(
            "Solo para gaps de tipo LUNCH_BREAK. "
            "True: el operario paró a comer (gap resuelto sin nota). "
            "False: el operario no paró a comer — nota libre obligatoria. "
            "None: no aplica (gap de tipo distinto a LUNCH_BREAK)."
        ),
    )
    lunch_time = models.TimeField(
        _("Hora de comida"),
        null=True,
        blank=True,
        help_text=_(
            "Solo para gaps de tipo LUNCH_BREAK cuando lunch_had=True. "
            "Hora aproximada a la que el operario paró a comer. Opcional."
        ),
    )

    class Meta:
        verbose_name        = _("Laguna de jornada")
        verbose_name_plural = _("Lagunas de jornada")
        ordering            = ["work_order", "gap_start"]

    def __str__(self):
        return (
            f"Parte #{self.work_order_id} — "
            f"{self.get_gap_type_display()} "
            f"{self.gap_start:%H:%M}–{self.gap_end:%H:%M} "
            f"({'resuelto' if self.resolved else 'pendiente'})"
        )


# ---------------------------------------------------------------------------
# ExportTemplate — user-defined Excel export templates
# ExportTemplate — plantillas de exportación Excel definidas por usuario
# ---------------------------------------------------------------------------

class ExportTemplate(models.Model):
    """
    Stores a named Excel export configuration for a CompanyUser.
    Each template defines which columns to include, the sheet layout
    (single sheet vs one sheet per operator) and the operator scope
    (all operators vs a specific selection).

    A default template is created automatically the first time a user
    accesses the export modal if they have no templates yet.

    ---

    Almacena una configuración de exportación Excel con nombre para un
    CompanyUser. Cada plantilla define qué columnas incluir, el diseño
    de hojas (una hoja vs una por operario) y el alcance de operarios
    (todos vs una selección específica).

    Se crea una plantilla por defecto automáticamente la primera vez que
    el usuario accede al modal de exportación si no tiene ninguna todavía.
    """

    # ------------------------------------------------------------------
    # Sheet format choices / Opciones de formato de hoja
    # ------------------------------------------------------------------
    class SheetFormat(models.TextChoices):
        SINGLE_SHEET = "single_sheet", _("Una sola hoja")
        MULTI_SHEET  = "multi_sheet",  _("Una hoja por operario")

    # ------------------------------------------------------------------
    # Operator scope choices / Opciones de alcance de operarios
    # ------------------------------------------------------------------
    class OperatorScope(models.TextChoices):
        ALL       = "all",       _("Todos los operarios")
        SELECTION = "selection", _("Selección manual")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="export_templates",
        verbose_name=_("Usuario"),
        help_text=_(
            "Usuario propietario de esta plantilla (plantillas personales). "
            "Null para plantillas globales de empresa."
        ),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="global_export_templates",
        verbose_name=_("Empresa"),
        help_text=_(
            "Empresa propietaria de la plantilla global. "
            "Solo se usa cuando is_global=True. Null para plantillas personales."
        ),
    )

    # ------------------------------------------------------------------
    # Global flag / Indicador de plantilla global
    # ------------------------------------------------------------------
    is_global = models.BooleanField(
        _("Plantilla global"),
        default=False,
        db_index=True,
        help_text=_(
            "Si True, esta plantilla pertenece a la empresa y es visible por todos "
            "los supervisores en modo lectura. Solo los ADMIN pueden crearla o editarla. "
            "Si un supervisor la edita, se crea automáticamente una copia personal."
        ),
    )

    # ------------------------------------------------------------------
    # Identity / Identidad
    # ------------------------------------------------------------------
    name = models.CharField(
        _("Nombre"),
        max_length=100,
        help_text=_("Nombre descriptivo de la plantilla. Visible en el modal de exportación."),
    )
    is_default = models.BooleanField(
        _("Plantilla por defecto"),
        default=False,
        help_text=_(
            "Si True, esta plantilla se preselecciona automáticamente en el modal "
            "de exportación. Solo puede haber una plantilla por defecto por usuario."
        ),
    )

    # ------------------------------------------------------------------
    # Export configuration / Configuración de exportación
    # ------------------------------------------------------------------
    columns = models.JSONField(
        _("Columnas"),
        default=list,
        help_text=_(
            "Lista ordenada de claves de columna a incluir en el Excel. "
            "Valores válidos: fecha, operario, maquina, descripcion, notas, "
            "hc, hf, delta_horas, estado, familia, origen."
        ),
    )
    sheet_format = models.CharField(
        _("Formato de hoja"),
        max_length=20,
        choices=SheetFormat.choices,
        default=SheetFormat.SINGLE_SHEET,
        help_text=_(
            "single_sheet: todas las filas en una sola hoja agrupadas por operario. "
            "multi_sheet: una hoja por operario distinto."
        ),
    )
    operator_scope = models.CharField(
        _("Alcance de operarios"),
        max_length=20,
        choices=OperatorScope.choices,
        default=OperatorScope.ALL,
        help_text=_(
            "all: exportar todos los operarios del listado filtrado. "
            "selection: el usuario selecciona manualmente los operarios a incluir."
        ),
    )

    # ------------------------------------------------------------------
    # Timestamps / Marcas de tiempo
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(
        _("Creada el"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _("Actualizada el"),
        auto_now=True,
    )

    class Meta:
        verbose_name        = _("Plantilla de exportación")
        verbose_name_plural = _("Plantillas de exportación")
        ordering            = ["-is_global", "company_user", "-is_default", "name"]
        constraints         = [
            models.UniqueConstraint(
                fields=["company_user", "name"],
                condition=models.Q(company_user__isnull=False),
                name="unique_export_template_name_per_user",
            ),
            models.UniqueConstraint(
                fields=["company", "name"],
                condition=models.Q(is_global=True),
                name="unique_export_template_name_per_company_global",
            ),
        ]

    def __str__(self) -> str:
        default_marker = " ★" if self.is_default else ""
        if self.is_global:
            owner = self.company.name if self.company else "Global"
            return f"{self.name}{default_marker} [Global · {owner}]"
        owner = self.company_user.user.username if self.company_user else "?"
        return f"{self.name}{default_marker} ({owner})"

    def save(self, *args, **kwargs):
        """
        Ensures only one template per user (personal) is marked as default.
        Global templates do not participate in the is_default logic.
        ---
        Garantiza que solo una plantilla personal por usuario esté marcada como
        por defecto. Las plantillas globales no participan en la lógica is_default.
        """
        if self.is_default and self.company_user_id and not self.is_global:
            ExportTemplate.objects.filter(
                company_user=self.company_user,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_default(cls, company_user):
        """
        Returns the default ExportTemplate for the given company_user (personal only).
        If no personal templates exist for the user, creates and returns a sensible
        default with all standard columns selected.
        Global templates are never returned by this method.
        ---
        Devuelve la ExportTemplate por defecto del company_user indicado (solo personales).
        Si el usuario no tiene ninguna plantilla personal, crea y devuelve una con
        todas las columnas estándar seleccionadas.
        Las plantillas globales nunca son devueltas por este método.
        """
        existing = cls.objects.filter(
            company_user=company_user,
            is_global=False,
        ).order_by("-is_default").first()
        if existing:
            return existing
        return cls.objects.create(
            company_user   = company_user,
            company        = None,
            is_global      = False,
            name           = "Exportación estándar",
            is_default     = True,
            columns        = [
                "fecha", "operario", "maquina", "descripcion",
                "notas", "hc", "hf", "delta_horas", "estado", "familia",
            ],
            sheet_format   = cls.SheetFormat.SINGLE_SHEET,
            operator_scope = cls.OperatorScope.ALL,
        )


# ---------------------------------------------------------------------------
# OperatorMonthlyCost
# ---------------------------------------------------------------------------

class OperatorMonthlyCost(models.Model):
    """
    Stores the total labour cost for a single operator over a single
    WorkPeriod (contract/liquidation period, ivr_config.models.WorkPeriod
    -- not a calendar month; see Key Learning below). Used by the
    Analytics Laboratory (H20, dimension D6) to distribute operator cost
    across every machine_asset/centro de gasto (real machines AND
    internal cost centres like PERSONAL, EMPRESA_ALMACEN_*) proportionally
    to hours worked, with no special-casing between the two.

    The cost figure represents the operator's TOTAL cost for the period:
    full payroll (nómina) plus any overtime (horas extraordinarias)
    already included as a single blended amount -- this model does not
    distinguish an ordinary-hour rate from an overtime-hour rate.

    company and worker identity are NOT stored redundantly here -- both
    are derived through work_period.company_user (company_user.company,
    company_user.user.get_full_name()). One cost record can exist per
    WorkPeriod (OneToOneField), which is a stronger guarantee than the
    previous (company, worker_name, year, month) unique_together and
    removes the risk of two records disagreeing about which operator/
    period they represent.

    Key Learning (H20, S010, 2026-07-09): redesigned from a
    (company, worker_name, year, month) key to WorkPeriod after a
    conversation between Miguel Ángel and Jerónimo (SUPERVISOR,
    accounting/payroll). Calendar months don't match how the workshop
    actually liquidates labour cost -- WorkPeriod (contract/liquidation
    periods, open or closed) is the real unit. See the H20 annex, section
    "NOTA DE DISEÑO -- S010", for the full design discussion.
    ---
    Almacena el coste laboral total de un operario para un único
    WorkPeriod (periodo de contrato/liquidación,
    ivr_config.models.WorkPeriod -- no un mes natural; ver Key Learning
    más abajo). Usado por el Laboratorio de Análisis (H20, dimensión D6)
    para repartir el coste del operario entre todos los machine_asset/
    centros de gasto (máquinas reales Y centros de gasto internos como
    PERSONAL, EMPRESA_ALMACEN_*) proporcionalmente a las horas
    trabajadas, sin distinción especial entre ambos.

    El importe representa el coste TOTAL del operario para el periodo:
    nómina completa más horas extraordinarias ya incluidas como un único
    importe mezclado -- este modelo no distingue tarifa de hora ordinaria
    de tarifa de hora extraordinaria.

    La identidad de empresa y operario NO se guardan de forma redundante
    aquí -- ambas se derivan a través de work_period.company_user
    (company_user.company, company_user.user.get_full_name()). Solo puede
    existir un registro de coste por WorkPeriod (OneToOneField), una
    garantía más fuerte que el anterior unique_together (company,
    worker_name, year, month), y elimina el riesgo de que dos registros
    discrepen sobre a qué operario/periodo representan.

    Key Learning (H20, S010, 2026-07-09): rediseñado de una clave
    (company, worker_name, year, month) a WorkPeriod tras una
    conversación de Miguel Ángel con Jerónimo (SUPERVISOR,
    contabilidad/nóminas). Los meses naturales no reflejan cómo el
    taller liquida realmente el coste laboral -- WorkPeriod (periodos de
    contrato/liquidación, abiertos o cerrados) es la unidad real. Ver el
    anexo de H20, sección "NOTA DE DISEÑO -- S010", para la discusión
    completa de diseño.
    """

    work_period = models.OneToOneField(
        WorkPeriod,
        on_delete=models.CASCADE,
        related_name='operator_cost',
        verbose_name='periodo de trabajo',
        help_text=(
            'Periodo de contrato/liquidación (ivr_config.WorkPeriod) al '
            'que corresponde este coste. Un único registro de coste por '
            'periodo -- la empresa y el operario se derivan de '
            'work_period.company_user.'
        ),
    )

    # Full operator cost for the period in EUR: nómina + horas extra,
    # sin desglosar. Coste total del operario para el periodo en EUR:
    # nómina + horas extra, sin desglosar.
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='coste total del periodo (EUR)',
        help_text=(
            'Coste total del operario para este periodo: nómina completa '
            'más horas extraordinarias ya incluidas en un único importe.'
        ),
    )

    # Audit timestamps / Marcas de tiempo de auditoria.
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='creado en',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='actualizado en',
    )

    class Meta:
        ordering = ['-work_period__start_date']
        verbose_name = 'Coste de operario por periodo'
        verbose_name_plural = 'Costes de operarios por periodo'

    def __str__(self):
        """
        Returns a human-readable representation of the cost record.
        WorkPeriod.__str__ already embeds the operator's name, so it is
        not repeated here to avoid duplication.
        ---
        Devuelve una representacion legible del registro de coste.
        WorkPeriod.__str__ ya incluye el nombre del operario, por lo que
        no se repite aquí para evitar duplicación.
        """
        return f'{self.work_period}: {self.total_cost} EUR'


# ---------------------------------------------------------------------------
# TaskPhoto — optional photo attached to a work block (H7, session S016)
# TaskPhoto — foto opcional adjunta a un bloque de trabajo (H7, sesión S016)
# ---------------------------------------------------------------------------

class TaskPhoto(models.Model):
    """
    An optional photo attached to a WorkOrderEntryLine (a task/work block).
    Never mandatory — the operator may attach zero or more photos to any
    line regardless of tipo_tarea.

    company, breakdown_ticket and machine_asset are denormalised from the
    parent line at creation time (same rationale as
    BreakdownTicket.section: fast filtering — "photos for this machine",
    "photos for this ticket" — without a join through the line, and stable
    traceability even if the line's own FKs change afterwards).
    breakdown_ticket is null whenever the line has no ticket linked (most
    tasks — ticket linkage is itself optional on WorkOrderEntryLine).

    Persistence mirrors spare_parts.DeliveryNote (S014-H10): the photo is
    saved locally on upload, then a Celery task
    (work_order_processor.tasks.upload_task_photo_to_drive) pushes it to
    Google Drive via spare_parts.gdrive_service and deletes the local file
    once the upload is confirmed. drive_file_id/drive_web_link stay empty
    until that confirmation.

    ---

    Foto opcional adjunta a un WorkOrderEntryLine (una tarea/bloque de
    trabajo). Nunca obligatoria — el operario puede adjuntar cero o más
    fotos a cualquier línea, sea cual sea su tipo_tarea.

    company, breakdown_ticket y machine_asset están denormalizados desde
    la línea padre en el momento de creación (mismo criterio que
    BreakdownTicket.section: filtrado rápido -- "fotos de esta máquina",
    "fotos de este ticket" -- sin join a través de la línea, y trazabilidad
    estable aunque los FK propios de la línea cambien después).
    breakdown_ticket queda nulo cuando la línea no tiene ticket vinculado
    (la mayoría de tareas -- la vinculación a ticket es en sí misma
    opcional en WorkOrderEntryLine).

    La persistencia replica spare_parts.DeliveryNote (S014-H10): la foto
    se guarda localmente al subirla, y una tarea Celery
    (work_order_processor.tasks.upload_task_photo_to_drive) la sube a
    Google Drive vía spare_parts.gdrive_service y borra el archivo local
    una vez confirmada la subida. drive_file_id/drive_web_link quedan
    vacíos hasta esa confirmación.
    """

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    line = models.ForeignKey(
        WorkOrderEntryLine,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name=_("Bloque de trabajo"),
        help_text=_(
            "Bloque de trabajo (tarea) al que pertenece esta foto. "
            "Un bloque puede tener cero o más fotos."
        ),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="task_photos",
        verbose_name=_("Empresa"),
        help_text=_(
            "Empresa a la que pertenece esta foto, denormalizada desde "
            "line.entry.work_order.company en el momento de creación."
        ),
    )
    breakdown_ticket = models.ForeignKey(
        "chat.BreakdownTicket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_photos",
        verbose_name=_("Ticket de avería"),
        help_text=_(
            "Ticket de avería vinculado a la línea en el momento de "
            "creación de la foto (denormalizado desde line.breakdown_ticket). "
            "Nulo cuando la línea no tiene ticket vinculado."
        ),
    )
    machine_asset = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_photos",
        verbose_name=_("Máquina / Centro de gasto"),
        help_text=_(
            "Máquina o centro de gasto vinculado a la línea en el momento "
            "de creación de la foto (denormalizado desde line.machine_asset)."
        ),
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_photos_uploaded",
        verbose_name=_("Subida por"),
        help_text=_("Usuario del panel que adjuntó esta foto."),
    )

    # ------------------------------------------------------------------
    # File / Archivo
    # ------------------------------------------------------------------
    image = models.ImageField(
        _("Foto"),
        upload_to="task_photos/",
        help_text=_(
            "Archivo original subido por el operario. Se sube a Google "
            "Drive tras la confirmación y se borra del servidor -- mismo "
            "criterio que spare_parts.DeliveryNote (S014-H10)."
        ),
    )
    caption = models.CharField(
        _("Descripción"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("Descripción opcional de lo que muestra la foto."),
    )

    # ------------------------------------------------------------------
    # Cloud persistence (S016-H07) — same fields/rationale as
    # spare_parts.DeliveryNote.drive_file_id / drive_web_link.
    # Persistencia en la nube (S016-H07) — mismos campos/razón de ser
    # que spare_parts.DeliveryNote.drive_file_id / drive_web_link.
    # ------------------------------------------------------------------
    drive_file_id = models.CharField(
        _("ID de archivo en Google Drive"),
        max_length=100,
        blank=True,
        default="",
    )
    drive_web_link = models.URLField(
        _("Enlace de Google Drive"),
        max_length=500,
        blank=True,
        default="",
    )
    # Persistencia en Google Cloud Storage (S022) -- ver
    # spare_parts.gcs_service.TASK_PHOTOS_BUCKET. drive_file_id/
    # drive_web_link quedan como legado (no hay fotos ya subidas a
    # Drive a fecha de esta migración, per Miguel Ángel S022, pero se
    # mantienen los campos por coherencia con los otros dos modelos).
    gcs_blob_name = models.CharField(
        _("Ruta del objeto en Google Cloud Storage"),
        max_length=500,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        _("Fecha de creación"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Foto de tarea")
        verbose_name_plural = _("Fotos de tarea")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Foto #{self.pk} — {self.line} ({self.machine_asset or 'sin máquina'})"