# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# ENTERPRISEBOT — ANEXO HITO V03 — IVR CONVERSACIONAL CONFIGURABLE DESDE PRODUCCIÓN
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-07
**Fecha de reanudación:** 2026-04-13

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

Ver especificación técnica completa en el documento satélite:
`DOCS_ATTACHED_2_ANNEX_V03/V03DOC_DATA_MODEL.md`

Resumen de entidades:

#### Entidades base (implementadas en sesiones anteriores)
- `Company` — Empresa cliente raíz del sistema multiempresa.
- `CompanyUser` — Usuario de empresa con rol ADMIN u OPERATOR.
- `Contact` — Persona contactable, interna o externa.
- `Section` — Sección o departamento de enrutamiento IVR.
- `PhoneNumber` — Número Twilio asignado a la empresa.
- `CallFlow` — Flujo IVR con system_instruction e initial_greeting.
- `PresenceStatus` — Estado de presencia del usuario interno.
- `CorporateVoiceProfile` — Perfil de voz corporativa inyectado en Gemini Live.
- `DataCaptureSet` — Conjunto de toma de datos por sección.

#### Entidades nuevas (acordadas sesión 2026-04-13)
- `SectionSchedule` — Horario por día de la semana para cada sección.
- `BlockedCaller` — Registro de números bloqueados por empresa.

#### Extensiones sobre entidades existentes (acordadas sesión 2026-04-13)
- `Contact.email` — EmailField para notificaciones por correo.
- `Contact.gender` — CharField M/F para tratamiento Sr./Sra. por Alia.
- `Section.is_24h` — BooleanField que cortocircuita la comprobación de horario.
- `CallFlow.notification_contact` — FK a Contact designado para actividad no recogida.

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
- `SectionSchedule` — horarios por día de la semana para cada sección. ← NUEVO
- `Contact` — contactos internos y externos.
- `PhoneNumber` — números Twilio asignados (solo lectura para CompanyUser).
- `CallFlow` — flujos IVR con system_instruction e initial_greeting editables.
- `CorporateVoiceProfile` — perfil de voz corporativa inyectado en Gemini Live.
- `PresenceStatus` — estado de presencia propio (todos los roles).
- `BlockedCaller` — números bloqueados activos e historial. ← NUEVO

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

### 3.5. Nota Responsive — Panel
La interfaz del panel (`/panel/`) debe ser completamente responsive. La mayoría
de accesos se realizarán desde dispositivos móviles y tablets. Aplicar en todas
las vistas: uso correcto de col-12/col-md-*/col-lg-*, tablas con table-responsive,
formularios con inputs de tamaño adecuado para pantalla táctil, navegación
colapsable en móvil.

---

## SECCIÓN 4 — INYECCIÓN DINÁMICA EN EL IVR

### 4.1. Flujo de llamada entrante con configuración dinámica

1. Twilio realiza POST `/api/vox/inbound/`
   → `UniversalVoiceBridge.handle_twiml_post()` en `voice_sidecar_bridge.py`
   → Captura el campo `To` del body del POST y lo almacena en `self._pending_twilio_number`.
   → Captura el campo `From` del body del POST y lo almacena en `self._pending_caller_number`.
   → Responde con TwiML `<Connect><Stream url="wss://{host}/media" />`

2. Twilio abre WebSocket GET `/media`
   → `UniversalVoiceBridge.handle_websocket_stream()` en `voice_sidecar_bridge.py`
   → Se inicia el bucle lector de eventos de Twilio.
   → `VoiceOrchestrationService` NO se instancia todavía.

3. Twilio envía evento `start` por el WebSocket
   → `handle_websocket_stream()` lee `twilio_number` de `self._pending_twilio_number`
     y `caller_number` de `self._pending_caller_number`.
   → Se instancia `VoiceOrchestrationService(twilio_number, caller_number)`.
   → Se lanza `run_voice_session()` como asyncio.Task concurrente.

4. Al inicio de `run_voice_session()`:
   → `await sync_to_async(build_live_config)(self.twilio_number, self.caller_number)`
       a. Comprueba `BlockedCaller` activo para (company, caller_number).
          Si bloqueado → retorna config de bloqueo → Alia responde y termina.
       b. Resuelve `PhoneNumber` activo por `twilio_number`.
       c. Carga `CallFlow` asociado.
       d. Carga `CorporateVoiceProfile` de la `Company`.
       e. Carga todas las `Section` activas con sus `SectionSchedule` y `Contact`.
       f. Consulta `PresenceStatus` activo de todos los `Contact` internos.
       g. Ensambla `system_instruction` dinámico con toda la información anterior.
       h. Retorna `(system_instruction, initial_greeting)`.
   → Fallback automático a `SYSTEM_INSTRUCTION_FALLBACK` / `INITIAL_GREETING_FALLBACK`
     si `build_live_config()` lanza cualquier excepción.

5. Twilio envía eventos `media` sucesivos
   → Se reenvían a `service.receive_twilio_audio()`.

6. Twilio envía evento `stop`
   → `service.terminate_session()` señaliza el fin de sesión.

### 4.2. Archivos del pipeline de voz
- `ivr_config/services.py` — Contiene `build_live_config()`.
- `vox_bridge/services.py` — Orquestación de sesión Gemini Live con carga async de config.
- `voice_sidecar_bridge.py` — Bridge aiohttp: captura `To` y `From` en POST,
  instancia servicio en `start`.
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
- Implementación detección automática de región vía Routes API (Paso 26).
- Fix `SynchronousOnlyOperation`: `build_live_config()` movida a `run_voice_session()`
  con `sync_to_async` (Paso 27).
- Diagnóstico definitivo: evento `start` Twilio no incluye campo `To` — captura
  desde POST HTTP inicial en `handle_twiml_post()` (Paso 28).
- Eliminación número Indiana `+12603466780` de BD (Paso 29).
- Calibración VAD: `SILENCE_THRESHOLD_RMS=300`, `SILENCE_FRAMES=50`, `SPEECH_FRAMES=15`.
- Validación E2E exitosa: llamada real al `+34951796832` procesada en IE1 (0.01 USD).

### Sesión 2026-04-12 — Validación Dinámica BD + Fix InterfaceError + Pausa
- Diagnóstico y fix de `InterfaceError` por conexión MySQL stale entre llamadas:
  `connection.close()` al inicio de `build_live_config()` (Paso 30).
- Validación E2E exitosa: carga dinámica completa desde BD confirmada en logs.
- Hito pausado: Paso 31 bloqueado pendiente organigrama Grupo Álvarez.
- Hito 4 activado para desarrollo canal WhatsApp.

### Sesión 2026-04-13 — Reanudación + Diseño de Flujo Completo
- MASTER_DOCUMENT corregido: Hito 3 → EN PROGRESO, Hito 4 → PAUSADO (PMP).
- Diseño completo del flujo IVR de producción acordado:
    · 9 tipos de llamada identificados y comportamiento definido para cada uno.
    · Toma de datos conversacional con ubicación textual (sin GPS en fase actual).
    · Notificación al responsable: llamada saliente Twilio + correo electrónico.
    · Bloqueo de números maliciosos con duración configurable.
    · Modo demo con frase clave + DTMF 7463.
- Extensiones de modelo acordadas y documentadas en `V03DOC_DATA_MODEL.md` (PMA):
    · `Contact`: campos `email` y `gender`.
    · `Section`: campo `is_24h`.
    · `CallFlow`: campo `notification_contact`.
    · Nuevo modelo `SectionSchedule`.
    · Nuevo modelo `BlockedCaller`.

---

## SECCIÓN 7 — PENDIENTES DIFERIDOS

1. `DataCaptureSet` por sección: campos específicos para Elevación, Asistencia y Grúas
   a definir con Grupo Álvarez (tipo_grua, tonelaje, tipo_vehiculo, matricula, etc.).
2. Recepción de ubicación GPS: integración con localización nativa WhatsApp +
   Grounding Google Maps (diferido a reactivación del Hito 4).
3. Sistema de recordatorios de presencia vía WhatsApp: diferido al Hito 4.
4. Registro de usuarios empresa: flujo de alta de nuevos `CompanyUser` con
   invitación por email.
5. Calibración VAD adicional: ajuste fino pendiente tras más pruebas con
   distintos dispositivos y condiciones de llamada.
6. Configuración real de producción de Grupo Álvarez: `CallFlow` y
   `CorporateVoiceProfile` definitivos pendientes de organigrama real.
7. Sección Grúas: no existe aún en BD. Añadir cuando se disponga del contacto real.

---

## SECCIÓN 8 — HOJA DE RUTA

### Pasos 1–30 ✅ COMPLETADOS
Ver registro de sesiones en Sección 6.

### Paso 31 — Extensiones de modelo en `ivr_config/models.py` ✅ COMPLETADO (sesión 2026-04-13)
Añadir a `ivr_config/models.py`:
- Campo `email` (EmailField, blank=True) en `Contact`.
- Campo `gender` (CharField M/F, blank=True) en `Contact`.
- Campo `is_24h` (BooleanField, default=False) en `Section`.
- Campo `notification_contact` (FK→Contact, null=True) en `CallFlow`.
- Modelo nuevo `SectionSchedule` con FK a Section, weekday, time_open, time_close.
- Modelo nuevo `BlockedCaller` con FK a Company, phone_number, blocked_until, blocked_by.
Generar y aplicar migraciones incrementales.
Actualizar `ivr_config/admin.py` con los nuevos modelos y campos.

### Paso 32 — Extensión del panel (`/panel/`) con nuevos módulos ✅ COMPLETADO (sesión 2026-04-13)
Añadir al panel personalizado:
- Gestión de `SectionSchedule`: inline dentro de la vista de edición de Section,
  permitiendo añadir/editar/eliminar franjas horarias por día de la semana.
- Gestión de `BlockedCaller`: listado de bloqueados activos, alta manual,
  desbloqueo manual antes de vencimiento, historial de expirados.
Criterio de éxito: el ADMIN puede configurar el horario completo de una sección
y bloquear/desbloquear un número desde el panel sin tocar la BD directamente.

### Paso 33 — Actualización de `build_live_config()` ⏳ PENDIENTE
Actualizar `ivr_config/services.py`:
- Añadir parámetro `caller_number: str` a `build_live_config()`.
- Implementar comprobación de `BlockedCaller` activo al inicio de la función.
- Cargar `SectionSchedule` de cada `Section` activa.
- Implementar función `is_section_available(section, now)` que evalúa
  `is_24h` y franjas `SectionSchedule` para el weekday y hora actuales.
- Inyectar en `system_instruction` la disponibilidad real de cada sección,
  el estado de presencia de cada `Contact` interno, el tratamiento Sr./Sra.
  según `Contact.gender`, y el `notification_contact` del `CallFlow`.
Criterio de éxito: `build_live_config()` retorna un `system_instruction`
que refleja disponibilidad real de secciones y presencia real de personas.

### Paso 34 — Captura del número llamante en `voice_sidecar_bridge.py` ⏳ PENDIENTE
Capturar el campo `From` del POST HTTP inicial en `handle_twiml_post()` y
almacenarlo en `self._pending_caller_number`, siguiendo el mismo patrón
implementado para `To` en el Paso 28.
Pasar `caller_number` al constructor de `VoiceOrchestrationService`.
Criterio de éxito: `build_live_config()` recibe el número llamante real
en todas las llamadas entrantes.

### Paso 35 — Seed de datos piloto Grupo Álvarez actualizado ⏳ PENDIENTE
Actualizar `ivr_config/management/commands/seed_grupo_alvarez.py` con:
- Secciones: Grúas, Asistencia (is_24h=True), Elevación, Administración, Taller.
- SectionSchedule para cada sección con horario representativo de demostración.
- BlockedCaller vacío (sin bloqueados iniciales).
- Contact con campos email y gender rellenos para los contactos existentes.
Criterio de éxito: ejecución del seed recrea el estado piloto completo
con la nueva estructura de datos sin errores.

### Paso 36 — Validación E2E del flujo completo ⏳ PENDIENTE
Realizar llamada real al `+34951796832` y verificar:
- Alia identifica correctamente el tipo de servicio solicitado.
- Alia informa correctamente de la disponibilidad de la sección (horario).
- Alia recoge datos conversacionalmente (nombre, teléfono, servicio, ubicación).
- Alia notifica al responsable (llamada saliente + correo).
- Alia responde correctamente ante llamada fuera de actividad.
- Modo demo funciona con frase clave + DTMF 7463.
- Número bloqueado recibe respuesta estándar y cierre inmediato.
Criterio de éxito: todos los tipos de llamada se comportan según la tabla
de la Sección 4.1 sin intervención manual en BD ni código.

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
**Descripción:** Sesión de validación y cierre temporal del Hito 3. Se diagnostica el
bug InterfaceError (0, '') que afectaba a todas las llamadas posteriores a la primera
exitosa: la conexión MySQL queda stale entre llamadas en el proceso de larga duración
always-on task. Solución: connection.close() al inicio de build_live_config() en
ivr_config/services.py, forzando reconexión fresca en cada llamada (PMA). Validación
E2E exitosa: llamada real al +34951796832 con carga dinámica completa confirmada en
logs. El hito se pausa para reactivar el Hito 4 (canal WhatsApp).

### Sesión 2026-04-13 — Primera parte
**Título:** Reanudación Hito 3 — Diseño de Flujo IVR Completo y Extensiones de Modelo
**Descripción:** Sesión de reanudación del Hito 3 tras pausa del Hito 4 por bloqueo
de Meta. Se corrige el MASTER_DOCUMENT permutando estados de Hito 3 (EN PROGRESO) e
Hito 4 (PAUSADO) mediante PMP. Se diseña el flujo IVR completo de producción: 9 tipos
de llamada con comportamiento definido, toma de datos conversacional con ubicación
textual, notificación al responsable por llamada saliente Twilio y correo electrónico,
bloqueo de números maliciosos con duración configurable, y modo demo con frase clave
más DTMF 7463. Se acuerdan y documentan las extensiones de modelo necesarias
(SectionSchedule, BlockedCaller, campos email/gender/is_24h/notification_contact).
Se actualiza V03DOC_DATA_MODEL.md con la especificación técnica completa (PMA) y
se reescribe el presente anexo con la hoja de ruta actualizada (Pasos 31–36).

### Sesión 2026-04-13 — Segunda parte
**Título:** Implementación Pasos 31 y 32 — Modelos, Migraciones y Panel Extendido
**Descripción:** Implementación completa de los Pasos 31 y 32 de la hoja de ruta.
Paso 31: extensiones de modelo en ivr_config/models.py (campos email y gender en
Contact, is_24h en Section, notification_contact en CallFlow, nuevos modelos
SectionSchedule y BlockedCaller), migración 0003 aplicada correctamente en producción.
Paso 32: extensión del panel con SectionScheduleForm y BlockedCallerForm en forms.py,
nuevas vistas BlockedCallerListView/CreateView/DeleteView y refactorización de
SectionCreateView/UpdateView con formset inline en views.py, nuevas rutas en urls.py,
tres templates nuevos de blockedcallers (list, form, confirm_delete) y actualización
de templates existentes (sections/form, contacts/form, callflows/form, base.html).
Limpieza global de 100 errores H021 (inline styles) en todos los templates del panel.
Añadido JavaScript dinámico para añadir franjas horarias sin recargar la página.
Validación E2E completa en producción: badges, formset de horarios, bloqueados,
contactos con email/gender, flujos IVR con notification_contact y dashboard. ✅
