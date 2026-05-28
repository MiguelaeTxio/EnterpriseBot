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
  management_fee_percent, surcharges_cumulative, notes, is_insurance_company.
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
result, status_update, history (ADMIN), detail (ADMIN), insurer_list,
insurer_create, insurer_update, insurer_toggle, insurer_delete,
tariff_create, tariff_save_notes, tariff_line_add_form, tariff_line_add,
tariff_line_save, tariff_line_delete.

### 2.6. Migraciones aplicadas en producción

- `budgets/migrations/0001_initial` — S001: modelos completos.
- `budgets/migrations/0002_budget_apply_iva` — S002: campo apply_iva en Budget.
- `budgets/migrations/0003_insurer_is_insurance_company` — S004: campo is_insurance_company en Insurer.
- `ivr_config/migrations/0030_company_labor_calendar_company_operation_bases` — S004: campos operation_bases y labor_calendar en Company.

---

## 3. Hoja de Ruta

### Paso 1 — Recopilación de datos y construcción de la skill
- Estado: COMPLETADO (S001 — integrado directamente en la app)

### Paso 2 — Validación de la skill con Miguel Ángel
- Estado: COMPLETADO (S001 — diseño validado iterativamente)

### Paso 3 — Modelo de datos Django (app budgets)
- Estado: COMPLETADO (S001 — migración 0001_initial aplicada en producción)

### Paso 4 — Panel de gestión de aseguradoras y tarifas
- Estado: COMPLETADO (S003/S004 — listado, acordeón, edición inline HTMX, toggle, eliminación modal).

### Paso 5 — Motor de generación de presupuestos
- Estado: COMPLETADO (S001 — formulario secuencial HTMX operativo)

### Paso 6 — Exportación del presupuesto
- Estado: PENDIENTE

### Paso 7 — Integración en sidebar del panel
- Estado: COMPLETADO (S001)

### Paso 8 — Ampliación del modelo Company: bases de operación y calendario laboral
- Estado: EN CURSO — campos añadidos al modelo y migrados en S004.
  Pendiente: exponer ambos campos en el formulario de edición de empresa del panel (ADMIN).

### Paso 9 — Flag compañía/particular en aseguradora (Insurer)
- Estado: EN CURSO — campo is_insurance_company añadido al modelo, migrado,
  añadido a InsurerForm y al template _insurer_fields_partial.html en S004.
  Pendiente: que el wizard de presupuestos muestre el label adecuado
  ('Aseguradora' vs 'Cliente particular') según el flag en el desplegable.

### Paso 10 — Corrección banner residual 'Acceso denegado' en OperatorDashboardView
- Estado: COMPLETADO (S004 — get_context_data vacía mensajes error para rol WORKSHOP).

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| S001   | 2026-05-26 | 1–5, 7          | Implementación completa de la app budgets: modelos, motor de cálculo, vistas, templates, rol ASSISTANCE, usuario asistencia, 23 tarifas 2026 cargadas en BD (550 líneas). Formulario secuencial HTMX operativo. Vista de desglose ADMIN. Sidebar adaptado por rol. |
| S002   | 2026-05-27 | 4 (parcial)     | IVA: campo apply_iva (BooleanField, default False) añadido al modelo Budget (migración 0002). Constante IVA_PERCENT = Decimal("21.00") en services.py. Paso 8 en motor de cálculo: aplica IVA sobre total_amount cuando apply_iva=True, asigna total_amount_with_iva como atributo de instancia. Paso IVA añadido al wizard (paso 8, entre NYF y fecha). result.html muestra base imponible + total con IVA cuando apply_iva=True. Documentación de rutas de log PythonAnywhere añadida a sección 4.3 del MASTER_DOCUMENT. Reorganización sidebar: Historial restringido a WORKSHOP/WORKSHOPBOSS en sección Operarios; Historial admin añadido en sección Operarios para ADMIN/SUPERVISOR apuntando a work_order_admin_history; Partes digitales eliminado del sidebar. |
| S003   | 2026-05-27 | 4 (visor)       | Panel de gestión de aseguradoras: listado con búsqueda live HTMX, filtro estado, toggle activa, modal eliminación. Vista edición con acordeón 3 paneles independientes (datos generales, tarifa activa + historial, líneas tarifa inline HTMX). Vistas TariffLineSaveView, TariffLineDeleteView, TariffLineAddFormView, TariffLineAddView, InsurerTariffCreateView, TariffSaveNotesView. Corrección inputs type=number a type=text inputmode=decimal (locale ES). Nuevos pasos 8, 9 y 10 incorporados a hoja de ruta del hito. |
| S004   | 2026-05-28 | 8 (parcial), 9 (parcial), 10 | Campo is_insurance_company (BooleanField, default True) añadido a Insurer con migración 0003. Campos operation_bases y labor_calendar (TextField, blank=True) añadidos a Company con migración ivr_config.0030. Campo is_insurance_company añadido a InsurerForm y a _insurer_fields_partial.html. Corrección banner residual 'Acceso denegado' en OperatorDashboardView: get_context_data vacía la cola de mensajes error cuando el usuario tiene rol WORKSHOP, evitando que artefactos de sesiones de mixin anteriores se muestren en el dashboard del operario. |

---

## 5. Hoja de Ruta para la Siguiente Sesión (S005)

### Contexto

Los pasos 8 y 9 tienen su infraestructura de modelo migrada en producción.
La siguiente sesión los completa con sus partes de interfaz pendientes, y
acomete el Paso 6 (exportación del presupuesto).

### ADVERTENCIAS CRÍTICAS

- `IVA_PERCENT = Decimal("21.00")` en `budgets/services.py` — constante de
  modificación directa. No mover a BD ni a settings.
- La migración `0002_budget_apply_iva` fue creada manualmente (no con
  makemigrations) y ya está aplicada en producción. No regenerar.
- El campo `total_amount_with_iva` NO está en BD — es atributo de instancia
  asignado por el motor. No añadir al modelo sin consenso explícito.
- `budgets/migrations/0001_initial` tiene dependencia en
  `ivr_config.0029_alter_companyuser_role` — no reordenar migraciones.
- El campo `is_insurance_company` en `Insurer` tiene `default=True` —
  todas las aseguradoras existentes quedan marcadas como compañía aseguradora.
  Revisar manualmente si alguna es cliente particular (p.ej. Grúas Alvarez).

### PRIORIDAD 0 — Completar Paso 9: label dinámico en wizard de presupuestos

El wizard de presupuestos (`BudgetWizardView`, `budgets/views.py`) renderiza
en su primer paso un desplegable de selección de aseguradora. Actualmente
el label es siempre "Aseguradora". Debe mostrar "Aseguradora" o "Cliente
particular" según el valor de `Insurer.is_insurance_company`.

#### Alcance técnico

**En `budgets/views.py` — `BudgetWizardView.get()`:**

El contexto del wizard incluye el queryset de aseguradoras activas para el
desplegable del paso 1. Actualmente el queryset es plano. Anotar o enriquecer
el contexto para pasar a cada opción del desplegable el flag `is_insurance_company`
o bien pasar el queryset completo de objetos `Insurer` y gestionar el label
en el template.

**En el template del wizard (`budgets/templates/budgets/wizard.html`):**

El desplegable de selección de aseguradora (paso 1) debe cambiar su título
dinámicamente si hay mezcla de aseguradoras y clientes particulares:
- Si `insurer.is_insurance_company` es True → label en el `<option>`: nombre tal cual.
- Si `insurer.is_insurance_company` es False → label en el `<option>`: nombre + " (Particular)".
- El `<label>` del campo cambia a "Aseguradora / Cliente" si hay mezcla en el queryset.
  Si todos son aseguradoras, el label es "Aseguradora". Si todos son particulares,
  el label es "Cliente particular".

Solicitar el archivo `budgets/templates/budgets/wizard.html` y `budgets/views.py`
al inicio de la sesión para construir las anclas exactas.

### PRIORIDAD 1 — Completar Paso 8: exponer campos en formulario de empresa

Los campos `operation_bases` y `labor_calendar` del modelo `Company`
(`ivr_config/models.py`) están migrados pero no expuestos en el panel.

#### Alcance técnico

Localizar la vista y template de edición de empresa (`CompanyEditView` o
equivalente en `panel/views.py` y su template correspondiente). Añadir
ambos campos como `<textarea>` al formulario existente de edición de empresa,
solo accesible para ADMIN.

- `operation_bases`: `<textarea>` con placeholder "Localidades o zonas de cobertura
  (ej: Valladolid, Arroyo de la Encomienda, Simancas...)".
- `labor_calendar`: `<textarea>` con placeholder "Festivos locales, nacionales
  y horario nocturno de referencia (ej: 1 ene, 6 ene... nocturno: 22:00–06:00)".

Solicitar la vista de edición de empresa y su template al inicio de la sesión.

### PRIORIDAD 2 — Paso 6: exportación del presupuesto

Implementar la exportación del presupuesto generado en formato PDF descargable
desde la vista de resultado (`BudgetResultView`, `/panel/budgets/<pk>/result/`).

#### Alcance técnico

- Librería recomendada: `weasyprint` (ya disponible en el entorno o instalar
  vía `pip install weasyprint --break-system-packages`). Verificar disponibilidad
  antes de implementar.
- Nuevo endpoint: `GET /panel/budgets/<pk>/pdf/` — vista `BudgetPdfView`
  (AdminRoleRequiredMixin + AssistanceRequiredMixin o mixin propio).
- Template HTML dedicado para el PDF: `budgets/templates/budgets/budget_pdf.html`.
  Diseño limpio con membrete, datos del servicio, desglose de conceptos
  (solo para ADMIN) y total. Para ASSISTANCE: solo membrete, datos básicos
  y total sin desglose.
- Botón "Descargar PDF" en `result.html` apuntando al nuevo endpoint.
- Nueva URL en `budgets/urls.py`: `path('<int:pk>/pdf/', views.BudgetPdfView.as_view(), name='budget_pdf')`.
- Actualizar la directriz 4.4 del MASTER_DOCUMENT antes de implementar (obligatorio).

Solicitar `budgets/templates/budgets/result.html` al inicio de la sesión.
