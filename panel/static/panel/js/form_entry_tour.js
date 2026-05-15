/*
 * form_entry_tour.js — Via A work-order form: Driver.js tour steps.
 * Registers and auto-starts the guided tour for first-time users.
 *
 * form_entry_tour.js — Formulario Via A: pasos del tour Driver.js.
 * Registra e inicia automáticamente el tour guiado para nuevos usuarios.
 */
/*
 * Tour steps for form_entry.html (Via A — structured web form).
 * Pasos del tour para form_entry.html (Via A — formulario web estructurado).
 */
document.addEventListener("DOMContentLoaded", function () {
    if (!window.EbTour) { return; }

    window.EbTour.register("form_entry", [
        {
            popover: {
                title:       "Formulario de parte",
                description: "Rellena este formulario para registrar tu parte diario. "
                             + "Todos los campos marcados con * son obligatorios.",
                side:        "over",
                align:       "center",
            },
        },
        {
            element:  "#id_fecha",
            popover: {
                title:       "Fecha del parte",
                description: "Selecciona la fecha a la que corresponde este parte. "
                             + "No puedes introducir fechas anteriores a tu ultimo parte revisado.",
                side:        "bottom",
                align:       "start",
            },
        },
        {
            element:  "#block-1",
            popover: {
                title:       "Bloque de tarea",
                description: "Indica la maquina o seccion, la hora de inicio (H.C.) y fin (H.F.) "
                             + "y describe la averia o tarea realizada. "
                             + "Puedes anadir mas bloques si trabajaste en varias maquinas.",
                side:        "top",
                align:       "center",
            },
        },
        {
            element:  "#btn-add-block",
            popover: {
                title:       "Anadir bloque",
                description: "Pulsa aqui para añadir otro bloque de tarea si realizaste "
                             + "trabajos en mas de una maquina o seccion durante el dia.",
                side:        "top",
                align:       "start",
            },
        },
        {
            element:  "#btn-add-repuesto",
            popover: {
                title:       "Repuestos utilizados",
                description: "Si usaste piezas o materiales, anadilos aqui antes de guardar. "
                             + "Indica el material, las unidades y la procedencia.",
                side:        "top",
                align:       "start",
            },
        },
        {
            element:  "#btn-form-submit",
            popover: {
                title:       "Guardar parte",
                description: "Cuando hayas revisado todos los datos, pulsa aqui para guardar. "
                             + "El sistema te pedira confirmacion antes de registrar el parte.",
                side:        "top",
                align:       "end",
            },
        },
    ]);

    window.EbTour.startIfNew("form_entry");
});
