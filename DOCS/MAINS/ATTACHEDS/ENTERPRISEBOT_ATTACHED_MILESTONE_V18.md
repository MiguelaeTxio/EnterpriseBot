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

## Hoja de Ruta para la Siguiente Sesión (Implementación Planificador Multi-Parada)

### CONTEXTO Y REGLAS DE NEGOCIO CERRADAS

La sesión de definición total (S013) ha producido la hoja de ruta técnica
completa. Las reglas de negocio que gobiernan el sistema de ruta son:

**Circuito siempre cerrado:** el camión de asistencia siempre sale de la
Base y siempre vuelve a la Base. La Routes API recibe `origin = Base` y
`destination = Base`. La distancia total devuelta ya incluye el recorrido
completo (no es necesario multiplicar por 2).

**Anatomía de paradas:**
```
Base (origen fijo, automático)
  └─► Punto de recogida del vehículo averiado  [OBLIGATORIO, 1º waypoint]
        └─► Punto de dejada 1                  [OBLIGATORIO]
              └─► Punto de dejada 2 (opcional)
                    └─► Base (destino final, siempre implícito)
```

El operario introduce las paradas en orden: recogida → dejada(s). La Base
como destino final la añade el sistema automáticamente. El operario no la
marca como destino — solo puede marcarla como **parada intermedia** en caso
de pernocta.

**Detección automática de pernocta:** cuando el operario añade la Base como
waypoint intermedio (botón "Volver a base" entre paradas), el sistema detecta
dos fases y marca `is_overnight = True`:

```
Servicio simple:   Base → Recogida → Dejada → Base
Pernocta:          Base → Recogida → Base(*) → Destino final → Base
                                    (*) waypoint intermedio explícito
```

- **Fase 1:** Base → Recogida → Base intermedia → `km_phase1`
- **Fase 2:** Base intermedia → Destino final → Base → `km_phase2`

---

### ARCHIVOS A VERSIONAR EN SWAP AL INICIO DE LA SESIÓN

```bash
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/models.py /home/MiguelAeTxio/SWAP/models.py.v01
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/services.py /home/MiguelAeTxio/SWAP/services.py.v01
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/views.py /home/MiguelAeTxio/SWAP/views.py.v01
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/urls.py /home/MiguelAeTxio/SWAP/urls.py.v01
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/templates/budgets/wizard.html /home/MiguelAeTxio/SWAP/wizard.html.v01
cp /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/templates/budgets/_route_calc_fragment.html /home/MiguelAeTxio/SWAP/_route_calc_fragment.html.v01
```

---

### PASO 1 — Actualización online obligatoria (Directriz 4.4)

Antes de escribir cualquier línea de código, actualizar en línea:

1. **Routes API v2 `computeRoutes`** — schema exacto con `intermediates[]`
   (waypoints), campo `polyline` en la respuesta (encoded polyline o
   GeoJSON), y si `TRAFFIC_AWARE` es compatible con multi-waypoint y
   circuito cerrado (origin = destination = mismas coordenadas).
2. **Maps JavaScript API + Places Autocomplete** — forma correcta de cargar
   ambas librerías en 2026: `?libraries=places,maps` o API separada.
   Confirmar si `AdvancedMarkerElement` ya es GA (no beta) y si el
   `mapId` sigue siendo obligatorio para usarlo.

---

### PASO 2 — Migración: añadir `waypoints_json` a `Budget`

Añadir en `budgets/models.py` dentro de la clase `Budget`, junto a los
campos de ruta existentes (después de `route_toll_real_cost`):

```python
# Ordered list of route waypoints for the multi-stop planner.
# Each element: {label, address, lat, lng, is_base_return}.
# is_base_return=True marks an intermediate return to base (overnight).
# Lista ordenada de paradas del planificador multi-parada.
# Cada elemento: {label, address, lat, lng, is_base_return}.
# is_base_return=True marca un retorno intermedio a base (pernocta).
waypoints_json = models.JSONField(
    null=True,
    blank=True,
    verbose_name="Paradas de ruta",
    help_text=(
        "Lista ordenada de paradas del planificador multi-parada. "
        "Cada elemento: {label, address, lat, lng, is_base_return}. "
        "is_base_return=True indica retorno intermedio a base (pernocta). "
        "Null en presupuestos con modo MANUAL o ruta punto a punto legacy."
    ),
)
```

Esquema JSON de cada parada:
```json
{
  "label":          "Recogida — A-45 P.K. 127.5, Antequera",
  "address":        "A-45, P.K. 127.5, Antequera, Málaga",
  "lat":            37.0123,
  "lng":            -4.5590,
  "is_base_return": false
}
```

Ejecutar `makemigrations` + `migrate`. Número de migración: `0020`.

---

### PASO 3 — `calculate_route_multileg()` en `services.py`

Nueva función pública. Firma exacta:

```python
def calculate_route_multileg(
    base: "Base",
    waypoints: list[dict],
    service_datetime: datetime.datetime,
    api_key: str,
) -> dict:
```

**Lógica interna:**

1. Detectar si hay waypoint con `is_base_return=True`. Si lo hay, dividir
   la lista en dos sublistas:
   - `leg1_waypoints`: desde el inicio hasta el waypoint `is_base_return`
     (exclusive).
   - `leg2_waypoints`: desde el waypoint `is_base_return` (exclusive) hasta
     el final.
2. Si **no hay** `is_base_return` → una sola llamada a `_call_routes_multileg()`:
   - `origin` = `{lat: base.latitude, lng: base.longitude}`
   - `intermediates` = todos los waypoints excepto el último
   - `destination` = `{lat: base.latitude, lng: base.longitude}`
   - Resultado → `distance_km` total, `has_tolls`, `polyline`.
3. Si **hay** `is_base_return` → dos llamadas a `_call_routes_multileg()`:
   - Llamada 1 (fase 1): `origin=Base`, `intermediates=leg1_waypoints`,
     `destination=Base`.
   - Llamada 2 (fase 2): `origin=Base`, `intermediates=leg2_waypoints`,
     `destination=Base`.
   - `km_phase1` = distancia llamada 1.
   - `km_phase2` = distancia llamada 2.
   - `is_overnight = True`.
   - `has_tolls` = OR de ambas llamadas.
   - `polyline` = polyline combinada (fase1 + fase2 concatenadas).

**Valor de retorno:**
```python
{
    "distance_km":   Decimal,   # km_phase1 si pernocta, total si simple
    "km_phase1":     Decimal,   # siempre
    "km_phase2":     Decimal | None,  # solo en pernocta
    "is_overnight":  bool,
    "has_tolls":     bool,
    "polyline":      str,       # encoded polyline para renderizar en mapa
    "error":         None | str,
}
```

`_call_routes_multileg()` es una función interna nueva que construye el
payload de `computeRoutes` con `intermediates[]` y llama a la Routes API v2.
Reutiliza `_call_routes_api()` como referencia de patrón, pero con el
schema multi-waypoint confirmado en el PASO 1.

---

### PASO 4 — `BudgetWaypointView` en `views.py`

Nuevo endpoint HTMX POST. Registrar en `budgets/urls.py`:

```python
path(
    "waypoints/",
    views.BudgetWaypointView.as_view(),
    name="waypoints",
),
```

**Lógica de la vista:**

1. Leer `base_id`, `waypoints_json` (string JSON), `service_date`,
   `service_time` del POST.
2. Obtener `base = Base.objects.get(pk=base_id)`.
3. Parsear `waypoints_json` → lista de dicts.
4. Construir `service_datetime` combinando `service_date` + `service_time`.
5. Leer `GOOGLE_MAPS_API_KEY` desde `os.environ` o `settings`.
6. Llamar a `calculate_route_multileg(base, waypoints, service_datetime,
   api_key)`.
7. Devolver render de `_route_multileg_fragment.html` con el contexto:
   - `distance_km`, `km_phase1`, `km_phase2`, `is_overnight`, `has_tolls`
   - `polyline` (para que el JS del mapa la renderice)
   - `waypoints` (lista para mostrar el resumen de paradas)
   - `error` (si lo hay)

---

### PASO 5 — Fragmento `_route_multileg_fragment.html` y JS del mapa

**Fragmento HTML** — renderiza:
- Mapa interactivo `<div id="route-map" style="height:400px">`.
- Lista de paradas con orden, label, botón eliminar, botón reordenar.
- Botón "Añadir parada" → abre input Places Autocomplete.
- Botón "Volver a base" → añade waypoint `is_base_return=True`.
- Botón "Calcular ruta" → dispara HTMX POST a `budgets:waypoints`.
- Sección de resultado (distancia, fases, peajes) — vacía hasta calcular.
- Campos hidden que se vuelcan al POST del wizard:
  ```html
  <input type="hidden" name="waypoints_json"          id="id_waypoints_json">
  <input type="hidden" name="route_distance_km"        id="id_route_distance_km">
  <input type="hidden" name="km_phase1"                id="id_km_phase1">
  <input type="hidden" name="km_phase2"                id="id_km_phase2">
  <input type="hidden" name="is_overnight"             id="id_is_overnight_route">
  <input type="hidden" name="route_toll_budget_cost"   id="id_route_toll_budget_cost">
  <input type="hidden" name="route_calculation_mode"   id="id_route_calculation_mode"
         value="API">
  ```

**JS del mapa** (`budgets/static/budgets/js/wizard_map.js`) — funciones:
- `initMap()` — inicializa `Map` centrado en `Base.latitude/longitude`,
  añade marker fijo de la Base (no eliminable).
- `addWaypoint(lat, lng, label, is_base_return)` — añade marker al mapa
  y entrada a la lista de paradas. Actualiza `id_waypoints_json`.
- `removeWaypoint(index)` — elimina marker y entrada.
- `reorderWaypoints()` — reordena la lista y actualiza el JSON hidden.
- `renderPolyline(encodedPolyline)` — decodifica y dibuja la ruta en el
  mapa tras recibir el resultado del servidor.
- `calcularRuta()` — serializa la lista de waypoints a JSON, vuelca en
  `id_waypoints_json` y dispara el HTMX POST a `budgets:waypoints`.
- Listener de clic en el mapa → `addWaypoint(lat, lng, "Punto manual", false)`.
- Places Autocomplete → al seleccionar lugar → `addWaypoint(lat, lng,
  place.formatted_address, false)`.

La carga de Maps JS API se hace en `wizard.html` con:
```html
<script src="https://maps.googleapis.com/maps/api/js
  ?key={{ GOOGLE_MAPS_API_KEY }}
  &libraries=places
  &callback=initMap"
  async defer>
</script>
```
`GOOGLE_MAPS_API_KEY` se inyecta desde `settings.py` vía context processor
o directamente en la vista.

---

### PASO 6 — Integración en `wizard.html`

El PASO 4 del wizard (ruta) tiene actualmente dos sub-modos: MANUAL y API.
Sustituir el bloque API actual (road_name + pk_km + dest_location) por el
nuevo contenedor que carga `_route_multileg_fragment.html` vía HTMX:

```html
<div id="route-multileg-section"
     hx-get="{% url 'budgets:route_multileg_init' %}"
     hx-trigger="load"
     hx-include="[name=base_id],[name=insurer_id]">
</div>
```

El bloque MANUAL (`_route_calc_fragment.html`) se mantiene sin cambios para
operarios que prefieran introducir km a mano.

Nuevo endpoint `BudgetRouteMultilegInitView` (GET) que devuelve el fragmento
con el mapa inicializado con las coordenadas de la Base seleccionada.

---

### PASO 7 — `BudgetWizardView.post()` — lectura de nuevos campos

En el POST de cierre del wizard, añadir la lectura de:

```python
waypoints_json_str = request.POST.get("waypoints_json", "")
km_phase1_str      = request.POST.get("km_phase1", "")
km_phase2_str      = request.POST.get("km_phase2", "")
is_overnight_route = request.POST.get("is_overnight_route", "") == "true"
```

Persistir en el budget antes de llamar a `calculate_budget()`:

```python
import json
if waypoints_json_str:
    try:
        budget.waypoints_json = json.loads(waypoints_json_str)
    except (json.JSONDecodeError, ValueError):
        budget.waypoints_json = None

if km_phase1_str:
    budget.km_phase1 = Decimal(km_phase1_str)
if km_phase2_str:
    budget.km_phase2 = Decimal(km_phase2_str)
if is_overnight_route:
    budget.is_overnight = True
```

El campo `route_calculation_mode` ya se lee en la lógica actual — asegurarse
de que `API` queda registrado cuando viene del planificador multi-parada.

---

### PASO 8 — Verificación E2E

1. Presupuesto servicio simple: Base → Recogida → Dejada → Base. Verificar
   `waypoints_json`, `km_phase1`, `route_distance_km`, `is_overnight=False`.
2. Presupuesto pernocta: Base → Recogida → Base(*) → Destino → Base.
   Verificar `km_phase1`, `km_phase2`, `is_overnight=True`.
3. Verificar que `calculate_budget()` usa `km_total` correctamente en ambos
   casos y que el total del presupuesto es coherente.
4. Verificar que el mapa renderiza la polyline de ruta tras calcular.

---

### ARCHIVOS A CREAR (nuevos, sin SWAP previo)

| Archivo | Tipo |
|---|---|
| `budgets/templates/budgets/_route_multileg_fragment.html` | Template nuevo |
| `budgets/static/budgets/js/wizard_map.js` | JS nuevo |
