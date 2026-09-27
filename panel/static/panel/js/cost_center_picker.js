/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/cost_center_picker.js */
/*
 * Cost-centre picker: type a code, pick it from the matching cost
 * centres. Same experience as the daily work order form (asset-search
 * in form_entry_assets.js): same JSON ({assets: [{code, brand_model}]}),
 * same dropdown classes (.asset-dropdown.confirm-dropdown), and the
 * input keeps "CODE — brand/model" once chosen (the server resolves
 * the code, fleet.cost_center_search.resolve_cost_center).
 *
 * Usage: <input class="cdg-search" data-cdg-url="..."> inside a
 * position-relative parent. Works for inputs added later (modals, htmx
 * swaps) through event delegation.
 *
 * ---
 *
 * Selector de centro de gasto: se escribe el código y se elige entre
 * los CdG que coinciden. Misma experiencia que el parte diario digital
 * (asset-search de form_entry_assets.js): mismo JSON, mismas clases de
 * desplegable, y el campo queda con "CÓDIGO — marca/modelo" al elegir
 * (el servidor resuelve el código). S121: se escribió aparte porque el
 * autocompletado del parte está entrelazado con lógica propia del parte
 * (modo ausencia PERSONAL, subtipos EMPRESA_*, contadores, tickets de
 * avería); la BÚSQUEDA sí es una sola, compartida en el servidor.
 */
(function () {
    "use strict";

    /* La pestaña llega por htmx y puede recargarse: una sola vez. */
    if (window.EBCostCenterPickerLoaded) return;
    window.EBCostCenterPickerLoaded = true;

    var DEBOUNCE_MS = 250;
    var timers = new WeakMap();
    var selecting = false;

    function dropdownFor(input) {
        var dropdown = input.parentElement.querySelector(".asset-dropdown");
        if (!dropdown) {
            dropdown = document.createElement("div");
            dropdown.className = "asset-dropdown d-none list-group mt-1 confirm-dropdown";
            input.insertAdjacentElement("afterend", dropdown);
        }
        return dropdown;
    }

    function hide(dropdown) {
        dropdown.classList.add("d-none");
        dropdown.innerHTML = "";
    }

    function render(input, assets) {
        var dropdown = dropdownFor(input);
        dropdown.innerHTML = "";
        if (!assets || !assets.length) {
            hide(dropdown);
            return;
        }
        assets.forEach(function (asset) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "list-group-item list-group-item-action text-sm py-1 px-2";
            button.textContent = asset.brand_model
                ? asset.code + " — " + asset.brand_model
                : asset.code;
            /* pointerdown/touchstart llegan antes que blur (también en
               Android): la guardia evita cerrar el desplegable antes de
               elegir -- misma técnica que el parte diario. */
            button.addEventListener("pointerdown", function () { selecting = true; });
            button.addEventListener("touchstart", function () { selecting = true; }, {passive: true});
            button.addEventListener("click", function () {
                input.value = button.textContent;
                selecting = false;
                hide(dropdown);
                input.dispatchEvent(new Event("change", {bubbles: true}));
                input.focus();
            });
            dropdown.appendChild(button);
        });
        dropdown.classList.remove("d-none");
    }

    function search(input) {
        var query = input.value.split(" — ")[0].trim();
        fetch(input.dataset.cdgUrl + "?q=" + encodeURIComponent(query), {
            headers: {"X-Requested-With": "XMLHttpRequest"},
        })
            .then(function (response) { return response.ok ? response.json() : {assets: []}; })
            .then(function (data) { render(input, data.assets); })
            .catch(function () { hide(dropdownFor(input)); });
    }

    document.addEventListener("input", function (event) {
        var input = event.target;
        if (!input.classList || !input.classList.contains("cdg-search")) return;
        clearTimeout(timers.get(input));
        timers.set(input, setTimeout(function () { search(input); }, DEBOUNCE_MS));
    });

    document.addEventListener("focusin", function (event) {
        var input = event.target;
        if (input.classList && input.classList.contains("cdg-search") && input.value.trim()) {
            search(input);
        }
    });

    document.addEventListener("focusout", function (event) {
        var input = event.target;
        if (!input.classList || !input.classList.contains("cdg-search")) return;
        setTimeout(function () {
            if (!selecting) hide(dropdownFor(input));
        }, 150);
    });

    document.addEventListener("keydown", function (event) {
        var input = event.target;
        if (event.key === "Escape" && input.classList && input.classList.contains("cdg-search")) {
            hide(dropdownFor(input));
        }
    });
}());
