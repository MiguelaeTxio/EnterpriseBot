/* /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/static_src/clockin_test_sw.js
 *
 * Service worker of the offline clock-in test (H24, S129). Scope:
 * /fichaje-prueba/ only.
 * - Keeps a copy of the page so it opens without coverage (copy
 *   first, refreshed in the background when there is network).
 * - Background Sync (Android/Chrome only): sends the presses stored
 *   in IndexedDB as soon as the connection returns, even with the
 *   page closed. Safari (iPhone) has no Background Sync: there the
 *   page sends them the next time it is opened with coverage.
 *
 * Service worker de la prueba de fichaje sin cobertura (H24, S129).
 * Ámbito: solo /fichaje-prueba/.
 * - Guarda una copia de la página para que abra sin cobertura (primero
 *   la copia, y se renueva por detrás cuando hay red).
 * - Background Sync (solo Android/Chrome): envía las pulsaciones
 *   guardadas en IndexedDB en cuanto vuelve la conexión, aunque la
 *   página esté cerrada. Safari (iPhone) no lo tiene: allí las envía
 *   la página la próxima vez que se abre con cobertura.
 */
const CACHE_NAME = "fichaje-prueba-v1";
const PAGE_URL = "/fichaje-prueba/";
const DB_NAME = "fichaje-prueba";
const STORE = "records";
const SYNC_TAG = "fichaje-prueba-enviar";

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function (cache) { return cache.addAll([PAGE_URL, PAGE_URL + "manifest.json"]); })
            .then(function () { return self.skipWaiting(); })
    );
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.filter(function (k) {
                return k.startsWith("fichaje-prueba-") && k !== CACHE_NAME;
            }).map(function (k) { return caches.delete(k); }));
        }).then(function () { return self.clients.claim(); })
    );
});

self.addEventListener("fetch", function (event) {
    const request = event.request;
    if (request.method !== "GET") return;
    const url = new URL(request.url);
    if (url.pathname !== PAGE_URL && url.pathname !== PAGE_URL + "manifest.json") return;
    // Primero la copia guardada (abre al instante, con o sin señal);
    // si hay red, se renueva la copia para la próxima vez.
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
                        "<h2 style='font-family:sans-serif;padding:2rem'>Sin cobertura y la página todavía no se había guardado. Ábrela una vez con cobertura.</h2>",
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

function sendPending(sentBy) {
    return openDb().then(function (db) {
        return allRecords(db).then(function (records) {
            const pending = records.filter(function (r) { return !r.received_at; });
            return pending.reduce(function (chain, record) {
                return chain.then(function () {
                    const body = Object.assign({}, record, {sent_by: sentBy});
                    return fetch(PAGE_URL + "enviar/", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(body),
                    }).then(function (response) {
                        if (!response.ok) throw new Error("HTTP " + response.status);
                        return response.json();
                    }).then(function (data) {
                        record.received_at = data.received_at;
                        record.gap_seconds = data.gap_seconds;
                        record.sent_by = sentBy;
                        return putRecord(db, record);
                    });
                });
            }, Promise.resolve());
        });
    }).then(function () {
        return self.clients.matchAll().then(function (clients) {
            clients.forEach(function (client) { client.postMessage({type: "records-updated"}); });
        });
    });
}

self.addEventListener("sync", function (event) {
    if (event.tag === SYNC_TAG) event.waitUntil(sendPending("segundo plano"));
});
