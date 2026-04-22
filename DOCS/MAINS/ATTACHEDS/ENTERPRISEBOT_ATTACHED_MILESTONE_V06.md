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
- Estado: PARCIALMENTE COMPLETADO (2026-04-22) — Pipeline E2E validado con
  PDF de listado de maquinaria (resultado FAILED esperado por ser documento
  tabular impreso, no parte manuscrito). Pendiente validación con partes
  reales manuscritos de Grupo Álvarez.

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-21 | —               | Creación del anexo. Inicio formal del hito. Hito declarado EN PROGRESO como siguiente sesión activa. |
| 002    | 2026-04-22 | 1, 2, 3, 4, 5, 6, 7, 8 | Implementación completa del pipeline PDF→Excel. Auditoría delivery_note_processor (Opción B). App work_order_processor creada desde cero. Modelos, migración, admin, services, tasks, vistas y templates implementados. Infraestructura Celery completa: celery.py, worker always-on task, broker Redis Cloud, cola work_orders aislada. MEDIA_URL/MEDIA_ROOT configurados. Validación E2E con PDF de prueba superada. Pendiente validación con partes reales de Grupo Álvarez. |

---

## 5. Hoja de Ruta para la Siguiente Sesión

### Objetivo principal
Dos objetivos en paralelo: (A) refactorización del sidebar dual de base.html
para eliminar la deuda técnica estructural del panel, y (B) validación E2E
definitiva del Hito 6 con partes de trabajo manuscritos reales de Grupo Álvarez.

### Secuencia de trabajo

#### Tarea 0 — Refactorización sidebar dual (deuda técnica)
Unificar los dos bloques de navegación duplicados de base.html (sidebar fijo
y offcanvas) en un único partial template `_nav_items.html` usando la variable
de contexto `active_nav` en lugar de bloques Django `{% block nav_X %}`.

Archivos afectados:
- `panel/templates/panel/base.html` — PMA: extraer nav a _nav_items.html,
  sustituir ambos bloques por `{% include "panel/_nav_items.html" %}`.
- `panel/templates/panel/_nav_items.html` — PEA: partial con lógica
  `{% if active_nav == "X" %}active{% endif %}` para cada entrada.
- `panel/views.py` — PMA: añadir `"active_nav": "X"` al contexto de
  cada vista. Mapa completo de valores:
    - dashboard → "dashboard"
    - presence/status → "presence"
    - users/list, form, create → "users"
    - sections/list, form → "sections"
    - contacts/list, form → "contacts"
    - callflows/list, form → "callflows"
    - phonenumbers/list → "phonenumbers"
    - voiceprofile/detail → "voiceprofile"
    - blockedcallers/list, form, confirm_delete → "blockedcallers"
    - datacapturesets/list, form → "datacapturesets"
    - work_orders/list, upload → "work_orders"
    - whatsapp/template_list → "whatsapp_templates"
    - whatsapp/active_session_list → "whatsapp_sessions"
- Todos los templates hijo — eliminar líneas `{% block nav_X %}active{% endblock %}`.

#### Tarea 1 — Validación E2E con partes reales (Paso 8 definitivo)
Miguel Ángel sube un PDF real con partes de trabajo manuscritos de Grupo Álvarez.

1. Subir el PDF desde /panel/work-orders/upload/.
2. Observar logs del worker Celery para verificar que Gemini Vision devuelve
   confianza HIGH o MEDIUM en los campos principales.
3. Descargar el Excel generado y verificar:
   - worker_name extraído correctamente.
   - work_date en formato correcto (YYYY-MM-DD → mostrado DD/MM/YYYY).
   - start_time y end_time redondeados a media hora según directriz D3.
   - vehicle_ref normalizado según directriz D4.
   - work_description e observations en contexto de vehículos pesados (D7).
4. Si la extracción es deficiente, afinar el prompt en services.py._EXTRACTION_PROMPT.

### Notas técnicas para la siguiente sesión
- El worker Celery arranca con: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/start_celery_worker.sh
- Cola exclusiva: work_orders (CELERY_TASK_DEFAULT_QUEUE = 'work_orders').
- Broker: Redis Cloud — URL en .env como CELERY_BROKER_URL.
- Los archivos Excel se guardan en: MEDIA_ROOT/work_orders/excel/
- La URL de descarga funciona porque /media/ está configurado en PythonAnywhere
  Static files apuntando a /home/MiguelAeTxio/PROJECTS/EnterpriseBot/media.
- El prompt de extracción está en: work_order_processor/services.py → _EXTRACTION_PROMPT.
- Las directrices D6 (Larios), D7 (vehículos pesados) y D8 (tolerancia caligráfica)
  están incorporadas en el prompt y en la skill partes-trabajo.

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
