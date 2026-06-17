// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/wizard_map.js
/**
 * Route planner modal logic (Google Maps JS API, Modo B).
 * APIs used (all current, June 2026):
 *   - Maps JS API: Map, Polyline (geometry.encoding for polyline decode)
 *   - Marker: AdvancedMarkerElement + PinElement (glyphText, marker.append(pin))
 *   - Places: Autocomplete legacy (input existente con estilos propios)
 *   - Geocoding: Geocoder (Promise-based)
 *   - Routes REST API v2: computeRoutes (fetch, for live display polyline)
 *   - Routes API v2 server-side: via BudgetWaypointView (confirmRoute)
 * ---
 * Contrato con wizard.html (PASO 3):
 *   window.ROUTE_PLANNER_CONFIG = {
 *     base: { lat, lng, name, id },
 *     mapId,           // GOOGLE_MAPS_MAP_ID (Raster)
 *     confirmUrl,      // {% url 'budgets:waypoints' %}
 *     serviceDateFieldId,
 *     serviceTimeFieldId,
 *   }
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Estado del módulo
  // ------------------------------------------------------------------
  let map           = null;
  let routePolyline = null;
  let geocoder      = null;
  let baseMarker    = null;
  let mapInitialized = false;
  let dragSourceIndex = null;

  let MarkerLib = null;   // cargado en initMap, reutilizado en addWaypoint

  /** Resultado de calculateRoute() — se vuelca en confirmRoute() */
  let _calculatedRouteData = null;

  /** waypoints[i] = { lat, lng, label, isBaseReturn, marker } */
  const waypoints = [];

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function getConfig() {
    const cfg = window.ROUTE_PLANNER_CONFIG;
    if (!cfg || !cfg.base) {
      throw new Error("ROUTE_PLANNER_CONFIG no está definido.");
    }
    return cfg;
  }

  function getCsrfToken() {
    const el = document.querySelector("input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function _getApiKey() {
    for (const s of document.querySelectorAll(
      'script[src*="maps.googleapis.com/maps/api/js"]'
    )) {
      const m = s.src.match(/[?&]key=([^&]+)/);
      if (m) return m[1];
    }
    return "";
  }

  // ── Spinner del mapa (durante recalculateRoute) ──────────────────
  function showMapSpinner() {
    const el = document.getElementById("route-map-spinner");
    if (el) el.classList.add("active");
  }
  function hideMapSpinner() {
    const el = document.getElementById("route-map-spinner");
    if (el) el.classList.remove("active");
  }

  // ── Spinner del botón Confirmar ──────────────────────────────────
  function showConfirmSpinner() {
    const sp = document.getElementById("route-btn-confirm-spinner");
    if (sp) sp.classList.remove("d-none");
  }
  function hideConfirmSpinner() {
    const sp = document.getElementById("route-btn-confirm-spinner");
    if (sp) sp.classList.add("d-none");
  }

  // ── Spinner del botón Calcular ───────────────────────────────────
  function showCalculateSpinner() {
    const sp = document.getElementById("route-btn-calculate-spinner");
    if (sp) sp.classList.remove("d-none");
  }
  function hideCalculateSpinner() {
    const sp = document.getElementById("route-btn-calculate-spinner");
    if (sp) sp.classList.add("d-none");
  }

  // ------------------------------------------------------------------
  // Inicialización
  // ------------------------------------------------------------------

  async function initMap() {
    if (mapInitialized) return;
    const config = getConfig();

    const [MapsLib, _MarkerLib, GeometryLib, GeocodingLib, PlacesLib] =
      await Promise.all([
        google.maps.importLibrary("maps"),
        google.maps.importLibrary("marker"),
        google.maps.importLibrary("geometry"),
        google.maps.importLibrary("geocoding"),
        google.maps.importLibrary("places"),
      ]);

    MarkerLib = _MarkerLib;
    const { Map, Polyline } = MapsLib;
    const { AdvancedMarkerElement, PinElement } = MarkerLib;
    const { Geocoder } = GeocodingLib;

    // Nombre de la base
    const baseNameEl = document.getElementById("route-base-name");
    if (baseNameEl) baseNameEl.textContent = config.base.name;

    // Mapa
    map = new Map(document.getElementById("route-planner-map"), {
      center: { lat: config.base.lat, lng: config.base.lng },
      zoom: 12,
      mapId: config.mapId,
    });

    // Marker base — patrón moderno: marker.append(pin) + map.append/marker.map
    const basePin = new PinElement({
      background:  "#212529",
      borderColor: "#212529",
      glyphColor:  "#fff",
    });
    baseMarker = new AdvancedMarkerElement({
      map,
      position: { lat: config.base.lat, lng: config.base.lng },
      title:    config.base.name,
    });
    baseMarker.content = basePin;

    // Polyline reutilizable
    routePolyline = new Polyline({
      map,
      strokeColor:   "#0d6efd",
      strokeOpacity: 0.85,
      strokeWeight:  4,
    });

    // Geocoder para clic en mapa
    geocoder = new Geocoder();
    map.addListener("click", async (event) => {
      let label = "Punto manual";
      try {
        const { results } = await geocoder.geocode({ location: event.latLng });
        if (results && results[0]) label = results[0].formatted_address;
      } catch (_) {}
      addWaypoint(event.latLng.lat(), event.latLng.lng(), label, false);
    });

    // Autocomplete legacy — acepta nuestro input existente con nuestros estilos.
    // PlaceAutocompleteElement no permite vincular un input propio (Shadow DOM).
    // Legacy Autocomplete — accepts existing input with our own styles.
    const searchInput = document.getElementById("route-place-search");
    if (searchInput) {
      const { Autocomplete } = PlacesLib;
      const autocomplete = new Autocomplete(searchInput, {
        fields: ["geometry", "name"],
        locationBias: {
          center: { lat: config.base.lat, lng: config.base.lng },
          radius: 50000,
        },
      });

      // El z-index del pac-container se gestiona via CSS en el fragmento.
      // No se mueve al body — Google pierde la referencia al input si se hace.

      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        if (!place || !place.geometry || !place.geometry.location) return;
        addWaypoint(
          place.geometry.location.lat(),
          place.geometry.location.lng(),
          place.name || "Parada",
          false
        );
        searchInput.value = "";
      });
    }

    bindStaticControls(config);
    mapInitialized = true;
  }

  function bindStaticControls(config) {
    const baseReturnBtn = document.getElementById("route-btn-base-return");
    if (baseReturnBtn) {
      baseReturnBtn.addEventListener("click", () =>
        addWaypoint(config.base.lat, config.base.lng,
          `${config.base.name} (vuelta a base)`, true)
      );
    }

    const calculateBtn = document.getElementById("route-btn-calculate");
    if (calculateBtn) {
      calculateBtn.addEventListener("click", () => calculateRoute(config));
    }

    const confirmBtn = document.getElementById("route-btn-confirm");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", () => confirmRoute());
    }

    const stopsList = document.getElementById("route-stops-list");
    if (stopsList) {
      stopsList.addEventListener("click",    handleStopsListClick);
      stopsList.addEventListener("dragstart", handleDragStart);
      stopsList.addEventListener("dragover",  handleDragOver);
      stopsList.addEventListener("drop",      handleDrop);
    }
  }

  // ------------------------------------------------------------------
  // Gestión de paradas
  // ------------------------------------------------------------------

  function _invalidateCalculation() {
    _calculatedRouteData = null;
    const confirmBtn = document.getElementById("route-btn-confirm");
    if (confirmBtn) confirmBtn.disabled = true;
    const distanceEl = document.getElementById("route-summary-distance");
    if (distanceEl) distanceEl.classList.remove("calculated");
    const hintEl = document.getElementById("route-summary-hint");
    if (hintEl) hintEl.classList.remove("d-none");
  }

  function addWaypoint(lat, lng, label, isBaseReturn) {
    const { AdvancedMarkerElement, PinElement } = MarkerLib;

    const pin = new PinElement({
      glyphText:   isBaseReturn ? "" : String(waypoints.length + 1),
      background:  isBaseReturn ? "#212529" : "#0d6efd",
      borderColor: isBaseReturn ? "#212529" : "#0d6efd",
      glyphColor:  "#fff",
    });
    const marker = new AdvancedMarkerElement({
      map,
      position: { lat, lng },
      title:    label,
    });
    marker.content = pin;

    waypoints.push({ lat, lng, label, isBaseReturn, marker });
    _invalidateCalculation();
    renderStopsList();
    recalculateRoute();
  }

  function removeWaypointAt(index) {
    const removed = waypoints.splice(index, 1)[0];
    if (removed && removed.marker) removed.marker.map = null;
    _invalidateCalculation();
    renderStopsList();
    recalculateRoute();
  }

  function reorderWaypoints(fromIndex, toIndex) {
    if (
      fromIndex === toIndex ||
      fromIndex < 0 || toIndex < 0 ||
      fromIndex >= waypoints.length || toIndex >= waypoints.length
    ) return;
    const [moved] = waypoints.splice(fromIndex, 1);
    waypoints.splice(toIndex, 0, moved);
    _invalidateCalculation();
    renderStopsList();
    recalculateRoute();
  }

  function renderStopsList() {
    const list       = document.getElementById("route-stops-list");
    const emptyMsg   = document.getElementById("route-stops-empty");
    const template   = document.getElementById("route-stop-item-template");
    const confirmBtn = document.getElementById("route-btn-confirm");
    if (!list || !template) return;

    list.innerHTML = "";
    waypoints.forEach((wp, index) => {
      const frag    = template.content.cloneNode(true);
      const li      = frag.querySelector(".route-planner-stop");
      const numEl   = frag.querySelector(".route-planner-marker-number");
      const labelEl = frag.querySelector(".route-planner-stop-label");

      li.dataset.waypointIndex = String(index);
      li.dataset.isBaseReturn  = wp.isBaseReturn ? "true" : "false";
      labelEl.textContent      = wp.label;

      if (wp.isBaseReturn) {
        numEl.innerHTML =
          '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" ' +
          'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
          'width="10" height="10"><path d="M2 7.5L8 2l6 5.5"/>' +
          '<path d="M3.5 6.5V13a.5.5 0 00.5.5h3v-3.5h2V13.5h3a.5.5 0 00.5-.5V6.5"/></svg>';
      } else {
        numEl.textContent = String(index + 1);
      }
      list.appendChild(frag);
    });

    if (emptyMsg)   emptyMsg.classList.toggle("d-none", waypoints.length > 0);
    // Calcular se habilita cuando hay paradas; Confirmar solo tras calculateRoute().
    const calcBtn = document.getElementById("route-btn-calculate");
    if (calcBtn) calcBtn.disabled = waypoints.length === 0;
    const confirmBtnEl = document.getElementById("route-btn-confirm");
    if (confirmBtnEl) confirmBtnEl.disabled = true;  // se habilita tras calculateRoute
  }

  function handleStopsListClick(event) {
    const btn = event.target.closest(".route-planner-stop-remove");
    if (!btn) return;
    const li    = btn.closest(".route-planner-stop");
    const index = Number(li.dataset.waypointIndex);
    removeWaypointAt(index);
  }

  function handleDragStart(event) {
    const li = event.target.closest(".route-planner-stop");
    if (!li) return;
    dragSourceIndex = Number(li.dataset.waypointIndex);
    event.dataTransfer.effectAllowed = "move";
  }

  function handleDragOver(event) {
    if (dragSourceIndex !== null) event.preventDefault();
  }

  function handleDrop(event) {
    event.preventDefault();
    const targetLi = event.target.closest(".route-planner-stop");
    if (!targetLi || dragSourceIndex === null) return;
    const targetIndex = Number(targetLi.dataset.waypointIndex);
    reorderWaypoints(dragSourceIndex, targetIndex);
    dragSourceIndex = null;
  }

  // ------------------------------------------------------------------
  // Cálculo de ruta en vivo (Routes API v2 REST, solo visualización)
  // ------------------------------------------------------------------

  async function recalculateRoute() {
    const config     = getConfig();
    const distanceEl = document.getElementById("route-summary-distance");
    const overnightEl = document.getElementById("route-summary-overnight");

    if (waypoints.length === 0) {
      if (distanceEl)  distanceEl.textContent = "—";
      if (overnightEl) { overnightEl.textContent = "No"; overnightEl.classList.remove("is-overnight"); }
      togglePhaseFields(false);
      if (routePolyline) routePolyline.setPath([]);
      return;
    }

    showMapSpinner();

    const intermediates = waypoints.map((s) => ({
      location: { latLng: { latitude: s.lat, longitude: s.lng } },
    }));

    const body = {
      origin:      { location: { latLng: { latitude: config.base.lat, longitude: config.base.lng } } },
      destination: { location: { latLng: { latitude: config.base.lat, longitude: config.base.lng } } },
      intermediates,
      travelMode:        "DRIVE",
      routingPreference: "TRAFFIC_UNAWARE",
      polylineQuality:   "OVERVIEW",
    };

    try {
      const resp = await fetch(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        {
          method: "POST",
          headers: {
            "Content-Type":    "application/json",
            "X-Goog-Api-Key":  _getApiKey(),
            "X-Goog-FieldMask":
              "routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs.distanceMeters",
          },
          body: JSON.stringify(body),
        }
      );
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.routes || !data.routes[0]) return;

      const route = data.routes[0];
      if (route.polyline && route.polyline.encodedPolyline) {
        const path = google.maps.geometry.encoding.decodePath(
          route.polyline.encodedPolyline
        );
        routePolyline.setPath(path);
      }
      applyRouteSummary(route);
    } catch (_) {
      // Fallo silencioso en visualización
    } finally {
      hideMapSpinner();
    }
  }

  function applyRouteSummary(route) {
    const distanceEl  = document.getElementById("route-summary-distance");
    const overnightEl = document.getElementById("route-summary-overnight");
    const totalMeters = route.distanceMeters || 0;

    if (distanceEl) distanceEl.textContent = formatKm(totalMeters);

    const baseReturnIndex = waypoints.findIndex((w) => w.isBaseReturn);
    const isOvernight     = baseReturnIndex !== -1;

    if (overnightEl) {
      overnightEl.textContent = isOvernight ? "Sí" : "No";
      overnightEl.classList.toggle("is-overnight", isOvernight);
    }
    togglePhaseFields(isOvernight);

    if (isOvernight && route.legs) {
      const phase1Meters = route.legs
        .slice(0, baseReturnIndex + 1)
        .reduce((s, l) => s + (l.distanceMeters || 0), 0);
      const phase2Meters = totalMeters - phase1Meters;
      const p1 = document.getElementById("route-summary-phase1");
      const p2 = document.getElementById("route-summary-phase2");
      if (p1) p1.textContent = formatKm(phase1Meters);
      if (p2) p2.textContent = formatKm(phase2Meters);
    }
  }

  function togglePhaseFields(show) {
    ["route-summary-phase1-label","route-summary-phase1",
     "route-summary-phase2-label","route-summary-phase2"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("d-none", !show);
    });
  }

  function formatKm(meters) {
    return `${(meters / 1000).toFixed(1)} km`;
  }

  // ------------------------------------------------------------------
  // FASE 1 — Calcular ruta server-side (Routes API v2)
  // Muestra km reales + peajes en el modal antes de confirmar.
  // ------------------------------------------------------------------

  async function calculateRoute(config) {
    const calculateBtn = document.getElementById("route-btn-calculate");
    const confirmBtn   = document.getElementById("route-btn-confirm");
    const tollsEl      = document.getElementById("route-summary-tolls");
    const hintEl       = document.getElementById("route-summary-hint");
    const dateField    = config.serviceDateFieldId
      ? document.getElementById(config.serviceDateFieldId) : null;
    const timeField    = config.serviceTimeFieldId
      ? document.getElementById(config.serviceTimeFieldId) : null;

    const payload = {
      base_id: config.base.id,
      waypoints_json: JSON.stringify(
        waypoints.map((s) => ({
          lat: s.lat, lng: s.lng,
          label: s.label, is_base_return: s.isBaseReturn,
        }))
      ),
      service_date: dateField ? dateField.value : "",
      service_time: timeField ? timeField.value : "",
    };

    if (calculateBtn) calculateBtn.disabled = true;
    showCalculateSpinner();
    clearRoutePlannerError();
    _calculatedRouteData = null;

    try {
      const resp = await fetch(config.confirmUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken":  getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `HTTP ${resp.status}`);
      }
      const data = await resp.json();

      // Guardar datos para confirmRoute()
      _calculatedRouteData = { payload, data };

      // Actualizar resumen con datos reales del servidor
      const distanceEl  = document.getElementById("route-summary-distance");
      const overnightEl = document.getElementById("route-summary-overnight");
      const phase1El    = document.getElementById("route-summary-phase1");
      const phase2El    = document.getElementById("route-summary-phase2");

      // Distancia total = phase1 + phase2 (si hay pernocta), o route_distance_km.
      // Total distance = phase1 + phase2 (if overnight), or route_distance_km.
      const km1 = parseFloat(data.km_phase1 || 0);
      const km2 = parseFloat(data.km_phase2 || 0);
      const totalKm = data.is_overnight
        ? (km1 + km2).toFixed(1)
        : parseFloat(data.route_distance_km || km1).toFixed(1);

      if (distanceEl) {
        distanceEl.textContent = `${totalKm} km`;
        distanceEl.classList.add("calculated");
      }
      if (overnightEl) {
        overnightEl.textContent = data.is_overnight ? "Sí" : "No";
        overnightEl.classList.toggle("is-overnight", Boolean(data.is_overnight));
      }
      togglePhaseFields(Boolean(data.is_overnight));
      if (data.is_overnight) {
        if (phase1El && data.km_phase1)
          phase1El.textContent = `${km1.toFixed(1)} km`;
        if (phase2El && data.km_phase2)
          phase2El.textContent = `${km2.toFixed(1)} km`;
      }
      if (tollsEl) {
        tollsEl.textContent = data.has_tolls ? "Sí" : "No";
        tollsEl.classList.toggle("has-tolls", Boolean(data.has_tolls));
      }

      // Ocultar hint y habilitar Confirmar
      if (hintEl) hintEl.classList.add("d-none");
      if (confirmBtn) confirmBtn.disabled = false;

    } catch (err) {
      showRoutePlannerError(
        err.message || "No se ha podido calcular la ruta. Inténtalo de nuevo."
      );
      if (calculateBtn) calculateBtn.disabled = false;
    } finally {
      hideCalculateSpinner();
    }
  }

  // ------------------------------------------------------------------
  // FASE 2 — Confirmar ruta (vuelca datos calculados en hidden inputs)
  // ------------------------------------------------------------------

  async function confirmRoute() {
    if (!_calculatedRouteData) return;
    const { payload, data } = _calculatedRouteData;

    setHiddenValue("id_waypoints_json",         payload.waypoints_json);
    setHiddenValue("id_route_distance_km",       data.route_distance_km);
    setHiddenValue("id_km_phase1_route",         data.km_phase1);
    setHiddenValue("id_km_phase2_route",         data.km_phase2);
    setHiddenValue("id_is_overnight_route",      data.is_overnight);
    setHiddenValue("id_route_toll_budget_cost",  data.route_toll_budget_cost);
    setHiddenValue("id_route_calculation_mode",  "API");

    // Resumen en el wizard — mostrar total real (phase1+phase2 si pernocta).
    // Wizard summary — show real total (phase1+phase2 if overnight).
    const summaryEl   = document.getElementById("route-confirmed-summary");
    const summaryText = document.getElementById("route-confirmed-text");
    if (summaryEl && summaryText) {
      const km1 = parseFloat(data.km_phase1 || 0);
      const km2 = parseFloat(data.km_phase2 || 0);
      const totalKm = data.is_overnight
        ? (km1 + km2).toFixed(1)
        : parseFloat(data.route_distance_km || km1).toFixed(1);
      const tolls    = data.has_tolls ? " · Con peajes" : "";
      const overnight = data.is_overnight ? " · Pernocta" : "";
      summaryText.textContent = `Ruta confirmada — ${totalKm} km${overnight}${tolls}`;
      summaryEl.classList.remove("d-none");
    }

    const modalEl = document.getElementById("routePlannerModal");
    if (modalEl && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
    }
  }

  function setHiddenValue(id, value) {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null) el.value = value;
  }

  function showRoutePlannerError(message) {
    const panel = document.querySelector(".route-planner-panel-inner");
    if (!panel) return;
    let alertEl = document.getElementById("route-planner-error");
    if (!alertEl) {
      alertEl = document.createElement("div");
      alertEl.id        = "route-planner-error";
      alertEl.className = "alert alert-danger alert-sm mt-2";
      alertEl.setAttribute("role", "alert");
      panel.appendChild(alertEl);
    }
    alertEl.textContent = message;
  }

  function clearRoutePlannerError() {
    const el = document.getElementById("route-planner-error");
    if (el) el.remove();
  }

  // ------------------------------------------------------------------
  // Arranque
  // ------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    const modalEl = document.getElementById("routePlannerModal");
    if (modalEl) {
      modalEl.addEventListener("shown.bs.modal", () => {
        initMap().catch(() =>
          showRoutePlannerError("No se ha podido cargar el mapa. Recarga la página.")
        );
      });
    }
  });
})();
