# ENTERPRISEBOT_ATTACHED_MILESTONE_V20.md

## Hito 20 - Laboratorio de Analisis Unificado

### Objetivo

Crear un centro de analisis de datos completamente configurable que unifique
y reemplace las vistas actuales de Graficas, Analitica CdG e Informes bajo
una unica interfaz de laboratorio. Permite analizar cualquier dimension
analizable del proyecto (operarios, centros de gasto/maquinas, familias de
averia, periodos, presupuestos) con graficas interactivas via Apache ECharts
y tablas de informe exportables a Excel.

---

### Arquitectura de la Vista

La vista se divide en tres paneles con gestion de pantalla completa independiente:

- Panel superior: Laboratorio (selector de dimension + filtros + boton Analizar).
  Colapsable para dar mas espacio al area de analisis.
- Panel inferior izquierdo: Informe tabular con columnas ordenables y exportacion Excel.
- Panel inferior derecho: Graficas ECharts interactivas con tooltip, zoom y selector
  de tipo de grafico.
- Divisor central arrastrable entre los dos paneles inferiores.
- Cada panel tiene boton de pantalla completa via Element.requestFullscreen().

---

### Libreria de Visualizacion

Apache ECharts 5 cargado desde CDN:
https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js

Sin instalacion en el venv. Tooltips ricos, animaciones fluidas, zoom, pan,
descarga de imagen. La vista actual analytics.html (Plotly.js) queda sustituida.

---

### Dimensiones de Analisis (Objetos Analizables)

#### D1 - Operario (CompanyUser WORKSHOP)
Metricas: horas trabajadas por periodo, numero de partes, partes por maquina,
familias de averia mas frecuentes, evolucion temporal de horas, ratio horas/parte,
dias trabajados.

#### D2 - Centro de Gasto / Maquina (MachineAsset)
Metricas: horas de mano de obra acumuladas, numero de intervenciones, familias
de averia dominantes, operarios que mas la intervienen, coste en horas por
periodo, frecuencia de averia (MTBF aproximado), evolucion temporal.

#### D3 - Familia de Averia (FaultCategory)
Metricas: frecuencia por periodo, maquinas mas afectadas, operarios que mas la
atienden, horas medias por intervencion, evolucion temporal, distribucion por maquina.

#### D4 - Periodo Temporal
Metricas cruzadas en un rango de fechas: resumen de horas totales, partes
procesados, distribucion por operario, distribucion por familia, top maquinas
intervenidas, comparativa entre periodos.

#### D5 - Presupuesto / Asistencia (Budget)
Metricas: presupuestos por aseguradora, importes medios, distribucion de
servicios, evolucion temporal. Solo disponible si existen registros en budgets.

---

### Tipos de Grafico por Dimension

D1 - Operario: barras (horas/periodo), linea temporal, heatmap (operario x familia).
D2 - Maquina: barras (intervenciones), scatter (horas vs frecuencia), pie familia.
D3 - Familia: barras apiladas, linea temporal, treemap por maquina.
D4 - Periodo: barras agrupadas, linea multi-serie.
D5 - Presupuesto: barras (importe/aseguradora), linea temporal.

---

### Arquitectura Tecnica

#### Backend

Vistas en panel/views.py:

AnalyticsLabView (SupervisorAccessMixin, View)
  GET: renderiza analytics_lab.html con operadores, maquinas, fault_categories,
  date_from_default (primer dia del mes actual) y date_to_default (hoy).
  URL: /panel/analytics/lab/

AnalyticsLabDataView (SupervisorAccessMixin, View)
  GET: devuelve JSON con chart, table y summary.
  Parametros: dimension (d1/d2/d3/d4/d5), entity_pk, date_from, date_to,
  granularity (day/week/month, default month), chart_type.
  Estructura de respuesta JSON:
    ok: bool
    chart: type, title, xAxis (lista), series (lista de name+data)
    table: columns (lista), rows (lista de listas)
    summary: total_hours, total_parts, avg_hours_per_part
  URL: /panel/analytics/lab/data/

AnalyticsLabExportView (SupervisorAccessMixin, View)
  POST: recibe columns y rows como JSON en el body, genera xlsx con openpyxl
  y lo devuelve como attachment. Nombre: lab_{dimension}_{date_from}_{date_to}.xlsx
  URL: /panel/analytics/lab/export/

#### Frontend

Template neonato: panel/templates/panel/analytics_lab.html
ECharts inicializado en DOMContentLoaded.
Fetch al endpoint de datos al pulsar Analizar.
Renderizado de grafico y tabla con JS puro sobre la respuesta JSON.
Boton de exportacion via POST al endpoint de export.
Botones de pantalla completa: element.requestFullscreen() / document.exitFullscreen().
Divisor arrastrable: JS drag listener sobre el divisor central.

#### URLs nuevas en panel/urls.py

path('analytics/lab/', AnalyticsLabView.as_view(), name='analytics_lab')
path('analytics/lab/data/', AnalyticsLabDataView.as_view(), name='analytics_lab_data')
path('analytics/lab/export/', AnalyticsLabExportView.as_view(), name='analytics_lab_export')

#### Navegacion sidebar

En panel/templates/panel/_nav_items.html sustituir las entradas actuales de
Graficas, Analitica CdG e Informes por una unica entrada 'Laboratorio de Analisis'
apuntando a analytics_lab.

---

### Trabajo Realizado

Ninguno sobre el Hito 20. La sesion S047 se dedico integramente a la
resolucion de incidencias urgentes de produccion y a la implementacion
de tours Driver.js en las vistas de asistencia y gestion. Trabajo de
soporte atendido fuera del hito:

- Restauracion de acceso de operarios de taller: migracion de 10 vistas
  de SupervisorAccessMixin a WorkshopRequiredMixin, reactivacion del
  CompanyUser miguel-loja (is_active=True).
- Correccion de NameError en InsurerDetailView.get: variable bases no
  definida antes de ser referenciada en el contexto.
- Siembra de 14 lineas UNLOCK faltantes en BD mediante comando de gestion
  seed_unlock_lines. Dos tarifas (RACE pk=86, Petit Forestier pk=101)
  pendientes de configuracion manual desde el panel.
- Implementacion de tours Driver.js para ADMIN/SUPERVISOR en 9 vistas
  del modulo budgets: insurer_list, insurer_detail, insurer_form (modos
  create y edit con apertura programatica de acordeones), bases,
  base_global, base_edit_page, history, detail y work_order_detail.
- Correccion de visibilidad del boton de ayuda en movil (d-none eliminado).
- Correccion del progressText de Driver.js mediante {% verbatim %} en
  _tour_workshop.html para evitar interpolacion Django.
- Exportacion de las 21 skills de usuario a skills_miguelaetxio.zip
  para sincronizacion con cuenta secundaria.

---

### Hoja de Ruta para la Siguiente Sesion (S048)

#### Paso 0 - Auditoria de modelos (OBLIGATORIO PRIMERO)

Los modelos ya fueron auditados en S047 y estan en memoria del anexo.
No es necesario releerlos salvo que hayan cambiado. Verificar unicamente
que no hay migraciones nuevas pendientes antes de implementar:

  python -m dotenv run python manage.py showmigrations | grep "\[ \]"

#### Paso 1 - Backend: tres vistas

Implementar AnalyticsLabView, AnalyticsLabDataView y AnalyticsLabExportView
en panel/views.py segun la arquitectura tecnica definida en este anexo.

Antes de implementar AnalyticsLabDataView, actualizarse online sobre la
API de ECharts 5 (Directriz 4.4 — actualizacion online obligatoria antes
de implementar el endpoint de datos).

Recordatorio del mapeo de campos validado en S047:
- D1 (Operario): fuente de nombres en WorkOrderEntry.worker_name (CharField,
  no FK). Selector construido con .values_list('worker_name', flat=True)
  .distinct(). Horas en WorkOrderEntryLine.delta_hours.
- D2 (Maquina): WorkOrderEntryLine.machine_asset FK a MachineAsset.
- D3 (Familia): WorkOrderEntryLine.fault_category (TextChoices, blank=True).
  Filtrar fault_category__gt="" en todas las consultas.
- D4 (Periodo): sin entity_pk. Filtros sobre WorkOrderEntry.work_date.
- D5 (Presupuesto): Budget.insurer (FK), Budget.service_date, Budget.total_amount.
  Disponibilidad: Budget.objects.filter(company=...).count() > 0.
- Toda consulta filtrada por company del usuario autenticado via
  request.company_user.company.

#### Paso 2 - URLs

Anadir las tres URLs a panel/urls.py e importar las tres vistas:
  path('analytics/lab/', AnalyticsLabView.as_view(), name='analytics_lab')
  path('analytics/lab/data/', AnalyticsLabDataView.as_view(), name='analytics_lab_data')
  path('analytics/lab/export/', AnalyticsLabExportView.as_view(), name='analytics_lab_export')

#### Paso 3 - Template analytics_lab.html (neonato puro)

Estructura HTML con tres paneles. ECharts desde CDN:
  https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js

Fetch al endpoint de datos al pulsar Analizar. Renderizado del grafico
y la tabla con JS. Boton de exportacion via POST. Botones de pantalla
completa via Element.requestFullscreen(). Divisor arrastrable entre
paneles inferiores. El selector de dimension debe mostrar solo dimensiones
con datos disponibles (verificar count > 0 antes de listar en el contexto).

#### Paso 4 - Navegacion sidebar

Localizar en panel/templates/panel/_nav_items.html las entradas actuales
de Graficas, Analitica CdG e Informes y sustituirlas por una unica entrada
'Laboratorio de Analisis' apuntando a analytics_lab.

#### Paso 5 - Verificacion E2E

Probar las cinco dimensiones con datos reales de produccion.
Verificar graficos, tabla, exportacion Excel y pantalla completa.
