/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/sw_albaran.js
 *
 * Service Worker v6 — H17 offline delivery-note prototype.
 * Scope restricted to /panel/budgets/albaran-demo/ only.
 * Does NOT intercept any other panel route.
 *
 * Service Worker v6 — prototipo offline de albarán H17.
 * Scope restringido a /panel/budgets/albaran-demo/ únicamente.
 * NO intercepta ninguna otra ruta del panel.
 */

const CACHE_NAME = "albaran-demo-v6";
const CACHE_URLS = [
    "/panel/budgets/albaran-demo/",
];

/* ── Install: precache the albaran page only ──────────────────────────────── */
self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(CACHE_URLS);
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

/* ── Activate: delete old caches ──────────────────────────────────────────── */
self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.filter(function (k) { return k !== CACHE_NAME; })
                    .map(function (k) { return caches.delete(k); })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

/* ── Fetch: only handle requests within our scope ─────────────────────────── */
self.addEventListener("fetch", function (event) {
    if (event.request.method !== "GET") return;

    /* Only intercept requests to the albaran demo page. */
    /* Solo interceptamos peticiones a la página del albarán demo. */
    const url = new URL(event.request.url);
    if (!url.pathname.startsWith("/panel/budgets/albaran-demo")) return;

    event.respondWith(
        fetch(event.request).then(function (networkResponse) {
            if (networkResponse && networkResponse.status === 200) {
                const clone = networkResponse.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, clone);
                });
            }
            return networkResponse;
        }).catch(function () {
            return caches.match(event.request).then(function (cached) {
                return cached || new Response(
                    "<h2 style='font-family:sans-serif;padding:2rem'>Sin cobertura — abre la app cuando recuperes conexión.</h2>",
                    { headers: { "Content-Type": "text/html" } }
                );
            });
        })
    );
});
