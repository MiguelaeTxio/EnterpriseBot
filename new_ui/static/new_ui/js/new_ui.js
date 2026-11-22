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
        // Acciones › De la vista: el bloque de la vista abierta.
        function paintViewActions(t) {
            const blocks = root.querySelectorAll("[data-nui-actions-for]");
            let any = false;
            blocks.forEach(function (b) {
                const on = b.dataset.nuiActionsFor.split(" ").indexOf(t) !== -1;
                b.classList.toggle("d-none", !on);
                any = any || on;
            });
            const none = root.querySelector("[data-nui-actions-none]");
            if (none) none.classList.toggle("d-none", any);
            const label = listPanel.querySelector(':scope > .nui-tabs [data-nui-tab="' + t + '"]');
            const tabButton = document.getElementById("nui-view-actions-tab");
            if (tabButton) tabButton.textContent = "De " + (label ? label.textContent.trim() : "la vista");
        }
        listPanel.addEventListener("nui:tab", function (ev) { paintViewActions(ev.detail); });
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
                if (!ids.length) { result("Marca primero en el listado las filas a las que aplicarlo.", true); return; }
                ids.forEach(id => body.append("selected", id));
            }
            const url = (submitter && submitter.getAttribute("formaction")) || f.getAttribute("action");
            if (f.hasAttribute("data-nui-download")) { download(url, body); return; }
            post(url, body)
                .then(function (data) {
                    result(data.message || "Hecho.", false);
                    // Lo guardado sigue en el formulario: guardar otra vez lo modifica.
                    const pkInput = f.querySelector("[data-nui-pk]");
                    if (pkInput && data.id) pkInput.value = data.id;
                    // Lo de la persona vista (su foto) se repinta.
                    if (f.closest("#nui-entity-actions")) loadEntityActions();
                    // Formularios de un solo uso (subir): vuelven a empezar.
                    if (f.hasAttribute("data-nui-reset-after")) {
                        f.reset();
                        f.querySelectorAll("[data-nui-clear]").forEach(i => { i.value = ""; });
                        f.querySelectorAll("[data-default]").forEach(el => { el.textContent = el.dataset.default; });
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
            fetch(url, {method: "POST", credentials: "same-origin", body: body, headers: {"X-CSRFToken": csrf()}})
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
                    const match = /filename="?([^";]+)"?/.exec(disposition);
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
                goToActions(uploadForm);
                return;
            }
            if (kind === "nui-doc-split") {
                const box = document.getElementById("nui-split-box");
                if (!box) return;
                box.innerHTML = '<p class="small text-muted mb-0">Cargando las páginas…</p>';
                goToActions(box);
                fetch(box.dataset.url.replace("/0/", "/" + parts[1] + "/"), {credentials: "same-origin"})
                    .then(r => r.ok ? r.text() : Promise.reject(new Error("No se ha podido abrir el documento.")))
                    .then(function (html) { box.innerHTML = html; })
                    .catch(function (err) { box.innerHTML = ""; result(err.message, true); });
            }
        });
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
            const items = mark ? Array.from(mark.closest("tr").querySelectorAll("[data-nui-row-actions] .dropdown-item")) : [];
            if (!items.length) {
                const p = document.createElement("p");
                p.className = "small text-muted mb-0";
                p.textContent = map.size === 1 ? "Esa fila no tiene acciones propias." : "Marca una sola fila del listado para ver aquí sus acciones.";
                box.appendChild(p);
                return;
            }
            const title = document.createElement("div");
            title.className = "small fw-semibold mb-1";
            title.textContent = mark.dataset.label || "";
            box.appendChild(title);
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
            fetch(urls.list + "?" + params().toString(), {credentials: "same-origin"})
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
            if (pick) { ev.preventDefault(); setScope({pk: pick.dataset.nuiScope, label: pick.dataset.nuiScopeLabel}); }
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
                const title = document.createElement("div");
                title.className = "small fw-semibold mb-1";
                title.textContent = scope.label;
                box.appendChild(title);
                p.textContent = "Todo lo suyo está en las pestañas de abajo.";
                if (section === "per" && urls.photoPanel) {
                    // S163: su foto (para plataformas, girar, subir...).
                    const photo = document.createElement("div");
                    photo.className = "mt-2";
                    box.appendChild(p);
                    box.appendChild(photo);
                    fetch(urls.photoPanel.replace("/0/", "/" + scope.pk + "/"), {credentials: "same-origin"})
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
        function loadCard() {
            const box = fichaBox();
            if (!box) return Promise.resolve();
            if (!(scope && scope.pk)) { box.innerHTML = ""; return Promise.resolve(); }
            const ticket = ++loading;
            box.innerHTML = '<p class="text-muted small p-3 mb-0">Cargando…</p>';
            return fetch(urls.card + "?s=" + section + "&t=" + tab() + "&pk=" + scope.pk, {credentials: "same-origin"})
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

        // Exportar.
        root.querySelectorAll("[data-nui-export]").forEach(function (button) {
            button.addEventListener("click", function () {
                if (isEntityTab(tab())) {
                    result(section === "cdg" ? "La ficha se exporta con su botón «Exportar» (PDF, Word, HTML, PNG o JPG)." : "La ficha no es un listado: elige otra pestaña para exportar.", false);
                    return;
                }
                const p = params({export_format: button.dataset.nuiExport});
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
