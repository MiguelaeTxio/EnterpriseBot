// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/albaran_upload.js
// S149 (H24). Carga de albaranes (ficha del trabajador y pestaña Fichajes).
//
// Miguel Ángel (16/11): "se queda condenada la vista [...] realizarlo en
// segundo plano para que se pueda seguir usando la plataforma". La
// ventana solo se ocupa de SUBIR los archivos (4 a la vez); la lectura
// con Gemini va en Celery. En cuanto se ha subido, la ventana se puede
// cerrar y seguir trabajando; mientras está abierta enseña cómo va y el
// resultado. Si se sale de la página durante la subida, el navegador
// avisa (la subida se cortaría).
//
// EbAlbaranUpload({prefix, startUrl, base, extraStart, onResult, onDone})
//   prefix:     prefijo de los ids ("cw" -> cw-alb-folder, cw-alb-go...)
//   startUrl:   URL que crea la carga (devuelve {batch})
//   base:       URL base de la carga (base + id + "/archivo/" ...)
//   extraStart: función que añade campos al FormData de inicio (opcional)
//   onResult:   función(datos, note) que pinta el resultado final (opcional)
//   onDone:     función() al terminar la lectura (refrescar la lista)
(function () {
    "use strict";
    const PARALLEL = 4;
    const OK = /\.(pdf|jpe?g|png)$/i;

    window.EbAlbaranUpload = function (cfg) {
        const $ = function (name) { return document.getElementById(cfg.prefix + "-alb-" + name); };
        const folder = $("folder"), loose = $("files"), go = $("go");
        const status = $("status"), notes = $("notes"), closeBtn = $("close");
        const bar = document.querySelector("#" + cfg.prefix + "-alb-progress .progress-bar");
        const modal = closeBtn ? closeBtn.closest(".modal") : null;
        const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
        let files = [];
        let uploading = false;
        let watching = null;

        function note(text, cls) {
            const li = document.createElement("li");
            if (cls) li.className = cls;
            li.textContent = text;
            notes.appendChild(li);
        }
        function progress(done, total) {
            $("progress").classList.remove("d-none");
            bar.style.width = Math.round(done * 100 / Math.max(total, 1)) + "%";
        }
        function pick(input) {
            files = Array.from(input.files || []).filter(function (f) { return OK.test(f.name); });
            status.textContent = files.length ? files.length + " archivo(s) PDF o foto." : "No hay PDF ni fotos.";
            notes.innerHTML = "";
            if (cfg.onResult) cfg.onResult(null, note);
            go.disabled = !files.length || uploading;
        }
        folder.addEventListener("change", function () { loose.value = ""; pick(folder); });
        loose.addEventListener("change", function () { folder.value = ""; pick(loose); });

        async function post(url, body) {
            const r = await fetch(url, {method: "POST", headers: {"X-CSRFToken": csrf, "Accept": "application/json"}, body: body});
            const data = await r.json().catch(function () {
                return {error: "El servidor no ha respondido bien (puede estar reiniciándose). Inténtalo de nuevo en un minuto."};
            });
            if (!r.ok || data.error) throw new Error(data.error || ("Error " + r.status));
            return data;
        }
        // Salir de la página a mitad de la subida la corta: el navegador avisa.
        window.addEventListener("beforeunload", function (evt) {
            if (!uploading) return;
            evt.preventDefault();
            evt.returnValue = "";
        });

        go.addEventListener("click", async function () {
            if (uploading || !files.length) return;
            uploading = true;
            go.disabled = folder.disabled = loose.disabled = true;
            notes.innerHTML = "";
            if (cfg.onResult) cfg.onResult(null, note);
            const list = files;
            files = [];
            try {
                const first = list[0].webkitRelativePath || "";
                const start = new FormData();
                start.append("count", list.length);
                start.append("folder", first.split("/")[0] || "");
                if (cfg.extraStart) cfg.extraStart(start);
                const batch = (await post(cfg.startUrl, start)).batch;
                let next = 0, done = 0;
                async function worker() {
                    while (next < list.length) {
                        const file = list[next++];
                        const body = new FormData();
                        body.append("file", file, file.name);
                        const data = await post(cfg.base + batch + "/archivo/", body);
                        if (data.skipped) note(data.skipped, "text-warning-emphasis");
                        done++;
                        progress(done, list.length);
                        status.textContent = "Subiendo " + done + " de " + list.length + "… (no salgas de esta página hasta que termine la subida)";
                    }
                }
                await Promise.all(Array.from({length: Math.min(PARALLEL, list.length)}, worker));
                await post(cfg.base + batch + "/fin/", new FormData());
                uploading = false;
                bar.style.width = "0%";
                status.innerHTML = "";
                note("Subidos " + list.length + " archivo(s). La IA los lee en segundo plano: puedes cerrar esta ventana y seguir usando la plataforma. "
                     + "El avance y el resultado se ven en «Cargas de albaranes».", "text-success");
                if (cfg.onDone) cfg.onDone();
                watch(batch);
            } catch (err) {
                status.innerHTML = "";
                note(err.message, "text-danger");
            }
            uploading = false;
            folder.disabled = loose.disabled = false;
            go.disabled = true;
        });

        function open() { return !modal || modal.classList.contains("show"); }
        // Mientras la ventana está abierta, cómo va la lectura; cerrada, nada.
        async function watch(batch) {
            watching = batch;
            while (watching === batch) {
                await new Promise(function (ok) { setTimeout(ok, 4000); });
                if (watching !== batch) return;
                if (!open()) continue;
                let d;
                try {
                    const r = await fetch(cfg.base + batch + "/estado/", {headers: {"Accept": "application/json"}});
                    if (!r.ok) throw new Error(String(r.status));
                    d = await r.json();
                } catch (e) {
                    status.textContent = "Esperando al servidor (puede estar reiniciándose)… La lectura sigue: si se corta, se reanuda sola.";
                    continue;
                }
                progress(d.read, d.files);
                if (d.status !== "READY" && d.status !== "CANCELLED") {
                    status.textContent = "La IA está leyendo: " + d.read + " de " + d.files + " archivo(s)… (puedes cerrar la ventana)";
                    continue;
                }
                watching = null;
                status.innerHTML = "";
                bar.style.width = "0%";
                notes.innerHTML = "";
                show(d);
                if (cfg.onDone) cfg.onDone();
                return;
            }
        }
        function show(d) {
            note(d.albaranes + " albarán(es) leído(s); " + d.days + " día(s) procesado(s) por la IA, "
                 + d.corrected + " corregido(s). Quedan sin visar: los visa un supervisor.", "text-success");
            if (cfg.onResult) cfg.onResult(d, note);
            (d.no_person || []).forEach(function (n) { note("Sin trabajador: " + n + " Cárgalo desde la ficha de fichajes de quien sea.", "text-warning-emphasis"); });
            (d.mismatch || []).forEach(function (n) { note("El nombre «" + n + "» no coincide del todo con el trabajador: revísalo.", "text-warning-emphasis"); });
            (d.unreadable || []).forEach(function (n) { note("Sin leer: " + n, "text-danger"); });
            if (d.error) note(d.error, "text-danger");
        }
        // Ver el resultado (o el avance) de una carga desde la lista.
        return {
            showBatch: function (batch) {
                if (uploading) return;
                notes.innerHTML = "";
                status.textContent = "Consultando la carga…";
                if (cfg.onResult) cfg.onResult(null, note);
                if (modal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(modal).show();
                watch(batch);
            },
        };
    };
})();
