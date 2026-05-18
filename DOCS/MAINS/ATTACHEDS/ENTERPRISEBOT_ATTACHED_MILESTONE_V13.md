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

---

## 3. Hoja de Ruta

### Paso 1 — Nueva app chat y modelos base
Estado: COMPLETADO.

### Paso 2 — Comando init_chat_rooms + inicializacion en produccion
Estado: COMPLETADO.
Resultado: 2 salas SECTION + 1 sala BREAKDOWNS para Grupo Alvarez (company_pk=1).

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
Estado: PENDIENTE.
Ver seccion "Hoja de Ruta para la Siguiente Sesion" para diseno completo.

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

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Prioridad 1 — Paso 10: implementar logica chat_session_renewal (pendiente aprobacion Meta)

Verificar primero el estado de aprobacion del template en Twilio dashboard.
Si aprobado, implementar en dos archivos:

A) chat/views.py — ChatSendView — sustituir chat_onboarding por chat_session_renewal
   para contactos con alias pero sesion fuera de ventana 24h.
   Logica exacta en el bucle de broadcast (actualmente lineas ~630-698 de chat/views.py):

   Condicion actual:
     needs_onboarding = not _receiver_alias or not has_active_session
   
   Nueva logica:
     needs_onboarding_cold   = not _receiver_alias  (sin alias — siempre chat_onboarding)
     needs_session_renewal   = _receiver_alias and not has_active_session
     
     Si needs_onboarding_cold → enviar chat_onboarding (igual que ahora).
     Si needs_session_renewal → enviar chat_session_renewal con variables:
       {"1": _receiver_alias, "2": company.name,
        "3": "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/"}
     Si tiene alias Y sesion activa → enviar mensaje libre (igual que ahora).

B) whatsapp/views.py — IncomingWhatsAppView — handler para respuesta de boton
   chat_session_renewal. El ButtonPayload llega en request.POST.get("ButtonPayload").
   
   Logica del handler (antes del dispatch_inbound_message):
     Si ButtonPayload == "opt_in":
       WhatsAppSession.objects.filter(company=company, phone_number=from_number).update(
           is_active=True, last_message_at=now())
       Enviar texto libre: "Perfecto, te mantendremos informado/a."
       return HttpResponse con TwiML vacio.
     Si ButtonPayload == "opt_out":
       contact.opt_out_broadcast = True
       contact.save(update_fields=["opt_out_broadcast"])
       Enviar texto libre: "De acuerdo, no recibirás más mensajes del grupo."
       return HttpResponse con TwiML vacio.

C) ivr_config/models.py — añadir Contact.opt_out_broadcast:
   opt_out_broadcast = models.BooleanField(default=False)
   Crear migracion correspondiente.
   En ChatSendView: excluir contactos con opt_out_broadcast=True del broadcast.

### Prioridad 2 — Paso 12: Sala de Averias, agente Gemini y gestion desde panel

El Paso 12 ha sido rediseñado respecto al diseno original. Alcance completo:

#### A) Modelo BreakdownTicket — extension

Revisar chat/models.py y añadir campos a BreakdownTicket si no existen:
  ticket_number: AutoField o secuencia propia por empresa.
  machine: ForeignKey a fleet.MachineAsset, null=True, blank=True.
  description: TextField(blank=True).
  is_repair_order: BooleanField(default=False).
  photos: JSONField(default=list) — lista de rutas/URLs de fotos adjuntas.
  created_by_contact: ForeignKey a ivr_config.Contact, null=True.
  section: ForeignKey a ivr_config.Section, null=True.
  resolved_by: ForeignKey a ivr_config.CompanyUser, null=True, blank=True.
  resolved_at: DateTimeField(null=True, blank=True).
Crear migracion si hay cambios en el modelo.

#### B) Membresía de la sala BREAKDOWNS — gestion desde panel

La sala BREAKDOWNS no tiene seccion fija. Los contactos que pueden enviar
mensajes a ella se gestionan mediante una relacion M2M directa entre
ChatRoom(BREAKDOWNS) y Contact (o Section).

Añadir a ChatRoom:
  breakdown_sections: ManyToManyField(Section, blank=True)
    Secciones cuyos miembros tienen acceso a la sala de averias.
  breakdown_contacts: ManyToManyField(Contact, blank=True)
    Contactos individuales adicionales con acceso directo.

Vista de gestion en panel (BreakdownRoomManageView):
  URL: /panel/chat/breakdowns/manage/
  Acceso: ADMIN y SUPERVISOR.
  Permite añadir/quitar secciones completas y contactos individuales.
  Al añadir una seccion: todos sus contactos quedan elegibles para BREAKDOWNS.

#### C) Enrutamiento de mensajes — contacto en seccion y en BREAKDOWNS

Cuando dispatch_inbound_message recibe un mensaje de un contacto que:
  - Tiene seccion asignada Y
  - Esta en breakdown_sections o breakdown_contacts de la sala BREAKDOWNS

El sistema debe preguntar via WhatsApp antes de enrutar:
  "¿A qué grupo deseas enviar el mensaje?
   Opción A — {nombre de su seccion}
   Opción B — Sala de Averias"

Implementar via template Quick Reply nuevo: breakdown_routing.
  Nombre: breakdown_routing
  Botones: ["Opcion A - {seccion}", "Opcion B - Averias"]
  Variables: {{1}} = nombre de la seccion.
  
Estado de enrutamiento pendiente: persistir en Contact un campo
  pending_routing_body = TextField(blank=True, default="")
  routing_state = CharField(choices: NONE | AWAITING_ROUTE, default=NONE)
para guardar el body original mientras se espera la respuesta del contacto.

Si el contacto solo tiene seccion (sin acceso a BREAKDOWNS) → enrutar
directamente a su sala de seccion sin preguntar (comportamiento actual).
Si el contacto solo tiene acceso a BREAKDOWNS (sin seccion) → enrutar
directamente a BREAKDOWNS sin preguntar.

#### D) Agente Gemini de averias (process_breakdown_turn)

Archivo: chat/services.py — funcion process_breakdown_turn(contact, body, room, to_number, from_number)
Modelo Gemini: gemini-2.5-flash (texto, no Live).
Autenticacion: Vertex AI via Service Account JSON (_build_genai_client de whatsapp/services.py).

El agente recoge los siguientes campos via dialogo campo a campo:
  1. Maquina afectada (nombre o codigo — buscar en MachineAsset de la empresa).
  2. Descripcion del problema / sintoma.
  3. Urgencia (Alta / Media / Baja).
  4. Ubicacion de la maquina.
  5. Fotos (el contacto puede enviar hasta 3 imagenes via WhatsApp Media).

El agente persiste BreakdownConversationTurn en BD en cada turno.
Cuando todos los campos esten recogidos, el agente:
  - Crea el BreakdownTicket con los datos recopilados.
  - Confirma al contacto con el numero de ticket.
  - Notifica a SUPERVISOR/ADMIN via ChatMessage(OUTBOUND) en la sala BREAKDOWNS.

#### E) Gestion de tickets desde panel

BreakdownTicketListView: /panel/chat/breakdowns/tickets/
  - Lista todos los BreakdownTicket de la empresa ordenados por created_at DESC.
  - Filtros: status, machine, section, is_repair_order.
  - Acceso: ADMIN y SUPERVISOR.

BreakdownTicketDetailView: /panel/chat/breakdowns/tickets/<pk>/
  - Muestra todos los campos del ticket.
  - Boton "Convertir en Orden de Reparacion": sets is_repair_order=True.
  - Boton "Cerrar ticket": sets status=RESOLVED, resolved_by=request.user.company_user,
    resolved_at=now().
  - Muestra fotos adjuntas si existen.

### Prioridad 3 — Paso 13: limpieza y ajustes finales

- Badge de mensajes no leidos en sidebar: contar ChatMessage(INBOUND) sin
  marcar como leido. Requiere campo ChatMessage.read BooleanField(default=False)
  y endpoint para marcar como leido al abrir la sala.
- Pruebas E2E con multiples salas y multiples usuarios simultaneos.
