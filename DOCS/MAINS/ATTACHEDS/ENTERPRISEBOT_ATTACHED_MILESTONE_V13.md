# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md

# ENTERPRISEBOT — ANEXO HITO 13
## Salas de Chat IRC por Sección (WhatsApp → Panel)

---

## Estado de Pasos

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Modelo `ChatRoom` y `ChatMessage` | COMPLETADO |
| 2 | Migración inicial chat | COMPLETADO |
| 3 | Creación automática de salas por sección | COMPLETADO |
| 4 | Vista `ChatRoomListView` | COMPLETADO |
| 5 | Vista `ChatRoomView` | COMPLETADO |
| 6 | Vista `ChatSendView` | COMPLETADO |
| 7 | Template `chat_room_list.html` | COMPLETADO |
| 8 | Template `chat_room.html` | COMPLETADO |
| 9 | URLs chat | COMPLETADO |
| 10 | Entrada sidebar Chat de Secciones | COMPLETADO |
| 11 | Sala BREAKDOWNS — modelo y migración | COMPLETADO |
| 12 | `BreakdownTicket` — modelo y migración | COMPLETADO |
| 13 | `BreakdownRoomManageView` + template | COMPLETADO |
| 14 | `BreakdownTicketListView` + template | COMPLETADO |
| 15 | `BreakdownTicketDetailView` + template | COMPLETADO |
| 16 | Rol `WORKSHOPBOSS` — implementación completa | COMPLETADO |

---

## Arquitectura Técnica

### Modelos (`chat/models.py`)

- `ChatRoom`: sala IRC por sección. Campos: `company`, `section` (FK nullable), `room_type` (`SECTION`/`BREAKDOWNS`), `name`, `is_active`.
- `ChatMessage`: mensaje en sala. Campos: `room` (FK), `sender_alias`, `body`, `created_at`.
- `BreakdownTicket`: ticket de avería generado desde sala BREAKDOWNS. Campos: `room`, `contact`, `machine`, `section`, `status`, `is_repair_order`, `resolved_by`, `created_at`, `updated_at`.

### Rol `WORKSHOPBOSS`

- **Constante:** `CompanyUser.ROLE_WORKSHOPBOSS = "WORKSHOPBOSS"`.
- **Display:** `"Jefe de taller"`.
- **Migración:** `ivr_config/migrations/0025_workshopboss_role.py`.
- **Tipo:** contacto interno (`is_internal=True`), provisionado por ADMIN/SUPERVISOR desde el panel.
- **Sección asignada:** una sección, asignada por ADMIN desde el panel.

### Matriz de Acceso `WORKSHOPBOSS`

| Sección Panel | Acceso |
|---|---|
| Inicio (dashboard) | Sí |
| Presencia (Mi estado) | Sí |
| Taller (Nuevo parte + Historial operario) | No |
| Administración (PDFs, Centros de gasto, Usuarios, Historial) | Sí |
| Configuración de jornada | Sí |
| Chat de Secciones (sala propia + BREAKDOWNS) | Sí |
| Tickets de Avería (list + detail + acciones) | Sí |
| Gestión membresía sala BREAKDOWNS | No (solo ADMIN) |
| IVR / WhatsApp / Analítica | No |

### Mixins afectados

- `WorkshopRequiredMixin`: `WORKSHOP`, `WORKSHOPBOSS`, `ADMIN`.
- `SupervisorAccessMixin`: `SUPERVISOR`, `WORKSHOPBOSS`, `ADMIN`.
- `AdminRoleRequiredMixin`: `ADMIN` exclusivamente (sin cambio).

### Archivos Modificados en S009

- `ivr_config/models.py` — `ROLE_WORKSHOPBOSS`, `ROLE_CHOICES`, `help_text`.
- `ivr_config/migrations/0025_workshopboss_role.py` — migración generada.
- `panel/mixins.py` — `WorkshopRequiredMixin` y `SupervisorAccessMixin`.
- `chat/views.py` — 7 guards de rol actualizados.
- `panel/views.py` — `CompanyUserUpdateView.post` y `MachineAssetListView`.
- `panel/templates/panel/_nav_items.html` — Inicio, Presencia, Taller, Administración, Configuración de jornada, Chat de Secciones, Tickets de Avería.
- `panel/templates/panel/chat/breakdown_ticket_list.html` — botón Gestionar membresía oculto para no-ADMIN.

---

## Nota de Cierre S009

Todos los pasos del Hito 13 completados en S009 (2026-05-21).
El sistema de gestión de tickets de avería y órdenes de reparación
ha sido promovido a hito propio: **Hito 14**.
Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md`.
