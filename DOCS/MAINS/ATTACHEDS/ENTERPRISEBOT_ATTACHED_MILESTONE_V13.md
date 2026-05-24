# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md

# ENTERPRISEBOT — ANEXO HITO 13
## Salas de Chat IRC por Sección (WhatsApp → Panel) — REDISEÑO ESTRATÉGICO S040

---

## 1. Contexto del Rediseño

El planteamiento original del Hito 13 (salas IRC por sección con polling HTMX,
replicación de mensajes WhatsApp en el panel y agente Gemini en sala BREAKDOWNS)
quedó completado en S009 (2026-05-21) y promovido parcialmente al Hito 14.

En la sesión S039 (2026-05-23) se acordó un cambio estratégico completo en el
modelo de gestión de averías y comunicación por WhatsApp. El nuevo enfoque
elimina la sala BREAKDOWNS como canal de entrada y redefine el rol del bot.

En la sesión S040 (2026-05-24) se acordó adicionalmente la migración completa
del canal WhatsApp de Twilio a Meta Cloud API directa, y se diseñó e implementó
la infraestructura base del sistema de gestión del bot en el panel.

---

## 2. Nueva Arquitectura Estratégica

### 2.1. Grupos WhatsApp con Bot

Se crean dos grupos WhatsApp reales de menos de 8 miembros (máximo 8 incluyendo
el bot, según límite de la Groups API de Meta), cada uno con el bot como
participante administrador:

  - Grupo Taller Mecánico: mecánicos de la sección de mecánica + bot.
  - Grupo Taller Elevación: mecánicos de la sección de elevación + bot.

El bot participa en estos grupos únicamente como receptor de la tarjeta de
avería generada — no gestiona conversaciones en el grupo. Los mecánicos se
comunican directamente entre ellos y con el chófer sin intervención del bot.

Sin restricción de ventana de 24h en grupos: el bot puede entregar tarjetas
en cualquier momento independientemente de la actividad del grupo.

### 2.2. Flujo de Avería 1:1 Chófer → Bot

Los chóferes reportan averías enviando un mensaje directo (1:1) al bot de
WhatsApp. El chófer siempre inicia la conversación, por lo que no existe
restricción de ventana de 24h.

Flujo conversacional del bot (ESTRICTAMENTE SECUENCIAL — campo a campo):
  1. Cualquier mensaje entrante de cualquier miembro del Grupo Álvarez →
     bot responde que el canal es exclusivo de averías y ofrece abrir ticket
     con reply buttons: [1 - Sí] [2 - No].
  2. Si Sí → bot pregunta máquina / centro de gasto afectado (texto libre).
  3. Bot instruye al chófer a describir la avería con detalle: elemento
     afectado + posición exacta (ej: "gato hidráulico trasero izquierdo").
  4. Bot pregunta: ¿puede el vehículo llegar al taller?
     Reply buttons: [Sí] [No].
     - Si No → bot solicita ubicación exacta (texto libre).
  5. Bot pregunta urgencia con lista numerada (4 opciones — supera límite
     de 3 botones de WhatsApp, se envía como texto):
       1. El vehículo funciona pero con alguna limitación → LOW
       2. El vehículo está parado pero la faena continúa → MEDIUM
       3. La faena está parada por esta avería → HIGH
       4. Hay riesgo para personas o para la máquina → CRITICAL
  6. Bot resume todos los datos y pide confirmación: [Sí, confirmar] [No, corregir].
  7. Al confirmar → bot crea BreakdownTicket en BD y envía tarjeta al grupo
     de taller pertinente vía Meta Cloud API Groups API.

### 2.3. BreakdownTicket

La generación de la tarjeta de avería por el bot crea automáticamente el
BreakdownTicket en BD. Este ticket sigue el ciclo de vida ya implementado
en el Hito 14: asignación a WORKSHOPBOSS, conversión a orden de reparación
y cierre desde el panel.

### 2.4. Routing al Grupo de Taller

El routing es automático por familia del catálogo de MachineAsset, configurable
desde Django Admin sin cambios de código mediante el modelo WorkshopFamilyMapping
(implementado en S040). El campo MachineAsset.family determina el grupo destino.
Fallback: MECHANICAL si la familia no está mapeada.

Los WORKSHOPBOSS pueden aceptar o redirigir tickets desde el panel si el routing
automático fue incorrecto.

### 2.5. Formato de Tarjeta de Avería (grupo WhatsApp)

  🔧 NUEVA AVERÍA — #EB-{id}

  🚗 Máquina: {nombre del CostCenter}
  📋 Descripción: {síntoma}
  📍 Ubicación: {taller / ubicación exacta}
  ⚡ Urgencia: {nivel con texto}
  👤 Reportado por: {alias del chófer}
  🕐 Hora: {timestamp}

### 2.6. Arquitectura WhatsApp — Migración a Meta Cloud API Directa

En S040 se acordó y documentó la migración completa del canal WhatsApp de
Twilio a Meta Cloud API directa:

  - Twilio NO soporta la Groups API de WhatsApp — incompatible con el Paso 20.
  - Meta Cloud API directa soporta grupos nativos, reply buttons en 1:1,
    y acceso prioritario a nuevas funcionalidades.
  - Twilio se mantiene exclusivamente para telefonía/IVR (voz).
  - La refactorización de whatsapp/services.py se realiza en S041.

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

## 4. Pasos Nuevos — Rediseño S040+

| Paso | Descripción | Estado |
|------|-------------|--------|
| 17a | CompanyUser.workshop_family + WorkshopFamilyMapping + migración 0027 | COMPLETADO S040 |
| 17b | WorkshopFamilyMappingAdmin en ivr_config/admin.py | COMPLETADO S040 |
| 17c | BotManagementView en panel/views.py + urls.py + sidebar | COMPLETADO S040 |
| 17d | Template panel/bot/dashboard.html | COMPLETADO S040 |
| 17e | Migración completa WhatsApp Twilio → Meta Cloud API directa | PENDIENTE |
| 17f | Configuración grupos de taller vía Groups API de Meta | PENDIENTE |
| 18 | Flujo conversacional bot 1:1 chófer → avería en chat/services.py | PENDIENTE |
| 19 | Generación automática de BreakdownTicket desde conversación bot | PENDIENTE |
| 20 | Entrega de tarjeta de avería al grupo WhatsApp pertinente | PENDIENTE |
| 21 | Validación E2E flujo completo | PENDIENTE |

---

## 5. Modelos Relevantes — Estado S040

### CompanyUser (ivr_config/models.py)
Campo añadido en S040:

  WORKSHOP_FAMILY_MECHANICAL = "MECHANICAL"
  WORKSHOP_FAMILY_ELEVATION  = "ELEVATION"
  WORKSHOP_FAMILY_CHOICES = [
      (WORKSHOP_FAMILY_MECHANICAL, "Taller Mecánico"),
      (WORKSHOP_FAMILY_ELEVATION,  "Taller Elevación"),
  ]
  workshop_family = models.CharField(
      max_length=20, choices=WORKSHOP_FAMILY_CHOICES,
      null=True, blank=True
  )

Solo relevante para rol WORKSHOPBOSS.

### WorkshopFamilyMapping (ivr_config/models.py) — NUEVO S040
Mapea MachineAsset.family (string del catálogo) a MECHANICAL/ELEVATION.
Configurable desde Django Admin sin cambios de código.
Campos: company (FK), catalogue_family (CharField), workshop_family (choices),
notes (CharField blank), created_at, updated_at.
unique_together: (company, catalogue_family).

### BreakdownTicket (chat/models.py) — SIN CAMBIOS
Campos relevantes para el visor: room (FK→ChatRoom→company), machine (FK),
contact (FK), assigned_to (FK), fault_summary, urgency, status.
Estados: STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_RESOLVED.
NO tiene campo company directo — filtrar siempre por room__company.

---

## 6. Vista BotManagementView — Arquitectura S040

Ubicación: panel/views.py
Hereda de: CompanyUserRequiredMixin, View
URL: /panel/bot/ (name="bot_management")
Template: panel/templates/panel/bot/dashboard.html

Bloques funcionales:
  - Bloque 1: Onboarding por sección (solo ADMIN) — selector de Section
    sin filtro is_active (todas las secciones de la empresa).
  - Bloque 2: Circular a grupos WhatsApp (solo ADMIN) — pendiente implementación POST.
  - Bloque 3: Circular 1:1 (solo ADMIN) — pendiente implementación POST.
  - Bloque 4: Visor de averías — visible para ADMIN, SUPERVISOR, WORKSHOPBOSS, WORKSHOP.

Lógica de visibilidad del visor por rol:
  - ADMIN/SUPERVISOR: ven todos los tickets, selector de familia por GET param.
  - WORKSHOPBOSS: ve solo su workshop_family.
  - WORKSHOP: hereda familia del WORKSHOPBOSS de su sección (cadena
    SectionContact → Section → WORKSHOPBOSS → workshop_family).

Routing del visor: WorkshopFamilyMapping.objects.filter(company, workshop_family)
→ lista de catalogue_family → filtro machine__family__in.

---

## 7. Hoja de Ruta para la Siguiente Sesión (S041)

### PRIORIDAD 0 — Configuración inicial en Django Admin (obligatorio antes de S041)
Miguel Ángel debe configurar antes de S041:
  a. En Django Admin → WorkshopFamilyMapping: crear los mapeos de familias
     del catálogo (PLATAFOR, CARR → ELEVATION; MOVILES, AUTOCARG, REMOLQUE,
     TTE. → MECHANICAL).
  b. En Django Admin → CompanyUser: asignar workshop_family a los WORKSHOPBOSS
     existentes (Taller Mecánico → MECHANICAL, Taller Elevación → ELEVATION).

### PRIORIDAD 1 — Migración WhatsApp Twilio → Meta Cloud API (Paso 17e)

#### 1.1. Actualización online obligatoria (Directriz 4.4)
Antes de implementar, actualizar en línea:
  - Meta Cloud API: endpoint de mensajes, autenticación (META_WHATSAPP_TOKEN,
    META_PHONE_NUMBER_ID), formato de payload para reply buttons,
    mensajes de texto y mensajes a grupos.
  - Groups API: endpoint de creación de grupo, añadir participantes,
    envío de mensajes a group_id.

#### 1.2. Variables de entorno a añadir al .env
  META_WHATSAPP_TOKEN=<token permanente de sistema de Meta>
  META_PHONE_NUMBER_ID=<ID del número en Meta>
  META_WABA_ID=<WhatsApp Business Account ID>
  META_VERIFY_TOKEN=<token de verificación del webhook>
  WHATSAPP_GROUP_TALLER_MECANICO=<group_id del grupo Taller Mecánico>
  WHATSAPP_GROUP_TALLER_ELEVACION=<group_id del grupo Taller Elevación>

#### 1.3. Refactorización whatsapp/services.py
Eliminar toda dependencia de Twilio para mensajería WhatsApp.
Implementar cliente Meta Cloud API directa:
  - send_whatsapp_message(to, text) → POST a /messages con type="text".
  - send_whatsapp_reply_buttons(to, body, buttons) → type="interactive",
    interactive.type="button", máximo 3 botones.
  - send_whatsapp_list_message(to, body, items) → type="interactive",
    interactive.type="list" para listas de más de 3 opciones (urgencia).
  - send_whatsapp_group_message(group_id, text) → POST a /messages con
    to=group_id.
Mantener Twilio exclusivamente para telefonía (voz/IVR) — no tocar vox_bridge.

#### 1.4. Refactorización del webhook
El webhook de entrada de mensajes WhatsApp actualmente procesa el formato
de Twilio. Debe adaptarse al formato de payload de Meta Cloud API:
  - Verificación del webhook con META_VERIFY_TOKEN (GET challenge).
  - Procesamiento del payload Meta (POST): extraer from, body, type,
    interactive.button_reply.id para reply buttons.
  - Mantener compatibilidad con el routing_state del Contact existente.

### PRIORIDAD 2 — Creación de grupos de taller vía Groups API (Paso 17f)
Tras implementar el cliente Meta Cloud API:
  - Documentar el procedimiento de creación de grupos vía API.
  - Registrar los group_id obtenidos en el .env.
  - Verificar que el bot puede enviar mensajes a los grupos.

### PRIORIDAD 3 — Flujo conversacional bot 1:1 (Paso 18)
Implementar _handle_driver_breakdown_flow() en chat/services.py.
El flujo usa el campo routing_state del modelo Contact para gestionar
el estado conversacional por contacto.

Estados del flujo (routing_state values):
  - "idle" → cualquier mensaje → respuesta exclusivo averías + reply buttons Sí/No.
  - "breakdown_confirm" → espera Sí/No.
  - "breakdown_machine" → espera nombre de máquina/CdG.
  - "breakdown_description" → espera descripción detallada.
  - "breakdown_can_move" → espera Sí/No (¿puede llegar al taller?).
  - "breakdown_location" → espera ubicación (solo si no puede llegar).
  - "breakdown_urgency" → espera número 1-4.
  - "breakdown_review" → espera confirmación final Sí/No.

Datos parciales del ticket se acumulan en un campo JSON del Contact
(verificar Contact.metadata o similar en S041 — añadir si no existe).

### PRIORIDAD 4 — Generación de BreakdownTicket y entrega de tarjeta (Pasos 19-20)
Al confirmar el chófer:
  - Crear BreakdownTicket en BD con todos los campos recopilados.
  - Resolver routing: MachineAsset.family → WorkshopFamilyMapping →
    workshop_family → group_id del .env.
  - Enviar tarjeta formateada al grupo vía send_whatsapp_group_message().
  - Resetear routing_state del Contact a "idle".

### PRIORIDAD 5 — Validación E2E (Paso 21)
Prueba completa del flujo: mensaje 1:1 chófer → conversación secuencial →
BreakdownTicket en BD → tarjeta en grupo → visor en panel.
