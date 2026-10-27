// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/form_entry_service.js
// H30 (S137). Casilla "Revisión" de cada tarea del parte.
// - ebServiceBlock(idx): HTML de la casilla para una tarea nueva, sacado
//   de la plantilla oculta #service-block-template (la pinta Django).
// - Marcar/desmarcar la casilla muestra u oculta sus campos.
// - "Del albarán": los repuestos pre-asignados a la máquina que ya salen
//   en la tarea (casillas entrada_N_consume_part_PK). Se pintan aquí como
//   espejo: marcar uno aquí es marcarlo como consumido en la tarea, y al
//   revés, así no se marca nada dos veces (Miguel Ángel, S137).
// - Al elegir el aceite, si la próxima revisión está vacía, la propone:
//   horómetro de la tarea + 800 h (semisintético) o + 1200 h (sintético);
//   en el motor de la grúa, con el horómetro de grúa.
// - Máquinas con horas de grúa (A con dos motores): se elige motor del
//   camión, de la grúa o los dos, cada uno con su aceite y su próxima
//   revisión. Se mira si la tarea enseña el horómetro de grúa, también
//   al cambiar de máquina.
(function () {
    "use strict";

    var INTERVALS = {SYNTHETIC: 1200, SEMI_SYNTHETIC: 800};

    window.ebServiceBlock = function (idx) {
        var tpl = document.getElementById("service-block-template");
        return tpl ? tpl.innerHTML.split("__IDX__").join(String(idx)) : "";
    };

    function partBoxes(idx) {
        var source = document.getElementById("ticket-resolution-" + idx);
        if (!source) {
            return [];
        }
        return Array.prototype.slice.call(source.querySelectorAll(
            'input[type="checkbox"][name^="entrada_' + idx +
            '_consume_part_"]'));
    }

    function partLabel(box) {
        var label = document.querySelector('label[for="' + box.id + '"]');
        return label ? label.textContent.trim() : box.name;
    }

    function renderAlbaran(idx) {
        var target = document.getElementById("service-albaran-" + idx);
        if (!target) {
            return;
        }
        var boxes = partBoxes(idx);
        target.innerHTML = "";
        if (!boxes.length) {
            target.innerHTML = '<span class="text-muted">Esta máquina no ' +
                'tiene repuestos de albarán pendientes.</span>';
            return;
        }
        boxes.forEach(function (box) {
            var wrap = document.createElement("div");
            wrap.className = "form-check";
            var mirror = document.createElement("input");
            mirror.type = "checkbox";
            mirror.className = "form-check-input service-albaran-mirror";
            mirror.id = "service-mirror-" + box.id;
            mirror.checked = box.checked;
            mirror.dataset.source = box.id;
            var label = document.createElement("label");
            label.className = "form-check-label";
            label.htmlFor = mirror.id;
            label.textContent = partLabel(box);
            wrap.appendChild(mirror);
            wrap.appendChild(label);
            target.appendChild(wrap);
        });
    }

    function craneVisible(idx) {
        var meter = document.querySelector(
            '.meter-crane[data-block-idx="' + idx + '"]');
        return !!meter && !meter.classList.contains("d-none");
    }

    function syncEngines(idx) {
        var engines = document.getElementById("service-engines-" + idx);
        if (!engines) {
            return;
        }
        var crane = craneVisible(idx);
        var truckBox = document.getElementById(
            "id_entrada_" + idx + "_service_truck");
        var craneBox = document.getElementById(
            "id_entrada_" + idx + "_service_crane");
        engines.classList.toggle("d-none", !crane);
        engines.querySelector(".service-engine-choice").disabled = !crane;
        var truck = document.getElementById("service-truck-" + idx);
        truck.classList.toggle("d-none", crane && !truckBox.checked);
        truck.querySelector(".service-engine-title").classList.toggle(
            "d-none", !crane);
        document.getElementById("service-crane-" + idx).classList.toggle(
            "d-none", !(crane && craneBox.checked));
    }

    function toggleFields(toggle) {
        var idx = toggle.dataset.blockIdx;
        var box = document.getElementById("service-fields-" + idx);
        if (box) {
            box.classList.toggle("d-none", !toggle.checked);
        }
        if (toggle.checked) {
            renderAlbaran(idx);
            syncEngines(idx);
        }
    }

    document.addEventListener("change", function (ev) {
        var el = ev.target;
        if (el.classList.contains("service-toggle")) {
            toggleFields(el);
            return;
        }
        if (el.classList.contains("service-engine")) {
            syncEngines(el.dataset.blockIdx);
            return;
        }
        if (el.classList.contains("service-albaran-mirror")) {
            var source = document.getElementById(el.dataset.source);
            if (source) {
                source.checked = el.checked;
                source.dispatchEvent(new Event("change", {bubbles: true}));
            }
            return;
        }
        var match = /^entrada_(\d+)_consume_part_\d+$/.exec(el.name || "");
        if (match) {
            var mirror = document.getElementById("service-mirror-" + el.id);
            if (mirror) {
                mirror.checked = el.checked;
            }
            return;
        }
        if (el.classList.contains("service-oil-type")) {
            var idx = el.dataset.blockIdx;
            var onCrane = el.dataset.engine === "crane";
            var next = document.getElementById(
                "id_entrada_" + idx + (onCrane ? "_service_crane_next_hours"
                                       : "_service_next_hours"));
            var meter = document.querySelector(
                'input[name="entrada_' + idx + (onCrane
                    ? '_crane_hours_reading"]'
                    : '_engine_hours_reading"]'));
            var step = INTERVALS[el.value];
            if (next && !next.value && meter && meter.value && step) {
                next.value = Math.round(parseFloat(meter.value) + step);
            }
        }
    });

    // La lista de repuestos de la tarea llega por HTMX al elegir la
    // máquina: se vuelve a pintar el espejo si la revisión está marcada.
    document.addEventListener("htmx:afterSwap", function (ev) {
        var match = /^ticket-resolution-(\d+)$/.exec(
            (ev.detail && ev.detail.target && ev.detail.target.id) || "");
        if (!match) {
            return;
        }
        var toggle = document.getElementById(
            "id_entrada_" + match[1] + "_is_service");
        if (toggle && toggle.checked) {
            renderAlbaran(match[1]);
        }
    });

    // Al elegir otra máquina, la tarea enseña u oculta el horómetro de
    // grúa (form_entry_assets.js): se rehace la elección de motor.
    var observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            var el = mutation.target;
            if (el.classList && el.classList.contains("meter-crane")) {
                syncEngines(el.dataset.blockIdx);
            }
        });
    });

    document.addEventListener("DOMContentLoaded", function () {
        observer.observe(document.body, {
            attributes: true, attributeFilter: ["class"], subtree: true,
        });
        document.querySelectorAll(".service-toggle:checked").forEach(
            toggleFields);
    });
}());
