/*
 * /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/list_fullscreen.js
 *
 * S153. "Ampliar" button for every list (directive 4.26): the list
 * panel goes full screen, only the list (fullscreen_layers.js hides the
 * "Selección actual" column). Lists that already have their own button
 * keep it. Used by panel/_fixed_list_layout.html (every list with a
 * fixed top panel) and by lists without that layout (data-eb-fullscreen).
 * ---
 * Botón "Ampliar" en todos los listados (directriz 4.26). Miguel Ángel:
 * "en todos los listados debe poder ampliarse el listado, que es donde
 * se ve bien todo, y que no se amplíe la selección". El panel de la
 * lista pasa a pantalla completa y fullscreen_layers.js oculta la
 * columna "Selección actual". Los listados que ya tenían su propio
 * botón lo conservan (no se pone otro). Lo llama
 * panel/_fixed_list_layout.html (todos los listados con panel fijo
 * arriba) y, en los que no lo usan, basta con data-eb-fullscreen en el
 * contenedor (y data-eb-fullscreen-header en su cabecera, si no es el
 * primer rótulo en negrita).
 */
(function () {
    "use strict";
    var style = document.createElement("style");
    style.textContent = [
        ".eb-fs-panel:fullscreen{background-color:var(--bs-body-bg);padding:1rem;",
        "height:100vh!important;max-height:none!important;overflow:auto}",
        ".eb-fs-panel:fullscreen>.row{height:100%!important}",
        ".eb-fs-panel:fullscreen .fixed-list-scroll{flex:1 1 auto;min-height:0;",
        "max-height:none!important}",
        ".eb-fs-btn{line-height:1;padding:.1rem .35rem}",
        ".eb-fs-corner{position:relative}",
        ".eb-fs-corner>.eb-fs-btn{position:absolute;top:.35rem;right:.6rem;z-index:5;",
        "background-color:var(--bs-body-bg)}"
    ].join("");
    document.head.appendChild(style);

    function titleIn(root) {
        // El primer rótulo en negrita que no esté dentro de la tabla.
        var found = null;
        (root ? root.querySelectorAll(".fw-bold") : []).forEach(function (el) {
            if (!found && !el.closest("table, .dropdown-menu, .modal")) { found = el; }
        });
        return found;
    }

    function header(panel) {
        var own = panel.querySelector("[data-eb-fullscreen-header]");
        if (own) { return own; }
        // El rótulo de la primera columna (la lista) o el del panel.
        var row = panel.querySelector(".row");
        return titleIn(row && row.firstElementChild) || titleIn(panel);
    }

    function paint() {
        document.querySelectorAll(".eb-fs-btn").forEach(function (btn) {
            var on = document.fullscreenElement === btn._ebPanel;
            btn.querySelector("i").className = on ? "bi bi-fullscreen-exit" : "bi bi-fullscreen";
            btn.title = on ? "Salir de pantalla completa" : "Ampliar el listado a pantalla completa";
        });
    }

    function attach(panel) {
        if (!panel || panel.dataset.ebFsDone) { return; }
        panel.dataset.ebFsDone = "1";
        // Ya tiene su propio botón de pantalla completa: se respeta.
        if (panel.querySelector(".bi-fullscreen")) { return; }
        if (!panel.requestFullscreen) { return; }
        panel.classList.add("eb-fs-panel");
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-sm btn-outline-secondary float-end ms-2 eb-fs-btn";
        btn.setAttribute("aria-label", "Ampliar el listado a pantalla completa");
        btn.appendChild(document.createElement("i"));
        btn._ebPanel = panel;
        btn.addEventListener("click", function () {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                panel.requestFullscreen().catch(function () {});
            }
        });
        var title = header(panel);
        if (title) {
            title.appendChild(btn);
        } else {
            // Lista sin rótulo: el botón flota en la esquina del panel.
            panel.classList.add("eb-fs-corner");
            btn.classList.remove("float-end", "ms-2");
            panel.appendChild(btn);
        }
        paint();
    }

    function scan(root) {
        (root || document).querySelectorAll("[data-eb-fullscreen]").forEach(attach);
    }

    document.addEventListener("fullscreenchange", paint);
    document.addEventListener("DOMContentLoaded", function () { scan(); });
    document.addEventListener("htmx:afterSettle", function (event) { scan(event.target); });
    window.EbListFullscreen = {attach: attach, scan: scan};
}());
