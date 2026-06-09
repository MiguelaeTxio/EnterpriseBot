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

S050 (2026-06-09):
  1. Actualizacion del PISA: PASO 0 ampliado de 3 a 9 lecturas obligatorias.
     Grupo B (PED completo): ped-router, ped-format, ped-pma, ped-pea, ped-pmp,
     ped-doc. Grupo C: pythonanywhere-reload. Skill empaquetada como pisa.skill.
  2. Correccion bug dimension vacia: nueva funcion labCollectFields() sustituye
     a labDeriveDimension(). El frontend serializa todos los campos activos como
     JSON array y los envia como parametro 'fields' al backend.
  3. Eliminacion de los 9 inline styles del template analytics_lab.html y de
     los inline styles JS en labAddField() y labFieldTypeChanged(). Clases CSS
     nuevas anadidas a panel.css: lab-field-type-select, lab-field-value-select,
     lab-field-remove-btn, lab-add-field-btn, lab-field-warning, lab-btn-xs,
     lab-table-wrap-hidden, lab-profile-select, lab-btn-delete-profile,
     lab-field-limit. djlint: 0 errores en estado final.
  4. Arquitectura multidimensional: nuevo dispatcher _dispatch() y handler
     _handle_cross() en AnalyticsLabDataView. Soporta hasta 5 campos activos
     con cruce por worker, machine, fault_category, period. Compatibilidad
     legacy con parametro 'dimension' conservada. Limite 5 campos en frontend.
  5. Correccion _handle_d1 heatmap: filtro worker_name aplicado correctamente
     cuando entity_pk presente (hm_entry_filter / hm_line_filter).
  6. Desglose por entidad en _handle_d1 y _handle_d2 cuando entity_pk=None:
     una serie por operario / una serie por maquina respectivamente.
  7. Sistema de plantillas de analisis: labLoadProfiles(), labSaveProfile(),
     labDeleteProfile(), labLoadProfile(), labCreateDefaultProfile()
     implementadas en analytics_lab.html. Selector de plantillas, boton
     guardar y boton eliminar anadidos a la cabecera del laboratorio.
     Plantilla por defecto creada automaticamente en primer acceso.
  8. Pendiente al cierre de S050: sustituir style.display por classList en
     las referencias JS a btn-delete-profile y lab-field-limit. Verificar
     que AnalyticsProfileListCreateView devuelve clave 'profiles' en GET.
     Verificacion E2E completa del flujo multidimensional y plantillas.

---

### Hoja de Ruta para la Siguiente Sesion (S051)

#### Contexto obligatorio previo

Auditar el estado real de los dos archivos modificados en S050 antes de
implementar nada:

  analytics/views.py
  panel/templates/panel/analytics_lab.html

#### Paso 1 - Correccion JS style.display -> classList

En analytics_lab.html existen dos referencias residuales a style.display
que deben sustituirse por classList para ser coherentes con el resto del
codigo y evitar conflictos con las clases CSS definidas en panel.css:

  Referencia 1 (linea aprox. 562 en S050):
    const delBtn = document.getElementById('btn-delete-profile');
    ...
    if (delBtn) delBtn.style.display = 'none';  -- en labLoadProfile()
    if (delBtn) delBtn.style.display = '';       -- en labLoadProfile()

  Sustituir por:
    if (delBtn) delBtn.classList.add('lab-btn-delete-profile');
    if (delBtn) delBtn.classList.remove('lab-btn-delete-profile');

  Referencia 2 (linea aprox. 682 en S050):
    const limitWarn = document.getElementById('lab-field-limit');
    if (limitWarn) limitWarn.style.display = '';   -- en labAddField()
    if (limitWarn) limitWarn.style.display = 'none'; -- en labAddField()

  Sustituir por:
    if (limitWarn) limitWarn.classList.remove('lab-field-limit');
    if (limitWarn) limitWarn.classList.add('lab-field-limit');

  Referencia 3 (linea aprox. 654 en S050):
    document.getElementById('btn-delete-profile').style.display = 'none';
    -- en labDeleteProfile()

  Sustituir por:
    document.getElementById('btn-delete-profile').classList.add(
        'lab-btn-delete-profile'
    );

  Tras cada sustitucion ejecutar djlint --lint y verificar 0 errores.

#### Paso 2 - Verificar endpoint AnalyticsProfileListCreateView

Auditar analytics/views.py: confirmar que AnalyticsProfileListCreateView.get()
devuelve un JSON con la clave 'profiles' como lista de objetos con campos
pk, nombre y config. Si la estructura es diferente, adaptar el JS o el
endpoint segun corresponda.

Comando de auditoria:
  grep -n "class AnalyticsProfileListCreateView\|def get\|def post\|profiles\|JsonResponse" \
      analytics/views.py | head -40

#### Paso 3 - Verificacion E2E

Con el servidor recargado tras los pasos anteriores:
  - Seleccionar 2 campos (Operario + Maquina), rango con datos, barras.
    Verificar que el grafico ECharts muestra una serie por maquina para
    el operario seleccionado.
  - Seleccionar 3 campos (Operario + Maquina + Familia). Verificar tabla
    cruzada correcta.
  - Guardar una plantilla, recargar la pagina, cargar la plantilla y
    verificar que todos los campos se restauran correctamente.
  - Probar exportacion Excel con cruce multidimensional.
  - Verificar plantilla por defecto creada automaticamente en primer acceso.
