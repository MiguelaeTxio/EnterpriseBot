/*
 * form_entry_assets.js — Via A work-order form: asset autocomplete,
 * dynamic block/spare-part rows, meter-reading fields, client-side
 * integrity validation and description typeahead.
 *
 * form_entry_assets.js — Formulario Via A: autocompletado de activos,
 * filas dinámicas de bloque/repuesto, campos de contadores, validación
 * de integridad client-side y typeahead de descripciones.
 *
 * Requires window.EB_CONFIG.assetsUrl and window.EB_CONFIG.assetDetailUrl
 * to be set before this script loads (injected inline by the template).
 * Requiere que window.EB_CONFIG.assetsUrl y window.EB_CONFIG.assetDetailUrl
 * estén definidos antes de cargar este script (inyectados inline por el template).
 */
(function () {
    "use strict";

    var ASSETS_URL       = (window.EB_CONFIG && window.EB_CONFIG.assetsUrl)      || "";
    var ASSET_DETAIL_URL = (window.EB_CONFIG && window.EB_CONFIG.assetDetailUrl) || "";

    /*
     * Lunch break interval from the operator WorkdaySchedule.
     * Pre-filled by the server via window.EB_CONFIG. Empty strings when the
     * operator has an intensive shift or no schedule assigned.
     *
     * Intervalo de pausa de comida del WorkdaySchedule del operario.
     * Prerrellenado por el servidor via window.EB_CONFIG. Cadenas vacias
     * cuando el operario tiene jornada intensiva o no tiene horario asignado.
     */
    var LUNCH_BREAK_START = (window.EB_CONFIG && window.EB_CONFIG.lunchBreakStart) || "";
    var LUNCH_BREAK_END   = (window.EB_CONFIG && window.EB_CONFIG.lunchBreakEnd)   || "";

    /*
     * Reveals or hides meter-reading fields for the given block index.
     * Revela u oculta los campos de contadores para el índice de bloque dado.
     */
    function _applyMeterFields(blockIdx, data) {
        var sel     = '[data-block-idx="' + blockIdx + '"]';
        var odoEl   = document.querySelector('.meter-odometer' + sel);
        var engEl   = document.querySelector('.meter-engine'   + sel);
        var craneEl = document.querySelector('.meter-crane'    + sel);
        if (odoEl) {
            odoEl.classList.toggle("d-none", !data.has_odometer);
            var odoInput = odoEl.querySelector("input");
            if (odoInput && data.mileage != null) {
                odoInput.dataset.refValue = data.mileage;
                odoInput.value = data.mileage;
            }
        }
        if (engEl) {
            engEl.classList.toggle("d-none", !data.has_engine_hours);
            var engInput = engEl.querySelector("input");
            if (engInput && data.hours != null) {
                engInput.dataset.refValue = data.hours;
                engInput.value = data.hours;
            }
        }
        if (craneEl) {
            craneEl.classList.toggle("d-none", !data.has_crane_hours);
            var craneInput = craneEl.querySelector("input");
            if (craneInput && data.hours != null) {
                craneInput.dataset.refValue = data.hours;
                craneInput.value = data.hours;
            }
        }
    }

    /*
     * Debounce helper: delays execution until after 'wait' ms have elapsed
     * since the last call. Prevents excessive API requests while typing.
     *
     * Helper debounce: retrasa la ejecucion hasta que transcurran 'wait' ms
     * desde la ultima llamada. Evita peticiones API excesivas al escribir.
     */
    function debounce(fn, wait) {
        var timer;
        return function () {
            var ctx  = this;
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(ctx, args); }, wait);
        };
    }

    /*
     * Attaches autocomplete behaviour to a single asset-search input.
     *
     * Asocia comportamiento de autocompletado a un unico input asset-search.
     */
    function attachAutocomplete(input) {
        var dropdown = input.parentElement.querySelector(".asset-dropdown");
        if (!dropdown) { return; }

        var lastQuery  = "";
        /* Guard flag: true while the user is pressing a dropdown option.
           Bandera de guardia: true mientras el usuario pulsa una opcion del dropdown.
           Prevents blur from hiding the dropdown before pointerdown writes the value,
           which on mobile (Android/iOS) fires in a different order than on desktop. */
        var _selecting = false;

        function _hideDropdown() {
            dropdown.classList.add("d-none");
            dropdown.innerHTML = "";
        }

        function fetchAndRender(q) {
            if (q === lastQuery) { return; }
            lastQuery = q;
            fetch(ASSETS_URL + "?q=" + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    dropdown.innerHTML = "";
                    if (!data.assets || data.assets.length === 0) {
                        dropdown.classList.add("d-none");
                        return;
                    }
                    data.assets.forEach(function (asset) {
                        var btn = document.createElement("button");
                        btn.type      = "button";
                        btn.className = "list-group-item list-group-item-action text-sm py-1 px-2";
                        btn.textContent = asset.code + " — " + asset.brand_model;

                        /* pointerdown fires before blur on all platforms including
                           Android Chrome — set guard so blur does not close dropdown
                           before the selection is committed.
                           pointerdown se dispara antes que blur en todas las plataformas
                           incluido Android Chrome — la guardia evita que blur cierre el
                           dropdown antes de que se confirme la seleccion. */
                        btn.addEventListener("pointerdown", function (e) {
                            e.preventDefault();
                            _selecting = true;
                        });
                        btn.addEventListener("click", function () {
                            input.value = asset.code;
                            lastQuery   = asset.code;
                            _selecting  = false;
                            _hideDropdown();
                            input.focus();
                            // Reveal/hide meter fields for this block after asset selection.
                            // Revelar/ocultar campos de contadores del bloque tras seleccionar activo.
                            var blockDiv = input.closest('[id^="block-"]');
                            if (blockDiv) {
                                var bIdx = (blockDiv.id || "").replace("block-", "");
                                if (bIdx) {
                                    fetch(ASSET_DETAIL_URL + "?code=" + encodeURIComponent(asset.code))
                                        .then(function (r) { return r.json(); })
                                        .then(function (d) { _applyMeterFields(bIdx, d); })
                                        .catch(function () {
                                            _applyMeterFields(bIdx, {has_odometer: false, has_engine_hours: false, has_crane_hours: false});
                                        });
                                }
                            }
                        });
                        dropdown.appendChild(btn);
                    });
                    dropdown.classList.remove("d-none");
                })
                .catch(function () { dropdown.classList.add("d-none"); });
        }

        var debouncedFetch = debounce(function () {
            var q = input.value.trim();
            if (q.length === 0) { dropdown.classList.add("d-none"); return; }
            fetchAndRender(q);
        }, 250);

        input.addEventListener("input", debouncedFetch);
        input.addEventListener("blur",  function () {
            /* Only hide if the user is NOT in the middle of selecting an option.
               Solo ocultar si el usuario NO esta en proceso de seleccionar una opcion. */
            if (!_selecting) {
                setTimeout(_hideDropdown, 200);
            }
        });
        input.addEventListener("focus", function () {
            if (input.value.trim().length > 0) { fetchAndRender(input.value.trim()); }
        });
    }

    // ==================================================================
    // CdG select logic — show/hide free-text input for "Otro" and refresh
    // all CdG selects when any machine_raw block value changes.
    // Lógica select CdG — mostrar/ocultar input libre para "Otro" y refrescar
    // todos los selects CdG cuando cambia cualquier machine_raw de bloque.
    // ==================================================================

    function _toggleOtroForm(ridx) {
        /*
         * Shows the free-text input when "__otro__" is selected.
         * Hides it otherwise.
         *
         * Muestra el input libre cuando se selecciona "__otro__".
         * Lo oculta en caso contrario.
         */
        var sel      = document.querySelector('[name="repuesto_' + ridx + '_vehiculo_raw"]');
        var libInput = document.querySelector('[name="repuesto_' + ridx + '_cdg_free"]');
        if (sel.value === "__otro__") {
            if (libInput) { libInput.classList.remove("d-none"); libInput.focus(); }
        } else {
            if (libInput) { libInput.classList.add("d-none"); }
        }
    }

    function _refreshCdgSelects() {
        /*
         * Rebuilds the options of every .repuesto-cdg-select from the current
         * unique non-empty machine_raw values present in the form blocks.
         * Preserves the current selection when the value still exists.
         * The last block machine_raw is the default for new selects.
         *
         * Reconstruye las opciones de cada .repuesto-cdg-select desde los
         * valores machine_raw únicos no vacíos de los bloques del formulario.
         * Preserva la selección actual si el valor sigue existiendo.
         * El machine_raw del último bloque es el valor por defecto.
         */
        var seen = [];
        var lastVal = "";
        document.querySelectorAll('.confirm-block [name$="_machine_raw"]').forEach(function (inp) {
            var v = inp.value.trim();
            if (v && seen.indexOf(v) === -1) { seen.push(v); lastVal = v; }
        });
        document.querySelectorAll(".repuesto-cdg-select").forEach(function (sel) {
            var current = sel.value;
            sel.innerHTML = "";
            seen.forEach(function (v) {
                var opt = document.createElement("option");
                opt.value       = v;
                opt.textContent = v;
                sel.appendChild(opt);
            });
            var otro = document.createElement("option");
            otro.value       = "__otro__";
            otro.textContent = "Otro — introducir CdG manualmente";
            if (current === "__otro__") { otro.selected = true; }
            sel.appendChild(otro);
        });
    }

    document.addEventListener("change", function (e) {
        if (e.target && e.target.classList.contains("repuesto-cdg-select")) {
            var ridx = e.target.dataset.repuestoIdx
                || (e.target.name.match(/repuesto_(\d+)_vehiculo_raw/) || [])[1];
            if (ridx) { _toggleOtroForm(ridx); }
        }
    });

    document.addEventListener("input", function (e) {
        if (e.target && e.target.name && /^entrada_\d+_machine_raw$/.test(e.target.name)) {
            _refreshCdgSelects();
        }
    });

    window._refreshCdgSelects = _refreshCdgSelects;

    // Attach autocomplete to all pre-rendered inputs.
    // Asociar autocompletado a todos los inputs pre-renderizados.
    document.querySelectorAll(".asset-search").forEach(attachAutocomplete);

    // On page load, reveal meter fields for any block that already has a
    // machine_raw value (server re-render after validation error).
    // Al cargar la página, revelar campos de contador para cualquier bloque
    // que ya tenga machine_raw (re-renderizado tras error de validación).
    document.querySelectorAll(".asset-search").forEach(function (input) {
        var code = input.value.trim();
        if (!code) { return; }
        var blockDiv = input.closest('[id^="block-"]');
        var bIdx = (blockDiv.id || "").replace("block-", "");
        fetch(ASSET_DETAIL_URL + "?code=" + encodeURIComponent(code))
            .then(function (r) { return r.json(); })
            .then(function (d) { _applyMeterFields(bIdx, d); })
            .catch(function () {
                _applyMeterFields(bIdx, {
                    has_odometer: false, has_engine_hours: false,
                    has_crane_hours: false, first_repair: false,
                    mileage: null, hours: null
                });
            });
    });

    // ==================================================================
    // Block counter / Contador de bloques
    // ==================================================================
    var numEntradasInput  = document.getElementById("num-entradas-input");
    var numRepuestosInput = document.getElementById("num-repuestos-input");
    var extraBlocksCont   = document.getElementById("extra-blocks-container");
    var extraRepCont      = document.getElementById("extra-repuestos-container");
    var btnAddBlock       = document.getElementById("btn-add-block");
    var btnAddRepuesto    = document.getElementById("btn-add-repuesto");
    var noRepuestosMsg    = document.getElementById("no-repuestos-msg");

    /*
     * Returns the current total number of rendered work blocks (both
     * server-rendered and dynamically added).
     *
     * Devuelve el numero total actual de bloques de trabajo renderizados
     * (tanto del servidor como anadidos dinamicamente).
     */
    function _currentBlockCount() {
        return parseInt(numEntradasInput.value, 10) || 1;
    }

    /*
     * Builds a work-block DOM node for the given idx.
     * Mirrors the field names expected by WorkOrderEntryFormView.post().
     *
     * Construye un nodo DOM de bloque de trabajo para el idx dado.
     * Replica los nombres de campo esperados por WorkOrderEntryFormView.post().
     */
    function _buildBlockRow(idx) {
        var div = document.createElement("div");
        div.className = "confirm-block mb-4 pb-4 border-bottom extra-block-row";
        div.id = "block-" + idx;
        div.innerHTML =
            '<div class="d-flex align-items-center gap-2 mb-3">' +
                '<span class="badge bg-dark">Tarea ' + idx + '</span>' +
                '<button type="button" class="btn btn-link btn-sm text-danger p-0 ms-2 btn-remove-block">' +
                    '<i class="bi bi-trash"></i> Eliminar bloque' +
                '</button>' +
            '</div>' +
            '<div class="row g-3">' +
                '<div class="col-12 col-md-4">' +
                    '<label class="form-label fw-medium">Máquina o Sección <span class="text-danger">*</span></label>' +
                    '<div class="position-relative">' +
                        '<input type="text" name="entrada_' + idx + '_machine_raw" ' +
                               'class="form-control asset-search" ' +
                               'placeholder="Código de máquina" autocomplete="off">' +
                        '<div class="asset-dropdown d-none list-group mt-1 confirm-dropdown"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="col-6 col-md-2">' +
                    '<label class="form-label fw-medium">H.C. <span class="text-danger">*</span></label>' +
                    '<input type="time" step="1800" name="entrada_' + idx + '_hc" class="form-control">' +
                '</div>' +
                '<div class="col-6 col-md-2">' +
                    '<label class="form-label fw-medium">H.F. <span class="text-danger">*</span></label>' +
                    '<input type="time" step="1800" name="entrada_' + idx + '_hf" class="form-control">' +
                '</div>' +
                '<div class="col-12 col-md-4">' +
                    '<label class="form-label fw-medium">O.R.</label>' +
                    '<input type="text" name="entrada_' + idx + '_or_val" ' +
                           'class="form-control field-optional" placeholder="Referencia O.R. (opcional)">' +
                '</div>' +
                // Meter readings — ocultos por defecto, revelados por _applyMeterFields().
                '<div class="col-12 col-md-3 meter-field meter-odometer d-none" data-block-idx="' + idx + '">' +
                    '<label class="form-label fw-medium">Km actuales <span class=\"text-danger meter-required\">*</span></label>' +
                    '<input type="number" step="0.1" min="0" name="entrada_' + idx + '_odometer_reading" class="form-control horometro-input" placeholder="Lectura km">' +
                '</div>' +
                '<div class="col-12 col-md-3 meter-field meter-engine d-none" data-block-idx="' + idx + '">' +
                    '<label class="form-label fw-medium">Horómetro motor (h) <span class=\"text-danger meter-required\">*</span></label>' +
                    '<input type="number" step="0.1" min="0" name="entrada_' + idx + '_engine_hours_reading" class="form-control horometro-input" placeholder="Horas motor">' +
                '</div>' +
                '<div class="col-12 col-md-3 meter-field meter-crane d-none" data-block-idx="' + idx + '">' +
                    '<label class="form-label fw-medium">Horómetro grúa (h) <span class=\"text-danger meter-required\">*</span></label>' +
                    '<input type="number" step="0.1" min="0" name="entrada_' + idx + '_crane_hours_reading" class="form-control horometro-input" placeholder="Horas grúa">' +
                '</div>' +
                '<div class="col-12 col-md-6">' +
                    '<label class="form-label fw-medium">Descripción avería <span class="text-danger">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_fault_description" ' +
                              'class="form-control desc-search" rows="3" ' +
                              'data-desc-field="fault_description" ' +
                              'placeholder="Descripción de la avería o tarea"></textarea>' +
                '</div>' +
                '<div class="col-12 col-md-6">' +
                    '<label class="form-label fw-medium">Reparación realizada <span class=\"text-danger\">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_repair_notes" ' +
                              'class="form-control desc-search field-flagged" rows="3" ' +
                              'data-desc-field="repair_notes" ' +
                              'placeholder="Descripción de la reparación"></textarea>' +
                '</div>' +
            '</div>';
        return div;
    }

    /*
     * Builds a spare-part row DOM node for the given ridx.
     *
     * Construye un nodo DOM de fila de repuesto para el ridx dado.
     */
    function _buildRepuestoRow(ridx) {
        /*
         * Builds a spare-part row DOM node for the given ridx.
         * Structure mirrors the S012 server-rendered static HTML and stt_entry.html:
         *   'asignado a' + select[name="repuesto_N_vehiculo_raw"] .repuesto-cdg-select
         *   with options built from unique machine_raw values currently in the form,
         *   plus an "Otro" option that reveals the free-text input cdg_free.
         *
         * Construye un nodo DOM de fila de repuesto para el ridx dado.
         * La estructura replica el HTML estático server-rendered de S012 y stt_entry.html:
         *   'asignado a' + select[name="repuesto_N_vehiculo_raw"] .repuesto-cdg-select
         *   con opciones construidas desde los machine_raw únicos presentes en el formulario,
         *   más una opción "Otro" que revela el input libre cdg_free.
         */
        var div = document.createElement("div");
        div.className = "confirm-block mb-4 pb-4 border-bottom extra-repuesto-row";
        div.innerHTML =
            '<div class="d-flex align-items-center gap-2 mb-3 flex-wrap">' +
                '<span class="badge bg-secondary">Repuesto ' + ridx + '</span>' +
                '<span class="text-muted small">asignado a</span>' +
                '<select name="repuesto_' + ridx + '_vehiculo_raw" ' +
                        'class="form-select form-select-sm repuesto-cdg-select w-auto" ' +
                        'data-repuesto-idx="' + ridx + '">' +
                    _buildCdgOptions() +
                '</select>' +
                // Input de texto libre para CdG manual (visible solo cuando se selecciona "Otro").
                // Free-text input for manual CdG (visible only when "Otro" is selected).
                '<input type="text" ' +
                       'name="repuesto_' + ridx + '_cdg_free" ' +
                       'class="form-control form-control-sm repuesto-cg-libre d-none mt-1 cg-libre-input" ' +
                       'placeholder="Código o nombre del CdG">' +
                '<button type="button" class="btn btn-link btn-sm text-danger p-0 ms-auto btn-remove-repuesto">' +
                    '<i class="bi bi-trash"></i> Eliminar' +
                '</button>' +
            '</div>' +
            '<div class="row g-3">' +
                '<div class="col-12 col-md-3">' +
                    '<label class="form-label fw-medium">Referencia</label>' +
                    '<input type="text" name="repuesto_' + ridx + '_referencia" ' +
                           'class="form-control" placeholder="Ref. albaran">' +
                '</div>' +
                '<div class="col-12 col-md-4">' +
                    '<label class="form-label fw-medium">Material <span class="text-danger">*</span></label>' +
                    '<input type="text" name="repuesto_' + ridx + '_material" ' +
                           'class="form-control" placeholder="Descripción del material">' +
                '</div>' +
                '<div class="col-6 col-md-2">' +
                    '<label class="form-label fw-medium">Unidades <span class="text-danger">*</span></label>' +
                    '<input type="text" name="repuesto_' + ridx + '_unidades" ' +
                           'class="form-control" placeholder="Cantidad">' +
                '</div>' +
                '<div class="col-12 col-md-3">' +
                    '<label class="form-label fw-medium">Procedencia</label>' +
                    '<select name="repuesto_' + ridx + '_origen" class="form-select">' +
                        '<option value="WAREHOUSE">Almacen</option>' +
                        '<option value="SUPPLIER">Proveedor</option>' +
                    '</select>' +
                '</div>' +
                '<div class="col-12 col-md-4">' +
                    '<label class="form-label fw-medium">Proveedor</label>' +
                    '<input type="text" name="repuesto_' + ridx + '_proveedor" ' +
                           'class="form-control" placeholder="Nombre proveedor (si aplica)">' +
                '</div>' +
            '</div>';
        return div;
    }

    function _buildCdgOptions() {
        /*
         * Reads unique non-empty machine_raw values from current work blocks
         * and builds <option> elements. The last value is selected by default.
         * Appends the "Otro" option for free-text CdG entry.
         *
         * Lee los valores machine_raw únicos no vacíos de los bloques de trabajo
         * actuales y construye los elementos <option>. El último valor se selecciona
         * por defecto. Añade la opción "Otro" para entrada de CdG libre.
         */
        var seen    = [];
        var lastVal = "";
        document.querySelectorAll('.confirm-block [name$="_machine_raw"]').forEach(function (inp) {
            var v = inp.value.trim();
            if (v && seen.indexOf(v) === -1) { seen.push(v); lastVal = v; }
        });
        var opts = "";
        seen.forEach(function (v) {
            var sel = (v === lastVal) ? ' selected' : '';
            opts += '<option value="' + v + '"' + sel + '>' + v + '</option>';
        });
        opts += '<option value="__otro__">Otro — introducir CdG manualmente</option>';
        return opts || '<option value="__otro__">Otro — introducir CdG manualmente</option>';
    }

    // -- Add block handler / Manejador anadir bloque --
    if (btnAddBlock) {
        btnAddBlock.addEventListener("click", function () {
            var current = parseInt(numEntradasInput.value, 10) || 1;
            var nextIdx = current + 1;
            numEntradasInput.value = nextIdx;
            var row = _buildBlockRow(nextIdx);
            extraBlocksCont.appendChild(row);
            // Attach autocomplete to new input.
            // Asociar autocompletado al nuevo input.
            var newInput = row.querySelector(".asset-search");
            if (newInput) { attachAutocomplete(newInput); }
            // Attach description typeahead to the two new desc-search textareas.
            // Asociar typeahead de descripcion a los dos nuevos textarea desc-search.
            row.querySelectorAll(".desc-search").forEach(function (ta) {
                if (window.DescTypeahead) { DescTypeahead.init(ta); }
            });
            // Remove handler / Manejador de eliminacion.
            var btnRemove = row.querySelector(".btn-remove-block");
            if (btnRemove) {
                btnRemove.addEventListener("click", function () {
                    extraBlocksCont.removeChild(row);
                    numEntradasInput.value = parseInt(numEntradasInput.value, 10) - 1;
                });
            }
        });
    }

    // -- Add repuesto handler / Manejador anadir repuesto --
    if (btnAddRepuesto) {
        btnAddRepuesto.addEventListener("click", function () {
            var current = parseInt(numRepuestosInput.value, 10) || 0;
            var nextIdx = current + 1;
            numRepuestosInput.value = nextIdx;
            var row = _buildRepuestoRow(nextIdx);
            extraRepCont.appendChild(row);
            if (noRepuestosMsg) { noRepuestosMsg.classList.add("d-none"); }
            // Attach autocomplete / Asociar autocompletado.
            var newInput = row.querySelector(".asset-search");
            if (newInput) { attachAutocomplete(newInput); }
            // Attach Centro de Gasto sync to the new repuesto select.
            // Asociar sincronización Centro de Gasto al nuevo select de repuesto.
            var newSel = row.querySelector(".repuesto-entry-select");
            if (newSel && window._attachEntrySelectListener) {
                _attachEntrySelectListener(newSel);
                var newRidx = newSel.dataset.repuestoIdx
                    || (newSel.name.match(/repuesto_(\d+)_entry_idx/) || [])[1];
                if (newRidx && window._syncCentroGasto) { _syncCentroGasto(newRidx); }
            }
            // Remove handler / Manejador de eliminacion.
            var btnRemove = row.querySelector(".btn-remove-repuesto");
            if (btnRemove) {
                btnRemove.addEventListener("click", function () {
                    extraRepCont.removeChild(row);
                    numRepuestosInput.value = parseInt(numRepuestosInput.value, 10) - 1;
                    var remaining = extraRepCont.querySelectorAll(".extra-repuesto-row");
                    if (noRepuestosMsg && remaining.length === 0) {
                        noRepuestosMsg.classList.remove("d-none");
                    }
                });
            }
        });
    }

    // ==================================================================
    // Client-side integrity validation / Validacion de integridad client-side
    // ==================================================================
    var form      = document.getElementById("form-entry");
    var alertBox  = document.getElementById("integrity-alert");
    var alertText = document.getElementById("integrity-alert-text");
    var btnSubmit = document.getElementById("btn-form-submit");

    function _val(name) {
        var el = form ? form.querySelector('[name="' + name + '"]') : null;
        return el ? el.value.trim() : "";
    }

    function _showAlert(msg) {
        if (!alertBox || !alertText) { return; }
        alertText.textContent = msg;
        alertBox.classList.remove("d-none");
        alertBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function _clearAlert() {
        if (!alertBox || !alertText) { return; }
        alertBox.classList.add("d-none");
        alertText.textContent = "";
    }

    function _markField(name, bad) {
        var el = form ? form.querySelector('[name="' + name + '"]') : null;
        if (!el) { return; }
        if (bad) { el.classList.add("field-flagged"); }
        else     { el.classList.remove("field-flagged"); }
    }

    if (form && btnSubmit) {
        form.addEventListener("submit", function (e) {
            _clearAlert();
            var errors = [];

            // Gate 1 — Date / Fecha.
            // type="date" always delivers YYYY-MM-DD or empty string.
            // type="date" entrega siempre YYYY-MM-DD o cadena vacía.
            var fecha = _val("fecha");
            _markField("fecha", !fecha);
            if (!fecha) { errors.push("La fecha del parte es obligatoria (selecciona una fecha)."); }

            // Gate 2 — Work blocks / Bloques de trabajo.
            var numEntradas = parseInt(_val("num_entradas"), 10) || 1;
            /*
             * _lunchOverlapMinutes — computes the overlap in minutes between
             * a work block [hc, hf] and the lunch break [lunchStart, lunchEnd].
             * All params are "HH:MM" strings. Returns 0 if any param is empty
             * or there is no overlap.
             *
             * _lunchOverlapMinutes — calcula el solapamiento en minutos entre
             * un bloque de trabajo [hc, hf] y la pausa de comida [lunchStart, lunchEnd].
             * Todos los parametros son cadenas "HH:MM". Devuelve 0 si algun parametro
             * esta vacio o no hay solapamiento.
             */
            function _lunchOverlapMinutes(hc, hf, lunchStart, lunchEnd) {
                if (!hc || !hf || !lunchStart || !lunchEnd) { return 0; }
                function _toMin(t) {
                    var parts = t.split(":");
                    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
                }
                var blockStart  = _toMin(hc);
                var blockEnd    = _toMin(hf);
                var lunchS      = _toMin(lunchStart);
                var lunchE      = _toMin(lunchEnd);
                var overlapStart = Math.max(blockStart, lunchS);
                var overlapEnd   = Math.min(blockEnd,   lunchE);
                return Math.max(0, overlapEnd - overlapStart);
            }

            /* Read lunch break from form fields (operator may have modified them). */
            /* Leer pausa de comida desde los campos del formulario (el operario pudo modificarlos). */
            /*
             * no_lunch_break: when checked, lunch overlap is forced to 0
             * and the backend skips Gate 4 LUNCH_BREAK detection.
             * no_lunch_break: cuando marcado, el solapamiento de comida es 0
             * y el backend omite la deteccion de LUNCH_BREAK en Gate 4.
             */
            var noLunchEl  = document.getElementById("id_no_lunch_break_value");
            var noLunch    = noLunchEl && noLunchEl.value === "1";
            var lunchStart = noLunch ? "" : (_val("lunch_break_start") || LUNCH_BREAK_START);
            var lunchEnd   = noLunch ? "" : (_val("lunch_break_end")   || LUNCH_BREAK_END);

            for (var i = 1; i <= numEntradas; i++) {
                var blk  = "Bloque " + i;
                var maq  = _val("entrada_" + i + "_machine_raw");
                var hc   = _val("entrada_" + i + "_hc");
                var hf   = _val("entrada_" + i + "_hf");
                var desc = _val("entrada_" + i + "_fault_description");

                _markField("entrada_" + i + "_machine_raw",        !maq);
                _markField("entrada_" + i + "_hc",                 !hc);
                _markField("entrada_" + i + "_hf",                 !hf);
                _markField("entrada_" + i + "_fault_description", !desc);

                if (!maq)  { errors.push(blk + ": codigo de maquina obligatorio."); }
                if (!hc)   { errors.push(blk + ": H.C. obligatoria."); }
                if (!hf)   { errors.push(blk + ": H.F. obligatoria."); }
                if (!desc) { errors.push(blk + ": descripcion de averia obligatoria."); }
                var rep_notes = _val("entrada_" + i + "_repair_notes");
                _markField("entrada_" + i + "_repair_notes", !rep_notes);
                if (!rep_notes) { errors.push(blk + ": descripcion de reparacion obligatoria."); }
                if (hc && hf && hf <= hc) {
                    _markField("entrada_" + i + "_hf", true);
                    errors.push(blk + ": H.F. debe ser posterior a H.C.");
                }

                /*
                 * Compute lunch overlap for this block and store in a hidden input
                 * so the backend can apply the exact deduction per line.
                 *
                 * Calcular el solapamiento de comida para este bloque y almacenarlo
                 * en un input oculto para que el backend aplique el descuento exacto.
                 */
                var overlapMin = _lunchOverlapMinutes(hc, hf, lunchStart, lunchEnd);
                var overlapId  = "lunch_overlap_" + i;
                var overlapEl  = document.getElementById(overlapId);
                if (!overlapEl) {
                    overlapEl      = document.createElement("input");
                    overlapEl.type = "hidden";
                    overlapEl.id   = overlapId;
                    overlapEl.name = "lunch_overlap_" + i;
                    document.getElementById("form-entry").appendChild(overlapEl);
                }
                overlapEl.value = overlapMin;
            }

            // Gate 3 — Spare parts / Repuestos.
            var numRepuestos = parseInt(_val("num_repuestos"), 10) || 0;
            for (var r = 1; r <= numRepuestos; r++) {
                var rep      = "Repuesto " + r;
                var material = _val("repuesto_" + r + "_material");
                var unidades = _val("repuesto_" + r + "_unidades");
                var qty      = parseFloat(unidades.replace(",", "."));

                _markField("repuesto_" + r + "_material", !material);
                _markField("repuesto_" + r + "_unidades", !unidades || isNaN(qty) || qty <= 0);

                if (!material) { errors.push(rep + ": descripcion de material obligatoria."); }
                if (!unidades || isNaN(qty) || qty <= 0) {
                    errors.push(rep + ": unidades deben ser un numero positivo.");
                }
            }

            if (errors.length > 0) {
                e.preventDefault();
                _showAlert(errors.join(" | "));
            }
        });
    }

    // ==================================================================
    // No-lunch-break toggle / Toggle sin pausa de comida
    // Only present in split-shift mode (when #lunch-break-times exists).
    // Solo en jornada partida (cuando existe #lunch-break-times).
    // ==================================================================
    var noLunchToggle  = document.getElementById("id_no_lunch_toggle");
    var noLunchHidden  = document.getElementById("id_no_lunch_break_value");
    var lunchTimesDiv  = document.getElementById("lunch-break-times");
    var lbStartInput   = document.getElementById("id_lunch_break_start");
    var lbEndInput     = document.getElementById("id_lunch_break_end");

    if (noLunchToggle && noLunchHidden && lunchTimesDiv) {
        noLunchToggle.addEventListener("change", function () {
            if (noLunchToggle.checked) {
                lunchTimesDiv.classList.add("d-none");
                noLunchHidden.value = "1";
                if (lbStartInput) { lbStartInput.value = ""; }
                if (lbEndInput)   { lbEndInput.value   = ""; }
            } else {
                lunchTimesDiv.classList.remove("d-none");
                noLunchHidden.value = "0";
                if (lbStartInput && window.EB_CONFIG && window.EB_CONFIG.lunchBreakStart) {
                    lbStartInput.value = window.EB_CONFIG.lunchBreakStart;
                }
                if (lbEndInput && window.EB_CONFIG && window.EB_CONFIG.lunchBreakEnd) {
                    lbEndInput.value = window.EB_CONFIG.lunchBreakEnd;
                }
            }
        });
    }

    // Progressive save: "Guardar bloques" button.
    // Guardado progresivo: boton Guardar bloques.
    var btnSaveBlocks   = document.getElementById("btn-save-blocks");
    var formActionInput = document.getElementById("form-action-input");

    if (btnSaveBlocks && formActionInput && form) {
        btnSaveBlocks.addEventListener("click", function () {
            _clearAlert();
            var sbErrors = [];
            var sbNum = parseInt(_val("num_entradas"), 10) || 1;
            var sbFecha = _val("fecha");
            if (!sbFecha) {
                _showAlert("La fecha del parte es obligatoria antes de guardar bloques.");
                return;
            }
            for (var sb = 1; sb <= sbNum; sb++) {
                var sbLabel = "Bloque " + sb;
                var sbMaq   = _val("entrada_" + sb + "_machine_raw");
                var sbHc    = _val("entrada_" + sb + "_hc");
                var sbHf    = _val("entrada_" + sb + "_hf");
                var sbDesc  = _val("entrada_" + sb + "_fault_description");
                var sbNotes = _val("entrada_" + sb + "_repair_notes");
                _markField("entrada_" + sb + "_machine_raw",       !sbMaq);
                _markField("entrada_" + sb + "_hc",                !sbHc);
                _markField("entrada_" + sb + "_hf",                !sbHf);
                _markField("entrada_" + sb + "_fault_description", !sbDesc);
                _markField("entrada_" + sb + "_repair_notes",      !sbNotes);
                if (!sbMaq)   { sbErrors.push(sbLabel + ": codigo de maquina obligatorio."); }
                if (!sbHc)    { sbErrors.push(sbLabel + ": H.C. obligatoria."); }
                if (!sbHf)    { sbErrors.push(sbLabel + ": H.F. obligatoria."); }
                if (!sbDesc)  { sbErrors.push(sbLabel + ": descripcion de averia obligatoria."); }
                if (!sbNotes) { sbErrors.push(sbLabel + ": descripcion de reparacion obligatoria."); }
                if (sbHc && sbHf && sbHf <= sbHc) {
                    _markField("entrada_" + sb + "_hf", true);
                    sbErrors.push(sbLabel + ": H.F. debe ser posterior a H.C.");
                }
            }
            if (sbErrors.length > 0) {
                _showAlert(sbErrors.join(" | "));
                return;
            }
            formActionInput.value = "save_blocks";
            form.submit();
        });
    }

    if (formActionInput) {
        formActionInput.value = "close_order";
    }

}());
