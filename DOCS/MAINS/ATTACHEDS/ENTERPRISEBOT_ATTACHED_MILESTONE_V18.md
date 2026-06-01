# ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md
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

### PENDIENTES

#### PRIORIDAD 0 - BUG ACTIVO (primera tarea de S004)
La variable _road se usa en dest_query_str pero el bloque que la define no esta
insertado en el archivo. Causa NameError silencioso que impide el calculo de ruta.
Ademas hay un bloque de debug (escritura a debug_route.json) que debe eliminarse.
La distancia devuelta es solo de ida - multiplicar por 2.

#### PRIORIDAD 1 - Mejora geocodificacion
Campo municipio/provincia del destino en el formulario del Modo B.

#### PRIORIDAD 2 - Peajes por tabla propia
Google Routes API no cubre precios para Espana. Tabla propia en BD.

#### PRIORIDAD 3 - Boton sync calendarios en BaseGlobalView.

---

## Hoja de Ruta para la Siguiente Sesion (S004)

### TAREA 1 - Fix calculate_route() en services.py (OBLIGATORIO PRIMERO)

Descargar services.py completo desde el servidor.
Leer las lineas del Step 2 (zona ~258-290).
Aplicar PMA con script Python en SWAP. Cuatro modificaciones atomicas:

MODIFICACION A - insertar antes de la linea pk_int = int(pk_km):
    import re as _re
    _road = road_name.strip().upper()
    _road = _re.sub(r'\s+', ' ', _road)
    _road = _re.sub(r'^([A-Z]+)-?([0-9])', r'\1-\2', _road)

MODIFICACION B - dest_query_str debe quedar exactamente:
    dest_query_str = f"{_road}, {pk_int}, Espana"
    (sin la palabra km, sin municipio de la base)

MODIFICACION C - bloque de retorno:
    return {
        'distance_km': _round2(distance_km * 2),
        'toll_cost':   _round2(toll_cost),
        'has_tolls':   has_tolls,
        'mode':        'API',
    }

MODIFICACION D - eliminar el bloque de debug completo:
    # DEBUG - log raw route data to SWAP.
    import json as _json_debug
    with open('/home/MiguelAeTxio/SWAP/debug_route.json', 'w') as _dbf:
        _json_debug.dump({...}, _dbf, indent=2)

Barrera de fuego obligatoria tras cada modificacion:
    grep de _road, dest_query_str y distance_km para confirmar que estan en disco.
    py_compile para verificar sintaxis.
Resultado esperado con a92 PK 203: aprox 180 km.

### TAREA 2 - Campo municipio del destino en Modo B
Input dest_location en _wizard_steps_fragment.html entre carretera y PK.
calcularRuta() en wizard.js: incluir dest_location en postValues.
BudgetRouteCalcView.post(): leer dest_location y pasarlo a calculate_route().
calculate_route(): usar dest_location en la query si no esta vacio.
Campo dest_location en modelo Budget y migracion correspondiente.

### TAREA 3 - Peajes por tabla propia
Diseno de modelo TollSegment: carretera, pk_inicio, pk_fin, coste_euros, tipo_vehiculo.
Logica de cruce en calculate_route() si has_tolls y carretera tiene entrada en TollSegment.
