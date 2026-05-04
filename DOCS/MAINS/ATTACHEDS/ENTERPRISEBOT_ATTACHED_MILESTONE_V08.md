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

El hito se estructura en nueve bloques de trabajo (A-I). Los bloques A-F
quedaron implementados en la sesion 002. Los bloques G, H y parte de sus
correcciones E2E se completaron en la sesion 003. El bloque I es el objetivo
de la sesion 004.

---

## 2. Arquitectura Tecnica

### 2.1. Bloque A — HTMX: polling de estado en lista de PDFs (COMPLETADO)

La lista de PDFs muestra el estado de cada WorkOrder mediante polling HTMX
automatico cada 4 segundos en filas PENDING o PROCESSING. El polling se
detiene automaticamente al alcanzar DONE o ERROR.

- WorkOrderStatusFragmentView en panel/views.py.
- Template parcial panel/work_orders/_status_fragment.html.
- Ruta work-orders/<int:pk>/status/ en panel/urls.py.
- CDN HTMX 1.9.12 con SHA384 verificado en base.html.
- Meta tag CSRF + handler htmx:configRequest en base.html.

### 2.2. Bloque B — HTMX: guardado automatico por campo en editor (COMPLETADO)

El editor de entradas inline guarda cada campo automaticamente al cambiar
(hx-trigger="change") sin recarga de pagina. La fila <tr> se reemplaza con
el fragmento devuelto por el servidor (outerHTML swap).

- WorkOrderLineSaveView en panel/views.py.
- Template parcial panel/work_orders/_line_row.html.
- Ruta work-orders/<wo_pk>/lines/<line_pk>/save/ en panel/urls.py.

### 2.3. Bloque C — Editor: mejoras de interaccion (COMPLETADO)

C1 — Insertar linea vacia entre dos existentes (boton + por fila).
C2 — Drag & drop para reordenar entradas (SortableJS 1.15.2).
C3 — Restaurar linea individual desde raw_gemini_response (por linea,
     no por grupo).
C4 — Avisos visuales de incidencias: row-has-flags (fondo amarillo),
     field-flagged (borde naranja).

### 2.4. Bloque D — Pipeline: correcciones (COMPLETADO)

D1 — Formula COSTE M.O. corregida: $B$3 -> $C$3=0 en generate_work_order_excel().
D2 — _normalise_machine_code() ampliada con _OCR_DIGIT_MAP aplicado
     solo al bloque numerico: O->0, L->1, T->7, S->5, Z->2, G->6.

### 2.5. Bloque E — Upload: deteccion de duplicado (COMPLETADO con fix sesion 003)

WorkOrderUploadView.post() detecta duplicados consultando WorkOrderEntry
directamente en BD por worker_name + solapamiento de work_date. Esta
estrategia es robusta independientemente del formato del nombre del PDF
(ano 4 vs 2 digitos, espacios vs guiones bajos) y funciona aunque
source_pdf haya sido eliminado del WorkOrder existente.

Fix sesion 003: la implementacion original basada en nombre de fichero
fue reemplazada por consulta directa a WorkOrderEntry. El modal Bootstrap
de advertencia se inicializa mediante polling de disponibilidad de Bootstrap
JS (50ms, maximo 3s) para evitar "bootstrap is not defined".

### 2.6. Bloque F — Lista PDFs: exportacion de Excels (COMPLETADO)

Checkboxes por fila DONE + boton Descargar seleccion en list.html.
WorkOrderExportView soporta dos modos (export_mode):
- single_sheet: hoja plana con todas las entradas ordenadas por operario
  y fecha, con fila separadora azul oscuro por operario.
- multi_sheet: una hoja por operario con su membrete individual.
Modal de seleccion de modo antes del POST si hay multiples operarios.
JS detecta operarios unicos y salta el modal enviando single_sheet directamente.

### 2.7. Bloque G — Campo reviewed + rol SUPERVISOR (COMPLETADO sesion 003)

Nuevo campo reviewed en WorkOrder:
- reviewed    = BooleanField(default=False, db_index=True)
- reviewed_by = ForeignKey(CompanyUser, null=True, blank=True, SET_NULL)
- reviewed_at = DateTimeField(null=True, blank=True)
Migracion aplicada: work_order_processor 0003.

Nuevo rol SUPERVISOR en CompanyUser.Role:
- ROLE_SUPERVISOR = "SUPERVISOR"
Migracion aplicada: ivr_config 0013.

SupervisorAccessMixin en panel/mixins.py:
- Permite acceso a ADMIN y SUPERVISOR.
- Redirige a dashboard con mensaje si rol insuficiente.

WorkOrderMarkReviewedView:
- POST /panel/work-orders/<pk>/review/
- Alterna reviewed True/False con reviewed_by y reviewed_at.
- Devuelve _review_badge_fragment.html para HTMX swap.

Permisos aplicados:
- WorkOrderUploadView: SupervisorAccessMixin.
- WorkOrderListView: SupervisorAccessMixin.
- WorkOrderExportView: SupervisorAccessMixin.
- WorkOrderEditView: AdminRoleRequiredMixin (sin cambio).
- WorkOrderDeleteView: AdminRoleRequiredMixin (sin cambio).
- WorkOrderStatusFragmentView: AdminRoleRequiredMixin (sin cambio).

### 2.8. Bloque H — Pestanas en list.html + rediseno Bloque F (COMPLETADO sesion 003)

Cuatro pestanas Bootstrap en list.html:
  1. "En cola" — WorkOrders PENDING o PROCESSING. Polling HTMX activo.
  2. "Error" — WorkOrders ERROR con boton ver log y boton borrar.
  3. "Pendiente revision" — WorkOrders DONE con reviewed=False.
  4. "Revisados" — WorkOrders DONE con reviewed=True.

Pestana activa por defecto: "Pendiente revision" si wo_pending > 0,
si no "En cola".

Boton "Descargar seleccion" visible solo en pestanas 3 y 4.
Neonatos creados: _review_badge_fragment.html, _queue_actions.html.

WorkOrderListView rediseniada con cuatro querysets:
  wo_queue, wo_error, wo_pending, wo_reviewed.

### 2.9. Bloque I — Hash SHA-256 para deteccion de duplicado exacto (COMPLETADO sesion 004)

Nuevo campo source_pdf_hash en WorkOrder:
  source_pdf_hash = models.CharField(max_length=64, blank=True, db_index=True)
Migracion aplicada: work_order_processor 0004_workorder_source_pdf_hash.

Flujo de deteccion en WorkOrderUploadView.post() — DOS NIVELES:
  NIVEL 1 — Hash exacto:
    SHA-256 del fichero entrante calculado en memoria antes de guardarlo.
    Se busca WorkOrder con mismo company + source_pdf_hash (excluye hash vacio).
    Si match -> duplicate_reason = "exact" -> modal con mensaje diferenciado.
  NIVEL 2 — Operario + periodo (solo si Nivel 1 no coincide):
    Se extrae worker_name del nombre del fichero.
    Se extrae periodo (date_from, date_to) del nombre del fichero si es posible.
    Se consulta WorkOrderEntry por empresa + worker_name + work_date solapado.
    Si match -> duplicate_reason = "content" -> modal con mensaje diferenciado.
  Si nada -> crear WorkOrder con source_pdf_hash = incoming_hash y encolar.

upload.html actualizado con bloque condicional segun duplicate_reason:
  "exact"   -> "Se ha detectado que el fichero PDF es identico al parte #X."
  "content" -> "Ya existen datos del operario X para este periodo en el parte #X."

Nuevo comando de gestion backfill_pdf_hashes:
  Ruta: work_order_processor/management/commands/backfill_pdf_hashes.py
  Directorio management/commands/ creado (no existia en work_order_processor).
  FASE 1 (siempre): itera WorkOrder con source_pdf_hash vacio, calcula SHA-256
    del fichero fisico, lo persiste. Informe: procesados / sin fichero / omitidos.
  FASE 2 (--purge-duplicates, opt-in, IRREVERSIBLE): identifica grupos de
    WorkOrders de la misma empresa con el mismo hash, conserva el pk mas alto
    (mas reciente) y elimina del disco el PDF fisico de los duplicados antiguos,
    vaciando su campo source_pdf. El registro WorkOrder se conserva intacto.
  Backfill ejecutado en sesion 004: 11 registros procesados correctamente.
    Duplicados exactos detectados: WorkOrders #26/#27 (mismo hash) y #28/#29.

Fix adicional sesion 004 — tasks.py guard WorkOrder eliminado en vuelo:
  Al confirmar sobrescritura de duplicado, duplicate_wo.delete() elimina el
  WorkOrder de BD mientras la tarea Celery del duplicado puede estar en vuelo.
  El bloque except Exception de process_work_order_pdf ahora verifica con
  WorkOrder.objects.filter(pk=work_order.pk).exists() si el registro todavia
  existe antes de intentar persistir STATUS=ERROR. Si no existe, loga un
  diagnostico claro y aborta sin reintentar (return), evitando el
  DatabaseError: Save with update_fields did not affect any rows.

Fix adicional sesion 004 — _queue_actions.html dropdown limpio:
  Los items "Editar" y "Descargar Excel" deshabilitados (disabled) en la
  pestaña "En cola" generaban un dropdown con scroll interno que ocultaba
  el boton "Borrar" y creaba apariencia de contenido inaccesible. Ambos
  items deshabilitados han sido eliminados. El dropdown de la pestana "En
  cola" muestra unicamente "Borrar".

---

## 3. Hoja de Ruta

### Paso 1 — HTMX en base.html + WorkOrderStatusFragmentView (Bloque A)
- Estado: COMPLETADO (sesion 002).

### Paso 2 — HTMX guardado automatico por campo en editor (Bloque B)
- Estado: COMPLETADO (sesion 002).

### Paso 3 — Editor: insertar + drag & drop + restaurar + avisos (Bloque C)
- Estado: COMPLETADO con correcciones E2E (sesion 002).

### Paso 4 — Columna mano de obra + parser OCR (Bloque D)
- Estado: COMPLETADO (sesion 002).

### Paso 5 — Deteccion de duplicado en upload (Bloque E)
- Estado: COMPLETADO con fix sesion 003 (deteccion por WorkOrderEntry).

### Paso 6 — Exportacion de Excels (Bloque F)
- Estado: COMPLETADO (sesion 003).

### Paso 7 — Campo reviewed + rol SUPERVISOR (Bloque G)
- Estado: COMPLETADO (sesion 003).

### Paso 8 — Pestanas en list.html + rediseno Bloque F (Bloque H)
- Estado: COMPLETADO (sesion 003).

### Paso 9 — Hash SHA-256 deteccion duplicado exacto (Bloque I)
- Estado: COMPLETADO (sesion 004).

### Paso 10 — Validacion E2E completa
- Validar polling HTMX con PDF real en extraccion: VALIDADO.
- Validar guardado automatico en editor sin scroll: VALIDADO (sesiones anteriores).
- Validar insercion, reordenado, restauracion individual y eliminacion de lineas: VALIDADO.
- Validar correccion columna mano de obra en Excel descargado: VALIDADO.
- Validar deteccion duplicado exacto (hash) + modal + sobrescritura: VALIDADO sesion 004.
- Validar deteccion duplicado por contenido (operario + periodo) + modal: VALIDADO sesion 005.
- Validar exportacion multi-Excel en ambos modos (single_sheet, multi_sheet): VALIDADO.
- Validar pestanas y filtrado por estado/revision: VALIDADO.
- Validar permisos del rol SUPERVISOR: VALIDADO.
- Validar toggle de revision HTMX inline: VALIDADO.
- Estado: COMPLETADO (sesion 005).

### Paso 11 — Comando detect_duplicate_entries (COMPLETADO sesion 005)
Comando de gestion que detecta WorkOrders distintos (hashes distintos) de la
misma empresa que comparten entradas con el mismo (worker_name, work_date).
Opera sobre datos ya extraidos por Gemini — maxima precision.
  - Itera grupos (company, worker_name, work_date) con mas de un WorkOrder distinto.
  - Reporta por grupo: operario, fecha, lista de WorkOrders implicados
    (pk, fecha de carga, hash, estado, reviewed).
  - Flag --company: acotar a empresa concreta por pk o nombre.
  - Flag --fix (opt-in, IRREVERSIBLE): para cada grupo conserva el WorkOrder
    con pk mas alto (mas reciente) y elimina los anteriores en cascada.
    Solicita confirmacion explicita en consola antes de actuar [s/N].
  - Salida: informe detallado con contadores de grupos detectados,
    WorkOrders implicados y (si --fix) eliminados.
  Ruta: work_order_processor/management/commands/detect_duplicate_entries.py

### Paso 12 — Barrera Nivel 3 en upload: modal duplicate_entries (COMPLETADO sesion 005)
En WorkOrderUploadView.post(), tras los Niveles 1 (hash) y 2 (periodo),
anadir Nivel 3: buscar WorkOrderEntry del mismo operario con work_date
concretas que caigan dentro del periodo extraido del nombre del fichero,
en WorkOrders con hash distinto al entrante.
  - Si match -> duplicate_reason = "duplicate_entries".
  - Modal muestra lista de fechas concretas detectadas:
    "Ya existen entradas del operario X para los dias 01/01/25, 02/01/25
    en el parte #N."
  - upload.html: nuevo bloque {% elif duplicate_reason == 'duplicate_entries' %}
    con mensaje enriquecido que lista las fechas concretas.
  - La variable duplicate_dates (lista de strings DD/MM/YY) se pasa al contexto.

### Paso 13 — Boton Buscar duplicados en pestana Pendiente revision (COMPLETADO sesion 005)
Boton "Buscar duplicados" en la cabecera de pane-pending en list.html.
Llama a un endpoint Django que ejecuta la logica de detect_duplicate_entries
acotada a la empresa del usuario autenticado y devuelve resultados inline
en el panel via HTMX.
  - Nueva vista WorkOrderDuplicateSearchView (SupervisorAccessMixin).
  - Endpoint: POST /panel/work-orders/duplicates/search/
  - Devuelve fragmento HTML con tabla de grupos duplicados detectados.
  - Cada grupo incluye boton "Eliminar duplicado" con modal de confirmacion
    (equivalente al --fix del comando, accion irreversible).
  - Nueva vista WorkOrderDuplicateDeleteView (AdminRoleRequiredMixin).
  - Endpoint: POST /panel/work-orders/duplicates/<pk>/delete/
  - Template parcial nuevo: panel/work_orders/_duplicates_fragment.html

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | —               | Creacion del anexo. Inicio formal del hito. H7 pausado. |
| 002    | 2026-04-28 | 1-6 + E2E       | Implementacion completa bloques A-F. Correcciones E2E: atomic INSERT, restore individual de linea, WorkOrderLineDeleteView, WorkOrderDeleteView. Bugfix formula COSTE M.O. Especificacion acordada para bloques G y H. |
| 003    | 2026-04-28 | 7-8 + fixes     | Implementacion bloques G y H: rol SUPERVISOR, SupervisorAccessMixin, WorkOrderMarkReviewedView, cuatro pestanas list.html, exportacion single_sheet/multi_sheet, neonatos _review_badge_fragment.html y _queue_actions.html. Fix deteccion duplicado por WorkOrderEntry. Fix modal Bootstrap bootstrap is not defined. Especificacion Bloque I (hash SHA-256). |
| 004    | 2026-04-29 | 9 + fixes E2E   | Implementacion completa Bloque I: campo source_pdf_hash (models.py + migracion 0004), WorkOrderUploadView.post() con deteccion dos niveles (hash exacto + operario/periodo), upload.html con mensajes diferenciados exact/content, neonato backfill_pdf_hashes con --purge-duplicates, backfill ejecutado (11 registros). Fix tasks.py: guard WorkOrder eliminado en vuelo por sobrescritura concurrente. Fix _queue_actions.html: dropdown limpio sin items deshabilitados. Directriz de negocio Alejandro: Excel solo en pestana Revisados (list.html + WorkOrderExportView). Skill pisa actualizada: directriz lectura integra obligatoria. Validacion E2E parcial (9/10 puntos). Especificacion Pasos 11-13 para sesion 005. |
| 005    | 2026-04-29 | 10-14 + cierre  | Validacion E2E punto 6 completada (duplicate_reason=content). Paso 11: neonato detect_duplicate_entries.py con flags --company y --fix. Paso 12: barrera Nivel 3 en WorkOrderUploadView.post() + bloque duplicate_entries en upload.html. Paso 13: WorkOrderDuplicateSearchView + WorkOrderDuplicateDeleteView + neonato _duplicates_fragment.html + 2 rutas en urls.py + boton Buscar duplicados en pane-pending de list.html. Paso 14: borrado automatico PDF fisico en tasks.py al alcanzar DONE. Debate y decision sobre persistencia de PDFs (Opcion A). Creacion hitos H9 (Informes), H10 (Albaranes Proveedores), H11 (Albaranes Clientes) en PAUSADO. H7 reactivado como EN PROGRESO. Hito 8 cerrado. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (HITO PAUSADO)

El Hito 8 queda PAUSADO al cierre de la sesion 009.

Pendiente si se reactiva:
  - Coloracion de incidencias (flags activos) en el Excel de salida generado por
    generate_work_order_excel() en services.py, si el supervisor lo requiere.
    Actualmente los flags se conservan en BD y son visibles en el editor del panel.
  - Badge de advertencia visual en el editor de partes para lineas con
    machine_asset=NULL (centro de gasto no resuelto en catalogo). Actualmente
    el campo Activo resuelto aparece vacio sin indicador diferenciado.

El siguiente hito activo es el Hito 7 — Partes Diarios de Reparacion Entrada Digital.
Ver ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md para la hoja de ruta de la proxima sesion.

### PRIMERA ACCION — Completar validacion E2E Paso 10

Unico punto pendiente del checklist:
  4. Subir PDF diferente del mismo operario y periodo -> modal "datos solapados"
     (duplicate_reason = "content"). Verificar que el mensaje del modal
     muestra correctamente: "Ya existen datos del operario X para este
     periodo en el parte #N."

### SEGUNDA ACCION — Paso 11: comando detect_duplicate_entries

Archivo nuevo (neonato puro):
  work_order_processor/management/commands/detect_duplicate_entries.py

Logica:
  1. Consultar grupos (company_id, worker_name, work_date) en WorkOrderEntry
     que aparezcan en mas de un WorkOrder distinto (hashes distintos):
       from django.db.models import Count
       duplicates = (
           WorkOrderEntry.objects
           .values("work_order__company_id", "worker_name", "work_date")
           .annotate(wo_count=Count("work_order_id", distinct=True))
           .filter(wo_count__gt=1)
           .order_by("work_order__company_id", "worker_name", "work_date")
       )
  2. Para cada grupo, recuperar los WorkOrders implicados con sus datos:
       pk, pdf_display_name, upload_date, source_pdf_hash, status, reviewed.
  3. Imprimir informe agrupado por empresa / operario / fecha.
  4. Flag --company (opcional): filtrar por company pk o nombre exacto.
  5. Flag --fix (opt-in, IRREVERSIBLE):
     - Para cada grupo, conservar el WorkOrder con pk mas alto (mas reciente).
     - Solicitar confirmacion en consola antes de actuar: "[s/N]".
     - Si confirma: eliminar los WorkOrders mas antiguos del grupo en cascada
       (WorkOrder.delete() propaga a WorkOrderEntry y WorkOrderEntryLine).
     - Informe final: grupos detectados, WorkOrders eliminados, omitidos.

### TERCERA ACCION — Paso 12: barrera Nivel 3 en upload

Archivo: panel/views.py — WorkOrderUploadView.post()
Anadir Nivel 3 tras el Nivel 2 existente (solo si duplicate_wo sigue siendo None):

    # NIVEL 3 — Fechas concretas en BD (solo si Nivel 1 y 2 no coincidieron).
    # Se buscan WorkOrderEntry del mismo operario con work_date concretas
    # dentro del periodo extraido del nombre del fichero, en WorkOrders
    # con hash distinto al entrante.
    if not duplicate_wo and incoming_worker and date_from and date_to:
        conflicting_entries = (
            WorkOrderEntry.objects
            .filter(
                work_order__company=company,
                worker_name=incoming_worker,
                work_date__gte=date_from,
                work_date__lte=date_to,
            )
            .exclude(work_order__source_pdf_hash=incoming_hash)
            .exclude(work_order__source_pdf_hash="")
            .select_related("work_order")
            .order_by("work_date")
        )
        if conflicting_entries.exists():
            # Build list of concrete dates for the modal message.
            # Construir lista de fechas concretas para el mensaje del modal.
            duplicate_dates = [
                e.work_date.strftime("%d/%m/%y")
                for e in conflicting_entries
                if e.work_date
            ]
            # Deduplicate preserving order.
            seen = set()
            duplicate_dates = [
                d for d in duplicate_dates
                if not (d in seen or seen.add(d))
            ]
            first_entry     = conflicting_entries.first()
            duplicate_wo     = first_entry.work_order
            duplicate_reason = "duplicate_entries"

Anadir duplicate_dates al contexto del render cuando duplicate_reason == "duplicate_entries":
    return render(request, self.template_name, {
        ...
        "duplicate_wo":     duplicate_wo,
        "duplicate_reason": duplicate_reason,
        "duplicate_dates":  duplicate_dates,   # lista de strings DD/MM/YY
        "pdf_file_name":    incoming_name,
    })

Archivo: panel/templates/panel/work_orders/upload.html
Anadir bloque en el modal tras el bloque {% else %} (duplicate_reason == "content"):
    {% elif duplicate_reason == 'duplicate_entries' %}
    <p>
        Ya existen entradas del operario
        <strong>{{ duplicate_wo.pdf_display_name }}</strong>
        para los dias concretos
        <strong>{{ duplicate_dates|join:", " }}</strong>
        en el parte <strong>#{{ duplicate_wo.pk }}</strong>
        (cargado el {{ duplicate_wo.upload_date|date:"d/m/Y H:i" }}).
        El fichero es distinto pero los datos se solapan exactamente.
    </p>

### CUARTA ACCION — Paso 13: boton Buscar duplicados en pestana Pendiente revision

#### 13A — Nueva vista WorkOrderDuplicateSearchView
Archivo: panel/views.py
Mixin: SupervisorAccessMixin
Endpoint: POST /panel/work-orders/duplicates/search/
Logica:
  - Ejecuta la misma consulta de detect_duplicate_entries acotada a
    company = request.user.company_user.company.
  - Devuelve el parcial _duplicates_fragment.html con los grupos detectados.
  - Si no hay duplicados: devuelve fragmento con mensaje informativo.

#### 13B — Nueva vista WorkOrderDuplicateDeleteView
Archivo: panel/views.py
Mixin: AdminRoleRequiredMixin
Endpoint: POST /panel/work-orders/duplicates/<pk>/delete/
Logica:
  - Recibe el pk del WorkOrder a eliminar (el duplicado antiguo).
  - Verifica que pertenece a la empresa del usuario autenticado.
  - Elimina en cascada (WorkOrder.delete()).
  - Devuelve fragmento HTML vacio (HTMX elimina la fila del DOM).

#### 13C — Nuevo template parcial _duplicates_fragment.html
Ruta: panel/templates/panel/work_orders/_duplicates_fragment.html
Contenido: tabla de grupos duplicados. Por cada grupo:
  - Operario, fecha conflictiva, lista de WorkOrders implicados
    (pk, nombre PDF, fecha carga, estado, revisado).
  - Boton "Eliminar" por cada WorkOrder no-keeper con modal de confirmacion.
    Solo el ADMIN ve el boton de eliminacion (comprobar company_user.role).

#### 13D — Boton en list.html
Archivo: panel/templates/panel/work_orders/list.html
Anadir en la cabecera de pane-pending, junto al titulo de la pestana o
debajo de la tabla cuando esta vacia, un boton:
    <button type="button"
            class="btn btn-outline-warning btn-sm"
            hx-post="{% url 'panel:work_order_duplicates_search' %}"
            hx-target="#duplicates-results"
            hx-swap="innerHTML">
        <i class="bi bi-search me-1"></i>Buscar duplicados
    </button>
    <div id="duplicates-results" class="mt-3"></div>

#### 13E — Nueva URL
Archivo: panel/urls.py
Anadir:
    path("work-orders/duplicates/search/",
         WorkOrderDuplicateSearchView.as_view(),
         name="work_order_duplicates_search"),
    path("work-orders/duplicates/<int:pk>/delete/",
         WorkOrderDuplicateDeleteView.as_view(),
         name="work_order_duplicate_delete"),

### Paso 14 — Borrado automatico del PDF fisico al alcanzar DONE (COMPLETADO sesion 005)

Modificacion en work_order_processor/tasks.py — process_work_order_pdf():
Tras la llamada a generate_work_order_excel() (Paso 4), se añade el Paso 5
que elimina el fichero PDF fisico del disco via source_pdf.delete(save=False)
y vacia el campo source_pdf en BD. El campo source_pdf_hash se conserva
intacto para mantener la deteccion de duplicados exactos (Nivel 1). El
borrado es no-fatal: un fallo en la eliminacion del fichero se registra como
WARNING pero no revierte el estado DONE ni el Excel generado.

### Estado de migraciones al inicio de la sesion 005

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0004_workorder_source_pdf_hash                         |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave al inicio de la sesion 005

- panel/views.py — WorkOrderUploadView.post() Nivel 3 (Paso 12) +
  WorkOrderDuplicateSearchView + WorkOrderDuplicateDeleteView (Paso 13).
- panel/urls.py — dos nuevas rutas duplicates/search/ y duplicates/<pk>/delete/.
- panel/templates/panel/work_orders/upload.html — bloque duplicate_entries (Paso 12).
- panel/templates/panel/work_orders/list.html — boton Buscar duplicados (Paso 13).
- panel/templates/panel/work_orders/_duplicates_fragment.html — neonato (Paso 13).
- work_order_processor/management/commands/detect_duplicate_entries.py — neonato (Paso 13).

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | Bloques A-F     | Implantacion HTMX en lista PDFs y editor inline. Exportacion Excels. Deteccion de duplicados Nivel 1 y 2. |
| 002    | 2026-04-28 | Bloques G, H    | Campo reviewed + rol SUPERVISOR. Pestanas en list.html. SupervisorAccessMixin. |
| 003    | 2026-04-29 | Bloques E fix, I| Fix modal Bootstrap duplicados. Hash SHA-256 Nivel 1. backfill_pdf_hashes. |
| 004    | 2026-04-29 | Pasos 11-13     | detect_duplicate_entries. Nivel 3 upload. Vistas WorkOrderDuplicateSearch/Delete. |
| 005    | 2026-04-29 | Paso 14         | Borrado automatico PDF fisico al alcanzar DONE en tasks.py. |
| 006    | 2026-04-30 | Fuera HR        | Hito reactivado. Correcciones panel: _field_pw.html (TemplateDoesNotExist), PanelSetPasswordForm (cambio forzado sin old_password), sidebar PDFs visible para SUPERVISOR. |
| 007    | 2026-05-01 | Nuevo trabajo   | Reactivacion del hito. Via B STT validada E2E: motor reemplazado de MediaRecorder a Web Speech API nativa (sin bytes de audio al servidor). WorkOrderEntrySTTExtractView.post() refactorizado: recibe JSON transcript, usa response_mime_type=application/json + response_schema + thinking_budget=0. Formulario pre-rellenado correctamente desde dictado natural. Problemas resueltos: TemplateDoesNotExist _field_pw.html, PanelSetPasswordForm para nuevos usuarios, sidebar SUPERVISOR, duplicacion de transcripcion (interimResults=false + sin reinicio automatico), truncado JSON Gemini (thinking tokens consumian output budget). |
| 008    | 2026-05-01 | Calidad datos + UX editor | Auditoria exhaustiva de 441 WorkOrderEntryLine en BD. Identificacion y confirmacion de tres incidencias reales: desbordamiento de linea (or_val con horario), multiples maquinas en un campo, confusion morfologica OCR en codigos de maquina. Diseno de mapa de confusion simetrico bidireccional (T<->7<->4, Z<->2, O<->0, L/I<->1, S<->5, G<->6, B<->8) validado contra catalogo de 313 MachineAsset incluyendo matrículas espanolas (guarda 4 digitos + 3 letras). PMA services.py: _OCR_CONFUSION_MAP anadido, _resolve_machine_asset ampliado con algoritmo de candidatos morfologicos por niveles (Nivel 1: 1 sustitucion; Nivel 2: 2 sustituciones simultaneas), _OCR_DIGIT_MAP legacy preservado con guarda de bloque numerico con letras, _EXTRACTION_PROMPT y _EXTRACTION_PROMPT_FULL reforzados con casos patron G-J (multiples maquinas, desbordamiento de linea, confusion morfologica, texto de etiqueta de formulario). Neonato repair_entry_lines.py con tres reglas deterministicas (R1: or_val->hc cuando hc=None; R2: explosion maquina_raw multi-codigo con normalizacion Y-inicial, guarda codigo-unico y guarda validacion de tokens; R3: re-resolucion morfologica de machine_asset=None). Ejecucion --apply: 2 lineas R1, 7 lineas R2 explosionadas en 14 nuevas, 36/72 lineas R3 resueltas. UX editor: columna Flags eliminada del panel (flags conservados en BD para Excel de incidencias); badge de jornada diaria en cabecera de grupo con cuatro niveles de color (day_total + day_css calculados en _build_groups()): <8h azul, 8-12h verde, 12-16h ambar, >16h rojo. Validado E2E. Hito pausado al cierre de sesion 008. |
| 009    | 2026-05-04 | Deuda tecnica + fix OCR inverso + Regla 4 | Renombrado completo de 6 campos a ingles (Regla de Oro del Idioma): maquina_raw->machine_raw, maquina_norm->machine_norm, descripcion_averia->fault_description, reparacion->repair_notes, delta_horas->delta_hours, fecha_incierta->uncertain_date. Migracion 0007_rename_fields_english aplicada. PMA sobre models.py, services.py, tasks.py, admin.py, repair_entry_lines.py, panel/views.py, 3 templates work_orders. Saneado de referencias a campos H12 (code, brand_model, type_name, family, is_active) en 12 archivos adicionales (panel/views.py, signals.py, 5 templates operator, analytics.html, _line_row.html, import_machine_catalog.py). Fix OCR inverso: _OCR_DIGIT_TO_LETTER_MAP anadido en services.py — codigos puramente numericos con digito inicial interpretable como letra (ej. 294->Z-94, 225->Z-25). Regla 4 anadida a repair_entry_lines.py: re-normaliza machine_norm en lineas ya resueltas donde el valor actual es crudo (igual al raw, vacio o puramente numerico), con guarda que protege machine_norm establecido por el resolver morfologico. Ejecucion --apply: 47 machine_norm actualizados. Fix import_name _compute_delta_horas->_compute_delta_hours en tasks.py y panel/views.py. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (008)

### Contexto

Los partes de trabajo manuscritos procesados via PDF presentan sistematicamente
problemas de calidad en los datos extraidos por Gemini Vision:

- Multiples bloques de trabajo colapsados en una sola WorkOrderEntryLine
  (el operario escribe varias tareas seguidas sin separacion clara).
- Una misma tarea asignada a multiples centros de gasto (vehiculos) en la
  misma linea, cuando deberia generar una WorkOrderEntryLine por centro.
- El horario (H.C./H.F.) escrito en el campo reservado a la O.R. y viceversa.
- Codigos de maquina con errores OCR no corregidos por _normalise_machine_code().
- Descripciones de averia con texto de relleno o instrucciones del propio
  formulario capturadas como contenido.

El objetivo de la sesion 008 es doble:
1. Reforzar _EXTRACTION_PROMPT (el prompt historico de PDFs) y
   _EXTRACTION_PROMPT_FULL (el prompt de la Via C del H7) para que Gemini
   gestione correctamente estos casos patron.
2. Confeccionar un comando de gestion Django permanente que se aplique sobre
   los WorkOrderEntryLine ya persistidos en BD y corrija automaticamente
   las incidencias detectables de forma programatica.

---

### Primera accion — Auditoria de partes historicos con incidencias

Antes de tocar ningun prompt ni escribir ningun comando, realizar una
auditoria exhaustiva de los WorkOrderEntryLine existentes en BD para
catalogar los tipos de incidencia reales y su frecuencia.

Herramienta: shell Django con ORM.

Consultas de auditoria a ejecutar:

````python
# 1. Lineas con H.C. o H.F. vacios o con valor no horario (posible confusion con O.R.)
from work_order_processor.models import WorkOrderEntryLine
import re
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
bad_times = WorkOrderEntryLine.objects.exclude(hc='').exclude(hf='').filter(
    models.Q(hc__isnull=False) | models.Q(hf__isnull=False)
)
# Filtrar los que no matchean HH:MM
non_time_hc = [l for l in WorkOrderEntryLine.objects.exclude(hc='') if not TIME_RE.match(l.hc or '')]
non_time_hf = [l for l in WorkOrderEntryLine.objects.exclude(hf='') if not TIME_RE.match(l.hf or '')]

# 2. Lineas con descripcion_averia que contenga patrones de formulario
suspect_desc = WorkOrderEntryLine.objects.filter(
    models.Q(descripcion_averia__icontains='descripcion') |
    models.Q(descripcion_averia__icontains='averia') |
    models.Q(descripcion_averia__icontains='reparacion')
)

# 3. Lineas con or_val que parezca un horario
or_as_time = [l for l in WorkOrderEntryLine.objects.exclude(or_val='')
              if TIME_RE.match(l.or_val or '')]

# 4. Lineas con maquina_raw vacio o no resuelto (machine_asset es None)
unresolved = WorkOrderEntryLine.objects.filter(machine_asset__isnull=True).exclude(maquina_raw='')
````

Los resultados de esta auditoria determinan:
- Que patrones anadir al prompt para prevenirlos en nuevas extracciones.
- Que correcciones puede aplicar el comando de gestion automaticamente
  (reglas deterministicas) y cuales requieren revision manual.

---

### Segunda accion — Refuerzo de _EXTRACTION_PROMPT y _EXTRACTION_PROMPT_FULL

Archivo: work_order_processor/services.py

Directriz: NO reescribir el prompt desde cero. Anadir secciones
especificas de manejo de casos patron al final del bloque de instrucciones
existente, antes del esquema JSON de respuesta esperada.

Casos patron a cubrir (minimo, ampliar con los hallazgos de la auditoria):

1. Multiples bloques de trabajo en una misma celda fisica:
   "Si un operario ha escrito mas de una tarea en el mismo espacio,
   genera una WorkOrderEntryLine separada por cada tarea identificable.
   Criterio de separacion: cambio de maquina, cambio de horario, o
   separacion visual clara (linea, barra, punto y aparte)."

2. Una tarea para multiples centros de gasto:
   "Si la misma descripcion de averia aparece asociada a mas de un
   codigo de maquina, genera una WorkOrderEntryLine por cada maquina,
   repitiendo la descripcion y el horario en cada una."

3. Confusion H.C./H.F. con O.R.:
   "El campo O.R. (Orden de Reparacion) es un identificador alfanumerico
   como 'OR-1234' o un nombre propio. Si el valor encontrado en el campo
   O.R. del formulario fisico tiene formato HH:MM, interpreta que el
   operario ha escrito el horario en el lugar equivocado: coloca ese
   valor en hc o hf segun corresponda y deja or_val vacio."

4. Texto de formulario capturado como contenido:
   "Si descripcion_averia contiene literalmente palabras como 'descripcion',
   'averia', 'reparacion', 'tarea' o similares que son etiquetas del propio
   formulario, ignora ese texto y deja el campo vacio."

5. Codigos de maquina con caracteres OCR:
   "Aplica las siguientes sustituciones al bloque numerico del codigo
   de maquina: O->0, L->1, T->7, S->5, Z->2, G->6."

---

### Tercera accion — Comando de gestion: repair_entry_lines

Archivo nuevo (neonato puro):
  work_order_processor/management/commands/repair_entry_lines.py

El comando opera sobre WorkOrderEntryLine ya persistidos en BD aplicando
correcciones automaticas deterministicas. No usa IA — solo reglas de
transformacion seguras.

Estructura del comando:

````python
# Invocacion:
#   python -m dotenv run python manage.py repair_entry_lines
#   python -m dotenv run python manage.py repair_entry_lines --company <pk_o_nombre>
#   python -m dotenv run python manage.py repair_entry_lines --dry-run
#   python -m dotenv run python manage.py repair_entry_lines --apply

# Flags:
#   --company    Filtrar por company pk o nombre exacto (opcional).
#   --dry-run    (por defecto) Mostrar incidencias detectadas sin modificar nada.
#   --apply      Aplicar correcciones. IRREVERSIBLE sin --dry-run previo.

# Reglas de correccion automatica (ejecutadas en orden):
#
# REGLA 1 — Intercambio H.C./H.F. con O.R.:
#   Si or_val matchea TIME_RE (HH:MM) y hc esta vacio:
#     hc = or_val, or_val = ''
#   Si or_val matchea TIME_RE y hf esta vacio:
#     hf = or_val, or_val = ''
#
# REGLA 2 — Normalizar codigos de maquina:
#   Aplicar _normalise_machine_code() sobre maquina_raw.
#   Si el resultado difiere de maquina_raw, actualizar maquina_raw
#   e intentar re-resolver machine_asset via _resolve_machine_asset().
#
# REGLA 3 — Limpiar descripcion_averia con texto de formulario:
#   KEYWORDS = ['descripcion', 'averia', 'reparacion', 'tarea']
#   Si descripcion_averia (en minusculas) es exactamente una de las keywords
#   o contiene solo keywords y espacios: vaciar el campo.
#
# Informe de salida:
#   Por cada linea afectada: pk, worker_name, work_date, regla aplicada,
#   valor anterior → valor nuevo.
#   Resumen final: total lineas inspeccionadas / total correcciones aplicadas /
#   total lineas con incidencias no automatizables (flags activos).
````

La implementacion exacta se construira en sesion 008 tras la auditoria
de la primera accion, que puede revelar nuevas reglas deterministicas
no contempladas aqui.

---

### Estado de migraciones al cierre de sesion 007

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0006_workorder_unique_pdf_hash_per_company             |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave modificados en sesion 007 (H8 reactivado)

- panel/forms.py — SetPasswordForm importado + PanelSetPasswordForm anadido.
- panel/views.py — PanelSetPasswordForm importado; _build_form() en
  PanelPasswordChangeView; WorkOrderEntrySTTExtractView.post() refactorizado
  (JSON transcript, response_mime_type, response_schema, thinking_budget=0).
- panel/templates/panel/password/_field_pw.html — neonato creado.
- panel/templates/panel/password/change.html — bloque old_password envuelto
  en {% if not is_forced %}.
- panel/templates/panel/_nav_items.html — seccion Partes visible para SUPERVISOR.
- panel/templates/panel/operator/stt_entry.html — motor STT reemplazado:
  Web Speech API nativa (interimResults=false, sin reinicio automatico);
  textarea de transcripcion visible; boton Enviar a IA.
