
// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/form_entry_assets.js
(function () {
    "use strict";

    var ASSETS_URL       = (window.EB_CONFIG && window.EB_CONFIG.assetsUrl)     || "/panel/operator/assets/";
    var ASSET_DETAIL_URL = (window.EB_CONFIG && window.EB_CONFIG.assetDetailUrl) || "/panel/operator/asset-detail/";

    /*
     * Reveals or hides meter-reading fields for the given block index.
     * Revela u oculta los campos de contadores para el índice de bloque dado.
     */
    /*
     * Sets a hidden input's value, creating it if it doesn't exist yet.
     * Used to send the reference meter value alongside the actual reading
     * so the server can detect unchanged (unmodified) readings.
     *
     * Establece el valor de un hidden input, creándolo si no existe.
     * Se usa para enviar el valor de referencia del contador junto con
     * la lectura real para que el servidor detecte lecturas no modificadas.
     */
    function _setRefHidden(form, name, value) {
        var hidden = form ? form.querySelector('[name="' + name + '"]') : null;
        if (!hidden) {
            hidden = document.createElement("input");
            hidden.type  = "hidden";
            hidden.name  = name;
            if (form) { form.appendChild(hidden); }
        }
        hidden.value = (value != null) ? value : "";
    }

    /*
     * Returns true when it is safe to pre-fill a meter input with the
     * reference value from the DB. Pre-fill is allowed only when:
     *   (a) the field is empty (operator has not typed anything yet), OR
     *   (b) the field currently holds the *previous* reference value
     *       (operator changed the machine — reset to new machine's baseline).
     *
     * This prevents overwriting a value the operator deliberately modified.
     *
     * ---
     *
     * Devuelve true cuando es seguro prerrellenar un campo de contador con
     * el valor de referencia de la BD. Se permite solo cuando:
     *   (a) el campo está vacío (el operario aún no ha escrito nada), O
     *   (b) el campo contiene el valor de referencia *anterior*
     *       (el operario cambió de máquina — resetear al baseline de la nueva).
     *
     * Esto evita sobreescribir un valor que el operario modificó a propósito.
     */
    function _canPrefill(input, newRef) {
        var current = input.value.trim();
        if (current === "") { return true; }
        var prevRef = input.dataset.refValue;
        if (prevRef != null && current === String(prevRef)) { return true; }
        return false;
    }

    function _applyMeterFields(blockIdx, data) {
        var sel     = '[data-block-idx="' + blockIdx + '"]';
        var odoEl   = document.querySelector('.meter-odometer' + sel);
        var engEl   = document.querySelector('.meter-engine'   + sel);
        var craneEl = document.querySelector('.meter-crane'    + sel);
        var _form   = document.getElementById("form-entry");
        if (odoEl) {
            odoEl.classList.toggle("d-none", !data.has_odometer);
            var odoInput = odoEl.querySelector("input");
            if (odoInput && data.mileage != null) {
                if (_canPrefill(odoInput, data.mileage)) {
                    odoInput.value = data.mileage;
                }
                odoInput.dataset.refValue = data.mileage;
                _setRefHidden(_form, "entrada_" + blockIdx + "_odometer_ref", data.mileage);
            }
        }
        if (engEl) {
            engEl.classList.toggle("d-none", !data.has_engine_hours);
            var engInput = engEl.querySelector("input");
            if (engInput && data.hours != null) {
                if (_canPrefill(engInput, data.hours)) {
                    engInput.value = data.hours;
                }
                engInput.dataset.refValue = data.hours;
                _setRefHidden(_form, "entrada_" + blockIdx + "_engine_hours_ref", data.hours);
            }
        }
        if (craneEl) {
            craneEl.classList.toggle("d-none", !data.has_crane_hours);
            var craneInput = craneEl.querySelector("input");
            if (craneInput && data.hours != null) {
                if (_canPrefill(craneInput, data.hours)) {
                    craneInput.value = data.hours;
                }
                craneInput.dataset.refValue = data.hours;
                _setRefHidden(_form, "entrada_" + blockIdx + "_crane_hours_ref", data.hours);
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
                        btn.textContent = asset.code + " — " + asset.brand_model;

                        /* pointerdown fires before blur on all platforms including
                           Android Chrome — set guard so blur does not close dropdown
                           before the selection is committed.
                           pointerdown se dispara antes que blur en todas las plataformas
                           incluido Android Chrome — la guardia evita que blur cierre el
                           dropdown antes de que se confirme la seleccion. */
                        btn.addEventListener("pointerdown", function () {
                            _selecting = true;
                        });
                        btn.addEventListener("touchstart", function () {
                            _selecting = true;
                        }, { passive: true });
                        btn.addEventListener("click", function () {
                            /* Show full label in the visible input for confirmation.
                               The server resolves the asset even if the label arrives.
                               Mostrar el label completo en el input como confirmación.
                               El servidor resuelve el activo aunque llegue el label. */
                            input.value = btn.textContent;
                            lastQuery   = asset.code;
                            var labelSpan = input.parentElement.querySelector(".asset-label");
                            if (labelSpan) { labelSpan.classList.add("d-none"); }
                            _selecting  = false;
                            _hideDropdown();
                            input.focus();
                            var blockDiv = input.closest('[id^="block-"]');
                            if (blockDiv) {
                                var bIdx = (blockDiv.id || "").replace("block-", "");
                                if (bIdx) {
                                    // Toggle absence mode if PERSONAL selected.
                                    // Activar modo ausencia si se selecciona PERSONAL.
                                    var EB_CFG    = window.EB_CONFIG || {};
                                    var isPersonal = asset.code === (EB_CFG.personalAssetCode || "PERSONAL");
                                    var isEmpresa  = !isPersonal && typeof asset.code === "string" &&
                                                     asset.code.toUpperCase().indexOf("EMPRESA_") === 0;
                                    _toggleAbsenceMode(bIdx, isPersonal);
                                    _toggleEmpresaMode(bIdx, isEmpresa, asset.code);
                                    if (isPersonal) {
                                        // Focus the absence selector or fault description.
                                        // Centrar el foco en el selector de ausencia o descripción.
                                        var catSel = document.getElementById("entrada_" + bIdx + "_absence_category");
                                        var faultTa = blockDiv.querySelector("[name=\"entrada_" + bIdx + "_fault_description\"]");
                                        setTimeout(function () {
                                            if (catSel) { catSel.focus(); }
                                            else if (faultTa) { faultTa.focus(); }
                                        }, 50);
                                    } else if (isEmpresa) {
                                        // Focus the empresa subtype selector.
                                        // Centrar el foco en el selector de subtipo empresa.
                                        setTimeout(function () {
                                            var esSel = document.getElementById("entrada_" + bIdx + "_empresa_subtype");
                                            if (esSel) { esSel.focus(); }
                                        }, 50);
                                    } else {
                                        // Reveal/hide meter fields for this block.
                                        // Revelar/ocultar campos de contadores del bloque.
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

        function _onInputChange() {
            debouncedFetch();
            // Trigger absence mode when value is PERSONAL.
            // Activar modo ausencia cuando el valor es PERSONAL.
            var blockDiv = input.closest("[id^=\"block-\"]");
            if (blockDiv) {
                var bIdx = (blockDiv.id || "").replace("block-", "");
                if (bIdx) {
                    var val = input.value.trim().toUpperCase();
                    _toggleAbsenceMode(bIdx, val === "PERSONAL");
                }
            }
        }
        // "input" covers desktop and most mobile browsers.
        // "keyup" is a fallback for Android virtual keyboards that fire
        // compositionend instead of "input" (keyCode 229 / IME events).
        // "input" cubre escritorio y la mayoría de móviles.
        // "keyup" es un respaldo para teclados virtuales Android que disparan
        // compositionend en lugar de "input" (keyCode 229 / eventos IME).
        input.addEventListener("input", _onInputChange);
        input.addEventListener("keyup",  _onInputChange);
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
    // When isPersonal=true: hides fault_description textarea, shows
    // absence category selector with a brief-note placeholder.
    //
    // Alterna un bloque entre modo reparación y modo ausencia.
    // Con isPersonal=true: oculta textarea de avería, muestra selector
    // de categoría con placeholder de nota breve.
    // ==================================================================
    function _toggleAbsenceMode(idx, isPersonal) {
        var absWrap    = document.getElementById("absence-selector-wrap-" + idx);
        var faultWrap  = document.getElementById("fault-description-wrap-" + idx);
        var repairWrap = document.getElementById("repair-notes-wrap-" + idx);
        var repairLbl  = document.getElementById("repair-notes-label-" + idx);
        var EB_CFG     = window.EB_CONFIG || {};

        if (isPersonal && (!absWrap || absWrap.innerHTML.trim() === "")) {
            var blockDiv = document.getElementById("block-" + idx);
            if (blockDiv && EB_CFG.absenceCategories) {
                // Use pre-existing empty wrapper (dynamic blocks) or insert before faultDiv.
                // Usar wrapper vacío pre-existente (bloques dinámicos) o insertar antes de faultDiv.
                var faultDiv = document.getElementById("fault-description-wrap-" + idx);
                if (!faultDiv) {
                    var fdr = blockDiv.querySelector("[name=\"entrada_" + idx + "_fault_description\"]");
                    if (fdr && fdr.parentElement) {
                        fdr.parentElement.id = "fault-description-wrap-" + idx;
                        faultDiv = fdr.parentElement;
                    }
                }
                var opts = "<option value=\"\">— Selecciona el motivo de ausencia —</option>";
                EB_CFG.absenceCategories.forEach(function (cat) {
                    opts += "<option value=\"" + cat.id + "\" data-requires-note=\"" +
                        (cat.requires_note ? "1" : "0") + "\">" + cat.label + "</option>";
                });
                var absContent =
                    "<label class=\"form-label fw-medium\">" +
                    "Categoría de ausencia <span class=\"text-danger\">*</span></label>" +
                    "<select name=\"entrada_" + idx + "_absence_category\" " +
                    "id=\"entrada_" + idx + "_absence_category\" " +
                    "class=\"form-select eb-field\">" + opts + "</select>" +
                    "<div class=\"form-text text-muted mt-1\">" +
                    "Selecciona el motivo. Describe brevemente en el campo de reparación si lo requiere." +
                    "</div>";
                if (absWrap) {
                    // Dynamic block: fill pre-existing empty wrapper.
                    absWrap.innerHTML = absContent;
                } else if (faultDiv) {
                    // Static block: create and insert wrapper.
                    var nad = document.createElement("div");
                    nad.className = "col-12 col-md-6 absence-selector-wrap d-none";
                    nad.id = "absence-selector-wrap-" + idx;
                    nad.innerHTML = absContent;
                    faultDiv.parentElement.insertBefore(nad, faultDiv);
                    absWrap = nad;
                }
                absWrap = document.getElementById("absence-selector-wrap-" + idx);
                var rdr = blockDiv.querySelector("[name=\"entrada_" + idx + "_repair_notes\"]");
                if (rdr) {
                    rdr.placeholder = "Describe brevemente el motivo de la ausencia (opcional).";
                    if (rdr.parentElement) {
                        if (!rdr.parentElement.id) { rdr.parentElement.id = "repair-notes-wrap-" + idx; }
                        var lbl = rdr.parentElement.querySelector("label");
                        if (lbl && !lbl.id) { lbl.id = "repair-notes-label-" + idx; }
                        repairWrap = rdr.parentElement;
                        repairLbl  = lbl;
                    }
                }
            }
        }
        if (!absWrap || !faultWrap) { return; }
        if (isPersonal) {
            absWrap.classList.remove("d-none");
            faultWrap.classList.add("d-none");
            // Keep repair_notes visible as the "brief reason" field.
            // Mantener repair_notes visible como campo de "motivo breve".
            var rdrPersonal = document.querySelector("[name=\"entrada_" + idx + "_repair_notes\"]");
            if (rdrPersonal) {
                rdrPersonal.placeholder = "Describe brevemente el motivo de la ausencia.";
            }
            if (repairLbl) {
                repairLbl.innerHTML = "Motivo de la ausencia <span class=\"text-danger\">*</span>";
            }
            if (repairWrap) { repairWrap.classList.remove("d-none"); }
            var catSel = document.getElementById("entrada_" + idx + "_absence_category");
            if (catSel) {
                catSel.addEventListener("change", function () { _adjustRepairNotes(idx, catSel); });
            }
        } else {
            absWrap.classList.add("d-none");
            faultWrap.classList.remove("d-none");
            var rdrReset = document.querySelector("[name=\"entrada_" + idx + "_repair_notes\"]");
            if (rdrReset) { rdrReset.placeholder = "Descripción de la reparación"; }
            if (repairLbl) { repairLbl.innerHTML = "Reparación realizada <span class=\"text-danger\">*</span>"; }
            if (repairWrap) { repairWrap.classList.remove("d-none"); }
        }
    }

    // ==================================================================
    // _toggleEmpresaMode
    // Switches a work block between repair mode and empresa cost-centre mode.
    // When isEmpresa=true: hides fault_description and repair_notes label,
    // shows a subtype <select> built from EB_CONFIG.empresaSubtypes[assetCode].
    // repair_notes stays visible as the mandatory note field.
    //
    // Alterna un bloque entre modo reparación y modo centro de gasto empresa.
    // Con isEmpresa=true: oculta avería, muestra select de subtipo construido
    // desde EB_CONFIG.empresaSubtypes[assetCode]. repair_notes sigue visible
    // como campo de nota obligatoria.
    // ==================================================================
    function _toggleEmpresaMode(idx, isEmpresa, assetCode) {
        var esWrap    = document.getElementById("empresa-selector-wrap-" + idx);
        var faultWrap = document.getElementById("fault-description-wrap-" + idx);
        var repairWrap = document.getElementById("repair-notes-wrap-" + idx);
        var repairLbl  = document.getElementById("repair-notes-label-" + idx);
        var EB_CFG     = window.EB_CONFIG || {};

        if (isEmpresa) {
            var subtypes = (
                EB_CFG.empresaSubtypes &&
                assetCode &&
                EB_CFG.empresaSubtypes[assetCode]
            ) || [];

            // Build or rebuild the subtype selector.
            // Construir o reconstruir el selector de subtipo.
            if (!esWrap) {
                // Static block: create wrapper before fault-description-wrap.
                // Bloque estático: crear wrapper antes de fault-description-wrap.
                var faultDiv = document.getElementById("fault-description-wrap-" + idx);
                if (!faultDiv) {
                    var fdr = document.querySelector("[name=\"entrada_" + idx + "_fault_description\"]");
                    if (fdr && fdr.parentElement) {
                        fdr.parentElement.id = "fault-description-wrap-" + idx;
                        faultDiv = fdr.parentElement;
                    }
                }
                if (faultDiv) {
                    var naw = document.createElement("div");
                    naw.className = "col-12 col-md-6 empresa-selector-wrap d-none";
                    naw.id = "empresa-selector-wrap-" + idx;
                    faultDiv.parentElement.insertBefore(naw, faultDiv);
                    esWrap = naw;
                }
            }

            if (esWrap && subtypes.length > 0) {
                var opts = "<option value=\"\">— Selecciona el tipo de tarea —</option>";
                subtypes.forEach(function (st) {
                    opts += "<option value=\"" + st.label + "\">" + st.label + "</option>";
                });
                esWrap.innerHTML =
                    "<label class=\"form-label fw-medium\">" +
                    "Tipo de tarea <span class=\"text-danger\">*</span></label>" +
                    "<select name=\"entrada_" + idx + "_empresa_subtype\" " +
                    "id=\"entrada_" + idx + "_empresa_subtype\" " +
                    "class=\"form-select eb-field empresa-subtype-select\"></select>" +
                    "<div class=\"form-text text-muted mt-1\">" +
                    "Selecciona el tipo de tarea y describe en el campo de nota." +
                    "</div>";
                // Fill select options.
                var sel = document.getElementById("entrada_" + idx + "_empresa_subtype");
                if (sel) { sel.innerHTML = opts; }
                esWrap.classList.remove("d-none");
            }

            // Hide fault description, keep repair_notes as mandatory note.
            // Ocultar descripción de avería, mantener repair_notes como nota obligatoria.
            if (faultWrap) { faultWrap.classList.add("d-none"); }
            if (repairWrap) { repairWrap.classList.remove("d-none"); }
            if (repairLbl) {
                repairLbl.innerHTML = "Nota <span class=\"text-danger\">*</span>";
            }
            var rdrEmpresa = document.querySelector("[name=\"entrada_" + idx + "_repair_notes\"]");
            if (rdrEmpresa) {
                rdrEmpresa.placeholder = "Describe brevemente la tarea realizada.";
            }
        } else {
            // Restore normal repair mode.
            // Restaurar modo reparación normal.
            if (esWrap) { esWrap.classList.add("d-none"); }
            if (faultWrap) { faultWrap.classList.remove("d-none"); }
            if (repairWrap) { repairWrap.classList.remove("d-none"); }
            if (repairLbl) {
                repairLbl.innerHTML = "Reparación realizada <span class=\"text-danger\">*</span>";
            }
            var rdrReset = document.querySelector("[name=\"entrada_" + idx + "_repair_notes\"]");
            if (rdrReset) { rdrReset.placeholder = "Descripción de la reparación"; }
        }
    }

    // ==================================================================
    // _adjustRepairNotes
    // Adjusts repair_notes visibility based on requires_note flag.
    // Ajusta repair_notes según el flag requires_note de la categoría.
    // ==================================================================
    function _adjustRepairNotes(idx, catSel) {
        var repairWrap = document.getElementById("repair-notes-wrap-" + idx);
        var repairLbl  = document.getElementById("repair-notes-label-" + idx);
        if (!repairWrap) { return; }
        var selOpt = catSel.options[catSel.selectedIndex];
        var requiresNote = selOpt && selOpt.dataset.requiresNote === "1";
        if (requiresNote) {
            repairWrap.classList.remove("d-none");
            if (repairLbl) {
                repairLbl.innerHTML = "Observaciones <span class=\"text-danger\">*</span>";
            }
        } else {
            repairWrap.classList.add("d-none");
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
            var v = (inp.dataset.codeValue || inp.value).trim();
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
    // machine_raw value (server re-render after validation error or edit mode).
    // Al cargar la página, revelar campos de contador para cualquier bloque
    // que ya tenga machine_raw (re-renderizado tras error de validación o
    // modo edición).
    document.querySelectorAll(".asset-search").forEach(function (input) {
        var raw = input.value.trim();
        if (!raw) { return; }

        // Extract the bare asset code when the field contains the full label
        // (e.g. "B43 — PALFINGER PK 72002").  The server accepts only codes.
        // Extraer el código limpio cuando el campo contiene el label completo.
        var code = raw;
        var _labelMatch = raw.match(/^([^—–\-]+?)\s*[—–]\s+/);
        if (_labelMatch) { code = _labelMatch[1].trim(); }

        var blockDiv = input.closest('[id^="block-"]');
        if (!blockDiv) { return; }
        var bIdx = (blockDiv.id || "").replace("block-", "");

        // Snapshot of meter inputs BEFORE the fetch so we can decide whether
        // to preserve their values (edit mode — already populated by server).
        // Captura de los inputs de contador ANTES del fetch para saber si
        // hay que preservar sus valores (modo edición — ya rellenos por servidor).
        var sel = '[data-block-idx="' + bIdx + '"]';
        var _preFilled = {
            odo:   (document.querySelector('.meter-odometer' + sel + ' input') || {}).value || "",
            eng:   (document.querySelector('.meter-engine'   + sel + ' input') || {}).value || "",
            crane: (document.querySelector('.meter-crane'    + sel + ' input') || {}).value || ""
        };

        fetch(ASSET_DETAIL_URL + "?code=" + encodeURIComponent(code))
            .then(function (r) {
                if (!r.ok) { throw new Error("HTTP " + r.status); }
                return r.json();
            })
            .then(function (d) {
                _applyMeterFields(bIdx, d);
                // After _applyMeterFields, restore server-pre-filled values
                // that _canPrefill may have skipped (edit mode with saved readings).
                // Tras _applyMeterFields, restaurar valores pre-rellenos por el
                // servidor que _canPrefill pudo haber saltado (modo edición con
                // lecturas guardadas).
                var odoInput   = document.querySelector('.meter-odometer' + sel + ' input');
                var engInput   = document.querySelector('.meter-engine'   + sel + ' input');
                var craneInput = document.querySelector('.meter-crane'    + sel + ' input');
                if (odoInput   && _preFilled.odo   !== "") { odoInput.value   = _preFilled.odo; }
                if (engInput   && _preFilled.eng   !== "") { engInput.value   = _preFilled.eng; }
                if (craneInput && _preFilled.crane !== "") { craneInput.value = _preFilled.crane; }
            })
            .catch(function () {
                // On fetch error, only hide meter divs that are NOT already
                // visible with server-pre-filled values (do not regress edit mode).
                // En caso de error de fetch, solo ocultar divs que NO estén ya
                // visibles con valores del servidor (no regresar el modo edición).
                var odoEl   = document.querySelector('.meter-odometer' + sel);
                var engEl   = document.querySelector('.meter-engine'   + sel);
                var craneEl = document.querySelector('.meter-crane'    + sel);
                if (odoEl   && _preFilled.odo   === "") { odoEl.classList.add("d-none"); }
                if (engEl   && _preFilled.eng   === "") { engEl.classList.add("d-none"); }
                if (craneEl && _preFilled.crane === "") { craneEl.classList.add("d-none"); }
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
                    '<i class="bi bi-trash"></i> Eliminar tarea' +
                '</button>' +
            '</div>' +
            '<div class="row g-3">' +
                '<div class="col-12 col-md-4">' +
                    '<label class="form-label fw-medium">Máquina o Sección <span class="text-danger">*</span></label>' +
                    '<div class="position-relative">' +
                        '<input type="text" name="entrada_' + idx + '_machine_raw" ' +
                               'class="form-control asset-search" ' +
                               'placeholder="Codigo de maquina" autocomplete="off">' +
                        '<small class="asset-label d-none text-muted mt-1 d-block"></small>' +
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
                           'class="form-control" placeholder="Referencia O.R. (opcional)">' +
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
                '<div class="col-12 col-md-6 absence-selector-wrap d-none" id="absence-selector-wrap-' + idx + '"></div>' +
                '<div class="col-12 col-md-6 empresa-selector-wrap d-none" id="empresa-selector-wrap-' + idx + '"></div>' +
                '<div class="col-12 col-md-6" id="fault-description-wrap-' + idx + '">' +
                    '<label class="form-label fw-medium">Descripción avería <span class="text-danger">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_fault_description" ' +
                              'class="form-control eb-field desc-search" rows="3" ' +
                              'data-desc-field="fault_description" ' +
                              'placeholder="Descripción de la avería o tarea"></textarea>' +
                '</div>' +
                '<div class="col-12 col-md-6" id="repair-notes-wrap-' + idx + '">' +
                    '<label class="form-label fw-medium" id="repair-notes-label-' + idx + '">Reparación realizada <span class="text-danger">*</span></label>' +
                    '<textarea name="entrada_' + idx + '_repair_notes" ' +
                              'class="form-control eb-field desc-search" rows="3" ' +
                              'data-desc-field="repair_notes" ' +
                              'placeholder="Descripción de la reparación"></textarea>' +
                '</div>' +
                '<div class="col-12">' +
                    '<div class="form-check mt-1">' +
                        '<input class="form-check-input" type="checkbox" ' +
                               'name="entrada_' + idx + '_is_on_site" ' +
                               'id="id_entrada_' + idx + '_is_on_site" value="1">' +
                        '<label class="form-check-label" ' +
                               'for="id_entrada_' + idx + '_is_on_site">' +
                            '<i class=\"bi bi-geo-alt me-1 text-secondary\"></i>' +
                            ' Trabajo in situ (fuera del taller)' +
                        '</label>' +
                    '</div>' +
                '</div>' +
                // Ticket de avería vinculado (H17)
                // Linked breakdown ticket selector (H17)
                _buildTicketBlock(idx) +
            '</div>';
        return div;
    }

    /*
     * Builds the breakdown ticket selector + close-checkbox HTML
     * for a work block. Returns an empty string when no repair orders
     * are available (EB_CONFIG.repairOrders is empty).
     *
     * Construye el selector de ticket de avería + checkbox de cierre
     * para un bloque de trabajo. Devuelve cadena vacía cuando no hay
     * órdenes disponibles (EB_CONFIG.repairOrders está vacío).
     */
    function _buildTicketBlock(idx) {
        var orders = (window.EB_CONFIG && window.EB_CONFIG.repairOrders) || [];
        if (!orders.length) { return ''; }
        var opts = '<option value="">\u2014 Sin ticket \u2014</option>';
        orders.forEach(function (ot) {
            var label = ot.code || ('Ticket #' + ot.pk);
            if (ot.machine_raw) { label += ' \u2014 ' + ot.machine_raw; }
            if (ot.fault_summary) {
                var fs = ot.fault_summary.length > 40
                    ? ot.fault_summary.slice(0, 40) + '\u2026'
                    : ot.fault_summary;
                label += ' | ' + fs;
            }
            opts += '<option value="' + ot.pk + '">' + label + '</option>';
        });
        return (
            '<div class="col-12 col-md-8">' +
                '<label class="form-label fw-medium">' +
                    '<i class="bi bi-exclamation-triangle me-1 text-warning"></i>' +
                    ' Ticket de aver\u00eda vinculado' +
                '</label>' +
                '<select name="entrada_' + idx + '_ticket_pk" ' +
                        'class="form-select form-select-sm ticket-select" ' +
                        'data-block-idx="' + idx + '">' +
                    opts +
                '</select>' +
            '</div>' +
            '<div class="col-12 col-md-4 d-flex align-items-end">' +
                '<div class="form-check mb-2">' +
                    '<input class="form-check-input ticket-close-check" ' +
                           'type="checkbox" ' +
                           'name="entrada_' + idx + '_ticket_closed" ' +
                           'id="id_entrada_' + idx + '_ticket_closed" value="1">' +
                    '<label class="form-check-label small fw-medium text-danger" ' +
                           'for="id_entrada_' + idx + '_ticket_closed">' +
                        '<i class="bi bi-check-circle me-1"></i>' +
                        ' Aver\u00eda resuelta \u2014 cerrar ticket' +
                    '</label>' +
                '</div>' +
            '</div>'
        );
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
                           'class="form-control" placeholder="Descripcion del material">' +
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
            var v = (inp.dataset.codeValue || inp.value).trim();
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

            // Compute suggested HC/HF for the new block based on the previous
            // block's HF and the operator's schedule periods. This is only a
            // pre-fill hint — the operator may override it, and the closing
            // guardian modal validates gaps/overlaps and the 8h minimum.
            //
            // Calcular HC/HF sugeridos para el nuevo bloque a partir de la HF
            // del bloque anterior y los periodos del horario. Es solo una
            // ayuda de prerrelleno — el operario puede cambiarla, y el modal
            // guardián valida lagunas/solapamientos y el mínimo de 8h.
            var prevHf = "";
            var prevBlock = document.getElementById("block-" + current);
            if (prevBlock) {
                var prevHfInput = prevBlock.querySelector("[name=\"entrada_" + current + "_hf\"]");
                if (prevHfInput && prevHfInput.value) { prevHf = prevHfInput.value; }
            }

            var _cfgAdd  = window.EB_CONFIG || {};
            var _endM    = _cfgAdd.endTimeMorning || "";
            var _endA    = _cfgAdd.endTimeAfternoon || "";
            var _startA  = _cfgAdd.startTimeAfternoon || "";
            var _lbStart = _cfgAdd.lunchBreakStart || "";
            var _lbEnd   = _cfgAdd.lunchBreakEnd   || "";
            // Lunch active? Split shift not flagged "no lunch", or intensive
            // with "had lunch" checked.
            // ¿Pausa activa? Jornada partida sin "no he parado a comer", o
            // intensiva con "he parado a comer" marcado.
            var _noLunchEl  = document.getElementById("id_no_lunch_break_value");
            var _lunchActive = !(_noLunchEl && _noLunchEl.value === "1");

            var newHc = prevHf;
            var newHf = "";
            if (prevHf && _lbStart && _lbEnd && prevHf === _lbStart && _lunchActive) {
                // Previous block ended exactly when the declared lunch break starts:
                // next block starts after the lunch break ends.
                // El bloque anterior terminó justo cuando empieza la pausa declarada:
                // el nuevo bloque arranca al fin de la pausa.
                newHc = _lbEnd;
                newHf = _endA || "";
            } else if (prevHf && _endM && prevHf === _endM && _lunchActive && _startA) {
                // Previous block ended at end of morning and there is a lunch
                // break: next block starts at the afternoon start time.
                // El bloque anterior acabó al fin de la mañana y hay pausa:
                // el nuevo bloque arranca al inicio de la tarde.
                newHc = _startA;
                newHf = _endA || "";
            } else if (prevHf && _endM && prevHf < _endM) {
                // HC falls in the morning period — HF defaults to end morning.
                // La HC cae en el periodo de mañana — HF por defecto fin mañana.
                newHf = _endM;
            } else {
                // HC falls in the afternoon period — HF defaults to end afternoon.
                // La HC cae en el periodo de tarde — HF por defecto fin tarde.
                newHf = _endA || _endM || "";
            }

            var row = _buildBlockRow(nextIdx);
            extraBlocksCont.appendChild(row);
            if (newHc) {
                var newHcInput = row.querySelector("[name=\"entrada_" + nextIdx + "_hc\"]");
                if (newHcInput) { newHcInput.value = newHc; }
            }
            if (newHf) {
                var newHfInput = row.querySelector("[name=\"entrada_" + nextIdx + "_hf\"]");
                if (newHfInput) { newHfInput.value = newHf; }
            }
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

    // -- Remove static block handler (server-rendered blocks in edit/validation mode).
    // Manejador de eliminacion de bloques estaticos (renderizados por servidor en modo
    // edicion o tras fallo de validacion). A diferencia de los bloques dinamicos
    // (gestionados por el handler de btn-add-block), estos estan en el DOM principal
    // y no en extra-blocks-container, por lo que se eliminan con row.remove().
    // --
    document.querySelectorAll(".btn-remove-block-static").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            var blockId = btn.getAttribute("data-block-id");
            var row = document.getElementById("block-" + blockId);
            if (row) {
                row.remove();
                var current = parseInt(numEntradasInput.value, 10) || 1;
                if (current > 1) { numEntradasInput.value = current - 1; }
            }
        });
    });

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
            var _cfgVal     = window.EB_CONFIG || {};
            var _personalCode = (_cfgVal.personalAssetCode || "PERSONAL").toUpperCase();
            for (var i = 1; i <= numEntradas; i++) {
                var blk  = "Tarea " + i;
                var maq  = _val("entrada_" + i + "_machine_raw");
                var hc   = _val("entrada_" + i + "_hc");
                var hf   = _val("entrada_" + i + "_hf");
                var desc = _val("entrada_" + i + "_fault_description");
                var isAbsenceBlk = maq.trim().toUpperCase() === _personalCode;
                var absCat = _val("entrada_" + i + "_absence_category");

                _markField("entrada_" + i + "_machine_raw", !maq);
                _markField("entrada_" + i + "_hc",          !hc);
                _markField("entrada_" + i + "_hf",          !hf);

                if (!maq)  { errors.push(blk + ": codigo de maquina obligatorio."); }
                if (!hc)   { errors.push(blk + ": H.C. obligatoria."); }
                if (!hf)   { errors.push(blk + ": H.F. obligatoria."); }
                if (isAbsenceBlk) {
                    // Absence block: require category, not fault description.
                    // Bloque de ausencia: exigir categoría, no descripción avería.
                    _markField("entrada_" + i + "_absence_category", !absCat);
                    if (!absCat) {
                        errors.push(blk + ": selecciona una categoria de ausencia.");
                    }
                } else {
                    _markField("entrada_" + i + "_fault_description", !desc);
                    if (!desc) { errors.push(blk + ": descripcion de averia obligatoria."); }
                }
                if (hc && hf && hf <= hc) {
                    _markField("entrada_" + i + "_hf", true);
                    errors.push(blk + ": H.F. debe ser posterior a H.C.");
                }
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

            // Gate A — overlap detection between blocks.
            var _blocks = [];
            for (var oi = 1; oi <= numEntradas; oi++) {
                var _ohc = _val("entrada_" + oi + "_hc");
                var _ohf = _val("entrada_" + oi + "_hf");
                if (_ohc && _ohf && _ohf > _ohc) {
                    _blocks.push({ idx: oi, hc: _ohc, hf: _ohf });
                }
            }
            _blocks.sort(function (a, b) { return a.hc < b.hc ? -1 : 1; });
            for (var bi = 0; bi < _blocks.length - 1; bi++) {
                if (_blocks[bi].hf > _blocks[bi + 1].hc) {
                    errors.push(
                        "Tarea " + _blocks[bi].idx + " y Tarea " + _blocks[bi + 1].idx +
                        ": los horarios se solapan (" + _blocks[bi].hf + " > " + _blocks[bi + 1].hc + ")."
                    );
                }
            }

            // Gate B — workday coverage check (close_order only).
            var _formActionEl = document.getElementById("form-action-input");
            var _formAction   = _formActionEl ? _formActionEl.value : "";
            var _gapErrors    = [];
            if (_formAction !== "save_blocks" && errors.length === 0) {
                var _cfg         = window.EB_CONFIG || {};
                var _isIntensive = !!_cfg.isIntensiveOverride;
                var _endTime     = _isIntensive
                    ? (_cfg.endTimeMorning || "")
                    : (_cfg.endTimeAfternoon || _cfg.endTimeMorning || "");
                function _toMin(t) {
                    if (!t) { return 0; }
                    var p = t.split(":");
                    return parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
                }
                var _lbStart  = (_cfg.lunchBreakStart || "");
                var _lbEnd    = (_cfg.lunchBreakEnd   || "");
                var _noLunchEl = document.getElementById("id_no_lunch_break_value");
                var _noLunch  = _noLunchEl && _noLunchEl.value === "1";
                if (_noLunch) { _lbStart = ""; _lbEnd = ""; }
                var _totalMin = 0;
                for (var gi = 1; gi <= numEntradas; gi++) {
                    var _ghc = _val("entrada_" + gi + "_hc");
                    var _ghf = _val("entrada_" + gi + "_hf");
                    if (!_ghc || !_ghf) { continue; }
                    var _gross = _toMin(_ghf) - _toMin(_ghc);
                    if (_gross <= 0) { continue; }
                    var _overlap = 0;
                    if (_lbStart && _lbEnd) {
                        _overlap = Math.max(0,
                            Math.min(_toMin(_ghf), _toMin(_lbEnd)) -
                            Math.max(_toMin(_ghc), _toMin(_lbStart))
                        );
                    }
                    _totalMin += (_gross - _overlap);
                }
                if (_totalMin < 480) {
                    var _missingMin = 480 - _totalMin;
                    var _missingH   = Math.floor(_missingMin / 60);
                    var _missingM   = _missingMin % 60;
                    var _missingStr = _missingH > 0
                        ? (_missingH + " h " + (_missingM > 0 ? _missingM + " min" : ""))
                        : (_missingM + " min");
                    _gapErrors.push(
                        "La jornada suma " + (_totalMin / 60).toFixed(2).replace(".", ",") +
                        " h, pero se requieren al menos 8 h. " +
                        "Faltan " + _missingStr + " para completar la jornada. " +
                        "Aniade las tareas que faltan o, si hubo ausencia, " +
                        "aniade una tarea con codigo PERSONAL en el campo " +
                        "Maquina/Centro de Gasto y selecciona el motivo."
                    );
                }
                // Early-close check. Skip when total >= 8h: the operator
                // may legitimately add an afternoon block in intensive shift
                // as long as the 8h are met.
                // Comprobación de cierre anticipado. Se omite si total >= 8h:
                // el operario puede añadir un bloque vespertino en jornada
                // intensiva siempre que se cumplan las 8h.
                if (_endTime && _totalMin < 480) {
                    var _lastHf  = _blocks.length > 0 ? _blocks[_blocks.length - 1].hf : "";
                    var _endMin  = _toMin(_endTime);
                    var _lastMin = _toMin(_lastHf);
                    if (_lastHf && _lastMin < _endMin - 14) {
                        var _missEndMin = _endMin - _lastMin;
                        _gapErrors.push(
                            "Cierre anticipado: tu ultimo bloque termina a las " + _lastHf +
                            " pero la jornada acaba a las " + _endTime +
                            " (faltan " + _missEndMin + " min). " +
                            "Aniade una tarea o justifica la ausencia con codigo PERSONAL."
                        );
                    }
                }
            }

            if (errors.length > 0) {
                e.preventDefault();
                _showAlert(errors.join(" | "));
                return;
            }

            if (_gapErrors.length > 0) {
                e.preventDefault();
                var _gapModal = document.getElementById("gapWarningModal");
                var _gapList  = document.getElementById("gap-warning-list");
                if (_gapModal && _gapList && window.bootstrap && bootstrap.Modal) {
                    _gapList.innerHTML = "";
                    _gapErrors.forEach(function (msg) {
                        var li = document.createElement("li");
                        li.className = "list-group-item ps-0 border-0 py-1";
                        li.innerHTML = '<i class="bi bi-clock text-warning me-2"></i>' + msg;
                        _gapList.appendChild(li);
                    });
                    var _m = bootstrap.Modal.getOrCreateInstance(_gapModal);
                    _m.show();
                } else {
                    _showAlert(_gapErrors.join(" | "));
                }
            }
        });
    }

    // ==================================================================
    // _initLunchBreak
    // Manages lunch-break field visibility and auto-fill based on shift.
    // - Split shift: show pre-filled lunch times from schedule.
    // - Intensive shift: no lunch — fields stay hidden.
    // - "No lunch" checkbox: hides times and flags no_lunch_break=1.
    //
    // Gestiona visibilidad y auto-relleno de pausa según jornada.
    // - Jornada partida: mostrar pausa prerrellenada del horario.
    // - Jornada intensiva: sin pausa — campos ocultos.
    // - Checkbox "no he parado a comer": oculta pausa y marca flag.
    // ==================================================================
    function _initLunchBreak() {
        var lbStart    = document.getElementById("id_lunch_break_start");
        var lbEnd      = document.getElementById("id_lunch_break_end");
        var noLunchCb  = document.getElementById("id_no_lunch_toggle");
        var hadLunchCb = document.getElementById("id_had_lunch_toggle");
        var noLunchVal = document.getElementById("id_no_lunch_break_value");
        if (!lbStart || !lbEnd) { return; }

        function _applyVisibility() {
            var showTimes;
            if (hadLunchCb) {
                // Intensive shift: lunch OFF by default, shown when checked.
                // Jornada intensiva: sin pausa por defecto, visible al marcar.
                showTimes = hadLunchCb.checked;
                if (noLunchVal) { noLunchVal.value = showTimes ? "0" : "1"; }
            } else if (noLunchCb) {
                // Split shift: lunch ON by default, hidden when checked.
                // Jornada partida: pausa por defecto, oculta al marcar.
                showTimes = !noLunchCb.checked && lbStart.value && lbEnd.value;
                if (noLunchVal) { noLunchVal.value = noLunchCb.checked ? "1" : "0"; }
            } else {
                showTimes = lbStart.value && lbEnd.value;
            }
            if (showTimes) {
                lbStart.classList.remove("d-none");
                lbEnd.classList.remove("d-none");
            } else {
                lbStart.classList.add("d-none");
                lbEnd.classList.add("d-none");
            }
        }

        _applyVisibility();

        if (noLunchCb)  { noLunchCb.addEventListener("change", _applyVisibility); }
        if (hadLunchCb) { hadLunchCb.addEventListener("change", _applyVisibility); }
    }

    // Run on load and re-run after each HTMX swap of the schedule fragment.
    // Ejecutar al cargar y tras cada swap HTMX del fragment de horario.
    _initLunchBreak();
    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (evt.target && evt.target.id === "schedule-dependent-fields") {
            _initLunchBreak();
            // Re-attach autocomplete to the new first block input.
            // Re-asociar autocompletado al nuevo input del primer bloque.
            var newFirst = evt.target.querySelector(".asset-search");
            if (newFirst) { attachAutocomplete(newFirst); }
        }
    });

    // No submit transformation needed — asset-search inputs always contain
    // the bare code. The .asset-label span is display-only and not submitted.
    // No se necesita transformación en submit — los inputs asset-search siempre
    // contienen el código limpio. El span .asset-label es solo visual, no se envía.

}());




