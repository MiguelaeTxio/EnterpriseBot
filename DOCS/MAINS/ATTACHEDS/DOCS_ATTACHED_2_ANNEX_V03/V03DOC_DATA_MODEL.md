# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V03/V03DOC_DATA_MODEL.md

# MODELO DE DATOS IVR MULTIEMPRESA
# MULTICOMPANY IVR DATA MODEL
---
# Especificación técnica completa de los modelos Django del Hito 3.
# Complete technical specification of the Django models for Milestone 3.
# Última actualización / Last update: 2026-04-13 — Extensiones de modelo acordadas en sesión.

## 1. Diagrama de Relaciones / Relationship Diagram

    Company
      ├── CompanyUser (FK→auth.User)
      │     └── PresenceStatus
      ├── CorporateVoiceProfile
      ├── DataCaptureSet
      ├── Section (M2M→Contact, FK→DataCaptureSet)
      │     └── SectionSchedule          ← NUEVO
      ├── Contact (FK→CompanyUser nullable)
      ├── CallFlow
      ├── PhoneNumber (FK→CallFlow)
      └── BlockedCaller                  ← NUEVO

## 2. Especificación de Campos / Field Specification

### Company
    name            CharField(max_length=200)
    slug            SlugField(unique=True)          # generado automáticamente desde name
    logo            ImageField(nullable)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### CompanyUser
    company         ForeignKey(Company, on_delete=CASCADE)
    user            OneToOneField(auth.User, on_delete=CASCADE)
    role            CharField(choices=[('ADMIN','Admin'),('OPERATOR','Operador')])
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Constraint: user.is_staff MUST be False para CompanyUser.
    El acceso a /admin/ se bloquea via middleware CompanyUserAdminBlockMiddleware.

### Contact
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    phone_number    CharField(max_length=20)        # formato E.164: +34XXXXXXXXX
    email           EmailField(blank=True)           # NUEVO — para notificaciones por correo
    gender          CharField(max_length=1,          # NUEVO — para tratamiento Sr./Sra.
                              choices=[('M','Sr.'),('F','Sra.')],
                              blank=True)
    is_internal     BooleanField(default=False)
    company_user    ForeignKey(CompanyUser, null=True, blank=True, on_delete=SET_NULL)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Constraint: si is_internal=True, company_user no puede ser null.
    Tratamiento verbal por Alia: "Sr. {name}" o "Sra. {name}" según gender.
    Si gender está vacío, Alia usa el nombre sin tratamiento.

### Section
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    description     TextField(blank=True)
    contacts        ManyToManyField(Contact, blank=True)
    data_capture_set ForeignKey(DataCaptureSet, null=True, blank=True, on_delete=SET_NULL)
    is_24h          BooleanField(default=False)      # NUEVO — cortocircuita comprobación de horario
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Lógica de disponibilidad:
    - Si is_24h=True → sección siempre disponible, ignorar SectionSchedule.
    - Si is_24h=False → consultar SectionSchedule para el weekday y hora actual.
    - Si no hay SectionSchedule definido para el día actual → sección NO disponible.

### SectionSchedule  ← NUEVO
    section         ForeignKey(Section, on_delete=CASCADE, related_name='schedules')
    weekday         IntegerField(choices=[
                        (0, 'Lunes'),
                        (1, 'Martes'),
                        (2, 'Miércoles'),
                        (3, 'Jueves'),
                        (4, 'Viernes'),
                        (5, 'Sábado'),
                        (6, 'Domingo'),
                    ])
    time_open       TimeField()
    time_close      TimeField()
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Constraint: puede existir más de un registro por (section, weekday) para
    modelar franjas horarias partidas (ej. 08:00-14:00 y 16:00-20:00).
    La sección se considera disponible si la hora actual cae en CUALQUIERA
    de las franjas definidas para el weekday en curso.

    Ejemplo Grupo Álvarez — Administración:
        weekday=0 (Lunes),    time_open=08:00, time_close=14:00
        weekday=0 (Lunes),    time_open=16:00, time_close=19:00
        weekday=1 (Martes),   time_open=08:00, time_close=14:00
        weekday=1 (Martes),   time_open=16:00, time_close=19:00
        ...
        weekday=5 (Sábado),   time_open=08:00, time_close=13:00

    Ejemplo Grupo Álvarez — Asistencia en carretera:
        Section.is_24h=True  →  sin registros SectionSchedule necesarios.

### PhoneNumber
    company         ForeignKey(Company, on_delete=CASCADE)
    number          CharField(max_length=20, unique=True)  # formato E.164
    friendly_name   CharField(max_length=200, blank=True)
    call_flow       ForeignKey(CallFlow, null=True, blank=True, on_delete=SET_NULL)
    capabilities    CharField(max_length=10, default='VOICE',
                              choices=[('VOICE','Solo Voz'),
                                       ('SMS','Solo SMS'),
                                       ('BOTH','Voz y SMS')])
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### CallFlow
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    system_instruction  TextField()
    initial_greeting    TextField()
    notification_contact ForeignKey(Contact, null=True, blank=True,  # NUEVO
                                    on_delete=SET_NULL,               # persona designada para
                                    related_name='notification_flows') # actividad no recogida
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    notification_contact: Contact designado para recibir notificación (llamada saliente
    + correo) cuando una llamada no encaja en ninguna sección conocida del CallFlow.

### PresenceStatus
    company_user    ForeignKey(CompanyUser, on_delete=CASCADE)
    status          CharField(choices=[
                        ('AVAILABLE',         'Disponible'),
                        ('IN_MEETING',        'Reunido'),
                        ('BUSY_UNTIL',        'Ocupado hasta'),
                        ('ABSENT_SCHEDULED',  'Ausente programado'),
                        ('ABSENT_VACATION',   'Vacaciones'),
                    ])
    starts_at       DateTimeField(default=now)
    ends_at         DateTimeField(null=True, blank=True)
    reminder_sent_at DateTimeField(null=True, blank=True)
    created_at      DateTimeField(auto_now_add=True)

    Constraint: solo un PresenceStatus activo por CompanyUser en cada momento.
    Un PresenceStatus es activo si: starts_at <= now AND (ends_at IS NULL OR ends_at > now).

### CorporateVoiceProfile
    company         ForeignKey(Company, on_delete=CASCADE, unique=True)
    tone_guidelines TextField()
    sample_responses JSONField(default=list)
    forbidden_phrases JSONField(default=list)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### DataCaptureSet
    company         ForeignKey(Company, on_delete=CASCADE)
    section         ForeignKey(Section, null=True, blank=True, on_delete=SET_NULL)
    name            CharField(max_length=200)
    fields          JSONField(default=list)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Campos base comunes a todas las secciones (heredados de plantilla base):
    - nombre_cliente    (texto libre)
    - telefono_contacto (formato E.164)
    - ubicacion         (texto libre conversacional — calle, municipio, referencia)
    - descripcion       (texto libre — motivo de la llamada)

    Campos específicos por sección (ejemplos Grupo Álvarez):
    - Grúas:      tipo_grua, tonelaje_estimado
    - Asistencia: tipo_vehiculo, matricula, averia_descrita
    - Elevación:  tipo_maquina, altura_requerida

### BlockedCaller  ← NUEVO
    company         ForeignKey(Company, on_delete=CASCADE)
    phone_number    CharField(max_length=20)        # formato E.164
    reason          TextField(blank=True)           # motivo del bloqueo
    blocked_at      DateTimeField(auto_now_add=True)
    blocked_until   DateTimeField()                 # default: blocked_at + 24h
    blocked_by      ForeignKey(auth.User, null=True, blank=True, on_delete=SET_NULL)
    created_at      DateTimeField(auto_now_add=True)

    Lógica de bloqueo:
    - Al inicio de cada llamada entrante, build_live_config() comprueba si el
      número llamante (From) tiene un BlockedCaller activo para la company.
    - Un BlockedCaller es activo si: blocked_until > now().
    - Si está bloqueado: Alia responde con mensaje estándar educado y termina.
    - La duración por defecto es 24 horas. Configurable por el ADMIN desde el panel.
    - El ADMIN puede desbloquear manualmente antes del vencimiento desde el panel.
    - Gestión desde el panel: listado de bloqueados activos, alta manual de bloqueo,
      desbloqueo manual, historial de bloqueos expirados.

---

## 3. Migraciones / Migrations

Orden de creación obligatorio para respetar dependencias FK:
1. Company
2. CompanyUser
3. CorporateVoiceProfile
4. DataCaptureSet (sin FK a Section aún)
5. Section
6. Contact
7. CallFlow
8. PhoneNumber
9. PresenceStatus
10. SectionSchedule   ← NUEVO (depende de Section)
11. BlockedCaller     ← NUEVO (depende de Company y auth.User)

Nota: DataCaptureSet se crea sin FK a Section para evitar dependencia circular.
Section tiene FK a DataCaptureSet. La relación inversa se navega desde Section.

Migraciones de extensión sobre modelos existentes:
- Contact: añadir campos email y gender (ALTER TABLE — migración incremental).
- Section: añadir campo is_24h (ALTER TABLE — migración incremental).
- CallFlow: añadir campo notification_contact (ALTER TABLE — migración incremental).

---

## 4. Flujo de Llamada Entrante / Inbound Call Flow

### 4.1. Comprobación de número bloqueado
Al recibir cualquier llamada entrante, antes de cualquier otra acción:
    1. Extraer número llamante (From) del POST de Twilio.
    2. Consultar BlockedCaller activo para (company, phone_number=From).
    3. Si bloqueado → Alia responde mensaje estándar educado → termina llamada.
    4. Si no bloqueado → continuar flujo normal.

### 4.2. Tipos de llamada y comportamiento

| Tipo de llamada                  | Comportamiento                                                                 |
|----------------------------------|--------------------------------------------------------------------------------|
| Servicio conocido — en horario   | Toma de datos conversacional → llamada saliente + correo al responsable        |
| Servicio conocido — fuera horario| Informa al cliente → toma de datos → llamada saliente + correo responsable     |
| Persona determinada              | Localiza Contact por nombre → comprueba PresenceStatus → transfiere o mensaje  |
| Actividad no recogida            | Toma de datos → notifica a notification_contact del CallFlow                   |
| Fuera de actividad empresa       | Respuesta educada → cierre de llamada                                          |
| Número bloqueado                 | Mensaje estándar educado → cierre inmediato                                    |
| Modo demo                        | Frase clave → DTMF 7463 → simulación sin acciones reales                      |

### 4.3. Toma de datos conversacional
Alia recoge los siguientes datos de forma conversacional natural,
sin formatos ni instrucciones explícitas al llamante:
    1. Nombre del cliente.
    2. Teléfono de contacto (si difiere del número llamante).
    3. Descripción del servicio necesario.
    4. Ubicación: nombre de vía, calle, municipio o referencia de lugar
       (texto libre — sin coordenadas GPS en fase actual).
    5. Campos adicionales según DataCaptureSet de la sección detectada.

Cuando WhatsApp esté operativo (Hito 4):
    - La ubicación conversacional se enriquece con localización GPS nativa
      de WhatsApp + Grounding Google Maps para cálculo de precios y rutas.

### 4.4. Notificación al responsable
Una vez completada la toma de datos, Alia notifica al responsable de la sección:
    1. Llamada saliente Twilio al teléfono del Contact responsable.
       Alia lee el resumen: nombre cliente, teléfono, servicio, ubicación.
    2. Correo electrónico al Contact.email del responsable con el resumen completo.
    Cuando WhatsApp esté operativo: mensaje WhatsApp al responsable (sustituye al correo).

### 4.5. Modo demo
    1. Llamante pronuncia frase clave: "Yo soy tu padre".
    2. Alia responde: "Introduzca la clave maestra."
    3. Llamante introduce DTMF: 7463.
    4. Alia confirma activación del modo demo.
    5. Alia simula el flujo IVR completo sin ejecutar acciones reales:
       - No realiza llamadas salientes.
       - No envía correos.
       - No registra datos en BD.
       - Describe verbalmente lo que haría en cada paso.
