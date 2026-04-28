# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md

# Anexo de Hito V08 — Mejoras Procesador PDF->Excel + HTMX
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-28

---

## 1. Vision General del Hito

El Hito 8 agrupa las mejoras postcierre del Hito 6 sobre el procesador de
partes de trabajo PDF->Excel, mas la implantacion quirurgica de HTMX en los
dos puntos de mayor friccion del panel: la lista de PDFs y el editor de
entradas inline.

El hito se estructura en seis bloques de trabajo independientes aunque el
Bloque A (HTMX base) debe completarse antes que el Bloque B (editor HTMX)
porque el guardado automatico por campo depende de los endpoints del Bloque A.

---

## 2. Arquitectura Tecnica

### 2.1. Bloque A — HTMX: polling de estado en lista de PDFs

La lista de PDFs (panel/work_orders/list.html) muestra el estado de cada
WorkOrder (PENDING / PROCESSING / DONE / ERROR) y su barra de progreso.
Actualmente el usuario debe recargar la pagina manualmente para ver el avance
de la extraccion Gemini.

Con HTMX se anade polling automatico sobre cada fila cuyo estado sea
PENDING o PROCESSING:

- Atributo hx-get="/panel/work-orders/{pk}/status/" sobre las celdas de
  estado y progreso agrupadas en un contenedor.
- hx-trigger="every 4s" — polling cada 4 segundos.
- hx-target apunta al propio contenedor (hx-swap="outerHTML").
- El endpoint /panel/work-orders/{pk}/status/ devuelve unicamente el
  fragmento HTML del contenedor (badge + barra de progreso).
- Cuando el estado alcanza DONE o ERROR el fragmento devuelto no incluye
  atributos HTMX y el polling se detiene automaticamente.

Nueva vista: WorkOrderStatusFragmentView en panel/views.py.
Nuevo template parcial: panel/work_orders/_status_fragment.html.
Nueva ruta: path("work-orders/<int:pk>/status/", ...) en panel/urls.py.

HTMX se carga desde CDN en base.html. VERIFICAR integridad SHA384 en
https://unpkg.com/htmx.org@1.9.12 antes de escribir el tag (Directriz 4.4).

### 2.2. Bloque B — HTMX: guardado automatico por campo en editor

El editor (panel/work_orders/edit.html) tiene actualmente un boton Guardar
por cada linea que hace POST completo y provoca scroll al top de la pagina.

Con HTMX se elimina el boton de guardado por linea y se sustituye por
guardado automatico al cambiar de campo (hx-trigger="change"):

- Cada input y textarea de la fila recibe:
  - hx-post="/panel/work-orders/{wo_pk}/lines/{line_pk}/save/"
  - hx-trigger="change"
  - hx-target apunta a la fila <tr> completa con hx-swap="outerHTML"
  - hx-include referencia todos los campos de la misma fila via selector CSS
- El endpoint devuelve la fila <tr> completa actualizada (delta_horas
  recalculado, asset resuelto, badges de flags actualizados).
- Sin scroll al top. La posicion del viewport se mantiene intacta.
- Indicador visual: la fila parpadea brevemente en verde al completarse
  el guardado (hx-on::after-request).

Nueva vista: WorkOrderLineSaveView en panel/views.py.
Nuevo template parcial: panel/work_orders/_line_row.html.
Nueva ruta: path("work-orders/<int:wo_pk>/lines/<int:line_pk>/save/", ...).

### 2.3. Bloque C — Editor: mejoras de interaccion

Sobre el editor mejorado con HTMX del Bloque B se anaden:

C1 — Insertar entrada entre otras dos existentes:
- Boton "+" entre filas consecutivas de un mismo grupo (pagina).
- POST a /panel/work-orders/{wo_pk}/lines/insert/ con parametros
  after_line_pk y entry_pk.
- Crea nueva WorkOrderEntryLine vacia con line_number reordenado.
- Devuelve la fila nueva como fragmento HTMX para insercion inline.

C2 — Drag & drop para reordenar entradas:
- Libreria SortableJS (CDN) sobre el <tbody> de cada grupo.
- Al soltar, POST a /panel/work-orders/{wo_pk}/lines/reorder/ con
  el array de line_pk en el nuevo orden.
- El servidor actualiza los line_number de todas las lineas del grupo.
- Sin recarga de pagina.

C3 — Restaurar entrada individual:
- Boton Restaurar por fila (icono bi-arrow-counterclockwise).
- POST a /panel/work-orders/{wo_pk}/lines/{line_pk}/restore/ que
  re-ejecuta la extraccion Gemini solo para esa pagina y repuebla
  las lineas del grupo desde raw_gemini_response almacenado.
- Devuelve el grupo completo como fragmento HTMX.

C4 — Avisos visuales de incidencias:
- Filas con flags no vacios reciben clase CSS row-has-flags →
  fondo amarillo claro (#fffbe6).
- Campos con su nombre en flags reciben clase field-flagged →
  borde naranja (#fd7e14).
- Al editar un campo flaggeado y guardar via HTMX, si el flag
  desaparece del servidor la clase field-flagged se elimina del
  fragmento devuelto y el color se normaliza automaticamente.

### 2.4. Bloque D — Pipeline: correcciones

D1 — Columna mano de obra vacia:
Diagnostico pendiente de confirmar en sesion. La columna P (COSTE M.O.)
del Excel aparece vacia. Causa probable: cambio de nombre de campo o
eliminacion de columna en la reestructuracion del Paso 9 del H6.
Archivos a auditar: work_order_processor/tasks.py (generate_work_order_excel).

D2 — Parser: confusiones de caracteres OCR:
Ampliar _normalise_machine_code() en work_order_processor/services.py:
- O -> 0
- L -> 1
- t -> 7
Sustituciones ya activas a confirmar: S->5, Z->2, G->6.
Verificar que no hay colisiones con codigos reales del catalogo fleet
antes de aplicar cada regla (consultar MachineAsset con codigo__regex).

### 2.5. Bloque E — Upload: deteccion de duplicado

Al subir un PDF en WorkOrderUploadView, antes de crear el WorkOrder,
comparar el nombre del operario y el periodo extraidos del nombre del PDF
con los WorkOrders existentes de la misma empresa.

Logica de deteccion:
- Parsear el nombre del PDF entrante con el parser de periodo existente
  en services.py para extraer worker_name y (date_from, date_to).
- Consultar WorkOrder.objects.filter(company=company) buscando
  coincidencia de operario + solapamiento de periodo.
- Si se detecta duplicado: no crear el WorkOrder todavia. Devolver al
  template de upload la info del duplicado detectado.
- El template muestra modal Bootstrap de advertencia con:
  - Nombre del PDF existente y fecha de carga original.
  - Aviso de que los datos actuales seran sobrescritos.
  - Aviso de que la accion no se puede deshacer.
  - Aviso de que para recuperar los datos hay que volver a subir el PDF
    o editar manualmente las entradas.
  - Botones: Continuar y sobrescribir / Cancelar.
- Si el usuario confirma: se elimina el WorkOrder duplicado (cascade
  elimina WorkOrderEntry y WorkOrderEntryLine) y se crea el nuevo.

### 2.6. Bloque F — Lista PDFs: concatenacion de Excels

Checkboxes por fila (solo DONE) en list.html. Boton Descargar seleccion
activo cuando hay al menos un checkbox marcado.

POST a /panel/work-orders/export/ con lista de pk seleccionados.
Vista WorkOrderExportView en panel/views.py:
- Carga cada WorkOrder en orden de pk.
- Por cada uno llama a generate_work_order_excel() en modo buffer
  (sin escribir a disco) y concatena las hojas en un unico Workbook
  openpyxl manteniendo el membrete individual de cada operario.
- Devuelve HttpResponse con Content-Type xlsx y nombre de fichero
  EXPORTACION_DD-MM-YY.xlsx.

---

## 3. Hoja de Ruta

### Paso 1 — HTMX en base.html + WorkOrderStatusFragmentView (Bloque A)
- Anadir CDN HTMX a panel/templates/panel/base.html.
- Crear WorkOrderStatusFragmentView en panel/views.py.
- Crear template parcial panel/work_orders/_status_fragment.html.
- Registrar ruta work-orders/<int:pk>/status/ en panel/urls.py.
- PMA list.html: sustituir celdas estado+progreso por include del parcial.
- Estado: PENDIENTE.

### Paso 2 — HTMX guardado automatico por campo en editor (Bloque B)
- Crear WorkOrderLineSaveView en panel/views.py.
- Crear template parcial panel/work_orders/_line_row.html.
- Registrar ruta work-orders/<int:wo_pk>/lines/<int:line_pk>/save/.
- PMA edit.html: eliminar boton Guardar por fila, anadir atributos HTMX.
- Estado: PENDIENTE.

### Paso 3 — Editor: insertar + drag & drop + restaurar + avisos (Bloque C)
- C1: WorkOrderLineInsertView + ruta insert/ + fragmento HTMX.
- C2: SortableJS CDN + WorkOrderLineReorderView + ruta reorder/.
- C3: WorkOrderLineRestoreView + ruta restore/ + fragmento grupo HTMX.
- C4: clases CSS row-has-flags / field-flagged en _line_row.html y panel.css.
- Estado: PENDIENTE.

### Paso 4 — Columna mano de obra + parser OCR (Bloque D)
- D1: auditar generate_work_order_excel() en tasks.py.
- D2: ampliar _normalise_machine_code() en services.py.
- Estado: PENDIENTE.

### Paso 5 — Deteccion de duplicado en upload (Bloque E)
- Extender WorkOrderUploadView con logica de deteccion pre-creacion.
- PMA upload.html: modal de advertencia de duplicado.
- Estado: PENDIENTE.

### Paso 6 — Concatenacion de Excels (Bloque F)
- Crear WorkOrderExportView en panel/views.py.
- Registrar ruta work-orders/export/ en panel/urls.py.
- PMA list.html: checkboxes por fila DONE + boton Descargar seleccion.
- Estado: PENDIENTE.

### Paso 7 — Validacion E2E
- Validar polling HTMX con PDF real en extraccion.
- Validar guardado automatico en editor sin scroll.
- Validar insercion, reordenado y restauracion de lineas.
- Validar correccion columna mano de obra en Excel descargado.
- Validar deteccion duplicado + modal + sobrescritura.
- Validar concatenacion de Excels multi-operario.
- Estado: PENDIENTE.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | —               | Creacion del anexo. Inicio formal del hito. H7 pausado (Pasos 1 y 2 completados). |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Objetivo principal
Paso 1 — HTMX en base.html + WorkOrderStatusFragmentView (Bloque A).

### PRIMERA ACCION — Verificar integridad HTMX y anadir CDN a base.html

Antes de tocar base.html, verificar la integridad SHA384 del CDN de HTMX
1.9.12 en https://unpkg.com/htmx.org@1.9.12 (Directriz 4.4 obligatoria).

Anadir el script CDN justo antes del cierre </body> en base.html,
despues del script de Bootstrap 5.3:

    <script src="https://unpkg.com/htmx.org@1.9.12"
            integrity="sha384-VERIFICAR_ANTES_DE_ESCRIBIR"
            crossorigin="anonymous"></script>

El valor de integrity debe obtenerse de la documentacion oficial o del
CDN en el momento de la sesion. NUNCA copiar un hash de memoria.

### SEGUNDA ACCION — WorkOrderStatusFragmentView en panel/views.py

Nueva vista sincrona que devuelve unicamente el fragmento HTML de estado
y progreso de un WorkOrder. Especificacion exacta:

    class WorkOrderStatusFragmentView(AdminRoleRequiredMixin, View):
        def get(self, request, pk):
            wo = get_object_or_404(
                WorkOrder,
                pk=pk,
                company=request.user.company_user.company,
            )
            return render(
                request,
                "panel/work_orders/_status_fragment.html",
                {"wo": wo},
            )

### TERCERA ACCION — Template parcial _status_fragment.html (Neonato Puro)

El template renderiza el badge de estado y la barra de progreso.
Si el estado es PENDING o PROCESSING incluye atributos HTMX para
polling cada 4 segundos. Si el estado es DONE o ERROR no incluye
atributos HTMX y el polling se detiene automaticamente.

Estructura del fragmento (contenedor unico que se reemplaza):

    <div id="wo-status-{{ wo.pk }}"
         {% if wo.status == 'PENDING' or wo.status == 'PROCESSING' %}
         hx-get="{% url 'panel:work_order_status_fragment' pk=wo.pk %}"
         hx-trigger="every 4s"
         hx-target="this"
         hx-swap="outerHTML"
         {% endif %}>
        [badge de estado]
        [barra de progreso]
    </div>

### CUARTA ACCION — PMA list.html

Sustituir el bloque de celdas de estado y progreso dentro del
{% for wo in work_orders %} por:

    {% include "panel/work_orders/_status_fragment.html" with wo=wo %}

Esto unifica el renderizado inicial y el fragmento HTMX en un unico template.
Las dos celdas <td> de estado y progreso se colapsan en una sola <td> que
contiene el include del parcial.

### QUINTA ACCION — Registrar ruta en panel/urls.py

    path("work-orders/<int:pk>/status/",
         WorkOrderStatusFragmentView.as_view(),
         name="work_order_status_fragment"),

Registrar en el bloque de WorkOrder management, despues de la ruta
work_order_edit existente.

### Estado de migraciones al inicio del hito

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave al inicio del hito

- panel/templates/panel/base.html — anadir CDN HTMX (Paso 1).
- panel/views.py — WorkOrderStatusFragmentView (Paso 1), WorkOrderLineSaveView (Paso 2).
- panel/urls.py — nuevas rutas HTMX (Pasos 1-3).
- panel/templates/panel/work_orders/list.html — polling HTMX (Paso 1).
- panel/templates/panel/work_orders/edit.html — guardado automatico (Paso 2).
- panel/templates/panel/work_orders/_status_fragment.html — Neonato Puro (Paso 1).
- panel/templates/panel/work_orders/_line_row.html — Neonato Puro (Paso 2).
- work_order_processor/services.py — parser OCR (Paso 4).
- work_order_processor/tasks.py — columna mano de obra (Paso 4).
