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

La funcionalidad se construye sobre la app Django existente `delivery_note_processor`
(ya presente en el proyecto bajo `/home/MiguelAeTxio/PAIRS/`), que se evalúa como
base reutilizable o referencia de arquitectura en la fase de auditoría inicial.

---

## 2. Arquitectura Técnica

### 2.1. Flujo de Procesamiento

    Usuario sube PDF
        -> Django recibe el archivo (vista de carga)
        -> Celery task: extrae páginas del PDF como imágenes
        -> Por cada página/imagen:
            -> Gemini Vision analiza la foto del parte
            -> Se extraen campos estructurados (ver seccion 2.3)
            -> Se persiste un registro WorkOrderEntry en BD
        -> Se genera fichero Excel con openpyxl
        -> Usuario descarga el Excel desde el panel

### 2.2. App Django

Se evalúa en la sesión de inicio si la funcionalidad se implementa:

- Opción A: Extendiendo la app existente `delivery_note_processor` si su
  arquitectura es compatible con el nuevo flujo.
- Opción B: Creando una nueva app Django `work_order_processor` con
  arquitectura limpia desde cero.

La decisión se toma tras auditar `delivery_note_processor/models.py`,
`delivery_note_processor/services.py` y `delivery_note_processor/views.py`
al inicio de la sesión de implementación.

### 2.3. Campos a Extraer por Parte

Campos objetivo por parte de trabajo (sujetos a revisión con Grupo Álvarez):

| Campo            | Tipo      | Descripción                                 |
|------------------|-----------|---------------------------------------------|
| worker_name      | CharField | Nombre del operario                         |
| work_date        | DateField | Fecha del parte                             |
| start_time       | TimeField | Hora de inicio de jornada                   |
| end_time         | TimeField | Hora de fin de jornada                      |
| vehicle_ref      | CharField | Referencia o matrícula del vehículo         |
| work_description | TextField | Descripción de los trabajos realizados      |
| location         | CharField | Lugar o dirección de la intervención        |
| observations     | TextField | Observaciones adicionales del operario      |

La estructura definitiva se acordará con el cliente antes de la implementación
del modelo Django y del prompt de extracción Gemini.

### 2.4. Stack Tecnológico

- Extracción de páginas PDF: PyMuPDF (fitz) — convierte cada página del PDF
  en imagen PNG en memoria, sin escritura en disco.
- Visión artificial: google-genai (ya en requirements) — modelo gemini-2.5-flash
  con entrada de imagen base64.
- Generación Excel: openpyxl — añadir vía requirements.in si no está presente.
- Procesamiento asíncrono: Celery + Celery Beat (ya configurado en el proyecto).
- Almacenamiento de archivos: Django FileField con upload_to configurado.

### 2.5. Modelo de Datos Principal

Nuevo modelo WorkOrder en la app seleccionada (seccion 2.2):

- company          — ForeignKey -> Company (multiempresa desde el inicio).
- uploaded_by      — ForeignKey -> CompanyUser.
- source_pdf       — FileField: archivo PDF original subido.
- upload_date      — DateTimeField(auto_now_add=True).
- status           — CharField choices: PENDING / PROCESSING / DONE / ERROR.
- total_pages      — IntegerField: número de páginas detectadas en el PDF.
- processed_pages  — IntegerField: páginas procesadas correctamente.
- excel_file       — FileField(null=True): Excel generado, disponible tras DONE.
- error_log        — TextField(blank=True): detalle de errores si status=ERROR.

Nuevo modelo WorkOrderEntry (un registro por página/parte extraído):

- work_order           — ForeignKey -> WorkOrder.
- page_number          — IntegerField: número de página en el PDF original.
- worker_name          — CharField.
- work_date            — DateField(null=True).
- start_time           — TimeField(null=True).
- end_time             — TimeField(null=True).
- vehicle_ref          — CharField(blank=True).
- work_description     — TextField(blank=True).
- location             — CharField(blank=True).
- observations         — TextField(blank=True).
- raw_gemini_response  — JSONField: respuesta cruda de Gemini para auditoría.
- extraction_confidence — CharField choices: HIGH / MEDIUM / LOW / FAILED.

---

## 3. Hoja de Ruta

### Paso 1 — Auditoría de delivery_note_processor
- Leer models.py, services.py y views.py de la app existente.
- Decidir Opción A (extensión) u Opción B (app nueva).
- Estado: COMPLETADO (2026-04-22) — Decisión: Opción B (nueva app work_order_processor).
  La app delivery_note_processor pertenece a CampuStudiOnline y su arquitectura
  es incompatible (sin multiempresa, SDK legacy, ImageField en lugar de FileField PDF).

### Paso 2 — Dependencias
- Añadir PyMuPDF y openpyxl a requirements.in si no están presentes.
- Ejecutar pip-compile y pip-sync en el entorno virtual del servidor.
- Estado: COMPLETADO (2026-04-22) — PyMuPDF 1.27.2.2, openpyxl 3.1.5, redis 7.4.0 instalados.

### Paso 3 — Modelo de Datos
- Implementar WorkOrder y WorkOrderEntry en la app seleccionada.
- Generar y aplicar migración Django.
- Registrar ambos modelos en admin.py.
- Estado: COMPLETADO (2026-04-22) — App work_order_processor creada. Modelos
  implementados, migración 0001_initial aplicada, admin registrado con inline.

### Paso 4 — Servicio de Extracción Gemini
- Implementar extract_work_order_page(image_bytes) -> dict en services.py.
- Construir prompt de extracción con los campos de la seccion 2.3.
- Respuesta Gemini en JSON estructurado; parsear y mapear a WorkOrderEntry.
- Estado: COMPLETADO (2026-04-22) — services.py implementado con prompt exhaustivo
  incorporando directrices D6 (alias Larios), D7 (contexto vehículos pesados) y
  D8 (tolerancia caligráfica). Cliente Gemini Vision vía Vertex AI (gemini-2.5-flash).

### Paso 5 — Tarea Celery de Procesamiento
- Implementar process_work_order_pdf(work_order_id) en tasks.py.
- Flujo: abrir PDF -> iterar páginas -> rasterizar -> invocar servicio Gemini
  -> persistir WorkOrderEntry -> actualizar WorkOrder.status y contadores.
- Estado: COMPLETADO (2026-04-22) — tasks.py implementado con rasterización en
  memoria a 200 DPI, persistencia por update_or_create, reintentos automáticos
  Celery (max_retries=3). Worker always-on task configurado y operativo.

### Paso 6 — Generación de Excel
- Implementar generate_work_order_excel(work_order_id) en services.py.
- Usar openpyxl para construir el libro con una fila por WorkOrderEntry.
- Cabeceras en castellano. Columnas: todos los campos de seccion 2.3 más
  fecha de extracción y nivel de confianza.
- Persistir el archivo en WorkOrder.excel_file y actualizar status a DONE.
- Estado: COMPLETADO (2026-04-22) — Implementado en services.py. Excel con
  11 columnas, cabecera oscura, fila fija, wrap text en columnas largas.
  Archivo persistido en MEDIA_ROOT/work_orders/excel/.

### Paso 7 — Vista de Carga y Descarga en Panel
- Vista de carga: formulario de subida de PDF restringido a usuarios ADMIN.
- Vista de listado: tabla de WorkOrder de la empresa con estado, progreso
  y enlace de descarga del Excel cuando status=DONE.
- Entrada en sidebar del panel: "Partes de Trabajo".
- URL base: /panel/work-orders/
- Estado: COMPLETADO (2026-04-22) — WorkOrderListView y WorkOrderUploadView
  implementadas. Templates list.html y upload.html creados. Entrada en sidebar
  fijo y offcanvas. MEDIA_URL/MEDIA_ROOT configurados. Static files en
  PythonAnywhere configurados para /media/.

### Paso 8 — Validación E2E
- Subir PDF de prueba con partes reales de Grupo Álvarez.
- Verificar extracción correcta de todos los campos.
- Verificar descarga del Excel generado con datos estructurados.
- Verificar registros en BD en el admin Django.
- Estado: PARCIALMENTE COMPLETADO (2026-04-22/23) — Pipeline E2E validado con
  PDF real de 23 partes manuscritos de Alejandro García Luque (21-10 al 20-11).
  Worker Celery operativo con DjangoTask. Confianzas HIGH y MEDIUM consistentes.
  BLOQUEANTE DETECTADO: el Excel generado no cumple la especificación de la
  skill partes-trabajo. Ver Paso 9 para el rediseño completo.

### Paso 9 — Rediseño del modelo de extracción y del generador Excel
- Estado: PENDIENTE.
- Objetivo: hacer que el Excel generado cumpla al 100% la especificación de
  la skill `partes-trabajo` (skill.md en /mnt/skills/user/partes-trabajo/).

Diagnóstico técnico de la sesión 003:
  A) El modelo de extracción Gemini (prompt en services.py._EXTRACTION_PROMPT)
     extrae UN resumen por página (1 vehículo, 1 H.C., 1 H.F.). La skill exige
     extraer TODOS LOS TRAMOS de la página (hasta 4 bloques por parte), uno por
     fila en el Excel.
  B) El modelo WorkOrderEntry almacena un registro por página, no por tramo.
     Necesita nuevos campos: maquina_raw, descripcion_averia, reparacion, or_val,
     o bien rediseñarse para soportar múltiples entradas por página (JSON).
  C) generate_work_order_excel() genera 11 columnas planas. La skill define 16
     columnas con cálculos: Δ HORAS (neta), HORAS NETAS DÍA, HORAS EXTRAS,
     SALARIO EXTRAS, REVISIÓN HORARIO (código de colores), más hoja LEYENDA y
     MANIFIESTO DE INCIDENCIAS al pie.
  D) El nombre del operario debe tomarse del nombre del archivo PDF fuente
     (ya disponible en WorkOrder.source_pdf.name), no del texto manuscrito
     extraído por Gemini (que produce variantes ortográficas inconsistentes).

Secuencia de trabajo del Paso 9:
  1. Rediseñar el prompt _EXTRACTION_PROMPT en services.py para que Gemini
     devuelva un JSON con lista de entradas (hasta 4 bloques) en lugar de
     un resumen de página. Estructura JSON objetivo por página:
     {
       "fecha": "DD/MM/YYYY",
       "fecha_incierta": false,
       "operario": "NOMBRE DEL PDF",
       "entradas": [
         {
           "maquina_raw": "A-54",
           "descripcion_averia": "...",
           "reparacion": "...",
           "hc": "08:00",
           "hf": "17:30",
           "or_val": null,
           "flags": []
         }
       ]
     }
  2. Adaptar WorkOrderEntry para soportar la nueva estructura. Evaluar si
     conviene un campo JSONField `entradas` en lugar de campos planos, o
     añadir campos individuales por tramo (maquina_raw, descripcion_averia,
     reparacion, or_val) y crear un modelo WorkOrderEntryLine para los tramos.
     Decidir en sesión tras auditar el modelo actual.
  3. Actualizar process_work_order_pdf en tasks.py para persistir los tramos
     con la nueva estructura.
  4. Reescribir generate_work_order_excel en services.py implementando las
     16 columnas, fórmulas de horas extras y salario, código de colores en
     REVISIÓN HORARIO (usando openpyxl PatternFill), hoja LEYENDA y
     MANIFIESTO DE INCIDENCIAS al pie, exactamente según la skill.
  5. Aplicar directrices D1-D5 de la skill en el generador Excel:
     D1 — una incidencia de fecha por día.
     D2 — deducción de fecha por contexto calendario.
     D3 — redondeo de horas a fracciones de media hora.
     D4 — normalización de nomenclatura de maquinaria.
     D5 — incidencia JORNADA si jornada diaria < 8h.
  6. Validación E2E final con el mismo PDF de Alejandro García Luque
     (ALEJANDRO_GARCIA_LUQUE_21-10_AL_20-11.pdf) comparando el Excel
     generado contra el Excel de referencia del agente
     (GARCIA_LUQUE_21-10_AL_20-11.xlsx). Criterio de éxito: estructura
     de columnas idéntica, horas calculadas correctas, manifiesto coherente.

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-21 | —               | Creación del anexo. Inicio formal del hito. Hito declarado EN PROGRESO como siguiente sesión activa. |
| 002    | 2026-04-22 | 1, 2, 3, 4, 5, 6, 7, 8 | Implementación completa del pipeline PDF→Excel. Auditoría delivery_note_processor (Opción B). App work_order_processor creada desde cero. Modelos, migración, admin, services, tasks, vistas y templates implementados. Infraestructura Celery completa: celery.py, worker always-on task, broker Redis Cloud, cola work_orders aislada. MEDIA_URL/MEDIA_ROOT configurados. Validación E2E con PDF de prueba superada. Pendiente validación con partes reales de Grupo Álvarez. |
| 003    | 2026-04-22 | Tarea 0, Paso 8, Paso 9 (inicio) | Refactorización sidebar dual de panel: partial _nav_items.html, 29 actualizaciones de active_nav en views.py, eliminación de 26 bloques nav en 22 templates, corrección CSS offcanvas. Pipeline Celery corregido: diagnóstico transaction.on_commit bajo uWSGI, solución definitiva con DjangoTask (@app.task base=DjangoTask). Validación E2E Paso 8 con PDF real 23 páginas: worker operativo, confianzas HIGH/MEDIUM. Bloqueante detectado: Excel generado no cumple especificación skill partes-trabajo. Paso 9 registrado para siguiente sesión. |

---

## 5. Hoja de Ruta para la Siguiente Sesión

### Objetivo principal
Ejecutar el **Paso 9** completo: rediseño del modelo de extracción Gemini y del
generador Excel para que el output cumpla al 100% la especificación de la skill
`partes-trabajo`. El Excel de referencia es GARCIA_LUQUE_21-10_AL_20-11.xlsx
(generado por el agente Claude con la skill). El PDF de validación es
ALEJANDRO_GARCIA_LUQUE_21-10_AL_20-11.pdf (23 páginas, partes reales de Grupo Álvarez).

### Secuencia de trabajo

#### Subtarea 9.1 — Auditoría de archivos afectados
Solicitar al inicio de sesión:
- `work_order_processor/services.py` — contiene _EXTRACTION_PROMPT y generate_work_order_excel()
- `work_order_processor/models.py` — contiene WorkOrder y WorkOrderEntry
- `work_order_processor/tasks.py` — contiene process_work_order_pdf

#### Subtarea 9.2 — Rediseño del prompt de extracción
Reescribir _EXTRACTION_PROMPT en services.py para que Gemini devuelva un JSON
con lista de entradas (hasta 4 tramos por página) en lugar de un resumen de página.
Ver estructura JSON objetivo en el Paso 9 de la sección 3.

El nombre del operario NO debe extraerse del manuscrito. Debe tomarse del nombre
del archivo PDF fuente, que ya está disponible en WorkOrder.source_pdf.name.
Formato: el nombre del archivo tiene la forma NOMBRE_APELLIDO1_APELLIDO2_DD-MM_AL_DD-MM.pdf.
Extraer la parte del nombre con str.split('_') y reconstruir en formato
"NOMBRE APELLIDO1 APELLIDO2" en mayúsculas.

#### Subtarea 9.3 — Decisión de modelo de datos
Decidir si WorkOrderEntry soporta los nuevos campos de tramo. Opciones:
  A) Añadir campos planos (maquina_raw, descripcion_averia, reparacion, or_val)
     a WorkOrderEntry y crear un registro por tramo (no por página).
  B) Añadir un JSONField `entradas` a WorkOrderEntry que almacene la lista de
     tramos, manteniendo un registro por página.
La decisión se toma en sesión tras auditar el modelo actual. La Opción A es
más limpia y alineada con la skill; la Opción B es menos invasiva en migraciones.

#### Subtarea 9.4 — Reescritura de generate_work_order_excel()
Implementar las 16 columnas según la skill, con fórmulas, código de colores
(openpyxl PatternFill), hoja LEYENDA y MANIFIESTO DE INCIDENCIAS.
Ver especificación exacta en skill partes-trabajo v1.2.

#### Subtarea 9.5 — Validación E2E final
Subir ALEJANDRO_GARCIA_LUQUE_21-10_AL_20-11.pdf y comparar el Excel generado
contra GARCIA_LUQUE_21-10_AL_20-11.xlsx. Criterio de éxito: estructura de
columnas idéntica, horas calculadas correctas, manifiesto coherente.

### Notas técnicas para la siguiente sesión
- Worker Celery: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/start_celery_worker.sh
- Cola exclusiva: work_orders (CELERY_TASK_DEFAULT_QUEUE = 'work_orders').
- Broker: Redis Cloud — CELERY_BROKER_URL en .env.
- DjangoTask como base de process_work_order_pdf — NO revertir.
- Excel de referencia del agente: GARCIA_LUQUE_21-10_AL_20-11.xlsx
- PDF de validación: ALEJANDRO_GARCIA_LUQUE_21-10_AL_20-11.pdf (23 páginas)
- Skill de referencia: /mnt/skills/user/partes-trabajo/SKILL.md (v1.2)
- Los archivos Excel se guardan en: MEDIA_ROOT/work_orders/excel/
- La URL de descarga funciona porque /media/ está configurado en PythonAnywhere
  Static files apuntando a /home/MiguelAeTxio/PROJECTS/EnterpriseBot/media.

---

## 6. Decisiones de Diseño y Notas Técnicas

- Multiempresa desde el inicio: Toda la funcionalidad queda acotada por empresa.
  Ninguna vista expone datos de otras empresas.
- Procesamiento asíncrono obligatorio: Los PDFs pueden contener decenas de páginas.
  El procesamiento Gemini por página tiene latencia variable. La tarea Celery es
  la única opción viable — nunca procesar de forma síncrona en la petición HTTP.
- Auditoría de extracción: raw_gemini_response y extraction_confidence en
  WorkOrderEntry permiten auditar la calidad de la extracción y detectar páginas
  problemáticas (fotografías de baja calidad, partes incompletos, etc.).
- Sin nueva app si Opción A: Si delivery_note_processor es reutilizable, los
  nuevos modelos se añaden a esa app. Si no (Opción B), se crea
  work_order_processor como app Django nueva siguiendo el patrón de registro
  establecido en el proyecto.
