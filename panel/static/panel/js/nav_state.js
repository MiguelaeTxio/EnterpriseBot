// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/nav_state.js
//
// H30 (S128), hoja de ruta punto 2. Guardado común de la navegación
// por usuario (PanelNavigationState, directriz 4.15) para todo el panel.
//
// Origen real: Miguel Ángel escribía un nombre en el listado de
// Personal, lo borraba, cambiaba de página y al volver el nombre
// reaparecía. Cada pantalla guardaba con su propio temporizador de
// 400 ms y `clearTimeout`: un guardado nuevo CANCELABA el anterior en
// vez de sumarse (reproducido en local: pulsar la pestaña Personal
// programa "pestaña = personal", la carga de su lista programa
// "filtros" y la pestaña no se guarda nunca), y lo pendiente se perdía
// al salir de la página antes de los 400 ms.
//
// EbNavState.save(screenKey, partialUpdate): suma `partialUpdate` a lo
// pendiente de esa pantalla, con la misma fusión que el servidor
// (panel/views_navigation_state.py: nivel 1, y nivel 2 en
// filters/person_accordion/document_selection), y lo envía 400 ms
// después del último cambio. Al salir u ocultar la página se envía ya,
// con `keepalive` para que la petición sobreviva a la navegación.
(function () {
    'use strict';

    if (window.EbNavState) {
        return;
    }

    var DELAY_MS = 400;
    var NESTED_MERGE_KEYS = ['filters', 'person_accordion', 'document_selection'];
    var pending = {};
    var timers = {};

    function isPlainObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    function merge(target, update) {
        Object.keys(update).forEach(function (key) {
            var value = update[key];
            if (NESTED_MERGE_KEYS.indexOf(key) !== -1
                    && isPlainObject(value) && isPlainObject(target[key])) {
                target[key] = Object.assign({}, target[key], value);
            } else {
                target[key] = value;
            }
        });
    }

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function flush(screenKey) {
        clearTimeout(timers[screenKey]);
        delete timers[screenKey];
        var payload = pending[screenKey];
        if (!payload) {
            return;
        }
        delete pending[screenKey];
        fetch('/panel/navegacion/estado/' + screenKey + '/', {
            method: 'POST',
            keepalive: true,
            headers: {'X-CSRFToken': csrfToken(), 'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        }).catch(function () { /* sin red: se pierde solo esta vez */ });
    }

    function flushAll() {
        Object.keys(pending).forEach(flush);
    }

    function save(screenKey, partialUpdate) {
        if (!pending[screenKey]) {
            pending[screenKey] = {};
        }
        merge(pending[screenKey], partialUpdate);
        clearTimeout(timers[screenKey]);
        timers[screenKey] = setTimeout(function () {
            flush(screenKey);
        }, DELAY_MS);
    }

    window.addEventListener('pagehide', flushAll);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') {
            flushAll();
        }
    });

    window.EbNavState = {save: save, flush: flushAll};
})();
