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
3. **Exportar tarifas y presupuestos**: PDF, Excel, Word y CSV desde el panel.
4. **Skill de referencia**: antes de implementar nada, se construye una skill
   que documente el esquema de tarifas, los campos de entrada y las reglas de
   cálculo, derivada de los datos reales entregados por el cliente.

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
  (nullable = concepto genérico).
- `Budget`: presupuesto generado. FK Company, Insurer, InsurerTariff, CompanyUser,
  VehicleType, Base (nullable). Campos: is_overnight, km_phase1, km_phase2,
  km_total, has_unlock, is_night (operario), is_night_or_holiday (calculado),
  is_loaded, wait_hours, rescue_hours, assistant_hours, worker_hours, custody_days,
  apply_iva, total_amount, total_amount_with_iva, status, service_date.
- `BudgetLine`: desglose de cálculo. FK Budget. Solo visible para ADMIN.
- `SpecialRateTariff`: tabla de tarifas especiales nocturno/festivo.
- `SpecialRateLine`: línea de precio especial.
- `Base`: base fisica de servicio. FK Insurer. Campos: name, municipality,
  latitude, longitude (nullable), labor_calendar (JSON ISO dates), calendar_synced_at,
  is_active. 74 bases sembradas via seed_bases (idempotente).

### 2.2. Motor de cálculo (`budgets/services.py`)

Función `calculate_budget(budget)` idempotente:
1. Resuelve la `InsurerTariff` activa (valid_to=None).
2. Calcula `is_holiday = _is_holiday(budget.service_date, budget.base)`.
   `_is_holiday()` parsea `base.labor_calendar` (JSON list de fechas ISO).
   Detecta sabados, domingos y festivos locales. Si base es None, solo fin de semana.
3. Calcula `budget.is_night_or_holiday = budget.is_night OR is_holiday`.
4. Fuerza apply_iva=True si insurer.always_apply_iva=True.
5. Calcula km_total = km_phase1 + km_phase2.
6. Resuelve SpecialRateTariff si is_night_or_holiday=True y
   insurer.special_night_holiday_tariff=True.
7-12. Aplica conceptos, recargos, management_fee, IVA segun logica previa.

Constante fiscal: `IVA_PERCENT = Decimal("21.00")` — no mover.

### 2.3. Sincronizacion de calendarios laborales

Comando `python manage.py sync_base_calendars`:
- Fuente: API publica calendariosnacionales.com (sin API key, sin limites).
- Endpoint: `https://calendariosnacionales.com/es/v1/{anio}/localidades/{ccaa}/{provincia}/{municipio}.json`
- Popula `base.labor_calendar` como JSON list de fechas ISO.
- Soporta `--year`, `--base-id`, `--dry-run`, `--force`.
- MUNICIPALITY_MAP en `sync_base_calendars.py` — ampliar si se añaden municipios nuevos.
- Ejecutar anualmente en Q4 para el siguiente año.

### 2.4. Exportaciones (S006)

8 vistas de exportacion en `budgets/views.py`:
- Familia A (tarifas por aseguradora): InsurerTariffExportCsvView,
  InsurerTariffExportExcelView, InsurerTariffExportPdfView, InsurerTariffExportWordView.
  Ancladas en InsurerDetailView. Dropdown "Exportar tarifa" en cabecera.
- Familia B (historial presupuestos): BudgetExportCsvView, BudgetExportExcelView,
  BudgetExportPdfView, BudgetExportWordView.
  Ancladas en BudgetHistoryView. Dropdown "Exportar" en cabecera. Respetan filtros GET.

Librerias: openpyxl, weasyprint 68.1, python-docx 1.2.0. En requirements.in.

### 2.5. Panel de bases (S006)

CRUD completo de bases en InsurerDetailView:
- Vistas: BaseCreateView, BaseUpdateView, BaseToggleView, BaseDeleteView.
- Templates parciales HTMX: base_list_fragment.html, base_row_fragment.html,
  base_edit_fragment.html en budgets/templates/budgets/partials/.
- BaseDeleteView rechaza eliminacion si la base tiene presupuestos asociados.

### 2.6. Wizard actualizado (S006)

- Paso 1b: selector HTMX de base (BudgetBasesView). Si 1 base activa: input
  oculto automatico. Si >1: desplegable visible. Si 0: sin campo.
- Paso 6: casilla "Nocturno" (is_night, operario). Festivo calculado automaticamente
  por el motor segun service_date y base.labor_calendar.
- POST wizard: service_date se convierte a datetime.date antes de pasar al motor.

### 2.7. SDK actualizado (S006)

- google-genai: 1.69.0 → 2.7.0. Sin breaking changes en el codigo del proyecto.
- requirements.in: google-genai==2.7.0, weasyprint, python-docx añadidos.

### 2.8. Migraciones aplicadas en produccion

- 0001_initial, 0002_budget_apply_iva (manual), 0003-0006 (S003-S005).
- 0007_budget_is_night — S006: campo is_night en Budget.
- 0008_base_model — S006: modelo Base.
- 0009_budget_base_fk — S006: FK base en Budget.

### 2.9. Comandos de gestion disponibles

- `seed_insurer_tariffs` — carga tarifas 2026 (idempotente).
- `seed_bases` — crea registros Base desde Insurer.notes (idempotente, 74 bases).
- `sync_base_calendars` — sincroniza calendarios desde calendariosnacionales.com.
- Script SWAP: `seed_special_rate_tariffs.py` — tarifas especiales RACC/Zurich.
  Ejecutar tras reseed total de aseguradoras.

### 2.10. URLs activas

Wizard, vehicle_types, bases (HTMX), optional_concepts, result, status_update,
history, detail, budget_bulk_delete, insurer_list, insurer_create, insurer_update,
insurer_detail, insurer_toggle, insurer_delete, tariff_create, tariff_save_notes,
tariff_line_add_form, tariff_line_add, tariff_line_save, tariff_line_delete,
base_create, base_update, base_toggle, base_delete,
insurer_tariff_export_csv/excel/pdf/word, budget_export_csv/excel/pdf/word.

---

## 3. Hoja de Ruta

### Paso 0 — Actualizacion SDK google-genai a 2.7.0
- Estado: COMPLETADO (S006 — google-genai 1.69.0 → 2.7.0, sin breaking changes)

### Paso 1 — Recopilacion de datos y construccion de la skill
- Estado: COMPLETADO (S001)

### Paso 2 — Validacion de la skill con Miguel Angel
- Estado: COMPLETADO (S001)

### Paso 3 — Modelo de datos Django (app budgets)
- Estado: COMPLETADO (S001 — migracion 0001_initial)

### Paso 4 — Panel de gestion de aseguradoras y tarifas
- Estado: COMPLETADO (S003/S004/S005 — listado, acordeon, edicion inline HTMX,
  toggle, eliminacion modal, campos insurer_company_name/service_company_name,
  always_apply_iva, special_night_holiday_tariff, vista de detalle solo lectura)

### Paso 5 — Motor de generacion de presupuestos
- Estado: COMPLETADO (S001/S002/S005 — calculo completo, IVA persistido,
  SpecialRateTariff, always_apply_iva, surcharges_are_cumulative)

### Paso 6 — Wizard de presupuestos
- Estado: COMPLETADO (S001/S005/S006 — selector base HTMX, is_night separado
  de festivo automatico, service_date como datetime.date en motor)

### Paso 7 — Vista de resultado y estados
- Estado: COMPLETADO (S001/S002)

### Paso 8 — Configuracion de empresa (CompanySettingsView)
- Estado: COMPLETADO (S005)

### Paso 9 — Label dinamico wizard y mejoras UX
- Estado: COMPLETADO (S005)

### Paso 10 — Correcciones y ajustes menores
- Estado: COMPLETADO (S004)

### Paso 11 — Exportaciones del panel de aseguradoras
- Estado: COMPLETADO (S006 — CSV, Excel, PDF, Word para tarifas e historial)

### Paso 12 — Calendario laboral en presupuestos
- Estado: COMPLETADO (S006 — modelo Base, is_night, _is_holiday JSON,
  sync_base_calendars, seed_bases, 74 bases sembradas)

### Paso 13 — Integracion Google Maps Routes API
- Estado: PENDIENTE — movido a Hito 18 (Gestion de Mapas y Geolocalizacion)

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| S001   | 2026-05-26 | 1-5, 7          | Implementacion completa app budgets: modelos, motor, vistas, templates, rol ASSISTANCE, 23 tarifas 2026. |
| S002   | 2026-05-27 | 4 (parcial)     | IVA: apply_iva en Budget (migracion 0002 manual). Motor paso 8. result.html muestra base + total IVA. |
| S003   | 2026-05-27 | 4 (visor)       | Panel aseguradoras: listado HTMX, acordeon edicion, vistas tarifa inline. Correccion inputs decimal. |
| S004   | 2026-05-28 | 8 (parcial), 9 (parcial), 10 | is_insurance_company, operation_bases, labor_calendar migrados. Correccion banner WORKSHOP. |
| S005   | 2026-05-29 | 8, 9, 11 (parcial), nuevos pasos | Label dinamico wizard. CompanySettingsView. Reseed 32 aseguradoras. SpecialRateTariff/SpecialRateLine. Seed tarifas especiales RACC/Zurich. Motor: always_apply_iva, special_night_holiday_tariff. IVA persistido. BudgetBulkDeleteView. InsurerDetailView. Template tags. Locale decimal ES. |
| S006   | 2026-05-30 | 0, 11, 12       | SDK google-genai 1.69.0 → 2.7.0. Exportaciones CSV/Excel/PDF/Word tarifas e historial. Modelo Base (migraciones 007-009). Panel CRUD bases en InsurerDetailView. BudgetBasesView HTMX. Wizard: selector base + is_night separado. seed_bases (74 bases). sync_base_calendars. _is_holiday JSON. Paso 13 movido a Hito 18. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

Este hito queda COMPLETADO en todos sus pasos implementables.
El Paso 13 (Google Maps Routes API) se traslada integro al Hito 18.
No hay trabajo pendiente en este hito.
