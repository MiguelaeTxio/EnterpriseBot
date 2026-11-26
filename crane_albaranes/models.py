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
    # S165: el planning real (una hoja por día) se carga por rango de
    # días y se actualiza sin duplicar.
    date_from = models.DateField(null=True, blank=True,
                                 verbose_name="Desde")
    date_to = models.DateField(null=True, blank=True,
                               verbose_name="Hasta")
    days_loaded = models.PositiveIntegerField(
        default=0, verbose_name="Días cargados")
    rows_updated = models.PositiveIntegerField(
        default=0, verbose_name="Servicios cambiados")
    rows_removed = models.PositiveIntegerField(
        default=0, verbose_name="Servicios quitados")

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


class PlanningName(models.Model):
    """
    How a worker is written in the planning (S165).

    ---

    Cómo viene escrito un trabajador en el planning o en el cuadrante de
    vacaciones («FCO GOMEZ RIVERO», «PETRUS», «DOCA»...) y quién es.
    Se asigna una vez en Tráfico › Nombres y vale para siempre; también
    se puede marcar que no es un trabajador («NUEVOS SERVICIOS»,
    «CUSTODIA», «ALQUILER»...).
    """

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="planning_names", verbose_name="Empresa",
    )
    key = models.CharField(max_length=120, verbose_name="Clave",
                           help_text="El texto sin tildes, mayúsculas ni "
                                     "signos.")
    text = models.CharField(max_length=120, verbose_name="Como viene")
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.CASCADE, related_name="planning_names",
        verbose_name="Trabajador",
    )
    not_a_worker = models.BooleanField(
        default=False, verbose_name="No es un trabajador")
    updated_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Asignado por",
    )
    updated_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Asignado")

    class Meta:
        ordering = ["text"]
        verbose_name = "Nombre del planning"
        verbose_name_plural = "Nombres del planning"
        constraints = [
            models.UniqueConstraint(fields=["company", "key"],
                                    name="planningname_unique_key"),
        ]

    def __str__(self):
        return self.text


class PlanningService(models.Model):
    """
    One row of the planning: a service of a day (S165).

    ---

    Una fila del planning de grúas (Excel de Carlos Núñez, una hoja por
    día): quién, con qué vehículo, para qué empresa, dónde, a qué hora y
    lo demás de la fila tal cual. Las filas que solo traen una nota
    (BAJA, vacaciones...) quedan como anotación y no se avisan. Al
    volver a cargar el planning, cada día se actualiza sin duplicar; si
    algo ya avisado cambia de hora o de lugar, queda marcado para
    reenviarlo.
    """

    KIND_SERVICE = "SERVICE"
    KIND_NOTE = "NOTE"
    KIND_CHOICES = [
        (KIND_SERVICE, "Servicio"),
        (KIND_NOTE, "Anotación"),
    ]

    class Notice(models.TextChoices):
        PENDING = "PENDING", "Sin enviar"
        SENT = "SENT", "Enviado"
        FAILED = "FAILED", "Envío fallido"

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="planning_services", verbose_name="Empresa",
    )
    planning = models.ForeignKey(
        PlanningImport, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="services", verbose_name="Carga del planning",
    )
    day = models.DateField(verbose_name="Fecha")
    position = models.PositiveSmallIntegerField(
        default=0, verbose_name="Fila")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES,
                            default=KIND_SERVICE, verbose_name="Tipo")
    raw_person = models.CharField(max_length=120, blank=True, default="",
                                  verbose_name="Personal (planning)")
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="planning_services",
        verbose_name="Gruista",
    )
    raw_vehicle = models.CharField(max_length=60, blank=True, default="",
                                   verbose_name="Vehículo (planning)")
    machine = models.ForeignKey(
        "fleet.MachineAsset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="planning_services",
        verbose_name="Vehículo",
    )
    tonnage = models.CharField(max_length=40, blank=True, default="",
                               verbose_name="Toneladas")
    raw_client = models.CharField(max_length=200, blank=True, default="",
                                  verbose_name="Empresa (planning)")
    client = models.ForeignKey(
        "worksites.Client", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="planning_services",
        verbose_name="Cliente",
    )
    raw_place = models.CharField(max_length=300, blank=True, default="",
                                 verbose_name="Lugar de trabajo")
    worksite = models.ForeignKey(
        "worksites.Worksite", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="planning_services",
        verbose_name="Obra",
    )
    raw_time = models.CharField(max_length=60, blank=True, default="",
                                verbose_name="Hora (planning)")
    planned_time = models.TimeField(null=True, blank=True,
                                    verbose_name="Hora")
    observations = models.TextField(blank=True, default="",
                                    verbose_name="Observaciones")
    price = models.CharField(max_length=200, blank=True, default="",
                             verbose_name="Precio")
    contracted_by = models.CharField(max_length=60, blank=True, default="",
                                     verbose_name="Contratado")
    offer_ref = models.CharField(max_length=60, blank=True, default="",
                                 verbose_name="Oferta económica")
    contact = models.CharField(max_length=200, blank=True, default="",
                               verbose_name="Contacto")
    albaran = models.ForeignKey(
        CraneAlbaran, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="planning_services", verbose_name="Albarán",
    )
    notice_status = models.CharField(
        max_length=8, choices=Notice.choices, default=Notice.PENDING,
        verbose_name="Aviso al gruista")
    notified_at = models.DateTimeField(null=True, blank=True,
                                       verbose_name="Avisado")
    notice_error = models.CharField(max_length=255, blank=True, default="",
                                    verbose_name="Fallo del aviso")
    changed_after_notice = models.BooleanField(
        default=False, verbose_name="Cambiado después del aviso")
    removed_from_planning = models.BooleanField(
        default=False, verbose_name="Quitado del planning")
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Modificado")

    class Meta:
        ordering = ["-day", "position"]
        verbose_name = "Servicio del planning"
        verbose_name_plural = "Servicios del planning"
        indexes = [
            models.Index(fields=["company", "day"],
                         name="planningservice_day"),
            models.Index(fields=["person", "day"],
                         name="planningservice_person_day"),
        ]

    def __str__(self):
        return "%s %s %s" % (self.day, self.raw_person, self.raw_place)


class PlanningNotice(models.Model):
    """
    One WhatsApp sent to a worker about a planned service (S165).

    ---

    Un WhatsApp enviado a un gruista por un servicio del planning: a
    quién, a qué móvil, qué se le dijo, si Twilio lo aceptó y, después,
    si le llegó y lo leyó (informe de entrega de Twilio).
    """

    STATUS_LABELS = {
        "": "", "accepted": "Aceptado", "queued": "En cola",
        "sending": "Enviándose", "sent": "Enviado",
        "delivered": "Entregado", "read": "Leído",
        "undelivered": "No entregado", "failed": "Fallido",
    }

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="planning_notices", verbose_name="Empresa",
    )
    service = models.ForeignKey(
        PlanningService, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notices", verbose_name="Servicio",
    )
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="planning_notices",
        verbose_name="Gruista",
    )
    day = models.DateField(verbose_name="Día del servicio")
    phone = models.CharField(max_length=40, blank=True, default="",
                             verbose_name="Móvil")
    text = models.TextField(blank=True, default="", verbose_name="Mensaje")
    ok = models.BooleanField(default=False, verbose_name="Aceptado")
    error = models.CharField(max_length=255, blank=True, default="",
                             verbose_name="Fallo")
    message_sid = models.CharField(max_length=64, blank=True, default="",
                                   verbose_name="Mensaje de Twilio")
    sent_as_text = models.BooleanField(
        default=False, verbose_name="Como texto libre")
    whatsapp_status = models.CharField(
        max_length=12, blank=True, default="",
        verbose_name="Estado del WhatsApp")
    whatsapp_status_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Estado a las")
    sent_by = models.ForeignKey(
        "ivr_config.CompanyUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Enviado por",
    )
    sent_at = models.DateTimeField(auto_now_add=True,
                                   verbose_name="Enviado")

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Envío a un gruista"
        verbose_name_plural = "Envíos a los gruistas"

    def __str__(self):
        return "%s %s" % (self.phone, self.sent_at)

    @property
    def status_label(self):
        """
        Twilio status in Spanish.
        ---
        Estado de Twilio en castellano.
        """
        return self.STATUS_LABELS.get(self.whatsapp_status,
                                      self.whatsapp_status)


class PlanningAlias(models.Model):
    """
    Another way the planning writes a client or a worksite (S165).

    ---

    Otra forma en que el planning escribe un cliente («VOTORAMTIN») o una
    obra. Se guarda al unir duplicados en Tráfico (Clientes u Obras):
    así la siguiente carga del planning no vuelve a dar de alta la
    errata.
    """

    KIND_CLIENT = "CLIENT"
    KIND_WORKSITE = "WORKSITE"
    KIND_CHOICES = [
        (KIND_CLIENT, "Cliente"),
        (KIND_WORKSITE, "Obra"),
    ]

    company = models.ForeignKey(
        "ivr_config.Company", on_delete=models.CASCADE,
        related_name="planning_aliases", verbose_name="Empresa",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES,
                            verbose_name="Tipo")
    key = models.CharField(
        max_length=320, verbose_name="Clave",
        help_text="Cliente: su nombre sin tildes ni signos. Obra: el "
                  "cliente y el lugar («12|nave antequera»).")
    client = models.ForeignKey(
        "worksites.Client", null=True, blank=True,
        on_delete=models.CASCADE, related_name="planning_aliases",
        verbose_name="Cliente",
    )
    worksite = models.ForeignKey(
        "worksites.Worksite", null=True, blank=True,
        on_delete=models.CASCADE, related_name="planning_aliases",
        verbose_name="Obra",
    )
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Creado")

    class Meta:
        verbose_name = "Alias del planning"
        verbose_name_plural = "Alias del planning"
        constraints = [
            models.UniqueConstraint(fields=["company", "kind", "key"],
                                    name="planningalias_unique_key"),
        ]

    def __str__(self):
        return self.key
