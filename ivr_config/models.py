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

from datetime import date, timedelta

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
    # Operational bases of the company (localities, coverage areas).
    # Bases de operación de la empresa (localidades, zonas de cobertura).
    operation_bases = models.TextField(
        blank=True,
        default="",
        verbose_name="Bases de operación",
        help_text=(
            "Localidades o zonas desde donde opera la empresa. "
            "Alimenta el motor de cálculo de presupuestos para determinar "
            "el punto de origen del servicio."
        ),
    )
    # Labour calendar: local/national holidays and night-time reference hours.
    # Calendario laboral: festivos locales/nacionales y horario nocturno de referencia.
    labor_calendar = models.TextField(
        blank=True,
        default="",
        verbose_name="Calendario laboral",
        help_text=(
            "Festivos locales, nacionales y horario nocturno de referencia. "
            "Alimenta el motor de cálculo de presupuestos para aplicar "
            "correctamente los recargos nocturnos y festivos según el calendario real."
        ),
    )
    # Night service start hour — configurable per company for the ASISTENCIA budget engine.
    # Default: 22:00. Services starting at or after this hour are flagged as night service.
    # Hora de inicio del servicio nocturno — configurable por empresa para el motor de presupuestos ASISTENCIA.
    # Por defecto: 22:00. Los servicios que comiencen a esta hora o despues se marcan como nocturnos.
    night_start = models.TimeField(
        default="22:00",
        verbose_name="Inicio franja nocturna",
        help_text=(
            "Hora de inicio de la franja nocturna para el módulo de presupuestos "
            "ASISTENCIA. Los servicios a esta hora o después se marcan automáticamente "
            "como nocturnos/festivos. Por defecto: 22:00."
        ),
    )
    # Night service end hour — configurable per company for the ASISTENCIA budget engine.
    # Default: 06:00. Services ending before this hour are flagged as night service.
    # Hora de fin del servicio nocturno — configurable por empresa para el motor de presupuestos ASISTENCIA.
    # Por defecto: 06:00. Los servicios que terminen antes de esta hora se marcan como nocturnos.
    night_end = models.TimeField(
        default="06:00",
        verbose_name="Fin franja nocturna",
        help_text=(
            "Hora de fin de la franja nocturna para el módulo de presupuestos "
            "ASISTENCIA. Los servicios antes de esta hora se marcan automáticamente "
            "como nocturnos/festivos. Por defecto: 06:00."
        ),
    )

    # ---------------------------------------------------------------------------
    # Toll configuration — ASISTENCIA budget engine
    # Configuración de peajes — motor de presupuestos ASISTENCIA
    # ---------------------------------------------------------------------------
    TOLL_VEHICLE_LIGHT   = "LIGHT"
    TOLL_VEHICLE_HEAVY_1 = "HEAVY_1"
    TOLL_VEHICLE_HEAVY_2 = "HEAVY_2"
    TOLL_VEHICLE_CHOICES = [
        (TOLL_VEHICLE_LIGHT,   "Ligero"),
        (TOLL_VEHICLE_HEAVY_1, "Pesado 1"),
        (TOLL_VEHICLE_HEAVY_2, "Pesado 2"),
    ]

    toll_vehicle_type = models.CharField(
        max_length=10,
        choices=TOLL_VEHICLE_CHOICES,
        default=TOLL_VEHICLE_HEAVY_1,
        verbose_name="Tipo de vehículo de peaje",
        help_text=(
            "Categoría de vehículo usada para calcular el coste de peaje en el "
            "motor de presupuestos ASISTENCIA. Se aplica a todos los presupuestos "
            "hasta que se cambie manualmente desde el panel de peajes."
        ),
    )
    toll_markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Recargo de peaje al cliente (%)",
        help_text=(
            "Porcentaje de recargo aplicado sobre el coste de peaje calculado. "
            "Se aplica a todos los presupuestos hasta que se cambie manualmente "
            "desde el panel de peajes. Ej: 10 = 10% de recargo."
        ),
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
    Links a Django auth.User to a Company with a defined role.
    Roles: ADMIN (full access), OPERATOR (presence management), WORKSHOP (workshop
    work orders), SUPERVISOR (PDF work-order review and export), DRIVER (reserved).
    CompanyUser instances must never have is_staff=True on their linked User.
    Access to /admin/ is blocked via CompanyUserAdminBlockMiddleware.
    ---
    Vincula un auth.User de Django a una Company con un rol definido.
    Roles: ADMIN (acceso completo), OPERATOR (gestión de presencia), WORKSHOP (partes
    de taller), SUPERVISOR (revisión y exportación de partes PDF), DRIVER (reservado).
    Las instancias de CompanyUser jamás deben tener is_staff=True en su User vinculado.
    El acceso a /admin/ se bloquea mediante CompanyUserAdminBlockMiddleware.
    """

    ROLE_ADMIN        = "ADMIN"
    ROLE_OPERATOR     = "OPERATOR"
    ROLE_WORKSHOP     = "WORKSHOP"
    # WORKSHOPBOSS: jefe de taller. Acceso a tickets de avería, sala BREAKDOWNS
    # y sala de su sección asignada. Mismo acceso que SUPERVISOR en Taller,
    # Administración y Configuración de jornada. Sin acceso a IVR ni WhatsApp.
    # WORKSHOPBOSS: workshop manager. Access to breakdown tickets, BREAKDOWNS room
    # and own section room. Same access as SUPERVISOR for Taller, Administration
    # and Workday configuration sections. No IVR or WhatsApp access.
    ROLE_WORKSHOPBOSS = "WORKSHOPBOSS"
    # SUPERVISOR: acceso a carga, lista, revisión y exportación de partes PDF.
    # Sin acceso al editor inline ni al resto del panel de configuración IVR.
    # SUPERVISOR: access to PDF work-order upload, list, review and export.
    # No access to the inline editor or the rest of the IVR configuration panel.
    ROLE_SUPERVISOR   = "SUPERVISOR"
    ROLE_DRIVER       = "DRIVER"
    # ASSISTANCE: operario de la seccion ASISTENCIA. Acceso exclusivo
    # al modulo de presupuestos. Sin acceso a IVR, WhatsApp, partes
    # ni ninguna otra seccion del panel.
    # ASSISTANCE: ASISTENCIA section operator. Exclusive access to the
    # budgets module. No access to IVR, WhatsApp, work orders or any
    # other panel section.
    ROLE_ASSISTANCE   = "ASSISTANCE"
    # DOCS_SUPERVISOR: acceso a la subida de documentación de centros de
    # gasto (Hito 23). El listado de "Documentación Centros de Gasto" es
    # de solo lectura para cualquier usuario autenticado del panel — este
    # rol (y ADMIN) son los únicos que además pueden subir documentación
    # nueva.
    # DOCS_SUPERVISOR: access to uploading cost-center documentation
    # (Hito 23). The "Documentación Centros de Gasto" listing is
    # read-only for any authenticated panel user — this role (and ADMIN)
    # are the only ones that can additionally upload new documentation.
    ROLE_DOCS_SUPERVISOR = "DOCS_SUPERVISOR"
    ROLE_CHOICES      = [
        (ROLE_ADMIN,         "Administrador"),
        (ROLE_OPERATOR,      "Operador"),
        (ROLE_WORKSHOP,      "Operario de taller"),
        (ROLE_WORKSHOPBOSS,  "Jefe de taller"),
        (ROLE_SUPERVISOR,    "Supervisor"),
        (ROLE_DRIVER,        "Chófer"),
        (ROLE_ASSISTANCE,    "Operario de Asistencia"),
        (ROLE_DOCS_SUPERVISOR, "Supervisor de Documentación"),
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
        help_text=(
            "ADMIN: acceso completo a la configuración. "
            "OPERATOR: gestión de presencia. "
            "WORKSHOP: partes de taller. "
            "WORKSHOPBOSS: jefe de taller — tickets de avería, sala BREAKDOWNS y sección propia, "
            "más acceso equivalente a SUPERVISOR en Taller, Administración y jornada. "
            "SUPERVISOR: revisión y exportación de partes PDF. "
            "DRIVER: reservado. "
            "ASSISTANCE: operario de Asistencia — solo modulo de presupuestos. "
            "DOCS_SUPERVISOR: puede subir documentación de centros de gasto "
            "(el listado es de solo lectura para cualquier usuario)."
        ),
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
    trusted_device_token = models.UUIDField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Token de dispositivo de confianza",
        help_text=(
            "UUID generado automáticamente cuando el usuario establece su "
            "contraseña por primera vez. Se almacena en una cookie HttpOnly "
            "firmada en el navegador del usuario para permitir el acceso "
            "sin formulario de login desde ese dispositivo. "
            "Anularlo fuerza al usuario a autenticarse de nuevo con contraseña."
        ),
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Teléfono",
        help_text=(
            "Número de teléfono de contacto del usuario de empresa. "
            "Formato libre (p. ej. +34XXXXXXXXX). Opcional."
        ),
    )
    dni = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="DNI / NIF",
        help_text=(
            "Documento Nacional de Identidad o NIF del usuario de empresa. "
            "Se usa para identificar al operario en el registro de signup. "
            "Debe ser único por empresa cuando se informe."
        ),
    )
    workday_schedule = models.ForeignKey(
        "WorkdaySchedule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_users",
        verbose_name="Horario de jornada",
        help_text=(
            "Horario de jornada asignado a este operario por el supervisor. "
            "Gate 4 usa este horario con prioridad máxima. "
            "Si no está asignado, Gate 4 aplica el horario por defecto de la empresa. "
            "Si tampoco existe horario por defecto, Gate 4 se omite completamente."
        ),
    )
    is_intensive_override = models.BooleanField(
        default=False,
        verbose_name="Jornada intensiva activa",
        help_text=(
            "Indica si este operario está en jornada intensiva (verano). "
            "El operario puede activarlo o desactivarlo desde el formulario "
            "de parte. El supervisor o administrador puede cambiarlo desde "
            "el panel de gestión de usuarios. Cuando está activo, Gate 4 "
            "resuelve el WorkdaySchedule con is_intensive=True de la empresa "
            "en lugar del horario partido (invierno). El estado persiste "
            "entre sesiones hasta que se modifique explícitamente."
        ),
    )
    # Granular per-user override, independent of role: grants a user with
    # role=ASSISTANCE access to the budget history list and the full
    # breakdown detail view (normally ADMIN-only). Introduced for special
    # ASSISTANCE users who need audit visibility into calculated budgets
    # without gaining any other ADMIN privilege. Has no effect for any
    # role other than ASSISTANCE — ADMIN already has full access
    # regardless of this flag.
    # ---
    # Override granular por usuario, independiente del rol: concede a un
    # usuario con role=ASSISTANCE acceso al listado de historial de
    # presupuestos y a la vista de desglose completo (normalmente
    # exclusiva de ADMIN). Introducido para usuarios ASISTENCIA
    # especiales que necesitan visibilidad de auditoría sobre los
    # presupuestos calculados sin ganar ningún otro privilegio de ADMIN.
    # No tiene efecto para ningún rol distinto de ASSISTANCE — ADMIN ya
    # tiene acceso completo independientemente de este flag.
    can_view_budget_breakdown = models.BooleanField(
        default=False,
        verbose_name="Puede ver desglose de presupuestos",
        help_text=(
            "Solo aplica a usuarios con rol Operario de Asistencia. "
            "Cuando está activo, además de crear presupuestos, el usuario "
            "puede ver el historial completo y el desglose detallado de "
            "cualquier presupuesto — funcionalidad normalmente exclusiva "
            "de Administrador. No concede ningún otro permiso de ADMIN."
        ),
    )
    alias = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Alias de chat",
        help_text=(
            "Apodo del usuario en el chat IRC de grupo. Fuente de verdad única "
            "para los mensajes enviados desde el panel. Se solicita mediante modal "
            "al acceder a una sala de chat por primera vez sin alias configurado. "
            "Los contactos externos (sin CompanyUser) usan Contact.alias para "
            "los mensajes recibidos por WhatsApp."
        ),
    )

    # ------------------------------------------------------------------
    # Workshop family — only relevant for WORKSHOPBOSS role.
    # Familia de taller — solo relevante para el rol WORKSHOPBOSS.
    # ------------------------------------------------------------------
    WORKSHOP_FAMILY_MECHANICAL = "MECHANICAL"
    WORKSHOP_FAMILY_ELEVATION  = "ELEVATION"
    WORKSHOP_FAMILY_CHOICES = [
        (WORKSHOP_FAMILY_MECHANICAL, "Taller Mecánico"),
        (WORKSHOP_FAMILY_ELEVATION,  "Taller Elevación"),
    ]

    workshop_family = models.CharField(
        max_length=20,
        choices=WORKSHOP_FAMILY_CHOICES,
        null=True,
        blank=True,
        verbose_name="Familia de taller",
        help_text=(
            "Solo aplica para el rol WORKSHOPBOSS. "
            "Determina qué familia de centros de gasto gestiona este jefe de taller "
            "y qué tickets de avería le son visibles y asignables. "
            "MECHANICAL: camiones, grúas y maquinaria pesada. "
            "ELEVATION: carretillas y plataformas elevadoras."
        ),
    )

    # ------------------------------------------------------------------
    # Base assignment — added in H24 (S018). Applies to ANY CompanyUser,
    # not just WORKSHOPBOSS (unlike workshop_family above) -- fundamental
    # for DRIVER (chóferes) and WORKSHOP operators, who previously had no
    # field at all linking them to a physical base.
    #
    # String reference to "budgets.Base" (not a top-level import): budgets
    # models.py already imports Company/CompanyUser from this same module,
    # so a direct import here would create a circular import. Django
    # resolves string FK references lazily via the app registry.
    #
    # Asignación de base — añadido en H24 (S018). Aplica a CUALQUIER
    # CompanyUser, no solo a WORKSHOPBOSS (a diferencia de workshop_family
    # arriba) -- fundamental para DRIVER (chóferes) y operarios WORKSHOP,
    # que antes no tenían ningún campo que los vinculara a una base física.
    #
    # Referencia por string a "budgets.Base" (no import de nivel de
    # módulo): budgets/models.py ya importa Company/CompanyUser de este
    # mismo módulo, así que un import directo aquí crearía un import
    # circular. Django resuelve referencias FK por string de forma
    # perezosa vía el registro de apps.
    # ------------------------------------------------------------------
    base = models.ForeignKey(
        "budgets.Base",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_users",
        verbose_name="Base",
        help_text=(
            "Base física de referencia de este usuario. Determina qué "
            "calendario laboral/festivos (Base.labor_calendar, ya "
            "sincronizado vía sync_base_calendars) aplica a sus "
            "vacaciones en el calendario de RRHH (H24). Nulo para roles "
            "que no lo necesitan (p. ej. ADMIN)."
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
        help_text="Lista de objetos JSON con estructura [{key, label, type, required}]. Tipos soportados: text, phone, location, reference, date, free_text.",
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
    fleet_families = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Familias de flota",
        help_text=(
            "Lista de familias del catálogo MachineAsset a incluir en el contexto IVR "
            "de esta sección. Ejemplo: [\"PLATAFOR\"] para Elevación, "
            "[\"MOVILES\", \"AUTOCARG\"] para Grúas. "
            "Los activos de estas familias se inyectan automáticamente en el "
            "system_instruction del CallFlow de sección al generarse o regenerarse."
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
    DEFAULT_ROLE_WORKSHOP = "WORKSHOP"
    DEFAULT_ROLE_DRIVER   = "DRIVER"
    DEFAULT_ROLE_CHOICES  = [
        (DEFAULT_ROLE_WORKSHOP, "Operario de taller"),
        (DEFAULT_ROLE_DRIVER,   "Chófer"),
    ]

    default_role = models.CharField(
        max_length=20,
        choices=DEFAULT_ROLE_CHOICES,
        default=DEFAULT_ROLE_WORKSHOP,
        verbose_name="Rol por defecto",
        help_text=(
            "Rol asignado automáticamente a los contactos de esta sección cuando se "
            "registran en la plataforma vía onboarding WhatsApp. "
            "WORKSHOP: operario de taller. DRIVER: chófer. "
            "Los roles de mayor rango (ADMIN, SUPERVISOR, OPERATOR) se asignan "
            "manualmente desde la consola de administración."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si esta sección está operativa para el enrutamiento IVR.",
    )
    is_broadcast_enabled = models.BooleanField(
        default=False,
        verbose_name="Habilitada para circulares WhatsApp",
        help_text=(
            "Indica si esta sección puede recibir circulares masivas de WhatsApp. "
            "Solo las secciones habilitadas aparecen en el selector del bot."
        ),
    )
    # IVR channel flags — control how this section participates in voice calls.
    # Flags de canal IVR — controlan cómo participa esta sección en las llamadas de voz.
    ivr_transfer_enabled = models.BooleanField(
        default=True,
        verbose_name="Transferencia IVR habilitada",
        help_text=(
            "Si está activo, esta sección aparece en el section_callflow_map y "
            "María puede transferir llamadas a sus contactos. "
            "Desactivar para secciones que gestionan averías internas o que no "
            "deben recibir transferencias de voz (p. ej. Taller Mecánico)."
        ),
    )
    ivr_breakdown_enabled = models.BooleanField(
        default=False,
        verbose_name="Avería interna IVR habilitada",
        help_text=(
            "Si está activo, cuando Gemini detecta que el llamante reporta una "
            "avería interna de flota, la conversación sigue el flujo de captura "
            "de datos para crear un BreakdownTicket vinculado a esta sección. "
            "No implica transferencia de llamada — el ticket se crea en BD y se "
            "notifica al taller por WhatsApp. Activar solo en secciones de taller."
        ),
    )
    workday_schedule = models.ForeignKey(
        "WorkdaySchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sections",
        verbose_name="Horario de trabajo por defecto",
        help_text=(
            "Horario de jornada que se aplica por defecto a todos los trabajadores "
            "de esta sección. Un trabajador con horario individual asignado "
            "(CompanyUser.workday_schedule) tiene prioridad sobre este valor. "
            "Si no hay horario de sección ni individual, Gate 4 usa el horario "
            "por defecto de empresa (WorkdaySchedule.is_default=True)."
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
    contact after a caller's data has been collected by María.
    The 'gender' field (M/F) controls María's verbal treatment: "Sr. {name}" or
    "Sra. {name}". If blank, María addresses the contact by name only.
    ---
    Representa una persona a la que el sistema IVR puede llamar o derivar interacciones.
    Los contactos internos (is_internal=True) tienen un CompanyUser asociado y pueden
    tener un PresenceStatus activo. Los contactos externos son registros simples
    sin acceso a la plataforma.
    Restricción: si is_internal=True, company_user no puede ser null.
    El campo 'email' se usa para enviar notificaciones de resumen de llamada al
    responsable tras la toma de datos del llamante por parte de María.
    El campo 'gender' (M/F) controla el tratamiento verbal de María: "Sr. {nombre}"
    o "Sra. {nombre}". Si está vacío, María se dirige al contacto solo por nombre.
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
        help_text="Nombre completo del contacto (legacy — usar first_name/last_name).",
    )
    first_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Nombre de pila",
        help_text=(
            "Nombre de pila del contacto. Si está relleno, se usa en saludos "
            "de voz (Alia IVR) en lugar del nombre completo."
        ),
    )
    last_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Apellidos",
        help_text="Apellidos del contacto.",
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
            "Género del contacto para tratamiento verbal por María (Sr./Sra.). "
            "Si está vacío, María usará el nombre sin tratamiento."
        ),
    )
    is_internal = models.BooleanField(
        default=False,
        verbose_name="Interno",
        help_text="True si el contacto es un empleado interno con acceso al panel.",
    )
    alias = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Alias de chat",
        help_text=(
            "Apodo del contacto externo en el chat IRC de grupo. Se recoge la primera "
            "vez que el contacto escribe en su sala SECTION via WhatsApp. "
            "Hasta que no está configurado, sus mensajes no se reenvían al grupo — "
            "el chatbot le solicita que elija su alias. "
            "Los contactos sin sección asignada (clientes) no tienen alias "
            "y nunca se les solicita. "
            "Para contactos internos (is_internal=True) vinculados a un CompanyUser, "
            "el alias canónico es CompanyUser.alias — este campo queda en desuso "
            "para contactos internos."
        ),
    )
    # --- Alias onboarding state — persisted in DB to survive server reloads. ---
    # --- Estado del onboarding de alias — persistido en BD para sobrevivir reloads. ---
    ALIAS_STEP_NONE       = "NONE"
    ALIAS_STEP_PENDING    = "PENDING"
    ALIAS_STEP_CONFIRMING = "CONFIRMING"
    ALIAS_STEP_CHOICES    = [
        (ALIAS_STEP_NONE,       "Sin estado"),
        (ALIAS_STEP_PENDING,    "Esperando nombre"),
        (ALIAS_STEP_CONFIRMING, "Esperando confirmación"),
    ]
    alias_onboarding_step = models.CharField(
        max_length=12,
        choices=ALIAS_STEP_CHOICES,
        default=ALIAS_STEP_NONE,
        verbose_name="Paso de onboarding de alias",
        help_text=(
            "Estado actual del diálogo de recogida de alias vía WhatsApp. "
            "NONE: sin diálogo activo. PENDING: se ha pedido el nombre, esperando respuesta. "
            "CONFIRMING: se ha recibido un alias propuesto, esperando confirmación SÍ/NO."
        ),
    )
    alias_onboarding_proposed = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Alias propuesto en onboarding",
        help_text=(
            "Alias propuesto por el contacto durante el diálogo de onboarding. "
            "Se guarda en el Paso B y se confirma o descarta en el Paso C."
        ),
    )
    # --- Broadcast opt-out — Paso 10 (chat_session_renewal). ---
    # --- Baja del broadcast — Paso 10 (chat_session_renewal). ---
    opt_out_broadcast = models.BooleanField(
        default=False,
        verbose_name="Baja del broadcast",
        help_text=(
            "Si está activo, el contacto ha optado por no recibir mensajes de "
            "broadcast del grupo de su sección. Se activa cuando el contacto "
            "pulsa 'No, gracias' en el template chat_session_renewal. "
            "Los contactos con este flag activo se excluyen del bucle de "
            "broadcast en ChatSendView."
        ),
    )
    # --- Breakdown routing state — Paso 13 (flujo de averia). ---
    # --- Estado del flujo de averia — Paso 13. ---
    ROUTING_STATE_NONE                      = "NONE"
    ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM = "AWAITING_BREAKDOWN_CONFIRM"
    ROUTING_STATE_BREAKDOWN_IN_PROGRESS      = "BREAKDOWN_IN_PROGRESS"
    ROUTING_STATE_CHOICES                   = [
        (ROUTING_STATE_NONE,                       "Sin flujo activo"),
        (ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM, "Esperando confirmacion de averia"),
        (ROUTING_STATE_BREAKDOWN_IN_PROGRESS,      "Recogida de averia en curso"),
    ]
    routing_state = models.CharField(
        max_length=30,
        choices=ROUTING_STATE_CHOICES,
        default=ROUTING_STATE_NONE,
        verbose_name="Estado de enrutamiento",
        help_text=(
            "Estado del flujo de averia del contacto. "
            "NONE: sin flujo activo. "
            "AWAITING_BREAKDOWN_CONFIRM: se ha enviado el Quick Reply Si/No. "
            "BREAKDOWN_IN_PROGRESS: el agente Gemini esta recogiendo los datos."
        ),
    )
    pending_routing_body = models.TextField(
        blank=True,
        default="",
        verbose_name="Mensaje pendiente de enrutamiento",
        help_text=(
            "Cuerpo del mensaje original recibido del contacto mientras se espera "
            "su selección de sala en el diálogo de enrutamiento dinámico. "
            "Se guarda cuando routing_state pasa a AWAITING_ROUTE y se descarta "
            "tras procesar la respuesta del contacto."
        ),
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
    backup_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Backup nombre",
        help_text="Copia anterior del nombre del flujo IVR para restauración de un clic.",
    )
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
    company. If blocked, María responds with a standard polite message and
    terminates the call immediately without any data capture or notification.
    The block duration defaults to 24 hours but is configurable per record.
    Admins can manually unblock a number before expiry from the panel.
    ---
    Registra un número de teléfono que ha sido bloqueado para acceder al sistema
    IVR de una empresa concreta. El bloqueo está activo mientras blocked_until > now().
    Al inicio de cada llamada entrante, build_live_config() comprueba si el número
    del llamante (From) tiene un registro BlockedCaller activo para la empresa.
    Si está bloqueado, María responde con un mensaje estándar educado y termina la
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


# ---------------------------------------------------------------------------
# 16. WORKER ABSENCE — Absence record for a workshop operator.
#     Registro de ausencia de un operario de taller.
# ---------------------------------------------------------------------------

class WorkerAbsence(models.Model):
    """
    Records a declared absence period for a CompanyUser with the WORKSHOP role.
    Each record covers a contiguous date range with a typed reason. The supervisor
    or ADMIN registers absences manually; operators cannot create their own records.
    The 'registered_by' field tracks which supervisor created the record for audit.
    ---
    Registra un periodo de ausencia declarado para un CompanyUser con rol WORKSHOP.
    Cada registro cubre un rango de fechas contiguo con un motivo tipificado. El
    supervisor o ADMIN registra las ausencias manualmente; los operarios no pueden
    crear sus propios registros.
    El campo 'registered_by' registra qué supervisor creó el registro para auditoría.
    """

    ABSENCE_VACATION            = "VACATION"
    ABSENCE_SICK_LEAVE          = "SICK_LEAVE"
    ABSENCE_WORK_ACCIDENT       = "WORK_ACCIDENT"
    ABSENCE_MATERNITY_PATERNITY = "MATERNITY_PATERNITY"
    ABSENCE_BEREAVEMENT         = "BEREAVEMENT"
    ABSENCE_PERSONAL            = "PERSONAL"
    ABSENCE_OTHER               = "OTHER"

    ABSENCE_CHOICES = [
        (ABSENCE_VACATION,            "Vacaciones anuales"),
        (ABSENCE_SICK_LEAVE,          "Baja médica (IT enfermedad común)"),
        (ABSENCE_WORK_ACCIDENT,       "Accidente laboral (IT profesional)"),
        (ABSENCE_MATERNITY_PATERNITY, "Maternidad / Paternidad"),
        (ABSENCE_BEREAVEMENT,         "Defunción de familiar"),
        (ABSENCE_PERSONAL,            "Asuntos propios"),
        (ABSENCE_OTHER,               "Otros"),
    ]

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="absences",
        verbose_name="Operario",
        help_text="Operario de taller al que pertenece este registro de ausencia.",
    )
    absence_type = models.CharField(
        max_length=30,
        choices=ABSENCE_CHOICES,
        verbose_name="Tipo de ausencia",
        help_text="Categoría de la ausencia según los tipos definidos por la plataforma.",
    )
    start_date = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Primer día de la ausencia (inclusive).",
    )
    end_date = models.DateField(
        verbose_name="Fecha de fin",
        help_text="Último día de la ausencia (inclusive).",
    )
    registered_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registered_absences",
        verbose_name="Registrado por",
        help_text=(
            "Supervisor o ADMIN que registró esta ausencia. "
            "Se establece automáticamente desde el usuario autenticado en el momento del alta."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
        help_text="Observaciones adicionales sobre la ausencia. Campo libre, opcional.",
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
        verbose_name = "Ausencia de operario"
        verbose_name_plural = "Ausencias de operario"
        ordering = ["-start_date"]

    def __str__(self):
        return (
            f"{self.company_user.user.get_full_name() or self.company_user.user.username} — "
            f"{self.get_absence_type_display()} "
            f"({self.start_date:%d/%m/%Y} – {self.end_date:%d/%m/%Y})"
        )


# ---------------------------------------------------------------------------
# 17. WORK PERIOD — Active employment period for a workshop operator.
#     Periodo de trabajo activo de un operario de taller.
# ---------------------------------------------------------------------------

class WorkPeriodGroup(models.Model):
    """
    Represents a company-wide work period that groups individual
    WorkPeriod records (one per operator) under a single administrative
    entity. This is the primary UI object: supervisors create, view and
    manage periods at the group level; individual operator rows are
    subordinate.

    A WorkPeriodGroup with is_closed=False is active — operators can
    still be added and their work orders created/edited.
    A WorkPeriodGroup with is_closed=True has been administratively
    locked: all subordinate WorkPeriod records are also locked.
    ---
    Representa un periodo de trabajo de ámbito empresarial que agrupa
    los registros WorkPeriod individuales (uno por operario) bajo una
    única entidad administrativa. Es el objeto primario de la UI: los
    supervisores crean, visualizan y gestionan los periodos a nivel de
    grupo; las filas individuales de operario son subordinadas.

    Un WorkPeriodGroup con is_closed=False está activo — se pueden
    añadir operarios y sus partes pueden crearse y editarse.
    Un WorkPeriodGroup con is_closed=True ha sido liquidado
    administrativamente: todos los WorkPeriod subordinados también
    quedan bloqueados.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="work_period_groups",
        verbose_name="Empresa",
        help_text=(
            "Empresa a la que pertenece este grupo de periodos de trabajo."
        ),
    )
    label = models.CharField(
        max_length=100,
        verbose_name="Etiqueta",
        help_text=(
            "Nombre descriptivo del periodo (p. ej. 'Junio-Julio 2026'). "
            "Se muestra como cabecera en la lista de periodos y en el "
            "historial de partes del operario."
        ),
    )
    start_date = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Primer día del periodo de trabajo (inclusive).",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de fin",
        help_text=(
            "Último día del periodo de trabajo (inclusive). "
            "Puede establecerse al crear el grupo sin que implique cierre."
        ),
    )
    is_closed = models.BooleanField(
        default=False,
        verbose_name="Liquidado",
        db_index=True,
        help_text=(
            "Indica que el periodo ha sido liquidado administrativamente. "
            "Cuando está activo, ningún parte dentro del rango puede editarse. "
            "Se activa manualmente por el ADMIN o SUPERVISOR al cerrar el "
            "periodo. Cierra también todos los WorkPeriod subordinados."
        ),
    )
    created_by = models.ForeignKey(
        "CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_work_period_groups",
        verbose_name="Creado por",
        help_text=(
            "Supervisor o ADMIN que creó este grupo de periodos. "
            "Se establece automáticamente desde el usuario autenticado."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última modificación",
    )

    # Computed status values (H24/S020 redesign) -- never stored, always
    # derived from is_closed + today's date vs. the period's own range.
    # A group is ACTIVE while today falls within its range, regardless of
    # is_closed; several groups can be simultaneously PENDING_LIQUIDATION
    # if liquidation lags -- that is expected, not a bug (ver anexo V24
    # "Hoja de Ruta para la Siguiente Sesión", puntos 1-2).
    # ---
    # Valores de estado calculados (rediseño H24/S020) -- nunca se
    # guardan, siempre se derivan de is_closed + la fecha de hoy frente al
    # propio rango del periodo. Un grupo está ACTIVE mientras hoy caiga
    # dentro de su rango, sin importar is_closed; pueden convivir varios
    # grupos PENDING_LIQUIDATION a la vez si la liquidación se retrasa --
    # es el comportamiento esperado, no un bug (ver anexo V24 "Hoja de
    # Ruta para la Siguiente Sesión", puntos 1-2).
    STATUS_ACTIVE = "ACTIVE"
    STATUS_PENDING_LIQUIDATION = "PENDING_LIQUIDATION"
    STATUS_LIQUIDATED = "LIQUIDATED"

    STATUS_LABELS_ES = {
        STATUS_ACTIVE: "Activo",
        STATUS_PENDING_LIQUIDATION: "Cerrado, pendiente de liquidar",
        STATUS_LIQUIDATED: "Liquidado",
    }

    class Meta:
        verbose_name = "Grupo de periodos de trabajo"
        verbose_name_plural = "Grupos de periodos de trabajo"
        ordering = ["-start_date"]

    @property
    def status(self):
        """
        Returns one of STATUS_ACTIVE / STATUS_PENDING_LIQUIDATION /
        STATUS_LIQUIDATED. Liquidated wins over date range. Otherwise,
        the period is active while today falls inside [start_date,
        end_date] (or there is no end_date yet); once today passes
        end_date without liquidation, it becomes PENDING_LIQUIDATION.
        ---
        Devuelve STATUS_ACTIVE / STATUS_PENDING_LIQUIDATION /
        STATUS_LIQUIDATED. Liquidado gana siempre sobre el rango de
        fechas. Si no, el periodo está activo mientras hoy caiga dentro
        de [start_date, end_date] (o no tenga aún end_date); en cuanto
        hoy supera end_date sin liquidar, pasa a PENDING_LIQUIDATION.
        """
        if self.is_closed:
            return self.STATUS_LIQUIDATED
        today = now().date()
        if self.end_date is not None and today > self.end_date:
            return self.STATUS_PENDING_LIQUIDATION
        return self.STATUS_ACTIVE

    @property
    def status_label(self):
        """
        Human-readable Spanish label for `status`, for direct use in
        templates without repeating the mapping.
        ---
        Etiqueta en castellano legible para `status`, para usarse
        directamente en templates sin repetir el mapeo.
        """
        return self.STATUS_LABELS_ES[self.status]

    def __str__(self):
        end_label = (
            self.end_date.strftime("%d/%m/%Y") if self.end_date
            else "sin fecha fin"
        )
        return (
            f"{self.company.name} — {self.label} "
            f"({self.start_date:%d/%m/%Y} / {end_label}) "
            f"[{self.status_label.upper()}]"
        )


# ---------------------------------------------------------------------------
# WorkPeriodGroup — cálculo de ciclo por fecha (rediseño H24/S020)
# ---------------------------------------------------------------------------
# Replaces the old manual creation flow (free label/start_date/end_date
# typed by the supervisor, WorkPeriodGroupCreateView -- removed): periods
# now follow a fixed cycle, the 21st of a month to the 20th of the next,
# computed on demand, never pre-created in advance. The row is ensured
# ("asegurada") the first time something actually needs it -- currently
# only the calendar's default (no group_pk) resolution, see
# hr_calendar/services.py::resolve_period_group_for_calendar.
# ---
# Sustituye al antiguo flujo de creación manual (label/start_date/end_date
# libres tecleados por el supervisor, WorkPeriodGroupCreateView --
# eliminada): los periodos siguen ahora un ciclo fijo, del día 21 de un
# mes al 20 del siguiente, calculado bajo demanda, nunca precreado por
# adelantado. La fila se asegura la primera vez que hace falta de verdad
# -- por ahora, solo la resolución por defecto del calendario (sin
# group_pk), ver hr_calendar/services.py::resolve_period_group_for_calendar.

_WORK_PERIOD_MONTH_NAMES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def compute_period_bounds_for_date(target_date):
    """
    Computes (start_date, end_date, label) for the fixed 21-to-20 cycle
    that contains target_date. Pure function, no DB access.

    Rule (confirmed by Miguel Ángel, no ambiguity): every period runs
    from the 21st of a month to the 20th of the following month
    (21/07-20/08, 21/08-20/09, ...). A date on day >= 21 belongs to the
    period starting that same month; a date on day <= 20 belongs to the
    period that started the previous month.
    ---
    Calcula (start_date, end_date, label) del ciclo fijo 21-al-20 que
    contiene target_date. Función pura, sin acceso a BD.

    Regla (confirmada por Miguel Ángel, sin ambigüedad): cada periodo va
    del día 21 de un mes al día 20 del mes siguiente (21/07-20/08,
    21/08-20/09, ...). Una fecha en día >= 21 pertenece al periodo que
    arranca ese mismo mes; una fecha en día <= 20 pertenece al periodo
    que arrancó el mes anterior.
    """
    if target_date.day >= 21:
        start_month = target_date.month
        start_year = target_date.year
    else:
        start_month = target_date.month - 1
        start_year = target_date.year
        if start_month == 0:
            start_month = 12
            start_year -= 1

    start_date = date(start_year, start_month, 21)

    end_month = start_month + 1
    end_year = start_year
    if end_month == 13:
        end_month = 1
        end_year += 1
    end_date = date(end_year, end_month, 20)

    start_name = _WORK_PERIOD_MONTH_NAMES_ES[start_month]
    end_name = _WORK_PERIOD_MONTH_NAMES_ES[end_month]
    if start_year == end_year:
        label = f"{start_name}-{end_name} {end_year}"
    else:
        label = f"{start_name} {start_year}-{end_name} {end_year}"

    return start_date, end_date, label


def ensure_work_period_group_for_date(company, target_date, created_by=None):
    """
    Ensures the WorkPeriodGroup covering target_date exists for company,
    following the 21-to-20 cycle, and returns (group, created).

    1. Looks for an existing group (any -- including historical/free-date
       ones such as the "prehistoric" period that predates this cycle)
       whose [start_date, end_date] already covers target_date. Never
       duplicates a group that already covers the date.
    2. If none covers it, computes the canonical 21-20 bounds and
       get_or_create's the group with those exact bounds.
    3. On creation only, auto-assigns a WorkPeriod to every active
       WORKSHOP operator of the company (Opción A confirmada por Miguel
       Ángel 2026-07-15 -- ya no hay asignación manual uno a uno).

    Never touches is_closed. Several groups can legitimately be open at
    once while liquidation lags -- see WorkPeriodGroup.status.
    ---
    Asegura que exista el WorkPeriodGroup que cubre target_date para
    company, siguiendo el ciclo 21-al-20, y devuelve (group, created).

    1. Busca un grupo ya existente (cualquiera -- incluidos los
       históricos/de fechas libres, como el periodo "prehistórico"
       anterior a este ciclo) cuyo [start_date, end_date] ya cubra
       target_date. Nunca duplica un grupo que ya cubre la fecha.
    2. Si ninguno la cubre, calcula los márgenes 21-20 canónicos y hace
       get_or_create del grupo con esas fechas exactas.
    3. Solo al crearlo, asigna automáticamente un WorkPeriod a cada
       operario WORKSHOP activo de la empresa (Opción A confirmada por
       Miguel Ángel 2026-07-15 -- ya no hay asignación manual uno a uno).

    Nunca toca is_closed. Pueden convivir legítimamente varios grupos
    abiertos a la vez si la liquidación se retrasa -- ver
    WorkPeriodGroup.status.
    """
    existing = (
        WorkPeriodGroup.objects
        .filter(company=company, start_date__lte=target_date)
        .filter(
            models.Q(end_date__gte=target_date)
            | models.Q(end_date__isnull=True)
        )
        .order_by("-start_date")
        .first()
    )
    if existing is not None:
        return existing, False

    start_date, end_date, label = compute_period_bounds_for_date(
        target_date
    )
    group, created = WorkPeriodGroup.objects.get_or_create(
        company=company,
        start_date=start_date,
        end_date=end_date,
        defaults={"label": label, "created_by": created_by},
    )
    if created:
        _assign_all_active_operators_to_group(group, created_by)
    return group, created


def _assign_all_active_operators_to_group(group, created_by):
    """
    Creates a WorkPeriod for every active WORKSHOP operator of the
    group's company, pointing at the group's own dates. Idempotent per
    (operator, group) pair via get_or_create.
    ---
    Crea un WorkPeriod para cada operario WORKSHOP activo de la empresa
    del grupo, apuntando a las fechas propias del grupo. Idempotente por
    par (operario, grupo) vía get_or_create.
    """
    operators = CompanyUser.objects.filter(
        company=group.company,
        is_active=True,
        role=CompanyUser.ROLE_WORKSHOP,
    )
    for operator in operators:
        WorkPeriod.objects.get_or_create(
            company_user=operator,
            group=group,
            defaults={
                "start_date": group.start_date,
                "end_date": group.end_date,
                "label": group.label,
                "created_by": created_by,
            },
        )


class WorkPeriod(models.Model):
    """
    Represents a contiguous employment or contract period for a CompanyUser.
    A period with is_closed=False is active — the operator's work orders within
    it can still be created and edited.
    A period with is_closed=True has been administratively locked (liquidated):
    no further edits are allowed on work orders falling within its date range.
    The end_date field defines the date range of the period; it is independent
    of the locked/unlocked state. A period can have an end_date set while still
    being active (is_closed=False).
    ---
    Representa un periodo de empleo o contrato contiguo para un CompanyUser.
    Un periodo con is_closed=False está activo — los partes dentro de él
    pueden crearse y editarse con normalidad.
    Un periodo con is_closed=True ha sido liquidado administrativamente:
    no se permiten más ediciones en los partes que caen en su rango de fechas.
    El campo end_date define el rango del periodo; es independiente del estado
    abierto/cerrado. Un periodo puede tener end_date definido y seguir activo.
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="work_periods",
        verbose_name="Operario",
        help_text="Operario de taller al que pertenece este periodo de trabajo.",
    )
    group = models.ForeignKey(
        WorkPeriodGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_periods",
        verbose_name="Grupo de periodo",
        help_text=(
            "Grupo de periodo al que pertenece este registro individual. "
            "Nulo para registros legacy creados antes de la introducción "
            "de WorkPeriodGroup."
        ),
    )
    start_date = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Primer día del periodo de trabajo (inclusive).",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de fin",
        help_text=(
            "Último día del periodo de trabajo (inclusive). "
            "Puede establecerse al crear el periodo sin que implique cierre."
        ),
    )
    is_closed = models.BooleanField(
        default=False,
        verbose_name="Liquidado",
        db_index=True,
        help_text=(
            "Indica que el periodo ha sido liquidado administrativamente. "
            "Cuando está activo, ningún parte dentro del rango puede editarse. "
            "Se activa manualmente por el ADMIN o SUPERVISOR al cerrar el periodo."
        ),
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Etiqueta",
        help_text=(
            "Nombre descriptivo opcional del periodo (p. ej. 'Mayo 2026', 'Verano 2026'). "
            "Se muestra en el historial de partes del operario como cabecera de grupo."
        ),
    )
    created_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_work_periods",
        verbose_name="Creado por",
        help_text=(
            "Supervisor o ADMIN que creó este periodo. "
            "Se establece automáticamente desde el usuario autenticado en el momento del alta."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Periodo de trabajo"
        verbose_name_plural = "Periodos de trabajo"
        ordering = ["-start_date"]

    def __str__(self):
        end_label = self.end_date.strftime("%d/%m/%Y") if self.end_date else "sin fecha fin"
        closed_label = " [LIQUIDADO]" if self.is_closed else ""
        return (
            f"{self.company_user.user.get_full_name() or self.company_user.user.username} — "
            f"{self.start_date:%d/%m/%Y} / {end_label}"
            + (f" [{self.label}]" if self.label else "")
            + closed_label
        )


# ---------------------------------------------------------------------------
# 18. WORKDAY SCHEDULE — Reference workday timetable for a company.
#     Horario de jornada de referencia para una empresa.
#
#     Season-aware split-shift model:
#       WINTER: split shift — morning tract + afternoon tract.
#       SUMMER: intensive shift — morning tract only (is_intensive=True).
#     The midday window between end_time_morning and start_time_afternoon
#     is excluded from GAP detection (mandatory lunch break).
#
#     Modelo de turno partido por temporada:
#       INVIERNO: turno partido — tramo de mañana + tramo de tarde.
#       VERANO: jornada intensiva — solo tramo de mañana (is_intensive=True).
#     La ventana de mediodía entre end_time_morning y start_time_afternoon
#     se excluye de la detección de GAP (pausa de comida obligatoria).
# ---------------------------------------------------------------------------

class WorkdaySchedule(models.Model):
    """
    Defines a named workday timetable for a Company. A company can have
    multiple schedules to cover the different shift profiles of its workforce
    (e.g. "Mecánicos invierno 07:00–14:00 / 15:00–18:00",
          "Mecánicos verano 07:00–15:00 [intensiva]").

    Season-aware split-shift model:
      - season=WINTER: split shift with morning and afternoon tracts.
        Gate 4 validates both tracts. The midday window between
        end_time_morning and start_time_afternoon is excluded from GAP
        detection (it is the mandatory lunch break).
      - season=SUMMER / is_intensive=True: morning tract only.
        Gate 4 validates only start_time_morning / end_time_morning.
        Afternoon fields are null and ignored.

    Each CompanyUser with the WORKSHOP role can be assigned a specific schedule
    via the CompanyUser.workday_schedule FK. Gate 4 resolves the schedule to
    apply using this priority chain:
      1. CompanyUser.workday_schedule (if set).
      2. WorkdaySchedule with is_default=True for the company (fallback).
      3. None → Gate 4 is skipped entirely (current behaviour preserved).

    Only one schedule per company may have is_default=True. This invariant is
    enforced in the save() override: setting is_default=True on a record
    automatically clears is_default on all other schedules of the same company.

    ---

    Define un horario de jornada con nombre para una Company. Una empresa puede
    tener múltiples horarios para cubrir los distintos perfiles de turno de su
    plantilla (p. ej. "Mecánicos invierno 07:00–14:00 / 15:00–18:00",
                      "Mecánicos verano 07:00–15:00 [intensiva]").

    Modelo de turno partido por temporada:
      - season=WINTER: turno partido con tramo de mañana y tramo de tarde.
        Gate 4 valida ambos tramos. La ventana de mediodía entre
        end_time_morning y start_time_afternoon se excluye de la detección
        de GAP (pausa de comida obligatoria).
      - season=SUMMER / is_intensive=True: solo tramo de mañana.
        Gate 4 valida únicamente start_time_morning / end_time_morning.
        Los campos de tarde son nulos e ignorados.

    Cada CompanyUser con rol WORKSHOP puede tener asignado un horario concreto
    mediante la FK CompanyUser.workday_schedule. Gate 4 resuelve el horario
    aplicable usando esta cadena de prioridad:
      1. CompanyUser.workday_schedule (si está asignado).
      2. WorkdaySchedule con is_default=True para la empresa (fallback).
      3. None → Gate 4 se omite completamente (comportamiento actual preservado).

    Solo puede haber un horario con is_default=True por empresa. Este invariante
    se impone en el override de save(): establecer is_default=True en un registro
    limpia automáticamente is_default en todos los demás horarios de la empresa.
    """

    class Season(models.TextChoices):
        """
        Season choices for the workday schedule timetable.
        ---
        Opciones de temporada para el horario de jornada.
        """
        WINTER = "WINTER", "Invierno"
        SUMMER = "SUMMER", "Verano"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="workday_schedules",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este horario de jornada.",
    )
    label = models.CharField(
        max_length=100,
        default="",
        verbose_name="Nombre del horario",
        help_text=(
            "Nombre descriptivo del perfil de turno "
            "(p. ej. 'Mecánicos', 'Chóferes de grúa', 'Administración'). "
            "Visible en el panel del supervisor al asignar horarios a operarios."
        ),
    )
    season = models.CharField(
        max_length=10,
        choices=Season.choices,
        default=Season.WINTER,
        verbose_name="Temporada",
        help_text=(
            "Temporada a la que aplica este horario. "
            "INVIERNO: turno partido con tramo de mañana y tarde. "
            "VERANO: jornada intensiva (solo mañana si is_intensive=True)."
        ),
    )
    # ------------------------------------------------------------------
    # Morning tract / Tramo de mañana (obligatorio siempre)
    # ------------------------------------------------------------------
    start_time_morning = models.TimeField(
        verbose_name="Entrada mañana",
        default="07:00",
        help_text=(
            "Hora de inicio del tramo de mañana. "
            "Los partes cuyo primer bloque comience después de esta hora más "
            "el margen de tolerancia generarán un aviso de inicio tardío."
        ),
    )
    end_time_morning = models.TimeField(
        verbose_name="Salida mañana",
        default="15:00",
        help_text=(
            "Hora de fin del tramo de mañana. "
            "En jornada intensiva (is_intensive=True) es también la hora de "
            "salida final de la jornada completa."
        ),
    )
    # ------------------------------------------------------------------
    # Afternoon tract / Tramo de tarde (null cuando is_intensive=True)
    # ------------------------------------------------------------------
    start_time_afternoon = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Entrada tarde",
        help_text=(
            "Hora de inicio del tramo de tarde. "
            "Dejar en blanco para jornada intensiva (is_intensive=True). "
            "La ventana entre la salida de mañana y esta hora se trata como "
            "pausa de mediodía y no genera aviso de laguna en Gate 4."
        ),
    )
    end_time_afternoon = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Salida tarde",
        help_text=(
            "Hora de fin del tramo de tarde y de la jornada completa. "
            "Dejar en blanco para jornada intensiva (is_intensive=True)."
        ),
    )
    # ------------------------------------------------------------------
    # Shift type / Tipo de turno
    # ------------------------------------------------------------------
    is_intensive = models.BooleanField(
        default=False,
        verbose_name="Jornada intensiva",
        help_text=(
            "Si está activo, este horario corresponde a jornada intensiva: "
            "Gate 4 solo valida el tramo de mañana y los campos de tarde "
            "quedan ignorados. Típico en temporada de verano."
        ),
    )
    tolerance_minutes = models.PositiveSmallIntegerField(
        default=15,
        verbose_name="Tolerancia (minutos)",
        help_text=(
            "Margen de tolerancia en minutos aplicado tanto al inicio como al "
            "fin de cada tramo antes de registrar un aviso. Por defecto: 15 min."
        ),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Horario por defecto",
        help_text=(
            "Si está activo, este horario se aplica como fallback a los operarios "
            "que no tienen un horario específicamente asignado. "
            "Solo puede haber un horario por defecto por empresa — activarlo aquí "
            "desactiva automáticamente el anterior horario por defecto."
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
        verbose_name = "Horario de jornada"
        verbose_name_plural = "Horarios de jornada"
        ordering = ["company__name", "label"]

    def clean(self):
        """
        Validates afternoon tract consistency with is_intensive flag.
        If is_intensive=True, clears afternoon fields silently.
        If is_intensive=False, both afternoon fields are required and
        start_time_afternoon must be after end_time_morning.
        ---
        Valida la coherencia del tramo de tarde con el flag is_intensive.
        Si is_intensive=True, limpia los campos de tarde silenciosamente.
        Si is_intensive=False, ambos campos de tarde son obligatorios y
        start_time_afternoon debe ser posterior a end_time_morning.
        """
        from django.core.exceptions import ValidationError

        if self.is_intensive:
            # Intensive shift — clear afternoon fields silently.
            # Jornada intensiva — limpiar campos de tarde silenciosamente.
            self.start_time_afternoon = None
            self.end_time_afternoon   = None
        else:
            if not self.start_time_afternoon or not self.end_time_afternoon:
                raise ValidationError(
                    "Los campos de entrada y salida de tarde son obligatorios "
                    "para jornada partida (jornada intensiva desactivada)."
                )
            if (
                self.end_time_morning
                and self.start_time_afternoon
                and self.start_time_afternoon <= self.end_time_morning
            ):
                raise ValidationError(
                    "La hora de entrada de tarde debe ser posterior a la hora "
                    "de salida de mañana."
                )
            if (
                self.start_time_afternoon
                and self.end_time_afternoon
                and self.end_time_afternoon <= self.start_time_afternoon
            ):
                raise ValidationError(
                    "La hora de salida de tarde debe ser posterior a la hora "
                    "de entrada de tarde."
                )

    def save(self, *args, **kwargs):
        """
        Runs clean() to enforce afternoon tract consistency, then enforces
        the single-default invariant across the company's schedules.
        ---
        Ejecuta clean() para imponer la coherencia del tramo de tarde, luego
        impone el invariante de único-por-defecto entre los horarios de la empresa.
        """
        self.clean()
        if self.is_default:
            WorkdaySchedule.objects.filter(
                company=self.company,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Returns a human-readable string combining company, label, season,
        morning tract and afternoon tract (if present).
        ---
        Devuelve una cadena legible combinando empresa, etiqueta, temporada,
        tramo de mañana y tramo de tarde (si existe).
        """
        default_marker   = " [por defecto]" if self.is_default else ""
        intensive_marker = " [intensiva]"   if self.is_intensive else ""
        season_label     = self.get_season_display()
        morning = (
            f"{self.start_time_morning:%H:%M}–{self.end_time_morning:%H:%M}"
            if self.start_time_morning and self.end_time_morning else "?–?"
        )
        if not self.is_intensive and self.start_time_afternoon and self.end_time_afternoon:
            afternoon = f" / {self.start_time_afternoon:%H:%M}–{self.end_time_afternoon:%H:%M}"
        else:
            afternoon = ""
        return (
            f"{self.company.name} — {self.label} [{season_label}] "
            f"{morning}{afternoon} "
            f"(±{self.tolerance_minutes} min){intensive_marker}{default_marker}"
        )


# ---------------------------------------------------------------------------
# 19. ABSENCE CATEGORY — Supervisor-managed catalogue of absence reasons.
#     Catálogo de motivos de ausencia gestionado por el supervisor.
# ---------------------------------------------------------------------------

class AbsenceCategory(models.Model):
    """
    Supervisor-managed catalogue of absence/incident reasons for a Company.
    Used by the Gate 4 resolution flow (WorkdayGapResolutionView) to let the
    operator justify each detected workday gap before the work order is
    persisted as DONE.

    Standard categories are pre-loaded via the seed_absence_categories
    management command. Supervisors can deactivate categories (is_active=False)
    without deleting them to preserve historical references.

    Uniqueness is enforced on (company, code) so that seed runs are idempotent
    (get_or_create by code + company).

    ---

    Catálogo de motivos de ausencia/incidencia gestionado por el supervisor de
    una Company. Usado por el flujo de resolución de Gate 4
    (WorkdayGapResolutionView) para que el operario justifique cada laguna de
    jornada detectada antes de que el parte se persista como DONE.

    Las categorías estándar se precargan mediante el comando de gestión
    seed_absence_categories. Los supervisores pueden desactivar categorías
    (is_active=False) sin eliminarlas para preservar referencias históricas.

    La unicidad se impone sobre (company, code) para que las ejecuciones del
    seed sean idempotentes (get_or_create por code + company).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="absence_categories",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece esta categoría de ausencia.",
    )
    code = models.CharField(
        max_length=40,
        verbose_name="Código",
        help_text=(
            "Identificador interno de la categoría (p. ej. MEDICAL, DAY_OFF). "
            "Único por empresa. Usado por el seed y la lógica de Gate 4."
        ),
    )
    label = models.CharField(
        max_length=100,
        verbose_name="Etiqueta",
        help_text=(
            "Texto visible para el operario en el selector de justificación "
            "de lagunas de jornada (WorkdayGapResolutionView)."
        ),
    )
    requires_note = models.BooleanField(
        default=False,
        verbose_name="Requiere nota",
        help_text=(
            "Si está activo, el operario debe rellenar el campo de notas "
            "para poder guardar la justificación de la laguna."
        ),
    )
    is_justified = models.BooleanField(
        default=True,
        verbose_name="Justificada",
        help_text=(
            "Indica si esta categoría de ausencia se considera justificada "
            "a efectos de informes de incidencias de jornada."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text=(
            "Desactivar en lugar de eliminar para preservar referencias "
            "históricas en WorkdayGap ya registrados."
        ),
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
        help_text=(
            "Posición de esta categoría en el selector del operario. "
            "Menor número = aparece antes. Las categorías con el mismo "
            "orden se ordenan alfabéticamente por etiqueta."
        ),
    )

    class Meta:
        verbose_name = "Categoría de ausencia"
        verbose_name_plural = "Categorías de ausencia"
        unique_together = [("company", "code")]
        ordering = ["company__name", "order", "label"]

    def __str__(self):
        status = "" if self.is_active else " [inactiva]"
        return f"{self.company.name} — {self.label}{status}"


# ---------------------------------------------------------------------------
# 20. INBOUND CALL LOG — Record of every inbound IVR call and its outcome.
#     Registro de cada llamada entrante al IVR y su resultado.
# ---------------------------------------------------------------------------

class InboundCallLog(models.Model):
    """
    Persists a structured record of every inbound call handled by the IVR
    agent (María). Captures technical identifiers (Twilio SIDs), caller data
    inferred by Gemini during the conversation, the call type, the associated
    section and, when applicable, the BreakdownTicket created.

    Created by the submit_call_summary Gemini function call at the end of
    every conversation, regardless of outcome (ticket, transfer, info, etc.).

    Read-only from the panel — no creation or editing from the UI.
    Only deletion is permitted (ADMIN role only).
    ---
    Persiste un registro estructurado de cada llamada entrante gestionada por
    el agente IVR (María). Captura identificadores técnicos (SIDs de Twilio),
    datos del llamante inferidos por Gemini durante la conversación, el tipo
    de llamada, la sección asociada y, cuando aplica, el BreakdownTicket creado.

    Creado por la function call submit_call_summary de Gemini al final de cada
    conversación, independientemente del resultado (ticket, transferencia,
    información, etc.).

    Solo lectura desde el panel — sin creación ni edición desde la UI.
    Solo se permite el borrado (exclusivamente rol ADMIN).
    """

    # ── Call type choices ────────────────────────────────────────────────────
    TYPE_BREAKDOWN  = "BREAKDOWN"   # Internal fleet breakdown → BreakdownTicket
    TYPE_TRANSFER   = "TRANSFER"    # Transfer to section contact
    TYPE_INFO       = "INFO"        # Informational only (schedules, services)
    TYPE_OTHER      = "OTHER"       # Ambiguous or unclassified
    TYPE_CHOICES = [
        (TYPE_BREAKDOWN, "Avería interna"),
        (TYPE_TRANSFER,  "Transferencia"),
        (TYPE_INFO,      "Información"),
        (TYPE_OTHER,     "Otro"),
    ]

    # ── Outcome choices ──────────────────────────────────────────────────────
    OUTCOME_TICKET_CREATED = "TICKET_CREATED"
    OUTCOME_TRANSFERRED    = "TRANSFERRED"
    OUTCOME_INFO_GIVEN     = "INFO_GIVEN"
    OUTCOME_ABANDONED      = "ABANDONED"
    OUTCOME_OTHER          = "OTHER"
    OUTCOME_CHOICES = [
        (OUTCOME_TICKET_CREATED, "Ticket creado"),
        (OUTCOME_TRANSFERRED,    "Transferido"),
        (OUTCOME_INFO_GIVEN,     "Información facilitada"),
        (OUTCOME_ABANDONED,      "Llamada abandonada"),
        (OUTCOME_OTHER,          "Otro"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="inbound_call_logs",
        verbose_name="Empresa",
        help_text="Empresa que recibió la llamada.",
    )
    # ── Technical identifiers ────────────────────────────────────────────────
    call_sid = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Call SID",
        help_text="Identificador único de llamada Twilio (CA...).",
    )
    twilio_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Número Twilio",
        help_text="Número E.164 de Twilio que recibió la llamada.",
    )
    caller_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Número llamante (CLI)",
        help_text=(
            "Número E.164 del llamante capturado por Twilio (CLI). "
            "Puede no coincidir con el número real del chófer si llamó "
            "desde un teléfono ajeno."
        ),
    )
    started_at = models.DateTimeField(
        verbose_name="Inicio de llamada",
        help_text="Momento en que Twilio conectó la llamada al bridge.",
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fin de llamada",
        help_text="Momento en que la sesión Gemini Live finalizó.",
    )
    # ── Caller data inferred by Gemini ───────────────────────────────────────
    caller_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Nombre del llamante",
        help_text="Nombre y apellidos inferidos por Gemini durante la conversación.",
    )
    caller_phone_reported = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Teléfono facilitado por el llamante",
        help_text=(
            "Número de teléfono que el llamante indicó verbalmente, si difiere "
            "del CLI o si llamó desde un teléfono ajeno."
        ),
    )
    call_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Motivo de la llamada",
        help_text="Resumen breve del motivo inferido por Gemini.",
    )
    # ── Classification ───────────────────────────────────────────────────────
    call_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_OTHER,
        verbose_name="Tipo de llamada",
        help_text="Clasificación del tipo de llamada inferida por Gemini.",
    )
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default=OUTCOME_OTHER,
        verbose_name="Resultado",
        help_text="Resultado final de la llamada.",
    )
    # ── Related objects ──────────────────────────────────────────────────────
    section = models.ForeignKey(
        "Section",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_call_logs",
        verbose_name="Sección",
        help_text="Sección identificada por Gemini como destino de la llamada.",
    )
    breakdown_ticket = models.ForeignKey(
        "chat.BreakdownTicket",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_call_logs",
        verbose_name="Ticket de avería",
        help_text="Ticket de avería creado durante esta llamada, si aplica.",
    )
    # ── Free-form summary ────────────────────────────────────────────────────
    raw_summary = models.TextField(
        blank=True,
        default="",
        verbose_name="Resumen de la conversación",
        help_text=(
            "Resumen libre generado por Gemini al final de la conversación. "
            "Incluye todos los datos capturados y el resultado de la llamada."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Registro de llamada entrante"
        verbose_name_plural = "Registros de llamadas entrantes"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        name = self.caller_name or self.caller_number or "Desconocido"
        return f"{self.company.name} — {name} — {self.started_at:%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------------------
# 21. WORKSHOP FAMILY MAPPING — Catalogue-family → workshop-family routing.
#     Mapeo de familia de catálogo a familia de taller para routing automático.
# ---------------------------------------------------------------------------

class WorkshopFamilyMapping(models.Model):
    """
    Maps a MachineAsset catalogue family string (e.g. "PLATAFOR", "CARR",
    "MOVILES") to a workshop family (MECHANICAL or ELEVATION). Used by the
    breakdown bot routing logic to determine which WhatsApp group receives
    the breakdown ticket card.

    Configurable from Django Admin without code changes. If a catalogue
    family is not mapped, the routing service falls back to MECHANICAL.

    Uniqueness is enforced on (company, catalogue_family) so that each
    family has exactly one routing target per company.

    ---

    Mapea una cadena de familia del catálogo de MachineAsset (p.ej. "PLATAFOR",
    "CARR", "MOVILES") a una familia de taller (MECHANICAL o ELEVATION). Lo usa
    la lógica de routing del bot de averías para determinar qué grupo WhatsApp
    recibe la tarjeta del ticket de avería.

    Configurable desde Django Admin sin cambios de código. Si una familia del
    catálogo no está mapeada, el servicio de routing usa MECHANICAL como fallback.

    La unicidad se impone sobre (company, catalogue_family) para que cada
    familia tenga exactamente un destino de routing por empresa.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="workshop_family_mappings",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este mapeo de familia de taller.",
    )
    catalogue_family = models.CharField(
        max_length=100,
        verbose_name="Familia de catálogo",
        help_text=(
            "Valor exacto del campo MachineAsset.family tal como figura en el "
            "catálogo importado (p.ej. PLATAFOR, CARR, MOVILES, AUTOCARG). "
            "La comparación es sensible a mayúsculas/minúsculas."
        ),
    )
    workshop_family = models.CharField(
        max_length=20,
        choices=CompanyUser.WORKSHOP_FAMILY_CHOICES,
        verbose_name="Familia de taller destino",
        help_text=(
            "Grupo de taller al que se enruta el ticket de avería cuando la "
            "máquina afectada pertenece a esta familia de catálogo. "
            "MECHANICAL: Taller Mecánico. ELEVATION: Taller Elevación."
        ),
    )
    notes = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Notas",
        help_text=(
            "Descripción opcional del tipo de maquinaria incluida en esta "
            "familia (p.ej. 'Plataformas tijera eléctricas y articuladas')."
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
        verbose_name = "Mapeo de familia de taller"
        verbose_name_plural = "Mapeos de familia de taller"
        unique_together = [("company", "catalogue_family")]
        ordering = ["company__name", "catalogue_family"]

    def __str__(self) -> str:
        return (
            f"{self.company.name} — {self.catalogue_family} "
            f"→ {self.get_workshop_family_display()}"
        )





