# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md

# Anexo de Hito V13 — Salas de Chat IRC por Sección (WhatsApp → Panel)
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-05-15

---

## 1. Vision General del Hito

El Hito 13 construye un sistema de salas de chat en tiempo cuasi-real dentro
del panel de EnterpriseBot, una sala por cada seccion de la empresa. El canal
de entrada es el numero de WhatsApp registrado con Meta (+34607961650). Cuando
un contacto vinculado a una seccion envia un mensaje a ese numero, el mensaje
se replica automaticamente en la sala de chat correspondiente a su seccion,
visible desde el panel para cualquier usuario autenticado.

El objetivo estrategico es eliminar la restriccion de 8 integrantes por grupo
impuesta por Meta para grupos con chatbot, simulando la pertenencia a un grupo
de WhatsApp con difusion completa hacia todos los miembros de la seccion.

El broadcast actua como mecanismo de onboarding: cuando desde el panel se
envia un mensaje a una seccion y un contacto no tiene alias, el sistema envia
automaticamente el template chat_onboarding para iniciar el proceso de alta.
El registro de trabajadores es competencia exclusiva del Supervisor desde el
panel — no existe autorregistro.

Adicionalmente se construye una sala especial de Averias donde los contactos
pueden iniciar un ticket de averia via WhatsApp mediante un agente Gemini 2.5
Flash (texto). El SUPERVISOR convierte el ticket en orden de reparacion desde
el panel.

---

## 2. Arquitectura Tecnica

### 2.1. Modelo de datos

#### Nuevos modelos en chat/models.py

- ChatRoom: sala IRC. room_type = SECTION | BREAKDOWNS.
- ChatMessage: mensaje en sala. direction = INBOUND | OUTBOUND.
- BreakdownTicket: ticket de averia. status = OPEN | IN_PROGRESS | RESOLVED.
  Campos: ticket_number (autoincremental), machine (FK a MachineAsset, nullable),
  description (TextField), is_repair_order (BooleanField, default=False),
  photos (JSONField, lista de URLs/paths), created_by_contact (FK Contact),
  section (FK Section), resolved_by (FK CompanyUser, nullable),
  resolved_at (DateTimeField, nullable).
- BreakdownConversationTurn: turno de dialogo del agente Gemini de averias.

#### Modificaciones en ivr_config/models.py

CompanyUser.alias — CharField(max_length=50, blank=True, default="")
  Fuente de verdad del alias para mensajes del panel y onboarding WhatsApp.

Contact.alias — CharField(max_length=50, blank=True, default="")
  Usado unicamente para contactos externos sin CompanyUser vinculado.

Contact.alias_onboarding_step — CharField choices: NONE | PENDING | CONFIRMING
  Estado del dialogo de onboarding de alias. Persistido en BD (migracion 0022).

Contact.alias_onboarding_proposed — CharField(max_length=50, blank=True)
  Alias propuesto durante el Paso B del dialogo. Persistido en BD (migracion 0022).

Section.default_role — CharField choices: WORKSHOP | DRIVER, default=WORKSHOP
  Rol asignado al provisionar un CompanyUser via onboarding WhatsApp.

#### Funcion de resolucion de alias

chat/services.py — _resolve_alias(contact) -> str
  1. Si contact.company_user_id y contact.company_user → devuelve CompanyUser.alias.
  2. En caso contrario → devuelve Contact.alias.
  Devuelve cadena vacia si no hay alias en ninguna fuente.

### 2.2. Flujo de onboarding WhatsApp — tres pasos (estado en BD)

Implementado en chat/services.py._handle_alias_collection.
El estado se persiste en Contact.alias_onboarding_step y
Contact.alias_onboarding_proposed — inmune a reloads del servidor.

Paso A — step == ALIAS_STEP_NONE:
  Solicitar nombre al contacto via WhatsApp.
  Guardar step = PENDING en BD.

Paso B — step == ALIAS_STEP_PENDING:
  Interpretar body como alias propuesto (max 50 chars).
  Enviar confirmacion con Quick Reply via WhatsAppChatService.send_quick_reply.
  Template: alias_confirmation (SID: HX55145a651470cc9a66d3b1a32961dc81).
  content_variables: {"1": proposed_alias}.
  Fallback a texto libre si send_quick_reply falla.
  Guardar step = CONFIRMING y alias_onboarding_proposed en BD.

Paso C — step == ALIAS_STEP_CONFIRMING:
  Detectar pulsacion de boton o texto libre afirmativo:
    body.strip().upper() in ("SI", "S", "YES", "Y") o
    body.strip().lower() == "si, usar este nombre"
  Si afirmativo:
    → llamar a _provision_company_user(contact, section, proposed_alias, to_number, from_number).
    → resetear step = NONE y alias_onboarding_proposed = "".
    → enviar mensaje de confirmacion final.
    → reenviar el ultimo ChatMessage(OUTBOUND) de la sala (mensaje que origino el onboarding).
  Si negativo → interpretar body como nuevo alias propuesto, re-confirmar.

### 2.3. Funcion _provision_company_user

Archivo: chat/services.py
Estado: IMPLEMENTADA Y OPERATIVA (sesion 005).
Firma: _provision_company_user(contact, section, proposed_alias, to_number, from_number)

Rama A — contact.company_user ya existe:
  contact.company_user.alias = proposed_alias
  contact.company_user.save(update_fields=["alias"])

Rama B — contact.company_user es None:
  1. Generar username: slugify(proposed_alias) en minusculas con sufijo numerico anti-colision.
  2. Crear auth.User con set_password("1234") y must_change_password=True.
  3. Crear CompanyUser con company=section.company, role=section.default_role, alias=proposed_alias.
  4. Vincular contact.company_user = nuevo CompanyUser.
     contact.alias = "", contact.is_internal = True.
     contact.save(update_fields=["company_user", "alias", "is_internal"]).
  5. Enviar credenciales al contacto via WhatsApp.

### 2.4. Templates WhatsApp

chat_onboarding:
  SID: HX9c92dd8981366dda0764900958b7abbc. Estado: APROBADO. Operativo.
  Uso: broadcast a contactos sin alias o fuera de ventana 24h desde ChatSendView.
  Variables: {{1}} = nombre del contacto, {{2}} = nombre de la empresa.

alias_confirmation:
  SID: HX55145a651470cc9a66d3b1a32961dc81. Estado: EN SESION (sin aprobacion Meta).
  Uso: Paso B del onboarding — confirmar alias propuesto con botones Quick Reply.
  Variables: {{1}} = alias propuesto.
  Botones: "Si, usar este nombre" (id: confirm) / "Cambiar nombre" (id: change).
  Registrado en BD: WhatsAppTemplate pk=5, name="alias_confirmation".

chat_session_renewal:
  SID: HX7e0f3f4d9b8553acc58240e7767f2133.
  Estado: ENVIADO A APROBACION META (2026-05-18). Pendiente de aprobacion.
  Uso: reabrir ventana de 24h para contactos con alias pero sin sesion activa.
  Variables: {{1}} = alias, {{2}} = nombre empresa, {{3}} = URL panel.
  Botones: "Si, quiero recibirlos" (id: opt_in) / "No, gracias" (id: opt_out).
  Registrado en BD: WhatsAppTemplate pk=6, name="chat_session_renewal".

### 2.5. Flujo de entrada — WhatsApp → sala IRC

1. Contacto envia mensaje al numero +34607961650.
2. Twilio dispara webhook POST a /api/whatsapp/incoming/.
3. dispatch_inbound_message(company, from_number, body, to_number) invocado
   antes del pipeline del Hito 4.
4. Si no tiene seccion → flujo Hito 5 (no consumido).
5. Si tiene seccion pero no alias → flujo de onboarding tres pasos (consumido).
6. Si tiene alias → ChatMessage(INBOUND) + broadcast Celery (consumido).

### 2.6. Flujo de salida — panel → WhatsApp

ChatSendView POST /panel/chat/<room_pk>/send/:
  1. Valida rol (solo ADMIN y SUPERVISOR pueden enviar).
  2. Resuelve alias del sender desde CompanyUser.alias. Si vacio → HTTP 400.
     El JS detecta el 400 y abre el modal de alias automaticamente.
     Tras guardar el alias, el JS reenvía el mensaje pendiente automaticamente.
  3. Crea ChatMessage(OUTBOUND) con body "{alias}: {body}".
  4. Por cada contacto de la seccion:
     - Sin alias O sesion fuera de ventana 24h → enviar chat_onboarding.
     - Con alias Y sesion activa → enviar mensaje libre prefijado con alias.
  5. Devuelve JSON {ok, message_pk, sent, skipped, out_of_window}.
  PENDIENTE: cuando chat_session_renewal sea aprobado, sustituir chat_onboarding
  por chat_session_renewal para contactos con alias pero fuera de ventana.

### 2.7. Numero de WhatsApp de la empresa

+34607961650 registrado en PhoneNumber (pk=5, capabilities=WHATSAPP).
ChatSendView resuelve from_number filtrando por capabilities=WHATSAPP.

### 2.8. Infraestructura de tiempo cuasi-real

Polling HTMX cada 3s + trigger "refresh" via hx-trigger en room.html.
El trigger "refresh" se dispara desde chat.js tras envio exitoso para
refresco inmediato sin esperar el ciclo de polling.
Auto-scroll condicional: solo desplaza al fondo cuando el conteo de mensajes
aumenta — no en cada ciclo de polling (chatScrollIfNewMessages en room.html).
Panel lateral de miembros colapsable con toggle tres puntos (⋮).
section_members pasado en contexto desde ChatRoomView.
JS del chat en panel/static/panel/js/chat.js (defer).

### 2.9. Gestion de trabajadores desde el panel

CompanyUserCreateView ampliada con SupervisorAccessMixin.
Formulario: username, nombre, rol, seccion (pre-rellena rol via AJAX), telefono, is_ivr_active.
Si se indica telefono: crea o recupera Contact y lo vincula al CompanyUser.
Si se selecciona seccion: anade el Contact a section.contacts M2M.
WorkerSignupView desactivada — redirige siempre a /panel/login/.
SectionCreateView y SectionUpdateView: SupervisorAccessMixin + inline de trabajadores.
SectionDefaultRoleView: endpoint AJAX GET /panel/sections/<pk>/default-role/.

### 2.10. URLs del modulo chat

/panel/chat/                          — ChatRoomListView
/panel/chat/<room_pk>/               — ChatRoomView
/panel/chat/<room_pk>/messages/      — ChatMessagesPollingView
/panel/chat/<room_pk>/send/          — ChatSendView
/panel/chat/alias/set/               — ChatAliasSetView
/panel/sections/<pk>/default-role/   — SectionDefaultRoleView

### 2.11. Logs de PythonAnywhere

Access log: /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.access.log
Error log:  /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log
Server log: /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.server.log

### 2.12. Signal post_save sobre Section — creacion automatica de ChatRoom

Implementada en S033 (incidencia on-fly) al detectar que las secciones creadas
desde el panel no generaban su ChatRoom automaticamente.

Archivo: chat/signals.py (neonato creado en S033).
Conexion: chat/apps.py ChatConfig.ready() importa chat.signals.

Logica:
  @receiver(post_save, sender=Section)
  def create_chat_room_for_section(sender, instance, created, **kwargs):
    Si created=False → return sin accion.
    Si created=True → ChatRoom.objects.get_or_create(
        company=instance.company, section=instance,
        room_type=SECTION, defaults={name, is_active=True})

Desacoplamiento Section.is_active / ChatRoom:
  Section.is_active=False significa que la seccion no es visible en el IVR.
  No implica ausencia de sala de chat. El comando init_chat_rooms fue corregido
  en S033 para eliminar el filtro is_active=True sobre Section, alineandose con
  este criterio. ChatRoom.is_active gestiona la visibilidad de la sala en el panel
  de forma independiente.

---

## 3. Hoja de Ruta

### Paso 1 — Nueva app chat y modelos base
Estado: COMPLETADO.

### Paso 2 — Comando init_chat_rooms + inicializacion en produccion
Estado: COMPLETADO.
Resultado inicial: 2 salas SECTION + 1 sala BREAKDOWNS para Grupo Alvarez (company_pk=1).
Actualizacion S033 (incidencia on-fly): filtro is_active=True eliminado del comando —
Section.is_active controla el IVR, no la existencia de sala de chat. Signal post_save
sobre Section anadida (chat/signals.py) para creacion automatica en nuevas secciones.
Ejecucion tras correccion: 3 salas SECTION adicionales creadas (Asistencia, Elevacion,
Taller Mecanico). Total activo: 6 salas (5 SECTION + 1 BREAKDOWNS).

### Paso 3 — Campos alias y default_role + migraciones
Estado: COMPLETADO.
- Contact.alias, CompanyUser.alias, Section.default_role — migrados.
- Contact.alias_onboarding_step, Contact.alias_onboarding_proposed — migracion 0022.

### Paso 4 — Vista IRC del panel (lectura + polling)
Estado: COMPLETADO.
- ChatRoomView, ChatMessagesPollingView, ChatRoomListView operativos.
- Variable de contexto renombrada a chat_messages.
- page-content-flush en base.html para vista de chat.
- CSS chat-room-container con flex layout.

### Paso 5 — Integracion webhook → ChatRoom (entrada WhatsApp)
Estado: COMPLETADO.
- dispatch_inbound_message inyectado en whatsapp/views.py.
- _resolve_alias implementado.

### Paso 6 — Envio desde panel → WhatsApp (salida con alias)
Estado: COMPLETADO.
- ChatSendView operativo.
- from_number resuelto desde PhoneNumber con capabilities=WHATSAPP.
- Sandbox +14155238886 eliminado de BD.

### Paso 7 — Flujo de onboarding WhatsApp (alias tres pasos + provision CompanyUser)
Estado: COMPLETADO (sesion 005).
- Flujo E2E verificado en produccion.
- Template alias_confirmation (HX55145a651470cc9a66d3b1a32961dc81) creado y operativo.
- Paso A, B y C operativos con botones Quick Reply reales.
- alias persistido en CompanyUser.alias tras Paso C.
- Mensaje pendiente reenviado al contacto tras confirmar el alias.
- _handle_alias_collection recibe section y room como parametros.

### Paso 8 — Gestion de trabajadores desde panel (Supervisor)
Estado: COMPLETADO.

### Paso 9 — Template chat_onboarding + broadcast
Estado: COMPLETADO.

### Paso 10 — Template chat_session_renewal
Estado: PARCIALMENTE COMPLETADO.
- Template creado en Twilio (SID: HX7e0f3f4d9b8553acc58240e7767f2133).
- Registrado en BD (WhatsAppTemplate pk=6).
- Enviado a aprobacion Meta (2026-05-18). Pendiente de aprobacion.
PENDIENTE tras aprobacion:
  a. En ChatSendView: si receptor tiene alias PERO sesion fuera de ventana 24h
     → enviar chat_session_renewal en lugar de chat_onboarding.
  b. En whatsapp/views.py: handler para respuesta del boton:
       "Si, quiero recibirlos" (ButtonPayload: opt_in):
         → WhatsAppSession.is_active=True, last_message_at=now().
       "No, gracias" (ButtonPayload: opt_out):
         → contact.opt_out_broadcast = True (nuevo campo BooleanField, migracion nueva).
  c. Migracion para Contact.opt_out_broadcast BooleanField(default=False).

### Paso 11 — UX sala IRC
Estado: COMPLETADO (sesion 005).
- Ventana de mensajes con scroll interno robusto en PC y Android.
- Input area siempre visible sin scroll de pagina.
- Auto-scroll condicional (solo al recibir/enviar mensajes nuevos).
- Refresco inmediato tras envio desde el panel (htmx.trigger refresh).
- Panel lateral de miembros colapsable con toggle tres puntos (⋮).
- Indicador de miembro: puntito negro estatico (bi-circle-fill, color #212529).

### Paso 12 — Sala de Averias, agente Gemini y gestion desde panel
Estado: COMPLETADO (sesion 006).
- Modelos ChatRoom.breakdown_sections M2M y ChatRoom.breakdown_contacts M2M anadidos.
- BreakdownTicket extendido: ticket_number (autoincremental por empresa), section FK,
  machine FK (fleet.MachineAsset), is_repair_order, photos JSONField, save() con MAX+1.
- Migraciones ivr_config/0023 y chat/0002 aplicadas en produccion.
- Contact extendido: opt_out_broadcast, routing_state, pending_routing_body.
- Template breakdown_routing creado via curl (SID: HX71d736523adabbd1e6d0fdf8acc2e99c, pk=7).
- chat/services.py: _handle_breakdown_routing, _resolve_pending_routing,
  process_breakdown_turn (agente Gemini 2.5 Flash, marcador TICKET_COMPLETE).
- BreakdownTicketListView, BreakdownTicketDetailView, BreakdownRoomManageView
  implementadas con templates HTML y registradas en URLs.
- django check: 0 errores. collectstatic: OK.

### Paso 13 — Tarea de limpieza y ajustes finales
Estado: PENDIENTE.
- Badge de mensajes no leidos en sidebar.
- Pruebas con multiples salas y multiples usuarios.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados       | Resumen |
|--------|------------|------------------------|---------|
| 001    | 2026-05-15 | —                      | Creacion del anexo. Diseno de arquitectura completo aprobado. Inicio formal del hito. |
| 002    | 2026-05-15 | Pasos 1, 2 y arq       | App chat creada, modelos migrados, init_chat_rooms ejecutado. Arquitectura revisada. |
| 003    | 2026-05-16 | Pasos 3-7 parcial      | CompanyUser.alias, Section.default_role, ChatSendView, ChatAliasSetView, modal alias, chat.js, onboarding tres pasos. Error de indentacion en chat/services.py — archivo en disco ROTO. |
| 004    | 2026-05-17/18 | Pasos 3-9 + rediseno | Restauracion y correccion de chat/services.py. Rediseno arquitectura de registro: WorkerSignupView desactivada, gestion de trabajadores desde panel Supervisor. CompanyUserCreateForm ampliado. SectionCreateView/UpdateView con inline trabajadores. SectionDefaultRoleView. Migracion 0022: alias_onboarding_step y alias_onboarding_proposed en Contact. Flujo de onboarding migrado de memoria a BD. send_quick_reply anadido a WhatsAppChatService. SID chat_onboarding corregido en BD. Sandbox eliminado. PhoneNumber +34607961650 registrado. Paso 7 en pruebas: Paso A y B operativos, Paso C pendiente verificacion. |
| 005    | 2026-05-18 | Pasos 7, 10, 11 + skill PED | Paso 7 completado E2E: template alias_confirmation creado via Content API, send_quick_reply rediseñado para usar content_sid pre-registrado con fallback a texto plano, NameError section y room corregidos en _handle_alias_collection, reenvio de mensaje pendiente tras onboarding operativo. Template chat_session_renewal creado y enviado a aprobacion Meta (pk=6). Paso 11 completado: layout flex robusto PC/Android, scroll condicional, refresco inmediato tras envio, panel lateral colapsable de miembros. Skill PED creada y actualizada con reglas de anclas exactas via script obligatorio. Logs PythonAnywhere registrados en arquitectura. |
| 006    | 2026-05-18 | Paso 12 completo            | Paso 10 bloqueado — template chat_session_renewal En revision en Meta. Paso 12 completado: Contact extendido (opt_out_broadcast, routing_state, pending_routing_body), ChatRoom M2M (breakdown_sections, breakdown_contacts), BreakdownTicket extendido (ticket_number autoincremental, section, machine, is_repair_order, photos), migraciones ivr_config/0023 y chat/0002 aplicadas. Template breakdown_routing creado via curl (HX71d736523adabbd1e6d0fdf8acc2e99c, pk=7). chat/services.py ampliado con _handle_breakdown_routing, _resolve_pending_routing y process_breakdown_turn (Gemini 2.5 Flash). Vistas BreakdownTicketListView, BreakdownTicketDetailView, BreakdownRoomManageView con templates HTML. Hito 13 pausado — se activa Hito 7 para siguiente sesion. |
| S033   | 2026-05-18 | Incidencia on-fly           | Incidencia detectada desde H7: secciones creadas desde el panel no generaban ChatRoom automaticamente. Causa raiz: init_chat_rooms filtraba Section.is_active=True mezclando visibilidad IVR con existencia de sala de chat. Solucion: (1) chat/signals.py creado — signal post_save sobre Section con get_or_create de ChatRoom tipo SECTION; (2) chat/apps.py ampliado con ready() que conecta la signal; (3) init_chat_rooms corregido eliminando filtro is_active=True sobre Section. Ejecucion del comando corregido: 3 salas nuevas creadas (Asistencia, Elevacion, Taller Mecanico). Total activo: 6 salas. django check: 0 errores. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### NOTA DE ESTADO
El Hito 13 queda PAUSADO tras la sesion 006. Se retoma cuando se reactive.
El Hito 7 pasa a EN PROGRESO para la siguiente sesion.

### Prioridad 1 — Paso 10: implementar logica chat_session_renewal

BLOQUEADO hasta aprobacion Meta del template chat_session_renewal
(SID: HX7e0f3f4d9b8553acc58240e7767f2133, pk=6, estado: En revision 2026-05-18).

Al reactivar este hito, verificar primero el estado en Twilio Dashboard.
Si aprobado, implementar en tres archivos:

A) chat/views.py — ChatSendView — bucle de broadcast (lineas aproximadas 780-865).
   Condicion actual:
     needs_onboarding = not _receiver_alias or not has_active_session
   Nueva logica:
     needs_onboarding_cold = not _receiver_alias
     needs_session_renewal = _receiver_alias and not has_active_session
     Si needs_onboarding_cold → enviar chat_onboarding (sin cambio).
     Si needs_session_renewal → enviar chat_session_renewal:
       variables: {"1": _receiver_alias, "2": company.name,
                   "3": "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/"}
     Ademas: excluir contactos con contact.opt_out_broadcast=True del bucle completo.

B) whatsapp/views.py — IncomingWhatsAppView.post() — insertar handler de ButtonPayload
   ANTES de la llamada a dispatch_inbound_message (linea aprox. 833).
   ButtonPayload = request.POST.get("ButtonPayload", "").strip()
   Si ButtonPayload == "opt_in":
     WhatsAppSession.objects.filter(company=company, phone_number=from_number).update(
         is_active=True, last_message_at=now())
     WhatsAppChatService.send_reply(from_number=to_number, to_number=from_number,
         reply_text="Perfecto, te mantendremos informado/a.")
     return HttpResponse(status=200)
   Si ButtonPayload == "opt_out":
     Contact resuelto de company+from_number.
     contact.opt_out_broadcast = True
     contact.save(update_fields=["opt_out_broadcast"])
     WhatsAppChatService.send_reply(from_number=to_number, to_number=from_number,
         reply_text="De acuerdo, no recibirás más mensajes del grupo.")
     return HttpResponse(status=200)

C) Contact.opt_out_broadcast ya existe en BD (migracion 0023 aplicada).
   Solo pendiente la logica de exclusion en ChatSendView (punto A).

### Prioridad 2 — Paso 13: limpieza y ajustes finales

- Badge de mensajes no leidos en sidebar: contar ChatMessage(INBOUND) sin
  marcar como leido. Requiere campo ChatMessage.read BooleanField(default=False)
  y endpoint para marcar como leido al abrir la sala.
- Pruebas E2E con multiples salas y multiples usuarios simultaneos.
- Verificacion E2E del flujo completo BREAKDOWNS: enrutamiento Quick Reply →
  agente Gemini → ticket creado → vista panel → cierre por SUPERVISOR.
