// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/form_entry_service.js
// H30 (S137). Casilla "Revisión" de cada tarea del parte.
// - ebServiceBlock(idx): HTML de la casilla para una tarea nueva, sacado
//   de la plantilla oculta #service-block-template (la pinta Django).
// - Marcar/desmarcar la casilla muestra u oculta sus campos.
// - Al elegir el aceite, si la próxima revisión está vacía, la propone:
//   horómetro de la tarea + 800 h (semisintético) o + 1200 h (sintético).
(function () {
    "use strict";

    var INTERVALS = {SYNTHETIC: 1200, SEMI_SYNTHETIC: 800};

    window.ebServiceBlock = function (idx) {
        var tpl = document.getElementById("service-block-template");
        return tpl ? tpl.innerHTML.split("__IDX__").join(String(idx)) : "";
    };

    document.addEventListener("change", function (ev) {
        var el = ev.target;
        if (el.classList.contains("service-toggle")) {
            var box = document.getElementById(
                "service-fields-" + el.dataset.blockIdx);
            if (box) {
                box.classList.toggle("d-none", !el.checked);
            }
            return;
        }
        if (el.classList.contains("service-oil-type")) {
            var idx = el.dataset.blockIdx;
            var next = document.getElementById(
                "id_entrada_" + idx + "_service_next_hours");
            var meter = document.querySelector(
                'input[name="entrada_' + idx + '_engine_hours_reading"]');
            var step = INTERVALS[el.value];
            if (next && !next.value && meter && meter.value && step) {
                next.value = Math.round(parseFloat(meter.value) + step);
            }
        }
    });
}());
