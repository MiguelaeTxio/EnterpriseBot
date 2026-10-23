// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/document_download_picker.js
//
// H31 (S136, sesión invasora). Ventana "Descargar documentación" de la
// ficha de una persona o de una máquina. Miguel Ángel: "un modal con
// la documentación separada por familia, con marcajes de obsoletos,
// para que filtro, etcétera [...] si se necesitan documentos, sea
// fácil extraerlos de la ficha".
//
// - openDocumentDownloadPicker(url): crea la ventana la primera vez,
//   la abre y carga el fragmento (DocumentDownloadPickerView).
// - Las casillas son la "Selección de documentos" de la ficha: se
//   guardan en PanelNavigationState (clave document_selection) y se
//   reflejan en las casillas y el contador de la propia ficha
//   (selectedDocumentIds, documentSelectionBadge).
// - Descargar ZIP / PDF único guarda primero la selección y después
//   abre la descarga de siempre de la selección.
// - Los filtros (estados y familia) se guardan por usuario
//   (directriz 4.15).
// - S136: "Enviar a la papelera" (la selección, o una fila desde su
//   menú de tres puntos) pide un segundo clic para confirmar; al cerrar
//   la ventana tras borrar algo, la ficha se recarga para que
//   desaparezca también de ella.
// - Formato único de listado (directriz 4.24): orden múltiple pulsando
//   las cabeceras (dentro de cada familia; máximo 4, superíndice con la
//   prioridad, "Quitar orden"), visor "Selección actual" y pantalla
//   completa de la lista (4.26). El orden se guarda con los filtros.
(function () {
    "use strict";

    let modalInstance = null;
    let trashedSomething = false;

    function csrf() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function saveState(screenKey, update) {
        return fetch("/panel/navegacion/estado/" + screenKey + "/", {
            method: "POST",
            headers: {
                "X-CSRFToken": csrf(),
                "Content-Type": "application/json",
            },
            body: JSON.stringify(update),
        }).then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response;
        });
    }

    // La selección de la ficha (variable global de su plantilla); si no
    // existe, una propia.
    function fichaSelection() {
        if (typeof selectedDocumentIds !== "undefined") {
            return selectedDocumentIds; // eslint-disable-line no-undef
        }
        window.ddpSelection = window.ddpSelection || new Set();
        return window.ddpSelection;
    }

    function shell() {
        let element = document.getElementById("documentDownloadPickerModal");
        if (element) {
            return element;
        }
        element = document.createElement("div");
        element.className = "modal fade";
        element.id = "documentDownloadPickerModal";
        element.tabIndex = -1;
        element.setAttribute("aria-labelledby", "documentDownloadPickerTitle");
        element.innerHTML =
            '<div class="modal-dialog modal-xl modal-dialog-centered">' +
            '<div class="modal-content ddp-content">' +
            '<div class="modal-header py-2">' +
            '<h5 class="modal-title" id="documentDownloadPickerTitle">' +
            '<i class="bi bi-download me-2"></i>Descargar documentación</h5>' +
            '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>' +
            "</div>" +
            '<div class="modal-body ddp-body"></div>' +
            "</div></div>";
        document.body.appendChild(element);
        element.addEventListener("hidden.bs.modal", function () {
            if (trashedSomething) {
                window.location.reload();
            }
        });
        return element;
    }

    window.openDocumentDownloadPicker = function (url, title) {
        const element = shell();
        const body = element.querySelector(".ddp-body");
        element.querySelector(".modal-title").innerHTML =
            '<i class="bi bi-download me-2"></i>Descargar documentación' +
            (title ? " — " : "");
        if (title) {
            element.querySelector(".modal-title").appendChild(
                document.createTextNode(title),
            );
        }
        body.innerHTML = '<div class="text-muted small py-3">Cargando…</div>';
        if (!modalInstance) {
            modalInstance = new bootstrap.Modal(element);
        }
        modalInstance.show();
        fetch(url).then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.text();
        }).then(function (html) {
            body.innerHTML = html;
            init(body.querySelector(".ddp-root"));
        }).catch(function () {
            body.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-0">' +
                "No se ha podido cargar la documentación.</div>";
        });
    };

    function init(root) {
        if (!root) {
            return;
        }
        const screenKey = root.dataset.screenKey;
        const subjectPk = root.dataset.subjectPk;
        const selection = fichaSelection();
        const rows = Array.from(root.querySelectorAll(".ddp-row"));
        const groups = Array.from(root.querySelectorAll(".ddp-family-group"));
        const search = root.querySelector(".ddp-search");
        const family = root.querySelector(".ddp-family");
        const states = Array.from(root.querySelectorAll(".ddp-state"));
        const onlySelected = root.querySelector(".ddp-only-selected");
        const checkAll = root.querySelector(".ddp-check-all");
        const message = root.querySelector(".ddp-message");
        const empty = root.querySelector(".ddp-empty");
        const clearSort = root.querySelector(".ddp-clear-sort");
        const sortLinks = Array.from(root.querySelectorAll(".ddp-sort"));
        const STATE_ORDER = {vigente: 0, caducado: 1, obsoleto: 2};
        const MAX_SORT = 4;
        let sortKeys = (root.dataset.sort || "").split(",").map(function (token) {
            token = token.trim();
            return {key: token.replace(/^-/, ""), desc: token.charAt(0) === "-"};
        }).filter(function (item) {
            return ["type", "issue", "expiry", "state"].indexOf(item.key) !== -1;
        }).slice(0, MAX_SORT);

        function sortValue(row, key) {
            if (key === "state") {
                return String(STATE_ORDER[row.dataset.state]);
            }
            return row.dataset[key] || "";
        }

        // Orden dentro de cada familia; sin orden, el del servidor. Los
        // vacíos (sin fecha) siempre al final.
        function applySort() {
            groups.forEach(function (group) {
                const groupRows = Array.from(group.querySelectorAll(".ddp-row"));
                groupRows.sort(function (a, b) {
                    for (let i = 0; i < sortKeys.length; i += 1) {
                        const key = sortKeys[i].key;
                        const va = sortValue(a, key);
                        const vb = sortValue(b, key);
                        if (va === vb) {
                            continue;
                        }
                        if (!va) {
                            return 1;
                        }
                        if (!vb) {
                            return -1;
                        }
                        const cmp = va < vb ? -1 : 1;
                        return sortKeys[i].desc ? -cmp : cmp;
                    }
                    return parseInt(a.dataset.index, 10) - parseInt(b.dataset.index, 10);
                });
                groupRows.forEach(function (row) {
                    group.appendChild(row);
                });
            });
            sortLinks.forEach(function (link) {
                const index = sortKeys.findIndex(function (item) {
                    return item.key === link.dataset.key;
                });
                const old = link.querySelector(".ddp-sort-mark");
                if (old) {
                    old.remove();
                }
                if (index === -1) {
                    return;
                }
                const mark = document.createElement("span");
                mark.className = "ddp-sort-mark";
                mark.innerHTML = ' <i class="bi bi-chevron-' +
                    (sortKeys[index].desc ? "down" : "up") + '"></i>' +
                    (sortKeys.length > 1 ? "<sup>" + (index + 1) + "</sup>" : "");
                link.appendChild(mark);
            });
            if (clearSort) {
                clearSort.classList.toggle("d-none", sortKeys.length === 0);
            }
        }

        function sortString() {
            return sortKeys.map(function (item) {
                return (item.desc ? "-" : "") + item.key;
            }).join(",");
        }

        rows.forEach(function (row) {
            row.querySelector(".ddp-check").checked =
                selection.has(parseInt(row.dataset.pk, 10));
        });

        function visibleRows() {
            return rows.filter(function (row) {
                return !row.classList.contains("d-none");
            });
        }

        // Visor "Selección actual": lo marcado aunque el filtro lo oculte.
        function refreshSelectionViewer() {
            const list = root.querySelector(".ddp-selection-list");
            const labels = rows.filter(function (row) {
                return selection.has(parseInt(row.dataset.pk, 10));
            }).map(function (row) {
                return row.dataset.label;
            }).sort(function (a, b) {
                return a.localeCompare(b);
            });
            root.querySelector(".ddp-selection-count").textContent = labels.length;
            list.innerHTML = "";
            if (!labels.length) {
                const li = document.createElement("li");
                li.className = "text-muted";
                li.textContent = "Nada seleccionado todavía.";
                list.appendChild(li);
                return;
            }
            labels.forEach(function (label) {
                const li = document.createElement("li");
                li.textContent = label;
                list.appendChild(li);
            });
        }

        function refreshCounts() {
            root.querySelector(".ddp-count").textContent = selection.size;
            refreshSelectionViewer();
            const visible = visibleRows();
            root.querySelector(".ddp-visible").textContent = visible.length;
            if (checkAll) {
                const checked = visible.filter(function (row) {
                    return row.querySelector(".ddp-check").checked;
                }).length;
                checkAll.checked = visible.length > 0 && checked === visible.length;
                checkAll.indeterminate = checked > 0 && checked < visible.length;
            }
        }

        function applyFilters() {
            const text = (search.value || "").trim().toLowerCase();
            const familyCode = family ? family.value : "";
            const wanted = states.filter(function (box) {
                return box.checked;
            }).map(function (box) {
                return box.value;
            });
            let anyVisible = false;
            groups.forEach(function (group) {
                let groupVisible = 0;
                const groupMatches = !familyCode || group.dataset.family === familyCode;
                group.querySelectorAll(".ddp-row").forEach(function (row) {
                    const show = groupMatches &&
                        wanted.indexOf(row.dataset.state) !== -1 &&
                        (!text || row.dataset.text.indexOf(text) !== -1) &&
                        (!onlySelected.checked ||
                            row.querySelector(".ddp-check").checked);
                    row.classList.toggle("d-none", !show);
                    if (show) {
                        groupVisible += 1;
                    }
                });
                group.classList.toggle("d-none", groupVisible === 0);
                group.querySelector(".ddp-family-count").textContent =
                    "(" + groupVisible + ")";
                anyVisible = anyVisible || groupVisible > 0;
            });
            if (empty) {
                empty.classList.toggle("d-none", anyVisible);
            }
            refreshCounts();
        }

        // Refleja la selección en la ficha (casillas y contador).
        function syncFicha() {
            document.querySelectorAll("input[data-doc-pk]").forEach(function (box) {
                box.checked = selection.has(parseInt(box.dataset.docPk, 10));
            });
            const badge = document.getElementById("documentSelectionBadge");
            if (badge) {
                badge.textContent = selection.size;
            }
        }

        function persistSelection() {
            const update = {document_selection: {}};
            update.document_selection[subjectPk] = Array.from(selection);
            syncFicha();
            refreshCounts();
            return saveState(screenKey, update);
        }

        function persistFilters() {
            saveState(screenKey, {
                download_picker: {
                    states: states.filter(function (box) {
                        return box.checked;
                    }).map(function (box) {
                        return box.value;
                    }),
                    family: family ? family.value : "",
                    sort: sortString(),
                },
            }).catch(function () {});
        }

        // Cabecera: la pulsada pasa a ser el criterio principal y las
        // demás quedan de desempate; pulsar la principal le da la vuelta
        // (mismas reglas que Centros de gasto, 4.24 regla 2).
        sortLinks.forEach(function (link) {
            link.addEventListener("click", function (ev) {
                ev.preventDefault();
                const key = link.dataset.key;
                const index = sortKeys.findIndex(function (item) {
                    return item.key === key;
                });
                if (index === 0) {
                    sortKeys[0].desc = !sortKeys[0].desc;
                } else if (index > 0) {
                    const item = sortKeys.splice(index, 1)[0];
                    sortKeys.unshift(item);
                } else {
                    sortKeys.unshift({key: key, desc: false});
                }
                sortKeys = sortKeys.slice(0, MAX_SORT);
                applySort();
                persistFilters();
            });
        });
        if (clearSort) {
            clearSort.addEventListener("click", function () {
                sortKeys = [];
                applySort();
                persistFilters();
            });
        }

        function setRows(list, checked) {
            list.forEach(function (row) {
                const pk = parseInt(row.dataset.pk, 10);
                row.querySelector(".ddp-check").checked = checked;
                if (checked) {
                    selection.add(pk);
                } else {
                    selection.delete(pk);
                }
            });
            persistSelection().catch(function () {});
            if (onlySelected.checked) {
                applyFilters();
            }
        }

        rows.forEach(function (row) {
            row.querySelector(".ddp-check").addEventListener("change", function () {
                setRows([row], this.checked);
            });
        });
        if (checkAll) {
            checkAll.addEventListener("change", function () {
                setRows(visibleRows(), checkAll.checked);
            });
        }
        root.querySelector(".ddp-check-visible").addEventListener("click", function () {
            setRows(visibleRows(), true);
        });
        root.querySelector(".ddp-uncheck-visible").addEventListener("click", function () {
            setRows(visibleRows(), false);
        });
        root.querySelector(".ddp-clear").addEventListener("click", function () {
            selection.clear();
            rows.forEach(function (row) {
                row.querySelector(".ddp-check").checked = false;
            });
            persistSelection().catch(function () {});
            applyFilters();
        });

        search.addEventListener("input", applyFilters);
        onlySelected.addEventListener("change", applyFilters);
        if (family) {
            family.addEventListener("change", function () {
                applyFilters();
                persistFilters();
            });
        }
        states.forEach(function (box) {
            box.addEventListener("change", function () {
                applyFilters();
                persistFilters();
            });
        });

        root.querySelectorAll(".ddp-download").forEach(function (button) {
            button.addEventListener("click", function () {
                if (selection.size === 0) {
                    message.className = "small mt-1 ddp-message text-danger";
                    message.textContent = "Marca primero algún documento.";
                    return;
                }
                message.className = "small mt-1 ddp-message text-muted";
                message.textContent = "Preparando la descarga…";
                persistSelection().then(function () {
                    message.textContent = "";
                    window.location.href = button.dataset.url;
                }).catch(function () {
                    message.className = "small mt-1 ddp-message text-danger";
                    message.textContent = "No se ha podido guardar la selección. Inténtalo otra vez.";
                });
            });
        });

        // S136: papelera. Primer clic: pide confirmación; segundo clic
        // (en 5 s): manda los documentos a la papelera.
        const trashUrl = root.dataset.trashUrl;

        function askThenTrash(button, pks, label) {
            if (button.dataset.armed !== "1") {
                button.dataset.armed = "1";
                button.dataset.label = button.innerHTML;
                button.innerHTML = label;
                button.classList.add("btn-danger", "text-white");
                setTimeout(function () {
                    if (button.dataset.armed === "1") {
                        button.dataset.armed = "";
                        button.innerHTML = button.dataset.label;
                        button.classList.remove("btn-danger", "text-white");
                    }
                }, 5000);
                return;
            }
            button.dataset.armed = "";
            button.disabled = true;
            const formData = new FormData();
            pks.forEach(function (pk) {
                formData.append("entry_ids", pk);
            });
            fetch(trashUrl, {
                method: "POST",
                headers: {"X-CSRFToken": csrf()},
                body: formData,
            }).then(function (response) {
                return response.json();
            }).then(function (data) {
                button.disabled = false;
                button.innerHTML = button.dataset.label;
                button.classList.remove("btn-danger", "text-white");
                if (!data.ok) {
                    message.className = "small mt-1 ddp-message text-danger";
                    message.textContent = data.error || "No se ha podido.";
                    return;
                }
                trashedSomething = true;
                (data.trashed_ids || []).forEach(function (pk) {
                    selection.delete(pk);
                    const row = root.querySelector('.ddp-row[data-pk="' + pk + '"]');
                    if (row) {
                        rows.splice(rows.indexOf(row), 1);
                        row.remove();
                    }
                });
                persistSelection().catch(function () {});
                applyFilters();
                message.className = "small mt-1 ddp-message text-success";
                message.textContent = data.trashed_ids.length +
                    " documento(s) enviados a la papelera.";
            }).catch(function () {
                button.disabled = false;
                button.innerHTML = button.dataset.label;
                button.classList.remove("btn-danger", "text-white");
                message.className = "small mt-1 ddp-message text-danger";
                message.textContent = "Error de red. Inténtalo otra vez.";
            });
        }

        const trashButton = root.querySelector(".ddp-trash");
        if (trashButton && trashUrl) {
            trashButton.addEventListener("click", function () {
                const pks = rows.filter(function (row) {
                    return row.querySelector(".ddp-check").checked;
                }).map(function (row) {
                    return parseInt(row.dataset.pk, 10);
                });
                if (!pks.length) {
                    message.className = "small mt-1 ddp-message text-danger";
                    message.textContent = "Marca primero algún documento.";
                    return;
                }
                askThenTrash(trashButton, pks,
                    "¿Seguro? Pulsa otra vez: " + pks.length + " a la papelera");
            });
        }
        if (trashUrl) {
            rows.forEach(function (row) {
                const button = row.querySelector(".ddp-row-trash");
                if (button) {
                    button.addEventListener("click", function () {
                        askThenTrash(button, [parseInt(row.dataset.pk, 10)],
                            "¿Seguro? Pulsa otra vez");
                    });
                }
            });
        }

        // Pantalla completa de la lista, formato del laboratorio de
        // análisis (directriz 4.26).
        const listBox = root.querySelector(".ddp-list-box");
        root.querySelector(".ddp-fullscreen").addEventListener("click", function () {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (listBox && listBox.requestFullscreen) {
                listBox.requestFullscreen();
            }
        });

        applySort();
        applyFilters();
    }
})();
