// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/machine_workshop_list.js
//
// H30 (S139, invasora). Comportamiento común de los dos listados del
// taller de una máquina (Partes de trabajo y Averías), con el formato de
// la directriz 4.24 y el mismo funcionamiento que Albaranes de Servicios:
// - Selección (clave de fila -> etiqueta, horas e importe) que sobrevive
//   a filtros, orden y repintados, guardada por usuario (EbNavState,
//   directriz 4.15) y con sus totales en el visor "Selección actual".
// - Casillas de estado (Abiertas/Cerradas) traducidas a un único valor
//   ("" ambas, "open", "closed", "none" ninguna), en Averías; en Libros
//   historial (S154), Vigentes/Históricos con "current"/"historic".
// - Casilleros de columnas visibles, guardados por usuario.
// - Excel de la selección (POST), pantalla completa de la lista
//   (formato del laboratorio de análisis, directriz 4.26) y totales de lo
//   listado, que llegan en #mw-fragment-state con cada repintado.
// Configuración en #mw-root: data-screen-key (data-export-url: el modal de exportación, S148).
(function () {
    "use strict";

    function number(value) {
        var parsed = parseFloat(String(value || "0").replace(",", "."));
        return isNaN(parsed) ? 0 : parsed;
    }

    function format(value) {
        return value.toLocaleString("es-ES", {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
    }

    function init() {
        var root = document.getElementById("mw-root");
        if (!root) { return; }
        var container = document.getElementById("mw-table-container");
        var screenKey = root.dataset.screenKey;

        var selection = new Map();
        try {
            JSON.parse(
                document.getElementById("mw-saved-selection").textContent
            ).forEach(function (item) {
                if (item && item.key) {
                    selection.set(String(item.key), {
                        label: item.label || "",
                        hours: number(item.hours),
                        ordinary: number(item.ordinary),
                        extra: number(item.extra),
                        festive: number(item.festive),
                        cost: number(item.cost),
                    });
                }
            });
        } catch (e) { /* estado guardado ilegible: sin selección */ }

        var lastSaved = "";
        function saveSelection() {
            var payload = [];
            selection.forEach(function (item, key) {
                payload.push({
                    key: key, label: item.label, hours: item.hours,
                    ordinary: item.ordinary, extra: item.extra,
                    festive: item.festive, cost: item.cost,
                });
            });
            var serialized = JSON.stringify(payload);
            if (serialized === lastSaved) { return; }
            lastSaved = serialized;
            if (window.EbNavState) {
                window.EbNavState.save(screenKey, {selection: payload});
            }
        }

        function setText(id, text) {
            var el = document.getElementById(id);
            if (el) { el.textContent = text; }
        }

        function refreshFromFragment() {
            var state = document.getElementById("mw-fragment-state");
            if (state) {
                setText("mw-row-count", state.dataset.count);
                setText("mw-row-hours", state.dataset.hours);
                setText("mw-row-cost", state.dataset.cost);
                var unpriced = document.getElementById("mw-row-unpriced");
                if (unpriced) {
                    unpriced.classList.toggle(
                        "d-none", state.dataset.unpriced === "0"
                    );
                    unpriced.querySelector("span").textContent =
                        state.dataset.unpriced;
                }
                var filtered = document.getElementById("mw-row-filtered");
                if (filtered) {
                    filtered.classList.toggle("d-none", !state.dataset.filtered);
                }
                document.getElementById("mw-clear-sort").classList.toggle(
                    "d-none", !state.dataset.sortActive
                );
                document.querySelector("#mw-sort input[name=sort]").value =
                    state.dataset.sort || "";
            }
            container.querySelectorAll(".mw-row-check").forEach(function (cb) {
                cb.checked = selection.has(cb.dataset.key);
            });
            updateSelectionUi();
        }

        function updateSelectionUi() {
            saveSelection();
            setText("mw-mass-count", selection.size);
            setText("mw-selection-count", selection.size);
            var list = document.getElementById("mw-selection-list");
            list.innerHTML = "";
            var hours = 0;
            var ordinary = 0;
            var extra = 0;
            var festive = 0;
            var cost = 0;
            if (!selection.size) {
                var empty = document.createElement("li");
                empty.className = "text-muted";
                empty.textContent = "Nada seleccionado todavía.";
                list.appendChild(empty);
            } else {
                var labels = [];
                selection.forEach(function (item) {
                    labels.push(item.label);
                    hours += item.hours;
                    ordinary += item.ordinary;
                    extra += item.extra;
                    festive += item.festive;
                    cost += item.cost;
                });
                labels.sort().forEach(function (label) {
                    var li = document.createElement("li");
                    li.textContent = label;
                    list.appendChild(li);
                });
            }
            setText(
                "mw-selection-totals",
                selection.size
                    ? format(hours) + " h (ordinarias " + format(ordinary)
                        + " · extra " + format(extra) + " · festivas "
                        + format(festive) + ") · " + format(cost)
                        + " € en repuestos"
                    : ""
            );
            var idsInput = document.getElementById("mw-selected-ids");
            var newIds = Array.from(selection.keys()).join(",");
            if (idsInput.value !== newIds) {
                idsInput.value = newIds;
                var onlySel = document.getElementById("mw-only-selected");
                if (onlySel.checked) {
                    htmx.trigger(onlySel, "mw-selection-refresh");
                }
            }
            document.querySelectorAll(".mw-needs-selection").forEach(
                function (btn) { btn.disabled = selection.size === 0; }
            );
            var all = document.getElementById("mw-check-all");
            if (!all) { return; }
            var rows = container.querySelectorAll(".mw-row-check");
            var checked = container.querySelectorAll(".mw-row-check:checked");
            all.checked = rows.length > 0 && checked.length === rows.length;
            all.indeterminate = (
                checked.length > 0 && checked.length < rows.length
            );
        }

        function select(cb, on) {
            if (on) {
                selection.set(cb.dataset.key, {
                    label: cb.dataset.label,
                    hours: number(cb.dataset.hours),
                    ordinary: number(cb.dataset.ordinary),
                    extra: number(cb.dataset.extra),
                    festive: number(cb.dataset.festive),
                    cost: number(cb.dataset.cost),
                });
            } else {
                selection.delete(cb.dataset.key);
            }
        }

        var stateHidden = document.getElementById("mw-filter-state");
        document.querySelectorAll(".mw-state-check").forEach(function (cb) {
            cb.addEventListener("change", function () {
                var open = document.getElementById("mw-state-open").checked;
                var closed = document.getElementById("mw-state-closed").checked;
                // S154: Libros historial usa sus propios valores
                // (current/historic) en data-open-value/data-closed-value.
                var openValue = stateHidden.dataset.openValue || "open";
                var closedValue = stateHidden.dataset.closedValue || "closed";
                stateHidden.value = open && closed ? "" : (
                    open ? openValue : (closed ? closedValue : "none")
                );
                htmx.trigger(stateHidden, "mw-state-change");
            });
        });

        // S139: pulsar la fila abre el parte (tr.mw-row-link, data-href).
        // La casilla, los enlaces y botones de la fila hacen lo suyo; con
        // Ctrl/Cmd o la rueda se abre en otra pestaña, como un enlace.
        function openRow(evt) {
            if (evt.target.closest("a, button, input, label, .form-check")) {
                return;
            }
            var row = evt.target.closest("tr.mw-row-link");
            if (!row || !row.dataset.href) { return; }
            if (evt.type === "auxclick" && evt.button !== 1) { return; }
            if (evt.ctrlKey || evt.metaKey || evt.type === "auxclick") {
                window.open(row.dataset.href, "_blank", "noopener");
            } else {
                window.location.href = row.dataset.href;
            }
        }
        container.addEventListener("click", openRow);
        container.addEventListener("auxclick", openRow);

        container.addEventListener("change", function (evt) {
            var target = evt.target;
            if (target.classList.contains("mw-row-check")) {
                select(target, target.checked);
                updateSelectionUi();
            } else if (target.id === "mw-check-all") {
                container.querySelectorAll(".mw-row-check").forEach(
                    function (cb) {
                        cb.checked = target.checked;
                        select(cb, target.checked);
                    }
                );
                updateSelectionUi();
            }
        });

        document.getElementById("mw-mass-clear").addEventListener(
            "click", function () {
                selection.clear();
                refreshFromFragment();
            }
        );

        // S148: el modal común de exportación con plantilla
        // (panel/_screen_export_modal.html) exporta la selección.
        window.EbScreenExport = window.EbScreenExport || {};
        window.EbScreenExport.mw = {
            params: function () {
                if (!selection.size) { return null; }
                var pairs = [];
                selection.forEach(function (_item, key) {
                    pairs.push(["selected", key]);
                });
                return pairs;
            },
            count: function () {
                return selection.size === 1
                    ? "Se exportará la fila seleccionada."
                    : "Se exportarán las " + selection.size + " filas seleccionadas.";
            },
        };

        document.getElementById("mw-fullscreen").addEventListener(
            "click", function () {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                    return;
                }
                document.getElementById("mw-list-box").requestFullscreen()
                    .catch(function (err) {
                        console.warn("Pantalla completa no disponible:", err);
                    });
            }
        );

        // Casilleros de columnas: una regla CSS esconde las desmarcadas
        // (clase mwc-<clave> en cada celda) y se guardan las ocultas.
        var colStyle = document.getElementById("mw-col-style");
        document.querySelectorAll(".mw-col-check").forEach(function (cb) {
            cb.addEventListener("change", function () {
                var hidden = [];
                document.querySelectorAll(".mw-col-check").forEach(
                    function (box) {
                        if (!box.checked) { hidden.push(box.dataset.col); }
                    }
                );
                if (colStyle) {
                    colStyle.textContent = hidden.map(function (key) {
                        return ".mwc-" + key + "{display:none}";
                    }).join("");
                }
                if (window.EbNavState) {
                    window.EbNavState.save(screenKey, {hidden_columns: hidden});
                }
            });
        });

        document.body.addEventListener("htmx:afterSwap", function (evt) {
            if (evt.detail.target && evt.detail.target.id === "mw-table-container") {
                refreshFromFragment();
            }
        });

        refreshFromFragment();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
