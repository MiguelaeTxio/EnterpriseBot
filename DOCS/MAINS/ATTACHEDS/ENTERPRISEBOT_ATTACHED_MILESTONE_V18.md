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
  para Grupo Álvarez (18h-06h por defecto, 20h-08h secundario).
- Vistas CRUD NightSchedule añadidas a budgets/views.py:
  NightScheduleForm, NightScheduleListView, NightScheduleUpdateView,
  NightScheduleDeleteView.
- Rutas night-schedules/ registradas en budgets/urls.py.
- Template night_schedule_list.html creado con tabla de horarios y modal
  de creación/edición.
- Campo night_schedule añadido a InsurerForm.Meta.fields y renderizado
  en _insurer_fields_partial.html con selector desplegable.
- Enlace 'Gestionar horarios nocturnos' pendiente de aplicar en
  panel/company/settings.html (patcher falló por ancla Unicode).

### COMPLETADAS EN S004
- Fix calculate_route(): bloque _road insertado, bloque debug eliminado, distancia × 2.
- Fix User-Agent en sync_base_calendars para evitar 403 desde PythonAnywhere.
- Parser API calendariosnacionales.com corregido: data['holidays']['calendar'] con deduplicacion por fecha.
- MUNICIPALITY_MAP ampliado con 9 municipios: antequera, carratraca, coin, fuengirola, loja, moraleda-de-zafayona, velez-malaga, villanueva-del-cauche (fallback antequera), la roda de andalucia (fallback estepa).
- Base Saula Rosalia fusionada con base Malaga (InsurerBase Mondial/Transgrual reasignada).
- Campo dest_location en wizard Modo B: template, JS, views, services, modelo Budget y migracion 0012.
- Boton "Sincronizar calendarios" en BaseGlobalView: BaseSyncCalendarsView, ruta base_sync_calendars.
- Franja horaria nocturna configurable: campos night_start/night_end en Company (migracion ivr_config 0031), formulario en panel/company/settings.html, CompanySettingsView actualizada.
- Nocturnidad automatica en BudgetWizardView.post(): calcula is_night desde service_time + night_start/night_end + _is_holiday().
- Paso 6 del wizard: checkbox siempre visible, pre-marcado automatico con badge "Auto" cuando hay service_time, override manual disponible siempre. BudgetStepsView pasa is_night_auto al contexto.
- Migracion a AdvancedMarkerElement en base_edit_fragment.html: mapId DEMO_MAP_ID, MarkerLib.AdvancedMarkerElement, marker.position en idle.
- Fix coordenadas con filtro unlocalize ({% load l10n %}) en base_edit_fragment.html.
- Vista de edicion de base como pagina dedicada: BaseUpdateView renderiza base_edit_page.html (pagina completa), POST redirige a base_global. Elimina conflicto de multiples mapas simultaneos.
- Seleccion multiple y limpieza de coordenadas: BaseClearCoordsView, ruta base_clear_coords, boton "Seleccionar bases" con modo seleccion JS client-side en base_global.html.
- UX botones tabla bases: columnas th/td con width:1% nowrap, botones en d-flex gap-1.
- Skill PED reforzada con Regla 8: verificacion obligatoria de salida integra antes de continuar.

### COMPLETADAS EN S011
- PASO 0: fix vista de detalle de aseguradora (InsurerDetailView). Añadido
  select_related('night_schedule') en la query. Calculado night_schedule_display
  en la vista con resolución en tres niveles: insurer.night_schedule activo →
  NightSchedule is_default=True de empresa → {"source": "none"}. Inyectado en
  el contexto. Template insurer_detail.html: nuevo bloque en card Datos generales
  que muestra badge azul (horario propio), badge gris (por defecto empresa) o
  texto sin configurar según source. Saneado de errores djlint preexistentes:
  tags huérfanos del bloque guía del pastor eliminados, &mdash; sustituidos
  por carácter Unicode directo, línea en blanco extra eliminada.
  0 errores djlint al cerrar.
- Actualización en línea Routes API v2: confirmado que para España la API
  no devuelve coste de peajes. Decisión de arquitectura para BLOQUE 4:
  dos llamadas separadas a la API (ruta normal + avoidTolls:true), cruce
  de coste con tabla TollSegment en BD (418 tramos, 10 autopistas).
  Auditoría BD: AP-46, AP-51, AP-53, AP-6, AP-61, AP-66, AP-68, AP-7,
  AP-71, AP-9. Solo nombres textuales, sin coordenadas geográficas.
  Sesión cerrada por agotamiento de cuota antes de implementar services.py.

### COMPLETADAS EN S012
- Fix IntegrityError (1364) en BudgetWizardView: campo is_informational de
  BudgetLine sin DEFAULT en MySQL. ALTER TABLE budgets_budgetline ALTER COLUMN
  is_informational SET DEFAULT 0 aplicado directamente en BD.
- Fix IntegrityError (1364) en BaseGlobalView: columna huérfana insurer_id en
  budgets_base (reliquia de migración 0010 que no ejecutó DROP COLUMN en MySQL).
  ALTER TABLE budgets_base DROP COLUMN insurer_id aplicado. Error resuelto
  sin migración Django — la columna no existía en el modelo actual.
- Fix is_active DEFAULT 1 en budgets_base y budgets_insurerbase: ALTER TABLE
  ... ALTER COLUMN is_active SET DEFAULT 1 en ambas tablas.
- Decisión de negocio BLOQUE 5 confirmada: los peajes se facturan SIEMPRE
  cuando la ruta se calcula por API. Si el operario introduce km manualmente,
  no hay ruta API y no se facturan peajes. No hay mecanismo de elección en el
  wizard — la distinción la hace el modo de cálculo (API vs manual).
- Nuevo sistema de trabajo PEW (Protocolo de Edición en Workspace): los
  archivos de código se editan en el workspace del modelo, se verifican con
  py_compile/djlint allí mismo y se entregan con present_files para descarga
  directa. Sustituye completamente a ped-router, ped-format, ped-pma, ped-pmp
  y ped-pea. Skill pew.skill generada y empaquetada.

### PENDIENTES
- PRIORIDAD 2 — Peajes por tabla propia: aplazado por decision de negocio.
  La Routes API indica presencia de peajes (has_tolls=True) y el operario
  introduce el importe manualmente. Sin tabla TollSegment por el momento.
- PRIORIDAD 3 — Boton sync calendarios: implementado en S004 como BaseSyncCalendarsView.

### NOTA DE DESVÍO DE SESIÓN

Durante una sesión con el Hito 18 EN PROGRESO, el trabajo se desvió por
completo a atender una incidencia crítica del módulo de partes digitales
(Hito 7 — Partes Diarios de Reparación). No se ejecutó la hoja de ruta del
Hito 18 en esa sesión.

Resumen breve de la incidencia atendida: eliminación del sistema "Gate 4"
de resolución de lagunas, unificación de la vista de creación y edición de
partes digitales para todos los roles, corrección de duplicidad de fecha y
fecha futura, modal guardián de validación con justificación de ausencias
(código PERSONAL), auto-relleno de horarios, copia de seguridad de partes
en logs y batería de smoke tests de validación.

El detalle completo, con pelos y señales, está registrado en el anexo del
Hito 7 (`ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`).

---

## DIRECTRIZ TÉCNICA VINCULANTE — API de Mapas, Geocodificación y Rutas

**De OBLIGADO CUMPLIMIENTO en todo el proyecto, sin excepción.**

1. **Google Maps Platform es la ÚNICA API permitida** para cualquier
   funcionalidad de mapas, geocodificación, autocompletado de direcciones,
   cálculo de rutas y matrices de distancia en EnterpriseBot.

2. **QUEDA TERMINANTEMENTE PROHIBIDO** el uso de OpenStreetMap, Leaflet.js,
   Nominatim, Mapbox o cualquier otro proveedor de mapas o geocodificación.
   La geolocalización de bases (`BaseGlobalView`) ya usa Google Maps
   correctamente; el módulo de presupuestos (`budgets`) debe alinearse con
   este mismo proveedor.

3. **APIs concretas de Google Maps Platform a utilizar:**
   - Maps JavaScript API — renderizado del mapa interactivo.
   - Places API — autocompletado y geocodificación de direcciones.
   - Geocoding API — conversión dirección estructurada ↔ coordenadas.
   - Routes API (Directions) — cálculo de ruta multi-parada, km y peajes.

4. **API key:** existe una única API key de Google Maps Platform con
   facturación activada y en uso. Toda nueva funcionalidad reutiliza esa
   misma key. No se crean keys adicionales ni se mezclan proveedores.

5. **Incumplir esta directriz es un ERROR CRÍTICO.** Cualquier referencia
   residual a Leaflet/Nominatim en el módulo de presupuestos debe eliminarse
   durante la implementación de este hito.

---

## Hoja de Ruta para la Siguiente Sesión (Sesión de Definición Total)

### CONTEXTO

Cambio de enfoque mayor en el sistema de ruta de presupuestos. La hoja de
ruta anterior (S013, visualización dual de rutas con Leaflet) queda
SUPERADA y se descarta: introducía Leaflet en el módulo de presupuestos,
en contra de la Directriz Técnica Vinculante recién establecida.

El nuevo sistema sustituye el cálculo punto-a-punto por un **planificador
de ruta multi-parada estilo Google Maps**, alineado con la geolocalización
de bases que ya usa Google Maps Platform.

La sesión siguiente es de **DEFINICIÓN TOTAL**: al arrancar el PISA se
cargarán los modelos de la app `budgets`, las tarifas de desplazamiento en
BD y la geolocalización de bases. Con ese mapa completo en el workspace se
redactará la hoja de ruta técnica detallada (nombres de campos, modelos,
endpoints y lógica exactos). Lo que sigue son los OBJETIVOS del hito.

### OBJETIVOS DEL NUEVO SISTEMA DE RUTA

1. **Migración a Google Maps en presupuestos.** Eliminar toda referencia a
   Leaflet/Nominatim del módulo `budgets`. El mapa del wizard de presupuestos
   pasa a Maps JavaScript API, reutilizando la API key existente.

2. **Dirección estructurada.** El input de ubicación actual se sustituye por
   una dirección estructurada de tres campos:
   - Nombre de vía.
   - Punto kilométrico (P.K.).
   - Municipio.
   Con geocodificación (Geocoding/Places API) a coordenadas para el mapa.

3. **Planificador de ruta multi-parada.** Igual que planificar una ruta con
   paradas en Google Maps:
   - **Origen:** geolocalización de la base (ya en BD, punto fijo de partida).
   - **Paradas intermedias:** múltiples puntos añadibles, bien introduciendo
     la dirección estructurada (vía + P.K. + municipio), bien pinchando
     directamente sobre el mapa.
   - **Destino final:** último punto de la ruta.
   - Paradas reordenables.

4. **Cálculo de ruta.** Routes API calcula la ruta completa origen →
   paradas → destino, devolviendo distancia/km totales (y peajes si los hay).

5. **Integración con tarifas en BD.** Los km totales de la ruta se cruzan
   con las **tarifas de desplazamiento ya existentes en BD** para calcular
   el coste del servicio, que se vuelca al presupuesto.

### PRIMER PASO DE LA SESIÓN DE DEFINICIÓN

Al arrancar, solicitar y cargar en el workspace: modelos de `budgets`
(Budget, BudgetLine, tarifas, Base con su geolocalización), `budgets/services.py`,
`budgets/views.py`, `budgets/urls.py`, el wizard y sus fragmentos. Con esos
modelos a la vista, redactar la hoja de ruta técnica detallada paso a paso.

### NOTA DE DISEÑO

El cálculo de ruta multi-parada debe hacerse en UNA sola llamada a Routes API
(Compute Routes con waypoints: origen + paradas + destino), nunca recalculando
en cada cambio de parada. El recálculo se dispara con acción explícita del
usuario (botón "Calcular ruta") o con debounce, no automáticamente en cada
clic. Es buena praxis de uso de la API.
