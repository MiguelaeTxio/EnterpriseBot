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

Número de teléfono Twilio vinculado a la empresa. Cada número tiene asociado
un `CallFlow` que determina el comportamiento del IVR al recibir una llamada.

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

## SECCIÓN 5 — HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA)

### Paso 1 — Nueva app Django: `ivr_config`
Crear la app `ivr_config` dentro del proyecto EnterpriseBot:
    python manage.py startapp ivr_config
Registrarla en `INSTALLED_APPS` de `enterprise_core/settings.py`.

### Paso 2 — Modelos Django
Implementar en `ivr_config/models.py` los siguientes modelos en este orden
exacto (respetando dependencias FK):
1. `Company`
2. `CompanyUser`
3. `CorporateVoiceProfile`
4. `DataCaptureSet`
5. `Section`
6. `Contact`
7. `CallFlow`
8. `PhoneNumber`
9. `PresenceStatus`

Todos los modelos deben incluir:
- `__str__` en inglés con formato `f"{self.company.name} — {self.name}"`.
- `class Meta` con `verbose_name` y `verbose_name_plural` en castellano.
- Docstring bilingüe (EN/ES) completo.
- `created_at = models.DateTimeField(auto_now_add=True)` en todos.
- `updated_at = models.DateTimeField(auto_now=True)` en todos excepto `PresenceStatus`.

### Paso 3 — Migraciones
    python -m dotenv run python manage.py makemigrations ivr_config
    python -m dotenv run python manage.py migrate

### Paso 4 — Superusuario inicial
    python -m dotenv run python manage.py createsuperuser
Datos: usuario `admin`, email del proyecto, contraseña segura.
Registrar credenciales en el `.env` bajo `SUPERUSER_USERNAME` y `SUPERUSER_EMAIL`.

### Paso 5 — Admin Django para gestión interna
Registrar todos los modelos de `ivr_config` en `ivr_config/admin.py` con
`list_display`, `list_filter` y `search_fields` apropiados. Esto permite la
gestión interna vía `/admin/` exclusivamente para el superusuario de la plataforma.

### Paso 6 — Seed de datos piloto (Grupo Álvarez)
Crear un script de seed `ivr_config/management/commands/seed_grupo_alvarez.py`
que cree los datos iniciales del piloto:
- `Company`: Grupo Álvarez
- `CompanyUser`: superusuario administrador de la empresa (1 usuario inicial)
- `Section`: Elevación, Asistencia (las dos secciones actualmente hardcodeadas)
- `CallFlow`: flujo actual de Alia con el `SYSTEM_INSTRUCTION` y
  `INITIAL_GREETING_TEXT` actuales migrados desde `vox_bridge/services.py`
- `CorporateVoiceProfile`: tono profesional, cálido y conciso — extraído del
  `SYSTEM_INSTRUCTION` actual

---

## SECCIÓN 6 — PENDIENTES DIFERIDOS

Los siguientes elementos se abordarán en sesiones posteriores, preferiblemente
tras reunión de refinamiento con el Grupo Álvarez:

1. `DataCaptureSet` por sección: Estructura exacta de campos para Elevación,
   Asistencia y Grúas. Campos comunes heredados de plantilla base.
2. Recepción de ubicaciones: Integración de geolocalización en el flujo de
   toma de datos.
3. Panel `/panel/` personalizado: Vistas class-based para gestión autónoma
   por empresa (Paso 5 de la hoja de ruta de sesiones siguientes).
4. Sistema de recordatorios de presencia: Integración Celery + Twilio SMS/WhatsApp
   para el mecanismo de "¿sigues reunido?".
5. Registro de usuarios empresa: Flujo de alta de nuevos `CompanyUser` con
   invitación por email.
6. Números españoles Twilio: Configuración de los 2 números ES aprobados
   (entrega estimada 1-3 días desde 2026-04-07) y calibración VAD para líneas ES.

---

## SECCIÓN 7 — PAH — REGISTRO DE SESIÓN
**Título:** Inicio del Hito 3 — Arquitectura IVR Multiempresa Configurable
**Descripción:** Sesión de arranque del Hito 3. Se define la arquitectura completa
del sistema IVR configurable desde producción: modelo de datos multiempresa,
sistema de presencia con gestión de ausencias, panel de administración personalizado
y mecanismo de inyección dinámica de configuración en Gemini Live. Se crea la
constelación documental satélite inicial del hito.
