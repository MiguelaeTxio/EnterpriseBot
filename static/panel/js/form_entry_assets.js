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
            if (q !== input.value.trim()) { lastQuery = ""; }
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
                        var plate = asset.plate ? " (" + asset.plate + ")" : "";
                        btn.textContent = asset.code + " — " + asset.brand_model + plate;

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
                            var blockDiv = input.closest('[id^="block-"]');
                            if (blockDiv) {
                                var bIdx = (blockDiv.id || "").replace("block-", "");
                                if (bIdx) {
                                    var isPersonal = asset.code === EB_CONFIG.personalAssetCode;
                                    _toggleAbsenceMode(bIdx, isPersonal);
                                    if (!isPersonal) {
                                        fetch(ASSET_DETAIL_URL + "?code=" + encodeURIComponent(asset.code))
                                            .then(function (r) { return r.json(); })
                                            .then(function (d) { _applyMeterFields(bIdx, d); })
                                            .catch(function () {
                                                _applyMeterFields(bIdx, {has_odometer: false, has_engine_hours: false, has_crane_hours: false});
                                            });
                                    }
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
            if (q.length < 2) { dropdown.classList.add("d-none"); return; }
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
    // _toggleAbsenceMode
    // Switches a work block between repair mode and absence mode.
    // When isPersonal=true: hides fault_description, shows absence
    // category selector. Adjusts repair_notes based on requires_note.
    //
    // Alterna un bloque entre modo reparación y modo ausencia.
    // Con isPersonal=true: oculta fault_description, muestra selector
    // de categoría. Ajusta repair_notes según requires_note.
    // ==================================================================
    function _toggleAbsenceMode(idx, isPersonal) {
        var absWrap    = document.getElementById('absence-selector-wrap-' + idx);
        var faultWrap  = document.getElementById('fault-description-wrap-' + idx);
        var repairWrap = document.getElementById('repair-notes-wrap-' + idx);
        var repairLbl  = document.getElementById('repair-notes-label-' + idx);
        if (isPersonal && !absWrap) {
            var blockDiv = document.getElementById('block-' + idx);
            if (blockDiv && EB_CONFIG.absenceCategories) {
                var faultDiv = document.getElementById('fault-description-wrap-' + idx);
                if (!faultDiv) {
                    var fdr = blockDiv.querySelector('[name="entrada_' + idx + '_fault_description"]');
                    if (fdr && fdr.parentElement) {
                        fdr.parentElement.id = 'fault-description-wrap-' + idx;
                        faultDiv = fdr.parentElement;
                    }
                }
                if (faultDiv) {
                    var opts = '<option value="">— Selecciona una categoría —</option>';
                    EB_CONFIG.absenceCategories.forEach(function (cat) {
                        opts += '<option value="' + cat.id + '" data-requires-note="' +
                            (cat.requires_note ? '1' : '0') + '">' + cat.label + '</option>';
                    });
                    var nad = document.createElement('div');
                    nad.className = 'col-12 col-md-6 absence-selector-wrap d-none';
                    nad.id = 'absence-selector-wrap-' + idx;
                    nad.innerHTML =
                        '<label class="form-label fw-medium">' +
                        'Categoría de ausencia <span class="text-danger">*</span></label>' +
                        '<select name="entrada_' + idx + '_absence_category" ' +
                        'id="entrada_' + idx + '_absence_category" ' +
                        'class="form-select eb-field">' + opts + '</select>';
                    faultDiv.parentElement.insertBefore(nad, faultDiv);
                    absWrap = nad;
                    var rdr = blockDiv.querySelector('[name="entrada_' + idx + '_repair_notes"]');
                    if (rdr && rdr.parentElement) {
                        rdr.parentElement.id = 'repair-notes-wrap-' + idx;
                        var lbl = rdr.parentElement.querySelector('label');
                        if (lbl) { lbl.id = 'repair-notes-label-' + idx; }
                        repairWrap = rdr.parentElement;
                        repairLbl  = lbl;
                    }
                }
            }
        }
        if (!absWrap || !faultWrap) { return; }
        if (isPersonal) {
            absWrap.classList.remove('d-none');
            faultWrap.classList.add('d-none');
            var catSel = document.getElementById('entrada_' + idx + '_absence_category');
            if (catSel) {
                catSel.addEventListener('change', function () { _adjustRepairNotes(idx, catSel); });
                _adjustRepairNotes(idx, catSel);
            }
        } else {
            absWrap.classList.add('d-none');
            faultWrap.classList.remove('d-none');
            if (repairLbl) { repairLbl.innerHTML = 'Reparación realizada <span class=\"text-danger\">*</span>'; }
            if (repairWrap) { repairWrap.classList.remove('d-none'); }
        }
    }

    // ==================================================================
    // _adjustRepairNotes
    // Adjusts repair_notes visibility and label based on requires_note.
    // Ajusta repair_notes según el flag requires_note de la categoría.
    // ==================================================================
    function _adjustRepairNotes(idx, catSel) {
        var repairWrap = document.getElementById('repair-notes-wrap-' + idx);
        var repairLbl  = document.getElementById('repair-notes-label-' + idx);
        if (!repairWrap) { return; }
        var selOpt = catSel.options[catSel.selectedIndex];
        var requiresNote = selOpt && selOpt.dataset.requiresNote === '1';
        if (requiresNote) {
            repairWrap.classList.remove('d-none');
            if (repairLbl) { repairLbl.innerHTML = 'Observaciones <span class=\"text-danger\">*</span>'; }
        } else {
            repairWrap.classList.add('d-none');
        }
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

    // Re-attach autocomplete after HTMX outerHTML swaps (e.g. intensive-shift
    // toggle replaces #schedule-dependent-fields, destroying the first block
    // input and inserting a new one without data-tp-init or the autocomplete
    // event listeners). MutationObserver deferred via setTimeout so the full
    // subtree is in the DOM before querySelectorAll runs.
    // Re-adjuntar autocompletado tras swaps HTMX outerHTML (el toggle de jornada
    // intensiva reemplaza #schedule-dependent-fields destruyendo el input del
    // primer bloque e insertando uno nuevo sin listeners de autocompletado).
    // MutationObserver diferido via setTimeout para que el subarbol completo
    // este en el DOM antes de que corra querySelectorAll.
    var _autocompleteObserver = new MutationObserver(function (mutations) {
        var needsAttach = false;
        mutations.forEach(function (m) {
            if (m.addedNodes.length) { needsAttach = true; }
        });
        if (needsAttach) {
            setTimeout(function () {
                document.querySelectorAll(".asset-search").forEach(function (inp) {
                    // attachAutocomplete is idempotent via the dropdown guard:
                    // if dropdown is absent or already has listeners, it returns.
                    // attachAutocomplete es idempotente via la guarda del dropdown.
                    attachAutocomplete(inp);
                });
            }, 0);
        }
    });
    _autocompleteObserver.observe(document.body, {
        childList: true,
        subtree: true
    });

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
    function _buildBlockRow(idx, initHc, initHf) {
        initHc = initHc || "";
        initHf = initHf || "";
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
                               'class="form-control asset-search eb-field" ' +
                               'placeholder="Código de máquina" autocomplete="off">' +
                        '<div class="asset-dropdown d-none list-group mt-1 confirm-dropdown"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="col-6 col-md-2">' +
                    '<label class="form-label fw-medium">H.C. <span class="text-danger">*</span></label>' +
                    '<input type="time" step="1800" name="entrada_' + idx + '_hc" class="form-control eb-field" value="' + initHc + '">' +
                '</div>' +
                '<div class="col-6 col-md-2">' +
                    '<label class="form-label fw-medium">H.F. <span class="text-danger">*</span></label>' +
                    '<input type="time" step="1800" name="entrada_' + idx + '_hf" class="form-control eb-field" value="' + initHf + '">' +
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
                '<div class="col-12 col-md-6 absence-selector-wrap d-none" id="absence-selector-wrap-' + idx + '">' +
                    '<label class="form-label fw-medium">Categoría de ausencia <span class="text-danger">*</span></label>' +
                    (function () {
                        var opts = '<option value="">— Selecciona una categoría —</option>';
                        if (EB_CONFIG.absenceCategories) {
                            EB_CONFIG.absenceCategories.forEach(function (cat) {
                                opts += '<option value="' + cat.id + '" data-requires-note="' +
                                    (cat.requires_note ? '1' : '0') + '">' + cat.label + '</option>';
                            });
                        }
                        return '<select name="entrada_' + idx + '_absence_category" ' +
                               'id="entrada_' + idx + '_absence_category" ' +
                               'class="form-select eb-field">' + opts + '</select>';
                    }()) +
                '</div>' +
                '<div class="col-12 col-md-6" id="fault-description-wrap-' + idx + '">' +
                    '<label class="form-label fw-medium">Descripción avería <span class="text-danger">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_fault_description" ' +
                              'class="form-control desc-search eb-field" rows="3" ' +
                              'data-desc-field="fault_description" ' +
                              'placeholder="Descripción de la avería o tarea"></textarea>' +
                '</div>' +
                '<div class="col-12 col-md-6" id="repair-notes-wrap-' + idx + '">' +
                    '<label class="form-label fw-medium" id="repair-notes-label-' + idx + '">Reparación realizada <span class=\"text-danger\">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_repair_notes" ' +
                              'class="form-control desc-search eb-field" rows="3" ' +
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
            /* Pre-fill HC/HF before appendChild so TimePicker reads the value on init.
               Read EB_CONFIG at click time (not at module init) so that changes made
               by the intensive-shift toggle are reflected immediately.
               Prerrellenar HC/HF antes de appendChild para que TimePicker lea el valor
               al inicializar. Se lee EB_CONFIG en el momento del click (no al cargar
               el modulo) para reflejar los cambios del toggle de jornada intensiva. */
            var endTimeMorning   = (window.EB_CONFIG && window.EB_CONFIG.endTimeMorning)   || "";
            var endTimeAfternoon = (window.EB_CONFIG && window.EB_CONFIG.endTimeAfternoon) || "";
            var afternoonStart   = (window.EB_CONFIG && window.EB_CONFIG.lunchBreakEnd)    || "";
            var prevHfInput = document.querySelector('[name="entrada_' + current + '_hf"]');
            var rawPrevHf   = prevHfInput ? prevHfInput.value : "";
            var suggestedHc = "";
            var suggestedHf = "";
            if (rawPrevHf && endTimeMorning && rawPrevHf < endTimeMorning) {
                /* Previous block ends before morning end: this block starts
                   where the previous ended and covers until morning end.
                   El bloque anterior termina antes del fin de manana: este
                   bloque empieza donde termino el anterior y cubre hasta el
                   fin del tramo de manana. */
                suggestedHc = rawPrevHf;
                suggestedHf = endTimeMorning;
            } else if (rawPrevHf) {
                /* Previous block ends at or after morning end: we are in the
                   afternoon tract. HC is forced to afternoon start, HF to
                   afternoon end. In intensive shift afternoonStart and
                   endTimeAfternoon are both empty so HC/HF stay empty.
                   El bloque anterior termina a la hora de fin de manana o
                   despues: estamos en el tramo de tarde. HC se fuerza al
                   inicio de tarde, HF al fin de tarde. En jornada intensiva
                   ambos estan vacios, por lo que HC/HF quedan vacios. */
                suggestedHc = afternoonStart   || "";
                suggestedHf = endTimeAfternoon || "";
            }
            var row = _buildBlockRow(nextIdx, suggestedHc, suggestedHf);
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
            }
            // Inject lunch overlap hidden inputs before close_order submit.
            // Inyectar inputs de solapamiento antes del submit close_order.
            _computeAndInjectLunchOverlaps(numEntradas);

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
    // ==================================================================
    // No-lunch-break toggle — delegated to document so it survives HTMX
    // outerHTML swaps that replace #schedule-dependent-fields in-place.
    // References captured at module load time become stale (zombie nodes)
    // after HTMX replaces the DOM subtree. Event delegation on document
    // always targets the live node, regardless of how many swaps occurred.
    //
    // Toggle sin pausa de comida — delegado al document para que sobreviva
    // los swaps HTMX outerHTML que reemplazan #schedule-dependent-fields.
    // Las referencias capturadas al cargar el módulo quedan obsoletas (nodos
    // zombie) tras el swap HTMX. La delegación sobre document siempre
    // apunta al nodo vivo, independientemente del número de swaps ocurridos.
    // ==================================================================
    document.addEventListener("change", function (evt) {
        if (!evt.target || evt.target.id !== "id_no_lunch_toggle") { return; }

        // Re-query live DOM on every change event — nodes may have been
        // replaced by a prior HTMX swap.
        // Re-consultar el DOM vivo en cada evento change — los nodos pueden
        // haber sido reemplazados por un swap HTMX anterior.
        var noLunchHidden = document.getElementById("id_no_lunch_break_value");
        var lunchTimesDiv = document.getElementById("lunch-break-times");
        var lbStartInput  = document.getElementById("id_lunch_break_start");
        var lbEndInput    = document.getElementById("id_lunch_break_end");

        if (!noLunchHidden || !lunchTimesDiv) { return; }

        if (evt.target.checked) {
            // Operator skipped lunch: hide time fields, clear values, flag 1.
            // El operario no ha parado: ocultar campos, vaciar valores, flag 1.
            lunchTimesDiv.classList.add("d-none");
            noLunchHidden.value = "1";
            if (lbStartInput) { lbStartInput.value = ""; }
            if (lbEndInput)   { lbEndInput.value   = ""; }
        } else {
            // Operator had lunch: show time fields, restore schedule values.
            // El operario ha parado: mostrar campos, restaurar valores de horario.
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

    // ==================================================================
    // _computeAndInjectLunchOverlaps
    // Computes the overlap in minutes between each work block [hc, hf]
    // and the lunch break window, injects the result into a hidden input
    // (lunch_overlap_N) for backend deduction. Called from both the
    // close_order submit handler and the save_blocks click handler.
    //
    // Calcula el solapamiento en minutos entre cada bloque [hc, hf] y la
    // ventana de pausa de comida, e inyecta el resultado en un input oculto
    // (lunch_overlap_N) para el descuento en backend. Se llama desde
    // close_order y save_blocks para garantizar descuento coherente.
    // ==================================================================
    function _computeAndInjectLunchOverlaps(numBlocks) {
        function _lunchOverlapMinutes(hc, hf, lunchStart, lunchEnd) {
            if (!hc || !hf || !lunchStart || !lunchEnd) { return 0; }
            function _toMin(t) {
                var parts = t.split(":");
                return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
            }
            var blockStart   = _toMin(hc);
            var blockEnd     = _toMin(hf);
            var lunchS       = _toMin(lunchStart);
            var lunchE       = _toMin(lunchEnd);
            var overlapStart = Math.max(blockStart, lunchS);
            var overlapEnd   = Math.min(blockEnd,   lunchE);
            return Math.max(0, overlapEnd - overlapStart);
        }
        var noLunchEl  = document.getElementById("id_no_lunch_break_value");
        var noLunch    = noLunchEl && noLunchEl.value === "1";
        var lunchStart = noLunch ? "" : (_val("lunch_break_start") || LUNCH_BREAK_START);
        var lunchEnd   = noLunch ? "" : (_val("lunch_break_end")   || LUNCH_BREAK_END);
        for (var i = 1; i <= numBlocks; i++) {
            var hc         = _val("entrada_" + i + "_hc");
            var hf         = _val("entrada_" + i + "_hf");
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
            // Inject lunch overlap inputs before save_blocks submit.
            // Inyectar inputs de solapamiento antes del submit save_blocks.
            _computeAndInjectLunchOverlaps(sbNum);
            formActionInput.value = "save_blocks";
            form.submit();
        });
    }

    if (formActionInput) {
        formActionInput.value = "close_order";
    }

}());
