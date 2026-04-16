# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# ENTERPRISEBOT — ANEXO HITO V03 — IVR CONVERSACIONAL CONFIGURABLE DESDE PRODUCCIÓN
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-07
**Fecha de reanudación:** 2026-04-16 (segunda reactivación)
**Última actualización:** 2026-04-16

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

#### Extensiones sobre entidades existentes (acordadas sesión 2026-04-15)
- `CompanyUser.must_change_password` — BooleanField (default=True). Fuerza cambio
  de contraseña en el primer acceso o tras reset del ADMIN. Migración 0004 aplicada.
- `CorporateVoiceProfile.voice_name` — CharField selección de voz Gemini Live
  por empresa. Migración 0005 aplicada ✅.
- `CallFlow.backup_system_instruction` / `backup_initial_greeting` /
  `backup_notification_contact` — campos de snapshot para restauración.
  Migración 0006 aplicada ✅.
- `CorporateVoiceProfile.backup_tone_guidelines` / `backup_sample_responses` /
  `backup_forbidden_phrases` — campos de snapshot para restauración (Paso 33-E).

#### Extensiones sobre entidades existentes (acordadas sesión 2026-04-16 — Estrategia B)
- `Section.call_flow` — ForeignKey('CallFlow', null=True, blank=True, SET_NULL,
  related_name='sections'). Flujo IVR específico de la sección, cargado dinámicamente
  cuando el agente detecta que el llamante desea ser atendido por esa sección.
  Las secciones sin call_flow asignado son IGNORADAS por el motor en tiempo de llamada.
  Migración 0007 aplicada ✅.
- `CallFlow.fallback_section` — ForeignKey('Section', null=True, blank=True, SET_NULL,
  related_name='fallback_for_call_flows'). Sección de último recurso designada para
  este flujo: cuando ninguna sección activa puede atender al llamante, el agente
  transfiere la llamada al responsable humano de esta sección. Cada PhoneNumber
  (y por tanto cada CallFlow) tiene su propia fallback_section independiente,
  permitiendo delegar responsabilidades por número.
  Migración 0007 aplicada ✅.

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
- `CompanyUser` — usuarios con roles ADMIN/OPERATOR. Alta desde panel con contraseña
  inicial configurable y cambio obligatorio en primer acceso. ← ACTUALIZADO
- `Section` — secciones o departamentos de enrutamiento IVR.
- `SectionSchedule` — horarios por día de la semana para cada sección.
- `Contact` — contactos internos y externos.
- `PhoneNumber` — números Twilio asignados (solo lectura para CompanyUser).
- `CallFlow` — flujos IVR con system_instruction e initial_greeting editables.
  Botón de restauración al estado anterior ✅ COMPLETADO (Paso 33-E).
- `CorporateVoiceProfile` — perfil de voz corporativa inyectado en Gemini Live.
  Selector de voz Gemini por empresa ✅ COMPLETADO (Paso 33-D).
  Botón de restauración al estado anterior ✅ COMPLETADO (Paso 33-E).
- `PresenceStatus` — estado de presencia propio (todos los roles).
- `BlockedCaller` — números bloqueados activos e historial.

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
- `data-bs-dismiss="offcanvas"` en los enlaces de navegación del sidebar offcanvas
  impide la navegación en algunos navegadores móviles. Solución: eliminar el atributo
  de los enlaces y mantenerlo solo en el `btn-close` del header del offcanvas.
- El `btn-close` del offcanvas debe estar dentro de un `offcanvas-header` estándar de
  Bootstrap (no en un div custom) para que `data-bs-dismiss` funcione correctamente.

### 3.4. Gestión de Presencia
- Cada usuario puede activar/desactivar su estado desde `/panel/presence/`.
- Al activar `IN_MEETING` sin `ends_at`: Celery Beat programa una tarea que
  a las 3 horas envía un recordatorio (SMS/WhatsApp vía Twilio).
- Al activar `BUSY_UNTIL`: Celery Beat programa la expiración automática.
- `ABSENT_SCHEDULED` y `ABSENT_VACATION`: gestión automática por rango de fechas.

### 3.5. Responsive — Panel
La interfaz del panel (`/panel/`) es completamente responsive desde la sesión
2026-04-15. Implementación:
- Sidebar fijo en escritorio (`>=lg`, `d-lg-flex`). Offcanvas Bootstrap con botón
  hamburguesa en móvil/tablet (`<lg`, `d-lg-none`).
- `margin-left: 260px` restringido a `@media (min-width: 992px)`.
- `page-content` con padding adaptativo: `1rem` en móvil, `2rem 1.5rem` en `>=md`.
- Tablas con `table-responsive` en todos los listados.
- Cabeceras de acciones con `flex-wrap gap-2` para evitar solapamiento en móvil.
- Campos del formset de horarios con `w-100` para usabilidad táctil.
- Nombre de usuario en top navbar con `d-none d-sm-inline`.

### 3.6. Gestión de Contraseñas de CompanyUser ← NUEVO (sesión 2026-04-15)
- Al crear un `CompanyUser` desde el panel, el ADMIN asigna una contraseña inicial
  (por defecto `1234`). El campo `must_change_password` se activa automáticamente.
- `CompanyUserRequiredMixin` redirige a `/panel/password/change/` en cada request
  mientras `must_change_password=True`, bloqueando el acceso al resto del panel.
- En `/panel/password/change/` el usuario establece su contraseña definitiva.
  Al guardar, `must_change_password` se limpia y el hash de sesión se refresca
  para que el usuario permanezca autenticado.
- El ADMIN puede forzar un reset desde `/panel/users/{pk}/edit/` — botón
  "Forzar cambio de contraseña" que reactiva `must_change_password=True`.
- Los campos de contraseña en login, cambio y creación de usuario incluyen:
  toggle mostrar/ocultar (icono ojo) y barra de nivel de seguridad en tiempo real.

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

4. Al inicio de `run_voice_session()` — FASE 1 (Bienvenida):
   → `await sync_to_async(build_live_config)(self.twilio_number, self.caller_number)`
       a. Comprueba `BlockedCaller` activo para (company, caller_number).
          Si bloqueado → retorna config de bloqueo → Alia responde y termina.
       b. Resuelve `PhoneNumber` activo por `twilio_number`.
       c. Carga `CallFlow` general asociado al PhoneNumber.
       d. Carga `CorporateVoiceProfile` de la `Company` (incluye `voice_name`).
       e. Carga todas las `Section` activas con `call_flow` asignado + `SectionSchedule`
          + `Contact`. Las secciones sin `call_flow` asignado se IGNORAN.
       f. Consulta `PresenceStatus` activo de todos los `Contact` internos.
       g. Ensambla `system_instruction` del CallFlow general (bienvenida + organigrama
          de secciones activas con sus horarios y presencia).
       h. Retorna `(system_instruction, initial_greeting, voice_name,
          section_callflow_map)` donde `section_callflow_map` es un dict
          `{section_id: CallFlow}` con los flujos de las secciones activas.
   → Fallback automático a `SYSTEM_INSTRUCTION_FALLBACK` / `INITIAL_GREETING_FALLBACK`
     / `VOICE_NAME_FALLBACK = 'Aoede'` si `build_live_config()` lanza excepción.

   FASE 2 — Identificación de sección destino (Estrategia B — PENDIENTE PASO 37):
   → El agente (Alia) identifica la intención del llamante mediante conversación.
   → Cuando la sección destino queda clara, `VoiceOrchestrationService` carga el
     `CallFlow` específico de esa sección desde `section_callflow_map`.
   → Se reinyecta el nuevo `system_instruction` de sección en la sesión Gemini Live
     activa mediante `session.send_client_content(turns=..., turn_complete=True)`.
   → El agente continúa la conversación con el contexto específico de la sección.

   FASE 3 — Fallback:
   → Si ninguna sección puede atender (todas inactivas, horario cerrado o sin flujo):
   → El agente carga el `CallFlow` de `CallFlow.fallback_section` del flujo general.
   → Transfiere la llamada al responsable humano de la sección fallback.

5. Twilio envía eventos `media` sucesivos
   → Se reenvían a `service.receive_twilio_audio()`.

6. Twilio envía evento `stop`
   → `service.terminate_session()` señaliza el fin de sesión.

### 4.2. Notificación al responsable de sección ← NUEVO (sesión 2026-04-15)
Una vez que Alia completa la toma de datos del llamante, notifica al responsable:
1. **Llamada saliente Twilio** al teléfono del `Contact` responsable de la sección.
   Alia lee el resumen: nombre cliente, teléfono, servicio, ubicación.
2. **WhatsApp** al responsable (cuando Hito 4 esté operativo).
3. **Email vía SendGrid** al `Contact.email` del responsable (diferido al Hito 4).

El mecanismo de notificación se implementa mediante **function calling de Gemini Live**:
Alia invoca `notify_section_contact(section_name, client_name, phone, service, location)`
y el backend ejecuta las acciones reales sin interrumpir el audio en curso.

### 4.3. Archivos del pipeline de voz
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
    · Notificación al responsable: llamada saliente Twilio + WhatsApp (Hito 4).
    · Bloqueo de números maliciosos con duración configurable.
    · Modo demo con frase clave + DTMF 7463.
- Extensiones de modelo acordadas y documentadas en `V03DOC_DATA_MODEL.md` (PMA):
    · `Contact`: campos `email` y `gender`.
    · `Section`: campo `is_24h`.
    · `CallFlow`: campo `notification_contact`.
    · Nuevo modelo `SectionSchedule`.
    · Nuevo modelo `BlockedCaller`.
- Pasos 31 y 32 implementados y validados E2E en producción.

### Sesión 2026-04-15 — Responsive + Gestión de Contraseñas + Hoja de Ruta
- Auditoría y corrección responsive completa del panel (Sección 3.5):
    · Sidebar offcanvas con hamburguesa en móvil.
    · Padding adaptativo, tablas responsive, formset táctil-friendly.
    · Fix navegación offcanvas (`data-bs-dismiss` eliminado de enlaces).
    · Fix btn-close offcanvas (movido a `offcanvas-header` estándar Bootstrap).
    · Clases de color de círculos de presencia migradas de inline a CSS.
- Gestión de contraseñas CompanyUser implementada (Paso 33-B):
    · Campo `must_change_password` en `CompanyUser`. Migración 0004 aplicada.
    · `CompanyUserCreateView`: alta de usuarios desde panel con contraseña inicial.
    · `PanelPasswordChangeView`: cambio de contraseña propio con forced-redirect.
    · `CompanyUserUpdateView`: acción `force_reset` para el ADMIN.
    · Toggle mostrar/ocultar y barra de seguridad en todos los campos de contraseña.
    · Templates: `password/change.html`, `users/create.html` (neonatos puros).
    · Templates actualizados: `users/list.html`, `users/form.html`, `login.html`.
- Hoja de ruta ampliada con Pasos 33-A, 33-C, 33-D, 33-E acordados en sesión.
- Decisiones de arquitectura acordadas:
    · Notificación al responsable: llamada saliente Twilio + WhatsApp (email diferido).
    · Mecanismo de notificación: function calling de Gemini Live.
    · Voz del agente configurable por empresa vía `CorporateVoiceProfile.voice_name`.
    · Restauración de CallFlow y CorporateVoiceProfile: campos backup_* en modelo.

---

## SECCIÓN 7 — PENDIENTES DIFERIDOS

1. `DataCaptureSet` por sección: campos específicos para Elevación, Asistencia y Grúas
   a definir con Grupo Álvarez (tipo_grua, tonelaje, tipo_vehiculo, matricula, etc.).
2. Recepción de ubicación GPS: integración con localización nativa WhatsApp +
   Grounding Google Maps (diferido a reactivación del Hito 4).
3. Sistema de recordatorios de presencia vía WhatsApp: diferido al Hito 4.
4. Email vía SendGrid al responsable tras toma de datos: diferido al Hito 4.
5. Calibración VAD adicional: ajuste fino pendiente tras más pruebas con
   distintos dispositivos y condiciones de llamada.
6. Configuración real de producción de Grupo Álvarez: `CallFlow` y
   `CorporateVoiceProfile` definitivos pendientes de organigrama real.
7. Sección Grúas: no existe aún en BD. Añadir cuando se disponga del contacto real.
8. Registro de usuarios empresa: flujo de alta con invitación por email (diferido).

---

## SECCIÓN 8 — HOJA DE RUTA

### Pasos 1–30 ✅ COMPLETADOS
Ver registro de sesiones en Sección 6.

### Paso 31 — Extensiones de modelo en `ivr_config/models.py` ✅ COMPLETADO (2026-04-13)
Campos `email`, `gender` en `Contact`; `is_24h` en `Section`;
`notification_contact` en `CallFlow`; nuevos modelos `SectionSchedule` y
`BlockedCaller`. Migraciones aplicadas.

### Paso 32 — Extensión del panel con nuevos módulos ✅ COMPLETADO (2026-04-13)
Gestión de `SectionSchedule` (inline en Section) y `BlockedCaller` (listado,
alta, desbloqueo, historial). Validación E2E en producción.

### Paso 33-A — Configuración MailerSend ⏸ DEUDA TÉCNICA
Bloqueado hasta compra del dominio `enterprisebot.com` (o `.es`) y verificación
en MailerSend. Cuenta MailerSend activa (plan Free, 500 emails/mes). Dominio
`campustudionline.com` verificado pero no usable para EnterpriseBot.
Se implementará en el Hito 4 o cuando el dominio esté disponible.

### Paso 33-B — Gestión de contraseñas CompanyUser ✅ COMPLETADO (2026-04-15)
Campo `must_change_password` en `CompanyUser`. Migración 0004 aplicada.
`CompanyUserCreateView`, `PanelPasswordChangeView`, acción `force_reset`.
Toggle mostrar/ocultar + barra de seguridad en todos los campos de contraseña.
Templates: `password/change.html`, `users/create.html`, actualizaciones en
`users/list.html`, `users/form.html`, `login.html`.

### Paso 33-C — Function calling Gemini Live: notify_section_contact ⏳ PENDIENTE (diferido al Hito 4)
Definir tool `notify_section_contact(section_name, client_name, phone, service,
location)` en `LiveConnectConfig` de `vox_bridge/services.py`.
Implementar handler en `vox_bridge/services.py` que ejecute:
  · Llamada saliente Twilio al `Contact.phone_number` del responsable.
  · WhatsApp al responsable (stub hasta activación Hito 4).
Alia invoca la función al completar la toma de datos, espera confirmación
del handler e informa al cliente del resultado.
Criterio de éxito: llamada real genera llamada saliente al responsable confirmada
en logs de Twilio y en la conversación con el llamante.

### Paso 33-D — Selector de voz Gemini por empresa ✅ COMPLETADO (2026-04-16)
Campo `voice_name` añadido a `CorporateVoiceProfile` con 8 voces confirmadas
para `gemini-live-2.5-flash-native-audio` en Vertex AI: Aoede, Puck, Charon,
Kore, Fenrir, Leda, Orus, Zephyr. Migración 0005 aplicada.
`build_live_config()` retorna `voice_name` como tercer elemento de la tupla.
`vox_bridge/services.py`: `self.voice_name` dinámico en `PrebuiltVoiceConfig`.
`CorporateVoiceProfileForm`: selector `voice_name` como primer campo.
Template `voiceprofile/detail.html` actualizado con selector.
Validado: cambiar voz desde panel afecta a la siguiente llamada sin reinicio.

### Paso 33-E — Restauración de CallFlow y CorporateVoiceProfile ✅ COMPLETADO (2026-04-16)
Campos `backup_*` añadidos a `CallFlow` (system_instruction, initial_greeting,
notification_contact) y `CorporateVoiceProfile` (voice_name, tone_guidelines,
sample_responses, forbidden_phrases). Migración 0006 aplicada.
`CallFlowUpdateView.form_valid()` y `CorporateVoiceProfileUpdateView.post()`
guardan snapshot previo antes de cada save. Swap activo ↔ backup bidireccional.
Vistas `CallFlowRestoreView` y `VoiceProfileRestoreView` (POST).
Botón condicional "Restaurar versión anterior" en ambos templates.
Validado: restauración funciona desde el panel con un solo clic.

### Paso 33 — Actualización de `build_live_config()` ✅ COMPLETADO (2026-04-16)
`ivr_config/services.py` completamente actualizado:
- Firma: `build_live_config(twilio_number, caller_number='')` → `tuple[str,str,str]`.
- Step 0: verificación `BlockedCaller` activo — retorna config de rechazo si bloqueado.
- Helpers nuevos: `_is_caller_blocked()` y `_build_section_schedule_context()`.
- `_build_section_schedule_context()`: evalúa `is_24h` y `SectionSchedule` por
  weekday y hora local para cada sección activa.
- Ensamblado: CallFlow base + VoiceProfile + horarios de secciones + presencia.
- Retorna `(system_instruction, initial_greeting, voice_name)`.

### Paso 34 — Captura del número llamante en `voice_sidecar_bridge.py` ✅ COMPLETADO (2026-04-16)
`handle_twiml_post()`: captura `From` → `self._pending_caller_number`.
Evento `start`: consume `self._pending_caller_number` y lo pasa a
`VoiceOrchestrationService(twilio_number=..., caller_number=...)`.
`vox_bridge/services.py`: `__init__` acepta `caller_number`, lo almacena
en `self.caller_number`, lo pasa a `build_live_config()` en `run_voice_session()`.

### Paso 35 — Seed de datos piloto Grupo Álvarez actualizado ✅ COMPLETADO (2026-04-16)
`seed_grupo_alvarez.py` actualizado:
- `CorporateVoiceProfile`: añadido `voice_name=VOICE_AOEDE` en defaults.
- `Section Asistencia`: `is_24h=True` en datos de seed.
- `_seed_sections()`: aplica `is_24h` del seed data y lo actualiza si ya existe.
- `_seed_section_schedules()`: crea 5 franjas L-V 08:00-18:00 para Elevación.
- `SectionSchedule` y `Contact` añadidos a imports.
Seed ejecutado: 5 franjas SectionSchedule creadas, capabilities actualizados a VOICE.

### Paso 36 — Validación E2E del flujo completo ⏳ PENDIENTE
Realizar llamada real al `+34951796832` y verificar:
- Alia identifica correctamente el tipo de servicio solicitado.
- Alia informa correctamente de la disponibilidad de la sección (horario).
- Alia recoge datos conversacionalmente (nombre, teléfono, servicio, ubicación).
- Alia notifica al responsable (llamada saliente Twilio).
- Alia responde correctamente ante llamada fuera de actividad.
- Modo demo funciona con frase clave + DTMF 7463.
- Número bloqueado recibe respuesta estándar y cierre inmediato.
Criterio de éxito: todos los tipos de llamada se comportan según la tabla
de la Sección 4.1 sin intervención manual en BD ni código.

---

### Paso 37 — Implementación Estrategia B: Carga Dinámica de CallFlow por Intención ⏳ PENDIENTE

**Contexto:** Los modelos `Section.call_flow` y `CallFlow.fallback_section` ya están
implementados y migrados (migración 0007, sesión 2026-04-16). Este paso implementa
la lógica de motor que los consume en tiempo de llamada.

**Alcance de cambios — OBLIGATORIO ejecutar en este orden:**

#### 37.A — `ivr_config/services.py` — Extensión de `build_live_config()`
Modificar la firma y el cuerpo de `build_live_config()` para:
1. En el Step e (carga de secciones activas), filtrar EXCLUSIVAMENTE las secciones
   con `call_flow` asignado y activo: `Section.objects.filter(company=company,
   is_active=True, call_flow__isnull=False, call_flow__is_active=True)`.
2. Construir el `section_callflow_map`: dict `{section.pk: section.call_flow}`
   para consumo en `VoiceOrchestrationService`.
3. Ampliar la tupla de retorno de 3 a 4 elementos:
   `return (system_instruction, initial_greeting, voice_name, section_callflow_map)`
   donde `section_callflow_map: dict[int, CallFlow]`.
4. Actualizar el docstring bilingüe con la nueva firma y semántica.

#### 37.B — `vox_bridge/services.py` — Extensión de `VoiceOrchestrationService`
1. En `run_voice_session()`, actualizar el desempaquetado de `build_live_config()`:
   `self.system_instruction, self.initial_greeting_text, self.voice_name,
   self.section_callflow_map = await sync_to_async(build_live_config)(...)`
   Añadir `self.section_callflow_map: dict = {}` como atributo de instancia en
   `__init__()` (valor inicial vacío, poblado en `run_voice_session()`).
2. Implementar el método `async def _reload_session_for_section(self, session,
   section_pk: int) -> bool`:
   - Busca `section_pk` en `self.section_callflow_map`.
   - Si no existe o la sección no tiene CallFlow → retorna False.
   - Construye nuevo `system_instruction` concatenando el `CallFlow.system_instruction`
     de la sección + bloque de presencia y horario relevante para esa sección.
   - Reinyecta en la sesión Gemini Live activa mediante:
     `await session.send_client_content(turns=[types.Content(parts=[
     types.Part(text=nuevo_system_instruction)], role='user')], turn_complete=True)`
   - Actualiza `self.system_instruction` con el nuevo valor.
   - Retorna True si la reinyección fue exitosa.
3. Implementar el método `async def _activate_fallback_section(self, session) -> bool`:
   - Obtiene `CallFlow.fallback_section` del flujo general cargado al inicio.
   - Si no hay fallback_section configurada → loguea warning y retorna False.
   - Construye el system_instruction del fallback con las instrucciones de
     transferencia al responsable humano.
   - Reinyecta en sesión activa con el mismo mecanismo de `send_client_content`.
   - Retorna True si fue exitoso.
4. El mecanismo de detección de intención de sección queda como STUB en esta
   fase — se implementará en el Paso 38. En el Paso 37 basta con que los métodos
   `_reload_session_for_section()` y `_activate_fallback_section()` existan,
   estén correctamente documentados y sean invocables desde `run_voice_session()`.

#### 37.C — Panel (`panel/` app) — Vistas de asignación de CallFlow a Section
Añadir al panel personalizado la capacidad de asignar `call_flow` a cada `Section`
y designar `fallback_section` en el `CallFlow` general:
1. `panel/forms.py`: añadir campo `call_flow` al `SectionForm` existente.
   Queryset filtrado por `company` del usuario autenticado y `is_active=True`.
2. `panel/forms.py`: añadir campo `fallback_section` al `CallFlowForm` existente.
   Queryset filtrado por `company` del usuario autenticado y `is_active=True`.
3. `panel/templates/panel/sections/form.html`: añadir selector de `call_flow`
   con etiqueta 'Flujo IVR de sección' y help text explicativo de la Estrategia B.
4. `panel/templates/panel/callflows/form.html`: añadir selector de `fallback_section`
   con etiqueta 'Sección de fallback' y help text explicativo.
Ambos campos son opcionales en el formulario (no obligatorios en el modelo).

**Criterio de éxito del Paso 37:**
- `build_live_config()` retorna tupla de 4 elementos sin romper el fallback existente.
- `VoiceOrchestrationService` almacena el `section_callflow_map` en `self`.
- `_reload_session_for_section()` y `_activate_fallback_section()` existen y están
  documentados aunque el trigger de detección de intención sea un stub.
- El panel permite asignar `call_flow` a secciones y `fallback_section` a CallFlows.
- Las migraciones de formularios no requieren migración de BD (campos ya existen).

### Paso 38 — Detección de Intención de Sección en el Audio ⏳ PENDIENTE
Este paso implementa el mecanismo de detección de la intención del llamante para
determinar qué sección desea y activar la Fase 2 de la Estrategia B:
- Investigar el mecanismo de function calling disponible en `gemini-live-2.5-flash-
  native-audio` con SDK `google-genai 1.69.0` en Vertex AI. Específicamente:
  si el modelo puede invocar funciones Python desde el audio en tiempo real
  (tool_use en sesión Live) sin interrumpir el flujo de audio.
- Si function calling está disponible: definir tool `route_to_section(section_id: int)`
  en `LiveConnectConfig.tools`. Cuando Alia detecte la sección destino, invocará
  la función y el handler llamará a `_reload_session_for_section(session, section_id)`.
- Si function calling NO está disponible en Live: implementar detección por análisis
  de transcripción parcial — Alia anuncia verbalmente la sección destino con un
  patrón reconocible, el bridge lo detecta y activa la reinyección.
- La investigación debe hacerse en línea (PAH 4.4 — actualización obligatoria)
  antes de implementar ninguna línea de código.
Criterio de éxito: llamada real en la que Alia detecta el tipo de servicio y
carga el CallFlow de la sección correspondiente de forma transparente al llamante.

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
implementados y validados E2E en producción son:
 login, dashboard, presencia propia,
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
textual, notificación al responsable por llamada saliente Twilio y WhatsApp, bloqueo
de números maliciosos con duración configurable, y modo demo con frase clave más DTMF
7463. Se acuerdan y documentan las extensiones de modelo necesarias (SectionSchedule,
BlockedCaller, campos email/gender/is_24h/notification_contact). Se actualiza
V03DOC_DATA_MODEL.md con la especificación técnica completa (PMA) y se reescribe el
presente anexo con la hoja de ruta actualizada (Pasos 31–36).

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

### Sesión 2026-04-16 (reactivación)
**Título:** Reactivación Hito 3 — Diseño Estrategia B: Carga Dinámica de CallFlow por Intención
**Descripción:** Sesión de reactivación del Hito 3 desde el Hito 4. Se diseña y aprueba
la arquitectura completa de la Estrategia B (carga dinámica de CallFlow por intención de
sección): cada Section tiene su propio CallFlow específico que el motor carga cuando el
agente detecta la intención del llamante, en lugar de un system_instruction monolítico.
Cada CallFlow general tiene una fallback_section designada por número para transferencia
humana. Los modelos Section.call_flow y CallFlow.fallback_section son implementados y
migrados (migración 0007 aplicada). Se documenta el Paso 37 (implementación del motor
de carga dinámica en ivr_config/services.py, vox_bridge/services.py y panel) y el Paso 38
(detección de intención de sección en audio, pendiente de investigación sobre function
calling en gemini-live-2.5-flash-native-audio con SDK 1.69.0). El hito queda EN PROGRESO
con los Pasos 37 y 38 como hoja de ruta de la siguiente sesión.

### Sesión 2026-04-16 (cierre anterior)
**Título:** Cierre Hito 3 — Pasos 33-D, 33-E, 33, 34, 35 y apertura Hito 4
**Descripción:** Sesión de cierre del Hito 3 e inicio del Hito 4. Se completan los
pasos pendientes de la hoja de ruta: selector de voz Gemini Live por empresa (33-D,
migración 0005), restauración de CallFlow y VoiceProfile con campos backup_* (33-E,
migración 0006), build_live_config() completo con BlockedCaller, SectionSchedule,
presencia y voice_name (Paso 33), captura de caller_number (From) en bridge (Paso 34)
y seed actualizado con SectionSchedule L-V para Elevación (Paso 35). Se documenta
la investigación de registro de número WhatsApp en documento satélite
V04DOC_WHATSAPP_NUMBER_REGISTRATION.md. Se actualiza el MASTER_DOCUMENT permutando
estados: Hito 3 → COMPLETADO, Hito 4 → EN PROGRESO.

### Sesión 2026-04-15
**Título:** Panel EnterpriseBot: Auditoría y Corrección Responsive Completa
**Descripción:** Sesión dedicada a identificar y corregir todos los defectos de diseño
responsive del panel personalizado (/panel/). Se auditaron los 14 templates Bootstrap
5.3 del panel en busca de columnas mal dimensionadas, tablas sin table-responsive,
formularios con inputs inadecuados para pantalla táctil y navegación no colapsable
en móvil. Se aplicaron las correcciones necesarias en cada template siguiendo las
directrices de la Sección 3.5 del anexo. Criterio de éxito: el panel es completamente
operable desde un dispositivo móvil sin desplazamiento horizontal ni elementos
inaccesibles con el dedo.
