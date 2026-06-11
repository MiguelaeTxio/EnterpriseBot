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

### PENDIENTES
- PRIORIDAD 2 — Peajes por tabla propia: aplazado por decision de negocio. La Routes API indica presencia de peajes (has_tolls=True) y el operario introduce el importe manualmente. Sin tabla TollSegment por el momento.
- PRIORIDAD 3 — Boton sync calendarios: implementado en S004 como BaseSyncCalendarsView.

---

## Hoja de Ruta para la Siguiente Sesion (S011)

### CONTEXTO S011

S010 completo: tabla TollSegment operativa con ordenacion y UX mejorada,
horarios nocturnos centralizados en aseguradoras con calculo automatico,
fondo verde menta en inputs del panel. El BLOQUE 4 del wizard (visualizacion
dual de rutas) y el BLOQUE 5 (integracion peajes en presupuesto) quedan
pendientes y son la prioridad de S011.

### PASO 0 — Fix vista de detalle de aseguradora (PRIORIDAD ANTES DEL BLOQUE 4)

La vista de detalle de aseguradora (InsurerDetailView, template insurer_detail.html,
accesible mediante el boton de ojito en el listado de aseguradoras) no muestra
el horario nocturno asignado. Anadir en el bloque de datos generales de la vista
de detalle la informacion del NightSchedule:
- Si insurer.night_schedule esta asignado: mostrar nombre, night_start, night_end.
- Si no esta asignado: mostrar "Horario por defecto de la empresa" con el nombre
  y franja del NightSchedule is_default=True de la empresa, o "Sin configurar"
  si tampoco existe horario por defecto.
Archivos afectados: budgets/templates/budgets/insurer_detail.html.
La vista InsurerDetailView ya pasa el objeto insurer al contexto — no requiere
cambios en views.py salvo verificar que night_schedule esta en los datos
disponibles (FK con select_related si procede).

### BLOQUE 4 — Visualizacion dual de rutas en el wizard (PRIORIDAD MAXIMA)

Antes de codificar, el modelo DEBE actualizar en linea la documentacion
de la Routes API v2 (Paso 0 del BLOQUE 1 del anexo original ya completado
en S009 — usar ese analisis como base pero verificar cambios desde entonces).

#### Paso 1 — Modificar calculate_route() en budgets/services.py

Anadir parametro `compute_alternative=True` a la llamada Routes API:
- Incluir `"computeAlternativeRoutes": True` en el payload JSON.
- Anadir `"routes.polyline.encodedPolyline"` al X-Goog-FieldMask.
- Devolver en el dict de resultado: `route_with_tolls` y `route_without_tolls`,
  cada uno con sus campos: `distance_km`, `toll_cost`, `has_tolls`,
  `encoded_polyline`, `mode`.
- La ruta sin peajes se obtiene con una segunda llamada Routes API con
  `"routeModifiers": {"avoidTolls": true}` — o si la API devuelve
  alternativas suficientes, usar la alternativa sin peajes de la misma
  llamada. Investigar en linea cual es el comportamiento real de la API
  para rutas espanolas antes de decidir el enfoque.

#### Paso 2 — Nuevo endpoint HTMX BudgetRouteDualView en budgets/views.py

Vista GET que recibe los mismos parametros que BudgetRouteCalcView pero
devuelve un fragmento HTML con:
- Mapa Leaflet.js con dos polylines: azul marino (#003580) para ruta con
  peajes, azul celeste (#4A90D9) para ruta sin peajes (AVOID_TOLLS).
- Selector de radio button: "Ruta con peajes (X km, Y euros)" vs
  "Ruta sin peajes (X km, sin coste adicional)".
- Al seleccionar una ruta: actualizar los hidden inputs del wizard
  km_phase1, route_toll_cost, route_calculation_mode y route_distance_km.
- Ruta: `budgets/route-dual/` con name `route_dual`.

#### Paso 3 — Template _route_dual_fragment.html (Neonato Puro)

Fragmento HTMX con:
- Contenedor del mapa Leaflet (altura fija 280px, clase css definida en
  panel.css).
- Importar Leaflet desde CDN solo en este fragmento.
- Radio buttons con detalle de distancia y coste de cada opcion.
- JS inline: inicializar mapa, renderizar polylines, manejar seleccion
  y actualizar hidden inputs del wizard.

#### Paso 4 — Modificar wizard.html y _wizard_steps_fragment.html

En el paso 4b del wizard (step-route):
- Reemplazar el boton "Calcular ruta" + div `route-result-section` por
  el nuevo endpoint HTMX `route-dual/`.
- El fragmento dual sustituye al _route_calc_fragment.html existente
  en ese contenedor.

#### Paso 5 — Registrar en urls.py y PROJECT_DIRECTORY

Anadir ruta `route-dual/` en budgets/urls.py. Registrar
`_route_dual_fragment.html` en PROJECT_DIRECTORY via PAM al finalizar.

### BLOQUE 5 — Integracion coste de peajes en presupuesto (PENDIENTE)

Pendiente de decision de negocio por parte de Miguel Angel:
- Opcion A: concepto facturable anadido automaticamente como BudgetLine.
- Opcion B: campo informativo visible solo en el desglose ADMIN.
Presentar la decision al inicio de S011 antes de implementar.
