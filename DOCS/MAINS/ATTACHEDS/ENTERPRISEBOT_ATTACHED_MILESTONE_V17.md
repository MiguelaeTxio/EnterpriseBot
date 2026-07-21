# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md

# Anexo de Hito V17 — Unificación IVR + WhatsApp — Motor de Averías y Log de Conversaciones
# Proyecto: EnterpriseBot
# Fecha de inicio: pendiente

---

## 1. Visión General del Hito

Este hito unifica los canales IVR y WhatsApp bajo una única lógica de
averías. Cualquier comunicación interna — llamada o mensaje — es
tratada automáticamente como avería y genera un BreakdownTicket.
Se elimina el modelo ChatRoom y toda su lógica de routing por salas.

Principios rectores:

1. **Todo contacto interno es avería.** Si el llamante o remitente
   pertenece a la empresa (Contact registrado), la llamada o el
   mensaje generan un ticket de avería. Sin excepciones.
2. **Un único número de contacto.** El número desde el que llama o
   escribe el trabajador es el único identificador. No hay distinción
   entre número IVR y número WA — es el mismo número para todo.
3. **Log de conversación en el ticket.** Tanto la transcripción de la
   llamada IVR como el hilo de mensajes WA quedan persistidos en el
   propio BreakdownTicket. No hay salas de chat separadas.
4. **Geolocalización vía WhatsApp.** Si la ubicación no coincide con
   una base conocida, el sistema envía una plantilla WA al número del
   llamante solicitando su ubicación. El ticket se completa con la
   respuesta o se marca `location_warning=True` si no hay respuesta
   en el timeout configurado.
5. **Broadcast a Taller Mecánico.** Al crear el ticket, se notifica
   por Broadcast a todos los miembros de Taller Mecánico, excluyendo
   al contacto que haya sido fuente del ticket si pertenece a esa
   sección.
6. **Onboarding en sección Usuarios.** El flujo de onboarding WA
   se mueve a la sección de Usuarios del panel. Desaparece la
   sección Salas de Chat del sidebar.

---

## 2. Arquitectura Técnica

### 2.1. Modelos afectados

**Eliminados:**
- `ChatRoom` y toda la lógica de routing por salas.
- Relaciones M2M `breakdown_contacts`, `breakdown_sections` en ChatRoom.

**Modificados:**
- `BreakdownTicket`: añadir campo `conversation_log` (JSONField) para
  persistir el hilo de mensajes WA y la transcripción IVR.

**Sin cambios:**
- `Contact`, `Section`, `BreakdownTicket` (campos existentes).
- Flujo de onboarding — solo se mueve de ubicación en el panel.

### 2.2. Lógica de validación del llamante/remitente

Regla única: si `Contact.objects.filter(phone_number=caller, company=company).exists()`
→ es avería → crear ticket. No se comprueban secciones ni salas.

### ⚠️ DIRECTRIZ CRÍTICA — ivr_breakdown_enabled NO interviene en averías

`Section.ivr_breakdown_enabled` controla ÚNICA Y EXCLUSIVAMENTE si esa sección
aparece en el `section_callflow_map` para enrutar llamantes **externos** al flujo
IVR de esa sección. No interviene en ningún otro mecanismo del sistema.

Para detectar que una llamada es una avería interna, la ÚNICA condición es:
`Contact.objects.filter(company=company, phone_number=caller_number).first()`

**QUEDA TERMINANTEMENTE PROHIBIDO** condicionar el STEP 4C (perfil Alia, greeting
personalizado, creación de ticket) a que exista `breakdown_context` o a que alguna
sección tenga `ivr_breakdown_enabled=True`. Esas flags son irrelevantes para el
flujo de averías internas.

### 2.3. Flujo IVR (Alia)

1. Llamada entrante → validar Contact por número llamante.
2. Si no es Contact registrado → informar y colgar.
3. Si es Contact registrado → Alia actúa como mecánica experta
   (vehículos ligeros a gran tonelaje: mecánica, electricidad,
   hidráulica) para diagnosticar la avería.
4. Recoger: máquina, descripción avería, ubicación en máquina,
   ubicación física (base o ruta).
5. Crear BreakdownTicket con `origin=IVR`.
6. Confirmar verbalmente el código del ticket al llamante.
7. Si ubicación no es base conocida → enviar plantilla WA al número
   del llamante solicitando ubicación GPS.
8. Persistir transcripción en `conversation_log` del ticket.

### 2.4. Flujo WhatsApp

1. Mensaje entrante → validar Contact por número remitente.
2. Si no es Contact registrado → flujo onboarding.
3. Si es Contact registrado → agente de averías puro.
4. Recoger todos los datos de la avería en conversación 1:1.
5. Crear BreakdownTicket con `origin=WHATSAPP`.
6. Persistir hilo de mensajes en `conversation_log` del ticket.
7. Broadcast a Taller Mecánico (excluyendo fuente si pertenece a esa sección).

### 2.5. Panel — cambios en sidebar

- **Eliminar:** sección "Salas de Chat".
- **Añadir:** "Log de Tickets" bajo la sección de Tickets/Averías.
- **Mover:** Onboarding a sección "Usuarios".

### 2.6. Geolocalización

- Base conocida: coordenadas resueltas desde `Base` model (budgets app).
- En ruta: plantilla WA con timeout configurable (setting `GEO_TIMEOUT_MINUTES`).
  Si no hay respuesta → `location_warning=True`.
- Respuesta WA con ubicación → actualizar `geo_lat`, `geo_lng` en ticket.

### 2.7. Prompt Alia — Técnica de Flota (ivr_config/services.py STEP 4C)

El bloque `alia_mechanic_context` en `build_live_config()` se activa cuando
el llamante es un Contact interno registrado en la empresa (única condición).
No depende de `breakdown_context` ni de `ivr_breakdown_enabled`. El prompt
define la personalidad experta con el flujo numerado 1→6 y tres reglas críticas:

- **Razonamiento técnico inmediato**: ante un fallo descrito (p.ej. "no lucen
  los intermitentes"), Alia evalúa el riesgo sin preguntar lo que ya sabe
  y orienta al conductor directamente.
- **Número WA ≠ número IVR**: cuando el conductor está en ruta, Alia dice
  exactamente: "Le vamos a enviar un mensaje de WhatsApp al número desde el
  que está llamando. Respóndalo con su ubicación." NUNCA pide que envíe
  la ubicación a este número.
- **Invocación explícita de report_breakdown**: solo tras confirmación expresa
  del conductor, inmediatamente después, una sola vez por llamada.

---

## 3. Hoja de Ruta

### Paso 1 — Eliminar ChatRoom y lógica de salas ✅ S_H17_01
### Paso 2 — Añadir conversation_log a BreakdownTicket ✅ S_H17_01
### Paso 3 — Refactorizar validación de llamante en vox_bridge ✅ S_H17_01
### Paso 4 — Prompt Alia experta en mecánica ✅ S_H17_01 + S057
### Paso 5 — Flujo geolocalización vía WhatsApp post-llamada — BLOQUEADO Meta
### Paso 6 — Agente WhatsApp de averías puro ✅ S055 + S056
### Paso 7 — Broadcast a Taller Mecánico — BLOQUEADO Meta
### Paso 8 — Refactorizar sidebar ✅ S056
### Paso 9 — Log de conversación en panel de tickets ✅ S056

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| — | — | — | Hito no iniciado. Arquitectura definida en S014 de H03/H14. |
| S_H17_01 | 2026-06-22 | 1,2,3,3b,4 | **Paso 1**: Eliminacion ChatRoom/ChatMessage/BreakdownConversationTurn. BreakdownTicket.room→company. Migracion 0007 OK. Limpieza whatsapp/views.py, panel/views.py, panel/urls.py, analytics/views.py, _nav_items.html. **Paso 2**: conversation_log JSONField en BreakdownTicket. Migracion 0008 OK. **Paso 3**: _create_breakdown() en vox_bridge/services.py simplificado: puerta de seguridad Contact.objects.filter(company,phone). **Extra 3b**: breakdown_ticket FK + ticket_closed BooleanField en WorkOrderEntryLine. Migracion 0025 OK. **Paso 4**: STEP 4C en build_live_config() — perfil Alia mecanica experta activado cuando caller es Contact interno con breakdown_context activo. Incidencias resueltas: FieldError room__company en views_operator.py; AbsenceCategory HORAS_JEFE creada. install_files management command creado. skill com-install-files creada. |
| S054 | 2026-06-24 | INCIDENCIA DNI | **INCIDENCIA PRIORITARIA — Campo DNI en CompanyUser**: (1) CompanyUserCreateForm: campo dni añadido (opcional), get_initial_password() derivada por rol — WORKSHOP/WORKSHOPBOSS: 4 ultimas cifras del DNI (fallback 1234), must_change_password=False; ADMIN/SUPERVISOR: initial_password explicito, must_change_password=True. (2) CompanyUserCreateView.post(): logica must_change_password por rol, new_cu.dni persistido. (3) CompanyUserUpdateView: dni añadido a fields, atributos Bootstrap en get_form(). (4) panel/users/form.html: campo DNI visible y editable con help text. **Desvio a H16**: ver anexo V16. **Auditoria WA**: 7 plantillas en BD identificadas (presence_reminder, welcome_message, alias_confirmation, breakdown_confirm, chat_onboarding, chat_session_renewal, ivr_capture_notification), infraestructura Content API correcta, todas con content_sid HX real. Paso 0 de H17 pendiente. |
| S055 | 2026-06-25 | Paso 0, Paso 6 + Onboarding WA | **Paso 0 — Plantillas WhatsApp**: Auditoria completa BD vs Twilio Content API v1. Corregido welcome_message→MARKETING, chat_session_renewal→UTILITY en BD. Eliminada alias_confirmation (legacy H13). 5 plantillas breakdown_* creadas en Twilio y enviadas a Meta (pending): breakdown_ticket_created HX32d590d2a40360c789060a7f88fa50ef, breakdown_location_request HXb9139eb63adb500855a679957d3de232, breakdown_info_request HXe3baa955000b20e312d6d000f775533b, breakdown_assigned HX41a742714147cc5ec92fa83dbf5c3db6, breakdown_broadcast HXa1b32520e94663a32d3c7c1453429fe3. Rechazadas por Meta (variable al final del body) y recreadas con patron "Hola {{1}}, usted recibe este mensaje...". seed_whatsapp_templates.py reescrito con inventario completo (11 plantillas). **Paso 6 — Agente WA averias + Onboarding**: Bifurcacion en IncomingWhatsAppView: Rama A (Contact interno + ticket abierto → BreakdownAgentService), Rama B (Contact interno sin ticket → Gemini decide averia/ayuda), Rama C (desconocido con onboarding activo → OnboardingService), Rama D (desconocido → chatbot generico + deteccion EMPLOYEE_ONBOARDING). BreakdownAgentService: get_or_create_ticket(), build_system_prompt() prompt Alia mecanica experta, build_history_from_log(), append_log(), parse_and_apply_ticket_data() marcador [TICKET_DATA:{...}]. OnboardingService (primera version): maquina de estados NAME→LASTNAME→DNI→SECTION con confirmacion en cada paso. Refinado a OnboardingService Gemini-driven: Gemini gestiona la conversacion completa, marcador [ONBOARDING_DATA:{...}] al confirmar todos los datos, _create_user() crea DjangoUser+CompanyUser (WORKSHOP si seccion Elevacion, DRIVER resto)+Contact+SectionContact. Username nombre.apellido1 (fallback nombre.apellido2). Contrasena: ultimos 4 digitos numericos DNI. Validado en produccion con Miguel Angel Munoz Cara y Jose Antonio Zafra. |
| S056 | 2026-06-25 | 6 ref., 8, 9, UI partes↔tickets | **Paso 8**: Auditado _nav_items.html — sin cambios necesarios (acc-chat eliminado S_H17_01, log accesible desde detalle ticket). **Paso 9**: Reescritura breakdown_ticket_detail.html — iteracion sobre ticket.conversation_log (JSONField); badge por canal (IVR/WA/Sistema); scroll 520px; contador mensajes. **Paso 6 refinamiento**: whatsapp/services.py — get_or_create_ticket: ticket nace IN_PROGRESS con assigned_to si rol WORKSHOP/WORKSHOPBOSS; build_system_prompt: instruccion reported_by para WORKSHOPBOSS/ADMIN; parse_and_apply_ticket_data: resolucion reported_by por nombre iexact→icontains. **Integracion UI partes↔tickets**: form_entry.html (selector ticket + checkbox ticket_closed por bloque), form_entry_assets.js (_buildTicketBlock), views_operator.py (parseo entrada_N_ticket_pk/ticket_closed, cierre ticket en close_order). |
| S057 | 2026-06-25 | Incidencias IVR + periodos + mapa + PDF | **Prompt Alia (ivr_config/services.py STEP 4C)**: Reescritura completa del bloque alia_mechanic_context con dos fixes criticos: (1) razonamiento experto inmediato — ante fallo de senalizacion, Alia evalua riesgo sin preguntar lo que ya sabe y orienta al conductor; (2) numero WA != numero IVR — cuando conductor en ruta, texto exacto: "Le vamos a enviar un mensaje de WhatsApp al numero desde el que esta llamando." Hash en servidor: 44a4542815c4ccf398eca621c348e282. Auditado que el PUT anterior no habia persistido — verificacion por md5sum sistematizada. **Identificacion de logs**: LOG_VOICE_ORCHESTRATOR=/var/log/alwayson-log-234987.log, LOG_CELERY_WORKER=/var/log/alwayson-log-242133.log. bridge.log movido de SWAP a logs/bridge.log permanente en voice_orchestrator.py. Session variables actualizadas con LOG_BRIDGE y tabla completa de logs. **Liquidacion de periodos (WorkPeriodCloseView + WorkPeriodLockView)**: WorkPeriodCloseView: bloquea cierre si hay partes sin revisar (reviewed=False) y force_close!=1; lista operarios afectados en el error. WorkPeriodLockView: advertencia warning si periodo individual se cierra con partes sin revisar. work_period_list.html: checkbox "Liquidar igualmente" con force_close=1 en modal de cierre global. **Modal planificador rutas (_route_multileg_fragment.html)**: panel-summary movido dentro de panel-scroll; #routePlannerPanelBody como flex container; overflow-y:scroll + max-height:480px en panel-scroll — barra de desplazamiento siempre visible. **Añadir dia en partes PDF (WorkOrderEntryAddView)**: Nueva vista en views_workorders.py (POST /panel/work-orders/<wo_pk>/entries/add/) — crea WorkOrderEntry con work_date + WorkOrderEntryLine vacia (line_number=1), devuelve _entry_group_fragment.html. URL work_order_entry_add registrada en panel/urls.py. Re-export en panel/views.py. Boton "Anyadir dia" + modal fecha + JS fetch en edit.html (solo visible para is_digital=False). Borrado automatico de WorkOrderEntry en WorkOrderLineDeleteView: si entry.lines.exists()==False tras borrar linea, entry.delete(). |

| S059 | 2026-06-26 | 5, 7, mejoras IVR/panel | **Paso 7 — Broadcast taller**: send_breakdown_broadcast() en WhatsAppChatService; filtra Contacts en secciones ivr_breakdown_enabled=True, excluye contact fuente; llamada desde BreakdownAgentService.get_or_create_ticket() y _create_breakdown() en vox_bridge. **Paso 5 — Geoloc post-IVR**: en _create_breakdown(), si not _at_base → envía breakdown_location_request al caller_number; en whatsapp/views.py Rama A: si is_location_msg y ticket abierto → persiste geo_lat/geo_lng en ticket y SYSTEM log. **intro.mp3**: recortada de 4,05s a 2,04s con ffmpeg; TwiML reemplazado por Pause length=1 sin Play. **Contact.first_name/last_name**: migración 0037 aplicada; fix is_internal=True en pk=17,18,28; diccionario de correcciones manuales aplicado a 16 internos; management command split_contact_names creado. **Prompt Alia**: fix _caller_display con first_name; activación desacoplada de breakdown_context (if caller_number); paso 6 con unmistakably según best practices Google; estructura de bloques restaurada (breakdown_context antes que alia_mechanic_context). **sort usuarios**: CompanyUserListView con sort server-side por username/fullname/role/status vía ?sort=&dir=. **Validación E2E**: flujo IVR completo con at_base=False validado en producción. |
| S011 | 2026-07-09 | Incidencia duplicado WA + tool_response IVR + pulido UX + desvío H10 | **Incidencia duplicado WhatsApp — RESUELTA**: causa raíz confirmada cruzando server.log/access.log/CSV de mensajería Twilio: `WhatsAppChatService.build_history(session)` incluía el turno entrante actual (ya persistido en Paso 4 de `IncomingWhatsAppView.post()` antes de construir el historial), duplicándolo al reenviarse explícitamente vía `chat.send_message()`. Fix centralizado en `build_history()`: excluye el último mensaje de la sesión si es `IN`. Corrige las tres ramas que comparten el método (chatbot genérico, onboarding, Rama B avería sin ticket); Rama A (`BreakdownAgentService.build_history_from_log`) auditada y confirmada correcta, sin cambios. Commit `708ae59`. **Bloqueo de llamadas IVR tras `report_breakdown` — RESUELTA**: diagnosticado con `bridge.log` en crudo (ni un solo `GEMINI-RX`/`TWILIO-TX` tras el tool_call, hasta el `stop` de Twilio ~10s después). Verificado en línea contra documentación oficial de la Live API (`ai.google.dev/gemini-api/docs/live-api/tools`) y un issue idéntico en `googleapis/python-genai`/`livekit/agents#2174`: la Live API exige `session.send_tool_response(function_responses=...)` con el campo `id` del `function_call` original — el código usaba `send_client_content(role="tool")` sin `id`, método incorrecto y no documentado. Corregidos los 5 manejadores de tool_call de `vox_bridge/services.py` (route_to_section, submit_captured_data, report_breakdown, submit_call_summary, transfer_to_section_contact). Commit `013e536`. Primera llamada de avería completada de principio a fin en producción tras el fix. **Pulido UX post-validación E2E**: `SILENCE_FRAMES_TO_END_ACTIVITY` 50→30 (~1000ms→~600ms, restaurado al valor documentado en V01 — el comentario llevaba desincronizado del valor real desde hacía tiempo); prompt de Alia reforzado con REGLA INAMOVIBLE para mencionar "WhatsApp" explícitamente al pedir ubicación (el ejemplo negativo previo no bastaba, Gemini lo decía igualmente); instrucción para inferir `fault_location` de la descripción del fallo en vez de preguntarla siempre de forma redundante. Commit `de1b157`. **Desvío a H10**: modal de aviso de ticket sin cerrar en `form_entry.html` — ver nota de desvío en `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`. Commit `2f9369f`. **Nueva REGLA ABSOLUTA en `com-standards`** (fuera del repo, skill de sistema): PDFs históricos vs. partes digitales nunca se mezclan — antipatrón ya localizado en `WorkOrderEditView`/`edit.html` (flag `_is_digital`), pendiente de separar en S012 (siguiente sesión). **Incidencia de sesión**: token de GitHub caducado a mitad de sesión (401 Bad credentials confirmado contra la API) — commit del modal quedó pendiente en local hasta recibir token nuevo, sin pérdida de trabajo. |
| S012 | 2026-07-10 | Bloque 1 completo + ampliado, Bloque 2 punto 3, sidebar | **Bloque 1 — Separación PDF vs. digital (RESUELTA, commit `a513df7`)**: 3 enlaces corregidos (`digital_list.html` ×2, `operator/history.html` ×1) que enrutaban partes digitales a `work_order_edit`. Guardia dura añadida en `WorkOrderEditView.get()`/`post()`: cualquier `WorkOrder` DIGITAL/GENERATED se bloquea y redirige a `operator_form_edit`, sin excepción de rol ni de origen del enlace. Guardia idéntica extendida a los 7 endpoints HTMX que sostienen `edit.html` (`WorkOrderLineSaveView`, `WorkOrderEntrySaveDateView`, `WorkOrderLineInsertView`, `WorkOrderEntryAddView`, `WorkOrderLineReorderView`, `WorkOrderLineRestoreView`, `WorkOrderLineDeleteView`) — ninguno comprobaba `source`, permitiendo en teoría tocar un parte digital vía POST directo sin pasar por la vista principal. Código muerto eliminado: `SupervisorAccessMixin` ya excluía WORKSHOP desde antes de esta sesión, las ramas `_is_workshop` de `WorkOrderEditView` eran inalcanzables; eliminadas junto con el bloque `workday_gaps` en `edit.html` (exclusivo de digitales, vacío una vez blindada la vista). **Ampliación no prevista en el anexo, a petición de Miguel Ángel — unificación total de 4 vistas de historial (commit `c7b4a97`)**: `WorkOrderAdminHistoryView` ("Historial") pasa a ser la ÚNICA vista de partes digitales, renombrada "Partes Digitales"; se eliminan por completo (vista + plantilla + URL + entrada de menú, sin marcar ni ignorar) `DigitalWorkOrderListView` (antigua Partes Digitales), `history.WorkOrderHistoryListView`/`WorkOrderHistoryDetailView` (Mis partes) y `WorkOrderEntryHistoryView`/`panel:operator_history` (Historial de operario) — esta última detectada por el propio Miguel Ángel como vista fantasma sin usar en meses tras una insistencia explícita en no dejar nunca vistas "marcadas como eliminadas". Mixin cambiado a `WorkOrderFormAccessMixin` para admitir también WORKSHOP, con alcance acotado a sus propios partes (`_build_base_queryset(owner=...)`), sin selector de operario ni Marcar revisado/Eliminar, guardia de rol añadida en `post()` (el mixin ampliado dejaba sus acciones de gestión alcanzables sin ella). Filtro Estado añadido (recupera la vieja pestaña Error sin pestaña dedicada); resumen de horas extra del periodo activo trasplantado desde la vieja pestaña de `operator_history` para WORKSHOP. **Limpieza DRY/plantillas tontas a petición expresa de Miguel Ángel**: color de badge Estado movido de la plantilla a la vista (`status_badge_class`); rama muerta de dispatch PDF eliminada del enlace Editar (esta vista nunca contiene PDFs); las 3 tablas casi-idénticas de Pendientes/Revisados/Histórico extraídas a un único parcial parametrizado nuevo (`_wo_table.html`); `admin_history.html` de 2018 a ~940 líneas. **Hotfix (commit `1320a60`)**: la reescritura del bloque Períodos se dejó por el camino el import `ExportTemplate as _ET`, tumbando `/panel/work-orders/history/` en producción para cualquier rol — detectado por Miguel Ángel vía traceback de Django, corregido y verificado con `pyflakes` sobre el archivo completo. **Reorganización de sidebar (commit `f010621`)**: PDFs trasladado de Taller Mecánico a Administración; subgrupo "Mecánicos" renombrado a "Taller" y ampliado con Tickets de avería (trasladado desde el subgrupo Taller, ahora eliminado); Taller Mecánico queda con 3 subgrupos: Centro de gasto, Almacén, Taller. **Bloque 2, punto 3 — Acceso WORKSHOP a tickets de avería (commit `8c6e874`)**: guardias de rol de las 3 vistas de `chat/views_tickets.py` (lista, detalle, crear) ampliados a WORKSHOP; guardia interna de "assign" (reasignar a otro operario) dejada intacta, solo ADMIN/SUPERVISOR; botón autoasignarme ampliado a WORKSHOP en el detalle; panel de despacho por arrastre ocultado para WORKSHOP en el listado (dispara una acción que no pueden ejecutar); sidebar ampliado. **Puntos 1 y 2 del Bloque 2 (responsivo móvil, color de mecánicos ocupados) y Bloque 3 (IVR) — sin empezar**, pasan a S013 (ver hoja de ruta). |
| S013 | 2026-07-13 | NOTA DE DESVÍO — sin trabajo directo en H17 | Sesión desviada por completo a H10 (Caso A, sin PCH invocado, marcador `EN PROGRESO` sin mover) para atender el Bloque B de la hoja de ruta de abajo (albaranes de proveedores) más una infraestructura de despliegue automático de plataforma pedida por Miguel Ángel a mitad de sesión, ninguna de las dos ligada a H17. Detalle técnico completo, commits y decisiones en `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`, fila S013 del Registro de Sesiones de ese anexo. Los Bloques A (fallo de confirmación de ticket IVR), C (CRUD de tickets responsivo + reversión del panel de despacho para WORKSHOP) y D (validación general IVR) de la hoja de ruta de abajo **siguen íntegramente pendientes, sin ningún avance** — la hoja de ruta de este hito no se reescribe (Caso A: "el hito no avanzó"). |
| S014 | 2026-07-13 | NOTA DE DESVÍO — sin trabajo directo en H17 | Sesión desviada por completo a H10 (Caso A, sin PCH invocado, marcador `EN PROGRESO` sin mover), a petición expresa de Miguel Ángel ("terminar con el tema de los albaranes"): cierre completo del Bloque B (fecha ES, unicidad `delivery_number`, subida async), persistencia en Google Drive (sustituye el envío por correo), más un cambio mayor de infraestructura de plataforma (nuevo flujo de migraciones — el modelo escribe el archivo directamente en vez del ciclo manual `makemigrations`; fix crítico de un bug real de `deploy.yml` que reportaba despliegues fallidos como exitosos; reinicio condicional de las Always-on Tasks en el despliegue automático) — ninguna de las dos ligada a H17. Detalle técnico completo, commits y decisiones en `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`, fila S014 del Registro de Sesiones de ese anexo, y en las skills de sistema `com-migrations` (reescrita de raíz), `nfs-enterprisebot-edit`, `com-bash-commands`, `nfs-enterprisebot-pcs`. Los Bloques A (fallo de confirmación de ticket IVR), C (CRUD de tickets responsivo + reversión del panel de despacho para WORKSHOP) y D (validación general IVR) de la hoja de ruta de abajo **siguen íntegramente pendientes, sin ningún avance** — la hoja de ruta de este hito no se reescribe (Caso A: "el hito no avanzó"). |
| S015 | 2026-07-13 | Bloque C completo, luego desvío a H10 | **Bloque C — CRUD de tickets responsivo + reversión del panel de despacho, COMPLETADO**: (1) Responsivo real en móvil de `breakdown_ticket_list.html` (mismo criterio ya validado en `analytics_lab.html`: `#tk-bottom` apila verticalmente por debajo de 767.98px, divisor arrastrable oculto, tabla superior con `overflow-x:auto`) y padding responsivo (`px-3 px-md-4`) en `breakdown_ticket_detail.html`/`breakdown_ticket_form.html` — commits `650c0d7`, `049abc6`. (2) Panel de despacho por arrastre revertido para WORKSHOP: visible (instrucción literal de Miguel Ángel al cierre de S012) pero sin poder arrastrar (`draggable=false` + clase `op-locked`, decisión explícita "opción c" frente a dejar fallar el POST con 403) — commit `eef1f1c`. (3) WORKSHOPBOSS ampliado a poder EJECUTAR `assign` (guard de backend solo permitía ADMIN/SUPERVISOR pese a tener el panel visible y arrastrable desde siempre — bug real corregido, no pedido explícitamente pero detectado leyendo el código) en las dos vías de entrada (drag&drop y tarjeta "Asignar operario" del detalle) — commits `40a36d6`, `33b36ad`. (4) A petición explícita de Miguel Ángel, WORKSHOPBOSS eliminado por completo como DESTINO asignable (nunca ejecuta órdenes de trabajo, era un remanente del diseño original del H14 sin tickets reales afectados en producción): `operators_qs`, `assignable_operators` y la validación final de `assignee_pk` restringidos a WORKSHOP — commit `6717375`. (5) Asimetría del desplegable "Asignar operario" (solo permitía WORKSHOPBOSS como destino, más restrictivo que el propio guard de backend) detectada e igualada a la regla del drag&drop — commit `7ee733c`. Punto 3 del Bloque C (color de mecánico ocupado) confirmado por Miguel Ángel como ya cubierto por el badge `op-busy`/`op-free` existente, sin cambios de código. **Desvío a H10** en la segunda mitad de la sesión, a petición de Miguel Ángel ("vamos a continuar con las albaranes"): ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`, fila S015, para el primer punto de la hoja de ruta (asignación única por albarán) más un bug real de OAuth y el backfill de 8 albaranes históricos. Los Bloques A (fallo de confirmación de ticket IVR) y D (validación general IVR) de la hoja de ruta de abajo **siguen pendientes, sin ningún avance esta sesión**. |
| S016 | 2026-07-14 | Bloque A verificado (sin repro) + bug real WhatsApp corregido, luego desvío a H7/H22 + apertura H23 | **Bloque A — verificado empíricamente, sin bug reproducido**: descargado `bridge.log` completo de una llamada de prueba real (tool_call `report_breakdown` → `BreakdownTicket` creado → plantilla WA enviada → `tool_response` enviado, los cuatro eventos en menos de 2s, audio `GEMINI-TX` continuo sin huecos en los 19s completos de la llamada). No se reprodujo el bloqueo reportado al cierre de S012. Matización honesta registrada en el propio chat: no hay cambio de código en `vox_bridge/services.py` desde S012 que explique la mejora — pudo ser intermitente. **Bug real encontrado y corregido — agente WhatsApp Rama B nunca creaba el ticket**: `whatsapp/views.py`, Rama B (contacto interno SIN ticket abierto) pedía a Gemini confirmar verbalmente la apertura del ticket pero nunca le exigía el marcador `[TICKET_DATA:{...}]` que `BreakdownAgentService.get_or_create_ticket` usa como condición real de creación (`if "[TICKET_DATA:" in reply_text`) — el agente confirmaba al trabajador que el ticket estaba abierto sin que se creara ningún `BreakdownTicket`, confirmado empíricamente con una avería real de frenos bloqueados en G12 sin ticket resultante. Corregido replicando el marcador de la Rama A. Commit `4914fe3`. **Desvío a H7** (a petición de Miguel Ángel, "vamos a por el tema de partes digitales para incluir el guardado de fotos"): modelo `TaskPhoto`, persistencia en Drive, widget de subida, galería en ticket y ficha de máquina — ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`, fila S016, para el detalle técnico completo (incluye un error real cometido y corregido en la propia sesión: `MachineHistoryView` duplicada, fusionada con la vista real de H22 — ver también `ENTERPRISEBOT_ATTACHED_MILESTONE_V22.md`, fila S016). **Apertura de H23** (Documentación de Centros de Gasto) al cierre, a petición explícita de Miguel Ángel — ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md`. Bloque D (validación general IVR) **sigue sin ningún avance**. |
| S027 | 2026-07-21 | Desvío puntual, sin avance de Bloques A/D | Sesión de H23 desviada al empezar (Caso D del enrutador, sin PCH, H17 permanece PAUSADO) para atender 2 de las 4 incidencias reportadas por Miguel Ángel sobre `WorkOrderAdminHistoryView` (unificada aquí en S012) — la otra mitad, sobre `form_entry.html`/`WorkOrderEntryFormView`, en `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`, fila `S_H07_12`. **[1]** Suma de horas del filtro en Revisados: verificada por lectura de código, ya funcionaba correctamente (`reviewed_totals` sobre `reviewed_list` ya filtrada, con fila TOTAL en `_wo_table.html`) — sin cambios. **[2]** Nuevo selector de Periodo en la barra de filtros (`admin_history.html`) que lista los `WorkPeriodGroup` existentes y autorrellena Fecha desde/hasta al elegir uno (`admin_history.js`, `initPeriodFilterShortcut`) — diseño (desplegable de periodos existentes, no auto-ajuste silencioso de fechas libres) confirmado correcto por Miguel Ángel en producción. **[3]** Preservación de `back_url` con todos los filtros activos al volver al listado desde `WorkOrderAdminHistoryView` (antes solo se preservaba `tab`) — propagado vía `_wo_table.html`. Limpieza posterior de los 12 avisos djlint preexistentes en `admin_history.html` (commit `6eb7bbb`): 9 estilos inline extraídos a 4 clases CSS nuevas dentro del `<style>` ya existente en `{% block extra_head %}`, 2 líneas en blanco sobrantes al final del archivo. Commits `372faae`/`6eb7bbb`, sin migración, ambos verificados desplegados vía API de GitHub Actions (el Action del primero falló solo en el paso de recarga por tráfico alto de PythonAnywhere, corregido por el despliegue exitoso del segundo). Sin avance de los Bloques A/D pendientes (hito sigue PAUSADO). Sesión interrumpida por caída de herramientas del modelo justo después, sin cierre formal ni registro del desvío — reanudada y documentada retroactivamente en sesión posterior (S028), confirmando con Miguel Ángel que ningún commit se perdió. |

### CIERRE DE SESIÓN S014 (2026-07-13)

Sesión larga y accidentada (fallo real de despliegue diagnosticado y
corregido en vivo, ver anexo H10) pero cerrada con los tres estados
(GitHub, workspace del modelo, servidor de producción) verificados
sincronizados con datos reales, no solo con el status de la API.
**Corrección sobre la primera declaración de cierre (commit
`008e13d`):** el propio commit de cierre reveló un SEGUNDO bug real de
`deploy.yml` (interpolación insegura de `${{
github.event.head_commit.message }}` -- rompe con mensajes de commit
multilínea, ver `nfs-enterprisebot-edit` para el detalle completo),
detectado por Miguel Ángel al ver el step "Resumen" en rojo -- el
modelo había declarado la sesión cerrada sin haber verificado ese
resultado, error señalado y corregido en el mismo tramo. Corregido en
commit `0d1b0e9`, verificado con datos reales del servidor (`git log
-1` = `0d1b0e912fdef77b32e4e4eea2e06786bcd0c98c`, coincide con GitHub)
antes de esta segunda declaración de cierre, esta vez sí verificada.
`working tree clean`. Sin cambios de hito -- H17 sigue `EN PROGRESO`,
sin avance directo esta sesión. Próxima sesión: Miguel Ángel decide
entre retomar H17 (Bloques A/C/D, ver hoja de ruta arriba) o continuar
en H10 con la nueva salvaguarda de validación de máquina por albarán
(primer punto de la hoja de ruta de H10, ver ese anexo).

---

### CIERRE DE SESIÓN S016 (2026-07-14) — PCH: H17 PAUSADO, H23 EN PROGRESO

Sesión con avance real sobre H17 pese a no tocar directamente los
Bloques A/D de la hoja de ruta: Bloque A verificado empíricamente sin
bug reproducido (sin cambio de código, ver fila S016), y un bug real
del canal WhatsApp corregido y desplegado (`4914fe3`). Desviada
después a H7 (fotos de tarea, ver ese anexo) y a H23, hito nuevo
abierto al cierre a petición explícita de Miguel Ángel para la
funcionalidad de documentación de centros de gasto.

**H17 pasa a PAUSADO** (marcador movido en `ENTERPRISEBOT_ANNEX_ROUTER.md`
a H23) — decisión explícita de Miguel Ángel al cierre, no un desvío de
sesión. Bloques A (sin bug reproducido, pero sin cambio de código que
lo explique — vigilar) y D (validación general IVR) quedan pendientes,
sin ningún avance de código esta sesión, para cuando se retome.

---

## 5. Hoja de Ruta para la Siguiente Sesion

**HITO PAUSADO — sin sesión asignada.** Retomar cuando Miguel Ángel lo
decida (Caso D del enrutador de anexos). Al retomar:

#### CIERRE DE S015 (2026-07-13)

Bloque C completo (ver fila S015 en el Registro de Sesiones, sección
4, para el detalle técnico completo de los 6 commits). Quedan
íntegramente pendientes, sin ningún avance desde S012: Bloque A (fallo
de confirmación de ticket IVR) y Bloque D (validación general IVR).

#### CIERRE DE S016 (2026-07-14)

Bloque A verificado sin bug reproducido en una llamada de prueba real
(ver fila S016) — sin cambio de código en `vox_bridge/services.py`, así
que no se puede dar por cerrado con certeza; si el fallo reaparece,
retomar el mismo método empírico (bridge.log crudo de una llamada real
que lo reproduzca). Bloque D sigue sin ningún avance.

#### S027 (2026-07-21) — desvío puntual, sin relación con Bloques A/D

Desvío desde H23 al selector de periodo, verificación de suma de horas
y preservación de filtros en `WorkOrderAdminHistoryView`, más limpieza
de djlint — ver fila `S027` en el Registro de Sesiones (sección 4)
para el detalle completo. Sin impacto en los Bloques A/D pendientes ni
en el resto de esta hoja de ruta.

#### PRÓXIMA SESIÓN DE H17 (cuando se retome)

**Miguel Ángel decide el orden real al empezar la sesión** entre los
dos bloques siguientes.

---

**Bloque A — IVR: fallo en la confirmación del ticket (incidencia
reportada al cierre de S012, sin ningún avance en S013/S014/S015).**

Las pausas entre respuestas de Alia ya funcionan bien — confirmado
explícitamente por Miguel Ángel. El fallo está localizado con
precisión: justo cuando Alia pregunta algo del tipo "¿es correcto el
ticket/la información?" y el conductor responde "sí", la llamada se
queda esperando mucho tiempo sin respuesta. Miguel Ángel cree que
coincide con el momento en que se genera/guarda el ticket. Empezar
por `bridge.log` en crudo de una llamada de prueba reciente que
reproduzca el fallo (mismo método que resolvió el bloqueo de S011:
buscar el hueco entre el último `GEMINI-RX`/`TWILIO-TX` tras la
confirmación y el siguiente evento) antes de tocar código — no asumir
la causa. Sospechoso más probable a verificar, no a dar por bueno:
alguna llamada bloqueante o lenta (creación de `BreakdownTicket`,
notificación WhatsApp del ticket, broadcast a sección) ejecutada
síncronamente dentro del manejador del tool_call que confirma el
ticket, en `vox_bridge/services.py`.

---

**Bloque D — IVR: validación general continuada (Bloque 3 original de
S012, sin empezar).** Más allá del fallo puntual del Bloque A,
continuar validando y puliendo el flujo de voz con nuevas llamadas de
prueba, y decidir con Miguel Ángel si hay más ajustes de UX pendientes
tras usarlo unos días en producción.

---

Todos los pasos de la Hoja de Ruta original (sección 3) y el Bloque C
completo en S015 siguen ejecutados y validados en producción -- no
reabrir ninguno sin instrucción explícita.

Incidencias menores registradas para futura atención (sin prioridad
sobre los bloques de arriba, no iniciar sin instrucción explícita):

**CORREGIDA EN S023 (no pendiente, registrada aquí solo como
histórico):** `CELERY_BEAT_SCHEDULE` (`enterprise_core/settings.py`)
seguía disparando a diario (3:00) `chat.tasks.purge_old_chat_messages`
— función eliminada por completo en este mismo Paso 1 de H17 junto con
`ChatRoom`/`ChatMessage`/`BreakdownConversationTurn` (`chat/tasks.py`
quedó como placeholder vacío desde entonces). La tarea llevaba
disparándose en el vacío desde ese momento sin fallar de forma
visible — Celery simplemente no encontraba nada que ejecutar cada día.
Detectado por Miguel Ángel durante una sesión de H23/H26, verificado
contra el código real (no contra el anexo) antes de corregir. Entrada
eliminada de `CELERY_BEAT_SCHEDULE`; el hueco horario (3:00) se
reutilizó para la tarea de alertas de vencimiento de documentos de
H26 (`send_document_expiry_alerts`) — ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md` y
`ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md` sección "COMPLETADAS EN
S023" para el detalle completo.

- **views_workorders.py — bug preexistente detectado por pyflakes en
  S012 (sin relación con los cambios de esa sesión)**: en
  `WorkOrderAdminExportView`, modo `export_mode="digital_full"`
  (línea ~4887), `pk_list` y `operator_filter` se usan antes de estar
  definidos. `NameError` en cuanto se ejercite esa ruta concreta.
- **views_workorders.py línea 1747** (referencia previa a S012,
  puede haber desplazado de línea): IntegrityError duplicate entry
  en /panel/work-orders/92/lines/insert/ — bug preexistente sin resolver.
- **SWAP en .gitignore del repo sistema** — pendiente fix.
- **Formulario Contact en panel**: first_name, last_name y alias
  editables desde el panel — pendiente implementar (desvío H17 o H10).
- **Prompt Alia — directorio de conductores con alias**: inyectar lista
  de Contacts internos con first_name + alias en el system_instruction
  para resolución de motes en tickets — pendiente cuando haya alias en BD.
- **`whatsapp/services.py` — Internal Server Error MySQL en
  `OnboardingService._create_user()`** (detectado en S010, ver server.log
  09:02:20 del 2026-07-09): fallo crudo de ejecución MySQL fuera del
  único `try/except` de la función, probablemente conexión huérfana
  tras reinicio de workers uWSGI. `_create_user()` carece de
  `transaction.atomic()`. No confundir con la incidencia de duplicado
  de S011 — son dos bugs distintos, el de MySQL sigue sin resolver.
- **Crash recurrente "MuPDF C++ internal assert failure"** que
  reinicia los 3 workers uWSGI cada 10-40 min (detectado en S010) —
  inestabilidad de producción ajena a WhatsApp/IVR, sin diagnosticar
  todavía la causa (probable pipeline PyMuPDF/fitz de H06/H08).
- **`settings.py` sin `LOGGING` explícito** — los `logger.info()` de
  la app (`[WHATSAPP]`/`[ONBOARDING]`) nunca llegan a `server.log`
  (detectado en S010).
- **`digital_list.html` (eliminado en S012) tenía un desbalance
  if/for aparente detectado por un verificador propio** — investigado
  en S012 y confirmado como falso positivo (el verificador contaba
  palabras dentro de un comentario Django `{# ... #}`, no código real).
  Sin acción pendiente — nota dejada solo por si reaparece un
  verificador similar en otro archivo.
