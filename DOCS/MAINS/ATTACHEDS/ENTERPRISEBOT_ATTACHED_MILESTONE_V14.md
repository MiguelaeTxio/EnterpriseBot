---
name: enterprisebot-annex-v14
description: "Anexo del Hito 14 de EnterpriseBot (Gestión de Tickets de Avería y Órdenes de Reparación). Contiene el historial de sesiones y la arquitectura del módulo: BreakdownTicket, ciclo de vida, integración con partes digitales del operario, CRUD manual desde el panel y futura entrada vía WhatsApp. Activar cuando el enrutador indique que el Hito 14 está EN PROGRESO, o cuando se necesite consultar BreakdownTicket, BreakdownTicketCreateView, BreakdownTicketDetailView, breakdown_ticket_list.html, breakdown_ticket_detail.html, o el flujo de órdenes de reparación."
---

# ENTERPRISEBOT — ANEXO HITO 14
## Gestión de Tickets de Avería y Órdenes de Reparación

---

## PARTE 1 — COMPORTAMIENTO DE LA SKILL

### RUTA EN PYTHONANYWHERE

```
/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md
```

### ACTIVACIÓN

Esta skill se activa en dos casos:

1. **El enrutador de anexos** indica que el Hito 14 está EN PROGRESO.
2. **Cualquier skill o sesión** necesita consultar la arquitectura de
   `BreakdownTicket`, `BreakdownTicketCreateView`, `BreakdownTicketDetailView`,
   el flujo de órdenes de reparación o la integración con partes digitales.

### PROTOCOLO DE CIERRE — LO QUE HACE ESTA SKILL AL SER INVOCADA POR PCS

Al cierre de sesión, si se ha trabajado en este hito:

#### PASO 1 — Redactar el registro de sesión

Nueva fila en la tabla `## 7. Registro de Sesiones`.

#### PASO 2 — Actualizar la Hoja de Ruta

Reescribir la sección `## 8. Hoja de Ruta para la Siguiente Sesión`.

#### PASO 3 — Reescribir el SKILL.md completo

```
/home/claude/skills/enterprisebot-annex-v14/SKILL.md
```

#### PASO 4 — Empaquetar

```bash
cd /mnt/skills/examples/skill-creator && \
python -m scripts.package_skill \
    /home/claude/skills/enterprisebot-annex-v14 \
    /mnt/user-data/outputs/skills
```

#### PASO 5 — Presentar el `.skill` para descarga

```python
present_files(["/mnt/user-data/outputs/skills/enterprisebot-annex-v14.skill"])
```

#### PASO 6 — Backup en PythonAnywhere

```sftp
put "/sdcard/Download/EnterpriseBot_{NNN}_PUT.txt" "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md"
exit
```

---

## PARTE 2 — CONTENIDO DEL ANEXO

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

### Modelo `BreakdownTicket` — Estado actual

Campos confirmados tras S010:
- `room` (FK `ChatRoom`)
- `contact` (FK `Contact`)
- `machine` (FK `MachineAsset`)
- `section` (FK `Section`)
- `status` — choices: OPEN, IN_PROGRESS, CLOSED
- `is_repair_order` (BooleanField)
- `resolved_by` (FK `CompanyUser` nullable)
- `assigned_to` (FK `CompanyUser` nullable, related_name `assigned_tickets`)
- `urgency` — choices: LOW/MEDIUM/HIGH/CRITICAL (cubre el campo `priority` previsto)
- `created_at`, `updated_at`

### Vistas actuales

- `BreakdownTicketCreateView` — creación manual desde panel
- `BreakdownTicketDetailView` — detalle con acciones: `assign`, `convert_repair`, `set_urgency`, `close`
- `breakdown_ticket_list.html` — listado con botón "Nuevo ticket"
- `breakdown_ticket_detail.html` — detalle y acciones ciclo de vida
- `breakdown_ticket_form.html` — formulario de creación

### Integración con partes digitales

`_get_context_base` de `WorkOrderEntryFormView` enriquecido con
`repair_orders` (OTs abiertas disponibles para el operario: sin
`assigned_to` o asignadas a él), con prerelleno automático via `data-*`.

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

---

## 5. Incidencias Activas

### I-BUG-A — FieldError en BreakdownTicketCreateView

**Síntoma:** `FieldError: Cannot resolve keyword 'asset_code' into field`
al acceder a `GET /panel/chat/breakdowns/tickets/create/`.

**Origen:** `BreakdownTicketCreateView` filtra o ordena `MachineAsset`
por `asset_code`, campo que no existe en el modelo. Los campos válidos
incluyen `code`, `type_code`, `company_code`, entre otros.

**Fix:** Localizar en `chat/views.py` la referencia a `asset_code` y
sustituirla por el campo correcto (`code` o el que corresponda según
el contexto).

---

## 6. Registro de Sesiones

| Sesión | Fecha | Resumen |
|--------|-------|---------|
| S010 | 2026-05-21 | Implementación completa de los pasos 1-11 originales del hito. Arquitectura base de BreakdownTicket operativa. |

---

## 7. Hoja de Ruta para la Siguiente Sesión

### Paso 12 — Fix I-BUG-A: FieldError `asset_code` en BreakdownTicketCreateView

Localizar en `chat/views.py` el filtro/orden por `asset_code` en el
queryset de `MachineAsset` de `BreakdownTicketCreateView`. Sustituir
por el campo correcto (`code`). Verificar que la vista GET responde
sin errores tras el fix.

### Paso 13 — Auditoría y smoke test del CRUD completo de tickets

Tras el fix del Paso 12, recorrer el flujo completo:
- Crear ticket manual desde el panel.
- Asignar a WORKSHOPBOSS.
- Convertir a OT (`is_repair_order=True`).
- Establecer urgencia.
- Cerrar ticket.
- Verificar que la OT aparece en el desplegable del formulario de parte.

### Paso 14 — CRUD de tickets desde el panel: mejoras UX

Revisar y mejorar la interfaz de gestión de tickets:
- Listado con filtros por estado, sección, urgencia y operario asignado.
- Acciones bulk (cerrar varios tickets a la vez).
- Vista de detalle completa con historial de cambios de estado.
- Badge de urgencia con color diferencial en el listado.

### Paso 15 — Entrada de tickets vía WhatsApp (robot)

Diseño e implementación del flujo de creación automática de tickets
desde mensajes entrantes de WhatsApp al robot de la sala BREAKDOWNS.
(Alcance a definir en la sesión correspondiente.)
