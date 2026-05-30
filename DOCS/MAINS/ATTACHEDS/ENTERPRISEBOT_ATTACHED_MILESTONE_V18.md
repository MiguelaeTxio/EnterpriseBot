# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md

# Anexo de Hito V18 - Gestion de Mapas y Geolocalizacion
# Proyecto: EnterpriseBot
# Fecha de inicio: pendiente

---

## 1. Vision General del Hito

Este hito implementa la integracion de mapas y geolocalizacion en el modulo
de presupuestos de ASISTENCIA. Tiene dos ambitos diferenciados:

1. Gestion de coordenadas de bases: desde el panel de administracion,
   el admin puede introducir la ubicacion de cada base mediante un input de
   texto con autocompletado, que llama a la Geocoding API de Google y situa
   un pin en un mapa interactivo. Las coordenadas se persisten en
   Base.latitude y Base.longitude.

2. Calculo de ruta en presupuestos: en el wizard, el operario puede introducir
   el nombre de la carretera y el punto kilometrico donde se encuentra el
   vehiculo averiado. El sistema calcula la ruta mas rapida desde la base
   seleccionada hasta ese punto, obtiene la distancia real por carretera
   y el coste de peajes, y los incorpora al presupuesto.

---

## 2. Arquitectura Tecnica

### 2.1. APIs de Google a utilizar

Geocoding API:
- Endpoint: https://maps.googleapis.com/maps/api/geocode/json
- Coste: 5 USD / 1.000 peticiones. Umbral gratuito: 10.000 / mes.
- Uso: una sola vez por base al configurar sus coordenadas.

Routes API (sustituye a Directions API legacy):
- Endpoint: https://routes.googleapis.com/directions/v2:computeRoutes
- SKU Preferred con computeTollInfo: umbral gratuito 1.000 / mes.
- Volumen real Gruas Alvarez: ~220 peticiones/mes. Coste: 0 EUR/mes.

### 2.2. Modelo Base - campos ya existentes en produccion

Base.latitude y Base.longitude (DecimalField 9,6 nullable) - migracion 0008.
Base.municipality - usado como fuente de geocodificacion por defecto.

### 2.3. Variable de entorno necesaria

GOOGLE_MAPS_API_KEY - anadir al .env del proyecto.
API key con restricciones: IP servidor PythonAnywhere + APIs habilitadas:
Geocoding API y Routes API.
Limite de seguridad recomendado en GCP Console: 50 peticiones/dia en Routes.

### 2.4. Logica de calculo de ruta en presupuestos

El vehiculo averiado se encuentra en la ruta que va de la base al destino
en el km X. El operario introduce nombre de carretera (ej: A-45, N-331)
y punto kilometrico (ej: 23.5).

El sistema:
1. Toma Base.latitude/longitude. Si nulas, geocodifica Base.municipality
   y persiste el resultado.
2. Geocodifica el punto kilometrico: query tipo
   'carretera A-45 km 23 Malaga Espana' -> Geocoding API -> coordenadas destino.
3. Llama a Routes API: origin=base coords, destination=punto coords,
   computeTollInfo=True, travelMode=DRIVE.
4. Extrae distance_km y toll_cost del response.
5. Asigna distance_km a budget.km_phase1.
6. Si toll_cost > 0: anade concepto TOLL como BudgetLine adicional.

Campos nuevos en Budget (migracion nueva):
- road_name: CharField max_length=50, blank=True, default=''
- pk_km: DecimalField max_digits=8, decimal_places=3, null=True, blank=True
- route_distance_km: DecimalField max_digits=8, decimal_places=3, null=True
- route_toll_cost: DecimalField max_digits=8, decimal_places=2, null=True
- route_calculation_mode: CharField max_length=10, default='MANUAL' (MANUAL/API)

Nueva funcion en budgets/services.py:
calculate_route(base, road_name, pk_km) -> dict con distance_km y toll_cost.

### 2.5. Wizard - nuevo modo de entrada de km

El paso de kilometros (Paso 4 actual) ofrece dos modos:
- Modo A Manual: el operario introduce km_phase1 directamente (flujo actual).
- Modo B Carretera + PK: el operario introduce road_name y pk_km.
  Un boton 'Calcular ruta' (HTMX POST) llama a calculate_route() y rellena
  km_phase1 automaticamente. Si hay peajes, se muestran como informacion
  adicional antes del calculo final.

### 2.6. Panel de bases - input de geolocalizacion

En base_edit_fragment.html y BaseUpdateView:
- Input texto location_search (no persistido) para buscar ubicacion.
- Boton Buscar que llama a Nominatim (https://nominatim.openstreetmap.org/search)
  y mueve el pin al primer resultado.
- Mapa Leaflet.js con pin draggable. Al mover el pin actualiza los inputs
  latitude y longitude del formulario BaseForm.
- Al guardar, BaseUpdateView persiste latitude y longitude en Base.
- Recomendacion: Leaflet.js (MIT, sin coste) + Nominatim para la interfaz.
  Reservar Google Geocoding API para el calculo de rutas en presupuestos.

---

## 3. Hoja de Ruta

### Paso 1 - Configuracion API key y test de conectividad
- Estado: PENDIENTE

### Paso 2 - Geolocalizacion de bases en panel (Leaflet + Nominatim)
- Estado: PENDIENTE

### Paso 3 - Campos de ruta en Budget + migracion
- Estado: PENDIENTE

### Paso 4 - Funcion calculate_route() en services.py
- Estado: PENDIENTE

### Paso 5 - Modo B en wizard (carretera + PK -> Routes API)
- Estado: PENDIENTE

### Paso 6 - Integracion peajes como concepto adicional en calculate_budget()
- Estado: PENDIENTE

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|----------|

---

## 5. Hoja de Ruta para la Siguiente Sesion (S001)

### Contexto

Primer hito de geolocalizacion del proyecto. Antes de implementar nada
hay que configurar la infraestructura de Google Cloud y verificar la
conectividad con ambas APIs desde el servidor de PythonAnywhere.

### ADVERTENCIAS CRITICAS

- GOOGLE_MAPS_API_KEY debe estar en .env antes de ejecutar cualquier paso.
- La API key debe tener restringidas las IPs al servidor PythonAnywhere
  y solo las APIs habilitadas: Geocoding API y Routes API.
- Configurar limite diario de 50 peticiones en Routes API en GCP Console.
- IVA_PERCENT = Decimal('21.00') en budgets/services.py. No mover.
- La migracion 0002_budget_apply_iva fue creada manualmente. No regenerar.
- El script seed_special_rate_tariffs.py esta en SWAP. Si hay reseed total
  de aseguradoras, ejecutarlo despues de seed_insurer_tariffs.

### PRIORIDAD 0 - Paso 1: configuracion API key y test de conectividad

1. Acceder a GCP Console (console.cloud.google.com).
2. Habilitar: Geocoding API y Routes API.
3. Crear API key con restricciones de IP (IP PythonAnywhere) y APIs.
4. Anadir al .env del proyecto: GOOGLE_MAPS_API_KEY=<clave>.
5. Configurar limite diario en Routes API: 50 peticiones/dia.
6. Test conectividad Geocoding:
   python -m dotenv run python -c "
   import requests, os
   r = requests.get(
       'https://maps.googleapis.com/maps/api/geocode/json',
       params={'address': 'Malaga, Espana', 'key': os.environ['GOOGLE_MAPS_API_KEY']}
   )
   print(r.status_code, r.json()['status'])
   "
7. Test conectividad Routes API:
   python -m dotenv run python -c "
   import requests, os
   r = requests.post(
       'https://routes.googleapis.com/directions/v2:computeRoutes',
       headers={
           'Content-Type': 'application/json',
           'X-Goog-Api-Key': os.environ['GOOGLE_MAPS_API_KEY'],
           'X-Goog-FieldMask': 'routes.distanceMeters,routes.duration',
       },
       json={
           'origin': {'location': {'latLng': {'latitude': 36.7213, 'longitude': -4.4214}}},
           'destination': {'location': {'latLng': {'latitude': 37.1773, 'longitude': -3.5986}}},
           'travelMode': 'DRIVE',
       }
   )
   print(r.status_code, r.text[:200])
   "

### PRIORIDAD 1 - Paso 2: geolocalizacion de bases en panel

Modificar base_edit_fragment.html y BaseUpdateView:
- Anadir Leaflet.js via CDN (https://cdnjs.cloudflare.com/ajax/libs/leaflet/).
- Input texto location_search para buscar direccion.
- Boton Buscar que llama a Nominatim y mueve el pin al primer resultado.
- Mapa Leaflet con pin draggable. Al mover el pin, actualiza los inputs
  latitude y longitude del BaseForm.
- Al guardar, BaseUpdateView persiste latitude y longitude en Base.
- Si Base ya tiene coordenadas, el mapa muestra el pin en esas coordenadas.

### PRIORIDAD 2 - Paso 3: campos de ruta en Budget + migracion

Anadir en budgets/models.py al modelo Budget:
- road_name = CharField(max_length=50, blank=True, default='')
  verbose_name='Carretera', help_text='Nombre de la via (ej: A-45, N-331).'
- pk_km = DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
  verbose_name='Punto kilometrico'
- route_distance_km = DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
  verbose_name='Distancia calculada (km)'
- route_toll_cost = DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
  verbose_name='Coste de peajes'
- route_calculation_mode = CharField(max_length=10, default='MANUAL')
  verbose_name='Modo de calculo km' (MANUAL / API)

Generar migracion:
python -m dotenv run python manage.py makemigrations budgets --name budget_route_fields
python -m dotenv run python manage.py migrate budgets

### PRIORIDAD 3 - Paso 4: funcion calculate_route() en services.py

Nueva funcion en budgets/services.py:

def calculate_route(base, road_name: str, pk_km: Decimal) -> dict:
    Devuelve {'distance_km': Decimal, 'toll_cost': Decimal, 'mode': 'API'}.
    En caso de error de API, lanza RouteCalculationError (excepcion nueva).

Logica interna:
1. Verificar que base.latitude y base.longitude no sean nulas.
   Si son nulas: llamar a Geocoding API con base.municipality,
   persistir resultado en base y continuar.
2. Construir query destino: f'{road_name} km {pk_km} {base.municipality} Espana'.
3. Llamar a Geocoding API para obtener coordenadas del punto kilometrico.
4. Llamar a Routes API con computeTollInfo=True.
5. Extraer distanceMeters -> distance_km = round(distanceMeters / 1000, 3).
6. Extraer tollInfo.estimatedPrice[0].units si existe -> toll_cost, else 0.
7. Devolver dict.

Nueva excepcion en budgets/services.py:
class RouteCalculationError(Exception): pass

Anadir al .env: GOOGLE_MAPS_API_KEY
Verificar que requests esta en requirements.in (ya esta).
