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
  concept_code max_length=50 (migración 0022 — alineado con TariffConcept.code).
- `SpecialRateTariff`: tabla de tarifas especiales nocturno/festivo.
- `SpecialRateLine`: línea de precio especial.
- `Base`: base fisica de servicio. FK Insurer. Campos: name, municipality,
  latitude, longitude (nullable), labor_calendar (JSON ISO dates), calendar_synced_at,
  is_active. 74 bases sembradas via seed_bases (idempotente).

### 2.2. Motor de cálculo (`budgets/services.py`)

Función `calculate_budget(budget)` idempotente:

- Resuelve tarifa activa del insurer.
- Aplica líneas de tarifa según vehicle_type y concept.code.
- Gestiona recargos (NYF, loaded) según surcharges_are_cumulative.
- Soporta special_night_holiday_tariff (SpecialRateTariff).
- Soporta local_service_km_threshold (forfait SERVICE_LOCAL).
- Genera BudgetLine por cada concepto aplicado.

### 2.3. Wizard de presupuesto

- `BudgetWizardView`: wizard multi-step con HTMX. Pasos: selección aseguradora,
  datos del servicio, ruta, confirmación.
- `BudgetWaypointView`: endpoint HTMX que recibe waypoints y calcula ruta
  (Routes API v2 REST) devolviendo km, peajes y coste.
- `wizard_map.js`: mapa interactivo con Routes Library nativa (importLibrary('routes')).
  Dos rutas paralelas (avoidTolls: false/true) pintadas con createPolylines() +
  setOptions() + setMap(). Cards de selección de ruta. Bottom sheet móvil.
  Cálculo parcial cuando no hay vuelta a base (destino = último waypoint, no base).

### 2.4. Templates del wizard

- `_route_multileg_fragment.html`: modal del planificador de ruta. Footer con
  botones Cancelar/Calcular ruta/Confirmar fuera del row para que en móvil
  quede debajo del mapa sin taparlo. Panel 38vh scrollable (overflow-y auto !important
  para sobrescribir el visible del autocomplete PAC).

---

## 3. Decisiones Técnicas

- **Routes Library JS** (no REST fetch): elimina CORS, usa mismos credentials
  que la carga de Maps. `Route.computeRoutes()` acepta `{ lat, lng }` (LatLngLiteral),
  NO `{ location: { latLng: { latitude, longitude } } }` (formato REST).
- **travelMode: "DRIVING"** (no "DRIVE" — ese es el valor REST).
- **createPolylines()** no acepta parámetros: el estilo se aplica con
  `p.setOptions({strokeColor, strokeOpacity, strokeWeight, zIndex})` + `p.setMap(map)`.
- **Promise.all** con función `debugComputeRoutes()` que loguea request y respuesta
  en consola para diagnóstico en Eruda/DevTools.
- **BudgetLine.concept_code max_length=50**: migración 0022 corrige DataError
  (1406) causado porque TariffConceptCreateView genera códigos de hasta 40 chars
  pero el campo tenía max_length=30.

---

## 4. Trabajo Realizado

| Sesión | Fecha | Archivos | Descripción |
|---|---|---|---|
| S001   | 2026-05-25 | 10+ nuevos     | Creación app budgets, modelos Insurer/InsurerTariff/TariffLine/Budget/BudgetLine, migraciones 0001–0003, seed data, vistas CRUD aseguradoras, wizard presupuesto paso 1, templates base. |
| S002   | 2026-05-26 | 8+, correcciones | Motor de cálculo calculate_budget(), BudgetStepsView, wizard pasos 2 y 3, exportación PDF básica. |
| S003   | 2026-05-27 | 6+, mejoras     | Exportación Excel y Word. Recargos NYF y vehículo cargado. SpecialRateTariff y SpecialRateLine. Migraciones 0004–0007. |
| S004   | 2026-05-28 | 4+, correcciones | Fix motor recargos acumulables. Fix exportación. Migración 0008 Base model. |
| S005   | 2026-05-29 | 5+              | Integración base en wizard. BudgetWaypointView. TollSegment y geocode_toll_segments. Migraciones 0009–0011. |
| S006   | 2026-06-18 | 8+, correcciones | Fix filtro TariffLine FK. Fix coste peajes max(price_light, price_heavy_1, price_heavy_2). Migración 0019. TariffConcept FK sustituyendo CharField. Migración 0020. |
| S007   | 2026-06-19 | 14+, nuevos     | Corrección protocolos PEE y Comando S (6 skills). TariffConcept: modelo, migración 0021 (manual vía SQL), seed 12 conceptos sistema, migración datos 861 TariffLine + 100 SpecialRateLine. CRUD VehicleType (4 vistas + 3 fragmentos HTMX). TariffConceptCreateView (desde modal aseguradora). Página dedicada conceptos (TariffConceptListView + Create/Update/Delete). Enlace nav Asistencia. Botones agrupados en Panel 3 insurer_form.html. Vista detalle corregida (solo lectura). Limpieza clases TollSegment duplicadas. |
| S008   | 2026-06-20 | correcciones, mejoras UX | Resolución de 5 bugs: (1) HTTP 400 en creación de conceptos desde tariff_concept_list.html — inputs sin atributo name. (2) HTTP 400 en creación de VehicleType desde modal de insurer_form.html — mismo bug. (3) Layout roto al guardar edición inline de concepto/vehículo — swap outerHTML sustituido por window.location.reload() en tariff_concept_edit_fragment.html y vehicle_type_edit_fragment.html. (4) HTTP 500 al añadir línea de tarifa con concepto personalizado — _parse_decimal enterrada como código muerto dentro del docstring de _get_concept_choices, extraída y definida como función independiente en views.py. (5) Layout roto al añadir nueva línea — _tariff_line_add_form_fragment.html cambiado a hx-swap=none + reload. Reestructuración UX del panel de edición de aseguradora: botones Añadir concepto y Añadir tipo de vehículo eliminados de la cabecera de líneas; modal Añadir concepto eliminado (gestión centralizada en /panel/budgets/concepts/); botón Añadir tipo de vehículo movido al Panel 3b embebido en bloque de tipos de vehículo. Limpieza BD: 33 registros VehicleType de prueba eliminados via shell Django. |
| S009   | 2026-06-20 | Paso 1 HR S009 — calendarios laborales | CRUD de calendarios laborales por base: BaseCalendarView (listado global con conteo de festivos y fecha de última sincronización), BaseCalendarDetailView (gestión HTMX de fechas individuales: add con validación ISO, remove con confirmación hx-confirm). Fragmento HTMX calendar_dates_fragment.html con tabla de fechas y nombre de día en castellano. Filtro weekday_name añadido a budgets_extras.py. Rutas calendars/ y calendars/<int:pk>/ en urls.py. Entrada sidebar "Calendarios laborales" con icono bi-calendar3 y active_nav=budgets_calendars en _nav_items.html + registro en mapa NAV_TO_ACC del JS. Bugs resueltos durante pruebas: (1) FieldError insurer__company — Base tiene FK company directa, no insurer; corregido en BaseCalendarView y _get_base. (2) Iteración carácter a carácter del JSON — labor_calendar es TextField (no JSONField); añadida deserialización json.loads en lectura y json.dumps en escritura, igual que el resto del código existente. |
| S010   | 2026-06-20 | Correcciones, mejoras UX, investigación ruta dual | [1] Inspección fragmentos wizard: colores Leaflet ya implementados desde S009. Diagnóstico defecto grave responsividad. [2] Fix responsividad _route_calc_fragment.html (col-6→col-12 col-sm-6 ×4) y _route_dual_fragment.html (form-check-inline→d-flex flex-wrap). [3] Auditoría AP-46 (ID=62, tariff_level=SPECIAL, same_point=True, coordenadas OK). [4] Fix motor de peajes _compute_toll_cost: max(price_light, price_heavy_1, price_heavy_2) — AP-46: 6,00€→8,70€. [5] Diagnóstico 500 /panel/budgets/steps/: TariffLine.concept es FK, filtros usaban string. [6] Fix views.py: 4 filtros concept=<string>→concept__code=<string> (_tariff_has_concept, _get_optional_concepts, _has_loaded_surcharge, BudgetStepsView). [7] Refactorización wizard_map.js: DirectionsRenderer draggable:true + detección de entorno isMobileDevice() + bottom sheet móvil (Añadir parada / Pasar por aquí via:true) + dos llamadas paralelas DirectionsService (normal + avoidTolls:true). Investigación ruta dual: rutas se calculan correctamente pero pintar dos polylines con colores distintos pendiente — próxima sesión dedicada íntegramente a investigar el patrón correcto. Fix botón Calcular ruta (no se deshabilita con keepPolyline=true). Fix responsividad _route_multileg_fragment.html (panel 42vh scrollable, mapa 42vh, footer sticky). |
| S011   | 2026-06-20 | Investigación pura: ruta dual con dos polylines de color | Sesión íntegramente dedicada a investigación sin implementar nada. HALLAZGOS PRINCIPALES: (1) DirectionsService y DirectionsRenderer deprecados el 25/02/2026 — se descarta su uso futuro. (2) La API correcta es la Routes Library nativa de Maps JS API (importLibrary('routes')), que elimina problemas de CORS al ser un cliente JS integrado, no un fetch externo. (3) Route.computeRoutes() acepta routeModifiers: {avoidTolls: true/false} y soporta intermediates (waypoints). (4) createPolylines({polylineOptions: {strokeColor, strokeWeight, strokeOpacity, zIndex, map}}) permite colorear cada polyline directamente en la llamada — patrón confirmado en documentación oficial de rutas alternativas. (5) Las polylines resultantes son instancias estándar de google.maps.Polyline, compatibles con mapa RASTER (el wizard usa new google.maps.Map(div, {}) que es RASTER por defecto). (6) Compatibilidad móvil Chrome Android confirmada — no hay restricción de tipo de renderizado. (7) Routes API ya estaba habilitada en Google Cloud (verificado en captura de pantalla de la consola). No es necesario ningún cambio en infraestructura. Decisión final: implementar en S012 con Routes Library JS. |
| S013   | 2026-06-22 | budgets/services.py, panel/static/panel/js/wizard_map.js | Fix detección de pernocta (Pendiente 0 PRIORITARIO): diagnosticado bug en dos puntos — applyRouteSummary() en wizard_map.js activaba is_overnight en cuanto existía cualquier waypoint isBaseReturn, y compute_route_multileg() en services.py asignaba split_index igualmente. Corregido en ambos lados: is_overnight=True solo cuando tras el waypoint base-return existen paradas reales (not isVia, not isBaseReturn). Desplegado vía install_files + collectstatic + reload (200 OK). PCH H16→H12 al cierre. |
| S014   | 2026-06-23 | budgets/templates/budgets/_route_multileg_fragment.html, panel/static/panel/css/panel.css | Fix UX modal planificador de ruta en portátiles (Pendiente 0 URGENTE). Diagnóstico: .route-planner-panel-inner tenía overflow-y:auto pero la cadena overflow:visible!important impuesta para el PAC (Google Autocomplete) destruía el scroll en desktop; con muchas paradas el panel desbordaba empujando el resumen y los botones fuera del viewport. Solución: reestructuración en dos zonas dentro del panel — (1) .route-planner-panel-scroll (flex:1 1 auto; overflow-y:auto; min-height:0) contiene base, lista de paradas y buscador; (2) .route-planner-panel-summary (flex-shrink:0) contiene HR y resumen, siempre visible. El overflow:visible!important del PAC se acota a .route-planner-add en lugar de propagarse al panel completo. En móvil: .route-planner-panel-scroll limita a max-height:30vh con overflow-y:auto. Desplegado vía install_files + collectstatic + reload (200 OK). PCH H16→H20 al cierre. |
| S054   | 2026-06-24 | budgets/views.py, budgets/urls.py, budgets/templates/budgets/insurer_detail.html, budgets/templates/budgets/_route_multileg_fragment.html | **Desvio desde H17**. (1) InsurerCopyTariffView: nueva vista POST insurers/<pk>/copy-tariff/ que copia InsurerTariff activa + VehicleType + TariffLine + SpecialRateTariff + SpecialRateLine de aseguradora origen a aseguradora existente destino en transaccion atomica. Cierra tarifa activa destino (valid_to=hoy-1d). VehicleType sin Budget se eliminan; los con Budget se conservan. Ruta insurer_copy_tariff añadida a urls.py. Boton Copiar tarifa a... y modal #copyTariffModal añadidos a insurer_detail.html. InsurerDetailView: other_insurers añadido al contexto. Bugs corregidos durante pruebas: (a) AttributeError tariff_lines — related_name real es lines (TariffLine.tariff FK a InsurerTariff). (b) FieldError insurer en SpecialRateTariff — modelo usa OneToOneField a InsurerTariff (related_name special_rate), acceso correcto via source_tariff.special_rate; SpecialRateLine FK a SpecialRateTariff via related_name lines. (c) NameError logger — logger no existe en budgets/views.py, eliminado bloque de logging. (2) Fix critico modal planificador de ruta — boton Confirmar inaccesible en laptop y movil: reestructuracion CSS completa — modal-content como flex column max-height:calc(100vh-3.5rem), .route-planner-fragment como flex column flex:1 1 auto, row g-0 con flex:1 1 auto overflow:hidden, footer con position:relative z-index:5 siempre visible, eliminado overflow:visible!important en modal-content y route-planner-panel que causaba el desbordamiento. |
| S055   | 2026-07-02 | budgets/models.py, budgets/services.py, budgets/views.py, budgets/urls.py, budgets/templates/budgets/insurer_form.html, budgets/templates/budgets/tariff_pdf_review.html, budgets/templates/budgets/_wizard_steps_fragment.html, budgets/templates/budgets/detail.html, budgets/templates/budgets/result.html, panel/mixins.py, ivr_config/models.py, panel/templates/panel/_nav_items.html | **Desvío desde H10.** Sesión íntegra dedicada a H16 por desvío (H10 se mantuvo EN PROGRESO sin avance directo — ver anexo H10 S002). **(1) Importación de tarifa por PDF con catálogo dinámico:** nuevo modelo `TariffPdfImport` (migración `0028_tariffpdfimport`: insurer FK origen, insurer_copy FK nullable, pdf_file, extraction_raw JSONField, status PENDING_REVIEW/APPLIED/DISCARDED/ERROR). `TariffPdfExtractionService` en services.py — extracción Gemini Vision (`gemini-3.5-flash`) totalmente dirigida por datos: el prompt recibe el catálogo `TariffConcept` real (sistema + personalizados de la empresa) leído de BD en cada llamada, y decide por línea si emparejar con un concepto existente o proponer uno nuevo (esquema Pydantic `TariffPdfExtraction`/`ExtractedTariffLine` con `concept_code_match`/`concept_new_label`/`concept_new_unit`). Modo festivo condicionado por `insurer.special_night_holiday_tariff`: tabla completa vs. recargo porcentual único (`night_holiday_surcharge_percent`). Convención de pares de aseguradora `'CompañíaA - CompañíaB'` resuelta genéricamente en el prompt (sin hardcodear ningún nombre): extrae solo la columna de la primera compañía nombrada. `InsurerTariffPdfUploadView`: clona la aseguradora origen como `'<nombre> copia'` (mismo patrón que `InsurerCloneView`) antes de aplicar la extracción. `InsurerTariffPdfReviewView`: pantalla de revisión con conceptos coincidentes (laborable/festivo editables) + conceptos nuevos propuestos (checkbox "Crear este concepto", nombre/unidad editables) + recargo % si aplica. Botones únicos **Cancelar** (borra la copia completa — `SpecialRateTariff` eliminada explícitamente primero por ser `on_delete=PROTECT`, evita `ProtectedError`) y **Aceptar** (persiste, crea conceptos nuevos confirmados como `TariffConcept` de la empresa con código auto-generado). Botón "Actualizar con PDF" reubicado a la cabecera de `insurer_form.html` (antes enterrado en el acordeón de líneas). Bug preexistente corregido en `InsurerDeleteView` y en la acción Cancelar: mismo `ProtectedError` por no borrar `SpecialRateTariff` antes de la `Insurer`. **(2) Modo manual del wizard de presupuestos:** radio "Manual"/"Planificación de ruta" (Planificación de ruta por defecto) en `_wizard_steps_fragment.html`, mutuamente excluyente vía `toggleCalcMode()` en `panel/static/panel/js/wizard.js` (limpia campos del modo abandonado al cambiar). Tarjeta Manual agrupa: pregunta de pernocta (movida aquí desde fuera — en modo ruta se sigue detectando automáticamente por retorno a base), Km fase1/fase2, checkbox "¿Servicio nocturno/festivo?" y Peajes (importe total €). Nuevo campo `Budget.is_night_or_holiday_manual_override` (BooleanField null=True, migración `0029`) — cuando no es null sustituye por completo el cálculo automático de `is_night_or_holiday` en `calculate_budget()` (sin consultar calendario). Peaje manual reutiliza `route_toll_budget_cost` ya existente (el motor ya tenía fallback a línea única `TOLL_COST` cuando no hay `encoded_polyline`, que nunca la hay en modo manual). **(3) Control de acceso granular — usuario `juan.vazquez`:** nuevo campo `CompanyUser.can_view_budget_breakdown` (BooleanField, migración `ivr_config.0040`) — override por usuario, no por rol. Nuevo mixin `BudgetAuditAccessMixin` en `panel/mixins.py` (ADMIN siempre, o ASSISTANCE con el flag) aplicado a `BudgetHistoryView` y `BudgetDetailView` (antes `AdminRoleRequiredMixin`). `_nav_items.html`: enlace "Historial presupuestos" separado del bloque ADMIN-only (Aseguradoras/Bases/Conceptos/Calendarios siguen exclusivos de ADMIN). `result.html`: botón "Ver desglose completo" con la misma condición ampliada. Usuario `juan.vazquez` creado (User pk=38, CompanyUser pk=37, role=ASSISTANCE, can_view_budget_breakdown=True, contraseña permanente, must_change_password=False). **(4) Mapa de ruta en el desglose:** `detail.html` — tarjeta "Mapa de la ruta" (solo si `budget.encoded_polyline`), mismo bootstrap loader `importLibrary` que `wizard.html` (`v:"beta"` obligatorio), decodifica polyline(s) con `geometry.encoding.decodePath`, dibuja `Polyline` de solo lectura (sin edición, sin marcadores arrastrables) vía `google.maps.geometry`, colores distintos por fase en servicios de pernocta (separador `\x01`). Contexto `google_maps_api_key`/`google_maps_map_id` añadido a `BudgetDetailView`. Todos los cambios verificados con `py_compile`/`djlint`/`node -c` antes de entrega; incidente de corrupción de bundle en mitad de sesión (bundle sin marcadores de cierre reales) recuperado con `sftp put` directo archivo a archivo, sin pérdida de datos. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Pendientes H16 — para retomar cuando eb-annex-router marque H16 EN PROGRESO

#### Pendiente 0 — Validar en producción el modo manual del wizard (PRIORITARIO)

Implementado en S055 pero sin validación E2E real por Miguel Ángel/operarios.
Crear un presupuesto completo en modo Manual (Km + Nocturno/Festivo + Peajes)
y confirmar que el desglose ADMIN refleja correctamente
`is_night_or_holiday_manual_override` (recargo NYF aplicado solo cuando la
casilla está marcada, laborable normal en caso contrario, sin excepciones
del calendario) y que la línea `TOLL_COST` única muestra el importe manual
introducido.

#### Pendiente 1 — Validar importación de tarifa por PDF con conceptos nuevos reales

`TariffPdfImport`/`TariffPdfExtractionService` implementados y probados con
el PDF de RACC/Zurich (conceptos de remolcaje ya existentes). Falta probar
el flujo completo de conceptos nuevos (sección "Reparación in situ" del
mismo PDF u otro con estructura distinta): confirmar que el checkbox
"Crear este concepto" da de alta correctamente el `TariffConcept`
(código auto-generado, `is_system=False`, `company` correcta) y sus
`TariffLine`/`SpecialRateLine`, y que el concepto nuevo queda disponible
para el catálogo dinámico del prompt en la siguiente importación de esa
misma empresa.

#### Pendiente 2 — Copia de calendario laboral entre bases

**Necesidad:** cuando dos bases comparten el mismo calendario de festivos
(ej. Málaga y Maqueda), el operario debe poder copiar el calendario de una
base origen y pegarlo en una base destino desde el panel, sin tener que
introducir las fechas manualmente una a una.

**Flujo esperado en el panel:**
- En `BaseCalendarDetailView` (vista de detalle de calendario de una base):
  añadir un botón "Copiar de otra base" que abra un selector de base origen.
- Al confirmar, sobrescribir el `labor_calendar` de la base destino con el
  `labor_calendar` de la base origen (JSON list de fechas ISO).
- Confirmar con un modal de advertencia ("¿Seguro? Se sobrescribirá el
  calendario actual de esta base.") antes de ejecutar.

**Archivos a revisar al inicio de sesión:**
- `budgets/views.py` — `BaseCalendarDetailView` y vistas auxiliares de
  calendario (BaseCalendarAddDateView, BaseCalendarRemoveDateView).
- `budgets/templates/budgets/base_calendar_detail.html` — template del
  detalle de calendario.
- `budgets/urls.py` — rutas de calendarios.

**Nueva vista a crear:**
- `BaseCalendarCopyView` — POST `/panel/budgets/calendars/<pk>/copy/`
  Recibe `source_base_id` por POST. Valida que la base origen tenga
  calendario. Copia `labor_calendar` de origen a destino. Devuelve
  fragmento HTMX con el calendario actualizado y mensaje de confirmación.
  Requiere `AdminRoleRequiredMixin`.

#### Pendiente 3 — Auditoría completa BREAKDOWNS smoke test
Ejecutar el flujo completo de creación de presupuesto E2E con varias
aseguradoras y tipos de vehículo para detectar errores residuales del motor
de cálculo.

#### Pendiente 4 — Export templates
Sistema de plantillas de exportación en dos niveles: global/admin vs
personal/supervisor con auto-copia en edición.

---

## Registro adicional — Desvío desde H12 (2026-06-22)

**Fix VehicleType drag & drop — eliminación del ordinal manual:**
El campo `sort_order` de `VehicleType` era editable manualmente (input numérico
en create y update), generando confusión en el desplegable de tipos de vehículo.
Solución completa:
- `VehicleTypeCreateView` (`budgets/views.py`): `sort_order` automático `max+1`,
  eliminado del POST. Propagación global (flag `globalize`) también usa max+1 por aseguradora.
- `VehicleTypeUpdateView`: ya no toca `sort_order` al editar (solo `name`).
- `VehicleTypeReorderView` (nueva): POST JSON `{insurer_pk, pks:[...]}`, persiste
  orden atómicamente en transacción. URL nueva `vehicle_type_reorder`.
- `vehicle_type_list_fragment.html`: sin columna "Orden", JS drag & drop HTML5 nativo.
- `vehicle_type_row_fragment.html`: sin celda `sort_order`, `draggable=true`,
  `data-pk`, handle `bi-grip-vertical`.
- `vehicle_type_edit_fragment.html`: solo campo `name`, `colspan=2`.
- `insurer_detail.html`: eliminada columna "Orden" de tabla solo lectura.

Archivos: `budgets/views.py`, `budgets/urls.py`, 3 templates partials,
`budgets/templates/budgets/insurer_detail.html`.

---

## Registro adicional — Desvío desde H07 (2026-06-22)

**Fix night_schedules en InsurerUpdateView:**
`InsurerUpdateView.get` construía el queryset `night_schedules` pero no lo
incluía en el dict de `_build_base_context`. El selector de horario nocturno
en `insurer_form.html` / `_insurer_fields_partial.html` iteraba
`{% for s in night_schedules %}` sobre una variable vacía — solo aparecía
el placeholder "Usar horario por defecto de la empresa".
Fix: añadido `'night_schedules': night_schedules` al dict del return.
Archivo: `budgets/views.py`. py_compile OK. Reload vía panel web PA OK.

---

## Registro adicional — Desvío desde H07 (2026-07-02, sesión S_H07_06)

**[1] Fix `ProtectedError` en `InsurerCopyTariffView` (copy-tariff):**
`POST /panel/budgets/insurers/<pk>/copy-tariff/` fallaba con `ProtectedError`
al intentar borrar `VehicleType` del destino referenciados por
`SpecialRateLine.vehicle_type` (`on_delete=PROTECT`) — el check previo al
borrado solo comprobaba `old_vt.budgets.exists()`, sin comprobar
`special_rate_lines` ni `work_orders_assistance` (`WorkOrderAssistance.vehicle_type`,
también `PROTECT`). Además, `TariffLine.vehicle_type` usa `CASCADE`: si el
borrado llegaba a completarse, arrastraba en cascada las `TariffLine`
históricas de tarifas ya cerradas del mismo `VehicleType`, con pérdida de
histórico. Decisión de diseño acordada con Miguel Ángel: eliminar la clase
de bug de raíz, no parchear los checks — `InsurerCopyTariffView.post()`
reescrito para fusionar el catálogo `VehicleType` por nombre exacto
(recortado) en vez de borrar y recrear: nombres coincidentes se reutilizan
en sitio (`sort_order`/`is_active` actualizados, sin tocar ninguna FK);
nombres del destino ausentes en el origen se desactivan (`is_active=False`),
nunca se borran, y se reportan en el mensaje de éxito
(`"Se han desactivado N tipo(s) de vehículo no presentes en la tarifa
origen: ..."`). Mismo criterio aplicado a `VehicleTypeDeleteView` (botón
manual "Eliminar" del catálogo): pasó de `vt.delete()` real (con los mismos
checks incompletos) a `vt.is_active = False` — sin ninguna comprobación de
integridad referencial, porque ya no puede fallar por PROTECT al no
borrarse ninguna fila nunca. Confirmado en real por Miguel Ángel: búsqueda
+ borrado desde el listado funciona, y `copy-tariff` de la aseguradora
recién actualizada por PDF hacia las otras cuatro (RACC, Zurich, Zurich
RACC) sin incidencias. Archivo: `budgets/views.py`.

**[2] Fix 405 al borrar aseguradora tras búsqueda HTMX en el listado:**
`POST /panel/budgets/insurers/` devolvía 405 al borrar una aseguradora
desde el listado tras usar el buscador/filtro live. Causa raíz:
`_insurer_table_fragment.html` enganchaba el modal de confirmación de
borrado (`#deleteModal`, evento `show.bs.modal`) dentro de
`document.addEventListener("DOMContentLoaded", ...)`. Ese fragmento se
recarga vía HTMX en cada búsqueda/filtro
(`hx-target="#insurer-table-wrapper"`), pero `DOMContentLoaded` solo
dispara una vez por navegación completa — tras cualquier recarga HTMX el
modal nuevo quedaba sin el listener, `form#delete-insurer-form` mantenía
`action=""` de fábrica, y el submit caía en la URL actual (`insurer_list`,
que no acepta POST). Fix: listener movido a `insurer_list.html` (se carga
una sola vez por navegación completa), delegado sobre `document.body`
(`document.body.addEventListener("show.bs.modal", ...)` filtrando
`event.target.id === "deleteModal"`) — sobrevive a cualquier número de
recargas HTMX del fragmento porque `document.body` nunca se sustituye.
Script duplicado eliminado de `_insurer_table_fragment.html`. Confirmado
en real por Miguel Ángel. Archivos:
`budgets/templates/budgets/insurer_list.html`,
`budgets/templates/budgets/_insurer_table_fragment.html`.

Ambos fixes: `py_compile`/`djlint` sin errores nuevos, `install_files` OK,
reload `200 {"status":"OK"}`. H16 no se puso EN PROGRESO — se atendió por
desvío mientras H07 era el hito EN PROGRESO; su hoja de ruta (sección 5)
no cambia, ninguno de los dos fixes formaba parte de los Pendientes 0-4
ya listados.
