/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/new_ui.js
 *
 * Nueva interfaz (S163, sesión invasora de UX): la vista única de
 * Documentación (panel/templates/panel/new_ui/shell.html).
 *
 * Común a todas las secciones (directriz 4.27, punto 4bis):
 *   - Cinco paneles: los tres de arriba cambian de altura arrastrando
 *     el asa horizontal; los dos de abajo cambian de anchura con el asa
 *     vertical (y de altura con la de arriba). Tamaños guardados por
 *     usuario (EbNavState, pantalla "nui", clave "layout").
 *   - Pestañas dentro de cada panel (data-nui-tab / data-nui-pane),
 *     guardadas por usuario (clave "tabs").
 *   - Selección persistente por sección (clave "selection_<sección>"),
 *     contador, Limpiar, "Seleccionar todos", visor de seleccionados.
 *   - Periodo rápido (botones día/semana/mes/año y actual/anterior).
 * Propio de Permisos: editor de permisos (usuario, grupo o rol),
 * acciones en bloque y grupos de usuarios (panel/views_new_ui.py).
 */
(function () {
    "use strict";

    const root = document.getElementById("nui");
    if (!root) return;
    const SCREEN = "nui";
    const section = root.dataset.section;
    const data = function (id) { return JSON.parse(document.getElementById(id).textContent); };
    const layout = Object.assign({top: 270, sel: 30}, data("nui-layout"));
    const tabs = data("nui-tabs");
    const selection = new Map(data("nui-selection").map(pk => [String(pk), ""]));

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
    restoreTabs();

    // ---- Periodo rápido ----
    const form = document.getElementById("nui-filters");
    function submitFilters() { if (form && window.htmx) htmx.trigger(form, "submit"); }
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

    // ---- Selección ----
    const list = document.getElementById("nui-lists");
    function paintSelection() {
        const ids = Array.from(selection.keys());
        root.querySelectorAll("[data-nui-count]").forEach(el => { el.textContent = ids.length; });
        const idsInput = document.getElementById("nui-selected-ids");
        if (idsInput) {
            const changed = idsInput.value !== ids.join(",");
            idsInput.value = ids.join(",");
            const only = document.getElementById("nui-only-selected");
            if (changed && only && only.checked) submitFilters();
        }
        const ul = document.getElementById("nui-selection-list");
        if (ul) {
            ul.innerHTML = "";
            if (!ids.length) {
                const li = document.createElement("li");
                li.className = "text-muted";
                li.textContent = "Nada seleccionado todavía.";
                ul.appendChild(li);
            }
            Array.from(selection.entries())
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
                    x.addEventListener("click", function () { selection.delete(pk); persistSelection(); syncChecks(); });
                    li.appendChild(span);
                    li.appendChild(x);
                    ul.appendChild(li);
                });
        }
        root.dispatchEvent(new CustomEvent("nui:selection", {detail: ids}));
    }
    function persistSelection() {
        const values = {};
        values["selection_" + section] = Array.from(selection.keys());
        save(values);
        paintSelection();
    }
    function syncChecks() {
        if (!list) { paintSelection(); return; }
        const boxes = list.querySelectorAll(".nui-row-check");
        boxes.forEach(function (box) {
            if (selection.has(box.value) && !selection.get(box.value)) selection.set(box.value, box.dataset.label || "");
            box.checked = selection.has(box.value);
        });
        const all = document.getElementById("nui-check-all");
        if (all) all.checked = boxes.length > 0 && Array.from(boxes).every(b => b.checked);
        const state = document.getElementById("nui-list-state");
        if (state) root.querySelectorAll("[data-nui-total]").forEach(el => { el.textContent = state.dataset.count; });
        paintSelection();
    }
    const clear = document.getElementById("nui-mass-clear");
    if (clear) clear.addEventListener("click", function () { selection.clear(); persistSelection(); syncChecks(); });
    if (list) {
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
            if (ev.target === list) { restoreTabs(list.closest("[data-nui-panel]").parentElement); syncChecks(); }
        });
    }
    const clearSort = document.getElementById("nui-clear-sort");
    if (clearSort) clearSort.addEventListener("click", function () { form.querySelector('[name="sort"]').value = ""; submitFilters(); });

    // ---- Avisos de resultado (nunca en silencio) ----
    function result(text, isError) {
        const box = document.getElementById("nui-result");
        if (!box) return;
        box.className = "alert small py-1 px-2 mt-2 mb-0 alert-" + (isError ? "danger" : "success");
        box.textContent = text;
    }
    function post(url, values) {
        const body = new URLSearchParams(values);
        result("Guardando…", false);
        return fetch(url, {
            method: "POST", credentials: "same-origin", body: body,
            headers: {"X-CSRFToken": csrf()},
        }).then(function (r) {
            return r.text().then(function (text) {
                let payload = null;
                try { payload = JSON.parse(text); } catch (e) { payload = null; }
                if (!r.ok) throw new Error(payload && payload.message ? payload.message : text || ("Error " + r.status));
                return payload || {};
            });
        }).then(function (payload) {
            result(payload.message || "Guardado.", false);
            return payload;
        }).catch(function (err) {
            result(err.message || "No se ha podido guardar.", true);
            throw err;
        });
    }

    if (section !== "permisos") { syncChecks(); return; }

    // ======================= PERMISOS =======================
    const urls = JSON.parse(document.getElementById("nui-urls").textContent);
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
        const panel = root.querySelector('[data-nui-panel="seleccion"]');
        if (panel) showTab(panel, "permisos", true);
        loadEditor(subject);
    }
    if (subjectSelect) subjectSelect.addEventListener("change", function () { loadEditor(currentSubject()); });
    root.addEventListener("nui:selection", function () {
        if (subjectSelect && !subjectSelect.value) loadEditor(currentSubject());
    });
    if (editor) editor.addEventListener("change", function (ev) {
        const select = ev.target.closest("[data-view-key]");
        if (!select) return;
        post(urls.editor, {subject: editor.querySelector("[data-subject]").dataset.subject, view_key: select.dataset.viewKey, level: select.value})
            .then(function () { loadEditor(editor.querySelector("[data-subject]").dataset.subject); submitFilters(); })
            .catch(function () { /* el aviso ya está pintado */ });
    });

    // Menú de tres puntos y botón derecho de las filas.
    root.addEventListener("click", function (ev) {
        const edit = ev.target.closest("[data-nui-edit]");
        if (edit) { ev.preventDefault(); openEditor(edit.dataset.nuiEdit); return; }
        const pick = ev.target.closest("[data-nui-select-group]");
        if (pick) { ev.preventDefault(); loadGroups([pick.dataset.nuiSelectGroup]); return; }
        const del = ev.target.closest("[data-nui-delete-group]");
        if (del) {
            ev.preventDefault();
            post(urls.bulk, {action: "group_delete", group: del.dataset.nuiDeleteGroup})
                .then(() => window.location.reload()).catch(() => {});
        }
    });

    // Grupos de selección = grupos de usuarios: la suma de los marcados.
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

    // Acciones en bloque.
    function ids() { return Array.from(selection.keys()).join(","); }
    function bulk(values, reload) {
        post(urls.bulk, Object.assign({ids: ids()}, values))
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
}());
