// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/static_src/room_sw.js
// H37 (S138). Service worker de la sala de chat, ámbito /sala/
// (chat/views_room.py). Lo que pide el navegador para dejar instalar
// la sala como app, y la última copia de la página de la sala para
// abrirla sin cobertura (los mensajes se piden siempre a la red).
"use strict";
var CACHE = "sala-v1";

self.addEventListener("install", function () { self.skipWaiting(); });

self.addEventListener("activate", function (event) {
    event.waitUntil(caches.keys().then(function (keys) {
        return Promise.all(keys.filter(function (key) {
            return key.indexOf("sala-") === 0 && key !== CACHE;
        }).map(function (key) { return caches.delete(key); }));
    }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (event) {
    var request = event.request;
    if (request.method !== "GET" || request.mode !== "navigate") {
        return;
    }
    // Pages: network first; the saved copy only without coverage.
    // Páginas: primero la red; la copia guardada solo sin cobertura.
    event.respondWith(fetch(request).then(function (response) {
        if (response.ok) {
            var copy = response.clone();
            caches.open(CACHE).then(function (cache) {
                cache.put(request, copy);
            });
        }
        return response;
    }).catch(function () {
        return caches.match(request).then(function (saved) {
            return saved || new Response(
                "<h1>Sin conexión</h1><p>Vuelve a abrir la sala cuando tengas cobertura.</p>",
                {headers: {"Content-Type": "text/html; charset=utf-8"}}
            );
        });
    }));
});
