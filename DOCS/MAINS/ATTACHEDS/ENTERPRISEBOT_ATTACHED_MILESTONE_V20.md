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
descarga de imagen.

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

#### D6 - Coste de Mano de Obra (OperatorMonthlyCost) -- PENDIENTE DE IMPLEMENTAR
Metricas: coste total por maquina en un periodo, coste por familia de averia,
coste por operario, reparto proporcional del coste mensual del operario segun
horas trabajadas en cada maquina.

Formula de reparto:
  coste_operario_en_maquina =
    (horas_operario_en_maquina / horas_totales_operario_en_mes)
    x coste_total_operario_en_mes

Fuente de datos: modelo OperatorMonthlyCost (work_order_processor).
Entrada: manual desde el panel o importacion de Excel mensual con
matching difuso de nombres por contexto de empresa.

---

### Tipos de Grafico por Dimension

D1 - Operario: barras (horas/periodo), linea temporal, heatmap (operario x familia).
D2 - Maquina: barras (intervenciones), scatter (horas vs frecuencia), pie familia.
D3 - Familia: barras apiladas, linea temporal, treemap por maquina.
D4 - Periodo: barras agrupadas, linea multi-serie.
D5 - Presupuesto: barras (importe/aseguradora), linea temporal.
D6 - Coste: barras (coste/maquina), linea temporal, pie (distribucion por maquina).

---

### Arquitectura Tecnica

#### App Django: analytics (segregada en S049)

En S049 se segrego el laboratorio de panel a su propia app Django independiente.
Esta decision es arquitectonicamente correcta y marca el patron para todos los
hitos futuros: todo dominio funcional nuevo va en app propia.

Estructura de la app analytics:
  analytics/__init__.py
  analytics/apps.py        -- AnalyticsConfig
  analytics/urls.py        -- 9 rutas bajo /panel/analytics/
  analytics/views.py       -- 8 vistas implementadas + vistas D6 pendientes

#### Backend: analytics/views.py

Vistas implementadas:
  AnalyticsView                  -- shell dashboard Plotly (legado, mantener)
  AnalyticsDataView              -- endpoint JSON para Plotly (legado, mantener)
  AnalyticsLabView               -- shell del laboratorio ECharts
  AnalyticsLabDataView           -- endpoint JSON multidimensional (D1-D5)
  AnalyticsLabExportView         -- exportacion Excel via openpyxl
  AnalyticsProfileListCreateView -- CRUD perfiles guardados (GET/POST JSON)
  AnalyticsProfileDeleteView     -- DELETE perfil por pk
  BotManagementView              -- panel gestion bot WhatsApp

Parametros de AnalyticsLabDataView.get():
  fields      (JSON array) -- lista de campos activos con type y value
  date_from   (str)        -- YYYY-MM-DD
  date_to     (str)        -- YYYY-MM-DD
  granularity (str)        -- day | week | month (por defecto: month)
  chart_type  (str)        -- bar | line | scatter | pie | heatmap | treemap

#### Modelo OperatorMonthlyCost (work_order_processor/models.py)

Creado en S051. Migracion 0023_operator_monthly_cost aplicada.
Campos: company (FK), worker_name (CharField 200), year, month
(PositiveSmallIntegerField), monthly_cost (DecimalField 10,2),
created_at, updated_at.
Unicidad: (company, worker_name, year, month).
Proposito: almacenar el coste laboral mensual bruto por operario para
que el laboratorio pueda calcular el reparto por maquina.

#### URLs en analytics/urls.py

  path("", AnalyticsView, name="analytics")
  path("data/", AnalyticsDataView, name="analytics_data")
  path("profiles/", AnalyticsProfileListCreateView, name="analytics_profile_list_create")
  path("profiles/<int:pk>/", AnalyticsProfileDeleteView, name="analytics_profile_delete")
  path("lab/", AnalyticsLabView, name="analytics_lab")
  path("lab/data/", AnalyticsLabDataView, name="analytics_lab_data")
  path("lab/export/", AnalyticsLabExportView, name="analytics_lab_export")
  path("bot/", BotManagementView, name="bot_management")

Incluida en enterprise_core/urls.py:
  path('panel/analytics/', include('analytics.urls', namespace='analytics'))

#### Frontend: panel/templates/panel/analytics_lab.html

Constructor aditivo de campos con limite de 5. POST de plantillas en JSON.
Modal de gestion de plantillas (labOpenManageModal / labDeleteProfileByPk).
ECharts 5 desde CDN. Tabla ordenable. Exportacion Excel via POST.
Fullscreen por panel. Divisor arrastrable. Unicode eliminado de comentarios
JS/CSS -- solo se conserva en contenido visible de usuario y simbolos CSS.

---

### Trabajo Realizado

S048: no produjo resultado utilizable.

S049 (2026-06-09):
  1. Diagnostico arquitectonico: panel/views.py tenia 18.765 lineas y 102 clases.
     Decision tomada: segregar el laboratorio a app Django independiente 'analytics'.
     Directriz arquitectonica vinculante registrada: todo dominio funcional nuevo
     va en app propia, sin excepciones.
  2. Creacion de la app analytics con apps.py, urls.py y views.py.
  3. Extraccion de las 8 clases analytics de panel/views.py a analytics/views.py.
     panel/views.py reducido de 18.765 a 16.482 lineas (-2.283 lineas).
  4. Registro de 'analytics' en INSTALLED_APPS (enterprise_core/settings.py).
  5. Inclusion de analytics.urls en enterprise_core/urls.py bajo /panel/analytics/.
  6. Eliminacion de las 8 rutas analytics de panel/urls.py.
  7. Correccion de todas las referencias panel:analytics* y panel:bot_management
     en los templates afectados (7 referencias en 3 archivos).
  8. Validacion django.setup() + django check --deploy: 0 errores, solo warnings
     de seguridad preexistentes.
  9. Recarga del servidor: status OK. Panel operativo sin errores de navegacion.
  10. Actualizacion de SYSTEM_PROMPTS_NEW.md a V.2.1: eliminadas las directrices
      de detenerse para preguntar como entregar el codigo.

S050 (2026-06-09):
  1. Actualizacion del PISA: PASO 0 ampliado de 4 lecturas obligatorias.
     Skills obligatorias: session-standards, ped (conjunto), pah,
     pythonanywhere-reload. Skill empaquetada como pisa.skill.
  2. Correccion bug dimension vacia: nueva funcion labCollectFields() sustituye
     a labDeriveDimension(). El frontend serializa todos los campos activos como
     JSON array y los envia como parametro 'fields' al backend.
  3. Eliminacion de los 9 inline styles del template analytics_lab.html y de
     los inline styles JS en labAddField() y labFieldTypeChanged(). Clases CSS
     nuevas anadidas a panel.css.
  4. Arquitectura multidimensional: nuevo dispatcher _dispatch() y handler
     _handle_cross() en AnalyticsLabDataView. Soporta hasta 5 campos activos
     con cruce por worker, machine, fault_category, period.
  5. Correcciones _handle_d1 heatmap y desglose por entidad en D1/D2.
  6. Sistema de plantillas de analisis implementado en analytics_lab.html.

S051 (2026-06-09):
  1. Correccion de tres referencias residuales style.display -> classList
     en analytics_lab.html (labLoadProfile, labDeleteProfile, labAddField).
     djlint 0 errores. Integridad 9/9 OK.
  2. Limpieza de Unicode en comentarios de desarrollador (JS, CSS, Django
     template comments). 123 caracteres Unicode auditados: eliminados de
     comentarios, conservados en contenido visible de usuario y simbolos
     CSS sort arrows (U+25B2 / U+25BC). Norma establecida: ASCII puro en
     contexto de desarrollador.
  3. Purgado de 2 registros legacy de AnalyticsProfile de la BD.
  4. Correccion POST de plantillas: urlencoded -> JSON en labCreateDefaultProfile()
     y labSaveProfile(). Alineacion con el endpoint que esperaba JSON.
  5. Modal de gestion de plantillas: boton lista en cabecera, labOpenManageModal(),
     labDeleteProfileByPk() con eliminacion individual desde el modal.
  6. Correccion tabla informe vacia: lab-table-wrap usaba style.display=''
     para mostrarse pero la ocultacion usaba classList -- inconsistencia que
     dejaba la tabla siempre oculta. Corregido con classList.remove().
  7. Creacion del modelo OperatorMonthlyCost en work_order_processor/models.py.
     Migracion 0023_operator_monthly_cost generada y aplicada correctamente.
     Tabla work_order_processor_operatormonthlycost operativa en BD.

---

### Hoja de Ruta para la Siguiente Sesion

NOTA: La siguiente sesion es H21 (split de panel/views.py). El H20 retoma
tras completar el split. Ver anexo ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md.

Pendiente en H20 al retomar:
  A) Vistas de gestion de OperatorMonthlyCost:
     - OperatorMonthlyCostListView   GET  /panel/analytics/costs/
     - OperatorMonthlyCostCreateView POST /panel/analytics/costs/create/
     - OperatorMonthlyCostDeleteView DELETE /panel/analytics/costs/<pk>/
     - OperatorMonthlyCostImportView POST /panel/analytics/costs/import/
       Logica de importacion Excel: columnas MECANICO, FECHA (serial Excel
       o YYYY-MM-DD), COSTE. Matching difuso de nombres via difflib.get_close_matches()
       contra worker_names unicos del mes en WorkOrderEntry para la empresa.
       Si ambiguedad (score < 0.8 o multiples candidatos): presentar al usuario
       para confirmacion antes de persistir. Formato serial Excel: dias desde
       1900-01-01 (ajuste leap year bug: restar 2 si valor > 60).
     Todas las vistas van en analytics/views.py. Rutas en analytics/urls.py
     bajo costs/. Mixin: SupervisorAccessMixin.

  B) Template de gestion de costes:
     panel/templates/panel/analytics_costs.html
     - Tabla de registros existentes (operario, mes/anyo, coste).
     - Formulario de entrada manual (select operario del mes, anyo, mes, coste).
     - Formulario de importacion Excel con preview de matching antes de confirmar.
     - Acceso desde sidebar bajo seccion Analisis.

  C) Dimension D6 en el laboratorio:
     - Nueva opcion 'cost' en el selector de tipo de campo de analytics_lab.html.
     - Handler _handle_cost() en AnalyticsLabDataView:
       * Cruzar WorkOrderEntryLine.delta_hours con OperatorMonthlyCost por
         (worker_name, year, month, company).
       * Si no hay registro de coste para un operario/mes: excluir o marcar
         como sin datos (configurable, por defecto excluir).
       * Calcular coste_en_maquina = (horas_en_maquina / horas_totales_mes)
         x monthly_cost para cada combinacion (operario, maquina, mes).
       * Devolver series y tabla con columnas:
         Operario, Maquina/CdG, Periodo, Horas, Coste (EUR).
     - Actualizar col_labels en _handle_cross() para incluir coste cuando
       el campo 'cost' este activo.
