/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/static/new_ui/js/new_ui.js
 *
 * Nueva interfaz (S163, sesión invasora de UX): la vista única de
 * Documentación (new_ui/templates/new_ui/shell.html).
 *
 * Común a todas las secciones (directriz 4.27, punto 4bis):
 *   - Cinco paneles: los tres de arriba cambian de altura con el asa
 *     horizontal; los dos de abajo, de anchura con la vertical (y de
 *     altura con la de arriba). Guardado por usuario ("layout").
 *   - Pestañas en cada panel (data-nui-tab / data-nui-pane), guardadas
 *     por usuario ("tabs").
 *   - Periodo rápido; avisos de cada acción (nunca en silencio).
 * Documentos, Personal y Centros de gasto: un listado por pestaña
 * (panel/views_new_ui.NewUiListView), con su orden, sus columnas
 * ("cols_<sección>") y su selección ("sel_<sección>"); pulsar una
 * persona o máquina la deja sola en toda la vista ("scope_<sección>"),
 * con su pestaña "Ficha" (en el sitio de "General", sin acordeones) y
 * sus acciones; el botón derecho abre aquí las pestañas que existen
 * (window.EbUiOpen, new_ui_context_menu.js); exportar; grupos de
 * selección (EbUiGroups).
 * Permisos: editor, acciones en bloque y grupos de usuarios.
 */
(function () {
    "use strict";

    const root = document.getElementById("nui");
    if (!root) return;
    const SCREEN = "nui";
    const section = root.dataset.section;
    const json = function (id, fallback) {
        const el = document.getElementById(id);
        if (!el) return fallback;
        const value = JSON.parse(el.textContent);
        return value === null ? fallback : value;
    };
    const layout = Object.assign({top: 270, sel: 30}, json("nui-layout", {}));
    const tabs = json("nui-tabs", {});
    const urls = json("nui-urls", {});

    function save(values) {
        if (window.EbUiState) window.EbUiState.save(SCREEN, values);
    }
    function csrf() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    // ---- Alto de la vista y tamaños de los paneles ----
    // La vista ocupa justo la pantalla: sin barra de desplazamiento de la
    // página (S163, Miguel Ángel); cada panel desplaza lo suyo. Se mide
    // lo que sobra por debajo (márgenes del panel) y se descuenta.
    // La página nunca se desplaza (S163): al enfocar un campo, el
    // navegador de la tableta subía todo y dejaba hueco debajo.
    const wide = window.matchMedia("(min-width: 992px)");
    function lockScroll() {
        document.documentElement.classList.toggle("nui-locked", wide.matches);
        if (wide.matches && (window.scrollY || document.documentElement.scrollTop)) {
            window.scrollTo(0, 0);
        }
    }
    window.addEventListener("scroll", function () { if (wide.matches) lockScroll(); }, {passive: true});
    document.addEventListener("focusout", function () { setTimeout(lockScroll, 50); });
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", function () { setTimeout(fitHeight, 50); });
    }
    function fitHeight() {
        lockScroll();
        if (!wide.matches) { root.style.height = ""; return; }
        // El borde de abajo va pegado al final de la pantalla siempre
        // (S163): alto = 100dvh menos lo que hay encima, así sigue a la
        // pantalla real (barras del navegador, teclado) sin esperar a JS.
        const top = root.getBoundingClientRect().top + window.scrollY;
        let offset = Math.ceil(top) + 4;
        root.style.height = "calc(100dvh - " + offset + "px)";
        const extra = document.documentElement.scrollHeight - window.innerHeight;
        if (extra > 0) {
            offset += extra;
            root.style.height = "calc(100dvh - " + offset + "px)";
        }
        applyLayout();
    }
    function applyLayout() {
        // El panel de arriba nunca deja al de abajo sin sitio.
        const room = (root.clientHeight || 600) - 170;
        if (room > 120 && layout.top > room) layout.top = room;
        root.style.setProperty("--nui-top", layout.top + "px");
        root.style.setProperty("--nui-sel", layout.sel + "%");
    }
    function dragger(handle, onMove) {
        handle.addEventListener("pointerdown", function (ev) {
            ev.preventDefault();
            handle.setPointerCapture(ev.pointerId);
            document.body.classList.add("nui-dragging");
            function move(e) { onMove(e); applyLayout(); }
            function up() {
                handle.removeEventListener("pointermove", move);
                handle.removeEventListener("pointerup", up);
                document.body.classList.remove("nui-dragging");
                save({layout: {top: Math.round(layout.top), sel: Math.round(layout.sel * 10) / 10}});
            }
            handle.addEventListener("pointermove", move);
            handle.addEventListener("pointerup", up);
        });
    }
    const hHandle = root.querySelector('[data-nui-resize="top"]');
    const vHandle = root.querySelector('[data-nui-resize="sel"]');
    if (hHandle) dragger(hHandle, function (e) {
        const box = root.querySelector(".nui-top").getBoundingClientRect();
        layout.top = Math.min(root.clientHeight - 170, Math.max(120, e.clientY - box.top));
    });
    if (vHandle) dragger(vHandle, function (e) {
        const box = root.querySelector(".nui-bottom").getBoundingClientRect();
        layout.sel = Math.min(70, Math.max(15, (box.right - e.clientX) / box.width * 100));
    });
    window.addEventListener("resize", fitHeight);
    window.addEventListener("load", fitHeight);
    fitHeight();

    // ---- Pantalla completa de cada panel (S163, Miguel Ángel) ----
    // Un botón en la cabecera de cada panel lo abre ocupando toda la
    // pantalla; el mismo botón (o Escape) lo devuelve a su sitio.
    function setMax(panel, on) {
        root.querySelectorAll(".nui-panel.nui-max").forEach(function (p) {
            if (p !== panel || !on) {
                p.classList.remove("nui-max");
                const b = p.querySelector(".nui-max-btn");
                if (b) { b.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>'; b.title = "Pantalla completa"; }
            }
        });
        if (on) {
            panel.classList.add("nui-max");
            const b = panel.querySelector(".nui-max-btn");
            if (b) { b.innerHTML = '<i class="bi bi-fullscreen-exit"></i>'; b.title = "Salir de pantalla completa (Esc)"; }
        }
        document.body.classList.toggle("nui-has-max", !!root.querySelector(".nui-panel.nui-max"));
    }
    root.querySelectorAll(".nui-panel").forEach(function (panel) {
        let bar = null;
        for (const child of panel.children) {
            if ((child.classList.contains("nui-head") || child.classList.contains("nui-tabs")) && !child.classList.contains("d-none")) { bar = child; break; }
        }
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "nui-head";
            panel.insertBefore(bar, panel.firstChild);
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "nui-max-btn";
        button.title = "Pantalla completa";
        button.setAttribute("aria-label", "Pantalla completa");
        button.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
        button.addEventListener("click", function () {
            setMax(panel, !panel.classList.contains("nui-max"));
        });
        bar.appendChild(button);
    });
    document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && root.querySelector(".nui-panel.nui-max")) setMax(null, false);
    });

    // ---- Pestañas de cada panel ----
    function panelOf(name) { return root.querySelector('[data-nui-panel="' + name + '"]'); }
    function activeTab(panelName) {
        const panel = panelOf(panelName);
        const button = panel && panel.querySelector(":scope > .nui-tabs .nav-link.active");
        return button ? button.dataset.nuiTab : "";
    }
    function showTab(panel, name, persist) {
        panel.querySelectorAll(":scope > .nui-tabs [data-nui-tab]").forEach(function (b) {
            const on = b.dataset.nuiTab === name;
            b.classList.toggle("active", on);
            b.setAttribute("aria-selected", on ? "true" : "false");
        });
        panel.querySelectorAll("[data-nui-pane]").forEach(function (p) {
            if (p.closest("[data-nui-panel]") !== panel) return;
            p.classList.toggle("d-none", p.dataset.nuiPane !== name);
        });
        if (persist) {
            tabs[section + ":" + panel.dataset.nuiPanel] = name;
            save({tabs: tabs});
        }
        panel.dispatchEvent(new CustomEvent("nui:tab", {detail: name, bubbles: true}));
    }
    function restoreTabs(scope) {
        (scope || root).querySelectorAll("[data-nui-panel]").forEach(function (panel) {
            const first = panel.querySelector(":scope > .nui-tabs [data-nui-tab]");
            if (!first) return;
            const saved = tabs[section + ":" + panel.dataset.nuiPanel];
            const exists = saved && panel.querySelector(':scope > .nui-tabs [data-nui-tab="' + saved + '"]');
            showTab(panel, exists ? saved : first.dataset.nuiTab, false);
        });
    }
    root.addEventListener("click", function (ev) {
        const button = ev.target.closest("[data-nui-tab]");
        if (!button) return;
        showTab(button.closest("[data-nui-panel]"), button.dataset.nuiTab, true);
    });

    // ---- Avisos de resultado (nunca en silencio) ----
    function result(text, isError) {
        const box = document.getElementById("nui-result");
        if (!box) return;
        box.className = "alert small py-1 px-2 mt-2 mb-0 alert-" + (isError ? "danger" : "success");
        box.textContent = text;
    }
    function post(url, body, box) {
        const show = box || result;
        show("Guardando…", false);
        return fetch(url, {
            method: "POST", credentials: "same-origin", body: body,
            headers: {"X-CSRFToken": csrf()},
        }).then(function (r) {
            return r.text().then(function (text) {
                let payload = null;
                try { payload = JSON.parse(text); } catch (e) { payload = null; }
                if (!r.ok || (payload && payload.ok === false)) {
                    throw new Error(payload ? (payload.message || payload.error || "No se ha podido guardar.") : (text || ("Error " + r.status)));
                }
                return payload || {};
            });
        }).then(function (payload) {
            show(payload.message || "Guardado.", false);
            return payload;
        }).catch(function (err) {
            show(err.message || "No se ha podido guardar.", true);
            throw err;
        });
    }

    // ---- Periodo rápido ----
    const form = document.getElementById("nui-filters");
    let submitFilters = function () {};
    if (form) {
        form.addEventListener("click", function (ev) {
            const unit = ev.target.closest("[data-period-unit]");
            const which = ev.target.closest("[data-period-which]");
            if (!unit && !which) return;
            ev.preventDefault();
            if (unit) {
                const input = form.querySelector('[name="periodo"]');
                input.value = input.value === unit.dataset.periodUnit ? "" : unit.dataset.periodUnit;
                form.querySelectorAll("[data-period-unit]").forEach(b => b.classList.toggle("active", b.dataset.periodUnit === input.value));
            } else {
                form.querySelector('[name="cual"]').value = which.dataset.periodWhich;
                form.querySelectorAll("[data-period-which]").forEach(b => b.classList.toggle("active", b === which));
            }
            form.querySelector('[name="desde"]').value = "";
            form.querySelector('[name="hasta"]').value = "";
            submitFilters();
        });
    }

    // ---- Visor de seleccionados (común) ----
    function paintSelectionList(map, onRemove) {
        root.querySelectorAll("[data-nui-count]").forEach(el => { el.textContent = map.size; });
        const ul = document.getElementById("nui-selection-list");
        if (!ul) return;
        ul.innerHTML = "";
        if (!map.size) {
            const li = document.createElement("li");
            li.className = "text-muted";
            li.textContent = "Nada seleccionado todavía.";
            ul.appendChild(li);
        }
        Array.from(map.entries())
            .sort((a, b) => (a[1] || "").localeCompare(b[1] || ""))
            .forEach(function ([pk, label]) {
                const li = document.createElement("li");
                li.className = "d-flex justify-content-between align-items-center border-bottom py-1";
                const span = document.createElement("span");
                span.textContent = label || ("#" + pk);
                const x = document.createElement("button");
                x.type = "button";
                x.className = "btn btn-sm btn-link text-danger p-0";
                x.setAttribute("aria-label", "Quitar de la selección");
                x.innerHTML = '<i class="bi bi-x-lg"></i>';
                x.addEventListener("click", function () { onRemove(pk); });
                li.appendChild(span);
                li.appendChild(x);
                ul.appendChild(li);
            });
    }

    // ---- «Qué ver» (arriba, en la entrada) manda en el listado (abajo) ----
    // El listado no tiene nada que elegir: sus pestañas, ocultas, solo
    // llevan el estado; aquí se reflejan los botones de arriba y su título.
    function syncViewbar() {
        const listPanel = panelOf("listado");
        if (!listPanel) return;
        const current = activeTab("listado");
        document.querySelectorAll("[data-nui-view]").forEach(function (b) {
            const twin = listPanel.querySelector(':scope > .nui-tabs [data-nui-tab="' + b.dataset.nuiView + '"]');
            b.classList.toggle("d-none", !!(twin && twin.classList.contains("d-none")));
            b.classList.toggle("active", b.dataset.nuiView === current);
            b.setAttribute("aria-selected", b.dataset.nuiView === current ? "true" : "false");
        });
        const title = document.getElementById("nui-list-title");
        const button = listPanel.querySelector(':scope > .nui-tabs [data-nui-tab="' + current + '"]');
        if (title) title.textContent = button ? button.textContent.trim() : "";
    }
    // Los botones de «Qué ver» van en la barra de título, fuera de #nui.
    document.addEventListener("click", function (ev) {
        const view = ev.target.closest("[data-nui-view]");
        if (!view) return;
        showTab(panelOf("listado"), view.dataset.nuiView, true);
    });
    root.addEventListener("nui:tab", function (ev) {
        if (ev.target === panelOf("listado")) syncViewbar();
    });

    if (section === "permisos") { permisos(); } else { lists(); }
    restoreTabs();
    syncViewbar();

    // =================== DOCUMENTOS, PERSONAL, CENTROS DE GASTO ===================
    function lists() {
        const listPanel = panelOf("listado");
        const allSelections = json("nui-selections", {});
        let scope = json("nui-scope", null);
        const sorts = {};
        const selections = {};
        Object.keys(allSelections).forEach(function (key) {
            selections[key] = new Map((allSelections[key] || []).map(p => [String(p[0]), p[1] || ""]));
        });
        function tab() { return activeTab("listado") || (listPanel.querySelector("[data-nui-tab]") || {dataset: {}}).dataset.nuiTab; }
        function key(t) { return section + "." + (t || tab()); }
        function sel(t) {
            const k = key(t);
            if (!selections[k]) selections[k] = new Map();
            return selections[k];
        }
        function persistSelection() {
            const out = {};
            Object.keys(selections).forEach(function (k) { out[k] = Array.from(selections[k].entries()); });
            const values = {};
            values["sel_" + section] = out;
            save(values);
            refreshSelection();
        }
        function pane(t) { return listPanel.querySelector('.nui-list-pane[data-tab="' + (t || tab()) + '"]'); }
        let groups = null;
        // S163 (Miguel Ángel, 23/11): el panel Acciones en tres apartados,
        // según sobre quién se actúa: 1) «Con los N <cosas> seleccionados»,
        // 2) «Con <lo pulsado>» (el documento marcado o la persona abierta)
        // y 3) «Nuevo y ajustes». Cada trozo de las plantillas de acciones
        // (hijo de un [data-nui-actions-for]) dice el suyo con data-nui-for
        // ("sel", "one", "new" o, por vista, "general:sel epis:one"); sin
        // decirlo: "sel" si lleva data-nui-needs-selection, "one" si usa la
        // persona abierta (data-nui-scope-input) y si no, "new".
        const nouns = json("nui-tab-nouns", {});
        const pieces = [];
        root.querySelectorAll("[data-nui-actions-stage] [data-nui-actions-for]").forEach(function (block) {
            const tabs = block.dataset.nuiActionsFor.split(" ").filter(Boolean);
            Array.from(block.children).forEach(function (child) {
                pieces.push({el: child, tabs: tabs, order: pieces.length});
            });
        });
        function groupOf(piece, t) {
            const spec = piece.el.dataset.nuiFor || "";
            if (spec.indexOf(":") !== -1) {
                const hit = spec.split(" ").map(s => s.split(":")).find(p => p[0] === t);
                if (hit) return hit[1];
            } else if (spec) {
                return spec;
            }
            if (piece.el.matches("[data-nui-needs-selection]") || piece.el.querySelector("[data-nui-needs-selection]")) return "sel";
            if (piece.el.querySelector("[data-nui-scope-input]")) return "one";
            return "new";
        }
        // Cada acción se ve plegada en su título (que dice qué hace); al
        // pulsarlo se abre. Las que no tienen título propio van abiertas.
        pieces.forEach(function (piece) {
            const title = Array.from(piece.el.children).find(c => c.classList && c.classList.contains("fw-semibold"))
                || (piece.el.tagName !== "FORM" && piece.el.firstElementChild && piece.el.firstElementChild.tagName === "FORM"
                    ? Array.from(piece.el.firstElementChild.children).find(c => c.classList && c.classList.contains("fw-semibold")) : null);
            if (!title) return;
            piece.el.classList.add("nui-piece");
            title.classList.add("nui-piece-title");
            title.setAttribute("role", "button");
            title.setAttribute("tabindex", "0");
        });
        root.addEventListener("click", function (ev) {
            const title = ev.target.closest(".nui-piece-title");
            if (!title) return;
            title.closest(".nui-piece").classList.toggle("nui-open");
        });
        root.addEventListener("keydown", function (ev) {
            const title = ev.target.closest && ev.target.closest(".nui-piece-title");
            if (!title || (ev.key !== "Enter" && ev.key !== " ")) return;
            ev.preventDefault();
            title.closest(".nui-piece").classList.toggle("nui-open");
        });
        function sec(name) { return root.querySelector('[data-nui-sec="' + name + '"]'); }
        function nounOf(t) { return nouns[t] || (section === "cdg" ? ["centro de gasto", "centros de gasto"] : ["trabajador", "trabajadores"]); }
        function paintViewActions(t) {
            t = t || tab();
            const shown = {sel: 0, one: 0, new: 0};
            const bodies = {sel: sec("sel"), one: sec("one"), new: sec("new")};
            pieces.forEach(function (piece) {
                // En la Ficha, todo lo que se hace con esta persona.
                const on = piece.tabs.indexOf(t) !== -1
                    || (t === "ficha" && piece.tabs.some(x => groupOf(piece, x) === "one"));
                piece.el.dataset.nuiActive = on ? "1" : "";
                if (!on) { piece.el.classList.add("d-none"); return; }
                const g = piece.tabs.indexOf(t) !== -1 ? groupOf(piece, t) : "one";
                const body = bodies[g] && bodies[g].querySelector("[data-nui-sec-body]");
                if (!body) return;
                body.appendChild(piece.el);
                piece.el.dataset.nuiGroup = g;
                piece.el.classList.remove("d-none");
                shown[g]++;
            });
            // El orden de las plantillas dentro de cada apartado.
            ["sel", "one", "new"].forEach(function (g) {
                const body = bodies[g] && bodies[g].querySelector("[data-nui-sec-body]");
                if (!body) return;
                pieces.filter(p => p.el.parentNode === body).sort((x, y) => x.order - y.order).forEach(p => body.appendChild(p.el));
            });
            paintSections();
        }
        function paintSections() {
            const t = tab();
            const map = sel();
            const n = map.size;
            const noun = nounOf(t);
            // 1) Los seleccionados.
            function activeIn(s) { return s ? Array.from(s.querySelector("[data-nui-sec-body]").children).filter(c => c.dataset.nuiActive) : []; }
            const s1 = sec("sel");
            if (s1) {
                const body = s1.querySelector("[data-nui-sec-body]");
                // Sin lista (Ficha, Jornadas...) no hay nada que seleccionar.
                const has = activeIn(s1).length > 0 && !listPanel.querySelector('[data-nui-entity-tab][data-nui-tab="' + t + '"]');
                s1.classList.toggle("d-none", !has);
                s1.querySelector("[data-nui-sec-title]").textContent = n === 1 ? "Con 1 " + noun[0] + " seleccionado" : "Con los " + n + " " + noun[1] + " seleccionados";
                const hint = s1.querySelector("[data-nui-sec-hint]");
                hint.textContent = n ? "" : "Marca con la casilla los " + noun[1] + " de la lista para hacer aquí lo mismo con todos a la vez.";
                hint.classList.toggle("d-none", !!n);
                body.classList.toggle("d-none", !n);
            }
            // 2) Lo pulsado: el elemento marcado (si hay uno solo) o la
            // persona o máquina abierta.
            const s2 = sec("one");
            if (s2) {
                const listBox = pane();
                const mark = n === 1 && listBox ? listBox.querySelector('.nui-rowmark[value="' + CSS.escape(Array.from(map.keys())[0]) + '"]') : null;
                const rowActions = document.getElementById("nui-row-actions");
                const hasRow = !!(rowActions && rowActions.children.length && !rowActions.querySelector("[data-nui-empty]"));
                const scoped = !!(scope && scope.pk) && section !== "doc";
                // Lo de esta persona, con ella abierta; «Actualizar» de un
                // documento o «Gestionar» de una solicitud lo enseñan sin
                // abrirla (data-nui-forced).
                let forced = "";
                activeIn(s2).forEach(function (c) {
                    // Separar páginas y Gestionar una solicitud solo salen
                    // al pulsarlos.
                    const visible = c.hasAttribute("data-nui-only-forced") ? !!c.dataset.nuiForced : (scoped || !!c.dataset.nuiForced);
                    c.classList.toggle("d-none", !visible);
                    if (!scoped && c.dataset.nuiForced) forced = c.dataset.nuiForced;
                });
                const entity = document.getElementById("nui-entity-actions");
                if (entity) entity.classList.toggle("d-none", !scoped);
                let who = "";
                if (mark && (hasRow || !scoped)) who = mark.dataset.label || "";
                else if (scoped) who = scope.label || "";
                else if (forced) who = forced;
                const title = s2.querySelector("[data-nui-sec-title]");
                const hint = s2.querySelector("[data-nui-sec-hint]");
                if (who) {
                    title.textContent = "Con " + who;
                    // Marcado uno solo sin abrirlo: lo suyo sale al abrirlo.
                    const closed = mark && !hasRow && !scoped && !forced;
                    hint.textContent = closed ? "Pulsa su nombre en la lista para ver aquí todo lo suyo (o usa las acciones de «Con 1 … seleccionado»)." : "";
                    hint.classList.toggle("d-none", !closed);
                } else {
                    const person = section === "cdg" ? "un centro de gasto" : "un trabajador";
                    title.textContent = section === "cdg" ? "Con un centro de gasto" : "Con un trabajador";
                    hint.textContent = "Pulsa el nombre de " + person + " en la lista (o marca un solo " + noun[0] + ") para ver aquí lo que puedes hacer con él.";
                    hint.classList.remove("d-none");
                }
                // Donde no hay nada que hacer con uno (p. ej. Tipos de
                // fichaje), el apartado no sale.
                s2.classList.toggle("d-none", !who && !hasRow && !activeIn(s2).length);
            }
            // 3) Nuevo y ajustes.
            const s3 = sec("new");
            if (s3) s3.classList.toggle("d-none", !activeIn(s3).length);
            const tabButton = document.getElementById("nui-view-actions-tab");
            if (tabButton) tabButton.textContent = "Acciones";
        }
        listPanel.addEventListener("nui:tab", function (ev) { paintViewActions(ev.detail); });
        // La pestaña inicial ya se anunció antes de llegar aquí.
        paintViewActions();
        // Plantillas de columnas de las exportaciones de pantalla: el bloque
        // se pide aparte y se repinta al guardar o borrar una plantilla; lo
        // común (fechas, plantilla elegida, columnas) va con cada formulario
        // del [data-nui-tpl-shared] al enviarlo.
        function loadScreenTpl() {
            document.querySelectorAll("[data-nui-screen-tpl]").forEach(function (box) {
                fetch(box.dataset.url, {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : Promise.reject(r.status))
                    .then(function (html) { box.innerHTML = html; })
                    .catch(function () { box.innerHTML = '<p class="small text-danger mb-0">No se ha podido cargar.</p>'; });
            });
        }
        loadScreenTpl();
        // Ajustes de fichaje de la empresa: se piden aparte y se repintan.
        function loadClockSettings() {
            document.querySelectorAll("[data-nui-clockset]").forEach(function (box) {
                fetch(box.dataset.url, {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : Promise.reject(r.status))
                    .then(function (html) { box.innerHTML = html; })
                    .catch(function () { box.innerHTML = '<p class="small text-danger mb-0">No se ha podido cargar.</p>'; });
            });
        }
        loadClockSettings();
        // Reglas por sección y tipos de ausencia (Saldo de vacaciones).
        function loadVacationSetup() {
            document.querySelectorAll("[data-nui-vacset]").forEach(function (box) {
                fetch(box.dataset.url, {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : Promise.reject(r.status))
                    .then(function (html) { box.innerHTML = html; })
                    .catch(function () { box.innerHTML = '<p class="small text-danger mb-0">No se ha podido cargar.</p>'; });
            });
        }
        loadVacationSetup();
        // Días libres por horas: 8:00 por día mientras no se toquen las horas.
        document.addEventListener("input", function (ev) {
            const f = ev.target.closest("[data-nui-free-days]");
            if (!f) return;
            const hours = f.querySelector('[name="hours"]');
            if (ev.target === hours) { hours.dataset.touched = "1"; return; }
            if (ev.target.name !== "days" || hours.dataset.touched) return;
            const n = parseInt(ev.target.value, 10);
            if (n > 0) hours.value = (n * 8) + ":00";
        });
        document.addEventListener("change", function (ev) {
            const radio = ev.target.closest("[data-nui-tpl-radio]");
            if (!radio) return;
            const keys = (radio.dataset.columns || "").split(",");
            radio.closest("[data-nui-tpl-shared]").querySelectorAll("[data-nui-tpl-col]").forEach(function (box) { box.checked = keys.indexOf(box.value) !== -1; });
        });
        document.addEventListener("submit", function (ev) {
            const f = ev.target.closest("[data-nui-tpl-export]");
            if (!f) return;
            const box = f.closest("[data-nui-tpl-shared]");
            f.querySelectorAll("[data-nui-copied]").forEach(el => el.remove());
            function add(name, value) {
                const input = document.createElement("input");
                input.type = "hidden"; input.name = name; input.value = value;
                input.setAttribute("data-nui-copied", "");
                f.appendChild(input);
            }
            const from = box.querySelector("[data-nui-tpl-from]"), to = box.querySelector("[data-nui-tpl-to]");
            if (from) add("desde", from.value);
            if (to) add("hasta", to.value);
            if (f.hasAttribute("data-nui-list-params") && window.nuiListExtra) {
                Object.entries(window.nuiListExtra()).forEach(([k, v]) => add(k, v));
            }
            const chosen = box.querySelector("[data-nui-tpl-radio]:checked");
            add("template_pk", chosen ? chosen.value : "");
            box.querySelectorAll("[data-nui-tpl-col]:checked").forEach(c => add("columns", c.value));
        }, true);
        root.addEventListener("submit", function (ev) {
            const f = ev.target.closest("[data-nui-action-form]");
            if (!f) return;
            ev.preventDefault();
            const submitter = ev.submitter || null;
            const ask = submitter && submitter.dataset.nuiConfirm;
            if (ask && !window.confirm(ask)) return;
            const body = new FormData(f);
            if (submitter && submitter.name) body.append(submitter.name, submitter.value);
            if (f.hasAttribute("data-nui-needs-selection")) {
                const ids = Array.from(sel().keys());
                if (!ids.length) { result("Marca primero con la casilla, en la lista de abajo, a quién aplicarlo.", true); return; }
                ids.forEach(id => body.append("selected", id));
                if (f.hasAttribute("data-nui-with-tab")) body.append("tab", tab());
            }
            const url = (submitter && submitter.getAttribute("formaction")) || f.getAttribute("action");
            if (f.hasAttribute("data-nui-docuten")) {
                // Docuten: los tres archivos seguidos, sueltos (nunca un ZIP).
                ["pdf", "csv", "pasos"].reduce(function (chain, kind) {
                    return chain.then(function () {
                        const part = new FormData();
                        body.forEach((v, k) => part.append(k, v));
                        part.append("archivo", kind);
                        return download(url, part);
                    });
                }, Promise.resolve());
                return;
            }
            if (f.hasAttribute("data-nui-download") || (submitter && submitter.hasAttribute("data-nui-download-button"))) { download(url, body); return; }
            post(url, body)
                .then(function (data) {
                    result(data.message || "Hecho.", false);
                    // Lo guardado sigue en el formulario: guardar otra vez lo modifica.
                    const pkInput = f.querySelector("[data-nui-pk]");
                    if (pkInput && data.id) pkInput.value = data.id;
                    // Contrato revisado: «Correcto» deja a mano el Deshacer.
                    if (f.hasAttribute("data-nui-contract")) {
                        const action = submitter ? submitter.value : "";
                        f.querySelector("[data-nui-contract-info]").textContent = data.message || "";
                        f.querySelector("[data-nui-contract-undo]").classList.toggle("d-none", action !== "review");
                    }
                    // Lo de la persona vista (su foto) se repinta.
                    if (f.closest("#nui-entity-actions") && !f.hasAttribute("data-nui-no-refresh")) loadEntityActions();
                    // Alta: la vista se queda con la persona nueva.
                    if (data.scope && (section === "per" || section === "cdg")) setScope(data.scope);
                    if (f.hasAttribute("data-nui-tpl-reload")) loadScreenTpl();
                    if (f.hasAttribute("data-nui-clockset-reload")) loadClockSettings();
                    if (f.hasAttribute("data-nui-vacset-reload")) loadVacationSetup();
                    if (f.hasAttribute("data-nui-fragment-reload")) {
                        const box = f.closest("[data-nui-fragment-box]");
                        if (box && box.dataset.current) loadFragment(box);
                    }
                    // Formularios de un solo uso (subir): vuelven a empezar.
                    if (f.hasAttribute("data-nui-reset-after")) {
                        f.querySelectorAll("[data-nui-temp]").forEach(el => el.remove());
                        f.querySelectorAll("[data-nui-intake-files]").forEach(el => { el.innerHTML = ""; });
                        f.reset();
                        f.querySelectorAll("[data-nui-clear]").forEach(i => { i.value = ""; });
                        f.querySelectorAll("[data-default]").forEach(el => { el.textContent = el.dataset.default; });
                        if (f.dataset.nuiForced) { delete f.dataset.nuiForced; paintSections(); }
                    }
                    load();
                })
                .catch(function (err) { result(err.message, true); });
        });
        // Acciones que devuelven un archivo (dosieres, S163): se descarga
        // sin salir de la vista; si vuelve JSON es un aviso o, al
        // comprobar una plantilla, las filas a resaltar.
        function download(url, body) {
            result("Preparando…", false);
            return fetch(url, {method: "POST", credentials: "same-origin", body: body, headers: {"X-CSRFToken": csrf()}})
                .then(function (r) {
                    const type = r.headers.get("Content-Type") || "";
                    if (type.indexOf("application/json") !== -1) {
                        return r.json().then(function (data) {
                            if (!r.ok || data.ok === false) throw new Error(data.message || data.error || ("Error " + r.status));
                            markMissing(data.missing || null);
                            result(data.message || "Hecho.", false);
                        });
                    }
                    if (!r.ok) return r.text().then(function (t) { throw new Error(t || ("Error " + r.status)); });
                    const disposition = r.headers.get("Content-Disposition") || "";
                    const named = r.headers.get("X-Docuten-Filename");
                    const match = named ? [null, decodeURIComponent(named)] : /filename="([^"]+)"|filename=([^;]+)/.exec(disposition);
                    if (match && !match[1] && match[2]) match[1] = match[2].trim();
                    let note = "Descargado.";
                    try { note = JSON.parse(r.headers.get("X-Nui-Message") || '"Descargado."'); } catch (e) { /* aviso por defecto */ }
                    return r.blob().then(function (blob) {
                        const a = document.createElement("a");
                        a.href = URL.createObjectURL(blob);
                        a.download = match ? match[1] : "descarga";
                        document.body.appendChild(a);
                        a.click();
                        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
                        result(note, false);
                    });
                })
                .catch(function (err) { result(err.message, true); });
        }
        function markMissing(ids) {
            const box = pane();
            if (!box || ids === null) return;
            box.querySelectorAll("tr.nui-missing").forEach(tr => tr.classList.remove("nui-missing"));
            ids.forEach(function (id) {
                const mark = box.querySelector('.nui-rowmark[value="' + CSS.escape(String(id)) + '"]');
                if (mark) mark.closest("tr").classList.add("nui-missing");
            });
        }
        // Plantillas de dosier (Documentos › Dosieres): ámbito, nueva y
        // «Modificar» desde Esta fila (enlace #nui-dossier-edit-<pk>).
        const dossierForm = document.getElementById("nui-dossier-form");
        function dossierScope(scope, locked) {
            if (!dossierForm) return;
            dossierForm.querySelectorAll('[name="scope"]').forEach(function (r) { r.checked = r.value === scope; r.disabled = !!locked && r.value !== scope; });
            dossierForm.querySelectorAll("[data-nui-dossier-scope]").forEach(function (box) {
                const on = box.dataset.nuiDossierScope === scope;
                box.classList.toggle("d-none", !on);
                box.querySelectorAll("input").forEach(i => { i.disabled = !on; });
            });
        }
        function dossierReset() {
            dossierForm.reset();
            dossierForm.querySelector('[name="template_pk"]').value = "";
            dossierForm.querySelector("[data-nui-dossier-title]").innerHTML = '<i class="bi bi-plus-circle me-1"></i>Nueva plantilla';
            dossierScope("PERSONAL", false);
        }
        // Formularios de crear/modificar (horarios, tipos de fichaje):
        // «Esta fila» › Modificar (#nui-edit:<formulario>:<pk>) carga la
        // fila en su formulario; «Empezar uno nuevo» lo vacía.
        function formTitle(form, html) {
            const t = form.querySelector("[data-nui-form-title]");
            if (t) t.innerHTML = html;
        }
        function formReset(form) {
            form.reset();
            const pkInput = form.querySelector("[data-nui-pk]");
            if (pkInput) pkInput.value = "";
            formTitle(form, '<i class="bi bi-plus-circle me-1"></i>' + (form.dataset.newTitle || "Nuevo"));
            form.dispatchEvent(new Event("change", {bubbles: true}));
        }
        function formFill(form, fields) {
            Object.keys(fields).forEach(function (name) {
                const value = fields[name];
                form.querySelectorAll('[name="' + CSS.escape(name) + '"]').forEach(function (el) {
                    if (el.type === "checkbox") el.checked = Array.isArray(value) ? value.map(String).indexOf(el.value) !== -1 : !!value;
                    else if (el.type === "radio") el.checked = String(el.value) === String(value);
                    else el.value = value === null || value === undefined ? "" : value;
                });
            });
            form.dispatchEvent(new Event("change", {bubbles: true}));
        }
        root.addEventListener("click", function (ev) {
            const b = ev.target.closest("[data-nui-form-new]");
            if (b) formReset(b.closest("form"));
        });
        document.addEventListener("click", function (ev) {
            const link = ev.target.closest('a[href^="#nui-edit:"]');
            if (!link) return;
            ev.preventDefault();
            const parts = link.getAttribute("href").split(":");
            const form = document.getElementById(parts[1]);
            if (!form) return;
            fetch(form.dataset.dataUrl.replace("/0/", "/" + parts[2] + "/"), {credentials: "same-origin"})
                .then(r => r.json())
                .then(function (data) {
                    if (!data.ok) throw new Error(data.message || "No se ha podido cargar.");
                    formReset(form);
                    formFill(form, data.fields);
                    formTitle(form, '<i class="bi bi-pencil-square me-1"></i>Modificar «' + String(data.title || "").replace(/[<>&]/g, "") + "»");
                    showTab(panelOf("acciones"), "vista", true);
                    result("Cargado: cambia lo que haga falta y guarda.", false);
                })
                .catch(function (err) { result(err.message, true); });
        });
        // Documentos (S163): historial de un tipo (el propio listado,
        // filtrado), actualizar (subir la versión nueva) y separar.
        function loadFragment(box) {
            box.innerHTML = '<p class="small text-muted mb-0">Cargando…</p>';
            fetch(box.dataset.current, {credentials: "same-origin"})
                .then(r => r.ok ? r.text() : Promise.reject(new Error("No se ha podido abrir.")))
                .then(function (html) { box.innerHTML = html; })
                .catch(function (err) { box.innerHTML = ""; result(err.message, true); });
        }
        function goToActions(el) {
            showTab(panelOf("acciones"), "vista", true);
            if (el) el.scrollIntoView({block: "start", behavior: "smooth"});
        }
        function ownFilter(name, value, text) {
            const el = document.querySelector('[name="' + name + '"]');
            if (!el) return;
            if (value && !Array.from(el.options).some(o => o.value === value)) {
                const o = document.createElement("option");
                o.value = value; o.textContent = text || value;
                el.appendChild(o);
            }
            el.value = value;
        }
        const uploadForm = document.getElementById("nui-upload-form");
        document.addEventListener("click", function (ev) {
            const link = ev.target.closest('a[href^="#nui-doc-"]');
            if (!link) return;
            ev.preventDefault();
            const parts = link.getAttribute("href").slice(1).split(":");
            const kind = parts[0];
            if (kind === "nui-doc-history") {
                ownFilter("x_documentos_tipo", parts[2], "Este tipo");
                ownFilter("x_documentos_estado", "", "");
                result("Historial del tipo: todos sus documentos, vigentes y sustituidos.", false);
                setScope({pk: parts[1], label: decodeURIComponent(parts[3] || "")}, "documentos");
                return;
            }
            if (kind === "nui-doc-update" && uploadForm) {
                uploadForm.querySelector('[name="domain"]').value = parts[1];
                uploadForm.querySelector('[name="subject_pk"]').value = parts[2];
                uploadForm.querySelectorAll('[name="document_type_code"]').forEach(r => { r.checked = r.value === parts[3]; });
                const typeLabel = decodeURIComponent(parts[4] || "");
                const who = decodeURIComponent(parts[5] || "");
                uploadForm.querySelector("[data-nui-upload-title]").textContent = "Actualizar " + typeLabel;
                uploadForm.querySelector("[data-nui-upload-who]").textContent = "De: " + who + " (la versión nueva sustituye a la anterior).";
                uploadForm.dataset.nuiForced = who;
                uploadForm.classList.add("nui-open");
                paintSections();
                goToActions(uploadForm);
                return;
            }
            if (kind === "nui-doc-jornada") {
                cardView = {pk: parts[1], tab: "jornadas", extra: {vista: "jornadas", dia: parts[2]}};
                setScope({pk: parts[1], label: decodeURIComponent(parts[3] || "")}, "jornadas");
                return;
            }
            if (kind === "nui-doc-fragment") {
                // S163: un fragmento con acciones (p. ej. «Gestionar» una
                // solicitud) en el bloque de Acciones de la vista abierta.
                const box = document.querySelector('[data-nui-actions-for~="' + tab() + '"] [data-nui-fragment-box]');
                if (!box) return;
                box.dataset.current = decodeURIComponent(parts[1]);
                const row = link.closest("tr") && link.closest("tr").querySelector(".nui-rowmark");
                box.dataset.nuiForced = (row && row.dataset.label) || "lo elegido";
                paintSections();
                loadFragment(box);
                goToActions(box);
                return;
            }
            if (kind === "nui-doc-split") {
                const box = document.getElementById("nui-split-box");
                if (!box) return;
                box.innerHTML = '<p class="small text-muted mb-0">Cargando las páginas…</p>';
                const row = link.closest("tr") && link.closest("tr").querySelector(".nui-rowmark");
                box.dataset.nuiForced = (row && row.dataset.label) || "este documento";
                paintSections();
                goToActions(box);
                fetch(box.dataset.url.replace("/0/", "/" + parts[1] + "/"), {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : Promise.reject(new Error("No se ha podido abrir el documento.")))
                    .then(function (html) { box.innerHTML = html; })
                    .catch(function (err) { box.innerHTML = ""; result(err.message, true); });
            }
        });
        // Formularios de la persona o máquina abierta (S163): el campo
        // marcado con data-nui-scope-input toma su id al enviar.
        root.addEventListener("submit", function (ev) {
            const input = ev.target.querySelector && ev.target.querySelector("[data-nui-scope-input]");
            if (input && scope && scope.pk) input.value = scope.pk;
        }, true);
        // Subir sin «Actualizar»: es de la persona o máquina abierta.
        root.addEventListener("submit", function (ev) {
            if (ev.target !== uploadForm) return;
            const subject = uploadForm.querySelector('[name="subject_pk"]');
            if (!subject.value && scope && scope.pk) subject.value = scope.pk;
        }, true);
        // Elegir un tipo sin desplegable: escribir filtra la lista.
        root.addEventListener("input", function (ev) {
            const input = ev.target.closest("[data-nui-filter-list]");
            if (!input) return;
            const words = input.value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").split(/\s+/).filter(Boolean);
            const target = input.nextElementSibling;
            target.querySelectorAll("[data-nui-filter-group]").forEach(function (group) {
                let any = false;
                group.querySelectorAll("[data-nui-filter-item]").forEach(function (item) {
                    const text = item.textContent.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
                    const on = words.every(w => text.indexOf(w) !== -1);
                    item.classList.toggle("d-none", !on);
                    any = any || on;
                });
                group.classList.toggle("d-none", !any);
            });
        });
        // Requisitos: ver solo un grupo (Personal, Centros de gasto,
        // Comunes) y una categoría; lo marcado y oculto se conserva.
        const reqForm = document.getElementById("nui-requirement-form");
        function reqView() {
            const group = (reqForm.querySelector('[name="_req_group"]:checked') || {}).value || "all";
            const cat = (reqForm.querySelector('[name="_req_cat"]:checked') || {}).value || "all";
            reqForm.querySelectorAll("[data-nui-req-group]").forEach(function (g) {
                g.classList.toggle("d-none", group !== "all" && g.dataset.nuiReqGroup !== group);
                g.querySelectorAll("[data-nui-req-section]").forEach(function (s) {
                    let any = false;
                    s.querySelectorAll("[data-nui-req-cat]").forEach(function (item) {
                        const on = cat === "all" || item.dataset.nuiReqCat === cat;
                        item.classList.toggle("d-none", !on);
                        any = any || on;
                    });
                    s.classList.toggle("d-none", !any);
                });
            });
        }
        if (reqForm) {
            reqForm.addEventListener("change", reqView);
            reqView();
        }
        // Alta (S163): «Leer los documentos» rellena el formulario con
        // lo leído; cada archivo lleva su tipo detectado al confirmar.
        document.querySelectorAll("[data-nui-intake]").forEach(function (intake) {
            const filesInput = intake.querySelector('[name="documents"]');
            const filesBox = intake.querySelector("[data-nui-intake-files]");
            const reactivateInput = intake.querySelector("[data-nui-reactivate]");
            function clearIntake() {
                intake.querySelectorAll("[data-nui-temp]").forEach(el => el.remove());
                filesBox.innerHTML = "";
                if (reactivateInput) reactivateInput.value = "";
                const label = intake.querySelector("[data-nui-intake-submit]");
                label.textContent = label.dataset.default;
            }
            filesInput.addEventListener("change", clearIntake);
            intake.querySelector("[data-nui-intake-read]").addEventListener("click", function () {
                if (!filesInput.files.length) { result("Elige primero los documentos.", true); return; }
                clearIntake();
                const body = new FormData();
                Array.from(filesInput.files).forEach(file => body.append("documents", file));
                result("Leyendo los documentos… (puede tardar un poco)", false);
                post(intake.dataset.readUrl, body).then(function (data) {
                    Object.entries(data.draft || {}).forEach(function ([name, value]) {
                        const el = intake.querySelector('[name="' + name + '"]');
                        if (!el || !value) return;
                        if (el.type === "radio") {
                            intake.querySelectorAll('[name="' + name + '"]').forEach(r => { r.checked = r.value === value; });
                        } else {
                            el.value = value;
                        }
                    });
                    const list = document.createElement("ul");
                    list.className = "mb-1 ps-3";
                    (data.per_file || []).forEach(function (item) {
                        [["document_type_codes", item.document_type_code], ["document_expiry_hints", item.expiry_hint || ""], ["document_issue_hints", item.issue_hint || ""]].forEach(function ([name, value]) {
                            const input = document.createElement("input");
                            input.type = "hidden"; input.name = name; input.value = value || "";
                            input.setAttribute("data-nui-temp", "");
                            intake.appendChild(input);
                        });
                        const li = document.createElement("li");
                        const kind = item.document_type_label || (item.document_type_code === "DESCONOCIDO" || !item.document_type_code ? "no reconocido (no se guarda)" : item.document_type_code);
                        li.textContent = (item.filename || item.name) + ": " + kind + (item.error ? " — " + item.error : "");
                        list.appendChild(li);
                    });
                    (data.warnings || []).forEach(function (w) {
                        const li = document.createElement("li");
                        li.className = "text-warning-emphasis";
                        li.textContent = w;
                        list.appendChild(li);
                    });
                    filesBox.appendChild(list);
                    if (data.reactivate && reactivateInput) {
                        reactivateInput.value = data.reactivate.id;
                        intake.querySelector("[data-nui-intake-submit]").textContent = "Reactivar y guardar sus documentos";
                    }
                    result(data.message || "Datos leídos.", !!data.duplicate);
                }).catch(function (err) { result(err.message, true); });
            });
        });
        // Acceso al panel (S163): filas de los marcados y crear.
        const access = document.getElementById("nui-access");
        if (access) {
            const rowsBox = access.querySelector("[data-nui-access-rows]");
            const createBtn = access.querySelector("[data-nui-access-create]");
            access.querySelector("[data-nui-access-preview]").addEventListener("click", function () {
                const ids = Array.from(sel().keys());
                if (!ids.length) { result("Marca primero en el listado a quién dar acceso.", true); return; }
                rowsBox.innerHTML = '<p class="small text-muted mb-0">Cargando…</p>';
                fetch(access.dataset.previewUrl + "?ids=" + ids.join(","), {credentials: "same-origin"})
                    .then(r => r.text())
                    .then(function (html) { rowsBox.innerHTML = html; createBtn.classList.remove("d-none"); });
            });
            createBtn.addEventListener("click", function () {
                const rows = Array.from(rowsBox.querySelectorAll("tr[data-person]:not([data-skip])")).map(tr => (tr.dataset.link ? {
                    person: tr.dataset.person, link: tr.dataset.link,
                } : {
                    person: tr.dataset.person,
                    username: tr.querySelector(".pa-username").value.trim(),
                    section: tr.querySelector(".pa-section").value,
                    base: tr.querySelector(".pa-base").value,
                    role: tr.querySelector(".pa-role").value,
                }));
                if (!rows.length) { result("No hay nadie a quien crear usuario.", true); return; }
                createBtn.disabled = true;
                result("Creando usuarios…", false);
                fetch(access.dataset.createUrl, {
                    method: "POST", credentials: "same-origin",
                    headers: {"X-CSRFToken": csrf(), "Content-Type": "application/json"},
                    body: JSON.stringify({rows: rows}),
                }).then(r => r.json()).then(function (data) {
                    result(data.message || "Hecho.", data.ok === false);
                    if (data.ok) { rowsBox.innerHTML = ""; createBtn.classList.add("d-none"); load(); }
                }).catch(function () { result("Error de red: no se ha creado nada.", true); })
                  .finally(function () { createBtn.disabled = false; });
            });
        }
        // EPIs (S163): en General se entrega a los marcados; en EPIs, a
        // la persona abierta. Un lote marca sus EPIs de golpe.
        root.addEventListener("submit", function (ev) {
            const form = ev.target;
            if (!form.hasAttribute || !form.hasAttribute("data-nui-epi-form")) return;
            const input = form.querySelector('[name="person_ids"]');
            if (tab() === "general") {
                input.value = "";
                const ids = Array.from(sel().keys());
                form.querySelectorAll("[data-nui-temp]").forEach(el => el.remove());
                ids.forEach(function (id) {
                    const extra = document.createElement("input");
                    extra.type = "hidden"; extra.name = "selected"; extra.value = id;
                    extra.setAttribute("data-nui-temp", "");
                    form.appendChild(extra);
                });
            }
        }, true);
        root.addEventListener("click", function (ev) {
            const batch = ev.target.closest("[data-nui-epi-batch]");
            if (batch) {
                const items = new Set(batch.dataset.nuiEpiBatch.split(",").filter(Boolean));
                batch.closest("form").querySelectorAll('[name="epi_ids"]').forEach(c => { c.checked = items.has(c.value); });
                return;
            }
            const edit = ev.target.closest("[data-nui-epi-batch-edit]");
            const fresh = ev.target.closest("[data-nui-epi-batch-new]");
            if (!edit && !fresh) return;
            const form = (edit || fresh).closest("form");
            form.querySelector('[name="batch_pk"]').value = edit ? edit.dataset.nuiEpiBatchEdit : "";
            form.querySelector('[name="name"]').value = edit ? edit.dataset.name : "";
            const items = new Set(edit ? edit.dataset.items.split(",").filter(Boolean) : []);
            form.querySelectorAll('[name="item_ids"]').forEach(c => { c.checked = items.has(c.value); });
        });
        document.addEventListener("click", function (ev) {
            const link = ev.target.closest('a[href^="#nui-epi-history:"]');
            if (!link) return;
            ev.preventDefault();
            const parts = link.getAttribute("href").slice(1).split(":");
            ownFilter("x_epis_epi", parts[2], "Este EPI");
            result("Historial de ese EPI de esta persona.", false);
            setScope({pk: parts[1], label: decodeURIComponent(parts[3] || "")}, "epis");
        });
        // Horario: qué partes del formulario se ven según las casillas.
        const scheduleForm = document.getElementById("nui-schedule-form");
        function scheduleParts() {
            const f = scheduleForm;
            const open = f.querySelector('[name="is_open"]').checked;
            const varies = !open && f.querySelector('[name="varies_by_day"]').checked;
            const continuous = f.querySelector('[name="is_intensive"]').checked;
            const holidays = f.querySelector('[name="works_holidays"]').checked;
            f.querySelector('[name="varies_by_day"]').disabled = open;
            f.querySelector('[data-nui-schedule-part="fixed"]').classList.toggle("d-none", varies);
            f.querySelectorAll('[data-nui-schedule-part="afternoon"]').forEach(el => el.classList.toggle("d-none", open || continuous));
            f.querySelector('[data-nui-schedule-part="days"]').classList.toggle("d-none", !varies);
            f.querySelector('[data-nui-schedule-part="holiday"]').classList.toggle("d-none", !holidays);
        }
        if (scheduleForm) {
            scheduleForm.addEventListener("change", scheduleParts);
            scheduleParts();
        }
        if (dossierForm) {
            dossierForm.addEventListener("change", function (ev) {
                if (ev.target.name === "scope") dossierScope(ev.target.value, false);
            });
            dossierForm.querySelector("[data-nui-dossier-new]").addEventListener("click", dossierReset);
            document.addEventListener("click", function (ev) {
                const link = ev.target.closest('a[href^="#nui-dossier-edit-"]');
                if (!link) return;
                ev.preventDefault();
                const pk = link.getAttribute("href").replace("#nui-dossier-edit-", "");
                fetch(dossierForm.dataset.dataUrl.replace("/0/", "/" + pk + "/"), {credentials: "same-origin"})
                    .then(r => r.json())
                    .then(function (data) {
                        if (!data.ok) throw new Error(data.message || "No se ha podido cargar.");
                        dossierReset();
                        dossierForm.querySelector('[name="template_pk"]').value = data.id;
                        dossierForm.querySelector('[name="name"]').value = data.name;
                        dossierForm.querySelector("[data-nui-dossier-title]").innerHTML = '<i class="bi bi-pencil-square me-1"></i>Modificar «' + data.name.replace(/[<>&]/g, "") + "»";
                        dossierScope(data.scope, true);
                        const types = new Set(data.type_ids.map(String));
                        const epis = new Set(data.epi_ids.map(String));
                        dossierForm.querySelectorAll('[name="document_type_ids"]').forEach(c => { c.checked = !c.disabled && types.has(c.value); });
                        dossierForm.querySelectorAll('[name="epi_item_ids"]').forEach(c => { c.checked = !c.disabled && epis.has(c.value); });
                        showTab(panelOf("acciones"), "vista", true);
                        result("Plantilla cargada: cambia lo que haga falta y guarda.", false);
                    })
                    .catch(function (err) { result(err.message, true); });
            });
            dossierScope("PERSONAL", false);
        }

        // Acciones › Esta fila: las acciones de la fila marcada (una sola).
        function paintRowActions() {
            const box = document.getElementById("nui-row-actions");
            if (!box) return;
            box.innerHTML = "";
            const map = sel();
            const listBox = pane();
            const mark = map.size === 1 && listBox ? listBox.querySelector('.nui-rowmark[value="' + CSS.escape(Array.from(map.keys())[0]) + '"]') : null;
            // «Ver su ficha» no se repite aquí: es el botón derecho.
            const items = mark ? Array.from(mark.closest("tr").querySelectorAll("[data-nui-row-actions] .dropdown-item")).filter(i => !i.hasAttribute("data-nui-scope")) : [];
            if (!items.length) {
                box.setAttribute("data-nui-empty", "");
                return;
            }
            box.removeAttribute("data-nui-empty");
            const wrap = document.createElement("div");
            wrap.className = "d-flex flex-wrap gap-1";
            items.forEach(function (original) {
                const b = document.createElement("button");
                b.type = "button";
                b.className = "btn btn-sm btn-outline-primary";
                b.innerHTML = original.innerHTML;
                b.addEventListener("click", function () { original.click(); });
                wrap.appendChild(b);
            });
            box.appendChild(wrap);
        }
        function refreshSelection() {
            const map = sel();
            paintSelectionList(map, function (pk) { map.delete(pk); persistSelection(); syncChecks(); });
            paintRowActions();
            paintSections();
            const idsInput = document.getElementById("nui-selected-ids");
            if (idsInput) idsInput.value = Array.from(map.keys()).join(",");
            if (groups) groups.refresh();
        }
        function syncChecks() {
            const box = pane();
            const map = sel();
            if (box) {
                const boxes = box.querySelectorAll(".nui-rowmark");
                boxes.forEach(function (b) {
                    if (map.has(b.value) && !map.get(b.value)) map.set(b.value, b.dataset.label || "");
                    b.checked = map.has(b.value);
                });
                const all = box.querySelector("#nui-all");
                if (all) all.checked = boxes.length > 0 && Array.from(boxes).every(b => b.checked);
                const state = box.querySelector(".nui-list-state");
                root.querySelectorAll("[data-nui-total]").forEach(el => { el.textContent = state ? state.dataset.count : "…"; });
            }
            refreshSelection();
        }
        const listExtra = {};
        window.nuiListExtra = function () { return Object.assign({q: (form.querySelector('[name="q"]') || {}).value || ""}, listExtra[tab()] || {}); };
        function params(extra) {
            const p = new URLSearchParams(new FormData(form));
            p.set("s", section);
            p.set("t", tab());
            p.set("sort", sorts[tab()] || "");
            p.set("selected_ids", Array.from(sel().keys()).join(","));
            if (scope && scope.pk) p.set("scope", scope.pk);
            Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
            return p;
        }
        let loading = 0;
        // Pestañas de una sola persona o máquina (Ficha, QR): no son
        // listados; solo se ven con ella elegida.
        const entityTabs = Array.from(listPanel.querySelectorAll("[data-nui-entity-tab]")).map(b => b.dataset.nuiTab);
        function isEntityTab(t) { return entityTabs.indexOf(t) !== -1; }
        function load() {
            const t = tab();
            if (isEntityTab(t)) { loadCard(); return; }
            const box = pane(t);
            if (!box) return;
            const ticket = ++loading;
            box.innerHTML = '<p class="text-muted small p-3 mb-0">Cargando…</p>';
            fetch(urls.list + "?" + params(listExtra[t] || {}).toString(), {credentials: "same-origin"})
                .then(r => r.ok ? r.text() : r.text().then(t2 => Promise.reject(t2)))
                .then(function (html) {
                    if (ticket !== loading) return;
                    box.innerHTML = html;
                    syncChecks();
                })
                .catch(function (err) {
                    if (ticket !== loading) return;
                    box.innerHTML = '<p class="text-danger small p-3 mb-0">No se ha podido cargar: ' + (typeof err === "string" ? err : "error de red") + '</p>';
                });
        }
        submitFilters = load;
        function paintOwnFilters(t, label) {
            const ownTab = document.getElementById("nui-own-filters-tab");
            if (!ownTab) return;
            const active = Array.from(root.querySelectorAll('[data-nui-note-for="' + t + '"] [data-nui-own-filter]')).filter(el => el.value).length;
            ownTab.textContent = "Filtros de " + label + (active ? " (" + active + ")" : "");
        }
        root.addEventListener("change", function (ev) {
            const own = ev.target.closest("[data-nui-own-filter]");
            if (!own) return;
            const tabButton = listPanel.querySelector('[data-nui-tab="' + tab() + '"]');
            if (tabButton) paintOwnFilters(tab(), tabButton.textContent.trim());
            load();
        });
        let typing = null;
        form.addEventListener("change", function (ev) {
            if (ev.target.id === "nui-q") return;
            load();
        });
        form.addEventListener("input", function (ev) {
            if (ev.target.id !== "nui-q") return;
            clearTimeout(typing);
            typing = setTimeout(load, 400);
        });
        form.addEventListener("submit", function (ev) { ev.preventDefault(); load(); });
        const clearSort = document.getElementById("nui-clear-sort");
        if (clearSort) clearSort.addEventListener("click", function () { sorts[tab()] = ""; load(); });

        // Cambio de pestaña del listado: su selección, sus columnas, su nota.
        listPanel.addEventListener("nui:tab", function (ev) {
            const t = ev.detail;
            const scoped = !!(scope && scope.pk) && section !== "doc";
            if (isEntityTab(t) && !scoped) { showTab(listPanel, "general", false); return; }
            if (t === "general" && scoped && entityTabs.length) { showTab(listPanel, "ficha", false); return; }
            root.querySelectorAll("[data-nui-total-box]").forEach(el => el.classList.toggle("invisible", isEntityTab(t)));
            root.querySelectorAll("[data-nui-cols-for]").forEach(el => el.classList.toggle("d-none", el.dataset.nuiColsFor !== t));
            root.querySelectorAll("[data-nui-note-for]").forEach(el => el.classList.toggle("d-none", el.dataset.nuiNoteFor !== t));
            // "Filtros de <pestaña>": el nombre dice a qué listado se
            // aplican; con alguno puesto, se marca con su número.
            const ownTab = document.getElementById("nui-own-filters-tab");
            const tabButton = listPanel.querySelector('[data-nui-tab="' + t + '"]');
            if (ownTab && tabButton) paintOwnFilters(t, tabButton.textContent.trim());
            load();
        });

        // Columnas visibles de cada pestaña.
        root.addEventListener("change", function (ev) {
            if (!ev.target.matches("[data-nui-col]")) return;
            const cols = {};
            root.querySelectorAll("[data-nui-cols-for]").forEach(function (block) {
                cols[section + "." + block.dataset.nuiColsFor] = Array.from(
                    block.querySelectorAll("[data-nui-col]")).filter(b => b.checked).map(b => b.value);
            });
            const values = {};
            values["cols_" + section] = cols;
            save(values);
            if (window.EbUiState && window.EbUiState.flush) window.EbUiState.flush();
            setTimeout(load, 300);
        });

        // Casillas, orden y "ver sus listados".
        const lists = document.getElementById("nui-lists");
        lists.addEventListener("change", function (ev) {
            const map = sel();
            if (ev.target.id === "nui-all") {
                pane().querySelectorAll(".nui-rowmark").forEach(function (b) {
                    b.checked = ev.target.checked;
                    if (b.checked) map.set(b.value, b.dataset.label || ""); else map.delete(b.value);
                });
                persistSelection();
                return;
            }
            if (ev.target.classList.contains("nui-rowmark")) {
                if (ev.target.checked) map.set(ev.target.value, ev.target.dataset.label || ""); else map.delete(ev.target.value);
                persistSelection();
                syncChecks();
            }
        });
        root.addEventListener("click", function (ev) {
            const sort = ev.target.closest("[data-nui-sort]");
            if (sort) { ev.preventDefault(); sorts[tab()] = sort.dataset.nuiSort; load(); return; }
            const pick = ev.target.closest("[data-nui-scope]");
            if (pick) {
                ev.preventDefault();
                // Con data-nui-scope-tab se abre esa pestaña de la persona
                // (con data-nui-scope-extra: sus parámetros, p. ej. el año).
                if (pick.dataset.nuiScopeTab) {
                    let extra = {};
                    try { extra = JSON.parse(pick.dataset.nuiScopeExtra || "{}"); } catch (e) { extra = {}; }
                    cardView = {pk: pick.dataset.nuiScope, tab: pick.dataset.nuiScopeTab, extra: extra};
                }
                // Clic izquierdo en un nombre de un listado que no es
                // «General»: sus filas de esta misma vista (sus fichajes
                // en Fichajes...); en General (o desde el menú), su ficha.
                let target = pick.dataset.nuiScopeTab;
                const now = tab();
                const fromList = pick.tagName === "A" && pick.closest("#nui-lists") && pane() && pane().querySelector('.nui-list-state[data-scopeable="1"]');
                if (!target && fromList && now !== "general" && !isEntityTab(now)) target = now;
                setScope({pk: pick.dataset.nuiScope, label: pick.dataset.nuiScopeLabel}, target);
            }
        });
        const clear = document.getElementById("nui-sel-clear");
        if (clear) clear.addEventListener("click", function () { sel().clear(); persistSelection(); syncChecks(); });
        // «Solo los filtrados»: de lo seleccionado, solo lo que cumple el
        // filtro del listado abierto. Hace el cruce y se desmarca sola.
        const onlyFiltered = document.getElementById("nui-sel-only-filtered");
        if (onlyFiltered) onlyFiltered.addEventListener("change", function () {
            if (!onlyFiltered.checked) return;
            const box = pane();
            const shown = new Set(box ? Array.from(box.querySelectorAll(".nui-rowmark")).map(b => b.value) : []);
            Array.from(sel().keys()).forEach(function (pk) { if (!shown.has(pk)) sel().delete(pk); });
            persistSelection();
            syncChecks();
            onlyFiltered.checked = false;
        });

        // Una sola persona o máquina: toda la vista con lo suyo.
        const chip = document.getElementById("nui-scope-chip");
        function paintScope() {
            if (chip) {
                chip.classList.toggle("d-none", !(scope && scope.pk));
                chip.classList.toggle("d-flex", !!(scope && scope.pk));
                const label = document.getElementById("nui-scope-label");
                if (label) label.textContent = scope ? scope.label : "";
            }
            const scoped = !!(scope && scope.pk);
            const generalTab = listPanel.querySelector('[data-nui-tab="general"]');
            listPanel.querySelectorAll("[data-nui-entity-tab]").forEach(b => b.classList.toggle("d-none", !scoped));
            if (generalTab && entityTabs.length) generalTab.classList.toggle("d-none", scoped);
            syncViewbar();
            loadEntityActions();
        }
        function setScope(value, target) {
            if (section === "doc") {
                // En Documentos, la persona se abre en Personal.
                const values = {"scope_per": value};
                tabs["per:listado"] = "ficha";
                values.tabs = tabs;
                save(values);
                if (window.EbUiState && window.EbUiState.flush) window.EbUiState.flush();
                setTimeout(function () { window.location.href = "?s=per"; }, 300);
                return;
            }
            scope = value;
            const values = {};
            values["scope_" + section] = value;
            save(values);
            paintScope();
            document.dispatchEvent(new CustomEvent("nui:scope"));
            paintSections();
            // Con una persona o máquina sola se abre su ficha (o la pestaña
            // pedida desde el menú); al quitarla, se vuelve a "General".
            const now = tab();
            const wanted = value ? (target || "ficha") : (isEntityTab(now) ? "general" : now);
            if (wanted !== now) showTab(listPanel, wanted, true); else load();
        }
        const scopeClear = document.getElementById("nui-scope-clear");
        if (scopeClear) scopeClear.addEventListener("click", function () { setScope(null); });

        // Acciones de la persona o máquina vista (las del botón derecho).
        function loadEntityActions() {
            // Acciones › «Del trabajador» / «Del centro de gasto». Lo que
            // tiene pestaña abajo no se repite aquí (S163); aquí irán las
            // acciones que no son un listado (subir, pedir, avisar...).
            const box = document.getElementById("nui-entity-actions");
            if (!box) return;
            box.innerHTML = "";
            const p = document.createElement("p");
            p.className = "small text-muted mb-0";
            if (!(scope && scope.pk)) {
                p.textContent = "Pulsa " + (section === "cdg" ? "un centro de gasto" : "una persona") + " en el listado para ver aquí sus acciones.";
            } else {
                const panelUrl = section === "per" ? urls.photoPanel : (section === "cdg" ? urls.machinePanel : "");
                if (panelUrl) {
                    // S163: sus acciones que no son un listado (foto para
                    // plataformas, contrato revisado, revisiones...).
                    const photo = document.createElement("div");
                    box.appendChild(photo);
                    fetch(panelUrl.replace("/0/", "/" + scope.pk + "/"), {credentials: "same-origin"})
                        .then(r => r.ok ? r.text() : "")
                        .then(function (html) { photo.innerHTML = html; });
                    return;
                }
            }
            box.appendChild(p);
        }
        // Recuadro sobre la foto para descargarla recortada.
        root.addEventListener("pointerdown", function (ev) {
            const area = ev.target.closest("[data-nui-crop]");
            if (!area) return;
            ev.preventDefault();
            const img = area.querySelector("img");
            const boxEl = area.querySelector("[data-nui-crop-box]");
            const rect = img.getBoundingClientRect();
            const start = {x: ev.clientX - rect.left, y: ev.clientY - rect.top};
            function clamp(v, max) { return Math.max(0, Math.min(v, max)); }
            function move(e) {
                const x = clamp(e.clientX - rect.left, rect.width), y = clamp(e.clientY - rect.top, rect.height);
                const l = Math.min(start.x, x), t = Math.min(start.y, y);
                const w = Math.abs(x - start.x), h = Math.abs(y - start.y);
                Object.assign(boxEl.style, {left: l + "px", top: t + "px", width: w + "px", height: h + "px"});
                boxEl.classList.remove("d-none");
                boxEl.dataset.frac = [l / rect.width, t / rect.height, w / rect.width, h / rect.height].map(v => v.toFixed(4)).join(",");
            }
            function up() {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", up);
                const panel = area.parentElement;
                const link = panel.querySelector("[data-nui-crop-download]");
                const frac = (boxEl.dataset.frac || "").split(",").map(Number);
                const clear = panel.querySelector("[data-nui-crop-clear]");
                if (frac.length === 4 && frac[2] > 0.03 && frac[3] > 0.03) {
                    link.href = link.dataset.base + "?x=" + frac[0] + "&y=" + frac[1] + "&w=" + frac[2] + "&h=" + frac[3];
                    panel.querySelector("[data-nui-crop-label]").textContent = "Descargar el recuadro para plataformas";
                    clear.classList.remove("d-none");
                } else {
                    boxEl.classList.add("d-none");
                }
            }
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", up);
        });
        root.addEventListener("click", function (ev) {
            const clear = ev.target.closest("[data-nui-crop-clear]");
            if (!clear) return;
            const panel = clear.closest("div.d-flex").parentElement.parentElement;
            panel.querySelector("[data-nui-crop-box]").classList.add("d-none");
            const link = panel.querySelector("[data-nui-crop-download]");
            link.href = link.dataset.base;
            panel.querySelector("[data-nui-crop-label]").textContent = "Descargar para plataformas";
            clear.classList.add("d-none");
        });
        // Acciones de fila que se hacen sin más (#nui-post:<url>:<datos>).
        document.addEventListener("click", function (ev) {
            const link = ev.target.closest('a[href^="#nui-post:"]');
            if (!link) return;
            ev.preventDefault();
            const parts = link.getAttribute("href").split(":");
            const body = new FormData();
            new URLSearchParams(parts[2] || "").forEach((v, k) => body.append(k, v));
            post(decodeURIComponent(parts[1]), body)
                .then(function (data) { result(data.message || "Hecho.", false); load(); loadEntityActions(); })
                .catch(function (err) { result(err.message, true); });
        });

        // Pestaña "Ficha" (S163): la ficha de la persona o máquina vista
        // sola, como una pestaña más del listado (sin acordeones).
        function fichaBox() { return pane(tab()); }
        let cardView = {pk: null, tab: null, extra: {}};
        // Vistas propias (no listados de modelo, p. ej. Alta en el
        // fichaje): sus botones de filtro van con la pestaña.
        lists.addEventListener("click", function (ev) {
            const btn = ev.target.closest("[data-nui-list-param]");
            if (!btn) return;
            ev.preventDefault();
            const t = tab();
            listExtra[t] = Object.assign({}, listExtra[t] || {});
            listExtra[t][btn.dataset.nuiListParam] = btn.dataset.value;
            load();
        });
        // S163: carga de albaranes (copia adaptada de
        // panel/static/panel/js/albaran_upload.js). La ventana solo sube los
        // archivos (4 a la vez); la IA los lee en segundo plano, así que se
        // puede seguir trabajando. Si se sale de la página a mitad de la
        // subida, el navegador avisa.
        root.querySelectorAll("[data-nui-albaranes]").forEach(function (box) {
            const PARALLEL = 4, OK = /\.(pdf|jpe?g|png)$/i;
            const q = name => box.querySelector("[data-nui-alb-" + name + "]");
            const folder = q("folder"), loose = q("files"), go = q("go"), status = q("status"), notes = q("notes"), list = q("batches");
            const bar = q("progress").querySelector(".progress-bar");
            let files = [], uploading = false, watching = null, listTimer = null;
            function note(text, cls) { const li = document.createElement("li"); if (cls) li.className = cls; li.textContent = text; notes.appendChild(li); }
            function progress(done, total) { q("progress").classList.remove("d-none"); bar.style.width = Math.round(done * 100 / Math.max(total, 1)) + "%"; }
            function mode() { return box.dataset.mode || "person"; }
            function loadList() {
                clearTimeout(listTimer);
                const personPk = (mode() === "person" && scope && scope.pk) ? scope.pk : "";
                fetch(box.dataset.batches + (personPk ? "?person_pk=" + personPk : ""), {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : "")
                    .then(function (html) {
                        list.innerHTML = html;
                        const busy = list.querySelector('[data-nui-alb-busy="1"]');
                        if (busy) listTimer = setTimeout(loadList, 20000);
                    });
            }
            function pick(input) {
                files = Array.from(input.files || []).filter(f => OK.test(f.name));
                status.textContent = files.length ? files.length + " archivo(s) PDF o foto." : "No hay PDF ni fotos.";
                notes.innerHTML = "";
                go.disabled = !files.length || uploading;
            }
            folder.addEventListener("change", function () { loose.value = ""; pick(folder); });
            loose.addEventListener("change", function () { folder.value = ""; pick(loose); });
            async function post(url, body) {
                const r = await fetch(url, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrf(), "Accept": "application/json"}, body: body});
                const data = await r.json().catch(() => ({error: "El servidor no ha respondido bien (puede estar reiniciándose). Inténtalo de nuevo en un minuto."}));
                if (!r.ok || data.error) throw new Error(data.error || ("Error " + r.status));
                return data;
            }
            window.addEventListener("beforeunload", function (evt) { if (!uploading) return; evt.preventDefault(); evt.returnValue = ""; });
            go.addEventListener("click", async function () {
                if (uploading || !files.length) return;
                const start = new FormData();
                start.append("mode", mode());
                if (mode() === "person") {
                    if (!scope || !scope.pk) { note("Abre primero a la persona.", "text-danger"); return; }
                    start.append("person_pk", scope.pk);
                } else {
                    start.append("selected", Array.from(sel().keys()).join(","));
                    start.append("tab", tab());
                }
                uploading = true;
                go.disabled = folder.disabled = loose.disabled = true;
                notes.innerHTML = "";
                const todo = files;
                files = [];
                try {
                    const first = todo[0].webkitRelativePath || "";
                    start.append("count", todo.length);
                    start.append("folder", first.split("/")[0] || "");
                    const batch = (await post(box.dataset.start, start)).batch;
                    let next = 0, done = 0;
                    async function worker() {
                        while (next < todo.length) {
                            const file = todo[next++];
                            const body = new FormData();
                            body.append("file", file, file.name);
                            const data = await post(box.dataset.base + batch + "/archivo/", body);
                            if (data.skipped) note(data.skipped, "text-warning-emphasis");
                            done++;
                            progress(done, todo.length);
                            status.textContent = "Subiendo " + done + " de " + todo.length + "… (no salgas de esta página hasta que termine la subida)";
                        }
                    }
                    await Promise.all(Array.from({length: Math.min(PARALLEL, todo.length)}, worker));
                    await post(box.dataset.base + batch + "/fin/", new FormData());
                    uploading = false;
                    bar.style.width = "0%";
                    status.textContent = "";
                    note("Subidos " + todo.length + " archivo(s). La IA los lee en segundo plano: puedes seguir trabajando. El avance y el resultado se ven aquí y en «Cargas de albaranes».", "text-success");
                    loadList();
                    watch(batch);
                } catch (err) {
                    status.textContent = "";
                    note(err.message, "text-danger");
                }
                uploading = false;
                folder.disabled = loose.disabled = false;
                go.disabled = true;
            });
            async function watch(batch) {
                watching = batch;
                while (watching === batch) {
                    await new Promise(ok => setTimeout(ok, 4000));
                    if (watching !== batch) return;
                    let d;
                    try {
                        const r = await fetch(box.dataset.base + batch + "/estado/", {credentials: "same-origin", headers: {"Accept": "application/json"}});
                        if (!r.ok) throw new Error(String(r.status));
                        d = await r.json();
                    } catch (e) {
                        status.textContent = "Esperando al servidor (puede estar reiniciándose)… La lectura sigue: si se corta, se reanuda sola.";
                        continue;
                    }
                    progress(d.read, d.files);
                    if (d.status !== "READY" && d.status !== "CANCELLED") {
                        status.textContent = "La IA está leyendo: " + d.read + " de " + d.files + " archivo(s)…";
                        continue;
                    }
                    watching = null;
                    status.textContent = "";
                    bar.style.width = "0%";
                    q("progress").classList.add("d-none");
                    notes.innerHTML = "";
                    show(d);
                    loadList();
                    if (scope && scope.pk && tab() === "jornadas") loadCard();
                    return;
                }
            }
            function show(d) {
                note(d.albaranes + " albarán(es) leído(s); " + d.days + " día(s) procesado(s) por la IA, " + d.corrected + " corregido(s). Quedan sin visar: los visa un supervisor.", "text-success");
                (d.people || []).forEach(p => note(p.name + ": " + p.albaranes + " albarán(es), " + p.days + " día(s), " + p.corrected + " corregido(s)."));
                (d.no_person || []).forEach(n => note("Sin trabajador: " + n + " Cárgalo como «De la persona abierta» con quien sea.", "text-warning-emphasis"));
                (d.mismatch || []).forEach(n => note("El nombre «" + n + "» no coincide del todo con el trabajador: revísalo.", "text-warning-emphasis"));
                (d.unreadable || []).forEach(n => note("Sin leer: " + n, "text-danger"));
                if (d.error) note(d.error, "text-danger");
            }
            box.addEventListener("click", function (ev) {
                const link = ev.target.closest("[data-nui-alb-show]");
                if (!link) return;
                ev.preventDefault();
                if (uploading) return;
                notes.innerHTML = "";
                status.textContent = "Consultando la carga…";
                watch(link.dataset.nuiAlbShow);
            });
            loadList();
            document.addEventListener("nui:scope", loadList);
        });
        // Motivos habituales de una corrección: al campo «reason» de su
        // formulario; «Según albarán n.º(s)…», con los números del día.
        lists.addEventListener("click", function (ev) {
            const btn = ev.target.closest("[data-nui-reasons] [data-reason]");
            if (!btn) return;
            ev.preventDefault();
            const bar = btn.closest("[data-nui-reasons]");
            const box = btn.closest("form") && btn.closest("form").querySelector('[name="reason"]');
            if (!box) return;
            function put(text) {
                box.value = (box.value.trim() ? box.value.trim() + " " : "") + text;
                box.focus();
                box.setSelectionRange(box.value.length, box.value.length);
            }
            if (!btn.hasAttribute("data-albaran") || !bar.dataset.day) { put(btn.dataset.reason); return; }
            fetch(bar.dataset.albaranUrl + "?day=" + encodeURIComponent(bar.dataset.day), {credentials: "same-origin"})
                .then(r => r.ok ? r.json() : {numbers: []})
                .then(function (data) {
                    const numbers = (data && data.numbers) || [];
                    put(btn.dataset.reason + numbers.join(", ") + (numbers.length ? "." : ""));
                })
                .catch(function () { put(btn.dataset.reason); });
        });
        lists.addEventListener("click", function (ev) {
            const view = ev.target.closest("[data-nui-card-view]");
            const day = ev.target.closest("[data-nui-card-day]");
            const param = ev.target.closest("[data-nui-card-param]");
            if (!view && !day && !param) return;
            ev.preventDefault();
            if (param) {
                const same = cardView.pk === (scope && scope.pk) && cardView.tab === tab();
                const extra = Object.assign({}, same ? cardView.extra : {});
                extra[param.dataset.nuiCardParam] = param.dataset.value;
                cardView = {pk: scope && scope.pk, tab: tab(), extra: extra};
            } else {
                cardView = {pk: scope && scope.pk, tab: tab(), extra: view ? {vista: view.dataset.nuiCardView} : {vista: "jornadas", dia: day.dataset.nuiCardDay}};
            }
            loadCard();
        });
        function loadCard() {
            const box = fichaBox();
            if (!box) return Promise.resolve();
            if (!(scope && scope.pk)) { box.innerHTML = ""; return Promise.resolve(); }
            const ticket = ++loading;
            box.innerHTML = '<p class="text-muted small p-3 mb-0">Cargando…</p>';
            // Con el periodo del filtro común y la vista elegida dentro de
            // la pestaña (Jornadas: jornadas, calendario, correcciones).
            const extra = (cardView.pk === scope.pk && cardView.tab === tab()) ? cardView.extra : {};
            return fetch(urls.card + "?" + params(Object.assign({pk: scope.pk}, extra)).toString(), {credentials: "same-origin"})
                .then(r => r.ok ? r.text() : Promise.reject(r.status))
                .then(function (html) { if (ticket === loading) box.innerHTML = html; })
                .catch(function () { if (ticket === loading) box.innerHTML = '<p class="text-danger small p-3 mb-0">No se ha podido cargar la ficha.</p>'; });
        }
        function cardResult(text, isError) {
            const box = fichaBox() && fichaBox().querySelector("[data-nui-card-result]");
            if (!box) return;
            box.className = "alert small py-1 px-2 mb-2 alert-" + (isError ? "danger" : "success");
            box.textContent = text;
        }
        function cardEditing(on) {
            const box = fichaBox();
            if (!box) return;
            box.querySelectorAll("[data-nui-view-only]").forEach(el => el.classList.toggle("d-none", on));
            box.querySelectorAll("[data-nui-edit-only]").forEach(function (el) {
                el.classList.toggle("d-none", !on);
                el.querySelectorAll("input, textarea, select").forEach(i => { i.disabled = !on; });
            });
        }
        lists.addEventListener("click", function (ev) {
            if (!ev.target.closest(".nui-ficha")) return;
            if (ev.target.closest("[data-nui-card-edit]")) cardEditing(true);
            if (ev.target.closest("[data-nui-card-cancel]")) { cardEditing(false); loadCard(); }
        });
        lists.addEventListener("submit", function (ev) {
            const f = ev.target.closest("[data-nui-card-form]");
            if (!f) return;
            ev.preventDefault();
            const body = new FormData(f);
            post(f.getAttribute("action"), body, cardResult)
                .then(function () { setTimeout(loadCard, 600); })
                .catch(() => {});
        });
        // Formularios de las pestañas de una sola persona o máquina (QR...):
        // se envían sin salir y la pestaña se repinta con el resultado.
        lists.addEventListener("submit", function (ev) {
            const f = ev.target.closest("[data-nui-pane-form]");
            if (!f) return;
            ev.preventDefault();
            if (f.dataset.nuiConfirm && !window.confirm(f.dataset.nuiConfirm)) return;
            const button = f.querySelector('[type="submit"]');
            if (button) { button.disabled = true; }
            fetch(f.getAttribute("action"), {method: "POST", credentials: "same-origin", body: new FormData(f), headers: {"X-CSRFToken": csrf()}})
                .then(r => r.json().catch(() => ({ok: false, message: "Error " + r.status})))
                .then(function (data) {
                    const message = data.message || (data.ok ? "Hecho." : "No se ha podido hacer.");
                    const ok = !!data.ok;
                    loadCard().then(function () {
                        const box = fichaBox() && fichaBox().querySelector("[data-nui-pane-result]");
                        if (box) { box.className = "alert small py-1 px-2 mb-2 alert-" + (ok ? "success" : "danger"); box.textContent = message; }
                    });
                })
                .catch(function () { if (button) button.disabled = false; });
        });
        lists.addEventListener("change", function (ev) {
            const input = ev.target.closest("[data-nui-card-photo]");
            if (!input || !input.files.length) return;
            const card = input.closest(".nui-ficha");
            const urlsBox = card.querySelector("[data-nui-card-urls]");
            const body = new FormData();
            body.append("file", input.files[0]);
            if (card.dataset.kind === "machine") body.append("document_type_code", "IMAGEN");
            cardResult("Subiendo la foto…", false);
            fetch(urlsBox.dataset.photoUpload, {method: "POST", credentials: "same-origin", body: body, headers: {"X-CSRFToken": csrf()}})
                .then(r => r.json())
                .then(function (data) {
                    if (card.dataset.kind === "machine") {
                        const up = (data.uploaded || [])[0];
                        if (!up) throw new Error((data.errors && data.errors[0]) || data.error || "No se ha podido subir la foto.");
                        const b = new URLSearchParams({entry_id: up.entry_id});
                        return fetch(urlsBox.dataset.photoSet, {method: "POST", credentials: "same-origin", body: b, headers: {"X-CSRFToken": csrf()}}).then(r => r.json());
                    }
                    return data;
                })
                .then(function (data) {
                    if (data && data.ok === false) throw new Error(data.error || "No se ha podido fijar la foto.");
                    cardResult("Foto cambiada.", false);
                    setTimeout(loadCard, 600);
                })
                .catch(function (err) { cardResult(err.message || "No se ha podido cambiar la foto.", true); });
        });

        // Desde el botón derecho (new_ui_context_menu.js): abre aquí la
        // pestaña `tab` con la persona o máquina sola. En Documentos, una
        // persona lleva a Personal.
        window.EbUiOpen = function (kind, pk, label, tab) {
            const own = (kind === "person" && section === "per") || (kind === "machine" && section === "cdg");
            const scopeValue = {pk: String(pk), label: label || ""};
            if (!own) {
                const target = kind === "person" ? "per" : "cdg";
                const values = {};
                values["scope_" + target] = scopeValue;
                tabs[target + ":listado"] = tab || "ficha";
                values.tabs = tabs;
                save(values);
                if (window.EbUiState && window.EbUiState.flush) window.EbUiState.flush();
                setTimeout(function () { window.location.href = "?s=" + target; }, 300);
                return true;
            }
            setScope(scopeValue, tab || "ficha");
            return true;
        };

        // Exportar › «Separar en hojas por» una de las columnas visibles
        // de la vista (empresa, sección...), sin desplegable.
        function paintSplit() {
            const box = root.querySelector("[data-nui-split-options]");
            if (!box) return;
            const block = root.querySelector('[data-nui-cols-for="' + tab() + '"]');
            const cols = block ? Array.from(block.querySelectorAll("[data-nui-col]")).filter(c => c.checked) : [];
            box.innerHTML = "";
            const byGroups = (section === "per" || section === "cdg") ? [["__grupos", "grupos marcados en Selección"]] : [];
            [["", "nada"]].concat(cols.map(c => [c.value, c.nextElementSibling ? c.nextElementSibling.textContent.trim() : c.value]), byGroups).forEach(function ([value, label], i) {
                const l = document.createElement("label");
                l.className = "form-check form-check-inline mb-0 ms-1";
                l.innerHTML = '<input class="form-check-input" type="radio" name="nui_split"> <span class="form-check-label"></span>';
                l.querySelector("input").value = value;
                l.querySelector("input").checked = i === 0;
                l.querySelector("span").textContent = label;
                box.appendChild(l);
            });
            root.querySelector("[data-nui-split]").classList.toggle("d-none", !cols.length);
        }
        // Columnas › plantillas: guardar las columnas marcadas con un
        // nombre, aplicarlas o borrarlas (por vista, de cada usuario).
        const colTemplates = json("nui-coltpl", {});
        function paintColTemplates() {
            const box = root.querySelector("[data-nui-coltpl]");
            if (!box) return;
            const t = tab();
            const block = root.querySelector('[data-nui-cols-for="' + t + '"]');
            box.innerHTML = "";
            if (!block || !block.querySelector("[data-nui-col]")) return;
            const mine = colTemplates[t] || {};
            const title = document.createElement("div");
            title.className = "fw-semibold mb-1";
            title.textContent = "Plantillas de columnas";
            box.appendChild(title);
            Object.keys(mine).sort().forEach(function (name) {
                const row = document.createElement("div");
                row.className = "d-flex align-items-center gap-1 mb-1";
                row.innerHTML = '<span class="me-auto"></span><button type="button" class="btn btn-sm btn-outline-primary py-0">Aplicar</button><button type="button" class="btn btn-sm btn-outline-danger py-0">Borrar</button>';
                row.querySelector("span").textContent = name;
                const [apply, remove] = row.querySelectorAll("button");
                apply.addEventListener("click", function () {
                    block.querySelectorAll("[data-nui-col]").forEach(function (c) {
                        if (!c.disabled) c.checked = mine[name].indexOf(c.value) !== -1;
                    });
                    block.querySelector("[data-nui-col]").dispatchEvent(new Event("change", {bubbles: true}));
                    result("Columnas de la plantilla «" + name + "» puestas.", false);
                });
                remove.addEventListener("click", function () {
                    if (!window.confirm("¿Borrar la plantilla «" + name + "»?")) return;
                    delete mine[name];
                    colTemplates[t] = mine;
                    const values = {}; values["coltpl_" + section] = colTemplates; save(values);
                    paintColTemplates();
                });
                box.appendChild(row);
            });
            const add = document.createElement("div");
            add.className = "d-flex gap-1";
            add.innerHTML = '<input type="text" class="form-control form-control-sm" placeholder="Nombre para guardar las columnas marcadas" aria-label="Nombre de la plantilla"><button type="button" class="btn btn-sm btn-success">Guardar</button>';
            add.querySelector("button").addEventListener("click", function () {
                const name = add.querySelector("input").value.trim();
                if (!name) { result("Escribe un nombre para la plantilla.", true); return; }
                mine[name] = Array.from(block.querySelectorAll("[data-nui-col]")).filter(c => c.checked).map(c => c.value);
                colTemplates[t] = mine;
                const values = {}; values["coltpl_" + section] = colTemplates; save(values);
                result("Plantilla «" + name + "» guardada.", false);
                paintColTemplates();
            });
            box.appendChild(add);
        }
        listPanel.addEventListener("nui:tab", function () { paintSplit(); paintColTemplates(); });
        root.addEventListener("change", function (ev) { if (ev.target.matches("[data-nui-col]")) paintSplit(); });
        paintSplit();
        paintColTemplates();

        // Exportar.
        root.querySelectorAll("[data-nui-export]").forEach(function (button) {
            button.addEventListener("click", function () {
                if (isEntityTab(tab())) {
                    result(section === "cdg" ? "La ficha se exporta con su botón «Exportar» (PDF, Word, HTML, PNG o JPG)." : "La ficha no es un listado: elige otra pestaña para exportar.", false);
                    return;
                }
                const split = root.querySelector('[name="nui_split"]:checked');
                const p = params({export_format: button.dataset.nuiExport, split_col: split ? split.value : ""});
                if (split && split.value === "__grupos") {
                    const marked = Array.from(root.querySelectorAll(".person-group-select-checkbox:checked")).map(el => el.dataset.pk);
                    if (!marked.length) { result("Marca en Selección los grupos con los que separar las hojas.", true); return; }
                    p.set("split_groups", marked.join(","));
                }
                Array.from(sel().keys()).forEach(pk => p.append("selected", pk));
                const url = urls.export + "?" + p.toString();
                if (button.dataset.nuiExport === "print" || button.dataset.nuiExport === "html") window.open(url, "_blank");
                else window.location.href = url;
                result("Preparando la exportación de «" + (listPanel.querySelector(".nav-link.active") || {}).textContent + "»…", false);
            });
        });

        // Grupos de selección de siempre (máquinas o personas) sobre "General".
        if (window.EbUiGroups && document.getElementById("nuiGroupSavedList")) {
            const machines = section === "cdg";
            groups = window.EbUiGroups.init({
                prefix: "nuiGroup",
                memoryKey: "nui_" + section,
                collapsedKey: machines ? "machine_groups" : "person_groups",
                saveUrl: urls.groupSave,
                updateUrl: function (pk) {
                    return urls.groupUpdate.replace("/0/", "/" + pk + "/");
                },
                deleteUrl: function (pk) {
                    return urls.groupDelete.replace("/0/", "/" + pk + "/");
                },
                memberField: machines ? "machine_ids" : "person_ids",
                noun: machines ? "máquina" : "persona",
                getIds: function () { return Array.from(sel("general").keys()); },
                setIds: function (pairs) {
                    const map = sel("general");
                    map.clear();
                    pairs.forEach(function ([pk, name]) { map.set(String(pk), machines ? (name || "").split(" ")[0] : (name || "")); });
                    persistSelection();
                    showTab(listPanel, "general", true);
                },
                labelOf: function (pk) { return sel("general").get(String(pk)) || ""; },
                toast: function (text, isError) { result(text, isError); },
            });
        }

        paintScope();
    }

    // =================== PERMISOS ===================
    function permisos() {
        const selection = new Map(json("nui-selection", []).map(pk => [String(pk), ""]));
        const list = document.getElementById("nui-lists");
        submitFilters = function () { if (form && window.htmx) htmx.trigger(form, "submit"); };
        function persistSelection() {
            save({selection_permisos: Array.from(selection.keys())});
            paint();
        }
        function paint() {
            paintSelectionList(selection, function (pk) { selection.delete(pk); persistSelection(); syncChecks(); });
            const idsInput = document.getElementById("nui-selected-ids");
            if (idsInput) {
                const ids = Array.from(selection.keys()).join(",");
                const changed = idsInput.value !== ids;
                idsInput.value = ids;
                const only = document.getElementById("nui-only-selected");
                if (changed && only && only.checked) submitFilters();
            }
            if (subjectSelect && !subjectSelect.value) loadEditor(currentSubject());
        }
        function syncChecks() {
            const boxes = list.querySelectorAll(".nui-rowmark");
            boxes.forEach(function (box) {
                if (selection.has(box.value) && !selection.get(box.value)) selection.set(box.value, box.dataset.label || "");
                box.checked = selection.has(box.value);
            });
            const all = document.getElementById("nui-all");
            if (all) all.checked = boxes.length > 0 && Array.from(boxes).every(b => b.checked);
            paint();
        }
        const clear = document.getElementById("nui-sel-clear");
        if (clear) clear.addEventListener("click", function () { selection.clear(); persistSelection(); syncChecks(); });
        const onlyFiltered = document.getElementById("nui-sel-only-filtered");
        if (onlyFiltered) onlyFiltered.addEventListener("change", function () {
            if (!onlyFiltered.checked) return;
            const shown = new Set(Array.from(list.querySelectorAll(".nui-rowmark")).map(b => b.value));
            Array.from(selection.keys()).forEach(function (pk) { if (!shown.has(pk)) selection.delete(pk); });
            persistSelection();
            syncChecks();
            onlyFiltered.checked = false;
        });
        list.addEventListener("change", function (ev) {
            if (ev.target.id === "nui-all") {
                list.querySelectorAll(".nui-rowmark").forEach(function (box) {
                    box.checked = ev.target.checked;
                    if (box.checked) selection.set(box.value, box.dataset.label || ""); else selection.delete(box.value);
                });
                persistSelection();
                return;
            }
            if (ev.target.classList.contains("nui-rowmark")) {
                if (ev.target.checked) selection.set(ev.target.value, ev.target.dataset.label || ""); else selection.delete(ev.target.value);
                persistSelection();
                syncChecks();
            }
        });
        list.addEventListener("click", function (ev) {
            const sort = ev.target.closest("[data-nui-sort]");
            if (!sort || !form) return;
            ev.preventDefault();
            form.querySelector('[name="sort"]').value = sort.dataset.nuiSort;
            submitFilters();
        });
        document.body.addEventListener("htmx:afterSettle", function (ev) {
            if (ev.target === list) { restoreTabs(panelOf("listado").parentElement); syncChecks(); }
        });
        const clearSort = document.getElementById("nui-clear-sort");
        if (clearSort) clearSort.addEventListener("click", function () { form.querySelector('[name="sort"]').value = ""; submitFilters(); });

        const editor = document.getElementById("nui-editor");
        const subjectSelect = document.getElementById("nui-subject");
        function loadEditor(subject) {
            if (!editor) return;
            if (!subject) {
                editor.innerHTML = '<p class="text-muted small mb-0">Marca un solo usuario en el listado, o elige arriba un grupo o un rol, para ver y cambiar sus permisos.</p>';
                return;
            }
            editor.innerHTML = '<p class="text-muted small mb-0">Cargando…</p>';
            fetch(urls.editor + "?subject=" + encodeURIComponent(subject), {credentials: "same-origin"})
                .then(r => r.ok ? r.text() : Promise.reject(r.status))
                .then(html => { editor.innerHTML = html; })
                .catch(() => { editor.innerHTML = '<p class="text-danger small mb-0">No se ha podido cargar el editor.</p>'; });
        }
        function currentSubject() {
            const chosen = subjectSelect ? subjectSelect.value : "";
            if (chosen) return chosen;
            return selection.size === 1 ? "user:" + Array.from(selection.keys())[0] : "";
        }
        function openEditor(subject) {
            if (subjectSelect) subjectSelect.value = subject.startsWith("user:") ? "" : subject;
            const panel = panelOf("acciones");
            if (panel) showTab(panel, "ver", true);
            loadEditor(subject);
        }
        if (subjectSelect) subjectSelect.addEventListener("change", function () { loadEditor(currentSubject()); });
        if (editor) editor.addEventListener("change", function (ev) {
            const select = ev.target.closest("[data-view-key]");
            if (!select) return;
            const subject = editor.querySelector("[data-subject]").dataset.subject;
            post(urls.editor, new URLSearchParams({subject: subject, view_key: select.dataset.viewKey, level: select.value}))
                .then(function () { loadEditor(subject); submitFilters(); })
                .catch(() => {});
        });
        root.addEventListener("click", function (ev) {
            const edit = ev.target.closest("[data-nui-edit]");
            if (edit) { ev.preventDefault(); openEditor(edit.dataset.nuiEdit); return; }
            const pick = ev.target.closest("[data-nui-select-group]");
            if (pick) { ev.preventDefault(); loadGroups([pick.dataset.nuiSelectGroup]); return; }
            const del = ev.target.closest("[data-nui-delete-group]");
            if (del) {
                ev.preventDefault();
                post(urls.bulk, new URLSearchParams({action: "group_delete", group: del.dataset.nuiDeleteGroup}))
                    .then(() => window.location.reload()).catch(() => {});
            }
        });
        function loadGroups(ids) {
            fetch(urls.members + "?groups=" + ids.join(","), {credentials: "same-origin"})
                .then(r => r.json())
                .then(function (payload) {
                    selection.clear();
                    payload.users.forEach(([pk, name]) => selection.set(pk, name));
                    persistSelection();
                    syncChecks();
                    result(payload.users.length + " usuarios seleccionados de los grupos marcados.", false);
                });
        }
        root.querySelectorAll(".nui-group-check").forEach(function (box) {
            box.addEventListener("change", function () {
                const ids = Array.from(root.querySelectorAll(".nui-group-check:checked")).map(b => b.value);
                if (ids.length) loadGroups(ids);
            });
        });
        function ids() { return Array.from(selection.keys()).join(","); }
        function bulk(values, reload) {
            post(urls.bulk, new URLSearchParams(Object.assign({ids: ids()}, values)))
                .then(function () { if (reload) window.location.reload(); else submitFilters(); })
                .catch(() => {});
        }
        const grantBtn = document.getElementById("nui-grant-apply");
        if (grantBtn) grantBtn.addEventListener("click", function () {
            bulk({action: "grant", view_key: document.getElementById("nui-grant-view").value, level: document.getElementById("nui-grant-level").value}, false);
        });
        const createBtn = document.getElementById("nui-group-create");
        if (createBtn) createBtn.addEventListener("click", function () {
            bulk({action: "group_create", name: document.getElementById("nui-group-name").value}, true);
        });
        ["add", "remove"].forEach(function (verb) {
            const b = document.getElementById("nui-group-" + verb);
            if (b) b.addEventListener("click", function () {
                bulk({action: "group_" + verb, group: document.getElementById("nui-group-target").value}, true);
            });
        });
        syncChecks();
        loadEditor(currentSubject());
    }
}());
