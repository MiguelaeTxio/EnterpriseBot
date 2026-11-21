/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/new_ui.js
 *
 * Nueva interfaz (S163, sesión invasora de UX): la vista única de
 * Documentación (panel/templates/panel/new_ui/shell.html).
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
 * con su tarjeta y sus acciones; exportar; grupos de selección.
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
        if (window.EbNavState) window.EbNavState.save(SCREEN, values);
    }
    function csrf() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    // ---- Alto de la vista y tamaños de los paneles ----
    function fitHeight() {
        const top = root.getBoundingClientRect().top;
        root.style.height = Math.max(520, window.innerHeight - top - 12) + "px";
    }
    function applyLayout() {
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
        layout.top = Math.min(root.clientHeight - 200, Math.max(120, e.clientY - box.top));
    });
    if (vHandle) dragger(vHandle, function (e) {
        const box = root.querySelector(".nui-bottom").getBoundingClientRect();
        layout.sel = Math.min(70, Math.max(15, (box.right - e.clientX) / box.width * 100));
    });
    window.addEventListener("resize", fitHeight);
    fitHeight();
    applyLayout();

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

    if (section === "permisos") { permisos(); } else { lists(); }
    restoreTabs();

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
        function refreshSelection() {
            const map = sel();
            paintSelectionList(map, function (pk) { map.delete(pk); persistSelection(); syncChecks(); });
            const idsInput = document.getElementById("nui-selected-ids");
            if (idsInput) idsInput.value = Array.from(map.keys()).join(",");
            if (groups) groups.refresh();
        }
        function syncChecks() {
            const box = pane();
            const map = sel();
            if (box) {
                const boxes = box.querySelectorAll(".nui-row-check");
                boxes.forEach(function (b) {
                    if (map.has(b.value) && !map.get(b.value)) map.set(b.value, b.dataset.label || "");
                    b.checked = map.has(b.value);
                });
                const all = box.querySelector("#nui-check-all");
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
        function load() {
            const t = tab();
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
            root.querySelectorAll("[data-nui-cols-for]").forEach(el => el.classList.toggle("d-none", el.dataset.nuiColsFor !== t));
            root.querySelectorAll("[data-nui-note-for]").forEach(el => el.classList.toggle("d-none", el.dataset.nuiNoteFor !== t));
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
            if (window.EbNavState && window.EbNavState.flush) window.EbNavState.flush();
            setTimeout(load, 300);
        });

        // Casillas, orden y "ver sus listados".
        const lists = document.getElementById("nui-lists");
        lists.addEventListener("change", function (ev) {
            const map = sel();
            if (ev.target.id === "nui-check-all") {
                pane().querySelectorAll(".nui-row-check").forEach(function (b) {
                    b.checked = ev.target.checked;
                    if (b.checked) map.set(b.value, b.dataset.label || ""); else map.delete(b.value);
                });
                persistSelection();
                return;
            }
            if (ev.target.classList.contains("nui-row-check")) {
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
        const clear = document.getElementById("nui-mass-clear");
        if (clear) clear.addEventListener("click", function () { sel().clear(); persistSelection(); syncChecks(); });

        // Una sola persona o máquina: toda la vista con lo suyo.
        const chip = document.getElementById("nui-scope-chip");
        function paintScope() {
            if (chip) {
                chip.classList.toggle("d-none", !(scope && scope.pk));
                chip.classList.toggle("d-flex", !!(scope && scope.pk));
                const label = document.getElementById("nui-scope-label");
                if (label) label.textContent = scope ? scope.label : "";
            }
            loadCard();
            loadEntityActions();
        }
        function setScope(value) {
            if (section === "doc") {
                // En Documentos, la persona se abre en Personal.
                const values = {"scope_per": value};
                save(values);
                if (window.EbNavState && window.EbNavState.flush) window.EbNavState.flush();
                setTimeout(function () { window.location.href = "?s=per"; }, 300);
                return;
            }
            scope = value;
            const values = {};
            values["scope_" + section] = value;
            save(values);
            paintScope();
            const sp = panelOf("seleccion");
            if (sp && value && sp.querySelector('[data-nui-tab="tarjeta"]')) showTab(sp, "tarjeta", true);
            load();
        }
        const scopeClear = document.getElementById("nui-scope-clear");
        if (scopeClear) scopeClear.addEventListener("click", function () { setScope(null); });

        // Acciones de la persona o máquina vista (las del botón derecho).
        function loadEntityActions() {
            const box = document.getElementById("nui-entity-actions");
            if (!box) return;
            if (!(scope && scope.pk)) {
                box.innerHTML = '<p class="small text-muted mb-0">Pulsa ' + (section === "cdg" ? "un centro de gasto" : "una persona") + ' en el listado: aquí salen todas sus acciones (las mismas del botón derecho).</p>';
                return;
            }
            const url = section === "cdg" ? "/panel/documentacion/maquinaria/" + scope.pk + "/menu/" : "/panel/documentacion/personal/" + scope.pk + "/menu/";
            fetch(url, {credentials: "same-origin"}).then(r => r.json()).then(function (data) {
                box.innerHTML = "";
                const title = document.createElement("div");
                title.className = "small fw-semibold mb-1";
                title.textContent = data.name;
                box.appendChild(title);
                const wrap = document.createElement("div");
                wrap.className = "d-flex flex-wrap gap-1";
                data.items.forEach(function (item) {
                    const a = document.createElement("a");
                    a.className = "btn btn-sm btn-outline-primary";
                    a.href = item.url;
                    a.innerHTML = '<i class="bi ' + item.icon + ' me-1"></i>';
                    a.appendChild(document.createTextNode(item.label));
                    if (item.card) {
                        a.addEventListener("click", function (ev) { ev.preventDefault(); window.EbMachineCard.open(item.url); });
                    }
                    wrap.appendChild(a);
                });
                box.appendChild(wrap);
            }).catch(function () { box.innerHTML = '<p class="small text-danger mb-0">No se han podido cargar sus acciones.</p>'; });
        }

        // Tarjeta: foto, datos, Modificar.
        const cardBox = document.getElementById("nui-card");
        function loadCard() {
            if (!cardBox) return;
            if (!(scope && scope.pk)) {
                cardBox.innerHTML = '<p class="text-muted small mb-0">Pulsa ' + (section === "cdg" ? "un centro de gasto" : "una persona") + ' en el listado para ver aquí su tarjeta.</p>';
                return;
            }
            cardBox.innerHTML = '<p class="text-muted small mb-0">Cargando…</p>';
            fetch(urls.card + "?s=" + section + "&pk=" + scope.pk, {credentials: "same-origin"})
                .then(r => r.ok ? r.text() : Promise.reject(r.status))
                .then(function (html) { cardBox.innerHTML = html; })
                .catch(function () { cardBox.innerHTML = '<p class="text-danger small mb-0">No se ha podido cargar la tarjeta.</p>'; });
        }
        function cardResult(text, isError) {
            const box = cardBox.querySelector("[data-nui-card-result]");
            if (!box) return;
            box.className = "alert small py-1 px-2 mb-2 alert-" + (isError ? "danger" : "success");
            box.textContent = text;
        }
        function cardEditing(on) {
            cardBox.querySelectorAll("[data-nui-card-view]").forEach(el => el.classList.toggle("d-none", on));
            const f = cardBox.querySelector("[data-nui-card-form]");
            if (f) f.classList.toggle("d-none", !on);
        }
        if (cardBox) {
            cardBox.addEventListener("click", function (ev) {
                if (ev.target.closest("[data-nui-card-edit]")) cardEditing(true);
                if (ev.target.closest("[data-nui-card-cancel]")) cardEditing(false);
            });
            cardBox.addEventListener("submit", function (ev) {
                const f = ev.target.closest("[data-nui-card-form]");
                if (!f) return;
                ev.preventDefault();
                const body = new FormData(f);
                post(f.getAttribute("action"), body, cardResult)
                    .then(function () { setTimeout(function () { loadCard(); load(); }, 600); })
                    .catch(() => {});
            });
            cardBox.addEventListener("change", function (ev) {
                const input = ev.target.closest("[data-nui-card-photo]");
                if (!input || !input.files.length) return;
                const card = cardBox.querySelector(".nui-card");
                const urlsBox = cardBox.querySelector("[data-nui-card-urls]");
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
        }

        // Exportar.
        root.querySelectorAll("[data-nui-export]").forEach(function (button) {
            button.addEventListener("click", function () {
                const p = params({export_format: button.dataset.nuiExport});
                Array.from(sel().keys()).forEach(pk => p.append("selected", pk));
                const url = urls.export + "?" + p.toString();
                if (button.dataset.nuiExport === "print" || button.dataset.nuiExport === "html") window.open(url, "_blank");
                else window.location.href = url;
                result("Preparando la exportación de «" + (listPanel.querySelector(".nav-link.active") || {}).textContent + "»…", false);
            });
        });

        // Grupos de selección de siempre (máquinas o personas) sobre "General".
        if (window.EbSelectionGroups && document.getElementById("nuiGroupSavedList")) {
            const machines = section === "cdg";
            groups = window.EbSelectionGroups.init({
                prefix: "nuiGroup",
                memoryKey: "nui_" + section,
                collapsedKey: machines ? "machine_groups" : "person_groups",
                saveUrl: machines ? urls.fleetGroupSave : urls.personGroupSave,
                updateUrl: function (pk) {
                    return machines ? "/panel/fleet/grupos/" + pk + "/guardar/" : urls.personGroupUpdate.replace("/0/", "/" + pk + "/");
                },
                deleteUrl: function (pk) {
                    return machines ? "/panel/fleet/grupos/" + pk + "/eliminar/" : urls.personGroupDelete.replace("/0/", "/" + pk + "/");
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
            const boxes = list.querySelectorAll(".nui-row-check");
            boxes.forEach(function (box) {
                if (selection.has(box.value) && !selection.get(box.value)) selection.set(box.value, box.dataset.label || "");
                box.checked = selection.has(box.value);
            });
            const all = document.getElementById("nui-check-all");
            if (all) all.checked = boxes.length > 0 && Array.from(boxes).every(b => b.checked);
            paint();
        }
        const clear = document.getElementById("nui-mass-clear");
        if (clear) clear.addEventListener("click", function () { selection.clear(); persistSelection(); syncChecks(); });
        list.addEventListener("change", function (ev) {
            if (ev.target.id === "nui-check-all") {
                list.querySelectorAll(".nui-row-check").forEach(function (box) {
                    box.checked = ev.target.checked;
                    if (box.checked) selection.set(box.value, box.dataset.label || ""); else selection.delete(box.value);
                });
                persistSelection();
                return;
            }
            if (ev.target.classList.contains("nui-row-check")) {
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
            const panel = panelOf("seleccion");
            if (panel) showTab(panel, "permisos", true);
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
