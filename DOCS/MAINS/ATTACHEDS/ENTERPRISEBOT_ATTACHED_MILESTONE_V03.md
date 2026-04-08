# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# ENTERPRISEBOT — ANEXO HITO V03 — IVR CONVERSACIONAL CONFIGURABLE DESDE PRODUCCIÓN
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-07

---

## SECCIÓN 1 — VISIÓN DEL HITO

Este hito transforma EnterpriseBot de un sistema IVR de demostración con configuración
hardcodeada en un producto multiempresa completamente configurable desde producción.
El objetivo es que cada empresa cliente pueda gestionar de forma autónoma su flujo de
llamadas, sus usuarios, sus secciones de negocio, sus contactos telefónicos y su
presencia en tiempo real — todo desde un panel de administración personalizado, sin
acceso al admin estándar de Django.

La empresa piloto es **Grupo Álvarez** (Grúas Álvarez), con la que se refinará la
configuración en sesiones posteriores.

---

## SECCIÓN 2 — ARQUITECTURA DE DATOS

### 2.1. Modelo de Entidades Principal

#### `Company` — Empresa cliente
    id, name, slug, logo, is_active, created_at

Entidad raíz del sistema multiempresa. Todo dato de configuración IVR pertenece
a una `Company`.

#### `CompanyUser` — Usuario de empresa
    id, company (FK), user (FK→auth.User), role (ADMIN|OPERATOR), is_active

- `ADMIN`: puede configurar la empresa completa.
- `OPERATOR`: solo puede gestionar su propia presencia.
- **PROHIBIDO** el acceso al `/admin/` estándar de Django para cualquier `CompanyUser`.

#### `Contact` — Persona contactable
    id, company (FK), name, phone_number, is_internal (bool), company_user (FK nullable)

Personas a las que el IVR puede llamar o enviar mensajes. Los usuarios internos
(`is_internal=True`) tienen un `CompanyUser` asociado y pueden tener `PresenceStatus`.
Los trabajadores externos (`is_internal=False`) son contactos sin acceso al sistema.

#### `Section` — Sección o departamento
    id, company (FK), name, description, contacts (M2M→Contact),
    data_capture_set (FK nullable), is_active

Unidad de enrutamiento del IVR. Ejemplos: Elevación, Asistencia, Grúas.
Cada sección tiene un conjunto de toma de datos propio (`DataCaptureSet`) que
se definirá con la empresa piloto en sesiones posteriores.

#### `PhoneNumber` — Número Twilio asignado
    id, company (FK), number, friendly_name, call_flow (FK), is_active

Número de teléfono Twilio vinculado a la empresa. Una empresa puede tener
**cualquier número de líneas Twilio simultáneas** — no existe límite superior.
Cada `PhoneNumber` tiene asociado de forma independiente un `CallFlow` propio,
lo que permite que una misma empresa opere centralitas con comportamientos IVR
distintos en cada número (24/7, horario restringido, idioma diferente, etc.).

El comando de seed acepta la lista de números como argumento dinámico
`--phone-numbers` en formato E.164, admitiendo uno o varios números en una
única ejecución:
    python manage.py seed_grupo_alvarez --phone-numbers +12603466780 +34XXXXXXXXX

#### `CallFlow` — Flujo IVR
    id, company (FK), name, system_instruction (TextField),
    initial_greeting (TextField), is_active

Define la personalidad y el comportamiento del agente IVR para un número concreto.
El `system_instruction` y el `initial_greeting` se inyectan dinámicamente en el
`LiveConnectConfig` de Gemini en tiempo de llamada, sustituyendo las constantes
hardcodeadas actuales (`SYSTEM_INSTRUCTION`, `INITIAL_GREETING_TEXT`) de
`vox_bridge/services.py`.

#### `PresenceStatus` — Estado de presencia del usuario
    id, company_user (FK), status (AVAILABLE|IN_MEETING|BUSY_UNTIL|
    ABSENT_SCHEDULED|ABSENT_VACATION), starts_at, ends_at (nullable),
    reminder_sent_at (nullable), created_at, updated_at

Estados posibles:
- `AVAILABLE`: disponible, estado por defecto.
- `IN_MEETING`: reunido. Sin `ends_at` → Celery envía recordatorio a las 3 horas.
- `BUSY_UNTIL`: ocupado hasta hora concreta. Expira automáticamente.
- `ABSENT_SCHEDULED`: ausente programado de fecha a fecha.
- `ABSENT_VACATION`: vacaciones de fecha a fecha.

Solo puede existir un `PresenceStatus` activo por usuario en cada momento.

#### `CorporateVoiceProfile` — Perfil de voz corporativa
    id, company (FK), tone_guidelines (TextField), sample_responses (JSONField),
    forbidden_phrases (JSONField), is_active

Semillero de respuestas y directrices de sonoridad corporativa. Se inyecta en el
`system_instruction` del `CallFlow` para que la IA mantenga la identidad de marca.

#### `DataCaptureSet` — Conjunto de toma de datos
    id, company (FK), section (FK nullable), name, fields (JSONField)

Define los campos que el IVR debe recopilar del cliente durante la llamada.
Cada sección puede tener su propio `DataCaptureSet` con campos específicos.
Los campos comunes (nombre, teléfono) se heredan de una plantilla base.
PENDIENTE DE DEFINICIÓN: La estructura exacta de `fields` y los conjuntos
por sección se definirán en sesiones posteriores con el Grupo Álvarez.

---

## SECCIÓN 3 — ARQUITECTURA DE AUTENTICACIÓN Y PANEL

### 3.1. Autenticación
- Los `CompanyUser` se autentican mediante el sistema de autenticación estándar
  de Django (`auth.User`), pero con un middleware o mixin que bloquea el acceso
  a `/admin/` si el usuario no tiene `is_staff=True`.
- El superusuario de la plataforma (`is_staff=True`, `is_superuser=True`) tiene
  acceso completo a todo, incluyendo el admin de Django.
- Los `CompanyUser` acceden exclusivamente al panel personalizado en una ruta
  dedicada `/panel/`.

### 3.2. Panel de Administración Personalizado (`/panel/`)
Vistas Django class-based (no Django admin) que permiten a cada empresa:
- Gestionar sus usuarios (`CompanyUser`).
- Configurar sus secciones (`Section`).
- Gestionar sus contactos (`Contact`).
- Configurar sus números Twilio (`PhoneNumber`) y flujos (`CallFlow`).
- Editar su perfil de voz corporativa (`CorporateVoiceProfile`).
- Ver y gestionar el estado de presencia de sus usuarios (`PresenceStatus`).

### 3.3. Gestión de Presencia
- Cada usuario puede activar/desactivar su estado desde el panel o desde
  un endpoint simple (para futura integración con botón físico o app móvil).
- Al activar `IN_MEETING` sin `ends_at`: Celery Beat programa una tarea que
  a las 3 horas envía un recordatorio (SMS/WhatsApp vía Twilio) preguntando
  si sigue reunido, con opciones de respuesta.
- Al activar `BUSY_UNTIL`: Celery Beat programa la expiración automática a
  la hora indicada.
- `ABSENT_SCHEDULED` y `ABSENT_VACATION`: el sistema gestiona la activación
  y desactivación automática según el rango de fechas, sin recordatorios.

---

## SECCIÓN 4 — INYECCIÓN DINÁMICA EN EL IVR

### 4.1. Flujo de llamada entrante con configuración dinámica
Cuando Twilio llama al endpoint `/api/vox/inbound/`:
1. La vista identifica el número Twilio receptor (`PhoneNumber`).
2. Carga el `CallFlow` asociado al número.
3. Construye el `SYSTEM_INSTRUCTION` dinámico combinando:
   - `CallFlow.system_instruction` (base del flujo).
   - `CorporateVoiceProfile.tone_guidelines` + `sample_responses` (sonoridad).
   - Estado de presencia activo de cada `Contact` interno relevante.
4. Construye el `INITIAL_GREETING` desde `CallFlow.initial_greeting`.
5. Inyecta ambos en el `LiveConnectConfig` de Gemini en tiempo de llamada.

### 4.2. Impacto en `vox_bridge/services.py`
Las constantes hardcodeadas actuales:
    SYSTEM_INSTRUCTION = "Eres Alia..."
    INITIAL_GREETING_TEXT = "El llamante acaba de contestar..."
Serán reemplazadas por un método de carga dinámica desde la base de datos,
recibiendo el número Twilio como parámetro de entrada.

---

## SECCIÓN 5 — HOJA DE RUTA (SESIÓN 2026-04-08) — COMPLETADA ✅

### Paso 1 — Nueva app Django: `ivr_config` ✅ COMPLETADO
App creada con `python manage.py startapp ivr_config` y registrada en
`INSTALLED_APPS` de `enterprise_core/settings.py`.
Dependencia añadida: `Pillow` (requerido por `ImageField` en `Company.logo`).

### Paso 2 — Modelos Django ✅ COMPLETADO
Implementados en `ivr_config/models.py` los 9 modelos en orden estricto de
dependencias FK:
1. `Company`
2. `CompanyUser`
3. `CorporateVoiceProfile`
4. `DataCaptureSet`
5. `Section`
6. `Contact`
7. `CallFlow`
8. `PhoneNumber`
9. `PresenceStatus`

Todos incluyen docstring bilingüe, `__str__`, `class Meta` con verbose names
en castellano, `created_at` y `updated_at` (excepto `PresenceStatus`).

### Paso 3 — Migraciones ✅ COMPLETADO
    python -m dotenv run python manage.py makemigrations ivr_config
    python -m dotenv run python manage.py migrate
WARNING conocido no bloqueante: `mysql.W002` — MySQL Strict Mode no activado.
Queda como deuda técnica menor para una sesión futura.

### Paso 4 — Superusuario inicial ✅ COMPLETADO
Superusuario `admin` creado con email `nummenor@proton.me`.
Credenciales registradas en `.env` bajo `SUPERUSER_USERNAME` y `SUPERUSER_EMAIL`.

### Paso 5 — Admin Django para gestión interna ✅ COMPLETADO
Todos los modelos de `ivr_config` registrados en `ivr_config/admin.py` con
`list_display`, `list_filter` y `search_fields` apropiados por entidad.

### Paso 6 — Seed de datos piloto (Grupo Álvarez) ✅ COMPLETADO
Script `ivr_config/management/commands/seed_grupo_alvarez.py` creado y ejecutado.
Acepta `--phone-numbers` como argumento dinámico E.164 (uno o varios números).
Ejecutado con:
    python manage.py seed_grupo_alvarez --phone-numbers +12603466780
Registros creados en BD:
- `Company`: Grupo Álvarez
- `CompanyUser`: alvarez_admin (ADMIN, is_staff=False, contraseña inutilizable)
- `CorporateVoiceProfile`: tono profesional, cálido y conciso
- `CallFlow`: Recepción principal — Alia (SYSTEM_INSTRUCTION e INITIAL_GREETING
  migrados literalmente desde `vox_bridge/services.py`)
- `PhoneNumber`: +12603466780 vinculado al CallFlow principal
- `Section`: Elevación, Asistencia

---

## SECCIÓN 6 — PENDIENTES DIFERIDOS

Los siguientes elementos se abordarán en sesiones posteriores, preferiblemente
tras reunión de refinamiento con el Grupo Álvarez:

1. `DataCaptureSet` por sección: Estructura exacta de campos para Elevación,
   Asistencia y Grúas. Campos comunes heredados de plantilla base.
2. Recepción de ubicaciones: Integración de geolocalización en el flujo de
   toma de datos.
3. Panel `/panel/` personalizado: Vistas class-based para gestión autónoma
   por empresa.
4. Sistema de recordatorios de presencia: Integración Celery + Twilio SMS/WhatsApp
   para el mecanismo de "¿sigues reunido?".
5. Registro de usuarios empresa: Flujo de alta de nuevos `CompanyUser` con
   invitación por email.
6. Números españoles Twilio: Configuración de los 2 números ES aprobados
   (entrega estimada 1-3 días desde 2026-04-07) y calibración VAD para líneas ES.
   Cuando lleguen, ejecutar:
       python manage.py seed_grupo_alvarez --phone-numbers +34XXXXXXXXX +34XXXXXXXXX
7. Deuda técnica — `mysql.W002`: Activación del Strict Mode de MySQL para la
   conexión `default`. Consultar documentación Django:
   https://docs.djangoproject.com/en/5.2/ref/databases/#mysql-sql-mode

---

## SECCIÓN 7 — HOJA DE RUTA SIGUIENTE SESIÓN

### Paso 7 — Cargador dinámico `ivr_config/services.py`
Implementar la función `build_live_config(twilio_number: str) -> tuple[str, str]`
según la especificación de `V03DOC_DYNAMIC_IVR_INJECTION.md`:
- Obtener `PhoneNumber` activo por `twilio_number`.
- Obtener `CallFlow` asociado.
- Obtener `CorporateVoiceProfile` de la `Company`.
- Consultar `PresenceStatus` activo de todos los `Contact` internos.
- Ensamblar `system_instruction` dinámico con contexto de presencia.
- Retornar `(system_instruction, initial_greeting)`.
- Implementar fallback de seguridad con constantes hardcodeadas actuales
  (`SYSTEM_INSTRUCTION_FALLBACK`, `INITIAL_GREETING_FALLBACK`).

### Paso 8 — Modificación de `vox_bridge/services.py`
- Añadir parámetro `twilio_number: str` al constructor de `VoiceOrchestrationService`.
- Llamar a `build_live_config(twilio_number)` en `__init__()`.
- Sustituir referencias a `SYSTEM_INSTRUCTION` y `INITIAL_GREETING_TEXT` por
  `self.system_instruction` y `self.initial_greeting_text`.
- Las constantes originales pasan a ser `SYSTEM_INSTRUCTION_FALLBACK` e
  `INITIAL_GREETING_FALLBACK`.

### Paso 9 — Modificación de `vox_bridge/views.py`
- Extraer `twilio_number = request.POST.get('To', '')` en `InboundCallView`.
- Pasar `twilio_number` al constructor de `VoiceOrchestrationService`.

---

## SECCIÓN 8 — PAH — REGISTRO DE SESIÓN
**Título:** Inicio del Hito 3 — Arquitectura IVR Multiempresa Configurable
**Descripción:** Sesión de arranque del Hito 3. Se define la arquitectura completa
del sistema IVR configurable desde producción: modelo de datos multiempresa,
sistema de presencia con gestión de ausencias, panel de administración personalizado
y mecanismo de inyección dinámica de configuración en Gemini Live. Se crea la
constelación documental satélite inicial del hito.
