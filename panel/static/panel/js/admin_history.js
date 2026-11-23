// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/admin_history.js
//
// Admin history view — selection (S133, directive 4.24), bulk actions,
// single delete and machine autocomplete.
// Partes Digitales — selección guardada (S133, directriz 4.24), acciones
// masivas, eliminar individual y autocompletado de máquina.
(function () {
    "use strict";

    // ------------------------------------------------------------------
    // S133 (directriz 4.24): selección de partes que sobrevive a filtros,
    // orden y pestañas, guardada por usuario (4.15), con su visor
    // "Selección actual", "Mostrar solo la selección actual", acciones
    // masivas siempre visibles en el panel fijo y pantalla completa.
    // ------------------------------------------------------------------
    var selection = new Map();

    // S147: "Grupos de selección" (como en Personal): la selección son
    // los partes del listado de las personas de los grupos marcados.
    window.EbGroupSelect = window.EbGroupSelect || {};
    // S149: las cuentas de los partes marcados, para crear un grupo con
    // ellas.
    window.EbGroupGet = window.EbGroupGet || {};
    window.EbGroupGet.wo = function () {
        var users = new Set();
        rowChecks().forEach(function (cb) {
            if (selection.has(cb.dataset.key) && cb.dataset.operator) {
                users.add(cb.dataset.operator);
            }
        });
        return {persons: [], users: Array.from(users)};
    };
    window.EbGroupSelect.wo = function (people) {
        selection.clear();
        rowChecks().forEach(function (cb) {
            if (people.users.has(cb.dataset.operator)) {
                selection.set(cb.dataset.key, cb.dataset.label || "");
            }
        });
        saveSelection();
        refreshSelectionUi();
        applyOnlySelected();
    };
    var screenKey = null;

    function readJson(id, fallback) {
        var el = document.getElementById(id);
        if (!el) { return fallback; }
        try { return JSON.parse(el.textContent); } catch (e) { return fallback; }
    }

    function saveSelection() {
        if (!screenKey || !window.EbNavState) { return; }
        var payload = Array.from(selection.entries()).map(function (pair) {
            return {key: pair[0], label: pair[1]};
        });
        window.EbNavState.save(screenKey, {selection: payload});
    }

    function rowChecks() {
        return Array.from(document.querySelectorAll(".wo-row-check"));
    }

    function applyOnlySelected() {
        var only = document.getElementById("wo-only-selected");
        var on = !!(only && only.checked);
        document.querySelectorAll("#wo-results-scroll tbody tr[data-key]").forEach(function (tr) {
            tr.classList.toggle("d-none", on && !selection.has(tr.dataset.key));
        });
    }

    function refreshSelectionUi() {
        saveSelection();
        var count = selection.size;
        ["wo-mass-count", "wo-selection-count"].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) { el.textContent = count; }
        });
        var list = document.getElementById("wo-selection-list");
        if (list) {
            list.innerHTML = "";
            if (!count) {
                var empty = document.createElement("li");
                empty.className = "text-muted";
                empty.textContent = "Nada seleccionado todavía.";
                list.appendChild(empty);
            } else {
                Array.from(selection.values()).sort().forEach(function (label) {
                    var li = document.createElement("li");
                    li.textContent = label;
                    list.appendChild(li);
                });
            }
        }
        document.querySelectorAll(".wo-needs-selection").forEach(function (btn) {
            btn.disabled = count === 0;
        });
        var rows = rowChecks();
        rows.forEach(function (cb) { cb.checked = selection.has(cb.dataset.key); });
        var all = document.getElementById("wo-check-all");
        if (all) {
            var checked = rows.filter(function (cb) { return cb.checked; }).length;
            all.checked = rows.length > 0 && checked === rows.length;
            all.indeterminate = checked > 0 && checked < rows.length;
        }
        applyOnlySelected();
    }

    function submitBulk(op) {
        var form = document.createElement("form");
        form.method = "post";
        form.action = window.location.pathname;
        form.style.display = "none";
        var fields = {
            csrfmiddlewaretoken: (document.querySelector('meta[name="csrf-token"]') || {}).content || "",
            action: "bulk_action",
            active_tab: readJson("wo-active-tab", "pending"),
            back_url: readJson("wo-back-url", ""),
            bulk_op: op
        };
        Object.keys(fields).forEach(function (name) {
            var input = document.createElement("input");
            input.type = "hidden"; input.name = name; input.value = fields[name];
            form.appendChild(input);
        });
        selection.forEach(function (_label, key) {
            var input = document.createElement("input");
            input.type = "hidden"; input.name = "selected_pks"; input.value = key;
            form.appendChild(input);
        });
        // Hecha la acción, la selección se vacía (los partes cambian de
        // pestaña o desaparecen).
        selection.clear();
        saveSelection();
        if (window.EbNavState) { window.EbNavState.flush(); }
        document.body.appendChild(form);
        form.submit();
    }

    function initSelection() {
        screenKey = readJson("wo-screen-key", null);
        readJson("wo-saved-selection", []).forEach(function (item) {
            if (item && item.key) { selection.set(String(item.key), item.label || ""); }
        });

        document.addEventListener("change", function (e) {
            var target = e.target;
            if (target.classList.contains("wo-row-check")) {
                if (target.checked) { selection.set(target.dataset.key, target.dataset.label); }
                else { selection.delete(target.dataset.key); }
                refreshSelectionUi();
            } else if (target.id === "wo-check-all") {
                rowChecks().forEach(function (cb) {
                    if (cb.closest("tr").classList.contains("d-none")) { return; }
                    if (target.checked) { selection.set(cb.dataset.key, cb.dataset.label); }
                    else { selection.delete(cb.dataset.key); }
                });
                refreshSelectionUi();
            } else if (target.id === "wo-only-selected") {
                if (screenKey && window.EbNavState) {
                    window.EbNavState.save(screenKey, {only_selected: target.checked});
                }
                applyOnlySelected();
            }
        });

        var clear = document.getElementById("wo-mass-clear");
        if (clear) {
            clear.addEventListener("click", function () {
                selection.clear();
                refreshSelectionUi();
            });
        }

        document.querySelectorAll(".wo-bulk").forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (!selection.size) { return; }
                if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) { return; }
                btn.disabled = true;
                btn.insertAdjacentHTML("afterbegin", '<span class="spinner-border spinner-border-sm me-1"></span>');
                submitBulk(btn.dataset.op);
            });
        });

        var full = document.getElementById("wo-fullscreen");
        if (full) {
            full.addEventListener("click", function () {
                if (document.fullscreenElement) { document.exitFullscreen(); return; }
                var box = document.getElementById("wo-list-box");
                if (box && box.requestFullscreen) {
                    box.requestFullscreen().catch(function (err) {
                        console.warn("Pantalla completa no disponible:", err);
                    });
                }
            });
        }

        refreshSelectionUi();
    }

    window.WoHistory = {
        selectedKeys: function () { return Array.from(selection.keys()); }
    };

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
            if (!items.length) {
                dropdown.style.display = "none";
                /* Return dropdown to its original parent when hiding.
                   Devolver el dropdown a su padre original al ocultar. */
                if (dropdown.parentNode === document.body) {
                    var wrapper = input.closest(".filter-machine-wrapper");
                    if (wrapper) { wrapper.appendChild(dropdown); }
                }
                return;
            }
            items.forEach(function (code) {
                var li        = document.createElement("li");
                li.textContent = code;
                li.addEventListener("mousedown", function (e) {
                    e.preventDefault();
                    input.value = code;
                    dropdown.style.display = "none";
                    // S163: el filtro se aplica al elegir la máquina.
                    input.dispatchEvent(new Event("change", {bubbles: true}));
                    /* Return dropdown to wrapper on selection.
                       Devolver dropdown al wrapper al seleccionar. */
                    if (dropdown.parentNode === document.body) {
                        var wrapper = input.closest(".filter-machine-wrapper");
                        if (wrapper) { wrapper.appendChild(dropdown); }
                    }
                });
                dropdown.appendChild(li);
            });
            _active = -1;

            /* Detach dropdown to <body> to escape any overflow:hidden ancestor.
               Desanclar el dropdown al <body> para escapar de cualquier
               ancestro con overflow:hidden. */
            if (dropdown.parentNode !== document.body) {
                document.body.appendChild(dropdown);
            }

            /* Position dropdown below the input using fixed coords.
               Posicionar el dropdown bajo el input con coordenadas fixed. */
            var rect                = input.getBoundingClientRect();
            dropdown.style.position = "fixed";
            dropdown.style.top      = (rect.bottom + 2) + "px";
            dropdown.style.left     = rect.left + "px";
            dropdown.style.width    = rect.width + "px";
            dropdown.style.display  = "block";
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

    // ------------------------------------------------------------------
    // Date editor toggle — Apertura y cierre del editor inline de fecha.
    // Uses event delegation so it works after HTMX outerHTML swaps.
    // Usa delegación de eventos para funcionar tras swaps HTMX outerHTML.
    //
    // btn-date-edit-toggle: opens the form and hides the date text + pencil.
    // btn-date-cancel:      closes the form and restores the date text + pencil.
    // ------------------------------------------------------------------
    document.addEventListener("click", function (e) {

        // --- Open: pencil toggle button ---
        // --- Apertura: botón lápiz toggle ---
        var toggleBtn = e.target.closest(".btn-date-edit-toggle");
        if (toggleBtn) {
            var grp      = toggleBtn.closest(".page-group-header");
            var entryPk  = toggleBtn.id.replace("btn-date-toggle-", "");
            var form     = grp.querySelector("#form-date-" + entryPk);
            var dateText = grp.querySelector("#date-text-" + entryPk);
            if (dateText)  { dateText.style.display  = "none"; }
            toggleBtn.style.display = "none";
            if (form) {
                form.style.display = "inline-flex";
                var inp = form.querySelector("input[name=work_date]");
                if (inp) { inp.focus(); }
            }
            return;
        }

        // --- Cancel: close the editor and restore text + pencil ---
        // --- Cancelar: cerrar el editor y restaurar texto + lápiz ---
        var cancelBtn = e.target.closest(".btn-date-cancel");
        if (cancelBtn) {
            var entryPk  = cancelBtn.dataset.entryPk;
            var grp      = cancelBtn.closest(".page-group-header");
            var form     = grp.querySelector("#form-date-" + entryPk);
            var dateText = grp.querySelector("#date-text-" + entryPk);
            var toggleBtn = grp.querySelector("#btn-date-toggle-" + entryPk);
            if (form)      { form.style.display      = "none"; }
            if (dateText)  { dateText.style.display  = ""; }
            if (toggleBtn) { toggleBtn.style.display = ""; }
            return;
        }

    });

    // ------------------------------------------------------------------
    // Period filter shortcut — Atajo de filtro de periodo.
    // Snaps date_from/date_to to the start/end of an existing
    // WorkPeriodGroup (fixed 21-to-20 cycle) chosen from the dropdown --
    // gap flagged by Miguel Ángel 2026-07-21: date filters had no
    // relation to the periods already in use.
    // Ajusta date_from/date_to al inicio/fin de un WorkPeriodGroup
    // existente (ciclo fijo 21-al-20) elegido en el desplegable -- gap
    // señalado por Miguel Ángel 2026-07-21: los filtros de fecha no
    // tenían ninguna relación con los periodos ya en uso.
    // ------------------------------------------------------------------
    function initPeriodFilterShortcut() {
        var select   = document.getElementById("filter-period-select");
        var dateFrom = document.querySelector("[name='date_from']");
        var dateTo   = document.querySelector("[name='date_to']");
        if (!select || !dateFrom || !dateTo) { return; }
        select.addEventListener("change", function () {
            if (!select.value) { return; }
            var parts = select.value.split("|");
            dateFrom.value = parts[0];
            dateTo.value   = parts[1];
        });
    }

    // S163 (23/11, Miguel Ángel: el botón «Filtrar» daba más problemas
    // que otra cosa): cada filtro se aplica en cuanto cambia; el
    // buscador, al pulsar Intro o al dejar de escribir un momento.
    function initAutoFilter() {
        var form = document.getElementById("wo-filter-form");
        if (!form) { return; }
        var timer = null;
        function go() {
            if (timer) { clearTimeout(timer); timer = null; }
            if (window.EbNavState) { window.EbNavState.flush(); }
            form.submit();
        }
        form.addEventListener("change", function (e) {
            var el = e.target;
            if (el.id === "filter-period-select" && !el.value) { return; }
            if (el.name === "q") { return; }
            go();
        });
        var search = form.querySelector("[name='q']");
        if (search) {
            search.addEventListener("input", function () {
                if (timer) { clearTimeout(timer); }
                timer = setTimeout(go, 900);
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initSelection();
        initMachineAutocomplete();
        initPeriodFilterShortcut();
        initAutoFilter();
    });

}());
