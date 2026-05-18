/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/chat.js
 *
 * IRC-style section chat room — client-side logic.
 * Handles:
 *   - Alias modal: shown on first visit when CompanyUser has no alias set.
 *   - Chat send: POST to ChatSendView with CSRF token and room pk.
 *   - Auto-scroll: scrolls message container to bottom after each HTMX swap.
 *
 * Loaded with defer on pages that include the chat room template (room.html).
 * All DOM access is deferred until the script executes after HTML parsing.
 *
 * ---
 * Sala de chat IRC — lógica del lado cliente.
 * Gestiona:
 *   - Modal de alias: mostrado en la primera visita cuando CompanyUser no tiene alias.
 *   - Envío de chat: POST a ChatSendView con token CSRF y pk de sala.
 *   - Auto-scroll: desplaza el contenedor de mensajes al final tras cada swap HTMX.
 *
 * Cargado con defer en páginas que incluyen la plantilla de sala de chat (room.html).
 * Todo acceso al DOM se aplaza hasta que el script se ejecuta tras el parseo del HTML.
 */

(function () {
    "use strict";

    /* ----------------------------------------------------------------
     * Utility: read CSRF token from meta tag.
     * Utilidad: leer el token CSRF desde el meta tag.
     * ---------------------------------------------------------------- */
    function getCsrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    /* ================================================================
     * ALIAS MODAL
     * Only active when #aliasModal exists in the DOM (alias_required=True).
     * Solo activo cuando #aliasModal existe en el DOM (alias_required=True).
     * ================================================================ */
    var aliasModalEl = document.getElementById("aliasModal");

    if (aliasModalEl) {
        var aliasInput   = document.getElementById("alias-input");
        var aliasSaveBtn = document.getElementById("alias-save-btn");
        var aliasError   = document.getElementById("alias-error");
        var bsAliasModal = new bootstrap.Modal(aliasModalEl);

        bsAliasModal.show();

        aliasInput.addEventListener("input", function () {
            aliasSaveBtn.disabled = aliasInput.value.trim().length === 0;
        });

        aliasInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && !aliasSaveBtn.disabled) {
                aliasSaveBtn.click();
            }
        });

        aliasSaveBtn.addEventListener("click", function () {
            var alias = aliasInput.value.trim();
            if (!alias) { return; }

            aliasSaveBtn.disabled = true;

            fetch("/panel/chat/alias/set/", {
                method:  "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken":  getCsrf(),
                },
                body: JSON.stringify({ alias: alias }),
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok) {
                    bsAliasModal.hide();
                    /* If there is a pending message, resend it now that alias is set.
                       Si hay un mensaje pendiente, reenviarlo ahora que el alias está establecido. */
                    if (pendingMessage) {
                        var msgToSend  = pendingMessage;
                        pendingMessage = null;
                        _doSend(msgToSend);
                    }
                } else {
                    aliasError.textContent = data.error || "Error desconocido.";
                    aliasError.classList.remove("d-none");
                    aliasSaveBtn.disabled  = false;
                }
            })
            .catch(function () {
                aliasError.textContent = "Error de red. Inténtalo de nuevo.";
                aliasError.classList.remove("d-none");
                aliasSaveBtn.disabled  = false;
            });
        });
    }

    /* ================================================================
     * CHAT SEND
     * Only active when #chat-send-btn exists in the DOM (can_send=True).
     * Solo activo cuando #chat-send-btn existe en el DOM (can_send=True).
     * ================================================================ */
    var input          = document.getElementById("chat-input");
    var sendBtn        = document.getElementById("chat-send-btn");
    /* pendingMessage holds a message body awaiting alias setup before resend.
       pendingMessage guarda el cuerpo de un mensaje en espera de alias antes del reenvío. */
    var pendingMessage = null;

    if (input && sendBtn) {

        input.addEventListener("input", function () {
            sendBtn.disabled = input.value.trim().length === 0;
        });

        function _doSend(body) {
            /*
             * Core send function — posts body to ChatSendView.
             * If the server returns HTTP 400 with an alias error, stores the
             * message as pending and opens the alias modal for immediate setup.
             * ---
             * Función de envío central — envía body a ChatSendView.
             * Si el servidor devuelve HTTP 400 con error de alias, guarda el
             * mensaje como pendiente y abre el modal de alias para configurarlo.
             */
            sendBtn.disabled = true;
            input.value      = "";

            var roomPk = sendBtn.dataset.roomPk;

            fetch("/panel/chat/" + roomPk + "/send/", {
                method:  "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken":  getCsrf(),
                },
                body: JSON.stringify({ body: body }),
            })
            .then(function (r) {
                return r.json().then(function (data) {
                    return { status: r.status, data: data };
                });
            })
            .then(function (result) {
                if (result.status === 400 && result.data.error &&
                        result.data.error.indexOf("alias") !== -1) {
                    /* Alias not set — store message and open alias modal.
                       Alias no configurado — guardar mensaje y abrir modal de alias. */
                    pendingMessage   = body;
                    sendBtn.disabled = false;
                    var modalEl = document.getElementById("aliasModal");
                    if (modalEl) {
                        var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
                        bsModal.show();
                    } else {
                        /* Modal not in DOM — alias_required was False on page load.
                           Reload to force modal rendering with alias_required=True.
                           Modal no está en el DOM — alias_required era False al cargar la página.
                           Recargar para forzar la renderización con alias_required=True. */
                        window.location.reload();
                    }
                } else if (!result.data.ok) {
                    console.error("# [CHAT SEND] Error:", result.data.error);
                    input.value      = body;
                    sendBtn.disabled = false;
                } else {
                    /* Send successful — trigger immediate HTMX refresh so the
                       sent message appears instantly without waiting for the
                       next 3-second polling cycle.
                       Envío exitoso — disparar refresco HTMX inmediato para que
                       el mensaje enviado aparezca al instante sin esperar el
                       próximo ciclo de polling de 3 segundos. */
                    sendBtn.disabled = false;
                    var container = document.getElementById("chat-messages-container");
                    if (container && window.htmx) {
                        htmx.trigger(container, "refresh");
                    }
                }
            })
            .catch(function (err) {
                console.error("# [CHAT SEND] Error de red:", err);
                input.value      = body;
                sendBtn.disabled = false;
            });
        }

        function handleSend() {
            var body = input.value.trim();
            if (!body) { return; }
            _doSend(body);
        }

        sendBtn.addEventListener("click", handleSend);
        sendBtn.addEventListener("touchend", function (e) {
            e.preventDefault();
            handleSend();
        });

        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });
    }

    /* ================================================================
     * AUTO-SCROLL
     * Managed by chatScrollIfNewMessages() in room.html — called via
     * hx-on::after-swap on #chat-messages-container. The htmx:afterSwap
     * global listener is intentionally removed here to avoid overriding
     * the conditional scroll logic and forcing scroll on every poll.
     * ---
     * Gestionado por chatScrollIfNewMessages() en room.html — llamado vía
     * hx-on::after-swap en #chat-messages-container. El listener global
     * htmx:afterSwap se elimina aquí intencionalmente para no sobreescribir
     * la lógica de scroll condicional y forzar scroll en cada polling.
     * ================================================================ */

}());
