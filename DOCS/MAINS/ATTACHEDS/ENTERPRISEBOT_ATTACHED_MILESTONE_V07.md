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

---

## Incidencias Pendientes al Cierre de S040

### I1 — Colores de campos del formulario (CSS)
**Causa raíz identificada:** La clase `field-flagged` actúa simultáneamente como
estado base naranja Y estado de error, en lugar de estar separadas. Los inputs de
hora vacíos reciben el rojo nativo `:invalid` del browser porque `field-flagged`
no siempre se aplica. Los campos opcionales quedan blancos en algunos contextos.

**Solución diseñada — NO IMPLEMENTADA por cierre de sesión:**

1. `panel/static/panel/css/panel.css`:
   - Nueva clase `eb-field`: fondo + borde naranja permanente para todos los campos.
   - `field-flagged` pasa a ser ÚNICAMENTE estado de error (borde rojo, fondo rojo tenue).
   - `field-optional` pasa a ser alias de `eb-field`.
   - Ancla OLD verificada en workspace. Caracteres Unicode `\u2014` (`—`) presentes.
   - **MÉTODO OBLIGATORIO:** script Python en SWAP (NO heredoc, NO python3 -c inline).
     El script debe escribirse con `cat << 'SCRIPT_EOF' > /home/MiguelAeTxio/SWAP/patch_panel_css_ebfield.py`
     usando concatenación de strings Python con `\n` explícitos para el OLD/NEW.
   - Barrera de fuego: `cssutils` (ya instalado en EnterpriseBot_venv).

2. `panel/templates/panel/operator/form_entry.html`:
   - Todos los inputs del primer bloque (renderizados desde template): añadir clase `eb-field`.
   - Los campos de hora: `class="form-control eb-field"` siempre, sin condicional.
   - `field-flagged` solo cuando el campo está vacío al renderizar.

3. `panel/static/panel/js/form_entry_assets.js`:
   - Nuevos bloques generados por JS: inputs de hora nacen con clase `eb-field`.
   - `_markField(name, bad)`: cuando `bad=true` añade `field-flagged`; cuando `bad=false`
     elimina `field-flagged`. La clase `eb-field` NUNCA se toca.
   - Barrera de fuego: `esprima` (ya instalado).

**ADVERTENCIA CRÍTICA PARA S041:**
Esta incidencia se intentó resolver en S040 pero se abortó por errores reiterados
debidos a incumplimiento del PED. El modelo S041 DEBE:
- Escribir SIEMPRE el script en SWAP con `cat << 'SCRIPT_EOF' > /ruta/script.py`
- NUNCA usar `python3 -c` inline para patchers con Unicode
- NUNCA usar heredoc con comillas/backticks/caracteres especiales en el OLD/NEW
- Leer la sección 4 del PED antes de redactar cualquier patcher
- La barrera de fuego CSS es: `python3 -c "import cssutils, logging; cssutils.log.setLevel(logging.CRITICAL); cssutils.parseFile('/ruta/archivo.css'); print('# [SYNTAX OK]')"`

### I2 — Pausa de comida desaparece en modo retomar (IN_PROGRESS)
**Descripción:** Al guardar bloques (acción save_blocks) y recargar el formulario
en modo retomar, los campos `lunch_break_start` y `lunch_break_end` aparecen vacíos
aunque fueron enviados en el POST.
**Causa probable:** El POST save_blocks persiste `_lb_start/_lb_end` en `WorkOrderEntry`
pero el GET en modo retomar los lee de `_ip_first_entry.lunch_break_start/end` —
verificar que el save_blocks efectivamente persiste estos valores en la entry.
**Pendiente diagnóstico y fix en S041.**

### I3 — HC/HF por defecto en bloques nuevos
**Descripción:** Al añadir un bloque nuevo, proponer como HC la HF del último
bloque guardado, y como HF el `end_time_morning` del horario (o `end_time_afternoon`
si la HC supera la comida).
**Pendiente implementación en S041 — JS en form_entry_assets.js.**

---

## Directrices Técnicas Vinculantes

- **SDK IA:** `google-genai 1.69.0` — Modelo: `gemini-live-2.5-flash-native-audio` — Vertex AI
- **Framework:** Django `5.2.12` — Servidor async: `aiohttp 3.13.5` — Puerto `8081`
- **Twilio SDK:** `twilio 9.10.4` — Auth via API Key
- **VAD servidor:** `disabled=True` — Voice: `Aoede`
- **Entorno:** PythonAnywhere — Python `3.10.5` — `EnterpriseBot_venv`
- **BD:** MySQL `MiguelAeTxio$enterprisebot`
- Directriz 4.4 activa: actualización online obligatoria antes de implementar código con APIs externas.
- `cssutils==2.15.0` instalado en `EnterpriseBot_venv` (añadido a requirements.in en S040).

---

## Migraciones Aplicadas en S040

| Número | Nombre | Descripción |
|---|---|---|
| 0020 | add_no_lunch_break_to_workorderentry | Campo BooleanField no_lunch_break en WorkOrderEntry |
| 0021 | add_in_progress_status | Nuevo valor IN_PROGRESS en WorkOrder.Status.TextChoices |

---

## Hoja de Ruta para la Siguiente Sesión (S041)

### Prioridad 0 — Fix CSS colores de campos (I1)
Ver sección "Incidencias Pendientes" — descripción completa y método obligatorio detallados arriba.
Ejecutar en este orden exacto: panel.css → form_entry.html → form_entry_assets.js.
Recolectar estáticos y recargar servidor al finalizar los tres archivos.

### Prioridad 1 — Diagnóstico y fix pausa de comida en modo retomar (I2)
Añadir log en save_blocks POST para verificar que _lb_start/_lb_end llegan y se persisten.
Si el problema es de parseo del POST: verificar que los campos lunch_break_start/end
se incluyen en el submit de save_blocks (pueden estar dentro de #lunch-break-times
que queda oculto si no_lunch_break está marcado — verificar que los inputs ocultos
siguen enviándose al servidor aunque el div sea d-none).

### Prioridad 2 — HC/HF por defecto en bloques nuevos (I3)
En form_entry_assets.js, en la función que añade un bloque nuevo (addBlock o similar),
leer la HF del último bloque visible y usarla como HC del nuevo bloque.
Usar EB_CONFIG.lunchBreakStart y EB_CONFIG.lunchBreakEnd para determinar si
el nuevo HC supera la comida y ajustar el HF sugerido al end_time_afternoon.

### Prioridad 3 — Bloque 3: campo in_situ + location_description
BooleanField `in_situ` y CharField `location_description` en WorkOrderEntry.
Migración, formulario (checkbox + textarea condicional), views y template.
JS: si in_situ=True mostrar textarea de ubicación; si False ocultarlo y limpiar valor.

### Prioridad 4 — Validación E2E menú de ayuda WhatsApp (P0 del anexo)
Pendiente desde S039. Requiere contacto real escribiendo variantes de "ayuda".
Verificar que quick-reply llega con ids correctos: help_schedules y help_agent.

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
