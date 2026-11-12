// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/group_splitter.js
/*
 * S149 (Miguel Ángel): en el recuadro "Grupos de selección" queda poco
 * espacio para el árbol y para lo de debajo; "entre medio de las dos una
 * barrita que la pinchas y subes o bajas para darle más espacio a una
 * parte o a la otra", igual en todas las vistas.
 *
 * Marcado (los tres recuadros de grupos: Personal, Maquinaria y
 * panel/_person_group_filter.html):
 *   <div class="... d-flex flex-column eb-split">
 *     <div class="eb-split-top">…árbol…</div>
 *     <div class="eb-split-handle" role="separator" …></div>
 *     <div class="eb-split-bottom">…lo de debajo…</div>
 *   </div>
 * Arrastrar la barra (ratón o dedo) o las flechas con ella enfocada
 * reparte el alto; doble clic vuelve al reparto de siempre. El reparto
 * es uno para todas las vistas (localStorage "eb-group-split"), en
 * proporción del alto del recuadro. Escucha en el documento, así que
 * vale también para los recuadros que llegan por htmx.
 */
(function () {
    "use strict";
    var KEY = "eb-group-split";
    var MIN_TOP = 48, MIN_BOTTOM = 40;

    var style = document.createElement("style");
    style.textContent =
        ".eb-split-handle{flex:0 0 10px;margin:2px 0;cursor:row-resize;position:relative;border-radius:4px;touch-action:none}" +
        ".eb-split-handle::before{content:'';position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--bs-border-color,#dee2e6)}" +
        ".eb-split-handle::after{content:'';position:absolute;left:50%;top:50%;width:40px;height:4px;margin:-2px 0 0 -20px;border-radius:2px;background:#adb5bd}" +
        ".eb-split-handle:hover,.eb-split-handle:focus-visible,.eb-split-handle.eb-dragging{background:rgba(13,110,253,.12);outline:none}" +
        ".eb-split-handle:hover::after,.eb-split-handle:focus-visible::after,.eb-split-handle.eb-dragging::after{background:#0d6efd}" +
        ".eb-split-bottom{flex:0 0 auto}" +
        ".eb-split.eb-split-set>.eb-split-top{flex:0 0 var(--eb-split-top)!important;min-height:0;max-height:none!important}" +
        ".eb-split.eb-split-set>.eb-split-bottom{flex:1 1 auto;min-height:0;overflow-y:auto}";
    document.head.appendChild(style);

    function readRatio() {
        try {
            var value = parseFloat(window.localStorage.getItem(KEY));
            return value > 0 && value < 1 ? value : null;
        } catch (e) { return null; }
    }
    function saveRatio(value) {
        try {
            if (value === null) { window.localStorage.removeItem(KEY); }
            else { window.localStorage.setItem(KEY, String(value)); }
        } catch (e) { /* sin almacenamiento: vale para esta página */ }
    }
    function parts(card) {
        return {
            top: card.querySelector(":scope > .eb-split-top"),
            handle: card.querySelector(":scope > .eb-split-handle"),
            bottom: card.querySelector(":scope > .eb-split-bottom"),
        };
    }
    // Alto que se reparten el árbol y lo de debajo.
    function room(card) {
        var p = parts(card);
        if (!p.top || !p.handle || !p.bottom) { return 0; }
        return p.top.offsetHeight + p.bottom.offsetHeight;
    }
    function setTop(card, px) {
        card.style.setProperty("--eb-split-top", Math.round(px) + "px");
        card.classList.add("eb-split-set");
    }
    function clamp(card, px) {
        var total = room(card);
        return Math.max(MIN_TOP, Math.min(px, total - MIN_BOTTOM));
    }
    function applyAll() {
        var ratio = readRatio();
        document.querySelectorAll(".eb-split").forEach(function (card) {
            if (ratio === null) {
                card.classList.remove("eb-split-set");
                return;
            }
            // Medir sin el reparto puesto: el alto natural del recuadro.
            card.classList.remove("eb-split-set");
            var total = room(card);
            if (total > 0) { setTop(card, clamp(card, total * ratio)); }
        });
    }

    var drag = null;
    document.addEventListener("pointerdown", function (evt) {
        var handle = evt.target.closest(".eb-split-handle");
        if (!handle) { return; }
        var card = handle.parentElement;
        var p = parts(card);
        if (!p.top) { return; }
        evt.preventDefault();
        drag = {card: card, handle: handle, startY: evt.clientY, startTop: p.top.offsetHeight, total: room(card)};
        handle.classList.add("eb-dragging");
        try { handle.setPointerCapture(evt.pointerId); } catch (e) { /* nada */ }
    });
    document.addEventListener("pointermove", function (evt) {
        if (!drag) { return; }
        setTop(drag.card, clamp(drag.card, drag.startTop + evt.clientY - drag.startY));
    });
    function endDrag() {
        if (!drag) { return; }
        var top = parts(drag.card).top.offsetHeight;
        drag.handle.classList.remove("eb-dragging");
        if (drag.total > 0) { saveRatio(top / drag.total); }
        drag = null;
        applyAll();
    }
    document.addEventListener("pointerup", endDrag);
    document.addEventListener("pointercancel", endDrag);

    document.addEventListener("dblclick", function (evt) {
        if (!evt.target.closest(".eb-split-handle")) { return; }
        saveRatio(null);
        applyAll();
    });
    document.addEventListener("keydown", function (evt) {
        var handle = evt.target.closest && evt.target.closest(".eb-split-handle");
        if (!handle || (evt.key !== "ArrowUp" && evt.key !== "ArrowDown")) { return; }
        evt.preventDefault();
        var card = handle.parentElement;
        var total = room(card);
        var top = clamp(card, parts(card).top.offsetHeight + (evt.key === "ArrowUp" ? -16 : 16));
        setTop(card, top);
        if (total > 0) { saveRatio(top / total); }
        applyAll();
    });

    document.addEventListener("DOMContentLoaded", applyAll);
    document.addEventListener("htmx:afterSettle", applyAll);
    window.addEventListener("resize", applyAll);
    if (document.readyState !== "loading") { applyAll(); }
})();
