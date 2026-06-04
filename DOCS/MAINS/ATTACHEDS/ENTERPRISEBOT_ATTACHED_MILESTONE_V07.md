# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md

# Hito 7 — Partes Diarios de Reparación — Entrada Digital desde el Panel

## Estado General
Implementación avanzada. Múltiples vías de entrada operativas. En curso.

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
| Selector AbsenceCategory en formulario (Vía A, bloque JS parcial) | S042 | PARCIAL |

---

## Incidencias Pendientes al Cierre de S042

### I-BUG-A — Descuento pausa de comida no se aplica correctamente
**Causa raíz diagnosticada:**
El backend lee `lunch_overlap_N` calculado por el JS para aplicar el descuento.
El JS calcula el overlap en el momento del submit usando el valor actual del
input `lunch_break_start` del DOM. Si el operario hace `save_blocks` antes de
rellenar la pausa, el input está vacío y el overlap es 0. Cuando hace
`close_order`, el input ya tiene valor pero el overlap ya fue enviado como 0
en el `save_blocks` anterior.

**Solución diseñada — NO IMPLEMENTADA:**
El backend debe calcular el overlap servidor-side desde `hc`, `hf`, `_lb_start`
y `_lb_end` — ignorando `lunch_overlap_N` del JS (que pasa a ser solo informativo).

**Regla de negocio confirmada:**
- Si el usuario no modifica los campos de pausa → el valor por defecto del horario
  es la fuente de verdad.
- Si el usuario los modifica → el valor modificado es la fuente de verdad.
- Si marca "no he parado a comer" → `no_lunch_break=True`, overlap=0.

**Archivos a modificar en S043:**
1. `panel/views.py` — `WorkOrderEntryFormView.post()`:
   - Bloque `close_order` (líneas ~9471-9490): sustituir lectura de
     `lunch_overlap_N` por cálculo server-side:
```python
     def _to_min(t): return t.hour * 60 + t.minute
     _overlap_min = max(0,
         min(_to_min(hf), _to_min(_lb_end)) -
         max(_to_min(hc), _to_min(_lb_start))
     ) if hc and hf and _lb_start and _lb_end and not _no_lunch_break else 0
```
   - Bloque `save_blocks` (líneas ~9319-9333): misma sustitución.
   - El fallback cuando `_lb_start` es None: usar `_post_schedule` si está
     disponible para obtener `end_time_morning` y `start_time_afternoon`.

### I-BUG-B — Redirección incorrecta tras guardar parte digital
**Causa raíz:**
`WorkOrderEntryFormView.post()` redirige a `/panel/work-orders/` (historial de
PDFs) en lugar de `/panel/work-orders/digital/` (historial de partes digitales).

**Fix — Línea exacta verificada en views.py:**
```python
# Línea ~9754 — cambiar:
return redirect("/panel/work-orders/")
# Por:
return redirect("/panel/work-orders/digital/")
```

**También verificar** que `save_blocks` redirige a `/panel/operator/form/`
(correcto, no necesita cambio).

### I6 — Disparador de ausencias en formulario de partes (PARCIAL)
**Estado:** JS y template implementados. Backend pendiente de procesar
`entrada_N_absence_category` en el POST.

**Pendiente en S043:**
- En `_parse_entry_lines_from_post`: leer `entrada_{i}_absence_category` del POST.
- Si el activo es `PERSONAL` y hay categoría, usar `label` de `AbsenceCategory`
  como `fault_description` de la línea.
- El campo `repair_notes` se envía libre si `requires_note=True`.
- `delta_hours` de bloques PERSONAL: calcular normal (hc/hf con descuento),
  representan tiempo de ausencia cubierto.

### I4 — Vista "Editar PDF" muestra título y lógica PDF para partes digitales
**Descripción:** La vista `WorkOrderEditView` (template `edit.html`) muestra
"Editar PDF #N" y `source_pdf.name` incluso para partes DIGITAL/GENERATED.
Título, subtítulo y lógica deben adaptarse según `work_order.source`.

**Pendiente en S043:**
- `edit.html`: condicionar título y subtítulo a `work_order.source`.
- `WorkOrderEditView.get()`: pasar `is_digital` al contexto.

### I2 — HC/HF por defecto en bloques nuevos
**Estado:** COMPLETADO en S041. Verificado en S042.

### I5 — Exportación Excel del historial de partes con plantillas configurables
**Pendiente diseño y implementación.**

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

## Migraciones Aplicadas en S040

| Número | Nombre | Descripción |
|---|---|---|
| 0020 | add_no_lunch_break_to_workorderentry | Campo BooleanField no_lunch_break en WorkOrderEntry |
| 0021 | add_in_progress_status | Nuevo valor IN_PROGRESS en WorkOrder.Status.TextChoices |

---

## Hoja de Ruta para S043

### Prioridad 0 — Fix descuento pausa de comida (I-BUG-A)
Ver sección "Incidencias Pendientes" — descripción completa arriba.

**Orden de ejecución obligatorio:**
1. Solicitar `panel/views.py` actualizado.
2. Localizar bloque `close_order` (~línea 9471) y bloque `save_blocks` (~línea 9319).
3. En ambos bloques: sustituir lectura de `lunch_overlap_N` por cálculo
   server-side usando `_to_min(hc/hf)` y `_lb_start/_lb_end`.
4. Fallback: si `_lb_start` es None, resolver desde `_post_schedule`.
5. Verificar con `fix_all_digital --dry-run` que 0 líneas quedan mal.
6. Introducir parte de prueba y verificar en BD que `delta_hours` es correcto.

### Prioridad 1 — Fix redirección tras guardar parte digital (I-BUG-B)
Ver sección "Incidencias Pendientes" — línea exacta documentada arriba.
Fix de una sola línea en `panel/views.py`.
Tras el fix, verificar que el operario llega a `/panel/work-orders/digital/`.

### Prioridad 2 — Fix título "Editar PDF" en partes digitales (I4)
Solicitar `panel/templates/panel/work_orders/edit.html` y `panel/views.py`.
Condicionar título, subtítulo y subtítulo secundario a `work_order.source`.

### Prioridad 3 — Backend selector de ausencias (I6)
Ver sección "Incidencias Pendientes" — descripción completa arriba.
Solicitar `work_order_processor/services.py` (función `_parse_entry_lines_from_post`).

### Prioridad 4 — Incidencias del histórico de partes
Pendiente de definición por el usuario en la siguiente sesión.

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
