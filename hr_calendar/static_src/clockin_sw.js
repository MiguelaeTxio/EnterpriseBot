/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/static_src/clockin_sw.js
 *
 * Service worker of the clock-in page (H24, S129). Scope: /fichaje/.
 * - Keeps a copy of the page so it opens without coverage (copy first,
 *   refreshed in the background when there is network).
 * - Background Sync (Android/Chrome): sends the presses stored in
 *   IndexedDB as soon as the connection returns, even with the page
 *   closed. Safari (iPhone) has no Background Sync: there the page
 *   sends them when it is opened, when the connection returns while it
 *   is open, every 30 s, or with the "Enviar pendientes" button.
 * Same store and same sending rules as the page (clockin.html).
 *
 * Service worker de la página de fichaje (H24, S129). Ámbito: /fichaje/.
 * - Guarda una copia de la página para que abra sin cobertura (primero
 *   la copia, y se renueva por detrás cuando hay red).
 * - Background Sync (Android/Chrome): envía las pulsaciones guardadas
 *   en IndexedDB en cuanto vuelve la conexión, aunque la página esté
 *   cerrada. Safari (iPhone) no lo tiene: allí las envía la página al
 *   abrirse, al volver la conexión con ella abierta, cada 30 s o con el
 *   botón «Enviar pendientes».
 * Mismo almacén y mismas reglas de envío que la página (clockin.html).
 */
// S130: v2 = página con botón único y fichaje manual.
// S143: v4 = sin fichaje manual, avisos con casillas y aviso de versión
// nueva (la página compara su versión con la de /fichaje/estado/).
const CACHE_NAME = "fichaje-v7";
const PAGE_URL = "/fichaje/";
const CACHED = [PAGE_URL, PAGE_URL + "manifest.json"];
const DB_NAME = "fichaje";
const STORE = "presses";
const SYNC_TAG = "fichaje-enviar";

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function (cache) { return cache.addAll(CACHED); })
            .then(function () { return self.skipWaiting(); })
    );
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.filter(function (k) {
                return k.startsWith("fichaje-") && k !== CACHE_NAME;
            }).map(function (k) { return caches.delete(k); }));
        }).then(function () { return self.clients.claim(); })
    );
});

self.addEventListener("fetch", function (event) {
    const request = event.request;
    if (request.method !== "GET") return;
    const url = new URL(request.url);
    if (CACHED.indexOf(url.pathname) === -1) return;
    event.respondWith(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.match(url.pathname).then(function (cached) {
                const network = fetch(request).then(function (response) {
                    if (response && response.status === 200) cache.put(url.pathname, response.clone());
                    return response;
                }).catch(function () { return null; });
                if (cached) {
                    event.waitUntil(network);
                    return cached;
                }
                return network.then(function (response) {
                    return response || new Response(
                        "<h2 style='font-family:sans-serif;padding:2rem'>Sin cobertura y la página de fichaje todavía no se había guardado en este móvil. Ábrela una vez con cobertura.</h2>",
                        {headers: {"Content-Type": "text/html; charset=utf-8"}}
                    );
                });
            });
        })
    );
});

function openDb() {
    return new Promise(function (resolve, reject) {
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = function () {
            if (!req.result.objectStoreNames.contains(STORE)) {
                req.result.createObjectStore(STORE, {keyPath: "id"});
            }
        };
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = function () { reject(req.error); };
    });
}

function allRecords(db) {
    return new Promise(function (resolve, reject) {
        const req = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
    });
}

function putRecord(db, record) {
    return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(record);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
    });
}

// Una pulsación está pendiente mientras no tenga received_at ni haya
// sido rechazada por inválida (400). Un 401 (móvil que no es el
// dispositivo de confianza) la deja pendiente y corta el envío.
function sendPending(sentBy) {
    return openDb().then(function (db) {
        return allRecords(db).then(function (records) {
            const pending = records.filter(function (r) { return !r.received_at && !r.rejected; })
                .sort(function (a, b) { return a.pressed_at.localeCompare(b.pressed_at); });
            return pending.reduce(function (chain, record) {
                return chain.then(function (stop) {
                    if (stop) return true;
                    return fetch(PAGE_URL + "enviar/", {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(Object.assign({}, record, {sent_by: record.manual ? "MANUAL" : sentBy})),
                    }).then(function (response) {
                        return response.json().catch(function () { return {}; }).then(function (data) {
                            if (response.ok) {
                                // S130: con `auto` el tipo lo ha decidido el servidor.
                                if (data.kind) record.kind = data.kind;
                                // S141: tipo de fichaje que ha quedado guardado.
                                record.clock_type = data.clock_type || null;
                                record.clock_type_name = data.clock_type_name || "";
                                record.auto = false;
                                record.received_at = data.received_at;
                                record.delay_seconds = data.delay_seconds;
                                record.parte_notice = data.parte_notice || "";
                                record.parte_ok = data.parte_ok !== false;
                                record.error = "";
                                return putRecord(db, record).then(function () { return false; });
                            }
                            record.error = data.error || ("Error " + response.status);
                            if (response.status === 400) record.rejected = true;
                            return putRecord(db, record).then(function () { return response.status === 401; });
                        });
                    });
                });
            }, Promise.resolve(false));
        });
    }).then(function () {
        return self.clients.matchAll().then(function (clients) {
            clients.forEach(function (client) { client.postMessage({type: "records-updated"}); });
        });
    });
}

self.addEventListener("sync", function (event) {
    if (event.tag === SYNC_TAG) event.waitUntil(sendPending("BACKGROUND"));
});
