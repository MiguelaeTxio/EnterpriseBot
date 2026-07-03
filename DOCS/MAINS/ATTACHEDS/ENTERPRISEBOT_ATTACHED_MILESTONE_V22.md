# ENTERPRISEBOT_ATTACHED_MILESTONE_V22.md

## Hito 22 — Visor de Historial de Máquinas (Operario)

### Objetivo

Proporcionar al operario de taller (rol WORKSHOP) una herramienta de consulta
de solo lectura que muestre el historial completo de intervenciones sobre
cualquier máquina de la flota. El operario selecciona una máquina y un rango
de fechas y obtiene un listado cronológico de todas las intervenciones: fecha,
operario que actuó, familia de avería, subcategoría, descripción de la avería,
reparación realizada y horas invertidas.

El objetivo es que el operario pueda contextualizar una orden de trabajo antes
de intervenir, identificar patrones de avería recurrentes y determinar si un
problema oculto está generando averías periódicas en una parte concreta de
una máquina.

---

### Descripción Funcional

- Acceso: rol WORKSHOP (operario de taller). Sin acceso a costes ni a partes individuales.
- Selector de máquina: desplegable con todas las máquinas activas de la empresa.
- Selector de rango de fechas: desde/hasta, por defecto últimos 12 meses.
- Resultado: tabla cronológica descendente con columnas:
    Fecha | Operario | Familia avería | Subcategoría | Descripción avería | Reparación | Horas
- Resumen de cabecera: total intervenciones, horas acumuladas, última intervención.
- Agrupación opcional por familia de avería para ver recurrencia.
- Sin exportación Excel. Solo lectura.
- Acceso desde el panel del operario (sidebar sección Taller).

---

### Arquitectura Técnica

#### Directriz Arquitectónica Vinculante

MachineHistoryView va en su PROPIA APP DJANGO independiente, no en panel/views.py.
Nombre de app: history (o machine_history).
Razón: evitar que panel/views.py siga creciendo en dimensiones. Cada dominio
funcional nuevo va en app propia -- patrón establecido en S049 con la app analytics.
Esta directriz es de obligado cumplimiento y no admite excepciones.

#### App Django destino

La vista vive en una nueva app Django `history`, no en panel/views.py.
Mixin: WorkshopAccessMixin (rol WORKSHOP).

Vista principal:
  MachineHistoryView  GET  /panel/history/machine/

Parámetros GET:
  machine_pk  (int)  -- PK del MachineAsset seleccionado
  date_from   (str)  -- YYYY-MM-DD, por defecto hoy - 365 días
  date_to     (str)  -- YYYY-MM-DD, por defecto hoy

Fuente de datos:
  WorkOrderEntryLine
    .filter(machine_asset=machine_pk,
            entry__work_date__range=(date_from, date_to))
    .select_related('entry', 'entry__work_order', 'machine_asset')
    .order_by('-entry__work_date', '-entry__work_order__id')

Campos devueltos al template:
  - entry.work_date
  - entry.worker_name
  - fault_category (traducido via _FAULT_CAT_MAP)
  - fault_subcategory (traducido via _FAULT_SUBCAT_LABELS)
  - fault_description
  - repair_notes
  - delta_hours
  - or_val

Resumen de cabecera:
  - total_intervenciones: count()
  - total_horas: sum(delta_hours)
  - ultima_intervencion: max(entry__work_date)

#### Template

panel/templates/panel/machine_history.html
  - Extiende base.html
  - Formulario GET inline: selector de máquina + rango de fechas + botón Consultar
  - Tabla Bootstrap responsive con los campos definidos
  - Resumen de cabecera con badges (igual estilo que el lab)
  - Estado vacío si no hay resultados
  - Sin JS complejo — respuesta síncrona servidor

#### URLs

history/urls.py (nueva):
  path('machine/', MachineHistoryView.as_view(), name='machine_history')

enterprise_core/urls.py:
  path('panel/history/', include('history.urls', namespace='history'))

#### Sidebar

Añadir entrada en el sidebar bajo sección Taller, visible para WORKSHOP:
  "Historial de Máquina" → /panel/history/machine/

---

### Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| — | — | Hito creado. Pendiente de implementación. |
| S053 | 2026-06-24 | Implementación completa. App Django `history` creada (\_\_init\_\_.py, apps.py, urls.py, views.py). MachineHistoryView: resuelve máquina por `code`, filtra WorkOrderEntryLine por machine_asset y rango de fechas (default 365 días), tabla cronológica descendente con 7 columnas + resumen de 4 cards (intervenciones, horas acumuladas, última intervención, máquina). Template machine_history.html con autocomplete reutilizando WorkshopAssetAutocompleteView (campo hidden machine_code, JS inline con debounce 250ms). Sidebar _nav_items.html: entrada Historial de Máquina visible para WORKSHOP y ADMIN, NAV_TO_ACC registrado. Registrada en INSTALLED_APPS y enterprise_core/urls.py. Fix desvío: bug NoReverseMatch breakdown_room_manage en breakdown_ticket_list.html (URL ChatRoom eliminada en H17). Validado con datos reales (B43 — PALFINGER PK 72002, 19 intervenciones, 90 h). |
| S056 | 2026-06-25 | Ampliación visor operario WORKSHOP. Bug analizado: MachineHistoryView sin filtro reviewed — causa real es work_date=None en entries de partes en curso (sin corrección necesaria). WorkOrderHistoryListView: listado paginado (25/pág) de WorkOrder por fecha/máquina/descripción/estado, scope propio WORKSHOP vs todos WORKSHOPBOSS/ADMIN, anotación latest_work_date para ordenación. WorkOrderHistoryDetailView: detalle read-only por pk, restricción ownership WORKSHOP via get_object_or_404 filtrado, prefetch entries+lines+machine_asset, enriquecimiento fault_category/subcategory en Python (patrón dumb template). history/urls.py: rutas workorders/ y workorders/<int:pk>/. Templates neonatos: workorder_history_list.html y workorder_history_detail.html. _nav_items.html: entrada Mis partes (WORKSHOP/WORKSHOPBOSS/ADMIN), NAV_TO_ACC workorder_history→acc-operarios. Fix get_item TemplateSyntaxError: enriquecimiento movido a vista. own_profile.html: card Alias de chat IRC eliminada + fila Alias actual (salas IRC obsoletas). workorder_history_list.html: autocomplete máquina con campo hidden woh-machine-code + JS debounce 250ms llamando WorkshopAssetAutocompleteView. PCH: H22 pausado, H17 EN PROGRESO. |

---

### Hoja de Ruta para la Siguiente Sesión

#### TRABAJO COMPLETADO EN S053 + S056

MachineHistoryView, WorkOrderHistoryListView y WorkOrderHistoryDetailView
operativas y validadas en producción. Sidebar con Historial de Máquina y
Mis partes. Alias de chat IRC eliminado de own_profile.html.

H22 sin pasos pendientes identificados. Reactivar si surge nueva necesidad
en el visor de historial del operario.
