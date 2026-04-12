# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# ENTERPRISEBOT — ANEXO HITO V03 — IVR CONVERSACIONAL CONFIGURABLE DESDE PRODUCCIÓN
**Estado:** PAUSADO
**Fecha de inicio:** 2026-04-07
**Fecha de pausa:** 2026-04-12

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

#### `CallFlow` — Flujo IVR
    id, company (FK), name, system_instruction (TextField),
    initial_greeting (TextField), is_active

Define la personalidad y el comportamiento del agente IVR para un número concreto.
El `system_instruction` y el `initial_greeting` se inyectan dinámicamente en el
`LiveConnectConfig` de Gemini en tiempo de llamada, sustituyendo las constantes
hardcodeadas (`SYSTEM_INSTRUCTION_FALLBACK`, `INITIAL_GREETING_FALLBACK`)
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
   → Captura el campo `To` del body del POST y lo almacena en `self._pending_twilio_number`.
   → Responde con TwiML `<Connect><Stream url="wss://{host}/media" />`

2. Twilio abre WebSocket GET `/media`
   → `UniversalVoiceBridge.handle_websocket_stream()` en `voice_sidecar_bridge.py`
   → Se inicia el bucle lector de eventos de Twilio.
   → `VoiceOrchestrationService` NO se instancia todavía.

3. Twilio envía evento `start` por el WebSocket
   → `handle_websocket_stream()` lee `twilio_number` de `self._pending_twilio_number`
     (el evento `start` de Twilio Media Streams NO incluye el campo `To` en su payload
     — confirmado por diagnóstico DEBUG-P28 en sesión 2026-04-11).
   → Se instancia `VoiceOrchestrationService(twilio_number=twilio_number)`
   → En `__init__()` se almacena `self.twilio_number` con valores de fallback iniciales.
   → Se lanza `run_voice_session()` como asyncio.Task concurrente.

4. Al inicio de `run_voice_session()`:
   → `await sync_to_async(build_live_config)(self.twilio_number)` carga desde BD:
       a. Resuelve `PhoneNumber` activo por `twilio_number`.
       b. Carga `CallFlow` asociado.
       c. Carga `CorporateVoiceProfile` de la `Company`.
       d. Consulta `PresenceStatus` activo de todos los `Contact` internos.
       e. Ensambla `system_instruction` dinámico.
       f. Retorna `(system_instruction, initial_greeting)`.
   → Fallback automático a `SYSTEM_INSTRUCTION_FALLBACK` / `INITIAL_GREETING_FALLBACK`
     si `build_live_config()` lanza cualquier excepción.

5. Twilio envía eventos `media` sucesivos
   → Se reenvían a `service.receive_twilio_audio()`.

6. Twilio envía evento `stop`
   → `service.terminate_session()` señaliza el fin de sesión.

### 4.2. Archivos del pipeline de voz
- `ivr_config/services.py` — Contiene `build_live_config()`.
- `vox_bridge/services.py` — Orquestación de sesión Gemini Live con carga async de config.
- `voice_sidecar_bridge.py` — Bridge aiohttp: captura `To` en POST, instancia servicio en `start`.
- `voice_orchestrator.py` — Arranque de ngrok + actualización webhook regional IE1/US1.

---

## SECCIÓN 5 — COMANDOS DE GESTIÓN

### Comandos disponibles
    python -m dotenv run python manage.py update_twilio_webhook
        Thin wrapper que delega en VoiceOrchestrator.update_twilio_webhook().
        Actualiza webhooks en el endpoint regional correcto (US1/IE1) para cada
        PhoneNumber activo con capacidad de voz.

    python -m dotenv run python manage.py trigger_outbound_call
        Dispara una llamada saliente de validación. Admite --to +34XXXXXXXXX.

    python -m dotenv run python manage.py seed_grupo_alvarez --phone-numbers +34XXXXXXXXX
        Siembra los datos piloto de Grupo Álvarez en la base de datos.

### Secuencia de arranque (always-on task — automática)
    La always-on task en PythonAnywhere ejecuta voice_orchestrator.py de forma
    autónoma. Al arrancar:
    1. Limpia infraestructura ngrok previa (API cloud ngrok).
    2. Lanza ngrok v3 en puerto 8081.
    3. Obtiene la URL pública del túnel.
    4. Actualiza el webhook de voz de cada PhoneNumber activo en su región
       correcta (US1 o IE1) consultando la Routes API de Twilio.
    5. Lanza voice_sidecar_bridge.py (bridge aiohttp).

### Credenciales regionales Twilio en `.env`
    TWILIO_ACCOUNT_SID         — universal (todas las regiones)
    TWILIO_API_KEY_SID         — API Key US1
    TWILIO_API_KEY_SECRET      — Secret US1
    TWILIO_API_KEY_SID_IE1     — API Key IE1 (para números españoles)
    TWILIO_API_KEY_SECRET_IE1  — Secret IE1
    TWILIO_AUTH_TOKEN_IE1      — Auth Token IE1

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
- Ficheros PEA creados: middleware, mixins, forms, 11 vistas class-based,
  urls, y 14 templates con Bootstrap 5.3 CDN.
- Ficheros PMA modificados: `enterprise_core/settings.py`, `enterprise_core/urls.py`.
- CompanyUser vinculado al usuario `admin` con rol ADMIN en Grupo Álvarez.
- Validación E2E completa de todos los módulos del panel en producción.
- Skill PMP (Protocolo de Modificación Puntual) documentada y registrada.

### Sesión 2026-04-10 — Saneamiento de BD + Always-On Task + Validación E2E
- Auditoría completa de BD mediante script no interactivo.
- Dependencia `celery==5.6.3` añadida a `requirements.in`.
- Reestructuración canónica de usuarios de la plataforma y Grupo Álvarez.
- `voice_orchestrator.py` refactorizado: `update_twilio_webhook()` automático
  consultando BD y actualizando todos los PhoneNumbers activos con capacidad de voz.
- Always-on task activada en PythonAnywhere.
- Validación E2E exitosa: llamada entrante real al `+34951796832` con conversación fluida.
- Identificado problema de routing regional IE1: webhook actualizado en US1 pero
  números españoles procesan en IE1.

### Sesión 2026-04-11 — Routing Regional IE1 + Carga Dinámica + Calibración VAD

#### Infraestructura regional Twilio (Paso 26)
- Diagnóstico completo de la arquitectura regional Twilio: confirmado que
  `+34951796832` y `+34951799117` tienen `voice_region: IE1` vía Routes API.
- Credenciales IE1 obtenidas en consola Twilio y añadidas al `.env`.
- Script de diagnóstico `ie1_diagnostic.py` ejecutado: autenticación IE1 validada,
  SIDs de ambos números localizados en endpoint `api.dublin.ie1.twilio.com`.
- `voice_orchestrator.py` refactorizado (PMA): `update_twilio_webhook()` ahora
  consulta la Routes API por cada número, detecta su `voice_region` y actualiza
  el webhook en el endpoint regional correcto usando credenciales regionales.
  Dominio correcto para IE1: `api.dublin.ie1.twilio.com` (el patrón
  `api.ie1.twilio.com` está deprecado y dejará de funcionar el 2026-04-28).

#### Carga dinámica de configuración IVR (Paso 27)
- `vox_bridge/services.py` refactorizado (PMA): `build_live_config()` extraída
  de `__init__()` (que es síncrono y se invoca desde contexto async aiohttp,
  causando `SynchronousOnlyOperation`) y movida al inicio de `run_voice_session()`
  usando `await sync_to_async(build_live_config)(self.twilio_number)`.

#### Resolución del campo `To` ausente en evento `start` (Paso 28)
- Diagnóstico definitivo: el evento `start` de Twilio Media Streams NO incluye
  el número destino (`To`) en su payload WebSocket — confirmado por log DEBUG-P28
  en ambas llamadas de prueba.
- Solución implementada (PMA sobre `voice_sidecar_bridge.py`): el campo `To`
  se captura del body del POST HTTP inicial en `handle_twiml_post()` y se
  almacena en `self._pending_twilio_number`. Al recibir el evento `start`,
  `handle_websocket_stream()` consume ese valor para instanciar el servicio
  con el número correcto.

#### Eliminación número Indiana (Paso 29)
- `PhoneNumber` `+12603466780` eliminado de BD mediante script no interactivo.
  El número no pertenecía a la cuenta Twilio activa.

#### Calibración VAD (Frente B)
- `vox_bridge/services.py` (PMP): ajuste de constantes de detección de actividad
  basado en análisis de logs RMS de las llamadas de prueba:
    `SILENCE_THRESHOLD_RMS`: 200 → 300
    `SILENCE_FRAMES_TO_END_ACTIVITY`: 30 → 50 (600ms → 1000ms)
    `SPEECH_FRAMES_TO_START_ACTIVITY`: 10 → 15 (200ms → 300ms)
- Validación E2E: llamada real al `+34951796832` procesada en IE1 con coste
  confirmado de 0.01 USD. Conversación fluida validada.

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
5. Calibración VAD adicional: Los valores actuales (RMS 300, silence 50 frames,
   speech 15 frames) son una primera iteración. Pendiente ajuste fino tras más
   pruebas con distintos dispositivos y condiciones de llamada.
6. Sección Grúas: No existe aún en BD. Añadir cuando se disponga de contacto real.
7. ✅ RESUELTO (sesión 2026-04-12): Validación de carga dinámica completa desde BD.
   `build_live_config()` confirmado operativo con configuración de Grupo Álvarez
   desde BD para `+34951796832`. Bug `InterfaceError` por conexión MySQL stale
   resuelto mediante `connection.close()` al inicio de `build_live_config()`.
8. Configuración real de producción del `CallFlow` y `CorporateVoiceProfile` de
   Grupo Álvarez: BLOQUEADO — pendiente de que Grupo Álvarez facilite el organigrama
   real, personas, números de teléfono y función de cada uno para definir el flujo
   IVR de producción definitivo.

---

## SECCIÓN 8 — HOJA DE RUTA PARA LA REANUDACIÓN DE ESTE HITO

### Contexto de pausa (2026-04-12)
El hito se pausa con el sistema IVR completamente operativo en producción:
- Carga dinámica de configuración desde BD validada E2E (`build_live_config()` ✅).
- Bug `InterfaceError` por conexión MySQL stale resuelto en `ivr_config/services.py`.
- Panel de administración `/panel/` operativo con todos los módulos validados.
- Always-on task activa con webhook regional IE1 automatizado.
- El `CallFlow` y `CorporateVoiceProfile` actuales contienen configuración
  funcional de demostración — pendiente de sustitución por configuración real.

El hito se reactiva cuando Grupo Álvarez facilite su organigrama real.

### Paso 31 — Configuración real de producción de Grupo Álvarez

**Prerrequisito BLOQUEANTE:** Grupo Álvarez debe facilitar antes de la sesión:
- Organigrama completo: nombres, apellidos, cargo y número de teléfono E.164
  de cada persona que debe estar en el sistema.
- Función de cada persona: qué tipo de llamadas gestiona (Elevación, Asistencia,
  Grúas u otras categorías que definan).
- Horarios de atención por departamento.
- Cualquier regla especial de enrutamiento (p. ej. fuera de horario, idiomas,
  prioridades de escalado).

**Procedimiento una vez disponible la información:**
1. Actualizar `Contact` y `Section` en BD desde el panel `/panel/` o mediante
   script `seed_grupo_alvarez` con los datos reales.
2. Redactar el `system_instruction` definitivo de Alia con el organigrama real:
   - Identificar a cada persona por nombre y función.
   - Definir reglas de enrutamiento por categoría de llamada.
   - Incorporar horarios de atención por departamento.
   - Incluir reglas de escalado para casos no contemplados.
3. Redactar el `initial_greeting` de producción.
4. Actualizar el `CorporateVoiceProfile`:
   - `tone_guidelines`: tono y estilo corporativo real de Grupo Álvarez.
   - `sample_responses`: ejemplos de respuestas reales del agente.
   - `forbidden_phrases`: frases que Alia no debe usar en ningún caso.
5. Acceder a `https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/`
   con el usuario `alvarez_admin` y actualizar los campos desde el panel.
6. Realizar llamada real al `+34951796832` y verificar en `bridge.log`:
   `[CONFIG] Configuración IVR dinámica cargada correctamente para el número '+34951796832'`
   con `system_instruction` de longitud coherente con el organigrama real.

**Criterio de éxito:** Alia atiende una llamada real respondiendo íntegramente
con la configuración de producción de Grupo Álvarez, sin usar el fallback.

### Paso 32 — Sección Grúas

**Prerrequisito:** Disponibilidad del contacto real del departamento de Grúas.
Añadir `Section` "Grúas" en BD con el contacto asignado y actualizar el
`system_instruction` del `CallFlow` para incluir la categoría de enrutamiento.

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

### Sesión 2026-04-10
**Título:** Saneamiento de BD + Always-On Task + Validación E2E con Número Español Real
**Descripción:** Sesión de saneamiento canónico de la base de datos, activación de la
always-on task en PythonAnywhere y primera validación E2E exitosa con número español
real. Se audita la BD completa, se reestructura la arquitectura canónica de usuarios
de la plataforma, se refactoriza update_twilio_webhook() para operar de forma autónoma
consultando la BD, y se activa la always-on task. Se identifica el problema de routing
regional IE1 de Twilio como bloqueo para la automatización completa del webhook.

### Sesión 2026-04-11
**Título:** IE1 Regional Webhook + SynchronousOnlyOperation Fix + Payload start Debug
**Descripción:** Sesión centrada en tres frentes técnicos críticos que bloqueaban la
carga dinámica completa desde BD. Se implementa la detección automática de región vía
Routes API de Twilio y actualización de webhook en endpoint regional correcto IE1/US1
en voice_orchestrator.py. Se resuelve SynchronousOnlyOperation moviendo build_live_config()
a run_voice_session() con sync_to_async. Se diagnostica definitivamente que el evento
start de Twilio Media Streams no incluye el campo To — solución: captura desde el POST
HTTP inicial en handle_twiml_post(). Se elimina de BD el número de Indiana +12603466780.
Se calibra el VAD con valores optimizados para telefonía española. Validación E2E exitosa
con llamada real al +34951796832 procesada en IE1 con coste confirmado de 0.01 USD.

### Sesión 2026-04-12
**Título:** Validación Dinámica BD + Fix InterfaceError MySQL Stale + Pausa Hito 3
**Descripción:** Sesión de validación y cierre del Hito 3. Se diagnostica el bug
InterfaceError (0, '') que afectaba a todas las llamadas posteriores a la primera
exitosa: la conexión MySQL queda stale entre llamadas en el proceso de larga duración
always-on task. Solución: connection.close() al inicio de build_live_config() en
ivr_config/services.py, forzando reconexión fresca en cada llamada (PMA). Validación
E2E exitosa: llamada real al +34951796832 con carga dinámica completa confirmada en
logs. El Paso 31 queda bloqueado pendiente de que Grupo Álvarez facilite su organigrama
real, personas, teléfonos y funciones. El hito se pausa y se reactiva el Hito 4.
