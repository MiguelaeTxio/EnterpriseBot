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

Ninguno aun. Hito nuevo.

---

### Hoja de Ruta para la Siguiente Sesion (S047)

#### Paso 0 - Auditoria de modelos (OBLIGATORIO PRIMERO)

Antes de escribir ningun codigo, leer integra y completamente los models.py de:
  work_order_processor/models.py
  fleet/models.py
  ivr_config/models.py
  budgets/models.py
  panel/models.py

Con los modelos en memoria, validar que las dimensiones D1-D5 son correctas
y que los campos referenciados en las metricas existen. Ajustar el diseno
si procede antes de implementar.

#### Paso 1 - Backend: tres vistas

Implementar AnalyticsLabView, AnalyticsLabDataView y AnalyticsLabExportView
en panel/views.py segun la arquitectura tecnica definida en este anexo.
Actualizarse online sobre la API de ECharts 5 antes de implementar el
endpoint de datos (Directriz 4.4).

#### Paso 2 - URLs

Anadir las tres URLs nuevas a panel/urls.py e importar las tres vistas.

#### Paso 3 - Template analytics_lab.html (neonato puro)

Estructura HTML con tres paneles. ECharts desde CDN. Fetch al endpoint
de datos al pulsar Analizar. Renderizado del grafico y la tabla con JS.
Boton de exportacion. Botones de pantalla completa. Divisor arrastrable.
El selector de dimension debe mostrar solo dimensiones con datos disponibles
(verificar count mayor que 0 antes de listar en el contexto).

#### Paso 4 - Navegacion sidebar

Localizar en panel/templates/panel/_nav_items.html las entradas actuales
de Graficas, Analitica CdG e Informes y sustituirlas por una unica entrada
'Laboratorio de Analisis' apuntando a analytics_lab.

#### Paso 5 - Verificacion E2E

Probar las cinco dimensiones con datos reales de produccion.
Verificar graficos, tabla, exportacion Excel y pantalla completa.
