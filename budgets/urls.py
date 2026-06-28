"""
URL configuration for the budgets application.
All routes are prefixed with /panel/budgets/ via enterprise_core/urls.py.
---
Configuracion de URLs para la aplicacion budgets.
Todas las rutas tienen el prefijo /panel/budgets/ via enterprise_core/urls.py.
"""

from django.urls import path

from budgets import views

app_name = "budgets"

urlpatterns = [
    # Budget wizard — formulario secuencial guiado paso a paso.
    # Paso 1: seleccion de aseguradora.
    # Accessible to ASSISTANCE and ADMIN roles.
    # Accesible para los roles ASSISTANCE y ADMIN.
    path(
        "",
        views.BudgetWizardView.as_view(),
        name="wizard",
    ),

    # HTMX endpoint — resuelve pasos 3-9 del wizard server-side y devuelve
    # el fragmento completo de pasos segun insurer_id, base_id y vehicle_type_id.
    # HTMX endpoint — resolves wizard steps 3-9 server-side and returns
    # the full steps fragment based on insurer_id, base_id and vehicle_type_id.
    path(
        "steps/",
        views.BudgetStepsView.as_view(),
        name="steps",
    ),

    # HTMX endpoint — calcula la ruta desde la base hasta el punto kilometrico
    # via Routes API. Devuelve el fragmento de resultado al wizard.
    # HTMX endpoint — calculates route from base to kilometre point
    # via Routes API. Returns the result fragment to the wizard.
    path(
        "route-calc/",
        views.BudgetRouteCalcView.as_view(),
        name="route_calc",
    ),

    # HTMX endpoint — calcula la ruta dual (con peajes / sin peajes) via
    # Routes API. Devuelve el fragmento de visualizacion dual con mapa Leaflet
    # y radio buttons de seleccion al paso 4b del wizard.
    # HTMX endpoint — calculates dual route (with tolls / without tolls) via
    # Routes API. Returns the dual visualisation fragment with Leaflet map
    # and selection radio buttons to wizard step 4b.
    path(
        "route-dual/",
        views.BudgetRouteDualView.as_view(),
        name="route_dual",
    ),

    # HTMX endpoint — inicializa el planificador de ruta multi-parada con
    # las coordenadas de la base seleccionada. GET. Devuelve el fragmento
    # _route_multileg_fragment.html con el mapa Google Maps listo.
    # HTMX endpoint — initialises the multi-stop route planner with the
    # selected base coordinates. GET. Returns the _route_multileg_fragment.html
    # with the Google Maps panel ready.
    path(
        "route-multileg-init/",
        views.BudgetRouteMultilegInitView.as_view(),
        name="route_multileg_init",
    ),

    # HTMX endpoint — calcula la ruta multi-parada (circuito cerrado
    # Base → paradas → Base) via Routes API. POST. Recibe base_id,
    # waypoints_json, service_date y service_time. Devuelve el fragmento
    # de resultado con distancia, km por fase, flag de pernocta y polyline.
    # HTMX endpoint — calculates the multi-stop route (closed circuit
    # Base → stops → Base) via Routes API. POST. Receives base_id,
    # waypoints_json, service_date and service_time. Returns the result
    # fragment with distance, km per phase, overnight flag and polyline.
    path(
        "waypoints/",
        views.BudgetWaypointView.as_view(),
        name="waypoints",
    ),

    # HTMX endpoint — devuelve los tipos de vehiculo para la aseguradora
    # seleccionada en el paso 1. Usado por el formulario secuencial.
    # HTMX endpoint — returns vehicle types for the selected insurer (step 1).
    path(
        "vehicle-types/",
        views.BudgetVehicleTypesView.as_view(),
        name="vehicle_types",
    ),

    # HTMX endpoint — devuelve el selector de bases para la aseguradora
    # seleccionada en el paso 1. Usado por el formulario secuencial.
    # HTMX endpoint — returns base selector for the selected insurer (step 1).
    path(
        "bases/",
        views.BudgetBasesView.as_view(),
        name="bases",
    ),

    # HTMX endpoint — devuelve los conceptos opcionales disponibles para la
    # combinacion aseguradora + tipo de vehiculo seleccionados.
    # HTMX endpoint — returns available optional concepts for the selected
    # insurer + vehicle type combination.
    path(
        "optional-concepts/",
        views.BudgetOptionalConceptsView.as_view(),
        name="optional_concepts",
    ),

    # Budget result — muestra el total al operario tras el calculo.
    # Budget result — shows the total to the operator after calculation.
    path(
        "<int:pk>/result/",
        views.BudgetResultView.as_view(),
        name="result",
    ),

    # Budget status update — acepta o rechaza el presupuesto (ACCEPTED/REJECTED).
    # Budget status update — accepts or rejects the budget (ACCEPTED/REJECTED).
    path(
        "<int:pk>/status/",
        views.BudgetStatusUpdateView.as_view(),
        name="status_update",
    ),

    # Albarán demo — prototipo offline H17. Formulario mobile-first con firma canvas.
    # Delivery note demo — H17 offline prototype. Mobile-first form with canvas signature.
    path(
        "albaran-demo/",
        views.AlbaranDemoView.as_view(),
        name="albaran_demo",
    ),

    # Budget history — listado de presupuestos generados.
    # Solo visible para ADMIN. El operario ASSISTANCE no tiene acceso.
    # Budget history — list of generated budgets. ADMIN only.
    path(
        "history/",
        views.BudgetHistoryView.as_view(),
        name="history",
    ),

    # Budget bulk delete — elimina multiples presupuestos seleccionados. Solo ADMIN.
    # Excluye presupuestos en estado ACCEPTED.
    # Budget bulk delete — deletes multiple selected budgets. ADMIN only.
    # Excludes budgets with ACCEPTED status.
    path(
        "history/bulk-delete/",
        views.BudgetBulkDeleteView.as_view(),
        name="budget_bulk_delete",
    ),

    # Budget detail — desglose completo de un presupuesto. Solo ADMIN.
    # Budget detail — full breakdown of a budget. ADMIN only.
    path(
        "<int:pk>/detail/",
        views.BudgetDetailView.as_view(),
        name="detail",
    ),

    # ---------------------------------------------------------------------------
    # Insurer management routes — ADMIN only
    # Rutas de gestion de aseguradoras — solo ADMIN
    # ---------------------------------------------------------------------------

    # Insurer list — listado con busqueda live HTMX y filtro de estado.
    # Insurer list — list with HTMX live search and status filter.
    path(
        "insurers/",
        views.InsurerListView.as_view(),
        name="insurer_list",
    ),

    # Insurer create — formulario de alta de nueva aseguradora.
    # Insurer create — new insurer creation form.
    path(
        "insurers/new/",
        views.InsurerCreateView.as_view(),
        name="insurer_create",
    ),

    # Insurer detail — vista de solo lectura de tarifa completa. Solo ADMIN.
    # Insurer detail — read-only full tariff view. ADMIN only.
    path(
        "insurers/<int:pk>/detail/",
        views.InsurerDetailView.as_view(),
        name="insurer_detail",
    ),

    # Insurer update — formulario de edicion de aseguradora existente.
    # Insurer update — edit form for an existing insurer.
    path(
        "insurers/<int:pk>/edit/",
        views.InsurerUpdateView.as_view(),
        name="insurer_update",
    ),

    # Insurer clone — POST, clona aseguradora con nombre nuevo. Solo ADMIN.
    # Insurer clone — POST, clones insurer with new name. ADMIN only.
    path(
        "insurers/<int:pk>/clone/",
        views.InsurerCloneView.as_view(),
        name="insurer_clone",
    ),

    # Insurer copy tariff — POST, copia la tarifa activa a una aseguradora
    # existente sin crear una nueva. Solo ADMIN.
    # Insurer copy tariff — POST, copies the active tariff to an existing
    # insurer without creating a new one. ADMIN only.
    path(
        "insurers/<int:pk>/copy-tariff/",
        views.InsurerCopyTariffView.as_view(),
        name="insurer_copy_tariff",
    ),

    # Insurer toggle — HTMX POST, alterna is_active, devuelve badge.
    # Insurer toggle — HTMX POST, toggles is_active, returns badge fragment.
    path(
        "insurers/<int:pk>/toggle/",
        views.InsurerToggleView.as_view(),
        name="insurer_toggle",
    ),

    # Insurer delete — POST con confirmacion modal, elimina en cascada.
    # Insurer delete — POST with modal confirmation, deletes via CASCADE.
    path(
        "insurers/<int:pk>/delete/",
        views.InsurerDeleteView.as_view(),
        name="insurer_delete",
    ),

    # ---------------------------------------------------------------------------
    # Vehicle type management routes — ADMIN only
    # Rutas de gestión de tipos de vehículo — solo ADMIN
    # ---------------------------------------------------------------------------

    # Vehicle type create — HTMX POST, crea nuevo tipo de vehículo para la aseguradora.
    # Vehicle type create — HTMX POST, creates new vehicle type for the insurer.
    path(
        "insurers/<int:pk>/vehicle-types/new/",
        views.VehicleTypeCreateView.as_view(),
        name="vehicle_type_create",
    ),

    # Vehicle type update — GET devuelve form inline; POST guarda y devuelve fila.
    # Vehicle type update — GET returns inline form; POST saves and returns row.
    path(
        "vehicle-types/<int:pk>/edit/",
        views.VehicleTypeUpdateView.as_view(),
        name="vehicle_type_update",
    ),

    # Vehicle type toggle — HTMX POST, alterna is_active, devuelve fila.
    # Vehicle type toggle — HTMX POST, toggles is_active, returns row fragment.
    path(
        "vehicle-types/<int:pk>/toggle/",
        views.VehicleTypeToggleView.as_view(),
        name="vehicle_type_toggle",
    ),

    # Vehicle type delete — HTMX POST con confirmación modal, elimina si es seguro.
    # Vehicle type delete — HTMX POST with modal confirmation, deletes if safe.
    path(
        "vehicle-types/<int:pk>/delete/",
        views.VehicleTypeDeleteView.as_view(),
        name="vehicle_type_delete",
    ),

    # Vehicle type reorder — JSON POST, persiste nuevo sort_order tras drag & drop.
    # Vehicle type reorder — JSON POST, persists new sort_order after drag & drop.
    path(
        "vehicle-types/reorder/",
        views.VehicleTypeReorderView.as_view(),
        name="vehicle_type_reorder",
    ),

    # Tariff concept create — HTMX POST, crea nuevo concepto personalizado para la empresa.
    # Tariff concept create — HTMX POST, creates new custom concept for the company.
    path(
        "insurers/<int:pk>/concepts/new/",
        views.TariffConceptCreateView.as_view(),
        name="tariff_concept_create",
    ),

    # Tariff concept create global — POST desde página de conceptos (sin insurer_pk).
    # Tariff concept create global — POST from concept list page (no insurer_pk).
    path(
        "concepts/new/",
        views.TariffConceptCreateGlobalView.as_view(),
        name="tariff_concept_create_global",
    ),

    # Tariff concept list — página dedicada de gestión de conceptos. Solo ADMIN.
    # Tariff concept list — dedicated concept management page. ADMIN only.
    path(
        "concepts/",
        views.TariffConceptListView.as_view(),
        name="tariff_concept_list",
    ),

    # Tariff concept update — GET form inline; POST guarda y devuelve fila.
    # Tariff concept update — GET inline form; POST saves and returns row.
    path(
        "concepts/<int:pk>/edit/",
        views.TariffConceptUpdateView.as_view(),
        name="tariff_concept_update",
    ),

    # Tariff concept delete — HTMX POST, elimina si no tiene líneas asociadas.
    # Tariff concept delete — HTMX POST, deletes if no associated lines.
    path(
        "concepts/<int:pk>/delete/",
        views.TariffConceptDeleteView.as_view(),
        name="tariff_concept_delete",
    ),

    # ---------------------------------------------------------------------------
    # Toll segment management routes — ADMIN only
    # Rutas de gestión de tramos de peaje — solo ADMIN
    # ---------------------------------------------------------------------------

    # Toll segment config — POST guarda tipo de vehículo y recargo de peaje.
    # Toll segment config — POST saves vehicle type and toll markup.
    path(
        "toll-segments/config/",
        views.TollSegmentConfigView.as_view(),
        name="toll_segment_config",
    ),

    # Toll segment list — GET lista con filtros. ADMIN only.
    # Toll segment list — GET filtered list. ADMIN only.
    path(
        "toll-segments/",
        views.TollSegmentListView.as_view(),
        name="toll_segment_list",
    ),

    # Toll segment create — GET formulario de alta, POST crea nuevo tramo.
    # Toll segment create — GET creation form, POST creates new segment.
    path(
        "toll-segments/new/",
        views.TollSegmentCreateView.as_view(),
        name="toll_segment_create",
    ),

    # Toll segment update — GET formulario, POST guarda cambios.
    # Toll segment update — GET form, POST saves changes.
    path(
        "toll-segments/<int:pk>/edit/",
        views.TollSegmentUpdateView.as_view(),
        name="toll_segment_update",
    ),

    # Toll segment delete — POST desactiva (action=deactivate) o elimina
    # fisicamente (action=delete) el tramo.
    # Toll segment delete — POST deactivates (action=deactivate) or hard
    # deletes (action=delete) the segment.
    path(
        "toll-segments/<int:pk>/delete/",
        views.TollSegmentDeleteView.as_view(),
        name="toll_segment_delete",
    ),

    # Toll segment bulk toggle — POST activa o desactiva en bloque los tramos
    # seleccionados. Recibe pks[] y action ('activate'|'deactivate').
    # Toll segment bulk toggle — POST activates or deactivates selected
    # segments in bulk. Receives pks[] and action ('activate'|'deactivate').
    path(
        "toll-segments/bulk-toggle/",
        views.TollSegmentBulkToggleView.as_view(),
        name="toll_segment_bulk_toggle",
    ),

    # ---------------------------------------------------------------------------
    # Night schedule management routes — ADMIN only
    # Rutas de gestión de horarios nocturnos — solo ADMIN
    # ---------------------------------------------------------------------------

    # Night schedule list + create — GET lista, POST crea nuevo horario.
    # Night schedule list + create — GET list, POST creates new schedule.
    path(
        "night-schedules/",
        views.NightScheduleListView.as_view(),
        name="night_schedule_list",
    ),

    # Night schedule update — GET formulario, POST guarda cambios.
    # Night schedule update — GET form, POST saves changes.
    path(
        "night-schedules/<int:pk>/edit/",
        views.NightScheduleUpdateView.as_view(),
        name="night_schedule_update",
    ),

    # Night schedule delete — POST elimina si no hay aseguradoras vinculadas.
    # Night schedule delete — POST deletes if no linked insurers.
    path(
        "night-schedules/<int:pk>/delete/",
        views.NightScheduleDeleteView.as_view(),
        name="night_schedule_delete",
    ),

    # ---------------------------------------------------------------------------
    # Tariff management routes — ADMIN only
    # Rutas de gestion de tarifas y lineas — solo ADMIN
    # ---------------------------------------------------------------------------

    # Insurer tariff create — crea nueva version de tarifa, cierra la activa.
    # Insurer tariff create — creates new tariff version, closes active one.
    path(
        "insurers/<int:pk>/tariffs/new/",
        views.InsurerTariffCreateView.as_view(),
        name="tariff_create",
    ),

    # Tariff save notes — guarda el campo notes de la tarifa activa.
    # Tariff save notes — saves the notes field of the active tariff.
    path(
        "tariffs/<int:pk>/notes/",
        views.TariffSaveNotesView.as_view(),
        name="tariff_save_notes",
    ),

    # Tariff line add form — HTMX GET, devuelve formulario inline de nueva linea.
    # Tariff line add form — HTMX GET, returns inline add-line form fragment.
    path(
        "tariffs/<int:pk>/lines/add-form/",
        views.TariffLineAddFormView.as_view(),
        name="tariff_line_add_form",
    ),

    # Tariff line add — HTMX POST, crea nueva linea y devuelve fragmento de fila.
    # Tariff line add — HTMX POST, creates new line and returns row fragment.
    path(
        "tariffs/<int:pk>/lines/add/",
        views.TariffLineAddView.as_view(),
        name="tariff_line_add",
    ),

    # Tariff line save — HTMX POST, guarda campo editado y devuelve fila.
    # Tariff line save — HTMX POST, saves edited field and returns row fragment.
    path(
        "lines/<int:pk>/save/",
        views.TariffLineSaveView.as_view(),
        name="tariff_line_save",
    ),

    # Tariff line delete — HTMX POST, elimina linea y devuelve respuesta vacia.
    # Tariff line delete — HTMX POST, deletes line and returns empty response.
    path(
        "lines/<int:pk>/delete/",
        views.TariffLineDeleteView.as_view(),
        name="tariff_line_delete",
    ),

    # ---------------------------------------------------------------------------
    # Base management routes — ADMIN only
    # Rutas de gestion de bases — solo ADMIN
    # ---------------------------------------------------------------------------

    # Base manage — vista dedicada de gestion de bases de una aseguradora.
    # Base manage — dedicated base management view for an insurer.
    path(
        "insurers/<int:pk>/bases/",
        views.BaseManageView.as_view(),
        name="base_manage",
    ),

    # Base create — nueva base para una aseguradora.
    # Base create — new base for an insurer.
    path(
        "insurers/<int:pk>/bases/new/",
        views.BaseCreateView.as_view(),
        name="base_create",
    ),

    # Base update — edicion de base existente (GET form + POST save).
    # Base update — edit existing base (GET form + POST save).
    path(
        "bases/<int:pk>/edit/",
        views.BaseUpdateView.as_view(),
        name="base_update",
    ),

    # Base toggle — HTMX POST, alterna is_active, devuelve fila.
    # Base toggle — HTMX POST, toggles is_active, returns row fragment.
    path(
        "bases/<int:pk>/toggle/",
        views.BaseToggleView.as_view(),
        name="base_toggle",
    ),

    # Base delete — POST con confirmacion modal, elimina si no hay presupuestos.
    # Base delete — POST with modal confirmation, deletes if no linked budgets.
    path(
        "bases/<int:pk>/delete/",
        views.BaseDeleteView.as_view(),
        name="base_delete",
    ),

    # InsurerBase toggle — HTMX POST, alterna InsurerBase.is_active por aseguradora.
    # InsurerBase toggle — HTMX POST, toggles InsurerBase.is_active per insurer.
    path(
        "insurers/<int:insurer_pk>/bases/<int:base_pk>/toggle/",
        views.InsurerBaseToggleView.as_view(),
        name="insurerbase_toggle",
    ),

    # Base global — listado global de bases de la empresa. Solo ADMIN.
    # Base global — global company base list. ADMIN only.
    path(
        "bases/global/",
        views.BaseGlobalView.as_view(),
        name="base_global",
    ),

    # Base sync calendars — HTMX POST, sincroniza calendarios laborales de todas
    # las bases activas de la empresa via calendariosnacionales.com. Solo ADMIN.
    # Base sync calendars — HTMX POST, syncs labour calendars for all active
    # company bases via calendariosnacionales.com. ADMIN only.
    path(
        "bases/sync-calendars/",
        views.BaseSyncCalendarsView.as_view(),
        name="base_sync_calendars",
    ),

    # ---------------------------------------------------------------------------
    # Base calendar management routes — ADMIN only
    # Rutas de gestión de calendarios laborales de bases — solo ADMIN
    # ---------------------------------------------------------------------------

    # Base calendar list — listado global de bases con resumen de calendarios.
    # Base calendar list — global base list with calendar summary.
    path(
        "calendars/",
        views.BaseCalendarView.as_view(),
        name="base_calendar_list",
    ),

    # Base calendar detail — gestión de fechas festivas de una base individual.
    # Base calendar detail — manage holiday dates for a single base.
    path(
        "calendars/<int:pk>/",
        views.BaseCalendarDetailView.as_view(),
        name="base_calendar_detail",
    ),
    # Base calendar copy — copia el calendario de una base a otra. Solo ADMIN.
    # Base calendar copy — copy calendar from one base to another. ADMIN only.
    path(
        "calendars/<int:pk>/copy-calendar/",
        views.BaseCalendarCopyView.as_view(),
        name="base_calendar_copy",
    ),

    # Base clear coords — HTMX POST, limpia coordenadas de las bases seleccionadas.
    # Recibe lista de PKs via POST. Pone latitude/longitude a null. Solo ADMIN.
    # Base clear coords — HTMX POST, clears coordinates of selected bases.
    # Receives list of PKs via POST. Sets latitude/longitude to null. ADMIN only.
    path(
        "bases/clear-coords/",
        views.BaseClearCoordsView.as_view(),
        name="base_clear_coords",
    ),

    # ---------------------------------------------------------------------------
    # Export routes — Insurer tariff and budget history exports
    # Rutas de exportacion — tarifas de aseguradora e historial de presupuestos
    # ---------------------------------------------------------------------------

    # Insurer tariff exports — CSV, Excel, PDF, Word. ADMIN only.
    path(
        "insurers/<int:pk>/export/tariff/csv/",
        views.InsurerTariffExportCsvView.as_view(),
        name="insurer_tariff_export_csv",
    ),
    path(
        "insurers/<int:pk>/export/tariff/excel/",
        views.InsurerTariffExportExcelView.as_view(),
        name="insurer_tariff_export_excel",
    ),
    path(
        "insurers/<int:pk>/export/tariff/pdf/",
        views.InsurerTariffExportPdfView.as_view(),
        name="insurer_tariff_export_pdf",
    ),
    path(
        "insurers/<int:pk>/export/tariff/word/",
        views.InsurerTariffExportWordView.as_view(),
        name="insurer_tariff_export_word",
    ),

    # Budget history exports — CSV, Excel, PDF, Word. ADMIN only.
    # Respetan los mismos filtros GET que BudgetHistoryView.
    path(
        "history/export/csv/",
        views.BudgetExportCsvView.as_view(),
        name="budget_export_csv",
    ),
    path(
        "history/export/excel/",
        views.BudgetExportExcelView.as_view(),
        name="budget_export_excel",
    ),
    path(
        "history/export/pdf/",
        views.BudgetExportPdfView.as_view(),
        name="budget_export_pdf",
    ),
    path(
        "history/export/word/",
        views.BudgetExportWordView.as_view(),
        name="budget_export_word",
    ),

    # ---------------------------------------------------------------------------
    # H17 — Work order assistance routes
    # Rutas de órdenes de trabajo de asistencia (Hito 17)
    # ---------------------------------------------------------------------------

    # Work order create from budget — POST, crea orden desde presupuesto aceptado.
    # Work order create from budget — POST, creates order from accepted budget.
    path(
        "budgets/<int:pk>/work-order/create/",
        views.WorkOrderCreateFromBudgetView.as_view(),
        name="work_order_create_from_budget",
    ),

    # Work order create direct — GET form + POST, crea orden sin presupuesto.
    # Work order create direct — GET form + POST, creates order without budget.
    path(
        "work-orders/new/",
        views.WorkOrderCreateDirectView.as_view(),
        name="work_order_create_direct",
    ),

    # Work order detail — vista de detalle completa de la orden. ASSISTANCE + ADMIN.
    # Work order detail — full detail view of the work order. ASSISTANCE + ADMIN.
    path(
        "work-orders/<int:pk>/",
        views.WorkOrderDetailView.as_view(),
        name="work_order_detail",
    ),

    # Work order albarán — formulario mobile-first por unidad. ASSISTANCE + ADMIN.
    # Work order albarán — mobile-first form per unit. ASSISTANCE + ADMIN.
    path(
        "work-orders/units/<int:pk>/albaran/",
        views.WorkOrderAlbaranView.as_view(),
        name="work_order_albaran",
    ),

    # Work order PDF — exportación PDF del albarán de una unidad. ASSISTANCE + ADMIN.
    # Work order PDF — PDF export of a unit albarán. ASSISTANCE + ADMIN.
    path(
        "work-orders/units/<int:pk>/pdf/",
        views.WorkOrderPdfView.as_view(),
        name="work_order_pdf",
    ),
]





