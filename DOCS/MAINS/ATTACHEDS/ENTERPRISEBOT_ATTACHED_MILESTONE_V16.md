# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V16.md

# Anexo de Hito V16 — Motor de Presupuestos para Sección ASISTENCIA
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-05-25

---

## 1. Visión General del Hito

La sección de ASISTENCIA de la empresa cliente gestiona servicios de grúa y
asistencia en carretera cubiertos total o parcialmente por compañías aseguradoras.
Cada aseguradora tiene una tarifa propia (kilómetros, servicios especiales, esperas,
recargos nocturnos, festivos, etc.). Actualmente los presupuestos se elaboran de
forma manual consultando las tarifas en papel, lo que genera errores y consume
tiempo.

Este hito implementa un motor de presupuestos integrado en el panel de EnterpriseBot
que permita:

1. **Gestionar tarifas por aseguradora**: altas, bajas y edición de conceptos y
   precios de tarifa de cada compañía desde el panel.
2. **Generar presupuestos**: a partir de los datos de entrada del operario
   (tipo de servicio, kilómetros, esperas, condiciones especiales) el motor
   aplica la tarifa vigente de la aseguradora correspondiente y genera el
   presupuesto desglosado.
3. **Exportar el presupuesto**: documento PDF o Excel descargable desde el panel.
4. **Skill de referencia**: antes de implementar nada, se construye una skill
   que documente el esquema de tarifas, los campos de entrada y las reglas de
   cálculo, derivada de los datos reales entregados por el cliente (tarifas por
   aseguradora, facturas de ejemplo).

---

## 2. Arquitectura Técnica

### 2.1. App Django `budgets`

App creada y operativa en producción desde la sesión 001. Modelos:

- `Insurer`: compañía aseguradora. FK Company. Campos: name, code, is_active,
  management_fee_percent, surcharges_cumulative, notes.
- `VehicleType`: tipo de vehículo con nomenclatura propia de cada aseguradora.
  FK Insurer. Campos: name, sort_order, is_active.
- `InsurerTariff`: tarifa vigente con histórico. FK Insurer. Campos: year,
  valid_from, valid_to (null = activa), notes.
- `TariffLine`: línea de concepto de tarifa. FK InsurerTariff + VehicleType
  (nullable = concepto genérico). Conceptos: DEPARTURE, SERVICE_LOCAL,
  KM_NORMAL, KM_LONG, UNLOCK, RESCUE_HOUR, WAIT_HOUR, WORKER_HOUR,
  ASSISTANT_HOUR, CUSTODY_DAY, NYF_PERCENT, LOADED_PERCENT.
- `Budget`: presupuesto generado. FK Company, Insurer, InsurerTariff,
  CompanyUser, VehicleType. Campos: is_overnight, km_phase1, km_phase2,
  km_total, has_unlock, is_night_or_holiday, is_loaded, wait_hours,
  rescue_hours, assistant_hours, worker_hours, custody_days, apply_iva,
  total_amount, status (DRAFT/ACCEPTED/REJECTED).
- `BudgetLine`: desglose de cálculo. FK Budget. Solo visible para ADMIN.

### 2.2. Motor de cálculo (`budgets/services.py`)

Función `calculate_budget(budget)` idempotente:
1. Resuelve la `InsurerTariff` activa (valid_to=None).
2. Calcula km_total = km_phase1 + km_phase2 (antes del save).
3. Aplica salidas (1 o 2 si pernocta).
4. Aplica km (KM_NORMAL o KM_LONG según umbral km_threshold).
5. Aplica desbloqueo si has_unlock.
6. Aplica conceptos opcionales (rescate, espera, MO, ayudante, custodia)
   respetando min_units.
7. Aplica recargos (NYF, cargado) según surcharges_cumulative de Insurer.
8. Aplica management_fee si procede (solo COVEI 5%).
9. Si apply_iva: aplica IVA_PERCENT (constante en services.py, actualmente 21%)
   sobre total_amount. Asigna total_amount_with_iva como atributo de instancia
   (no persistido en BD).
10. Devuelve lista de BudgetLine sin guardar. El caller persiste atómicamente.

Constante fiscal: `IVA_PERCENT = Decimal("21.00")` en budgets/services.py.
Para cambiar el IVA, modificar directamente esta constante.

### 2.3. Rol y usuario

- Rol `ROLE_ASSISTANCE` = "ASSISTANCE" añadido a CompanyUser.
- Usuario `asistencia` / `1234` creado con must_change_password=False.
- Mixin `AssistanceRequiredMixin` en panel/mixins.py.
- Sidebar: rol ASSISTANCE ve solo "Presupuestos → Nuevo presupuesto".
  Rol ADMIN ve además "Historial presupuestos".

### 2.4. Tarifas cargadas

23 aseguradoras, 188 tipos de vehículo, 550 líneas de tarifa cargadas
mediante `python manage.py seed_insurer_tariffs` (idempotente, con --dry-run).

Aseguradoras: Transsorual/Mondial, Europ Assistance, ARAG, Avinatan/ATE,
IMA Ibérica, Treasca, Asitur, TAI 2026, RACE, Mapfre, Inter Partner/AXA,
Servireac (SVR), Grúas Alvarez (tarifa propia), MAN Truck, Petit Forestier,
COVEI, TVA (ALSA), Scora y Selltruck (Ford), Veinluc, UTE Envases Ligeros,
Prosegur, F.C.C., Angal Truck.

### 2.5. URLs

Registradas en `enterprise_core/urls.py`:
`path('panel/budgets/', include('budgets.urls', namespace='budgets'))`

Endpoints: wizard, vehicle_types (HTMX), optional_concepts (HTMX),
result, status_update, history (ADMIN), detail (ADMIN).

### 2.6. Migraciones aplicadas en producción

- `budgets/migrations/0001_initial` — S001: modelos completos.
- `budgets/migrations/0002_budget_apply_iva` — S002: campo apply_iva en Budget.

---

## 3. Hoja de Ruta

### Paso 1 — Recopilación de datos y construcción de la skill
- Estado: COMPLETADO (S001 — integrado directamente en la app)

### Paso 2 — Validación de la skill con Miguel Ángel
- Estado: COMPLETADO (S001 — diseño validado iterativamente)

### Paso 3 — Modelo de datos Django (app budgets)
- Estado: COMPLETADO (S001 — migración 0001_initial aplicada en producción)

### Paso 4 — Panel de gestión de aseguradoras y tarifas
- Estado: PENDIENTE — ver hoja de ruta S003.

### Paso 5 — Motor de generación de presupuestos
- Estado: COMPLETADO (S001 — formulario secuencial HTMX operativo)

### Paso 6 — Exportación del presupuesto
- Estado: PENDIENTE

### Paso 7 — Integración en sidebar del panel
- Estado: COMPLETADO (S001)

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| S001   | 2026-05-26 | 1–5, 7          | Implementación completa de la app budgets: modelos, motor de cálculo, vistas, templates, rol ASSISTANCE, usuario asistencia, 23 tarifas 2026 cargadas en BD (550 líneas). Formulario secuencial HTMX operativo. Vista de desglose ADMIN. Sidebar adaptado por rol. |
| S002   | 2026-05-27 | 4 (parcial)     | IVA: campo apply_iva (BooleanField, default False) añadido al modelo Budget (migración 0002). Constante IVA_PERCENT = Decimal("21.00") en services.py. Paso 8 en motor de cálculo: aplica IVA sobre total_amount cuando apply_iva=True, asigna total_amount_with_iva como atributo de instancia. Paso IVA añadido al wizard (paso 8, entre NYF y fecha). result.html muestra base imponible + total con IVA cuando apply_iva=True. Documentación de rutas de log PythonAnywhere añadida a sección 4.3 del MASTER_DOCUMENT. Reorganización sidebar: Historial restringido a WORKSHOP/WORKSHOPBOSS en sección Operarios; Historial admin añadido en sección Operarios para ADMIN/SUPERVISOR apuntando a work_order_admin_history; Partes digitales eliminado del sidebar. |

---

## 5. Hoja de Ruta para la Siguiente Sesión (S003)

### Contexto

La app `budgets` está operativa con el motor de cálculo completo y el campo
IVA funcionando. La siguiente sesión implementa el panel de gestión de
aseguradoras y sus tarifas, actualmente solo gestionables via Django Admin
y management command.

### ADVERTENCIAS CRÍTICAS

- `IVA_PERCENT = Decimal("21.00")` en `budgets/services.py` — constante de
  modificación directa. No mover a BD ni a settings.
- La migración `0002_budget_apply_iva` fue creada manualmente (no con
  makemigrations) y ya está aplicada en producción. No regenerar.
- El campo `total_amount_with_iva` NO está en BD — es atributo de instancia
  asignado por el motor. No añadir al modelo sin consenso explícito.
- `budgets/migrations/0001_initial` tiene dependencia en
  `ivr_config.0029_alter_companyuser_role` — no reordenar migraciones.

### PRIORIDAD 0 — Panel de gestión de aseguradoras

Implementar un panel de gestión completo para las entidades `Insurer`,
`VehicleType`, `InsurerTariff` y `TariffLine` accesible desde el panel
de EnterpriseBot para el rol ADMIN, sin necesidad de acceder al Django Admin.

#### Alcance funcional

**Listado de aseguradoras** (`/panel/budgets/insurers/`):
- Tabla con columnas: Nombre, Código, Activa (badge), Gastos gestión (%),
  Recargos acumulables, Nº tarifas, Acciones (Editar, Activar/Desactivar,
  Eliminar con confirmación).
- Filtro por nombre/código (búsqueda live HTMX).
- Botón "Nueva aseguradora".
- Solo visible para ADMIN.

**Formulario de aseguradora** (crear/editar):
- Campos: name, code, management_fee_percent, surcharges_are_cumulative,
  is_active, notes.
- Validación: code único por empresa (unique_together con company).
- Tras guardar: redirige al listado con mensaje de éxito.

**Activar/Desactivar aseguradora** (toggle HTMX):
- Endpoint POST `/panel/budgets/insurers/<pk>/toggle/`.
- Devuelve fragmento badge actualizado. Sin recarga de página.
- Una aseguradora inactiva no aparece en el wizard de presupuestos.

**Gestión de tipos de vehículo** (`/panel/budgets/insurers/<pk>/vehicles/`):
- Listado inline dentro de la vista de edición de aseguradora.
- CRUD completo: añadir, editar nombre/sort_order/is_active, eliminar.
- HTMX para añadir/eliminar sin recarga.

**Gestión de tarifas** (`/panel/budgets/insurers/<pk>/tariffs/`):
- Listado de versiones de tarifa (año, valid_from, valid_to, estado activa/histórica).
- Crear nueva tarifa: año + valid_from. Al crear, cierra la tarifa activa anterior
  estableciendo su valid_to = today - 1 día.
- Ver/editar líneas de tarifa de una versión concreta.

**Gestión de líneas de tarifa** (`/panel/budgets/tariffs/<pk>/lines/`):
- Tabla editable inline con todas las TariffLine de la tarifa.
- Columnas: concepto, tipo de vehículo (nullable), unidad, precio,
  umbral km (nullable), mínimo facturable (nullable), requiere autorización.
- Añadir línea, editar precio/campos inline (HTMX), eliminar línea.
- Guardado automático por campo via HTMX (hx-trigger="change").

#### Implementación

Nuevas vistas en `budgets/views.py` (todas con `AdminRoleRequiredMixin`):
- `InsurerListView`
- `InsurerCreateView`
- `InsurerUpdateView`
- `InsurerToggleView` (HTMX)
- `InsurerDeleteView`
- `VehicleTypeListView` (inline en InsurerUpdateView)
- `VehicleTypeCreateView`, `VehicleTypeUpdateView`, `VehicleTypeDeleteView`
- `InsurerTariffListView`, `InsurerTariffCreateView`
- `TariffLineListView`, `TariffLineSaveView` (HTMX), `TariffLineDeleteView`

Nuevas URLs en `budgets/urls.py` bajo prefijo `insurers/`.

Nuevos templates en `budgets/templates/budgets/`:
- `insurer_list.html`
- `insurer_form.html`
- `insurer_tariff_list.html`
- `tariff_line_list.html`
- `_insurer_badge_fragment.html` (HTMX toggle activa)

Nuevo ítem en sidebar `_nav_items.html` para ADMIN bajo sección Presupuestos:
`<i class="bi bi-building"></i>Aseguradoras`
→ `{% url 'budgets:insurer_list' %}`

Antes de implementar: actualización online obligatoria de la API de Django
y HTMX (Directriz 4.4 del MASTER_DOCUMENT).

### PRIORIDAD 1 — Corrección banner "Acceso denegado" residual en OperatorDashboardView

El template `operator/dashboard.html` muestra los mensajes Django del framework
al inicio de la página. Tras la corrección de mixins de S002, un mensaje
residual de sesión anterior aparece en la primera carga del dashboard del
operario. Investigar si el mensaje proviene de un {% if messages %} en
`base.html` o `dashboard.html` y añadir lógica para suprimir mensajes de
tipo "error" en la vista del operario si el usuario tiene rol WORKSHOP,
o limpiar la cola de mensajes al inicio de `OperatorDashboardView.get()`.
