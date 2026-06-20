// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/wizard_map.js
/**
 * Route planner modal logic (Google Maps JS API, Modo B).
 *
 * Standard pattern (June 2026):
 *   - DirectionsService with provideRouteAlternatives:true → result.routes[]
 *   - One DirectionsRenderer per route, each with its own routeIndex + color
 *   - Click on a route polyline to select it (highlight/dim)
 *   - Desktop: DirectionsRenderer draggable:true on selected renderer
 *   - Mobile:  tap map → bottom sheet (Add stop / Pass through via:true)
 *   - Server-side calculation via BudgetWaypointView (Routes API v2)
 *
 * Contrato con wizard.html:
 *   window.ROUTE_PLANNER_CONFIG = {
 *     base: { lat, lng, name, id },
 *     mapId,
 *     confirmUrl,
 *     serviceDateFieldId,
 *     serviceTimeFieldId,
 *   }
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Colores de ruta
  // Route colors
  // ------------------------------------------------------------------
  const COLOR_PRIMARY = "#1565C0";   // Azul oscuro — ruta principal / Dark blue — primary
  const COLOR_ALT     = "#90CAF9";   // Azul claro  — ruta alternativa / Light blue — alternative
  const WEIGHT_ACTIVE = 6;
  const WEIGHT_DIM    = 4;
  const OPACITY_ACTIVE = 0.95;
  const OPACITY_DIM    = 0.45;

  // ------------------------------------------------------------------
  // Estado del módulo
  // ------------------------------------------------------------------
  let map               = null;
  let directionsService = null;
  let geocoder          = null;
  let baseMarker        = null;
  let mapInitialized    = false;
  let dragSourceIndex   = null;
  let MarkerLib         = null;

  /**
   * Renderers activos — uno por ruta alternativa devuelta.
   * renderers[0] = ruta principal, renderers[1] = alternativa, ...
   */
  let renderers      = [];
  let selectedRouteIndex = 0;

  /** Waypoints del usuario: { lat, lng, label, isBaseReturn, isVia, marker } */
  const waypoints = [];

  /** Via-waypoints añadidos por drag (desktop) */
  let _dragWaypoints = [];

  /** Resultado de calculateRoute() — volcado en confirmRoute() */
  let _calculatedRouteData = null;

  // ------------------------------------------------------------------
  // Detección de entorno
  // ------------------------------------------------------------------
  function isMobileDevice() {
    return (
      window.matchMedia("(pointer: coarse)").matches &&
      navigator.maxTouchPoints > 0
    );
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function getConfig() {
    const cfg = window.ROUTE_PLANNER_CONFIG;
    if (!cfg || !cfg.base) throw new Error("ROUTE_PLANNER_CONFIG no definido.");
    return cfg;
  }

  function getCsrfToken() {
    const el = document.querySelector("input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function showMapSpinner()      { _toggleId("route-map-spinner",           true,  "active"); }
  function hideMapSpinner()      { _toggleId("route-map-spinner",           false, "active"); }
  function showCalculateSpinner(){ _toggleId("route-btn-calculate-spinner", false, "d-none"); }
  function hideCalculateSpinner(){ _toggleId("route-btn-calculate-spinner", true,  "d-none"); }

  function _toggleId(id, add, cls) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle(cls, add);
  }

  // ------------------------------------------------------------------
  // Gestión de renderers
  // ------------------------------------------------------------------

  /** Elimina todos los renderers/polylines del mapa y limpia el array */
  function _clearRenderers() {
    renderers.forEach((r) => {
      if (r.renderer) r.renderer.setMap(null);
      if (r.polyline) r.polyline.setMap(null);
    });
    renderers = [];
    selectedRouteIndex = 0;
    _dragWaypoints = [];
  }

  /**
   * Construye los renderers a partir del resultado de DirectionsService.
   * Uno por ruta: el primero en azul oscuro, el resto en azul claro.
   * Sets up one DirectionsRenderer per route from DirectionsService result.
   * First route: dark blue. Rest: light blue. Click to select.
   */
  /**
   * Pinta las rutas directamente con Polyline (no DirectionsRenderer).
   * Evita interferencias con mapId/vector rendering.
   * Para desktop, el renderer draggable se aplica solo a la ruta seleccionada.
   *
   * Draws routes directly with Polyline (not DirectionsRenderer).
   * Avoids interference with mapId/vector rendering.
   */
  function _buildRenderersFromResults(resultNormal, resultAlt) {
    _clearRenderers();
    const { DirectionsRenderer } = window._mapsRoutesLib;
    const { Polyline } = window._mapsLib;

    // Ruta alternativa (azul claro) — se pinta PRIMERO para quedar debajo
    // Alternative route (light blue) — drawn FIRST to appear below
    if (resultAlt) {
      const pathAlt = resultAlt.routes[0].overview_path;
      const polyAlt = new Polyline({
        map,
        path:          pathAlt,
        strokeColor:   COLOR_ALT,
        strokeOpacity: OPACITY_DIM,
        strokeWeight:  WEIGHT_DIM,
        zIndex:        1,
        clickable:     true,
      });
      polyAlt.addListener("click", () => _selectRoute(1));
      renderers.push({ polyline: polyAlt, result: resultAlt, isPrimary: false });
    }

    // Ruta principal (azul oscuro) con DirectionsRenderer draggable en desktop
    // Primary route (dark blue) with draggable DirectionsRenderer on desktop
    const rendererPrimary = new DirectionsRenderer({
      map,
      directions:      resultNormal,
      routeIndex:      0,
      draggable:       !isMobileDevice(),
      suppressMarkers: true,
      polylineOptions: {
        strokeColor:   COLOR_PRIMARY,
        strokeOpacity: OPACITY_ACTIVE,
        strokeWeight:  WEIGHT_ACTIVE,
        zIndex:        2,
        clickable:     true,
      },
    });
    rendererPrimary.addListener("directions_changed", () => {
      const res = rendererPrimary.getDirections();
      if (!res) return;
      _dragWaypoints = [];
      const route = res.routes[0];
      if (route) {
        route.legs.forEach((leg) => {
          (leg.via_waypoints || []).forEach((pt) => {
            _dragWaypoints.push({ lat: pt.lat(), lng: pt.lng() });
          });
        });
      }
      _invalidateCalculation(true);
    });
    rendererPrimary.addListener("click", () => _selectRoute(0));
    renderers.push({ renderer: rendererPrimary, result: resultNormal, isPrimary: true });

    if (resultAlt) {
      _buildRouteSelectorCardsFromResults(resultNormal, resultAlt);
    }

    _selectRoute(0);
  }

  /**
   * Selecciona la ruta con índice idx:
   * resalta su polyline, atenúa las demás.
   */
  function _selectRoute(idx) {
    selectedRouteIndex = idx;
    renderers.forEach((r, i) => {
      const active = i === idx;
      if (r.renderer) {
        r.renderer.setOptions({
          polylineOptions: {
            strokeColor:   active ? COLOR_PRIMARY : COLOR_ALT,
            strokeOpacity: active ? OPACITY_ACTIVE : OPACITY_DIM,
            strokeWeight:  active ? WEIGHT_ACTIVE  : WEIGHT_DIM,
            zIndex:        active ? 2 : 1,
          },
          draggable: active && !isMobileDevice(),
        });
      }
      if (r.polyline) {
        r.polyline.setOptions({
          strokeColor:   active ? COLOR_PRIMARY : COLOR_ALT,
          strokeOpacity: active ? OPACITY_ACTIVE : OPACITY_DIM,
          strokeWeight:  active ? WEIGHT_ACTIVE  : WEIGHT_DIM,
          zIndex:        active ? 2 : 1,
        });
      }
    });
    // Actualizar estado visual de las cards
    document.querySelectorAll(".rp-route-card").forEach((card, i) => {
      card.classList.toggle("rp-route-card--active", i === idx);
    });
    _invalidateCalculation(true);
  }

  // ------------------------------------------------------------------
  // Cards de selección de ruta en el panel lateral
  // Route selector cards in the side panel
  // ------------------------------------------------------------------

  function _buildRouteSelectorCardsFromResults(resultNormal, resultAlt) {
    document.querySelectorAll(".rp-route-cards-wrapper").forEach((el) => el.remove());

    if (!document.getElementById("rp-route-cards-style")) {
      const style = document.createElement("style");
      style.id = "rp-route-cards-style";
      style.textContent = `
        .rp-route-cards-wrapper { display:flex; flex-direction:column; gap:.4rem; margin-top:.75rem; }
        .rp-route-card {
          display:flex; align-items:center; gap:.5rem;
          padding:.5rem .65rem; border:2px solid #dee2e6;
          border-radius:.45rem; cursor:pointer; background:#fff;
          font-size:.82rem; transition:border-color .15s,background .15s;
        }
        .rp-route-card:hover { border-color:#adb5bd; background:#f8f9fa; }
        .rp-route-card--active { border-color:#1565C0 !important; background:#e8f0fe !important; }
        .rp-route-card__dot { width:.85rem; height:.85rem; border-radius:50%; flex-shrink:0; }
        .rp-route-card__label { flex:1; font-weight:600; }
        .rp-route-card__km { color:#495057; }
      `;
      document.head.appendChild(style);
    }

    const hintEl = document.getElementById("route-summary-hint");
    if (!hintEl) return;

    const wrapper = document.createElement("div");
    wrapper.className = "rp-route-cards-wrapper";

    const routeDefs = [
      { result: resultNormal, label: "Con peajes",  color: COLOR_PRIMARY, idx: 0 },
      { result: resultAlt,    label: "Sin peajes",  color: COLOR_ALT,     idx: 1 },
    ];

    routeDefs.forEach(({ result, label, color, idx }) => {
      if (!result) return;
      const meters = result.routes[0].legs.reduce(
        (s, leg) => s + (leg.distance ? leg.distance.value : 0), 0
      );
      const km = (meters / 1000).toFixed(1);

      const card = document.createElement("div");
      card.className = "rp-route-card" + (idx === 0 ? " rp-route-card--active" : "");
      card.innerHTML = `
        <span class="rp-route-card__dot" style="background:${color}"></span>
        <span class="rp-route-card__label">${label}</span>
        <span class="rp-route-card__km">${km} km</span>
      `;
      card.addEventListener("click", () => _selectRoute(idx));
      wrapper.appendChild(card);
    });

    hintEl.after(wrapper);
  }

  // ------------------------------------------------------------------
  // Menú contextual móvil (bottom sheet)
  // ------------------------------------------------------------------

  function _showMobileMapMenu(latLng, label) {
    _closeMobileMapMenu();

    const sheet = document.createElement("div");
    sheet.id = "rp-mobile-menu";
    sheet.innerHTML = `
      <style>
        #rp-mobile-menu {
          position:fixed; bottom:0; left:0; right:0; z-index:9999;
          background:#fff; border-radius:1rem 1rem 0 0;
          box-shadow:0 -4px 24px rgba(0,0,0,.18);
          padding:1rem 1rem 1.5rem;
          animation:rp-slide-up .2s ease;
        }
        @keyframes rp-slide-up {
          from { transform:translateY(100%); } to { transform:translateY(0); }
        }
        #rp-mobile-menu .rp-mm-handle {
          width:2.5rem; height:.3rem; background:#dee2e6;
          border-radius:1rem; margin:0 auto .85rem;
        }
        #rp-mobile-menu .rp-mm-label {
          font-size:.8rem; color:#6c757d; margin-bottom:.65rem;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }
        #rp-mobile-menu .rp-mm-btn {
          display:flex; align-items:center; gap:.6rem;
          width:100%; padding:.75rem .5rem;
          border:0; background:transparent;
          font-size:.95rem; text-align:left;
          border-radius:.4rem; cursor:pointer;
        }
        #rp-mobile-menu .rp-mm-btn:active { background:#f8f9fa; }
        #rp-mobile-menu .rp-mm-icon {
          width:2rem; height:2rem; border-radius:50%;
          display:inline-flex; align-items:center; justify-content:center;
          font-weight:700; color:#fff; flex-shrink:0;
        }
        #rp-mobile-menu hr { border:0; border-top:1px solid #dee2e6; margin:.25rem 0; }
        #rp-mobile-menu .rp-mm-cancel {
          display:block; width:100%; padding:.6rem; border:0;
          background:transparent; color:#dc3545; font-size:.9rem;
          cursor:pointer; margin-top:.25rem; border-radius:.4rem;
        }
        #rp-overlay { position:fixed; inset:0; z-index:9998; background:transparent; }
      </style>
      <div class="rp-mm-handle"></div>
      <div class="rp-mm-label">${label}</div>
      <button class="rp-mm-btn" id="rp-mm-stop">
        <span class="rp-mm-icon" style="background:#0d6efd">●</span>
        <span><strong>Añadir parada</strong><br>
          <small style="color:#6c757d">La grúa se detiene aquí</small></span>
      </button>
      <hr>
      <button class="rp-mm-btn" id="rp-mm-via">
        <span class="rp-mm-icon" style="background:#6c757d">→</span>
        <span><strong>Pasar por aquí</strong><br>
          <small style="color:#6c757d">Fuerza la ruta por este punto</small></span>
      </button>
      <hr>
      <button class="rp-mm-cancel" id="rp-mm-cancel">Cancelar</button>
    `;

    const overlay = document.createElement("div");
    overlay.id = "rp-overlay";
    overlay.addEventListener("click", _closeMobileMapMenu);
    document.body.appendChild(overlay);
    document.body.appendChild(sheet);

    document.getElementById("rp-mm-stop").addEventListener("click", () => {
      _closeMobileMapMenu();
      addWaypoint(latLng.lat(), latLng.lng(), label, false, false);
    });
    document.getElementById("rp-mm-via").addEventListener("click", () => {
      _closeMobileMapMenu();
      addWaypoint(latLng.lat(), latLng.lng(), label, false, true);
    });
    document.getElementById("rp-mm-cancel").addEventListener("click", _closeMobileMapMenu);
  }

  function _closeMobileMapMenu() {
    ["rp-mobile-menu", "rp-overlay"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
  }

  // ------------------------------------------------------------------
  // Inicialización del mapa
  // ------------------------------------------------------------------

  async function initMap() {
    if (mapInitialized) return;
    const config = getConfig();
    const mobile = isMobileDevice();

    const [MapsLib, _MarkerLib, GeocodingLib, PlacesLib, RoutesLib] =
      await Promise.all([
        google.maps.importLibrary("maps"),
        google.maps.importLibrary("marker"),
        google.maps.importLibrary("geocoding"),
        google.maps.importLibrary("places"),
        google.maps.importLibrary("routes"),
      ]);

    MarkerLib = _MarkerLib;
    // Guardamos RoutesLib para usarla en _buildRenderers
    window._mapsRoutesLib = RoutesLib;
    window._mapsLib = MapsLib;

    const { Map }                = MapsLib;
    const { AdvancedMarkerElement, PinElement } = MarkerLib;
    const { Geocoder }           = GeocodingLib;
    const { DirectionsService }  = RoutesLib;

    const baseNameEl = document.getElementById("route-base-name");
    if (baseNameEl) baseNameEl.textContent = config.base.name;

    map = new Map(document.getElementById("route-planner-map"), {
      center: { lat: config.base.lat, lng: config.base.lng },
      zoom: 12,
      mapId: config.mapId,
    });

    const basePin = new PinElement({
      background: "#212529", borderColor: "#212529", glyphColor: "#fff",
    });
    baseMarker = new AdvancedMarkerElement({
      map, position: { lat: config.base.lat, lng: config.base.lng },
      title: config.base.name,
    });
    baseMarker.content = basePin;

    directionsService = new DirectionsService();
    geocoder = new Geocoder();

    map.addListener("click", async (event) => {
      let label = "Punto manual";
      try {
        const { results } = await geocoder.geocode({ location: event.latLng });
        if (results && results[0]) label = results[0].formatted_address;
      } catch (_) {}

      if (mobile) {
        _showMobileMapMenu(event.latLng, label);
      } else {
        addWaypoint(event.latLng.lat(), event.latLng.lng(), label, false, false);
      }
    });

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
      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        if (!place || !place.geometry || !place.geometry.location) return;
        addWaypoint(
          place.geometry.location.lat(),
          place.geometry.location.lng(),
          place.name || "Parada",
          false, false
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
          `${config.base.name} (vuelta a base)`, true, false)
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
  // Invalidar cálculo server-side
  // ------------------------------------------------------------------

  function _invalidateCalculation(keepPolyline = false) {
    _calculatedRouteData = null;

    const confirmBtn = document.getElementById("route-btn-confirm");
    if (confirmBtn) confirmBtn.disabled = true;

    const distanceEl = document.getElementById("route-summary-distance");
    if (distanceEl) distanceEl.classList.remove("calculated");

    const hintEl = document.getElementById("route-summary-hint");
    if (hintEl) hintEl.classList.remove("d-none");

    // Solo deshabilitar "Calcular ruta" si no hay paradas reales,
    // o si se limpia la polyline (cambio de paradas).
    // keepPolyline=true → el usuario arrastró la ruta, el botón debe
    // mantenerse habilitado para que pueda recalcular.
    // Only disable "Calcular ruta" if no real stops, or polyline is cleared.
    // keepPolyline=true → user dragged the route, button stays enabled.
    const calcBtn = document.getElementById("route-btn-calculate");
    const hasStops = waypoints.some((w) => !w.isVia);
    if (calcBtn && !keepPolyline) calcBtn.disabled = !hasStops;

    if (!keepPolyline) {
      _clearRenderers();
      document.querySelectorAll(".rp-route-cards-wrapper").forEach((el) => el.remove());
      _dragWaypoints = [];
    }
  }

  // ------------------------------------------------------------------
  // Gestión de paradas
  // ------------------------------------------------------------------

  function addWaypoint(lat, lng, label, isBaseReturn, isVia) {
    const { AdvancedMarkerElement, PinElement } = MarkerLib;
    const stopCount = waypoints.filter((w) => !w.isVia && !w.isBaseReturn).length;

    let pin;
    if (isVia) {
      pin = new PinElement({
        glyphText: "→", background: "#6c757d",
        borderColor: "#6c757d", glyphColor: "#fff", scale: 0.7,
      });
    } else if (isBaseReturn) {
      pin = new PinElement({
        background: "#212529", borderColor: "#212529", glyphColor: "#fff",
      });
    } else {
      pin = new PinElement({
        glyphText: String(stopCount + 1),
        background: "#0d6efd", borderColor: "#0d6efd", glyphColor: "#fff",
      });
    }

    const marker = new AdvancedMarkerElement({
      map, position: { lat, lng }, title: label,
    });
    marker.content = pin;

    waypoints.push({ lat, lng, label, isBaseReturn, isVia: !!isVia, marker });
    _invalidateCalculation(false);
    renderStopsList();
    recalculateRouteDisplay();
  }

  function removeWaypointAt(index) {
    const removed = waypoints.splice(index, 1)[0];
    if (removed && removed.marker) removed.marker.map = null;
    _invalidateCalculation(false);
    renderStopsList();
    recalculateRouteDisplay();
  }

  function reorderWaypoints(fromIndex, toIndex) {
    if (
      fromIndex === toIndex || fromIndex < 0 || toIndex < 0 ||
      fromIndex >= waypoints.length || toIndex >= waypoints.length
    ) return;
    const [moved] = waypoints.splice(fromIndex, 1);
    waypoints.splice(toIndex, 0, moved);
    _invalidateCalculation(false);
    renderStopsList();
    recalculateRouteDisplay();
  }

  function renderStopsList() {
    const list     = document.getElementById("route-stops-list");
    const emptyMsg = document.getElementById("route-stops-empty");
    const template = document.getElementById("route-stop-item-template");
    if (!list || !template) return;

    list.innerHTML = "";
    let stopNum = 0;
    waypoints.forEach((wp, index) => {
      const frag    = template.content.cloneNode(true);
      const li      = frag.querySelector(".route-planner-stop");
      const numEl   = frag.querySelector(".route-planner-marker-number");
      const labelEl = frag.querySelector(".route-planner-stop-label");

      li.dataset.waypointIndex = String(index);
      li.dataset.isBaseReturn  = wp.isBaseReturn ? "true" : "false";

      if (wp.isVia) {
        labelEl.innerHTML = `<span style="color:#6c757d">${wp.label}</span>
          <span style="font-size:.7rem;background:#e9ecef;color:#6c757d;
            padding:.1rem .35rem;border-radius:.3rem;margin-left:.35rem">vía</span>`;
      } else {
        labelEl.textContent = wp.label;
      }

      if (wp.isBaseReturn) {
        numEl.innerHTML =
          '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" ' +
          'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
          'width="10" height="10"><path d="M2 7.5L8 2l6 5.5"/>' +
          '<path d="M3.5 6.5V13a.5.5 0 00.5.5h3v-3.5h2V13.5h3a.5.5 0 00.5-.5V6.5"/></svg>';
      } else if (wp.isVia) {
        numEl.textContent = "→";
        numEl.style.fontSize = ".7rem";
      } else {
        stopNum++;
        numEl.textContent = String(stopNum);
      }
      list.appendChild(frag);
    });

    if (emptyMsg) emptyMsg.classList.toggle("d-none", waypoints.length > 0);
    const calcBtn = document.getElementById("route-btn-calculate");
    const hasStops = waypoints.some((w) => !w.isVia);
    if (calcBtn) calcBtn.disabled = !hasStops;
  }

  function handleStopsListClick(event) {
    const btn = event.target.closest(".route-planner-stop-remove");
    if (!btn) return;
    const li    = btn.closest(".route-planner-stop");
    removeWaypointAt(Number(li.dataset.waypointIndex));
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
    reorderWaypoints(dragSourceIndex, Number(targetLi.dataset.waypointIndex));
    dragSourceIndex = null;
  }

  // ------------------------------------------------------------------
  // Visualización de ruta en vivo
  // Dos llamadas paralelas a DirectionsService:
  //   1. Ruta normal → azul oscuro (#1565C0)
  //   2. Ruta avoidTolls:true → azul claro (#90CAF9)
  // provideRouteAlternatives con waypoints no devuelve alternativas (limitación
  // documentada de la Directions API). Dos llamadas independientes garantizan
  // siempre dos trazados distintos.
  // ------------------------------------------------------------------

  function recalculateRouteDisplay() {
    const config = getConfig();
    const hasStops = waypoints.some((w) => !w.isVia);

    if (!hasStops) {
      _clearRenderers();
      const distanceEl  = document.getElementById("route-summary-distance");
      const overnightEl = document.getElementById("route-summary-overnight");
      if (distanceEl)  distanceEl.textContent = "—";
      if (overnightEl) { overnightEl.textContent = "No"; overnightEl.classList.remove("is-overnight"); }
      togglePhaseFields(false);
      return;
    }

    showMapSpinner();
    _clearRenderers();

    const origin      = { lat: config.base.lat, lng: config.base.lng };
    const destination = { lat: config.base.lat, lng: config.base.lng };

    const intermediates = waypoints.map((wp) => ({
      location: { lat: wp.lat, lng: wp.lng },
      stopover: !wp.isVia,
    }));

    const baseRequest = {
      origin,
      destination,
      waypoints:  intermediates,
      travelMode: google.maps.TravelMode.DRIVING,
    };

    let resultNormal = null;
    let resultAlt    = null;
    let pending      = 2;

    function onBothDone() {
      hideMapSpinner();
      if (!resultNormal) return;   // La ruta principal es obligatoria
      _buildRenderersFromResults(resultNormal, resultAlt);
      applyRouteSummary(resultNormal, 0);
    }

    // Llamada 1 — ruta normal (con peajes permitidos)
    // Call 1 — normal route (tolls allowed)
    directionsService.route(baseRequest, (result, status) => {
      if (status === "OK") resultNormal = result;
      if (--pending === 0) onBothDone();
    });

    // Llamada 2 — ruta evitando peajes
    // Call 2 — toll-free route
    directionsService.route(
      { ...baseRequest, avoidTolls: true },
      (result, status) => {
        if (status === "OK") resultAlt = result;
        if (--pending === 0) onBothDone();
      }
    );
  }

  function applyRouteSummary(directionsResult, routeIdx) {
    const route       = directionsResult.routes[routeIdx];
    const distanceEl  = document.getElementById("route-summary-distance");
    const overnightEl = document.getElementById("route-summary-overnight");

    const totalMeters = route.legs.reduce(
      (s, leg) => s + (leg.distance ? leg.distance.value : 0), 0
    );
    if (distanceEl) distanceEl.textContent = formatKm(totalMeters);

    const baseReturnIndex = waypoints.findIndex((w) => w.isBaseReturn);
    const isOvernight     = baseReturnIndex !== -1;

    if (overnightEl) {
      overnightEl.textContent = isOvernight ? "Sí" : "No";
      overnightEl.classList.toggle("is-overnight", isOvernight);
    }
    togglePhaseFields(isOvernight);

    if (isOvernight) {
      const phase1Meters = route.legs
        .slice(0, baseReturnIndex + 1)
        .reduce((s, l) => s + (l.distance ? l.distance.value : 0), 0);
      const p1 = document.getElementById("route-summary-phase1");
      const p2 = document.getElementById("route-summary-phase2");
      if (p1) p1.textContent = formatKm(phase1Meters);
      if (p2) p2.textContent = formatKm(totalMeters - phase1Meters);
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

    const allWaypoints = [
      ...waypoints.map((s) => ({
        lat: s.lat, lng: s.lng,
        label: s.label, is_base_return: s.isBaseReturn, is_via: s.isVia || false,
      })),
      ..._dragWaypoints.map((pt) => ({
        lat: pt.lat, lng: pt.lng,
        label: "Vía (arrastre)", is_base_return: false, is_via: true,
      })),
    ];

    const payload = {
      base_id: config.base.id,
      waypoints_json: JSON.stringify(allWaypoints),
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
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      _calculatedRouteData = { payload, data };

      const distanceEl  = document.getElementById("route-summary-distance");
      const overnightEl = document.getElementById("route-summary-overnight");
      const phase1El    = document.getElementById("route-summary-phase1");
      const phase2El    = document.getElementById("route-summary-phase2");

      const km1 = parseFloat(data.km_phase1 || 0);
      const km2 = parseFloat(data.km_phase2 || 0);
      const totalKm = data.is_overnight
        ? (km1 + km2).toFixed(1)
        : parseFloat(data.route_distance_km || km1).toFixed(1);

      if (distanceEl) { distanceEl.textContent = `${totalKm} km`; distanceEl.classList.add("calculated"); }
      if (overnightEl) {
        overnightEl.textContent = data.is_overnight ? "Sí" : "No";
        overnightEl.classList.toggle("is-overnight", Boolean(data.is_overnight));
      }
      togglePhaseFields(Boolean(data.is_overnight));
      if (data.is_overnight) {
        if (phase1El && data.km_phase1) phase1El.textContent = `${km1.toFixed(1)} km`;
        if (phase2El && data.km_phase2) phase2El.textContent = `${km2.toFixed(1)} km`;
      }
      if (tollsEl) {
        tollsEl.textContent = data.has_tolls ? "Sí" : "No";
        tollsEl.classList.toggle("has-tolls", Boolean(data.has_tolls));
      }
      if (hintEl) hintEl.classList.add("d-none");
      if (confirmBtn) confirmBtn.disabled = false;

    } catch (err) {
      showRoutePlannerError(err.message || "No se ha podido calcular la ruta. Inténtalo de nuevo.");
      if (calculateBtn) calculateBtn.disabled = false;
    } finally {
      hideCalculateSpinner();
    }
  }

  // ------------------------------------------------------------------
  // FASE 2 — Confirmar ruta
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

    const summaryEl   = document.getElementById("route-confirmed-summary");
    const summaryText = document.getElementById("route-confirmed-text");
    if (summaryEl && summaryText) {
      const km1 = parseFloat(data.km_phase1 || 0);
      const km2 = parseFloat(data.km_phase2 || 0);
      const totalKm = data.is_overnight
        ? (km1 + km2).toFixed(1)
        : parseFloat(data.route_distance_km || km1).toFixed(1);
      const tolls   = data.has_tolls ? " · Con peajes" : "";
      const ovnight = data.is_overnight ? " · Pernocta" : "";
      summaryText.textContent = `Ruta confirmada — ${totalKm} km${ovnight}${tolls}`;
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
      alertEl.id = "route-planner-error";
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
