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

## Hoja de Ruta para la Siguiente Sesion (S008)

### CONTEXTO DE LA REACTIVACION

En S007 se acuerda reactivar V18 para implementar:
1. Visualizacion de rutas en mapa estilo Google Maps integrada en el wizard
   de presupuestos: ruta con peajes (azul marino) y ruta sin peajes
   (azul celeste), con eleccion de ruta por parte del operario.
2. Calculo del coste de peajes en ambos casos (con y sin peajes) usando
   tabla propia poblada mediante web scraping de tarifas oficiales.
3. Web scraping de tarifas de peajes espanoles para poblar la BD.

### BLOQUE 1 -- Investigacion y diseno previo (OBLIGATORIO ANTES DE CODIFICAR)

Antes de escribir una sola linea de codigo, el modelo debe:

1. Actualizar conocimiento de la Google Maps/Routes API para visualizacion
   de rutas alternativas: buscar documentacion actual sobre Routes API v2
   (alternativeRoutes, polyline encoding, renderizado en Maps JavaScript API).
2. Investigar fuentes de tarifas de peajes espanoles susceptibles de scraping:
   - ministerio de transportes (mitma.gob.es)
   - operadoras: Abertis, Globalvia, Sacyr, AP-7, AP-2, etc.
   - APIs abiertas o datasets descargables si existen.
3. Presentar a Miguel Angel el diseno tecnico antes de implementar:
   - Modelo TollSegment propuesto (campos, relaciones).
   - Estrategia de scraping (fuente, frecuencia de actualizacion, formato).
   - Integracion en el wizard: donde se muestra el mapa, como se elige ruta,
     como se traspasa el coste de peajes al presupuesto.
   - Flujo de calculo: ruta con peajes (Routes API ya devuelve toll_cost) vs
     ruta sin peajes (Routes API con AVOID_TOLLS + calculo propio desde tabla).
   Esperar confirmacion de Miguel Angel antes de continuar.

### BLOQUE 2 -- Modelo TollSegment y migracion

Segun diseno confirmado en BLOQUE 1. Campos minimos esperados:
road_code (CharField), km_start (DecimalField), km_end (DecimalField),
toll_name (CharField), price_car (DecimalField), price_van (DecimalField),
price_truck (DecimalField), direction (CharField, choices: AB/BA/BOTH),
is_active (BooleanField), updated_at (DateTimeField auto).
Ejecutar makemigrations + migrate. Registrar en PROJECT_DIRECTORY.

### BLOQUE 3 -- Script de web scraping

Desarrollar siguiendo el protocolo WSCR (skill wscr):
- Ejecucion local obligatoria (Edge Processing).
- Salida: script Ready-to-Deploy que popula la tabla TollSegment via
  Django ORM (shell script o management command).
- Verificar con Miguel Angel el resultado antes de poblar produccion.

### BLOQUE 4 -- Visualizacion de rutas en wizard

Modificar el wizard de presupuestos para mostrar ambas rutas en mapa:
- Llamada a Routes API con alternativeRoutes=true.
- Ruta con peajes: polyline azul marino (#003580 o similar).
- Ruta sin peajes (AVOID_TOLLS): polyline azul celeste (#4A90D9 o similar).
- El operario elige una de las dos rutas haciendo clic en ella o mediante
  selector de radio button junto al mapa.
- Al elegir ruta: actualizar km_phase1, route_toll_cost y route_calculation_mode
  en el formulario. Si elige ruta sin peajes: calcular coste desde tabla
  TollSegment y mostrarlo igualmente como informacion al operario.

### BLOQUE 5 -- Integracion coste de peajes en presupuesto

Independientemente de la ruta elegida, el coste de peajes debe reflejarse
en el presupuesto como concepto separado si la aseguradora lo contempla.
Definir con Miguel Angel si el coste de peajes es:
- Un concepto facturable anadido automaticamente al BudgetLine, o
- Un campo informativo visible solo en el desglose ADMIN.
