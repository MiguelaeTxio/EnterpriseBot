# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/models.py
"""
Data models for the whatsapp channel app.
Defines WhatsAppSession, WhatsAppMessage and WhatsAppTemplate — the three
entities that support the WhatsApp chatbot and presence webhook features.
All models integrate with the multicompany data model built in Hito 3
(ivr_config.Company, ivr_config.Contact, ivr_config.PresenceStatus,
ivr_config.Section).

Extensions added in Paso 18 (Hito 4, session 2026-04-16):
  - WhatsAppSession: geographic location fields (latitude, longitude,
    location_address, location_captured_at) and target section FK (target_section).
  - WhatsAppMessage: message type field (message_type) and coordinate fields
    (latitude, longitude) to store inbound location messages from WhatsApp.
---
Modelos de datos para la app del canal WhatsApp.
Define WhatsAppSession, WhatsAppMessage y WhatsAppTemplate — las tres
entidades que soportan el chatbot de WhatsApp y las funcionalidades del
webhook de presencia. Todos los modelos se integran con el modelo de datos
multiempresa construido en el Hito 3 (ivr_config.Company, ivr_config.Contact,
ivr_config.PresenceStatus, ivr_config.Section).

Extensiones añadidas en el Paso 18 (Hito 4, sesión 2026-04-16):
  - WhatsAppSession: campos de ubicación geográfica (latitude, longitude,
    location_address, location_captured_at) y FK de sección destino (target_section).
  - WhatsAppMessage: campo de tipo de mensaje (message_type) y campos de
    coordenadas (latitude, longitude) para almacenar mensajes de ubicación
    entrantes de WhatsApp.
"""

from django.db import models

from ivr_config.models import Company, Section


# ---------------------------------------------------------------------------
# 1. WHATSAPP SESSION — Conversation session between a user and a company.
#    Sesión de conversación entre un usuario y una empresa por WhatsApp.
# ---------------------------------------------------------------------------

class WhatsAppSession(models.Model):
    """
    Groups all messages exchanged between a specific phone number and a company
    within a single Meta 24-hour session window. A session is considered active
    while is_active=True. The Celery task expire_whatsapp_sessions deactivates
    sessions whose last_message_at is older than 24 hours.
    ---
    Agrupa todos los mensajes intercambiados entre un número de teléfono concreto
    y una empresa dentro de una única ventana de sesión Meta de 24 horas. Una
    sesión se considera activa mientras is_active=True. La tarea Celery
    expire_whatsapp_sessions desactiva las sesiones cuyo last_message_at sea
    anterior a 24 horas.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="whatsapp_sessions",
        verbose_name="Empresa",
        help_text="Empresa con la que se mantiene esta sesión de WhatsApp.",
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name="Número de teléfono",
        help_text=(
            "Número de teléfono del usuario en formato E.164 (p. ej. +34XXXXXXXXX). "
            "Identifica de forma única al interlocutor externo dentro de la empresa."
        ),
    )
    session_start = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Inicio de sesión",
        help_text="Fecha y hora de creación de la sesión.",
    )
    last_message_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último mensaje",
        help_text=(
            "Fecha y hora del último mensaje registrado en la sesión. "
            "Actualizado automáticamente en cada operación de guardado. "
            "La tarea expire_whatsapp_sessions usa este campo para determinar "
            "si la ventana de 24 horas de Meta ha expirado."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text=(
            "True mientras la ventana de sesión Meta de 24 horas esté abierta. "
            "La tarea Celery expire_whatsapp_sessions lo establece a False "
            "cuando last_message_at supera las 24 horas."
        ),
    )

    # ------------------------------------------------------------------
    # GEOGRAPHIC LOCATION FIELDS — Paso 18 (Hito 4, 2026-04-16)
    # Optional capture of the client's geographic position, received either
    # via a native WhatsApp location message (Latitude/Longitude fields in
    # the Twilio webhook POST) or via IVR DataCaptureSet. All fields are
    # optional — location capture is never mandatory.
    # ------------------------------------------------------------------
    # CAMPOS DE UBICACIÓN GEOGRÁFICA — Paso 18 (Hito 4, 2026-04-16)
    # Captura opcional de la posición geográfica del cliente, recibida bien
    # mediante un mensaje de ubicación nativo de WhatsApp (campos Latitude/
    # Longitude en el POST del webhook de Twilio) o mediante DataCaptureSet
    # del IVR. Todos los campos son opcionales — la captura nunca es obligatoria.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitud",
        help_text=(
            "Latitud geográfica del cliente en grados decimales. "
            "Se rellena cuando el cliente comparte su ubicación por WhatsApp "
            "o cuando el IVR captura la posición vía DataCaptureSet."
        ),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitud",
        help_text=(
            "Longitud geográfica del cliente en grados decimales. "
            "Se rellena conjuntamente con latitude cuando la ubicación está disponible."
        ),
    )
    location_address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Dirección formateada",
        help_text=(
            "Dirección postal legible asociada a las coordenadas de ubicación. "
            "Puede ser proporcionada por el propio mensaje de ubicación de WhatsApp "
            "o resolverse mediante Grounding with Google Maps (Paso 20)."
        ),
    )
    location_captured_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ubicación capturada en",
        help_text=(
            "Fecha y hora en que se registró la ubicación geográfica del cliente. "
            "Permite auditar el momento exacto de la captura dentro de la sesión."
        ),
    )

    # ------------------------------------------------------------------
    # TARGET SECTION FIELD — Paso 18 (Hito 4, 2026-04-16)
    # The section the client intends to reach, detected by the chatbot agent
    # during the conversation and updated as the intent becomes clear.
    # Used by Paso 21 to route the interaction to the correct department.
    # ------------------------------------------------------------------
    # CAMPO DE SECCIÓN DESTINO — Paso 18 (Hito 4, 2026-04-16)
    # Sección a la que el cliente desea ser dirigido, detectada por el agente
    # chatbot durante la conversación y actualizada a medida que la intención
    # se clarifica. Usada por el Paso 21 para enrutar la interacción al
    # departamento correcto.
    target_section = models.ForeignKey(
        Section,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="whatsapp_sessions",
        verbose_name="Sección destino",
        help_text=(
            "Sección de la empresa a la que el cliente desea ser derivado. "
            "El agente chatbot detecta esta intención durante la conversación "
            "y actualiza este campo. Null si la intención aún no ha sido "
            "identificada o si el cliente no ha especificado sección."
        ),
    )

    class Meta:
        verbose_name = "Sesión de WhatsApp"
        verbose_name_plural = "Sesiones de WhatsApp"
        ordering = ["-session_start"]
        # A phone number can only have one active session per company at a time.
        # Un número de teléfono solo puede tener una sesión activa por empresa.
        indexes = [
            models.Index(
                fields=["company", "phone_number", "is_active"],
                name="whatsapp_session_lookup_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.company.name} — {self.phone_number} "
            f"({'activa' if self.is_active else 'cerrada'})"
        )


# ---------------------------------------------------------------------------
# 2. WHATSAPP MESSAGE — Individual message within a session.
#    Mensaje individual dentro de una sesión de WhatsApp.
# ---------------------------------------------------------------------------

class WhatsAppMessage(models.Model):
    """
    Stores a single message — inbound or outbound — within a WhatsAppSession.
    The full ordered history of WhatsAppMessage records for a session is used
    to reconstruct the Gemini chat history on each webhook invocation, providing
    conversational context persistence across stateless HTTP requests.
    ---
    Almacena un único mensaje — entrante o saliente — dentro de una WhatsAppSession.
    El historial completo ordenado de registros WhatsAppMessage de una sesión se
    utiliza para reconstruir el historial de chat de Gemini en cada invocación
    del webhook, proporcionando persistencia de contexto conversacional a través
    de peticiones HTTP sin estado.
    """

    DIRECTION_IN  = "IN"
    DIRECTION_OUT = "OUT"
    DIRECTION_CHOICES = [
        (DIRECTION_IN,  "Entrante"),
        (DIRECTION_OUT, "Saliente"),
    ]

    session = models.ForeignKey(
        WhatsAppSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Sesión",
        help_text="Sesión de WhatsApp a la que pertenece este mensaje.",
    )
    direction = models.CharField(
        max_length=3,
        choices=DIRECTION_CHOICES,
        verbose_name="Dirección",
        help_text="IN: mensaje entrante del usuario. OUT: respuesta saliente del agente.",
    )
    body = models.TextField(
        verbose_name="Cuerpo",
        help_text="Contenido textual completo del mensaje.",
    )
    message_sid = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="SID de mensaje",
        help_text=(
            "SID de mensaje Twilio (SMxxxxxxxx). "
            "Presente en mensajes salientes confirmados por la API de Twilio. "
            "Vacío en mensajes entrantes."
        ),
    )
    content_sid = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="SID de contenido",
        help_text=(
            "SID del Content Template de Twilio (HXxxxxxxxx). "
            "Presente únicamente en mensajes salientes enviados mediante template. "
            "Vacío en mensajes de texto libre."
        ),
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Marca de tiempo",
        help_text="Fecha y hora de registro del mensaje en la base de datos.",
    )

    # ------------------------------------------------------------------
    # MESSAGE TYPE AND LOCATION FIELDS — Paso 18 (Hito 4, 2026-04-16)
    # WhatsApp supports multiple message types beyond plain text. The
    # message_type field classifies each message for correct processing.
    # For messages of type 'location', Twilio provides Latitude and Longitude
    # fields in the webhook POST; these are stored here and propagated to
    # the parent WhatsAppSession (latitude, longitude, location_captured_at).
    # ------------------------------------------------------------------
    # TIPO DE MENSAJE Y CAMPOS DE UBICACIÓN — Paso 18 (Hito 4, 2026-04-16)
    # WhatsApp soporta múltiples tipos de mensaje más allá del texto plano.
    # El campo message_type clasifica cada mensaje para su procesamiento correcto.
    # Para mensajes de tipo 'location', Twilio proporciona los campos Latitude
    # y Longitude en el POST del webhook; se almacenan aquí y se propagan a la
    # WhatsAppSession padre (latitude, longitude, location_captured_at).
    MESSAGE_TYPE_TEXT     = "text"
    MESSAGE_TYPE_LOCATION = "location"
    MESSAGE_TYPE_MEDIA    = "media"
    MESSAGE_TYPE_TEMPLATE = "template"

    MESSAGE_TYPE_CHOICES = [
        (MESSAGE_TYPE_TEXT,     "Texto"),
        (MESSAGE_TYPE_LOCATION, "Ubicación"),
        (MESSAGE_TYPE_MEDIA,    "Media"),
        (MESSAGE_TYPE_TEMPLATE, "Template"),
    ]

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        default=MESSAGE_TYPE_TEXT,
        verbose_name="Tipo de mensaje",
        help_text=(
            "Tipo de contenido del mensaje: "
            "text (texto libre o respuesta del agente), "
            "location (mensaje de ubicación nativo de WhatsApp), "
            "media (imagen, documento u otro adjunto), "
            "template (mensaje enviado mediante Content Template de Twilio)."
        ),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitud",
        help_text=(
            "Latitud geográfica contenida en el mensaje. "
            "Solo presente en mensajes de tipo 'location'. "
            "Twilio proporciona este valor en el campo Latitude del webhook POST."
        ),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitud",
        help_text=(
            "Longitud geográfica contenida en el mensaje. "
            "Solo presente en mensajes de tipo 'location'. "
            "Twilio proporciona este valor en el campo Longitude del webhook POST."
        ),
    )

    class Meta:
        verbose_name = "Mensaje de WhatsApp"
        verbose_name_plural = "Mensajes de WhatsApp"
        ordering = ["timestamp"]
        indexes = [
            models.Index(
                fields=["session", "timestamp"],
                name="whatsapp_message_history_idx",
            ),
        ]

    def __str__(self):
        direction_label = "→" if self.direction == self.DIRECTION_IN else "←"
        return (
            f"{self.session.company.name} {direction_label} "
            f"{self.session.phone_number} [{self.timestamp:%Y-%m-%d %H:%M}]"
        )


# ---------------------------------------------------------------------------
# 3. WHATSAPP TEMPLATE — Meta-approved message template registry.
#    Registro de plantillas de mensaje aprobadas por Meta.
# ---------------------------------------------------------------------------

class WhatsAppTemplate(models.Model):
    """
    Centralised registry of Meta-approved WhatsApp message templates available
    for a company. Templates are required for business-initiated messages sent
    outside the 24-hour session window, and for presence reminders sent by the
    check_in_meeting_reminders Celery task. The content_sid (HX...) is obtained
    from the Twilio Content Template Builder and seeded via the management
    command seed_whatsapp_templates.
    ---
    Registro centralizado de plantillas de mensaje WhatsApp aprobadas por Meta
    disponibles para una empresa. Las plantillas son obligatorias para mensajes
    iniciados por la empresa fuera de la ventana de sesión de 24 horas, y para
    los recordatorios de presencia enviados por la tarea Celery
    check_in_meeting_reminders. El content_sid (HX...) se obtiene del Content
    Template Builder de Twilio y se siembra mediante el comando de gestión
    seed_whatsapp_templates.
    """

    CATEGORY_UTILITY        = "UTILITY"
    CATEGORY_MARKETING      = "MARKETING"
    CATEGORY_AUTHENTICATION = "AUTHENTICATION"

    CATEGORY_CHOICES = [
        (CATEGORY_UTILITY,        "Utilidad"),
        (CATEGORY_MARKETING,      "Marketing"),
        (CATEGORY_AUTHENTICATION, "Autenticación"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="whatsapp_templates",
        verbose_name="Empresa",
        help_text="Empresa propietaria de esta plantilla de mensaje.",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text=(
            "Nombre identificativo de la plantilla (p. ej. presence_reminder). "
            "Usado internamente para seleccionar la plantilla correcta en el código."
        ),
    )
    content_sid = models.CharField(
        max_length=50,
        verbose_name="SID de contenido",
        help_text=(
            "SID del Content Template de Twilio en formato HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx. "
            "Obtenido del Content Template Builder del Console de Twilio tras la aprobación de Meta."
        ),
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name="Categoría",
        help_text=(
            "Categoría Meta de la plantilla: "
            "UTILITY (notificaciones de servicio), "
            "MARKETING (promociones), "
            "AUTHENTICATION (OTP y verificación)."
        ),
    )
    language = models.CharField(
        max_length=10,
        default="es",
        verbose_name="Idioma",
        help_text=(
            "Código de idioma BCP-47 de la plantilla (p. ej. 'es', 'en', 'ca'). "
            "Debe coincidir con el idioma registrado en el Console de Twilio."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text=(
            "True si la plantilla está disponible para su uso. "
            "Establecer a False para retirar una plantilla sin eliminar su registro."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Plantilla de WhatsApp"
        verbose_name_plural = "Plantillas de WhatsApp"
        ordering = ["company__name", "name"]
        constraints = [
            # Enforce uniqueness of (company, name) to prevent duplicate template
            # registrations for the same company under the same internal name.
            # Garantizar unicidad de (company, name) para evitar registros duplicados
            # de plantilla para la misma empresa bajo el mismo nombre interno.
            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_whatsapp_template_per_company",
            ),
        ]

    def __str__(self):
        return f"{self.company.name} — {self.name} [{self.category}]"
