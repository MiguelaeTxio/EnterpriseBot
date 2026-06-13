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

### COMPLETADAS EN S013
- Sesión de DEFINICIÓN TOTAL del planificador de ruta multi-parada.
- Reglas de negocio cerradas: circuito siempre cerrado (Base → paradas → Base),
  detección automática de pernocta cuando la Base aparece como waypoint
  intermedio (is_base_return=True), anatomía de paradas (recogida obligatoria
  → dejada(s) → Base implícita como destino final).
- Actualización online obligatoria (Directriz 4.4): Routes API v2 computeRoutes
  con intermediates[] confirmado (hasta 25 waypoints, circuito cerrado válido,
  TRAFFIC_AWARE compatible con multi-waypoint, polyline por leg y total).
  Maps JavaScript API con Dynamic Library Import, AdvancedMarkerElement GA
  con mapId obligatorio, Places Autocomplete vía importLibrary("places").
- Map ID creado en Google Cloud Console: EnterpriseBot Wizard, tipo JavaScript,
  rendering Vector. ID: 203beab70bcb8a02c9b383b1. Añadido a .env como
  GOOGLE_MAPS_MAP_ID.
- Migración 0020_budget_waypoints_json aplicada: campo JSONField waypoints_json
  en modelo Budget. Esquema por parada: {label, address, lat, lng, is_base_return}.
- calculate_route_multileg() en budgets/services.py: orquesta una o dos llamadas
  a Routes API v2 según presencia de waypoint is_base_return. Devuelve
  distance_km, km_phase1, km_phase2, is_overnight, has_tolls, encoded_polyline.
  Función interna _call_routes_multileg() construye el payload computeRoutes
  con intermediates[]. No multiplica distancia por 2 — circuito cerrado.
- BudgetRouteMultilegInitView (GET) en budgets/views.py: endpoint HTMX que
  devuelve _route_multileg_fragment.html inicializado con coordenadas de Base,
  GOOGLE_MAPS_API_KEY y GOOGLE_MAPS_MAP_ID.
- BudgetWaypointView (POST) en budgets/views.py: endpoint HTMX que recibe
  base_id, waypoints_json, service_date, service_time. Valida inputs, llama
  a calculate_route_multileg() y devuelve fragmento de resultado.
- Rutas route-multileg-init/ y waypoints/ registradas en budgets/urls.py.
- Script transversal reload_app.py creado en /home/MiguelAeTxio/: centraliza
  la recarga de webapps PythonAnywhere via API REST con DOMAIN_MAP interno.
  Recibe PROJECT_ID como argumento. Sustituye el comando inline python3 -c.
- Skill pew-reload actualizada y empaquetada: método de recarga via
  reload_app.py, salida obligatoria redirigida a SWAP (Comando S), regla
  JAMÁS ejecutar sin capturar salida.
- Decisión de arquitectura para el frontend: modal fullscreen para el
  planificador, renderizado de ruta en vivo con DirectionsService +
  DirectionsRenderer client-side (recalcula al añadir/eliminar/reordenar
  paradas), cálculo final de facturación con Routes API v2 server-side
  al confirmar. Panel izquierdo de paradas + mapa derecho.

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

## Hoja de Ruta para la Siguiente Sesión (Implementación Frontend del Modal Multi-Parada)

### CONTEXTO

La sesión S013 completó toda la capa backend del planificador multi-parada
(modelo, migración, services, views, urls) y la configuración de Google Maps
Platform (Map ID, .env). Queda pendiente la capa frontend: el modal interactivo
con mapa Google Maps, renderizado de ruta en vivo y la integración en el wizard.

### DECISIÓN DE ARQUITECTURA CERRADA — Modal + DirectionsService Live

El planificador de ruta se presenta en un **modal Bootstrap 5 fullscreen**
(o `modal-xl`) que se abre desde el wizard con un botón "Planificar ruta".

**Renderizado de ruta en vivo** — cada vez que el operario añade, elimina o
reordena una parada, la ruta se recalcula y redibuja instantáneamente en el
mapa usando `DirectionsService` + `DirectionsRenderer` de Maps JavaScript API
(client-side, sin round-trip al servidor). La UX es idéntica a Google Maps
cuando planificas un viaje con paradas.

**Cálculo de facturación final** — al pulsar "Confirmar ruta", un `fetch()`
a `budgets:waypoints` (Routes API v2 server-side, ya implementado) devuelve
los datos exactos de facturación: km con TRAFFIC_AWARE, detección de peajes,
fases de pernocta. Estos datos se vuelcan en los hidden inputs del wizard.

### REGLAS DE NEGOCIO (recordatorio vinculante)

- **Circuito cerrado:** Base → paradas → Base. Siempre.
- **Anatomía:** recogida (obligatoria, 1er waypoint) → dejada(s) → Base
  implícita como destino final.
- **Pernocta:** waypoint `is_base_return=True` → dos fases → `km_phase1`
  y `km_phase2` independientes.

### ARCHIVOS A VERSIONAR EN SWAP AL INICIO

```bash
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/templates/budgets/wizard.html /home/MiguelAeTxio/SWAP/wizard.html.v01
```

### PASO 1 — Crear `_route_multileg_fragment.html` (contenido del modal)

Template nuevo en `budgets/templates/budgets/`. Contenido del modal, NO el
modal wrapper — el `<div class="modal">` vive en `wizard.html`.

Estructura del fragmento:

```
┌────────────────────────┬────────────────────────────────────┐
│  PANEL DE PARADAS      │                                    │
│                        │                                    │
│  📍 Base: {nombre}     │         GOOGLE MAPS               │
│  ────────────────────  │         (mapa interactivo)         │
│  1. 📌 Recogida...     │                                    │
│  2. 📌 Dejada 1...     │         polyline en vivo           │
│  3. 🏠 Volver a base   │         markers numerados          │
│  4. 📌 Destino final   │                                    │
│  ────────────────────  │                                    │
│  [+ Añadir parada]     │                                    │
│  [🏠 Volver a base]    │                                    │
│                        │                                    │
│  ─── RESUMEN RUTA ───  │                                    │
│  Distancia: 234 km     │                                    │
│  Fase 1: 120 km        │                                    │
│  Fase 2: 114 km        │                                    │
│  Pernocta: Sí          │                                    │
│  Peajes: No            │                                    │
│                        │                                    │
│  [Confirmar ruta]      │                                    │
└────────────────────────┴────────────────────────────────────┘
```

**Panel izquierdo** (control, ~30% ancho):
- Base origen fija (no editable, marker especial en mapa).
- Lista de paradas reordenables con drag (HTML5 drag-and-drop o SortableJS
  si el peso es aceptable). Cada parada: número, icono, label, botón ✕.
- Input Places Autocomplete para añadir parada.
- Botón "Volver a base" → inserta waypoint is_base_return=True con icono 🏠.
- Sección resumen: distancia total, fases si pernocta, peajes. Se actualiza
  en vivo con cada recálculo del DirectionsService (distancia client-side,
  no la de facturación final).

**Mapa derecho** (~70% ancho):
- Google Maps con AdvancedMarkerElement, mapId GOOGLE_MAPS_MAP_ID.
- Marker fijo de la Base (no eliminable, icono diferenciado).
- Markers numerados de cada parada (eliminables con clic).
- Polyline de ruta vía DirectionsRenderer, actualizada en vivo.
- Clic en el mapa → añade parada con reverse geocoding para label.

**Botón "Confirmar ruta"** (footer del panel):
- `fetch()` a `budgets:waypoints` con base_id, waypoints_json, service_date,
  service_time.
- Al recibir respuesta: vuelca km_phase1, km_phase2, is_overnight, has_tolls,
  waypoints_json, route_distance_km, route_calculation_mode=API en los hidden
  inputs del wizard.
- Cierra el modal.

**Campos hidden** (dentro del fragmento, se vuelcan al form del wizard):
```html
<input type="hidden" name="waypoints_json"        id="id_waypoints_json">
<input type="hidden" name="route_distance_km"      id="id_route_distance_km">
<input type="hidden" name="km_phase1"              id="id_km_phase1">
<input type="hidden" name="km_phase2"              id="id_km_phase2">
<input type="hidden" name="is_overnight"           id="id_is_overnight_route">
<input type="hidden" name="route_toll_budget_cost" id="id_route_toll_budget_cost">
<input type="hidden" name="route_calculation_mode" id="id_route_calculation_mode"
       value="API">
```

En móvil: panel arriba colapsable, mapa debajo (stacked).

**Diseño:** el modal debe tener una UX limpia, sin ruido, guiada. Partes
bien diferenciadas. El diseño debe ser simple, directo e intuitivo. Conectar
con la skill `frontend-design` para las decisiones estéticas. Bootstrap 5
como base, coherente con el resto del panel pero con licencia para lucirse
dentro del modal.

---

### PASO 2 — Crear `wizard_map.js`

Archivo JS nuevo en `budgets/static/budgets/js/`. Toda la lógica del mapa:

**Carga de librerías:**
```javascript
async function initMap() {
    const { Map } = await google.maps.importLibrary("maps");
    const { AdvancedMarkerElement } = await google.maps.importLibrary("marker");
    const { Autocomplete } = await google.maps.importLibrary("places");
    const { DirectionsService, DirectionsRenderer } = await google.maps.importLibrary("routes");
    // ...
}
```

**Funciones principales:**
- `initMap()` — inicializa Map centrado en Base.latitude/longitude con
  GOOGLE_MAPS_MAP_ID. Añade marker fijo de la Base. Inicializa
  DirectionsService y DirectionsRenderer. Se dispara en `shown.bs.modal`
  del modal (no antes, para evitar problemas de renderizado).
- `addWaypoint(lat, lng, label, is_base_return)` — añade marker al mapa
  y entrada a la lista de paradas. Llama a `recalculateRoute()`.
- `removeWaypoint(index)` — elimina marker y entrada. Llama a
  `recalculateRoute()`.
- `reorderWaypoints()` — tras drag-and-drop, reordena la lista interna
  y llama a `recalculateRoute()`.
- `recalculateRoute()` — construye DirectionsRequest con origin=Base,
  destination=Base, waypoints=paradas intermedias. Llama a
  `directionsService.route()` y pasa el resultado a DirectionsRenderer.
  Actualiza la sección de resumen (distancia total desde la respuesta).
  Si hay waypoint is_base_return, calcula distancias parciales por legs.
- `confirmRoute()` — `fetch()` a budgets:waypoints para datos de
  facturación. Vuelca resultados en hidden inputs. Cierra modal.
- Listener de clic en mapa → `addWaypoint(lat, lng, "Punto manual", false)`.
- Listener de Autocomplete → `addWaypoint(lat, lng, place.name, false)`.

**Nota técnica:** `DirectionsService` usa la Directions API (más barata) y
devuelve la ruta con polyline y distances por leg. Es suficiente para la
visualización en vivo. Los datos de facturación finales usan Routes API v2
(TRAFFIC_AWARE, peajes) vía el endpoint server-side.

---

### PASO 3 — Integración en `wizard.html`

- Añadir el wrapper `<div class="modal" id="routePlannerModal">` con el
  contenido del fragmento.
- En el PASO 4 del wizard (ruta), añadir botón "Planificar ruta" que abre
  el modal: `data-bs-toggle="modal" data-bs-target="#routePlannerModal"`.
- Cargar Maps JavaScript API con Dynamic Library Import en el `<head>` o
  al final del body (solo si el wizard está en modo API, no en MANUAL).
- El bloque MANUAL se mantiene sin cambios.
- Cargar `wizard_map.js` como script estático.

---

### PASO 4 — `BudgetWizardView.post()` — lectura de nuevos campos

En el POST de cierre del wizard, añadir lectura de:
```python
waypoints_json_str = request.POST.get("waypoints_json", "")
km_phase1_str      = request.POST.get("km_phase1", "")
km_phase2_str      = request.POST.get("km_phase2", "")
is_overnight_route = request.POST.get("is_overnight_route", "") == "true"
```
Persistir en budget antes de calculate_budget(). route_calculation_mode=API.

---

### PASO 5 — collectstatic + Verificación E2E

1. `collectstatic --noinput --clear` para `wizard_map.js`.
2. Presupuesto servicio simple: Base → Recogida → Dejada → Base.
3. Presupuesto pernocta: Base → Recogida → Base(*) → Destino → Base.
4. Verificar polyline en vivo, resumen de distancias, hidden inputs.

---

### ARCHIVOS A CREAR (nuevos, sin SWAP previo)

| Archivo | Tipo |
|---|---|
| `budgets/templates/budgets/_route_multileg_fragment.html` | Template nuevo |
| `budgets/static/budgets/js/wizard_map.js` | JS nuevo |

### ARCHIVOS A MODIFICAR (con SWAP)

| Archivo | Acción |
|---|---|
| `budgets/templates/budgets/wizard.html` | Modal wrapper + botón + carga Maps API |
| `budgets/views.py` | BudgetWizardView.post() lectura waypoints |
