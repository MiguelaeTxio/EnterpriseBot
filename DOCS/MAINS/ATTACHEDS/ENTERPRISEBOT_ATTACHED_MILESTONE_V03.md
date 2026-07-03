# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md

# Anexo de Hito V03 — IVR Conversacional Configurable desde Producción
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-04-07
# Última actualización: 2026-04-20

---

## 1. Visión General del Hito

Transformación de EnterpriseBot de un IVR de demostración hardcodeado a un
producto multiempresa completamente configurable desde producción. Cada empresa
cliente gestiona de forma autónoma su flujo de llamadas, usuarios, secciones,
contactos y presencia desde el panel `/panel/`. Empresa piloto: Grupo Álvarez.

---

## 2. Arquitectura de Datos

### 2.1. Modelos en `ivr_config/models.py`

**Entidades base:**
- `Company` — Empresa cliente raíz del sistema multiempresa.
- `CompanyUser` — Usuario con rol ADMIN u OPERATOR. Campo `must_change_password`
  (migración 0004) fuerza cambio de contraseña en primer acceso.
- `Contact` — Persona contactable (interna o externa). Campos `email` y `gender`.
- `Section` — Sección de enrutamiento IVR. Campo `is_24h` y FK `call_flow`.
- `PhoneNumber` — Número Twilio asignado a la empresa.
- `CallFlow` — Flujo IVR con `system_instruction`, `initial_greeting`,
  `notification_contact`, `fallback_section` y campos `backup_*`.
- `PresenceStatus` — Estado de presencia del usuario.
- `CorporateVoiceProfile` — Perfil de voz: `voice_name`, `tone_guidelines`,
  `sample_responses`, `forbidden_phrases` y campos `backup_*`.
- `DataCaptureSet` — Conjunto de toma de datos por sección.
- `SectionSchedule` — Horario por día de la semana para cada sección.
- `BlockedCaller` — Números bloqueados por empresa con duración configurable.

**Modelos de transferencia (migración 0008):**
- `SectionContact` — Tabla intermedia M2M Section↔Contact con campo `priority`.
  Reemplaza la relación M2M implícita anterior.
- `TransferAttempt` — Persiste el estado de transferencia entre bridge y webhook.
  Campos: `call_sid`, `section`, `twilio_number`, `caller_number`,
  `contact_index`, `status` (PENDING/FAILED/COMPLETED).
- `PendingNotification` — Registra llamadas donde todos los contactos fallaron.
  Stub activo hasta Hito 4 (Celery+WhatsApp).

### 2.2. Migraciones aplicadas en producción

| Migración | Contenido |
|---|---|
| 0001 | Initial — 9 modelos base |
| 0002 | — |
| 0003 | SectionSchedule, BlockedCaller, campos email/gender/is_24h/notification_contact |
| 0004 | CompanyUser.must_change_password |
| 0005 | CorporateVoiceProfile.voice_name |
| 0006 | Campos backup_* en CallFlow y CorporateVoiceProfile |
| 0007 | Section.call_flow, CallFlow.fallback_section |
| 0008 | SectionContact (priority), TransferAttempt, PendingNotification (SeparateDatabaseAndState) |

---

## 3. Arquitectura del Panel `/panel/`

### 3.1. Autenticación

- `CompanyUser` se autentica via Django `auth.User`. Middleware bloquea `/admin/`
  a usuarios sin `is_staff=True`.
- Panel personalizado en `/panel/` — URL estable de producción:
  `https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/`
- El túnel ngrok es exclusivo para el webhook de Twilio, nunca para el panel.
- `CompanyUserRequiredMixin`: redirige a `/panel/password/change/` mientras
  `must_change_password=True`.

### 3.2. Módulos del panel

CompanyUser, Section (con SectionSchedule inline y SectionContact por prioridad),
Contact, PhoneNumber (solo lectura), CallFlow (con restauración backup_*),
CorporateVoiceProfile (con selector de voz y restauración backup_*),
PresenceStatus, BlockedCaller, PendingNotification (solo lectura).

### 3.3. Responsive

Panel completamente responsive desde sesión 2026-04-15: sidebar offcanvas
en móvil/tablet, tablas con `table-responsive`, padding adaptativo, formset táctil.

### 3.4. Lecciones aprendidas

- Accessor ORM desde `auth.User` → `CompanyUser`: `user.company_user`
  (related_name="company_user", NO `user.companyuser`).
- `redirect_authenticated_user=True` en `LoginView` provoca bucle infinito.
  Solución: sobrescribir `dispatch()` en `PanelLoginView`.
- Hash SRI Bootstrap JS en jsDelivr varía por edge node — eliminar `integrity`.
- Instrucciones condicionales con negaciones en `system_instruction` pueden causar
  silencio de Gemini en telefonía — usar instrucciones afirmativas cortas.
- `*()` no válido dentro de constructores Pydantic (`LiveConnectConfig` es
  `BaseModel`) — construir tools antes del constructor y pasar como `tools=`.

---

## 4. Pipeline de Voz — Estrategia B

### 4.1. `build_live_config()` en `ivr_config/services.py`

Firma: `build_live_config(twilio_number, caller_number='')` → tupla de 5 elementos:
`(system_instruction, initial_greeting, voice_name, section_callflow_map, general_call_flow)`

Flujo interno:
- Step 0: `_is_caller_blocked()` — retorna config de rechazo si bloqueado.
- `_build_section_schedule_context()` — evalúa `is_24h` y `SectionSchedule`
  por weekday y hora local para cada sección activa. Retorna
  `(schedule_context, section_callflow_map)`.
- Inyecta bloque `IDENTIFICADORES DE SECCIÓN` (tabla pk → nombre) en
  `system_instruction` para que Gemini use IDs correctos en function calling.
- `connection.close()` al inicio: fuerza reconexión MySQL fresca en always-on task.

### 4.2. `VoiceOrchestrationService` en `vox_bridge/services.py`

- `__init__`: acepta `twilio_number` y `caller_number`. Almacena
  `self.section_callflow_map` y `self.general_call_flow`.
- Function declarations: `route_to_section(section_id)` y
  `transfer_to_section_contact(section_id)`.
- `_reload_session_for_section()`: reinyecta `system_instruction` del CallFlow
  de sección en la sesión Gemini Live activa.
- `_activate_fallback_section()`: activa la sección fallback del CallFlow general.
- `_execute_transfer()`: flujo resiliente multi-contacto ordenado por `SectionContact.priority`.

### 4.3. Sistema de transferencia resiliente

Ver especificación técnica completa en `V03DOC_TRANSFER_ARCHITECTURE.md`.

Flujo resumido:
1. Alia invoca `transfer_to_section_contact(section_id)` via function calling.
2. Bridge actualiza llamada con TwiML `<Dial><Conference>` (música `hold.mp3`).
3. Bridge llama al contacto prioritario. Crea `TransferAttempt` en BD.
4. Si el contacto responde → `ContactStatusView` actualiza `status=COMPLETED`.
5. Si no responde → `TransferStatusView` incrementa `contact_index`, reconecta Alia.
6. Alia ofrece siguiente contacto / mensaje de voz / callback.
7. Si todos fallan → `PendingNotification` en BD (stub WhatsApp hasta H4).

**Fix DT-1:** `<Dial><Conference>` siempre envía `DialCallStatus=answered` al
action URL — el status real solo se obtiene via `status_callback` de la llamada
saliente al contacto (`ContactStatusView`).

### 4.4. Archivos del pipeline

| Archivo | Rol |
|---|---|
| `ivr_config/services.py` | `build_live_config()` |
| `vox_bridge/services.py` | `VoiceOrchestrationService` completo |
| `voice_sidecar_bridge.py` | Bridge aiohttp — captura To/From, gestión Media Stream |
| `voice_orchestrator.py` | Arranque ngrok + actualización webhook regional |
| `vox_bridge/views.py` | `HoldMusicView`, `TransferStatusView`, `ContactStatusView`, `TransferAcceptView` |
| `vox_bridge/static/vox_bridge/audio/` | `intro.mp3` (3-5s), `hold.mp3` (>30s) |

### 4.5. Credenciales regionales Twilio en `.env`

```
TWILIO_ACCOUNT_SID          — universal
TWILIO_API_KEY_SID          — API Key US1
TWILIO_API_KEY_SECRET       — Secret US1
TWILIO_API_KEY_SID_IE1      — API Key IE1
TWILIO_API_KEY_SECRET_IE1   — Secret IE1
TWILIO_AUTH_TOKEN_IE1       — Auth Token IE1
```

---

## 5. Comandos de Gestión

```bash
python -m dotenv run python manage.py update_twilio_webhook
python -m dotenv run python manage.py trigger_outbound_call [--to +34XXXXXXXXX]
python -m dotenv run python manage.py seed_grupo_alvarez [--phone-numbers +34XXXXXXXXX]
```

---

## 6. Pendientes Diferidos

1. `DataCaptureSet` por sección (pendiente organigrama Grupo Álvarez).
2. Recepción de ubicación GPS (diferido a H4).
3. Sistema de recordatorios de presencia vía WhatsApp (diferido a H4).
4. Email vía SendGrid (diferido a H4, pendiente dominio `enterprisebot.com`).
5. Calibración VAD adicional (ajuste fino pendiente).
6. Notificación WhatsApp `PendingNotification`: Celery activo cuando H4 esté operativo.
7. Paso 33-A (MailerSend): bloqueado hasta dominio verificado.
8. Paso 33-C (`notify_section_contact`): diferido a H4.

---

## 7. Registro de Sesiones

| Sesión | Fecha | Resumen |
|---|---|---|
| S001 | 2026-04-07 | Diseño arquitectura multiempresa. 9 modelos. Migración 0001. Seed Grupo Álvarez. Constelación documental V03. |
| S002 | 2026-04-08 | `build_live_config()`. Refactor `VoiceOrchestrationService` + bridge. Comandos Django. |
| S003 | 2026-04-09 | App `panel` completa: 11 vistas, 14 templates Bootstrap 5.3. Validación E2E todos los módulos. |
| S004 | 2026-04-10 | Saneamiento BD. Always-on task activada. Validación E2E llamada real. |
| S005 | 2026-04-11 | Routing regional IE1 vía Routes API. Fix SynchronousOnlyOperation. Captura To desde POST. Calibración VAD. |
| S006 | 2026-04-12 | Fix InterfaceError MySQL stale (`connection.close()`). Validación E2E carga dinámica BD. Pausa → H4. |
| S007 | 2026-04-13 | Reanudación. Diseño flujo IVR completo. Pasos 31+32: SectionSchedule, BlockedCaller, extensiones modelo. Migración 0003. |
| S008 | 2026-04-15 | Responsive completo panel. Gestión contraseñas CompanyUser (Paso 33-B). Migración 0004. |
| S009 | 2026-04-16 | Pasos 33-D/E/33/34/35. Selector voz. Restauración backup_*. Migraciones 0005-0007. Estrategia B: Section.call_flow + CallFlow.fallback_section. |
| S010 | 2026-04-17 | Estrategia B implementada (Paso 37). Function calling route_to_section (Paso 38). Rediseño transferencia resiliente. |
| S011 | 2026-04-18 | Transferencia resiliente (Paso 39): SectionContact, TransferAttempt, PendingNotification. Migración 0008. hold.mp3 + intro.mp3 (Paso 40). Fix cliente Twilio IE1. |
| S012 | 2026-04-20 | Validación E2E transferencia completa (Paso 41). DT-1 resuelta (ContactStatusView). DT-2 resuelta (forbidden_phrases). DT-3 diferida. |
| S013 | 2026-06-19 | Diagnóstico latencia Gemini Live (TTFT=0.953s, cuello de botella VAD 1s). Rediseño IVR con flags ivr_transfer_enabled/ivr_breakdown_enabled en Section (migración 0034). Nuevo modelo InboundCallLog (migración 0035). Function calls report_breakdown + submit_call_summary en vox_bridge/services.py. Vistas InboundCallLog en panel. Fix importación circular views.py. Plataforma estable al cierre. Prueba E2E pendiente para S014. |
| S014 | 2026-06-20 | Diagnóstico fallos E2E pruebas previas: TypeError fault_location (campo inexistente), ValueError reported_by (string en lugar de Contact). Paso 23 H14: migración chat/0006 (fault_location, geo_lat, geo_lng, location_warning en BreakdownTicket). Refactorización _create_breakdown(): puerta de seguridad (solo Contacts registrados crean tickets), resolución room+contact+reported_by desde llamante, añadido location=_base_name. Tres tickets IVR creados correctamente en BD (origin=IVR, contact, reported_by, machine resueltos). Rediseño arquitectónico completo: se abandona lógica de salas/secciones para averías — todo contacto interno es avería. H14 absorbido por nuevo H17. Hito pausado. |

---

## 8. Hoja de Ruta para la Siguiente Sesion

### Contexto — H03 PAUSADO

H03 queda pausado tras S014. La arquitectura de averías IVR ha sido
rediseñada completamente y se continúa en H17 (Unificación IVR+WA).

Pendientes menores de H03 que se resolverán al reactivar este hito
o dentro de H17 según corresponda:

1. **Prompt Alia experta en mecánica** — cuando el llamante es un
   Contact interno, Alia adopta perfil de mecánica experta
   (vehículos ligeros a gran tonelaje: mecánica, electricidad,
   hidráulica). Implementar en `build_live_config()`.

2. **Simplificar puerta de seguridad en `_create_breakdown()`** —
   la validación actual comprueba `breakdown_contacts` y
   `breakdown_sections`. Simplificar a: cualquier Contact de la
   empresa puede crear ticket. Sin comprobación de salas.

3. **`section` en ticket desde `_contact.sections.first()`** —
   actualmente `section=None`. Resolver la sección del ticket
   directamente desde la sección del Contact llamante.

4. **Reducción VAD** — `SILENCE_FRAMES_TO_END_ACTIVITY` de 50→25
   frames para reducir ~500ms de latencia percibida.

5. **CRUD secciones** — verificar checkboxes `ivr_transfer_enabled`
   e `ivr_breakdown_enabled` en formulario de edición de sección.

6. **Flag `ivr_breakdown_enabled`** — evaluar si sigue siendo
   necesario o queda obsoleto tras la nueva arquitectura de H17.
