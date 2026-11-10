// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/select_filtered.js
/*
 * H24 (S149 invasora). Casilla "Solo los filtrados" en todos los
 * listados con el formato único (directriz 4.24).
 *
 * Miguel Ángel: "Incluimos una casilla para seleccionar solamente los
 * elementos filtrados: si hay 20 seleccionados pero el filtro muestra
 * 10, quiero poder seleccionar solo esos 10."
 *
 * Corregido el mismo día, Miguel Ángel: "no es los que se ven, sino
 * los filtrados [...] señalo a todos los de grúa con la selección de
 * grupo, filtro quitando a los que ya fichan [...] quiero seleccionar
 * de grúas los que siguen sin fichar". Al marcarla, la selección se
 * queda en su cruce con el filtro: de lo seleccionado, solo lo que
 * cumple el filtro actual. La lista de cada listado trae todas las
 * filas del filtro (sin paginar; Personal, páginas de 2000), así que
 * las filas marcadas de la lista son ese cruce, se vean o no en
 * pantalla. Se vacía con el propio "Limpiar" del listado y se vuelven
 * a marcar esas filas con sus casillas, para que cada listado guarde
 * la selección como siempre (navegación persistida, visor "Selección
 * actual"). Queda marcada mientras todo lo seleccionado cumpla el
 * filtro; desmarcarla no cambia la selección.
 *
 * Se engancha sola en cualquier listado que tenga el trío
 * `{prefijo}-mass-clear` (Limpiar), `{prefijo}-mass-count` (contador)
 * y `{prefijo}-check-all` o `{prefijo}-select-all-page`, con las
 * casillas de fila `.{prefijo}-row-check` o `.{prefijo}-select-checkbox`.
 */
(function () {
    "use strict";

    var BOX_CLASS = "eb-only-filtered";

    function visible(el) {
        return !!(el && el.offsetParent !== null);
    }

    function pick(nodes) {
        var list = Array.prototype.slice.call(nodes);
        return list.filter(visible)[0] || list[0] || null;
    }

    function parts(prefix) {
        var checkAll = pick(document.querySelectorAll(
            '[id="' + prefix + '-check-all"], [id="' + prefix + '-select-all-page"]'));
        var scope = (checkAll && checkAll.closest("table")) || document;
        var rows = Array.prototype.slice.call(scope.querySelectorAll(
            "." + prefix + "-row-check, ." + prefix + "-select-checkbox"));
        var count = pick(document.querySelectorAll('[id="' + prefix + '-mass-count"]'));
        var clear = pick(document.querySelectorAll('[id="' + prefix + '-mass-clear"]'));
        return {checkAll: checkAll, rows: rows, count: count, clear: clear};
    }

    function sync(box) {
        var p = parts(box.dataset.prefix);
        var selected = p.count ? parseInt(p.count.textContent, 10) || 0 : -1;
        var checked = p.rows.filter(function (cb) { return cb.checked; }).length;
        box.checked = checked > 0 && selected === checked;
        box.disabled = !p.clear || p.rows.length === 0;
    }

    function syncAll() {
        document.querySelectorAll("input." + BOX_CLASS).forEach(sync);
    }

    var pending = null;
    function syncSoon() {
        if (pending) return;
        pending = setTimeout(function () {
            pending = null;
            syncAll();
        }, 0);
    }

    function apply(box) {
        var p = parts(box.dataset.prefix);
        if (box.checked && p.clear) {
            var keep = p.rows.filter(function (cb) { return cb.checked; });
            p.clear.click();
            keep.forEach(function (cb) {
                cb.checked = true;
                cb.dispatchEvent(new Event("change", {bubbles: true}));
            });
        }
        syncSoon();
    }

    function attach() {
        document.querySelectorAll('[id$="-mass-clear"]').forEach(function (clear) {
            if (clear.dataset.ebOnlyFiltered) return;
            var prefix = clear.id.slice(0, -"-mass-clear".length);
            if (!document.querySelector('[id="' + prefix + '-mass-count"]')) return;
            clear.dataset.ebOnlyFiltered = "1";
            var label = document.createElement("label");
            label.className = "form-check-label small text-nowrap d-inline-flex align-items-center gap-1";
            label.title = "De lo seleccionado, deja solo lo que cumple el filtro actual";
            var box = document.createElement("input");
            box.type = "checkbox";
            box.className = "form-check-input mt-0 " + BOX_CLASS;
            box.dataset.prefix = prefix;
            box.addEventListener("change", function (ev) {
                ev.stopPropagation();
                apply(box);
            });
            label.appendChild(box);
            label.appendChild(document.createTextNode("Solo los filtrados"));
            clear.insertAdjacentElement("afterend", label);
            sync(box);
        });
    }

    function init() {
        attach();
        syncSoon();
        // Las selecciones guardadas se restauran tras cargar la página.
        setTimeout(syncAll, 300);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
    document.addEventListener("htmx:afterSettle", function () {
        attach();
        syncSoon();
    });
    document.addEventListener("change", function (ev) {
        if (!ev.target.classList.contains(BOX_CLASS)) syncSoon();
    });
    document.addEventListener("click", syncSoon);
}());
