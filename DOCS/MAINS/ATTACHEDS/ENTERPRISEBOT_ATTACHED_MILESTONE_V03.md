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
- El accessor ORM desde `auth.User` es `user.company_user` (related_name definido en modelo).

#### `Contact` — Persona contactable
    id, company (FK), name, phone_number, is_internal (bool), company_user (FK nullable)

Personas a las que el IVR puede llamar, transferir llamadas o enviar mensajes.
Los usuarios internos (`is_internal=True`) tienen un `CompanyUser` asociado y pueden
tener `PresenceStatus`. Los trabajadores externos (`is_internal=False`) son contactos
sin acceso al sistema. El campo `phone_number` en formato E.164 es el número que
Twilio marca cuando el IVR decide transferir o llamar a ese contacto.

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
  de Django (`auth.User`), pero con un middleware que bloquea el acceso
  a `/admin/` si el usuario no tiene `is_staff=True`.
- El superusuario de la plataforma (`is_staff=True`, `is_superuser=True`) tiene
  acceso completo a todo, incluyendo el admin de Django.
- Los `CompanyUser` acceden exclusivamente al panel personalizado en una ruta
  dedicada `/panel/`.
- URL estable de producción: `https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/`
- El túnel ngrok es exclusivo para el webhook de Twilio — nunca para el panel.

### 3.2. Panel de Administración Personalizado (`/panel/`) — IMPLEMENTADO
Vistas Django class-based que permiten a cada empresa gestionar:
- `CompanyUser` — usuarios con roles ADMIN/OPERATOR.
- `Section` — secciones o departamentos de enrutamiento IVR.
- `Contact` — contactos internos y externos (números a los que el IVR puede llamar).
- `PhoneNumber` — números Twilio asignados (solo lectura para CompanyUser).
- `CallFlow` — flujos IVR con system_instruction e initial_greeting editables.
- `CorporateVoiceProfile` — perfil de voz corporativa inyectado en Gemini Live.
- `PresenceStatus` — estado de presencia propio (todos los roles).

### 3.3. Lecciones Aprendidas — Implementación del Panel
- El accessor ORM correcto desde `auth.User` hacia `CompanyUser` es `user.company_user`
  (related_name="company_user" definido en el modelo — NO `user.companyuser`).
- `redirect_authenticated_user = True` en `LoginView` provoca bucle de redirección
  infinito. Solución: sobrescribir `dispatch()` en `PanelLoginView` con comprobación
  explícita del `company_user` antes de redirigir.
- El hash SRI de Bootstrap JS en CDN jsDelivr varía según el edge node. Se elimina
  el atributo `integrity` del script JS para evitar bloqueos intermitentes.
- Para forzar la invalidación del bytecode en PythonAnywhere WSGI:
      find /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/__pycache__ -name "*.pyc" -delete
      touch /var/www/enterprisebot-miguelaetxio_pythonanywhere_com_wsgi.py
- La recarga correcta de la aplicación es desde el botón verde del panel web de
  PythonAnywhere — siempre verificar que se recarga EnterpriseBot y no otro proyecto.

### 3.4. Gestión de Presencia
- Cada usuario puede activar/desactivar su estado desde `/panel/presence/`.
- Al activar `IN_MEETING` sin `ends_at`: Celery Beat programa una tarea que
  a las 3 horas envía un recordatorio (SMS/WhatsApp vía Twilio).
- Al activar `BUSY_UNTIL`: Celery Beat programa la expiración automática.
- `ABSENT_SCHEDULED` y `ABSENT_VACATION`: gestión automática por rango de fechas.

---

## SECCIÓN 4 — INYECCIÓN DINÁMICA EN EL IVR

### 4.1. Flujo de llamada entrante con configuración dinámica (IMPLEMENTADO)

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
- `vox_bridge/services.py` — constantes → fallback, constructor acepta `twilio_number`.
- `voice_sidecar_bridge.py` — instanciación diferida al evento `start`, guardias defensivas.

---

## SECCIÓN 5 — COMANDOS DE GESTIÓN

### Comandos disponibles
    python -m dotenv run python manage.py update_twilio_webhook
        Actualiza el webhook de voz de Twilio para que apunte al túnel ngrok
        activo. Lee la URL desde DOCS/SESSION/NGROK_URL.txt.

    python -m dotenv run python manage.py trigger_outbound_call
        Dispara una llamada saliente de validación desde +12603466780 al número
        por defecto (+34688360595). Admite --to +34XXXXXXXXX.

    python -m dotenv run python manage.py seed_grupo_alvarez --phone-numbers +12603466780
        Siembra los datos piloto de Grupo Álvarez en la base de datos.

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

### Sesión 2026-04-09 — Panel de Administración Personalizado Completo
- App Django `panel` creada manualmente vía heredoc (sin `startapp`).
- Ficheros PEA creados:
    `panel/__init__.py`
    `panel/apps.py`
    `panel/middleware.py`   ← CompanyUserAdminBlockMiddleware
    `panel/mixins.py`       ← PanelLoginRequiredMixin, CompanyUserRequiredMixin, AdminRoleRequiredMixin
    `panel/forms.py`        ← PanelAuthenticationForm, PresenceStatusForm, ContactForm,
                               SectionForm, CallFlowForm, CorporateVoiceProfileForm
    `panel/views.py`        ← 11 vistas class-based completas
    `panel/urls.py`         ← 13 rutas bajo /panel/
    `panel/templates/panel/base.html`
    `panel/templates/panel/login.html`
    `panel/templates/panel/dashboard.html`
    `panel/templates/panel/presence/status.html`
    `panel/templates/panel/users/list.html`
    `panel/templates/panel/users/form.html`
    `panel/templates/panel/sections/list.html`
    `panel/templates/panel/sections/form.html`
    `panel/templates/panel/contacts/list.html`
    `panel/templates/panel/contacts/form.html`
    `panel/templates/panel/callflows/list.html`
    `panel/templates/panel/callflows/form.html`
    `panel/templates/panel/phonenumbers/list.html`
    `panel/templates/panel/voiceprofile/detail.html`
- Ficheros PMA modificados:
    `enterprise_core/settings.py` — panel en INSTALLED_APPS + middleware registrado.
    `enterprise_core/urls.py`     — panel/ incluido en urlpatterns.
- CompanyUser vinculado al usuario `admin` con rol ADMIN en Grupo Álvarez.
- Validación E2E completa de todos los módulos del panel en producción.
- Skill PMP (Protocolo de Modificación Puntual) documentada y registrada.

### Sesión 2026-04-10 — Saneamiento de BD + Always-On Task + Validación E2E con Número Español Real
- Auditoría completa de BD mediante script no interactivo (`audit_bd_enterprisebot.py`).
- Dependencia `celery==5.6.3` añadida a `requirements.in` y compilada con `pip-tools`
  (resuelve `ModuleNotFoundError` que impedía el arranque de scripts Django standalone).
- Reestructuración canónica de usuarios de la plataforma y Grupo Álvarez:
    - `admin` (id=2) eliminado de BD — era un CompanyUser anómalo (is_staff=True).
    - `alvarez_admin` actualizado: email `administracion@gruasalvarez.com`, contraseña usable.
    - `alvarez_staff_01` creado: email `nummenor@gmail.com`, rol OPERATOR, para pruebas.
    - `Contact` Miguel Ángel Muñoz Cara reasignado a `CompanyUser` `alvarez_staff_01` (id=3).
- Arquitectura canónica de usuarios definida y documentada:
    `{empresa}_admin`        → CompanyUser ADMIN, acceso completo al /panel/.
    `{empresa}_staff_{id}`   → CompanyUser OPERATOR, acceso solo a presencia propia.
- `voice_orchestrator.py` refactorizado (PMA): nuevo método `update_twilio_webhook()`
  que actualiza automáticamente los webhooks de todos los PhoneNumbers activos con
  capacidad de voz consultando la BD, eliminando la intervención manual en el arranque.
- `update_twilio_webhook.py` (management command) refactorizado (PMA) a thin wrapper
  que delega en `VoiceOrchestrator.update_twilio_webhook()` — única fuente de verdad.
- Always-on task activada en PythonAnywhere: la infraestructura arranca de forma
  completamente autónoma sin intervención manual.
- **Validación E2E exitosa**: llamada entrante real al `+34951796832` completada con
  conversación fluida — Alia saluda, conversa y se despide correctamente.
- Identificado problema de routing regional IE1 de Twilio: la API estándar actualiza
  el webhook en US1 pero los números españoles tienen routing activo en IE1, que
  requiere el endpoint regional `api.dublin.ie1.twilio.com` para la actualización
  automática completa.

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
5. Número de Indiana `+12603466780`: Presente en BD como PhoneNumber activo pero
   no pertenece a la cuenta Twilio activa. Eliminar de BD en próxima sesión de
   limpieza o reasignar cuando sea necesario.
6. Calibración VAD para líneas ES: Pendiente de pruebas con los números españoles
   ya activos `+34951799117` y `+34951796832`.
7. Sección Grúas: No existe aún en BD. Añadir cuando se disponga de contacto real.

---

## SECCIÓN 8 — HOJA DE RUTA SIGUIENTE SESIÓN

### Contexto de arranque
El sistema IVR está operativo con números españoles reales y always-on task activa.
La validación E2E con conversación fluida ha sido completada en sesión 2026-04-10.
La siguiente sesión se centra en completar la automatización del webhook regional
IE1 de Twilio, resolver el fallback activo por campo `to` ausente y validar la
carga dinámica completa desde BD.

### Paso 26 — Automatización del webhook regional IE1 de Twilio

**Problema identificado:** La API estándar de Twilio (`api.twilio.com`) actualiza
el webhook en la región US1. Los números españoles tienen routing activo en IE1,
cuya configuración se gestiona a través del endpoint regional:
    `https://api.dublin.ie1.twilio.com/2010-04-01/Accounts/{SID}/IncomingPhoneNumbers/{SID}.json`

**Solución a implementar en `VoiceOrchestrator.update_twilio_webhook()`:**
1. Para cada `PhoneNumber` activo con capacidad de voz, determinar su región
   activa consultando la Inbound Processing Region API de Twilio:
       `GET https://routes.twilio.com/v2/PhoneNumbers/{number_e164}`
   El campo `voice_region` de la respuesta indica la región activa (`IE1`, `US1`, etc.).
2. Construir el endpoint correcto según la región:
   - `US1` (defecto): `https://api.twilio.com/...`
   - `IE1`: `https://api.dublin.ie1.twilio.com/...`
   - `AU1`: `https://api.sydney.au1.twilio.com/...`
3. Instanciar el `TwilioClient` con el parámetro `region` correspondiente:
       `TwilioClient(api_key_sid, api_key_secret, account_sid, region='ie1')`
4. Ejecutar la actualización del webhook sobre ese cliente regional.

**Criterio de éxito:** Al arrancar la always-on task, todos los números se
actualizan automáticamente en su región correcta sin intervención manual.

### Paso 27 — Resolver SynchronousOnlyOperation en build_live_config()

**Problema identificado:** `build_live_config()` ejecuta queries ORM síncronas
desde el contexto async de `VoiceOrchestrationService.__init__()`. Esto provoca:
    `SynchronousOnlyOperation: You cannot call this from an async context`
El sistema cae al fallback hardcodeado en cada llamada, impidiendo la carga
dinámica de configuración desde BD.

**Solución a implementar en `vox_bridge/services.py`:**
Envolver la llamada a `build_live_config()` con `sync_to_async`:
```python
    from asgiref.sync import sync_to_async
    # En __init__() no se puede usar await — mover la carga al arranque de la sesión.
    # La instanciación del servicio debe separarse de la carga de configuración.
```
La estrategia correcta es mover `build_live_config()` fuera de `__init__()` y
llamarla desde `run_voice_session()` usando `await sync_to_async(build_live_config)(twilio_number)`.
Esto requiere que `self.system_instruction` y `self.initial_greeting_text` se
asignen de forma asíncrona al inicio de `run_voice_session()`, antes del saludo.

**Archivos afectados:**
- `vox_bridge/services.py` — PMA: mover carga de config a `run_voice_session()`.

**Criterio de éxito:** Los logs muestran `[CONFIG] Configuración dinámica cargada`
sin `[ERROR]` ni `FALLBACK`, y `build_live_config()` devuelve el `system_instruction`
y `initial_greeting` correctos desde BD para el número llamado.

### Paso 28 — Resolver campo `to` ausente en evento `start` de Twilio

**Problema identificado:** El evento `start` de Twilio llega sin el campo `to`
en el payload WebSocket, por lo que `twilio_number` es una cadena vacía.

**Investigación necesaria:** Revisar el payload completo del evento `start` en
los logs para identificar el campo correcto donde Twilio envía el número destino.
Puede ser `data["start"]["to"]`, `data["start"]["To"]` o un campo anidado diferente.

**Solución provisional:** Añadir logging exhaustivo del payload completo del
evento `start` para identificar la estructura real:
    `self.flush_print(f"# [DEBUG] Payload evento start completo: {data}")`

**Archivos afectados:**
- `voice_sidecar_bridge.py` — PMP o PMA según el campo identificado.

### Paso 29 — Eliminar número de Indiana de BD

El `PhoneNumber` `+12603466780` está registrado en BD con `capabilities=VOICE`
pero no pertenece a la cuenta Twilio activa. Eliminarlo con script no interactivo:
```python
    PhoneNumber.objects.filter(number="+12603466780").delete()
```
Verificar en la auditoría de BD que el registro ha sido eliminado.

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

### Sesión 2026-04-09
**Título:** Panel de Administración Personalizado EnterpriseBot: 7 Módulos E2E en Producción
**Descripción:** Sesión de implementación de los Pasos 10 al 22 de la hoja de ruta
del Hito 3. Se crea la app Django panel manualmente vía heredoc evitando ficheros
residuales. Se implementan middleware de bloqueo de admin, mixins de autenticación
por capas, 11 vistas class-based y 14 templates con Bootstrap 5.3 CDN. Los módulos
implementados y validados E2E en producción son: login, dashboard, presencia propia,
usuarios, secciones, contactos, flujos IVR, números de teléfono y perfil de voz
corporativa. Se documentan y resuelven lecciones aprendidas sobre el accessor ORM
company_user, el bucle de redirección de LoginView y la invalidación de bytecode WSGI.
Se documenta y registra la skill PMP (Protocolo de Modificación Puntual) para
sustituciones atómicas con grep + sed como alternativa ligera al PMA completo.
