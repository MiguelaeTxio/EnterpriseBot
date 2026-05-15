/*
 * gap_resolution.js — Gate 4 gap resolution UI.
 *
 * Handles two card types:
 *   1. Standard gaps (GAP / LATE_START / EARLY_END): shows/hides the note
 *      field based on the requires_note flag of the selected AbsenceCategory.
 *      The "Volver y editar" button (type=button) triggers a confirm() dialog
 *      and submits the form programmatically on acceptance, bypassing the
 *      browser's native required-field validation on the gap selects.
 *   2. LUNCH_BREAK gaps: shows lunch_time_wrapper when radio=yes; shows
 *      lunch_note_wrapper (required) when radio=no.
 * Validates all required fields before allowing form submission.
 *
 * gap_resolution.js — UI de resolución de lagunas Gate 4.
 *
 * Gestiona dos tipos de tarjeta:
 *   1. Lagunas estándar (GAP / LATE_START / EARLY_END): muestra/oculta el
 *      campo de nota según el flag requires_note de la AbsenceCategory.
 *      El botón "Volver y editar" (type=button) lanza un confirm() y envía
 *      el formulario programáticamente al aceptar, evitando la validación
 *      nativa del browser sobre los selects requeridos.
 *   2. Lagunas LUNCH_BREAK: muestra lunch_time_wrapper si radio=sí; muestra
 *      lunch_note_wrapper (obligatorio) si radio=no.
 * Valida todos los campos requeridos antes de permitir el envío del formulario.
 */
(function () {
    "use strict";

    /**
     * Toggles the visibility and required attribute of the note field
     * for a standard gap based on the selected category's requires_note flag.
     * Uses classList (d-none) instead of style.display for Bootstrap compat.
     * ---
     * Activa/desactiva la visibilidad y el atributo required del campo de
     * nota para una laguna estándar según el flag requires_note de la categoría.
     * Usa classList (d-none) en lugar de style.display para compatibilidad Bootstrap.
     *
     * @param {HTMLSelectElement} selectEl - The category select element.
     */
    function toggleNoteField(selectEl) {
        var gapPk       = selectEl.getAttribute("data-gap-pk");
        var wrapper     = document.getElementById("note_wrapper_" + gapPk);
        var noteField   = document.getElementById("gap_" + gapPk + "_note");
        var selectedOpt = selectEl.options[selectEl.selectedIndex];

        if (!wrapper || !noteField) { return; }

        var requiresNote = selectedOpt &&
                           selectedOpt.getAttribute("data-requires-note") === "true";

        if (requiresNote) {
            wrapper.classList.remove("d-none");
            noteField.required = true;
        } else {
            wrapper.classList.add("d-none");
            noteField.required = false;
            noteField.value    = "";
        }
    }

    /**
     * Toggles lunch_time_wrapper and lunch_note_wrapper visibility based on
     * the selected lunch radio (yes/no) for a LUNCH_BREAK gap card.
     * Radio=yes → show time field, hide note field.
     * Radio=no  → hide time field, show note field (required).
     * ---
     * Activa/desactiva lunch_time_wrapper y lunch_note_wrapper según el radio
     * seleccionado (sí/no) para una tarjeta de laguna LUNCH_BREAK.
     * Radio=sí → muestra campo hora, oculta campo nota.
     * Radio=no → oculta campo hora, muestra campo nota (obligatorio).
     *
     * @param {HTMLInputElement} radioEl - The triggered radio input element.
     */
    function toggleLunchFields(radioEl) {
        var gapPk       = radioEl.getAttribute("data-gap-pk");
        var timeWrapper = document.getElementById("lunch_time_wrapper_" + gapPk);
        var noteWrapper = document.getElementById("lunch_note_wrapper_" + gapPk);
        var timeInput   = document.getElementById("gap_" + gapPk + "_lunch_time");
        var noteField   = document.getElementById("gap_" + gapPk + "_lunch_note");

        if (!timeWrapper || !noteWrapper) { return; }

        if (radioEl.value === "yes") {
            /* Radio = sí: mostrar hora, ocultar nota */
            timeWrapper.classList.remove("d-none");
            noteWrapper.classList.add("d-none");
            if (noteField) {
                noteField.required = false;
                noteField.value    = "";
            }
        } else {
            /* Radio = no: ocultar hora, mostrar nota obligatoria */
            timeWrapper.classList.add("d-none");
            noteWrapper.classList.remove("d-none");
            if (timeInput) {
                timeInput.value = "";
            }
            if (noteField) {
                noteField.required = true;
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {

        /* --- Standard gap selects --- */
        /* --- Selectores de laguna estándar --- */
        var selects = document.querySelectorAll(".gap-category-select");
        selects.forEach(function (sel) {
            toggleNoteField(sel);
            sel.addEventListener("change", function () {
                toggleNoteField(sel);
            });
        });

        /* --- LUNCH_BREAK radios --- */
        /* --- Radios de pausa de comida --- */
        var lunchRadios = document.querySelectorAll(".lunch-had-radio");
        lunchRadios.forEach(function (radio) {
            /* Initialise state for pre-checked radios (e.g. after POST error). */
            /* Inicializar estado para radios pre-marcados (p.ej. tras error POST). */
            if (radio.checked) {
                toggleLunchFields(radio);
            }
            radio.addEventListener("change", function () {
                toggleLunchFields(radio);
            });
        });

        /* --- "Volver y editar" button — type=button bypasses required       --- */
        /* --- validation; confirm() is shown before programmatic submit.     --- */
        /* --- Botón "Volver y editar" — type=button evita la validación      --- */
        /* --- required; confirm() se muestra antes del submit programático.  --- */
        var backBtn = document.getElementById("btnBackToForm");
        var form    = document.getElementById("formGapResolution");

        if (backBtn && form) {
            backBtn.addEventListener("click", function () {
                if (!confirm("\u00bfDescartar el parte y volver al formulario para corregir las horas?")) {
                    return;
                }
                /* Inject back_to_form field dynamically and submit.          */
                /* form.submit() does not fire the submit event listener,     */
                /* so required-field validation is bypassed entirely.         */
                /* Inyectar el campo back_to_form dinámicamente y enviar.     */
                /* form.submit() no dispara el event listener de submit,      */
                /* por lo que la validación required se evita por completo.   */
                var hidden = document.createElement("input");
                hidden.type  = "hidden";
                hidden.name  = "back_to_form";
                hidden.value = "1";
                form.appendChild(hidden);
                form.submit();
            });
        }

        /* --- Client-side validation before submission --- */
        /* --- Validación client-side antes del envío --- */
        if (!form) { return; }

        form.addEventListener("submit", function (e) {

            var allValid = true;

            /* Validate standard gap selects — Validar selectores de laguna estándar */
            selects.forEach(function (sel) {
                if (!sel.value) {
                    sel.classList.add("is-invalid");
                    allValid = false;
                } else {
                    sel.classList.remove("is-invalid");
                }
            });

            /* Validate LUNCH_BREAK radios — Validar radios LUNCH_BREAK          */
            /* Group radios by gap pk and check at least one is selected.         */
            /* Agrupar radios por gap pk y verificar que al menos uno esté marcado. */
            var lunchGroups = {};
            lunchRadios.forEach(function (radio) {
                var pk = radio.getAttribute("data-gap-pk");
                if (!lunchGroups[pk]) {
                    lunchGroups[pk] = { hasChecked: false, radios: [] };
                }
                lunchGroups[pk].radios.push(radio);
                if (radio.checked) {
                    lunchGroups[pk].hasChecked = true;
                }
            });

            Object.keys(lunchGroups).forEach(function (pk) {
                var group = lunchGroups[pk];
                if (!group.hasChecked) {
                    group.radios.forEach(function (r) {
                        r.classList.add("is-invalid");
                    });
                    allValid = false;
                } else {
                    group.radios.forEach(function (r) {
                        r.classList.remove("is-invalid");
                    });
                }
            });

            if (!allValid) {
                e.preventDefault();
                /* Scroll to first invalid field — Desplazar al primer campo inválido */
                var firstInvalid = form.querySelector(".is-invalid");
                if (firstInvalid) {
                    firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }
        });
    });
}());
