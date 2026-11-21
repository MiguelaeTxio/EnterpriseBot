/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/context_menu.js
 *
 * Menú propio del botón derecho en TODO el panel (pieza común, cargada
 * en panel/base.html; directriz 4.27 del documento maestro).
 *
 * Origen: H24 (S144), menú sobre un trabajador (antes person_menu.js).
 * Ampliado en S163 (invasora UX). Miguel Ángel: "ya teníamos
 * implementado que con el botón derecho teníamos un menú [...] cuando
 * creamos vistas nuevas [...] ya desaparece". Para que ninguna vista
 * nueva se quede sin él, no hay que hacer nada en cada vista: se abre
 * solo sobre
 *   1. un trabajador: enlace a su ficha (/panel/documentacion/personal/
 *      <pk>/) o a sus fichajes, o un elemento con data-person-pk;
 *   2. un centro de gasto: enlace a su ficha o a cualquiera de sus
 *      páginas (/panel/documentacion/maquinaria/<pk>/...), o un elemento
 *      con data-machine-pk;
 *   3. cualquier fila de un listado: si la fila tiene menú de tres
 *      puntos (directriz 4.24, punto 9), sus mismas acciones; si en la
 *      fila hay un trabajador o un centro de gasto, también su menú.
 * Las entradas de trabajador y máquina las da el servidor
 * (panel/views_person_menu.py, panel/views_machine_menu.py): solo lo
 * que ese usuario puede abrir. Con Mayúsculas pulsada, sobre casillas
 * de texto o con texto seleccionado sale el menú normal del navegador.
 *
 * El botón de tres puntos común (panel/_entity_menu_button.html, clase
 * eb-entity-menu-btn) abre el mismo menú.
 *
 * EbMachineCard.open(url): ventana con la tarjeta técnica de un centro
 * de gasto (panel/machine_card/_card.html). Un clic normal en un
 * elemento con data-machine-card="<url>" la abre (Ctrl/Cmd/rueda: lo
 * de siempre del enlace).
 */
(function () {
    "use strict";

    const PERSON_PATTERNS = [
        /^\/panel\/documentacion\/personal\/(\d+)\/$/,
        /^\/panel\/documentacion\/fichajes\/(\d+)\/jornadas\/$/,
    ];
    const MACHINE_PATTERN = /^\/panel\/documentacion\/maquinaria\/(\d+)\//;
    let menu = null;

    function pathOf(link) {
        try { return new URL(link.href, window.location.href).pathname; } catch (e) { return ""; }
    }

    // Entidad (trabajador o máquina) de un elemento concreto, o null.
    function entityOfElement(el) {
        if (!el) return null;
        if (el.dataset && /^\d+$/.test(el.dataset.personPk || "")) return {kind: "person", pk: el.dataset.personPk};
        if (el.dataset && /^\d+$/.test(el.dataset.machinePk || "")) return {kind: "machine", pk: el.dataset.machinePk};
        if (el.tagName !== "A" || !el.getAttribute("href")) return null;
        const path = pathOf(el);
        for (const re of PERSON_PATTERNS) {
            const m = path.match(re);
            if (m) return {kind: "person", pk: m[1]};
        }
        const m = path.match(MACHINE_PATTERN);
        return m ? {kind: "machine", pk: m[1]} : null;
    }

    // La entidad bajo el puntero, subiendo por sus contenedores.
    function entityOf(target) {
        let el = target;
        while (el && el !== document.body) {
            const found = entityOfElement(el);
            if (found) return found;
            el = el.parentElement;
        }
        return null;
    }

    // La primera entidad de una fila (para el clic derecho en cualquier
    // parte de ella).
    function entityOfRow(row) {
        if (!row) return null;
        const candidates = row.querySelectorAll("[data-person-pk], [data-machine-pk], a[href]");
        for (const el of candidates) {
            if (el.closest(".dropdown-menu")) continue;
            const found = entityOfElement(el);
            if (found) return found;
        }
        return null;
    }

    // Acciones del menú de tres puntos de la fila (sus elementos reales).
    function rowActions(row) {
        if (!row) return [];
        const list = row.querySelector(".dropdown-menu");
        // Un menú de tres puntos que ya es el de la máquina o el
        // trabajador de la fila (data-eb-entity-menu) no se repite.
        if (!list || list.hasAttribute("data-eb-entity-menu")) return [];
        return Array.from(list.querySelectorAll(".dropdown-item, .dropdown-divider, .dropdown-header"));
    }

    function close() {
        if (menu) { menu.remove(); menu = null; }
    }

    function place(el, x, y) {
        const w = el.offsetWidth, h = el.offsetHeight;
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

    function serverItem(item, entity, name) {
        const a = document.createElement("a");
        a.className = "dropdown-item";
        a.href = item.url;
        const icon = document.createElement("i");
        icon.className = "bi " + item.icon + " me-2";
        a.appendChild(icon);
        a.appendChild(document.createTextNode(item.label));
        // S163: en la nueva interfaz (EbEntityOpen), las entradas que
        // tienen pestaña allí (ficha, vacaciones, revisiones...) se abren
        // en la misma vista, nunca en la ficha de acordeones.
        if (entity && window.EbEntityOpen) {
            a.addEventListener("click", function (ev) {
                if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
                if (!window.EbEntityOpen(entity.kind, entity.pk, name, item.code)) return;
                ev.preventDefault();
                ev.stopImmediatePropagation();
                close();
            });
        }
        if (item.card) {
            a.addEventListener("click", function (ev) {
                if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
                ev.preventDefault();
                close();
                window.EbMachineCard.open(item.url);
            });
        }
        return a;
    }

    // Copia de una acción de la fila: al pulsarla, se pulsa la original
    // (enlace, ventana de Bootstrap, htmx o función de la página).
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
        menu.className = "dropdown-menu show shadow eb-context-menu";
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
        if (!entity) {
            addRowActions(current, actions);
            place(current, x, y);
            return;
        }
        const loading = document.createElement("span");
        loading.className = "dropdown-item-text small text-muted";
        loading.textContent = "Cargando…";
        current.appendChild(loading);
        const url = entity.kind === "person"
            ? "/panel/documentacion/personal/" + entity.pk + "/menu/"
            : "/panel/documentacion/maquinaria/" + entity.pk + "/menu/";
        fetch(url, {credentials: "same-origin"})
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (data) {
                if (menu !== current) return;
                current.innerHTML = "";
                current.appendChild(header(data.name));
                data.items.forEach(function (item) { current.appendChild(serverItem(item, entity, data.name)); });
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
        const t = ev.target;
        if (t.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], .eb-context-menu")) return true;
        const sel = window.getSelection ? window.getSelection() : null;
        return !!(sel && !sel.isCollapsed && sel.toString().trim());
    }

    document.addEventListener("contextmenu", function (ev) {
        if (wantsNativeMenu(ev)) return;
        const row = ev.target.closest("tbody tr");
        const entity = entityOf(ev.target) || entityOfRow(row);
        const actions = rowActions(row);
        if (!entity && !actions.length) return;
        ev.preventDefault();
        open(entity, actions, ev.clientX, ev.clientY);
    });
    document.addEventListener("click", function (ev) {
        if (menu && !menu.contains(ev.target)) close();
    }, true);
    // Botón de tres puntos común de las filas (panel/_entity_menu_button.html):
    // el mismo menú, debajo del botón.
    document.addEventListener("click", function (ev) {
        const button = ev.target.closest(".eb-entity-menu-btn");
        if (!button) return;
        ev.preventDefault();
        const entity = entityOfElement(button);
        if (!entity) return;
        const rect = button.getBoundingClientRect();
        open(entity, [], rect.left, rect.bottom + 2);
    });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") close(); });
    window.addEventListener("scroll", function (ev) {
        if (menu && !menu.contains(ev.target)) close();
    }, true);
    window.addEventListener("resize", close);

    // ---- Tarjeta técnica de un centro de gasto (ventana) ----
    let cardModal = null;
    function cardElement() {
        if (cardModal) return cardModal;
        cardModal = document.createElement("div");
        cardModal.className = "modal fade";
        cardModal.id = "ebMachineCardModal";
        cardModal.tabIndex = -1;
        cardModal.innerHTML = '<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content"></div></div>';
        document.body.appendChild(cardModal);
        return cardModal;
    }
    window.EbMachineCard = {
        open: function (url) {
            const el = cardElement();
            const content = el.querySelector(".modal-content");
            content.innerHTML = '<div class="modal-body text-muted small">Cargando…</div>';
            window.bootstrap.Modal.getOrCreateInstance(el).show();
            fetch(url, {credentials: "same-origin"})
                .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
                .then(function (html) { content.innerHTML = html; })
                .catch(function () {
                    content.innerHTML = '<div class="modal-body text-danger small">No se ha podido cargar la tarjeta técnica.</div>';
                });
        },
    };
    document.addEventListener("click", function (ev) {
        const opener = ev.target.closest("[data-machine-card]");
        if (!opener || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
        ev.preventDefault();
        close();
        window.EbMachineCard.open(opener.dataset.machineCard);
    });
}());
