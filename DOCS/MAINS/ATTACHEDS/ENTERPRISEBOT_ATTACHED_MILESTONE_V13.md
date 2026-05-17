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

El broadcast actua ademas como mecanismo de onboarding: al enviar el template
chat_onboarding a los contactos de una seccion, el sistema recoge su alias
y provisiona automaticamente su CompanyUser si aun no estaba registrado.

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

#### Modificaciones en ivr_config/models.py (sesion 002-003)

CompanyUser.alias — CharField(max_length=50, blank=True, default="")
  Fuente de verdad del alias para mensajes del panel y onboarding WhatsApp.
  Los roles ADMIN/SUPERVISOR/OPERATOR se asignan via consola.
  Los roles WORKSHOP/DRIVER se asignan automaticamente via onboarding WhatsApp
  segun el campo default_role de la Section.

Contact.alias — CharField(max_length=50, blank=True, default="")
  Usado unicamente para contactos externos sin CompanyUser vinculado.
  Para contactos internos (is_internal=True) el alias canonico es CompanyUser.alias.

Section.default_role — CharField choices: WORKSHOP | DRIVER, default=WORKSHOP
  Rol asignado automaticamente al provisionar un CompanyUser via onboarding WhatsApp.
  Los roles de mayor rango se asignan manualmente via consola de administracion.

#### Funcion de resolucion de alias

chat/services.py — _resolve_alias(contact) -> str
  1. Si contact.company_user_id y contact.company_user → devuelve CompanyUser.alias.
  2. En caso contrario → devuelve Contact.alias.
  Devuelve cadena vacia si no hay alias en ninguna fuente.

### 2.2. Flujo de onboarding WhatsApp — tres pasos

El flujo de recogida de alias esta implementado en chat/services.py como
maquina de estados en memoria (_ALIAS_PENDING: set, _ALIAS_CONFIRMING: dict).

Paso A — contacto escribe por primera vez, sin estado previo:
  El chatbot solicita el nombre con el que quiere aparecer en el grupo.
  Se anade from_number a _ALIAS_PENDING.

Paso B — contacto esta en _ALIAS_PENDING:
  Se interpreta body como el alias propuesto.
  Se pide confirmacion explicando que ese nombre lo identificara en el grupo.
  Se mueve from_number a _ALIAS_CONFIRMING con el alias propuesto.

Paso C — contacto esta en _ALIAS_CONFIRMING:
  Si body es afirmativo (SI/SÍ/S/YES/Y):
    Se llama a _provision_company_user(contact, section, proposed_alias,
    to_number, from_number) — funcion PENDIENTE DE IMPLEMENTAR.
    Se elimina from_number de _ALIAS_CONFIRMING.
    Se envia mensaje de confirmacion final con URL de la plataforma.
  Si body no es afirmativo:
    Se interpreta body como nuevo alias propuesto.
    Se actualiza _ALIAS_CONFIRMING[from_number] con el nuevo alias.
    Se vuelve a pedir confirmacion.

ATENCION: en la sesion 003, el patcher del Paso C introdujo un error de
indentacion en chat/services.py (lineas 404-408). El archivo fue consolidado
con ese error. El backup limpio esta en:
  /home/MiguelAeTxio/SWAP/chat_services.py.bak
La primera accion de la siguiente sesion es restaurar el backup y reimplementar
el Paso C correctamente.

### 2.3. Funcion _provision_company_user — PENDIENTE DE IMPLEMENTAR

Archivo: chat/services.py
Firma: _provision_company_user(contact, section, proposed_alias, to_number, from_number) -> None

Logica completa:
  1. Si contact.company_user ya existe:
     contact.company_user.alias = proposed_alias
     contact.company_user.save(update_fields=["alias"])
     No crear ningun User ni CompanyUser nuevo.
  2. Si contact.company_user es None:
     a. Generar username: slugify(proposed_alias) en minusculas. Si ya existe
        en auth.User, anadir sufijo numerico hasta encontrar uno libre.
     b. Crear User(username=username, password="1234") con set_password("1234").
     c. Crear CompanyUser(
          company=section.company,
          user=user_nuevo,
          role=section.default_role,
          alias=proposed_alias,
          must_change_password=True,
          is_active=True,
        )
     d. Vincular contact.company_user = company_user_nuevo.
        contact.alias = ""  (se deja vacio — el canonico es CompanyUser.alias)
        contact.is_internal = True
        contact.save(update_fields=["company_user", "alias", "is_internal"])
     e. Enviar mensaje WhatsApp al contacto con sus credenciales:
        "✓ Ya estas registrado en la plataforma de Grupo Alvarez.
         Puedes acceder en: https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/login/
         Usuario: {username}
         Contrasena: 1234
         Te pediremos que la cambies en tu primer inicio de sesion."

### 2.4. Template de onboarding — chat_onboarding

SID: HX1a42a1c870b66af03fbc91baf54349b5
Estado: pendiente de aprobacion Meta (WhatsApp business initiated).
Texto:
  "Hola {{1}}, te informamos de que tu numero ha sido registrado en el sistema
   de comunicaciones de {{2}}. Para completar el registro, responde a este
   mensaje indicando tu nombre."
Variables: {{1}} = nombre del contacto, {{2}} = nombre de la empresa.

Una vez aprobado: integrar en ChatSendView para broadcast a contactos sin sesion
activa (fuera de ventana de 24h). El broadcast actual solo llega a contactos
con sesion activa.

### 2.5. Flujo de entrada — WhatsApp → sala IRC

1. Contacto envia mensaje al numero +34607961650.
2. Twilio dispara webhook POST a /api/whatsapp/inbound/.
3. dispatch_inbound_message(company, from_number, body, to_number) es invocado
   como primer paso, antes del pipeline del Hito 4.
4. Si no tiene seccion → flujo Hito 5 (no consumido).
5. Si tiene seccion pero no alias → flujo de onboarding tres pasos (consumido).
6. Si tiene alias → ChatMessage(INBOUND) + broadcast via Celery (consumido).

### 2.6. Flujo de salida — panel → WhatsApp

ChatSendView POST /panel/chat/<room_pk>/send/:
  1. Valida rol (solo ADMIN y SUPERVISOR pueden enviar).
  2. Resuelve alias desde company_user.alias. Si vacio → HTTP 400.
  3. Crea ChatMessage(OUTBOUND) con cuerpo "{alias}: {body}".
  4. Broadcast a todos los contactos de la seccion con phone_number no vacio
     y sesion WhatsApp activa (WhatsAppSession.is_active=True).
  5. Devuelve JSON {ok, message_pk, sent, skipped, out_of_window}.

### 2.7. Infraestructura de tiempo cuasi-real

Polling HTMX cada 3 segundos via hx-trigger="every 3s" en room.html.
El fragmento de mensajes se recarga completo (ultimos 7 dias) en cada poll.
JS del chat en archivo estatico: panel/static/panel/js/chat.js (con defer).
Modal de alias en room.html — se abre automaticamente si alias_required=True.
Z-index del modal: 1070 !important en panel.css.

### 2.8. URLs del modulo chat

/panel/chat/                          — ChatRoomListView (lista de salas)
/panel/chat/<room_pk>/               — ChatRoomView (sala IRC)
/panel/chat/<room_pk>/messages/      — ChatMessagesPollingView (fragmento HTMX)
/panel/chat/<room_pk>/send/          — ChatSendView (envio desde panel)
/panel/chat/alias/set/               — ChatAliasSetView (guardar alias desde modal)

---

## 3. Hoja de Ruta

### Paso 1 — Nueva app chat y modelos base
Estado: COMPLETADO.

### Paso 2 — Comando init_chat_rooms + inicializacion en produccion
Estado: COMPLETADO.
Resultado: 2 salas SECTION + 1 sala BREAKDOWNS para Grupo Alvarez (company_pk=1).

### Paso 3 — Campos alias y default_role + migraciones
Estado: COMPLETADO.
- Contact.alias — migracion aplicada.
- CompanyUser.alias — migracion aplicada.
- Section.default_role (WORKSHOP|DRIVER, default=WORKSHOP) — migracion 0021 aplicada.

### Paso 4 — Vista IRC del panel (lectura + polling)
Estado: COMPLETADO.
- ChatRoomView, ChatMessagesPollingView, ChatRoomListView operativos.
- Sidebar con seccion "Chat de Secciones".
- Polling HTMX cada 3s desde chat.js (defer).
- Modal de alias operativo (z-index corregido en panel.css).

### Paso 5 — Integracion webhook → ChatRoom (entrada WhatsApp)
Estado: COMPLETADO.
- dispatch_inbound_message inyectado en whatsapp/views.py antes del Step 5.
- _resolve_alias implementado.
- purge_old_chat_messages registrado en CELERY_BEAT_SCHEDULE (diaria 03:00).

### Paso 6 — Envio desde panel → WhatsApp (salida con alias)
Estado: COMPLETADO.
- ChatSendView operativo. Alias desde CompanyUser.alias.
- Broadcast a todos los contactos con phone_number y sesion activa.
- ChatAliasSetView operativo. Modal de alias en room.html.

### Paso 7 — Flujo de onboarding WhatsApp (alias tres pasos + provision CompanyUser)
Estado: PARCIALMENTE COMPLETADO — BLOQUEADO POR ERROR EN DISCO.

Completado:
- Maquina de estados _ALIAS_PENDING / _ALIAS_CONFIRMING implementada.
- Pasos A y B del dialogo operativos.
- Section.default_role implementado y migrado.

BLOQUEADO:
- chat/services.py tiene error de indentacion en lineas 404-408 (Paso C).
- _provision_company_user no implementada aun.

PRIMERA ACCION OBLIGATORIA DE LA SIGUIENTE SESION:
1. Restaurar el backup limpio:
   cp /home/MiguelAeTxio/SWAP/chat_services.py.bak \
      /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/services.py
2. Verificar sintaxis:
   python3 -m py_compile /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/services.py
3. Reimplementar el Paso C del flujo de alias con la llamada a _provision_company_user.
4. Implementar _provision_company_user segun la especificacion exacta de la seccion 2.3.

### Paso 8 — Sala de Averias y agente Gemini
Estado: PENDIENTE.
- process_breakdown_turn en chat/services.py.
- BreakdownTicketListView en panel para SUPERVISOR.
- Cierre de ticket desde panel (status RESOLVED).

### Paso 9 — Template chat_onboarding + broadcast a contactos sin sesion
Estado: PENDIENTE — esperando aprobacion Meta.
- SID: HX1a42a1c870b66af03fbc91baf54349b5
- Integrar en ChatSendView para broadcast a contactos fuera de ventana 24h.

### Paso 10 — Tarea de limpieza y ajustes finales
Estado: PENDIENTE.
- Badge de mensajes no leidos en sidebar.
- Ajustes UX y pruebas con multiples salas activas.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|------------------|---------|
| 001    | 2026-05-15 | —                | Creacion del anexo. Diseno de arquitectura completo aprobado. Inicio formal del hito. |
| 002    | 2026-05-15 | Pasos 1, 2 y arq | App chat creada, modelos migrados, init_chat_rooms ejecutado. Arquitectura revisada: alias, broadcast, polling HTMX 3s. |
| 003    | 2026-05-16 | Pasos 3-7 parcial | CompanyUser.alias, Section.default_role, ChatSendView, ChatAliasSetView, modal alias, chat.js estatico, onboarding tres pasos. Error de indentacion en chat/services.py lineas 404-408 — archivo en disco ROTO. Backup limpio en SWAP. |
