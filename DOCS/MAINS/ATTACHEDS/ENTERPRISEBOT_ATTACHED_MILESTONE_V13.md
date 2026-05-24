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

---

## 2. Nueva Arquitectura Estratégica

### 2.1. Grupos WhatsApp con Bot

Se crean dos grupos WhatsApp reales de menos de 8 miembros, cada uno con el
bot como participante:

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

Flujo conversacional del bot:
  1. Chófer escribe cualquier mensaje al bot → bot detecta intención de avería.
  2. Bot hace las preguntas pertinentes campo a campo:
       - Máquina / Centro de Gasto afectado.
       - Síntoma o descripción de la avería.
       - Ubicación.
       - Urgencia.
  3. Bot confirma los datos con el chófer.
  4. Bot genera la tarjeta de avería y crea el BreakdownTicket en BD.
  5. Bot envía la tarjeta al grupo WhatsApp pertinente (Taller Mecánico o
     Taller Elevación) según el tipo de avería o sección del CdG.

### 2.3. BreakdownTicket

La generación de la tarjeta de avería por el bot crea automáticamente el
BreakdownTicket en BD. Este ticket sigue el ciclo de vida ya implementado
en el Hito 14: asignación a WORKSHOPBOSS, conversión a orden de reparación
y cierre desde el panel.

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
| 17 | Definición de grupos WhatsApp y configuración en .env | PENDIENTE |
| 18 | Flujo conversacional bot 1:1 chófer → avería | PENDIENTE |
| 19 | Generación automática de BreakdownTicket desde conversación bot | PENDIENTE |
| 20 | Entrega de tarjeta de avería al grupo WhatsApp pertinente | PENDIENTE |
| 21 | Validación E2E flujo completo | PENDIENTE |

---

## 5. Hoja de Ruta para la Siguiente Sesión (S040)

### Orden de trabajo S040

PRIORIDAD 0 — Diseño técnico del flujo conversacional bot 1:1:
  Antes de implementar nada, acordar con Miguel Ángel:
    - ¿Cómo detecta el bot que el mensaje 1:1 de un chófer es una avería
      y no otro tipo de mensaje (ayuda, consulta, etc.)?
    - ¿El flujo conversacional de avería es lineal (pregunta a pregunta)
      o puede el chófer enviar toda la información en un solo mensaje?
    - ¿Qué campos son obligatorios para cerrar el ticket y cuáles opcionales?
    - ¿Cómo determina el bot a qué grupo enviar la tarjeta (Taller Mecánico
      o Taller Elevación)? ¿Por familia del CdG, por sección del chófer,
      o por selección explícita del chófer?
    - Formato exacto de la tarjeta de avería que se entrega en el grupo.

  OBLIGATORIO: no implementar el Paso 18 sin haber acordado estas decisiones
  con Miguel Ángel al inicio de la sesión.

PRIORIDAD 1 — Configuración de grupos WhatsApp en .env:
  Definir y añadir al .env las variables:
    WHATSAPP_GROUP_TALLER_MECANICO=whatsapp:+34XXXXXXXXXXX (SID del grupo)
    WHATSAPP_GROUP_TALLER_ELEVACION=whatsapp:+34XXXXXXXXXXX (SID del grupo)
  Verificar que Twilio permite enviar mensajes a grupos WhatsApp desde la API.
  Documentar el procedimiento de alta del bot en cada grupo.

PRIORIDAD 2 — Implementación del flujo conversacional (tras acordar diseño):
  Nueva función en chat/services.py: _handle_driver_breakdown_flow().
  Gestión de estado conversacional por contacto (campo routing_state ya existe).
  Preguntas secuenciales campo a campo con validación de respuesta.
  Confirmación final antes de crear el ticket.
  Creación de BreakdownTicket en BD al confirmar.
  Envío de tarjeta al grupo WhatsApp pertinente.
