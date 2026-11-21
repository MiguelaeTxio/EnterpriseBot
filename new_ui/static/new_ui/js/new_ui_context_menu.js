/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/static/new_ui/js/new_ui_context_menu.js
 *
 * Menú del botón derecho de la nueva interfaz (S163). Copia adaptada de
 * panel/static/panel/js/context_menu.js: la nueva interfaz no usa el de
 * la antigua. Se adelanta a él (fase de captura en window) solo dentro
 * de la nueva interfaz (#nui), así que el de la antigua no llega a
 * abrirse aquí y en el resto del panel no cambia nada.
 *
 * Sobre una persona o máquina (data-person-pk / data-machine-pk) da su
 * ficha y sus pestañas de la nueva interfaz (new_ui:menu, solo las que
 * ese usuario puede ver) y las abre aquí mismo (window.EbUiOpen, en
 * new_ui.js); sobre una fila con menú de tres puntos, también sus
 * acciones ("Esta fila"). Con Mayúsculas, sobre casillas de texto o con
 * texto seleccionado sale el menú normal del navegador.
 */
(function () {
    "use strict";

    let menu = null;

    function urls() {
        try { return JSON.parse(document.getElementById("nui-urls").textContent); } catch (e) { return {}; }
    }

    function entityOfElement(el) {
        if (!el || !el.dataset) return null;
        if (/^\d+$/.test(el.dataset.personPk || "")) return {kind: "person", pk: el.dataset.personPk};
        if (/^\d+$/.test(el.dataset.machinePk || "")) return {kind: "machine", pk: el.dataset.machinePk};
        return null;
    }

    function entityOf(target) {
        let el = target;
        while (el && el !== document.body) {
            const found = entityOfElement(el);
            if (found) return found;
            el = el.parentElement;
        }
        return null;
    }

    function entityOfRow(row) {
        if (!row) return null;
        for (const el of row.querySelectorAll("[data-person-pk], [data-machine-pk]")) {
            if (el.closest(".dropdown-menu")) continue;
            const found = entityOfElement(el);
            if (found) return found;
        }
        return null;
    }

    function rowActions(row) {
        if (!row) return [];
        const list = row.querySelector(".dropdown-menu");
        if (!list) return [];
        return Array.from(list.querySelectorAll(".dropdown-item, .dropdown-divider, .dropdown-header"));
    }

    function close() {
        if (menu) { menu.remove(); menu = null; }
    }

    function place(el, x, y) {
        const w = el.offsetWidth;
        const h = el.offsetHeight;
        el.style.left = Math.max(4, Math.min(x, window.innerWidth - w - 4)) + "px";
        el.style.top = Math.max(4, Math.min(y, window.innerHeight - h - 4)) + "px";
    }

    function header(text) {
        const h = document.createElement("h6");
        h.className = "dropdown-header";
        h.textContent = text;
        return h;
    }

    function divider() {
        const hr = document.createElement("hr");
        hr.className = "dropdown-divider";
        return hr;
    }

    function tabItem(item, entity, name) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dropdown-item";
        const icon = document.createElement("i");
        icon.className = "bi " + item.icon + " me-2";
        button.appendChild(icon);
        button.appendChild(document.createTextNode(item.label));
        button.addEventListener("click", function () {
            close();
            if (window.EbUiOpen) window.EbUiOpen(entity.kind, entity.pk, name, item.code);
        });
        return button;
    }

    function proxyItem(original) {
        if (original.classList.contains("dropdown-divider")) return divider();
        if (original.classList.contains("dropdown-header")) return header(original.textContent.trim());
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = original.className;
        copy.innerHTML = original.innerHTML;
        copy.disabled = original.disabled || original.classList.contains("disabled");
        copy.addEventListener("click", function () {
            close();
            original.click();
        });
        return copy;
    }

    function newMenu(x, y) {
        close();
        menu = document.createElement("div");
        menu.className = "dropdown-menu show shadow nui-context-menu";
        menu.style.position = "fixed";
        menu.style.zIndex = "2000";
        menu.style.maxHeight = "80vh";
        menu.style.overflowY = "auto";
        document.body.appendChild(menu);
        place(menu, x, y);
        return menu;
    }

    function addRowActions(target, actions) {
        if (!actions.length) return;
        if (target.childElementCount) target.appendChild(divider());
        target.appendChild(header("Esta fila"));
        actions.forEach(function (action) { target.appendChild(proxyItem(action)); });
    }

    function open(entity, actions, x, y) {
        const current = newMenu(x, y);
        const menuUrl = urls().menu;
        if (!entity || !menuUrl) {
            addRowActions(current, actions);
            place(current, x, y);
            return;
        }
        const loading = document.createElement("span");
        loading.className = "dropdown-item-text small text-muted";
        loading.textContent = "Cargando…";
        current.appendChild(loading);
        fetch(menuUrl + "?kind=" + entity.kind + "&pk=" + entity.pk, {credentials: "same-origin"})
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (data) {
                if (menu !== current) return;
                current.innerHTML = "";
                current.appendChild(header(data.name));
                data.items.forEach(function (item) { current.appendChild(tabItem(item, entity, data.name)); });
                addRowActions(current, actions);
                place(current, x, y);
            })
            .catch(function () {
                if (menu !== current) return;
                current.innerHTML = "";
                if (actions.length) {
                    addRowActions(current, actions);
                } else {
                    const err = document.createElement("span");
                    err.className = "dropdown-item-text small text-danger";
                    err.textContent = "No se ha podido cargar el menú.";
                    current.appendChild(err);
                }
                place(current, x, y);
            });
    }

    function wantsNativeMenu(ev) {
        if (ev.shiftKey) return true;
        if (ev.target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], .nui-context-menu")) return true;
        const sel = window.getSelection ? window.getSelection() : null;
        return !!(sel && !sel.isCollapsed && sel.toString().trim());
    }

    // Captura en window: antes que el menú de la antigua (document).
    window.addEventListener("contextmenu", function (ev) {
        if (!ev.target.closest || !ev.target.closest("#nui")) return;
        ev.stopPropagation();
        if (wantsNativeMenu(ev)) return;
        const row = ev.target.closest("tbody tr");
        const entity = entityOf(ev.target) || entityOfRow(row);
        const actions = rowActions(row);
        if (!entity && !actions.length) return;
        ev.preventDefault();
        open(entity, actions, ev.clientX, ev.clientY);
    }, true);
    document.addEventListener("click", function (ev) {
        if (menu && !menu.contains(ev.target)) close();
    }, true);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") close(); });
    window.addEventListener("scroll", function (ev) {
        if (menu && !menu.contains(ev.target)) close();
    }, true);
    window.addEventListener("resize", close);
})();
