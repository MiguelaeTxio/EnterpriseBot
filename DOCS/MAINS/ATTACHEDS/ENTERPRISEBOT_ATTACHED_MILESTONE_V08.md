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

### 2.9. Bloque I — Hash SHA-256 para deteccion de duplicado exacto (PENDIENTE)

Nuevo campo source_pdf_hash en WorkOrder:
  source_pdf_hash = models.CharField(max_length=64, blank=True, db_index=True)

Nueva migracion requerida en work_order_processor.

Flujo de deteccion en WorkOrderUploadView.post():
  1. Calcular SHA-256 del fichero entrante en memoria (antes de guardarlo).
  2. Buscar WorkOrder con mismo company + source_pdf_hash.
  3. Si hash match -> modal de duplicado exacto (mismo fichero).
  4. Si no hash match pero existen WorkOrderEntry del mismo operario
     y periodo -> modal de duplicado por contenido.
  5. Si nada -> crear WorkOrder, guardar hash en source_pdf_hash y encolar.

Al crear el WorkOrder en Step 3 de post():
  work_order.source_pdf_hash = incoming_hash
  work_order.save(update_fields=["source_pdf_hash"])
  (despues de work_order = WorkOrder.objects.create(...))

Nuevo comando de gestion backfill_pdf_hashes:
  Ruta: work_order_processor/management/commands/backfill_pdf_hashes.py
  - Itera WorkOrder con source_pdf y source_pdf_hash vacio.
  - Calcula SHA-256 del fichero fisico en disco.
  - Guarda en source_pdf_hash.
  - Si el fichero fisico no existe: registra warning y continua (hash vacio).
  - Salida: informe de cuantos procesados, cuantos sin fichero, cuantos omitidos.

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
- Estado: PENDIENTE.

### Paso 10 — Validacion E2E completa
- Validar polling HTMX con PDF real en extraccion.
- Validar guardado automatico en editor sin scroll.
- Validar insercion, reordenado, restauracion individual y eliminacion de lineas.
- Validar correccion columna mano de obra en Excel descargado.
- Validar deteccion duplicado exacto (hash) + modal + sobrescritura.
- Validar deteccion duplicado por contenido (operario + periodo) + modal.
- Validar exportacion multi-Excel en ambos modos (single_sheet, multi_sheet).
- Validar pestanas y filtrado por estado/revision.
- Validar permisos del rol SUPERVISOR.
- Validar toggle de revision HTMX inline.
- Estado: PENDIENTE.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | —               | Creacion del anexo. Inicio formal del hito. H7 pausado. |
| 002    | 2026-04-28 | 1-6 + E2E       | Implementacion completa bloques A-F. Correcciones E2E: atomic INSERT, restore individual de linea, WorkOrderLineDeleteView, WorkOrderDeleteView. Bugfix formula COSTE M.O. Especificacion acordada para bloques G y H. |
| 003    | 2026-04-28 | 7-8 + fixes     | Implementacion bloques G y H: rol SUPERVISOR, SupervisorAccessMixin, WorkOrderMarkReviewedView, cuatro pestanas list.html, exportacion single_sheet/multi_sheet, neonatos _review_badge_fragment.html y _queue_actions.html. Fix deteccion duplicado por WorkOrderEntry. Fix modal Bootstrap bootstrap is not defined. Especificacion Bloque I (hash SHA-256). |

---

## 5. Hoja de Ruta para la Siguiente Sesion (004)

### Objetivo principal
Paso 9 (Bloque I) + Paso 10 (Validacion E2E completa).

### PRIMERA ACCION — Bloque I: campo source_pdf_hash

#### I1 — Campo source_pdf_hash en WorkOrder
Archivo: work_order_processor/models.py
Anadir campo tras reviewed_at:

    source_pdf_hash = models.CharField(
        _("Hash SHA-256 del PDF"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_(
            "Hash SHA-256 del fichero PDF original calculado en el momento "
            "de la carga. Permite detectar duplicados exactos independientemente "
            "del nombre del fichero."
        ),
    )

Generar y aplicar migracion:
    python -m dotenv run python manage.py makemigrations work_order_processor
    python -m dotenv run python manage.py migrate

#### I2 — Calculo y guardado del hash en WorkOrderUploadView.post()
Archivo: panel/views.py
En WorkOrderUploadView.post(), ANTES del Step 2 de deteccion de duplicado:

    import hashlib
    pdf_file.seek(0)
    incoming_hash = hashlib.sha256(pdf_file.read()).hexdigest()
    pdf_file.seek(0)

Step 2 rediseniado — dos niveles:

    NIVEL 1 — Hash exacto:
    hash_duplicate = WorkOrder.objects.filter(
        company=company,
        source_pdf_hash=incoming_hash,
    ).exclude(source_pdf_hash="").first()
    if hash_duplicate:
        duplicate_wo = hash_duplicate
        duplicate_reason = "exact"

    NIVEL 2 — Operario + periodo (solo si no hay hash match):
    if not duplicate_wo and incoming_worker:
        entry_qs = WorkOrderEntry.objects.filter(
            work_order__company=company,
            worker_name=incoming_worker,
        ).select_related("work_order")
        if date_from and date_to:
            entry_qs = entry_qs.filter(
                work_date__gte=date_from,
                work_date__lte=date_to,
            )
        existing_entry = entry_qs.first()
        if existing_entry:
            duplicate_wo = existing_entry.work_order
            duplicate_reason = "content"

El modal de duplicado debe mostrar mensaje diferenciado segun duplicate_reason:
    - "exact": "Se ha detectado que el fichero PDF es identico al parte #X."
    - "content": "Ya existen datos del operario X para este periodo en el parte #X."

Al crear el WorkOrder en Step 3:
    work_order = WorkOrder.objects.create(
        company=company,
        uploaded_by=company_user,
        source_pdf=pdf_file,
        source_pdf_hash=incoming_hash,
    )

#### I3 — Comando de gestion backfill_pdf_hashes
Archivo nuevo: work_order_processor/management/commands/backfill_pdf_hashes.py
Logica:
    - Iterar WorkOrder.objects.filter(source_pdf_hash="").order_by("pk").
    - Para cada WorkOrder con source_pdf:
        - Intentar abrir source_pdf.path.
        - Si existe: calcular SHA-256, guardar en source_pdf_hash, contar como procesado.
        - Si no existe (FileNotFoundError): registrar warning con pk, contar como sin_fichero.
    - Para cada WorkOrder sin source_pdf: contar como omitido.
    - Al finalizar: imprimir resumen: procesados, sin_fichero, omitidos.

#### I4 — Ejecutar backfill tras aplicar migracion
    python -m dotenv run python manage.py backfill_pdf_hashes

#### I5 — Actualizar upload.html
El modal de duplicado debe recibir duplicate_reason del contexto y mostrar
mensaje diferenciado segun su valor ("exact" o "content").

### SEGUNDA ACCION — Validacion E2E completa (Paso 10)

Checklist de validacion en orden:
  1. Subir PDF nuevo -> aparece en "En cola" con polling activo.
  2. Esperar a DONE -> aparece en "Pendiente revision".
  3. Subir mismo PDF (hash identico) -> modal "fichero identico".
  4. Subir PDF diferente del mismo operario y periodo -> modal "datos solapados".
  5. Confirmar sobrescritura -> duplicado eliminado, nuevo encolado.
  6. Marcar revisado -> badge cambia a "Revisado" con nombre y fecha inline.
  7. Desmarcar -> badge vuelve a "Pendiente revision" inline.
  8. Seleccionar varios partes -> modal de modo exportacion.
  9. Exportar single_sheet -> verificar separadores por operario en Excel.
  10. Exportar multi_sheet -> verificar una hoja por operario.
  11. Acceder con rol SUPERVISOR -> acceso a PDFs, sin acceso a configuracion IVR.
  12. Acceder con rol OPERATOR -> redireccion a dashboard.

### Estado de migraciones al inicio de la sesion 004

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0003_workorder_reviewed_workorder_reviewed_at_and_more |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

NOTA: la migracion del Bloque I (source_pdf_hash) es la PRIMERA accion
de la sesion 004 — aplicarla antes de cualquier otra cosa.

### Archivos clave al inicio de la sesion 004

- work_order_processor/models.py — anadir source_pdf_hash (I1).
- panel/views.py — WorkOrderUploadView.post() dos niveles de deteccion (I2).
- work_order_processor/management/commands/backfill_pdf_hashes.py — neonato (I3).
- panel/templates/panel/work_orders/upload.html — mensaje diferenciado (I5).
