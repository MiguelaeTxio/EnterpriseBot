# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/models.py
"""
Data models for the machine_documents app (Hito 23).

MachineDocument stores a pointer to a single official document of a
MachineAsset (technical sheet, ITV card, inspection certificate,
insurance receipt, registry inscription, CE declaration, etc.). The
actual file lives in Google Drive (same pattern as
work_order_processor.TaskPhoto / spare_parts.DeliveryNote); this model
only keeps the Drive reference plus metadata produced by the Gemini
Vision classification service (machine_documents/document_classification_service.py).

Processing is asynchronous (Celery task
machine_documents.tasks.process_machine_document_batch, added
2026-07-14 after a PythonAnywhere webapp timeout incident with a
synchronous first version -- see that task's docstring): a document is
created here with status=PENDING the instant it's uploaded (fast, no
Gemini/Drive calls on the request thread), and the task fills in
document_type/display_name/expiry_date/etc. and uploads to Drive in
the background. status distinguishes PENDING (queued, not processed
yet) from CLASSIFIED (done) and ERROR (classification or extraction
failed -- see error_message).

document_type is intentionally a free CharField, not a closed
`choices` list: per Miguel Ángel's explicit decision (S016 session
that opened this milestone), Gemini may propose new categories on its
own when none of the known ones fit, instead of forcing everything
into a generic "OTRO" bucket.

expiry_date/issue_date/document_number/issuing_entity (added
2026-07-14, Miguel Ángel's decision) are extracted in the SAME Gemini
call as the classification, not a separate one -- every extra field
in one response_schema costs a few output tokens, while a second call
per document would double the request count against PythonAnywhere's
5-minute limit, which is exactly what caused the incident these
fields are being added right after. All four are optional: not every
document type carries all four (a technical sheet has no expiry date;
a manual classified by filename heuristic never touches Gemini at all
and so never gets any of them). expiry_date is captured now
specifically so a future alerting feature (documents nearing expiry)
has the data it needs without having to re-process every document
retroactively -- Miguel Ángel flagged this as the next likely step,
not built in this milestone.

---

Modelos de datos para la app machine_documents (Hito 23).

MachineDocument almacena un puntero a un único documento oficial de un
MachineAsset (ficha técnica, tarjeta ITV, certificado de inspección,
recibo de seguro, inscripción de registro, declaración CE, etc.). El
archivo real vive en Google Drive (mismo patrón que
work_order_processor.TaskPhoto / spare_parts.DeliveryNote); este
modelo solo guarda la referencia de Drive más los metadatos producidos
por el servicio de clasificación Gemini Vision
(machine_documents/document_classification_service.py).

El procesamiento es asíncrono (tarea Celery
machine_documents.tasks.process_machine_document_batch, añadida
2026-07-14 tras un incidente de timeout del webapp de PythonAnywhere
con una primera versión síncrona -- ver el docstring de esa tarea): un
documento se crea aquí con status=PENDING en el instante en que se
sube (rápido, sin llamadas a Gemini/Drive en el hilo de la petición),
y la tarea rellena document_type/display_name/expiry_date/etc. y sube
a Drive en segundo plano. status distingue PENDING (en cola, aún sin
procesar) de CLASSIFIED (terminado) y ERROR (falló la clasificación o
extracción -- ver error_message).

document_type es deliberadamente un CharField libre, no una lista
`choices` cerrada: por decisión explícita de Miguel Ángel (sesión S016
que abrió este hito), Gemini puede proponer categorías nuevas por su
cuenta cuando ninguna de las conocidas encaja, en vez de forzar todo
a un cajón genérico "OTRO".

expiry_date/issue_date/document_number/issuing_entity (añadidos
2026-07-14, decisión de Miguel Ángel) se extraen en la MISMA llamada a
Gemini que la clasificación, no en una llamada aparte -- cada campo
extra en un mismo response_schema cuesta unos pocos tokens de salida
más, mientras que una segunda llamada por documento duplicaría el
número de peticiones contra el límite de 5 minutos de PythonAnywhere,
que es exactamente lo que causó el incidente justo después del cual se
añaden estos campos. Los cuatro son opcionales: no todos los tipos de
documento llevan los cuatro (una ficha técnica no tiene fecha de
caducidad; un manual clasificado por heurística de nombre nunca toca
Gemini y por tanto nunca los tiene). expiry_date se captura ya
específicamente para que una futura funcionalidad de avisos
(documentos próximos a caducar) tenga el dato que necesita sin tener
que reprocesar retroactivamente cada documento -- Miguel Ángel señaló
esto como el siguiente paso probable, no construido en este hito.
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

    class Status(models.TextChoices):
        """
        Processing status -- set to PENDING at creation (upload
        request thread), moved to CLASSIFIED, UNASSIGNED or ERROR by
        machine_documents.tasks.process_machine_document_batch.

        UNASSIGNED added S024 alongside the automatic folder-ingestion
        feature (document_ingestion.entity_matching_service): a
        document routed to the MACHINE domain whose code/plate couldn't
        be matched with confidence against a real MachineAsset is
        still classified (document_type/display_name/etc. filled in),
        just not linked to any machine yet -- machine_asset stays null
        until a human assigns it by hand from the "sin asignar" bucket
        (same principle already applied to PersonalDocument in S024).
        ---
        Estado de procesamiento -- se pone a PENDING en la creación
        (hilo de la petición de subida), y pasa a CLASSIFIED,
        UNASSIGNED o ERROR desde
        machine_documents.tasks.process_machine_document_batch.

        UNASSIGNED añadido en S024 junto con la ingesta automática de
        carpeta (document_ingestion.entity_matching_service): un
        documento enrutado al dominio MACHINE cuyo código/matrícula no
        se pudo emparejar con confianza contra un MachineAsset real
        sigue clasificado (document_type/display_name/etc. rellenos),
        solo que sin enlazar todavía a ninguna máquina -- machine_asset
        se queda a null hasta que una persona lo asigne a mano desde el
        bloque "sin asignar" (mismo principio ya aplicado a
        PersonalDocument en S024).
        """
        PENDING = "PENDING", "Pendiente"
        CLASSIFIED = "CLASSIFIED", "Clasificado"
        UNASSIGNED = "UNASSIGNED", "Clasificado, sin asignar"
        ERROR = "ERROR", "Error"

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    machine_asset = models.ForeignKey(
        MachineAsset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="Máquina / Centro de gasto",
        help_text="Máquina o centro de gasto al que pertenece este "
                  "documento. Nulo cuando la ingesta automática de "
                  "carpeta (S024) detecta un código/matrícula que no "
                  "se pudo emparejar con confianza -- ver "
                  "Status.UNASSIGNED. Nunca nulo en la subida manual "
                  "de una sola máquina (el usuario elige siempre la "
                  "máquina antes de subir).",
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
    detected_reference_hint = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Código/matrícula detectado (sin asignar)",
        help_text="Código o matrícula leído por Gemini en el propio "
                  "documento cuando machine_asset es nulo -- "
                  "trazabilidad para vincular manualmente desde el "
                  "bloque \"sin asignar\". Vacío en cualquier otro "
                  "caso. Simétrico a "
                  "PersonalDocument.detected_dni_hint (S024).",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Hash de contenido (SHA-256)",
        help_text="SHA-256 de los bytes crudos del archivo, calculado "
                  "en la subida -- deduplicación (S024, ver "
                  "document_ingestion.deduplication_service). Vacío "
                  "solo en filas anteriores a S024.",
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
                  "contenido del documento (ficha técnica, tarjeta "
                  "ITV, certificado de inspección, recibo de seguro, "
                  "inscripción de registro, declaración CE, u otra "
                  "categoría que Gemini proponga libremente — sin "
                  "lista cerrada). Vacío mientras status=PENDING.",
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre legible",
        help_text="Nombre legible generado a partir del contenido "
                  "(ej. \"Certificado OCA 2025-2026 (vigente)\"), "
                  "usado tanto en BD como en el propio archivo "
                  "persistido en Drive. Vacío mientras status=PENDING.",
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
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nombre de archivo original",
        help_text="Nombre tal como lo subió el usuario, capturado en "
                  "la creación. source_file.name es la ruta de "
                  "almacenamiento (Django puede añadirle un sufijo si "
                  "hay colisión de nombres) -- este campo es el que "
                  "usa la tarea de clasificación para la heurística de "
                  "nombre de archivo y como contexto de prompt.",
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de caducidad",
        help_text="Fecha de fin de vigencia extraída del contenido "
                  "del documento (ITV, certificados OCA, seguros...). "
                  "Nulo si el documento no tiene fecha de caducidad o "
                  "no se pudo extraer.",
    )
    issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de emisión",
        help_text="Fecha de emisión/expedición extraída del "
                  "contenido del documento. Nulo si no aplica o no se "
                  "pudo extraer.",
    )
    document_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Número/referencia de documento",
        help_text="Número de expediente, póliza, certificado, etc. "
                  "extraído del contenido, cuando el documento tiene "
                  "uno reconocible.",
    )
    issuing_entity = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Entidad emisora",
        help_text="Organismo o empresa que emite el documento (ej. "
                  "aseguradora, OCA, Junta de Andalucía), cuando se "
                  "identifica en el contenido.",
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        verbose_name="Inicio de periodo",
        help_text="Inicio del periodo de cobro/cobertura extraído del "
                  "contenido (ej. pagos trimestrales de seguro, periodo "
                  "de cobertura de una póliza) -- distinto de "
                  "issue_date/expiry_date, que son fecha de emisión y "
                  "fecha de caducidad del documento en sí. Nulo si el "
                  "documento no tiene periodo de cobro/cobertura.",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fin de periodo",
        help_text="Fin del periodo de cobro/cobertura extraído del "
                  "contenido. Nulo si el documento no tiene periodo de "
                  "cobro/cobertura.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Importe",
        help_text="Importe en euros extraído del contenido (ej. prima "
                  "de un periodo de seguro), cuando el documento lleva "
                  "una cantidad monetaria reconocible. Nulo si no "
                  "aplica o no se pudo extraer.",
    )
    extra_data = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        verbose_name="Metadatos adicionales",
        help_text="Diseño híbrido acordado con Miguel Ángel (S021): los "
                  "campos de fecha/importe que se repiten entre varios "
                  "tipos de documento tienen columna propia con tipo "
                  "real (expiry_date, issue_date, period_start, "
                  "period_end, amount) para poder ordenar/filtrar por "
                  "SQL sin trucos; este campo JSON es exclusivamente "
                  "para lo genuinamente impredecible por tipo de "
                  "documento -- pensado sobre todo para cuando H23 se "
                  "extienda a documentación de personal (cursos, "
                  "certificados, etc.), donde cada tipo puede tener una "
                  "forma completamente distinta. Gemini decide qué "
                  "claves rellenar según lo que detecte, sin lista "
                  "cerrada, mismo espíritu que document_type libre. "
                  "Vacío ({}) por defecto.",
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
    # Persistencia en Google Cloud Storage (S022) -- ver
    # spare_parts.gcs_service.MACHINE_DOCUMENTS_BUCKET. Los documentos
    # ya subidos a Drive en esta app son de prueba (S017) y se borran,
    # no se migran -- decisión explícita de Miguel Ángel en S022 (ver
    # anexo H23 sección 5). drive_file_id/drive_web_link quedan como
    # campos legado por coherencia con los otros dos modelos.
    gcs_blob_name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Ruta del objeto en Google Cloud Storage",
    )

    # ------------------------------------------------------------------
    # Local staging file / Archivo local de staging
    # Same pattern as work_order_processor.TaskPhoto.image and
    # spare_parts.DeliveryNote.pdf_file: the local file is DELETED by
    # the Celery task once the Drive upload succeeds (mirrors
    # work_order_processor.tasks.upload_task_photo_to_drive /
    # spare_parts.tasks.upload_delivery_note_photo_to_drive exactly) --
    # kept only when the Drive upload hasn't happened yet or failed, so
    # nothing is lost and a manual retry stays possible.
    # ---
    # Mismo patrón que work_order_processor.TaskPhoto.image y
    # spare_parts.DeliveryNote.pdf_file: el archivo local se BORRA
    # desde la tarea Celery en cuanto la subida a Drive tiene éxito
    # (replica exactamente
    # work_order_processor.tasks.upload_task_photo_to_drive /
    # spare_parts.tasks.upload_delivery_note_photo_to_drive) -- se
    # conserva solo mientras la subida a Drive no se ha hecho todavía o
    # ha fallado, para no perder nada y poder reintentar a mano.
    # ------------------------------------------------------------------
    source_file = models.FileField(
        upload_to="machine_documents/%Y/%m/",
        blank=True,
        verbose_name="Archivo",
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
        return f"{self.display_name or '(pendiente)'} — {self.machine_asset}"
