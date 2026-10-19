// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/subject_upload.js
// H30 (S123). Envío común del modal "Subir documento" de las fichas de
// persona y de máquina. Miguel Ángel, tras subir un contrato real:
// "le das al botón y no sabemos lo que está ocurriendo. He tenido que
// volver a darle [...] He tenido que cerrar el modal, se queda
// abierto". La lectura de la fecha (Cloud Vision / Gemini) tarda varios
// segundos y el botón no daba ninguna señal, así que se pulsaba otra
// vez y el documento se subía dos veces.
//
// - Mientras sube: botón desactivado con indicador de carga y aviso de
//   que puede tardar; un segundo envío se ignora.
// - Al terminar: cada documento dice con qué fecha ha quedado.
// - Todo bien y con fecha: se cierra solo y la ficha se recarga.
// - Alguno sin fecha: se avisa y el botón pasa a "Aceptar" (recarga).
// - Error: se muestra y el botón vuelve a estar disponible.
// - Cerrar el modal después de haber subido algo recarga la ficha.
//
// ---
//
// Shared submit handler for the subject upload modal (person and
// machine detail pages): busy state, no double submit, per-document
// date feedback, auto close and reload.
(function () {
    'use strict';

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function renderResults(data) {
        let html = '';
        (data.uploaded || []).forEach(function (u) {
            html += '<div class="alert alert-success py-1 px-2 small mb-1">Subido: ' + escapeHtml(u.entry_name);
            if (u.date_label) {
                html += ' — fecha del ' + escapeHtml(u.date_kind) + ': <strong>' + escapeHtml(u.date_label) + '</strong>';
            }
            if (u.superseded_count) {
                html += ' — ' + u.superseded_count + ' anterior(es) marcado(s) obsoleto(s)';
            }
            html += '</div>';
            if (!u.date_label && u.needs_date) {
                html += '<div class="alert alert-warning py-1 px-2 small mb-1">No se ha podido leer ninguna fecha de '
                    + escapeHtml(u.entry_name) + '. Si la necesita (un contrato, para colocarlo en su periodo), '
                    + 'bórralo y vuelve a subirlo escribiendo la fecha.</div>';
            }
            // S130: el contenido parece de otro tipo -- aviso con botón
            // para corregirlo sin salir del modal (Cambiar tipo).
            if (u.type_mismatch) {
                html += '<div class="alert alert-warning py-1 px-2 small mb-1">⚠ ' + escapeHtml(u.entry_name)
                    + ' parece <strong>' + escapeHtml(u.type_mismatch.label) + '</strong>'
                    + (u.type_mismatch.description ? ' (' + escapeHtml(u.type_mismatch.description) + ')' : '')
                    + ', no el tipo elegido. '
                    + '<button type="button" class="btn btn-sm btn-warning py-0 ms-1" data-change-type-entry="'
                    + escapeHtml(u.entry_id) + '" data-change-type-code="' + escapeHtml(u.type_mismatch.code) + '">'
                    + 'Cambiar a ' + escapeHtml(u.type_mismatch.label) + '</button></div>';
            }
            // S130: datos del centro de gasto tomados del documento.
            if (u.filled && Object.keys(u.filled).length) {
                html += '<div class="alert alert-info py-1 px-2 small mb-1">Datos tomados del documento: '
                    + Object.keys(u.filled).map(function (k) {
                        return escapeHtml(k) + ' <strong>' + escapeHtml(u.filled[k]) + '</strong>';
                    }).join(', ') + '.</div>';
            }
            if (u.different && Object.keys(u.different).length) {
                html += '<div class="alert alert-warning py-1 px-2 small mb-1">El documento no coincide con la ficha: '
                    + Object.keys(u.different).map(function (k) {
                        return escapeHtml(k) + ' en la ficha ' + escapeHtml(u.different[k].current)
                            + ', en el documento <strong>' + escapeHtml(u.different[k].read) + '</strong>';
                    }).join('; ') + '. No se ha cambiado nada: revísalo.</div>';
            }
            if (u.warning) {
                html += '<div class="alert alert-warning py-1 px-2 small mb-1">⚠ Escribiste ' + escapeHtml(u.warning.typed_date)
                    + ', el sistema (' + escapeHtml(u.warning.source) + ') lee ' + escapeHtml(u.warning.system_date) + '. Verifica.</div>';
            }
        });
        (data.errors || []).forEach(function (e) {
            html += '<div class="alert alert-danger py-1 px-2 small mb-1">' + escapeHtml(e.file) + ': ' + escapeHtml(e.error) + '</div>';
        });
        if (data.error) {
            html += '<div class="alert alert-danger py-1 px-2 small mb-1">' + escapeHtml(data.error) + '</div>';
        }
        return html;
    }

    window.submitSubjectUpload = function (form, url, csrfToken, onUploaded) {
        if (form.dataset.busy === '1') { return; }
        const button = form.querySelector('button[type="submit"]');
        const resultDiv = form.querySelector('#uploadResult');
        const modalEl = form.closest('.modal');
        const originalLabel = button ? button.innerHTML : '';
        form.dataset.busy = '1';
        if (button) {
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Subiendo…';
        }
        resultDiv.innerHTML = '<div class="alert alert-info py-1 px-2 small mb-1">Subiendo y leyendo el documento. '
            + 'Puede tardar hasta un minuto: no cierres esta ventana.</div>';

        function release() {
            form.dataset.busy = '';
            if (button) {
                button.disabled = false;
                button.innerHTML = originalLabel;
            }
        }

        fetch(url, {
            method: 'POST', body: new FormData(form),
            headers: {'X-CSRFToken': csrfToken},
        }).then(function (r) { return r.json(); }).then(function (data) {
            resultDiv.innerHTML = renderResults(data);
            const uploaded = data.uploaded || [];
            if (uploaded.length && modalEl) {
                // Con algo ya subido, cerrar el modal siempre recarga.
                modalEl.addEventListener('hidden.bs.modal', function () {
                    location.reload();
                }, {once: true});
            }
            if (!data.ok) {
                release();
                return;
            }
            if (onUploaded && onUploaded(data)) { return; }
            // S130: botones "Cambiar a ..." del aviso de tipo.
            resultDiv.querySelectorAll('[data-change-type-entry]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    const body = new FormData();
                    body.append('document_type_code', btn.dataset.changeTypeCode);
                    btn.disabled = true;
                    fetch('/panel/documentacion/documento/' + btn.dataset.changeTypeEntry + '/cambiar-tipo/', {
                        method: 'POST', body: body, headers: {'X-CSRFToken': csrfToken},
                    }).then(function (r) { return r.json(); }).then(function (res) {
                        btn.closest('.alert').className = 'alert py-1 px-2 small mb-1 alert-' + (res.ok === false ? 'danger' : 'success');
                        btn.closest('.alert').textContent = res.ok === false
                            ? (res.error || 'No se pudo cambiar el tipo.')
                            : 'Tipo cambiado. Pulsa Aceptar para ver la ficha.';
                    }).catch(function () { btn.disabled = false; });
                });
            });
            const needsReview = uploaded.some(function (u) {
                return (!u.date_label && u.needs_date) || u.type_mismatch
                    || (u.different && Object.keys(u.different).length);
            });
            if (needsReview && button) {
                form.dataset.busy = '1';
                button.disabled = false;
                button.innerHTML = 'Aceptar';
                button.type = 'button';
                button.onclick = function () { location.reload(); };
                return;
            }
            setTimeout(function () {
                if (modalEl && window.bootstrap) {
                    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                } else {
                    location.reload();
                }
            }, 1500);
        }).catch(function () {
            resultDiv.innerHTML = '<div class="alert alert-danger py-1 px-2 small mb-1">Error de red al subir. '
                + 'Comprueba en la ficha si el documento llegó a subirse antes de repetirlo.</div>';
            release();
        });
    };
}());
