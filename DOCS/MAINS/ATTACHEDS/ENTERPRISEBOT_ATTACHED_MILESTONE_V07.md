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
| Selector AbsenceCategory en formulario (Vía A, template + JS) | S042 | COMPLETADO |
| Fix I-BUG-A — descuento pausa comida server-side en save_blocks y close_order | S043 | COMPLETADO |
| Fix laguna: recálculo de líneas previas al cambiar pausa en save_blocks | S043 | COMPLETADO |
| Fix I-BUG-B — redirección a historial digital tras guardar parte | S043 | COMPLETADO |
| Fix I4 — WorkOrderEditView: acceso WORKSHOP + título condicional + redirecciones por rol | S043 | COMPLETADO |
| Fix I6 — backend selector ausencias: _parse_entry_lines_from_post + WorkdayGap sintético | S043 | COMPLETADO |
| Fix I6 — WorkdayGapResolutionView crea WorkOrderEntryLine PERSONAL al resolver gap | S043 | COMPLETADO |
| Fix serialización JSON de absence_categories en contexto GET (regresión autocomplete) | S043 | COMPLETADO |

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

## Hoja de Ruta para S044

### Prioridad 1 — Mejoras UX historial de partes digitales (P4)

#### 1.1 Ordenación por columnas — vista WORKSHOP (`WorkOrderEntryHistoryView`)
La vista `WorkOrderEntryHistoryView` renderiza el historial personal del
operario en 4 pestañas. La pestaña principal (periodo actual) y las demás
deben permitir ordenar por las columnas visibles.

**Implementación:**
- Leer parámetro GET `sort` (nombre de columna) y `dir` (asc/desc).
- Aplicar `order_by` al queryset según el par `sort`/`dir`.
- En el template, cada cabecera de columna es un enlace que alterna
  `dir=asc` / `dir=desc` e incluye un indicador visual (▲/▼).
- Preservar los filtros activos (pestaña, fecha) en los enlaces de ordenación.

**Columnas ordenables:** fecha del parte, máquina, horas totales, estado.

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderEntryHistoryView.get()`: añadir lógica
  de ordenación al queryset de cada pestaña.
- `panel/templates/panel/operator/history.html`: cabeceras con enlaces
  de ordenación y clase CSS activa en la columna activa.

#### 1.2 Ordenación por columnas — vista SUPERVISOR/ADMIN (`WorkOrderAdminHistoryView`)
Misma lógica que 1.1 aplicada a `WorkOrderAdminHistoryView`.

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderAdminHistoryView.get()`.
- `panel/templates/panel/work_orders/digital_list.html` (o el template
  correspondiente): cabeceras con enlaces de ordenación.

#### 1.3 Exportación Excel historial de partes digitales
El SUPERVISOR/ADMIN y el WORKSHOP deben poder exportar a Excel el listado
de partes digitales filtrado por el periodo/criterio activo en ese momento.

**Implementación:**
- Añadir parámetro GET `export=excel` a ambas vistas.
- Reutilizar `generate_work_order_excel` o crear una función específica
  que genere un Excel con las columnas del listado (fecha, operario,
  máquina, horas, estado).
- El botón de exportación se añade en el template junto a los filtros,
  preservando los parámetros de filtrado activos en la URL.

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderEntryHistoryView.get()` y
  `WorkOrderAdminHistoryView.get()`: rama `export=excel`.
- Templates correspondientes: botón de exportación.

**Orden de ejecución en S044:**
1. Solicitar `panel/views.py` actualizado y los dos templates de historial.
2. Implementar ordenación (1.1 y 1.2) en una sola caja PMA sobre views.py.
3. Implementar exportación Excel (1.3) en caja PMA separada.
4. Actualizar templates con cabeceras y botón de exportación.
5. Verificar en producción con operario y supervisor.

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
