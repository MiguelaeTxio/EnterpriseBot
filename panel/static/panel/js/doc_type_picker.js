// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/doc_type_picker.js
//
// H30 (S128). Gestor común de "Requisitos de documentación" y
// "Dosieres" (plantillas de dosier) del hub de Documentación.
//
// Miguel Ángel (S128): "Cuando yo selecciono general, me debe de
// aparecer [...] los que tengan marca deben de aparecer marcados [...]
// y [...] en el listado de los documentos que tiene seleccionado [...]
// puedas añadir o quitar al vuelo [...] y que tengas libertad a la
// hora de crear uno nuevo cambiándole el nombre." Y: "quiero eliminar
// lo de plantilla activa".
//
// Por qué un componente y no dos scripts sueltos: las dos pantallas
// vivían en el mismo hub con los mismos ids (formTitle,
// draftPreviewList...) y las mismas variables globales (`let
// lastSnapshot`). La segunda pestaña cargada lanzaba un SyntaxError
// por redeclaración y su script entero no se ejecutaba: sin colores,
// sin cargar al pulsar, sin guardar. Aquí todo cuelga de la raíz de
// cada pantalla (`[data-tp-root]`, atributos `data-tp-*`) y nada es
// global salvo `window.EbTypePicker`.
//
// Uso: `EbTypePicker.init(rootElement)`, una vez por fragmento. La
// configuración llega en atributos data- de la raíz (ver
// panel/templates/panel/_doc_type_picker.html).
(function () {
    'use strict';

    if (window.EbTypePicker) {
        return;
    }

    var LG_BREAKPOINT = 992;
    var COUNTDOWN_SECONDS = 5;

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function postForm(url, formData) {
        return fetch(url, {
            method: 'POST',
            body: formData,
            headers: {'X-CSRFToken': csrfToken()},
        }).then(function (response) {
            return response.json().catch(function () {
                return {ok: false, error: 'Respuesta no válida del servidor.'};
            });
        });
    }

    function splitIds(raw) {
        return (raw || '').split(',').filter(Boolean);
    }

    function init(root) {
        if (!root || root.dataset.tpReady === '1') {
            return;
        }
        root.dataset.tpReady = '1';

        var cfg = root.dataset;
        var requireName = cfg.tpRequireName === '1';
        var requireItems = cfg.tpRequireItems === '1';
        var nounNew = cfg.tpNounNew || 'Nuevo';

        function q(role) {
            return root.querySelector('[data-tp="' + role + '"]');
        }
        function qa(selector) {
            return Array.prototype.slice.call(root.querySelectorAll(selector));
        }

        var nameInput = q('name');
        var titleEl = q('title');
        var previewList = q('preview-list');
        var resultEl = q('result');
        var tbody = q('rows');
        var selectAll = q('select-all');
        var selectionCount = q('selection-count');

        var loadedPk = '';
        var loadedName = null;
        var snapshot = null;

        // --- Colores de familia (dato del catálogo, fuera de style= en
        // la plantilla por el aviso H021 de djlint) ------------------
        qa('[data-tp-bg]').forEach(function (el) {
            el.style.backgroundColor = el.dataset.tpBg;
        });

        // --- Casillas de tipos/EPIs/clases --------------------------
        function itemBoxes(kind) {
            return qa('input[data-tp-item="' + kind + '"]');
        }
        function checkedIds(kind) {
            return itemBoxes(kind).filter(function (el) {
                return el.checked;
            }).map(function (el) {
                return el.value;
            });
        }
        function setChecked(kind, ids) {
            var wanted = {};
            ids.forEach(function (id) { wanted[id] = true; });
            itemBoxes(kind).forEach(function (el) {
                el.checked = !!wanted[el.value];
            });
        }
        var itemKinds = (cfg.tpItemKinds || 'type').split(',');

        function currentState() {
            var state = {name: nameInput.value.trim()};
            itemKinds.forEach(function (kind) {
                state[kind] = checkedIds(kind).sort();
            });
            return JSON.stringify(state);
        }
        function takeSnapshot() {
            snapshot = currentState();
        }
        function isDirty() {
            return snapshot !== null && snapshot !== currentState();
        }

        // --- Filtro de categoría (S153, solo Requisitos) -----------
        // Miguel Ángel: "un botón [...] para mostrar la categoría 1,
        // mostrar la categoría 2 o mostrar ambas [...] por defecto
        // tengamos solamente los de categoría 1 en pantalla". Un
        // documento marcado se ve siempre, sea de la categoría que sea:
        // nunca queda marcado algo que no se ve. Las secciones sin
        // nada visible se ocultan.
        var categoryView = cfg.tpCategoryView || '';
        // S153: además, Personal / Centros de gasto / Todos (Miguel
        // Ángel: "que quedasen separados los de personal y los de los
        // centros de gasto"). Los comunes se ven siempre.
        var groupView = cfg.tpGroupView || '';

        function groupVisible(group) {
            return !groupView || groupView === 'all' || !group
                || group === 'common' || group === groupView;
        }
        function applyCategoryView() {
            if (!categoryView && !groupView) {
                return;
            }
            qa('[data-tp-cat]').forEach(function (label) {
                var box = label.querySelector('input[data-tp-item]');
                var visible = !categoryView || categoryView === 'all'
                    || label.dataset.tpCat === categoryView
                    || (box && box.checked);
                label.classList.toggle('d-none', !visible);
            });
            qa('[data-tp-section]').forEach(function (section) {
                var items = section.querySelectorAll('.tp-item');
                var shown = section.querySelectorAll('.tp-item:not(.d-none)');
                var checked = section.querySelector('input[data-tp-item]:checked');
                var hidden = (items.length > 0 && shown.length === 0)
                    || (!groupVisible(section.dataset.tpGroup) && !checked);
                section.classList.toggle('d-none', hidden);
            });
            qa('[data-tp-group-title]').forEach(function (title) {
                var group = title.dataset.tpGroup;
                var anyShown = qa(
                    '[data-tp-section][data-tp-group="' + group + '"]'
                ).some(function (section) {
                    return !section.classList.contains('d-none');
                });
                title.classList.toggle('d-none', !anyShown);
            });
            qa('[data-tp-cat-view]').forEach(function (btn) {
                var active = btn.dataset.tpCatView === categoryView;
                btn.classList.toggle('active', active);
                btn.setAttribute('aria-pressed', active ? 'true' : 'false');
            });
            qa('[data-tp-group-view]').forEach(function (btn) {
                var active = btn.dataset.tpGroupView === groupView;
                btn.classList.toggle('active', active);
                btn.setAttribute('aria-pressed', active ? 'true' : 'false');
            });
        }
        function setGroupView(value) {
            groupView = value;
            applyCategoryView();
            if (cfg.tpNavKey && window.EbNavState) {
                window.EbNavState.save(cfg.tpNavKey, {group_view: value});
            }
        }
        function setCategoryView(value) {
            categoryView = value;
            applyCategoryView();
            if (cfg.tpNavKey && window.EbNavState) {
                window.EbNavState.save(cfg.tpNavKey, {category_view: value});
            }
        }

        // --- Cambiar la categoría de un documento (S153) -----------
        // Miguel Ángel: "poder añadir o pasar de categoría 1 a categoría
        // 2 ciertos documentos [...] la persona que se va a dedicar a
        // llevar este tema [...] le interesará tener más limpio aún el
        // CRUD". Con "Cambiar categorías" pulsado, cada documento lleva
        // un botón que lo pasa a la otra categoría (se guarda al
        // momento); sin pulsar, no se ve nada.
        var categoryEditing = false;

        function paintCategorySwitch(label) {
            var button = label.querySelector('[data-tp-cat-switch]');
            if (!categoryEditing) {
                if (button) {
                    button.remove();
                }
                return;
            }
            if (!button) {
                button = document.createElement('button');
                button.type = 'button';
                button.className = 'btn btn-link btn-sm p-0 ms-1 align-baseline';
                button.setAttribute('data-tp-cat-switch', '');
                label.appendChild(button);
            }
            var target = label.dataset.tpCat === '1' ? '2' : '1';
            button.dataset.target = target;
            button.textContent = '→ Cat. ' + target;
            button.title = 'Pasar a la categoría ' + target;
        }
        function setCategoryEditing(on) {
            categoryEditing = on;
            qa('[data-tp-cat]').forEach(paintCategorySwitch);
            qa('[data-tp-cat-edit]').forEach(function (btn) {
                btn.classList.toggle('active', on);
                btn.setAttribute('aria-pressed', on ? 'true' : 'false');
            });
        }
        function switchCategory(button) {
            var label = button.closest('[data-tp-cat]');
            var box = label.querySelector('input[data-tp-item]');
            var formData = new FormData();
            formData.append('type_id', box.value);
            formData.append('category', button.dataset.target);
            button.disabled = true;
            postForm(cfg.tpCategoryUrl, formData).then(function (data) {
                button.disabled = false;
                if (!data.ok) {
                    showError(data.error || 'No se pudo cambiar la categoría.');
                    return;
                }
                label.dataset.tpCat = String(data.category);
                paintCategorySwitch(label);
                applyCategoryView();
                toast('«' + data.label + '» pasa a la categoría ' + data.category + '.');
            }).catch(function () {
                button.disabled = false;
                showError('Error de red al cambiar la categoría.');
            });
        }

        // --- Visor: lo marcado ahora mismo, siempre a la vista -------
        function refreshPreview() {
            var lines = [];
            itemKinds.forEach(function (kind) {
                itemBoxes(kind).forEach(function (el) {
                    if (el.checked) {
                        lines.push(el.dataset.tpLabel);
                    }
                });
            });
            previewList.innerHTML = '';
            if (!lines.length) {
                var empty = document.createElement('li');
                empty.className = 'text-muted';
                empty.textContent = 'Ningún documento marcado todavía.';
                previewList.appendChild(empty);
            }
            lines.forEach(function (label) {
                var li = document.createElement('li');
                li.textContent = label;
                previewList.appendChild(li);
            });
            q('preview-count').textContent = lines.length;
            var name = nameInput.value.trim();
            titleEl.textContent = name || nounNew;
        }

        // --- Fila seleccionada -> marcas + visor --------------------
        function rowOf(pk) {
            return tbody.querySelector('tr[data-pk="' + pk + '"]');
        }
        function highlight(pk) {
            qa('tr[data-pk]').forEach(function (tr) {
                tr.classList.toggle('table-primary', tr.dataset.pk === String(pk));
            });
        }
        function saveNavigation(pk) {
            if (cfg.tpNavKey && window.EbNavState) {
                window.EbNavState.save(cfg.tpNavKey, {
                    loaded_pk: pk ? Number(pk) : null,
                });
            }
        }
        function confirmDiscard() {
            if (!isDirty()) {
                return true;
            }
            var current = nameInput.value.trim() || nounNew;
            return window.confirm(
                'Hay cambios sin guardar en "' + current + '". '
                + '¿Descartarlos?'
            );
        }
        function loadRow(pk) {
            var tr = rowOf(pk);
            if (!tr) {
                return;
            }
            loadedPk = String(pk);
            loadedName = tr.dataset.name || '';
            nameInput.value = loadedName;
            itemKinds.forEach(function (kind) {
                setChecked(kind, splitIds(tr.dataset['ids' + kind]));
            });
            highlight(pk);
            resultEl.textContent = '';
            refreshPreview();
            applyCategoryView();
            takeSnapshot();
        }
        function resetForm() {
            loadedPk = '';
            loadedName = null;
            nameInput.value = '';
            itemKinds.forEach(function (kind) {
                setChecked(kind, []);
            });
            highlight('');
            resultEl.textContent = '';
            refreshPreview();
            applyCategoryView();
            takeSnapshot();
        }

        // --- Selección múltiple de filas ----------------------------
        function rowBoxes() {
            return qa('input[data-tp="row-check"]');
        }
        function selectedPks() {
            return rowBoxes().filter(function (el) {
                return el.checked;
            }).map(function (el) {
                return el.value;
            });
        }
        function refreshSelection() {
            var boxes = rowBoxes();
            var picked = selectedPks();
            selectionCount.textContent = picked.length;
            selectAll.checked = boxes.length > 0 && picked.length === boxes.length;
            selectAll.indeterminate = picked.length > 0 && picked.length < boxes.length;
            qa('[data-tp-needs-selection]').forEach(function (btn) {
                btn.disabled = picked.length === 0;
            });
        }

        // --- Filas: crear/actualizar sin recargar -------------------
        function rowSummary(tr) {
            var labels = [];
            itemKinds.forEach(function (kind) {
                splitIds(tr.dataset['ids' + kind]).forEach(function (id) {
                    var box = root.querySelector(
                        'input[data-tp-item="' + kind + '"][value="' + id + '"]'
                    );
                    if (box) {
                        labels.push(box.dataset.tpLabel);
                    }
                });
            });
            return labels;
        }
        function paintRow(tr) {
            var labels = rowSummary(tr);
            tr.querySelector('[data-tp="row-name"]').textContent = tr.dataset.name;
            tr.querySelector('[data-tp="row-count"]').textContent = labels.length;
            var summary = tr.querySelector('[data-tp="row-summary"]');
            summary.textContent = labels.join(', ') || 'Sin documentos';
            summary.title = labels.join('\n');
            var badge = tr.querySelector('[data-tp="row-state"]');
            if (badge) {
                var active = tr.dataset.active === '1';
                badge.textContent = active ? 'Activo' : 'Desactivado';
                badge.className = 'badge ' + (active ? 'bg-success' : 'bg-secondary');
                tr.classList.toggle('text-muted', !active);
            }
        }
        function upsertRow(pk, name, idsByKind) {
            var tr = rowOf(pk);
            if (!tr) {
                var template = q('row-template');
                tr = template.content.firstElementChild.cloneNode(true);
                tr.dataset.pk = pk;
                tr.dataset.active = '1';
                tr.querySelector('input[data-tp="row-check"]').value = pk;
                var empty = q('empty-row');
                if (empty) {
                    empty.remove();
                }
                tbody.appendChild(tr);
            }
            tr.dataset.name = name;
            itemKinds.forEach(function (kind) {
                tr.dataset['ids' + kind] = idsByKind[kind].join(',');
            });
            paintRow(tr);
            return tr;
        }
        function removeRows(pks) {
            pks.forEach(function (pk) {
                var tr = rowOf(pk);
                if (tr) {
                    tr.remove();
                }
            });
            if (pks.indexOf(loadedPk) !== -1) {
                resetForm();
                saveNavigation(null);
            }
            if (!tbody.querySelector('tr[data-pk]')) {
                var template = q('empty-template');
                tbody.appendChild(template.content.firstElementChild.cloneNode(true));
            }
            refreshSelection();
        }

        // S128: cualquier cambio (guardar, borrar, activar/desactivar)
        // avisa al resto del hub para que refresque los listados que
        // dependen de estos datos (insignias de Personal y Centros de
        // gasto, Avisos) sin recargar la página.
        function notifyChanged() {
            if (cfg.tpChangedEvent) {
                document.dispatchEvent(new CustomEvent(cfg.tpChangedEvent));
            }
        }

        function toast(message) {
            var el = document.getElementById('personGroupToast');
            var body = document.getElementById('personGroupToastBody');
            if (el && body && window.bootstrap) {
                body.textContent = message;
                window.bootstrap.Toast.getOrCreateInstance(el).show();
            }
        }
        function showError(message) {
            resultEl.textContent = message;
        }

        // --- Guardar -------------------------------------------------
        // Miguel Ángel (S119/S128): con el mismo nombre con el que se
        // cargó, se edita; con otro nombre, se crea uno NUEVO y el
        // original queda intacto.
        function save() {
            var name = nameInput.value.trim();
            if (requireName && !name) {
                showError('Falta el nombre.');
                return;
            }
            var idsByKind = {};
            var total = 0;
            itemKinds.forEach(function (kind) {
                idsByKind[kind] = checkedIds(kind);
                total += idsByKind[kind].length;
            });
            if (requireItems && total === 0) {
                showError('Marca al menos un documento.');
                return;
            }
            var editing = loadedPk && loadedName !== null && name === loadedName;
            var url = editing
                ? cfg.tpUpdateUrl.replace('{pk}', loadedPk)
                : cfg.tpCreateUrl;
            var formData = new FormData();
            formData.append('name', name);
            if (cfg.tpScope) {
                formData.append('scope', cfg.tpScope);
            }
            itemKinds.forEach(function (kind) {
                var field = root.dataset[
                    'tpField' + kind.charAt(0).toUpperCase() + kind.slice(1)
                ];
                idsByKind[kind].forEach(function (id) {
                    formData.append(field, id);
                });
            });
            postForm(url, formData).then(function (data) {
                if (!data.ok) {
                    showError(data.error || 'Error al guardar.');
                    return;
                }
                upsertRow(String(data.id), data.name, idsByKind);
                loadRow(String(data.id));
                saveNavigation(data.id);
                toast(editing ? 'Guardado.' : 'Creado: ' + data.name);
                if (cfg.tpSavedEvent) {
                    document.dispatchEvent(new CustomEvent(cfg.tpSavedEvent, {
                        detail: {id: data.id, name: data.name},
                    }));
                }
                notifyChanged();
            }).catch(function () {
                showError('Error de red al guardar.');
            });
        }

        // --- Activar / desactivar (solo requisitos) -----------------
        function setActive(active) {
            var pks = selectedPks();
            if (!pks.length) {
                return;
            }
            var formData = new FormData();
            pks.forEach(function (pk) { formData.append('ids', pk); });
            formData.append('active', active ? '1' : '0');
            postForm(cfg.tpActiveUrl, formData).then(function (data) {
                if (!data.ok) {
                    showError(data.error || 'No se pudo cambiar el estado.');
                    return;
                }
                pks.forEach(function (pk) {
                    var tr = rowOf(pk);
                    if (tr) {
                        tr.dataset.active = active ? '1' : '0';
                        paintRow(tr);
                    }
                });
                toast((active ? 'Activados: ' : 'Desactivados: ') + data.count);
                notifyChanged();
            }).catch(function () {
                showError('Error de red.');
            });
        }

        // --- Eliminar con cuenta atrás de 5 s -----------------------
        var modalEl = q('delete-modal');
        var modalList = q('delete-list');
        var modalBtn = q('delete-confirm');
        var modalLabel = q('delete-countdown');
        var countdownTimer = null;

        function openDelete() {
            var pks = selectedPks();
            if (!pks.length) {
                return;
            }
            modalList.innerHTML = '';
            pks.forEach(function (pk) {
                var li = document.createElement('li');
                li.textContent = rowOf(pk).dataset.name;
                modalList.appendChild(li);
            });
            var seconds = COUNTDOWN_SECONDS;
            modalBtn.disabled = true;
            modalLabel.textContent = '(' + seconds + ')';
            clearInterval(countdownTimer);
            countdownTimer = setInterval(function () {
                seconds -= 1;
                if (seconds <= 0) {
                    clearInterval(countdownTimer);
                    modalBtn.disabled = false;
                    modalLabel.textContent = '';
                } else {
                    modalLabel.textContent = '(' + seconds + ')';
                }
            }, 1000);
            modalBtn.dataset.pks = pks.join(',');
            window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
        modalEl.addEventListener('hidden.bs.modal', function () {
            clearInterval(countdownTimer);
            modalBtn.disabled = true;
            modalLabel.textContent = '';
        });
        modalBtn.addEventListener('click', function () {
            var pks = splitIds(modalBtn.dataset.pks);
            var formData = new FormData();
            pks.forEach(function (pk) { formData.append('ids', pk); });
            modalBtn.disabled = true;
            postForm(cfg.tpDeleteUrl, formData).then(function (data) {
                window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                if (!data.ok) {
                    showError(data.error || 'No se pudo eliminar.');
                    return;
                }
                removeRows(pks);
                toast('Eliminados: ' + data.count);
                if (cfg.tpDeletedEvent) {
                    pks.forEach(function (pk) {
                        document.dispatchEvent(new CustomEvent(cfg.tpDeletedEvent, {
                            detail: {id: Number(pk)},
                        }));
                    });
                }
                notifyChanged();
            }).catch(function () {
                window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                showError('Error de red al eliminar.');
            });
        });

        // --- Eventos (delegados en la raíz) -------------------------
        root.addEventListener('change', function (event) {
            var target = event.target;
            if (target.matches('input[data-tp-item]')) {
                refreshPreview();
            } else if (target === selectAll) {
                rowBoxes().forEach(function (el) {
                    el.checked = selectAll.checked;
                });
                refreshSelection();
            } else if (target.matches('input[data-tp="row-check"]')) {
                refreshSelection();
            }
        });
        root.addEventListener('input', function (event) {
            if (event.target === nameInput) {
                refreshPreview();
            }
        });
        root.addEventListener('click', function (event) {
            var catSwitch = event.target.closest('[data-tp-cat-switch]');
            if (catSwitch && root.contains(catSwitch)) {
                // Dentro de la etiqueta de la casilla: que no la marque.
                event.preventDefault();
                switchCategory(catSwitch);
                return;
            }
            var catEdit = event.target.closest('[data-tp-cat-edit]');
            if (catEdit && root.contains(catEdit)) {
                setCategoryEditing(!categoryEditing);
                return;
            }
            var groupButton = event.target.closest('button[data-tp-group-view]');
            if (groupButton && root.contains(groupButton)) {
                setGroupView(groupButton.dataset.tpGroupView);
                return;
            }
            var catButton = event.target.closest('[data-tp-cat-view]');
            if (catButton && root.contains(catButton)) {
                setCategoryView(catButton.dataset.tpCatView);
                return;
            }
            var action = event.target.closest('[data-tp-action]');
            if (action && root.contains(action)) {
                var what = action.dataset.tpAction;
                if (what === 'save') {
                    save();
                } else if (what === 'new') {
                    if (confirmDiscard()) {
                        resetForm();
                        saveNavigation(null);
                    }
                } else if (what === 'activate') {
                    setActive(true);
                } else if (what === 'deactivate') {
                    setActive(false);
                } else if (what === 'delete') {
                    openDelete();
                }
                return;
            }
            // Clic en la fila (no en su casilla): cargar.
            var tr = event.target.closest('tr[data-pk]');
            if (tr && !event.target.matches('input[data-tp="row-check"]')) {
                if (tr.dataset.pk === loadedPk) {
                    return;
                }
                if (confirmDiscard()) {
                    loadRow(tr.dataset.pk);
                    saveNavigation(tr.dataset.pk);
                }
            }
        });
        window.addEventListener('beforeunload', function (event) {
            if (document.body.contains(root) && isDirty()) {
                event.preventDefault();
                event.returnValue = '';
            }
        });

        // --- Altura: pantalla fija, scroll solo en las listas (4.24) -
        function fitHeight() {
            if (!document.body.contains(root)) {
                return;
            }
            if (window.innerWidth < LG_BREAKPOINT || !root.offsetParent) {
                root.style.height = '';
                return;
            }
            // Altura natural menos el exceso real sobre la ventana (mismo
            // algoritmo que #personal-bottom-panel, S114): lo que haya
            // debajo de la raíz (márgenes del panel, pie) también cuenta.
            var top = root.getBoundingClientRect().top + window.scrollY;
            var height = window.innerHeight - top;
            root.style.height = Math.max(height, 360) + 'px';
            var excess = document.documentElement.scrollHeight - window.innerHeight;
            if (excess > 0) {
                root.style.height = Math.max(height - excess, 360) + 'px';
            }
        }
        window.addEventListener('resize', fitHeight);
        if (window.ResizeObserver) {
            // Se dispara también cuando la pestaña pasa de oculta a
            // visible (el tamaño de la raíz cambia de 0 a real).
            new ResizeObserver(fitHeight).observe(root.parentElement);
        }

        // --- Arranque ------------------------------------------------
        qa('tr[data-pk]').forEach(paintRow);
        refreshSelection();
        if (cfg.tpInitialPk && rowOf(cfg.tpInitialPk)) {
            loadRow(cfg.tpInitialPk);
        } else {
            resetForm();
        }
        fitHeight();
    }

    window.EbTypePicker = {init: init};
})();
