// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/selection_groups.js
// H31 (S148). Recuadro "Grupos de selección" con gestión (crear,
// cambiar, borrar, "Dentro de" por niveles, cambios sin guardar), el
// mismo comportamiento que el de Personal (S147, _personal_pane.html),
// sacado aquí para usarlo en Centros de Gasto con máquinas. Miguel
// Ángel: "Vamos a hacer lo mismo que en personal, creando los grupos
// de selección".
//
// Uso:
//   EbSelectionGroups.init({
//     prefix: "machineGroup",            // ids del árbol y del formulario
//     collapsedKey: "machine_groups",    // plegado por usuario
//     saveUrl: "/panel/fleet/grupos/guardar/",
//     updateUrl: (pk) => ..., deleteUrl: (pk) => ...,
//     memberField: "machine_ids",
//     noun: "máquina",
//     getIds: () => [...pks marcados...],
//     setIds: (pairs) => {...},          // [[pk, nombre], ...]
//     labelOf: (pk) => "nombre",
//     toast: (texto, esError) => {...},
//     extra: (formData, accion) => {...},  // opcional: campos de más
//   });
// Devuelve {refresh}: llamarlo cada vez que cambie la selección.
// Reglas (iguales que Personal): marcar grupos selecciona la suma de
// sus miembros; la casilla de un grupo con subgrupos marca los
// subgrupos; marcar un subgrupo nunca marca el padre (queda a medias);
// se edita el grupo marcado él solo y solo si es de quien mira; con
// otro nombre, Guardar crea un grupo nuevo.
(function () {
    "use strict";

    function esc(text) {
        return String(text).replace(/[<>&]/g, "");
    }

    function getCookie(name) {
        const value = "; " + document.cookie;
        const parts = value.split("; " + name + "=");
        return parts.length === 2 ? parts.pop().split(";").shift() : "";
    }

    function init(cfg) {
        const p = cfg.prefix;
        const $ = (suffix) => document.getElementById(p + suffix);
        const list = $("SavedList");
        if (!list || list.dataset.bound) return {refresh: function () {}};
        list.dataset.bound = "1";
        const nounPlural = cfg.nounPlural || cfg.noun + "s";

        let editingPk = "";
        let editingName = "";
        let parentTouched = false;
        let savedIds = new Set();
        let savedNames = new Map();

        const row = (pk) => document.getElementById(p + "Row" + pk);
        const box = (pk) => document.getElementById(p + "Select" + pk);
        const folderRow = (key) => list.querySelector('.person-group-folder[data-pk="' + key + '"]');
        function children(pk) {
            const r = row(pk);
            return r && r.dataset.children ? r.dataset.children.split(",").filter(Boolean) : [];
        }
        function descendants(pk) {
            const out = [];
            const stack = children(pk);
            while (stack.length) {
                const child = stack.pop();
                out.push(child);
                children(child).forEach((c) => stack.push(c));
            }
            return out;
        }
        function checkedGroups() {
            return Array.from(list.querySelectorAll(".person-group-select-checkbox:checked")).map((el) => el.dataset.pk);
        }
        function isNewCopy() {
            return Boolean(editingPk) && $("Name").value.trim() !== editingName;
        }
        function activate() {
            $("ManagementEmpty").classList.add("d-none");
            $("ManagementForm").classList.remove("d-none");
        }

        // "Dentro de" por niveles, como en Personal.
        function buildParentPicker() {
            const sel = $("Parent");
            const pickerBox = $("ParentPicker");
            const opts = Array.from(sel.options)
                .filter((o) => o.value && !o.disabled)
                .map((o) => ({pk: o.value, parent: o.dataset.parent || "", name: o.dataset.name || o.textContent}));
            const avail = new Set(opts.map((o) => o.pk));
            const byPk = new Map(opts.map((o) => [o.pk, o]));
            const kids = (pk) => opts.filter((o) => (pk ? o.parent === pk : (!o.parent || !avail.has(o.parent))));
            const path = [];
            let cur = avail.has(sel.value) ? sel.value : "";
            while (cur) {
                path.unshift(cur);
                const o = byPk.get(cur);
                cur = o && avail.has(o.parent) ? o.parent : "";
            }
            if (!avail.has(sel.value)) sel.value = "";
            const signature = sel.value + "|" + opts.map((o) => o.pk + ":" + o.parent + ":" + o.name).join(",");
            if (pickerBox.dataset.signature === signature) return;
            if (pickerBox.contains(document.activeElement)) return;
            pickerBox.dataset.signature = signature;
            pickerBox.innerHTML = "";
            function addLevel(items, chosen, parentPk) {
                if (parentPk) {
                    const label = document.createElement("div");
                    label.className = "small text-muted mb-1";
                    label.textContent = "¿Dentro de algún subgrupo de «" + byPk.get(parentPk).name + "»?";
                    pickerBox.appendChild(label);
                }
                const s = document.createElement("select");
                s.className = "form-select form-select-sm mb-1";
                s.setAttribute("aria-label", "Dentro de");
                s.add(parentPk
                    ? new Option("No: directamente en «" + byPk.get(parentPk).name + "»", parentPk)
                    : new Option("Dentro de: ninguno (grupo principal)", ""));
                items.forEach((o) => s.add(new Option((parentPk ? "Sí: dentro de «" + o.name + "»" : "Dentro de: " + o.name), o.pk)));
                s.value = chosen || (parentPk || "");
                s.addEventListener("change", () => {
                    sel.value = s.value;
                    parentTouched = true;
                    s.blur();
                    refresh();
                });
                pickerBox.appendChild(s);
            }
            addLevel(kids(""), path[0], "");
            path.forEach((pk, i) => {
                const c = kids(pk);
                if (c.length) addLevel(c, path[i + 1], pk);
            });
        }

        function refresh() {
            const diff = $("Diff");
            const saveBtn = $("SaveBtn");
            const parentSelect = $("Parent");
            const ids = cfg.getIds().map(String);
            saveBtn.classList.add("btn-primary");
            saveBtn.classList.remove("btn-warning");
            saveBtn.textContent = "Guardar";
            const banned = (editingPk && !isNewCopy())
                ? new Set([editingPk].concat(descendants(editingPk))) : new Set();
            Array.from(parentSelect.options).forEach((opt) => { opt.disabled = banned.has(opt.value); });
            buildParentPicker();
            if (ids.length) activate();
            if (!editingPk) {
                const many = checkedGroups().length > 1;
                diff.classList.toggle("d-none", !many);
                diff.innerHTML = many ? '<span class="text-muted">Varios grupos marcados: la selección es la suma de sus ' +
                    nounPlural + ". Para cambiar uno, márcalo solo; Guardar crea un grupo nuevo con esta selección.</span>" : "";
                return;
            }
            if (isNewCopy()) {
                const parentText = parentSelect.selectedOptions.length ? parentSelect.selectedOptions[0].textContent : "";
                diff.classList.remove("d-none");
                diff.innerHTML = '<div class="fw-semibold">Grupo nuevo</div><div class="text-muted">«' +
                    esc($("Name").value.trim()) + "» con " + ids.length + " " + (ids.length === 1 ? cfg.noun : nounPlural) +
                    " (" + esc(parentText) + "). «" + esc(editingName) + "» no se toca.</div>";
                saveBtn.textContent = "Crear grupo nuevo";
                return;
            }
            const current = new Set(ids);
            const added = ids.filter((pk) => !savedIds.has(pk));
            const removed = Array.from(savedIds).filter((pk) => !current.has(pk));
            const label = (pk) => cfg.labelOf(pk) || savedNames.get(pk) || ("#" + pk);
            diff.classList.remove("d-none");
            if (!added.length && !removed.length) {
                diff.innerHTML = '<span class="text-muted">Sin cambios: desmarca para quitar o marca otra (con cualquier filtro) para añadirla. Con otro nombre, se crea un grupo nuevo.</span>';
                return;
            }
            let html = '<div class="fw-semibold">Cambios sin guardar</div>';
            if (added.length) html += '<div class="text-success">+ Se añaden (' + added.length + "): " + esc(added.map(label).sort().join("; ")) + "</div>";
            if (removed.length) html += '<div class="text-danger">− Se quitan (' + removed.length + "): " + esc(removed.map(label).sort().join("; ")) + "</div>";
            html += '<div class="text-muted">Con otro nombre, se crea un grupo nuevo y este no se toca.</div>';
            diff.innerHTML = html;
            saveBtn.textContent = "Actualizar el grupo";
            saveBtn.classList.remove("btn-primary");
            saveBtn.classList.add("btn-warning");
        }

        function applyCheckedGroups() {
            const pairs = [];
            const seen = new Set();
            checkedGroups().forEach((pk) => {
                const r = row(pk);
                if (!r) return;
                const ids = (r.dataset.memberIds || "").split(",").filter(Boolean);
                const names = (r.dataset.memberNames || "").split("||");
                ids.forEach((id, i) => {
                    if (seen.has(id)) return;
                    seen.add(id);
                    pairs.push([id, names[i] || ""]);
                });
            });
            cfg.setIds(pairs);
        }

        function setEditingTarget(pk) {
            const checked = new Set(checkedGroups());
            const expected = new Set([pk].concat(pk ? descendants(pk) : []));
            const isRoot = pk && checked.size === expected.size && Array.from(checked).every((g) => expected.has(g));
            const isTarget = isRoot && row(pk).dataset.canEdit === "1";
            const parentSelect = $("Parent");
            if (isTarget) {
                const r = row(pk);
                editingPk = String(pk);
                const ids = (r.dataset.memberIds || "").split(",").filter(Boolean);
                const names = (r.dataset.memberNames || "").split("||");
                savedIds = new Set(ids);
                savedNames = new Map(ids.map((id, i) => [id, names[i] || ""]));
                parentTouched = false;
                editingName = r.dataset.name || "";
                $("Name").value = editingName;
                parentSelect.value = r.dataset.parent || "";
                $("DeleteBtn").classList.remove("d-none");
            } else {
                editingPk = "";
                editingName = "";
                parentTouched = false;
                savedIds = new Set();
                savedNames = new Map();
                Array.from(parentSelect.options).forEach((opt) => { opt.disabled = false; });
                $("DeleteBtn").classList.add("d-none");
                if (isRoot) {
                    $("FormResult").innerHTML = '<div class="alert alert-info py-1 px-2 small mb-0">Grupo de ' +
                        esc(row(pk).dataset.owner || "otro usuario") +
                        ": lo puedes usar, pero solo quien lo creó lo cambia. Guardar crea un grupo nuevo tuyo con esta selección.</div>";
                }
            }
            buildParentPicker();
        }

        function onGroupChange(checkbox) {
            const pk = checkbox.dataset.pk;
            descendants(pk).forEach((child) => {
                const cb = box(child);
                if (cb) cb.checked = checkbox.checked;
            });
            let parent = row(pk) && row(pk).dataset.parent;
            while (parent) {
                const cb = box(parent);
                if (cb) {
                    if (!checkbox.checked) cb.checked = false;
                    cb.indeterminate = !cb.checked && descendants(parent).some((k) => box(k) && box(k).checked);
                }
                parent = row(parent) && row(parent).dataset.parent;
            }
            activate();
            applyCheckedGroups();
            const checkedSet = new Set(checkedGroups());
            const roots = Array.from(checkedSet).filter((g) => {
                const r = row(g);
                return !(r && r.dataset.parent && checkedSet.has(r.dataset.parent));
            });
            $("FormResult").innerHTML = "";
            setEditingTarget(roots.length === 1 ? roots[0] : "");
            if (!checkedGroups().length) $("Name").value = "";
            refresh();
        }

        // Plegado recordado por usuario.
        let collapsed = new Set((list.dataset.collapsed || "").split(",").filter(Boolean));
        function applyCollapsed() {
            list.querySelectorAll(".person-group-node, .person-group-folder").forEach((r) => {
                let hidden = false;
                let parent = r.dataset.parent;
                while (parent) {
                    if (collapsed.has(parent)) { hidden = true; break; }
                    parent = row(parent) && row(parent).dataset.parent;
                }
                let folder = r.dataset.folder;
                while (!hidden && folder) {
                    if (collapsed.has(folder)) { hidden = true; break; }
                    folder = folderRow(folder) && folderRow(folder).dataset.folder;
                }
                r.classList.toggle("d-none", hidden);
                const icon = r.querySelector(".person-group-toggle i");
                if (icon) icon.className = collapsed.has(r.dataset.pk) ? "bi bi-chevron-right" : "bi bi-chevron-down";
            });
        }
        list.addEventListener("click", function (ev) {
            // S148: papelera de cada grupo propio sin subgrupos.
            const trash = ev.target.closest(".person-group-delete");
            if (trash) { remove(trash.dataset.pk, trash.dataset.name); return; }
            const toggle = ev.target.closest(".person-group-toggle");
            if (!toggle) return;
            const pk = toggle.dataset.pk;
            if (collapsed.has(pk)) collapsed.delete(pk); else collapsed.add(pk);
            applyCollapsed();
            window.EbNavState.save(cfg.collapsedKey, {collapsed: Array.from(collapsed)});
        });
        list.addEventListener("change", function (ev) {
            if (ev.target.classList.contains("person-group-select-checkbox")) onGroupChange(ev.target);
        });

        $("Name").addEventListener("input", function () {
            if (editingPk && !parentTouched) {
                const r = row(editingPk);
                $("Parent").value = isNewCopy() ? editingPk : ((r && r.dataset.parent) || "");
            }
            refresh();
        });

        function redraw(data, checkPk) {
            list.innerHTML = data.tree_html;
            const parentSelect = $("Parent");
            parentSelect.innerHTML = '<option value="">Dentro de: ninguno (grupo principal)</option>';
            (data.parents || []).forEach((item) => {
                const opt = new Option("Dentro de: " + item.label, String(item.pk));
                opt.dataset.parent = String(item.parent || "");
                opt.dataset.name = item.name || item.label;
                parentSelect.add(opt);
            });
            applyCollapsed();
            if (checkPk) {
                const cb = box(checkPk);
                if (cb) {
                    cb.checked = true;
                    descendants(checkPk).forEach((c) => { const k = box(c); if (k) k.checked = true; });
                }
                setEditingTarget(String(checkPk));
            } else {
                setEditingTarget("");
            }
            refresh();
        }

        function reset() {
            list.querySelectorAll(".person-group-select-checkbox").forEach((el) => { el.checked = false; el.indeterminate = false; });
            setEditingTarget("");
            $("Name").value = "";
            $("Parent").value = "";
            $("FormResult").innerHTML = "";
            refresh();
        }

        function save() {
            const name = $("Name").value.trim();
            const result = $("FormResult");
            if (!name) {
                result.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">Falta el nombre del grupo.</div>';
                return;
            }
            const form = new FormData();
            form.append("name", name);
            form.append("parent_id", $("Parent").value);
            cfg.getIds().forEach((pk) => form.append(cfg.memberField, pk));
            if (cfg.extra) cfg.extra(form);
            const wasEditing = Boolean(editingPk) && !isNewCopy();
            const url = wasEditing ? cfg.updateUrl(editingPk) : cfg.saveUrl;
            fetch(url, {method: "POST", body: form, headers: {"X-CSRFToken": getCookie("csrftoken")}})
                .then((r) => r.json())
                .then((data) => {
                    if (!data.ok) {
                        result.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">' + esc(data.error || "Error al guardar.") + "</div>";
                        return;
                    }
                    result.innerHTML = "";
                    list.querySelectorAll(".person-group-select-checkbox").forEach((el) => { el.checked = false; });
                    if (wasEditing) {
                        redraw(data, data.id);
                        cfg.toast("Grupo guardado.");
                    } else {
                        redraw(data, "");
                        $("Name").value = "";
                        cfg.toast("Grupo creado.");
                    }
                })
                .catch(() => {
                    result.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">Error de red al guardar.</div>';
                });
        }

        function remove(trashPk, trashName) {
            const pk = (typeof trashPk === "string" && trashPk) || editingPk;
            if (!pk) return;
            const label = trashName ? "«" + trashName + "»" : "este grupo";
            if (!confirm("¿Eliminar " + label + "? No afecta a las " + nounPlural + " en sí.")) return;
            const result = $("FormResult");
            const body = new FormData();
            if (cfg.extra) cfg.extra(body, "delete");
            fetch(cfg.deleteUrl(pk), {method: "POST", body: body, headers: {"X-CSRFToken": getCookie("csrftoken")}})
                .then((r) => r.json())
                .then((data) => {
                    if (data.ok) {
                        const keep = String(editingPk) !== String(pk) ? editingPk : "";
                        redraw(data, keep);
                        if (!keep) $("Name").value = "";
                        cfg.toast("Grupo eliminado.");
                    } else {
                        result.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">' + esc(data.error || "No se ha podido eliminar.") + "</div>";
                    }
                })
                .catch(() => {
                    result.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">No se ha podido eliminar el grupo.</div>';
                });
        }

        $("SaveBtn").addEventListener("click", save);
        $("DeleteBtn").addEventListener("click", function () { remove(); });
        $("ResetBtn").addEventListener("click", reset);
        applyCollapsed();
        buildParentPicker();
        return {refresh: refresh};
    }

    window.EbSelectionGroups = {init: init};
}());
