# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/models.py
"""
Crane work delivery notes (H11, S162).

---

Albaranes de trabajo de las grúas (H11, S162, sesión invasora). Miguel
Ángel: "un pipeline para enviar el albarán relleno con el cliente, obra,
máquina y gruista, que lo enviamos por WhatsApp. Ese albarán le llega al
gruista, lo abre en su aplicación y él solamente tiene que rellenar [...]
o quedar rellenado con los fichajes del gruista". Dos orígenes: la
oficina (a mano o con el planning en Excel de Carlos Núñez) y el propio
gruista desde cero. Los campos son los del albarán de papel actual
(«PARTE DE PRODUCCIÓN» + «ALBARÁN»), leídos de los albaranes que carga
Juan para cotejar los fichajes (hr_calendar.AlbaranSheet).
"""
import secrets

from django.db import models


class PlanningImport(models.Model):
    """
    One planning Excel loaded by the office (H11, S162).

    ---

    Un Excel de planning cargado por la oficina (Carlos Núñez): dónde
    trabaja cada gruista, en qué obra y con qué máquina. Cada fila buena
    crea un albarán preparado.
    """

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="crane_plannings", verbose_name="Empresa",
    )
    file_name = models.CharField(max_length=255, verbose_name="Archivo")
    uploaded_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Cargado por",
    )
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Cargado")
    rows_total = models.PositiveIntegerField(default=0,
                                             verbose_name="Filas")
    rows_created = models.PositiveIntegerField(
        default=0, verbose_name="Albaranes creados")
    problems = models.JSONField(default=list, blank=True,
                                verbose_name="Filas con problemas")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Planning de grúas"
        verbose_name_plural = "Plannings de grúas"

    def __str__(self):
        return "%s (%s)" % (self.file_name, self.created_at)


def _new_token():
    return secrets.token_urlsafe(24)


class CraneAlbaran(models.Model):
    """
    A digital crane work delivery note (H11, S162).

    ---

    Albarán de trabajo digital de una grúa. La oficina lo prepara
    (cliente, obra, máquina, gruista, trabajo a realizar) y se lo envía
    por WhatsApp; el gruista lo abre en su aplicación de fichaje, las
    horas salen de sus fichajes del día, completa lo que falte, firma él
    y firma el cliente; entonces se genera el PDF, se guarda en el cubo
    (ALBARANES DE TRABAJO del trabajador) y se entrega al cliente por
    correo o WhatsApp, según la obra.
    """

    ORIGIN_OFFICE = "OFFICE"
    ORIGIN_PLANNING = "PLANNING"
    ORIGIN_WORKER = "WORKER"
    ORIGIN_CHOICES = [
        (ORIGIN_OFFICE, "Oficina"),
        (ORIGIN_PLANNING, "Planning"),
        (ORIGIN_WORKER, "Gruista"),
    ]

    class Status(models.TextChoices):
        PREPARED = "PREPARED", "Preparado"
        SENT = "SENT", "Enviado al gruista"
        SEND_FAILED = "SEND_FAILED", "Aviso fallido"
        OPENED = "OPENED", "Abierto por el gruista"
        SIGNED = "SIGNED", "Firmado"
        DELIVERED = "DELIVERED", "Entregado al cliente"
        DELIVERY_FAILED = "DELIVERY_FAILED", "Entrega fallida"
        CANCELLED = "CANCELLED", "Anulado"

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="crane_albaranes", verbose_name="Empresa",
    )
    number = models.CharField(
        max_length=20, verbose_name="Nº de albarán",
        help_text="Serie digital D000001, distinta de la numeración de "
                  "los talonarios de papel.",
    )
    issuer = models.ForeignKey(
        "document_explorer.CompanyFiscalProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Empresa emisora",
    )
    origin = models.CharField(max_length=10, choices=ORIGIN_CHOICES,
                              default=ORIGIN_OFFICE,
                              verbose_name="Origen")
    planning = models.ForeignKey(
        PlanningImport, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="albaranes", verbose_name="Planning",
    )
    status = models.CharField(max_length=16, choices=Status.choices,
                              default=Status.PREPARED,
                              verbose_name="Estado")
    day = models.DateField(verbose_name="Fecha")
    planned_time = models.TimeField(null=True, blank=True,
                                    verbose_name="Hora prevista")
    # Obra y cliente (los datos del cliente se copian al prepararlo, para
    # que el albarán firmado no cambie si luego se edita la ficha).
    worksite = models.ForeignKey(
        "worksites.Worksite", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crane_albaranes",
        verbose_name="Obra",
    )
    client = models.ForeignKey(
        "worksites.Client", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crane_albaranes",
        verbose_name="Cliente",
    )
    client_name = models.CharField(max_length=200, blank=True, default="",
                                   verbose_name="Cliente (en el albarán)")
    client_tax_id = models.CharField(max_length=20, blank=True, default="",
                                     verbose_name="N.I.F.")
    client_address = models.CharField(max_length=300, blank=True,
                                      default="", verbose_name="Domicilio")
    client_locality = models.CharField(max_length=120, blank=True,
                                       default="", verbose_name="Localidad")
    client_province = models.CharField(max_length=80, blank=True,
                                       default="", verbose_name="Provincia")
    client_phone = models.CharField(max_length=40, blank=True, default="",
                                    verbose_name="Teléfono")
    order_number = models.CharField(max_length=60, blank=True, default="",
                                    verbose_name="Nº de pedido")
    work_place = models.CharField(max_length=300, blank=True, default="",
                                  verbose_name="Lugar de trabajo")
    work_locality = models.CharField(max_length=120, blank=True,
                                     default="", verbose_name="Localidad")
    # Máquina y gruista.
    machine = models.ForeignKey(
        "fleet.MachineAsset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crane_albaranes",
        verbose_name="Máquina",
    )
    tonnage = models.CharField(max_length=20, blank=True, default="",
                               verbose_name="Toneladas")
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crane_albaranes",
        verbose_name="Gruista",
    )
    helpers = models.CharField(max_length=200, blank=True, default="",
                               verbose_name="Ayudantes")
    # Trabajo.
    task = models.TextField(blank=True, default="",
                            verbose_name="Trabajo a realizar",
                            help_text="Lo que indica la oficina.")
    work_done = models.TextField(blank=True, default="",
                                 verbose_name="Trabajo realizado")
    hours_worked = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Horas trabajadas")
    min_hours = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        verbose_name="Horas mínimas")
    trips = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Salidas / desplazamientos")
    km = models.PositiveIntegerField(null=True, blank=True,
                                     verbose_name="Kilómetros")
    # Parte de producción (horas del día).
    base_out = models.TimeField(null=True, blank=True,
                                verbose_name="Salida de base")
    work_in = models.TimeField(null=True, blank=True,
                               verbose_name="Llegada al trabajo")
    work_out = models.TimeField(null=True, blank=True,
                                verbose_name="Salida del trabajo")
    base_in = models.TimeField(null=True, blank=True,
                               verbose_name="Llegada a base")
    times_from_clock = models.BooleanField(
        default=False, verbose_name="Horas sacadas de los fichajes")
    vehicle_on_site = models.BooleanField(default=False,
                                          verbose_name="Vehículo en obra")
    continues_previous = models.BooleanField(
        default=False, verbose_name="Continuación del día anterior")
    observations = models.TextField(blank=True, default="",
                                    verbose_name="Observaciones")
    # Mercancía transportada (carga, descarga y propietaria).
    goods = models.JSONField(default=dict, blank=True,
                             verbose_name="Mercancía transportada")
    # Firmas.
    operator_signature = models.TextField(
        blank=True, default="", verbose_name="Firma del operario",
        help_text="Imagen PNG en data URL.")
    signer_name = models.CharField(max_length=120, blank=True, default="",
                                   verbose_name="Firma el cliente: nombre")
    signer_dni = models.CharField(max_length=20, blank=True, default="",
                                  verbose_name="Firma el cliente: D.N.I.")
    client_signature = models.TextField(
        blank=True, default="", verbose_name="Firma del cliente",
        help_text="Imagen PNG en data URL.")
    signed_at = models.DateTimeField(null=True, blank=True,
                                     verbose_name="Firmado")
    sign_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud de la firma")
    sign_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud de la firma")
    # Aviso al gruista.
    token = models.CharField(max_length=40, unique=True,
                             default=_new_token,
                             verbose_name="Llave del enlace")
    notified_at = models.DateTimeField(null=True, blank=True,
                                       verbose_name="Aviso enviado")
    notice_error = models.CharField(max_length=255, blank=True,
                                    default="", verbose_name="Fallo del "
                                    "aviso")
    opened_at = models.DateTimeField(null=True, blank=True,
                                     verbose_name="Abierto")
    # Documento y entrega al cliente.
    pdf_blob = models.CharField(max_length=500, blank=True, default="",
                                verbose_name="PDF en el cubo")
    delivery_channel = models.CharField(
        max_length=10, blank=True, default="",
        verbose_name="Entrega por")
    delivered_to = models.CharField(max_length=300, blank=True, default="",
                                    verbose_name="Entregado a")
    delivered_at = models.DateTimeField(null=True, blank=True,
                                        verbose_name="Entregado")
    delivery_error = models.CharField(max_length=255, blank=True,
                                      default="",
                                      verbose_name="Fallo de la entrega")
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Modificado")

    class Meta:
        ordering = ["-day", "-number"]
        verbose_name = "Albarán de grúa"
        verbose_name_plural = "Albaranes de grúas"
        constraints = [
            models.UniqueConstraint(fields=["company", "number"],
                                    name="cranealbaran_unique_number"),
        ]
        indexes = [
            models.Index(fields=["person", "day"],
                         name="cranealbaran_person_day"),
        ]

    def __str__(self):
        return "%s %s" % (self.number, self.day)

    @property
    def is_signed(self):
        """
        Whether the client already signed it.
        ---
        Si ya lo ha firmado el cliente (desde ahí no se edita).
        """
        return self.signed_at is not None

    @property
    def can_edit(self):
        """
        Editable until signed and not cancelled.
        ---
        Editable hasta que se firma, salvo anulado.
        """
        return (not self.is_signed
                and self.status != self.Status.CANCELLED)
