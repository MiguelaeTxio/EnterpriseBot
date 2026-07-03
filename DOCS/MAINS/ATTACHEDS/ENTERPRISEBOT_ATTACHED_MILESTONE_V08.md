# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md

# Anexo de Hito V08 — Mejoras Procesador PDF->Excel + HTMX
# Proyecto: EnterpriseBot
# Estado: PAUSADO
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
directamente en BD por worker_name + solapamiento de work_date.

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

### 2.7. Bloque G — Campo reviewed + rol SUPERVISOR (COMPLETADO sesion 003)

Nuevo campo reviewed en WorkOrder:
- reviewed    = BooleanField(default=False, db_index=True)
- reviewed_by = ForeignKey(CompanyUser, null=True, blank=True, SET_NULL)
- reviewed_at = DateTimeField(null=True, blank=True)
Migracion aplicada: work_order_processor 0003.

Nuevo rol SUPERVISOR en CompanyUser.Role.
SupervisorAccessMixin en panel/mixins.py.
WorkOrderMarkReviewedView: POST /panel/work-orders/<pk>/review/

### 2.8. Bloque H — Pestanas en list.html + rediseno Bloque F (COMPLETADO sesion 003)

Cuatro pestanas Bootstrap en list.html:
  1. "En cola" — WorkOrders PENDING o PROCESSING. Polling HTMX activo.
  2. "Error" — WorkOrders ERROR con boton ver log y boton borrar.
  3. "Pendiente revision" — WorkOrders DONE con reviewed=False.
  4. "Revisados" — WorkOrders DONE con reviewed=True.

### 2.9. Bloque I — Hash SHA-256 para deteccion de duplicado exacto (COMPLETADO sesion 004)

Nuevo campo source_pdf_hash en WorkOrder (max_length=64, db_index=True).
Migracion aplicada: work_order_processor 0004_workorder_source_pdf_hash.
Flujo de deteccion en WorkOrderUploadView.post() — DOS NIVELES:
  NIVEL 1 — Hash exacto (SHA-256 del fichero entrante).
  NIVEL 2 — Operario + periodo (solo si Nivel 1 no coincide).
Nuevo comando backfill_pdf_hashes con --purge-duplicates.

### 2.10. Editor de fecha inline en partes PDF (COMPLETADO — fix S048 desvío H7)

El editor de fecha inline permite al supervisor corregir la fecha de un
grupo de entradas directamente desde edit.html sin recarga de pagina.

Arquitectura:
- `WorkOrderEntrySaveDateView` (SupervisorAccessMixin) en panel/views_workorders.py.
  POST /panel/work-orders/<wo_pk>/entries/<entry_pk>/save-date/
  Persiste work_date en WorkOrderEntry y pone uncertain_date=False.
  Devuelve _entry_group_fragment.html renderizado (HTMX outerHTML swap).
- URL registrada en panel/urls.py: work_order_entry_save_date.
- HTML del editor en _entry_group_fragment.html:
  - .page-group-header contiene todos los elementos.
  - #date-text-{entry_pk}: texto de fecha, oculto al editar.
  - #btn-date-toggle-{entry_pk} (.btn-date-edit-toggle): botón lápiz.
  - #form-date-{entry_pk}: formulario hx-post con input[name=work_date].
  - .btn-date-cancel con data-entry-pk: botón cancelar.
- JS del toggle en edit.html (bloque <script> inline):
  Handler click delegado sobre .btn-date-edit-toggle y .btn-date-cancel.
  NOTA: el JS vive en edit.html, NO en admin_history.js. La regresión
  S048 consistió en que el handler JS se había perdido de edit.html en
  un merge. Fix aplicado: añadido el bloque Date editor toggle al IIFE
  de edit.html (antes del cierre }();).

---

## 3. Hoja de Ruta

### Pasos 1-14 — COMPLETADOS (sesiones 001-009)

Ver sección 4. Registro de Sesiones para el detalle completo.

### Hoja de Ruta para la Siguiente Sesion (HITO PAUSADO)

El Hito 8 queda PAUSADO al cierre de la sesion 009.

Pendiente si se reactiva:
  - Coloracion de incidencias (flags activos) en el Excel de salida generado por
    generate_work_order_excel() en services.py.
  - Badge de advertencia visual en el editor de partes para lineas con
    machine_asset=NULL (centro de gasto no resuelto en catalogo).
  - **Regresión edición centros de gasto (detectada S048):** la vista de edición
    de centros de gasto (MachineAsset) está rota — no se pueden editar. Causa
    raíz pendiente de diagnosticar. Archivos probables: panel/views.py o
    panel/views_workorders.py (MachineAssetUpdateView) + template fleet/update.html.
  - **Mejora vista centros de gasto (acordada S048):** la vista de listado de
    centros de gasto muestra muy pocos campos. Añadir scroll horizontal y mostrar
    todos los campos del modelo MachineAsset (code, brand_model, type_name, family,
    plate, is_active, first_repair, etc.) para que el supervisor tenga una visión
    completa sin necesidad de entrar a editar cada registro.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | —               | Creacion del anexo. Inicio formal del hito. H7 pausado. |
| 002    | 2026-04-28 | 1-6 + E2E       | Implementacion completa bloques A-F. Correcciones E2E: atomic INSERT, restore individual de linea, WorkOrderLineDeleteView, WorkOrderDeleteView. Bugfix formula COSTE M.O. Especificacion acordada para bloques G y H. |
| 003    | 2026-04-28 | 7-8 + fixes     | Implementacion bloques G y H: rol SUPERVISOR, SupervisorAccessMixin, WorkOrderMarkReviewedView, cuatro pestanas list.html, exportacion single_sheet/multi_sheet, neonatos _review_badge_fragment.html y _queue_actions.html. Fix deteccion duplicado por WorkOrderEntry. Fix modal Bootstrap bootstrap is not defined. Especificacion Bloque I (hash SHA-256). |
| 004    | 2026-04-29 | 9 + fixes E2E   | Implementacion completa Bloque I: campo source_pdf_hash (models.py + migracion 0004), WorkOrderUploadView.post() con deteccion dos niveles (hash exacto + operario/periodo), upload.html con mensajes diferenciados exact/content, neonato backfill_pdf_hashes con --purge-duplicates, backfill ejecutado (11 registros). Fix tasks.py: guard WorkOrder eliminado en vuelo por sobrescritura concurrente. Fix _queue_actions.html: dropdown limpio sin items deshabilitados. |
| 005    | 2026-04-29 | 10-14 + cierre  | Validacion E2E punto 6 completada. Paso 11: neonato detect_duplicate_entries.py. Paso 12: barrera Nivel 3 en WorkOrderUploadView.post(). Paso 13: WorkOrderDuplicateSearchView + WorkOrderDuplicateDeleteView + neonato _duplicates_fragment.html. Paso 14: borrado automatico PDF fisico en tasks.py al alcanzar DONE. |
| 006    | 2026-04-30 | Fuera HR        | Hito reactivado. Correcciones panel: _field_pw.html (TemplateDoesNotExist), PanelSetPasswordForm (cambio forzado sin old_password), sidebar PDFs visible para SUPERVISOR. |
| 007    | 2026-05-01 | Nuevo trabajo   | Via B STT validada E2E: motor reemplazado de MediaRecorder a Web Speech API nativa. WorkOrderEntrySTTExtractView.post() refactorizado: recibe JSON transcript, usa response_mime_type=application/json + response_schema + thinking_budget=0. |
| 008    | 2026-05-01 | Calidad datos + UX editor | Auditoria exhaustiva de 441 WorkOrderEntryLine. Diseno de mapa de confusion simetrico bidireccional. PMA services.py: _OCR_CONFUSION_MAP, _resolve_machine_asset ampliado con algoritmo de candidatos morfologicos por niveles. Neonato repair_entry_lines.py con tres reglas deterministicas. Ejecucion --apply: 2 lineas R1, 7 lineas R2 explosionadas en 14 nuevas, 36/72 lineas R3 resueltas. UX editor: columna Flags eliminada; badge de jornada diaria en cabecera de grupo (day_total + day_css). |
| 009    | 2026-05-04 | Deuda tecnica + fix OCR inverso + Regla 4 | Renombrado completo de 6 campos a ingles. Migracion 0007_rename_fields_english aplicada. Fix OCR inverso: _OCR_DIGIT_TO_LETTER_MAP en services.py. Regla 4 en repair_entry_lines.py: re-normaliza machine_norm en lineas ya resueltas. Ejecucion --apply: 47 machine_norm actualizados. |
| S048   | 2026-06-17 | Fix desvío H7  | Incidencia: botón editor de fecha inline en edit.html no respondía al pulsar (regresión por merge). Causa: el handler JS del toggle (btn-date-edit-toggle / btn-date-cancel) se había perdido del bloque <script> de edit.html. El HTML en _entry_group_fragment.html y la vista WorkOrderEntrySaveDateView estaban correctos. Fix: añadido el bloque "Date editor toggle" al IIFE de edit.html antes del cierre }();. Archivo subido: EnterpriseBot_072_OUT.txt → edit.html. |
