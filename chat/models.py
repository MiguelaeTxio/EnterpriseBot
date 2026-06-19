# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/models.py
"""
Data models for the chat module of EnterpriseBot.
Defines the entity graph for IRC-style section chat rooms:
ChatRoom, ChatMessage, BreakdownTicket, BreakdownConversationTurn.
All entities are scoped to a Company. ChatRoom instances are created
idempotently via the init_chat_rooms management command, and also
automatically via the post_save signal on Section (chat/signals.py).

BreakdownTicket lifecycle (Hito 14 redesign):
  OPEN → IN_PROGRESS (operario asignado) → CLOSED
  OPEN/IN_PROGRESS → PAUSED (operario reasignado a otro ticket)
  ticket_date_code: YYYYMMDD-NN (diario por empresa, ej. 20260618-01)
  origin: MANUAL (panel) | CHATBOT (agente Gemini WhatsApp)
---
Modelos de datos para el módulo de chat de EnterpriseBot.
Define el grafo de entidades para las salas de chat IRC por sección:
ChatRoom, ChatMessage, BreakdownTicket, BreakdownConversationTurn.
Todas las entidades pertenecen a una Company. Las instancias de ChatRoom
se crean de forma idempotente mediante el comando init_chat_rooms, y también
de forma automática mediante la signal post_save sobre Section (chat/signals.py).

Ciclo de vida BreakdownTicket (rediseño Hito 14):
  OPEN → IN_PROGRESS (operario asignado) → CLOSED
  OPEN/IN_PROGRESS → PAUSED (operario reasignado a otro ticket)
  ticket_date_code: YYYYMMDD-NN (diario por empresa, ej. 20260618-01)
  origin: MANUAL (panel) | CHATBOT (agente Gemini WhatsApp)
"""

from django.db import models
from django.utils import timezone

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
    Represents a breakdown ticket created either manually from the panel or
    automatically by the Gemini WhatsApp agent via the BREAKDOWNS room.

    Status lifecycle (Hito 14 redesign):
      OPEN        — ticket created, no operator assigned.
      IN_PROGRESS — operator assigned; ticket is an active repair order (OT).
      PAUSED      — operator was reassigned to another ticket; awaiting a new one.
      CLOSED      — work finished; resolved_by and resolved_at are set.

    ticket_date_code: human-readable identifier YYYYMMDD-NN, daily sequential
    per company (e.g. 20260618-01). Assigned automatically on first save().

    origin: MANUAL (panel creation) | CHATBOT (Gemini WhatsApp agent).

    BreakdownTickets are never automatically purged.
    ---
    Representa un ticket de avería creado manualmente desde el panel o
    automáticamente por el agente Gemini de WhatsApp a través de la sala
    BREAKDOWNS.

    Ciclo de vida del estado (rediseño Hito 14):
      OPEN        — ticket creado, sin operario asignado.
      IN_PROGRESS — operario asignado; el ticket es una OT activa.
      PAUSED      — el operario fue reasignado a otro ticket; espera uno nuevo.
      CLOSED      — trabajo finalizado; resolved_by y resolved_at asignados.

    ticket_date_code: identificador legible YYYYMMDD-NN, secuencial diario
    por empresa (ej. 20260618-01). Se asigna automáticamente en el primer save().

    origin: MANUAL (creación desde panel) | CHATBOT (agente Gemini WhatsApp).

    Los BreakdownTicket nunca se eliminan automáticamente.
    """

    # --- Status choices ---------------------------------------------------
    STATUS_OPEN        = "OPEN"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_PAUSED      = "PAUSED"
    STATUS_CLOSED      = "CLOSED"
    STATUS_CHOICES     = [
        (STATUS_OPEN,        "Abierto"),
        (STATUS_IN_PROGRESS, "En curso"),
        (STATUS_PAUSED,      "Pausado"),
        (STATUS_CLOSED,      "Cerrado"),
    ]

    # --- Urgency choices --------------------------------------------------
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

    # --- Origin choices ---------------------------------------------------
    ORIGIN_MANUAL  = "MANUAL"
    ORIGIN_CHATBOT = "CHATBOT"
    ORIGIN_IVR     = "IVR"
    ORIGIN_CHOICES = [
        (ORIGIN_MANUAL,  "Manual"),
        (ORIGIN_CHATBOT, "Chatbot"),
        (ORIGIN_IVR,     "IVR (llamada de voz)"),
    ]

    # --- ticket_date_code: YYYYMMDD-NN daily sequential per company. ------
    # Assigned automatically in save() when blank, using the count of tickets
    # already created today for this company to build the ordinal (01-99).
    ticket_date_code = models.CharField(
        max_length=11,
        blank=True,
        default="",
        verbose_name="Código de ticket",
        help_text=(
            "Identificador legible del ticket: YYYYMMDD-NN. "
            "Secuencial diario por empresa. Se asigna automáticamente "
            "en el primer save()."
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
    reported_by = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_breakdown_tickets",
        verbose_name="Detectado por",
        help_text=(
            "Contacto que detectó la avería. Puede diferir del contacto "
            "que abrió el ticket (ej. chofer que llama vs. jefe de taller)."
        ),
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
            "MachineAsset resuelto a partir de machine_raw. "
            "Null hasta que se identifica la máquina en el catálogo."
        ),
    )
    origin = models.CharField(
        max_length=8,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_MANUAL,
        verbose_name="Origen",
        help_text="Indica si el ticket fue creado manualmente o por el chatbot.",
    )
    fault_category = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Categoría de avería",
        help_text=(
            "Categoría principal de la avería. Usa los mismos códigos que "
            "FaultCategory en work_order_processor (ej. HYDRAULIC, ELECTRICAL_ELECTRONIC)."
        ),
    )
    photos = models.JSONField(
        default=list,
        verbose_name="Fotos adjuntas",
        help_text=(
            "Lista de rutas o URLs de las fotos adjuntas enviadas por el "
            "contacto durante el diálogo. El agente Gemini acepta hasta 3 "
            "imágenes vía WhatsApp Media."
        ),
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        verbose_name="Estado",
        help_text=(
            "Estado actual del ticket. "
            "Ciclo: OPEN → IN_PROGRESS → CLOSED | OPEN/IN_PROGRESS → PAUSED."
        ),
    )
    machine_raw = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Máquina / Vehículo",
        help_text=(
            "Identificación de la máquina o vehículo afectado tal como "
            "la describe el contacto o el agente."
        ),
    )
    fault_summary = models.TextField(
        blank=True,
        default="",
        verbose_name="Resumen de la avería",
        help_text="Descripción de la avería recogida mediante diálogo o entrada manual.",
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
        help_text="Nivel de urgencia.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas adicionales",
        help_text="Observaciones adicionales recogidas durante el diálogo o la gestión.",
    )
    assigned_to = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_breakdown_tickets",
        verbose_name="Asignado a",
        help_text=(
            "Operario de taller (WORKSHOPBOSS) al que se ha asignado este ticket. "
            "Null cuando el ticket está disponible para asignar."
        ),
    )
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de pausa",
        help_text=(
            "Timestamp en que el ticket pasó a estado PAUSED por "
            "reasignación del operario a otro ticket."
        ),
    )
    resolved_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_breakdown_tickets",
        verbose_name="Cerrado por",
        help_text="Usuario del panel que cerró el ticket.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de cierre",
        help_text="Timestamp en que se marcó el ticket como CLOSED.",
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

    def save(self, *args, **kwargs):
        """
        Assigns ticket_date_code on first save if not already set.
        Format: YYYYMMDD-NN — daily sequential per company (01-99).
        ---
        Asigna ticket_date_code en el primer save si no está asignado.
        Formato: YYYYMMDD-NN — secuencial diario por empresa (01-99).
        """
        if not self.ticket_date_code:
            today = timezone.localdate()
            date_str = today.strftime("%Y%m%d")
            company = self.room.company if self.room_id else None
            if company:
                existing = BreakdownTicket.objects.filter(
                    room__company=company,
                    ticket_date_code__startswith=date_str,
                ).count()
                ordinal = existing + 1
            else:
                ordinal = 1
            self.ticket_date_code = f"{date_str}-{ordinal:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        code = self.ticket_date_code or f"pk:{self.pk}"
        return (
            f"[{code}] [{self.get_status_display()}] "
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

