# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/models.py
"""
Data models for the ivr_config multicompany IVR configuration engine.
Defines the full entity graph: Company, CompanyUser, CorporateVoiceProfile,
DataCaptureSet, Section, Contact, CallFlow, PhoneNumber, PresenceStatus,
SectionSchedule and BlockedCaller.
Creation order respects all FK dependencies to avoid circular references.
---
Modelos de datos para el motor de configuración IVR multiempresa ivr_config.
Define el grafo completo de entidades: Company, CompanyUser, CorporateVoiceProfile,
DataCaptureSet, Section, Contact, CallFlow, PhoneNumber, PresenceStatus,
SectionSchedule y BlockedCaller.
El orden de creación respeta todas las dependencias FK para evitar referencias circulares.
Última actualización: 2026-04-13 — Extensiones de modelo acordadas en sesión.
"""

from datetime import timedelta

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
    must_change_password = models.BooleanField(
        default=True,
        verbose_name="Debe cambiar contraseña",
        help_text=(
            "Si está activo, el usuario será redirigido obligatoriamente a la "
            "pantalla de cambio de contraseña al iniciar sesión. Se activa "
            "automáticamente al crear el usuario o cuando el ADMIN fuerza un reset."
        ),
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
    # Available voices for gemini-live-2.5-flash-native-audio on Vertex AI (Live API).
    # Voces disponibles para gemini-live-2.5-flash-native-audio en Vertex AI (Live API).
    VOICE_AOEDE   = "Aoede"
    VOICE_PUCK    = "Puck"
    VOICE_CHARON  = "Charon"
    VOICE_KORE    = "Kore"
    VOICE_FENRIR  = "Fenrir"
    VOICE_LEDA    = "Leda"
    VOICE_ORUS    = "Orus"
    VOICE_ZEPHYR  = "Zephyr"

    VOICE_CHOICES = [
        (VOICE_AOEDE,  "Aoede — Femenina, cálida (por defecto)"),
        (VOICE_PUCK,   "Puck — Masculina, juvenil y conversacional"),
        (VOICE_CHARON, "Charon — Masculina, profunda y autoritaria"),
        (VOICE_KORE,   "Kore — Femenina, clara y profesional"),
        (VOICE_FENRIR, "Fenrir — Masculina, cercana y accesible"),
        (VOICE_LEDA,   "Leda — Femenina, suave"),
        (VOICE_ORUS,   "Orus — Masculina, neutra"),
        (VOICE_ZEPHYR, "Zephyr — Femenina, enérgica"),
    ]

    voice_name = models.CharField(
        max_length=50,
        choices=VOICE_CHOICES,
        default=VOICE_AOEDE,
        verbose_name="Voz del agente",
        help_text=(
            "Voz Gemini Live que el agente IVR usará en las llamadas entrantes. "
            "Voces disponibles para gemini-live-2.5-flash-native-audio en Vertex AI. "
            "El cambio tiene efecto en la siguiente llamada sin necesidad de reiniciar."
        ),
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
    # ------------------------------------------------------------------
    # BACKUP FIELDS — Single-level restore snapshot (Paso 33-E).
    # Populated automatically on every successful save in CorporateVoiceProfileUpdateView.
    # The ADMIN can restore from these fields via /panel/voiceprofile/restore/.
    # ------------------------------------------------------------------
    # CAMPOS DE BACKUP — Snapshot de un nivel de restauración (Paso 33-E).
    # Se rellenan automáticamente en cada guardado exitoso de CorporateVoiceProfileUpdateView.
    # El ADMIN puede restaurar desde estos campos en /panel/voiceprofile/restore/.
    backup_voice_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Backup voz del agente",
        help_text="Copia anterior de voice_name para restauración de un clic.",
    )
    backup_tone_guidelines = models.TextField(
        blank=True,
        default="",
        verbose_name="Backup directrices de tono",
        help_text="Copia anterior de tone_guidelines para restauración de un clic.",
    )
    backup_sample_responses = models.JSONField(
        default=list,
        verbose_name="Backup respuestas de ejemplo",
        help_text="Copia anterior de sample_responses para restauración de un clic.",
    )
    backup_forbidden_phrases = models.JSONField(
        default=list,
        verbose_name="Backup frases prohibidas",
        help_text="Copia anterior de forbidden_phrases para restauración de un clic.",
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
    Availability is controlled by is_24h and SectionSchedule records:
    - is_24h=True  → always available, SectionSchedule is ignored.
    - is_24h=False → availability is determined by SectionSchedule for the
                     current weekday and time. If no schedule exists for the
                     current day, the section is considered unavailable.
    ---
    Representa una unidad de negocio o departamento dentro de una empresa (p. ej.
    Elevación, Asistencia, Grúas). Las secciones son las unidades primarias de
    enrutamiento del sistema IVR. Cada sección puede tener su propio DataCaptureSet
    y un conjunto de contactos asociados.
    La disponibilidad se controla mediante is_24h y los registros SectionSchedule:
    - is_24h=True  → siempre disponible, SectionSchedule se ignora.
    - is_24h=False → la disponibilidad la determinan los SectionSchedule para el
                     día de la semana y hora actuales. Si no existe horario para el
                     día actual, la sección se considera no disponible.
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
        through="SectionContact",
        through_fields=("section", "contact"),
        blank=True,
        related_name="sections",
        verbose_name="Contactos",
        help_text=(
            "Personas asociadas a esta sección ordenadas por prioridad de transferencia. "
            "La relación se gestiona a través del modelo intermedio SectionContact, que "
            "añade el campo 'priority' para controlar el orden de intento de transferencia "
            "desde el panel. Menor número de prioridad = mayor preferencia."
        ),
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
    call_flow = models.ForeignKey(
        "CallFlow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sections",
        verbose_name="Flujo IVR de sección",
        help_text=(
            "Flujo IVR específico de esta sección. Cuando el agente identifica que "
            "el llamante desea ser atendido por esta sección, carga este CallFlow "
            "para continuar la conversación con el contexto específico de la sección. "
            "Las secciones sin CallFlow asignado son ignoradas por el motor en "
            "tiempo de llamada (Estrategia B — carga dinámica por intención)."
        ),
    )
    is_24h = models.BooleanField(
        default=False,
        verbose_name="Disponible 24 horas",
        help_text=(
            "Si está activo, la sección se considera siempre disponible independientemente "
            "del horario definido en SectionSchedule. Usar para servicios de guardia permanente "
            "(p. ej. Asistencia en carretera)."
        ),
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
    The 'email' field is used to send call summary notifications to the responsible
    contact after a caller's data has been collected by Alia.
    The 'gender' field (M/F) controls Alia's verbal treatment: "Sr. {name}" or
    "Sra. {name}". If blank, Alia addresses the contact by name only.
    ---
    Representa una persona a la que el sistema IVR puede llamar o derivar interacciones.
    Los contactos internos (is_internal=True) tienen un CompanyUser asociado y pueden
    tener un PresenceStatus activo. Los contactos externos son registros simples
    sin acceso a la plataforma.
    Restricción: si is_internal=True, company_user no puede ser null.
    El campo 'email' se usa para enviar notificaciones de resumen de llamada al
    responsable tras la toma de datos del llamante por parte de Alia.
    El campo 'gender' (M/F) controla el tratamiento verbal de Alia: "Sr. {nombre}"
    o "Sra. {nombre}". Si está vacío, Alia se dirige al contacto solo por nombre.
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
    email = models.EmailField(
        blank=True,
        verbose_name="Correo electrónico",
        help_text="Dirección de correo electrónico para notificaciones de llamada al responsable.",
    )
    gender = models.CharField(
        max_length=1,
        choices=[("M", "Sr."), ("F", "Sra.")],
        blank=True,
        verbose_name="Género",
        help_text=(
            "Género del contacto para tratamiento verbal por Alia (Sr./Sra.). "
            "Si está vacío, Alia usará el nombre sin tratamiento."
        ),
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
    The notification_contact field designates the person to be notified (outbound
    call + email) when an inbound call does not match any known section.
    ---
    Define la personalidad y el comportamiento del agente IVR para un número Twilio concreto.
    Los campos system_instruction e initial_greeting se inyectan dinámicamente en el
    LiveConnectConfig de Gemini Live en tiempo de llamada, sustituyendo las constantes
    hardcodeadas SYSTEM_INSTRUCTION e INITIAL_GREETING_TEXT en vox_bridge/services.py.
    El campo notification_contact designa a la persona que debe recibir la notificación
    (llamada saliente + correo) cuando una llamada entrante no encaja en ninguna sección conocida.
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
    notification_contact = models.ForeignKey(
        "Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_flows",
        verbose_name="Contacto de notificación",
        help_text=(
            "Contacto designado para recibir la notificación (llamada saliente + correo) "
            "cuando una llamada no encaja en ninguna sección conocida del flujo IVR. "
            "Si está vacío, las llamadas de actividad no recogida no generan notificación."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si este flujo IVR está disponible para su asignación a números.",
    )
    fallback_section = models.ForeignKey(
        "Section",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fallback_for_call_flows",
        verbose_name="Sección de fallback",
        help_text=(
            "Sección de último recurso para este flujo IVR. Cuando ninguna sección "
            "activa puede atender al llamante, el agente transfiere la llamada al "
            "responsable humano de esta sección. Cada número puede tener su propia "
            "sección de fallback independiente según las necesidades de la empresa."
        ),
    )
    # ------------------------------------------------------------------
    # BACKUP FIELDS — Single-level restore snapshot (Paso 33-E).
    # Populated automatically on every successful save in CallFlowUpdateView.
    # The ADMIN can restore from these fields via /panel/callflows/{pk}/restore/.
    # ------------------------------------------------------------------
    # CAMPOS DE BACKUP — Snapshot de un nivel de restauración (Paso 33-E).
    # Se rellenan automáticamente en cada guardado exitoso de CallFlowUpdateView.
    # El ADMIN puede restaurar desde estos campos en /panel/callflows/{pk}/restore/.
    backup_system_instruction = models.TextField(
        blank=True,
        default="",
        verbose_name="Backup instrucción de sistema",
        help_text="Copia anterior de system_instruction para restauración de un clic.",
    )
    backup_initial_greeting = models.TextField(
        blank=True,
        default="",
        verbose_name="Backup saludo inicial",
        help_text="Copia anterior de initial_greeting para restauración de un clic.",
    )
    backup_notification_contact = models.ForeignKey(
        "Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backup_notification_flows",
        verbose_name="Backup contacto de notificación",
        help_text="Copia anterior de notification_contact para restauración de un clic.",
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
    The 'capabilities' field declares the communication channels this number
    is authorised to handle: voice IVR only, WhatsApp messaging only, or both.
    This distinction is used by IncomingWhatsAppView and the IVR webhook to
    resolve the correct company from the inbound Twilio number.
    ---
    Representa un número de teléfono Twilio asignado a una empresa.
    Cada PhoneNumber está vinculado a un CallFlow que determina el comportamiento
    IVR cuando se recibe una llamada entrante en ese número.
    El campo 'number' almacena el número en formato E.164 (+XXXXXXXXXXX).
    El campo 'capabilities' declara los canales de comunicación que este número
    está autorizado a gestionar: solo IVR de voz, solo mensajería WhatsApp, o ambos.
    Esta distinción es utilizada por IncomingWhatsAppView y el webhook IVR para
    resolver la empresa correcta a partir del número Twilio entrante.
    """

    # ------------------------------------------------------------------
    # Capabilities choices — communication channel authorisation flags.
    # Choices de capacidades — indicadores de autorización de canal.
    # ------------------------------------------------------------------
    CAPABILITY_VOICE     = "VOICE"
    CAPABILITY_WHATSAPP  = "WHATSAPP"
    CAPABILITY_BOTH      = "BOTH"

    CAPABILITY_CHOICES = [
        (CAPABILITY_VOICE,    "Solo voz (IVR)"),
        (CAPABILITY_WHATSAPP, "Solo WhatsApp"),
        (CAPABILITY_BOTH,     "Voz + WhatsApp"),
    ]

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
    capabilities = models.CharField(
        max_length=10,
        choices=CAPABILITY_CHOICES,
        default=CAPABILITY_VOICE,
        verbose_name="Capacidades",
        help_text=(
            "Canal o canales de comunicación autorizados para este número: "
            "VOICE (solo IVR de voz), WHATSAPP (solo mensajería WhatsApp) "
            "o BOTH (voz e IVR + WhatsApp simultáneamente)."
        ),
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


# ---------------------------------------------------------------------------
# 10. SECTION SCHEDULE — Weekly timetable for a section's availability.
#     Horario semanal de disponibilidad de una sección.
# ---------------------------------------------------------------------------

class SectionSchedule(models.Model):
    """
    Defines a time slot during which a Section is available for IVR routing.
    Multiple records per (section, weekday) pair are allowed to model split
    schedules (e.g. 08:00–14:00 and 16:00–20:00 on the same day).
    A section is considered available if the current time falls within ANY
    of the time slots defined for the current weekday.
    This model is only consulted when Section.is_24h is False.
    ---
    Define una franja horaria durante la cual una Section está disponible para
    el enrutamiento IVR. Se permiten múltiples registros por par (section, weekday)
    para modelar horarios partidos (p. ej. 08:00–14:00 y 16:00–20:00 el mismo día).
    Una sección se considera disponible si la hora actual cae en CUALQUIERA de las
    franjas definidas para el día de la semana en curso.
    Este modelo solo se consulta cuando Section.is_24h es False.
    """

    WEEKDAY_CHOICES = [
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="Sección",
        help_text="Sección a la que pertenece esta franja horaria.",
    )
    weekday = models.IntegerField(
        choices=WEEKDAY_CHOICES,
        verbose_name="Día de la semana",
        help_text="Día de la semana al que aplica esta franja horaria (0=Lunes, 6=Domingo).",
    )
    time_open = models.TimeField(
        verbose_name="Hora de apertura",
        help_text="Hora de inicio de la franja de disponibilidad (formato HH:MM).",
    )
    time_close = models.TimeField(
        verbose_name="Hora de cierre",
        help_text="Hora de fin de la franja de disponibilidad (formato HH:MM).",
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
        verbose_name = "Horario de sección"
        verbose_name_plural = "Horarios de sección"
        ordering = ["section__company__name", "section__name", "weekday", "time_open"]

    def __str__(self):
        return (
            f"{self.section.name} — "
            f"{self.get_weekday_display()} "
            f"{self.time_open:%H:%M}–{self.time_close:%H:%M}"
        )


# ---------------------------------------------------------------------------
# 11. BLOCKED CALLER — Temporarily blocked inbound phone number.
#     Número de teléfono entrante bloqueado temporalmente.
# ---------------------------------------------------------------------------

class BlockedCaller(models.Model):
    """
    Records a phone number that has been blocked from reaching the IVR system
    for a given company. The block is active while blocked_until > now().
    At the start of every inbound call, build_live_config() checks whether
    the caller's number (From) has an active BlockedCaller record for the
    company. If blocked, Alia responds with a standard polite message and
    terminates the call immediately without any data capture or notification.
    The block duration defaults to 24 hours but is configurable per record.
    Admins can manually unblock a number before expiry from the panel.
    ---
    Registra un número de teléfono que ha sido bloqueado para acceder al sistema
    IVR de una empresa concreta. El bloqueo está activo mientras blocked_until > now().
    Al inicio de cada llamada entrante, build_live_config() comprueba si el número
    del llamante (From) tiene un registro BlockedCaller activo para la empresa.
    Si está bloqueado, Alia responde con un mensaje estándar educado y termina la
    llamada inmediatamente sin toma de datos ni notificación.
    La duración del bloqueo es 24 horas por defecto, pero es configurable por registro.
    Los administradores pueden desbloquear manualmente un número antes del vencimiento
    desde el panel.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="blocked_callers",
        verbose_name="Empresa",
        help_text="Empresa para la que se aplica este bloqueo.",
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name="Número de teléfono",
        help_text="Número de teléfono bloqueado en formato E.164 (p. ej. +34XXXXXXXXX).",
    )
    reason = models.TextField(
        blank=True,
        verbose_name="Motivo",
        help_text="Descripción del motivo del bloqueo para registro interno.",
    )
    blocked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de bloqueo",
    )
    blocked_until = models.DateTimeField(
        verbose_name="Bloqueado hasta",
        help_text="Fecha y hora de expiración del bloqueo. Por defecto: 24 horas desde el bloqueo.",
    )
    blocked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocked_callers",
        verbose_name="Bloqueado por",
        help_text="Usuario administrador que aplicó el bloqueo.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Llamante bloqueado"
        verbose_name_plural = "Llamantes bloqueados"
        ordering = ["-blocked_at"]
        indexes = [
            # Fast lookup by company + phone_number at call time.
            # Búsqueda rápida por empresa + número en tiempo de llamada.
            models.Index(
                fields=["company", "phone_number"],
                name="ivr_blocked_company_phone_idx",
            ),
        ]

    def __str__(self):
        return f"{self.company.name} — {self.phone_number} (hasta {self.blocked_until:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        """
        Sets blocked_until to 24 hours after creation if not explicitly provided.
        ---
        Establece blocked_until a 24 horas tras la creación si no se ha indicado explícitamente.
        """
        if not self.pk and not self.blocked_until:
            self.blocked_until = now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """
        Returns True if the block is currently in effect.
        ---
        Retorna True si el bloqueo está actualmente en vigor.
        """
        return self.blocked_until > now()

# ---------------------------------------------------------------------------
# 12. SECTION CONTACT — Explicit through model for Section ↔ Contact M2M.
#     Modelo intermedio explícito para la relación M2M Section ↔ Contact.
# ---------------------------------------------------------------------------

class SectionContact(models.Model):
    """
    Explicit through model that replaces the implicit Section.contacts M2M table.
    Adds a 'priority' field to control the order in which contacts are attempted
    during a resilient multi-contact call transfer (Paso 39). Lower priority
    number means higher preference. Contacts without a phone_number are excluded
    by the transfer engine at runtime regardless of their priority value.
    The unique_together constraint prevents the same contact from being added
    to the same section more than once.
    ---
    Modelo intermedio explícito que reemplaza la tabla M2M implícita Section.contacts.
    Añade el campo 'priority' para controlar el orden en que se intenta contactar a
    las personas durante una transferencia resiliente multi-contacto (Paso 39). Número
    de prioridad menor = mayor preferencia. Los contactos sin phone_number son excluidos
    por el motor de transferencia en tiempo de ejecución independientemente de su
    valor de prioridad. La restricción unique_together evita que el mismo contacto
    se añada a la misma sección más de una vez.
    """

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="section_contacts",
        verbose_name="Sección",
        help_text="Sección a la que pertenece esta asignación de contacto.",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="section_assignments",
        verbose_name="Contacto",
        help_text="Contacto asignado a esta sección para transferencias de llamada.",
    )
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad",
        help_text=(
            "Orden de intento de transferencia. Menor número = mayor prioridad. "
            "El motor intentará contactar primero al registro con priority=0, "
            "luego al siguiente, hasta agotar todos los contactos de la sección."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Contacto de sección"
        verbose_name_plural = "Contactos de sección"
        unique_together = [("section", "contact")]
        ordering = ["section", "priority", "contact__name"]

    def __str__(self):
        return (
            f"{self.section.name} — {self.contact.name} "
            f"(prioridad: {self.priority})"
        )


# ---------------------------------------------------------------------------
# 13. TRANSFER ATTEMPT — Persistent state bridge between bridge and webhook.
#     Puente de estado persistente entre el bridge y el webhook de Twilio.
# ---------------------------------------------------------------------------

class TransferAttempt(models.Model):
    """
    Persists the state of an in-progress call transfer across the boundary
    between the voice bridge process and the Twilio action webhook. Twilio
    does not carry session context in its action webhook POST body, so the
    database is the only viable mechanism to pass state between the two
    asynchronous processes. Each record is keyed by call_sid (unique per
    Twilio call leg) and tracks which contact index is being attempted and
    whether the transfer is pending, completed, or failed.
    ---
    Persiste el estado de una transferencia de llamada en curso a través del
    límite entre el proceso bridge de voz y el webhook action de Twilio. Twilio
    no transporta contexto de sesión en el body del POST del webhook action, por
    lo que la base de datos es el único mecanismo viable para pasar estado entre
    los dos procesos asíncronos. Cada registro tiene como clave call_sid (único
    por tramo de llamada Twilio) y rastrea qué índice de contacto se está
    intentando y si la transferencia está pendiente, completada o fallida.
    """

    STATUS_PENDING   = "PENDING"
    STATUS_FAILED    = "FAILED"
    STATUS_COMPLETED = "COMPLETED"

    STATUS_CHOICES = [
        (STATUS_PENDING,   "Pendiente"),
        (STATUS_FAILED,    "Fallida"),
        (STATUS_COMPLETED, "Completada"),
    ]

    call_sid = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        verbose_name="Call SID",
        help_text="Identificador único de la llamada Twilio (CA...). Clave primaria de negocio.",
    )
    section = models.ForeignKey(
        Section,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_attempts",
        verbose_name="Sección",
        help_text="Sección destino de la transferencia.",
    )
    twilio_number = models.CharField(
        max_length=20,
        verbose_name="Número Twilio",
        help_text="Número Twilio receptor de la llamada original (formato E.164).",
    )
    caller_number = models.CharField(
        max_length=20,
        verbose_name="Número llamante",
        help_text="Número del llamante original (formato E.164).",
    )
    contact_index = models.IntegerField(
        default=0,
        verbose_name="Índice de contacto",
        help_text=(
            "Índice (base 0) del contacto de sección que se está intentando en este momento, "
            "ordenado por SectionContact.priority ASC. El webhook TransferStatusView "
            "incrementa este valor en cada intento fallido para avanzar al siguiente contacto."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
        help_text="Estado actual de la transferencia.",
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
        verbose_name = "Intento de transferencia"
        verbose_name_plural = "Intentos de transferencia"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Transferencia {self.call_sid} — "
            f"{self.get_status_display()} — "
            f"contacto idx {self.contact_index}"
        )


# ---------------------------------------------------------------------------
# 14. PENDING NOTIFICATION — Unresolved call requiring follow-up contact.
#     Llamada sin resolver que requiere contacto de seguimiento.
# ---------------------------------------------------------------------------

class PendingNotification(models.Model):
    """
    Records inbound calls where all transfer attempts to section contacts
    failed and the caller chose to leave their data for a callback. When the
    WhatsApp channel (Hito 4) becomes operational, a Celery worker will
    process records with channel='PENDING' and convert them into real
    WhatsApp or SMS notifications to the section's responsible contact.
    Until then the record serves as a manual follow-up registry visible
    from the administration panel.
    ---
    Registra las llamadas entrantes en las que todos los intentos de
    transferencia a contactos de sección fallaron y el llamante eligió
    dejar sus datos para que le devuelvan la llamada. Cuando el canal
    WhatsApp (Hito 4) esté operativo, un worker de Celery procesará los
    registros con channel='PENDING' y los convertirá en notificaciones
    reales de WhatsApp o SMS al contacto responsable de la sección. Hasta
    entonces el registro sirve como archivo de seguimiento manual visible
    desde el panel de administración.
    """

    CHANNEL_WHATSAPP = "WHATSAPP"
    CHANNEL_SMS      = "SMS"
    CHANNEL_EMAIL    = "EMAIL"
    CHANNEL_PENDING  = "PENDING"

    CHANNEL_CHOICES = [
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_SMS,      "SMS"),
        (CHANNEL_EMAIL,    "Correo electrónico"),
        (CHANNEL_PENDING,  "Pendiente"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="pending_notifications",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece esta notificación pendiente.",
    )
    section = models.ForeignKey(
        Section,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_notifications",
        verbose_name="Sección",
        help_text="Sección destino que no pudo gestionar la llamada.",
    )
    caller_number = models.CharField(
        max_length=20,
        verbose_name="Número llamante",
        help_text="Número de teléfono del llamante en formato E.164.",
    )
    call_sid = models.CharField(
        max_length=40,
        verbose_name="Call SID",
        help_text="Identificador único de la llamada Twilio para trazabilidad.",
    )
    voice_recording_url = models.URLField(
        blank=True,
        verbose_name="URL de grabación de voz",
        help_text="URL de Twilio de la grabación de voz del mensaje dejado por el llamante.",
    )
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_PENDING,
        verbose_name="Canal de notificación",
        help_text=(
            "Canal por el que se enviará la notificación al responsable. "
            "PENDING: aún no procesado por Celery. El worker de Hito 4 "
            "actualizará este campo al enviar la notificación real."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de notificación",
        help_text="Fecha y hora en que se envió la notificación real al responsable.",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notas",
        help_text="Observaciones adicionales sobre la llamada o el seguimiento.",
    )

    class Meta:
        verbose_name = "Notificación pendiente"
        verbose_name_plural = "Notificaciones pendientes"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Notificación {self.caller_number} — "
            f"{self.created_at:%Y-%m-%d %H:%M} — "
            f"{self.get_channel_display()}"
        )

# ---------------------------------------------------------------------------
# 15. CALL DATA CAPTURE — IVR data capture record persisted per call.
#     Registro de captura de datos IVR persistido por llamada.
# ---------------------------------------------------------------------------

class CallDataCapture(models.Model):
    """
    Persists the structured data collected by a DataCaptureSet during an
    active IVR call session. Each record represents a single completed
    capture cycle for a given call leg. Once all DataCaptureSet fields are
    filled, the IVR engine instantiates this record, attempts a WhatsApp
    notification to the section's referent contact, and proceeds with the
    call transfer. The notified_via_whatsapp flag tracks delivery success.
    ---
    Persiste los datos estructurados recopilados por un DataCaptureSet durante
    una sesion de llamada IVR activa. Cada registro representa un ciclo de
    captura completado para un tramo de llamada concreto. Una vez completados
    todos los campos del DataCaptureSet, el motor IVR instancia este registro,
    intenta la notificacion WhatsApp al contacto referente de la seccion y
    procede con la transferencia de la llamada. El flag notified_via_whatsapp
    registra el exito de la entrega.
    """

    call_sid = models.CharField(
        max_length=40,
        db_index=True,
        verbose_name="Call SID",
        help_text=(
            "Identificador unico del tramo de llamada Twilio (CA...). "
            "No es unique: una misma llamada puede generar multiples capturas "
            "si el flujo IVR atraviesa mas de una seccion con DataCaptureSet."
        ),
    )
    call_flow = models.ForeignKey(
        "CallFlow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="call_data_captures",
        verbose_name="Flujo IVR",
        help_text="Flujo IVR activo en el momento de la captura.",
    )
    section = models.ForeignKey(
        "Section",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="call_data_captures",
        verbose_name="Seccion",
        help_text="Seccion en la que se produjo la captura de datos.",
    )
    contact = models.ForeignKey(
        "Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="call_data_captures",
        verbose_name="Contacto referente",
        help_text=(
            "Snapshot del contacto referente de la seccion en el momento de la captura. "
            "Se almacena como FK para trazabilidad historica; el contacto puede cambiar "
            "posteriormente sin afectar al registro."
        ),
    )
    captured_data = models.JSONField(
        default=dict,
        verbose_name="Datos capturados",
        help_text=(
            "Diccionario clave->valor con los datos recopilados por el DataCaptureSet activo. "
            "Estructura: {nombre_campo: valor_capturado}. "
            "Ejemplo: {nombre: Juan Garcia, telefono: +34600000000, motivo: Averia grua}."
        ),
    )
    captured_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de captura",
        help_text="Timestamp UTC en que se completo el ciclo de captura.",
    )
    notified_via_whatsapp = models.BooleanField(
        default=False,
        verbose_name="Notificado via WhatsApp",
        help_text=(
            "True si la notificacion WhatsApp al contacto referente fue enviada "
            "y confirmada por la API de Twilio. False hasta entonces."
        ),
    )
    whatsapp_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de envio WhatsApp",
        help_text="Timestamp UTC en que la notificacion WhatsApp fue confirmada como enviada.",
    )

    class Meta:
        verbose_name = "Captura de datos de llamada"
        verbose_name_plural = "Capturas de datos de llamada"
        ordering = ["-captured_at"]

    def __str__(self):
        section_name = self.section.name if self.section else "sin seccion"
        notified = "WA enviado" if self.notified_via_whatsapp else "pendiente"
        return (
            f"Captura {self.call_sid} "
            f"{section_name} "
            f"{self.captured_at:%Y-%m-%d %H:%M} "
            f"{notified}"
        )
