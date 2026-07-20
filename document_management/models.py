# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/models.py
"""
Hito 26 -- Infraestructura Documental Compartida. Servicio transversal
consumido por H23 (machine_documents, ya construido) y H25
(documentación de personal, todavía sin construir) -- ver
ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md. Esta app NUNCA importa
modelos de machine_documents ni de la futura app de H25: la relación
con el documento concreto es genérica (ContentType), para que ningún
dominio duplique esta lógica (mismo principio DRY que motivó el hito,
ver anexo H26 sección 1).

Esta app no construye ninguna interfaz de usuario todavía -- las
interfaces de H23/H25 son las que llaman a estos modelos y a los
servicios de este paquete.

---

Hito 26 -- Shared Document Infrastructure. Cross-domain service
consumed by H23 (machine_documents, already built) and H25 (personnel
documentation, not built yet) -- see
ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md. This app NEVER imports models
from machine_documents nor from the future H25 app: the relation to
the concrete document is generic (ContentType), so no domain app
duplicates this logic (same DRY principle that motivated the
milestone, see H26 annex section 1).

This app builds no user interface yet -- the H23/H25 interfaces are
the ones that call into these models and this package's services.
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from ivr_config.models import Company, CompanyUser


class EmailTemplate(models.Model):
    """
    Reusable, editable email text (subject + body) offered by the panel
    as copy-paste text when a user wants to send documentation by
    email. Editable via Django admin by whoever handles documentation
    -- explicit instruction from Miguel Angel (S023): "cualquier cosa
    generica y modificable desde la misma aplicacion, luego que lo
    rellene la persona encargada de documentacion". This app NEVER
    sends email itself -- no SMTP/API integration, explicitly out of
    scope (H26 annex section 2.3).

    ---

    Texto de email reutilizable y editable (asunto + cuerpo) que el
    panel ofrece como texto para copiar y pegar cuando un usuario
    quiere enviar documentacion por correo. Editable desde el admin de
    Django por quien se encargue de documentacion -- instruccion
    explicita de Miguel Angel (S023): "cualquier cosa generica y
    modificable desde la misma aplicacion, luego que lo rellene la
    persona encargada de documentacion". Esta app NUNCA envia el email
    ella misma -- sin integracion SMTP/API, fuera de alcance explicito
    (anexo H26 seccion 2.3).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="email_templates",
        verbose_name="Empresa",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Nombre interno de la plantilla",
        help_text=(
            "Identificador legible para elegirla en el panel, ej. "
            "'Envio de documentacion a organismo'."
        ),
    )
    subject = models.CharField(
        max_length=255,
        verbose_name="Asunto",
    )
    body = models.TextField(
        verbose_name="Cuerpo del mensaje",
        help_text=(
            "Texto generico para copiar y pegar en el cliente de "
            "correo del usuario, junto con el PDF generado aparte."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creacion",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Ultima modificacion",
    )

    class Meta:
        verbose_name = "Plantilla de email"
        verbose_name_plural = "Plantillas de email"

    def __str__(self) -> str:
        return self.name


class DocumentAlert(models.Model):
    """
    Tracks one expiry alert for a document belonging to any domain app
    (H23 MachineDocument today, H25 personnel documents later) via a
    generic relation. Fields per Miguel Angel's exact spec (S023):
    which document, expiry date, when to alert, contact(s) to notify,
    and resolution tracking.

    ---

    Registra una alerta de caducidad para un documento de cualquier
    app de dominio (H23 MachineDocument hoy, documentacion de personal
    de H25 mas adelante) via relacion generica. Campos segun la
    especificacion literal de Miguel Angel (S023): que documento,
    fecha de caducidad, cuando avisar, contacto(s) a los que avisar, y
    seguimiento de resolucion.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SENT = "SENT", "Enviada"
        RESOLVED = "RESOLVED", "Resuelta"

    # ------------------------------------------------------------
    # Genericamente vinculado al documento real (MachineDocument hoy,
    # el modelo de H25 manana) -- nunca un FK directo a un modelo de
    # dominio concreto.
    # ------------------------------------------------------------
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Tipo de documento",
    )
    object_id = models.PositiveBigIntegerField(
        verbose_name="ID del documento",
    )
    document = GenericForeignKey("content_type", "object_id")

    # ------------------------------------------------------------
    # Campos denormalizados de texto legible -- rellenados por quien
    # crea la alerta (H23/H25), NUNCA calculados aqui a partir del
    # objeto generico. Evita que este modulo tenga que conocer los
    # campos internos de MachineDocument ni del futuro modelo de H25
    # (mismo principio DRY/desacoplo que motivo el hito).
    # ------------------------------------------------------------
    document_label = models.CharField(
        max_length=255,
        verbose_name="Nombre legible del documento",
        help_text="Ej. 'Certificado OCA 2025-2026'.",
    )
    subject_label = models.CharField(
        max_length=255,
        verbose_name="Nombre legible del sujeto",
        help_text=(
            "Ej. 'A-45 -- LIEBHERR LTM 1055' (maquina) hoy; nombre de "
            "trabajador cuando H25 lo consuma."
        ),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="document_alerts",
        verbose_name="Empresa",
    )

    expiry_date = models.DateField(
        verbose_name="Fecha de caducidad del documento",
    )
    alert_offset_days = models.PositiveIntegerField(
        default=30,
        verbose_name="Dias de antelacion para avisar",
        help_text=(
            "Cuantos dias antes de la fecha de caducidad se dispara "
            "la alerta."
        ),
    )
    contacts = models.ManyToManyField(
        CompanyUser,
        related_name="document_alerts",
        verbose_name="Contacto(s) a los que avisar",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Estado",
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de envio",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de resolucion",
    )
    resolved_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_alerts_resolved",
        verbose_name="Resuelta por",
    )
    resolution_notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Notas de resolucion",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creacion",
    )

    class Meta:
        verbose_name = "Alerta de documento"
        verbose_name_plural = "Alertas de documento"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"Alerta {self.get_status_display()} -- vence {self.expiry_date}"


class DocumentSubstitutionLog(models.Model):
    """
    Registro de trazabilidad de una sustitución de documento aplicada
    EN SILENCIO durante la subida (S025, corrige explícitamente el
    diseño original del anexo H26 sección 2.4 -- decisión de Miguel
    Angel: "no tiene sentido que salte [un dialogo]... se hace el
    cambio simplemente y no se avisa. Se sustituye un documento por
    otro y se deja el vigente [...] que quede registrado como en una
    especie de log visible").

    La sustitucion en si NUNCA la decide este modelo -- la calcula
    document_management.vigencia_service.evaluate_substitution() (logica
    pura, agnostica de dominio) a partir de las fechas de los
    documentos; esta tabla solo persiste el resultado para poder
    consultarlo despues. Alcance actual: solo centros de gasto
    (machine_documents/H23) -- personal (H25) queda pendiente hasta
    cerrar que tipos de documento participan en sustitucion (anexo H26
    seccion 3).

    Igual que DocumentAlert, vinculado genericamente (ContentType) a
    los dos documentos reales -- este modulo nunca importa
    MachineDocument ni el futuro modelo de H25.
    ---
    Traceability record of a document substitution applied SILENTLY
    during upload (S025) -- see H26 annex section 2.4 for the original
    (superseded) design and the S025 correction.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="document_substitution_logs",
        verbose_name="Empresa",
    )

    # ------------------------------------------------------------
    # Documento que queda vigente (gana la comparacion de fechas).
    # ------------------------------------------------------------
    superseding_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="Tipo del documento vigente",
    )
    superseding_object_id = models.PositiveBigIntegerField(
        verbose_name="ID del documento vigente",
    )
    superseding_document = GenericForeignKey(
        "superseding_content_type", "superseding_object_id",
    )
    superseding_label = models.CharField(
        max_length=255,
        verbose_name="Nombre legible del documento vigente",
    )

    # ------------------------------------------------------------
    # Documento que queda archivado (pierde la comparacion).
    # ------------------------------------------------------------
    superseded_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="Tipo del documento archivado",
    )
    superseded_object_id = models.PositiveBigIntegerField(
        verbose_name="ID del documento archivado",
    )
    superseded_document = GenericForeignKey(
        "superseded_content_type", "superseded_object_id",
    )
    superseded_label = models.CharField(
        max_length=255,
        verbose_name="Nombre legible del documento archivado",
    )

    subject_label = models.CharField(
        max_length=255,
        verbose_name="Nombre legible del sujeto",
        help_text="Ej. 'A-45 -- LIEBHERR LTM 1055' (maquina).",
    )
    document_type = models.CharField(
        max_length=100,
        verbose_name="Tipo de documento",
    )
    reasoning = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Motivo",
        help_text="Texto de vigencia_service.evaluate_substitution() "
                  "explicando por que prevalece uno u otro.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de la sustitucion",
    )

    class Meta:
        verbose_name = "Registro de sustitución de documento"
        verbose_name_plural = "Historial de sustituciones de documentos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.superseded_label} -> {self.superseding_label}"
