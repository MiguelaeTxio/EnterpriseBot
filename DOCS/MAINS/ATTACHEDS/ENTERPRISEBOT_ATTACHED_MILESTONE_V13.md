# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md

# Anexo de Hito V13 — Salas de Chat IRC por Sección (WhatsApp → Panel)
# Proyecto: EnterpriseBot
# Estado: PAUSADO
# Fecha de inicio: 2026-05-15

---

## 1. Vision General del Hito

El Hito 13 construye un sistema de salas de chat en tiempo cuasi-real dentro
del panel de EnterpriseBot, una sala por cada seccion de la empresa. El canal
de entrada es el numero de WhatsApp registrado con Meta (+34607961650). Cuando
un contacto vinculado a una seccion envia un mensaje a ese numero, el mensaje
se replica automaticamente en la sala de chat correspondiente a su seccion,
visible desde el panel para cualquier usuario autenticado (ADMIN, SUPERVISOR,
WORKSHOP).

El objetivo estrategico es eliminar la restriccion de 8 integrantes por grupo
impuesta por Meta para grupos con chatbot, simulando la pertenencia a un grupo
de WhatsApp con difusion completa hacia todos los miembros de la seccion.

Adicionalmente se construye una sala especial de Averias donde los contactos
pueden iniciar un ticket de averia via WhatsApp. Un agente conversacional
Gemini 2.5 Flash (texto) recoge los datos pertinentes de la averia mediante
dialogo natural y los persiste en un modelo dedicado. El SUPERVISOR cierra
el ticket desde el panel cuando la averia queda resuelta.

Limitacion de alcance: el enrutamiento de contactos desconocidos (sin seccion
asignada) queda fuera de este hito. Es responsabilidad del Hito 5 (puente
IVR <-> WhatsApp).

---

## 2. Arquitectura Tecnica

### 2.1. Modelo de datos — nuevos modelos

#### ChatRoom (chat/models.py)

Representa una sala de chat. Una sala puede ser de tipo SECTION (una por
seccion) o BREAKDOWNS (sala especial de averias, una por empresa).

Campos:
  company       — FK(Company, CASCADE), related_name="chat_rooms"
  section       — FK(Section, SET_NULL, null=True, blank=True) — nulo para sala BREAKDOWNS
  room_type     — CharField choices: SECTION / BREAKDOWNS
  name          — CharField(max_length=100) — nombre legible de la sala
  is_active     — BooleanField(default=True)
  created_at    — DateTimeField(auto_now_add=True)

Invariante: una empresa tiene exactamente una ChatRoom por Section activa
mas una ChatRoom de tipo BREAKDOWNS.

#### ChatMessage (chat/models.py)

Representa un mensaje en una sala. Origen puede ser un contacto externo
(WhatsApp entrante) o un usuario del panel (respuesta saliente).

Campos:
  room           — FK(ChatRoom, CASCADE), related_name="messages"
  direction      — CharField choices: INBOUND / OUTBOUND
  sender_contact — FK(Contact, SET_NULL, null=True, blank=True) — contacto WhatsApp origen
  sender_user    — FK(CompanyUser, SET_NULL, null=True, blank=True) — usuario panel origen
  body           — TextField — contenido del mensaje
  whatsapp_sid   — CharField(max_length=64, blank=True) — SID del mensaje Twilio
  created_at     — DateTimeField(auto_now_add=True, db_index=True)

Regla TTL: mensajes con created_at < now() - 7 dias se eliminan por tarea
Celery periodica (purge_old_chat_messages).

#### BreakdownTicket (chat/models.py)

Representa un ticket de averia iniciado por un contacto desde WhatsApp.
El agente Gemini recoge los datos campo a campo mediante dialogo natural.

Campos:
  room           — FK(ChatRoom, CASCADE) — sala BREAKDOWNS de la empresa
  contact        — FK(Contact, CASCADE) — contacto que inicia el ticket
  status         — CharField choices: OPEN / IN_PROGRESS / RESOLVED
  machine_raw    — CharField(max_length=200, blank=True) — maquina/vehiculo afectado
  fault_summary  — TextField(blank=True) — resumen de la averia
  location       — CharField(max_length=200, blank=True) — ubicacion del vehiculo
  urgency        — CharField choices: LOW / MEDIUM / HIGH / CRITICAL
  notes          — TextField(blank=True) — notas adicionales del operario
  resolved_by    — FK(CompanyUser, SET_NULL, null=True, blank=True) — quien cierra
  resolved_at    — DateTimeField(null=True, blank=True)
  created_at     — DateTimeField(auto_now_add=True)
  updated_at     — DateTimeField(auto_now=True)

#### BreakdownConversationTurn (chat/models.py)

Registro de cada turno del dialogo de recogida de datos de averia.
Necesario para reconstruir el contexto de la conversacion en cada llamada
a Gemini (sin estado — contexto completo en cada peticion).

Campos:
  ticket        — FK(BreakdownTicket, CASCADE), related_name="turns"
  role          — CharField choices: USER / MODEL
  content       — TextField
  created_at    — DateTimeField(auto_now_add=True)

### 2.2. Nueva app Django — `chat`

Nueva aplicacion Django `chat` alojada en:
  /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/

Estructura minima:
  chat/models.py        — ChatRoom, ChatMessage, BreakdownTicket, BreakdownConversationTurn
  chat/views.py         — ChatRoomView, ChatSendView, ChatMessagesPollingView,
                          BreakdownTicketListView, BreakdownTicketResolveView
  chat/services.py      — logica de despacho, agente Gemini de averias
  chat/tasks.py         — purge_old_chat_messages, broadcast_inbound_message
  chat/urls.py          — rutas del modulo chat
  chat/admin.py         — registro en Django admin
  chat/apps.py          — configuracion de la app
  chat/migrations/      — migraciones
  chat/management/commands/init_chat_rooms.py

### 2.3. Flujo de entrada — WhatsApp → sala IRC

1. Contacto envia mensaje al numero +34607961650.
2. Twilio dispara webhook POST a /api/whatsapp/inbound/ (endpoint existente
   del Hito 4, reutilizado).
3. La vista del webhook identifica el remitente (numero de telefono) y
   busca el Contact correspondiente en BD (scope: empresa del numero receptor).
4. Si el Contact tiene seccion asignada → se determina la ChatRoom de tipo
   SECTION correspondiente.
   Si el Contact no tiene seccion → fuera de alcance de este hito (ver H5).
5. Se crea un ChatMessage(direction=INBOUND) en la sala.
6. Se encola tarea Celery broadcast_inbound_message(message_pk).
7. Si la sala es BREAKDOWNS y el contacto tiene un ticket OPEN o IN_PROGRESS:
   el mensaje se enruta al agente Gemini de averias en lugar de al chat general
   (ver seccion 2.5).

### 2.4. Flujo de salida — panel → WhatsApp

El usuario del panel escribe un mensaje en la sala y pulsa Enviar.
ChatSendView(SupervisorAccessMixin, View) POST:
  1. Crea ChatMessage(direction=OUTBOUND, sender_user=cu).
  2. Envia el mensaje via Twilio WhatsApp API a los contactos de la seccion
     que tengan sesion activa (ventana de 24h de Meta).
  3. Persiste el whatsapp_sid de cada envio en el ChatMessage.

Limitacion de ventana: Meta impone ventana de 24h para responder a mensajes
libres. Fuera de esa ventana solo se puede usar un template aprobado (HX...).
El panel advierte visualmente cuando un contacto esta fuera de ventana.

### 2.5. Agente de Averias — Gemini 2.5 Flash conversacional

Modelo: gemini-2.5-flash (texto, no audio).
Plataforma: Vertex AI (mismo service account que el resto del proyecto).
Sin estado: el contexto completo de la conversacion se reconstruye en cada
llamada desde BreakdownConversationTurn.

Campos objetivo que el agente debe recoger:
  - machine_raw  : identificacion de la maquina o vehiculo afectado.
  - fault_summary: descripcion de la averia con el mayor detalle posible.
  - location     : ubicacion actual del vehiculo o donde ocurrio la averia.
  - urgency      : nivel de urgencia (el agente sugiere, el contacto confirma).

Flujo del agente:
  1. Al recibir el primer mensaje en la sala BREAKDOWNS (o detectar intencion
     de averia), se crea un BreakdownTicket(status=OPEN).
  2. El agente responde con el primer campo pendiente de recoger.
  3. Por cada respuesta del contacto, el agente valida el campo recibido,
     lo persiste en el ticket y avanza al siguiente campo pendiente.
  4. Cuando todos los campos obligatorios estan cubiertos, el agente confirma
     el resumen al contacto y marca el ticket como IN_PROGRESS.
  5. El ticket queda visible en el panel para que el SUPERVISOR lo gestione
     y lo cierre (status=RESOLVED) cuando la averia sea atendida.

Prompt del agente: castellano. Tono profesional y conciso. Sin divagaciones.
El agente NO diagnostica ni da instrucciones tecnicas — solo recoge datos.

Funcion principal en chat/services.py:
  process_breakdown_turn(ticket_pk, user_message) -> str
  Reconstruye el historial, llama a Gemini, persiste el turno MODEL,
  devuelve el texto de respuesta para enviarlo por WhatsApp al contacto.

### 2.6. Infraestructura de tiempo cuasi-real — Polling + Redis

PythonAnywhere no soporta WebSocket ni ASGI. El tiempo real se implementa
mediante polling HTMX desde el panel.

Polling:
  - GET /panel/chat/<room_pk>/messages/?since=<timestamp> cada 4 segundos
    via hx-trigger="every 4s".
  - La vista devuelve solo los mensajes nuevos desde el timestamp dado.
  - HTMX hace swap del fragmento HTML en el contenedor de mensajes.

Redis (instancia externa Redis Labs — misma que CampuStudiOnline, DB separada):
  - Celery usa Redis como broker (ya configurado en EnterpriseBot).
  - Variable de entorno: REDIS_URL (ya existente para Celery).

### 2.7. Vista del panel — sala IRC

URL: GET /panel/chat/<room_pk>/
Vista: ChatRoomView(SupervisorAccessMixin, View)
Acceso: ADMIN, SUPERVISOR, WORKSHOP (todos los roles autenticados).

La vista renderiza:
  - Cabecera con nombre de la sala y seccion asociada.
  - Lista de mensajes del periodo activo (ultimos 7 dias), ordenados por
    created_at ascendente.
  - Input de respuesta con boton Enviar (ADMIN y SUPERVISOR).
    WORKSHOP puede leer pero no responder.
  - Polling HTMX cada 4 segundos al endpoint de mensajes nuevos.
  - Indicador visual de contactos fuera de ventana de 24h.

Navegacion: nueva seccion "Chat de Secciones" en el sidebar del panel,
visible para ADMIN y SUPERVISOR. Lista todas las ChatRoom activas de la
empresa con badge de mensajes no leidos.

### 2.8. Tarea de limpieza — purge_old_chat_messages

Tarea Celery periodica registrada en CELERY_BEAT_SCHEDULE.
Frecuencia: diaria (hora de baja carga).
Logica:
  - Elimina ChatMessage con created_at < now() - timedelta(days=7).
  - Elimina BreakdownConversationTurn de tickets con updated_at
    < now() - timedelta(days=7) y status=RESOLVED.
  - Los BreakdownTicket se conservan indefinidamente.

### 2.9. Comando de gestion — init_chat_rooms

Archivo: chat/management/commands/init_chat_rooms.py
Argumento obligatorio: --company-pk
Logica idempotente:
  - Crea una ChatRoom(room_type=SECTION) por cada Section activa de la
    empresa que no tenga sala creada.
  - Crea la ChatRoom(room_type=BREAKDOWNS) si no existe.
  - No modifica ni elimina salas existentes.

### 2.10. Integracion con el webhook existente del Hito 4

El webhook /api/whatsapp/inbound/ del Hito 4 gestiona actualmente mensajes
de presencia y el chatbot conversacional general.

En este hito se anade logica de despacho en chat/services.py invocada
desde la vista del webhook como primer paso, antes de la logica existente:
  1. Si el contacto pertenece a una seccion → despachar a ChatRoom SECTION.
  2. Si el cuerpo contiene intencion de averia o el contacto tiene ticket
     abierto → despachar a ChatRoom BREAKDOWNS y activar agente Gemini.
  3. En cualquier otro caso → flujo existente del Hito 4 sin modificacion.

---

## 3. Hoja de Ruta

### Paso 1 — Nueva app `chat` y modelos base
Estado: PENDIENTE.
- Crear estructura de directorios de la app chat.
- Definir modelos ChatRoom, ChatMessage, BreakdownTicket,
  BreakdownConversationTurn en chat/models.py.
- Migraciones iniciales.
- Registro en INSTALLED_APPS y admin.

### Paso 2 — Comando init_chat_rooms + inicializacion en produccion
Estado: PENDIENTE.
- Implementar chat/management/commands/init_chat_rooms.py.
- Ejecutar en produccion para Grupo Alvarez.
- Verificar salas creadas correctamente.

### Paso 3 — Vista IRC del panel (solo lectura)
Estado: PENDIENTE.
- ChatRoomView: renderizado de sala con historial ultimos 7 dias.
- ChatMessagesPollingView: GET /panel/chat/<room_pk>/messages/?since=<ts>.
- Navegacion sidebar: seccion "Chat de Secciones".
- Sin envio aun — solo visualizacion de mensajes.

### Paso 4 — Integracion webhook → ChatRoom (entrada WhatsApp)
Estado: PENDIENTE.
- Logica de despacho en chat/services.py.
- Modificacion minima del webhook existente para invocar el despachador.
- Tarea Celery broadcast_inbound_message.
- Validacion E2E: mensaje WhatsApp real aparece en sala del panel.

### Paso 5 — Envio desde el panel → WhatsApp (salida)
Estado: PENDIENTE.
- ChatSendView: POST con creacion ChatMessage OUTBOUND y envio Twilio.
- Broadcast a contactos activos de la seccion (ventana 24h).
- Indicador visual de contactos fuera de ventana.
- Validacion E2E: respuesta del panel llega al WhatsApp del contacto.

### Paso 6 — Sala de Averias y agente Gemini
Estado: PENDIENTE.
- ChatRoom BREAKDOWNS creada por init_chat_rooms.
- process_breakdown_turn en chat/services.py.
- Flujo completo: deteccion intencion → creacion ticket → dialogo campo
  a campo → confirmacion resumen → status IN_PROGRESS.
- BreakdownTicketListView en panel para SUPERVISOR.
- Cierre de ticket desde panel (status RESOLVED).
- Validacion E2E con contacto real via WhatsApp.

### Paso 7 — Tarea de limpieza y ajustes finales
Estado: PENDIENTE.
- purge_old_chat_messages en Celery Beat.
- Badge de mensajes no leidos en sidebar.
- Ajustes UX y pruebas con multiples salas activas.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|------------------|---------|
| 001    | 2026-05-15 | —                | Creacion del anexo. Diseno de arquitectura completo aprobado. Inicio formal del hito. |
