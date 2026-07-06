// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/wizard.js
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
      if (km2Input) {
        km2Input.required = true;
        km2Input.disabled = false;
      }
    } else {
      phase2.classList.add('d-none');
      if (km2Input) {
        km2Input.required = false;
        km2Input.disabled = true;
        km2Input.value = '';
      }
    }
  }
  window.toggleOvernightFields = toggleOvernightFields;

  // ---------------------------------------------------------------------------
  // Modo B — route calculation fields toggle
  // Modo B — toggle de campos de calculo de ruta
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Paso 4 — Modo de cálculo: Manual vs Planificación de ruta.
  // Cada modo anula al otro por completo: al cambiar, se oculta la tarjeta
  // del modo contrario, se fija route_calculation_mode directamente (fuente
  // única de verdad leída por la vista), y en modo Manual se limpian los
  // campos de ruta para que nunca viajen datos de un modo abandonado.
  // ---------------------------------------------------------------------------
  //
  // Paso 4 — Calculation mode: Manual vs Route planning.
  // Each mode fully overrides the other: on change, the opposite card is
  // hidden, route_calculation_mode is set directly (single source of truth
  // read by the view), and in Manual mode the route fields are cleared so
  // no data from an abandoned mode is ever submitted.

  function toggleCalcMode(mode) {
    var manualCard = document.getElementById('step-km-manual');
    var routeCard  = document.getElementById('step-route');
    var hiddenMode = document.getElementById('id_route_calculation_mode');

    if (mode === 'MANUAL') {
      if (manualCard) manualCard.classList.remove('d-none');
      if (routeCard)  routeCard.classList.add('d-none');
      if (hiddenMode) hiddenMode.value = 'MANUAL';

      // Clear route-side data so an abandoned route selection never
      // gets submitted alongside manual values.
      // Limpiar datos de ruta para que una selección de ruta abandonada
      // nunca se envíe junto a los valores manuales.
      var resultSection = document.getElementById('route-result-section');
      if (resultSection) resultSection.innerHTML = '';
      var confirmedSummary = document.getElementById('route-confirmed-summary');
      if (confirmedSummary) confirmedSummary.classList.add('d-none');
      [
        'id_route_distance_km', 'id_route_toll_cost', 'id_road_name',
        'id_pk_km', 'id_dest_location', 'id_waypoints_json',
        'id_km_phase1_route', 'id_km_phase2_route',
        'id_is_overnight_route', 'id_route_toll_budget_cost',
        'id_encoded_polyline',
      ].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.value = '';
      });
    } else {
      if (manualCard) manualCard.classList.add('d-none');
      if (routeCard)  routeCard.classList.remove('d-none');
      if (hiddenMode) hiddenMode.value = 'API';

      // Clear manual-side data so it never gets submitted alongside a
      // confirmed route. Overnight is reset too — in Route mode it is
      // detected automatically from the waypoints (base-return stop),
      // not from this radio.
      // Limpiar datos manuales para que nunca se envíen junto a una
      // ruta confirmada. La pernocta también se resetea — en modo Ruta
      // se detecta automáticamente desde las paradas (retorno a base),
      // no desde este radio.
      var km1 = document.getElementById('id_km_phase1');
      var km2 = document.getElementById('id_km_phase2');
      var nyf = document.getElementById('id_manual_is_night_holiday');
      var toll = document.getElementById('id_manual_toll_total');
      var overnightNo = document.getElementById('overnight-no');
      if (km1) km1.value = '';
      if (km2) km2.value = '';
      if (nyf) nyf.checked = false;
      if (toll) toll.value = '';
      // Limpiar la tabla itemizada de peajes por tramo (nº de pases),
      // generada dinámicamente por tramo — no tiene un id fijo único.
      document.querySelectorAll('input[id^="id_toll_pases_"]').forEach(
        function (el) { el.value = ''; }
      );
      if (overnightNo) {
        overnightNo.checked = true;
        toggleOvernightFields(false);
      }
    }
  }
  window.toggleCalcMode = toggleCalcMode;

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


