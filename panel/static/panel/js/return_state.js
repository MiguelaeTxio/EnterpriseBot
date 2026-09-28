// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/return_state.js
// H30 (S123), punto 4 de la hoja de ruta. "Volver" y el breadcrumb de
// las fichas de persona y de máquina devuelven la pantalla de origen
// exactamente como estaba (directriz 4.15).
//
// La pestaña y los filtros ya los guarda el servidor por usuario
// (PanelNavigationState). Lo que se perdía era la posición del scroll
// de las listas (y de la página), porque las pestañas se cargan por
// htmx y vuelven arriba. Al pulsar un enlace a una ficha se guarda en
// sessionStorage la pestaña activa y el scroll de cada contenedor
// desplazado; al volver a esa misma página se reaplica en cuanto las
// pestañas terminan de cargar.
//
// ---
//
// H30 (S123), roadmap point 4. Stores the scroll position of every
// scrolled container when a detail page link is clicked, and restores
// it when coming back to the same page, once htmx panes settle.
(function () {
    'use strict';

    const STORAGE_KEY = 'eb:return-state';
    const MAX_AGE_MS = 2 * 60 * 60 * 1000;
    const RESTORE_WINDOW_MS = 8000;
    const DETAIL_LINK = /\/panel\/documentacion\/(personal|maquinaria)\/\d+\/?(\?|$)/;

    function selectorFor(el) {
        // Id si lo tiene; si no, ruta nth-child desde el antecesor con id
        // más cercano (o desde body).
        if (el.id) { return '#' + CSS.escape(el.id); }
        const parts = [];
        let node = el;
        while (node && node !== document.body && !node.id) {
            const parent = node.parentElement;
            if (!parent) { break; }
            const index = Array.prototype.indexOf.call(parent.children, node) + 1;
            parts.unshift(node.tagName.toLowerCase() + ':nth-child(' + index + ')');
            node = parent;
        }
        const root = (node && node.id) ? '#' + CSS.escape(node.id) : 'body';
        return parts.length ? root + ' > ' + parts.join(' > ') : root;
    }

    function captureState() {
        const scrolls = [];
        document.querySelectorAll('body *').forEach(function (el) {
            if (el.scrollTop > 0 && el.scrollHeight > el.clientHeight) {
                scrolls.push({sel: selectorFor(el), top: el.scrollTop});
            }
        });
        const activeTab = document.querySelector('#docH30Tabs .nav-link.active');
        return {
            path: window.location.pathname,
            savedAt: Date.now(),
            windowY: window.scrollY,
            activeTab: activeTab ? activeTab.id : null,
            scrolls: scrolls,
        };
    }

    document.addEventListener('click', function (ev) {
        const link = ev.target.closest('a[href]');
        if (!link) { return; }
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || !DETAIL_LINK.test(url.pathname + url.search)) {
            return;
        }
        // Una ficha no guarda su propio estado al ir a otra ficha: el
        // origen es siempre el listado.
        if (DETAIL_LINK.test(window.location.pathname)) { return; }
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(captureState()));
        } catch (err) {
            // Sin sessionStorage (modo privado estricto): se vuelve igual,
            // solo que sin el scroll.
        }
    }, true);

    function loadPending() {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            if (!raw) { return null; }
            const state = JSON.parse(raw);
            if (state.path !== window.location.pathname
                    || Date.now() - state.savedAt > MAX_AGE_MS) {
                return null;
            }
            return state;
        } catch (err) {
            return null;
        }
    }

    function restore(state) {
        sessionStorage.removeItem(STORAGE_KEY);
        if (state.activeTab) {
            const tab = document.getElementById(state.activeTab);
            if (tab && !tab.classList.contains('active')) { tab.click(); }
        }
        const pending = state.scrolls.slice();
        let windowDone = false;
        const startedAt = Date.now();

        function attempt() {
            for (let i = pending.length - 1; i >= 0; i--) {
                const el = document.querySelector(pending[i].sel);
                if (el && el.scrollHeight - el.clientHeight >= pending[i].top) {
                    el.scrollTop = pending[i].top;
                    pending.splice(i, 1);
                }
            }
            if (!windowDone && document.documentElement.scrollHeight - window.innerHeight >= state.windowY) {
                window.scrollTo(0, state.windowY);
                windowDone = true;
            }
            return !pending.length && windowDone;
        }

        if (attempt()) { return; }
        const onSettle = function () {
            if (attempt()) { document.body.removeEventListener('htmx:afterSettle', onSettle); }
        };
        document.body.addEventListener('htmx:afterSettle', onSettle);
        const timer = setInterval(function () {
            if (attempt() || Date.now() - startedAt > RESTORE_WINDOW_MS) {
                clearInterval(timer);
                document.body.removeEventListener('htmx:afterSettle', onSettle);
            }
        }, 200);
    }

    function start() {
        const state = loadPending();
        if (state) { restore(state); }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
