// /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/static/panel/js/export_templates.js
//
// Export template CRUD — list.html
// Gestiona creación, edición y copia de plantillas de exportación via JSON API.
// Soporta plantillas personales y globales (is_global).
//
// Export template CRUD — list.html
// Manages template creation, editing and copy via JSON API.
// Supports personal and global templates (is_global).
//
// Requires: window.EB_EXPORT_TEMPLATES (injected by list.html)
//   {
//     createUrl: "{% url 'panel:export_template_create' %}",
//     csrf:      "{{ csrf_token }}"
//   }
(function () {
    "use strict";

    var cfg       = window.EB_EXPORT_TEMPLATES || {};
    var CREATE_URL = cfg.createUrl || "";
    var CSRF       = cfg.csrf      || "";

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------
    function _jsonPost(url, payload, onOk, onErr) {
        fetch(url, {
            method:  "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
            body:    JSON.stringify(payload),
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
            if (!res.ok) { onErr(res.data.error || "Error desconocido."); return; }
            onOk(res.data);
        })
        .catch(function () { onErr("Error de red. Inténtalo de nuevo."); });
    }

    function _showErr(elId, msg) {
        var el = document.getElementById(elId);
        if (!el) { return; }
        el.textContent = msg;
        el.classList.remove("d-none");
    }

    function _hideErr(elId) {
        var el = document.getElementById(elId);
        if (el) { el.classList.add("d-none"); }
    }

    function _getChecked(selector) {
        return Array.from(document.querySelectorAll(selector + ":checked"))
                    .map(function (el) { return el.value; });
    }

    // ------------------------------------------------------------------
    // Create personal template
    // ------------------------------------------------------------------
    var btnCreate = document.getElementById("btn-create-template");
    if (btnCreate) {
        btnCreate.addEventListener("click", function () {
            _hideErr("create-error");
            var name     = (document.getElementById("create-name").value || "").trim();
            var columns  = _getChecked(".create-col-check");
            var sheetFmt = document.getElementById("create-sheet-format").value;
            var opScope  = document.getElementById("create-operator-scope").value;
            var isDef    = document.getElementById("create-is-default").checked;

            if (!name)            { _showErr("create-error", "El nombre es obligatorio."); return; }
            if (!columns.length)  { _showErr("create-error", "Selecciona al menos una columna."); return; }

            _jsonPost(
                CREATE_URL,
                { name: name, columns: columns, sheet_format: sheetFmt, operator_scope: opScope, is_default: isDef, is_global: false },
                function () { (window.EB_EXPORT_TEMPLATES && window.EB_EXPORT_TEMPLATES.onSuccess ? window.EB_EXPORT_TEMPLATES.onSuccess() : window.location.reload()); },
                function (msg) { _showErr("create-error", msg); }
            );
        });
    }

    // ------------------------------------------------------------------
    // Create global template (ADMIN only)
    // ------------------------------------------------------------------
    var btnCreateGlobal = document.getElementById("btn-create-global-template");
    if (btnCreateGlobal) {
        btnCreateGlobal.addEventListener("click", function () {
            _hideErr("create-global-error");
            var name     = (document.getElementById("create-global-name").value || "").trim();
            var columns  = _getChecked(".create-global-col-check");
            var sheetFmt = document.getElementById("create-global-sheet-format").value;
            var opScope  = document.getElementById("create-global-operator-scope").value;

            if (!name)           { _showErr("create-global-error", "El nombre es obligatorio."); return; }
            if (!columns.length) { _showErr("create-global-error", "Selecciona al menos una columna."); return; }

            _jsonPost(
                CREATE_URL,
                { name: name, columns: columns, sheet_format: sheetFmt, operator_scope: opScope, is_global: true },
                function () { (window.EB_EXPORT_TEMPLATES && window.EB_EXPORT_TEMPLATES.onSuccess ? window.EB_EXPORT_TEMPLATES.onSuccess() : window.location.reload()); },
                function (msg) { _showErr("create-global-error", msg); }
            );
        });
    }

    // ------------------------------------------------------------------
    // "Usar como base" — SUPERVISOR copies a global template
    // ------------------------------------------------------------------
    document.querySelectorAll(".btn-usar-base").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var pk       = btn.getAttribute("data-pk");
            var name     = btn.getAttribute("data-name");
            var columns  = (btn.getAttribute("data-columns") || "").split(",").filter(Boolean);
            var sheetFmt = btn.getAttribute("data-sheet-format");
            var opScope  = btn.getAttribute("data-operator-scope");

            _jsonPost(
                "/panel/export-templates/" + pk + "/update/",
                { name: name, columns: columns, sheet_format: sheetFmt, operator_scope: opScope },
                function () { (window.EB_EXPORT_TEMPLATES && window.EB_EXPORT_TEMPLATES.onSuccess ? window.EB_EXPORT_TEMPLATES.onSuccess() : window.location.reload()); },
                function (msg) { alert(msg); }
            );
        });
    });

    // ------------------------------------------------------------------
    // Pre-fill edit modal
    // ------------------------------------------------------------------
    document.querySelectorAll(".btn-edit-tpl").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var columns = (btn.getAttribute("data-columns") || "").split(",").filter(Boolean);
            var isDef   = btn.getAttribute("data-is-default") === "true";

            document.getElementById("edit-pk").value             = btn.getAttribute("data-pk");
            document.getElementById("edit-name").value           = btn.getAttribute("data-name");
            document.getElementById("edit-sheet-format").value   = btn.getAttribute("data-sheet-format");
            document.getElementById("edit-operator-scope").value = btn.getAttribute("data-operator-scope");
            document.getElementById("edit-is-default").checked   = isDef;

            document.querySelectorAll(".edit-col-check").forEach(function (chk) {
                chk.checked = columns.indexOf(chk.value) !== -1;
            });

            _hideErr("edit-error");
        });
    });

    // ------------------------------------------------------------------
    // Save edit
    // ------------------------------------------------------------------
    var btnSaveEdit = document.getElementById("btn-save-edit-template");
    if (btnSaveEdit) {
        btnSaveEdit.addEventListener("click", function () {
            _hideErr("edit-error");
            var pk       = document.getElementById("edit-pk").value;
            var name     = (document.getElementById("edit-name").value || "").trim();
            var columns  = _getChecked(".edit-col-check");
            var sheetFmt = document.getElementById("edit-sheet-format").value;
            var opScope  = document.getElementById("edit-operator-scope").value;
            var isDef    = document.getElementById("edit-is-default").checked;

            if (!name)           { _showErr("edit-error", "El nombre es obligatorio."); return; }
            if (!columns.length) { _showErr("edit-error", "Selecciona al menos una columna."); return; }

            _jsonPost(
                "/panel/export-templates/" + pk + "/update/",
                { name: name, columns: columns, sheet_format: sheetFmt, operator_scope: opScope, is_default: isDef },
                function () { (window.EB_EXPORT_TEMPLATES && window.EB_EXPORT_TEMPLATES.onSuccess ? window.EB_EXPORT_TEMPLATES.onSuccess() : window.location.reload()); },
                function (msg) { _showErr("edit-error", msg); }
            );
        });
    }

}());
