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
(function () {
    "use strict";

    let modalInstance = null;

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

        rows.forEach(function (row) {
            row.querySelector(".ddp-check").checked =
                selection.has(parseInt(row.dataset.pk, 10));
        });

        function visibleRows() {
            return rows.filter(function (row) {
                return !row.classList.contains("d-none");
            });
        }

        function refreshCounts() {
            root.querySelector(".ddp-count").textContent = selection.size;
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
                },
            }).catch(function () {});
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

        // Pantalla completa con el formato del laboratorio de análisis
        // (directriz 4.26): el contenedor estable de la ventana.
        const content = root.closest(".ddp-content");
        root.querySelector(".ddp-fullscreen").addEventListener("click", function () {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (content && content.requestFullscreen) {
                content.requestFullscreen();
            }
        });

        applyFilters();
    }
})();
