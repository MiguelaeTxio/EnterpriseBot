# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md

# ENTERPRISEBOT — ANEXO HITO 14
## Gestión de Tickets de Avería y Órdenes de Reparación

---

## Estado de Pasos

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Auditoría flujo creación automática `BreakdownTicket` desde BREAKDOWNS | COMPLETADO |
| 2 | Campo `assigned_to` en `BreakdownTicket` + migración (`priority` cubierto por `urgency`) | COMPLETADO |
| 3 | `BreakdownTicketCreateView` + formulario + URL + botón en listado | COMPLETADO |
| 4 | Ciclo de vida: asignación, conversión a OT, urgencia inline, cierre | COMPLETADO |
| 5 | Integración formulario de parte de operario con órdenes de reparación | COMPLETADO |
| 6 | `OwnProfileView` — edición de alias de chat desde el panel | COMPLETADO |
| 7 | Gestión sala BREAKDOWNS: todas las secciones (sin filtro `is_active`) | COMPLETADO |
| 8 | Sincronización automática de contactos al añadir/quitar sección BREAKDOWNS | COMPLETADO |
| 9 | Color diferencial rojo/naranja en secciones completas/incompletas | COMPLETADO |
| 10 | Panel lateral de miembros en salas de sección y sala BREAKDOWNS | COMPLETADO |
| 11 | Botón Gestionar membresía de Averías en lista de salas (solo ADMIN) | COMPLETADO |

---

## Arquitectura Técnica

### Contexto

Este hito nace de la promoción de la hoja de ruta de S010 del Hito 13.
El modelo `BreakdownTicket` y la infraestructura de salas BREAKDOWNS
están completamente operativos desde S009. Este hito extiende y completa
el ciclo de vida del ticket sin modificar la arquitectura de chat.

### Modelo `BreakdownTicket` — Estado actual conocido

Campos confirmados en S009:
- `room` (FK `ChatRoom`)
- `contact` (FK `Contact`)
- `machine` (FK `MachineAsset`)
- `section` (FK `Section`)
- `status` — valores actuales por confirmar en auditoría (Paso 1)
- `is_repair_order` (BooleanField)
- `resolved_by` (FK `CompanyUser` nullable)
- `created_at`, `updated_at`

Campos a añadir en Paso 2 (si no existen):
- `assigned_to` (FK `CompanyUser` nullable, related_name `assigned_tickets`)
- `priority` — choices: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`

### Paso 1 — Auditoría flujo creación automática desde BREAKDOWNS

Verificar en `chat/signals.py`, `chat/tasks.py` y `whatsapp/services.py`:
- Qué componente crea el `BreakdownTicket` al detectar el patrón de avería
  en un mensaje entrante de WhatsApp a la sala BREAKDOWNS.
- Qué campos se rellenan automáticamente (`contact`, `machine`, `section`).
- Qué valor de `status` se asigna al ticket recién creado.
- Si existe notificación al `WORKSHOPBOSS` (WhatsApp o panel) en la creación.

### Paso 2 — Campos `assigned_to` y `priority`

- Verificar existencia de ambos campos en `chat/models.py` antes de crear migración.
- Si no existen: añadir al modelo y generar migración con nombre descriptivo.
- `assigned_to`: `ForeignKey('ivr_config.CompanyUser', null=True, blank=True, on_delete=SET_NULL, related_name='assigned_tickets')`.
- `priority`: `CharField(max_length=10, choices=[('LOW','Baja'),('MEDIUM','Media'),('HIGH','Alta'),('CRITICAL','Crítica')], default='MEDIUM')`.

### Paso 3 — `BreakdownTicketCreateView`

- Vista basada en clase, mixin `SupervisorAccessMixin` (ADMIN, SUPERVISOR, WORKSHOPBOSS).
- Formulario Django con campos: `contact`, `machine`, `section`, descripción inicial.
- `contact` filtrado por empresa del usuario autenticado.
- `machine` filtrado por activos (`is_active=True`) de la empresa.
- `section` filtrada por secciones activas de la empresa.
- URL: `panel/chat/breakdowns/tickets/create/` — nombre `panel:breakdown_ticket_create`.
- Botón "Nuevo ticket de avería" en `breakdown_ticket_list.html` visible para
  ADMIN, SUPERVISOR y WORKSHOPBOSS.
- Tras creación exitosa: redirección a `panel:breakdown_ticket_detail`.

### Paso 4 — Ciclo de vida del ticket

Acciones en `BreakdownTicketDetailView` a revisar y completar:
- **Asignar**: acción `assign` — asigna `assigned_to` a un WORKSHOPBOSS concreto
  de la empresa. Solo ADMIN y SUPERVISOR pueden asignar.
- **Conversión a OT**: acción `convert_repair` — activa `is_repair_order=True`
  y actualiza `status` a valor apropiado. Revisar implementación actual.
- **Cierre**: acción `close` — marca `resolved_by` con el usuario autenticado
  y actualiza `status` a cerrado. Revisar implementación actual.
- **Prioridad**: campo editable inline desde el detalle del ticket para ADMIN,
  SUPERVISOR y WORKSHOPBOSS.

### Paso 5 — Integración formulario de parte de operario

En `OperatorDashboardView` y template `operator/form_entry.html`:
- Nuevo desplegable "Orden de reparación" (opcional) que muestre:
  - `BreakdownTicket` con `is_repair_order=True` y `status` abierto,
    sin `assigned_to` (disponibles para cualquier operario de la empresa).
  - `BreakdownTicket` con `is_repair_order=True` asignados al operario
    autenticado (`assigned_to=company_user`), con badge de `priority`.
- Al seleccionar una OT: prerelleno automático de `machine`, `section`
  y descripción del parte vía atributos `data-*` en las opciones del
  desplegable (sin fetch adicional, datos embebidos en el HTML).
- El desplegable es opcional: si no se selecciona ninguna OT, el parte
  se crea normalmente sin vinculación.

### Paso 6 — `OwnProfileView`

- Vista accesible para todos los roles con acceso al panel.
- Formulario con campo `alias` editable.
- Validación de unicidad de `alias` dentro de la empresa del usuario.
- URL: `panel/profile/` — nombre `panel:own_profile`.
- Entrada en sidebar bajo nueva sección "Mi perfil", visible para todos los roles.
- Los mensajes históricos de `ChatMessage` mantienen el `sender_alias` con el que
  fueron enviados (snapshot inmutable). El nuevo alias aplica solo a mensajes futuros.

---

## Archivos Previstos

- `chat/models.py` — campos `assigned_to` y `priority` (Paso 2)
- `chat/migrations/XXXX_breakdownticket_assigned_priority.py` — migración (Paso 2)
- `chat/views.py` — `BreakdownTicketCreateView` + acciones ciclo de vida (Pasos 3 y 4)
- `chat/urls.py` — URL `breakdown_ticket_create` (Paso 3)
- `panel/views.py` — `OwnProfileView` (Paso 6)
- `panel/urls.py` — URL `own_profile` (Paso 6)
- `panel/forms.py` — formulario `OwnProfileForm` (Paso 6)
- `panel/templates/panel/chat/breakdown_ticket_list.html` — botón Nuevo ticket (Paso 3)
- `panel/templates/panel/chat/breakdown_ticket_detail.html` — acciones ciclo de vida (Paso 4)
- `panel/templates/panel/chat/breakdown_ticket_form.html` — Neonato Puro (Paso 3)
- `panel/templates/panel/operator/form_entry.html` — desplegable OT (Paso 5)
- `panel/templates/panel/profile/own_profile.html` — Neonato Puro (Paso 6)
- `panel/templates/panel/_nav_items.html` — sección "Mi perfil" (Paso 6)

---

## Nota de Cierre S010

Arquitectura real implementada en S010 (2026-05-21):

- `assigned_to` añadido al modelo `BreakdownTicket`. El campo `priority` del anexo
  fue cubierto por el campo `urgency` ya existente (choices idénticos: LOW/MEDIUM/HIGH/CRITICAL).
  No se creó campo duplicado.
- Acciones POST de `BreakdownTicketDetailView`: `convert_repair` (pasa a IN_PROGRESS si OPEN),
  `assign` (solo ADMIN/SUPERVISOR), `set_urgency`, `close`.
- `_get_context_base` de `WorkOrderEntryFormView` enriquecido con `repair_orders` (OTs abiertas
  disponibles para el operario autenticado — sin `assigned_to` o asignadas a él).
- Gestión sala BREAKDOWNS: filtro `is_active` eliminado — todas las secciones de la empresa
  aparecen independientemente de su estado en el IVR.
- Color diferencial en secciones: rojo (completa) / naranja (incompleta: algún miembro excluido
  individualmente) / verde Añadir (no añadida).

---

## Nota de Cierre S010 (continuación)

Trabajo adicional completado en la misma sesión S010:

- Sincronización automática de contactos: al añadir una sección a BREAKDOWNS,
  todos sus contactos con teléfono se añaden automáticamente a `breakdown_contacts`.
  Al quitar una sección, sus contactos se eliminan salvo que pertenezcan a otra
  sección restante.
- Color diferencial en botones de sección: rojo (completa) / naranja (incompleta).
  Una sección es incompleta cuando alguno de sus contactos ha sido excluido
  individualmente de `breakdown_contacts`.
- Panel lateral de miembros refactorizado: para salas SECTION busca desde
  `Contact.sections` M2M; para sala BREAKDOWNS construye la lista desde
  `breakdown_sections` y `breakdown_contacts`. Template `room.html` actualizado
  para usar `member.display` en lugar de `member.alias|default:member.user.username`.
- Botón "Gestionar membresía de Averías" añadido en `room_list.html` bajo la
  tarjeta de la sala BREAKDOWNS, visible exclusivamente para el rol ADMIN.

## Hito 14 completado en S010 (2026-05-21). Sin hoja de ruta para sesión siguiente.
