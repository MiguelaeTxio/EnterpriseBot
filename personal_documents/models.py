# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/personal_documents/models.py
"""
Data models for the personal_documents app (Hito 25).

PersonalDocument is the sibling of machine_documents.MachineDocument
(H23): same classification/persistence design (status PENDING ->
CLASSIFIED/ERROR, GCS persistence, hybrid dynamic-fields model), but
pointing at a worker (ivr_config.CompanyUser) instead of a
fleet.MachineAsset. Kept as a fully separate app/model on purpose --
explicit decision of Miguel Ángel in S022 ("la modularidad ya es
importante porque el proyecto tiene una dimensión gigantesca"), not a
subclass or a shared abstract base -- see
ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md sección 2.1.

Two differences from MachineDocument, both closed with Miguel Ángel in
S024:

1. `company_user` is NULLABLE (MachineDocument.machine_asset is not).
   A document detected during folder ingestion (H23/H27's automatic
   detection flow) can name a worker who doesn't have a CompanyUser
   account yet -- pre-registration by DNI is a separate, not-yet-built
   piece (its own CRUD, still to be designed with Miguel Ángel). Until
   that exists, the document is persisted with company_user=None and
   `detected_dni_hint` kept for traceability, and shows up in the
   panel's "sin asignar" bucket (see
   ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md, "Decisiones cerradas en
   S024", propuesta d) until someone links it by hand.
2. Two extra fields not present in MachineDocument, for the "computed
   expiry" case identified in the real example folder Miguel Ángel
   provided in S022 (a medical check-up whose filename had a
   hand-calculated expiry date, while the document itself only stated
   "la validez del resultado de su examen de salud es ANUAL" plus the
   real exam date): `validity_rule` (the textual rule Gemini detects
   in the document, verbatim) and `computed_expiry_date` (the actual
   date derived from applying that rule to `issue_date`). `expiry_date`
   is kept for the other case -- a document that states its expiry
   date directly, same as MachineDocument. Never both filled at once
   for the same document; the vigencia logic (H26) checks
   `expiry_date` first, `computed_expiry_date` otherwise.

Access role (S024, confirmado por Miguel Ángel): ADMIN y
DOCS_SUPERVISOR únicamente -- dato sensible (DNI, salud) -- nunca
WORKSHOP/DRIVER, ni siquiera para su propia documentación. Enforced en
las vistas (panel/personal_documents), no en este modelo.

---

Modelos de datos para la app personal_documents (Hito 25).

PersonalDocument es el hermano de machine_documents.MachineDocument
(H23): mismo diseño de clasificación/persistencia (status PENDING ->
CLASSIFIED/ERROR, persistencia en GCS, modelo híbrido de campos
dinámicos), pero apuntando a un trabajador (ivr_config.CompanyUser) en
vez de a un fleet.MachineAsset. Se mantiene como app/modelo
completamente separado a propósito -- decisión explícita de Miguel
Ángel en S022 ("la modularidad ya es importante porque el proyecto
tiene una dimensión gigantesca"), no una subclase ni una base
abstracta compartida -- ver ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md
sección 2.1.

Dos diferencias frente a MachineDocument, ambas cerradas con Miguel
Ángel en S024:

1. `company_user` es NULLABLE (MachineDocument.machine_asset no lo
   es). Un documento detectado durante la ingesta de carpeta (flujo de
   detección automática de H23/H27) puede nombrar a un trabajador que
   todavía no tiene cuenta CompanyUser -- el pre-registro por DNI es
   una pieza aparte, todavía sin construir (su propio CRUD, pendiente
   de diseñar con Miguel Ángel). Hasta que exista, el documento se
   persiste con company_user=None y se conserva `detected_dni_hint`
   para trazabilidad, y aparece en el bloque "sin asignar" del panel
   (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md, "Decisiones cerradas
   en S024", propuesta d) hasta que alguien lo vincule a mano.
2. Dos campos extra que MachineDocument no tiene, para el caso de
   "vigencia calculada" identificado en la carpeta de ejemplo real que
   aportó Miguel Ángel en S022 (un reconocimiento médico cuyo nombre de
   archivo llevaba una fecha de caducidad calculada a mano, mientras
   que el documento en sí solo indicaba "la validez del resultado de
   su examen de salud es ANUAL" más la fecha real del examen):
   `validity_rule` (la regla textual que Gemini detecta en el
   documento, tal cual) y `computed_expiry_date` (la fecha real
   derivada de aplicar esa regla a `issue_date`). `expiry_date` se
   mantiene para el otro caso -- un documento que declara su fecha de
   caducidad directamente, igual que MachineDocument. Nunca se rellenan
   los dos a la vez para el mismo documento; la lógica de vigencia
   (H26) comprueba `expiry_date` primero, `computed_expiry_date` si no.

Rol de acceso (S024, confirmado por Miguel Ángel): ADMIN y
DOCS_SUPERVISOR únicamente -- dato sensible (DNI, salud) -- nunca
WORKSHOP/DRIVER, ni siquiera para su propia documentación. Se aplica en
las vistas (panel/personal_documents), no en este modelo.
"""
from django.db import models

from ivr_config.models import Company, CompanyUser


class PersonalDocument(models.Model):
    """
    A single official document belonging to a worker, classified by
    content via Gemini Vision and persisted in Google Cloud Storage.
    Sibling model of machine_documents.MachineDocument -- see module
    docstring for the two real differences.
    ---
    Un documento oficial de un trabajador, clasificado por contenido
    vía Gemini Vision y persistido en Google Cloud Storage. Modelo
    hermano de machine_documents.MachineDocument -- ver el docstring
    del módulo para las dos diferencias reales.
    """

    class Status(models.TextChoices):
        """
        Same processing status semantics as
        machine_documents.MachineDocument.Status, plus UNASSIGNED for
        documents whose worker couldn't be determined with enough
        confidence during automatic folder ingestion (H23/H27) --
        classified, but not linked to any CompanyUser yet.
        ---
        Misma semántica de estado que
        machine_documents.MachineDocument.Status, más UNASSIGNED para
        documentos cuyo trabajador no se pudo determinar con
        confianza suficiente durante la ingesta automática de carpeta
        (H23/H27) -- clasificado, pero sin enlazar todavía a ningún
        CompanyUser.
        """
        PENDING = "PENDING", "Pendiente"
        CLASSIFIED = "CLASSIFIED", "Clasificado"
        UNASSIGNED = "UNASSIGNED", "Clasificado, sin asignar"
        ERROR = "ERROR", "Error"

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_documents",
        verbose_name="Trabajador",
        help_text="Trabajador al que pertenece este documento. Nulo "
                  "cuando la ingesta automática de carpeta detecta un "
                  "DNI/nombre que todavía no tiene cuenta CompanyUser "
                  "-- ver detected_dni_hint. Nunca nulo en la subida "
                  "manual (el usuario elige siempre el trabajador).",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="personal_documents",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este documento, "
                  "denormalizada desde company_user.company (o "
                  "asignada explícitamente en la subida cuando "
                  "company_user es nulo) -- mismo patrón que "
                  "TaskPhoto/MachineDocument.",
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_documents_uploaded",
        verbose_name="Subido por",
        help_text="Usuario del panel (ADMIN o DOCS_SUPERVISOR) que "
                  "subió este documento.",
    )
    detected_dni_hint = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="DNI detectado (sin asignar)",
        help_text="DNI leído por Gemini en el propio documento cuando "
                  "company_user es nulo -- trazabilidad para vincular "
                  "manualmente en cuanto exista el CRUD de "
                  "pre-registro. Vacío en cualquier otro caso.",
    )

    # ------------------------------------------------------------------
    # Processing status / Estado de procesamiento
    # ------------------------------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Estado",
    )
    error_message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Mensaje de error",
        help_text="Motivo del fallo cuando status=ERROR. Vacío en "
                  "cualquier otro estado.",
    )

    # ------------------------------------------------------------------
    # Classification (Gemini Vision) / Clasificación (Gemini Vision)
    # ------------------------------------------------------------------
    document_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Tipo de documento",
        help_text="Categoría propuesta por Gemini a partir del "
                  "contenido del documento (identidad, contractual, "
                  "permiso/carnet, reconocimiento médico, curso de "
                  "formación, EPI, u otra categoría que Gemini "
                  "proponga libremente -- sin lista cerrada, mismo "
                  "criterio que MachineDocument). Vacío mientras "
                  "status=PENDING.",
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre legible",
        help_text="Nombre legible generado a partir del contenido "
                  "(ej. \"Carnet de Grúas A (vigente)\"), usado tanto "
                  "en BD como en el propio archivo persistido en GCS. "
                  "Vacío mientras status=PENDING.",
    )
    source_master_hint = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Origen (documento maestro)",
        help_text="Si este documento se extrajo de un PDF maestro en "
                  "vez de subirse ya como archivo individual, nombre "
                  "del archivo maestro de procedencia (trazabilidad, "
                  "mismo mecanismo que MachineDocument). Vacío cuando "
                  "el documento se subió directamente como "
                  "individual.",
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre de archivo original",
        help_text="Nombre tal como lo subió el usuario o como llegó "
                  "en la carpeta de ingesta, capturado en la "
                  "creación -- usado por la heurística de nombre de "
                  "archivo y como contexto de prompt.",
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de caducidad",
        help_text="Fecha de fin de vigencia cuando el propio "
                  "documento la declara directamente (permisos, "
                  "carnets...). Nulo si el documento no tiene fecha "
                  "de caducidad explícita o su vigencia se calcula "
                  "vía validity_rule/computed_expiry_date en su "
                  "lugar.",
    )
    issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de emisión",
        help_text="Fecha de emisión/expedición extraída del "
                  "contenido, o fecha real del examen/curso cuando "
                  "aplica -- base para calcular computed_expiry_date "
                  "cuando hay validity_rule. Nulo si no aplica o no "
                  "se pudo extraer.",
    )
    validity_rule = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Regla de vigencia (texto detectado)",
        help_text="Regla de vigencia tal como la declara el propio "
                  "documento cuando no da una fecha de caducidad "
                  "directa (ej. \"validez ANUAL desde la fecha del "
                  "examen\", detectado literalmente por Gemini en un "
                  "reconocimiento médico -- caso real, carpeta de "
                  "ejemplo S022). Vacío cuando el documento declara "
                  "expiry_date directamente o no tiene vigencia.",
    )
    computed_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de caducidad calculada",
        help_text="Fecha derivada de aplicar validity_rule a "
                  "issue_date (ej. examen del 15/09/2025 + regla "
                  "ANUAL -> 15/09/2026). Se calcula solo cuando el "
                  "documento no declara expiry_date directamente -- "
                  "decisión de Miguel Ángel en S022 (\"que sea de "
                  "forma explícita siempre que exista y que se "
                  "calcule cuando no haya otra opción\"). Nunca "
                  "relleno a la vez que expiry_date para el mismo "
                  "documento.",
    )
    document_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Número/referencia de documento",
        help_text="Número de carnet, expediente, código de acción "
                  "formativa, etc. extraído del contenido, cuando el "
                  "documento tiene uno reconocible.",
    )
    issuing_entity = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Entidad emisora",
        help_text="Organismo, entidad formadora o empresa que emite "
                  "el documento, cuando se identifica en el "
                  "contenido.",
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        verbose_name="Inicio de periodo",
        help_text="Inicio de periodo extraído del contenido (ej. "
                  "fecha de inicio de un curso de formación), cuando "
                  "aplica. Mismo campo que MachineDocument.period_start "
                  "por coherencia, aunque su uso real difiera.",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fin de periodo",
        help_text="Fin de periodo extraído del contenido (ej. fecha "
                  "de fin de un curso de formación), cuando aplica.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Importe",
        help_text="Importe en euros extraído del contenido, cuando el "
                  "documento lleva una cantidad monetaria reconocible "
                  "(ej. coste de un curso). Nulo si no aplica o no se "
                  "pudo extraer.",
    )
    extra_data = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        verbose_name="Metadatos adicionales",
        help_text="Mismo diseño híbrido que MachineDocument.extra_data "
                  "(decisión S021, reafirmada para H25 en S024): "
                  "campos de fecha/importe que se repiten tienen "
                  "columna propia con tipo real; este JSON es "
                  "exclusivamente para lo genuinamente impredecible "
                  "por tipo de documento -- especialmente relevante "
                  "aquí, dado el volumen y variedad de document_type "
                  "en personal frente a centros de gasto (ver anexo "
                  "H25 sección 3.bis). Vacío ({}) por defecto.",
    )

    # ------------------------------------------------------------------
    # Archival / Archivado — mismo campo y semántica que se diseñó
    # para MachineDocument en S021 (ver anexo H23, "Decisiones
    # cerradas en S021", punto 2) y que H26 consume igual para ambos
    # dominios (document_management.vigencia_service).
    # ------------------------------------------------------------------
    is_archived = models.BooleanField(
        default=False,
        verbose_name="Archivado",
        help_text="True cuando este documento quedó superado por uno "
                  "más vigente del mismo tipo (o se archivó a mano). "
                  "Los documentos archivados aparecen en la sección "
                  "\"Archivados\" del listado, con opción de borrado "
                  "manual -- mismo criterio que MachineDocument.",
    )

    # ------------------------------------------------------------------
    # Cloud persistence — Google Cloud Storage desde el origen (H25 se
    # abre después de la migración GCS de H23/S022, nunca pasa por
    # Google Drive) — bucket dedicado
    # enterprisebot-alvarez-personnel-documents, ya confirmado en el
    # anexo H25 sección 2.3 y en la migración de H23 sección 5.
    # ------------------------------------------------------------------
    gcs_blob_name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Ruta del objeto en Google Cloud Storage",
    )

    # ------------------------------------------------------------------
    # Local staging file — mismo patrón que
    # MachineDocument.source_file: se borra tras la subida a GCS con
    # éxito, se conserva si falla para poder reintentar.
    # ------------------------------------------------------------------
    source_file = models.FileField(
        upload_to="personal_documents/%Y/%m/",
        blank=True,
        verbose_name="Archivo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Documento de personal"
        verbose_name_plural = "Documentos de personal"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        quien = self.company_user or self.detected_dni_hint or "(sin asignar)"
        return f"{self.display_name or '(pendiente)'} — {quien}"
