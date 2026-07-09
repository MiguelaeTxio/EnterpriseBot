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

#### D6 - Coste de Mano de Obra (OperatorMonthlyCost) -- IMPLEMENTADO EN S010

Metricas: coste por centro de gasto (maquina real o interno) en un
periodo, reparto proporcional del coste TOTAL del operario en ese
WorkPeriod segun horas trabajadas en cada centro de gasto -- incluye
PERSONAL/EMPRESA_ALMACEN_* en pie de igualdad con las maquinas reales.

Formula de reparto (vigente):
  coste_operario_en_centro_de_gasto =
    (horas_operario_en_ese_centro_de_gasto / horas_totales_operario_en_el_periodo)
    x coste_total_operario_en_el_periodo

coste_total_operario_en_el_periodo es un unico importe (nomina + horas
extraordinarias ya incluidas, sin desglose de tarifa ordinaria/extra).

Fuente de datos: modelo OperatorMonthlyCost (work_order_processor),
clave WorkPeriod (ivr_config.models, periodo de contrato/liquidacion
real del operario, no mes natural). Entrada: manual desde el panel
(analytics_costs.html) o importacion de Excel con matching difuso
contra CompanyUser reales de la empresa y resolucion de WorkPeriod por
fecha.

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
  analytics/urls.py        -- 13 rutas bajo /panel/analytics/
  analytics/views.py       -- 13 vistas implementadas, D1-D6 completas

#### Backend: analytics/views.py

Vistas implementadas:
  AnalyticsView                    -- shell dashboard Plotly (legado, mantener)
  AnalyticsDataView                -- endpoint JSON para Plotly (legado, mantener)
  AnalyticsLabView                 -- shell del laboratorio ECharts
  AnalyticsLabDataView             -- endpoint JSON multidimensional (D1-D6)
  AnalyticsLabExportView           -- exportacion Excel via openpyxl
  AnalyticsProfileListCreateView   -- CRUD perfiles guardados (GET/POST JSON)
  AnalyticsProfileDeleteView       -- DELETE perfil por pk
  AnalyticsProfileUpdateView       -- PATCH perfil por pk
  AnalyticsProfileCloneView        -- POST clonar perfil
  OperatorMonthlyCostListView      -- GET lista de costes por periodo
  OperatorMonthlyCostFormOptionsView -- GET operarios+periodos para selectores
  OperatorMonthlyCostCreateView    -- POST upsert coste (work_period_id + total_cost)
  OperatorMonthlyCostDeleteView    -- DELETE coste por pk
  OperatorMonthlyCostImportView    -- POST import Excel en dos fases
  AnalyticsCostsView               -- shell pagina de gestion de costes
  BotManagementView                -- panel gestion bot WhatsApp

Mixin: SupervisorAccessMixin (ADMIN/SUPERVISOR/WORKSHOPBOSS) en todas
las vistas de Laboratorio y Costes desde S010 -- antes AnalyticsLabView/
AnalyticsLabDataView/AnalyticsLabExportView usaban AdminRoleRequiredMixin
(ADMIN unicamente).

Parametros de AnalyticsLabDataView.get():
  fields      (JSON array) -- lista de campos activos con type y value
  date_from   (str)        -- YYYY-MM-DD
  date_to     (str)        -- YYYY-MM-DD
  granularity (str)        -- day | week | month (por defecto: month)
  chart_type  (str)        -- bar | line | scatter | pie | heatmap | treemap

Metricas soportadas en _handle_cross(): ordinary_hours, extra_hours,
cost (S010). 'cost' resuelve entry.worker_name -> CompanyUser real
(match exacto, normalizado a mayusculas) -> WorkPeriod que cubre la
fecha -> OperatorMonthlyCost.total_cost, con reparto proporcional
sobre el total de horas del operario en el periodo (todos los centros
de gasto, internos incluidos).

#### Modelo OperatorMonthlyCost (work_order_processor/models.py)

Creado en S051 (migracion 0023), rediseñado en S010 (migracion 0029)
tras conversacion de Miguel Angel con Jeronimo sobre el calculo real
de coste/hora.
Campos actuales: work_period (OneToOneField a ivr_config.WorkPeriod),
total_cost (DecimalField 10,2 -- coste total del periodo, nomina +
horas extra sin desglose), created_at, updated_at.
company y worker_name YA NO se guardan -- se derivan de
work_period.company_user (company_user.company,
company_user.user.get_full_name()).
Unicidad: garantizada por el OneToOneField (un coste por WorkPeriod).
Proposito: almacenar el coste laboral total del operario para un
WorkPeriod (periodo de contrato/liquidacion, no mes natural) para que
el laboratorio (dimension D6) calcule el reparto por centro de gasto.

#### URLs en analytics/urls.py

  path("", AnalyticsView, name="analytics")
  path("data/", AnalyticsDataView, name="analytics_data")
  path("profiles/", AnalyticsProfileListCreateView, name="analytics_profile_list_create")
  path("profiles/<int:pk>/", AnalyticsProfileDeleteView, name="analytics_profile_delete")
  path("profiles/<int:pk>/update/", AnalyticsProfileUpdateView, name="analytics_profile_update")
  path("profiles/<int:pk>/clone/", AnalyticsProfileCloneView, name="analytics_profile_clone")
  path("costs/", OperatorMonthlyCostListView, name="operator_monthly_cost_list")
  path("costs/form-options/", OperatorMonthlyCostFormOptionsView, name="operator_monthly_cost_form_options")
  path("costs/create/", OperatorMonthlyCostCreateView, name="operator_monthly_cost_create")
  path("costs/<int:pk>/", OperatorMonthlyCostDeleteView, name="operator_monthly_cost_delete")
  path("costs/import/", OperatorMonthlyCostImportView, name="operator_monthly_cost_import")
  path("costs/manage/", AnalyticsCostsView, name="analytics_costs")
  path("lab/", AnalyticsLabView, name="analytics_lab")
  path("lab/data/", AnalyticsLabDataView, name="analytics_lab_data")
  path("lab/export/", AnalyticsLabExportView, name="analytics_lab_export")
  path("bot/", BotManagementView, name="bot_management")

Incluida en enterprise_core/urls.py:
  path('panel/analytics/', include('analytics.urls', namespace='analytics'))

#### Frontend: panel/templates/panel/analytics_lab.html

Constructor aditivo de campos con limite de 5. POST de plantillas en JSON.
Modal de gestion de plantillas (labOpenManageModal / labDeleteProfileByPk).
ECharts 5 desde CDN. Tabla ordenable con fila de totales (TOTAL, S010)
para columnas sumables. Exportacion Excel via POST (incluye fila de
totales). Fullscreen por panel. Divisor arrastrable. Selector "Por
periodo" en Agrupacion (S010): sustituye Desde/Hasta por un select de
WorkPeriodGroup (periodo de ambito empresa). Unicode eliminado de
comentarios JS/CSS -- solo se conserva en contenido visible de usuario
y simbolos CSS.

#### Frontend: panel/templates/panel/analytics_costs.html (S010)

Pagina de gestion de OperatorMonthlyCost: tabla de registros (operario/
periodo/estado/coste), formulario manual con select operario -> select
periodo en cascada (OperatorMonthlyCostFormOptionsView), importador
Excel en dos fases con preview de operario+periodo por fila.

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

S052 (2026-06-24):
  1. Correccion bug p.pk -> p.id en labLoadProfiles: selector de plantillas operativo.
  2. Minimo de campos reducido a 1 en labAnalyze (antes 2).
  3. Eliminacion de spare_part del selector frontend y labFieldTypeChanged.
     Eliminacion de funcion muerta labBuildFieldsParam.
  4. Correccion critica de bundle: GET subido como template -- revertido y
     corregido con extraccion sed del archivo limpio.
  5. Responsive CSS completo para movil (<768px) y tablet (768-991px):
     layout vertical apilado, alturas fijas y ResizeObserver para ECharts.
  6. Expansion del selector de campos de 4 a 17 dimensiones: fault_subcategory,
     machine_family, machine_type, work_order_source, or_val, has_diet,
     is_on_site, has_ticket, reviewed, no_lunch_break, machine_company,
     ordinary_hours, extra_hours. Eliminado extraction_confidence y D5 (Budget).
  7. Correccion grafico de tarta: pieData desde xAxis + series[0].data con
     nombres reales en leyenda. Eliminado dataZoom del pie.
  8. Col-chooser: checkboxes sobre la tabla para activar/desactivar columnas.
  9. Subcategorias de averia traducidas al espanol en _handle_cross via
     _FAULT_SUBCAT_LABELS (antes mostraba claves internas ET_ENGINE etc).
  10. Metricas Horas ordinarias y Horas extra: calculo proporcional por jornada
      8h. Activables como columnas opcionales desde el selector.
  11. Orden de columnas en tabla respeta el orden de campos elegidos: helper
      _field_value() + ordered_dim_types sustituyen if group_by_* fijos.
  12. CRUD completo de plantillas: AnalyticsProfileUpdateView (PATCH),
      AnalyticsProfileCloneView (POST clone), modal rediseñado con
      lista+preview, botones Cargar/Renombrar/Clonar/Eliminar y formulario
      de nueva plantilla. Nuevas rutas: profiles/<pk>/update/ y /clone/.
  13. Normalizacion de 207 WorkOrderEntry.worker_name en BD:
      ANTONIO FOLTABA/FONTALBA SERON -> ANTONIO FONTALBA SERON (con tilde),
      PABLO CAÑAMERO NAVARO -> PABLO CAÑAMERO NAVARRO,
      JOSE CRUCES HEREDIA -> JOSE MANUEL CRUCES HEREDIA,
      MANUEL ALONSO -> MANUEL ALONSO PEDROSA,
      JOSE ZAFRA BALBUENA -> JOSE ANTONIO ZAFRA BALBUENA.
  14. Creacion de usuario jeronimo (SUPERVISOR, must_change_password=True)
      para acceso al Laboratorio de Analisis.

S010 (2026-07-09) -- sesion larga, PCH en cierre de S009 reabrio H20:

  Fix inicial de incidencia reportada (icono roto en sidebar):
  1. bi-flask no existe en Bootstrap Icons 1.11.3 (confirmado por
     Miguel Angel via Ctrl+F directo sobre el CSS servido por el CDN),
     por eso "Laboratorio de Analisis" no mostraba icono. Sustituido
     por bi-pie-chart-fill (confirmado presente) en _nav_items.html y
     en la cabecera de analytics_lab.html.
  2. Tras el fix de icono, nueva incidencia: al entrar a la pagina de
     costes (ver bloque A/B abajo) desaparecia media sidebar
     (Administracion, Asistencia...). Causa real: AnalyticsCostsView
     renderizaba sin pasar company_user/company/active_nav/own_presence
     en el contexto -- _nav_items.html se incluye sin 'with' en
     base.html, así que hereda el contexto que le da cada vista, y sin
     company_user todos los {% if company_user.role == ... %} de la
     sidebar evaluan a False en silencio. Corregido pasando el mismo
     contexto estandar que ya usan AnalyticsView/AnalyticsLabView.

  Bloque A) Vistas de gestion de OperatorMonthlyCost -- implementado
  dos veces en la misma sesion (ver rework mas abajo):
  3. Primera version: OperatorMonthlyCostListView/CreateView/
     DeleteView/ImportView con clave (company, worker_name, year,
     month). Importador Excel en dos fases (preview + confirm) con
     matching difuso via difflib contra WorkOrderEntry.worker_name.

  Bloque B) Template de gestion de costes -- igualmente dos versiones:
  4. Primera version: panel/templates/panel/analytics_costs.html con
     tabla + alta manual (operario/año/mes/coste) + importador Excel.
  5. Acceso sidebar (Laboratorio + Costes) abierto a SUPERVISOR y
     WORKSHOPBOSS ademas de ADMIN: AnalyticsLabView, AnalyticsLabDataView
     y AnalyticsLabExportView pasan de AdminRoleRequiredMixin a
     SupervisorAccessMixin (import AdminRoleRequiredMixin eliminado,
     quedaba huerfano). Motivado por incidencia real: Jeronimo
     (SUPERVISOR) no podia entrar al Laboratorio.

  DESVIO DE SESION (Caso A, H20 EN PROGRESO no cambia) -- pertenece al
  dominio de H10 (Paso 4-bis, tipo_tarea), documentar tambien en el
  anexo de H10 cuando se retome ese hito:
  6. Miguel Angel plantea que el historico de partes PDF (y las lineas
     digitales clasificadas entre el 13/05 y el 08/07/2026) nunca
     distinguio avería de mantenimiento/mejora/fabricacion -- todo se
     forzaba a una FaultCategory real via el prompt antiguo
     classify_fault() (sin concepto de tipo_tarea). Confirmado por
     rastreo de git: classify_task() y la bifurcacion por ticket en
     classify_fault_line se introdujeron el mismo 08/07/2026 (commit
     ead5a74); todo lo clasificado desde el 13/05/2026 (S023/S024)
     hasta esa fecha uso el prompt antiguo, incluidas 168 lineas
     digitales sin ticket (0 de 168 con ticket).
  7. Cambio de modelo: WorkOrderEntryLine gana tipo_tarea (TextChoices
     AVERIA/MEJORA/MANTENIMIENTO/FABRICACION, mirror de
     chat.BreakdownTicket.TIPO_TAREA_CHOICES) y task_category_free,
     persistidos siempre en la linea con independencia de si existe
     breakdown_ticket -- antes tipo_tarea solo existia a nivel de
     ticket, y las lineas sin ticket (historico, o cualquier bloque
     legacy) no tenian donde guardar esta clasificacion. Migracion
     0028_workorderentryline_task_category_free_and_more.
  8. classify_fault_line() (tasks.py) reescrita por completo: unifica
     ambas ramas (con/sin ticket) en una unica llamada a classify_task(),
     persiste tipo_tarea/task_category_free en la linea siempre, y
     fault_category/fault_subcategory solo si AVERIA. classify_fault()
     (prompt antiguo) deja de llamarse desde esta tarea.
  9. Bug de diseño encontrado y corregido en el prompt classify_task()
     (services.py): la regla 4 forzaba AVERIA por defecto ante
     informacion insuficiente -- esto etiquetaba sistematicamente
     descripciones cortas y vagas ("limpiar", "organizar caseta",
     "lijar") como AVERIA/OTHER en vez de MANTENIMIENTO. Corregido: el
     fallback por defecto pasa a MANTENIMIENTO, AVERIA solo si el texto
     menciona explicitamente un problema/rotura/pieza a reparar.
     Verificado en produccion con reclasificacion de 6 lineas de
     prueba tras el fix.
  10. Management command nuevo
      work_order_processor/management/commands/backfill_task_types.py:
      reclasifica via classify_task() toda WorkOrderEntryLine con
      fault_description no vacia y tipo_tarea vacio (cubre historico
      PDF + digital pre-fix), con --dry-run, --limit, --batch-size,
      reintento ante 429 de Vertex AI (60s, hasta 3 intentos) y
      try/except defensivo por fila (una fila problematica no tumba el
      resto). Bug encontrado y corregido en produccion: la primera
      version volvia a consultar la linea por pk dentro de
      _classify_with_retry, lo que provoco un WorkOrderEntryLine.
      DoesNotExist real al toparse con una fila editada/borrada en
      produccion durante la ejecucion larga (paro el proceso tras 1301
      de 1313 lineas) -- corregido pasando fault_description/
      repair_notes ya cargados en vez de re-consultar.
      Ejecutado contra produccion: 1331 lineas totales detectadas
      (110 dry-run inicial + 1313 reales tras el fix del prompt),
      procesadas sin errores tras las correcciones.

  Rework de A) y B) sobre WorkPeriod (tras conversacion de Miguel
  Angel con Jeronimo sobre el calculo de coste/hora):
  11. Decision de diseño: OperatorMonthlyCost pasa de clave (company,
      worker_name, year, month) a OneToOneField a
      ivr_config.models.WorkPeriod. company/worker_name dejan de
      guardarse redundantes -- se derivan de
      work_period.company_user. Campo monthly_cost renombrado a
      total_cost (coste total del periodo: nomina + horas extra ya
      incluidas, sin desglose). Datos de prueba (0 registros reales,
      tabla estaba vacia) sin perdida. Migracion
      0029_alter_operatormonthlycost_options_and_more.
  12. CRUD (bloque A) reescrito: nueva vista
      OperatorMonthlyCostFormOptionsView (GET operarios+periodos para
      los selectores en cascada). Create/Delete/List adaptadas a la
      nueva clave. Importador Excel: el matching difuso pasa de
      WorkOrderEntry.worker_name (texto libre) a CompanyUser reales de
      la empresa; tras resolver el operario, resuelve a que WorkPeriod
      cae la fecha de cada fila (nuevo estado 'no_period' en el
      preview cuando no hay periodo que cubra la fecha).
  13. Template (bloque B) reescrito: tabla operario/periodo/estado/
      coste, formulario manual con select operario -> select periodo
      en cascada, preview de importacion con selector de periodo por
      fila.
  14. Correccion cosmetica: OperatorMonthlyCost.__str__ duplicaba el
      nombre del operario (WorkPeriod.__str__ ya lo incluye).

  Bloque C) Dimension D6 (coste) en el Laboratorio -- implementada
  completa esta sesion (no existia codigo previo, solo diseño):
  15. Nueva metrica 'cost' (dim d20) en _handle_cross(): resuelve
      entry.worker_name -> CompanyUser real (empresa) -> WorkPeriod que
      cubre entry.work_date -> OperatorMonthlyCost.total_cost:
      coste_en_maquina = (horas_linea / horas_totales_operario_periodo)
      x total_cost_periodo. Horas totales del periodo = SUMA de
      TODAS las horas del operario en TODOS los centros de gasto del
      periodo (maquinas reales + PERSONAL/EMPRESA_ALMACEN_* internos,
      sin caso especial) -- decision explicita de Miguel Angel para
      poder comparar coste de tiempo interno vs coste de reparar una
      maquina. Lineas sin operario/periodo/coste resoluble aportan 0
      (comportamiento por defecto, sin excluir la fila).
  16. Bug real encontrado y corregido tras smoke test con datos reales:
      el coste salia siempre a 0 para todos los operarios. Causa:
      comparacion sensible a mayusculas entre entry.worker_name
      (guardado en mayusculas por el pipeline digital) y
      CompanyUser.user.get_full_name() (no necesariamente en
      mayusculas) -- normalizados ambos lados del lookup a mayusculas.
      Verificado con smoke test de 8 operarios reales con costes
      distintos: reparto proporcional correcto, coste/hora constante
      por operario en todas sus filas, centros de gasto internos
      reciben coste igual que maquinas reales.
  17. Frontend: opcion "Coste (EUR)" en ambos selectores de campo
      (estatico y dinamico), badge de resumen condicional (solo
      aparece si el resumen trae total_cost), exportacion Excel sin
      cambios (reutiliza columns/rows ya recibidos).

  Mejoras adicionales del Laboratorio (a peticion de Miguel Angel):
  18. Atajo "Por periodo" en Agrupacion: sustituye Desde/Hasta por un
      selector de WorkPeriodGroup (periodo de AMBITO EMPRESA, no
      WorkPeriod individual por operario -- WorkPeriodGroup ya existia
      en ivr_config.models con exactamente los campos necesarios,
      company/label/start_date/end_date/is_closed, no hizo falta
      migracion). Al elegir un periodo, prerellena Desde/Hasta con su
      rango; granularity se traduce a 'month' para el backend (que no
      conoce el valor UI-only 'by_period_group'). Aclaracion de Miguel
      Angel: WorkPeriod individual por operario fue un error de diseño
      -- el periodo real es el mismo para toda la empresa (norma
      general 21 de un mes al 20 del siguiente), un operario solo
      tendria un WorkPeriod propio distinto si su contrato empieza a
      mitad de un periodo ya establecido. No se ha corregido el modelo
      WorkPeriod en si esta sesion (fuera de alcance), solo se ha usado
      WorkPeriodGroup, que ya resuelve el caso de uso del selector.
  19. Fila de totales (TOTAL) para columnas sumables (Horas trabajadas,
      Intervenciones, Horas ordinarias, Horas extra, Coste EUR), tanto
      en la tabla en pantalla (se recalcula sola al ocultar/mostrar
      columnas) como en la exportacion a Excel. Verificado con Excel
      real: TOTAL de coste coincidio exactamente con el total_cost del
      unico operario cuyo periodo completo caia dentro del rango
      exportado.

  Limpieza final de datos de prueba:
  20. Borrados los 8 OperatorMonthlyCost de prueba, los 4 WorkOrder
      (y en cascada WorkOrderEntry/WorkOrderEntryLine/SparePartLine)
      de ALVAREZ_ADMIN (cuenta de pruebas de Miguel Angel Muñoz Cara).
      Confirmado que no queda ningun WorkOrderEntry ni CompanyUser de
      "Silvia" (usuaria eliminada previamente) en la base de datos.

  Incidencia de sesion no relacionada con codigo: el token de GitHub
  caduco/dejo de autenticar (401) a mitad de sesion tras varios pushes
  exitosos -- resuelto con un token nuevo entregado por Miguel Angel
  (el segundo intento de token nuevo tambien fallo, 403 "Write access
  not granted", por falta del scope Contents: Read and write; el
  tercero funciono).

---

### Hoja de Ruta para la Siguiente Sesion

#### Estado al cierre de S010 (2026-07-09)

Los pendientes A/B/C quedaron completados e implementados esta sesion
(dos veces en el caso de A/B -- primera version con clave year/month,
luego reescritos sobre WorkPeriod tras la conversacion con Jeronimo).
El Laboratorio de Analisis tiene ahora seis dimensiones completas
(D1-D6) mas el atajo "Por periodo" y la fila de totales. H20 sigue EN
PROGRESO en el router (no hubo PCH esta sesion) -- si Miguel Angel no
indica lo contrario al empezar la proxima sesion, se entiende que H20
puede darse por suficientemente maduro para plantear un PCH a otro
hito, pero esa decision es suya, no automatica.

Unico punto de diseño de H20 que sigue sin resolver (ver "NOTA DE
DISEÑO -- S010" mas abajo, punto 5): que hacer cuando un operario no
tiene WorkPeriod de coste informado para el periodo consultado.
Comportamiento actual: excluye (coste 0), sin marcar la fila como "sin
datos" de forma visualmente distinta a un coste real de 0 €. No
iniciar cambio de comportamiento sin instruccion explicita.

---

#### AVISO -- trabajo de dominio H10 realizado esta sesion (desvio, Caso A)

Durante S010, con H20 EN PROGRESO, se atendio un desvio de sesion que
pertenece en realidad al dominio de H10 (Paso 4-bis, tipo_tarea): ver
el punto "DESVIO DE SESION" completo en la seccion "Trabajo Realizado"
de este mismo anexo (bloques 6-10). Resumen para quien retome H10:

  - WorkOrderEntryLine gano tipo_tarea/task_category_free (migracion
    0028), persistidos siempre en la linea, con o sin breakdown_ticket.
  - classify_fault_line() (tasks.py) reescrita: unica llamada a
    classify_task() para todas las lineas.
  - Prompt classify_task() (services.py) corregido: fallback por
    defecto ante info insuficiente pasa de AVERIA a MANTENIMIENTO.
  - Management command backfill_task_types.py creado y ejecutado
    contra produccion (1331 lineas historicas + digitales
    reclasificadas, sin errores).

Este trabajo NO esta reflejado en el anexo de H10
(`ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md` o el que corresponda) --
solo en este documento (H20), porque el protocolo de cierre de sesion
(`nfs-enterprisebot-pcs`) solo actualiza el anexo del hito EN
PROGRESO. Cuando se retome H10, releer el bloque "DESVIO DE SESION"
de este anexo (S010) y trasladar lo relevante al anexo de H10 antes de
continuar, para no perder la trazabilidad.

---

Pendiente en H20 (sin orden obligatorio, confirmar con Miguel Angel
cual primero si decide seguir en H20 en vez de hacer PCH):

  A) [COMPLETADO EN S010] Vistas de gestion de OperatorMonthlyCost --
     ver "Arquitectura Tecnica" arriba para el listado actual de
     vistas y rutas. Clave: OneToOneField a WorkPeriod. Sin trabajo
     pendiente conocido.

  B) [COMPLETADO EN S010] Template de gestion de costes
     (analytics_costs.html) -- tabla, alta manual con cascada
     operario->periodo, importador Excel con resolucion de periodo por
     fecha. Sin trabajo pendiente conocido.

  C) [COMPLETADO EN S010] Dimension D6 (coste) en el laboratorio --
     metrica 'cost' en _handle_cross(), verificada con smoke test de
     datos reales (8 operarios, costes distintos, reparto proporcional
     correcto incluyendo centros de gasto internos). Sin trabajo
     pendiente conocido salvo el punto 5 sin resolver (ver arriba).

  D) NOTA -- Posible dimension D7 (coste de manipulacion de almacen),
     surgida durante el diseno del Hito 10 (S001-H10, no iniciado a
     fecha de esta nota). Idea de Miguel Angel: el coste real de un
     repuesto no es solo su precio de compra (o el de la maquina
     donante si es SALVAGED, ver anexo H10 seccion 3.6) sino tambien
     el tiempo de manipulacion logistica -- meter y sacar el repuesto
     del almacen, gestionar su pre-asignacion en el limbo, etc. Ese
     tiempo de almacen, repercutido proporcionalmente entre todas las
     maquinas que reciben repuestos (formula de reparto analoga a la
     de D6/OperatorMonthlyCost), daria un coste total mas preciso por
     maquina y por repuesto.
     Base de datos ya disponible para esto sin migracion adicional:
     StockMovement.created_by + StockMovement.created_at (anexo H10,
     app spare_parts) registran quien y cuando se realizo cada
     movimiento de almacen. Si en el futuro se aborda esta dimension,
     valorar si haria falta un OperatorMonthlyCost especifico para el
     rol de logistica/almacen, o si se reutiliza el existente filtrando
     por operario con StockMovement asociados.
     PENDIENTE DE DECISION DE ALCANCE -- no iniciar sin instruccion
     explicita de Miguel Angel, igual que el resto de pendientes de H20.

  E) NOTA -- error de diseño detectado en WorkPeriod (ivr_config.models,
     NO en OperatorMonthlyCost) durante S010, sin corregir esta sesion
     por estar fuera de alcance: WorkPeriod es un registro individual
     por operario con su propio start_date/end_date, cuando en la
     practica el periodo real es de ambito EMPRESA (norma general: 21
     de un mes al 20 del mes siguiente, igual para todos los
     operarios via WorkPeriodGroup) -- un operario solo deberia tener
     fechas propias distintas si su contrato empieza a mitad de un
     periodo ya establecido, y aun asi seguiria siendo "el mismo
     periodo", solo que sin datos desde el inicio del periodo hasta el
     alta del operario. Miguel Angel confirma que esta regla de
     negocio (fecha por defecto 21->20 al crear un periodo) ya existia
     documentada en algun punto anterior del proyecto, posiblemente
     perdida en alguno de los traspasos de persistencia (PythonAnywhere
     -> skills -> GitHub). Para el selector "Por periodo" del
     Laboratorio (S010) no hizo falta tocar el modelo WorkPeriod --
     WorkPeriodGroup ya cubre el caso de uso (rango de fechas de
     ambito empresa). Si en el futuro se aborda una limpieza de este
     diseño (p.ej. que WorkPeriod deje de tener start_date/end_date
     propios y siempre herede los de su WorkPeriodGroup), es un cambio
     de modelo mas amplio, con impacto en WorkPeriodLockView y el
     resto de flujo de liquidacion de partes -- no iniciar sin
     instruccion explicita y sin revisar primero todo el codigo que
     usa WorkPeriod.start_date/end_date directamente.

  ---

  NOTA DE DISEÑO -- S010 (2026-07-09), criterio corregido tras conversación
  de Miguel Ángel con Jerónimo (SUPERVISOR, contable/nóminas):

  1. Granularidad: OperatorMonthlyCost usa clave OneToOneField a
     ivr_config.models.WorkPeriod (periodo de empleo/contrato del
     CompanyUser, activo o liquidado). IMPLEMENTADO EN S010 (migracion
     0029) -- ver "Arquitectura Tecnica" arriba para el esquema actual.
  2. Contenido del coste: el importe que se introduce (manual o Excel)
     es el COSTE TOTAL del trabajador en ese periodo -- nómina completa
     MÁS horas extraordinarias ya incluidas. Un único número, sin
     desglose. IMPLEMENTADO (campo total_cost).
  3. D6 NO calcula ni muestra valor de hora ordinaria ni valor de hora
     extraordinaria por separado. El reparto es siempre sobre el coste
     total del periodo entre el total de horas trabajadas por el
     operario en ese periodo. IMPLEMENTADO.
  4. RESUELTO en conversación con Jerónimo (S010): "horas totales del
     operario en el periodo" (denominador del reparto) incluye TODAS
     las horas del operario en TODOS los centros de gasto del periodo
     -- máquinas reales Y centros de gasto internos (PERSONAL,
     EMPRESA_ALMACEN_MECANICO, EMPRESA_ALMACEN_ELEVACION,
     EMPRESA_ALMACEN_HUELVA, EMPRESA_ALMACEN_DEPENDENCIAS). Sin
     excepciones ni caso especial. Los centros de gasto internos NO se
     excluyen del resultado -- reciben su propio coste imputado igual
     que cualquier máquina real. IMPLEMENTADO y verificado con smoke
     test de datos reales.
  5. Sigue SIN RESOLVER (no se ha hablado con Jerónimo de esto todavía):
     qué hacer cuando un operario no tiene WorkPeriod de coste
     informado para el periodo en cuestión. Comportamiento actual:
     "excluir" (coste 0, sin marca visual distinta de un coste real de
     0 €) -- se mantiene como comportamiento por defecto salvo que
     Miguel Ángel diga lo contrario antes de tocarlo.
