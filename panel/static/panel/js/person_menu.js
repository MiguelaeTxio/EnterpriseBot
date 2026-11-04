/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/person_menu.js
 *
 * H24 (S144). Menú del botón derecho sobre un trabajador. Miguel Ángel:
 * "poder clicar con el derecho y que nos abriera un submenú para ir a
 * sitios de ese trabajador". Se abre sobre cualquier enlace a su ficha
 * (/panel/documentacion/personal/<pk>/), a su página de fichajes
 * (/panel/documentacion/fichajes/<pk>/jornadas/) o sobre un elemento
 * con data-person-pk. Las entradas las da el servidor
 * (panel/views_person_menu.py): solo las vistas que tiene ese
 * trabajador y que el usuario puede abrir. Con Mayúsculas pulsada sale
 * el menú normal del navegador (abrir en pestaña nueva, copiar enlace).
 */
(function () {
    "use strict";

    const PATTERNS = [
        /^\/panel\/documentacion\/personal\/(\d+)\/$/,
        /^\/panel\/documentacion\/fichajes\/(\d+)\/jornadas\/$/,
    ];
    let menu = null;

    function personOf(target) {
        const marked = target.closest("[data-person-pk]");
        if (marked && /^\d+$/.test(marked.dataset.personPk)) return marked.dataset.personPk;
        const link = target.closest("a[href]");
        if (!link) return null;
        let path;
        try { path = new URL(link.href, window.location.href).pathname; } catch (e) { return null; }
        for (const re of PATTERNS) {
            const m = path.match(re);
            if (m) return m[1];
        }
        return null;
    }

    function close() {
        if (menu) { menu.remove(); menu = null; }
    }

    function place(el, x, y) {
        const w = el.offsetWidth, h = el.offsetHeight;
        el.style.left = Math.max(4, Math.min(x, window.innerWidth - w - 4)) + "px";
        el.style.top = Math.max(4, Math.min(y, window.innerHeight - h - 4)) + "px";
    }

    function open(pk, x, y) {
        close();
        menu = document.createElement("div");
        menu.className = "dropdown-menu show shadow eb-person-menu";
        menu.style.position = "fixed";
        menu.style.zIndex = "2000";
        menu.innerHTML = '<span class="dropdown-item-text small text-muted">Cargando…</span>';
        document.body.appendChild(menu);
        place(menu, x, y);
        const current = menu;
        fetch("/panel/documentacion/personal/" + pk + "/menu/", {credentials: "same-origin"})
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (data) {
                if (menu !== current) return;
                menu.innerHTML = "";
                const head = document.createElement("h6");
                head.className = "dropdown-header";
                head.textContent = data.name;
                menu.appendChild(head);
                data.items.forEach(function (item) {
                    const a = document.createElement("a");
                    a.className = "dropdown-item";
                    a.href = item.url;
                    const icon = document.createElement("i");
                    icon.className = "bi " + item.icon + " me-2";
                    a.appendChild(icon);
                    a.appendChild(document.createTextNode(item.label));
                    menu.appendChild(a);
                });
                place(menu, x, y);
            })
            .catch(function () {
                if (menu !== current) return;
                menu.innerHTML = '<span class="dropdown-item-text small text-danger">No se ha podido cargar el menú.</span>';
            });
    }

    document.addEventListener("contextmenu", function (ev) {
        if (ev.shiftKey) return;
        const pk = personOf(ev.target);
        if (!pk) return;
        ev.preventDefault();
        open(pk, ev.clientX, ev.clientY);
    });
    document.addEventListener("click", function (ev) {
        if (menu && !menu.contains(ev.target)) close();
    }, true);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") close(); });
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
}());
