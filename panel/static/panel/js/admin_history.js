// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/admin_history.js
//
// Admin history view — bulk selection, single delete and machine autocomplete.
// Vista de historial admin — selección múltiple, eliminar individual y autocompletado.
(function () {
    "use strict";

    // ------------------------------------------------------------------
    // Bulk selection — Selección múltiple.
    // Handles: select-all checkbox, per-row checkboxes, bulk bar
    // visibility and counter update.
    // Gestiona: checkbox seleccionar-todos, checkboxes por fila,
    // visibilidad de la barra bulk y actualización del contador.
    // ------------------------------------------------------------------
    function initBulkGroup(groupName) {
        var allChk  = document.querySelector('.bulk-check-all[data-target="' + groupName + '"]');
        var bar     = document.getElementById("bulk-bar-" + groupName);
        var counter = document.getElementById("bulk-count-" + groupName);

        // Guard: elements only exist when the corresponding tab is active.
        // Guardia: los elementos solo existen cuando la pestaña está activa.
        if (!allChk || !bar) { return; }

        function getItems() {
            return Array.from(document.querySelectorAll(
                '.bulk-check-item[data-group="' + groupName + '"]'
            ));
        }

        function refresh() {
            var items   = getItems();
            var checked = items.filter(function (c) { return c.checked; });
            bar.style.display = checked.length > 0 ? "flex" : "none";
            if (counter) {
                counter.textContent = checked.length + " seleccionado" +
                    (checked.length === 1 ? "" : "s");
            }
            allChk.checked       = items.length > 0 && checked.length === items.length;
            allChk.indeterminate = checked.length > 0 && checked.length < items.length;
        }

        allChk.addEventListener("change", function () {
            getItems().forEach(function (c) { c.checked = allChk.checked; });
            refresh();
        });

        document.addEventListener("change", function (e) {
            if (e.target.matches('.bulk-check-item[data-group="' + groupName + '"]')) {
                refresh();
            }
        });
    }

    // ------------------------------------------------------------------
    // Single delete — Eliminación individual.
    // Reads data-pk, data-form and data-tab from the button.
    // Lee data-pk, data-form y data-tab del botón.
    // ------------------------------------------------------------------
    document.addEventListener("click", function (e) {
        var btn = e.target.closest(".btn-delete-single");
        if (!btn) { return; }
        var pk     = btn.dataset.pk;
        var formId = btn.dataset.form;
        var tab    = btn.dataset.tab;
        if (!confirm("¿Eliminar el parte #" + pk + "? Esta acción no se puede deshacer.")) { return; }
        var f = document.getElementById(formId);
        if (!f) { return; }
        f.querySelector("[name=action]").value     = "delete_work_order";
        f.querySelector("[name=active_tab]").value = tab;
        var inp   = document.createElement("input");
        inp.type  = "hidden";
        inp.name  = "work_order_pk";
        inp.value = pk;
        f.appendChild(inp);
        f.submit();
    });

    // ------------------------------------------------------------------
    // Machine / CdG autocomplete — Autocompletado de Máquina / CdG.
    // Uses GET /panel/operator/assets/?q=XX → {"results": [...]}
    // ------------------------------------------------------------------
    function initMachineAutocomplete() {
        var input    = document.getElementById("filter-machine-input");
        var dropdown = document.getElementById("filter-machine-dropdown");

        if (!input || !dropdown) { return; }

        var _timer  = null;
        var _active = -1;

        function showDropdown(items) {
            dropdown.innerHTML = "";
            if (!items.length) { dropdown.style.display = "none"; return; }
            items.forEach(function (code) {
                var li        = document.createElement("li");
                li.textContent = code;
                li.addEventListener("mousedown", function (e) {
                    e.preventDefault();
                    input.value            = code;
                    dropdown.style.display = "none";
                });
                dropdown.appendChild(li);
            });
            _active                = -1;
            dropdown.style.display = "block";
        }

        function fetchSuggestions(q) {
            /* Build URL with current operator/date filters for scoped results.
               Construir URL con filtros actuales de operario/fecha para resultados acotados. */
            var params = new URLSearchParams({ q: q });
            var opInput   = document.querySelector("[name='operator_pk']");
            var dateFrom  = document.querySelector("[name='date_from']");
            var dateTo    = document.querySelector("[name='date_to']");
            if (opInput  && opInput.value)  { params.set("operator_pk", opInput.value); }
            if (dateFrom && dateFrom.value) { params.set("date_from",   dateFrom.value); }
            if (dateTo   && dateTo.value)   { params.set("date_to",     dateTo.value); }
            fetch("/panel/work-orders/machines/?" + params.toString())
                .then(function (r) { return r.json(); })
                .then(function (data) { showDropdown(data.results || []); })
                .catch(function () { dropdown.style.display = "none"; });
        }

        input.addEventListener("input", function () {
            clearTimeout(_timer);
            var q = input.value.trim();
            if (q.length < 1) { dropdown.style.display = "none"; return; }
            _timer = setTimeout(function () { fetchSuggestions(q); }, 220);
        });

        input.addEventListener("keydown", function (e) {
            var items = dropdown.querySelectorAll("li");
            if (!items.length) { return; }
            if (e.key === "ArrowDown") {
                e.preventDefault();
                _active = Math.min(_active + 1, items.length - 1);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                _active = Math.max(_active - 1, 0);
            } else if (e.key === "Enter" && _active >= 0) {
                e.preventDefault();
                input.value            = items[_active].textContent;
                dropdown.style.display = "none";
                return;
            } else if (e.key === "Escape") {
                dropdown.style.display = "none";
                return;
            }
            items.forEach(function (li, i) {
                li.style.backgroundColor = i === _active ? "#e8f0fe" : "";
            });
        });

        document.addEventListener("click", function (e) {
            if (!input.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.style.display = "none";
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initBulkGroup("pending");
        initBulkGroup("history");
        initMachineAutocomplete();
    });

}());
