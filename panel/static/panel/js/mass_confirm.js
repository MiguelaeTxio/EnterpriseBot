/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/mass_confirm.js
 *
 * H24 (S144). Confirmación de las acciones sobre los marcados. Miguel
 * Ángel: "es muy común tener seleccionado a alguien, cambiar un filtro,
 * seleccionar a otros y no acordarse [...] hay que poner un modal con
 * un tiempo de 3 segundos [...] tienes seleccionados tantos
 * trabajadores. Compruebe que la selección no tiene seleccionados
 * ocultos" (iba a quitar a Carlos Carlín de los fichajes y quitó la
 * sección entera de Taller).
 *
 * EbMassConfirm({action, names, hidden, noun}) -> Promise<boolean>
 *   action: qué se va a hacer ("Quitar los recordatorios").
 *   names:  nombres de todos los marcados.
 *   hidden: nombres de los marcados que NO se ven en la lista con los
 *           filtros actuales (se destacan en rojo).
 * El botón "Confirmar" se activa a los 3 segundos.
 */
(function () {
    "use strict";

    const WAIT_SECONDS = 3;
    let modalEl = null;

    function build() {
        modalEl = document.createElement("div");
        modalEl.className = "modal fade";
        modalEl.id = "ebMassConfirmModal";
        modalEl.tabIndex = -1;
        modalEl.setAttribute("aria-hidden", "true");
        modalEl.innerHTML =
            '<div class="modal-dialog modal-dialog-scrollable">' +
            '  <div class="modal-content">' +
            '    <div class="modal-header">' +
            '      <h5 class="modal-title"><i class="bi bi-exclamation-triangle text-warning me-2"></i>Comprueba la selección</h5>' +
            '      <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>' +
            '    </div>' +
            '    <div class="modal-body">' +
            '      <div class="fw-semibold mb-2" data-mc="action"></div>' +
            '      <div class="mb-2" data-mc="count"></div>' +
            '      <div class="alert alert-danger py-2 small d-none" data-mc="hidden"></div>' +
            '      <div class="small text-muted mb-1">Compruebe que la selección no tiene marcados ocultos:</div>' +
            '      <ul class="small mb-0 ps-3" data-mc="list" style="max-height: 40vh; overflow-y: auto;"></ul>' +
            '    </div>' +
            '    <div class="modal-footer">' +
            '      <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancelar</button>' +
            '      <button type="button" class="btn btn-primary" data-mc="ok" disabled></button>' +
            '    </div>' +
            '  </div>' +
            '</div>';
        document.body.appendChild(modalEl);
    }

    window.EbMassConfirm = function (opts) {
        opts = opts || {};
        if (!modalEl) build();
        const names = (opts.names || []).slice().sort(function (a, b) { return a.localeCompare(b); });
        const hidden = new Set(opts.hidden || []);
        const q = function (key) { return modalEl.querySelector('[data-mc="' + key + '"]'); };
        q("action").textContent = opts.action || "Se va a aplicar un cambio";
        // S155: opts.noun para listados que no son de personas.
        q("count").innerHTML = "Tienes marcados <strong>" + names.length + "</strong> " + (opts.noun || "trabajador(es)") + ".";
        const hiddenBox = q("hidden");
        if (hidden.size) {
            hiddenBox.classList.remove("d-none");
            hiddenBox.textContent = (hidden.size === 1 ? "1 de ellos NO se ve" : hidden.size + " de ellos NO se ven") + " en la lista con los filtros actuales (marcados en rojo abajo). Si no querías incluirlos, cancela y quítalos de la selección.";
        } else {
            hiddenBox.classList.add("d-none");
        }
        const list = q("list");
        list.innerHTML = "";
        names.forEach(function (name) {
            const li = document.createElement("li");
            li.textContent = name;
            if (hidden.has(name)) {
                li.className = "text-danger fw-semibold";
                li.textContent = name + " (no se ve en la lista)";
            }
            list.appendChild(li);
        });
        const ok = q("ok");
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        return new Promise(function (resolve) {
            let left = WAIT_SECONDS;
            let decided = false;
            ok.disabled = true;
            ok.textContent = "Confirmar (" + left + ")";
            const timer = setInterval(function () {
                left -= 1;
                if (left > 0) {
                    ok.textContent = "Confirmar (" + left + ")";
                } else {
                    clearInterval(timer);
                    ok.textContent = "Confirmar";
                    ok.disabled = false;
                }
            }, 1000);
            function onOk() {
                decided = true;
                modal.hide();
            }
            function onHidden() {
                clearInterval(timer);
                ok.removeEventListener("click", onOk);
                modalEl.removeEventListener("hidden.bs.modal", onHidden);
                resolve(decided);
            }
            ok.addEventListener("click", onOk);
            modalEl.addEventListener("hidden.bs.modal", onHidden);
            modal.show();
        });
    };

    /* Ayuda para las listas: nombres de los marcados que no están entre
     * las casillas visibles. `selection` es un Map(pk -> nombre) o un
     * Set de pks con `names` (Map pk -> nombre) aparte. */
    window.EbHiddenSelected = function (selectionNames, visiblePks) {
        const visible = new Set(Array.from(visiblePks || []).map(String));
        const hidden = [];
        selectionNames.forEach(function (name, pk) {
            if (!visible.has(String(pk))) hidden.push(name);
        });
        return hidden;
    };
}());
