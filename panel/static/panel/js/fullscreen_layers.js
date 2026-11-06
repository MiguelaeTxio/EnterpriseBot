/*
 * /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/fullscreen_layers.js
 *
 * H24 (S143). Modals and toasts over a list shown in full screen.
 * With the browser's full screen (directive 4.26) only the element in
 * full screen and what is inside it are painted; a modal or a toast
 * that lives in <body> stays underneath. While a modal opens in full
 * screen it is moved inside the full-screen element and goes back to
 * its place when it closes; the toast containers follow the full
 * screen in and out.
 * ---
 * Modales y avisos encima de una lista en pantalla completa (Miguel
 * Ángel: a Juan Francisco, "cuando le da a editar, se queda por debajo
 * de la ampliación al modal"). En pantalla completa solo se pinta el
 * elemento ampliado y lo que tiene dentro: el modal que se abre se mete
 * dentro y vuelve a su sitio al cerrarse; los contenedores de avisos
 * entran y salen con la pantalla completa.
 */
(function () {
    "use strict";
    document.addEventListener("show.bs.modal", function (event) {
        var full = document.fullscreenElement;
        var modal = event.target;
        if (!full || full.contains(modal)) { return; }
        modal._fsHome = modal.parentNode;
        modal._fsNext = modal.nextSibling;
        full.appendChild(modal);
    });
    document.addEventListener("hidden.bs.modal", function (event) {
        var modal = event.target;
        if (!modal._fsHome) { return; }
        modal._fsHome.insertBefore(modal, modal._fsNext);
        modal._fsHome = modal._fsNext = null;
    });
    document.addEventListener("fullscreenchange", function () {
        var full = document.fullscreenElement;
        document.querySelectorAll(".toast-container").forEach(function (box) {
            if (full) {
                if (!full.contains(box)) {
                    box._fsHome = box.parentNode;
                    box._fsNext = box.nextSibling;
                    full.appendChild(box);
                }
            } else if (box._fsHome) {
                box._fsHome.insertBefore(box, box._fsNext);
                box._fsHome = box._fsNext = null;
            }
        });
    });
}());
