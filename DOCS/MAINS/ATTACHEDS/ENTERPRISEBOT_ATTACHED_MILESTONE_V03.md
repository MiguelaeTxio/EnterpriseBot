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
hardcodeadas actuales (`SYSTEM_INSTRUCTION_FALLBACK`, `INITIAL_GREETING_FALLBACK`)
de `vox_bridge/services.py`.

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

### 4.1. Flujo de llamada entrante con configuración dinámica (IMPLEMENTADO)

El flujo real de ejecución de una llamada entrante es el siguiente:

1. Twilio realiza POST `/api/vox/inbound/`
   → `UniversalVoiceBridge.handle_twiml_post()` en `voice_sidecar_bridge.py`
   → Responde con TwiML `<Connect><Stream url="wss://{host}/media" />`

2. Twilio abre WebSocket GET `/media`
   → `UniversalVoiceBridge.handle_websocket_stream()` en `voice_sidecar_bridge.py`
   → Se inicia el bucle lector de eventos de Twilio.
   → `VoiceOrchestrationService` NO se instancia todavía.

3. Twilio envía evento `start` por el WebSocket
   → `handle_websocket_stream()` extrae `twilio_number` de `data["start"]["to"]`
   → Se instancia `VoiceOrchestrationService(twilio_number=twilio_number)`
   → En `__init__()` se llama a `build_live_config(twilio_number)`:
       a. Resuelve `PhoneNumber` activo por `twilio_number`.
       b. Carga `CallFlow` asociado.
       c. Carga `CorporateVoiceProfile` de la `Company`.
       d. Consulta `PresenceStatus` activo de todos los `Contact` internos.
       e. Ensambla `system_instruction` dinámico.
       f. Retorna `(system_instruction, initial_greeting)`.
   → Fallback automático a `SYSTEM_INSTRUCTION_FALLBACK` / `INITIAL_GREETING_FALLBACK`
     si `build_live_config()` lanza cualquier excepción.
   → Se lanza `run_voice_session()` como asyncio.Task concurrente.

4. Twilio envía eventos `media` sucesivos
   → Se reenvían a `service.receive_twilio_audio()`.

5. Twilio envía evento `stop`
   → `service.terminate_session()` señaliza el fin de sesión.

### 4.2. Archivos modificados en esta implementación
- `ivr_config/services.py` — NUEVO. Contiene `build_live_config()`.
- `vox_bridge/services.py` — `SYSTEM_INSTRUCTION` → `SYSTEM_INSTRUCTION_FALLBACK`,
  `INITIAL_GREETING_TEXT` → `INITIAL_GREETING_FALLBACK`. Constructor acepta
  `twilio_number: str`. Llama a `build_live_config()` con fallback.
- `voice_sidecar_bridge.py` — Instanciación de `VoiceOrchestrationService`
  diferida al evento `start`. Extracción de `twilio_number` de `data["start"]["to"]`.
  Guardias defensivas en todos los manejadores de eventos.

---

## SECCIÓN 5 — COMANDOS DE GESTIÓN

Los scripts standalone de laboratorio han sido migrados a comandos Django reales
bajo `vox_bridge/management/commands/`, siguiendo el estándar Django de gestión.

### Comandos disponibles
    python -m dotenv run python manage.py update_twilio_webhook
        Actualiza el webhook de voz de Twilio para que apunte al túnel ngrok
        activo. Lee la URL desde DOCS/SESSION/NGROK_URL.txt. Debe ejecutarse
        tras levantar voice_orchestrator.py y antes de cualquier prueba de
        llamada entrante.

    python -m dotenv run python manage.py trigger_outbound_call
        Dispara una llamada saliente de validación desde +12603466780 al número
        por defecto (+34688360595). Admite --to +34XXXXXXXXX para especificar
        un destino distinto.

    python -m dotenv run python manage.py seed_grupo_alvarez --phone-numbers +12603466780
        Siembra los datos piloto de Grupo Álvarez en la base de datos.
        Admite múltiples números E.164 en una única ejecución.

### Secuencia de arranque del laboratorio
    1. python voice_orchestrator.py
       Esperar: "# [READY] Puente HÍBRIDO (aiohttp) activo en puerto 8081."
       Esperar: "# [SUCCESS] TÚNEL 2026 ACTIVO: https://xxxx.ngrok-free.app"
    2. (Segunda consola) python -m dotenv run python manage.py update_twilio_webhook
    3. Realizar llamada entrante al +12603466780 o ejecutar trigger_outbound_call.

---

## SECCIÓN 6 — HITOS COMPLETADOS EN ESTE HITO

### Sesión 2026-04-07 — Inicio del Hito 3
- Diseño completo de la arquitectura de datos multiempresa.
- Implementación de los 9 modelos Django en `ivr_config/models.py`.
- Migraciones aplicadas correctamente.
- Superusuario `admin` creado.
- Admin Django configurado para todos los modelos de `ivr_config`.
- Seed de datos piloto Grupo Álvarez ejecutado correctamente.
- Constelación documental satélite inicial creada (3 documentos).

### Sesión 2026-04-08 — Inyección Dinámica + Refactorización
- `ivr_config/services.py` implementado (PEA) con `build_live_config()`.
- `vox_bridge/services.py` refactorizado (PMA): constantes → fallback,
  constructor acepta `twilio_number`, llama a `build_live_config()`.
- `voice_sidecar_bridge.py` refactorizado (PMA): instanciación diferida
  al evento `start`, extracción de `twilio_number`, guardias defensivas.
- `V03DOC_DYNAMIC_IVR_INJECTION.md` corregido (PMA): flujo real documentado.
- Scripts standalone migrados a comandos Django reales:
    `vox_bridge/management/commands/update_twilio_webhook.py`
    `vox_bridge/management/commands/trigger_outbound_call.py`
- Prueba E2E de llamada entrante real pendiente por ausencia de números
  españoles Twilio (entrega estimada 1-3 días desde 2026-04-07).

---

## SECCIÓN 7 — PENDIENTES DIFERIDOS

1. `DataCaptureSet` por sección: Estructura exacta de campos para Elevación,
   Asistencia y Grúas. Campos comunes heredados de plantilla base.
2. Recepción de ubicaciones: Integración de geolocalización en el flujo de
   toma de datos.
3. Sistema de recordatorios de presencia: Integración Celery + Twilio SMS/WhatsApp
   para el mecanismo de "¿sigues reunido?".
4. Registro de usuarios empresa: Flujo de alta de nuevos `CompanyUser` con
   invitación por email.
5. Números españoles Twilio: Configuración de los 2 números ES aprobados
   (entrega estimada 1-3 días desde 2026-04-07) y calibración VAD para líneas ES.
   Cuando lleguen, ejecutar:
       python manage.py seed_grupo_alvarez --phone-numbers +34XXXXXXXXX +34XXXXXXXXX
6. Deuda técnica — `mysql.W002`: Activación del Strict Mode de MySQL para la
   conexión `default`.
   https://docs.djangoproject.com/en/5.2/ref/databases/#mysql-sql-mode
7. Prueba E2E de llamada entrante real con número español y teléfono de empresa.

---

## SECCIÓN 8 — HOJA DE RUTA SIGUIENTE SESIÓN

### Paso 10 — App Django `panel` y estructura base

Crear la app Django `panel` con `python manage.py startapp panel` y registrarla
en `INSTALLED_APPS`. Crear la estructura de directorios:

    panel/
        __init__.py
        apps.py
        urls.py
        views.py
        mixins.py          ← Mixins de autenticación y autorización
        forms.py           ← Formularios para cada entidad
        templates/
            panel/
                base.html
                dashboard.html
                login.html
                presence/
                    status.html
                company/
                    detail.html
                users/
                    list.html
                    form.html
                sections/
                    list.html
                    form.html
                contacts/
                    list.html
                    form.html
                callflows/
                    list.html
                    form.html
                phonenumbers/
                    list.html

### Paso 11 — Middleware de bloqueo de admin para CompanyUser

Implementar `CompanyUserAdminBlockMiddleware` en `panel/middleware.py`:
- Si el usuario autenticado tiene un `CompanyUser` vinculado (es decir,
  `hasattr(request.user, 'company_user')`), bloquear el acceso a cualquier
  ruta que empiece por `/admin/` devolviendo `HttpResponseForbidden`.
- Si el usuario tiene `is_staff=True`, dejar pasar sin restricción.
- Registrar el middleware en `MIDDLEWARE` de `enterprise_core/settings.py`
  DESPUÉS de `AuthenticationMiddleware`.

### Paso 12 — Mixin de autenticación de panel (`PanelLoginRequiredMixin`)

Implementar en `panel/mixins.py`:
- `PanelLoginRequiredMixin`: hereda de `LoginRequiredMixin`. Redirige a
  `/panel/login/` si el usuario no está autenticado.
- `CompanyUserRequiredMixin`: hereda de `PanelLoginRequiredMixin`. Verifica
  que el usuario tiene un `CompanyUser` activo vinculado. Si no, redirige
  a `/panel/login/` con mensaje de error.
- `AdminRoleRequiredMixin`: hereda de `CompanyUserRequiredMixin`. Verifica
  que el `CompanyUser.role == 'ADMIN'`. Si no, devuelve 403.

### Paso 13 — Vistas base del panel

Implementar en `panel/views.py` las siguientes vistas class-based:

    PanelLoginView(LoginView)
        template_name = 'panel/login.html'
        redirect_authenticated_user = True
        next_page = '/panel/'

    PanelLogoutView(LogoutView)
        next_page = '/panel/login/'

    PanelDashboardView(CompanyUserRequiredMixin, TemplateView)
        template_name = 'panel/dashboard.html'
        Contexto: company, company_user, presencia propia activa,
        resumen de secciones activas, número de contactos.

### Paso 14 — URLs del panel

Crear `panel/urls.py` con todas las rutas del panel bajo el prefijo `/panel/`.
Incluir en `enterprise_core/urls.py` con:
    path('panel/', include('panel.urls')),

### Paso 15 — Templates base y login

Implementar `panel/templates/panel/base.html` con:
- Navegación lateral con enlaces a todas las secciones del panel.
- Indicador del estado de presencia propio en la cabecera.
- Bloque `{% block content %}` para el contenido específico de cada vista.
- Diseño limpio, sin dependencias externas de CSS (usar Bootstrap CDN).

Implementar `panel/templates/panel/login.html` con:
- Formulario de login estándar Django.
- Mensaje de error si las credenciales son incorrectas.
- Sin enlace de registro (el alta de usuarios es por invitación).

---

## SECCIÓN 9 — PAH — REGISTRO DE SESIONES

### Sesión 2026-04-07
**Título:** Inicio del Hito 3 — Arquitectura IVR Multiempresa Configurable
**Descripción:** Sesión de arranque del Hito 3. Se define la arquitectura completa
del sistema IVR configurable desde producción: modelo de datos multiempresa,
sistema de presencia con gestión de ausencias, panel de administración personalizado
y mecanismo de inyección dinámica de configuración en Gemini Live. Se crea la
constelación documental satélite inicial del hito.

### Sesión 2026-04-08
**Título:** Inyección Dinámica de Configuración IVR: build_live_config + Refactor services.py
**Descripción:** Sesión de implementación de los Pasos 7, 8 y 9 de la hoja de ruta
del Hito 3. Se implementa build_live_config() en ivr_config/services.py, se refactoriza
VoiceOrchestrationService para carga dinámica desde BD con fallback de seguridad, y
se refactoriza voice_sidecar_bridge.py para diferir la instanciación del servicio al
evento start de Twilio donde el número To está disponible. Se corrige la documentación
satélite V03DOC_DYNAMIC_IVR_INJECTION.md con el flujo real de ejecución. Los scripts
standalone de laboratorio se migran a comandos Django reales bajo
vox_bridge/management/commands/.
