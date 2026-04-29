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
- Validar deteccion duplicado por contenido (operario + periodo) + modal: PENDIENTE.
- Validar exportacion multi-Excel en ambos modos (single_sheet, multi_sheet): VALIDADO.
- Validar pestanas y filtrado por estado/revision: VALIDADO.
- Validar permisos del rol SUPERVISOR: VALIDADO.
- Validar toggle de revision HTMX inline: VALIDADO.
- Estado: PARCIALMENTE COMPLETADO (pendiente punto 6).

### Paso 11 — Comando detect_duplicate_entries (PENDIENTE)
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

### Paso 12 — Barrera Nivel 3 en upload: modal duplicate_entries (PENDIENTE)
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

### Paso 13 — Boton Buscar duplicados en pestana Pendiente revision (PENDIENTE)
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

---

## 5. Hoja de Ruta para la Siguiente Sesion (005)

### Objetivo principal
Paso 10 (completar punto 6 de validacion E2E pendiente) +
Paso 11 (comando detect_duplicate_entries) +
Paso 12 (barrera Nivel 3 en upload: modal duplicate_entries) +
Paso 13 (boton Buscar duplicados en pestana Pendiente revision).

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
- work_order_processor/management/commands/detect_duplicate_entries.py — neonato (Paso 11).
