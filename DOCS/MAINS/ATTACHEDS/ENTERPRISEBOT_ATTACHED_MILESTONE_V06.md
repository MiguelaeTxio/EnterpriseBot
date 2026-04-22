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
- Estado: PENDIENTE

### Paso 2 — Dependencias
- Añadir PyMuPDF y openpyxl a requirements.in si no están presentes.
- Ejecutar pip-compile y pip-sync en el entorno virtual del servidor.
- Estado: PENDIENTE

### Paso 3 — Modelo de Datos
- Implementar WorkOrder y WorkOrderEntry en la app seleccionada.
- Generar y aplicar migración Django.
- Registrar ambos modelos en admin.py.
- Estado: PENDIENTE

### Paso 4 — Servicio de Extracción Gemini
- Implementar extract_work_order_page(image_bytes) -> dict en services.py.
- Construir prompt de extracción con los campos de la seccion 2.3.
- Respuesta Gemini en JSON estructurado; parsear y mapear a WorkOrderEntry.
- Estado: PENDIENTE

### Paso 5 — Tarea Celery de Procesamiento
- Implementar process_work_order_pdf(work_order_id) en tasks.py.
- Flujo: abrir PDF -> iterar páginas -> rasterizar -> invocar servicio Gemini
  -> persistir WorkOrderEntry -> actualizar WorkOrder.status y contadores.
- Estado: PENDIENTE

### Paso 6 — Generación de Excel
- Implementar generate_work_order_excel(work_order_id) en services.py.
- Usar openpyxl para construir el libro con una fila por WorkOrderEntry.
- Cabeceras en castellano. Columnas: todos los campos de seccion 2.3 más
  fecha de extracción y nivel de confianza.
- Persistir el archivo en WorkOrder.excel_file y actualizar status a DONE.
- Estado: PENDIENTE

### Paso 7 — Vista de Carga y Descarga en Panel
- Vista de carga: formulario de subida de PDF restringido a usuarios ADMIN.
- Vista de listado: tabla de WorkOrder de la empresa con estado, progreso
  y enlace de descarga del Excel cuando status=DONE.
- Entrada en sidebar del panel: "Partes de Trabajo".
- URL base: /panel/work-orders/
- Estado: PENDIENTE

### Paso 8 — Validación E2E
- Subir PDF de prueba con partes reales de Grupo Álvarez.
- Verificar extracción correcta de todos los campos.
- Verificar descarga del Excel generado con datos estructurados.
- Verificar registros en BD en el admin Django.
- Estado: PENDIENTE

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-21 | —               | Creación del anexo. Inicio formal del hito. Hito declarado EN PROGRESO como siguiente sesión activa. |

---

## 5. Hoja de Ruta para la Siguiente Sesión

### Objetivo principal
Ejecutar la auditoría de delivery_note_processor (Paso 1) y, según la decisión
tomada, implementar el modelo de datos completo (Paso 3) y las dependencias
necesarias (Paso 2).

### Secuencia de trabajo

1. Solicitar al inicio de sesión:
   - PAIRS/delivery_note_processor/models.py
   - PAIRS/delivery_note_processor/services.py
   - PAIRS/delivery_note_processor/views.py
   - requirements.in

2. Auditoría y decisión de arquitectura (Paso 1):
   - Evaluar si delivery_note_processor es extensible para el nuevo flujo.
   - Declarar explícitamente Opción A u Opción B antes de continuar.

3. Dependencias (Paso 2):
   - Verificar presencia de PyMuPDF y openpyxl en requirements.in.
   - Si faltan, añadirlos vía PMP y ejecutar pip-compile + pip-sync.

4. Modelo de datos (Paso 3):
   - Implementar WorkOrder y WorkOrderEntry según seccion 2.5 del anexo.
   - Los campos son la fuente de verdad — no inventar ni añadir campos no
     documentados sin acuerdo explícito con el usuario.
   - Migración y registro en admin.

### Notas técnicas
- El modelo es multiempresa desde el inicio: WorkOrder.company es obligatorio
  y el queryset de todas las vistas se filtra siempre por
  request.user.company_user.company.
- PyMuPDF se importa como fitz en el código Python.
- El prompt de extracción Gemini debe solicitar respuesta exclusivamente en
  JSON con las claves exactas de la seccion 2.3 para facilitar el parseo.
- La rasterización de páginas PDF se realiza en memoria (page.get_pixmap())
  sin escritura en disco temporal.

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
