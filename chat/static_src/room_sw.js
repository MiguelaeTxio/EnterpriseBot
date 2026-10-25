// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/static_src/room_sw.js
// H37 (S138). Service worker de la sala de chat, ámbito /sala/
// (chat/views_room.py). Lo que pide el navegador para dejar instalar
// la sala como app, y la última copia de la página de la sala para
// abrirla sin cobertura (los mensajes se piden siempre a la red).
"use strict";
var CACHE = "sala-v2";

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

// S138: push notifications. One notification per room (same tag):
// the last message replaces the previous one, and it rings again.
// Notificaciones push. Una por sala (mismo tag): el último mensaje
// sustituye al anterior y vuelve a sonar.
self.addEventListener("push", function (event) {
    var data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
    event.waitUntil(self.registration.showNotification(
        data.title || "Sala de Asistencia",
        {
            body: data.body || "Hay mensajes nuevos.",
            tag: data.tag || "sala",
            renotify: true,
            icon: "/static/panel/img/albaran_icon_192.png",
            badge: "/static/panel/img/albaran_icon_192.png",
            data: {url: data.url || "/sala/"}
        }
    ));
});

// Touching it opens the room (or brings it to the front).
// Al tocarla se abre la sala (o se trae al frente).
self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || "/sala/";
    event.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(function (list) {
        for (var i = 0; i < list.length; i++) {
            if (list[i].url.indexOf(url) !== -1 && "focus" in list[i]) {
                return list[i].focus();
            }
        }
        return self.clients.openWindow(url);
    }));
});
