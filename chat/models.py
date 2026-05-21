# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/models.py
"""
Data models for the chat module of EnterpriseBot.
Defines the entity graph for IRC-style section chat rooms:
ChatRoom, ChatMessage, BreakdownTicket, BreakdownConversationTurn.
All entities are scoped to a Company. ChatRoom instances are created
idempotently via the init_chat_rooms management command, and also
automatically via the post_save signal on Section (chat/signals.py).
---
Modelos de datos para el módulo de chat de EnterpriseBot.
Define el grafo de entidades para las salas de chat IRC por sección:
ChatRoom, ChatMessage, BreakdownTicket, BreakdownConversationTurn.
Todas las entidades pertenecen a una Company. Las instancias de ChatRoom
se crean de forma idempotente mediante el comando init_chat_rooms, y también
de forma automática mediante la signal post_save sobre Section (chat/signals.py).
"""

from django.db import models

from ivr_config.models import Company, CompanyUser, Contact, Section


class ChatRoom(models.Model):
    """
    Represents a chat room scoped to a company.
    Room types:
      SECTION    — one room per active Section; relays WhatsApp messages from
                   contacts assigned to that section.
      BREAKDOWNS — one special room per company; routes messages to the
                   Gemini conversational agent that collects breakdown data.
    Invariant: a company has exactly one ChatRoom per active Section plus
    exactly one ChatRoom of type BREAKDOWNS.
    ---
    Representa una sala de chat perteneciente a una empresa.
    Tipos de sala:
      SECTION    — una sala por cada Section activa; replica mensajes WhatsApp
                   de los contactos asignados a esa sección.
      BREAKDOWNS — una sala especial por empresa; enruta los mensajes al agente
                   conversacional Gemini que recoge los datos de la avería.
    Invariante: una empresa tiene exactamente una ChatRoom por Section activa
    más exactamente una ChatRoom de tipo BREAKDOWNS.
    """

    ROOM_TYPE_SECTION    = "SECTION"
    ROOM_TYPE_BREAKDOWNS = "BREAKDOWNS"
    ROOM_TYPE_CHOICES    = [
        (ROOM_TYPE_SECTION,    "Sección"),
        (ROOM_TYPE_BREAKDOWNS, "Averías"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="chat_rooms",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece esta sala de chat.",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_rooms",
        verbose_name="Sección",
        help_text="Sección asociada a esta sala. Nulo únicamente para salas de tipo BREAKDOWNS.",
    )
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPE_CHOICES,
        verbose_name="Tipo de sala",
        help_text=(
            "SECTION: sala de difusión de mensajes WhatsApp de una sección. "
            "BREAKDOWNS: sala especial de recogida de averías con agente Gemini."
        ),
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Nombre",
        help_text="Nombre legible de la sala mostrado en el panel.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si la sala está operativa y visible en el panel.",
    )
    # --- Breakdown membership — Paso 12. ---
    # --- Membresía de la sala BREAKDOWNS — Paso 12. ---
    breakdown_sections = models.ManyToManyField(
        "ivr_config.Section",
        blank=True,
        related_name="breakdown_rooms",
        verbose_name="Secciones con acceso a Averías",
        help_text=(
            "Secciones cuyos miembros tienen acceso a esta sala BREAKDOWNS. "
            "Al añadir una sección, todos sus contactos quedan elegibles para "
            "enviar mensajes a la sala de averías. "
            "Solo aplica a salas de tipo BREAKDOWNS."
        ),
    )
    breakdown_contacts = models.ManyToManyField(
        "ivr_config.Contact",
        blank=True,
        related_name="breakdown_rooms",
        verbose_name="Contactos individuales con acceso a Averías",
        help_text=(
            "Contactos individuales adicionales con acceso directo a esta sala "
            "BREAKDOWNS, independientemente de su sección. "
            "Solo aplica a salas de tipo BREAKDOWNS."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Sala de chat"
        verbose_name_plural = "Salas de chat"
        ordering = ["company__name", "room_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(room_type="BREAKDOWNS"),
                name="unique_breakdowns_room_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "section"],
                condition=models.Q(room_type="SECTION"),
                name="unique_section_room_per_company_section",
            ),
        ]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


class ChatMessage(models.Model):
    """
    Represents a single message posted in a ChatRoom.
    Direction:
      INBOUND  — message received from a WhatsApp contact (external).
      OUTBOUND — message sent from the panel by a CompanyUser (internal).
    TTL policy: messages older than 7 days are purged by the Celery periodic
    task purge_old_chat_messages. BreakdownTickets are NOT purged.
    ---
    Representa un mensaje individual publicado en una ChatRoom.
    Dirección:
      INBOUND  — mensaje recibido de un contacto de WhatsApp (externo).
      OUTBOUND — mensaje enviado desde el panel por un CompanyUser (interno).
    Política TTL: los mensajes con más de 7 días son eliminados por la tarea
    Celery periódica purge_old_chat_messages. Los BreakdownTicket NO se eliminan.
    """

    DIRECTION_INBOUND  = "INBOUND"
    DIRECTION_OUTBOUND = "OUTBOUND"
    DIRECTION_CHOICES  = [
        (DIRECTION_INBOUND,  "Entrante"),
        (DIRECTION_OUTBOUND, "Saliente"),
    ]

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Sala",
        help_text="Sala de chat a la que pertenece este mensaje.",
    )
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        verbose_name="Dirección",
        help_text="INBOUND: mensaje entrante de WhatsApp. OUTBOUND: mensaje saliente desde el panel.",
    )
    sender_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages_sent",
        verbose_name="Contacto remitente",
        help_text="Contacto de WhatsApp origen del mensaje. Informado únicamente para mensajes INBOUND.",
    )
    sender_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages_sent",
        verbose_name="Usuario remitente",
        help_text="Usuario del panel que envió el mensaje. Informado únicamente para mensajes OUTBOUND.",
    )
    body = models.TextField(
        verbose_name="Contenido",
        help_text="Texto completo del mensaje.",
    )
    whatsapp_sid = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="SID de WhatsApp",
        help_text="SID del mensaje asignado por Twilio. Vacío para mensajes del agente Gemini.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Fecha de creación",
        help_text="Indexado para consultas de polling por rango de fechas.",
    )

    class Meta:
        verbose_name = "Mensaje de chat"
        verbose_name_plural = "Mensajes de chat"
        ordering = ["created_at"]

    def __str__(self):
        sender = (
            self.sender_contact.name
            if self.sender_contact
            else (self.sender_user.user.username if self.sender_user else "Sistema")
        )
        return f"[{self.room.name}] {self.get_direction_display()} — {sender}"


class BreakdownTicket(models.Model):
    """
    Represents a breakdown ticket created when a WhatsApp contact initiates
    a breakdown report via the BREAKDOWNS room.
    The Gemini conversational agent collects the required fields one by one
    via natural dialogue. The SUPERVISOR closes the ticket from the panel
    once the breakdown has been attended.
    Status lifecycle: OPEN → IN_PROGRESS → RESOLVED.
    BreakdownTickets are never automatically purged.
    ---
    Representa un ticket de avería creado cuando un contacto de WhatsApp inicia
    un reporte de avería a través de la sala BREAKDOWNS.
    El agente conversacional Gemini recoge los campos requeridos uno a uno
    mediante diálogo natural. El SUPERVISOR cierra el ticket desde el panel
    una vez atendida la avería.
    Ciclo de vida del estado: OPEN → IN_PROGRESS → RESOLVED.
    Los BreakdownTicket nunca se eliminan automáticamente.
    """

    STATUS_OPEN        = "OPEN"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_RESOLVED    = "RESOLVED"
    STATUS_CHOICES     = [
        (STATUS_OPEN,        "Abierto"),
        (STATUS_IN_PROGRESS, "En curso"),
        (STATUS_RESOLVED,    "Resuelto"),
    ]

    URGENCY_LOW      = "LOW"
    URGENCY_MEDIUM   = "MEDIUM"
    URGENCY_HIGH     = "HIGH"
    URGENCY_CRITICAL = "CRITICAL"
    URGENCY_CHOICES  = [
        (URGENCY_LOW,      "Baja"),
        (URGENCY_MEDIUM,   "Media"),
        (URGENCY_HIGH,     "Alta"),
        (URGENCY_CRITICAL, "Crítica"),
    ]

    # --- ticket_number: auto-incremental por empresa. ---
    # Se inicializa en save() si es None usando MAX(ticket_number)+1 dentro
    # de la empresa, o 1 si no existe ningún ticket previo.
    ticket_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Número de ticket",
        help_text=(
            "Número de ticket autoincremental por empresa. Se asigna "
            "automáticamente en el primer save() mediante MAX+1 dentro "
            "del scope de la empresa."
        ),
    )
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="breakdown_tickets",
        verbose_name="Sala",
        help_text="Sala BREAKDOWNS de la empresa a la que pertenece este ticket.",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="breakdown_tickets",
        verbose_name="Contacto",
        help_text="Contacto de WhatsApp que inició el reporte de avería.",
    )
    section = models.ForeignKey(
        "ivr_config.Section",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="breakdown_tickets",
        verbose_name="Sección",
        help_text=(
            "Sección del contacto en el momento de abrir el ticket. "
            "Se registra para trazabilidad aunque la membresía M2M pueda cambiar."
        ),
    )
    machine = models.ForeignKey(
        "fleet.MachineAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="breakdown_tickets",
        verbose_name="Máquina / Centro de gasto",
        help_text=(
            "MachineAsset resuelto por el agente Gemini a partir de machine_raw. "
            "Null hasta que el agente identifica la máquina en el catálogo."
        ),
    )
    is_repair_order = models.BooleanField(
        default=False,
        verbose_name="Convertido en orden de reparación",
        help_text=(
            "True cuando el SUPERVISOR ha pulsado 'Convertir en orden de "
            "reparación' desde la vista de detalle del ticket."
        ),
    )
    photos = models.JSONField(
        default=list,
        verbose_name="Fotos adjuntas",
        help_text=(
            "Lista de rutas o URLs de las fotos adjuntas enviadas por el "
            "contacto durante el diálogo de recogida de avería. "
            "El agente Gemini acepta hasta 3 imágenes vía WhatsApp Media."
        ),
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        verbose_name="Estado",
        help_text="Estado actual del ticket. Ciclo: OPEN → IN_PROGRESS → RESOLVED.",
    )
    machine_raw = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Máquina / Vehículo",
        help_text="Identificación de la máquina o vehículo afectado tal como la describe el contacto.",
    )
    fault_summary = models.TextField(
        blank=True,
        default="",
        verbose_name="Resumen de la avería",
        help_text="Descripción de la avería recogida por el agente Gemini mediante diálogo natural.",
    )
    location = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Ubicación",
        help_text="Ubicación actual del vehículo o lugar donde ocurrió la avería.",
    )
    urgency = models.CharField(
        max_length=10,
        choices=URGENCY_CHOICES,
        blank=True,
        default="",
        verbose_name="Urgencia",
        help_text="Nivel de urgencia. El agente Gemini sugiere y el contacto confirma.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas adicionales",
        help_text="Observaciones adicionales del operario recogidas durante el diálogo.",
    )
    assigned_to = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_breakdown_tickets",
        verbose_name="Asignado a",
        help_text=(
            "WORKSHOPBOSS al que se ha asignado este ticket para su atención. "
            "Null cuando el ticket está disponible para cualquier jefe de taller."
        ),
    )
    resolved_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_breakdown_tickets",
        verbose_name="Resuelto por",
        help_text="Usuario del panel (SUPERVISOR) que cerró el ticket.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de resolución",
        help_text="Timestamp en que el SUPERVISOR marcó el ticket como RESOLVED.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de modificación",
    )

    class Meta:
        verbose_name = "Ticket de avería"
        verbose_name_plural = "Tickets de avería"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"[{self.get_status_display()}] {self.contact.name} — "
            f"{self.machine_raw or 'Máquina no identificada'}"
        )


class BreakdownConversationTurn(models.Model):
    """
    Records each turn of the Gemini breakdown agent dialogue.
    The full conversation history is reconstructed from these turns on every
    call to the Gemini API (stateless — complete context per request).
    Role values mirror the Gemini API conventions:
      USER  — message sent by the WhatsApp contact.
      MODEL — response generated by the Gemini agent.
    TTL policy: turns belonging to tickets whose updated_at is older than
    7 days AND whose status is RESOLVED are purged by purge_old_chat_messages.
    The BreakdownTicket itself is never purged.
    ---
    Registra cada turno del diálogo del agente Gemini de averías.
    El historial completo de la conversación se reconstruye a partir de estos
    turnos en cada llamada a la API de Gemini (sin estado — contexto completo
    por petición).
    Los valores de rol siguen las convenciones de la API de Gemini:
      USER  — mensaje enviado por el contacto de WhatsApp.
      MODEL — respuesta generada por el agente Gemini.
    Política TTL: los turnos de tickets cuyo updated_at supere los 7 días Y
    cuyo estado sea RESOLVED son eliminados por purge_old_chat_messages.
    El BreakdownTicket en sí nunca se elimina.
    """

    ROLE_USER  = "USER"
    ROLE_MODEL = "MODEL"
    ROLE_CHOICES = [
        (ROLE_USER,  "Usuario"),
        (ROLE_MODEL, "Modelo"),
    ]

    ticket = models.ForeignKey(
        BreakdownTicket,
        on_delete=models.CASCADE,
        related_name="turns",
        verbose_name="Ticket de avería",
        help_text="Ticket de avería al que pertenece este turno de diálogo.",
    )
    role = models.CharField(
        max_length=5,
        choices=ROLE_CHOICES,
        verbose_name="Rol",
        help_text="USER: turno del contacto. MODEL: turno del agente Gemini.",
    )
    content = models.TextField(
        verbose_name="Contenido",
        help_text="Texto completo del turno de diálogo.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Turno de conversación de avería"
        verbose_name_plural = "Turnos de conversación de avería"
        ordering = ["ticket", "created_at"]

    def __str__(self):
        return f"[{self.ticket}] {self.get_role_display()} — {self.created_at:%Y-%m-%d %H:%M}"
