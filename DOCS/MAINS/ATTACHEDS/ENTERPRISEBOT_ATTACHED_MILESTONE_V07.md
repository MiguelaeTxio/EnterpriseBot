# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md

# Anexo de Hito V07 — Partes Diarios de Reparación — Entrada Digital desde el Panel
# Proyecto: EnterpriseBot

---

## 1. Visión General del Hito

Implementación avanzada de múltiples vías de entrada de partes diarios de
reparación digital desde el panel de EnterpriseBot.

### Vía A — Formulario Web Estructurado
Formulario unificado con validación client-side y server-side. Flujo modal
de confirmación al cierre. Clasificación automática de averías vía Celery +
Gemini.

### Vía B — STT
ABANDONADO DEFINITIVAMENTE (S022).

### Vía C — Upload Gemini Vision
Upload de PDF escaneado procesado por Gemini Vision, con flujo de merge
con la Vía A (S033).

---

## 2. Arquitectura Actual del Módulo de Partes Digitales

### 2.1. Vista única de creación y edición (S045)

`WorkOrderEntryFormView` es la única vista de creación y edición de partes
digitales para todos los roles (WORKSHOP, SUPERVISOR, ADMIN).
`WorkOrderEditView` queda reservada exclusivamente para partes de origen
PDF histórico.

El antiguo "Gate 4" (detección automática de lagunas de jornada con
desvío a un `WorkOrder` borrador en estado `PENDING_GAPS`) fue **eliminado
por completo** en S045: se eliminaron `WorkdayGapResolutionView`,
`WorkOrderEntryMergeView`, las funciones `_detect_workday_gaps`,
`_detect_overlaps`, `_serialize_pending_lines`, y las rutas
`operator/gaps/` y `operator/merge/`. El "Camino B — Detección automática"
descrito en la Sección 4 de este anexo queda **OBSOLETO**: solo subsiste
el "Camino A — Declaración voluntaria".

### 2.2. Modal guardián de cierre (S045)

El modal de validación al cierre informa al operario de lagunas,
solapamientos y jornada incompleta (mínimo 8 h) sin permitir cerrar el
parte hasta corregirlos. El mensaje de jornada incompleta indica añadir
una tarea o justificar la ausencia con código PERSONAL en el campo
Máquina/Centro de Gasto. En jornada intensiva se permite añadir una tarea
vespertina siempre que se cumplan las 8 h.

Se añadió validación de fecha futura (rechazo de fechas posteriores a hoy)
en `WorkOrderEntryConfirmView` y `WorkOrderEntryFormView`, preservando los
datos introducidos al devolver el error. La detección de fecha duplicada
excluye correctamente los partes `IN_PROGRESS` propios y el parte en
edición.

### 2.3. Selector de ausencias PERSONAL — Camino A (S042/S043/S045)

Al introducir PERSONAL en el campo Máquina se despliega el selector de
`AbsenceCategory` (con foco automático). El campo de motivo solo se exige
cuando la categoría tiene `requires_note=True`. La validación
server-side y client-side exime la descripción de avería en tareas de
ausencia y exige en su lugar la categoría.

Backend: `_parse_entry_lines_from_post` lee
`entrada_{i}_absence_category`, resuelve `AbsenceCategory` y sobreescribe
`fault_description` con su label. `save_blocks` y `close_order` crean un
`WorkdayGap` sintético (`resolved=True`) con `gap_start=hc`, `gap_end=hf`,
`absence_category` y `note`.

Serialización de `absence_categories` a JSON válido (comillas dobles,
booleanos JS), desdoblada en `absence_categories` (JSON para EB_CONFIG) y
`absence_categories_list` (lista Python para el fragment).

### 2.4. Pausa de comida (S042/S043/S045)

El backend calcula el overlap de pausa de comida server-side en
`save_blocks` y `close_order` (fix I-BUG-A), eliminando la dependencia de
`lunch_overlap_N` del JS. Incluye recálculo de líneas ya persistidas
cuando el operario modifica la pausa tras haber guardado bloques.

Checkbox "No he parado a comer" en jornada partida (pausa activa por
defecto, se oculta al marcar) y checkbox "He parado a comer" en jornada
intensiva (pausa oculta por defecto, se despliega vacía al marcar, para
registrar averías de tarde). Reinicialización de la lógica tras cada swap
HTMX del fragment de horario. Campo `no_lunch_break` en `WorkOrderEntry`
(migración 0020).

### 2.5. Auto-relleno de horarios (S045)

Al añadir una tarea, la H.C. toma la H.F. de la tarea anterior; si esta
acabó al fin del periodo de mañana y hay pausa activa, la nueva tarea
arranca en el inicio de la tarde (`start_time_afternoon`). La H.F. toma el
fin del periodo donde cae la H.C. Es un prerrelleno orientativo y editable;
el modal guardián valida al cerrar.

### 2.6. Guardado progresivo por bloques (S040)

Estado `IN_PROGRESS` en `WorkOrder.Status` (migración 0021).
`WorkOrderEntryFormView` GET/POST rediseñado para guardado progresivo
(`save_blocks` / `close_order`), con retomar parte `IN_PROGRESS` al
acceder al formulario.

### 2.7. Nomenclatura unificada (S045)

Todo "bloque" visible en la interfaz pasó a "tarea" (Añadir tarea, Guardar
tareas, Eliminar tarea, Tarea N) en template, fragment, JS y mensajes de
validación de servidor y cliente.

### 2.8. Copia de seguridad en logs (S045)

Cada parte cerrado registra en el log del servidor una línea
`# [PARTE-BACKUP]` con el payload completo en JSON (fecha, operario,
pausa, y cada tarea con máquina, horas, O.R., avería, reparación y
ausencia), como copia de recuperación temporal.

### 2.9. Smoke test de validación (S045)

Batería de smoke tests (test client de Django, transacciones revertidas)
que verifica el bloqueo al cierre en los casos: fecha vacía, fecha futura,
tarea sin máquina, sin H.C., sin H.F., H.F. anterior a H.C., tareas
solapadas, sin descripción de avería y jornada incompleta (<8 h).
Resultado: 9/9 correctos. Entregado en SWAP.

---

## 3. Vistas de Historial y Ordenación (S044)

Ordenación por columna (parámetros GET `sort`/`dir`) implementada en:

- `WorkOrderEntryHistoryView` (Tab 1 — periodo actual; columnas
  fecha/num_bloques/horas_totales/reviewed).
- `WorkOrderAdminHistoryView` (pestañas Pendientes, Revisados e Histórico;
  columnas fecha/operator_name/horas_totales/reviewed).

Ambas vistas pasan `sort_col` y `sort_dir` al contexto del template.

---

## 4. Arquitectura Histórica I6 — Ausencias en Partes Diarios (anterior a S045)

> **Nota:** el "Camino B" descrito aquí quedó OBSOLETO en S045 (ver
> Sección 2.1). Se conserva como referencia histórica del diseño original.

### Camino A — Declaración voluntaria (operario)
El operario añade un bloque con activo PERSONAL en el formulario. Ver
Sección 2.3 para el estado vigente (sigue activo).

### Camino B — Detección automática (Gate 4) — OBSOLETO
Gate 4 detectaba huecos de jornada → creaba `WorkdayGap` sin resolver →
redirigía a `WorkdayGapResolutionView`. Al resolver un gap estándar, además
de actualizar el `WorkdayGap`, se creaba una `WorkOrderEntryLine` con
`machine_asset=PERSONAL`, `fault_description=absence_cat.label`,
`hc=gap_start`, `hf=gap_end`. Eliminado por completo en S045.

---

## 5. Arquitectura Circular WhatsApp por Secciones (S043)

### Campo `Section.is_broadcast_enabled`
Migración `ivr_config 0032`. Controla qué secciones son candidatas para
circulares masivas. Por defecto `False`. El ADMIN lo activa por sección
desde el formulario de edición de sección.

### Flujo `group_broadcast`
1. ADMIN escribe mensaje y pulsa "Enviar circular".
2. Modal Bootstrap lista secciones con `is_broadcast_enabled=True`.
3. ADMIN selecciona secciones y confirma.
4. Backend itera contactos activos de cada sección:
   - Dentro de ventana 24h (`WhatsAppSession.last_message_at >= now-24h`):
     `send_reply` directo.
   - Fuera de ventana: `chat_session_renewal` + mensaje encolado en
     `WhatsAppSession.pending_broadcast_messages` (JSONField, migración
     `whatsapp 0004`).
5. En `opt_in` del webhook: entrega de `pending_broadcast_messages` con
   expiración 48h + creación de `ChatMessage OUTBOUND` en la sala de la
   sección.

---

## 6. Migraciones Aplicadas

| App | Número | Nombre | Descripción |
|---|---|---|---|
| panel/work_order_processor | 0020 | — | Campo `no_lunch_break` en `WorkOrderEntry`. |
| panel/work_order_processor | 0021 | — | Estado `IN_PROGRESS` en `WorkOrder.Status`. |
| ivr_config | 0032 | add_section_is_broadcast_enabled | Campo `BooleanField is_broadcast_enabled` en `Section`. |
| whatsapp | 0004 | add_pending_broadcast_messages | Campo `JSONField pending_broadcast_messages` en `WhatsAppSession`. |

---

## 7. Registro de Sesiones

| Sesión | Fecha | Resumen |
|---|---|---|
| S001-S039 | — | Historial extenso preservado en versiones anteriores del anexo (no migrado a este formato). Incluye: formulario multi-bloque Vía A (S016), Gate 4 validación de jornada (S018), flujo de merge Gate 0 (S020), abandono definitivo de Vía B / STT (S022), clasificación de tipología de averías por Celery+Gemini (S024), vistas de supervisor — períodos/ausencias/horarios (S028), historial de operario de 4 pestañas (S030), Vía C Upload Gemini Vision (S033), dispositivo de confianza con flujo forzado (S038), menú de ayuda WhatsApp implementado pendiente E2E y correcciones de navegación digital/Excel digital (S039), permisos `WorkshopRequiredMixin` (S002-SB). |
| S040 | 2026-05-27 | Fix GAP comida, horas negativas, no_lunch_break y guardado progresivo por bloques. Corrección del falso positivo de GAP entre bloques mañana+tarde (validators.py + views.py). Corrección de horas extra negativas en operario sin partes. Campo `no_lunch_break` en WorkOrderEntry (migración 0020) con checkbox en jornada partida. Guardado progresivo por bloques con estado IN_PROGRESS (migración 0021), rediseño de WorkOrderEntryFormView GET/POST, Gate 0 actualizado. Sesión cerrada con incidencia CSS sin resolver. |
| S041 | — | Fix CSS `eb-field`/`field-flagged`/`field-optional`. |
| S042 | 2026-06-04 | Fix CSS eb-field, pausa comida retomar y HC/HF por defecto en bloques nuevos. I1 confirmado (ya resuelto en S041). I2: fix pausa de comida en modo retomar (views.py GET, placeholders XX:XX sustituidos por valores reales de _ip_first_entry). I3 verificado (HC/HF por defecto ya implementado). I4: configuración de empresa — eliminados textareas obsoletos de bases y calendario laboral, sustituidos por tablas en vivo de Base y WorkdaySchedule con botones de gestión. I6 parcial: activo PERSONAL creado en BD vía seed_personal_asset, contexto absence_categories y personal_asset_code añadido al formulario, JS _toggleAbsenceMode/_adjustRepairNotes/_buildBlockRow implementados, pendiente backend. Corrección en BD de 10 partes digitales con delta_hours sin descuento de comida (fix_digital_lunch_deduction, fix_all_digital). Diagnóstico de I-BUG-A (descuento pausa comida debe calcularse server-side) e I-BUG-B (redirección a historial digital tras guardar). |
| S043 | 2026-06-04 | Fix pausa comida server-side, redirección digital, backend ausencias y circular WhatsApp por secciones. I-BUG-A resuelto: cálculo server-side del overlap de pausa de comida en save_blocks y close_order, con recálculo de líneas previas al modificar la pausa. I-BUG-B resuelto: redirección a /panel/work-orders/digital/ tras guardar parte, condicional al rol. I4: WorkOrderEditView migrado a WorkshopRequiredMixin con guardia de acceso, título condicional y redirecciones por rol. I6 completado: backend de _parse_entry_lines_from_post para absence_category, WorkdayGap sintético en save_blocks/close_order para bloques PERSONAL, WorkdayGapResolutionView crea WorkOrderEntryLine PERSONAL al resolver gaps automáticos, fix de serialización JSON de absence_categories. Incidencias detectadas y resueltas en pruebas: FieldError en BotManagementView por lookup inválido de workshop_family (código muerto, eliminado); rediseño de group_broadcast con is_broadcast_enabled (migración ivr_config 0032), modal de selección, ventana 24h con pending_broadcast_messages (migración whatsapp 0004) y entrega en opt_in con registro en sala de chat; fix de activación de usuarios WORKSHOP inactivos desde panel. |
| S044 | 2026-06-04 | Ordenación por columnas en historial de partes digitales y pivotaje a Hito 19. Implementada ordenación por columna (GET sort/dir) en WorkOrderEntryHistoryView (Tab 1) y WorkOrderAdminHistoryView (3 pestañas), ambas pasando sort_col/sort_dir al contexto. Se debatió la exportación Excel y se concluyó que el alcance correcto es un motor de exportación por plantillas (modelo ExportTemplate en work_order_processor, filtro por familia de avería, búsqueda libre en fault_description+repair_notes, acción desmarcar revisado, sustitución completa del sistema de exportación existente). Todo ello promovido al Hito 19. **Hito 7 queda PAUSADO en este punto.** |
| S045 | 2026-06-13 | Eliminación del Gate 4, vista única de partes digitales y refuerzo de validación al cierre. Sesión incidencia del Hito 7 atendida por desvío mientras el hito EN PROGRESO era el Hito 18 (Gestión de Mapas y Geolocalización). Reingeniería completa del flujo de creación/edición: eliminación total del Gate 4 (WorkdayGapResolutionView, WorkOrderEntryMergeView, funciones _detect_workday_gaps/_detect_overlaps/_serialize_pending_lines, rutas operator/gaps/ y operator/merge/); vista única WorkOrderEntryFormView para todos los roles, WorkOrderEditView reservada a partes PDF históricos (recuperada estructura de form_entry.html del commit 76c184a, previo al Gate 4); validación de fecha duplicada corregida (excluye IN_PROGRESS propios y parte en edición) y validación de fecha futura añadida; modal guardián de cierre (lagunas, solapamientos, jornada <8h, con guía de tarea PERSONAL); selector de ausencias con foco automático y validación condicional por requires_note, fix de serialización JSON de absence_categories; pausa de comida según tipo de jornada con checkboxes "No he parado a comer"/"He parado a comer" y reinicialización tras swap HTMX; auto-relleno de horarios al añadir tarea; unificación de nomenclatura "bloque"→"tarea"; copia de seguridad por log `# [PARTE-BACKUP]`; smoke test 9/9. Archivos: panel/views_operator.py, panel/views.py, panel/urls.py, form_entry.html, _schedule_fields_fragment.html, form_entry_assets.js. Detalle del desvío anotado también en el anexo del Hito 18. |
| S046 | 2026-06-15 | Fix validators.py/views_operator.py (lunch_window desacoplado), fix Android asset-search y reset contraseña Fontalba. Sesión incidencia del Hito 7 atendida por desvío mientras el hito EN PROGRESO era el Hito 18. **Fix lunch_window (Paso 46):** desacoplada la ventana de comida hardcodeada en `validators.py` — eliminadas constantes `_LUNCH_WINDOW_START_MIN/_LUNCH_WINDOW_END_MIN`; `_is_lunch_gap` recibe ahora `lunch_window` (devuelve False si None); `validate_intra_gaps` y `run_intra_part_validation` propagan el parámetro. En `views_operator.py` (WorkOrderEntryFormView.post, ~línea 2873): añadido bloque de resolución de `_lunch_window` a partir de `_lb_start/_lb_end/_no_lunch_break` (turno declarado) o `WorkdaySchedule.end_time_morning/start_time_afternoon` si no es jornada intensiva. WorkOrderEntryConfirmView.post (~línea 1417, Vía C/PDF) no tocado — sigue pasando lunch_window=None. Ambos archivos verificados con py_compile OK, sftp put confirmado (validators.py 30 KB, views_operator.py 172 KB), backups SWAP .v01 ejecutados. Reload con timeout (ReadTimeout 15s) — timeout conocido de la API de PythonAnywhere que no implica fallo; webapp verificada como operativa. Workaround de WO #162 / entry #1412 (bloque único ficticio 07:00-21:30, Pablo Cañamero, 2026-06-10) pendiente de revertir/recalcular en caliente cuando se confirme el fix en producción. **Fix Android asset-search:** el campo `.asset-search` no disparaba el desplegable de búsqueda en Android (teclado virtual IME, keyCode 229, no propagaba evento `input`). Fix: añadido listener `keyup` como fallback en `attachAutocomplete` de `form_entry_assets.js` (`input.addEventListener("keyup", _onInputChange)`), junto al listener `input` ya existente. Verificado en consola Eruda: dropdown funciona con búsqueda "G1" mostrando G10-G16. **Reset contraseña Fontalba:** contraseña de Antonio Fontalba restablecida a `1234` vía shell interactiva Django (`set_password`), con flag `must_change_password=True` para forzar cambio en el primer login. |
| S049 | 2026-06-17 | Paso 49: plantillas de exportación compartidas por empresa. `is_global` + `company` en `ExportTemplate`, migración 0024, vistas CREATE/UPDATE/LIST ampliadas, modal de gestión inline en `admin_history.html`, JS estático `export_templates.js`, fix lookup en `WorkOrderAdminExportByTemplateView`. Skills de nomenclatura `_GET`/`_PUT` actualizadas (9 skills). |
| S048 | 2026-06-17 | Sesión de continuación H07 con desvíos a H08 y mejoras en WorkOrderAdminHistoryView. **Desvío H08:** fix regresión editor fecha inline en edit.html — el handler JS (btn-date-edit-toggle/btn-date-cancel) se había perdido del IIFE en un merge; añadido antes del cierre }();. **Fix duplicación entries (H07):** restaurado work_order.entries.all().delete() antes de work_order.status=DONE en bloque if _reuse_wo is not None de close_order en views_operator.py. Entries WO#172 y WO#173 verificadas limpias (1 entry cada una). **Botón eliminar tarea en modo edición:** añadido btn-remove-block-static con data-block-id en bloques server-side de form_entry.html; handler en form_entry_assets.js (row.remove() + decremento numEntradasInput + e.preventDefault()/stopPropagation()). **Columna H. Extra en WorkOrderAdminHistoryView:** campo horas_extra=max(0,horas_totales-8) añadido a _enrich_work_orders en views_workorders.py; columna H. Extra con badge verde (+Xh) en las tres pestañas de admin_history.html; horas_extra añadida a _VALID_SORT_COLS y al sort-stack JS de admin_history.js (initBulkGroup("reviewed") también añadido). **Colores horas extra:** overtime-positive → verde en operator/history.html; lógica negativo eliminada. **Selección múltiple revisados:** initBulkGroup("reviewed") faltaba en admin_history.js. **H. Extra en plantillas exportación:** horas_extra añadida a COLUMN_DEFS de build_export_from_template en services.py y a column_choices en views_workorders.py. **Autoajuste columnas Excel:** función _autofit_columns añadida en services.py, aplicada en single_sheet y multi_sheet. Skill enterprisebot-annex-v08 creada. Skill com-edit creada (sin backup SWAP). |
| S050 | 2026-06-18 | Desvío H07 durante sesión H14. **Fix NoReverseMatch digital_list.html:** eliminado `<li>` con `{% url 'panel:work_order_export' wo.pk %}` de la pestaña Revisados (URL no acepta pk). **Fix autocomplete máquina form_entry_assets.js:** input muestra label completo al seleccionar (`B43 — PALFINGER PK 72002`) como confirmación visual; servidor resuelve el activo aunque llegue el label completo (pasadas 3-4 en views_operator.py: regex extrae código antes de ` — `, fallback por brand_model). Regresión intermedia detectada y corregida en la misma sesión. |
| S051 | 2026-06-19 | **Fix I-S007:** pausa de comida no editable en modo edición. Causa raíz: `form_entry.html` condicionaba el `{% include "_schedule_fields_fragment.html" %}` con `{% if not entradas_enriched %}`, omitiendo el fragment completo en modo edición. Fix: eliminada la guarda exterior — el fragment se incluye siempre; guarda interna protege el bloque-1 dinámico. Smoke test OK. **Desactivación Vía C (Upload/Gemini Vision):** tarjeta eliminada de `dashboard.html`, URLs `operator/upload/` y `operator/confirm/` comentadas en `urls.py`. Código preservado para reactivación futura. PCH ejecutado: H07 → H03 + H14. |
| S_H07_02 | 2026-06-22 | **S_H07_01 — Fix edición admin de partes digitales.** (1) `_enrich_work_orders` en `views_workorders.py`: añadido `"source": wo.source` al dict enriquecido. (2) `admin_history.html`: botón "Editar / Revisar" condiciona la URL según `wo.source` — `DIGITAL`/`GENERATED` → `operator_form_edit`; PDF → `work_order_edit`. (3) `WorkOrderEntryFormView.get`: filtro `uploaded_by=cu` suprimido para `ADMIN`/`SUPERVISOR`; redirect de error corregido a `work_order_admin_history`. (4) `WorkOrderEntryFormView.post` (close): mismo fix en bloque `edit_wo_pk`. **Fix pausa de comida invisible en jornada intensiva.** En modo edición GET, `_show_lunch_edit` ignoraba `first_entry.lunch_break_start/end`. Fix: Prioridad 1 — leer pausa real del parte guardado (independientemente del tipo de jornada); Prioridad 2 — fallback al horario base para jornada partida sin pausa guardada. Añadido `no_lunch_break` al `context.update`. **Fix redirección tras guardar como admin.** (a) `save_blocks`: `WORKSHOP` → `/panel/operator/form/`; `ADMIN`/`SUPERVISOR` → `work_order_admin_history`. (b) Overlap: `ADMIN`/`SUPERVISOR` redirigen a `work_order_admin_history` en lugar de render de `form_entry.html`. Archivos: `panel/views_workorders.py`, `panel/templates/panel/work_orders/admin_history.html`, `panel/views_operator.py`. py_compile/djlint OK. Reloads 200 OK. PCH: H07 → H17. |

---

| S_H07_05 | 2026-06-23 | **Implementación is_on_site, has_diet y dropdown EMPRESA_* en partes digitales.** [1] `WorkOrderEntryLine.is_on_site` (BooleanField, nivel bloque) + `WorkOrderEntry.has_diet` (BooleanField, nivel parte) añadidos a `work_order_processor/models.py`; migración `0026_workorderentry_has_diet_and_more` generada y aplicada. [2] `panel/views_operator.py`: `_parse_entry_lines_from_post` lee `entrada_{i}_is_on_site` y `empresa_subtype` del POST; ambas rutas de persistencia (save_blocks + close_order) pasan `is_on_site` a `WorkOrderEntryLine.create`; close_order lee `has_diet` y lo pasa a `WorkOrderEntry.create`; GET inyecta `empresa_subtypes` (dict código→lista subtipos) en contexto para paths creación + in_progress. Fix residual H17: `room__company=company` → `company=company` en query `BreakdownTicket` de `_get_context_base`. [3] `form_entry.html`: checkbox `has_diet` en card de jornada; wrapper `empresa-selector-wrap` en bloques server-rendered; `empresaSubtypes` en `EB_CONFIG`. [4] `_schedule_fields_fragment.html`: wrapper `empresa-selector-wrap-1` + checkbox `is_on_site` añadidos al primer bloque (Tarea 1). [5] `form_entry_assets.js`: `_toggleEmpresaMode(idx, isEmpresa, assetCode)` implementada (oculta avería, muestra select subtipo, repair_notes como nota obligatoria); detección `EMPRESA_*` en autocomplete handler; wrappers en template JS de bloque dinámico. [6] `seed_empresa_assets.py` reescrito: desactiva `EMPRESA_ALMACEN` genérico; crea 4 activos ALMACEN_* (`EMPRESA_ALMACEN_MECANICO`, `EMPRESA_ALMACEN_ELEVACION`, `EMPRESA_ALMACEN_HUELVA`, `EMPRESA_ALMACEN_DEPENDENCIAS`); define `EMPRESA_SUBTYPES` (taller/dependencias: Orden y limpieza/Reparación/Otros; almacén: +Inventario) y `get_empresa_subtype_group`. Seed ejecutado: 4 creados, EMPRESA_ALMACEN desactivado. collectstatic + reload 200 OK en todos los despliegues. |
| S_H07_04 | 2026-06-22 | Sesión de desvíos masivos desde H07 (enrutador marcaba H07 EN PROGRESO, PCH H07→H17 pendiente). 12 incidencias de producción resueltas. **[1]** fix `form_entry_assets.js` `_applyMeterFields`: `_canPrefill()` evita sobreescribir lecturas de km/horas que el operario modifica manualmente. **[2]** fix visibilidad campos km/horas en modo edición: meter-divs revelados server-side en `form_entry.html` con `{% if entrada.machine_asset.has_odometer %}`; on-load JS extrae código limpio del label y preserva valores del servidor. **[3]** fix `digital_list.html` corrupto (TemplateSyntaxError línea 311): pestaña Pendientes truncada desde commit 379fc76, reconstruido bloque completo (20 líneas añadidas, 624 total). **[4]** fix `import_machine_catalog.py`: `mileage`/`hours` excluidos de `defaults` en `update_or_create` — solo se aplican en creación; activos existentes preservan lecturas reales. **[5]** corrección manual `WorkOrderEntryLine` pk=3056 (WO#216 Fontalba 22/06): `odometer_reading` 995270→117515 vía shell Django. **[6]** `MachineAsset` A58: `mileage` corregido a 117515 vía shell Django. **[7]** `validators.py` R6/R7: lectura menor convertida de error bloqueante a warning confirmable via `meterWarningModal`; cualquier discrepancia (< o > threshold) es warning. **[8]** fix Gate0 fecha duplicada en edición admin: el ADMIN tenía un parte de prueba para 22/06 — eliminado manualmente. **[9]** `form_entry.html` enlace "Volver al historial" y botón Cancelar: discriminan por rol (`WORKSHOP`/`WORKSHOPBOSS`→`operator_history`, resto→`digital_work_order_list`). **[10]** `digital_list.html` (con dropdown) borrado — era una copia corrupta generada al reconstruir el template truncado. **[11]** `views_operator.py`: 3 redirects y `_elevated_url` fallback cambiados de `work_order_admin_history`/`digital_work_order_list` a `operator_history`. **[12]** `budgets/views.py` `InsurerUpdateView.get`: `night_schedules` añadido al contexto (faltaba en el dict de `_build_base_context`). Archivos: `form_entry_assets.js`, `form_entry.html`, `digital_list.html` (eliminado), `import_machine_catalog.py`, `validators.py`, `views_operator.py`, `views_workorders.py`, `budgets/views.py`. |
| S_H07_06 | 2026-07-02 | **Fix H07 PASO 0 — pausa de comida y checkbox no persisten en modo edición (wo_pk).** Causa raíz confirmada en `panel/views_operator.py`: la rama de edición `wo_pk is not None` (WorkOrder DIGITAL/GENERATED, reviewed=False) construía `lunch_break_start`/`lunch_break_end` exclusivamente desde `_schedule_edit` (fallback WorkdaySchedule), ignorando `first_entry.lunch_break_start/end`; el fix de S_H07_02 solo se había aplicado a la rama paralela `in_progress` (`_ip_first_entry`), nunca a esta. Solo se manifestaba en jornada partida porque es la única rama donde el fallback de horario realmente rellena algo (en intensiva ese bloque nunca setea `_lunch_start_edit`/`_lunch_end_edit`). Fix: mismo patrón de prioridad que la rama in_progress — `lunch_break_start`/`lunch_break_end` priorizan el valor real guardado (`first_entry.lunch_break_start/end`), con fallback al horario base solo si no hay valor guardado. Añadido también `no_lunch_break` al contexto de esta rama (ausente hasta ahora). Segundo hallazgo relacionado, mismo bloque: `_schedule_fields_fragment.html` renderizaba los checkboxes `id_no_lunch_toggle`/`id_had_lunch_toggle` sin atributo `checked` condicional — arrancaban desmarcados siempre, en ambas ramas de edición, ignorando el contexto Django. Fix: `id_no_lunch_toggle` con `{% if no_lunch_break %}checked{% endif %}`; `id_had_lunch_toggle` con `{% if lunch_break_start %}checked{% endif %}` (checked solo si hay pausa real guardada, ya que el fallback de horario nunca rellena `lunch_break_start` en intensiva). Eliminada `EB_CONFIG.noLunchBreak` en `form_entry.html` — hardcodeada a `false`, confirmado por grep que no se lee en ningún punto de `form_entry_assets.js` (código muerto). Archivos: `panel/views_operator.py`, `panel/templates/panel/operator/_schedule_fields_fragment.html`, `panel/templates/panel/operator/form_entry.html`. `form_entry_assets.js` solo se leyó, no se modificó. Verificado `py_compile`/`djlint` sin errores nuevos, `install_files` OK, reload `200 {"status":"OK"}`. Pendiente de confirmación funcional por Pablo Cañamero en producción — anotar resultado cuando llegue. Sesión con dos desvíos previos a H16 (ver anexo H16): fix `ProtectedError` en `InsurerCopyTariffView` (borrado+recreación de `VehicleType` sustituido por merge-por-nombre con desactivación — nunca se borra ninguna fila, ninguna relación PROTECT puede volver a bloquear la operación; mismo criterio aplicado a `VehicleTypeDeleteView`, que pasó de `.delete()` real a `is_active=False`) y fix 405 al borrar aseguradora tras búsqueda HTMX en el listado (listener `show.bs.modal` movido de `DOMContentLoaded`/fragmento recargado por HTMX a delegación sobre `document.body` en `insurer_list.html`). Ambos fixes de H16 confirmados en real por Miguel Ángel. PCH ejecutado al cierre: H07 → H10 (Albaranes de Proveedores y Almacén de Repuestos). |
| S_H07_07 | 2026-07-07 | **NOTA DE DESVÍO desde H10 (EN PROGRESO) — incidente `TemplateDoesNotExist` en `/panel/work-orders/digital/`, SIN RESOLVER AL CIERRE.** Miguel Ángel reportó el error en producción durante una sesión de H10. Investigación con `git log --diff-filter`/`git show`/`git diff` sobre `panel/templates/panel/work_orders/digital_list.html`: el archivo nació en S026 (`67b8335`) y fue borrado en `S_H07_04` (`357b29f`, 2026-06-23) — **el propio registro de esa sesión (punto [10] de su fila en esta tabla) documenta que el borrado fue una decisión deliberada** ("copia corrupta generada al reconstruir el template truncado"), no un accidente puro como se asumió al principio de esta sesión. `DigitalWorkOrderListView` (`panel/views_workorders.py`) siguió referenciando el `template_name` borrado sin que nadie lo notara durante dos semanas. **Dos intentos de restauración, ninguno satisfactorio:** (1) reconstrucción desde cero (commit `2c78090`) — simplificada, sin la exportación Excel de 3 modos ni otras piezas históricas; sustituida al descubrir el historial real. (2) restauración fiel desde el último commit bueno anterior al borrado (`379fc76`, commit `df17e35`, con fix de icono en `b6a3a98`), reparando la misma truncación ya diagnosticada por `S_H07_04` en su punto [3] (verificado con `git diff 934d78a 379fc76` — el diff exacto que introdujo la truncación no toca la sección de exportación Excel, que permanece idéntica en ambos commits). **Pese a esto, Miguel Ángel confirma en producción que la pestaña Revisados sigue sin exportación (ni por selección ni individual), y describe además cómputo total de horas, indicador de dieta, y un dropdown de "Acciones" con tres opciones por fila — ninguna de estas tres últimas cosas aparece en NINGUNA versión de `digital_list.html` recuperable por Git** (verificado con `grep` en los tres snapshots disponibles: `934d78a` S050, `379fc76` S_H07_03, y el propio archivo restaurado — cero resultados para `total_hours`/`dieta`/`has_diet` en los tres). También verificado que `total_hours` sí existe en `views_workorders.py`, pero pertenece a `WorkOrderEntrySaveDateView` (editor de un parte, `edit.html`), no a `DigitalWorkOrderListView`. **Hipótesis principal para retomar, sin verificar todavía:** lo que Miguel Ángel recuerda pertenece a `admin_history.html`/`WorkOrderAdminHistoryView` (114 KB, vista de historial mucho más rica, con pestaña Períodos) y no a `digital_list.html` — comparar ambas plantillas línea a línea antes de tocar nada más. Sesión cerrada por Miguel Ángel con este incidente expresamente sin resolver, indicando que lo retomará otra sesión. Sin cambio de hito EN PROGRESO — H10 permanece `← EN PROGRESO` en el enrutador; este desvío no afectó a ningún paso de H10. Archivos tocados en este desvío: `panel/templates/panel/work_orders/digital_list.html` (creado y reescrito 3 veces), `panel/templates/panel/_nav_items.html` (nuevo ítem "Partes Digitales", este sí correcto y sin cuestionar). |

| S_H07_08 | 2026-07-07 | **RESOLUCIÓN del incidente `digital_list.html` (ver `S_H07_07` arriba) — causa raíz confirmada: no era un problema de la plantilla, sino que Miguel Ángel recordaba funcionalidad real de `admin_history.html`.** Miguel Ángel confirmó explícitamente: "es en el listado de PDF's históricos donde se exporta el Excel" — la hipótesis principal de `S_H07_07` era correcta. Verificado con `grep` que `WorkOrderAdminHistoryView` filtra **exclusivamente** `source IN (DIGITAL, GENERATED)` — es decir, "Historial" ya es en la práctica la vista de gestión rica para partes digitales; `digital_list.html`/`DigitalWorkOrderListView` es una vista paralela más simple, sin decisión de unificarlas (no solicitado). **Replicado en `digital_list.html`, no en Historial:** (1) columnas `horas_totales`/`horas_extra` + fila de totales en Pendiente y Revisados, mismo criterio de cómputo que `WorkOrderAdminHistoryView._enrich_work_orders()` (suma de `delta_hours` por entry, extra = max(0, total−8)), anotado como atributo directo sobre cada instancia `WorkOrder` en `DigitalWorkOrderListView.get()` con `prefetch_related('entries__lines')` para evitar N+1. (2) Modal de exportación antiguo (3 modos: digital_full/multi_sheet/single_sheet, restaurado en `S_H07_07` desde el histórico de Git de mayo) **sustituido por completo** por el modal "Exportar por plantilla" — mismo HTML/JS que `admin_history.html`, adaptado a los checkboxes `.chk-wo` propios de esta plantilla; mismo backend genérico `work_order_export_by_template`/`export_template_list`, sin cambios de vista de exportación (ya soportaba cualquier `WorkOrder` pk de la empresa independientemente del source). Explica por qué Miguel Ángel no reconocía el modal restaurado en `S_H07_07`: no estaba obsoleto por accidente, era una versión anterior ya reemplazada en el resto de la app por el sistema de plantillas (H19). **Dietas:** Miguel Ángel pidió explícitamente sumar el número de dietas por operario y periodo, y celdas de precio de hora ordinaria/extra en el Excel. Implementado en `work_order_processor/services.py`, `build_export_from_template()`: nueva columna `dietas` en `COLUMN_DEFS` (1 si `WorkOrderEntry.has_diet`, 0 si no — métrica de entry, se acumula una vez por entry igual que `horas_extra`) añadida a `NUMERIC_KEYS`; nuevo `_write_price_cells()` con dos celdas de entrada `PRECIO HORA EXTRA`/`COSTE HORA ORDINARIA` antes de la cabecera de columnas (cabecera desplazada a fila 3, datos desde fila 4), mismo patrón visual que `generate_work_order_excel` (C2/C3) — sin fórmulas de salario por fila, fuera de alcance de lo pedido, solo las celdas de entrada. `dietas` añadida también a las dos listas `column_choices` (`WorkOrderAdminHistoryView.get()` y `ExportTemplateListView.get()`) como columna seleccionable al crear/editar una plantilla, y a `dietas` en pantalla (columna + total) en `digital_list.html`, igual patrón que horas. **Filtro multi-operario:** a petición de Miguel Ángel ("filtrar por periodo y sacar la suma de horas extras según los operarios filtrados... sin exportar el Excel"), `operator_pk` (int único) sustituido por `operator_pks` (lista, `GET.getlist`) en `DigitalWorkOrderListView.get()`, filtro `uploaded_by__pk__in`; en la plantilla, el `<select>` único de operario pasa a un dropdown de checkboxes multi-selección con botón "Filtrar" explícito (los checkboxes no auto-submiten, evita un submit por cada clic al marcar varios). La fila de totales (ya existente) refleja automáticamente el subconjunto de operarios + periodo elegido, sin necesidad de exportar nada. Tres commits de código (`6045cc7`, `5481238`, `9b2ac14`). Archivos: `panel/templates/panel/work_orders/digital_list.html`, `panel/templates/panel/work_orders/admin_history.html` (solo `COLUMN_LABELS` del JS del modal compartido), `panel/views_workorders.py`, `work_order_processor/services.py`. Sin cambios de modelo (`has_diet` ya existía desde antes), sin migración, sin estáticos. Incidente `S_H07_07` cerrado y resuelto. Sin cambio de hito EN PROGRESO — H10 permanece `← EN PROGRESO`; este bloque fue íntegramente un desvío de sesión, sin afectar a ningún paso de H10 (ver nota de desvío añadida en el anexo H10, fila `S008`). |

| S_H07_09 | 2026-07-08 | **NOTA DE DESVÍO desde H10 (EN PROGRESO) — dos incidencias de producción sobre `admin_history.html`/`WorkOrderAdminHistoryView`, AMBAS RESUELTAS EN LA MISMA SESIÓN.** [1] **Columna Dieta ausente en el historial de administrador.** Miguel Ángel señaló que la pestaña de historial (Pendientes/Revisados/Histórico) no mostraba qué partes tenían dieta marcada ni el total del periodo filtrado. Fix: `_enrich_work_orders()` añade `wo["dieta"] = any(entry.has_diet for entry in entries_list)` (booleano por WorkOrder, cualquier entry con dieta marcada); `reviewed_totals["dietas"]` cuenta cuántos partes de la lista filtrada tienen dieta. Columna "Dieta" (badge o "—") añadida a las tres pestañas de `admin_history.html`, tras "H. Extra"; total de dietas añadido a la fila TOTAL de Revisados (única pestaña con fila de totales). [2] **Partes ya liquidados seguían apareciendo en Revisados.** Miguel Ángel señaló que un parte revisado, una vez su periodo queda liquidado (`WorkPeriod.is_closed=True`), no debería seguir en la pestaña Revisados — solo debe quedar visible en Histórico (que sí muestra todos los periodos sin filtrar). Fix: tras construir `reviewed_list`, se excluyen los partes cuya fecha cae dentro de un `WorkPeriod` liquidado (`is_closed=True`, `end_date` definido) del propio operario del parte — mismo criterio de rango de fechas que ya usaba `WorkPeriodLockView` para detectar partes sin revisar al liquidar un periodo. Periodos liquidados sin `end_date` (edge case del toggle individual) no filtran nada, mismo criterio conservador que el código ya existente. Pestaña Pendientes deliberadamente sin tocar: un parte sin revisar dentro de un periodo liquidado sigue apareciendo ahí, es justo el caso que el propio sistema ya avisa al liquidar. Dos commits de código. Archivos: `panel/views_workorders.py`, `panel/templates/panel/work_orders/admin_history.html`. Sin migración (ningún campo nuevo, solo cálculo). Sin cambio de hito EN PROGRESO — H10 permanece `← EN PROGRESO` en el enrutador durante todo el desvío (que ocurrió justo antes del PCH de cierre de la propia sesión S009 a H20); ver nota de desvío añadida en el anexo H10, fila `S009`. |
| S_H07_10 | 2026-07-14 | **DESVÍO desde H17 (EN PROGRESO al empezar la sesión) — fotos opcionales de tarea, nueva funcionalidad completa, a petición de Miguel Ángel.** Nuevo modelo `work_order_processor.TaskPhoto`: foto opcional en cualquier `WorkOrderEntryLine` (cualquier `tipo_tarea`, nunca obligatoria), con FKs denormalizados a `company`, `breakdown_ticket` y `machine_asset` tomados de la línea en el momento de creación — acceso directo a los tres vínculos pedidos (ticket, tarea/parte, centro de gasto) sin joins. Migración `0030_taskphoto.py`. Persistencia en Google Drive calcada de `spare_parts.DeliveryNote` (S014-H10): `spare_parts/gdrive_service.py` generalizado (`ensure_root_folder` acepta `folder_name`) + nueva función `upload_task_photo_file()` + nueva raíz `TASK_PHOTOS_ROOT_FOLDER_NAME` ('EnterpriseBot - Fotos de Tareas'), localizada/creada bajo demanda (sin variable de entorno dedicada, el modelo no puede escribir env vars nuevas en PythonAnywhere). Nueva tarea Celery `upload_task_photo_to_drive`. Nuevas vistas `panel/views_task_photos.py` (widget HTMX de subida/listado/borrado por línea), enganchadas en `form_entry.html` bajo cada tarea ya guardada (mismo patrón que el widget `ticket-resolution`). Galería añadida también a `breakdown_ticket_detail.html`. **Bug real corregido en el propio bloque:** `gdrive_service.py` usaba `machine_asset.company_code` (código de EMPRESA) en vez de `machine_asset.code` (código real de máquina) al nombrar el archivo en Drive — detectado releyendo `fleet/models.py`, corregido antes de producción con datos reales. **Error propio cometido y corregido en la misma sesión:** se creó `fleet.views.MachineHistoryView` (con URL/plantilla/sidebar propios) sin comprobar antes si ya existía algo equivalente — sí existía: `history.views.MachineHistoryView` (Hito 22, COMPLETADO). Revertido por completo (vista, URL, reexport, plantilla, enlace de sidebar, sin restos huérfanos) y fusionado en su lugar dentro de la vista real de H22 — ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V22.md`, fila S016, para el detalle completo de la fusión (historial de tickets + galería de fotos añadido a `history/views.py`, mixin ampliado a todos los roles). Un push sin migración con `MachineHistoryView` mal reexportada rompió el despliegue real (`ImportError`, confirmado con `manage.py check` en el servidor, log de Actions no descargable por estar fuera de la lista de dominios permitidos) — corregido en el mismo tramo, verificado con datos reales del servidor tras el fix. **Pendiente, sin verificar todavía:** una subida de foto real de principio a fin (local → Drive → thumbnail visible) — todo lo demás de este bloque se verificó con datos reales, esto no. Sesión desviada después a H23 (hito nuevo, ver ese anexo). |
| S_H07_11 | 2026-07-16 | **DESVÍO desde H24 (EN PROGRESO al empezar la sesión) — recuperación de dos partes "perdidos" (22/06 y 03/07) y nueva vista de Borradores.** Miguel Ángel reportó dos partes que parecían no haberse guardado. Verificado empíricamente que el log `# [PARTE-BACKUP]` (S045) sí funciona en producción (39 líneas reales en `error.log`, pese a que `settings.py` no tiene bloque `LOGGING` explícito — PythonAnywhere enruta igualmente el `logger.info()` de la app ahí). Filtrando por `work_date` dentro del JSON del log (no por la fecha en que se escribió la línea, que puede ser un día distinto) aparecieron los dos partes buscados (David Contreras 22/06 `wo_pk=299`, Antonio Fontalba 22/06 `wo_pk=316`, Pablo Cañamero 03/07 `wo_pk=322`) — verificado también en BD que los tres `WorkOrder` existen con `status=DONE` y el mismo número de líneas que el log. Confirmado por Miguel Ángel: Fontalba y Cañamero eran justo los dos que buscaba, y ya los había recuperado él mismo reintroduciéndolos a mano (por eso el `wo_pk`/fecha de log de ambos es de hoy y de ayer, no del día real del parte) — el mecanismo de log solo cubre "se guardó pero algo falló después", nunca "nunca se llegó a guardar". A raíz de esto, Miguel Ángel pidió un mecanismo para no depender solo de ese log — verificado que **ya existe** un guardado progresivo real en BD (`WorkOrder.Status.IN_PROGRESS` + botón "Guardar bloques" en `FormView.save_blocks`, sin usar hasta ahora desde Administración): nueva `WorkOrderDraftListView` (`/panel/work-orders/drafts/`) que lista esos `WorkOrder` sin cerrar, y nuevo `SuperuserRequiredMixin` (`panel/mixins.py`, basado en `request.user.is_superuser` de Django) para restringirla — sustituye de paso el antipatrón de username hardcodeado (`request.user.username == 'alvarez_admin'`) que vivía en `panel/_nav_items.html` para el enlace al Django Admin. `alvarez_admin` promovido a superusuario real de Django (`is_staff`/`is_superuser`, cambio de BD vía shell, no de código) — necesario tanto para esta vista nueva como para que el enlace ya existente al Django Admin (bloqueado hasta ahora por `CompanyUserAdminBlockMiddleware`) funcionara de verdad. **Error propio cometido y corregido en la misma sesión:** `WorkOrderDraftListView` se añadió a `views_workorders.py` pero se olvidó re-exportar en el fichero fino `panel/views.py` (arquitectura post-H21) — rompió el despliegue real (`ImportError`, confirmado con `manage.py check` vía Comando S, nunca dado por bueno ni por malo solo con el icono de Actions), corregido en el mismo tramo y verificado limpio en producción. Archivos: `panel/mixins.py`, `panel/views_workorders.py`, `panel/views.py`, `panel/urls.py`, `panel/templates/panel/_nav_items.html`, `panel/templates/panel/work_orders/draft_list.html` (nuevo). Sin migración (ningún modelo nuevo). Sesión desviada a H23 después de esto (ver ese anexo) — PCH ejecutado al cierre: H24 → H23. |
| S_H07_12 | 2026-07-21 | **DESVÍO desde H23 (EN PROGRESO al empezar S027) — 4 incidencias reales reportadas por Miguel Ángel en `WorkOrderAdminHistoryView`/`WorkOrderEntryFormView`, 3 resueltas con código nuevo, 1 verificada sin cambios.** Parte compartida con H17 (unificación S012) — ver también `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`, fila `S027`, para el detalle de la mitad correspondiente a `admin_history.html`. Piezas propias de H07 (`form_entry.html`/`views_operator.py`): **[1]** botón "Marcar revisado" para ADMIN/SUPERVISOR/WORKSHOPBOSS al editar/ver un parte digital — nuevo botón visible solo si `edit_mode and is_elevated`, nueva rama `form_action=mark_reviewed` al inicio de `WorkOrderEntryFormView.post()`, independiente y previa a todo el pipeline de parseo/guardado, sin tocar ni validar datos del formulario; JS en `form_entry_modal.js` (`btn-mark-reviewed`, mismo patrón que `btn-save-blocks`). **[2]** propagación de `back_url` (con todos los filtros activos) a `WorkOrderEntryFormView` y `WorkOrderDetailView` y de vuelta en todos sus redirects (guardado/cierre de parte, `mark_reviewed`, "Volver" de `detail.html`) — nuevo `panel/url_utils.py` (`safe_back_url`, previene open-redirect). **Hallazgo real fuera de alcance, corregido de inmediato (directriz 4.9):** `WorkOrderEntryFormView.get()` redirigía a `/panel/operator/history/`, URL eliminada en la unificación H17-S012 — 404 real cada vez que se disparaba esa rama (parte inexistente/ya revisado/ajeno); ahora redirige a `work_order_admin_history`. Verificado: `py_compile` (`views_workorders.py`, `views_operator.py`, `url_utils.py`) OK, `node --check` (`form_entry_modal.js`) OK. Limpieza posterior de los 12 avisos djlint preexistentes en `form_entry.html` (commit `6eb7bbb`, a petición de Miguel Ángel): 1 espacio doble sobrante en `value="SUPPLIER"` + 1 línea en blanco sobrante al final del archivo. **Confirmado por Miguel Ángel en producción: todo funciona correctamente**, ambos commits (`372faae`, `6eb7bbb`) verificados desplegados vía API de GitHub Actions (el primero con fallo real solo en el paso de recarga, corregido por el despliegue exitoso del segundo — ver `com-bash-commands`/`nfs-enterprisebot-edit` para el criterio de verificación). Commits sin migración. Sesión interrumpida por caída de herramientas del modelo antes de volver a H23 — cierre formal de S027 documentado retroactivamente en sesión posterior (S028). |
| S_H07_13 | 2026-07-22 | **DESVÍO desde H23 (EN PROGRESO, S028) — investigación de un bug real reportado por Miguel Ángel mientras esperaba el reinicio del worker Celery, SIN código tocado, solo diagnóstico.** "Cuando se editan los partes, no se está renderizando exactamente lo que la base de datos tiene... dietas, he parado/no he parado a comer, horario, pausa, si la jornada es intensiva". Confirmado con lectura directa del código (`panel/views_operator.py`, `WorkOrderEntryFormView`): en modo edición, `show_lunch_break` (si se muestran los campos de pausa) se calcula con `_resolve_operator_schedule(cu, company)` — el horario EN VIVO del operario, sin parámetro de fecha, nunca a partir de los datos reales del `first_entry` en edición. Si el horario del operario cambió desde que se guardó el parte, el formulario puede ocultar campos de pausa que sí existen en BD — y al guardar, como esos campos nunca llegan en el POST, `entry.lunch_break_start = None if _no_lunch_break else _lb_start` (líneas ~3560-3561/3579-3580) los sobrescribe con `None`: **riesgo real de pérdida de datos**, no solo de visualización. `no_lunch_break` sí lee bien de `first_entry`. Dietas/horario mencionados por Miguel Ángel como sospechosos pero sin auditar con el mismo detalle por falta de tiempo. Solución identificada (derivar `show_lunch_break` de los datos guardados del `first_entry`, nunca del horario en vivo) pero NO implementada — archivo muy denso, varias decenas de referencias a `lunch_break_start`/`lunch_break_end` en distintas rutas de guardado, Miguel Ángel decidió dejarlo anotado como primer punto de la próxima sesión de H07 en vez de arreglarlo con prisa: "no es cosa de dos minutos... prefiero ir con cuidado en vez de rápido" (dicho por el propio modelo, confirmado por Miguel Ángel: "aunque cuando lo resolvamos pasemos con lo que quede de lo que estamos haciendo ahora si no terminamos en esta sesión"). Ver detalle técnico completo en la Hoja de Ruta (sección 8) de este mismo anexo. Sin cambio de hito EN PROGRESO — H23 permanece `← EN PROGRESO` en el enrutador, este desvío no avanzó ningún paso de H23. |
| S_H07_14 | 2026-07-23 | **DESVÍO desde H23 (EN PROGRESO, S030) — cierre completo del bug de S_H07_13, con auditoría real de producción.** Corregido en `WorkOrderEntryFormView` (modo edición y modo reanudación de parte en curso): `show_lunch_break` pasa a derivarse de `first_entry`/`_ip_first_entry` (tiene `lunch_break_start`/`end` o `no_lunch_break=True` → fue partida; si no → intensiva), nunca del horario en vivo (commit `fc55e5c`). **Segundo hallazgo real del mismo origen, corregido en el mismo bloque:** `has_diet` no estaba en absoluto en el contexto de `get()` (ni edición ni reanudación) — el checkbox de dieta se veía siempre desmarcado al editar y se borraba al guardar, sin ninguna condición (peor que el de pausa, que solo fallaba si cambiaba el horario). Auditoría sistemática de todo `WorkOrderEntryFormView` aplicando el principio explícito de Miguel Ángel ("editar sin tocar nada debe grabar exactamente igual; la lógica de creación-vs-edición va en la vista, nunca en la plantilla"): encontrado un tercer punto, `first_block_hc`/`first_block_hf` en modo edición seguían calculándose del horario en vivo — sin causar daño real solo porque la plantilla los ocultaba con `{% if not entradas_enriched %}`, pero dependían de ese guard como única protección; fijados explícitamente a `""` en la vista en ambos modos (commit `749b795`). **Cuarto hallazgo, distinto pero mismo patrón, encontrado investigando la pregunta original de Miguel Ángel sobre repuestos sin vincular a máquina:** el selector "Bloque asociado" mostrado para repuestos ya guardados al editar no estaba conectado a nada (ni JS ni backend lo leían) — el contexto enviaba `vehiculo_raw=""` siempre para repuestos existentes, perdiendo su vínculo con la máquina en cada edición y regrabado, sin que el operario tocara nada. Corregido: se rellena con el código real de `spare.vehicle`, y el selector pasa a ser el mismo mecanismo ya probado de los repuestos nuevos (`repuesto_N_vehiculo_raw` + opción "Otro"), con `cdg_options` calculado en la vista (no en la plantilla, mismo commit `749b795`). **Auditoría de producción, a petición explícita de Miguel Ángel — comparación real contra logs, no solo heurística:** consulta ORM sobre 76 `WorkOrderEntry` con posible inconsistencia semanal de horario/pausa entre operarios, 19 avisos brutos; cruzados contra el log `# [PARTE-BACKUP]` (actual + 9 archivos rotados `.log.1`/`.log.2-9.gz`, cobertura real hasta el 21/06) para los 14 casos de `lunch_break_start=None` divergente. Resultado: **13 de 14 coincidían exactamente entre el guardado original en log y la BD actual — falsos positivos de la heurística, días reales sin pausa**; el único con discrepancia real entre log y BD (francisco.carvajal, 06/07, `wo_pk=269`, pausa 07:00–17:30 en el log) fue confirmado por Miguel Ángel como error de tecleo del propio operario corregido después a mano, no el bug. **Ningún parte de los 14 resultó víctima real del bug.** De paso, corregidos con datos reales los 15 `SparePartLine` con `vehicle=NULL` en tareas con máquina real detectados en la auditoría de repuestos (script dedicado, vehículo asignado desde la máquina real de su propia `entry_line`, verificados los 15 antes de tocar cada uno). **Hallazgo adicional del modal global de repuestos (H10, mismo desvío):** aviso real de Miguel Ángel probando en el propio parte — la tabla de resultados del modal "Añadir repuesto" no era usable en móvil (5 columnas, campo de cantidad inalcanzable sin scroll horizontal); rediseñada a lista apilada, mismo patrón que `_warehouse_search_results.html` (commit `6f28113`). Verificado en los cuatro commits: `py_compile`/`node --check` limpios; djlint no disponible en este workspace, balance de etiquetas comprobado a mano. Sin migración en ningún commit. Sesión desviada después a H23 (documentación de maquinaria) — ver ese anexo. |


---

## 8. Hoja de Ruta para la Siguiente Sesion

**Nota S_H07_14 (cierre del punto PRIORITARIO de S_H07_13):** el bug de
pérdida de datos al editar (pausa de comida, dieta, `first_block_hc`/hf,
y el hallazgo adicional de repuestos sin máquina) quedó corregido y
desplegado, con auditoría completa de producción sin daño real
encontrado. Ver Registro de Sesiones, fila `S_H07_14`, para el detalle
íntegro. Sin puntos pendientes propios de este bloque.

**Nota S_H07_12:** desvío puntual al empezar S027, sin deuda pendiente

propia — las 4 incidencias reportadas por Miguel Ángel quedaron
resueltas (o verificadas sin necesidad de cambio) y confirmadas en
producción por él mismo, sin ningún punto pendiente de verificación.

**Nota S_H07_11:** desvío puntual, sin deuda pendiente propia — la
vista de Borradores y el `SuperuserRequiredMixin` quedaron completos
y desplegados, verificados con `manage.py check` limpio.

Pendiente de S016 (fotos opcionales de tarea), sin prioridad sobre
nada del hito EN PROGRESO actual — retomar si Miguel Ángel lo pide:

- **Verificar una subida de foto real de principio a fin** (local →
  Drive → thumbnail visible en el widget y en la ficha del ticket) —
  única pieza de S016 sin verificar con datos reales.
- **Punto de navegación para WORKSHOP/DRIVER hacia la ficha de
  máquina** (`history:machine_history`, ya ampliada en S016 con
  galería de fotos) — hoy solo ADMIN/SUPERVISOR/WORKSHOPBOSS llegan
  desde `/panel/fleet/`; WORKSHOP y DRIVER no tienen ningún enlace
  propio todavía pese a que la vista ya les es accesible.
- Sin incidentes urgentes pendientes de antes de S016 — el de
  `digital_list.html` (`S_H07_07`) quedó resuelto en `S_H07_08` (ver
  fila arriba).

Sin pasos comprometidos pendientes. PASO 0 (pausa de comida no
persiste en jornada partida) resuelto en S_H07_06 — pendiente
únicamente de confirmación funcional de Pablo Cañamero en producción
(probará el fix en el uso real y reportará el resultado). Si reporta
algún fallo, retomar empezando por `panel/views_operator.py` líneas
~2198-2219 (rama `wo_pk is not None`) y
`panel/templates/panel/operator/_schedule_fields_fragment.html`
(checkboxes `id_no_lunch_toggle`/`id_had_lunch_toggle`).

Trabajo futuro sugerido (no comprometido, sin cambios respecto a
sesiones anteriores):

- **Validación EMPRESA_*** — añadir al Gate 1 de
  `_parse_entry_lines_from_post` una comprobación de que
  `empresa_subtype` no llegue vacío cuando la máquina tiene prefijo
  `EMPRESA_`. Explicado a Miguel Ángel en S_H07_06 y pospuesto por
  decisión suya — no hay incidencia real reportada en pruebas, no
  urgente. Retomar cuando convenga o cuando se detecte el fallo en
  producción.
- **Exportación Excel** — columna `is_on_site` todavía sin añadir a
  `COLUMN_DEFS`/`column_choices` (`dietas`/`has_diet` ya se añadió en
  `S_H07_08`). `empresa_subtype` sigue pendiente también.
- **Analítica** — `is_on_site` sigue siendo candidata a dimensión en
  el Laboratorio de Análisis (H20). `has_diet` ya tiene una primera
  aplicación real (columna Dietas + suma en `digital_list.html` y en
  el export por plantilla, `S_H07_08`) — evaluar si conviene también
  como dimensión propia en H20 más adelante.
- **Salario por fórmula en el export por plantilla** — las celdas de
  precio (`PRECIO HORA EXTRA`/`COSTE HORA ORDINARIA`) añadidas en
  `S_H07_08` son solo de entrada, sin fórmulas de salario por fila
  conectadas (a diferencia de `generate_work_order_excel`, que sí las
  tiene). Si Miguel Ángel lo pide, es la continuación natural.

---

## 9. Registro adicional — S_H07_03 (2026-06-22, desvíos desde H12)

Cuatro incidencias de H07 resueltas por desvío durante la sesión H12:

**[1] Fix permisos SUPERVISOR en WorkOrderEntryFormView:** Carolina (SUPERVISOR)
recibía 403 al editar partes digitales desde el historial de taller.
`WorkOrderEntryFormView` usaba `WorkshopRequiredMixin` ({WORKSHOP,WORKSHOPBOSS,ADMIN}).
Solución: nuevo mixin `WorkOrderFormAccessMixin` en `panel/mixins.py`
({WORKSHOP,WORKSHOPBOSS,SUPERVISOR,ADMIN}), aplicado a `WorkOrderEntryFormView`
en `panel/views_operator.py`. Import actualizado.

**[5] Filtros persistentes + periodos en historial:** (a) `digital_list.html`:
hidden input `tab` en form GET, pestañas con onclick, show/active server-side.
`DigitalWorkOrderListView`: `active_tab` leído de GET param. (b)
`WorkOrderAdminHistoryView`: `period_operator_groups` añadido al contexto —
pestaña Períodos del historial de taller ahora muestra todos los periodos. (c)
`WorkOrderEditView`: `back_url` leído de `?back=` GET param; campo hidden
`back_url` en form regenerate de `edit.html`; POST redirige al `back_url`.

**[6] Redirect correcto tras guardar en WorkOrderEntryFormView:** Los redirects
de SUPERVISOR/ADMIN iban hardcodeados a `work_order_admin_history` ("vista rara").
Solución: `_elevated_url` en el POST (lee `back_url` del hidden o fallback a
`digital_work_order_list`). Los 3 puntos de redirect sustituidos. `form_entry.html`:
campo hidden `back_url` añadido con `{% if back_url %}`.

**[7] WorkPeriod.is_closed — periodos liquidables:** `end_date` causaba que
periodos con fecha de fin aparecieran como "cerrados". Nuevo campo
`is_closed=BooleanField(default=False)` en `ivr_config/models.py` (migración
`0036` generada y aplicada). `has_open` basado en `is_closed=False`. Nueva
`WorkPeriodLockView` (ADMIN, toggle `is_closed` por pk). Guards en
`WorkOrderEditView.get` y `WorkOrderEntryFormView.get` bloquean edición en
periodos liquidados. Templates con columna Estado badge Activo/Liquidado y
botón Liquidar/Reabrir solo para ADMIN.

Archivos modificados: `panel/mixins.py`, `panel/views_operator.py`,
`panel/views_workorders.py`, `panel/views.py`, `panel/urls.py`,
`ivr_config/models.py`, `digital_list.html`, `edit.html`, `form_entry.html`,
`admin_history.html`, `work_period_list.html`.
