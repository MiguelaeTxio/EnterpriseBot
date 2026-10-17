/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/form_entry_clock.js
 *
 * H24 (S129). Parte form and clock-in: shows the clocked stretches of
 * the chosen day, pre-fills the tasks with them on a fresh form and
 * locks the clocked times (they are not editable). The server checks
 * everything again (hr_calendar/clock_parts.py); this only helps.
 *
 * H24 (S129). Formulario de partes y fichajes: muestra los tramos
 * fichados del día elegido, rellena con ellos las tareas en un parte
 * nuevo y bloquea las horas fichadas (no se pueden cambiar). El
 * servidor lo vuelve a comprobar todo (hr_calendar/clock_parts.py);
 * esto solo ayuda.
 */
(function () {
    "use strict";
    var cfg = window.EB_CONFIG || {};
    var dateInput = document.getElementById("id_fecha");
    var banner = document.getElementById("clock-stretches-banner");
    var form = document.getElementById("form-entry");
    if (!cfg.clockStretchesUrl || !dateInput || !banner || !form) { return; }

    var stretches = [];
    var editInput = form.querySelector('[name="edit_wo_pk"]');
    var inProgress = form.querySelector('[name="in_progress_wo_pk"]');

    function field(name) { return form.querySelector('[name="' + name + '"]'); }

    function blockCount() {
        var n = document.getElementById("num-entradas-input");
        return n ? (parseInt(n.value, 10) || 1) : 1;
    }

    // Un parte "en blanco": una sola tarea sin máquina, ni edición ni
    // parte en curso -- solo entonces se rellenan las tareas solas.
    function isFresh() {
        if (editInput || inProgress) { return false; }
        if (blockCount() !== 1) { return false; }
        var machine = field("entrada_1_machine_raw");
        return !machine || !machine.value.trim();
    }

    function setValue(input, value) {
        if (!input) { return; }
        input.value = value;
        input.dispatchEvent(new Event("tp:sync"));
    }

    function lockInput(input, locked, title) {
        if (!input) { return; }
        input.readOnly = locked;
        input.classList.toggle("bg-light", locked);
        input.classList.toggle("eb-clock-locked", locked);
        if (locked) {
            input.setAttribute("step", "60");
            input.title = title;
        } else if (input.classList.contains("eb-was-locked")) {
            input.setAttribute("step", "1800");
            input.title = "";
        }
        input.classList.toggle("eb-was-locked", locked);
    }

    // Fija la entrada (hora de inicio de la tarea que empieza a la hora
    // fichada). La salida fichada se fija en la última tarea del tramo
    // solo si el tramo tiene más de una tarea: con una sola, su hora de
    // fin se puede mover (de 8:30 a 12:30 si la salida es a las 13:00) y
    // entonces aparece sola la tarea que cubre hasta la salida.
    function applyLocks() {
        var tasks = [];
        for (var i = 1; i <= blockCount(); i++) {
            var hc = field("entrada_" + i + "_hc");
            var hf = field("entrada_" + i + "_hf");
            if (hc || hf) { tasks.push({hc: hc, hf: hf}); }
            lockInput(hc, false, "");
            lockInput(hf, false, "");
        }
        stretches.forEach(function (s) {
            var inside = tasks.filter(function (t) {
                var v = t.hc ? t.hc.value : "";
                return v && (!s.start || v >= s.start) && (!s.end || v < s.end);
            });
            if (!inside.length) { return; }
            inside.forEach(function (t) {
                if (s.start && t.hc.value === s.start) {
                    lockInput(t.hc, true, "Hora de entrada fichada: no se puede cambiar.");
                }
            });
            var last = inside.reduce(function (a, b) { return b.hc.value > a.hc.value ? b : a; });
            if (s.end && inside.length > 1 && last.hf && last.hf.value === s.end) {
                lockInput(last.hf, true, "Hora de salida fichada: no se puede cambiar.");
            }
        });
    }

    function setLunch(lunch) {
        var lbStart = document.getElementById("id_lunch_break_start");
        var lbEnd = document.getElementById("id_lunch_break_end");
        var noLunchCb = document.getElementById("id_no_lunch_toggle");
        var hadLunchCb = document.getElementById("id_had_lunch_toggle");
        if (lunch) {
            setValue(lbStart, lunch.start);
            setValue(lbEnd, lunch.end);
            if (noLunchCb) { noLunchCb.checked = false; noLunchCb.dispatchEvent(new Event("change")); }
            if (hadLunchCb) { hadLunchCb.checked = true; hadLunchCb.dispatchEvent(new Event("change")); }
        } else {
            if (noLunchCb) { noLunchCb.checked = true; noLunchCb.dispatchEvent(new Event("change")); }
            if (hadLunchCb) { hadLunchCb.checked = false; hadLunchCb.dispatchEvent(new Event("change")); }
        }
    }

    function prefill(lunch) {
        var addBtn = document.getElementById("btn-add-block");
        stretches.forEach(function (s, i) {
            var idx = i + 1;
            if (idx > blockCount()) {
                if (!addBtn) { return; }
                addBtn.click();
            }
            var hc = field("entrada_" + idx + "_hc");
            var hf = field("entrada_" + idx + "_hf");
            if (hc && s.start) { setValue(hc, s.start); }
            setValue(hf, s.end || "");
        });
        setLunch(lunch);
    }

    // Sin la salida fichada el parte no se puede cerrar (solo guardar
    // tareas): se desactiva "Cerrar parte" y se explica por qué.
    function applyCloseBlock(blockers) {
        var closeBtn = document.getElementById("btn-form-submit");
        var note = document.getElementById("clock-close-note");
        if (closeBtn) {
            closeBtn.disabled = blockers.length > 0;
            closeBtn.title = blockers.join(" ");
        }
        if (!note && closeBtn && closeBtn.parentNode) {
            note = document.createElement("div");
            note.id = "clock-close-note";
            note.className = "small text-warning-emphasis text-end mb-2";
            var row = closeBtn.parentNode;
            row.parentNode.insertBefore(note, row);
        }
        if (note) { note.textContent = blockers.join(" "); }
    }

    function render(data) {
        stretches = data.stretches || [];
        applyCloseBlock(data.close_blockers || []);
        if (!stretches.length) {
            banner.classList.add("d-none");
            banner.textContent = "";
            applyLocks();
            return;
        }
        var parts = stretches.map(function (s) {
            return (s.start || "?") + "–" + (s.end || "sin salida todavía");
        });
        banner.innerHTML = "";
        var strong = document.createElement("strong");
        strong.textContent = "Fichajes de este día: " + parts.join(" · ") + ". ";
        banner.appendChild(strong);
        banner.appendChild(document.createTextNode(
            "Las horas fichadas no se pueden cambiar: la primera tarea de cada tramo empieza a la entrada, " +
            "la última termina a la salida y, al cerrar el parte, todo lo fichado tiene que tener tarea." +
            (data.lunch ? " El hueco entre tramos es la pausa de comida." : "")
        ));
        banner.classList.remove("d-none");
        if (isFresh()) { prefill(data.lunch); }
        applyLocks();
    }

    function load() {
        if (!dateInput.value) { render({stretches: [], close_blockers: []}); return; }
        var params = new URLSearchParams({fecha: dateInput.value});
        if (editInput && editInput.value) { params.set("wo_pk", editInput.value); }
        fetch(cfg.clockStretchesUrl + "?" + params.toString(), {credentials: "same-origin"})
            .then(function (r) { return r.ok ? r.json() : {stretches: []}; })
            .then(render)
            .catch(function () { /* sin fichajes a la vista: el servidor comprueba igual */ });
    }

    function toMin(v) { var p = (v || "").split(":"); return p.length < 2 ? NaN : (+p[0]) * 60 + (+p[1]); }

    // Si la última tarea de un tramo termina antes de la salida fichada,
    // se añade la tarea que va de ahí a la salida (Miguel Ángel: "si
    // acabó una tarea a las 13:30 es obligatorio una tarea de 13:30 a
    // 14"). Las horas que no son de fichaje siguen siendo editables.
    function fillToClockOut(changed) {
        var v = changed.value;
        if (!v) { return; }
        var stretch = stretches.find(function (s) {
            return s.end && (!s.start || v > s.start) && v < s.end;
        });
        if (!stretch) { return; }
        for (var i = 1; i <= blockCount(); i++) {
            var hc = field("entrada_" + i + "_hc");
            if (hc && hc.value && hc.value >= v && hc.value < stretch.end) { return; }
        }
        if (toMin(stretch.end) - toMin(v) <= 0) { return; }
        var addBtn = document.getElementById("btn-add-block");
        if (!addBtn) { return; }
        addBtn.click();
        var idx = blockCount();
        var newHc = field("entrada_" + idx + "_hc");
        var newHf = field("entrada_" + idx + "_hf");
        setValue(newHc, v);
        setValue(newHf, stretch.end);
        applyLocks();
    }

    form.addEventListener("change", function (e) {
        if (e.target && /^entrada_\d+_hf$/.test(e.target.name || "") && stretches.length) {
            fillToClockOut(e.target);
        }
    });

    dateInput.addEventListener("change", load);
    form.addEventListener("input", function (e) {
        if (e.target && /^entrada_\d+_h[cf]$/.test(e.target.name || "")) { applyLocks(); }
    });
    var extra = document.getElementById("extra-blocks-container");
    if (extra && window.MutationObserver) {
        new MutationObserver(applyLocks).observe(extra, {childList: true});
    }
    load();
}());
