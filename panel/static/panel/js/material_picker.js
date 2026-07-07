
// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/material_picker.js
/*
 * Modal de selección/alta rápida de repuesto para el campo "Material"
 * del formulario de parte (panel/operator/form_entry.html). Gap
 * señalado por Miguel Ángel (2026-07-07): al añadir un repuesto desde
 * el propio parte, en vez de escribirlo como texto libre, hay que
 * escogerlo del almacén digital o darlo de alta por la vía rápida --
 * sin salir del modal ni tener que guardar la tarea todavía (puede
 * estar incompleta).
 *
 * Vanilla JS + fetch(), mismo patrón que el resto de este formulario
 * (form_entry_assets.js, asset-search) -- no HTMX, este formulario no
 * lo usa en ningún otro punto.
 *
 * Por cada fila de repuesto (ridx dinámico, filas server-rendered o
 * añadidas por JS) existe un botón "Buscar repuesto" que abre este
 * modal (único, reutilizado) vía Bootstrap data-bs-toggle/target +
 * data-repuesto-idx. Al elegir un resultado o completar el alta
 * rápida, rellena:
 *   - input[name="repuesto_{ridx}_material"]  -> descripción
 *   - input[name="repuesto_{ridx}_spare_part_entry_pk"] (hidden) -> pk
 *   - input[name="repuesto_{ridx}_referencia"] -> referencia interna,
 *     solo si estaba vacío (no sobreescribe una ref. de proveedor ya
 *     escrita a mano).
 *
 * Si el mecánico edita el Material a mano después de elegir un
 * resultado, el hidden pk se limpia (evita que el backend vincule un
 * SparePartEntry que ya no corresponde al texto mostrado).
 *
 * ---
 *
 * Spare-part selection/quick-create modal for the "Material" field of
 * the work-order form. Gap flagged by Miguel Ángel (2026-07-07): when
 * a spare part is added from the work order itself, instead of typing
 * it as free text, it should be picked from the digital warehouse or
 * quick-registered -- without leaving the modal or having to save the
 * task yet (it may still be incomplete).
 */
(function () {
    "use strict";

    var CFG = window.EB_CONFIG || {};
    var SEARCH_URL       = CFG.materialSearchUrl      || "/panel/repuestos/materiales/buscar/";
    var QUICK_CREATE_URL = CFG.materialQuickCreateUrl || "/panel/repuestos/materiales/alta-rapida/";

    var _currentRidx = null;
    var _searchTimer = null;

    function _csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    function _rowFieldFor(ridx, suffix) {
        return document.querySelector('[name="repuesto_' + ridx + '_' + suffix + '"]');
    }

    /*
     * Ensures the hidden spare_part_entry_pk input exists for this
     * ridx (server-rendered rows don't have it yet -- added here on
     * first use), and returns it.
     * ---
     * Garantiza que exista el input oculto spare_part_entry_pk para
     * este ridx (las filas server-rendered todavía no lo tienen --
     * se añade aquí en el primer uso), y lo devuelve.
     */
    function _ensureHiddenPk(ridx) {
        var hidden = _rowFieldFor(ridx, "spare_part_entry_pk");
        if (hidden) { return hidden; }
        var materialInput = _rowFieldFor(ridx, "material");
        if (!materialInput) { return null; }
        hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "repuesto_" + ridx + "_spare_part_entry_pk";
        materialInput.insertAdjacentElement("afterend", hidden);
        return hidden;
    }

    /*
     * Clears the link (hidden pk) whenever the mechanic types by hand
     * in a Material input -- attached once per input via a data flag
     * to avoid duplicate listeners on rows re-scanned after HTMX/JS
     * mutations.
     * ---
     * Limpia el vínculo (pk oculto) en cuanto el mecánico escribe a
     * mano en un input Material -- se asocia una sola vez por input
     * mediante un flag de datos, para evitar listeners duplicados en
     * filas re-escaneadas tras mutaciones HTMX/JS.
     */
    function _watchMaterialInput(input) {
        if (input.dataset.materialWatchAttached === "1") { return; }
        input.dataset.materialWatchAttached = "1";
        input.addEventListener("input", function () {
            var ridxMatch = (input.name || "").match(/repuesto_(\d+)_material/);
            if (!ridxMatch) { return; }
            var hidden = _rowFieldFor(ridxMatch[1], "spare_part_entry_pk");
            if (hidden) { hidden.value = ""; }
        });
    }

    function _scanMaterialInputs() {
        document.querySelectorAll('input[name^="repuesto_"][name$="_material"]')
            .forEach(_watchMaterialInput);
    }

    function _resetModal() {
        var searchInput = document.getElementById("materialPickerSearchInput");
        var results      = document.getElementById("materialPickerResults");
        var qcForm        = document.getElementById("materialPickerQuickCreateForm");
        var qcToggleWrap  = document.getElementById("materialPickerQuickCreateToggleWrap");
        var qcError       = document.getElementById("materialPickerQcError");
        if (results) { results.innerHTML = ""; }
        if (qcForm) { qcForm.classList.add("d-none"); }
        if (qcToggleWrap) { qcToggleWrap.classList.add("d-none"); }
        if (qcError) { qcError.classList.add("d-none"); qcError.textContent = ""; }
        var qcDescription = document.getElementById("materialPickerQcDescription");
        var qcQuantity    = document.getElementById("materialPickerQcQuantity");
        var qcUncountable = document.getElementById("materialPickerQcUncountable");
        var qcLevel       = document.getElementById("materialPickerQcLevel");
        if (qcQuantity) { qcQuantity.value = ""; }
        if (qcUncountable) { qcUncountable.checked = false; }
        if (qcLevel) { qcLevel.value = ""; }
        if (qcDescription) { qcDescription.value = searchInput ? searchInput.value.trim() : ""; }
        _toggleQcCountableFields();
    }

    function _toggleQcCountableFields() {
        var uncountable   = document.getElementById("materialPickerQcUncountable");
        var quantityWrap  = document.getElementById("materialPickerQcQuantityWrap");
        var levelWrap     = document.getElementById("materialPickerQcLevelWrap");
        if (!uncountable || !quantityWrap || !levelWrap) { return; }
        var isUncountable = uncountable.checked;
        quantityWrap.classList.toggle("d-none", isUncountable);
        levelWrap.classList.toggle("d-none", !isUncountable);
    }

    function _applySelection(pk, description, internalReference) {
        if (_currentRidx == null) { return; }
        var materialInput = _rowFieldFor(_currentRidx, "material");
        var hidden         = _ensureHiddenPk(_currentRidx);
        var referenciaInput = _rowFieldFor(_currentRidx, "referencia");
        if (materialInput) { materialInput.value = description; }
        if (hidden) { hidden.value = pk; }
        if (referenciaInput && !referenciaInput.value.trim() && internalReference) {
            referenciaInput.value = internalReference;
        }
        var modalEl = document.getElementById("materialPickerModal");
        if (modalEl && window.bootstrap) {
            var instance = window.bootstrap.Modal.getOrCreateInstance(modalEl);
            instance.hide();
        }
    }

    function _renderResults(results) {
        var container = document.getElementById("materialPickerResults");
        var qcToggleWrap = document.getElementById("materialPickerQuickCreateToggleWrap");
        if (!container) { return; }
        container.innerHTML = "";
        if (!results || results.length === 0) {
            var q = (document.getElementById("materialPickerSearchInput") || {}).value || "";
            if (q.trim().length >= 2) {
                var empty = document.createElement("p");
                empty.className = "text-muted small mb-0";
                empty.textContent = 'Sin resultados para "' + q.trim() + '" en el almacén.';
                container.appendChild(empty);
            }
            if (qcToggleWrap) { qcToggleWrap.classList.toggle("d-none", q.trim().length < 2); }
            return;
        }
        if (qcToggleWrap) { qcToggleWrap.classList.remove("d-none"); }
        var list = document.createElement("div");
        list.className = "list-group";
        results.forEach(function (item) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "list-group-item list-group-item-action d-flex justify-content-between align-items-center";
            btn.innerHTML =
                "<span><strong>" + _escapeHtml(item.description) + "</strong>" +
                (item.internal_reference ? ' <code class="ms-1">' + _escapeHtml(item.internal_reference) + "</code>" : "") +
                "</span>" +
                '<span class="badge bg-secondary">' + _escapeHtml(String(item.stock_label)) + "</span>";
            btn.addEventListener("click", function () {
                _applySelection(item.pk, item.description, item.internal_reference);
            });
            list.appendChild(btn);
        });
        container.appendChild(list);
    }

    function _escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str == null ? "" : str;
        return div.innerHTML;
    }

    function _doSearch(q) {
        if (q.trim().length < 2) {
            _renderResults([]);
            return;
        }
        fetch(SEARCH_URL + "?q=" + encodeURIComponent(q.trim()))
            .then(function (r) { return r.json(); })
            .then(function (data) { _renderResults(data.results || []); })
            .catch(function () { _renderResults([]); });
    }

    function _submitQuickCreate() {
        var description   = (document.getElementById("materialPickerQcDescription") || {}).value || "";
        var uncountableEl  = document.getElementById("materialPickerQcUncountable");
        var quantityEl     = document.getElementById("materialPickerQcQuantity");
        var levelEl        = document.getElementById("materialPickerQcLevel");
        var errorEl        = document.getElementById("materialPickerQcError");
        var isUncountable  = !!(uncountableEl && uncountableEl.checked);

        if (errorEl) { errorEl.classList.add("d-none"); errorEl.textContent = ""; }

        var body = new URLSearchParams();
        body.set("description", description.trim());
        body.set("is_uncountable", isUncountable ? "1" : "");
        body.set("stock_quantity", quantityEl ? quantityEl.value : "");
        body.set("stock_level", levelEl ? levelEl.value : "");

        fetch(QUICK_CREATE_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": _csrfToken(),
            },
            body: body.toString(),
        })
            .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
            .then(function (res) {
                if (!res.ok) {
                    if (errorEl) {
                        errorEl.textContent = res.data.error || "No se ha podido dar de alta el repuesto.";
                        errorEl.classList.remove("d-none");
                    }
                    return;
                }
                _applySelection(res.data.pk, res.data.description, res.data.internal_reference);
            })
            .catch(function () {
                if (errorEl) {
                    errorEl.textContent = "Error de red al dar de alta el repuesto.";
                    errorEl.classList.remove("d-none");
                }
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var modalEl = document.getElementById("materialPickerModal");
        if (!modalEl) { return; }

        _scanMaterialInputs();
        // Re-scan periodically-ish via a MutationObserver would be
        // overkill here -- filas nuevas se anaden solo por
        // btn-add-repuesto/_buildRepuestoRow, que ya incluye el
        // boton "Buscar repuesto" con su propio listener delegado
        // (ver abajo), y el input Material de esa fila se vigila en
        // el propio momento de abrir el modal (_ensureHiddenPk +
        // _watchMaterialInput se llaman de nuevo ahi por seguridad).

        modalEl.addEventListener("show.bs.modal", function (event) {
            var btn = event.relatedTarget;
            _currentRidx = btn ? btn.getAttribute("data-repuesto-idx") : null;
            _scanMaterialInputs();
            _resetModal();
            var searchInput = document.getElementById("materialPickerSearchInput");
            if (searchInput && _currentRidx != null) {
                var materialInput = _rowFieldFor(_currentRidx, "material");
                searchInput.value = materialInput ? materialInput.value.trim() : "";
                if (searchInput.value) { _doSearch(searchInput.value); }
            }
        });

        modalEl.addEventListener("shown.bs.modal", function () {
            var searchInput = document.getElementById("materialPickerSearchInput");
            if (searchInput) { searchInput.focus(); }
        });

        var searchInput = document.getElementById("materialPickerSearchInput");
        if (searchInput) {
            searchInput.addEventListener("input", function () {
                clearTimeout(_searchTimer);
                var q = searchInput.value;
                _searchTimer = setTimeout(function () { _doSearch(q); }, 350);
            });
        }

        var qcToggle = document.getElementById("materialPickerQuickCreateToggle");
        if (qcToggle) {
            qcToggle.addEventListener("click", function () {
                var qcForm = document.getElementById("materialPickerQuickCreateForm");
                var qcDescription = document.getElementById("materialPickerQcDescription");
                var searchVal = (document.getElementById("materialPickerSearchInput") || {}).value || "";
                if (qcDescription && !qcDescription.value.trim()) { qcDescription.value = searchVal.trim(); }
                if (qcForm) { qcForm.classList.toggle("d-none"); }
            });
        }

        var qcUncountable = document.getElementById("materialPickerQcUncountable");
        if (qcUncountable) {
            qcUncountable.addEventListener("change", _toggleQcCountableFields);
        }

        var qcSubmit = document.getElementById("materialPickerQcSubmit");
        if (qcSubmit) {
            qcSubmit.addEventListener("click", _submitQuickCreate);
        }

        // Delegated listener: "Buscar repuesto" buttons open the
        // Bootstrap modal via data-bs-toggle/target already declared
        // in the HTML (server-rendered rows and _buildRepuestoRow-
        // generated rows alike) -- nothing extra to wire here beyond
        // Bootstrap's own attribute-driven behaviour. This listener
        // only exists to make sure newly-added rows' Material inputs
        // get the "clear pk on manual edit" watcher attached even if
        // the row was inserted after DOMContentLoaded.
        document.body.addEventListener("click", function (event) {
            if (event.target.closest && event.target.closest(".btn-material-search")) {
                _scanMaterialInputs();
            }
        });
    });
}());
