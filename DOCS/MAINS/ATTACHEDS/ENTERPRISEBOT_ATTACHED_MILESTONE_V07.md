# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md

# Anexo de Hito V07 — Partes Diarios de Reparación: Entrada Digital desde el Panel
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-27

---

## 1. Vision General del Hito

El Hito 7 digitaliza el origen de los partes de reparacion. Hasta ahora el flujo
exigia que un encargado escaneara los partes manuscritos en papel y los subiera
como PDF para que Gemini Vision los procesara. Este hito elimina el papel como
origen obligatorio: el propio operario de taller rellena su parte directamente
desde el panel de EnterpriseBot, eligiendo la via que mejor se adapta a su
contexto en cada momento.

El objetivo estrategico es la adopcion organica del formulario web estructurado
(Form) como via principal, sin imponer nada. La friccion deliberada del flujo
Upload (validacion campo a campo de datos ilegibles) y la comodidad del dictado
por voz (STT) actuan como catalizadores naturales del abandono progresivo del
manuscrito en papel.

---

## 2. Arquitectura Tecnica

### 2.1. Roles de CompanyUser ampliados

Los siguientes roles fueron anadidos a CompanyUser.role (TextChoices) en sesion 002:
- WORKSHOP — Operario de taller: acceso exclusivo a la entrada de partes.
- DRIVER   — Chofer: reservado para uso futuro.
- SUPERVISOR ya existia; se completo su soporte en el listado de usuarios (H7, sesion 003).

El mixin WorkshopRequiredMixin (panel/mixins.py) restringe el acceso a las
vistas de operario a los roles WORKSHOP y ADMIN.

### 2.2. Tres vias de entrada convergentes

Las tres vias prerellenan el mismo formulario de confirmacion. El formulario
de confirmacion es el unico punto de persistencia en BD.

#### Via A — Form (formulario web estructurado)
Estado: PENDIENTE (Paso 7 de la hoja de ruta actualizada).

#### Via B — STT (Speech-to-Text via Web Speech API)
Estado: PENDIENTE (Paso 8 de la hoja de ruta actualizada).

#### Via C — Upload (foto/PDF manuscrito con Gemini Vision)
Estado: COMPLETADO (sesion 003).
- WorkOrderEntryUploadView: rasteriza la imagen/PDF y llama a
  extract_work_order_page_full() (prompt completo, cara delantera + trasera).
- WorkOrderEntryConfirmView: formulario de confirmacion completo con
  validacion campo a campo. Persiste WorkOrder sintetico (status=DONE,
  source_pdf en blanco) + WorkOrderEntry + WorkOrderEntryLine + SparePartLine.
  Genera Excel sincronamente tras la persistencia.
- Templates: panel/operator/upload_entry.html, panel/operator/confirm_entry.html.
- Endpoint de autocompletado: GET /panel/operator/assets/ (WorkshopAssetAutocompleteView).

### 2.3. Modelo SparePartLine

Nuevo modelo en work_order_processor/models.py. Representa una linea de
repuesto/material consumido durante un bloque de trabajo (WorkOrderEntryLine).
Migrado en 0005_add_spare_part_line.

Campos: entry_line (FK WorkOrderEntryLine CASCADE), line_number, reference,
material, vehicle (FK MachineAsset SET_NULL), quantity (DecimalField),
source (SUPPLIER/WAREHOUSE), supplier, flags (JSONField).

### 2.4. Prompt Gemini ampliado

_EXTRACTION_PROMPT_FULL en work_order_processor/services.py: extrae tanto
la cara delantera (bloques de trabajo) como la trasera (tabla de repuestos)
en una unica llamada API. El pipeline historico sigue usando _EXTRACTION_PROMPT
sin modificacion.

Funcion publica: extract_work_order_page_full(image_bytes) -> dict.
JSON de respuesta incluye clave "repuestos": [{referencia, vehiculo_raw,
material, unidades, origen, proveedor, flags}].

### 2.5. Correccion multiempresa en _resolve_machine_asset

Se anodio parametro company=None a _resolve_machine_asset() en services.py.
Todas las llamadas desde panel/views.py pasan company=company. El pipeline
historico (tasks.py) mantiene compatibilidad al no pasar company.

### 2.6. Correccion HTMX _line_row.html

Bug: Django filter add con entero produce suma aritmetica en lugar de
concatenacion de cadena, generando row_class vacio y selector CSS invalido
('.') que bloqueaba todo el guardado HTMX. Corregido usando
{% with pk_str=line.pk|stringformat:"s" %} + {% with row_class="line-row-"|add:pk_str %}.
URL de guardado construida con {% url %} tag en lugar de concatenacion manual.

### 2.7. Correccion WorkOrderLineRestoreView

Anadida ruta alternativa para partes digitales (raw_gemini_response=None):
re-resolucion de machine_asset desde maquina_raw almacenado y recalculo
de delta_horas desde hc/hf. Los partes historicos siguen usando la ruta
original desde raw_gemini_response.

### 2.8. Stack tecnologico

- Web Speech API (nativa en Chrome/Edge) — STT sin coste ni dependencias.
- google-genai 1.69.0 / Vertex AI — Gemini Vision para Via C.
- pdf2image 1.x + Pillow 12.2.0 + poppler 0.86.1 — rasterizacion de PDF.
- openpyxl — generacion Excel sincrona postpersistencia con hoja Repuestos.
- Django 5.2.12 — vistas sincronas estandar (sin Celery para Vias A y B).
- Bootstrap 5.3 + Bootstrap Icons — UI del formulario de confirmacion.

### 2.9. Correccion race condition en WorkOrderUploadView

Bug: dos POSTs concurrentes del mismo PDF eludian el Nivel 1 de deteccion
de duplicados creando dos WorkOrder identicos (mismo hash SHA-256). Causa:
la ventana entre la pre-comprobacion y el INSERT permitia que la segunda
peticion pasara antes de que la primera hiciera commit.

Correccion: bloque transaction.atomic() + select_for_update() en Step 4
de WorkOrderUploadView.post() en panel/views.py. La segunda peticion queda
bloqueada hasta que la primera hace commit; si entonces detecta un registro
existente con el mismo hash, aborta con mensaje informativo.

Complemento: UniqueConstraint parcial sobre (company, source_pdf_hash)
excluyendo hash vacio en WorkOrder.Meta. Nota: MySQL no soporta constraints
parciales a nivel de DDL (W036) — la barrera real es el select_for_update.
Migracion: 0006_workorder_unique_pdf_hash_per_company.

Limpieza: 2 pares de WorkOrders duplicados existentes eliminados de BD
(#27 y #29), conservando el editado de cada par (#26 y #28).

### 2.10. Barrera de integridad sine qua non en Vias A y C

Toda persistencia de parte digital (Via A y Via C) requiere superar una
barrera de integridad obligatoria antes del INSERT. Los datos deben estar
completos al 100% — no se permite guardar un parte incompleto bajo ninguna
circunstancia.

Barrera server-side en WorkOrderEntryConfirmView.post() y
WorkOrderEntryFormView.post() (panel/views.py):
  Gate 1: fecha presente y parseable (DD/MM/AAAA o YYYY-MM-DD).
  Gate 2: cada bloque tiene maquina_raw no vacio, machine_asset resuelto
          en catalogo, hc y hf presentes, delta_horas positivo, y
          descripcion_averia no vacia.
  Gate 3: cada repuesto tiene material no vacio y quantity positiva.

En caso de fallo: re-renderiza el formulario con mensaje de error detallado
por campo y bloque, sin perder los datos ya introducidos.

Barrera client-side en confirm_entry.html y form_entry.html:
  Replica las tres gates antes del submit. Marca campos con field-flagged,
  hace scroll al alert y bloquea el envio si hay errores. El servidor actua
  como segunda barrera independiente.

---

## 3. Hoja de Ruta

### Paso 1 — Nuevo rol OPERATOR/WORKSHOP en CompanyUser
Estado: COMPLETADO (2026-04-28).

### Paso 2 — Mixin y navegacion restringida del operario
Estado: COMPLETADO (2026-04-28).

### Paso 3 — Modelo SparePartLine + migracion
Estado: COMPLETADO (2026-04-30).

### Paso 4 — Prompt Gemini ampliado + extract_work_order_page_full()
Estado: COMPLETADO (2026-04-30).

### Paso 5 — Via C: Upload con confirmacion total + repuestos
Estado: COMPLETADO (2026-04-30).

### Paso 6 — Excel ampliado: hoja Repuestos en generate_work_order_excel()
Estado: COMPLETADO (2026-04-30).
- Hoja "Repuestos" añadida al Excel generado con columnas:
  FECHA, BLOQUE, REFERENCIA, VEHICULO, MATERIAL, UNIDADES, ORIGEN, PROVEEDOR.
- Datos obtenidos de SparePartLine relacionados con las WorkOrderEntryLine
  del WorkOrder. Solo se crea cuando existe al menos un SparePartLine.
- Implementado en work_order_processor/services.py via PMA.

### Paso 7 — Via A: formulario web estructurado (Form)
Estado: COMPLETADO (2026-04-30).
- WorkOrderEntryFormView implementada en panel/views.py con barrera de
  integridad sine qua non identica a la Via C.
- Template panel/operator/form_entry.html: formulario multi-bloque con
  autocompletado MachineAsset, botones Anadir bloque y Anadir repuesto
  dinamicos via JS, validacion client-side y server-side.
- Persistencia sincrona: WorkOrder sintetico + WorkOrderEntry +
  WorkOrderEntryLine + SparePartLine + Excel.
- Ruta: GET/POST /panel/operator/form/ (name=operator_form).
- Dashboard Via A activada: boton deshabilitado sustituido por enlace activo.

### Paso 8 — Via B: dictado por voz (STT)
Estado: COMPLETADO PARCIAL (sesion 006, 2026-04-30) — pendiente validacion E2E Via B.
- WorkOrderEntrySTTView implementada en panel/views.py. Logica POST
  delegada completamente en WorkOrderEntryFormView.post() via MRO (refactor DRY).
- Correccion H021 djlint (sesion 006): inline style div#stt-transcript extraido
  a clase .stt-transcript-box en panel/static/panel/css/panel.css (PMA).
- Motor STT reemplazado (sesion 006): Web Speech API eliminada. Sustituida por
  MediaRecorder API (soporte universal: Chrome, Edge, Firefox, Opera, Android).
  El audio grabado se envia al endpoint WorkOrderEntrySTTExtractView via
  multipart/form-data. Gemini 2.5 Flash procesa el audio directamente y
  devuelve JSON estructurado con los campos del parte. Sin dependencia de
  transcripcion intermedia ni parser JS local (este queda como fallback offline).
- Nuevo endpoint: POST /panel/operator/stt/extract/ (WorkOrderEntrySTTExtractView).
  Recibe audio binario, llama a Gemini con Part.from_bytes, devuelve JSON con:
  fecha (DD/MM/AAAA), maquina_raw, hc (HH:MM), hf (HH:MM),
  descripcion_averia, reparacion, or_val.
- panel/urls.py actualizado: import WorkOrderEntrySTTExtractView + ruta
  operator/stt/extract/ (name=operator_stt_extract).
- stt_entry.html: SECTION 0 rediseñada con botones Iniciar grabacion /
  Detener y procesar, spinner de procesamiento y resumen de resultado.
- Pendiente: validacion E2E Via B en sesion 007.

### 2.11. Correccion identificadores Regla de Oro del Idioma (sesion 008)

Los templates del operario y panel/views.py usaban los nombres de campo
anteriores al renombrado aplicado en H8/S009. La correccion fue atomica
y simultanea en vistas + templates.

Mapa de renombrado aplicado:
  maquina_raw        → machine_raw       (WorkOrderEntryLine.machine_raw)
  descripcion_averia → fault_description (WorkOrderEntryLine.fault_description)
  reparacion         → repair_notes      (WorkOrderEntryLine.repair_notes)
  fecha_incierta     → uncertain_date    (contexto de confirmacion)

Archivos corregidos:
  - panel/views.py:
    - _resolve_machine: codigo__iexact → code__iexact (x2)
    - WorkOrderEntryConfirmView.get: es_activo=True → is_active=True (x4)
    - _parse_entry_lines_from_post: codigo__iexact → code__iexact (x4)
    - _parse_spare_parts_from_post: codigo__iexact → code__iexact (x4)
    - WorkshopAssetAutocompleteView.get: codigo__icontains → code__icontains (x1)
  - panel/templates/panel/operator/confirm_entry.html: todos los name=, variables
    de contexto, condicionales fecha_incierta y JS gate.
  - panel/templates/panel/operator/form_entry.html: idem + _buildBlockRow JS.
  - panel/templates/panel/operator/stt_entry.html: idem.

### 2.12. Widget TimePicker custom (sesion 008)

El atributo step="1800" en input[type="time"] no restringe el selector
visual del navegador (Chrome/Firefox lo ignoran visualmente). Se implemento
un selector custom de dos columnas (horas 00-23 scrollable / minutos 00|30
fijos) como partial Django reutilizable.

Partial: panel/templates/panel/_time_picker_widget.html
  - CSS embebido: .tp-wrapper, .tp-display, .tp-dropdown, .tp-col-hours,
    .tp-col-minutes, .tp-option, .tp-selected, .tp-flagged.
  - JS embebido: motor TimePicker con API publica TimePicker.init(input) /
    TimePicker.initAll(). Oculta el input[type="time"] original (display:none)
    y lo mantiene como campo real del formulario.
  - Dropdown anclado al <body> via getBoundingClientRect() para escapar
    del contexto de apilado de tablas HTMX (fix necesario para edit.html).
  - MutationObserver: activa el widget sobre inputs anadidos dinamicamente
    (_buildBlockRow en form_entry.html, swaps HTMX en edit.html).
  - Dispara evento change nativo sobre el input oculto para compatibilidad
    con hx-trigger="change" de HTMX en _line_row.html.
  - Sincronizacion de flag field-flagged via MutationObserver sobre el input.

Templates que incluyen el partial via {% block extra_scripts %}:
  - panel/templates/panel/operator/form_entry.html
  - panel/templates/panel/operator/stt_entry.html
  - panel/templates/panel/work_orders/edit.html
    (requiere reglas CSS adicionales en {% block extra_head %} para
    integracion con .edit-table: position/overflow en td y overrides
    de .tp-display, .tp-dropdown dentro de la tabla)

### 2.13. Restriccion de minutos a 00/30 con step="1800"

Anadido atributo step="1800" a todos los input[type="time"] de:
  - panel/templates/panel/operator/form_entry.html (x6: dinamico + estatico + JS)
  - panel/templates/panel/operator/stt_entry.html (x4: dinamico + estatico)
  - panel/templates/panel/work_orders/_line_row.html (x2: hc + hf)
El atributo step actua como barrera de validacion HTML5 aunque el navegador
no lo aplique visualmente al selector nativo (cubierto por widget 2.12).

### 2.14. Fix WorkshopAssetAutocompleteView (sesion 008)

Bug: codigo__icontains en el filtro de busqueda (nombre anterior al renombrado
de H8/S009). Corregido a code__icontains en panel/views.py linea ~4929.
El autocompletado de centros de gasto en form_entry.html y stt_entry.html
queda operativo.

### Paso 9 — Validacion E2E de las tres vias
Estado: COMPLETADO PARCIAL (sesion 006, 2026-04-30).
- Via A (Form): VALIDADA. Persistencia correcta, nombre sintetico legible
  en listado (OPERARIO_DD-MM-AAAA.pdf), resolucion de activo funcionando.
- Via B (STT): PENDIENTE validacion E2E. Motor MediaRecorder implementado
  y conectado a Gemini. Pendiente de prueba real en sesion 007.
- Via C (Upload): PENDIENTE validacion E2E.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-27 | —               | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-28 | Pasos 1 y 2     | Arquitectura de roles ampliada: WORKSHOP y DRIVER anadidos a CompanyUser.role. WorkshopRequiredMixin creado en panel/mixins.py. OperatorDashboardView implementada. Navegacion restringida. Template operator/dashboard.html creado. Usuario taller_test_01 validado E2E. Hito pausado para abrir H8. |
| 003    | 2026-04-30 | Pasos 3-5 + fixes | Modelo SparePartLine creado y migrado (0005). Prompt Gemini ampliado (_EXTRACTION_PROMPT_FULL + extract_work_order_page_full). Via C implementada: WorkOrderEntryUploadView + WorkOrderEntryConfirmView + WorkshopAssetAutocompleteView + templates + CSS + pdf2image. Fix multiempresa en _resolve_machine_asset (company=). Fix HTMX _line_row.html (row_class con pk_str). Fix WorkOrderLineRestoreView para partes digitales. Fix doble form en users/form.html. Fix listado roles (badge-supervisor, badge-workshop). |
| 004    | 2026-04-30 | Paso 6 + Paso 7 + fixes fuera HR | Diagnostico y limpieza de duplicados en BD (race condition upload). UniqueConstraint parcial + select_for_update en WorkOrderUploadView. Barrera integridad sine qua non en Vias A y C (server-side + client-side). Boton Anadir repuesto dinamico en confirm_entry.html. Hoja Repuestos en generate_work_order_excel(). WorkOrderEntryFormView implementada (Via A). form_entry.html creado (Neonato Puro). Dashboard Via A activada. |
| 005    | 2026-04-30 | Paso 8 (parcial)                  | WorkOrderEntrySTTView implementada en panel/views.py (PMA). stt_entry.html creado (PEA): grabador Web Speech API es-ES, parser JS client-side, formulario identico a form_entry.html, validacion client-side. urls.py actualizado: import + ruta operator/stt/. Dashboard Via B activada. Pendiente H021 CSS (inline style en stt-transcript div). |
| 006    | 2026-04-30 | Paso 8 (completado parcial) + fixes | H021 CSS corregido: .stt-transcript-box extraida a panel.css (PMA). Nombre sintetico source_pdf en Vias A/B/C (PMA views.py). Fix autocomplete mobile: pointerdown + guardia _selecting en form_entry.html y stt_entry.html. type=date para fecha y type=time para hc/hf en form_entry.html y stt_entry.html. Refactor DRY: STTView.post() delega en FormView.post() via MRO; funciones de modulo _parse_entry_lines_from_post() y _parse_spare_parts_from_post() con resolucion en dos pasadas (raw iexact primero, normalizado despues). Via A validada E2E. Motor STT reemplazado: Web Speech API → MediaRecorder + Gemini audio. Nuevo endpoint WorkOrderEntrySTTExtractView (operator/stt/extract/). Parser JS queda como fallback offline. Pendiente: validacion E2E Via B y C. |
| 007    | 2026-05-01 | Sesion 007 (ver H8 sesion 007)      | Hito pausado para trabajar H8. Ver registro de sesiones de ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md sesion 007 para detalle de cambios aplicados durante esta sesion. |
| 008    | 2026-05-05 | Pasos 8 (fix), 9 (parcial), flecos  | PRIMERA ACCION completada: correccion atomica de identificadores renombrados en panel/views.py (code__iexact, is_active, code__icontains) y en los tres templates del operario (machine_raw, fault_description, repair_notes, uncertain_date) incluido JS gate y _buildBlockRow. Widget TimePicker custom implementado (_time_picker_widget.html): selector de dos columnas 00/30 con dropdown anclado al body, compatible HTMX. Fix WorkshopAssetAutocompleteView (code__icontains). step="1800" en todos los inputs de hora. SEGUNDA y TERCERA ACCION pendientes para sesion 009. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (009)

### CONTEXTO

La sesion 008 completo la PRIMERA ACCION (correccion de identificadores) y
los flecos de UX (widget TimePicker, step 1800, autocompletado centros de
gasto). Quedan pendientes la SEGUNDA ACCION (validacion E2E) y la TERCERA
ACCION (historial de partes), asi como el fleco de autocompletado de
descripciones.

### PRIMERA ACCION — Validacion E2E de las tres vias

Validar en produccion con el usuario taller_test_01 (Chrome/Edge) que las
tres vias funcionan correctamente tras la correccion de identificadores.

Via A (Form) — /panel/operator/form/:
  1. Rellenar un parte completo con al menos dos bloques de trabajo y
     un repuesto. Usar el widget TimePicker para hc/hf.
  2. Verificar que el autocompletado de centros de gasto funciona
     (GET /panel/operator/assets/?q=XXX devuelve JSON correcto).
  3. Confirmar y verificar:
     - Persistencia en BD: WorkOrder (status=DONE, source=DIGITAL),
       WorkOrderEntry, WorkOrderEntryLine(s), SparePartLine(s).
     - Excel descargable con nombre sintetico OPERARIO_DD-MM-AAAA.pdf.
     - Hoja Repuestos en Excel si hay repuestos.
  4. Barrera de integridad: intentar enviar con campos obligatorios vacios
     y verificar que el gate client-side bloquea el submit.

Via B (STT) — /panel/operator/stt/:
  1. Iniciar grabacion, dictar un parte completo en voz alta.
  2. Detener y procesar: verificar que WorkOrderEntrySTTExtractView
     devuelve JSON correcto con los campos pre-rellenados.
  3. Revisar pre-relleno en el formulario (campos machine_raw,
     fault_description, repair_notes, hc, hf correctamente mapeados).
  4. Confirmar y verificar persistencia identica a Via A.

Via C (Upload) — /panel/operator/upload/:
  1. Subir foto o PDF de parte manuscrito.
  2. Verificar extraccion Gemini Vision: confirm_entry.html pre-rellenado
     con datos extraidos, campos flaggeados en rojo si son inciertos.
  3. Corregir campos si procede y confirmar.
  4. Verificar persistencia y Excel con hoja Repuestos.

Barrera de integridad (todas las vias):
  Verificar gate client-side (campo field-flagged resaltado, submit bloqueado)
  y gate server-side (re-render con errores por campo si se manipula el POST).

### SEGUNDA ACCION — Historial de partes y horas por trabajador

Alcance acordado con Alejandro (confirmar al inicio de sesion si ha cambiado):

  Nueva vista: WorkOrderEntryHistoryView (WorkshopRequiredMixin + LoginRequiredMixin).
  Endpoint: GET /panel/operator/history/
  URL name: operator_history

  Comportamiento:
    - Rol WORKSHOP: muestra unicamente los WorkOrders propios del operario
      autenticado (filtro: WorkOrder.created_by = request.user o
      WorkOrderEntry.operator = CompanyUser del request.user — verificar
      que campo existe antes de implementar).
    - Rol ADMIN / SUPERVISOR: puede ver el historial de cualquier operario
      de su empresa. Incluir selector de operario por CompanyUser (GET param
      ?user_pk=XX). Si no se pasa, mostrar listado propio.
    - Agrupacion: por mes (AAAA-MM). Cada grupo muestra cabecera con mes
      y total de horas del mes.
    - Por cada WorkOrder: fecha, numero de partes (entradas), horas totales
      del parte (suma de WorkOrderEntryLine.delta_hours), estado de revision
      (WorkOrder.status badge).
    - Resumen en cabecera de pagina: total horas del mes en curso para el
      operario visualizado.

  Modelo de datos:
    - WorkOrder.created_by: verificar si este campo existe o si el filtro
      debe hacerse por WorkOrderEntry → CompanyUser → user.
    - WorkOrderEntryLine.delta_hours: campo DecimalField ya existente.
    - Solicitar work_order_processor/models.py al inicio de sesion para
      confirmar la cadena de FK antes de implementar.

  Template: panel/templates/panel/operator/history.html (Neonato Puro).
    - Extiende panel/base.html.
    - Tabla Bootstrap agrupada por mes con cabecera colapsable (opcional).
    - Resumen de horas del mes en badge prominente en cabecera.
    - Enlace a Excel del WorkOrder si disponible.

  Sidebar: anadir entrada en panel/templates/panel/_nav_items.html
    para rol WORKSHOP: icono bi-clock-history, texto 'Mis partes',
    url operator_history. Solicitar _nav_items.html al inicio de sesion.

  URL: anadir en panel/urls.py. Solicitar panel/urls.py al inicio de sesion.

### TERCER FLECO — Autocompletado de descripciones (typeahead)

Pendiente de decision de alcance al inicio de sesion. Opciones:
  A) Typeahead sobre fault_description y repair_notes: endpoint GET
     /panel/operator/descriptions/?q=XXX que consulta WorkOrderEntryLine
     filtrando por company y el campo correspondiente icontains, devuelve
     lista de valores unicos. Coste: una consulta BD por tecla pulsada
     con debounce de 300ms. Implementar solo si Alejandro lo confirma.
  B) Dejar solo el autocompletado de centros de gasto (ya operativo).

### Estado de migraciones al cierre de sesion 008

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0003_rename_fields_english                             |
| work_order_processor   | 0007_rename_fields_english                             |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave a solicitar al inicio de sesion 009

OBLIGATORIO solicitarlos via SFTP antes de generar ningun PMA:
  - work_order_processor/models.py (verificar cadena FK para historial)
  - panel/urls.py (anadir ruta operator_history)
  - panel/templates/panel/_nav_items.html (anadir entrada sidebar)
  - panel/views.py (implementar WorkOrderEntryHistoryView)
