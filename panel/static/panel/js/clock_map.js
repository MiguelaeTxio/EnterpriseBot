/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/clock_map.js
 *
 * H24 (S129). Map of a clock-in press inside the panel (Google Maps JS
 * API, same key as the budgets) instead of the Google Maps website.
 * Any element with data-clk-map-root holds a .clk-map-wrap (title,
 * close button, .clk-map); a click on a .clk-map-link inside it
 * (data-lat, data-lon, data-acc, data-label) shows that press with a
 * marker and its GPS accuracy circle. Used by the Fichajes tab and by
 * the worker's file (Personal). Without the API loaded, opens Google
 * Maps as before.
 *
 * H24 (S129). Mapa de una pulsación de fichaje dentro del panel (API
 * de Google Maps) en vez de la web de Google Maps. Lo usan la pestaña
 * Fichajes y la ficha del trabajador.
 */
(function () {
    "use strict";
    if (window.__ebClockMapBound) { return; }
    window.__ebClockMapBound = true;

    async function show(root, link) {
        const lat = parseFloat(link.dataset.lat);
        const lng = parseFloat(link.dataset.lon);
        const acc = parseInt(link.dataset.acc || "0", 10);
        const g = window.google;
        if (!g || !g.maps || !g.maps.importLibrary) {
            window.open("https://www.google.com/maps?q=" + lat + "," + lng, "_blank", "noopener");
            return;
        }
        const wrap = root.querySelector(".clk-map-wrap");
        root.querySelector(".clk-map-title").textContent = link.dataset.label || "";
        wrap.classList.remove("d-none");
        const position = {lat: lat, lng: lng};
        const mapsLib = await g.maps.importLibrary("maps");
        const markerLib = await g.maps.importLibrary("marker");
        let state = root.__clkMap;
        if (!state) {
            const map = new mapsLib.Map(root.querySelector(".clk-map"), {
                center: position, zoom: 16,
                mapId: root.dataset.mapId || "DEMO_MAP_ID",
                streetViewControl: false,
            });
            state = root.__clkMap = {
                map: map,
                marker: new markerLib.AdvancedMarkerElement({map: map, position: position}),
                circle: new mapsLib.Circle({
                    map: map, center: position, radius: acc || 0,
                    strokeColor: "#0d6efd", strokeOpacity: 0.6, strokeWeight: 1,
                    fillColor: "#0d6efd", fillOpacity: 0.12,
                }),
            };
        } else {
            state.map.setCenter(position);
            state.map.setZoom(16);
            state.marker.position = position;
            state.circle.setCenter(position);
            state.circle.setRadius(acc || 0);
        }
        wrap.scrollIntoView({block: "nearest"});
    }

    document.addEventListener("click", function (e) {
        const link = e.target.closest(".clk-map-link");
        if (link) {
            const root = link.closest("[data-clk-map-root]");
            if (!root) { return; }
            e.preventDefault();
            show(root, link);
            return;
        }
        const close = e.target.closest(".clk-map-close");
        if (close) {
            const root = close.closest("[data-clk-map-root]");
            if (root) { root.querySelector(".clk-map-wrap").classList.add("d-none"); }
        }
    });
}());
