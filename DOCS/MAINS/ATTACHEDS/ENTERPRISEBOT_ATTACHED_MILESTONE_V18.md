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

### PENDIENTES
- PRIORIDAD 2 — Peajes por tabla propia: aplazado por decision de negocio. La Routes API indica presencia de peajes (has_tolls=True) y el operario introduce el importe manualmente. Sin tabla TollSegment por el momento.
- PRIORIDAD 3 — Boton sync calendarios: implementado en S004 como BaseSyncCalendarsView.

---

## Hoja de Ruta para la Siguiente Sesion (S012)

### CONTEXTO S012

S011 completo: PASO 0 cerrado (vista detalle aseguradora muestra horario
nocturno, 0 errores djlint). Actualizacion en linea Routes API confirmada:
para Espana la API no devuelve coste de peajes. Arquitectura del BLOQUE 4
decidida: dos llamadas separadas (ruta normal + avoidTolls) + cruce de coste
con TollSegment en BD. services.py no fue modificado por agotamiento de cuota.

### DECISION DE NEGOCIO PREVIA (OBLIGATORIA ANTES DE IMPLEMENTAR)

El BLOQUE 5 requiere decision de Miguel Angel antes de implementar:
- Opcion A: coste de peajes como concepto facturable (BudgetLine) anadido
  automaticamente al presupuesto.
- Opcion B: campo informativo visible solo en el desglose ADMIN.
Esta decision condiciona el diseno de calculate_route() y BudgetRouteDualView.
Presentar y obtener confirmacion al inicio de S012 antes de codificar.

### BLOQUE 4 — Visualizacion dual de rutas en el wizard (PRIORIDAD MAXIMA)

Arquitectura verificada en S011. Dos llamadas separadas a Routes API v2:
- Llamada 1 (ruta normal): payload con TRAFFIC_AWARE, extraComputations
  omitido (API no devuelve coste para Espana), FieldMask:
  `routes.distanceMeters,routes.polyline.encodedPolyline,routes.travelAdvisory.tollInfo`.
  Extraer: distance_km, encoded_polyline, has_tolls (de travelAdvisory.tollInfo
  o de la presencia/ausencia de la seccion tollInfo en la respuesta).
- Llamada 2 (ruta sin peajes): mismo payload pero con
  `"routeModifiers": {"avoidTolls": true}`. FieldMask identico.
  Extraer: distance_km, encoded_polyline, has_tolls=False.

#### Paso 1 — Leer budgets/services.py

Solicitar services.py al inicio de sesion (no fue leido en S011).
Localizar calculate_route() y entender su estructura actual antes de
modificarla. Construir anclas desde el archivo real en disco.

#### Paso 2 — Modificar calculate_route() en budgets/services.py

Refactorizar calculate_route() para devolver un dict con dos entradas:

```python
{
    "route_with_tolls": {
        "distance_km": Decimal,
        "has_tolls": bool,
        "encoded_polyline": str,
    },
    "route_without_tolls": {
        "distance_km": Decimal,
        "has_tolls": False,
        "encoded_polyline": str,
    },
    "error": str | None,
}
```

La segunda llamada (avoidTolls) solo se ejecuta si la primera devuelve
has_tolls=True. Si has_tolls=False, route_without_tolls = None (no hay
ruta alternativa que mostrar, la ruta normal ya es sin peajes).

Compatibilidad: BudgetRouteCalcView existente usa calculate_route() —
verificar que sigue funcionando con el nuevo dict de retorno o adaptar
BudgetRouteCalcView al nuevo contrato antes de entregar.

#### Paso 3 — Nuevo endpoint HTMX BudgetRouteDualView en budgets/views.py

Vista GET que recibe los mismos parametros que BudgetRouteCalcView:
base_id, road_name, pk_km, dest_location, service_datetime.
Llama a calculate_route() y devuelve _route_dual_fragment.html con:
- Si route_without_tolls is None: mostrar solo la ruta normal (sin
  selector dual — no hay alternativa).
- Si route_without_tolls existe: mapa Leaflet con dos polylines +
  radio buttons de seleccion.
- Colores: azul marino #003580 (ruta con peajes), azul celeste #4A90D9
  (ruta sin peajes).
- Al seleccionar: actualizar hidden inputs km_phase1, route_toll_cost,
  route_calculation_mode, route_distance_km del wizard.
- Ruta: `budgets/route-dual/` con name `route_dual`.

#### Paso 4 — Template _route_dual_fragment.html (Neonato Puro)

Fragmento HTMX con:
- Contenedor mapa Leaflet altura fija 280px. Clase CSS map-route-dual
  definida en panel.css (anadir en el mismo patcher del CSS si aplica).
- Importar Leaflet CDN solo en este fragmento.
- Radio buttons con etiquetas: "Con peajes (X,X km)" y
  "Sin peajes (X,X km)" pasados como variables de contexto
  route_with_tolls y route_without_tolls desde la vista.
- JS inline: inicializar mapa Leaflet, decodificar polylines con
  L.Polyline desde encoded_polyline (requiere plugin leaflet-encoded
  o decodificacion manual), renderizar ambas polylines, manejar
  seleccion de radio y actualizar hidden inputs del formulario wizard.
- Dumb template: toda la logica de presentacion calculada en la vista.

#### Paso 5 — Modificar wizard.html y _wizard_steps_fragment.html

En el paso 4b del wizard (step-route):
- Reemplazar el boton "Calcular ruta" + div route-result-section por
  el nuevo endpoint HTMX route-dual/ con hx-get y hx-trigger=load.
- El fragmento dual sustituye completamente a _route_calc_fragment.html
  en ese contenedor.

#### Paso 6 — Registrar en urls.py y ejecutar PAM

Anadir ruta route-dual/ en budgets/urls.py. Ejecutar PAM al finalizar
el bloque completo para actualizar PROJECT_DIRECTORY con el nuevo template.

### BLOQUE 5 — Integracion coste de peajes en presupuesto

Implementar segun la decision de negocio obtenida al inicio de S012.
Si Opcion A (BudgetLine): anadir logica en calculate_budget() para crear
una BudgetLine con concepto TOLL_COST cuando route_toll_cost > 0.
Si Opcion B (campo informativo): mostrar route_toll_cost en la vista de
resultado del presupuesto solo para rol ADMIN, sin afectar al total.
