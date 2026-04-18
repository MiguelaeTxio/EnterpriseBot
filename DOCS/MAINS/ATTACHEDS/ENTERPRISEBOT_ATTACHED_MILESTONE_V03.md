# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# ENTERPRISEBOT — ANEXO HITO V03 — IVR CONVERSACIONAL CONFIGURABLE DESDE PRODUCCIÓN
**Estado:** EN PROGRESO
**Fecha de inicio:** 2026-04-07
**Fecha de reanudación:** 2026-04-17 (tercera reactivación)
**Última actualización:** 2026-04-18 (PCS)

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

## SECCIÓN 4 — PIPELINE DE VOZ Y ARQUITECTURA DE TRANSFERENCIA

Ver especificación técnica completa de la arquitectura de transferencia en:
`DOCS_ATTACHED_2_ANNEX_V03/V03DOC_TRANSFER_ARCHITECTURE.md`

### 4.1. Flujo de llamada entrante — Visión General

**FASE 0 — Audio de bienvenida (Paso 41):**
Twilio realiza POST `/api/vox/inbound/`. El bridge responde con TwiML `<Play>` del
archivo `intro.mp3` (3-5s de música) seguido de `<Connect><Stream>`. El llamante
escucha la música antes de que Alia comience a hablar.

**FASE 1 — Bienvenida e identificación de sección (Estrategia B):**
1. Twilio abre el WebSocket `/media`. Se instancia `VoiceOrchestrationService`.
2. `build_live_config()` carga CallFlow general, CorporateVoiceProfile, secciones
   activas con `call_flow` asignado, horarios, presencia e IDENTIFICADORES DE SECCIÓN.
   Retorna tupla de 5 elementos: `(system_instruction, initial_greeting, voice_name,
   section_callflow_map, general_call_flow)`.
3. Alia saluda al llamante e identifica su intención mediante conversación.
4. Cuando la sección queda clara, Alia invoca `route_to_section(section_id)` via
   function calling. El bridge llama a `_reload_session_for_section()` y reinyecta
   el `system_instruction` del CallFlow de sección en la sesión Gemini Live activa.
5. Alia continúa con el contexto específico de la sección.

**FASE 2 — Transferencia real al responsable (Pasos 39-42):**
1. El CallFlow de sección instruye a Alia para transferir la llamada.
2. Alia invoca `transfer_to_section_contact(section_id)` via function calling.
3. El bridge cierra el WebSocket del Media Stream (salida de Gemini Live).
4. El bridge actualiza la llamada vía REST API con TwiML `<Dial><Conference>`.
   El llamante entra en la Conference y escucha música de espera (`hold.mp3`).
5. El bridge llama al responsable de la sección vía llamada saliente Twilio.

**FASE 3A — Transferencia exitosa:**
El responsable acepta y se une a la Conference. Música cesa. Conversación directa.
Alia queda desconectada. La llamada finaliza cuando cualquiera cuelga.

**FASE 3B — Transferencia fallida (responsable no responde):**
Timeout del `<Dial>` (30s) → Twilio dispara el action webhook.
El bridge reconecta a Alia con nuevo Media Stream. Alia informa al llamante y
ofrece dejar un mensaje de voz. Se registra `PendingNotification` en BD.
Cuando WhatsApp esté operativo (Hito 4), Celery procesa los registros pendientes.

### 4.2. Decisión arquitectónica: Transferencia real vs notificación saliente

La arquitectura original (sesiones 2026-04-13 a 2026-04-16) contemplaba una
**notificación saliente**: Alia recogía datos del llamante y llamaba al responsable
de forma independiente, sin transferir la llamada original.

En sesión 2026-04-17 se acordó el rediseño hacia **transferencia real**:
- La llamada original se transfiere al responsable mediante `<Dial><Conference>`.
- El llamante escucha música de espera en lugar de seguir hablando con Alia.
- Si el responsable no responde, Alia retoma la llamada y ofrece mensaje de voz.
- La notificación WhatsApp queda como mecanismo de fallback (stub hasta Hito 4).

### 4.3. Archivos del pipeline de voz
- `ivr_config/services.py` — `build_live_config()` → tupla de 5 elementos.
- `vox_bridge/services.py` — `VoiceOrchestrationService`: Estrategia B completa,
  function calling `route_to_section` y `transfer_to_section_contact` (Paso 39).
- `voice_sidecar_bridge.py` — Bridge aiohttp: captura `To` y `From`, gestión
  del ciclo de vida del Media Stream, reconexión tras transferencia fallida.
- `voice_orchestrator.py` — Arranque de ngrok + actualización webhook regional.
- `vox_bridge/views.py` — Nuevos endpoints: `TransferCallView`, `HoldMusicView`,
  `TransferStatusView`, `TransferAcceptView` (Pasos 39-42).
- `ivr_config/models.py` — Nuevo modelo `PendingNotification` (Paso 40).
- `vox_bridge/static/vox_bridge/audio/` — Archivos `intro.mp3` y `hold.mp3`.

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
4. Email vía SendGrid al responsable: diferido al Hito 4.
5. Calibración VAD adicional: ajuste fino pendiente tras más pruebas con
   distintos dispositivos y condiciones de llamada.
6. Configuración real de producción de Grupo Álvarez: `CallFlow` y
   `CorporateVoiceProfile` definitivos pendientes de organigrama real.
7. Sección Grúas: no existe aún en BD. Añadir cuando se disponga del contacto real.
8. Registro de usuarios empresa: flujo de alta con invitación por email (diferido).
9. Notificación WhatsApp vía `PendingNotification`: stub activo hasta Hito 4.
   Celery procesará los registros pendientes cuando WhatsApp esté operativo.
10. Archivos de audio `intro.mp3` y `hold.mp3`: música clásica instrumental
    (estilo Beethoven, Ravel, Tchaikovsky). Miguel Ángel aportará el MP3.
    Requisitos técnicos en `V03DOC_TRANSFER_ARCHITECTURE.md`.
    `hold.mp3`: >30s, instrumental. `intro.mp3`: 3-5s, mismo estilo.

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

### Paso 36 — Validación E2E del flujo completo ✅ COMPLETADO (2026-04-17)
Llamada real al `+34951796832` confirmada: Alia identificó correctamente la sección,
informó de disponibilidad, recogió datos conversacionalmente y se despidió.
La rellamada al responsable (Paso 39) estaba pendiente de implementación.
Número bloqueado, modo demo y fuera de horario validados en sesión posterior.

---

### Paso 37 — Implementación Estrategia B: Carga Dinámica de CallFlow por Intención ✅ COMPLETADO (2026-04-17)
- `ivr_config/services.py`: `_build_section_schedule_context()` retorna tupla
  `(schedule_context, section_callflow_map)`. `build_live_config()` retorna
  tupla de 5 elementos: `(system_instruction, initial_greeting, voice_name,
  section_callflow_map, general_call_flow)`.
- `vox_bridge/services.py`: `self.section_callflow_map`, `self.general_call_flow`
  en `__init__()`. Desempaquetado de 5 elementos en `run_voice_session()`.
  Métodos `_reload_session_for_section()` y `_activate_fallback_section()` implementados.
- `panel/forms.py`: campos `call_flow` en `SectionForm` y `fallback_section` en
  `CallFlowForm`. Querysets restringidos por empresa en vistas.
- Templates `sections/form.html` y `callflows/form.html` actualizados con selectores.
- Fix logout Django 5.x: `http_method_names` extendido en `PanelLogoutView`.
- Validado: selectores visibles en panel, flujo sin regresiones.

### Paso 38 — Detección de Intención de Sección: Function Calling route_to_section ✅ COMPLETADO (2026-04-17)
- Investigación confirmada: `gemini-live-2.5-flash-native-audio` soporta function
  calling en sesión Live con SDK `google-genai 1.69.0` en Vertex AI.
- `vox_bridge/services.py`: `FunctionDeclaration` `route_to_section(section_id: int)`
  registrada en `LiveConnectConfig.tools` (solo si `section_callflow_map` no vacío).
- Bloque `IDENTIFICADORES DE SECCIÓN` (tabla pk → nombre) inyectado en
  `system_instruction` por `build_live_config()` para que el modelo use IDs correctos.
- Handler `tool_call` implementado en `_receive_gemini_audio()`: captura invocación,
  llama a `_reload_session_for_section()`, responde con `tool_response`.
- Validación E2E pendiente de llamada real con sección configurada.

---

### Paso 39 — Sistema de Transferencia Resiliente Multi-Contacto ✅ COMPLETADO (2026-04-18)

**REDISEÑO ACORDADO EN SESIÓN 2026-04-17** respecto al diseño inicial.
Ver especificación técnica completa en `V03DOC_TRANSFER_ARCHITECTURE.md`.

#### Errores de diseño identificados y corregidos:
- El filtro `is_internal=True` en `_execute_transfer()` es incorrecto: los
  contactos destino de una transferencia pueden ser externos (p. ej. el
  responsable de administración que gestiona proveedores sin ser usuario del panel).
  El criterio correcto es: primer contacto de la sección con `phone_number` válido,
  independientemente de `is_internal`.
- El `section_id` no debe hardcodearse en el `system_instruction` del CallFlow
  de sección. Alia lo obtiene del bloque `IDENTIFICADORES DE SECCIÓN` que
  `build_live_config()` inyecta dinámicamente.

#### Nuevos modelos requeridos (migración 0008):

**`SectionContact`** — tabla intermedia explícita que reemplaza la relación M2M
implícita `Section.contacts`. Añade campo `priority` (IntegerField) para controlar
el orden de intento de transferencia desde el panel:
    - `section` (FK → Section, CASCADE)
    - `contact` (FK → Contact, CASCADE)
    - `priority` (IntegerField, default=0 — menor número = mayor prioridad)
    - `created_at` (DateTimeField, auto_now_add)
    Meta: unique_together = [('section', 'contact')], ordering = ['section', 'priority', 'contact__name']

**`TransferAttempt`** — persiste el estado de la transferencia entre el bridge
y el webhook `TransferStatusView`. Necesario porque Twilio no envía contexto
de sesión en el action webhook — la persistencia en BD es el único mecanismo
viable para mantener el estado entre ambos procesos:
    - `call_sid` (CharField max_length=40, unique=True, db_index=True)
    - `section` (FK → Section, SET_NULL, null=True)
    - `twilio_number` (CharField max_length=20)
    - `caller_number` (CharField max_length=20)
    - `contact_index` (IntegerField, default=0 — índice del contacto intentado)
    - `status` (CharField choices: PENDING / FAILED / COMPLETED, default=PENDING)
    - `created_at` (DateTimeField, auto_now_add)
    - `updated_at` (DateTimeField, auto_now)

**`PendingNotification`** — registra llamadas donde todos los contactos fallaron
y el llamante optó por dejar sus datos para ser contactado:
    - `company` (FK → Company, CASCADE)
    - `section` (FK → Section, SET_NULL, null=True)
    - `caller_number` (CharField max_length=20)
    - `call_sid` (CharField max_length=40)
    - `voice_recording_url` (URLField, blank=True)
    - `channel` (CharField choices: WHATSAPP / SMS / EMAIL / PENDING, default=PENDING)
    - `created_at` (DateTimeField, auto_now_add)
    - `notified_at` (DateTimeField, null=True, blank=True)
    - `notes` (TextField, blank=True)

#### Flujo resiliente multi-contacto:

`_execute_transfer(section_id)` en `vox_bridge/services.py`:
1. Obtiene lista de contactos de la sección ordenada por `SectionContact.priority`
   ASC, filtrando por `phone_number` no vacío (sin filtro `is_internal`).
2. Selecciona el contacto en `contact_index=0`.
3. Crea registro `TransferAttempt(call_sid, section, twilio_number, caller_number,
   contact_index=0, status=PENDING)`.
4. Actualiza la llamada del llamante con TwiML `<Dial><Conference>` (música de espera).
5. Establece `session_active=False` (cierra Gemini Live).
6. Realiza llamada saliente al contacto seleccionado.

`TransferStatusView` en `vox_bridge/views.py` (action webhook Twilio):
1. Consulta `TransferAttempt` por `call_sid`.
2. Lee `DialCallStatus`:
   - `completed` → `TransferAttempt.status=COMPLETED` → TwiML vacío → fin.
   - `no-answer / busy / failed` → incrementa `contact_index` en el registro.
     - Si existe contacto en `contact_index+1` (siguiente por prioridad):
       Reconecta Alia con nuevo Media Stream. Alia informa: "La Sra./Sr. X no
       está disponible en este momento. ¿Desea que intente ponerle en contacto
       con la Sra./Sr. Y, dejar un mensaje de voz, o que le llamen cuando esté
       disponible?" Alia gestiona la respuesta del llamante e invoca
       `transfer_to_section_contact` de nuevo si elige el siguiente contacto.
     - Si no hay más contactos:
       Reconecta Alia. Alia ofrece mensaje de voz o callback.
       Registra `PendingNotification` en BD.

#### Cambios en el panel:
- `SectionContact` con campo `priority` editable mediante formset inline en
  el formulario de sección (`/panel/sections/{pk}/edit/`).
  Ordenable por prioridad (input numérico). Reemplaza el widget M2M actual.
- `PendingNotification` listado de solo lectura en panel (módulo nuevo).

#### Archivos afectados:
- `ivr_config/models.py` — nuevos modelos `SectionContact`, `TransferAttempt`,
  `PendingNotification`. Migración 0008.
- `vox_bridge/services.py` — `_execute_transfer()` refactorizado.
- `vox_bridge/views.py` — `TransferStatusView` refactorizado con flujo multi-contacto.
- `panel/forms.py` — formset inline `SectionContactFormSet`.
- `panel/views.py` — `SectionCreateView` / `SectionUpdateView` con formset de contactos.
- `panel/templates/panel/sections/form.html` — tabla de contactos con prioridad.
- `panel/urls.py` — nueva ruta `pending_notifications/`.
- `panel/templates/panel/pending_notifications/list.html` — nuevo template.

Criterio de éxito: llamada real en la que el primer contacto no responde,
Alia ofrece el segundo contacto al llamante, el llamante elige, y la segunda
transferencia conecta correctamente con el segundo contacto.

### Paso 40 — Audio de bienvenida `intro.mp3` y espera `hold.mp3` ✅ COMPLETADO (2026-04-18)
Miguel Ángel aportará el archivo MP3 de música clásica (estilo Beethoven / Ravel /
Tchaikovsky). El mismo archivo puede usarse para `hold.mp3` (espera durante la
transferencia) y para `intro.mp3` (3-5s antes del saludo de Alia, recortado del mismo).

`hold.mp3`:
- Formato: MP3, >30 segundos, instrumental sin voz.
- Ruta destino: `vox_bridge/static/vox_bridge/audio/hold.mp3`.
- `HoldMusicView` ya implementada — sirve TwiML `<Play loop="0">`.
- Ejecutar `collectstatic` tras despliegue.

`intro.mp3`:
- Formato: MP3, 3-5 segundos (recorte del mismo archivo clásico).
- Ruta destino: `vox_bridge/static/vox_bridge/audio/intro.mp3`.
- Añadir `<Play>` en `handle_twiml_post()` de `voice_sidecar_bridge.py`
  antes del `<Connect><Stream>`.

Criterio de éxito: el llamante escucha la música clásica tanto al inicio de la
llamada (intro) como durante la espera de transferencia (hold).

### Paso 41 — Validación E2E Sistema de Transferencia Completo ⏳ PENDIENTE

Validación E2E parcial completada en sesión 2026-04-18. Pendiente de validación
completa del flujo multi-contacto (segundo contacto y PendingNotification).

Realizar llamada real con el sistema de transferencia resiliente activo:
1. Alia identifica la sección → carga CallFlow de sección.
2. Alia recoge datos → invoca `transfer_to_section_contact`.
3. Llamante escucha música de espera (por defecto Twilio).
4. Primer contacto no responde → Alia reconecta → ofrece segundo contacto.
5. Segundo contacto acepta → conversación directa → llamada completada.
6. Alternativamente: todos los contactos fallan → `PendingNotification` en BD.
Criterio de éxito: flujo completo E2E sin intervención manual.

#### Deudas técnicas identificadas en sesión 2026-04-18

**DT-1 — TransferAttempt.status no se actualiza a COMPLETED:**
`TransferStatusView` actualiza el status a COMPLETED cuando `DialCallStatus=completed`
pero los registros permanecen en PENDING. Investigar si el webhook `transfer_status`
recibe correctamente el POST de Twilio tras la transferencia exitosa.

**DT-2 — Fallback "no le he entendido" en CallFlow general:**
Añadir en el `system_instruction` del CallFlow general de Grupo Álvarez la regla:
"Si no entiendes al llamante, responde: 'Disculpe, no le he entendido. ¿Podría repetirlo?'"
Esto se hace desde el panel en `/panel/callflows/` — no requiere cambio de código.

**DT-3 — Pausa de transferencia (3.5s) puede ser insuficiente en algunos casos:**
La pausa fija post-drenado de `audio_output_queue` antes de `_execute_transfer()`
es de 3.5s. En condiciones de red lenta puede seguir cortándose la última frase
de Alia. Pendiente de calibración con más pruebas reales.

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

### Sesión 2026-04-18
**Título:** Paso 39: Sistema de Transferencia Resiliente — Modelos, Endpoints, Audio y Validación E2E
**Descripción:** Sesión de implementación completa del Paso 39 del Hito 3 y avance en el Hito 4.
Paso 39: creación de los modelos SectionContact (through M2M con priority), TransferAttempt y
PendingNotification con migración 0008 usando SeparateDatabaseAndState para preservar relaciones
M2M existentes. Refactorización de _execute_transfer() eliminando filtro is_internal, usando
SectionContact.priority y creando TransferAttempt en BD antes de llamar a Twilio. Refactorización
de TransferStatusView con flujo resiliente multi-contacto. Fix crítico del cliente Twilio:
migración a credenciales IE1 con edge="dublin" y region="ie1" para resolver HTTP 404 en
calls.update() en región IE1. Paso 40: despliegue de hold.mp3 (Sonata nº 14 Beethoven) e
intro.mp3 (recorte 4s con ffmpeg). Validación E2E con múltiples iteraciones: fix turn_complete=False
en _reload_session_for_section() para eliminar doble respuesta, implementación de drenado de
audio_output_queue + pausa 3.5s antes de ejecutar transferencia para evitar corte de voz,
texto "centralita" en TwiML saliente, eliminación de waitUrl (música por defecto de Twilio).
Hito 4: registro exitoso del sender WhatsApp +34607961650 (Grupo Álvarez) en Twilio — estado Online.

### Sesión 2026-04-17 — Segunda parte
**Título:** Sistema de Transferencia Resiliente: Diseño Multi-Contacto con Prioridad
**Descripción:** Sesión de diagnóstico y rediseño del sistema de transferencia de
llamada. Se diagnostican dos errores de diseño en _execute_transfer(): filtro
is_internal=True incorrecto (los contactos destino pueden ser externos) y
dependencia de section_id hardcodeado en el system_instruction (debe obtenerse
dinámicamente del bloque IDENTIFICADORES DE SECCIÓN). Se diseña y aprueba la
arquitectura resiliente multi-contacto: nuevo modelo SectionContact con campo
priority para ordenar los intentos de transferencia desde el panel, nuevo modelo
TransferAttempt para persistir el estado entre el bridge y el webhook de Twilio,
nuevo modelo PendingNotification para registrar los casos de fallo total. El flujo
completo incluye: intento con contacto prioritario → fallo → Alia ofrece siguiente
contacto al llamante con opciones (siguiente contacto / mensaje de voz / callback) →
registro de PendingNotification si todos fallan. Se acuerda que los archivos de audio
serán música clásica (Beethoven / Ravel / Tchaikovsky) en formato MP3 aportado por
Miguel Ángel. Se actualiza la hoja de ruta con los Pasos 39-41 rediseñados.
Fix documentado: el operador *(...) no es válido dentro de constructores Pydantic
(LiveConnectConfig es BaseModel) — las tools deben construirse antes del constructor
y pasarse como keyword argument tools=live_tools.

### Sesión 2026-04-17
**Título:** Estrategia B E2E: Pasos 37-38 + Rediseño Arquitectura de Transferencia Real
**Descripción:** Sesión de implementación completa de los Pasos 37 y 38 y rediseño
arquitectónico del mecanismo de transferencia de llamada. Paso 37: implementación del
motor de Estrategia B en ivr_config/services.py (section_callflow_map, bloque
IDENTIFICADORES DE SECCIÓN), vox_bridge/services.py (_reload_session_for_section,
_activate_fallback_section, general_call_flow), panel/forms.py (call_flow en
SectionForm, fallback_section en CallFlowForm) y templates/vistas correspondientes.
Fix logout Django 5.x (http_method_names en PanelLogoutView). Paso 38: investigación
confirmada de function calling en gemini-live-2.5-flash-native-audio con Vertex AI,
implementación de FunctionDeclaration route_to_section en LiveConnectConfig y handler
tool_call en _receive_gemini_audio(). Rediseño arquitectónico acordado: la notificación
saliente original se sustituye por transferencia real via Dial Conference, con música
de espera, gestión de fallback por no respuesta, ofrecimiento de mensaje de voz y
registro de PendingNotification en BD (stub WhatsApp). Se crea documento satélite
V03DOC_TRANSFER_ARCHITECTURE.md con la especificación técnica completa. Nuevos Pasos
39-42 añadidos a la hoja de ruta.

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
