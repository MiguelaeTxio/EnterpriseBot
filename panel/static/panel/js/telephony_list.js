// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/telephony_list.js
//
// S155 (invasora H03). Comportamiento común de los listados de Telefonía
// y Secciones (panel/telephony_lists.py, plantilla
// panel/telephony_lists/page.html), con el formato único (directrices
// 4.24 y 4.27) y el mismo funcionamiento que Usuarios:
// - Selección (pk -> etiqueta) que sobrevive a filtros, orden y
//   repintados, guardada por usuario (EbNavState, directriz 4.15), con
//   su visor "Selección actual" y "Mostrar solo la selección actual".
// - Filtros de casillas con semántica literal: todas marcadas = "",
//   ninguna = "none", si no, las marcadas separadas por comas.
// - Acciones masivas con la confirmación común (EbMassConfirm) y el
//   aviso de la respuesta (cabecera X-List-Message).
// "Solo los filtrados" (select_filtered.js) y "Ampliar"
// (list_fullscreen.js, desde _fixed_list_layout.html) se enganchan
// solos por los ids {prefijo}-mass-clear / -mass-count / -check-all.
(function () {
    "use strict";

    var root = document.querySelector("[data-screen-key][data-prefix]");
    if (!root) { return; }
    var p = root.dataset.prefix;
    var screenKey = root.dataset.screenKey;
    var actionUrl = root.dataset.actionUrl;
    var noun = root.dataset.noun || "elemento(s)";
    var results = document.getElementById(p + "-results");
    var filters = document.getElementById(p + "-filters");
    var byId = function (suffix) { return document.getElementById(p + suffix); };

    var selection = new Map();
    try {
        JSON.parse(document.getElementById("tl-saved-selection").textContent)
            .forEach(function (item) {
                if (item && item.pk) { selection.set(String(item.pk), item.label || ""); }
            });
    } catch (e) { /* estado guardado ilegible: sin selección */ }

    var lastSaved = null;
    function saveSelection() {
        var payload = Array.from(selection.entries()).map(function (entry) {
            return {pk: entry[0], label: entry[1]};
        });
        var serialized = JSON.stringify(payload);
        if (serialized === lastSaved) { return; }
        lastSaved = serialized;
        if (window.EbNavState) { window.EbNavState.save(screenKey, {selection: payload}); }
    }

    function updateSelectionUi() {
        saveSelection();
        byId("-mass-count").textContent = selection.size;
        byId("-selection-count").textContent = selection.size;
        var list = byId("-selection-list");
        list.innerHTML = "";
        var names = Array.from(selection.values()).sort(function (a, b) { return a.localeCompare(b); });
        if (!names.length) {
            var empty = document.createElement("li");
            empty.className = "text-muted";
            empty.textContent = "Nada seleccionado todavía.";
            list.appendChild(empty);
        }
        names.forEach(function (name) {
            var li = document.createElement("li");
            li.textContent = name;
            list.appendChild(li);
        });
        var idsInput = byId("-selected-ids");
        var newIds = Array.from(selection.keys()).join(",");
        if (idsInput.value !== newIds) {
            idsInput.value = newIds;
            if (byId("-only-selected").checked) { htmx.trigger(filters, p + "-selection-refresh"); }
        }
        var all = byId("-check-all");
        if (!all) { return; }
        var rows = results.querySelectorAll("." + p + "-row-check");
        var checked = results.querySelectorAll("." + p + "-row-check:checked");
        all.checked = rows.length > 0 && checked.length === rows.length;
        all.indeterminate = checked.length > 0 && checked.length < rows.length;
    }

    function refreshFromFragment() {
        var state = byId("-fragment-state");
        if (state) {
            byId("-row-count").textContent = state.dataset.count;
            byId("-clear-sort").classList.toggle("d-none", !state.dataset.sortActive);
        }
        results.querySelectorAll("." + p + "-row-check").forEach(function (cb) {
            cb.checked = selection.has(cb.dataset.pk);
        });
        updateSelectionUi();
    }

    // Filtros de casillas: semántica literal.
    filters.querySelectorAll(".tl-group").forEach(function (group) {
        var boxes = Array.from(group.querySelectorAll(".tl-group-check"));
        var input = group.querySelector(".tl-group-input");
        boxes.forEach(function (box) {
            box.addEventListener("change", function () {
                var marked = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
                input.value = marked.length === boxes.length ? "" : (marked.length ? marked.join(",") : "none");
            });
        });
    });

    results.addEventListener("change", function (evt) {
        var target = evt.target;
        if (target.classList.contains(p + "-row-check")) {
            if (target.checked) { selection.set(target.dataset.pk, target.dataset.label); }
            else { selection.delete(target.dataset.pk); }
            updateSelectionUi();
        } else if (target.id === p + "-check-all") {
            results.querySelectorAll("." + p + "-row-check").forEach(function (cb) {
                cb.checked = target.checked;
                if (target.checked) { selection.set(cb.dataset.pk, cb.dataset.label); }
                else { selection.delete(cb.dataset.pk); }
            });
            updateSelectionUi();
        }
    });

    byId("-mass-clear").addEventListener("click", function () {
        selection.clear();
        refreshFromFragment();
    });

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    function showToast(text, danger) {
        var toast = byId("-toast");
        toast.classList.toggle("text-bg-danger", !!danger);
        toast.classList.toggle("text-bg-dark", !danger);
        byId("-toast-msg").textContent = text;
        new bootstrap.Toast(toast).show();
    }
    function visibleIds() {
        return Array.from(results.querySelectorAll("." + p + "-row-check")).map(function (cb) { return cb.dataset.pk; });
    }

    async function runAction(action, question) {
        if (!selection.size) { showToast("Marca algo en la lista.", true); return; }
        if (!(await window.EbMassConfirm({
            action: question, noun: noun, names: Array.from(selection.values()),
            hidden: window.EbHiddenSelected(selection, visibleIds()),
        }))) { return; }
        var body = new FormData();
        new FormData(filters).forEach(function (value, key) { body.append("_f_" + key, value); });
        var sortInput = results.querySelector("#" + p + '-sort-inputs input[name="sort"]');
        body.append("_f_sort", sortInput ? sortInput.value : "");
        body.append("action", action);
        selection.forEach(function (_label, pk) { body.append("selected", pk); });
        fetch(actionUrl, {
            method: "POST", headers: {"X-CSRFToken": csrfMeta ? csrfMeta.content : ""}, body: body,
        }).then(function (r) {
            if (!r.ok) { showToast("No se ha podido guardar (" + r.status + ").", true); return; }
            var message = r.headers.get("X-List-Message");
            var isError = r.headers.get("X-List-Error") === "1";
            return r.text().then(function (html) {
                results.innerHTML = html;
                htmx.process(results);
                refreshFromFragment();
                if (message) { showToast(decodeURIComponent(message), isError); }
            });
        }).catch(function () {
            showToast("Sin conexión con el servidor: no se ha guardado nada.", true);
        });
    }
    root.querySelectorAll("[data-tl-action]").forEach(function (button) {
        button.addEventListener("click", function () {
            runAction(button.dataset.tlAction, button.dataset.tlQuestion);
        });
    });

    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (evt.detail.target && evt.detail.target.id === p + "-results") { refreshFromFragment(); }
    });

    refreshFromFragment();
}());
