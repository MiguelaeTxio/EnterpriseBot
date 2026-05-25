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

## 7. BotManagementView — Estado S042

post() implementado en S042. Los tres handlers están operativos:
  action=onboarding: lanza chat_onboarding a contactos sin alias completado.
  action=group_broadcast: circular 1:1 a salas SECTION de taller via Twilio.
  action=direct_broadcast: circular 1:1 a contactos activos de la empresa.
Número del bot resuelto desde PhoneNumber activo con capabilities WHATSAPP/BOTH.
Campos corregidos en dashboard.html:
  ticket.machine / ticket.machine_raw, ticket.fault_summary, ticket.contact.
Referencias a Meta Cloud API eliminadas de Bloques 2 y 3.
Acceso por rol en ChatRoomListView y ChatRoomView actualizado:
  WORKSHOPBOSS ve SECTION + BREAKDOWNS.
  WORKSHOP y DRIVER ven solo su sala SECTION.
  Sala BREAKDOWNS es can_send=False para todos los roles del panel.

---

## 8. Hoja de Ruta para la Siguiente Sesión (S043)

### PRIORIDAD Única — Validación E2E en producción y cierre del Paso 21

Ejecutar la validación E2E completa del flujo de avería con los compañeros
en el entorno de producción. Secuencia a verificar:

  1. Chofer envía mensaje 1:1 al bot.
  2. Bot responde con Quick Reply breakdown_confirm
     (SID: HX71d736523adabbd1e6d0fdf8acc2e99c).
  3. Chofer pulsa 'Si, es una averia'.
  4. Agente Gemini recoge datos campo a campo hasta TICKET_COMPLETE.
  5. BreakdownTicket guardado en BD con routing_state reseteado a NONE.
  6. Tarjeta de avería despachada 1:1 a todos los CompanyUser activos
     del ChatRoom SECTION de taller destino (resolución via WorkshopFamilyMapping).
  7. Historial del chofer visible en visor sala BREAKDOWNS del panel.
  8. Ticket visible y correcto en BotManagementView (campos machine, fault_summary,
     contact con alias resuelto).
  9. WORKSHOPBOSS puede ver sala BREAKDOWNS en ChatRoomListView.
 10. WORKSHOP y DRIVER NO ven sala BREAKDOWNS en ChatRoomListView.
 11. Nadie puede enviar mensajes desde el panel en la sala BREAKDOWNS (can_send=False).
 12. Los tres formularios del dashboard del bot (onboarding, group_broadcast,
     direct_broadcast) funcionan correctamente con sus respectivos action.

Si todos los puntos se validan sin errores: cerrar el Paso 21 en este anexo
marcando su estado como COMPLETADO en la tabla de pasos.
A continuación actualizar el MASTER_DOCUMENT para cerrar formalmente el Hito 13.
