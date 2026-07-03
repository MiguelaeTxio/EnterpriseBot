---

## 1. Título

**Hito 14 — Gestión de Tickets de Avería y Órdenes de Reparación**

Estado: **PAUSADO** (trabajo en curso — nuevas fases previstas)

---

## 2. Descripción

Módulo de gestión manual de tickets de avería desde el panel y su
ciclo de vida como órdenes de reparación. Incluye la creación manual
desde el panel (CRUD), el ciclo de vida completo (asignación, conversión
a OT, urgencia, cierre), la integración con los partes digitales del
operario, y la futura entrada automática vía WhatsApp.

---

## 3. Arquitectura Técnica

### Modelo `BreakdownTicket` — Estado tras S050

Campos confirmados:
- `room` (FK `ChatRoom`)
- `contact` (FK `Contact`)
- `machine` (FK `MachineAsset`, nullable)
- `machine_raw` (CharField — código raw tal como lo reportó el contacto)
- `fault_summary` (CharField)
- `location` (CharField)
- `section` (FK `Section`, nullable)
- `status` — choices: OPEN, IN_PROGRESS, PAUSED, CLOSED
- `origin` — choices: MANUAL, CHATBOT
- `urgency` — choices: LOW/MEDIUM/HIGH/CRITICAL
- `ticket_date_code` (CharField, formato YYYYMMDD-NN, asignado en `save()`)
- `fault_category` (CharField, nullable)
- `paused_at` (DateTimeField, nullable)
- `reported_by` (CharField, nullable)
- `resolved_by` (FK `CompanyUser`, nullable)
- `assigned_to` (FK `CompanyUser`, nullable)
- `created_at`, `updated_at`
- Eliminados: `is_repair_order`, `ticket_number`
- Migración aplicada: `chat/0004`

### Modelo `BreakdownConversationTurn`

Turnos de conversación Gemini asociados al ticket:
- `ticket` (FK `BreakdownTicket`)
- `role` — ROLE_USER / ROLE_MODEL
- `content` (TextField)
- `created_at`

### Vistas — chat/views_tickets.py (split de chat/views.py)

- `BreakdownTicketListView` — dashboard 3 paneles (igual que analytics_lab):
  - Panel top: CRUD con filtros por estado
  - Panel bottom-left: operarios con estado activo/libre
  - Panel bottom-right: tickets OPEN/PAUSED/IN_PROGRESS asignables
  - Drag & Drop operario → ticket → modal confirmación → POST action=assign
  - Divisor arrastrable idéntico a analytics_lab
  - Contexto: `operators` (WORKSHOPBOSS activos), `assignable_tickets`, `STATUS_CHOICES`
- `BreakdownTicketDetailView` — detalle con acciones POST:
  - `assign` — asigna operario, pausa OT previa automáticamente
  - `self_assign` — autoasignación
  - `pause` — pausa ticket, libera operario
  - `close` — cierre con resolved_by y resolved_at
- `BreakdownTicketCreateView` — creación manual desde panel

### Canal WhatsApp BREAKDOWNS — chat/services.py

- `dispatch_inbound_message` — Rule 5b excluye contactos internos (`is_internal=True`);
  solo externos (choferes) reciben el Quick Reply de avería
- `_handle_breakdown_confirm` — envía Quick Reply y guarda `routing_state=AWAITING_BREAKDOWN_CONFIRM`
- `_resolve_breakdown_confirm` — procesa respuesta Sí/No con detección robusta
  (unicodedata NFD, startswith "si,", "si ")
- `process_breakdown_turn` — agente Gemini sin catálogo; valida máquina server-side
  via `_normalise_machine_code` + `_resolve_machine_asset`
- `_dispatch_breakdown_card` — notifica sala Taller/Elevación:
  - Enrutamiento por `machine.family`: PLATAFOR → Elevación, resto → Taller Mecánico
  - Persiste tarjeta OUTBOUND en sala IRC
  - Respeta ventana 24h: sesión activa → `send_reply`; inactiva → `send_template`
    (chat_session_renewal) + encola en `WhatsAppSession.pending_broadcast_messages`

### Resolución de máquina en views_operator.py

Pasadas 1-4 para resolver `machine_raw` incluso cuando el input contiene
el label completo (`"B43 — PALFINGER PK 72002"`):
- Pasada 1: `code__iexact=machine_raw`
- Pasada 2: `code__iexact=_normalise_machine_code(machine_raw)`
- Pasada 3: extrae código antes de ` — ` con regex, reintenta pasadas 1-2
- Pasada 4: `brand_model__iexact` / `brand_model__icontains`

---

## 4. Funcionalidades Completadas

| Paso | Descripción | Sesión |
|------|-------------|--------|
| 1 | Auditoría flujo creación automática `BreakdownTicket` desde BREAKDOWNS | S010 |
| 2 | Campo `assigned_to` en `BreakdownTicket` + migración (`priority` cubierto por `urgency`) | S010 |
| 3 | `BreakdownTicketCreateView` + formulario + URL + botón en listado | S010 |
| 4 | Ciclo de vida: asignación, conversión a OT, urgencia inline, cierre | S010 |
| 5 | Integración formulario de parte de operario con órdenes de reparación | S010 |
| 6 | `OwnProfileView` — edición de alias de chat desde el panel | S010 |
| 7 | Gestión sala BREAKDOWNS: todas las secciones (sin filtro `is_active`) | S010 |
| 8 | Sincronización automática de contactos al añadir/quitar sección BREAKDOWNS | S010 |
| 9 | Color diferencial rojo/naranja en secciones completas/incompletas | S010 |
| 10 | Panel lateral de miembros en salas de sección y sala BREAKDOWNS | S010 |
| 11 | Botón Gestionar membresía de Averías en lista de salas (solo ADMIN) | S010 |
| 12 | Fix I-BUG-A: `asset_code` → `code` en `BreakdownTicketCreateView` | S050 |
| 13 | Split `chat/views.py` → `chat/views_tickets.py` | S050 |
| 14 | Rediseño modelo `BreakdownTicket`: STATUS_PAUSED/CLOSED, `ticket_date_code`, `origin`, `fault_category`, `paused_at`, `reported_by`; eliminados `is_repair_order`, `ticket_number`; migración 0004 aplicada | S050 |
| 15 | Dashboard 3 paneles `breakdown_ticket_list.html` (igual que analytics_lab): CRUD top, operarios bottom-left, tickets asignables bottom-right, drag & drop, divisor arrastrable | S050 |
| 16 | Canal WhatsApp BREAKDOWNS operativo: Quick Reply → agente Gemini → ticket creado con `origin=CHATBOT` | S050 |
| 17 | `_dispatch_breakdown_card`: enrutamiento por familia (PLATAFOR→Elevación, resto→Taller Mecánico), ventana 24h (send_reply / renewal + pending_broadcast_messages) | S050 |
| 18 | Rule 5b: contactos internos (`is_internal=True`) nunca reciben Quick Reply de avería | S050 |
| 19 | `views_operator.py`: pasadas 3-4 para resolver máquina desde label completo | S050 |
| 20 | Fix autocomplete `form_entry_assets.js`: input muestra label completo; servidor resuelve por código o brand_model | S050 |

---

## 5. Incidencias Activas

Sin incidencias activas.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Resumen |
|--------|-------|---------|
| S010 | 2026-05-21 | Implementación completa de los pasos 1-11 originales del hito. Arquitectura base de BreakdownTicket operativa. |
| S050 | 2026-06-18 | Fix I-BUG-A. Split views. Rediseño modelo (ticket_date_code, origin, PAUSED/CLOSED). Dashboard 3 paneles. Canal WhatsApp BREAKDOWNS operativo de punta a punta: Quick Reply → Gemini → ticket creado → tarjeta al Taller con ventana 24h. Fixes autocomplete partes (regresión H07). Rule 5b: internos no reciben Quick Reply. |
| S051 | 2026-06-18 | Paso 21: panel operarios vacío — fix views_tickets.py ampliando role__in=[ROLE_WORKSHOP, ROLE_WORKSHOPBOSS] en operators_qs y acción assign. Paso 22: jerarquía visual sidebar — reglas CSS sidebar-accordion-toggle y sidebar-accordion-body. Desvíos: fix STATUS_RESOLVED→STATUS_CLOSED en analytics/views.py y purge task; send_template añadido a WhatsAppChatService; fix lunch_window time→minutes en views_operator.py; selector 1:1 bot dashboard secciones→usuarios; opt_out_broadcast alvarez_admin False; sección Taller Huelva + usuarios Carlos Bas y David Contreras; PVR bloqueante en com-file-request. |
| S014 | 2026-06-20 | Paso 23 completado: migración chat/0006 (fault_location, geo_lat, geo_lng, location_warning en BreakdownTicket). Rediseño arquitectónico completo acordado: toda comunicación interna es avería, se eliminan ChatRoom y lógica de salas, se unifica IVR+WA en un motor de averías único con log de conversación en ticket. H14 queda absorbido por H17 (Unificación IVR+WA — Motor de Averías y Log de Conversaciones). H14 PAUSADO. |

---

## 7. Hoja de Ruta para la Siguiente Sesión

### Contexto — H14 PAUSADO

H14 queda pausado tras S014. La arquitectura de averías ha sido
rediseñada completamente en S014 y el trabajo restante se continúa
en **H17 (Unificación IVR+WA — Motor de Averías y Log de Conversaciones)**.

Los pasos 24-27 definidos anteriormente han sido absorbidos por H17
con la arquitectura actualizada. El modelo `BreakdownTicket` y la
migración `chat/0006` (fault_location, geo_lat, geo_lng, location_warning)
son la base sobre la que construye H17.

**No hay pasos pendientes en H14.** Todo el trabajo futuro de averías
se ejecuta en H17.
