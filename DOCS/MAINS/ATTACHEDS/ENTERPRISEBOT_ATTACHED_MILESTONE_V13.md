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
Flash (texto). El SUPERVISOR cierra el ticket desde el panel.

---

## 2. Arquitectura Tecnica

### 2.1. Modelo de datos

#### Nuevos modelos en chat/models.py

- ChatRoom: sala IRC. room_type = SECTION | BREAKDOWNS.
- ChatMessage: mensaje en sala. direction = INBOUND | OUTBOUND.
- BreakdownTicket: ticket de averia. status = OPEN | IN_PROGRESS | RESOLVED.
- BreakdownConversationTurn: turno de dialogo del agente Gemini de averias.

#### Modificaciones en ivr_config/models.py

CompanyUser.alias — CharField(max_length=50, blank=True, default="")
  Fuente de verdad del alias para mensajes del panel y onboarding WhatsApp.

Contact.alias — CharField(max_length=50, blank=True, default="")
  Usado unicamente para contactos externos sin CompanyUser vinculado.

Contact.alias_onboarding_step — CharField choices: NONE | PENDING | CONFIRMING
  Estado del dialogo de onboarding de alias. Persistido en BD (migracion 0022).
  Sustituye a los sets en memoria _ALIAS_PENDING / _ALIAS_CONFIRMING.

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
  Enviar confirmacion con Quick Reply buttons via WhatsAppChatService.send_quick_reply.
  Botones: ["Si, usar este nombre", "Cambiar nombre"].
  Guardar step = CONFIRMING y alias_onboarding_proposed en BD.

Paso C — step == ALIAS_STEP_CONFIRMING:
  Detectar pulsacion de boton o texto libre afirmativo:
    body.strip().upper() in ("SI", "S", "YES", "Y", "SI, USAR ESTE NOMBRE")
  Si afirmativo → llamar a _provision_company_user, resetear step = NONE.
  Si negativo → interpretar body como nuevo alias propuesto, re-confirmar con botones.

### 2.3. Funcion _provision_company_user

Archivo: chat/services.py
Estado: IMPLEMENTADA (sesion 004).

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
  SID real en Twilio: HX9c92dd8981366dda0764900958b7abbc (corregido en sesion 004).
  Estado: APROBADO por Meta. Operativo.
  Uso: broadcast a contactos sin alias o fuera de ventana 24h desde ChatSendView.
  Variables: {{1}} = nombre del contacto, {{2}} = nombre de la empresa.

chat_session_renewal:
  Estado: PENDIENTE DE CREACION.
  Uso: reabrir ventana de 24h para contactos con alias pero sin sesion activa.
  Cuerpo: "Hola {{1}}, tienes mensajes nuevos en el chat de grupo de tu seccion en {{2}}.
           Si prefieres no recibirlos por WhatsApp, puedes consultarlos desde el panel en: {{3}}
           Si no eres trabajador de {{2}}, ignora este mensaje."
  Botones Quick Reply: ["Si, quiero recibirlos", "No, gracias"]
  Categoria: Utility.

### 2.5. Flujo de entrada — WhatsApp → sala IRC

1. Contacto envia mensaje al numero +34607961650.
2. Twilio dispara webhook POST a /api/whatsapp/incoming/.
3. dispatch_inbound_message invocado antes del pipeline del Hito 4.
4. Si no tiene seccion → flujo Hito 5 (no consumido).
5. Si tiene seccion pero no alias → flujo de onboarding tres pasos (consumido).
6. Si tiene alias → ChatMessage(INBOUND) + broadcast (consumido).

### 2.6. Flujo de salida — panel → WhatsApp

ChatSendView POST /panel/chat/<room_pk>/send/:
  1. Valida rol (solo ADMIN y SUPERVISOR pueden enviar).
  2. Resuelve alias del sender desde CompanyUser.alias. Si vacio → HTTP 400.
     El JS detecta el 400 y abre el modal de alias automaticamente.
     Tras guardar el alias, el JS reenvía el mensaje pendiente automaticamente.
  3. Crea ChatMessage(OUTBOUND).
  4. Por cada contacto de la seccion:
     - Si no tiene alias O sesion fuera de ventana 24h → enviar chat_onboarding.
     - Si tiene alias Y sesion activa → enviar mensaje libre prefijado con alias.
  5. Devuelve JSON {ok, message_pk, sent, skipped, out_of_window}.

### 2.7. Numero de WhatsApp de la empresa

+34607961650 registrado en PhoneNumber (pk=5, capabilities=WHATSAPP).
El sandbox +14155238886 fue eliminado de BD en sesion 004.
ChatSendView resuelve from_number filtrando por capabilities=WHATSAPP.

### 2.8. Infraestructura de tiempo cuasi-real

Polling HTMX cada 3s via hx-trigger en room.html.
Variable de contexto renombrada a chat_messages (evita conflicto con Django messages).
JS del chat en panel/static/panel/js/chat.js (defer).
Modal de alias: se abre automaticamente si alias_required=True o si el sender
  intenta enviar sin alias (captura el HTTP 400 en el JS).
Contenedor IRC: clase page-content-flush en base.html cuando active_nav == 'chat'.
CSS: .chat-room-container con flex:1 y min-height:0 en panel.css.

### 2.9. Gestion de trabajadores desde el panel

CompanyUserCreateView ampliada con SupervisorAccessMixin.
Formulario: username, nombre, rol, seccion (pre-rellena rol via AJAX), telefono, is_ivr_active.
Si se indica telefono: crea o recupera Contact y lo vincula al CompanyUser.
Si se selecciona seccion: anade el Contact a section.contacts M2M.
WorkerSignupView desactivada — redirige siempre a /panel/login/ con mensaje informativo.
SectionCreateView y SectionUpdateView: SupervisorAccessMixin + inline de trabajadores
  con tabla de CompanyUser asignados y fila expandible para dar de alta nuevos.
SectionDefaultRoleView: endpoint AJAX GET /panel/sections/<pk>/default-role/
  Devuelve JSON {"default_role": "..."} para pre-rellenar el selector de rol.

### 2.10. URLs del modulo chat

/panel/chat/                          — ChatRoomListView
/panel/chat/<room_pk>/               — ChatRoomView
/panel/chat/<room_pk>/messages/      — ChatMessagesPollingView
/panel/chat/<room_pk>/send/          — ChatSendView
/panel/chat/alias/set/               — ChatAliasSetView
/panel/sections/<pk>/default-role/   — SectionDefaultRoleView

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
- Variable de contexto renombrada a chat_messages (evita conflicto Django messages).
- page-content-flush en base.html para vista de chat.
- CSS chat-room-container con flex layout.

### Paso 5 — Integracion webhook → ChatRoom (entrada WhatsApp)
Estado: COMPLETADO.
- dispatch_inbound_message inyectado en whatsapp/views.py.
- _resolve_alias implementado.
- logger anadido a chat/views.py (import logging).

### Paso 6 — Envio desde panel → WhatsApp (salida con alias)
Estado: COMPLETADO.
- ChatSendView operativo con verificacion de alias del receptor.
- from_number resuelto desde PhoneNumber con capabilities=WHATSAPP.
- Sandbox +14155238886 eliminado de BD.
- content_variables enviado como JSON string (corregido en sesion 004).

### Paso 7 — Flujo de onboarding WhatsApp (alias tres pasos + provision CompanyUser)
Estado: PARCIALMENTE COMPLETADO — EN PRUEBAS.

Completado:
- Estado migrado de memoria a BD (Contact.alias_onboarding_step / alias_onboarding_proposed).
- _provision_company_user implementada.
- Paso A y Paso B operativos.
- Paso C: deteccion de afirmativo con boton "Si, usar este nombre" implementada.
- send_quick_reply anadido a WhatsAppChatService.

PENDIENTE:
- Verificar end-to-end en produccion que el Paso C cierra el flujo correctamente
  y persiste el alias en CompanyUser.alias.
- Implementar template chat_session_renewal con botones Quick Reply en Twilio/Meta.
- Una vez aprobado: logica en ChatSendView para usar chat_session_renewal
  cuando el receptor tiene alias pero sesion fuera de ventana 24h (en lugar de chat_onboarding).

### Paso 8 — Gestion de trabajadores desde panel (Supervisor)
Estado: COMPLETADO (incorporado en sesion 004 como parte del rediseno de arquitectura).
- WorkerSignupView desactivada.
- CompanyUserCreateForm con section, phone_number, is_ivr_active.
- SectionCreateView y SectionUpdateView con inline de trabajadores.
- SectionDefaultRoleView (endpoint AJAX).

### Paso 9 — Template chat_onboarding + broadcast a contactos sin sesion/alias
Estado: COMPLETADO.
- SID corregido en BD: HX9c92dd8981366dda0764900958b7abbc.
- Broadcast a contactos sin alias o fuera de ventana 24h desde ChatSendView.

### Paso 10 — Template chat_session_renewal
Estado: PENDIENTE.
- Dar de alta en Twilio Content Template Builder con botones Quick Reply.
- Categoria: Utility.
- Variables: {{1}} alias, {{2}} nombre empresa, {{3}} URL panel.
- Botones: "Si, quiero recibirlos" / "No, gracias".
- Esperar aprobacion Meta.
- Implementar logica en ChatSendView: si receptor tiene alias pero sesion fuera
  de ventana → enviar chat_session_renewal en lugar de chat_onboarding.
- Implementar handler en whatsapp/views.py para procesar respuesta del boton:
    Si "Si" → reabrir sesion (WhatsAppSession.is_active=True, last_message_at=now()).
    Si "No" → marcar contacto como fuera de broadcast (nuevo campo a definir).

### Paso 11 — UX sala IRC
Estado: PENDIENTE.
- Ventana de mensajes de altura fija con scroll interno robusto (revisar CSS).
- Panel lateral con listado de miembros de la sala (CompanyUser asignados a la seccion).
- Input area siempre visible sin necesidad de scroll de pagina.

### Paso 12 — Sala de Averias y agente Gemini
Estado: PENDIENTE.
- process_breakdown_turn en chat/services.py.
- BreakdownTicketListView en panel para SUPERVISOR.
- Cierre de ticket desde panel (status RESOLVED).

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
| 004    | 2026-05-17/18 | Pasos 3-9 + rediseno | Restauracion y correccion de chat/services.py. Rediseno arquitectura de registro: WorkerSignupView desactivada, gestion de trabajadores desde panel Supervisor. CompanyUserCreateForm ampliado. SectionCreateView/UpdateView con inline trabajadores. SectionDefaultRoleView. Migracion 0022: alias_onboarding_step y alias_onboarding_proposed en Contact. Flujo de onboarding migrado de memoria a BD. send_quick_reply anadido a WhatsAppChatService. SID chat_onboarding corregido en BD. Sandbox eliminado. PhoneNumber +34607961650 registrado. logger anadido a chat/views.py. page-content-flush para UX chat. Variable chat_messages. Paso 7 en pruebas: Paso A y B operativos, Paso C pendiente verificacion. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Prioridad 1 — Verificar y cerrar Paso C del onboarding de alias

El Paso C (confirmacion de alias via boton Quick Reply) debe verificarse
end-to-end en produccion. El estado del contacto de prueba debe resetearse:

  python -m dotenv run python manage.py shell << 'EOF'
  from ivr_config.models import Contact
  c = Contact.objects.get(phone_number="+34711509585")
  c.alias_onboarding_step     = Contact.ALIAS_STEP_NONE
  c.alias_onboarding_proposed = ""
  if c.company_user:
      c.company_user.alias = ""
      c.company_user.save(update_fields=["alias"])
  c.save(update_fields=["alias_onboarding_step", "alias_onboarding_proposed"])
  EOF

Flujo a verificar:
  1. Enviar mensaje desde el panel → contacto sin alias → recibe chat_onboarding.
  2. Contacto responde → recibe solicitud de nombre (Paso A).
  3. Contacto da su nombre → recibe mensaje con botones Quick Reply (Paso B).
  4. Contacto pulsa "Si, usar este nombre" → alias guardado en CompanyUser.alias
     y alias_onboarding_step reseteado a NONE (Paso C).
  5. Enviar nuevo mensaje desde el panel → contacto ahora recibe el mensaje libre.

Si send_quick_reply falla (Twilio rechaza el content template transitorio):
  Revisar la implementacion de WhatsAppChatService.send_quick_reply
  en whatsapp/services.py. El metodo crea un template twilio/quick-reply
  en la Content API y lo envia. Si la Content API no esta disponible en
  el plan actual de Twilio, sustituir por texto libre con instruccion
  explicita: "Responde SI para confirmar o escribe otro nombre."

### Prioridad 2 — Template chat_session_renewal

Dar de alta en Twilio Content Template Builder:
  Nombre: chat_session_renewal
  Categoria: Utility
  Cuerpo: "Hola {{1}}, tienes mensajes nuevos en el chat de grupo de tu seccion
           en {{2}}. Si prefieres no recibirlos por WhatsApp, puedes consultarlos
           desde el panel en: {{3}} Si no eres trabajador de {{2}}, ignora este mensaje."
  Botones Quick Reply: ["Si, quiero recibirlos", "No, gracias"]

Una vez aprobado por Meta:
  a. Registrar en WhatsAppTemplate con name="chat_session_renewal".
  b. En ChatSendView: si receptor tiene alias PERO sesion fuera de ventana 24h
     → enviar chat_session_renewal en lugar de chat_onboarding.
  c. En whatsapp/views.py: handler para respuesta del boton:
       "Si, quiero recibirlos" → WhatsAppSession.is_active=True, last_message_at=now().
       "No, gracias" → marcar contacto (nuevo campo boolean contact.opt_out_broadcast).

### Prioridad 3 — UX sala IRC (Paso 11)

Objetivo: ventana de mensajes de altura fija, input siempre visible, panel de miembros.

  a. Revisar el CSS de .chat-room-container y .page-content-flush para garantizar
     que la altura es robusta en todos los viewports moviles.
  b. Anadir panel lateral derecho en room.html con listado de miembros de la sala:
     - Consultar CompanyUser vinculados a la seccion via section.contacts.
     - Mostrar alias (o username si sin alias) y indicador de sesion activa.
  c. Verificar que el input area es siempre visible sin scroll de pagina.
