/*
 * form_entry_modal.js — Via A work-order form: modal save flow.
 * Handles the zero-meter confirmation modal and the final save
 * confirmation modal before form submission.
 *
 * form_entry_modal.js — Formulario Via A: flujo modal de guardado.
 * Gestiona el modal de confirmación de ceros en contadores y el modal
 * de confirmación final antes del envío del formulario.
 */
(function () {
    "use strict";

    function _initModalFlow() {

    /*
     * Modal save flow for form_entry.html (Via A).
     * Intercepts the "Guardar parte" button, runs zero-meter detection,
     * shows the appropriate modal(s) and only submits the real form once the
     * operator has confirmed all warnings.
     *
     * Flujo modal de guardado para form_entry.html (Via A).
     * Intercepta el boton "Guardar parte", detecta contadores a cero,
     * muestra el modal correspondiente y solo envia el formulario real una vez
     * que el operario ha confirmado todos los avisos.
     */

    var form              = document.getElementById("form-entry");
    var btnTrigger        = document.getElementById("btn-form-submit");
    var saveConfirmedEl   = document.getElementById("save-confirmed-input");
    var zeroMetersEl      = document.getElementById("zero-meters-confirmed-input");
    var summaryEl         = document.getElementById("confirm-save-summary");
    var zeroListEl        = document.getElementById("zero-meter-list");
    var btnZeroConfirm    = document.getElementById("btn-zero-meter-confirm");
    var btnSaveFinal      = document.getElementById("btn-confirm-save-final");

    var zeroMeterModal   = null;
    var confirmSaveModal = null;
    var _pendingZeroData = {};

    if (typeof bootstrap !== "undefined") {
        zeroMeterModal   = new bootstrap.Modal(document.getElementById("zeroMeterModal"));
        confirmSaveModal = new bootstrap.Modal(document.getElementById("confirmSaveModal"));
    }

    /*
     * Collects visible meter-field inputs with value == 0.
     * Returns an object keyed by block idx, value is array of meter type labels.
     * Recopila los inputs meter-field visibles con valor == 0.
     * Devuelve un objeto con clave block idx y valor array de etiquetas de contador.
     */
    function _detectZeroMeters() {
        var zeros = {};
        document.querySelectorAll(".meter-field:not(.d-none)").forEach(function (wrapper) {
            var input = wrapper.querySelector("input");
            if (!input) { return; }
            var val = parseFloat(input.value);
            if (!isNaN(val) && val === 0) {
                var bIdx  = wrapper.dataset.blockIdx || "?";
                var label = (wrapper.querySelector("label") || {}).textContent || input.name;
                if (!zeros[bIdx]) { zeros[bIdx] = []; }
                zeros[bIdx].push({ label: label.trim(), name: input.name });
            }
        });
        return zeros;
    }

    /*
     * Builds the summary HTML injected into #confirm-save-summary.
     * Construye el HTML del resumen inyectado en #confirm-save-summary.
     */
    function _buildSummary() {
        var fecha = (form.querySelector('[name="fecha"]') || {}).value || "—";
        var numEntradas = parseInt((form.querySelector('[name="num_entradas"]') || {}).value, 10) || 0;
        var html = '<table class="table table-sm mb-0">';
        html += '<tr><th class="text-muted fw-normal">Fecha</th><td>' + fecha + '</td></tr>';
        html += '<tr><th class="text-muted fw-normal">Tareas</th><td>' + numEntradas + '</td></tr>';
        var totalHoras = 0;
        for (var i = 1; i <= numEntradas; i++) {
            var hc = (form.querySelector('[name="entrada_' + i + '_hc"]') || {}).value || "";
            var hf = (form.querySelector('[name="entrada_' + i + '_hf"]') || {}).value || "";
            if (hc && hf) {
                var hcParts = hc.split(":"); var hfParts = hf.split(":");
                var delta = (parseInt(hfParts[0], 10) * 60 + parseInt(hfParts[1], 10)) -
                            (parseInt(hcParts[0], 10) * 60 + parseInt(hcParts[1], 10));
                if (delta > 0) { totalHoras += delta / 60; }
            }
        }
        html += '<tr><th class="text-muted fw-normal">Horas estimadas</th><td>' +
                totalHoras.toFixed(1) + ' h</td></tr>';
        html += '</table>';
        return html;
    }

    /*
     * Main flow: called when the operator clicks "Guardar parte".
     * Flujo principal: llamado cuando el operario pulsa "Guardar parte".
     */
    function _onSaveTrigger() {
        var zeros = _detectZeroMeters();
        if (Object.keys(zeros).length > 0) {
            _pendingZeroData = zeros;
            zeroListEl.innerHTML = "";
            Object.keys(zeros).forEach(function (bIdx) {
                zeros[bIdx].forEach(function (m) {
                    var li = document.createElement("li");
                    li.textContent = "Bloque " + bIdx + " — " + m.label;
                    zeroListEl.appendChild(li);
                });
            });
            if (zeroMeterModal) { zeroMeterModal.show(); }
        } else {
            _showConfirmModal();
        }
    }

    /*
     * Shows the confirmation summary modal.
     * Muestra el modal de resumen de confirmacion.
     */
    function _showConfirmModal() {
        if (summaryEl) { summaryEl.innerHTML = _buildSummary(); }
        if (confirmSaveModal) { confirmSaveModal.show(); }
    }

    if (btnZeroConfirm) {
        btnZeroConfirm.addEventListener("click", function () {
            if (zeroMetersEl) {
                zeroMetersEl.value = JSON.stringify(_pendingZeroData);
            }
            if (zeroMeterModal) { zeroMeterModal.hide(); }
            _showConfirmModal();
        });
    }

    if (btnSaveFinal) {
        btnSaveFinal.addEventListener("click", function () {
            if (saveConfirmedEl) { saveConfirmedEl.value = "1"; }
            if (confirmSaveModal) { confirmSaveModal.hide(); }
            form.submit();
        });
    }

    if (btnTrigger) {
        btnTrigger.addEventListener("click", _onSaveTrigger);
    }
}

/*
 * Defer modal initialisation until Bootstrap is available.
 * form_entry_modal.js loads inside {% block content %}, before
 * bootstrap.bundle.min.js at the end of base.html. Wrapping in
 * DOMContentLoaded guarantees Bootstrap is ready when we call
 * new bootstrap.Modal(...).
 *
 * Diferir la inicializacion de modales hasta que Bootstrap este disponible.
 * form_entry_modal.js se carga dentro de {% block content %}, antes que
 * bootstrap.bundle.min.js al final de base.html. Envolver en
 * DOMContentLoaded garantiza que Bootstrap esta listo al llamar a
 * new bootstrap.Modal(...).
 */
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initModalFlow);
} else {
    _initModalFlow();
}

}());
