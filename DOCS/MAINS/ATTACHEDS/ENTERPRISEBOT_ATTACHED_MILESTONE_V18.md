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
- Habilitada en GCP Console (proyecto 72810069987). Operativa desde S001.

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
Anadida al .env en S001. Verificada con tests de conectividad.

API key con restricciones en GCP:
- APIs habilitadas: Geocoding API, Routes API, Maps JavaScript API, Places API (New).
- Restriccion por IP: PENDIENTE.
- Limite diario Routes API 50 pet/dia: PENDIENTE.

### 2.4. Logica de calculo de ruta en presupuestos

DECISION DE DISENO S001 — Peajes con dependencia horaria:
Implementacion hibrida Opcion 2 + Opcion 4:
- La llamada a Routes API incluye departureTime construido desde
  service_date + service_time (campo nuevo en Budget).
- El coste de peaje devuelto por la API se mostrara como campo editable
  route_toll_cost en el wizard antes del submit final.

Campos nuevos en Budget (migracion 0011 aplicada en S002):
- road_name: CharField max_length=50, blank=True, default=''
- pk_km: DecimalField max_digits=8, decimal_places=3, null=True, blank=True
- route_distance_km: DecimalField max_digits=8, decimal_places=3, null=True, blank=True
- route_toll_cost: DecimalField max_digits=8, decimal_places=2, null=True, blank=True
- route_calculation_mode: CharField max_length=10, default='MANUAL' (MANUAL/API)
- service_time: TimeField null=True, blank=True

Funcion calculate_route() implementada en budgets/services.py (S002):
- Parametros: base, road_name, pk_km, service_datetime
- Devuelve: {'distance_km': Decimal, 'toll_cost': Decimal, 'mode': 'API'}
- Lanza RouteCalculationError en caso de fallo de API.
- Geocodifica la base si no tiene coordenadas y persiste el resultado.
- Usa urllib.request (sin dependencias externas).

### 2.5. Panel de bases - estado en S002

BaseManageView refactorizada en S002 segun diseno acordado:
- Seccion superior: resumen solo lectura de bases activas de la aseguradora
  (badges verdes, InsurerBase.is_active=True AND Base.is_active=True).
- Seccion inferior: listado completo de bases de la empresa con toggle
  InsurerBase.is_active por HTMX (InsurerBaseToggleView).
- El toggle opera sobre InsurerBase.is_active, NO sobre Base.is_active.

Nueva vista InsurerBaseToggleView: POST insurers/<insurer_pk>/bases/<base_pk>/toggle/
Nuevo template: budgets/partials/insurerbase_toggle_fragment.html

### 2.6. Vista global de bases - estado en S002

BaseGlobalView implementada en S002 en /panel/budgets/bases/global/
- Lista todas las bases de la empresa con filtro GET por aseguradora.
- Columnas: nombre, municipio, coordenadas, calendario, aseguradoras
  vinculadas (con badge activa/inactiva por aseguradora), flag is_active
  global, toggle global Base.is_active, editar, eliminar.
- Toggle global opera sobre Base.is_active (flag global).
- Formulario de alta de nueva base (sin aseguradora en el alta).
- Entrada en el sidebar bajo la seccion "Asistencia" (label renombrado
  desde "Presupuestos" en S002).

Template: budgets/base_global.html

### 2.7. Vista "Gestionar bases" desde aseguradora - estado en S002

La vista BaseManageView quedo refactorizada en S002 segun el diseno acordado.

DISENO IMPLEMENTADO:
- Arriba: resumen solo lectura de bases activas de ESA aseguradora
  (badges verdes). Itera active_insurer_bases (InsurerBase activos).
- Abajo: listado completo de TODAS las bases de la empresa con toggle
  InsurerBase.is_active por HTMX (activa/inactiva para ESA aseguradora).
- El toggle en esta vista opera sobre InsurerBase.is_active.
- El toggle de Base.is_active solo opera desde la vista global de bases.

### 2.8. UX del mapa Google Maps - estado en S002

Mejora UX implementada en S002 en base_edit_fragment.html:
- Sustituido AdvancedMarkerElement (requeria mapId, pin invisible) por
  google.maps.Marker clasico (pin rojo visible sin mapId).
- Pin SVG fijo en el centro del mapa (overlay CSS, z-index 10).
- Badge de coordenadas en tiempo real (monospace, fondo semitransparente).
- Patron "mapa movil bajo pin fijo": usuario mueve el mapa, el pin
  permanece centrado. Al idle del mapa: marker clasico se sincroniza
  al centro, inputs lat/lng y badge se actualizan.
- PlaceAutocompleteElement conservado: al seleccionar lugar, el mapa
  se centra e idle se dispara automaticamente actualizando todo.

---

## 3. Hoja de Ruta

### Paso 1 - Configuracion API key y test de conectividad
- Estado: COMPLETADO (S001)

### Paso 2 - Geolocalizacion de bases en panel (Google Maps)
- Estado: COMPLETADO (S001 + S002)
- UX mapa mejorada en S002: Marker clasico + pin fijo + badge coords.

### Paso 3 - Campos de ruta en Budget + migracion
- Estado: COMPLETADO (S002)
- Migracion 0011_budget_route_fields aplicada.

### Paso 4 - Funcion calculate_route() en services.py
- Estado: COMPLETADO (S002)
- RouteCalculationError definida. Geocodificacion automatica de base.

### Paso 5 - Modo B en wizard (carretera + PK -> Routes API)
- Estado: PENDIENTE

### Paso 6 - Integracion peajes como concepto adicional en calculate_budget()
- Estado: PENDIENTE

### Paso 7 - Vista global de bases en menu lateral
- Estado: COMPLETADO (S002)
- URL: /panel/budgets/bases/global/
- Pendiente: boton "Sincronizar todos los calendarios" (lanza sync_base_calendars).

### Paso 8 - Refactorizacion BaseManageView segun diseno acordado
- Estado: COMPLETADO (S002)

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|----------|
| S001 | 2026-05-30/31 | P1, P2 (parcial), Arquitectura InsurerBase | Configuracion API key Google Maps. Bootstrap loader Google Maps JS. Refactorizacion completa arquitectura Base->InsurerBase: migracion manual 0010, consolidacion 74->12 bases, seed_bases actualizado. Vista BaseManageView creada. Panel 4 bases en insurer_form. Wizard operativo con nueva arquitectura. |
| S002 | 2026-05-31 | P2 (completo), P3, P4, UX mapa, bugs InsurerBase | Auditoria y correccion de 4 bugs causados por refactorizacion InsurerBase (insurer.bases.count, base.insurer.pk, BaseManageView, base_list_fragment). Refactorizacion completa BaseManageView + InsurerBaseToggleView. Vista global BaseGlobalView. Sidebar renombrado a Asistencia. Campos de ruta en Budget (migracion 0011). calculate_route() implementada. UX mapa mejorada: Marker clasico + pin fijo + badge coords. Skills pisa y session-standards actualizadas (reload, Comando S). |

---

## 5. Hoja de Ruta para la Siguiente Sesion (S003)

### Contexto

En S002 se completaron los Pasos 3 y 4 (campos de ruta en Budget y funcion
calculate_route()), la refactorizacion completa de BaseManageView, la vista
global de bases y la mejora UX del mapa. El wizard sigue funcionando en
modo MANUAL exclusivamente. S003 conecta la infraestructura con el wizard.

### ADVERTENCIAS CRITICAS

- GOOGLE_MAPS_API_KEY en .env: ***GOOGLE_MAPS_API_KEY_REDACTED***
- IVA_PERCENT = Decimal('21.00') en budgets/services.py. No mover.
- La migracion 0002_budget_apply_iva fue creada manualmente. No regenerar.
- El script seed_special_rate_tariffs.py esta en SWAP. Si hay reseed total
  de aseguradoras, ejecutarlo despues de seed_insurer_tariffs.
- La migracion 0010_base_insurerbase_refactor.py es MANUAL. No regenerar.
- La migracion 0011_budget_route_fields.py es AUTOGENERADA. No editar.
- Base.company es nullable temporalmente (null=True, blank=True).

### PRIORIDAD 1 - Paso 5: Modo B en wizard

El wizard actual tiene los pasos 1-9 en wizard.html. El Modo B se inserta
como paso opcional entre PASO 4 (kilometros) y PASO 5 (desbloqueo).

#### Arquitectura del Modo B

El Modo B es un bloque opcional activado por un toggle. Solo aparece si
la base seleccionada tiene coordenadas (base.latitude AND base.longitude).
Si no hay coordenadas, el bloque no se muestra y el operario introduce km
manualmente como siempre.

El flujo completo del Modo B es:

1. Operario activa el toggle "Calcular ruta por carretera".
2. Aparecen tres campos: road_name, pk_km, service_time.
3. Operario rellena los tres campos y pulsa "Calcular ruta".
4. HTMX POST a BudgetRouteCalcView con {base_id, road_name, pk_km,
   service_date, service_time}.
5. La vista llama a calculate_route() y devuelve el fragmento
   _route_calc_fragment.html con distancia y peajes calculados.
6. El operario ve el resultado y puede editar route_toll_cost si procede.
7. Al hacer submit del formulario principal, los valores
   route_distance_km, route_toll_cost, route_calculation_mode='API'
   y service_time se incluyen como inputs ocultos.
8. BudgetWizardView.post() lee estos campos adicionales y los persiste.

#### Nueva vista BudgetRouteCalcView

En budgets/views.py, justo antes de BudgetVehicleTypesView (linea ~472):

class BudgetRouteCalcView(AssistanceRequiredMixin, View):
    """
    HTMX POST endpoint. Receives base_id, road_name, pk_km, service_date
    and service_time. Calls calculate_route() and returns the route result
    fragment. Returns error fragment on RouteCalculationError.
    """

    def post(self, request):
        company_user = _get_company_user(request)
        data = request.POST

        # Validar campos requeridos
        base_id = data.get('base_id', '').strip()
        road_name = data.get('road_name', '').strip()
        pk_km_raw = data.get('pk_km', '').strip()
        service_date_str = data.get('service_date', '').strip()
        service_time_str = data.get('service_time', '').strip()

        if not all([base_id, road_name, pk_km_raw, service_date_str, service_time_str]):
            return render(request, 'budgets/_route_calc_fragment.html',
                {'error': 'Rellena todos los campos para calcular la ruta.'})

        from decimal import Decimal
        import datetime as _dt
        try:
            base = Base.objects.get(pk=int(base_id), company=company_user.company)
            pk_km = Decimal(pk_km_raw.replace(',', '.'))
            service_date = _dt.date.fromisoformat(service_date_str)
            service_time_obj = _dt.time.fromisoformat(service_time_str)
            service_datetime = _dt.datetime.combine(service_date, service_time_obj)
        except Exception as exc:
            return render(request, 'budgets/_route_calc_fragment.html',
                {'error': f'Datos invalidos: {exc}'})

        from budgets.services import calculate_route, RouteCalculationError
        try:
            result = calculate_route(base, road_name, pk_km, service_datetime)
        except RouteCalculationError as exc:
            return render(request, 'budgets/_route_calc_fragment.html',
                {'error': str(exc)})

        return render(request, 'budgets/_route_calc_fragment.html', {
            'distance_km': result['distance_km'],
            'toll_cost': result['toll_cost'],
            'road_name': road_name,
            'pk_km': pk_km,
            'service_time': service_time_str,
        })

#### Nueva ruta en budgets/urls.py

Insertar antes de la ruta 'vehicle-types/':

    path(
        'route-calc/',
        views.BudgetRouteCalcView.as_view(),
        name='route_calc',
    ),

#### Cambios en wizard.html

Insertar nuevo bloque entre PASO 4 (step-km) y PASO 5 (step-unlock).
El bloque tiene id='step-route' y clase 'wizard-step d-none'.

Estructura del bloque:

<div class="card mb-3 wizard-step d-none border-info" id="step-route">
  <div class="card-body">
    <!-- Toggle de activacion del Modo B -->
    <div class="form-check form-switch mb-3">
      <input class="form-check-input" type="checkbox"
             id="id_use_route_calc" onchange="toggleRouteCalc(this.checked)">
      <label class="form-check-label fw-semibold" for="id_use_route_calc">
        4b. Calcular kilometros por carretera (opcional)
      </label>
    </div>
    <!-- Campos del Modo B — ocultos por defecto -->
    <div id="route-calc-fields" class="d-none">
      <div class="row g-2 mb-2">
        <div class="col-12 col-md-5">
          <label class="form-label small">Carretera</label>
          <input type="text" class="form-control" id="id_road_name_calc"
                 placeholder="Ej: A-45, N-331">
        </div>
        <div class="col-6 col-md-3">
          <label class="form-label small">Punto kilometrico</label>
          <input type="number" class="form-control" id="id_pk_km_calc"
                 step="0.001" min="0" placeholder="Ej: 127.5">
        </div>
        <div class="col-6 col-md-4">
          <label class="form-label small">Hora del servicio</label>
          <input type="time" class="form-control" id="id_service_time_calc">
        </div>
      </div>
      <button type="button" class="btn btn-outline-info btn-sm"
              onclick="calcularRuta()">
        <i class="bi bi-signpost-2 me-1"></i>Calcular ruta
      </button>
      <!-- Fragmento de resultado — sustituido por HTMX -->
      <div id="route-result-section" class="mt-2"></div>
      <!-- Inputs ocultos enviados con el formulario -->
      <input type="hidden" name="road_name" id="id_road_name" value="">
      <input type="hidden" name="pk_km" id="id_pk_km" value="">
      <input type="hidden" name="service_time" id="id_service_time" value="">
      <input type="hidden" name="route_distance_km" id="id_route_distance_km" value="">
      <input type="hidden" name="route_toll_cost" id="id_route_toll_cost" value="">
      <input type="hidden" name="route_calculation_mode"
             id="id_route_calculation_mode" value="MANUAL">
    </div>
  </div>
</div>

El bloque step-route se muestra en la funcion showStep al activarse
el vehicle-type-section (junto con los demas pasos), SOLO si la base
seleccionada tiene coordenadas. La logica JS:

function toggleRouteCalc(active) {
  document.getElementById('route-calc-fields').classList.toggle('d-none', !active);
  if (!active) {
    // Limpiar resultado y resetear inputs ocultos
    document.getElementById('route-result-section').innerHTML = '';
    document.getElementById('id_route_calculation_mode').value = 'MANUAL';
    document.getElementById('id_route_distance_km').value = '';
    document.getElementById('id_route_toll_cost').value = '';
  }
}

function calcularRuta() {
  const baseId = document.querySelector('[name=base_id]')
                 || document.querySelector('input[name=base_id]');
  const roadName = document.getElementById('id_road_name_calc').value.trim();
  const pkKm = document.getElementById('id_pk_km_calc').value.trim();
  const serviceDate = document.getElementById('id_service_date').value;
  const serviceTime = document.getElementById('id_service_time_calc').value;
  if (!roadName || !pkKm || !serviceDate || !serviceTime) {
    alert('Rellena carretera, punto kilometrico, fecha y hora del servicio.');
    return;
  }
  const params = new FormData();
  params.append('base_id', baseId ? baseId.value : '');
  params.append('road_name', roadName);
  params.append('pk_km', pkKm);
  params.append('service_date', serviceDate);
  params.append('service_time', serviceTime);
  params.append('csrfmiddlewaretoken',
    document.querySelector('[name=csrfmiddlewaretoken]').value);
  htmx.ajax('POST', '{% url "budgets:route_calc" %}', {
    target: '#route-result-section',
    swap: 'innerHTML',
    values: Object.fromEntries(params),
  });
}

// Mostrar step-route solo si la base tiene coordenadas
// bases_map_with_coords = JSON map pk -> has_coords (bool)
// Se calcula en BudgetWizardView.get() y se pasa al template.
function updateRouteStepVisibility() {
  const baseIdInput = document.querySelector('[name=base_id]');
  const basePk = baseIdInput ? baseIdInput.value : '';
  const hasCoords = basePk && basesMapWithCoords[basePk];
  const stepRoute = document.getElementById('step-route');
  if (stepRoute) {
    if (hasCoords) {
      stepRoute.classList.remove('d-none');
    } else {
      stepRoute.classList.add('d-none');
      // Desactivar modo B si la base no tiene coordenadas
      document.getElementById('id_use_route_calc').checked = false;
      toggleRouteCalc(false);
    }
  }
}

#### Nuevo contexto en BudgetWizardView.get()

Anadir al ctx de BudgetWizardView.get():

  import json as _json2
  bases_map_with_coords = _json2.dumps({
      str(ib.base.pk): bool(ib.base.latitude and ib.base.longitude)
      for ins in insurers
      for ib in InsurerBase.objects.filter(
          insurer=ins, is_active=True, base__is_active=True
      ).select_related('base')
  })
  ctx['bases_map_with_coords'] = bases_map_with_coords

En wizard.html, bajo la declaracion de alwaysIvaMap:
  const basesMapWithCoords = {{ bases_map_with_coords|safe }};

#### Cambios en BudgetWizardView.post()

Anadir la lectura de los campos de ruta tras la lectura de base_id:

  road_name = data.get('road_name', '').strip()
  pk_km_raw = data.get('pk_km', '').strip()
  route_distance_km_raw = data.get('route_distance_km', '').strip()
  route_toll_cost_raw = data.get('route_toll_cost', '').strip()
  route_calculation_mode = data.get('route_calculation_mode', 'MANUAL').strip()
  service_time_raw = data.get('service_time', '').strip()

  import datetime as _dt2
  from decimal import Decimal as _Dec
  route_distance_km = _Dec(route_distance_km_raw) if route_distance_km_raw else None
  route_toll_cost = _Dec(route_toll_cost_raw) if route_toll_cost_raw else None
  service_time_obj = _dt2.time.fromisoformat(service_time_raw) if service_time_raw else None

Anadir al Budget(...) constructor:
  road_name=road_name,
  pk_km=_Dec(pk_km_raw.replace(',', '.')) if pk_km_raw else None,
  route_distance_km=route_distance_km,
  route_toll_cost=route_toll_cost,
  route_calculation_mode=route_calculation_mode,
  service_time=service_time_obj,

#### Nuevo template _route_calc_fragment.html

Neonato Puro. Ruta:
/home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/templates/budgets/_route_calc_fragment.html

Estructura:
{% if error %}
<div class="alert alert-danger py-2 small mt-2">
  <i class="bi bi-exclamation-circle me-1"></i>{{ error }}
</div>
{% else %}
<div class="alert alert-success py-2 small mt-2">
  <i class="bi bi-signpost-2 me-1"></i>
  Ruta calculada: <strong>{{ distance_km }} km</strong>
  {% if toll_cost %}
  — Peajes estimados: <strong>{{ toll_cost }} EUR</strong>
  {% endif %}
</div>
<!-- Inputs visibles editables: el operario puede corregir el peaje -->
<div class="row g-2 mt-1">
  <div class="col-6 col-md-4">
    <label class="form-label small mb-1">Distancia calculada (km)</label>
    <input type="number" class="form-control form-control-sm"
           id="id_route_distance_km_display"
           value="{{ distance_km }}" step="0.001" readonly>
  </div>
  <div class="col-6 col-md-4">
    <label class="form-label small mb-1">Peajes (EUR) — editable</label>
    <input type="number" class="form-control form-control-sm"
           id="id_route_toll_cost_display"
           value="{{ toll_cost }}" step="0.01"
           onchange="actualizarPeaje(this.value)">
  </div>
</div>
<script>
// Al cargar el fragmento, poblar los inputs ocultos del formulario principal.
(function() {
  var distKm = "{{ distance_km }}";
  var tollCost = "{{ toll_cost }}";
  var roadName = "{{ road_name }}";
  var pkKm = "{{ pk_km }}";
  var serviceTime = "{{ service_time }}";
  document.getElementById('id_route_distance_km').value = distKm;
  document.getElementById('id_route_toll_cost').value = tollCost;
  document.getElementById('id_route_calculation_mode').value = 'API';
  document.getElementById('id_road_name').value = roadName;
  document.getElementById('id_pk_km').value = pkKm;
  document.getElementById('id_service_time').value = serviceTime;
})();
function actualizarPeaje(val) {
  document.getElementById('id_route_toll_cost').value = val;
}
</script>
{% endif %}

### PRIORIDAD 2 - Paso 6: Peajes como concepto adicional en calculate_budget()

En budgets/services.py, dentro de calculate_budget(), anadir la logica
de peajes como concepto adicional DESPUES del calculo de IVA:

if budget.route_toll_cost and budget.route_toll_cost > 0:
    toll_line = BudgetLine(
        concept_code='TOLL',
        concept_label=f'Peajes ({budget.road_name})',
        units=Decimal('1'),
        unit_price=budget.route_toll_cost,
        subtotal=budget.route_toll_cost,
        is_surcharge=False,
        sort_order=sort_order,
    )
    lines.append(toll_line)
    total += budget.route_toll_cost
    sort_order += 1

Nota: este bloque va ANTES del calculo de IVA para que el IVA se aplique
tambien sobre los peajes cuando apply_iva=True.

### PRIORIDAD 3 - Boton sync calendarios en BaseGlobalView

En base_global.html, anadir boton en la cabecera de la tabla:

<form method="post" action="{% url 'budgets:sync_calendars' %}" class="d-inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-outline-secondary btn-sm">
    <i class="bi bi-arrow-clockwise me-1"></i>Sincronizar calendarios
  </button>
</form>

Nueva vista BaseSyncCalendarsView en budgets/views.py:
- Llama al comando de gestion sync_base_calendars via call_command.
- Redirige a base_global con mensaje de exito.

Nueva ruta: path('bases/sync-calendars/', views.BaseSyncCalendarsView.as_view(),
                  name='sync_calendars')

### PRIORIDAD 4 - Restricciones pendientes en GCP Console

- Restriccion por IP en la API key.
- Limite diario Routes API: 50 peticiones/dia.
