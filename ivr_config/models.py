# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/models.py
"""
Data models for the ivr_config multicompany IVR configuration engine.
Defines the full entity graph: Company, CompanyUser, CorporateVoiceProfile,
DataCaptureSet, Section, Contact, CallFlow, PhoneNumber and PresenceStatus.
Creation order respects all FK dependencies to avoid circular references.
---
Modelos de datos para el motor de configuración IVR multiempresa ivr_config.
Define el grafo completo de entidades: Company, CompanyUser, CorporateVoiceProfile,
DataCaptureSet, Section, Contact, CallFlow, PhoneNumber y PresenceStatus.
El orden de creación respeta todas las dependencias FK para evitar referencias circulares.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils.timezone import now


# ---------------------------------------------------------------------------
# 1. COMPANY — Root entity of the multicompany system.
#    Entidad raíz del sistema multiempresa.
# ---------------------------------------------------------------------------

class Company(models.Model):
    """
    Represents a client company subscribing to the EnterpriseBot IVR platform.
    All IVR configuration data is scoped to a Company instance.
    ---
    Representa una empresa cliente suscrita a la plataforma IVR EnterpriseBot.
    Todos los datos de configuración IVR pertenecen a una instancia de Company.
    """

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text="Nombre comercial de la empresa cliente.",
    )
    slug = models.SlugField(
        unique=True,
        blank=True,
        verbose_name="Slug",
        help_text="Identificador URL único, generado automáticamente desde el nombre.",
    )
    logo = models.ImageField(
        upload_to="company_logos/",
        null=True,
        blank=True,
        verbose_name="Logotipo",
        help_text="Logotipo de la empresa en formato de imagen.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si la empresa está operativa en la plataforma.",
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
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Overrides save to auto-generate the slug from the company name
        if it has not been set manually.
        ---
        Sobreescribe save para generar automáticamente el slug desde el nombre
        de la empresa si no ha sido establecido manualmente.
        """
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# 2. COMPANY USER — Platform user bound to a specific company.
#    Usuario de plataforma vinculado a una empresa específica.
# ---------------------------------------------------------------------------

class CompanyUser(models.Model):
    """
    Links a Django auth.User to a Company with a defined role (ADMIN or OPERATOR).
    CompanyUser instances must never have is_staff=True on their linked User.
    Access to /admin/ is blocked via CompanyUserAdminBlockMiddleware.
    ---
    Vincula un auth.User de Django a una Company con un rol definido (ADMIN u OPERATOR).
    Las instancias de CompanyUser jamás deben tener is_staff=True en su User vinculado.
    El acceso a /admin/ se bloquea mediante CompanyUserAdminBlockMiddleware.
    """

    ROLE_ADMIN = "ADMIN"
    ROLE_OPERATOR = "OPERATOR"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrador"),
        (ROLE_OPERATOR, "Operador"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_users",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este usuario.",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="company_user",
        verbose_name="Usuario",
        help_text="Usuario de autenticación Django vinculado.",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_OPERATOR,
        verbose_name="Rol",
        help_text="ADMIN: acceso completo a la configuración de la empresa. OPERATOR: solo gestión de presencia propia.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si el usuario tiene acceso activo al panel.",
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
        verbose_name = "Usuario de empresa"
        verbose_name_plural = "Usuarios de empresa"
        ordering = ["company__name", "user__username"]

    def __str__(self):
        return f"{self.company.name} — {self.user.username}"


# ---------------------------------------------------------------------------
# 3. CORPORATE VOICE PROFILE — Brand voice identity for a company.
#    Identidad de voz corporativa de una empresa.
# ---------------------------------------------------------------------------

class CorporateVoiceProfile(models.Model):
    """
    Defines the brand voice identity of a company for IVR interactions.
    Tone guidelines, sample responses and forbidden phrases are injected
    into the Gemini Live system_instruction at call time.
    ---
    Define la identidad de voz de marca de una empresa para las interacciones IVR.
    Las directrices de tono, respuestas de ejemplo y frases prohibidas se inyectan
    en el system_instruction de Gemini Live en tiempo de llamada.
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="voice_profile",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este perfil de voz corporativa.",
    )
    tone_guidelines = models.TextField(
        verbose_name="Directrices de tono",
        help_text="Descripción del tono y estilo de comunicación esperado del agente IVR.",
    )
    sample_responses = models.JSONField(
        default=list,
        verbose_name="Respuestas de ejemplo",
        help_text="Lista de ejemplos de respuestas correctas para calibrar el tono del agente.",
    )
    forbidden_phrases = models.JSONField(
        default=list,
        verbose_name="Frases prohibidas",
        help_text="Lista de expresiones que el agente IVR debe evitar en todo momento.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si este perfil de voz está en uso.",
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
        verbose_name = "Perfil de voz corporativa"
        verbose_name_plural = "Perfiles de voz corporativa"

    def __str__(self):
        return f"{self.company.name} — Perfil de voz"


# ---------------------------------------------------------------------------
# 4. DATA CAPTURE SET — Set of data fields to collect during a call.
#    Conjunto de campos de datos a recopilar durante una llamada.
#    NOTE: Created before Section to avoid circular FK dependency.
#    NOTA: Creado antes que Section para evitar dependencia FK circular.
# ---------------------------------------------------------------------------

class DataCaptureSet(models.Model):
    """
    Defines the structured set of data fields the IVR agent must collect
    from the caller during a call for a given section or company.
    The exact structure of 'fields' is PENDING definition with the pilot
    company (Grupo Álvarez) in subsequent sessions.
    ---
    Define el conjunto estructurado de campos de datos que el agente IVR debe
    recopilar del llamante durante una llamada para una sección o empresa dada.
    La estructura exacta de 'fields' está PENDIENTE de definición con la empresa
    piloto (Grupo Álvarez) en sesiones posteriores.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="data_capture_sets",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este conjunto de captura de datos.",
    )
    # FK to Section is intentionally omitted here to avoid circular dependency.
    # Section holds the FK to DataCaptureSet instead.
    # La FK a Section se omite aquí intencionalmente para evitar dependencia circular.
    # Section tiene la FK a DataCaptureSet en su lugar.
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text="Nombre descriptivo del conjunto de captura de datos.",
    )
    fields = models.JSONField(
        default=list,
        verbose_name="Campos",
        help_text="Estructura JSON de campos a recopilar. PENDIENTE: definir con empresa piloto.",
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
        verbose_name = "Conjunto de captura de datos"
        verbose_name_plural = "Conjuntos de captura de datos"
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 5. SECTION — Business unit or department for IVR routing.
#    Unidad de negocio o departamento para el enrutamiento IVR.
# ---------------------------------------------------------------------------

class Section(models.Model):
    """
    Represents a business unit or department within a company (e.g. Elevación,
    Asistencia, Grúas). Sections are the primary routing units of the IVR system.
    Each section may have its own DataCaptureSet and a set of associated contacts.
    ---
    Representa una unidad de negocio o departamento dentro de una empresa (p. ej.
    Elevación, Asistencia, Grúas). Las secciones son las unidades primarias de
    enrutamiento del sistema IVR. Cada sección puede tener su propio DataCaptureSet
    y un conjunto de contactos asociados.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece esta sección.",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text="Nombre de la sección o departamento (p. ej. Elevación, Asistencia).",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
        help_text="Descripción detallada del ámbito y función de esta sección.",
    )
    contacts = models.ManyToManyField(
        "Contact",
        blank=True,
        related_name="sections",
        verbose_name="Contactos",
        help_text="Personas asociadas a esta sección a las que el IVR puede derivar llamadas.",
    )
    data_capture_set = models.ForeignKey(
        DataCaptureSet,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sections",
        verbose_name="Conjunto de captura de datos",
        help_text="Conjunto de datos a recopilar para las llamadas de esta sección.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si esta sección está operativa para el enrutamiento IVR.",
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
        verbose_name = "Sección"
        verbose_name_plural = "Secciones"
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 6. CONTACT — Person contactable by the IVR system.
#    Persona contactable por el sistema IVR.
# ---------------------------------------------------------------------------

class Contact(models.Model):
    """
    Represents a person the IVR system can call or route interactions to.
    Internal contacts (is_internal=True) have an associated CompanyUser and
    may have an active PresenceStatus. External contacts are simple records
    with no platform access.
    Constraint: if is_internal=True, company_user must not be null.
    ---
    Representa una persona a la que el sistema IVR puede llamar o derivar interacciones.
    Los contactos internos (is_internal=True) tienen un CompanyUser asociado y pueden
    tener un PresenceStatus activo. Los contactos externos son registros simples
    sin acceso a la plataforma.
    Restricción: si is_internal=True, company_user no puede ser null.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este contacto.",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text="Nombre completo del contacto.",
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name="Número de teléfono",
        help_text="Número de teléfono en formato E.164 (p. ej. +34XXXXXXXXX).",
    )
    is_internal = models.BooleanField(
        default=False,
        verbose_name="Interno",
        help_text="True si el contacto es un empleado interno con acceso al panel.",
    )
    company_user = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contact_profile",
        verbose_name="Usuario de empresa",
        help_text="Usuario de empresa vinculado. Obligatorio si el contacto es interno.",
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
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 7. CALL FLOW — IVR personality and behaviour definition for a phone number.
#    Definición de personalidad y comportamiento IVR para un número de teléfono.
# ---------------------------------------------------------------------------

class CallFlow(models.Model):
    """
    Defines the IVR agent personality and behaviour for a specific Twilio number.
    The system_instruction and initial_greeting fields are injected dynamically
    into Gemini Live's LiveConnectConfig at call time, replacing the hardcoded
    constants SYSTEM_INSTRUCTION and INITIAL_GREETING_TEXT in vox_bridge/services.py.
    ---
    Define la personalidad y el comportamiento del agente IVR para un número Twilio concreto.
    Los campos system_instruction e initial_greeting se inyectan dinámicamente en el
    LiveConnectConfig de Gemini Live en tiempo de llamada, sustituyendo las constantes
    hardcodeadas SYSTEM_INSTRUCTION e INITIAL_GREETING_TEXT en vox_bridge/services.py.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="call_flows",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este flujo IVR.",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text="Nombre descriptivo del flujo IVR (p. ej. Recepción principal Grupo Álvarez).",
    )
    system_instruction = models.TextField(
        verbose_name="Instrucción de sistema",
        help_text="Instrucción completa de sistema para el agente Gemini Live. Define rol, reglas y comportamiento.",
    )
    initial_greeting = models.TextField(
        verbose_name="Saludo inicial",
        help_text="Texto del saludo inicial que el agente pronuncia al conectar la llamada.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si este flujo IVR está disponible para su asignación a números.",
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
        verbose_name = "Flujo IVR"
        verbose_name_plural = "Flujos IVR"
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 8. PHONE NUMBER — Twilio number assigned to a company and a call flow.
#    Número Twilio asignado a una empresa y a un flujo IVR.
# ---------------------------------------------------------------------------

class PhoneNumber(models.Model):
    """
    Represents a Twilio phone number assigned to a company.
    Each PhoneNumber is linked to a CallFlow that determines the IVR behaviour
    when an inbound call is received on that number.
    The 'number' field stores the number in E.164 format (+XXXXXXXXXXX).
    ---
    Representa un número de teléfono Twilio asignado a una empresa.
    Cada PhoneNumber está vinculado a un CallFlow que determina el comportamiento
    IVR cuando se recibe una llamada entrante en ese número.
    El campo 'number' almacena el número en formato E.164 (+XXXXXXXXXXX).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="phone_numbers",
        verbose_name="Empresa",
        help_text="Empresa a la que está asignado este número Twilio.",
    )
    number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Número",
        help_text="Número de teléfono Twilio en formato E.164 (p. ej. +12603466780).",
    )
    friendly_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nombre amigable",
        help_text="Nombre descriptivo del número para identificación interna.",
    )
    call_flow = models.ForeignKey(
        CallFlow,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="phone_numbers",
        verbose_name="Flujo IVR",
        help_text="Flujo IVR que gestiona las llamadas entrantes a este número.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si este número está operativo para recibir llamadas.",
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
        verbose_name = "Número de teléfono"
        verbose_name_plural = "Números de teléfono"
        ordering = ["company__name", "number"]

    def __str__(self):
        return f"{self.company.name} — {self.number}"


# ---------------------------------------------------------------------------
# 9. PRESENCE STATUS — Real-time availability state of an internal user.
#    Estado de disponibilidad en tiempo real de un usuario interno.
# ---------------------------------------------------------------------------

class PresenceStatus(models.Model):
    """
    Records the real-time availability state of a CompanyUser.
    Only one PresenceStatus can be active per CompanyUser at any given time.
    A PresenceStatus is considered ACTIVE if:
        starts_at <= now() AND (ends_at IS NULL OR ends_at > now())
    When a new PresenceStatus is created for a user, any previously open record
    (ends_at IS NULL) must be closed by setting its ends_at = now().
    Note: updated_at is intentionally omitted per data model specification —
    each state transition creates a new record rather than modifying existing ones.
    ---
    Registra el estado de disponibilidad en tiempo real de un CompanyUser.
    Solo puede existir un PresenceStatus activo por CompanyUser en cada momento.
    Un PresenceStatus se considera ACTIVO si:
        starts_at <= now() AND (ends_at IS NULL OR ends_at > now())
    Cuando se crea un nuevo PresenceStatus para un usuario, cualquier registro
    abierto anterior (ends_at IS NULL) debe cerrarse estableciendo ends_at = now().
    Nota: updated_at se omite intencionalmente según la especificación del modelo de datos —
    cada transición de estado crea un nuevo registro en lugar de modificar los existentes.
    """

    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_IN_MEETING = "IN_MEETING"
    STATUS_BUSY_UNTIL = "BUSY_UNTIL"
    STATUS_ABSENT_SCHEDULED = "ABSENT_SCHEDULED"
    STATUS_ABSENT_VACATION = "ABSENT_VACATION"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Disponible"),
        (STATUS_IN_MEETING, "Reunido"),
        (STATUS_BUSY_UNTIL, "Ocupado hasta"),
        (STATUS_ABSENT_SCHEDULED, "Ausente programado"),
        (STATUS_ABSENT_VACATION, "Vacaciones"),
    ]

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="presence_statuses",
        verbose_name="Usuario de empresa",
        help_text="Usuario de empresa al que pertenece este estado de presencia.",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
        verbose_name="Estado",
        help_text="Estado de presencia actual del usuario.",
    )
    starts_at = models.DateTimeField(
        default=now,
        verbose_name="Inicio",
        help_text="Fecha y hora de inicio del estado de presencia.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fin",
        help_text="Fecha y hora de fin del estado. Null indica estado abierto sin fin definido.",
    )
    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Recordatorio enviado",
        help_text="Fecha y hora en que se envió el recordatorio SMS/WhatsApp para IN_MEETING.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Estado de presencia"
        verbose_name_plural = "Estados de presencia"
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.company_user} — {self.get_status_display()} desde {self.starts_at:%Y-%m-%d %H:%M}"
