//
// Budget wizard — minimal client-side logic.
// Step sequencing is handled entirely by chained HTMX attributes in the templates.
// This file only handles what HTMX cannot: inline toggle behaviors and the
// route calculation POST (Modo B).
//
// Logica client-side minima del wizard de presupuestos.
// La secuencia de pasos la gestionan completamente los atributos HTMX encadenados
// en los templates. Este archivo solo gestiona lo que HTMX no puede: toggles
// inline y el POST de calculo de ruta (Modo B).

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Overnight fields toggle — show/hide km phase-2 input
  // Toggle de campos de pernocta — mostrar/ocultar input de km fase 2
  // ---------------------------------------------------------------------------

  function toggleOvernightFields(isOvernight) {
    var phase2   = document.getElementById('km-phase2-wrapper');
    var km2Input = document.getElementById('id_km_phase2');
    if (!phase2) return;
    if (isOvernight) {
      phase2.classList.remove('d-none');
      if (km2Input) km2Input.required = true;
    } else {
      phase2.classList.add('d-none');
      if (km2Input) { km2Input.required = false; km2Input.value = ''; }
    }
  }
  window.toggleOvernightFields = toggleOvernightFields;

  // ---------------------------------------------------------------------------
  // Modo B — route calculation fields toggle
  // Modo B — toggle de campos de calculo de ruta
  // ---------------------------------------------------------------------------

  function toggleRouteCalc(active) {
    var fields = document.getElementById('route-calc-fields');
    if (!fields) return;
    fields.classList.toggle('d-none', !active);
    if (!active) {
      // Clear route result and reset all route-related hidden inputs.
      // Limpiar el resultado de ruta y resetear los inputs ocultos de ruta.
      var resultSection = document.getElementById('route-result-section');
      if (resultSection) resultSection.innerHTML = '';
      ['id_route_calculation_mode', 'id_route_distance_km',
       'id_route_toll_cost', 'id_road_name', 'id_pk_km', 'id_dest_location',
       'id_km_phase1',
      ].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.value = id === 'id_route_calculation_mode' ? 'MANUAL' : '';
      });
    }
  }
  window.toggleRouteCalc = toggleRouteCalc;

  // ---------------------------------------------------------------------------
  // Modo B — dual route calculation GET (route-dual/ endpoint)
  // Modo B — calculo de ruta dual GET (endpoint route-dual/)
  //
  // Calls BudgetRouteDualView via HTMX GET and injects the dual fragment into
  // #route-result-section. The fragment renders a Leaflet map with two
  // polylines (with tolls / without tolls) for visual reference only.
  // Budget inputs (km_phase1, route_distance_km) are always set from the
  // primary route (with tolls) — radio buttons only control map highlight.
  //
  // Llama a BudgetRouteDualView via HTMX GET e inyecta el fragmento dual en
  // #route-result-section. El fragmento muestra un mapa Leaflet con dos
  // polylines (con peajes / sin peajes) solo para referencia visual.
  // Los inputs del presupuesto (km_phase1, route_distance_km) se fijan siempre
  // con la ruta primaria (con peajes) — los radio buttons solo controlan el
  // resaltado del mapa.
  // ---------------------------------------------------------------------------

  function calcularRuta() {
    var form         = document.getElementById('budget-form');
    var baseIdInput  = document.querySelector('[name=base_id]');
    var roadName     = document.getElementById('id_road_name_calc').value.trim();
    var destLocation = (
      document.getElementById('id_dest_location_calc') || { value: '' }
    ).value.trim();
    var pkKm        = document.getElementById('id_pk_km_calc').value.trim();
    var serviceDate = (document.getElementById('id_service_date') || {}).value || '';
    var serviceTime = (document.getElementById('id_service_time') || {}).value || '';

    if (!roadName || !pkKm) {
      alert('Rellena carretera y punto kil\u00f3metrico.');
      return;
    }
    if (!serviceDate || !serviceTime) {
      alert(
        'Introduce la fecha y hora del servicio en el paso 2b ' +
        'antes de calcular la ruta.'
      );
      return;
    }

    // Sync hidden POST inputs from the visible calc fields before the request.
    // Sincronizar los inputs ocultos POST desde los campos visibles de calculo.
    var hiddenRoad = document.getElementById('id_road_name');
    var hiddenPk   = document.getElementById('id_pk_km');
    var hiddenDest = document.getElementById('id_dest_location');
    if (hiddenRoad) hiddenRoad.value = roadName;
    if (hiddenPk)   hiddenPk.value   = pkKm;
    if (hiddenDest) hiddenDest.value = destLocation;

    var baseId  = baseIdInput ? baseIdInput.value : '';
    var urlBase = form.dataset.urlRouteDual;
    var params  = [
      'base_id='       + encodeURIComponent(baseId),
      'road_name='     + encodeURIComponent(roadName),
      'dest_location=' + encodeURIComponent(destLocation),
      'pk_km='         + encodeURIComponent(pkKm),
      'service_date='  + encodeURIComponent(serviceDate),
      'service_time='  + encodeURIComponent(serviceTime),
    ].join('&');

    htmx.ajax('GET', urlBase + '?' + params, {
      target: '#route-result-section',
      swap:   'innerHTML',
    });
  }
  window.calcularRuta = calcularRuta;

  // ---------------------------------------------------------------------------
  // Page init — trigger insurer change if browser restores a pre-selected value
  // Inicio de pagina — disparar change de aseguradora si el navegador restaura valor
  // ---------------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', function () {
    var insurerSelect = document.getElementById('id_insurer');
    if (insurerSelect && insurerSelect.value) {
      var baseSel  = document.getElementById('base-selector-section');
      var vtSel    = document.getElementById('vehicle-type-section');
      var stepsSel = document.getElementById('wizard-steps-section');
      if (baseSel)  baseSel.innerHTML  = '';
      if (vtSel)    vtSel.innerHTML    = '';
      if (stepsSel) stepsSel.innerHTML = '';
      insurerSelect.dispatchEvent(new Event('change'));
    }
  });

  // ---------------------------------------------------------------------------
  // HTMX afterSwap — reset downstream when base or vehicle type changes
  // HTMX afterSwap — resetear downstream al cambiar base o tipo de vehiculo
  // ---------------------------------------------------------------------------

  document.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'base-selector-section') {
      var vtSel    = document.getElementById('vehicle-type-section');
      var stepsSel = document.getElementById('wizard-steps-section');
      if (vtSel)    vtSel.innerHTML    = '';
      if (stepsSel) stepsSel.innerHTML = '';
    }
    if (evt.detail.target.id === 'vehicle-type-section') {
      var stepsSel = document.getElementById('wizard-steps-section');
      if (stepsSel) stepsSel.innerHTML = '';
    }
  });

  // ---------------------------------------------------------------------------
  // Always-apply-IVA enforcement
  // Bloqueo de IVA obligatorio
  // ---------------------------------------------------------------------------

  (function () {
    var form          = document.getElementById('budget-form');
    var insurerSelect = document.getElementById('id_insurer');
    if (!form || !insurerSelect) return;

    var alwaysIvaMap = {};
    try {
      alwaysIvaMap = JSON.parse(
        form.dataset.alwaysIvaMap
          ? form.dataset.alwaysIvaMap.replace(/&quot;/g, '"') : '{}'
      );
    } catch (e) {
      alwaysIvaMap = {};
    }

    function updateIvaState() {
      var ivaCheckbox = document.getElementById('id_apply_iva');
      var ivaHint     = document.getElementById('iva-hint');
      var ivaRequired = document.getElementById('iva-required-hint');
      if (!ivaCheckbox) return;
      var pk       = insurerSelect.value;
      var required = pk && alwaysIvaMap[pk] === true;
      if (required) {
        ivaCheckbox.checked  = true;
        ivaCheckbox.disabled = true;
        if (ivaHint)     ivaHint.classList.add('d-none');
        if (ivaRequired) ivaRequired.classList.remove('d-none');
      } else {
        ivaCheckbox.disabled = false;
        if (ivaHint)     ivaHint.classList.remove('d-none');
        if (ivaRequired) ivaRequired.classList.add('d-none');
      }
    }

    insurerSelect.addEventListener('change', updateIvaState);

    document.addEventListener('htmx:afterSwap', function (evt) {
      if (evt.detail.target.id === 'wizard-steps-section') {
        updateIvaState();
      }
    });
  })();

})();
