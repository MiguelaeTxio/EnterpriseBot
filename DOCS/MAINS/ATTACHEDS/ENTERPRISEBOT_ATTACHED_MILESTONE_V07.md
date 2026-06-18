---
name: enterprisebot-annex-v07
description: "Anexo del Hito 7 de EnterpriseBot (Partes Diarios de Reparación — Entrada Digital desde el Panel). Contiene el historial completo de sesiones y la arquitectura del módulo de partes digitales: formulario unificado WorkOrderEntryFormView, vista única de creación/edición, validación al cierre (modal guardián), selector de ausencias PERSONAL, circulares WhatsApp por sección y migraciones de ivr_config/whatsapp asociadas. Activar cuando el enrutador de anexos indique que el Hito 7 está EN PROGRESO, cuando se necesite consultar WorkOrder/WorkOrderEntry/WorkOrderEntryLine/WorkdayGap/AbsenceCategory, el formulario form_entry.html, el flujo de circulares group_broadcast/pending_broadcast_messages, o cuando el cierre de sesión (v00-pcs) invoque este anexo."
---

# ENTERPRISEBOT — ANEXO HITO 7
# Partes Diarios de Reparación — Entrada Digital desde el Panel

---

## ═══════════════════════════════════════════
## PARTE 1 — COMPORTAMIENTO DE LA SKILL
## ═══════════════════════════════════════════

### RUTA EN PYTHONANYWHERE

```
/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md
```

### ACTIVACIÓN

Esta skill se activa en dos casos:

1. **El enrutador de anexos** indica que el Hito 7 está EN PROGRESO (caso
   normal) o que hay un desvío de sesión hacia H7 (Caso A — incidencia
   fuera del hito EN PROGRESO).
2. **Cualquier skill o sesión** necesita consultar la arquitectura del
   módulo de partes digitales: `WorkOrder`, `WorkOrderEntry`,
   `WorkOrderEntryLine`, `WorkdayGap`, `AbsenceCategory`, el formulario
   `form_entry.html` / `form_entry_assets.js`, las vistas
   `WorkOrderEntryFormView` / `WorkOrderEditView` /
   `WorkOrderEntryHistoryView` / `WorkOrderAdminHistoryView`, o el flujo de
   circulares WhatsApp por sección (`group_broadcast`,
   `pending_broadcast_messages`, `Section.is_broadcast_enabled`).

### PROTOCOLO DE CIERRE — LO QUE HACE ESTA SKILL AL SER INVOCADA POR PCS

Al cierre de sesión, si se ha trabajado en este hito (EN PROGRESO o por
desvío — Caso A del enrutador):

#### PASO 1 — Redactar el registro de sesión

Nueva fila en la tabla `## 7. Registro de Sesiones` con el número
siguiente al último registrado (actualmente S045). Si la sesión fue un
desvío (Caso A), indicarlo explícitamente en la columna "Resumen" —
incluyendo de qué hito EN PROGRESO se desvió y qué se resolvió — sin
alterar el resto de la hoja de ruta.

#### PASO 2 — Actualizar la Hoja de Ruta

Reescribir la sección `## 8. Hoja de Ruta para la Siguiente Sesion` con
los cambios pertinentes. Recordar que el hito está PAUSADO: la
continuidad funcional (exportación, filtros, búsqueda) vive en el Hito 19
(`enterprisebot-annex-v19`), no en este anexo.

#### PASO 3 — Reescribir el SKILL.md completo

Escribir en:
```
/home/claude/skills/enterprisebot-annex-v07/SKILL.md
```

#### PASO 4 — Empaquetar

```bash
cd /mnt/skills/examples/skill-creator && \
python -m scripts.package_skill \
    /home/claude/skills/enterprisebot-annex-v07 \
    /mnt/user-data/outputs/skills
```

#### PASO 5 — Presentar el `.skill` para descarga

```python
present_files(["/mnt/user-data/outputs/skills/enterprisebot-annex-v07.skill"])
```

#### PASO 6 — Backup en PythonAnywhere

```sftp
put "sdcard/Download/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md" "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md"
```

---

## ═══════════════════════════════════════════
## PARTE 2 — TEXTO ÍNTEGRO DEL ANEXO
## ═══════════════════════════════════════════

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
| S048 | 2026-06-17 | Sesión de continuación H07 con desvíos a H08 y mejoras en WorkOrderAdminHistoryView. **Desvío H08:** fix regresión editor fecha inline en edit.html — el handler JS (btn-date-edit-toggle/btn-date-cancel) se había perdido del IIFE en un merge; añadido antes del cierre }();. **Fix duplicación entries (H07):** restaurado work_order.entries.all().delete() antes de work_order.status=DONE en bloque if _reuse_wo is not None de close_order en views_operator.py. Entries WO#172 y WO#173 verificadas limpias (1 entry cada una). **Botón eliminar tarea en modo edición:** añadido btn-remove-block-static con data-block-id en bloques server-side de form_entry.html; handler en form_entry_assets.js (row.remove() + decremento numEntradasInput + e.preventDefault()/stopPropagation()). **Columna H. Extra en WorkOrderAdminHistoryView:** campo horas_extra=max(0,horas_totales-8) añadido a _enrich_work_orders en views_workorders.py; columna H. Extra con badge verde (+Xh) en las tres pestañas de admin_history.html; horas_extra añadida a _VALID_SORT_COLS y al sort-stack JS de admin_history.js (initBulkGroup("reviewed") también añadido). **Colores horas extra:** overtime-positive → verde en operator/history.html; lógica negativo eliminada. **Selección múltiple revisados:** initBulkGroup("reviewed") faltaba en admin_history.js. **H. Extra en plantillas exportación:** horas_extra añadida a COLUMN_DEFS de build_export_from_template en services.py y a column_choices en views_workorders.py. **Autoajuste columnas Excel:** función _autofit_columns añadida en services.py, aplicada en single_sheet y multi_sheet. Skill enterprisebot-annex-v08 creada. Skill v01-edit creada (sin backup SWAP). |

---

## 8. Hoja de Ruta para la Siguiente Sesion

### Estado: Hito PAUSADO

La hoja de ruta del Paso 49 fue completada en S049. Sin pasos pendientes
para la siguiente sesión en este hito.

### Criterios de reapertura de este hito (H7)

Este anexo puede reabrirse — como hito EN PROGRESO o por desvío (Caso A)
— para:

1. Regresiones en el flujo unificado `WorkOrderEntryFormView` tras la
   reingeniería de S045 (Gate 4 eliminado, vista única de creación/edición).
2. Ajustes al modal guardián de cierre, al selector de ausencias PERSONAL
   o al auto-relleno de horarios.
3. Extensiones al flujo de circulares WhatsApp por sección
   (`group_broadcast`, `pending_broadcast_messages`).
4. Cualquier incidencia sobre `WorkOrder`/`WorkOrderEntry`/
   `WorkOrderEntryLine`/`WorkdayGap`/`AbsenceCategory` no cubierta por el
   alcance del Hito 19.
5. Ajustes o ampliaciones al sistema de plantillas de exportación compartidas
   implementado en S049.

**Continuar el trabajo planificado en**
`ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md` (`enterprisebot-annex-v19`).
