# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md
# Hito 18 - Gestion de Mapas y Geolocalización (Modo B: Ruta por Carretera)

## Estado de Tareas

### COMPLETADAS EN S001
- Migracion 0011: campos latitude, longitude en Base.
- BaseGlobalView: integracion Leaflet + Nominatim, pin draggable, guardado de coordenadas.
- Admin Base: campos latitude/longitude en readonly_fields.

### COMPLETADAS EN S002
- Campos de ruta en modelo Budget: road_name, pk_km, route_distance_km, route_toll_cost, route_calculation_mode, service_time.
- Migracion 0012 aplicada.
- BudgetRouteCalcView: endpoint HTMX POST, integracion Routes API.
- calculate_route() en budgets/services.py: geocodificacion Geocoding API + Routes API TRAFFIC_AWARE + extraccion distancia + deteccion de peajes has_tolls.
- _route_calc_fragment.html: fragmento de resultado con base origen, destino, distancia, indicador de peajes.
- BudgetStepsView: endpoint HTMX GET, resuelve pasos 3-9 server-side.
- _wizard_steps_fragment.html: pasos 2b fecha+hora, 3, 4a, 4b condicional, 5, 6, 7, 8 + submit.
- _base_selector_fragment.html: HTMX encadenado.
- _vehicle_types_fragment.html: HTMX encadenado.
- wizard.html: PASO 1 estatico + tres contenedores HTMX.
- wizard.js: JS minimo - toggleOvernightFields, toggleRouteCalc, calcularRuta, bloqueo IVA, init F5, reset downstream.
- ManifestStaticFilesStorage activado en settings.py.
- urls.py: rutas steps/, route-calc/, vehicle-types/, bases/.
- BudgetWizardView.post(): km_phase1 opcional en Modo B, service_time desde campo 2b, validacion service_datetime futuro.

### COMPLETADAS EN S003
- Refactorizacion completa del wizard: arquitectura HTMX encadenado puro.
- Fix POST calcularRuta(): objeto plano en lugar de Object.fromEntries(FormData).
- Fix F5: DOMContentLoaded dispara change en id_insurer si tiene valor preseleccionado.
- Fix reset downstream: htmx:afterSwap limpia secciones al cambiar base o aseguradora.
- routingPreference TRAFFIC_AWARE en Routes API.
- has_tolls en calculate_route() y en el fragmento de resultado.
- Fecha del servicio movida al PASO 2b.
- service_time como campo directo del PASO 2b.
- Validacion service_datetime futuro en BudgetRouteCalcView.
- Mensajes Django en wizard.html.

### COMPLETADAS EN S010
- Tabla TollSegment: ordenacion client-side por todas las columnas con iconos
  neutrales/ascendente/descendente. Anchos de columna fijos via clases CSS
  ts-col-* en panel.css. 0 errores djlint: form huerfano H025 resuelto
  (action condicional inline), inline styles eliminados de los <th>.
- Filas alternas en gris #e9ecef sobre <td> via selector CSS con especificidad
  suficiente para superar a Bootstrap.
- Horarios nocturnos centralizados en aseguradoras: helper _resolve_night_schedule()
  en budgets/services.py — prioridad insurer.night_schedule, fallback is_default
  de la empresa. service_time obligatorio en el wizard. Checkbox manual is_night
  eliminado. Card "Franja horaria nocturna" eliminada de settings.html.
- Fondo verde menta #f0fdf4 en .form-control y .form-select del panel (UX global).

### COMPLETADAS EN S008
- Modelo NightSchedule creado en budgets/models.py con campos: company (FK Company),
  name, night_start, night_end, is_default, is_active, created_at, updated_at.
  Método save() impone restricción de único is_default=True por empresa.
- FK night_schedule (nullable) añadida al modelo Insurer.
- Migración 0017_add_night_schedule aplicada correctamente.
- Comando seed_night_schedules creado y ejecutado: dos horarios sembrados
  (22:00-07:00 y 20:00-08:00), ambos is_active=True, primero is_default=True.
- BudgetNightScheduleListView + BudgetNightScheduleUpdateView: CRUD completo
  accesible desde /panel/budgets/night-schedules/.
- Lógica nocturna refactorizada: is_night_or_holiday calculado server-side
  comparando service_time con el horario activo de la aseguradora.
  Checkbox manual eliminado del wizard. Campo is_night_or_holiday eliminado
  del formulario.
- Fix HTMX: reset de #vehicle-type-section y #wizard-steps-section al
  cambiar de aseguradora o base (el campo 2b depende de ambas selecciones).

### COMPLETADAS EN S011
- Planificador de ruta multi-parada (Modo B): modal Bootstrap fullscreen
  con mapa Google Maps, lista de paradas drag-and-drop, botones Calcular ruta /
  Confirmar y usar esta ruta / Cancelar.
- Modelo de paradas: array de objetos {label, address, lat, lng, is_base_return}.
  is_base_return=True marca el retorno intermedio a base (punto de pernocta).
- wizard_map.js: inicialización lazy del mapa (shown.bs.modal), addWaypoint(),
  renderStopList(), updateMap() con Polyline y Markers, confirmRoute() que vuelca
  km_phase1, km_phase2, is_overnight, waypoints_json, route_toll_budget_cost
  en hidden inputs del wizard.
- _route_multileg_fragment.html: UI del modal con lista de paradas, mapa,
  resumen de ruta (distancia, pernocta, peajes) y botones de acción.
- BudgetWaypointView: endpoint POST /panel/budgets/waypoints/ que llama a
  calculate_route_multileg() y devuelve JSON con km, encoded_polyline, peajes.
- calculate_route_multileg(): orquesta 1 o 2 llamadas a Routes API según
  presencia de is_base_return. Soporta pernocta con dos fases independientes.
- TollSegment: campo markup_percent añadido (migración 0023). Modelo completo
  con CRUD en TollSegmentListView + TollSegmentCreateView, tabla ordenable,
  configuración global (toll_vehicle_type, toll_markup_percent) en Company.
- import_toll_segments.py + toll_segments.json: 8 tramos reales AP-7 y AP-46
  con precios oficiales MITMA 2026. Total BD: 424 tramos.

### COMPLETADAS EN S012
- Polyline drag-and-drop en wizard_map.js: Polyline editable con listener
  dragend sobre cada vértice. Preview en tiempo real de la ruta modificada
  via throttled computeRoutes() (200ms). Coordenada raw con fallback (Roads
  API snapToRoads descartada por restricción CORS en browser keys).
- Migración completa de Leaflet/OpenStreetMap a Google Maps Platform en
  _route_dual_fragment.html: mapa de previsualización dual migrado.
- Campos de temporada alta en TollSegment: price_light_high, price_heavy_1_high,
  price_heavy_2_high, season_high_start, season_high_end. Migraciones 0024 y
  0025 aplicadas. Motor _compute_toll_cost actualizado con lógica de temporada.
  TollSegmentForm incluye los 5 campos nuevos. Formulario en dos columnas
  temporada baja/alta. import_toll_segments.py ampliado. toll_segments.json
  con precios oficiales MITMA 2026 temporada alta/baja.
- 8 tramos AP-7 y AP-46 con precios reales: 6 creados + 2 actualizados.
- Recargo global toll_markup_percent en Company operativo en _compute_toll_cost.

### COMPLETADAS EN S013

- **Migración Places API (`PlaceAutocompleteElement`):** `google.maps.places.Autocomplete`
  (deprecated 01/03/2025) sustituida por `PlaceAutocompleteElement` en
  `wizard_map.js`. Evento `gmp-placeselect` → `gmp-select` (corrección tras
  diagnóstico con Eruda). `event.placePrediction.toPlace()` + `fetchFields()`
  para obtener coordenadas. `<input id="route-place-search">` sustituido por
  `<div id="route-place-search">` contenedor en `_route_multileg_fragment.html`.
  Clase CSS `.route-planner-row` para sustituir inline style eliminado (fix H021
  djlint). 2× blanks extra eliminados (fix H014).

- **Función `_is_holy_week(d)`** añadida a `budgets/services.py`. Algoritmo
  Butcher/Meeus — sin dependencias externas. Rango: Viernes de Dolores
  (Pascua − 15 días) a Domingo in Albis (Pascua + 7 días), ambos inclusive.
  Integrada en `_compute_toll_cost` como segundo criterio de temporada alta
  cuando no hay rango estacional activo en el tramo.

- **`_compute_toll_cost` refactorizada** — devuelve `list[dict]` con campos:
  `segment_name` (`"road_code | origin → dest"`), `vehicle_type_label`
  (`"Ligero"/"Pesado 1"/"Pesado 2"`), `price` (Decimal base sin recargo),
  `is_high_season` (bool), `season_type` (`"VERANO"/"SEMANA_SANTA"/None`).
  Dos llamadas en `calculate_route_multileg` (tramo simple y pernocta)
  actualizadas para sumar `d["price"]` de la lista.

- **`_build_toll_budget_lines(toll_details, markup_percent, sort_order_start)`**
  nueva función en `budgets/services.py`. Genera `BudgetLine` (no guardadas)
  por tramo con código `CODE_TOLL_SEGMENT` y etiqueta completa:
  `"road_code | origin → dest (Pesado 1) — Temp. alta (verano)"` /
  `"— Temp. alta (Semana Santa)"` / `"— Temp. baja"`.
  Línea adicional `CODE_TOLL_MARKUP` si `markup_percent > 0`.
  Devuelve `(lines, total_with_markup)`.

- **`TariffConcept`** en `budgets/models.py`: constantes `CODE_TOLL_SEGMENT`
  y `CODE_TOLL_MARKUP` añadidas.

- **`TollSegment.markup_percent` eliminado (Opción A):** campo por-segmento
  eliminado de `budgets/models.py`. Migración `0026_remove_tollsegment_markup_percent`
  aplicada. `TollSegmentForm` en `views.py` actualizado.

- **Campo `encoded_polyline` en `Budget`:** `TextField(null=True, blank=True)`
  añadido a `budgets/models.py`. Migración `0027_budget_encoded_polyline` aplicada.
  `confirmRoute()` en `wizard_map.js` vuelca `data.encoded_polyline` al hidden
  input `id_encoded_polyline` (añadido a `_wizard_steps_fragment.html`).
  `BudgetWizardView.post()` en `views.py` recoge el campo y lo guarda en `Budget`.

- **`calculate_budget()` refactorizada** — bloque TOLL_COST sustituido por
  lectura de `budget.encoded_polyline`, split por `\x01` (pernocta = dos polylines),
  cruce con `TollSegment` via `_compute_toll_cost()` y volcado de
  `_build_toll_budget_lines()`. Fallback a línea única TOLL_COST si no hay
  polyline almacenada (presupuestos legacy).

- **`BaseCalendarCopyView`** añadida a `budgets/views.py`. URL
  `budgets:base_calendar_copy` (`calendars/<pk>/copy-calendar/`) en `urls.py`.
  `BaseCalendarDetailView.get()` pasa `other_bases` al contexto. Card de copia
  en `base_calendar_detail.html` con selector de base destino y botón "Copiar
  a esta base".

- **Fix `TollSegmentConfigView`:** `Decimal` no importado en ámbito local →
  sustituido por `from decimal import Decimal as _Decimal` en bloque try/except.

- **Fix datos AP-46:** PK:62 (`SPECIAL`, sin temporada, sin coordenadas legacy)
  desactivado. PK:424 (`NORMAL`, temporada alta 01/05→31/10) geocodificado con
  coordenadas de PK:62. Ahora el motor detecta correctamente el tramo y aplica
  7,30€ (Pesado 1, temporada alta verano) en lugar de 6,00€ legacy.

- **Skills de sesión actualizadas:**
  - `v00-standards`: prohibición absoluta de fragmentos de archivo (excepción:
    logs via tail). Limpieza previa `rm -f` antes de cada GET.
  - `v01-edit`: directriz del tail eliminada; regla de adiciones al final via
    str_replace desde workspace; excepción tail para logs documentada.
  - `v00-file-request`, `v00-bash-commands`, `v00-reload`: limpieza previa
    `!rm -f` incorporada en todas las cajas GET de los formatos Android y PC.
  - `v01-edit`: directriz obsoleta "re-solicitar archivo tras PUT" eliminada.

---

### COMPLETADAS EN S014

**Desvío — Rediseño completo del sistema de períodos de trabajo (WorkPeriodGroup)**

- **Modelo `WorkPeriodGroup`** creado en `ivr_config/models.py`:
  campos `company` (FK), `label`, `start_date`, `end_date`, `is_closed`,
  `created_by`, `created_at`, `updated_at`. FK `group` (nullable, SET_NULL)
  añadida a `WorkPeriod`. Migración `0039_workperiodgroup_workperiod_group`
  generada y aplicada sin incidencias.

- **Vistas nuevas** en `panel/views_workorders.py` — 6 clases activas:
  - `WorkPeriodGroupDetailView` — `/panel/work-periods/<pk>/`
  - `WorkPeriodGroupCreateView` — `/panel/work-periods/create/`
  - `WorkPeriodGroupAddOperatorView` — `/panel/work-periods/<pk>/add-operator/`
  - `WorkPeriodGroupCloseView` — `/panel/work-periods/<pk>/close/`
  - `WorkPeriodGroupLockView` — `/panel/work-periods/<pk>/lock/`
  - `WorkPeriodLockView` — `/panel/work-periods/operator/<pk>/lock/` (toggle individual ADMIN)

- **Vistas eliminadas:** `WorkPeriodListView`, `WorkPeriodCreateView`,
  `WorkPeriodCloseView`, `WorkPeriodOperatorAddView`, `WorkPeriodGroupListView`.
  Sus rutas y re-exports en `panel/urls.py` y `panel/views.py` también eliminados.

- **TAB 5 "Períodos"** de `admin_history.html` reescrito: una fila por
  `WorkPeriodGroup` con columnas Etiqueta / Inicio / Fin / Estado / Operarios
  (N/total con aviso visual si faltan) / Acciones (Ver/Gestionar, Liquidar).
  Modal legacy `#modalWorkPeriodCreate` y `#modalWorkPeriodClose` sustituidos
  por `#modalCreatePeriodGroup` que POST a `work_period_group_create`.

- **`WorkOrderAdminHistoryView`** actualizada: bloque `period_operator_groups`
  (por operario) sustituido por `period_groups` (lista de `WorkPeriodGroup`
  con `operator_count` y `total_operators`).

- **Template `work_period_detail.html`** (neonato): cabecera de grupo,
  tabla de operarios asignados con estado individual y toggle ADMIN,
  panel de operarios disponibles, modal "Añadir operario" y modal
  "Liquidar periodo". Modales dentro de `{% block content %}` para
  evitar error Bootstrap backdrop.

- **Script de migración de datos legacy** `migrate_work_period_groups.py`
  ejecutado en SWAP: 2 grupos creados (`Mayo-Junio 2026`, `Junio-Julio`),
  8 periodos vinculados.

- **Fix `NoReverseMatch`:** referencias a `work_period_group_list`
  en template y vista sustituidas por
  `{% url 'panel:work_order_admin_history' %}?tab=periods`.

- **Fix Bootstrap modal:** modales movidos dentro de `{% block content %}`
  para que Bootstrap los inicialice correctamente tras la carga del bundle JS.

- Validado en producción: `/panel/work-periods/` devuelve 404 (ruta eliminada).
  Pestaña "Períodos" muestra 2 grupos. Detalle abre correctamente. Modal
  "Añadir operario" funcional.

**Tarea 0 — Fix pausa comida jornada partida**

- **Bug identificado:** `WorkOrderEntryFormView.post()` en
  `panel/views_operator.py` reconstruía `_post_lb_start`/`_post_lb_end`
  desde el schedule de BD, sobreescribiendo los valores del POST en el
  re-render tras error de validación.
- **Fix:** dos líneas añadidas tras el bloque del schedule para sobreescribir
  con los valores del POST cuando `_lb_start_raw`/`_lb_end_raw` están presentes.
- Desplegado y recargado (200 OK). **Pendiente validación** con Antonio
  Fontalba cuando vuelva de vacaciones.

**Tarea 1 — Auditoría AP-7 (PARCIAL — bloqueada por geocodificación)**

- Auditados los 8 tramos reales de la BD con `price_heavy_1_high > 0`:
  ID 424 (AP-46), IDs 5, 10, 419, 420, 421, 422, 423 (AP-7).
- Diagnóstico: IDs 5 y 10 tienen coordenadas `39.4592, -0.5526` (Valencia,
  incorrectas). IDs 419-423 sin coordenadas. Ninguno de los 7 tramos AP-7
  matchea actualmente en rutas reales Costa del Sol.

---

### COMPLETADAS EN S018

**Resolución definitiva: autocompletado del planificador roto (desvío
desde sesión H10/S001) — sustitución de PlaceAutocompleteElement**

- **Contexto:** desvío completo desde una sesión de H10 (S001) al
  reportarse de nuevo el planificador de ruta roto — mismo síntoma que
  la incidencia S016 (autocompletado y fondo del modal). Diagnóstico
  empírico exhaustivo realizado de principio a fin antes de tocar
  código, según el mandato de "Primer acto" dejado en S017.

- **Hallazgos del diagnóstico (todos verificados con evidencia
  directa, no asumidos):**
  - `git diff` contra commit `f2f9c0c` (el de recuperación de S016) en
    `budgets/views.py`: vacío. El código fuente no había cambiado
    desde entonces — descartado `views.py` como causa, pese a la
    sospecha inicial.
  - Fondo negro del campo: causa raíz real fue que Google introdujo
    respeto automático al modo oscuro del sistema en
    `PlaceAutocompleteElement` (release notes Maps JS API, ~junio
    2026). Fix aplicado: `color-scheme: light` en el selector CSS.
    Corrige el color pero NO el autocompletado en sí (eran dos
    síntomas con causas distintas).
  - Panel de Google Cloud: `Places API (New)` habilitada, 380
    peticiones/30 días. Pestaña Network del navegador: peticiones
    `AutocompletePlaces` con `200 OK` y payload de datos reales al
    escribir. Esto descartó: API no habilitada, restricciones de key,
    cuota agotada, facturación.
  - Script de diagnóstico en consola: `importLibrary("places")` OK,
    `PlaceAutocompleteElement` disponible, instancia de prueba creada
    sin error. Descartado error de JS antes de inicializar.
  - Canal de carga `v: "weekly"` → cambiado a `v: "beta"`
    (`PlaceAutocompleteElement` documentado como disponible solo en
    canal beta/alpha). Cambio aplicado y verificado en servidor — no
    resolvió el síntoma por sí solo.
  - Outer HTML completo de `panel/base.html` solicitado y revisado:
    `{% block extra_head %}{% endblock %}` vacío en la plantilla
    padre, sin script de Maps duplicado. Descartada la hipótesis de
    doble carga del script.
  - Inspección del Shadow DOM con "Show user agent shadow DOM"
    activado en DevTools: el `<input>` interno del componente vive en
    un Shadow Root que se comporta como cerrado a efectos prácticos
    (`gmpEl.shadowRoot` inaccesible desde JS externo en todos los
    intentos). El listbox de predicciones no se localizó dentro de la
    estructura accesible del shadow root del input — el componente
    recibía el texto (`aria-expanded` alternaba true/false según
    interacción) pero nunca renderizaba el panel de sugerencias
    visible.
  - Intento de reposicionamiento del campo fuera de
    `.route-planner-panel-scroll` (hipótesis de overflow recortando
    el dropdown): revertido — no solo no resolvió el problema sino
    que rompió el layout visual. Lección: el Shadow DOM cerrado hace
    inviable diagnosticar con certeza el comportamiento interno del
    componente; cualquier fix sobre el HTML/CSS externo es
    especulación sin poder verificar el efecto real dentro del shadow
    root.

- **Decisión final adoptada:** abandonar `PlaceAutocompleteElement`
  (Web Component oficial de Google) y sustituirlo por una
  implementación propia usando la API programática
  `AutocompleteSuggestion.fetchAutocompleteSuggestions()` +
  `AutocompleteSessionToken`, con un `<input>` y un `<ul>` de
  sugerencias construidos en HTML normal, fuera de cualquier Shadow
  DOM. Esto da control total sobre el renderizado y el debugging.

- **Implementación (`panel/static/panel/js/wizard_map.js`):**
  - `searchContainer.innerHTML` limpiado; se inyectan `inputEl`
    (`#route-place-input`, con `id`/`name` propios — soluciona
    también el warning de accesibilidad de autofill que tenía el
    `<input>` del Shadow DOM cerrado, sin `id` ni `name` accesibles)
    y `dropdownEl` (`#route-place-listbox`, `<ul role="listbox">`).
  - `dropdownEl` movido a `document.body` con `position: fixed`
    calculado dinámicamente por `positionDropdown()`
    (`getBoundingClientRect()` del input) en cada apertura — evita
    por diseño cualquier recorte por `overflow:scroll/hidden` de
    contenedores ancestros, sin necesidad de reestructurar el HTML
    del template (lección de la reversión anterior).
  - Debounce de 250ms en el listener `input`, con `requestId`
    incremental para descartar respuestas de peticiones obsoletas si
    el usuario sigue escribiendo.
  - `AutocompleteSessionToken` renovado tras cada selección completa,
    siguiendo la recomendación de Google para agrupar correctamente
    la facturación por sesión de autocompletado.
  - `selectSuggestion()`: `suggestion.placePrediction.toPlace()` +
    `fetchFields({fields: ["location", "displayName"]})`, igual
    patrón de datos que el `PlaceAutocompleteElement` original — sin
    cambios en `addWaypoint()` ni en el resto del flujo del
    planificador.
  - Cierre del dropdown: click fuera del contenedor, tecla Escape.

- **CSS (`_route_multileg_fragment.html`):** bloque
  `gmp-place-autocomplete` eliminado por completo. Nuevas clases
  `.route-place-search-custom`, `.route-place-input` (fondo verde
  menta `#f0fdf4`, igual paleta que el intento anterior),
  `.route-place-dropdown-fixed` (`z-index: 1090`, por encima del
  z-index estándar de un modal Bootstrap 5 — `1055`),
  `.route-place-dropdown-item` (hover en verde menta).

- **Validación:** confirmado funcionando en producción por Miguel
  Ángel tras hard refresh — autocompletado y color correctos
  simultáneamente.

- **Deuda/nota para el futuro:** si Google publica una corrección
  para `PlaceAutocompleteElement` y se quisiera volver al Web
  Component oficial más adelante, esta sesión deja documentado que la
  causa de fondo nunca llegó a confirmarse con certeza absoluta — el
  Shadow DOM cerrado impidió ver el motivo exacto del fallo de
  renderizado del listbox. No reintentar sin una herramienta de
  diagnóstico mejor (p. ej. una build de Chrome con shadow DOM
  abierto a nivel de flag, no solo de DevTools) o confirmación
  explícita de Google de que el bug se ha corregido.

---

### COMPLETADAS EN S017

**Recuperación planificador de ruta + auditoría motor de peajes**

- **Incidencia crítica S016 resuelta:** diagnóstico empírico completo (logs Django,
  git diff, wizard_map.js, views.py). Causa raíz: `collectstatic` no ejecutado tras
  revert `cb83247`. Ejecutado `collectstatic` (146 archivos) + reload 200 OK.
  Planificador recuperado y verificado visualmente en producción.

- **Recuperación trabajo S014 (WorkPeriodGroup):** el revert `git checkout f2f9c0c -- .`
  había pisado 7 archivos del commit `cb50c0a`. Recuperados via `git checkout cb50c0a`
  sobre `ivr_config/models.py`, `panel/views_workorders.py`, `panel/views.py`,
  `panel/urls.py`, `panel/views_operator.py`, `admin_history.html`,
  `work_period_list.html`. Collectstatic + reload 200 OK. Commit `b301bd3` pusheado.

- **Auditoría motor peajes `budgets/services.py`:**
  - `_is_holy_week()`: correcto — algoritmo Butcher/Meeus, ventana Viernes de
    Dolores (Pascua−15d) hasta Domingo in Albis (Pascua+7d).
  - Temporada alta: correcto — comparación `(month, day)` sin año, cascada
    VERANO → SEMANA_SANTA. `season_type` devuelve valor correcto en cada caso.
  - Matching cabinas punto único: correcto — SNAP_KM=1.5, `same_point` detectado
    por diferencia < 0.0001 en lat/lng.
  - Gratuidad nocturna AP-46: campo `has_free_night=True`, `free_night_start=00:00`,
    `free_night_end=06:00` en BD. **No implementada en `_compute_toll_cost()`.**
    Decisión: aplaza implementación — Grupo Álvarez opera con Pesado 2 y la
    gratuidad nocturna AP-46 es exclusiva de ligeros (verificado en PDF oficial
    Ministerio de Transportes 2026). Sin impacto funcional para el caso de uso real.

- **Validación E2E parcial:** presupuesto real creado con ruta que pasa por AP-46.
  Motor detecta `AP-46 | Casabermeja → Casabermeja` (Pesado 2, temporada alta
  verano, 11,35 €). Recargo 5% aplicado correctamente.

- **BD TollSegment confirmada:** 4 cabinas activas, coordenadas correctas,
  precios baja/alta verificados empíricamente.

- **eb-annex-router corregido:** H10 estaba marcado EN PROGRESO incorrectamente
  tras la sesión perdida. Corregido a H18 al inicio de S017.

---

### INCIDENCIA CRÍTICA S016 — Planificador de ruta roto

Durante el cierre de S016 se entregó `budgets/views.py` via bundle
(EnterpriseBot_021_PUT.txt) usando como base el archivo descargado al
inicio de sesión (`EnterpriseBot_016_GET.txt`), que era una versión
anterior a los cambios de S013 (`PlaceAutocompleteElement`, `gmp-select`).
Esto sobreescribió los cambios correctos en producción.

Se intentó recuperar con `git checkout f2f9c0c -- .` pero el planificador
de ruta sigue sin funcionar correctamente (autocompletado y fondo del modal).

**Primer acto de la siguiente sesión: auditoría completa del estado del
planificador de ruta. NO tocar código hasta tener diagnóstico empírico
completo (logs, diff git, revisión visual). Un modelo fresco debe hacer
la auditoría desde cero.**

**Reconstrucción arquitectónica TollSegment — 4 cabinas físicas**

- **Decisión de arquitectura:** una fila por cabina física (punto único,
  `origin_lat/lng == dest_lat/lng`). El motor detecta que la polyline
  pasa cerca de la cabina y aplica el precio. No hay pares OD de recorrido.

- **4 cabinas insertadas:**
  - AP-7 Calahonda Troncal (36.505833, -4.717500): P1 baja=9,25 / alta=9,25
  - AP-7 San Pedro Troncal (36.499167, -5.009167): P1 baja=6,25 / alta=6,25
  - AP-7 Manilva Troncal (36.378900, -5.260000): P1 baja=3,65 / alta=4,60
  - AP-46 Casabermeja (36.849908, -4.484081): P1 baja=6,00 / alta=7,60

- **Temporadas verificadas en fuentes oficiales:**
  - AP-7 (Ausol RD 436/1996 y 1099/1999): alta = junio-septiembre +
    17 días desde Viernes de Dolores hasta Domingo in Albis.
  - AP-46: alta = mayo-octubre + fines de semana + mismos 17 días Semana Santa.
  - Semana Santa detectada automáticamente por `_is_holy_week()` en el motor.

- **Gratuidad nocturna AP-46:** `has_free_night=True`, 00:00-06:00 para
  ligeros (por pliego de concesión). AP-7 Ausol: sin gratuidad nocturna.

- **TollSegmentForm corregido:** texto de ayuda correcto (tipos de vehículo
  vs temporadas), Semana Santa del año actual calculada y mostrada en el
  formulario, nota sobre gratuidad nocturna por concesión.

- **views.py:** función `_get_holy_week_dates()` añadida. Inyectada en
  contexto de `TollSegmentCreateView` y `TollSegmentUpdateView`.

---

### COMPLETADAS EN S015

**Reconstrucción completa de la tabla TollSegment — datos Andalucía 2026**

- **Decisión de alcance:** reducir la tabla TollSegment exclusivamente a los
  peajes de Andalucía con datos completos y verificados: AP-7 Málaga–Estepona,
  AP-7 Estepona–Guadiaro, AP-46 Las Pedrizas–Málaga.

- **Documento maestro de peajes** creado:
  `/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/PEAJES_ANDALUCIA_2026.md`
  Tarifas oficiales extraídas directamente de PDFs del Ministerio de Transportes
  (vigencia 01/01/2026). Contiene barreras de peaje, recorridos directos,
  temporadas alta/baja y coordenadas GPS verificadas para las 3 autopistas.

- **Geocodificación de cabinas verificadas:**
  - CALAHONDA (troncal/acceso): 36.505833, -4.717500 (Wikimapia ID 26709654)
  - SAN PEDRO troncal: 36.499167, -5.009167 (Wikimapia ID 13641913)
  - SAN PEDRO acceso: 36.498611, -5.001944 (Wikimapia ID 13641973)
  - ESTEPONA (origen): 36.435493, -5.151214 (BD existente verificada)
  - MANILVA: 36.378900, -5.260000 (estimación geográfica km145)
  - GUADIARO: 36.311000, -5.307000 (estimación geográfica)
  - CASABERMEJA (AP-46): 36.849908, -4.484081 (Geocoding API `AP-46, Málaga`)

- **Script `rebuild_toll_segments.py`** preparado e instalado en SWAP.
  Estructura: `transaction.atomic()` envuelve borrado + inserción (protección
  contra borrado sin inserción). 20 tramos totales: 14 AP-7 Málaga–Estepona
  (barreras + recorridos directos) + 3 AP-7 Estepona–Guadiaro (barrera
  troncal + acceso + recorrido directo) + 2 recorridos Estepona–Manilva y
  Manilva–Guadiaro + 1 AP-46. Fechas `season_high_start/end` en formato
  `YYYY-MM-DD` con año convencional 2000. `tariff_level='NORMAL'`
  (choices del modelo: `NORMAL`/`SPECIAL`, `max_length=10`).
  `valid_from='2026-01-01'` en todos los registros (campo NOT NULL).

- **Estado al cierre:** script pendiente de ejecución exitosa. La BD tiene
  0 tramos (vacía por el borrado atómico de la pasada anterior que falló por
  `valid_from` NULL). El script corregido con `valid_from` está listo en SWAP
  como `rebuild_toll_segments.py`.

---

### COMPLETADAS EN S019

**Desvío desde H10.** Sesión dedicada por completo a H16 y H18 mientras H10
permanecía EN PROGRESO sin avance directo (ver anexo H10 S002 y anexo H16
S055 para el resto del trabajo de la sesión). Este registro cubre
exclusivamente el trabajo de mapas/geolocalización/peajes.

**(1) Bug crítico de peajes — ida/vuelta no se contaba dos veces y tramos
adyacentes se perdían.** Causa raíz en `_compute_toll_cost`
(`budgets/services.py`): el algoritmo buscaba el punto globalmente más
cercano (mínimo único) para origen y destino de cada `TollSegment` en toda
la polyline del circuito cerrado, asumiendo una única ocurrencia por
segmento. En un viaje de ida y vuelta el mismo peaje físico se cruza dos
veces (ida + vuelta) y el algoritmo solo lo contaba una. Con corredores de
varios peajes cercanos (AP-7), el emparejamiento por mínimo global podía
"engancharse" a un punto de la dirección contraria y perder el tramo por
completo. **Fix:** nueva función interna `_find_occurrences(target_lat,
target_lng, snap_km)` — recorre la polyline secuencialmente y devuelve el
índice del punto más cercano para CADA pasada por separado (declustering
de puntos contiguos cercanos en una única ocurrencia por paso físico). Para
segmentos punto-a-punto (origen≠destino) se empareja cada ocurrencia de
origen con la ocurrencia de destino no usada más próxima por índice, sin
importar el orden (la vuelta recorre el segmento en sentido físico
contrario). `SNAP_KM` reducido de 1.5 a 1.0 km — verificado empíricamente
que los pares troncal/salida de la AP-7 (Calahonda, San Pedro, Manilva)
están separados ~2,6-2,9 km, dejando margen de seguridad suficiente.

**(2) Lógica de puertas troncal/salida para la AP-7 (Calahonda, San Pedro,
Manilva).** Cada una de estas tres cabinas tiene en realidad DOS pórticos
físicos distintos — uno "Troncal" en el carril principal y uno "Salida" en
el ramal de entrada/salida intermedia — con tarifa propia y menor cada uno.
El emparejamiento genérico por proximidad no puede distinguirlos cuando
ambos caen dentro de `SNAP_KM` (cobraba los dos por error). Solución:
constante `AP7_GATE_PAIRS` en `_compute_toll_cost` con 3 pares de
coordenadas de control (`checkpoint_a`/`checkpoint_b`, proporcionadas y
verificadas empíricamente por Miguel Ángel) — si la ruta pasa por
`checkpoint_a` Y por `checkpoint_b` en la misma pasada → Troncal; si pasa
por `checkpoint_a` pero NO por `checkpoint_b` → Salida. Cada ocurrencia de
`checkpoint_a` se resuelve de forma independiente (permite ida por el
tramo completo y vuelta saliendo por el ramal, o viceversa, facturado
correctamente por sentido). Nueva función `_resolve_gate_pair()`. AP-46
(Casabermeja) no tiene esta ambigüedad — barrera física única, sigue el
bucle genérico sin cambios. **3 cabinas de "Salida" dadas de alta en BD**
(pk=449 Salida Calahonda, pk=450 Salida San Pedro, pk=451 Salida Manilva),
coordenadas de Manu (documento `AP7_Malaga_Informacion_Peajes.md`,
marcadas como aproximadas, pendientes de validación empírica en el primer
trayecto real que las cruce), precios verificados contra la tarifa oficial
de Ausol (`autopistadelsol.com/es/tarifas-y-descuentos/tarifas/`, coinciden
céntimo a céntimo), mismo `valid_from`/`tariff_level`/rango de temporada
alta que las 3 troncales ya existentes. Validado en producción con
presupuesto real Málaga↔Marbella (ida y vuelta, 3 cabinas × 2 = 6 líneas
correctas).

**(3) Fechas pasadas/presentes habilitadas en planificación de ruta.**
Google's Routes API rechaza `departureTime` en el pasado para
`RouteTravelMode=DRIVE` (verificado contra documentación oficial vigente,
2026-06). Nuevo parámetro `include_traffic` en `_call_routes_api` y
`_call_routes_multileg`: cuando la fecha de servicio no es futura, se omite
`departureTime` por completo y `routingPreference` cae a
`TRAFFIC_UNAWARE` (geometría/distancia/peajes no dependen de la fecha, solo
se pierde la predicción de tráfico en vivo, irrelevante para un servicio ya
prestado). `calculate_route`/`calculate_route_multileg` calculan
`include_traffic = service_datetime > datetime.datetime.utcnow()` y lo
propagan. Las 3 validaciones que bloqueaban `service_datetime` no futuro en
`views.py` (`InboundCallView`-equivalente wizard, endpoint route_calc,
endpoint route JSON del wizard multileg) eliminadas. El cálculo real del
presupuesto (nocturnidad, festivo, temporada alta de peajes) sigue usando
siempre la fecha real introducida por el operario, nunca la que se envía a
Google.

**(4) Fix drag-and-drop del planificador de ruta — números de parada no se
resincronizaban en el mapa.** Causa raíz en `wizard_map.js`: el
`glyphText` de cada `PinElement` se fija una sola vez en `addWaypoint` (a
partir de `stopCount` en el momento de crear el marcador) y nunca se
actualizaba tras reordenar o eliminar una parada — `reorderWaypoints()` y
`removeWaypointAt()` recalculaban bien la polyline (`recalculateRouteDisplay()`)
y la lista lateral (`renderStopsList()`) con el nuevo orden del array
`waypoints`, pero los pines ya existentes en el mapa mantenían su número
original. Fix: nueva función `refreshMarkerLabels()` — recorre `waypoints`
en su orden actual y reconstruye el `PinElement` de cada parada
(no-via, no-base-return) con el `glyphText` correcto, reasignando
`marker.content` (patrón ya usado en `addWaypoint`; la Maps JS API no
documenta mutación en caliente de `PinElement.glyphText`). Llamada añadida
en ambas funciones. Corrige también el mismo bug latente al eliminar una
parada intermedia (los pines restantes no se renumeraban).

**Archivos:** `budgets/services.py`, `budgets/views.py`,
`panel/static/panel/js/wizard_map.js`. Todos verificados con
`py_compile`/`node -c` antes de entrega. Instalación vía `install_files`
(bundle con marcadores de cierre reales tras incidente de corrupción
detallado en el registro de H16 S055) y `sftp put` directo para archivos
únicos. `collectstatic --clear` tras cada cambio de estático. Reloads con
timeout ocasional de la API de PythonAnywhere (conocido, no implica
fallo — reintento inmediato o recarga manual desde el botón verde del
dashboard web resuelve).

---

## DIRECTRIZ TÉCNICA VINCULANTE — API de Mapas, Geocodificación y Rutas

**De OBLIGADO CUMPLIMIENTO en todo el proyecto, sin excepción.**

1. **Google Maps Platform es la ÚNICA API permitida** para cualquier
   funcionalidad de mapas, geocodificación, autocompletado de direcciones,
   cálculo de rutas y matrices de distancia en EnterpriseBot.

2. **QUEDA TERMINANTEMENTE PROHIBIDO** el uso de OpenStreetMap, Leaflet.js,
   Nominatim, Mapbox o cualquier otro proveedor de mapas o geocodificación.

3. **APIs concretas de Google Maps Platform a utilizar:**
   - Maps JavaScript API — renderizado del mapa interactivo.
   - Places API — autocompletado y geocodificación de direcciones.
   - Geocoding API — conversión dirección estructurada ↔ coordenadas.
   - Routes API (Directions) — cálculo de ruta multi-parada, km y peajes.

4. **API key:** existe una única API key con facturación activada. Toda nueva
   funcionalidad reutiliza esa misma key. No se crean keys adicionales.

5. **Incumplir esta directriz es un ERROR CRÍTICO.**

---

## Hoja de Ruta para la Siguiente Sesión (retoma H18)

### ESTADO AL CIERRE DE S019

- **BD TollSegment:** 7 cabinas físicas activas y verificadas en producción.
  AP-7: Calahonda Troncal (pk=445), San Pedro Troncal (pk=446), Manilva
  Troncal (pk=447), Salida Calahonda (pk=449), Salida San Pedro (pk=450),
  Salida Manilva (pk=451) — las 3 "Salida" nuevas en S019, coordenadas de
  Manu marcadas como aproximadas, precios verificados contra tarifa oficial
  Ausol. AP-46: Casabermeja (pk=448, `has_free_night=True`, 00:00–06:00
  ligeros).
- **Motor de peajes reescrito en S019:** detección de ocurrencias múltiples
  (`_find_occurrences`) sustituye el emparejamiento por mínimo global —
  resuelve ida/vuelta y tramos adyacentes. Lógica de puertas
  `AP7_GATE_PAIRS`/`_resolve_gate_pair` resuelve troncal vs. salida para
  las 3 cabinas de la AP-7. `SNAP_KM=1.0`. Gratuidad nocturna AP-46 sigue
  sin implementar en `_compute_toll_cost()` — aplazado porque Grupo Álvarez
  opera con Pesado 2 (sin gratuidad nocturna).
- **Fechas pasadas/presentes habilitadas (S019):** `include_traffic`
  condiciona el envío de `departureTime` a Google Routes API. Validado
  en producción.
- **Planificador de ruta:** operativo en producción. Autocompletado de
  direcciones con API programática propia
  (`AutocompleteSuggestion.fetchAutocompleteSuggestions()` +
  `AutocompleteSessionToken`, dropdown HTML propio) desde S018 —
  sustituye a `PlaceAutocompleteElement`. `encoded_polyline` correcto
  desde S013. **Fix S019:** números de parada (`glyphText` de
  `PinElement`) se resincronizan tras drag-and-drop o borrado
  (`refreshMarkerLabels()`).
- **Fix pausa comida:** desplegado en S014. Pendiente validación con
  Antonio Fontalba (sin cambios este cierre).

### Pendiente 1 (PRIORITARIO) — Validar coordenadas aproximadas de las 3 cabinas "Salida" AP-7

Las coordenadas de Salida Calahonda/San Pedro/Manilva (pk=449/450/451)
proceden de un documento generado por IA (Manu), marcado explícitamente
como aproximado. En el primer presupuesto real que cruce alguna de estas
salidas, revisar en el desglose ADMIN si el resultado (Troncal vs. Salida)
coincide con la realidad del trayecto. Si no coincide, ajustar coordenadas
o, si el problema es de alcance (`checkpoint_a` no se cruza en algún
sentido de circulación), valorar un segundo par de puntos de control por
sentido — ver discusión de S019 sobre simetría del algoritmo de puertas.

### Pendiente 2 — Ampliar BD con peajes de otras CCAA (TAREA INMEDIATA original, sin empezar)

Añadir cabinas físicas de autopistas con presencia en rutas habituales de Grupo
Álvarez: Extremadura, Murcia y Castilla-La Mancha.

**Procedimiento:**
1. Consultar PDFs oficiales del Ministerio de Transportes para las autopistas
   relevantes de cada CCAA. Fuente:
   `https://www.transportes.gob.es/carreteras/peajes-en-autopistas/informacion-para-usuarios/tarifas-de-peaje`
2. Identificar cabinas físicas (una fila por cabina, `origin_lat/lng == dest_lat/lng`,
   coordenadas GPS verificadas) o pares troncal/salida si la vía tiene esa
   estructura (ver `AP7_GATE_PAIRS` como referencia de patrón).
3. Insertar con el mismo formato que las cabinas existentes: `road_code`,
   `section_name`, `origin_name`, `dest_name`, coordenadas, precios baja/alta
   por tipo de vehículo, `season_high_start/end` (año convencional 2000),
   `tariff_level='NORMAL'`, `valid_from='2026-01-01'`.
4. Murcia: AP-7 Cartagena–Vera (SEITT). Extremadura y CLM: verificar qué
   autopistas de peaje atraviesan las rutas tipo de Grupo Álvarez.

### Pendiente 3 — Validación PDF

Verificar que las `BudgetLine` con `CODE_TOLL_SEGMENT` se renderizan correctamente
en la exportación PDF (etiqueta completa, sin truncar), incluyendo las
nuevas líneas de "Salida" con el nuevo motor de peajes de S019.
