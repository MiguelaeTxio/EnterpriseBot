# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/worksites/models.py
"""
H31 (S115). Modelo de Obra -- ver worksites/apps.py y la deuda
técnica 4.23 del documento maestro para el contexto completo de por
qué se crea ya, con qué alcance, y qué queda deliberadamente para
más adelante (Cliente/Proveedor reales, facturación, DECA).

Decisión explícita de Miguel Ángel (S115): crear la tabla ya --
"la necesitamos ya, pero tenemos que tener previsto que se va a
enlazar con [...] y que va a crecer con el número de registros o de
campos" -- sin esperar al diseño completo de Cliente/Proveedor.

H11 (S162, sesión invasora): llega el Cliente real y la obra crece con
lo que piden los albaranes de trabajo de las grúas. Miguel Ángel: "cómo
se definen las obras por clientes, con su ubicación, su número, el
número de proyecto, etcétera".
"""
from django.db import models


class Client(models.Model):
    """
    A customer of the group's crane services (H11, S162).

    ---

    Cliente de los servicios de grúa del grupo (H11, S162). Recoge los
    "DATOS CLIENTE" del albarán de papel (cliente, N.I.F., domicilio,
    localidad, provincia, teléfono) y el correo al que se le envían los
    albaranes firmados.
    """

    name = models.CharField(max_length=200, verbose_name="Cliente")
    tax_id = models.CharField(
        max_length=20, blank=True, default="", verbose_name="N.I.F.",
    )
    address = models.CharField(
        max_length=300, blank=True, default="", verbose_name="Domicilio",
    )
    locality = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Localidad",
    )
    province = models.CharField(
        max_length=80, blank=True, default="", verbose_name="Provincia",
    )
    phone = models.CharField(
        max_length=40, blank=True, default="", verbose_name="Teléfono",
    )
    email = models.CharField(
        max_length=254, blank=True, default="",
        verbose_name="Correo para los albaranes",
        help_text="Uno o varios correos separados por comas. La obra "
                  "puede tener los suyos propios.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    notes = models.TextField(blank=True, default="", verbose_name="Notas")
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Fecha de alta")
    updated_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Última modificación")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Worksite(models.Model):
    """
    Represents a real construction/service site ("obra") to which
    circulars, delivery notes (albaranes) and, in the future,
    invoicing can be attached. Deliberately minimal today (name is
    the only field actually required) but designed to grow: `client_name`
    and `managing_company` are the seams where future Cliente/Proveedor
    models will attach without needing to redesign this table.

    ---

    Representa una obra real a la que se pueden ligar circulares,
    albaranes y, en el futuro, facturación. Deliberadamente mínimo
    hoy (solo `name` es realmente obligatorio) pero pensado para
    crecer: `client_name` y `managing_company` son las costuras por
    donde engancharán los futuros modelos Cliente/Proveedor sin tener
    que rediseñar esta tabla.

    H11 (S162): `client` (FK a Client), número de proyecto y de pedido,
    localidad y provincia, coordenadas (para el mapa y para cotejar los
    fichajes del gruista), persona de contacto, horas mínimas y cómo se
    entregan sus albaranes firmados (correo, WhatsApp o los dos).
    """

    DELIVERY_EMAIL = "EMAIL"
    DELIVERY_WHATSAPP = "WHATSAPP"
    DELIVERY_BOTH = "BOTH"
    DELIVERY_NONE = "NONE"
    DELIVERY_CHOICES = [
        (DELIVERY_EMAIL, "Por correo"),
        (DELIVERY_WHATSAPP, "Por WhatsApp"),
        (DELIVERY_BOTH, "Por correo y WhatsApp"),
        (DELIVERY_NONE, "No se envía"),
    ]

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre de la obra",
        help_text="Nombre identificativo de la obra, tal como se usará "
                  "en circulares y documentación.",
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Código interno",
        help_text=(
            "Autogenerado al crear la obra (formato OBRA-0001), nunca "
            "introducido a mano -- evita que cada persona invente su "
            "propio formato con el tiempo (0001, A01, Build 1...)."
        ),
    )
    client_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Cliente (texto libre)",
        help_text=(
            "Cliente para el que se ejecuta la obra / a quien se "
            "factura. Texto libre por ahora -- mismo patrón que "
            "PersonIdentity.employer_company antes de tener un modelo "
            "Cliente real: se sustituirá por FK cuando ese modelo exista."
        ),
    )
    managing_company = models.ForeignKey(
        "ivr_config.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worksites",
        verbose_name="Empresa del grupo que gestiona la obra",
        help_text="Empresa del grupo (Grúas Álvarez, Transgrual, etc.) "
                  "que gestiona esta obra.",
    )
    address = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Ubicación",
        help_text="Lugar donde se ejecuta la obra (dirección o "
                  "referencia libre).",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="False cuando la obra ha finalizado -- se conserva el "
                  "registro, no se borra.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Fecha de modificación")
    # H11 (S162).
    client = models.ForeignKey(
        Client,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="worksites",
        verbose_name="Cliente",
    )
    project_number = models.CharField(
        max_length=60, blank=True, default="",
        verbose_name="Nº de proyecto",
    )
    order_number = models.CharField(
        max_length=60, blank=True, default="",
        verbose_name="Nº de pedido",
        help_text="El que se pone en sus albaranes si el planning no "
                  "trae otro.",
    )
    locality = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Localidad",
    )
    province = models.CharField(
        max_length=80, blank=True, default="", verbose_name="Provincia",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud",
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud",
    )
    contact_name = models.CharField(
        max_length=120, blank=True, default="",
        verbose_name="Persona de contacto",
    )
    contact_phone = models.CharField(
        max_length=40, blank=True, default="",
        verbose_name="Teléfono de contacto",
    )
    min_hours = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        verbose_name="Horas mínimas",
        help_text="Mínimo de horas que se factura por servicio.",
    )
    delivery_channel = models.CharField(
        max_length=10, choices=DELIVERY_CHOICES, default=DELIVERY_EMAIL,
        verbose_name="Entrega del albarán firmado",
    )
    delivery_email = models.CharField(
        max_length=254, blank=True, default="",
        verbose_name="Correo de la obra",
        help_text="Uno o varios correos separados por comas; vacío, el "
                  "del cliente.",
    )
    delivery_whatsapp = models.CharField(
        max_length=40, blank=True, default="",
        verbose_name="WhatsApp de la obra",
        help_text="Móvil al que se envía el albarán firmado por WhatsApp; "
                  "vacío, el teléfono de contacto.",
    )

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def client_label(self):
        """
        Client name: the real client or the free text.
        ---
        Nombre del cliente: el real o, si no hay, el texto libre.
        """
        return self.client.name if self.client_id else self.client_name

    def emails(self):
        """
        Delivery e-mails of the site, else the client's.
        ---
        Correos de entrega de la obra o, si no tiene, los del cliente.
        """
        raw = self.delivery_email or (
            self.client.email if self.client_id else "")
        return [e.strip() for e in raw.replace(";", ",").split(",")
                if "@" in e]

    def whatsapp_phone(self):
        """
        Mobile for WhatsApp delivery.
        ---
        Móvil para la entrega por WhatsApp.
        """
        return self.delivery_whatsapp or self.contact_phone
