# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V06.md

# Anexo de Hito V06 — Procesador de Partes de Trabajo PDF -> Excel + BBDD
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-21

---

## 1. Visión General del Hito

El Hito 6 incorpora a EnterpriseBot una funcionalidad de procesamiento documental
que permite a empresas cliente cargar archivos PDF que contienen fotografías de
partes de trabajo diarios de sus operarios. El sistema extrae automáticamente los
datos de cada parte mediante visión artificial (Gemini Vision), los persiste en
base de datos y genera un informe Excel descargable con la información estructurada.

La funcionalidad se construye sobre la app Django `work_order_processor` creada
desde cero (Opción B auditada en Paso 1), con arquitectura multiempresa desde
el inicio. La app `fleet` gestiona el catálogo de maquinaria como centros de
gasto y el libro de mantenimiento de cada activo.

---

## 2. Arquitectura Técnica

### 2.1. Flujo de Procesamiento

    Usuario sube PDF
        -> Django recibe el archivo (vista de carga)
        -> Celery task: extrae páginas del PDF como imágenes (200 DPI, en memoria)
        -> Por cada página/imagen:
            -> Gemini Vision analiza la foto del parte
            -> Se extraen hasta 4 bloques de trabajo por página (JSON multi-tramo)
            -> Se persiste WorkOrderEntry (cabecera de página) + WorkOrderEntryLine (por bloque)
            -> Se resuelve MachineAsset del catálogo fleet por código normalizado D4
        -> Se genera fichero Excel con openpyxl (17 columnas, skill partes-trabajo v1.2)
        -> Usuario descarga el Excel desde el panel

### 2.2. Apps Django involucradas

- `work_order_processor` — pipeline completo PDF->Excel, modelos WorkOrder /
  WorkOrderEntry / WorkOrderEntryLine.
- `fleet` — catálogo de maquinaria (MachineAsset), libro de mantenimiento
  (MaintenanceLog, MaintenanceItem). Centro de gasto por activo.

### 2.3. Campos extraídos por bloque (WorkOrderEntryLine)

| Campo              | Tipo            | Descripción                                      |
|--------------------|-----------------|--------------------------------------------------|
| maquina_raw        | CharField       | Código tal como lo extrae Gemini                 |
| maquina_norm       | CharField       | Normalizado según D4                             |
| machine_asset      | FK MachineAsset | Resuelto del catálogo fleet                      |
| descripcion_averia | TextField       | Descripción de la avería                         |
| reparacion         | TextField       | Descripción de la reparación                     |
| hc                 | TimeField       | Hora de comienzo (redondeada D3)                 |
| hf                 | TimeField       | Hora de finalización (redondeada D3)             |
| or_val             | CharField       | Referencia O.R.                                  |
| delta_horas        | DecimalField    | Horas netas (descontada pausa comida 13:30-15h)  |
| flags              | JSONField       | Campos con lectura incierta                      |

### 2.4. Stack Tecnológico

- Extracción de páginas PDF: PyMuPDF (fitz) — 200 DPI en memoria.
- Visión artificial: google-genai (Vertex AI) — modelo gemini-2.5-flash.
  Timeout: HttpOptions(timeout=60000) — 60 segundos en milisegundos. CRITICO.
  Endpoint global: location="global" (aiplatform.googleapis.com) para evitar
  contención regional. Retry automático 3 intentos con 60s de espera en 429.
- Generación Excel: openpyxl — 16 columnas (sin OPERARIO), skill partes-trabajo v1.2.
- Procesamiento asíncrono: Celery + DjangoTask, cola work_orders, broker Redis Cloud.
- connection.close() antes de cada persistencia para evitar MySQL wait_timeout.

### 2.5. Modelo de Datos

WorkOrder — ciclo de vida del PDF: PENDING / PROCESSING / DONE / ERROR.
WorkOrderEntry — cabecera de página: worker_name (del nombre del PDF), work_date,
  fecha_incierta, raw_gemini_response, extraction_confidence.
WorkOrderEntryLine — un registro por bloque de trabajo (hasta 4/página).
MachineAsset — centro de gasto de flota. 313 activos importados del
  LISTADO MAQUINARIA de Grupo Álvarez. FK a Company.
MaintenanceLog — intervención de mantenimiento por MachineAsset.
  FK work_entry_line a WorkOrderEntryLine activado tras migración fleet.0002.
MaintenanceItem — línea de repuesto/mano de obra por intervención.
  tipos: REPUESTO_ALMACEN / REPUESTO_TERCERO / MANO_OBRA_TERCERO.

### 2.6. Excel generado (skill partes-trabajo v1.2 + col P)

Filas 1-3: area de configuracion (titulo, precio hora extra C3 — merge A+B,
coste hora ordinaria C3 — merge A+B). Fila 4: cabeceras. Fila 5+: datos
(una fila por WorkOrderEntryLine, con sombreado alterno por dia).

16 columnas (OPERARIO eliminado — nombre en titulo):
A=FECHA, B=CODIGO/VEH., C=MARCA/MODELO, D=KM, E=HORAS VEH.,
F=DESCRIPCION AVERIA, G=REPARACION, H=H.C., I=H.F., J=O.R.,
K=Delta HORAS (neta), L=HORAS NETAS DIA, M=HORAS EXTRAS,
N=SALARIO EXTRAS, O=REVISION HORARIO, P=COSTE M.O.

Formato canónico nombre PDF: NOMBRE DD-MM-YY AL DD-MM-YY.pdf
El sufijo aleatorio de Django (_bVofaFF) es manejado por el parser de periodo.

Fila de totales: SUMPRODUCT(ISNUMBER) para cols K-N y P.
Leyenda dinamica en col O: aviso si C3=0, precio aplicado si no.
Hoja LEYENDA + MANIFIESTO DE INCIDENCIAS al pie (D1-D5 de la skill).

---

## 3. Hoja de Ruta

### Paso 1 — Auditoria de delivery_note_processor
- Estado: COMPLETADO (2026-04-22) — Decision Opcion B: nueva app work_order_processor.

### Paso 2 — Dependencias
- Estado: COMPLETADO (2026-04-22) — PyMuPDF 1.27.2.2, openpyxl 3.1.5, redis 7.4.0.

### Paso 3 — Modelo de Datos
- Estado: COMPLETADO (2026-04-22) — WorkOrder + WorkOrderEntry. Migracion 0001.

### Paso 4 — Servicio de Extraccion Gemini
- Estado: COMPLETADO (2026-04-22) — services.py inicial con prompt plano.

### Paso 5 — Tarea Celery de Procesamiento
- Estado: COMPLETADO (2026-04-22) — DjangoTask, reintentos, 200 DPI.

### Paso 6 — Generacion de Excel
- Estado: COMPLETADO (2026-04-22) — Excel 11 columnas inicial.

### Paso 7 — Vista de Carga y Descarga en Panel
- Estado: COMPLETADO (2026-04-22) — WorkOrderListView + WorkOrderUploadView.

### Paso 8 — Validacion E2E inicial
- Estado: COMPLETADO (2026-04-22/23) — Pipeline E2E validado. Bloqueante detectado:
  Excel no cumple especificacion skill partes-trabajo. Paso 9 registrado.

### Paso 9 — Rediseno del modelo de extraccion y del generador Excel
- Estado: COMPLETADO (2026-04-23 / 2026-04-27).

Trabajo completado en sesion 004:

  A) App fleet creada:
     - Modelos: MachineAsset, MaintenanceLog, MaintenanceItem.
     - 313 activos importados del LISTADO MAQUINARIA (seed_fleet_catalog.py en SWAP).
     - Admin completo con inlines. MaintenanceLog.work_entry_line FK activado
       tras migracion 0002 de work_order_processor.
     - fleet registrada en INSTALLED_APPS. Migraciones 0001 y 0002 aplicadas.

  B) Reestructuracion work_order_processor:
     - WorkOrderEntry: eliminados campos de tramo. Anadidos: fecha_incierta.
       worker_name deriva del nombre del fichero PDF.
     - Nuevo modelo WorkOrderEntryLine: campos de bloque + FK MachineAsset.
     - Migracion 0002 aplicada.

  C) services.py reescrito:
     - _EXTRACTION_PROMPT: JSON multi-tramo con lista entradas[] hasta 4 bloques/pagina.
     - Helpers: _normalise_machine_code (D4), _resolve_machine_asset,
       _compute_delta_horas (descuento pausa comida 13:30-15:00).
     - _worker_name_from_pdf_path: deriva nombre del operario del nombre del fichero.
     - generate_work_order_excel(): 17 columnas, skill v1.2, PatternFill, LEYENDA,
       MANIFIESTO DE INCIDENCIAS, columna COSTE M.O. (delta_horas x C3).
     - HttpOptions(timeout=360000): 6 minutos en milisegundos. CRITICO.

  D) tasks.py adaptado:
     - Persiste WorkOrderEntry + WorkOrderEntryLine por bloque.
     - Normalizacion D4 + resolucion MachineAsset en el pipeline.
     - connection.close() antes de cada bloque de persistencia.

  E) admin.py de work_order_processor actualizado.

  F) Senal post_save en ivr_config para generacion automatica de CallFlow de seccion:
     - ivr_config/signals.py creado. Registrado en apps.py ready().
     - Al crear Section: genera CallFlow desde plantilla canonica con maquinaria
       de fleet filtrada por section.fleet_families.
     - Al modificar Section: backup + regeneracion del system_instruction.
     - ivr_config/models.py: campo fleet_families (JSONField) anadido a Section.
     - Migracion ivr_config.0011 aplicada.

  G) Fix backup/restore de CallFlow en panel:
     - Campo backup_name anadido a CallFlow. Migracion ivr_config.0012 aplicada.
     - CallFlowUpdateView.form_valid: values() directa a BD para estado pre-guardado.
     - CallFlowRestoreView: QuerySet.update() con variables locales pre-swap.
       Check has_backup incluye backup_name.
     - Template form.html: boton Restaurar fuera del form de edicion.
       Boton guardar renombrado a "Guardar".

Trabajo completado en sesion 005 (2026-04-24):

  H) Diagnostico y resolucion del problema de worker Celery atascado:
     - Causa raiz: worker reiniciado por PythonAnywhere con WorkOrder en
       estado PROCESSING. Fix: reset a PENDING + reencole manual.
     - 429 RESOURCE_EXHAUSTED: endpoint cambiado a location="global".
     - Timeout reducido de 360s a 60s. Retry automatico 3 intentos x 60s.
     - time.sleep(15) entre paginas como guardia de rate limit.
     - Logging DEBUG activado para httpx y google.genai en settings.py.

  I) Mejoras del prompt de extraccion Gemini Vision:
     - Seccion CALIGRAFIA RAPIDA con reglas A-E: confusion letra/numero,
       alias Larios, tachones, estructura verbo+objeto, curvas degeneradas.
     - Post-procesado Python en extract_work_order_page(): separacion
       automatica de alias Larios concatenado sin espacio.

  J) Resolucion de MachineAsset mejorada:
     - _normalise_machine_code: preserva espacios en aliases de empresa.
     - _resolve_machine_asset: lookup previo Larios → FURGLAR.
     - Variantes sin guion: A-54 → busca A54 en catalogo.
     - _LARIOS_TWO_WORD_RE: cualquier variante [TIPO] [LARIOS] → FURGLAR.

  K) Inferencia de fechas por contexto calendario:
     - _extract_period_from_pdf_name: extrae periodo DD-MM-YY AL DD-MM-YY.
       Acepta espacios o guiones bajos. Maneja sufijo aleatorio Django.
     - _infer_dates_from_context: pase post-extraccion que infiere fechas
       ausentes o fuera de rango usando secuencia L-V y contexto de vecinos.
     - _is_valid: rechaza fechas con año fuera del periodo del PDF.
     - _worker_name_from_pdf_path: para en primer token que empiece por digit.

  L) Generador Excel mejorado:
     - Eliminada columna OPERARIO (nombre en titulo). 16 columnas.
     - Sombreado alterno por dia: dias impares con _CLR_DAY_SHADE (EBF3FB).
     - Fila de totales: SUMPRODUCT(ISNUMBER) evita #VALOR en col N.
     - Fórmulas corregidas: HORAS EXTRAS OR(M<=0), SALARIO EXTRAS OR(N<=0).
     - COSTE M.O.: IFERROR para celdas L vacias.
     - Titulo desde nombre PDF (no min/max fechas datos).
     - Hoja LEYENDA: escritura antes de merge para evitar sheet2.xml invalido.
     - Leyenda dinamica C2: aviso si precio no introducido.
     - Manifiesto: titulo con recuento, descripcion fusionada A→P, altura fija.

Trabajo completado en sesion 006 (2026-04-27):

  M) Validacion final Excel con PDF ALEJANDRO GARCIA LUQUE 21-10-25 AL 20-11-25:
     - Incidencia detectada: A=36 (Gemini lee guion manuscrito como signo igual).
     - Fix PMP en services.py: _normalise_machine_code añade .replace("=", "").
     - Incidencia detectada: fecha pag 1 -> 21/10/2020 en lugar de 21/10/2025.
     - Bug en _infer_dates_from_context: sin vecino anterior real, _weekdays_between
       excluia anchor_start, dejando la primera pagina sin correccion de fecha.
     - Fix PMA en tasks.py: distincion has_real_prev / has_real_nxt. Cuando no hay
       vecino real anterior y anchor_start es dia laborable anterior a nxt, se usa
       directamente como candidato unico.
     - Resto de assets y fechas correctos en todo el PDF. Validacion superada.

  N) Subtarea 9.6 — UX del panel:
     - Sidebar reestructurado en secciones: Presencia, Voz, WhatsApp, Administracion.
     - Seccion Voz: Flujos IVR, Secciones, Contactos, Numeros de telefono,
       Perfil de voz, Bloqueados.
     - Seccion WhatsApp: Plantillas, Sesiones activas.
     - Seccion Administracion: Usuarios, Conjuntos de captura, PDFs, Analitica.
     - Item "Partes de Trabajo" renombrado a "PDFs".
     - Analitica: nueva vista AnalyticsView con grafico Plotly interactivo
       (intervenciones por activo, agregado global por empresa). Template
       panel/analytics.html. Ruta /panel/analytics/. Plotly instalado via
       pip-tools (requirements.in + pip-compile + pip-sync).
     - Fix company en contexto de WorkOrderListView y WorkOrderUploadView.

  O) Subtarea 9.7 — Vista de edicion de WorkOrderEntryLine:
     - WorkOrderEditView en panel/views.py: GET (tabla agrupada por pagina/fecha)
       + POST acciones save_line (guarda linea individual, recalcula delta_horas,
       re-resuelve machine_asset) y regenerate (regenera Excel desde BD actual).
     - Ruta /panel/work-orders/<pk>/edit/ registrada como work_order_edit.
     - Template panel/templates/panel/work_orders/edit.html: tabla editable inline
       con badges de confianza, aviso fecha incierta, flags editables, boton
       Regenerar Excel. Agrupacion por pagina con cabecera coloreada.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-21 | —               | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-22 | 1-8             | Pipeline PDF->Excel inicial. App work_order_processor. E2E validado. Bloqueante Excel detectado. |
| 003    | 2026-04-22 | Tarea 0, 8, 9 inicio | Sidebar dual. DjangoTask. E2E PDF real 23 pags. Diagnostico Paso 9. |
| 004    | 2026-04-23 | Paso 9 parcial  | App fleet completa. Reestructuracion work_order_processor. Prompt multi-tramo. Excel 17 cols. Senal IVR secciones. Fix backup/restore CallFlow. Fix timeout Gemini Vision ms. E2E en curso al cierre. |
| 005    | 2026-04-24 | Paso 9 parcial  | Diagnostico worker atascado. Fix 429 endpoint global + timeout 60s + retry 3x60s. Prompt CALIGRAFIA RAPIDA. Post-procesado Larios. Resolucion MachineAsset sin guion. Inferencia fechas calendario. Excel 16 cols sin OPERARIO. Sombreado alterno dia. Fix formulas #VALOR. Titulo desde nombre PDF. |
| 006    | 2026-04-27 | Paso 9 completo, 9.6, 9.7 | Validacion Excel: fix A=36 (PMP services.py) + fix fecha pag 1 (PMA tasks.py). Subtarea 9.6: sidebar reestructurado (Voz/WhatsApp/Administracion), PDFs, Analitica con Plotly. Subtarea 9.7: WorkOrderEditView tabla editable inline + regenerar Excel. BD limpiada. |
| 007    | 2026-04-27 | Paso 9 validacion + 9.6 constructor graficos | Validacion E2E PDF superada: 5 puntos criticos confirmados. Investigacion G-8: Gemini devuelve maquina_raw=null cuando operario anota codigo en campo KM en lugar de MAQUINA. PMA services.py: regla F anadida al prompt (_EXTRACTION_PROMPT). Constructor de graficos client-side: AnalyticsView refactorizada + AnalyticsDataView (endpoint JSON) + analytics.html reescrito con Plotly.js, filtros de fecha/activo/PDF/metrica/tipo/paleta. Subtarea 9.6.1 (perfiles de grafico) registrada para proxima sesion. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Objetivo principal
Subtarea 9.6.1 (perfiles de grafico guardados) + Subtarea 9.7 (mejoras listado PDFs).

### PRIMERA ACCION — Subtarea 9.6.1: Perfiles de grafico

El constructor de graficos client-side implementado en sesion 007 es completamente
funcional. La siguiente sesion anade la capacidad de guardar y recuperar
configuraciones de grafico nombradas por el usuario.

#### Modelo AnalyticsProfile

Nuevo modelo en panel/models.py (crear si no existe como neonato puro):

    class AnalyticsProfile(models.Model):
        company_user = models.ForeignKey(
            CompanyUser,
            on_delete=models.CASCADE,
            related_name="analytics_profiles",
        )
        nombre = models.CharField(max_length=100)
        config = models.JSONField()
        creado_en = models.DateTimeField(auto_now_add=True)
        actualizado_en = models.DateTimeField(auto_now=True)

        class Meta:
            unique_together = [("company_user", "nombre")]
            ordering = ["nombre"]

El JSONField config almacena el estado completo de los controles del constructor:
    {
      "metric":      "interventions" | "hours" | "weekday" | "top10",
      "chart_type":  "bar_v" | "bar_h" | "line" | "area",
      "palette":     "corporate" | "blues" | "viridis" | "reds" | "greens" | "plasma",
      "date_from":   "YYYY-MM-DD" | null,
      "date_to":     "YYYY-MM-DD" | null,
      "assets":      ["A-54", "B-42"] | null,  (null = todos)
      "work_orders": [18] | null               (null = todos)
    }

#### Migracion necesaria
- Crear panel/migrations/ si no existe (app panel actualmente sin modelos propios).
- Migrar: python -m dotenv run python manage.py makemigrations panel
- Aplicar: python -m dotenv run python manage.py migrate

#### Endpoints necesarios
- GET  /panel/analytics/profiles/       → lista perfiles del CompanyUser (JSON)
- POST /panel/analytics/profiles/       → crear o actualizar perfil (JSON body: {nombre, config})
- DELETE /panel/analytics/profiles/<pk>/ → eliminar perfil

Nuevas vistas: AnalyticsProfileListCreateView, AnalyticsProfileDeleteView.
Registrar en panel/urls.py.

#### Modificaciones en analytics.html
En el panel de filtros, anadir por encima del separador hr:
  - Selector "Mis perfiles" (select desplegable) — se puebla con GET /profiles/.
  - Boton "Guardar perfil" — abre un input inline para introducir el nombre
    y hace POST /profiles/ con el estado actual de los controles.
  - Boton "Eliminar perfil" (icono papelera) — activo solo si hay perfil seleccionado.

Al seleccionar un perfil del desplegable, el JS restaura todos los controles
con los valores del campo config y llama a renderChart() automaticamente.

### SEGUNDA ACCION — Subtarea 9.7: Mejoras listado PDFs (list.html)

El list.html actual muestra tabla simple. Mejoras a implementar en una sola sesion:
  A) Mostrar nombre del PDF parseado (sin sufijo aleatorio Django) en lugar de pk.
  B) Anadir enlace directo "Editar" por WorkOrder → /panel/work-orders/{pk}/edit/.
  C) Desplegable de acciones por fila: Editar, Descargar Excel, Borrar.
  D) Boton "Ver incidencias" que muestre el manifiesto del Excel en modal o panel.
  E) Indicador visual de estado (PENDING / PROCESSING / DONE / ERROR) con badges.

### Stack tecnico vigente al cierre de sesion 007

- work_order_processor/services.py:
    _normalise_machine_code: .replace("=", "") activo.
    _EXTRACTION_PROMPT: regla F anadida — codigo de maquina en campo KM.
- work_order_processor/tasks.py:
    _infer_dates_from_context con has_real_prev / has_real_nxt.
    anchor_start usado directamente como candidato cuando no hay vecino anterior
    real y es dia laborable anterior a nxt.
- HttpOptions(timeout=60000) — 60 segundos en MILISEGUNDOS. CRITICO.
- Endpoint global: location="global". Retry automatico 3 intentos x 60s en 429.
- time.sleep(15) entre paginas como guardia de rate limit.
- Nombre canonico PDF: NOMBRE DD-MM-YY AL DD-MM-YY.pdf (año 2 digitos).

### Estado de migraciones al cierre de sesion 007

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |
| panel                  | (sin migraciones propias — pendiente crear en 9.6.1)  |

### Archivos modificados en sesion 007 (resumen)

work_order_processor/services.py — PMA: regla F en _EXTRACTION_PROMPT
  (codigo de maquina en campo KM cuando MAQUINA esta vacio).
panel/views.py — PMA: AnalyticsView refactorizada (template shell sin server-side
  Plotly) + nueva AnalyticsDataView (endpoint JSON con lineas, work_orders, assets).
panel/urls.py — PMA: ruta analytics/data/ registrada (AnalyticsDataView).
panel/templates/panel/analytics.html — PEA: reescritura completa con constructor
  de graficos client-side (Plotly.js): filtros fecha/activo/PDF/metrica/tipo/paleta,
  resumen dinamico, titulo/subtitulo automaticos, paletas configurables.
