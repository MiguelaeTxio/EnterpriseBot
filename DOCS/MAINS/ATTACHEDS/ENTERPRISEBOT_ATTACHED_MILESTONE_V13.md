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

## Hoja de Ruta para la Siguiente Sesión (S010)

### Bloque A — Gestión de Tickets y Órdenes de Reparación

#### A1. Flujo de inicio de ticket desde sala BREAKDOWNS

Revisar el mecanismo actual por el que un mensaje en la sala BREAKDOWNS genera un `BreakdownTicket`. Verificar:
- Qué signal o view crea el ticket al detectar el patrón de avería en el mensaje entrante.
- Qué campos se rellenan automáticamente (`contact`, `machine`, `section`).
- Qué campo `status` inicial se asigna al ticket recién creado.
- Si el `WORKSHOPBOSS` recibe notificación (WhatsApp o panel) cuando se crea un nuevo ticket.

#### A2. Flujo de inicio de ticket desde el panel por `WORKSHOPBOSS`

Implementar la capacidad de crear un `BreakdownTicket` manualmente desde el panel:
- Nueva vista `BreakdownTicketCreateView` accesible para `ADMIN`, `SUPERVISOR` y `WORKSHOPBOSS`.
- Formulario con campos: `contact` (desplegable contactos de empresa), `machine` (desplegable `MachineAsset` activos), `section` (desplegable secciones activas), descripción inicial.
- URL: `panel/chat/breakdowns/tickets/create/` con nombre `panel:breakdown_ticket_create`.
- Botón "Nuevo ticket" en `breakdown_ticket_list.html` visible para `ADMIN`, `SUPERVISOR` y `WORKSHOPBOSS`.

#### A3. Gestión del ciclo de vida del ticket

Revisar y completar las acciones disponibles en `BreakdownTicketDetailView`:
- **Asignar al `WORKSHOPBOSS`**: el ticket puede asignarse a un `WORKSHOPBOSS` concreto. Añadir campo `assigned_to` (FK `CompanyUser` nullable) al modelo `BreakdownTicket` si no existe.
- **Conversión a orden de reparación**: acción `convert_repair` — revisar su implementación actual y completarla si procede.
- **Cierre del ticket**: acción `close` — revisar su implementación actual.
- **Prioridad**: añadir campo `priority` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`) al modelo `BreakdownTicket` si no existe.

#### A4. Formulario de parte de operario — integración con órdenes de reparación

En el formulario de entrada de partes (`operator_dashboard` / `OperatorDashboardView`):
- Añadir desplegable de selección de orden de reparación que muestre:
  - Órdenes `BreakdownTicket` con `is_repair_order=True` y `status` abierto, sin `assigned_to` (disponibles para cualquier operario).
  - Órdenes `BreakdownTicket` con `is_repair_order=True` asignadas al operario autenticado (`assigned_to=company_user`), con su `priority`.
- Al seleccionar una orden, prerrellenar automáticamente los campos del formulario de parte con los datos de la orden (`machine`, `section`, descripción).
- La lógica de prerelleno debe implementarse via JavaScript (fetch a endpoint JSON) o via atributos `data-*` en las opciones del desplegable.

### Bloque B — Perfil propio del operario

#### B1. Cambio de nick del chat desde el panel

- El nick del chat se almacena en `CompanyUser.alias` (verificar nombre exacto del campo consultando `ivr_config/models.py`).
- Crear vista `OwnProfileView` accesible para `WORKSHOP` y `WORKSHOPBOSS` (y cualquier rol con acceso al panel).
- Formulario con campo `alias` editable, con validación de unicidad dentro de la empresa.
- URL: `panel/profile/` con nombre `panel:own_profile`.
- Entrada en sidebar bajo nueva sección "Mi perfil" visible para todos los roles con acceso al panel.
- El cambio de alias debe propagarse a los mensajes futuros del chat — los mensajes históricos mantienen el alias con el que fueron enviados (`sender_alias` es snapshot en `ChatMessage`).
