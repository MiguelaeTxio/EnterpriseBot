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
3. **Exportar listado de aseguradoras**: PDF, Excel, Word y CSV desde el panel.
4. **Skill de referencia**: antes de implementar nada, se construye una skill
   que documente el esquema de tarifas, los campos de entrada y las reglas de
   cálculo, derivada de los datos reales entregados por el cliente (tarifas por
   aseguradora, facturas de ejemplo).

---

## 2. Arquitectura Técnica

### 2.1. App Django `budgets`

App creada y operativa en producción. Modelos actuales:

- `Insurer`: compañía aseguradora o cliente directo. FK Company. Campos: name,
  insurer_company_name, service_company_name, code, is_active, management_fee_percent,
  surcharges_are_cumulative, notes, is_insurance_company, always_apply_iva,
  special_night_holiday_tariff.
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
  total_amount, total_amount_with_iva (persistido en BD), status (DRAFT/ACCEPTED/REJECTED).
- `BudgetLine`: desglose de cálculo. FK Budget. Solo visible para ADMIN.
- `SpecialRateTariff`: tabla de tarifas especiales nocturno/festivo. OneToOneField
  a InsurerTariff. Vinculada cuando Insurer.special_night_holiday_tariff=True.
- `SpecialRateLine`: línea de precio especial. FK SpecialRateTariff + VehicleType
  (nullable). Misma estructura que TariffLine.

### 2.2. Motor de cálculo (`budgets/services.py`)

Función `calculate_budget(budget)` idempotente:
1. Resuelve la `InsurerTariff` activa (valid_to=None).
2. Fuerza apply_iva=True si insurer.always_apply_iva=True.
3. Calcula km_total = km_phase1 + km_phase2 (antes del save).
4. Resuelve SpecialRateTariff si is_night_or_holiday=True y
   insurer.special_night_holiday_tariff=True. Si existe, usa SpecialRateLine
   para pasos 4-7. Si no, usa TariffLine estándar.
5. Aplica salidas (1 o 2 si pernocta).
6. Aplica km (KM_NORMAL o KM_LONG según umbral km_threshold).
7. Aplica desbloqueo si has_unlock.
8. Aplica conceptos opcionales (rescate, espera, MO, ayudante, custodia)
   respetando min_units.
9. Aplica recargos (NYF_PERCENT, LOADED_PERCENT) según surcharges_are_cumulative.
   OMITIDO si using_special_rate=True.
10. Aplica management_fee si procede (solo COVEI 5%).
11. Si apply_iva: aplica IVA_PERCENT sobre total_amount. Persiste
    total_amount_with_iva en BD (migración 0005).
12. Devuelve lista de BudgetLine sin guardar. El caller persiste atómicamente.

Constante fiscal: `IVA_PERCENT = Decimal("21.00")` en budgets/services.py.

### 2.3. Rol y usuario

- Rol `ROLE_ASSISTANCE` = "ASSISTANCE" en CompanyUser.
- Usuario `asistencia` / `1234` creado con must_change_password=False.
- Mixin `AssistanceRequiredMixin` en panel/mixins.py.
- Sidebar: rol ASSISTANCE ve solo "Presupuestos → Nuevo presupuesto".
  Rol ADMIN ve además "Historial presupuestos" y "Configuración empresa".

### 2.4. Tarifas cargadas (S005)

32 aseguradoras, 250 tipos de vehículo, 798 líneas de tarifa cargadas
mediante `python manage.py seed_insurer_tariffs` (idempotente, con --dry-run).
Nombres en formato "Aseguradora / Empresa prestadora" con campos
insurer_company_name y service_company_name separados.

4 SpecialRateTariff cargadas (RACC/Zurich variantes Transgrual y AGG),
25 líneas especiales cada una, mediante script
`/home/MiguelAeTxio/SWAP/seed_special_rate_tariffs.py` (ya ejecutado,
conservar en SWAP para reutilizar si hay reseed).

### 2.5. URLs

Registradas en `enterprise_core/urls.py`:
`path('panel/budgets/', include('budgets.urls', namespace='budgets'))`

Endpoints activos: wizard, vehicle_types (HTMX), optional_concepts (HTMX),
result, status_update, history (ADMIN), detail (ADMIN), budget_bulk_delete,
insurer_list, insurer_create, insurer_update, insurer_detail, insurer_toggle,
insurer_delete, tariff_create, tariff_save_notes, tariff_line_add_form,
tariff_line_add, tariff_line_save, tariff_line_delete,
company_settings (ADMIN).

### 2.6. Migraciones aplicadas en producción

- `budgets/migrations/0001_initial` — S001: modelos completos.
- `budgets/migrations/0002_budget_apply_iva` — S002: campo apply_iva en Budget.
  CREADA MANUALMENTE — no regenerar.
- `budgets/migrations/0003_insurer_is_insurance_company` — S004.
- `budgets/migrations/0004_insurer_company_and_service_name` — S005:
  campos insurer_company_name y service_company_name en Insurer.
- `budgets/migrations/0005_budget_total_amount_with_iva` — S005:
  campo total_amount_with_iva en Budget.
- `budgets/migrations/0006_insurer_iva_special_rate_tariff` — S005:
  campos always_apply_iva y special_night_holiday_tariff en Insurer,
  modelos SpecialRateTariff y SpecialRateLine.
- `ivr_config/migrations/0030_company_labor_calendar_company_operation_bases`
  — S004.

### 2.7. Template tags

- `budgets/templatetags/budgets_extras.py`: filtros `concept_label` y
  `unit_label` que traducen códigos internos (DEPARTURE, FIXED, etc.)
  a etiquetas legibles en castellano para la interfaz.

### 2.8. Locale decimal (S005)

- `enterprise_core/settings.py`: añadidos `USE_L10N = True`,
  `DECIMAL_SEPARATOR = ','`, `USE_THOUSAND_SEPARATOR = False`.
- `InsurerForm`: campo `management_fee_percent` declarado explícitamente
  con `localize=True`.
- Helper `_parse_decimal()` en `budgets/views.py`: normaliza coma→punto
  en campos decimales de vistas HTMX (TariffLineSaveView, TariffLineAddView).

---

## 3. Hoja de Ruta

### Paso 1 — Recopilación de datos y construcción de la skill
- Estado: COMPLETADO (S001)

### Paso 2 — Validación de la skill con Miguel Ángel
- Estado: COMPLETADO (S001)

### Paso 3 — Modelo de datos Django (app budgets)
- Estado: COMPLETADO (S001 — migración 0001_initial)

### Paso 4 — Panel de gestión de aseguradoras y tarifas
- Estado: COMPLETADO (S003/S004/S005 — listado, acordeón, edición inline HTMX,
  toggle, eliminación modal, campos insurer_company_name/service_company_name,
  always_apply_iva, special_night_holiday_tariff, vista de detalle solo lectura).

### Paso 5 — Motor de generación de presupuestos
- Estado: COMPLETADO (S001/S005 — formulario secuencial HTMX operativo,
  IVA persistido en BD, tarifa especial nocturno/festivo operativa,
  always_apply_iva forzado en motor).

### Paso 6 — Exportación del presupuesto individual
- Estado: DESCARTADO — Los presupuestos se comunican verbalmente por teléfono.
  No existe caso de uso real. Decisión tomada en S005 (2026-05-29).

### Paso 7 — Integración en sidebar del panel
- Estado: COMPLETADO (S001)

### Paso 8 — Ampliación del modelo Company: bases de operación y calendario laboral
- Estado: COMPLETADO (S005 — CompanySettingsView, template company/settings.html,
  ruta panel/company/settings/, enlace sidebar ADMIN).

### Paso 9 — Label dinámico en wizard de presupuestos
- Estado: COMPLETADO (S005 — insurer_label calculado dinámicamente en
  BudgetWizardView.get(), sufijo '(Particular)' en opciones del desplegable).

### Paso 10 — Corrección banner residual 'Acceso denegado'
- Estado: COMPLETADO (S004)

### Paso 11 — Exportaciones del panel de aseguradoras
- Estado: PENDIENTE (S006)
- Alcance: botones de exportación en InsurerListView (PDF, Excel, Word, CSV).
  Librería recomendada para PDF: weasyprint. Para Excel: openpyxl.
  Para Word: python-docx. Para CSV: csv stdlib.
  Verificar disponibilidad de librerías antes de implementar.

### Paso 12 — Calendario laboral en presupuestos
- Estado: PENDIENTE (S006)
- Alcance: parsear Company.labor_calendar para detectar festivos.
  La casilla "Nocturno/Festivo" del wizard se divide en solo "Nocturno"
  (marcada por el operario). "Festivo" lo determina el sistema según la
  fecha del servicio: sábado, domingo, o fecha presente en labor_calendar.
  Si es nocturno Y festivo → se aplica un solo recargo (el mayor, regla
  ya implementada en el motor).

### Paso 13 — Integración Google Maps Routes API
- Estado: PENDIENTE (S006)
- Alcance: cálculo de ruta y peajes desde la base del operario hasta
  la ubicación del cliente. Dos modos de entrada:
  1. Coordenadas GPS recibidas por WhatsApp.
  2. Referencia textual (pueblo + km aproximados) geocodificada con
     Geocoding API.
  API key pendiente de confirmar. Peajes como concepto adicional en presupuesto.

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| S001   | 2026-05-26 | 1-5, 7          | Implementación completa app budgets: modelos, motor, vistas, templates, rol ASSISTANCE, 23 tarifas 2026. |
| S002   | 2026-05-27 | 4 (parcial)     | IVA: apply_iva en Budget (migración 0002 manual). Motor paso 8. result.html muestra base + total IVA. |
| S003   | 2026-05-27 | 4 (visor)       | Panel aseguradoras: listado HTMX, acordeón edición, vistas tarifa inline. Corrección inputs decimal. |
| S004   | 2026-05-28 | 8 (parcial), 9 (parcial), 10 | is_insurance_company, operation_bases, labor_calendar migrados. Corrección banner WORKSHOP. |
| S005   | 2026-05-29 | 8, 9, 11 (parcial), nuevos pasos | Label dinámico wizard (Paso 9). CompanySettingsView (Paso 8). Reseed completo 32 aseguradoras con insurer_company_name/service_company_name. Modelos SpecialRateTariff/SpecialRateLine (migración 0006). Seed tarifas especiales RACC/Zurich (4 tablas x 25 líneas). Motor actualizado: always_apply_iva, special_night_holiday_tariff, _get_special_rate_lines. IVA persistido en BD (migración 0005). Eliminación masiva presupuestos (BudgetBulkDeleteView). Vista detalle solo lectura aseguradora (InsurerDetailView). Template tags budgets_extras (concept_label, unit_label). Locale decimal ES (settings + InsurerForm + _parse_decimal). Skill PED actualizada (salvaguarda U+2500). Skill session-standards actualizada (tee + reglas entorno sftp). |

---

## 5. Hoja de Ruta para la Siguiente Sesión (S006)

### Contexto

S005 completó los pasos centrales del motor y la gestión de aseguradoras.
S006 cierra los pasos pendientes de interfaz y acomete la integración con
Google Maps y el calendario laboral. El orden de prioridad es:

### ADVERTENCIAS CRÍTICAS

- `IVA_PERCENT = Decimal("21.00")` en `budgets/services.py` — constante de
  modificación directa. No mover a BD ni a settings.
- La migración `0002_budget_apply_iva` fue creada manualmente. No regenerar.
- `budgets/migrations/0001_initial` tiene dependencia en
  `ivr_config.0029_alter_companyuser_role` — no reordenar migraciones.
- El script `seed_special_rate_tariffs.py` está en SWAP. Si hay reseed total
  de aseguradoras, ejecutarlo después de `seed_insurer_tariffs`.
- `USE_L10N = True` y `DECIMAL_SEPARATOR = ','` en settings — todos los
  DecimalField de formularios deben tener `localize=True` si se declaran
  explícitamente.

### PRIORIDAD 0 — Paso 11: exportaciones del panel de aseguradoras

Añadir botones de exportación al listado de aseguradoras (`InsurerListView`,
`budgets/views.py`) y a la vista de detalle (`InsurerDetailView`).

#### Alcance técnico

- **CSV**: stdlib `csv`. Sin dependencias adicionales.
- **Excel**: `openpyxl`. Verificar disponibilidad: `python -c "import openpyxl"`.
- **PDF**: `weasyprint`. Verificar disponibilidad: `python -c "import weasyprint"`.
- **Word**: `python-docx`. Verificar disponibilidad: `python -c "import docx"`.
- Si alguna librería no está disponible, instalar con `pip install --break-system-packages`.
- Nuevos endpoints en `budgets/urls.py`:
  - `insurers/export/csv/` → `InsurerExportCsvView`
  - `insurers/export/excel/` → `InsurerExportExcelView`
  - `insurers/export/pdf/` → `InsurerExportPdfView`
  - `insurers/export/word/` → `InsurerExportWordView`
- Cada vista exporta el queryset filtrado actual (mismos filtros que el listado).
- Botones de exportación añadidos a `insurer_list.html` junto al botón
  "Nueva aseguradora".

### PRIORIDAD 1 — Paso 12: calendario laboral en presupuestos

#### Alcance técnico

**Modelo**: ningún cambio de modelo necesario. `Company.labor_calendar`
(TextField) ya existe. Formato libre de texto — el parser debe ser tolerante.

**Parser `budgets/services.py`**: nueva función `_is_holiday(date, company)`
que:
1. Lee `company.labor_calendar` (texto libre con festivos: "1 ene, 6 ene,
   25 dic... nocturno: 22:00-06:00").
2. Parsea líneas con formato "DD MMM" o "DD/MM" en español.
3. Devuelve True si la fecha es sábado, domingo, o coincide con algún festivo.

**Wizard (`budgets/views.py` y `wizard.html`)**:
- La casilla actual "Nocturno/Festivo" (`is_night_or_holiday`) se divide en:
  - `is_night` (BooleanField nuevo en Budget) — marcada por el operario.
  - `is_holiday` — calculado automáticamente por el sistema según la fecha
    del servicio y `_is_holiday()`.
- El campo `is_night_or_holiday` pasa a ser calculado: True si is_night OR is_holiday.
- **Migración necesaria**: añadir `is_night` (BooleanField, default False) a Budget.
  `is_night_or_holiday` se mantiene como campo calculado (no se elimina — compatibilidad).

**ADVERTENCIA**: solicitar al inicio de S006 el estado actual de
`wizard.html` y `Budget` model desde disco antes de parchear.

### PRIORIDAD 2 — Paso 13: integración Google Maps Routes API

#### Alcance técnico

**API key**: configurar en `.env` como `GOOGLE_MAPS_API_KEY`.

**Nueva función `budgets/services.py`**: `calculate_route(origin, destination)`
que llama a Google Maps Routes API y devuelve:
- `distance_km`: distancia real por carretera.
- `toll_cost`: coste de peajes (si Routes API devuelve `computeTollInfo`).

**Dos modos de entrada en wizard (nuevo paso HTMX)**:
1. **Coordenadas GPS**: input lat/lng directo (recibido de WhatsApp).
2. **Referencia textual**: nombre de municipio + km aproximados.
   Geocodificar el municipio con Geocoding API, tomar como punto de
   referencia y sumar km indicados.

**Origen**: base más cercana del insurer (campo `notes` de Insurer contiene
las bases — parsear para extraer municipios).

**Integración en wizard**: nuevo paso opcional entre paso 1 (aseguradora)
y paso 2 (tipo de vehículo). Si el operario introduce ubicación, km_phase1
se precalcula automáticamente y los peajes se añaden como concepto adicional
en `calculate_budget()`.

**ADVERTENCIA**: antes de implementar, verificar disponibilidad de
`googlemaps` package: `python -c "import googlemaps"`. Instalar si necesario.
