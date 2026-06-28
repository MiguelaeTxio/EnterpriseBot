
// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/wizard_map.js
/**
 * Route planner modal logic (Google Maps JS API, Routes Library).
 *
 * Standard pattern (June 2026):
 *   - Routes Library: importLibrary('routes') → Route.computeRoutes()
 *   - DirectionsService / DirectionsRenderer DEPRECATED (Feb 2026) — NOT used
 *   - Two parallel Route.computeRoutes() calls via Promise.all:
 *       1. avoidTolls:false → dark blue polylines (primary, on top)
 *       2. avoidTolls:true  → light blue polylines (toll-free, below)
 *   - createPolylines() + setOptions() + setMap() for custom colors
 *   - Mobile: tap map → bottom sheet (Add stop / Pass through)
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
  const COLOR_PRIMARY = "#1565C0";   // Azul oscuro — ruta con peajes / Dark blue — toll route
  const COLOR_ALT     = "#4FC3F7";   // Azul claro visible — ruta sin peajes / Visible light blue — toll-free route
  const WEIGHT_ACTIVE = 7;
  const WEIGHT_DIM    = 5;
  const OPACITY_ACTIVE = 1.0;
  const OPACITY_DIM    = 0.75;  // Visible aunque no seleccionada / Visible even when not selected

  // ------------------------------------------------------------------
  // Estado del módulo
  // ------------------------------------------------------------------
  let map            = null;
  let Route          = null;   // Routes Library — Route class
  let geocoder       = null;
  let baseMarker     = null;
  let mapInitialized = false;
  let dragSourceIndex = null;
  let MarkerLib      = null;

  /**
   * Polylines activas — array de { polylines: Polyline[], isPrimary: bool,
   * distanceMeters: number, durationMillis: number }
   * index 0 = ruta sin peajes (azul claro, debajo)
   * index 1 = ruta con peajes (azul oscuro, encima)
   */
  let activeRoutes       = [];
  let selectedRouteIndex = 1;   // Por defecto seleccionada la ruta con peajes

  /** Waypoints del usuario: { lat, lng, label, isBaseReturn, isVia, marker } */
  const waypoints = [];

  /** Resultado de calculateRoute() — volcado en confirmRoute() */
  let _calculatedRouteData = null;

  // ------------------------------------------------------------------
  // Estado del drag de polyline
  // Polyline drag state
  // ------------------------------------------------------------------
  let _isDraggingPolyline = false;
  let _dragThrottleTimer  = null;
  let _dragSegmentIndex   = null;   // Índice del tramo (entre waypoints) arrastrado
  let _dragPreviewPolys   = [];     // Polylines provisionales del preview
  let _mapClickListener   = null;   // Referencia al listener map.click (para suspender)

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
  // Gestión de polylines activas
  // ------------------------------------------------------------------

  /** Elimina todas las polylines del mapa y vacía el array */
  function _clearRoutes() {
    activeRoutes.forEach((route) => {
      (route.polylines || []).forEach((p) => p.setMap(null));
    });
    activeRoutes = [];
    selectedRouteIndex = 1;
    document.querySelectorAll(".rp-route-cards-wrapper").forEach((el) => el.remove());
  }

  /**
   * Pinta las dos rutas con la Routes Library nativa.
   * Recibe los objetos Route de computeRoutes para ruta con peajes (routeNormal)
   * y ruta sin peajes (routeAlt). routeAlt puede ser null.
   *
   * Draws both routes using the native Routes Library.
   * Receives Route objects from computeRoutes for toll route (routeNormal)
   * and toll-free route (routeAlt). routeAlt may be null.
   */
  function _buildPolylinesFromRoutes(routeNormal, routeAlt) {
    _clearRoutes();

    // --- Ruta sin peajes (azul claro) — se pinta PRIMERO para quedar DEBAJO
    // --- Toll-free route (light blue) — drawn FIRST to appear BELOW
    if (routeAlt) {
      const polysAlt = routeAlt.createPolylines();
      polysAlt.forEach((p) => {
        p.setOptions({
          strokeColor:   COLOR_ALT,
          strokeOpacity: OPACITY_DIM,
          strokeWeight:  WEIGHT_DIM,
          zIndex:        1,
          clickable:     true,
        });
        p.setMap(map);
        p.addListener("click", () => _selectRoute(0));
      });
      activeRoutes.push({
        polylines:      polysAlt,
        isPrimary:      false,
        distanceMeters: routeAlt.distanceMeters || 0,
        durationMillis: routeAlt.durationMillis || 0,
      });
    }

    // --- Ruta con peajes (azul oscuro) — se pinta DESPUÉS para quedar ENCIMA
    // --- Toll route (dark blue) — drawn AFTER to appear ON TOP
    const polysNormal = routeNormal.createPolylines();
    polysNormal.forEach((p) => {
      p.setOptions({
        strokeColor:   COLOR_PRIMARY,
        strokeOpacity: OPACITY_ACTIVE,
        strokeWeight:  WEIGHT_ACTIVE,
        zIndex:        2,
        clickable:     true,
      });
      p.setMap(map);
      p.addListener("click", () => _selectRoute(routeAlt ? 1 : 0));
    });
    activeRoutes.push({
      polylines:      polysNormal,
      isPrimary:      true,
      distanceMeters: routeNormal.distanceMeters || 0,
      durationMillis: routeNormal.durationMillis || 0,
    });

    // Ajustar el mapa al viewport de la ruta principal
    // Fit map to primary route viewport
    if (routeNormal.viewport) {
      map.fitBounds(routeNormal.viewport, 50);
    }

    // Construir cards de selección si hay dos rutas
    if (routeAlt) {
      _buildRouteSelectorCards();
    }

    // Seleccionar la ruta con peajes por defecto (último índice)
    _selectRoute(activeRoutes.length - 1);

    // Activar drag de polyline (solo desktop — pointer:fine)
    // Enable polyline drag (desktop only — pointer:fine)
    if (!isMobileDevice()) {
      _bindPolylineDrag(
        activeRoutes.flatMap((r) => r.polylines || [])
      );
    }
  }

  /**
   * Selecciona la ruta con índice idx:
   * resalta su polyline, atenúa las demás.
   * Selects route at index idx: highlights its polyline, dims others.
   */
  function _selectRoute(idx) {
    selectedRouteIndex = idx;
    activeRoutes.forEach((route, i) => {
      const active = i === idx;
      (route.polylines || []).forEach((p) => {
        p.setOptions({
          strokeColor:   active ? (route.isPrimary ? COLOR_PRIMARY : COLOR_ALT) : COLOR_ALT,
          strokeOpacity: active ? OPACITY_ACTIVE : OPACITY_DIM,
          strokeWeight:  active ? WEIGHT_ACTIVE  : WEIGHT_DIM,
          zIndex:        active ? 2 : 1,
        });
      });
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

  function _buildRouteSelectorCards() {
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

    // activeRoutes[0] = sin peajes (azul claro), activeRoutes[1] = con peajes (azul oscuro)
    const cardDefs = [
      { label: "Sin peajes", color: COLOR_ALT,     idx: 0 },
      { label: "Con peajes", color: COLOR_PRIMARY,  idx: 1 },
    ];

    cardDefs.forEach(({ label, color, idx }) => {
      if (!activeRoutes[idx]) return;
      const km = (activeRoutes[idx].distanceMeters / 1000).toFixed(1);

      const card = document.createElement("div");
      card.className = "rp-route-card" + (idx === selectedRouteIndex ? " rp-route-card--active" : "");
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
    Route = RoutesLib.Route;   // Routes Library — clase Route para computeRoutes()

    const { Map }                           = MapsLib;
    const { AdvancedMarkerElement, PinElement } = MarkerLib;
    const { Geocoder }                      = GeocodingLib;

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

    geocoder = new Geocoder();

    _mapClickListener = map.addListener("click", async (event) => {
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
    // keepPolyline=true → el usuario seleccionó otra ruta, el botón debe
    // mantenerse habilitado para que pueda recalcular.
    // Only disable "Calcular ruta" if no real stops, or polyline is cleared.
    // keepPolyline=true → user selected another route, button stays enabled.
    const calcBtn = document.getElementById("route-btn-calculate");
    const hasStops = waypoints.some((w) => !w.isVia);
    if (calcBtn && !keepPolyline) calcBtn.disabled = !hasStops;

    if (!keepPolyline) {
      _clearRoutes();
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
  // Visualización de ruta en vivo con Routes Library nativa
  //
  // Dos llamadas paralelas a Route.computeRoutes() via Promise.all:
  //   1. avoidTolls:false → ruta con peajes (azul oscuro, encima)
  //   2. avoidTolls:true  → ruta sin peajes (azul claro, debajo)
  //
  // Live route display using native Routes Library.
  // Two parallel Route.computeRoutes() calls via Promise.all:
  //   1. avoidTolls:false → toll route (dark blue, on top)
  //   2. avoidTolls:true  → toll-free route (light blue, below)
  // ------------------------------------------------------------------

  async function recalculateRouteDisplay() {
    const config = getConfig();
    const hasStops = waypoints.some((w) => !w.isVia);

    if (!hasStops) {
      _clearRoutes();
      const distanceEl  = document.getElementById("route-summary-distance");
      const overnightEl = document.getElementById("route-summary-overnight");
      if (distanceEl)  distanceEl.textContent = "—";
      if (overnightEl) { overnightEl.textContent = "No"; overnightEl.classList.remove("is-overnight"); }
      togglePhaseFields(false);
      return;
    }

    showMapSpinner();
    _clearRoutes();

    // Origen: siempre la base.
    // Destino: la base SI existe un waypoint isBaseReturn; si no, el último waypoint real.
    // Esto evita cerrar el bucle (Málaga→Loja→Málaga) cuando el usuario solo ha
    // añadido paradas intermedias sin haber pulsado "Volver a base".
    //
    // Origin: always the base.
    // Destination: the base IF there is an isBaseReturn waypoint; otherwise the last real waypoint.
    // This prevents closing the loop (Málaga→Loja→Málaga) when the user has only
    // added intermediate stops without pressing "Return to base".
    const origin = { lat: config.base.lat, lng: config.base.lng };
    const hasBaseReturn = waypoints.some((w) => w.isBaseReturn);

    // Separar waypoints intermedios (todo excepto el último si no hay vuelta a base)
    // Separate intermediate waypoints (all except the last one if no base return)
    let intermediates;
    let destination;

    if (hasBaseReturn) {
      // Bucle cerrado: base → [...todos los waypoints...] → base
      // Closed loop: base → [...all waypoints...] → base
      destination = { lat: config.base.lat, lng: config.base.lng };
      intermediates = waypoints.map((wp) => ({
        location: { lat: wp.lat, lng: wp.lng },
        via: !!wp.isVia,
      }));
    } else {
      // Trayecto parcial: base → [...intermedios...] → último waypoint
      // Partial route: base → [...intermediates...] → last waypoint
      const lastWp = waypoints[waypoints.length - 1];
      destination = { lat: lastWp.lat, lng: lastWp.lng };
      intermediates = waypoints.slice(0, -1).map((wp) => ({
        location: { lat: wp.lat, lng: wp.lng },
        via: !!wp.isVia,
      }));
    }

    const baseRequest = {
      origin:      { lat: origin.lat,      lng: origin.lng      },
      destination: { lat: destination.lat, lng: destination.lng },
      intermediates,
      travelMode: "DRIVING",
      fields:     ["path", "legs", "distanceMeters", "durationMillis", "viewport"],
    };

    // Debug: loga cada llamada a computeRoutes con request, respuesta y error.
    // Visible en Eruda (movil) y DevTools (desktop).
    async function debugComputeRoutes(request, label) {
      console.group("[ROUTE] " + label);
      console.log("request origin:", JSON.stringify(request.origin));
      console.log("request destination:", JSON.stringify(request.destination));
      console.log("request intermediates:", JSON.stringify(request.intermediates));
      console.log("request travelMode:", request.travelMode);
      console.log("request routeModifiers:", JSON.stringify(request.routeModifiers));
      try {
        const result = await Route.computeRoutes(request);
        const route = result && result.routes && result.routes[0];
        if (!route) {
          const msg = "Sin rutas en respuesta para " + label;
          console.error(msg, result);
          console.groupEnd();
          throw new Error(msg);
        }
        console.log("OK — distanceMeters:", route.distanceMeters);
        console.groupEnd();
        return route;
      } catch (err) {
        console.error("ERROR en " + label + ":", err && err.message ? err.message : err);
        console.groupEnd();
        throw err;
      }
    }

    try {
      // Ambas rutas son obligatorias. Si cualquiera falla, el catch muestra error.
      // Both routes are mandatory. If either fails, catch shows error.
      const [routeNormal, routeAlt] = await Promise.all([
        debugComputeRoutes(
          { ...baseRequest, routeModifiers: { avoidTolls: false } },
          "con-peajes"
        ),
        debugComputeRoutes(
          { ...baseRequest, routeModifiers: { avoidTolls: true } },
          "sin-peajes"
        ),
      ]);

      console.log("[ROUTE] Ambas rutas OK — pintando polylines");
      _buildPolylinesFromRoutes(routeNormal, routeAlt);
      applyRouteSummary(routeNormal);

    } catch (err) {
      console.error("[ROUTE] Fallo definitivo:", err && err.message ? err.message : err);
      showRoutePlannerError("No se ha podido calcular la ruta. Inténtalo de nuevo.");
    } finally {
      hideMapSpinner();
    }
  }

  /**
   * Actualiza el resumen de distancia, pernocta y fases
   * a partir de un objeto Route de la Routes Library.
   *
   * Updates distance, overnight, and phase summary
   * from a Routes Library Route object.
   */
  function applyRouteSummary(route) {
    const distanceEl  = document.getElementById("route-summary-distance");
    const overnightEl = document.getElementById("route-summary-overnight");

    const totalMeters = route.distanceMeters || 0;
    if (distanceEl) distanceEl.textContent = formatKm(totalMeters);

    const baseReturnIndex = waypoints.findIndex((w) => w.isBaseReturn);
    // Overnight only when the base-return waypoint has real stops after it.
    // A single "Return to base" closing a normal circuit is NOT overnight.
    // Solo hay pernocta si tras el waypoint base-return hay paradas reales.
    // Un unico "Volver a base" que cierra el circuito normal NO es pernocta.
    const isOvernight = baseReturnIndex !== -1
      && waypoints.slice(baseReturnIndex + 1).some(
           (w) => !w.isVia && !w.isBaseReturn
         );

    if (overnightEl) {
      overnightEl.textContent = isOvernight ? "Sí" : "No";
      overnightEl.classList.toggle("is-overnight", isOvernight);
    }
    togglePhaseFields(isOvernight);

    if (isOvernight && route.legs && route.legs.length) {
      const phase1Meters = route.legs
        .slice(0, baseReturnIndex + 1)
        .reduce((s, leg) => s + (leg.distanceMeters || 0), 0);
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

    const allWaypoints = waypoints.map((s) => ({
      lat: s.lat, lng: s.lng,
      label: s.label, is_base_return: s.isBaseReturn, is_via: s.isVia || false,
    }));

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
  // Drag de polyline — forzar ruta por un punto del mapa (solo desktop)
  // Polyline drag — force route through a map point (desktop only)
  // ------------------------------------------------------------------

  /**
   * Adjunta los listeners mousedown a cada polyline para activar el drag.
   * El mousemove se escucha en la misma polyline (no en el mapa) para evitar
   * el problema conocido de Maps JS API en el que el mapa no recibe mousemove
   * cuando el cursor permanece sobre la polyline.
   * mouseup se escucha en document para capturar el soltado aunque el cursor
   * salga del área de la polyline.
   *
   * Attaches mousedown listeners to each polyline to activate drag mode.
   * mousemove is listened on the polyline itself (not on the map) to avoid
   * the known Maps JS API issue where the map doesn't receive mousemove when
   * the cursor stays over the polyline.
   * mouseup is listened on document to catch the release even when the cursor
   * leaves the polyline area.
   *
   * @param {google.maps.Polyline[]} polylines
   */
  function _bindPolylineDrag(polylines) {
    polylines.forEach((poly) => {
      poly.addListener("mousedown", (event) => {
        if (isMobileDevice()) return;

        _isDraggingPolyline = true;
        _dragSegmentIndex   = null;

        // Bloquear pan del mapa — imprescindible para que el mapa no se
        // arrastre durante el drag y para que reciba mousemove/mouseup.
        // Block map pan — essential so the map doesn't pan during drag
        // and so it receives mousemove/mouseup events.
        map.setOptions({ draggable: false, gestureHandling: "none" });

        // Suspender click del mapa para no añadir paradas al soltar
        // Suspend map click to avoid adding stops on release
        if (_mapClickListener) {
          google.maps.event.removeListener(_mapClickListener);
          _mapClickListener = null;
        }

        const mapDiv = map.getDiv();
        if (mapDiv) mapDiv.style.cursor = "grabbing";

        // mousemove en el mapa (funciona porque draggable:false libera
        // los eventos de movimiento al handler de Maps JS API).
        // mousemove on the map (works because draggable:false releases
        // move events to the Maps JS API handler).
        const _moveListener = map.addListener(
          "mousemove",
          (moveEvent) => {
            if (!_isDraggingPolyline) return;
            if (_dragThrottleTimer) return;
            _dragThrottleTimer = setTimeout(() => {
              _dragThrottleTimer = null;
            }, 200);
            _onPolylineDrag(moveEvent.latLng);
          }
        );

        // mouseup en el mapa — recibe LatLng directamente, sin proyección
        // mouseup on the map — receives LatLng directly, no projection needed
        const _upListener = google.maps.event.addListenerOnce(
          map,
          "mouseup",
          (upEvent) => {
            google.maps.event.removeListener(_moveListener);
            _commitPolylineDrag(
              upEvent.latLng || _lastDragLatLng
            );
          }
        );
      });
    });
  }

  /** Última posición LatLng registrada durante el drag (para fallback en mouseup) */
  let _lastDragLatLng = null;

  /**
   * Llamado en cada evento mousemove throttled durante el drag.
   * Llama a snapToRoads y pinta una polyline preview punteada.
   *
   * Called on each throttled mousemove during drag.
   * Calls snapToRoads and draws a dotted preview polyline.
   *
   * @param {google.maps.LatLng} latLng
   */
  async function _onPolylineDrag(latLng) {
    if (!_isDraggingPolyline) return;

    _lastDragLatLng = latLng;

    // Limpiar preview anterior
    // Clear previous preview
    _dragPreviewPolys.forEach((p) => p.setMap(null));
    _dragPreviewPolys = [];

    const cfg    = getConfig();
    const origin = { lat: cfg.base.lat, lng: cfg.base.lng };

    // Construir el mismo request que recalculateRouteDisplay pero con
    // el punto del cursor insertado como via:true. Solo avoidTolls:false
    // para minimizar latencia del preview.
    // Build the same request as recalculateRouteDisplay but with the
    // cursor point inserted as via:true. Only avoidTolls:false to
    // minimise preview latency.
    const hasStops    = waypoints.some((w) => !w.isVia);
    if (!hasStops) return;

    const hasBaseReturn = waypoints.some((w) => w.isBaseReturn);
    let destination;
    let baseIntermediates;

    if (hasBaseReturn) {
      destination        = { lat: cfg.base.lat, lng: cfg.base.lng };
      baseIntermediates  = waypoints.map((wp) => ({
        location: { lat: wp.lat, lng: wp.lng },
        via:      !!wp.isVia,
      }));
    } else {
      const lastWp      = waypoints[waypoints.length - 1];
      destination       = { lat: lastWp.lat, lng: lastWp.lng };
      baseIntermediates = waypoints.slice(0, -1).map((wp) => ({
        location: { lat: wp.lat, lng: wp.lng },
        via:      !!wp.isVia,
      }));
    }

    // Insertar el punto del cursor antes del último intermedio
    // Insert cursor point before the last intermediate
    const insertAt = Math.max(baseIntermediates.length - 1, 0);
    const previewIntermediates = [...baseIntermediates];
    previewIntermediates.splice(insertAt, 0, {
      location: { lat: latLng.lat(), lng: latLng.lng() },
      via:      true,
    });

    try {
      const result = await Route.computeRoutes({
        origin,
        destination,
        intermediates:  previewIntermediates,
        travelMode:     "DRIVING",
        routeModifiers: { avoidTolls: false },
        fields:         ["path"],
      });

      const route = result && result.routes && result.routes[0];
      if (!route || !_isDraggingPolyline) return;

      // Pintar polylines del preview en naranja punteado
      // Draw preview polylines in dotted orange
      const polys = route.createPolylines();
      polys.forEach((p) => {
        p.setOptions({
          strokeColor:   "#FF6D00",
          strokeOpacity: 0,
          strokeWeight:  6,
          zIndex:        10,
          clickable:     false,
          icons: [
            {
              icon:   {
                path:           "M 0,-1 0,1",
                strokeOpacity:  0.85,
                strokeColor:    "#FF6D00",
                scale:          4,
              },
              offset: "0",
              repeat: "14px",
            },
          ],
        });
        p.setMap(map);
        _dragPreviewPolys.push(p);
      });

      // Dot de anclaje en la posición del cursor
      // Anchor dot at cursor position
      const dot = new google.maps.Polyline({
        path: [
          { lat: latLng.lat(), lng: latLng.lng() },
          { lat: latLng.lat(), lng: latLng.lng() },
        ],
        strokeColor:   "#FF6D00",
        strokeOpacity: 1,
        strokeWeight:  14,
        zIndex:        12,
        clickable:     false,
        map,
      });
      _dragPreviewPolys.push(dot);

    } catch (_) {
      // Si falla el preview, solo pintar el dot
      // If preview fails, just show the dot
      const dot = new google.maps.Polyline({
        path: [
          { lat: latLng.lat(), lng: latLng.lng() },
          { lat: latLng.lat(), lng: latLng.lng() },
        ],
        strokeColor:   "#FF6D00",
        strokeOpacity: 1,
        strokeWeight:  14,
        zIndex:        12,
        clickable:     false,
        map,
      });
      _dragPreviewPolys.push(dot);
    }
  }

  /**
   * Cancela el drag sin confirmar ningún waypoint.
   * Cancels the drag without confirming any waypoint.
   */
  function _abortPolylineDrag() {
    _isDraggingPolyline = false;
    _lastDragLatLng     = null;

    if (_dragThrottleTimer) {
      clearTimeout(_dragThrottleTimer);
      _dragThrottleTimer = null;
    }

    _dragPreviewPolys.forEach((p) => p.setMap(null));
    _dragPreviewPolys = [];

    const mapDiv = map.getDiv();
    if (mapDiv) mapDiv.style.cursor = "";

    map.setOptions({ draggable: true, gestureHandling: "auto" });
    _restoreMapClickListener();
  }

  /**
   * Llamado en mouseup: confirma el waypoint vía en la posición snapeada.
   * Inserta el punto en waypoints[], invalida el cálculo y recalcula.
   *
   * Called on mouseup: confirms the via waypoint at the snapped position.
   * Inserts the point in waypoints[], invalidates and recalculates.
   *
   * @param {google.maps.LatLng} latLng
   */
  async function _commitPolylineDrag(latLng) {
    _isDraggingPolyline = false;
    _lastDragLatLng     = null;

    if (_dragThrottleTimer) {
      clearTimeout(_dragThrottleTimer);
      _dragThrottleTimer = null;
    }

    // Limpiar preview
    // Clear preview
    _dragPreviewPolys.forEach((p) => p.setMap(null));
    _dragPreviewPolys = [];

    const mapDiv = map.getDiv();
    if (mapDiv) mapDiv.style.cursor = "";

    map.setOptions({ draggable: true, gestureHandling: "auto" });
    _restoreMapClickListener();

    const snapped = { lat: latLng.lat(), lng: latLng.lng() };

    // Insertar waypoint vía antes del último waypoint real
    // Insert via waypoint before the last real waypoint
    const insertAt = Math.max(waypoints.length - 1, 0);
    waypoints.splice(insertAt, 0, {
      lat:          snapped.lat,
      lng:          snapped.lng,
      label:        "Paso por carretera",
      isBaseReturn: false,
      isVia:        true,
      marker:       null,
    });

    _dragSegmentIndex = null;
    _invalidateCalculation(false);
    renderStopsList();
    recalculateRouteDisplay();
  }

  /**
   * Restaura el listener click del mapa tras un drag (o su cancelación).
   * Restores the map click listener after a drag (or its cancellation).
   */
  function _restoreMapClickListener() {
    if (_mapClickListener) return;   // Ya restaurado
    const mobile = isMobileDevice();
    _mapClickListener = map.addListener("click", async (event) => {
      let label = "Punto manual";
      try {
        const { results } = await geocoder.geocode({
          location: event.latLng,
        });
        if (results && results[0]) label = results[0].formatted_address;
      } catch (_) {}

      if (mobile) {
        _showMobileMapMenu(event.latLng, label);
      } else {
        addWaypoint(
          event.latLng.lat(),
          event.latLng.lng(),
          label,
          false,
          false
        );
      }
    });
  }

  /**
   * Llama a la Roads API snapToRoads para ajustar {lat,lng} a la carretera
   * más cercana. Lanza Error si la respuesta es inesperada o sin puntos.
   * La API key se lee de window.ROUTE_PLANNER_CONFIG.googleMapsApiKey.
   *
   * Calls Roads API snapToRoads to snap {lat,lng} to the nearest road.
   * Throws Error if the response is unexpected or has no snapped points.
   * API key is read from window.ROUTE_PLANNER_CONFIG.googleMapsApiKey.
   *
   * @param {number} lat
   * @param {number} lng
   * @returns {Promise<{lat:number, lng:number}>}
   */
  async function _snapToRoad(lat, lng) {
    const cfg    = getConfig();
    const apiKey = cfg.googleMapsApiKey || "";
    const url    = (
      "https://roads.googleapis.com/v1/snapToRoads"
      + `?path=${lat},${lng}&key=${apiKey}`
    );
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error(`snapToRoads HTTP ${resp.status}`);
    }
    const data = await resp.json();
    if (!data.snappedPoints || !data.snappedPoints.length) {
      throw new Error("snapToRoads: ZERO_RESULTS");
    }
    const loc = data.snappedPoints[0].location;
    return { lat: loc.latitude, lng: loc.longitude };
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
