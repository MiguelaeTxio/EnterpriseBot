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

---

### Tipos de Grafico por Dimension

D1 - Operario: barras (horas/periodo), linea temporal, heatmap (operario x familia).
D2 - Maquina: barras (intervenciones), scatter (horas vs frecuencia), pie familia.
D3 - Familia: barras apiladas, linea temporal, treemap por maquina.
D4 - Periodo: barras agrupadas, linea multi-serie.
D5 - Presupuesto: barras (importe/aseguradora), linea temporal.

---

### Arquitectura Tecnica

#### App Django: analytics (segregada en S049)

En S049 se segrego el laboratorio de panel a su propia app Django independiente.
Esta decision es arquitectonicamente correcta y marca el patron para todos los
hitos futuros: todo dominio funcional nuevo va en app propia.

Estructura de la app analytics:
  analytics/__init__.py
  analytics/apps.py        -- AnalyticsConfig
  analytics/urls.py        -- 8 rutas bajo /panel/analytics/
  analytics/views.py       -- 8 vistas (ver detalle abajo)

#### Backend: analytics/views.py

Vistas implementadas:
  AnalyticsView             -- shell dashboard Plotly (legado, mantener)
  AnalyticsDataView         -- endpoint JSON para Plotly (legado, mantener)
  AnalyticsLabView          -- shell del laboratorio ECharts
  AnalyticsLabDataView      -- endpoint JSON multidimensional (D1-D5)
  AnalyticsLabExportView    -- exportacion Excel via openpyxl
  AnalyticsProfileListCreateView -- CRUD perfiles guardados (GET/POST)
  AnalyticsProfileDeleteView     -- DELETE perfil por pk
  BotManagementView         -- panel gestion bot WhatsApp (movida aqui desde panel)

Parametros de AnalyticsLabDataView.get():
  dimension   (str) -- d1 | d2 | d3 | d4 | d5
  entity_pk   (str) -- pk de operario/maquina/familia; omitir para d4/d5
  date_from   (str) -- YYYY-MM-DD
  date_to     (str) -- YYYY-MM-DD
  granularity (str) -- day | week | month  (por defecto: month)
  chart_type  (str) -- bar | line | scatter | pie | heatmap | treemap

Validacion defensiva en get(): si dimension no esta en (d1..d5) devuelve
HTTP 400 con mensaje "Dimension no valida: ''. Valores permitidos: d1, d2, d3, d4, d5."

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

#### Templates afectados en S049

  panel/templates/panel/_nav_items.html
    -- panel:analytics_lab   -> analytics:analytics_lab
    -- panel:bot_management  -> analytics:bot_management
  panel/templates/panel/analytics.html
    -- panel:analytics_data                -> analytics:analytics_data
    -- panel:analytics_profile_list_create -> analytics:analytics_profile_list_create
    -- panel:analytics_profile_delete      -> analytics:analytics_profile_delete
  panel/templates/panel/bot/dashboard.html
    -- panel:bot_management (x3)           -> analytics:bot_management

#### Frontend: panel/templates/panel/analytics_lab.html

Constructor aditivo de campos: el usuario anade campos uno a uno con boton +.
Cada campo tiene selector de tipo (worker/machine/fault_category/spare_part/period)
y selector de valor (o * para todos).
Minimo 2 campos activos para poder analizar -- aviso visible si no se cumple.
ECharts 5 desde CDN. Tabla ordenable. Exportacion Excel via POST. Fullscreen. Divisor arrastrable.

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
  11. Bug identificado pendiente de resolver: el boton Analizar no envia el
      parametro 'dimension' correctamente al endpoint -- el backend lo recibe
      vacio y devuelve HTTP 400. La causa es un problema en el template
      analytics_lab.html (construccion del parametro dimension en el JS).

---

### Hoja de Ruta para la Siguiente Sesion (S050)

#### Contexto obligatorio previo

Antes de implementar nada, el modelo debe auditar el estado real de:
  analytics/views.py        -- verificar que las 8 vistas estan correctas
  panel/templates/panel/analytics_lab.html -- estado real del template

Comandos de auditoria:
  grep -n "dimension\|entity_pk\|Analizar\|fetch\|GET" panel/templates/panel/analytics_lab.html | head -60

#### Paso 1 - Correccion del bug de dimension vacia

El boton Analizar no envia el parametro 'dimension' al endpoint
analytics:analytics_lab_data. El backend recibe dimension='' y devuelve
HTTP 400 "Dimension no valida: ''".

La causa esta en analytics_lab.html: el JS que construye la URL de la
peticion al endpoint no esta incluyendo el parametro 'dimension' correctamente.

El template envia los campos como "tipo1:valor1,tipo2:valor2,..." via el
parametro 'fields' segun la arquitectura del anexo original, pero
AnalyticsLabDataView.get() espera el parametro 'dimension' (d1..d5), no 'fields'.

DECISION ARQUITECTONICA CRITICA: hay dos opciones.

OPCION A (recomendada): adaptar el template para que envie 'dimension' y
'entity_pk' en lugar de 'fields', alineandose con la implementacion real
del backend. El frontend construye dimension=d1 cuando el primer campo es
de tipo worker, dimension=d2 para machine, etc.

Mapeo tipo_campo -> dimension:
  worker        -> d1, entity_pk = nombre del operario (worker_name)
  machine       -> d2, entity_pk = pk del MachineAsset
  fault_category-> d3, entity_pk = clave de la familia (ej. HYDRAULIC)
  period        -> d4, entity_pk = null
  budget        -> d5, entity_pk = null

OPCION B: reimplementar el backend para aceptar 'fields' en lugar de
'dimension'+'entity_pk'. Mayor impacto, no recomendada.

El modelo debe presentar el analisis al usuario y ejecutar la OPCION A
salvo instruccion expresa en contrario.

#### Paso 2 - Sistema de plantillas de analisis por usuario

Modelo: AnalyticsProfile (ya existe en panel/models.py).
Campos existentes: company_user (FK), nombre (str), config (JSONField).
El campo config almacena la configuracion completa del laboratorio:
{
  "dimension": "d1",
  "entity_pk": "PABLO CAÑAMERO",
  "date_from": "2026-06-01",
  "date_to": "2026-06-09",
  "granularity": "month",
  "chart_type": "bar",
  "fields_raw": "worker:PABLO CAÑAMERO,machine:*"
}

Endpoints ya implementados en analytics/views.py:
  AnalyticsProfileListCreateView -- GET lista perfiles, POST crea/actualiza
  AnalyticsProfileDeleteView     -- DELETE elimina por pk

Lo que falta: la integracion en el template analytics_lab.html.
  - Boton "Guardar plantilla" que abre un input de nombre y hace POST a
    analytics:analytics_profile_list_create con el config actual.
  - Selector de plantillas guardadas que al seleccionar rellena todos los
    campos del laboratorio con los valores del config.
  - Boton de borrado por plantilla que llama a analytics:analytics_profile_delete.
  - Las plantillas se cargan al abrir el laboratorio via GET al endpoint
    analytics:analytics_profile_list_create.
  - Toda la logica de plantillas es client-side (JS) salvo las llamadas
    a los endpoints de persistencia.

#### Paso 3 - Verificacion E2E

Probar con datos reales de produccion:
  - Seleccionar D1 (Operario) con un operario concreto, rango de fechas
    con datos, granularidad mensual, tipo barras. Verificar que el grafico
    ECharts se renderiza y la tabla de informe se puebla correctamente.
  - Probar exportacion Excel.
  - Guardar una plantilla, recargar la pagina, cargar la plantilla y
    verificar que los campos se rellenan correctamente.
