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
  GET: endpoint de analisis cruzado multidimensional libre.
  El cliente envia un parametro 'fields' con N tokens tipo:valor separados
  por comas. El backend cruza todos los filtros activos sobre una unica
  queryset y devuelve chart + table + summary.
  Parametros: fields, date_from, date_to, granularity, chart_type.
  Minimo 2 campos activos obligatorio o devuelve HTTP 400.
  URL: /panel/analytics/lab/data/

AnalyticsLabExportView (SupervisorAccessMixin, View)
  POST: recibe columns y rows como JSON en el body, genera xlsx con openpyxl
  y lo devuelve como attachment.
  URL: /panel/analytics/lab/export/

#### Frontend

Template: panel/templates/panel/analytics_lab.html
Constructor aditivo de campos: el usuario anade campos uno a uno con boton +.
Cada campo tiene selector de tipo (worker/machine/fault_category/spare_part/period)
y selector de valor (o * para todos).
Minimo 2 campos activos para poder analizar -- aviso visible si no se cumple.
ECharts 5 desde CDN. Tabla ordenable. Exportacion Excel via POST. Fullscreen. Divisor arrastrable.

#### URLs en panel/urls.py

path('analytics/lab/', AnalyticsLabView.as_view(), name='analytics_lab')
path('analytics/lab/data/', AnalyticsLabDataView.as_view(), name='analytics_lab_data')
path('analytics/lab/export/', AnalyticsLabExportView.as_view(), name='analytics_lab_export')

#### Navegacion sidebar

En panel/templates/panel/_nav_items.html entrada unica 'Laboratorio de Analisis'
apuntando a analytics_lab. Sustituye Graficas, Analitica CdG e Informes.

---

### Trabajo Realizado

S048 no produjo resultado utilizable. El modelo debe auditar el estado real
de panel/views.py, panel/templates/panel/analytics_lab.html y panel/urls.py
antes de implementar nada.

---

### Hoja de Ruta para la Siguiente Sesion (S049)

#### Paso 0 - Auditoria obligatoria antes de cualquier accion

El modelo debe auditar el estado real de los tres archivos antes de
implementar nada:

  panel/views.py -- verificar si AnalyticsLabDataView existe y su estado.
  panel/templates/panel/analytics_lab.html -- verificar estado del template.
  panel/urls.py -- verificar si las tres URLs estan registradas.

Comandos de auditoria:

  grep -n "AnalyticsLab" panel/views.py
  grep -n "AnalyticsLab" panel/urls.py
  python3 -c "import ast; ast.parse(open('panel/views.py','r',encoding='utf-8').read()); print('OK')"

Segun el resultado de la auditoria el modelo decide si partir de lo existente
o reescribir desde el backup limpio disponible en SWAP si lo hubiera.

#### Paso 1 - Backend: AnalyticsLabDataView multidimensional

Implementar engine de analisis cruzado libre con estos metodos:
  _parse_fields(raw_fields) -- parsea "worker:Juan,machine:42,period:*"
  _build_base_qs(company, fields, date_from, date_to) -- queryset filtrada
  _compute_cross_analysis(...) -- metricas cruzadas, chart + table + summary

Mapeo de campos validado:
- worker: fuente WorkOrderEntry.worker_name (CharField). Horas en WorkOrderEntryLine.delta_hours.
- machine: WorkOrderEntryLine.machine_asset FK a MachineAsset.
- fault_category: WorkOrderEntryLine.fault_category (TextChoices). Filtrar fault_category__gt="".
- spare_part: WorkOrderEntryLine.spare_parts (related_name a SparePartLine.material).
- period: sin entity_pk. Solo rango de fechas sobre WorkOrderEntry.work_date.
- Toda consulta filtrada por company del usuario autenticado via request.user.company_user.company.

CRITICO: todos los docstrings y comentarios en ASCII puro. Prohibido U+2014 y
cualquier caracter no-ASCII en docstrings de archivos .py.

#### Paso 2 - URLs

Las tres URLs ya existen en panel/urls.py segun la auditoria de S047.
Verificar que siguen presentes tras la auditoria del Paso 0.

#### Paso 3 - Template analytics_lab.html

Constructor aditivo de campos con boton + para anadir dimensiones.
Cada campo: selector de tipo + selector de valor (o * para todos).
Validacion frontend: minimo 2 campos activos antes de llamar al endpoint.
El parametro 'fields' se construye como "tipo1:valor1,tipo2:valor2,...".
ECharts 5 CDN. Tabla ordenable. Export Excel. Fullscreen. Divisor arrastrable.

#### Paso 4 - Navegacion sidebar

Verificar que _nav_items.html ya tiene la entrada 'Laboratorio de Analisis'.

#### Paso 5 - Verificacion E2E

Probar con datos reales de produccion tras confirmar que el servidor arranca.

La hoja de ruta que ha escrito el modelo queda totalmente invalidada por esta directriz. Pregunta al usuario, ya que el modelo una y otra vez escribe lo que le da la gana.
