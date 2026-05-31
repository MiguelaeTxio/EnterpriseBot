# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md

# Anexo de Hito V18 - Gestion de Mapas y Geolocalizacion
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-05-30

---

## 1. Vision General del Hito

Este hito implementa la integracion de mapas y geolocalizacion en el modulo
de presupuestos de ASISTENCIA. Tiene dos ambitos diferenciados:

1. Gestion de coordenadas de bases: desde la vista dedicada de gestion de bases,
   el admin puede introducir la ubicacion de cada base mediante un mapa Google Maps
   con pin draggable y autocompletado de Places API. Las coordenadas se persisten
   en Base.latitude y Base.longitude.

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

Maps JavaScript API:
- Usada para el mapa interactivo con pin draggable en el panel de bases.
- Requiere bootstrap loader oficial (importLibrary pattern).

Places API (New):
- Usada para PlaceAutocompleteElement en el panel de bases.
- PENDIENTE: habilitar en GCP Console (proyecto 72810069987).

### 2.2. Modelo Base - arquitectura refactorizada en S001

En S001 se refactorizo completamente la arquitectura de bases:

- Base.insurer (ForeignKey) ELIMINADO.
- Base.company (ForeignKey a Company, nullable temporalmente) ANADIDO.
- Base.is_active conservado como flag global de empresa.
- Nueva tabla InsurerBase(insurer, base, is_active, unique_together).

La migracion aplicada es 0010_base_insurerbase_refactor.py (manual, con
SeparateDatabaseAndState por incompatibilidad Django+MySQL con unique_together).

Consolidacion de datos realizada en S001:
- 74 registros Base reducidos a 12 bases fisicas unicas.
- 74 registros InsurerBase creados correctamente.
- Base.company poblado en las 12 bases (company=Grupo Alvarez).
- Comando seed_bases actualizado para la nueva arquitectura.

### 2.3. Variable de entorno

GOOGLE_MAPS_API_KEY=***GOOGLE_MAPS_API_KEY_REDACTED***
Añadida al .env en S001. Verificada con tests de conectividad.

API key con restricciones en GCP:
- APIs habilitadas: Geocoding API, Routes API, Maps JavaScript API, Places API (New).
- Restriccion por IP: PENDIENTE (lunes).
- Limite diario Routes API 50 pet/dia: PENDIENTE (lunes).

### 2.4. Logica de calculo de ruta en presupuestos

DECISION DE DISENO S001 — Peajes con dependencia horaria:
Implementacion hibrida Opcion 2 + Opcion 4:
- La llamada a Routes API incluira departureTime construido desde
  service_date + service_time (nuevo campo en Budget).
- El coste de peaje devuelto por la API se mostrara como campo editable
  route_toll_cost en el wizard antes del submit final.

Campos nuevos en Budget (migracion 0011 pendiente):
- road_name: CharField max_length=50, blank=True, default=''
  verbose_name='Carretera', help_text='Nombre de la via (ej: A-45, N-331).'
- pk_km: DecimalField max_digits=8, decimal_places=3, null=True, blank=True
  verbose_name='Punto kilometrico'
- route_distance_km: DecimalField max_digits=8, decimal_places=3, null=True
  verbose_name='Distancia calculada (km)'
- route_toll_cost: DecimalField max_digits=8, decimal_places=2, null=True
  verbose_name='Coste de peajes'
- route_calculation_mode: CharField max_length=10, default='MANUAL'
  verbose_name='Modo de calculo km' (MANUAL / API)
- service_time: TimeField null=True, blank=True
  verbose_name='Hora del servicio'

Nueva funcion en budgets/services.py:
calculate_route(base, road_name, pk_km, service_datetime) -> dict
  Devuelve {'distance_km': Decimal, 'toll_cost': Decimal, 'mode': 'API'}.
  En caso de error de API lanza RouteCalculationError (excepcion nueva).

Nueva excepcion: class RouteCalculationError(Exception): pass

### 2.5. Panel de bases - estado en S001

Implementado en base_edit_fragment.html:
- Bootstrap loader oficial de Google Maps JS API.
- AdvancedMarkerElement con gmpDraggable: True.
- PlaceAutocompleteElement (Places API New) — funcional en codigo pero
  bloqueada por Places API (New) no habilitada en GCP (proyecto 72810069987).
- Al mover el pin actualiza inputs latitude y longitude del BaseForm.
- Al seleccionar lugar mueve mapa y pin y actualiza inputs.

### 2.6. Vista dedicada de bases - estado en S001

Creada BaseManageView en /panel/budgets/insurers/<pk>/bases/ con template
bases.html. Accesible desde el Panel 4 "Bases de servicio" en insurer_form.html
(edicion de aseguradora) y desde insurer_detail.html.

PENDIENTE: Vista global de bases en el menu lateral
(entrada independiente /panel/budgets/bases/ que liste TODAS las bases de
la empresa con filtro por aseguradora).

### 2.7. Vista "Gestionar bases" desde aseguradora - estado en S001

La vista BaseManageView en su estado actual muestra las bases de la empresa
(company_bases) pero necesita refactorizarse para implementar la logica
correcta segun el diseno acordado en S001:

DISENO ACORDADO:
- Arriba: resumen solo lectura de las bases activas de ESA aseguradora
  (badges verdes, sin botones). Iterar insurer.insurer_bases.filter(is_active=True).
- Abajo: listado completo de TODAS las bases de la empresa ordenado
  alfabeticamente, con toggle InsurerBase.is_active por HTMX (activa/inactiva
  para ESA aseguradora). La base se activa o desactiva al instante.
- El toggle en esta vista opera sobre InsurerBase.is_active, NO sobre Base.is_active.
- El toggle de Base.is_active (flag global) solo opera desde la vista global
  de bases del menu lateral.

---

## 3. Hoja de Ruta

### Paso 1 - Configuracion API key y test de conectividad
- Estado: COMPLETADO (S001)

### Paso 2 - Geolocalizacion de bases en panel (Google Maps)
- Estado: PARCIALMENTE COMPLETADO (S001)
- Pendiente: activar Places API (New) en GCP Console proyecto 72810069987.
- Pendiente: restriccion por IP y limite de cuota (lunes).

### Paso 3 - Campos de ruta en Budget + migracion
- Estado: PENDIENTE

### Paso 4 - Funcion calculate_route() en services.py
- Estado: PENDIENTE

### Paso 5 - Modo B en wizard (carretera + PK -> Routes API)
- Estado: PENDIENTE

### Paso 6 - Integracion peajes como concepto adicional en calculate_budget()
- Estado: PENDIENTE

### Paso 7 - Vista global de bases en menu lateral
- Estado: PENDIENTE
- URL: /panel/budgets/bases/
- Lista TODAS las bases de la empresa con filtro por aseguradora.
- Crear, editar con mapa Google Maps, calendario laboral con boton sync,
  toggle Base.is_active (flag global), dar de baja.
- Entrada en el menu lateral de budgets.

### Paso 8 - Refactorizacion BaseManageView segun diseno acordado
- Estado: PENDIENTE
- Ver seccion 2.7 para el diseno exacto.

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|----------|
| S001 | 2026-05-30/31 | P1, P2 (parcial), Arquitectura InsurerBase | Configuracion API key Google Maps. Bootstrap loader Google Maps JS. Refactorizacion completa arquitectura Base->InsurerBase: migracion manual 0010, consolidacion 74->12 bases, seed_bases actualizado. Vista BaseManageView creada. Panel 4 bases en insurer_form. Wizard operativo con nueva arquitectura. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (S002)

### Contexto

En S001 se completo la infraestructura de Google Maps y se refactorizo
completamente la arquitectura de bases a InsurerBase. El wizard funciona
correctamente. El mapa Google Maps carga en el panel de edicion de bases.
El PlaceAutocompleteElement esta implementado pero bloqueado por Places API
(New) no habilitada en GCP.

### ADVERTENCIAS CRITICAS

- GOOGLE_MAPS_API_KEY en .env: ***GOOGLE_MAPS_API_KEY_REDACTED***
- IVA_PERCENT = Decimal('21.00') en budgets/services.py. No mover.
- La migracion 0002_budget_apply_iva fue creada manualmente. No regenerar.
- El script seed_special_rate_tariffs.py esta en SWAP. Si hay reseed total
  de aseguradoras, ejecutarlo despues de seed_insurer_tariffs.
- La migracion 0010_base_insurerbase_refactor.py es MANUAL. No regenerar
  con makemigrations — rompe la migracion.
- Base.company es nullable temporalmente (null=True, blank=True). Pendiente
  hacer NOT NULL en una migracion posterior cuando sea oportuno.

### PRIORIDAD 0 - Activar Places API (New) en GCP

Antes de cualquier implementacion, activar Places API (New) en GCP Console:
- Proyecto: 72810069987
- APIs y servicios -> Biblioteca -> Places API (New) -> Habilitar.
- Verificar que el PlaceAutocompleteElement funciona en el panel de bases.

### PRIORIDAD 1 - Paso 8: Refactorizacion BaseManageView

Modificar BaseManageView en views.py y su template bases.html segun el
diseno acordado en S001 (ver seccion 2.7):

En views.py - BaseManageView.get():
  Cambiar logica para pasar al template:
  - insurer: el objeto Insurer.
  - active_insurer_bases: InsurerBase.objects.filter(insurer=insurer, is_active=True,
    base__is_active=True).select_related('base').order_by('base__name')
  - all_company_bases: Base.objects.filter(company=company_user.company,
    is_active=True).order_by('name') con anotacion de si tiene InsurerBase
    activo para esta aseguradora.
  - Para cada base en all_company_bases, anadir flag has_active_ib=True/False.
  Usar annotate o construir un dict: {base.pk: is_active_for_insurer}.

Nueva URL para toggle InsurerBase desde BaseManageView:
  path('insurers/<int:insurer_pk>/bases/<int:base_pk>/toggle/',
       views.InsurerBaseToggleView.as_view(), name='insurerbase_toggle')

Nueva vista InsurerBaseToggleView(AdminRoleRequiredMixin, View):
  POST: alterna InsurerBase.is_active para (insurer_pk, base_pk).
  Si no existe InsurerBase, crearlo con is_active=True.
  Devuelve fragmento HTMX con el toggle actualizado.

En bases.html: redisenar segun el diseno acordado.

### PRIORIDAD 2 - Paso 7: Vista global de bases en menu lateral

Nueva vista BaseGlobalView en /panel/budgets/bases/:
  - Lista Base.objects.filter(company=company_user.company).order_by('name').
  - Filtro por aseguradora (GET param insurer_id).
  - Para cada base muestra: nombre, municipio, coordenadas, calendario
    (synced/no synced), flag is_active global, boton editar con mapa,
    boton toggle Base.is_active, boton eliminar.
  - Formulario de alta de nueva base (nombre, municipio, sin aseguradora).
  - Boton "Sincronizar todos los calendarios" que lanza sync_base_calendars.
  - Entrada en el menu lateral junto a Aseguradoras e Historial.

Nueva URL: path('bases/', views.BaseGlobalView.as_view(), name='base_global')

Nuevo template: budgets/base_global.html

En base_edit_fragment.html el boton cancelar usa base.insurer.pk (roto).
Corregir el onclick para recargar la pagina correctamente desde la nueva
vista global: location.reload() es suficiente, eliminar el htmx.ajax previo.

### PRIORIDAD 3 - Paso 3: Campos de ruta en Budget + migracion

Anadir en budgets/models.py al modelo Budget (despues del campo km_phase1):
  road_name = CharField(max_length=50, blank=True, default='')
    verbose_name='Carretera', help_text='Nombre de la via (ej: A-45, N-331).'
  pk_km = DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    verbose_name='Punto kilometrico'
  route_distance_km = DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    verbose_name='Distancia calculada (km)'
  route_toll_cost = DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    verbose_name='Coste de peajes'
  route_calculation_mode = CharField(max_length=10, default='MANUAL')
    verbose_name='Modo de calculo km' (MANUAL / API)
  service_time = TimeField(null=True, blank=True)
    verbose_name='Hora del servicio'

Generar y aplicar migracion:
  python -m dotenv run python manage.py makemigrations budgets --name budget_route_fields
  python -m dotenv run python manage.py migrate budgets

### PRIORIDAD 4 - Paso 4: calculate_route() en services.py

Nueva funcion en budgets/services.py (antes de calculate_budget):

from datetime import datetime as _datetime

class RouteCalculationError(Exception):
    pass

def calculate_route(base: Base, road_name: str, pk_km: Decimal,
                    service_datetime: _datetime) -> dict:
    Devuelve {'distance_km': Decimal, 'toll_cost': Decimal, 'mode': 'API'}.
    Lanza RouteCalculationError en caso de fallo de API.

Logica interna:
1. Verificar base.latitude y base.longitude. Si nulas: llamar a Geocoding API
   con base.municipality, persistir resultado en base y continuar.
2. Construir query destino: f'{road_name} km {int(pk_km)} {base.municipality} Espana'.
3. Llamar a Geocoding API para obtener coordenadas del punto kilometrico.
4. Construir departureTime: service_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
   (UTC — advertencia: PythonAnywhere usa UTC).
5. Llamar a Routes API:
   POST https://routes.googleapis.com/directions/v2:computeRoutes
   Headers: X-Goog-Api-Key, X-Goog-FieldMask:
     routes.distanceMeters,routes.duration,routes.travelAdvisory.tollInfo
   Body: {origin: {location: {latLng: {latitude, longitude}}},
          destination: {location: {latLng: {latitude, longitude}}},
          travelMode: 'DRIVE',
          departureTime: service_datetime_str,
          extraComputations: ['TOLLS']}
6. Extraer distanceMeters -> distance_km = round(Decimal(meters) / 1000, 3).
7. Extraer tollInfo.estimatedPrice[0].units si existe -> toll_cost, else Decimal('0').
8. Devolver dict.

GOOGLE_MAPS_API_KEY se lee via os.environ.get('GOOGLE_MAPS_API_KEY', '').
