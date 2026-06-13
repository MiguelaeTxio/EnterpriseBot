# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md

# Hito 7 — Partes Diarios de Reparación — Entrada Digital desde el Panel

## Estado General
Implementación avanzada. Múltiples vías de entrada operativas. **PAUSADO** — pivotaje a Hito 19 en S044 (2026-06-04). Las mejoras de la vista de administración (filtros, búsqueda, ordenación, exportación por plantillas) se desarrollan en el anexo V19.

---

## Arquitectura Consolidada

### Vía A — Formulario Web Estructurado
**Estado:** COMPLETADO

Formulario multi-bloque con validación client-side (Gates 1-3) y server-side (Gate 4).
Flujo modal de confirmación. Clasificación automática de averías via Celery + Gemini.

### Vía B — STT
**Estado:** ABANDONADO DEFINITIVAMENTE (S022)

### Vía C — Upload Gemini Vision
**Estado:** COMPLETADO (S033)

Upload de PDF escaneado procesado por Gemini Vision. Flujo de merge con Vía A.

---

## Funcionalidades Completadas

| Funcionalidad | Sesión | Estado |
|---|---|---|
| Formulario multi-bloque Vía A | S016 | COMPLETADO |
| Gate 4 — validación de jornada | S018 | COMPLETADO |
| Flujo de merge Gate 0 | S020 | COMPLETADO |
| Clasificación tipología averías Celery+Gemini | S024 | COMPLETADO |
| Vistas supervisor — períodos, ausencias, horarios | S028 | COMPLETADO |
| Historial operario — 4 pestañas | S030 | COMPLETADO |
| Dispositivo de confianza — flujo forzado | S038 | COMPLETADO |
| Menú ayuda WhatsApp (implementado, pendiente E2E) | S039 | PARCIAL |
| Correcciones navegación digital, Excel digital | S039 | COMPLETADO |
| WorkshopRequiredMixin permisos | S002-SB | COMPLETADO |
| Fix GAP falso positivo mañana+tarde (validators.py + views.py) | S040 | COMPLETADO |
| Fix horas extra negativas operario sin partes | S040 | COMPLETADO |
| Campo no_lunch_break en WorkOrderEntry (migración 0020) | S040 | COMPLETADO |
| Checkbox No he parado a comer en formulario (jornada partida) | S040 | COMPLETADO |
| Estado IN_PROGRESS en WorkOrder.Status (migración 0021) | S040 | COMPLETADO |
| Guardado progresivo por bloques — save_blocks / close_order | S040 | COMPLETADO |
| Retomar parte IN_PROGRESS al acceder al formulario | S040 | COMPLETADO |
| Gate 0 — excluir IN_PROGRESS propio del flujo de merge | S040 | COMPLETADO |
| Fix CSS eb-field / field-flagged / field-optional | S041 | COMPLETADO |
| Fix pausa de comida en modo retomar (lb_start/end en contexto GET) | S042 | COMPLETADO |
| Fix campos obsoletos configuración empresa (bases + horarios) | S042 | COMPLETADO |
| _computeAndInjectLunchOverlaps elevada a scope de módulo (JS) | S042 | COMPLETADO |
| Corrección BD: 10 partes con delta_hours sin descuento comida | S042 | COMPLETADO |
| Activo PERSONAL creado + comando seed_personal_asset | S042 | COMPLETADO |
| Selector AbsenceCategory en formulario (Vía A, template + JS) | S042 | COMPLETADO |
| Fix I-BUG-A — descuento pausa comida server-side en save_blocks y close_order | S043 | COMPLETADO |
| Fix laguna: recálculo de líneas previas al cambiar pausa en save_blocks | S043 | COMPLETADO |
| Fix I-BUG-B — redirección a historial digital tras guardar parte | S043 | COMPLETADO |
| Fix I4 — WorkOrderEditView: acceso WORKSHOP + título condicional + redirecciones por rol | S043 | COMPLETADO |
| Fix I6 — backend selector ausencias: _parse_entry_lines_from_post + WorkdayGap sintético | S043 | COMPLETADO |
| Fix I6 — WorkdayGapResolutionView crea WorkOrderEntryLine PERSONAL al resolver gap | S043 | COMPLETADO |
| Fix serialización JSON de absence_categories en contexto GET (regresión autocomplete) | S043 | COMPLETADO |
| Ordenación por columna (sort/dir) en WorkOrderEntryHistoryView (Tab 1) | S044 | COMPLETADO |
| Ordenación por columna (sort/dir) en WorkOrderAdminHistoryView (3 pestañas) | S044 | COMPLETADO |

---

## Incidencias Resueltas en S043 (detectadas en pruebas)

| Incidencia | Causa raíz | Solución |
|---|---|---|
| BotManagementView FieldError `section__companyuser__workshop_family` | Lookup inválido — Section no tiene FK directa a CompanyUser | Consulta en BD, traversal correcta via `section__contacts__company_user__workshop_family` |
| BotManagementView FieldError `sections` en CompanyUser | `workshop_family` es código muerto — ningún CU tiene valor | Rediseño completo: eliminado `workshop_family`, circular por sección directa |
| Usuario WORKSHOP inactivo no activable desde panel | Template `users/form.html` ocultaba `is_active` para WORKSHOP | Eliminada condición `{% if object.role not in "WORKSHOP,DRIVER" %}` |
| Circular WhatsApp fuera ventana 24h no llegaba | `send_reply` solo funciona dentro de ventana | Lógica ventana 24h: dentro → `send_reply`, fuera → `chat_session_renewal` + `pending_broadcast_messages` |
| Circular no registrada en sala de chat del panel | `ChatMessage` solo se creaba para envíos directos | Creación de `ChatMessage OUTBOUND` en opt_in tras entrega de `pending_broadcast_messages` |

---

## Arquitectura I6 — Ausencias en Partes Diarios

### Camino A — Declaración voluntaria (operario)
El operario añade un bloque con activo PERSONAL en el formulario Vía A.
`_parse_entry_lines_from_post` lee `entrada_{i}_absence_category`, resuelve
`AbsenceCategory` y sobreescribe `fault_description` con su label.
`save_blocks` y `close_order` crean un `WorkdayGap` sintético (resolved=True)
con `gap_start=hc`, `gap_end=hf`, `absence_category` y `note`.

### Camino B — Detección automática (Gate 4)
Gate 4 detecta huecos de jornada → crea `WorkdayGap` sin resolver → redirige
a `WorkdayGapResolutionView`. Al resolver un gap estándar, además de actualizar
el `WorkdayGap`, se crea una `WorkOrderEntryLine` con `machine_asset=PERSONAL`,
`fault_description=absence_cat.label`, `hc=gap_start`, `hf=gap_end`.

**Resultado en BD: idéntico en ambos caminos.**

---

## Arquitectura Circular WhatsApp — Secciones

### Campo `Section.is_broadcast_enabled`
Migración `ivr_config 0032`. Controla qué secciones son candidatas para
circulares masivas. Defecto `False`. El ADMIN lo activa por sección desde
el formulario de edición de sección.

### Flujo group_broadcast
1. ADMIN escribe mensaje y pulsa "Enviar circular".
2. Modal Bootstrap lista secciones con `is_broadcast_enabled=True`.
3. ADMIN selecciona secciones y confirma.
4. Backend itera contactos activos de cada sección:
   - Dentro ventana 24h (`WhatsAppSession.last_message_at >= now-24h`):
     `send_reply` directo.
   - Fuera de ventana: `chat_session_renewal` + mensaje encolado en
     `WhatsAppSession.pending_broadcast_messages` (JSONField, migración
     `whatsapp 0004`).
5. En `opt_in` del webhook: entrega de `pending_broadcast_messages` con
   expiración 48h + creación de `ChatMessage OUTBOUND` en la sala de la sección.

---

## Directrices Técnicas Vinculantes

- **SDK IA:** `google-genai 1.69.0` — Modelo: `gemini-live-2.5-flash-native-audio` — Vertex AI
- **Framework:** Django `5.2.12` — Servidor async: `aiohttp 3.13.5` — Puerto `8081`
- **Twilio SDK:** `twilio 9.10.4` — Auth via API Key
- **VAD servidor:** `disabled=True` — Voice: `Aoede`
- **Entorno:** PythonAnywhere — Python `3.10.5` — `EnterpriseBot_venv`
- **BD:** MySQL `MiguelAeTxio$enterprisebot`
- Directriz 4.4 activa: actualización online obligatoria antes de implementar
  código con APIs externas.
- `cssutils==2.15.0` instalado en `EnterpriseBot_venv`.

---

## Migraciones Aplicadas en S043

| App | Número | Nombre | Descripción |
|---|---|---|---|
| ivr_config | 0032 | add_section_is_broadcast_enabled | Campo BooleanField is_broadcast_enabled en Section |
| whatsapp | 0004 | add_pending_broadcast_messages | Campo JSONField pending_broadcast_messages en WhatsAppSession |

---

## Hoja de Ruta — CERRADA en S044

La hoja de ruta original de S044 quedó parcialmente ejecutada.
La ordenación (P1.1 y P1.2) se implementó correctamente en views.py.
Las mejoras restantes (exportación, filtros, búsqueda) evolucionaron
en alcance durante la sesión y se promovieron al Hito 19, donde se
implementarán con la arquitectura correcta (motor de plantillas,
modelo ExportTemplate, filtro familia de avería, búsqueda libre).

**Hito 7 queda PAUSADO.** Continuar en `ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md`.

---

## Registro de Sesiones

### S001 — S039
[Historial anterior preservado — ver versiones anteriores del anexo]

### S040 — 2026-05-27
**Título:** Fix GAP comida, horas negativas, no_lunch_break y guardado progresivo por bloques
**Descripción:** Sesión S040 del Hito 7. Se resolvieron cuatro incidencias principales:
corrección del bug de GAP falso positivo entre bloques mañana+tarde (validators.py +
views.py, comparadores >= y <=, eliminación de constantes hardcodeadas de duración);
corrección de horas extra negativas en operario sin partes (WorkOrderEntryHistoryView,
cortocircuito cuando earliest=None); implementación completa del campo no_lunch_break
en WorkOrderEntry (modelo, migración 0020, views, template, JS) con checkbox visible
solo en jornada partida y toggle de campos de hora; implementación del guardado
progresivo por bloques con estado IN_PROGRESS (migración 0021, rediseño de
WorkOrderEntryFormView GET/POST, Gate 0 actualizado, template con dos botones).
La sesión se cerró con la incidencia de colores CSS sin resolver por errores
reiterados de incumplimiento del PED por parte del modelo.

### S042 — 2026-06-04
**Título:** Fix CSS eb-field, pausa comida retomar y HC/HF por defecto en bloques nuevos
**Descripción:** Sesión S042 del Hito 7. Se resolvió I1 (CSS eb-field/field-flagged
ya estaba implementado en S041). Se corrigió I2 (pausa de comida en modo retomar:
fix en views.py GET, placeholders XX:XX sustituidos por valores reales de
_ip_first_entry). Se verificó I3 (HC/HF por defecto en bloques nuevos, ya implementado).
Se implementó I4 (configuración de empresa: eliminados textareas obsoletos de bases
y calendario laboral, sustituidos por tablas en vivo de Base y WorkdaySchedule con
botones de gestión). Se implementó parcialmente I6 (selector de ausencias PERSONAL:
activo PERSONAL creado en BD via seed_personal_asset, contexto absence_categories y
personal_asset_code añadido al formulario, JS _toggleAbsenceMode y _adjustRepairNotes
implementados, _buildBlockRow actualizado; pendiente backend). Se corrigieron 10 partes
digitales en BD con delta_hours bruto via comandos fix_digital_lunch_deduction y
fix_all_digital. Se diagnosticaron dos bugs críticos pendientes: I-BUG-A (descuento
pausa de comida — el backend debe calcular el overlap server-side en lugar de confiar
en lunch_overlap_N del JS) e I-BUG-B (redirección a historial PDF en lugar de historial
digital tras guardar parte). Se refactorizaron las skills PED en arquitectura modular
(ped-router, ped-format, ped-pma, ped-pea, ped-pmp, ped-doc) y se actualizó
session-standards eliminando el bucle de preguntas sobre método de entrega.

### S043 — 2026-06-04
**Título:** Fix pausa comida server-side, redirección digital, backend ausencias y circular WhatsApp por secciones
**Descripción:** Sesión S043 del Hito 7. Se resolvieron todas las incidencias acumuladas
desde S042. I-BUG-A: el backend calcula el overlap de pausa de comida server-side en
save_blocks y close_order, eliminando la dependencia de lunch_overlap_N del JS; además
se implementó el recálculo de líneas ya persistidas cuando el operario modifica la pausa
tras haber guardado bloques. I-BUG-B: redirección a /panel/work-orders/digital/ tras
guardar parte, condicional al rol (WORKSHOP → operator_history, SUPERVISOR/ADMIN →
digital_work_order_list). I4: WorkOrderEditView migrado a WorkshopRequiredMixin con
guardia de acceso WORKSHOP, título condicional en edit.html y redirecciones por rol.
I6: backend completo del selector de ausencias — _parse_entry_lines_from_post procesa
absence_category, save_blocks y close_order crean WorkdayGap sintético para bloques
PERSONAL, WorkdayGapResolutionView crea WorkOrderEntryLine PERSONAL al resolver gaps
automáticos; fix de serialización JSON de absence_categories que rompía el autocomplete.
En pruebas se detectaron y resolvieron: FieldError en BotManagementView por lookup
inválido de workshop_family (código muerto); rediseño completo del group_broadcast
eliminando workshop_family y creando infraestructura de circulares por sección con
is_broadcast_enabled (migración ivr_config 0032), modal de selección, lógica de ventana
24h con pending_broadcast_messages (migración whatsapp 0004) y entrega en opt_in con
registro en sala de chat; fix de activación de usuarios WORKSHOP inactivos desde panel.

### S044 — 2026-06-04
**Título:** Ordenación por columnas en historial de partes digitales y pivotaje a Hito 19
**Descripción:** Sesión S044 del Hito 7. Se implementó la ordenación por columna
(parámetros GET sort/dir) en WorkOrderEntryHistoryView (Tab 1 — periodo actual,
columnas fecha/num_bloques/horas_totales/reviewed) y en WorkOrderAdminHistoryView
(pestañas Pendientes, Revisados e Histórico, columnas fecha/operator_name/horas_totales/reviewed).
Ambas vistas pasan sort_col y sort_dir al contexto del template. Durante la sesión
se debatió la exportación Excel y se concluyó que el alcance correcto es un motor
de exportación por plantillas con modelo ExportTemplate en work_order_processor,
filtro por familia de avería, campo de búsqueda libre (fault_description + repair_notes),
acción desmarcar revisado y sustitución completa del sistema de exportación existente.
Todo ello se promovió al Hito 19. El Hito 7 queda PAUSADO en este punto.

### S045 — 2026-06-13
**Título:** Eliminación del Gate 4, vista única de partes digitales y refuerzo de validación al cierre

**Descripción:** Sesión incidencia del Hito 7 atendida mientras el hito en
progreso era el Hito 18 (Gestión de Mapas y Geolocalización). El trabajo se
desvió íntegramente a resolver una incidencia crítica del módulo de partes
digitales: el sistema "Gate 4" de resolución de lagunas estaba borrando
partes al editarlos. Se acometió una reingeniería completa del flujo de
creación y edición de partes digitales. Detalle:

**1. Eliminación total del Gate 4.** Se eliminaron de `panel/views_operator.py`
la clase `WorkdayGapResolutionView` completa y la clase `WorkOrderEntryMergeView`
completa, junto con los bloques del POST de `WorkOrderEntryConfirmView` y
`WorkOrderEntryFormView` que detectaban lagunas de jornada y desviaban a un
`WorkOrder` borrador en estado `PENDING_GAPS`. Se eliminaron también las
funciones huérfanas asociadas (`_detect_workday_gaps`, `_detect_overlaps`,
`_serialize_pending_lines`) y las rutas `operator/gaps/` y `operator/merge/`
de `panel/urls.py`, así como los imports correspondientes en `panel/views.py`.
El "Camino B — Detección automática (Gate 4)" descrito en la sección
"Arquitectura I6 — Ausencias en Partes Diarios" de este anexo QUEDA OBSOLETO:
ya no existe detección automática de lagunas. Subsiste únicamente el "Camino A
— Declaración voluntaria", donde el operario añade una tarea con activo
PERSONAL y categoría de ausencia.

**2. Vista única de creación y edición.** Se unificó el formulario de partes
digitales: `WorkOrderEntryFormView` es ahora la única vista de creación y
edición para todos los roles (WORKSHOP, SUPERVISOR, ADMIN). `WorkOrderEditView`
queda reservada exclusivamente para partes de origen PDF histórico. Se recuperó
del commit `76c184a` (previo a la introducción del Gate 4) la estructura del
template `form_entry.html` con su primer bloque renderizado server-side, y se
reconstruyó el JS `form_entry_assets.js` sobre esa base.

**3. Validación de fecha al cierre.** Se corrigió la detección de fecha
duplicada para excluir correctamente los partes `IN_PROGRESS` propios y el
parte en edición (evitaba el bloqueo erróneo y los duplicados). Se añadió
validación de fecha futura (rechazo de fechas posteriores a hoy) tanto en
`WorkOrderEntryConfirmView` como en `WorkOrderEntryFormView`, preservando los
datos introducidos en el formulario al devolver el error.

**4. Modal guardián de cierre.** El modal de validación informa al operario de
lagunas, solapamientos y jornada incompleta (mínimo 8 h) sin permitir cerrar
el parte hasta corregirlos. El mensaje de jornada incompleta indica que se
añada una tarea o se justifique la ausencia con código PERSONAL en el campo
Máquina/Centro de Gasto. En jornada intensiva se permite añadir una tarea
vespertina siempre que se cumplan las 8 h.

**5. Selector de ausencias.** Al introducir PERSONAL en el campo Máquina se
despliega el selector de categoría de ausencia (con foco automático). El campo
de motivo solo se exige cuando la categoría tiene `requires_note=True`. La
validación server-side y client-side exime la descripción de avería en tareas
de ausencia y exige en su lugar la categoría. Se corrigió la serialización de
`absence_categories` a JSON válido (comillas dobles, booleanos JS) y se
desdobló el contexto en `absence_categories` (JSON para EB_CONFIG) y
`absence_categories_list` (lista Python para el fragment).

**6. Pausa de comida según jornada.** Checkbox "No he parado a comer" en jornada
partida (pausa activa por defecto, se oculta al marcar) y checkbox "He parado
a comer" en jornada intensiva (pausa oculta por defecto, se despliega vacía al
marcar, para registrar averías de tarde). Reinicialización de la lógica tras
cada swap HTMX del fragment de horario.

**7. Auto-relleno de horarios al añadir tarea.** La H.C. de la nueva tarea toma
la H.F. de la tarea anterior; si esta acabó al fin del periodo de mañana y hay
pausa activa, la nueva tarea arranca en el inicio de la tarde
(`start_time_afternoon`). La H.F. toma el fin del periodo donde cae la H.C. Es
un prerrelleno orientativo y editable; el modal guardián valida al cerrar.

**8. Directriz de proveedor de mapas.** A raíz de detectar que el módulo de
presupuestos usaba Leaflet/Nominatim mientras la geolocalización de bases ya
usa Google Maps, se estableció en el anexo del Hito 18 una Directriz Técnica
Vinculante: Google Maps Platform como único proveedor de mapas, geocodificación
y rutas en todo el proyecto.

**9. Copia de seguridad en logs.** Cada parte cerrado registra en el log del
servidor una línea `# [PARTE-BACKUP]` con el payload completo en JSON (fecha,
operario, pausa, y cada tarea con máquina, horas, O.R., avería, reparación y
ausencia), como copia de recuperación temporal.

**10. Smoke test de validación.** Se creó una batería de smoke tests (test
client de Django, transacciones revertidas) que verifica el bloqueo al cierre
en los casos: fecha vacía, fecha futura, tarea sin máquina, sin H.C., sin H.F.,
H.F. anterior a H.C., tareas solapadas, sin descripción de avería y jornada
incompleta (<8 h). Resultado: 9/9 correctos.

**11. Unificación de nomenclatura.** Todo "bloque" visible en la interfaz pasó
a "tarea" (Añadir tarea, Guardar tareas, Eliminar tarea, Tarea N) en template,
fragment, JS y mensajes de validación de servidor y cliente.

**Archivos tocados:** `panel/views_operator.py`, `panel/views.py`,
`panel/urls.py`, `panel/templates/panel/operator/form_entry.html`,
`panel/templates/panel/operator/_schedule_fields_fragment.html`,
`panel/static/panel/js/form_entry_assets.js`. Smoke test entregado en SWAP.
El detalle del desvío de sesión queda anotado en el anexo del Hito 18.
