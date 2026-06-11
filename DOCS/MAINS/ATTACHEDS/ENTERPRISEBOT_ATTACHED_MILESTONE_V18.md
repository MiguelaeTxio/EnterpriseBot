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

---

## Hoja de Ruta para la Siguiente Sesion (S013)

### CONTEXTO S013

S012 completo: tres fixes de BD aplicados directamente en MySQL (is_informational
DEFAULT 0, DROP COLUMN insurer_id, is_active DEFAULT 1). Decisión de negocio
BLOQUE 5 confirmada: peajes siempre facturados cuando hay ruta API. Nuevo
sistema de trabajo PEW adoptado: los archivos se editan en workspace del modelo.
services.py fue leído en S012 pero NO modificado — el patcher falló por el
sistema de trabajo anterior. En S013 se usa PEW desde el primer archivo.

### SISTEMA DE TRABAJO S013 — OBLIGATORIO

**PEW activo.** Para cualquier archivo de código (.py, .html, .js, .css):
1. El usuario sube el archivo al workspace vía upload o sftp get + upload.
2. El modelo lo edita en workspace con str_replace o reescritura completa.
3. py_compile / djlint en workspace antes de entregar.
4. present_files → usuario descarga → backup en SWAP → sftp put al servidor.

No se usan patchers remotos, heredocs ni bloques OLD/NEW en SWAP.

### BLOQUE 4 — Visualización dual de rutas en el wizard (PRIORIDAD MÁXIMA)

#### Paso 1 — Modificar calculate_route() en budgets/services.py (PEW)

El archivo services.py fue leído en S012 (EnterpriseBot07.txt en uploads).
Solicitar el archivo actualizado al inicio de S013 (puede haber cambiado).

Refactorizar en workspace:
- Extraer helper privado _call_routes_api() antes de calculate_route().
  Firma: _call_routes_api(origin_lat, origin_lng, dest_lat, dest_lng,
  departure_time_str, api_key, avoid_tolls=False) -> dict.
  Devuelve: {"distance_km": Decimal, "has_tolls": bool, "encoded_polyline": str}.
  FieldMask obligatorio: routes.distanceMeters, routes.duration,
  routes.polyline.encodedPolyline, routes.travelAdvisory.tollInfo.
  Si avoid_tolls=True: añadir "routeModifiers": {"avoidTolls": true} al payload.

- calculate_route() pasa a orquestar dos llamadas:
  Llamada 1: _call_routes_api(..., avoid_tolls=False) → route_with_tolls.
  Llamada 2: solo si route_with_tolls["has_tolls"]=True →
             _call_routes_api(..., avoid_tolls=True) → route_without_tolls.
             Forzar route_without_tolls["has_tolls"] = False.
  Si has_tolls=False: route_without_tolls = None.

- Nuevo contrato de retorno:
  {
      "route_with_tolls": {"distance_km": Decimal, "has_tolls": bool, "encoded_polyline": str},
      "route_without_tolls": {"distance_km": Decimal, "has_tolls": False, "encoded_polyline": str} | None,
      "error": None,
  }

- Compatibilidad BudgetRouteCalcView: esta vista usa calculate_route() —
  leer views.py para ver cómo consume el retorno actual y adaptar si es
  necesario al nuevo contrato antes de entregar.

#### Paso 2 — Adaptar BudgetRouteCalcView en budgets/views.py (PEW)

Leer views.py (solicitar al inicio si no está en uploads).
Localizar BudgetRouteCalcView y adaptar el consumo de calculate_route()
al nuevo dict dual. El fragmento _route_calc_fragment.html puede seguir
mostrando solo la ruta primaria (route_with_tolls) — no cambia su interfaz.

#### Paso 3 — Nuevo endpoint BudgetRouteDualView en budgets/views.py (PEW)

Añadir en views.py (mismo archivo, mismo PEW):
Vista GET. Parámetros: base_id, road_name, pk_km, dest_location, service_datetime.
Llama a calculate_route(). Devuelve _route_dual_fragment.html con contexto:
  - route_with_tolls: dict con distance_km, has_tolls, encoded_polyline.
  - route_without_tolls: dict o None.
  - show_dual: bool — True solo cuando route_without_tolls is not None.
Toda la lógica de presentación en la vista (Dumb Template).

#### Paso 4 — Template _route_dual_fragment.html (Neonato PEW)

Crear en workspace. Fragmento HTMX. Estructura:
- Si show_dual=False: mostrar solo ruta normal con distancia. Sin mapa ni
  radio buttons. Mensaje: "Ruta calculada: X,X km (sin peajes)".
- Si show_dual=True:
  - Contenedor mapa Leaflet altura 280px. Clase CSS: map-route-dual.
  - Importar Leaflet CDN (https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
    y leaflet.css) solo en este fragmento.
  - Radio buttons:
    id="route-opt-tolls" → "Con peajes (X,X km)" (marcado por defecto).
    id="route-opt-notolls" → "Sin peajes (X,X km)".
  - JS inline: inicializar mapa Leaflet, decodificar encoded_polyline con
    función manual (Google Encoded Polyline Algorithm — no requiere plugin),
    renderizar polyline con peajes en #003580 y sin peajes en #4A90D9,
    al cambiar radio button actualizar hidden inputs del wizard:
    #id_km_phase1, #id_route_toll_cost, #id_route_calculation_mode,
    #id_route_distance_km.
  - Variables de contexto pasadas desde la vista como JSON en data attributes
    del contenedor (data-route-with-tolls, data-route-without-tolls) para
    evitar interpolación Django en JS inline.
- Dumb template: ninguna lógica de presentación en el template.
- 0 errores djlint al cerrar.

#### Paso 5 — Modificar wizard.html y _wizard_steps_fragment.html (PEW)

Solicitar ambos archivos. En el paso 4b (step-route):
- Eliminar el botón "Calcular ruta" y el div route-result-section.
- Sustituir por: hx-get="{% url 'budgets:route_dual' %}" con los mismos
  parámetros que BudgetRouteCalcView. hx-trigger="load" para calcular
  automáticamente al cargar el paso.
- El fragmento _route_dual_fragment.html sustituye a _route_calc_fragment.html.

#### Paso 6 — Registrar en urls.py y ejecutar PAM

Añadir en budgets/urls.py:
  path("route-dual/", views.BudgetRouteDualView.as_view(), name="route_dual"),

Ejecutar PAM al finalizar para actualizar PROJECT_DIRECTORY con el nuevo template.

### BLOQUE 5 — Integración coste de peajes en presupuesto (PEW)

Decisión confirmada: peajes siempre facturados cuando hay ruta API.
Implementar en budgets/services.py dentro de calculate_budget():
- Después del bloque de km, si budget.route_calculation_mode == "API"
  y budget.route_toll_cost > 0:
  _add_line("TOLL_COST", "Peajes de autopista", Decimal("1"),
            budget.route_toll_cost, is_surcharge=False)
- El campo route_toll_cost del Budget se rellena en BudgetWizardView.post()
  con el valor del hidden input #id_route_toll_cost que actualiza el JS
  del fragmento dual al seleccionar la ruta.
- is_informational=False en esta BudgetLine — es facturable.
