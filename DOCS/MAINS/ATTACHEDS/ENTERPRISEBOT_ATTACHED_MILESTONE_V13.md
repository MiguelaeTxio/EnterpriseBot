# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md

# ENTERPRISEBOT — ANEXO HITO 13
## Salas de Chat IRC por Sección (WhatsApp -> Panel) — REDISENO ESTRATEGICO S041

---

## 1. Contexto del Rediseno

El planteamiento original del Hito 13 quedó completado en S009 (2026-05-21).
En S039 se acordó un cambio estratégico completo. En S040 se diseñó la
infraestructura base del sistema de gestión del bot. En S041 se investigó
la Groups API de Meta, se detectaron premisas incorrectas de S039/S040 y
se rediseñó completamente la arquitectura con el enfoque híbrido definitivo.

---

## 2. Arquitectura Definitiva (S041)

### 2.1. Canal WhatsApp — Decisión Definitiva

Twilio se mantiene como único proveedor para mensajería WhatsApp y voz/IVR.
La migración a Meta Cloud API directa queda descartada.
Los Pasos 17e y 17f quedan eliminados de la hoja de ruta.
La Groups API de Meta requiere OBA (tick verde) — actualmente en tramitación.

### 2.2. Grupos Virtuales y Flujo de Mensajes

Sala BREAKDOWNS (choferes / personal sin sección de taller):
- Mensajes 1:1 estrictos — ningún otro chofer los recibe.
- Visor del panel: historial agregado sin reenvío a nadie.
- Tarjeta de ticket: despachada 1:1 a miembros del ChatRoom de taller destino.

Salas SECTION (secciones de taller):
- Todos los mensajes de integrantes se replican 1:1 a todos los miembros vía Celery.
- Tarjetas de avería entrantes también se despachan 1:1 a todos los miembros.
- Visor del panel refleja todo el tráfico.

Circulares:
- Alcance definido por el remitente: toda la empresa, sección concreta o combinación.
- Todos los usuarios de Grupo Álvarez son destinatarios potenciales.

### 2.3. Flujo de Avería — Bot 1:1 con Chofer

Estados en Contact.routing_state:

ROUTING_STATE_NONE
  cualquier mensaje entrante
  -> Quick Reply breakdown_confirm (SID: HX71d736523adabbd1e6d0fdf8acc2e99c)
  -> persiste en BREAKDOWNS sin broadcast

ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM
  opt_in / afirmativo -> ROUTING_STATE_BREAKDOWN_IN_PROGRESS
                      -> persiste mensaje en BREAKDOWNS
                      -> invoca process_breakdown_turn()
  opt_out / negativo  -> ROUTING_STATE_NONE
                      -> informa canal exclusivo de averias
  no reconocido       -> reenvía Quick Reply

ROUTING_STATE_BREAKDOWN_IN_PROGRESS
  todos los mensajes -> process_breakdown_turn() directo
                     -> persisten en BREAKDOWNS sin broadcast
  al detectar TICKET_COMPLETE:
    -> guarda BreakdownTicket en BD
    -> resetea ROUTING_STATE_NONE
    -> llama _dispatch_breakdown_card()

### 2.4. Despacho de Tarjeta (_dispatch_breakdown_card)

Resolución ChatRoom destino:
1. MachineAsset.family -> WorkshopFamilyMapping -> workshop_family
2. ChatRoom SECTION cuya sección tiene CompanyUser con ese workshop_family
3. Fallback: todas las salas SECTION activas

Envío: 1:1 a cada CompanyUser activo del ChatRoom destino con phone_number.
Registro: ChatMessage(OUTBOUND) en sala de taller para historial del panel.

Formato de tarjeta:
  Averia #N
  Maquina: {machine_raw}
  Problema: {fault_summary}
  Ubicacion: {location}
  Urgencia: {display}
  Reportado por: {alias}

### 2.5. Template breakdown_confirm

SID: HX71d736523adabbd1e6d0fdf8acc2e99c
Nombre en BD: breakdown_confirm (WhatsAppTemplate pk=7)
Body: "Este canal es exclusivo para averias. El mensaje que acabas de enviar, es una averia?"
Botones: [opt_in: "Si, es una averia"] [opt_out: "No, es otro asunto"]
Actualizado en Twilio y BD en S041.

---

## 3. Estado de Pasos — Implementación Original (S009)

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Modelo ChatRoom y ChatMessage | COMPLETADO |
| 2 | Migración inicial chat | COMPLETADO |
| 3 | Creación automática de salas por sección | COMPLETADO |
| 4 | Vista ChatRoomListView | COMPLETADO |
| 5 | Vista ChatRoomView | COMPLETADO |
| 6 | Vista ChatSendView | COMPLETADO |
| 7 | Template chat_room_list.html | COMPLETADO |
| 8 | Template chat_room.html | COMPLETADO |
| 9 | URLs chat | COMPLETADO |
| 10 | Entrada sidebar Chat de Secciones | COMPLETADO |
| 11 | Sala BREAKDOWNS — modelo y migración | COMPLETADO |
| 12 | BreakdownTicket — modelo y migración | COMPLETADO |
| 13 | BreakdownRoomManageView + template | COMPLETADO |
| 14 | BreakdownTicketListView + template | COMPLETADO |
| 15 | BreakdownTicketDetailView + template | COMPLETADO |
| 16 | Rol WORKSHOPBOSS — implementación completa | COMPLETADO |

---

## 4. Pasos Nuevos — Rediseno S040+

| Paso | Descripción | Estado |
|------|-------------|--------|
| 17a | CompanyUser.workshop_family + WorkshopFamilyMapping + migración 0027 | COMPLETADO S040 |
| 17b | WorkshopFamilyMappingAdmin en ivr_config/admin.py | COMPLETADO S040 |
| 17c | BotManagementView en panel/views.py + urls.py + sidebar | COMPLETADO S040 |
| 17d | Template panel/bot/dashboard.html | COMPLETADO S040 |
| 17e | Migración WhatsApp Twilio -> Meta Cloud API | CANCELADO |
| 17f | Configuración grupos de taller vía Groups API de Meta | CANCELADO |
| 18 | Flujo confirmación avería + agente Gemini en chat/services.py | COMPLETADO S041 |
| 19 | Generación automática de BreakdownTicket desde conversación bot | COMPLETADO S041 |
| 20 | Despacho tarjeta 1:1 a miembros de sala de taller | COMPLETADO S041 |
| 21 | Correcciones BotManagementView POST + dashboard.html + E2E | PENDIENTE |

---

## 5. Modelos Relevantes — Estado S041

### Contact (ivr_config/models.py) — MODIFICADO S041
Migración 0028 aplicada. Nuevos estados routing_state:
  ROUTING_STATE_NONE = "NONE"
  ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM = "AWAITING_BREAKDOWN_CONFIRM"
  ROUTING_STATE_BREAKDOWN_IN_PROGRESS = "BREAKDOWN_IN_PROGRESS"
max_length del campo routing_state ampliado a 30.

### ChatRoom (chat/models.py) — SIN CAMBIOS
ROOM_TYPE_SECTION: salas de taller — broadcast completo.
ROOM_TYPE_BREAKDOWNS: sala de averías — historial individual sin broadcast.

### BreakdownTicket (chat/models.py) — SIN CAMBIOS
Campos relevantes: room, contact, machine, machine_raw, fault_summary,
location, urgency, status, assigned_to, ticket_number.
Filtrar siempre por room__company.

### WorkshopFamilyMapping (ivr_config/models.py) — SIN CAMBIOS
Mapea MachineAsset.family -> workshop_family (MECHANICAL/ELEVATION).

---

## 6. Funciones chat/services.py — Estado S041

Funciones eliminadas:
  _handle_breakdown_routing() — obsoleta
  _resolve_pending_routing() — obsoleta

Funciones nuevas:
  _handle_breakdown_confirm(contact, body, from_number, to_number)
    Envía Quick Reply breakdown_confirm. Guarda AWAITING_BREAKDOWN_CONFIRM.
  _resolve_breakdown_confirm(contact, body, breakdown_room, from_number, to_number)
    Procesa respuesta Si/No. Activa agente Gemini o informa canal exclusivo.
  _persist_inbound_only(room, contact, body)
    Persiste ChatMessage(INBOUND) en sala BREAKDOWNS sin broadcast.
  _dispatch_breakdown_card(ticket, contact, to_number)
    Resuelve sala de taller destino y envía tarjeta 1:1 a todos sus miembros.

dispatch_inbound_message — Nueva Regla 5:
  Regla 5a: sala SECTION -> _persist_and_broadcast()
  Regla 5b: sala BREAKDOWNS ->
    BREAKDOWN_IN_PROGRESS        -> process_breakdown_turn() directo
    AWAITING_BREAKDOWN_CONFIRM   -> _resolve_breakdown_confirm()
    NONE u otro                  -> _handle_breakdown_confirm()

---

## 7. BotManagementView — Pendiente S042

Solo get() operativo. POST pendiente para onboarding y circulares.
Errores de campos en dashboard.html identificados en S041:
  ticket.machine_asset -> ticket.machine (con fallback ticket.machine_raw)
  ticket.description   -> ticket.fault_summary
  ticket.reported_by_contact -> ticket.contact

---

## 8. Hoja de Ruta para la Siguiente Sesión (S042)

### PRIORIDAD 1 — Correcciones dashboard.html

Corregir los tres campos erróneos en panel/bot/dashboard.html:
  a. ticket.machine_asset -> ticket.machine.code si ticket.machine else ticket.machine_raw
  b. ticket.description -> ticket.fault_summary
  c. ticket.reported_by_contact -> ticket.contact, mostrar
     ticket.contact.company_user.alias|default:ticket.contact.name

Actualizar textos de Bloques 2 y 3 que mencionan Meta Cloud API:
  Bloque 2 "Circular a grupos de taller": redisenar como circular 1:1
    por sección de taller via Twilio. Selector de ChatRoom SECTION activos.
    Eliminar referencias a Meta Cloud API y grupos WhatsApp.
  Bloque 3 "Circular 1:1": actualizar descripción a Twilio.

### PRIORIDAD 2 — POST de BotManagementView

Implementar post() en BotManagementView discriminado por campo oculto action:

  action="onboarding":
    Obtener Section por section_id (validar company).
    Obtener Contact de esa Section sin onboarding completado:
      alias_onboarding_step != ALIAS_STEP_NONE o company_user sin alias.
    Enviar template chat_onboarding (SID: HX9c92dd8981366dda0764900958b7abbc)
      variables: {"1": contact.name, "2": company.name}
    via WhatsAppChatService.send_quick_reply() desde número del bot.
    Redirigir con mensaje de éxito indicando cuántos contactos recibieron onboarding.

  action="group_broadcast":
    Obtener secciones de taller seleccionadas por workshop_family.
    Resolver ChatRoom SECTION via WorkshopFamilyMapping.
    Para cada CompanyUser activo de esas salas obtener Contact y enviar
      mensaje libre via WhatsAppChatService.send_reply().
    Persistir ChatMessage(OUTBOUND) en cada sala afectada.
    Redirigir con mensaje de éxito.

  action="direct_broadcast":
    Obtener Contact activos de la company (filtrando por section_id si aplica).
    Enviar mensaje libre 1:1 a cada uno via WhatsAppChatService.send_reply().
    Redirigir con mensaje de éxito.

  Añadir en cada formulario del template:
    <input type="hidden" name="action" value="onboarding|group_broadcast|direct_broadcast">

### PRIORIDAD 3 — Validación E2E

  1. Chofer envía mensaje 1:1 al bot.
  2. Bot responde con Quick Reply breakdown_confirm.
  3. Chofer pulsa "Si, es una averia".
  4. Agente Gemini recoge datos campo a campo.
  5. Al completar: BreakdownTicket en BD, routing_state=NONE.
  6. Tarjeta enviada 1:1 a todos los miembros del ChatRoom de taller destino.
  7. Historial visible en visor sala BREAKDOWNS del panel.
  8. Ticket visible en BotManagementView visor de averías.
