# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/models.py
"""
CAE platform notices read from the mails uploaded by the mail agent.

---

H31 (S156). Avisos de las plataformas CAE que llegan por correo.

- `CaeMail`: un aviso original (el .msg que Yolanda reenvía como
  adjunto, o el propio correo si llega sin adjunto), con lo que se ha
  leído de él.
- `CaeDemand`: cada cosa concreta que pide el aviso: un documento de la
  empresa, de un trabajador o de una máquina, con su estado y su fecha.
  Un aviso que solo da un recuento o un enlace no tiene demandas.
"""
from django.conf import settings
from django.db import models


class CaeMail(models.Model):
    """
    One original CAE notice and what was read from it.

    ---

    Un aviso original de una plataforma CAE y lo leído de él.
    """

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSED = "PROCESSED"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En cola"),
        (STATUS_PROCESSED, "Leído"),
        (STATUS_ERROR, "Error"),
    ]

    key = models.CharField(
        max_length=64, unique=True, verbose_name="Huella",
    )
    source_prefix = models.CharField(
        max_length=255, db_index=True,
        verbose_name="Carpeta del correo en el cubo",
    )
    attachment_name = models.CharField(
        max_length=255, blank=True,
        verbose_name="Adjunto .msg (vacío si es el propio correo)",
    )
    forwarded_at = models.DateTimeField(
        verbose_name="Recibido en administración",
    )
    received_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha del aviso",
    )
    sender_name = models.CharField(
        max_length=255, blank=True, verbose_name="Remitente",
    )
    sender_address = models.CharField(
        max_length=255, blank=True, verbose_name="Dirección del remitente",
    )
    subject = models.CharField(
        max_length=500, blank=True, verbose_name="Asunto",
    )
    body_text = models.TextField(blank=True, verbose_name="Texto")
    platform = models.CharField(
        max_length=100, blank=True, verbose_name="Plataforma",
    )
    client = models.CharField(
        max_length=255, blank=True, verbose_name="Cliente",
    )
    our_company = models.CharField(
        max_length=255, blank=True, verbose_name="Empresa del grupo",
    )
    summary = models.TextField(blank=True, verbose_name="Resumen")
    has_detail = models.BooleanField(
        default=False,
        verbose_name="Dice qué documentos pide",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING,
        verbose_name="Estado",
    )
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    # Quien supervisa (Yolanda, o Juan en sus vacaciones) lo da por
    # atendido cuando ha subido a la plataforma lo que pedía.
    attended_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Atendido el",
    )
    attended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Atendido por",
    )

    class Meta:
        verbose_name = "Aviso CAE"
        verbose_name_plural = "Avisos CAE"
        ordering = ["-received_at", "-forwarded_at"]

    def __str__(self):
        return "%s — %s" % (self.platform or self.sender_address,
                            self.subject)


class CaeDemand(models.Model):
    """
    One concrete document a CAE notice asks for.

    ---

    Un documento concreto que pide un aviso CAE: de la empresa, de un
    trabajador o de una máquina, con su estado y su fecha.
    """

    SUBJECT_COMPANY = "EMPRESA"
    SUBJECT_WORKER = "TRABAJADOR"
    SUBJECT_MACHINE = "MAQUINA"
    SUBJECT_OTHER = "OTRO"
    SUBJECT_CHOICES = [
        (SUBJECT_COMPANY, "Empresa"),
        (SUBJECT_WORKER, "Trabajador"),
        (SUBJECT_MACHINE, "Máquina"),
        (SUBJECT_OTHER, "Otro"),
    ]

    mail = models.ForeignKey(
        CaeMail, on_delete=models.CASCADE, related_name="demands",
        verbose_name="Aviso",
    )
    subject_type = models.CharField(
        max_length=10, choices=SUBJECT_CHOICES, default=SUBJECT_OTHER,
        verbose_name="De quién",
    )
    subject_name = models.CharField(
        max_length=255, blank=True,
        verbose_name="Trabajador, máquina o empresa",
    )
    subject_ref = models.CharField(
        max_length=100, blank=True,
        verbose_name="DNI, matrícula o código",
    )
    document = models.CharField(max_length=500, verbose_name="Documento")
    state = models.CharField(
        max_length=255, blank=True, verbose_name="Estado en la plataforma",
    )
    due_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha límite o caducidad",
    )
    site = models.CharField(
        max_length=255, blank=True, verbose_name="Centro u obra",
    )
    # Lo que es en EnterpriseBot: tipo del catálogo (lo elige Gemini al
    # leer el aviso) y de quién es (lo enlaza el código por CIF/nombre,
    # DNI/nombre o matrícula/código). Vacíos si no se ha podido saber.
    document_type = models.ForeignKey(
        "document_explorer.DocumentTypeCatalog", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Tipo documental",
    )
    company = models.ForeignKey(
        "document_explorer.CompanyFiscalProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Empresa del grupo",
    )
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Trabajador",
    )
    machine = models.ForeignKey(
        "fleet.MachineAsset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Centro de gasto",
    )

    class Meta:
        verbose_name = "Documento pedido"
        verbose_name_plural = "Documentos pedidos"
        ordering = ["due_date", "subject_type", "subject_name"]

    def __str__(self):
        return "%s — %s" % (self.subject_name or self.subject_type,
                            self.document)
