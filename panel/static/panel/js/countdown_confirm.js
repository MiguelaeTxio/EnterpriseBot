// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/countdown_confirm.js
//
// Modal de confirmación con cuenta atrás -- reutilizable en cualquier
// plantilla que incluya el parcial
// panel/documentation/_countdown_confirm_modal.html (S028, DRY --
// antes vivía duplicado byte a byte en hub.html y machine_page.html
// como openDeleteConfirm(). Miguel Ángel: "esto no se puede
// reutilizar, habría que hacer un parcial... no vamos a quitarnos la
// regla de Don't Repeat Yourself, DRY es fundamental").
//
// window.openCountdownConfirm(config) -- genérico, para CUALQUIER
// acción que necesite una confirmación con cuenta atrás antes de
// habilitar el botón de aceptar, no solo borrar. config:
//   modalId       -- id del modal a controlar (por defecto
//                     'countdownConfirmModal', el que trae el parcial
//                     si no se le pasa otro modal_id al incluirlo).
//   url           -- action del <form> del modal.
//   method        -- método del form, 'post' por defecto.
//   hxTarget      -- opcional. Si se pasa, el form se envía por HTMX
//                     (hx-post/hx-target/hx-swap) en vez de un submit
//                     normal con recarga completa.
//   hxSwap        -- 'innerHTML' por defecto, solo si hxTarget.
//   bodyParts     -- array de trozos de texto para el cuerpo del
//                     modal, cada uno {text: '...'} o {strong: '...'}
//                     -- SIEMPRE vía textContent/createElement, nunca
//                     innerHTML con datos del servidor, para no abrir
//                     una vía de inyección con nombres de documento
//                     arbitrarios.
//   seconds       -- segundos de cuenta atrás antes de habilitar el
//                     botón, 5 por defecto.
//   extraFields   -- objeto {nombre: valor} de inputs hidden extra a
//                     incluir en el form (p.ej. machine_a/machine_b
//                     para no perder el contexto de la pantalla de
//                     transferencia al redirigir).
(function () {
    'use strict';

    function setBodyParts(bodyEl, bodyParts) {
        if (!bodyEl || !bodyParts) { return; }
        bodyEl.innerHTML = '';
        bodyParts.forEach(function (part) {
            if (part.strong !== undefined) {
                var strong = document.createElement('strong');
                strong.textContent = part.strong;
                bodyEl.appendChild(strong);
            } else if (part.text !== undefined) {
                bodyEl.appendChild(document.createTextNode(part.text));
            }
        });
    }

    window.openCountdownConfirm = function (config) {
        var modalEl = document.getElementById(config.modalId || 'countdownConfirmModal');
        if (!modalEl) {
            return;
        }
        var form = modalEl.querySelector('form');
        var btn = modalEl.querySelector('[data-countdown-btn]');
        var countdownLabel = modalEl.querySelector('[data-countdown-label]');
        var bodyEl = modalEl.querySelector('[data-countdown-body]');

        form.setAttribute('action', config.url);
        form.setAttribute('method', config.method || 'post');
        if (config.hxTarget) {
            form.setAttribute('hx-post', config.url);
            form.setAttribute('hx-target', config.hxTarget);
            form.setAttribute('hx-swap', config.hxSwap || 'innerHTML');
            if (window.htmx) { window.htmx.process(form); }
        } else {
            form.removeAttribute('hx-post');
            form.removeAttribute('hx-target');
            form.removeAttribute('hx-swap');
        }

        // Limpia inputs hidden extra de una apertura anterior del
        // mismo modal antes de añadir los de esta llamada.
        form.querySelectorAll('[data-countdown-extra]').forEach(function (el) {
            el.remove();
        });
        if (config.extraFields) {
            Object.keys(config.extraFields).forEach(function (name) {
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = name;
                input.value = config.extraFields[name];
                input.setAttribute('data-countdown-extra', '1');
                form.appendChild(input);
            });
        }

        setBodyParts(bodyEl, config.bodyParts);

        var seconds = config.seconds || 5;
        btn.disabled = true;
        countdownLabel.textContent = '(' + seconds + ')';
        if (modalEl._countdownInterval) {
            clearInterval(modalEl._countdownInterval);
        }
        modalEl._countdownInterval = setInterval(function () {
            seconds -= 1;
            if (seconds <= 0) {
                clearInterval(modalEl._countdownInterval);
                btn.disabled = false;
                countdownLabel.textContent = '';
            } else {
                countdownLabel.textContent = '(' + seconds + ')';
            }
        }, 1000);

        modalEl.addEventListener('hidden.bs.modal', function onHide() {
            if (modalEl._countdownInterval) {
                clearInterval(modalEl._countdownInterval);
            }
            btn.disabled = true;
            countdownLabel.textContent = '';
            modalEl.removeEventListener('hidden.bs.modal', onHide);
        }, { once: true });

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    };

    // Compatibilidad -- las plantillas de documentación (hub.html,
    // machine_page.html) siguen llamando a openDeleteConfirm(url,
    // targetSelector, docName) desde onclick= en cada botón de
    // papelera (_machine_detail.html, _personal_detail.html). En vez
    // de tocar esos 4 sitios de llamada, se mantiene el nombre como
    // envoltorio fino sobre el genérico -- misma mecánica, un único
    // origen de verdad.
    window.openDeleteConfirm = function (url, targetSelector, docName) {
        window.openCountdownConfirm({
            modalId: 'countdownConfirmModal',
            url: url,
            hxTarget: targetSelector,
            bodyParts: [
                { text: '¿Seguro que quieres eliminar ' },
                { strong: docName },
                { text: '? Esta operación no podrá revertirse.' },
            ],
            seconds: 5,
        });
    };
})();
