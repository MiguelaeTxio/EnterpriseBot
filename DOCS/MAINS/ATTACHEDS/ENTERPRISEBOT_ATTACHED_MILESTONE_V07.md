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

### 2.15. Tercer Fleco — Typeahead de descripciones (sesion 009)

Implementado autocompletado de texto sobre los campos fault_description y
repair_notes en las tres vias de entrada del operario.

Nuevo endpoint: GET /panel/operator/descriptions/?field=fault_description&q=XXX
  Vista: WorkOrderDescriptionAutocompleteView (WorkshopRequiredMixin + View).
  Whitelist de campos: {"fault_description", "repair_notes"}.
  Minimo de caracteres: 2. Maximo de sugerencias: 8.
  Consulta: WorkOrderEntryLine.objects.filter(entry__work_order__company=company,
  <field>__icontains=q).exclude(<field>="").values_list(<field>, flat=True)
  .distinct().order_by(<field>)[:8].
  Respuesta: JsonResponse({"results": [...]}).

Nuevo partial: panel/templates/panel/_description_typeahead.html
  API publica JS: DescTypeahead.init(textarea) / DescTypeahead.initAll().
  Clase marcadora en textareas: "desc-search" + data-desc-field=<campo>.
  Dropdown flotante con clase .desc-typeahead-dropdown. Guardia pointerdown
  para compatibilidad movil. Auto-inicializacion en DOMContentLoaded.

Incluido en: form_entry.html, stt_entry.html, confirm_entry.html via
{% block extra_scripts %} / antes de {% endblock %}.

Limpieza BD: 9 registros en fault_description y 9 en repair_notes tenian
prefijo de fecha (DD/M/AA) del pipeline historico. Eliminados con ORM
(transaction.atomic + pattern re r'^\d{1,2}/\d{1,2}/\d{2,4}\s+').

### 2.16. Validaciones de integridad temporal (sesion 009)

Nuevo modulo: work_order_processor/validators.py
  Reglas implementadas:
    R1 — Solapamiento intra-parte: dos bloques del mismo envio se solapan.
         Barrera dura. Bloquea el guardado.
    R2 — HF <= HC: hora de fin no posterior a hora de inicio.
         Barrera dura. Bloquea el guardado.
    R3 — Laguna intra-parte >= 30 min: hueco sin cubrir entre bloques consecutivos.
         Barrera dura. Bloquea el guardado. El operario debe cubrir la laguna
         con un bloque de AUSENCIA JUSTIFICADA o AUSENCIA NO JUSTIFICADA.
    R4 — Solapamiento inter-parte: el nuevo parte solapa con un WorkOrder
         existente del mismo operario y fecha. Incidencia diferida — no bloquea.
         Ambos WorkOrders se marcan con has_overlap_incident=True.
    R5 — Parte complementario: misma fecha, sin solapamiento. Se acepta.

  API publica:
    run_intra_part_validation(blocks: List[TimeBlock]) -> IntraPartResult
    validate_inter_overlap(company_user, work_date, blocks, exclude_pk) -> InterPartResult
    parse_blocks_from_post(POST, num_entradas) -> List[TimeBlock]

Nuevo campo WorkOrder: has_overlap_incident BooleanField(default=False, db_index=True).
Migracion: 0008_workorder_has_overlap_incident.

Nuevo partial: panel/templates/panel/_overlap_incident_modal.html
  Modal Bootstrap static que se auto-dispara si el contexto devuelve
  overlap_incidents=True tras persistir. Muestra tabla de partes en conflicto
  con sus fechas. Boton "Ir a la lista de partes".
  Variable de contexto: conflicting_parts = [{"pk": N, "fecha": "DD/MM/YYYY"}].

Integrado en: WorkOrderEntryFormView.post() y WorkOrderEntryConfirmView.post()
  en panel/views.py. WorkOrderEntrySTTView delega en FormView.post() via MRO.

### 2.17. Refactor UI repuestos — vehicle field (sesion 009)

El campo Vehiculo de la seccion de repuestos (SparePartLine.vehicle/vehiculo_raw)
se elimino del formulario del operario para evitar redundancia con el bloque
de trabajo asociado.

Nuevo comportamiento en _parse_spare_parts_from_post():
  Firma ampliada: (POST, company, entry_lines_data=None).
  vehiculo_raw y vehicle_asset se rellenan automaticamente desde el bloque
  de trabajo referenciado por entry_idx usando entry_map[entry_idx]["machine_raw"]
  y entry_map[entry_idx]["machine_asset"]. Sin consulta BD adicional.

UI del encabezado de repuesto (tres vias):
  Encabezado: [badge Repuesto N] asignado a [dropdown inline] con CdG del bloque.
  Texto hardcodeado: "del" [select Bloque X] "asignado a" [span CdG].
  Span .centro-gasto-label .cg-label-static: texto plano no interactivo,
  clase CSS en _description_typeahead.html (.cg-label-static: user-select:none;
  pointer-events:none). Se actualiza en tiempo real via JS al cambiar el select
  del bloque o al escribir en el campo Centro de Gasto del bloque de trabajo.

  form_entry.html y confirm_entry.html: select .repuesto-entry-select con
  data-repuesto-idx en el encabezado. Logica JS: _syncCentroGasto(ridx),
  _attachEntrySelectListener(sel), listener 'input' en machine_raw.
  stt_entry.html: sin select (bloque siempre 1). Solo _syncAllCentroGastoSTT().

Label "Maquina" → "Centro de Gasto" en los tres templates (bloques de trabajo).

### 2.18. Nuevo campo WorkOrder.has_cg_incident — PENDIENTE IMPLEMENTACION

Identificado en sesion 009 como necesario para el subsistema de control de
centros de gasto. Implementacion diferida a sesion 010.

Campo: has_cg_incident BooleanField(default=False, db_index=True).
Semantica: el operario ha asignado un repuesto a un CdG via "Otro" que no
existe en MachineAsset. El supervisor debe validar y crear el CdG en BD.

### 2.19. Dropdown CdG con opcion Otro — PENDIENTE IMPLEMENTACION (sesion 010)

El selector "Bloque asociado" del encabezado de repuesto sera sustituido por
un dropdown personalizado con las siguientes opciones:
  - Un item por cada bloque de trabajo del parte con machine_raw no vacio.
  - Opcion especial "Otro" con input de texto libre.

Comportamiento "Otro":
  - Aparece un input text libre para que el operario escriba el CdG alternativo.
  - El servidor intenta resolver el valor libre contra MachineAsset (iexact).
  - Si no resuelve: vehiculo_raw = texto libre, vehicle_asset = None,
    WorkOrder.has_cg_incident = True.
  - entry_idx = 0 como centinela para el caso Otro.

Notificacion SUPERVISOR/ADMIN al guardar un parte con has_cg_incident=True:
  Pendiente de diseno de sistema de notificaciones (Hito 12).

### 2.20. Horómetros y odómetro en bloques de trabajo — PENDIENTE IMPLEMENTACION (sesion 010)

MachineAsset ya tiene fields mileage (km) y hours (lecturas actuales en BD).

Nuevos campos en WorkOrderEntryLine (sesion 010):
  odometer_reading    DecimalField(null=True, blank=True)  — lectura km al momento.
  engine_hours_reading DecimalField(null=True, blank=True) — lectura horometro motor.
  crane_hours_reading  DecimalField(null=True, blank=True) — lectura horometro grua.

Nuevos campos en MachineAsset (sesion 010):
  has_odometer     BooleanField(default=False) — tiene odometro.
  has_engine_hours BooleanField(default=False) — tiene horometro de motor.
  has_crane_hours  BooleanField(default=False) — tiene horometro de grua.

Logica de validacion (sesion 010):
  Si el MachineAsset del bloque tiene has_odometer=True, el campo
  odometer_reading es OBLIGATORIO (R6 en validators.py).
  Idem para has_engine_hours y has_crane_hours.
  Contraste con lectura anterior en BD: si la lectura nueva < lectura actual
  del activo => error bloqueante. Si salto > umbral configurable => aviso.

Actualizacion de MachineAsset en revision del parte (Hito 12):
  Al marcar un WorkOrder como revisado, el supervisor puede confirmar la
  actualizacion de mileage/hours en MachineAsset desde las lecturas del parte.

### 2.21. Campo unit_price en SparePartLine (sesion 012)

Nuevo campo añadido a SparePartLine para soporte de informes de coste (H9).
No visible ni editable por el operario. Se rellena en H10 desde albaranes
de proveedor o manualmente por SUPERVISOR.

  unit_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

Migracion: 0011_sparepartline_unit_price.

### 2.22. Refactor UX operario — repuestos y etiquetas (sesion 012)

Cambios aplicados en los tres templates del operario (form_entry, stt_entry,
confirm_entry) y en _parse_spare_parts_from_post() en panel/views.py:

  - Etiqueta seccion tareas: "Bloques de trabajo" → "Tareas".
  - Etiqueta campo maquina en bloque: "Centro de Gasto" → "Maquina o Seccion".
  - Encabezado repuesto: "Repuesto {N} del [Bloque X] asignado a {CdG}"
    → "Repuesto {N} asignado a [select CdG]".
  - Select CdG: lista los valores machine_raw unicos no vacios del parte
    mas opcion "Otro — introducir CdG manualmente". Valor por defecto: ultimo
    bloque introducido. Campo libre: name="repuesto_N_cdg_free".
  - Eliminada la indirection entry_idx: vehiculo_raw lo entrega directamente
    el select (name="repuesto_N_vehiculo_raw"). Si value=="__otro__", se lee
    repuesto_N_cdg_free. Sentinel entry_idx eliminado.
  - _parse_spare_parts_from_post(): ya no usa entry_map ni entry_lines_data
    para resolver vehiculo_raw. Resolucion contra MachineAsset en dos pasadas
    para todos los repuestos. Si value=="__otro__", lee cdg_free.
  - Fix artefactos bash incrustados en form_entry.html (lineas ~3290, ~3315).

PENDIENTE (bug activo al cierre de sesion 012):
  La UI de repuestos sigue mostrando la version antigua ("del [Bloque 1]
  asignado a...") a pesar de tener los archivos en disco correctos, collectstatic
  ejecutado, aplicacion recargada y cache vaciada. Causa no identificada.
  Investigar al inicio de sesion 013 antes de cualquier otra accion.

### Paso 9 — Validacion E2E de las tres vias
Estado: COMPLETADO PARCIAL (sesiones 006-009).
- Via A (Form): VALIDADA. Persistencia correcta, nombre sintetico legible.
- Via B (STT): PENDIENTE validacion E2E real con operario.
- Via C (Upload): PENDIENTE validacion E2E real con operario.

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
| 009    | 2026-05-06 | Flecos, validaciones, refactor UI   | Tercer Fleco completado: typeahead descripciones (WorkOrderDescriptionAutocompleteView + partial _description_typeahead.html) en tres vias. Limpieza BD: prefijos fecha en fault_description y repair_notes (9 registros cada uno). Validaciones temporales: work_order_processor/validators.py con R1-R5, campo has_overlap_incident en WorkOrder (migr. 0008), partial _overlap_incident_modal.html integrado en tres vias. Refactor UI repuestos: campo Vehiculo eliminado de formulario, relleno automatico en _parse_spare_parts_from_post() desde entry_map. Encabezado repuesto rediseniado: [Repuesto N] del [select Bloque X] asignado a [span CdG]. Label Maquina → Centro de Gasto en bloques de trabajo. CSS .cg-label-static en _description_typeahead.html. Identificados para sesion 010: has_cg_incident, dropdown CdG con Otro, horometros/odometro en WorkOrderEntryLine, flags has_odometer/has_engine_hours/has_crane_hours en MachineAsset. |
| 011    | 2026-05-06 | SEGUNDA ACCION completa: R6/R7/R8, WorkshopAssetDetailView, UI horómetros, persistencia | Diagnostico migraciones: fleet 0004 y work_order_processor 0010 ya aplicadas en BD. makemigrations --check sin cambios. validators.py: TimeBlock ampliado con machine_asset + tres lecturas de contadores; IntraPartResult.warnings añadido; validate_odometer (R6), validate_engine_hours (R7), validate_crane_hours (R8) implementadas; run_intra_part_validation integra R6/R7/R8; parse_blocks_from_post acepta entry_lines_data. panel/views.py: WorkshopAssetDetailView (GET /panel/operator/assets/detail/) devuelve flags y referencias; _parse_entry_lines_from_post lee y devuelve los tres campos de contador via _parse_decimal(); parse_blocks_from_post enriquecido en FormView y ConfirmView con entry_lines_data=; WorkOrderEntryLine.objects.create persiste odometer_reading, engine_hours_reading, crane_hours_reading en ambas vistas; _meter_warnings propagado a django_messages. panel/urls.py: import y ruta operator_asset_detail. Tres templates (form_entry, stt_entry, confirm_entry): campos .meter-field ocultos por defecto revelados por _applyMeterFields() llamado desde click/mousedown del autocomplete via ASSET_DETAIL_URL. TERCERA ACCION pendiente para sesion 012. |
| 012    | 2026-05-07 | unit_price, refactor UX repuestos, bug UI pendiente | SparePartLine.unit_price añadido (migr. 0011). Refactor UX operario: etiquetas "Bloques de trabajo"→"Tareas", "Centro de Gasto"→"Maquina o Seccion"; encabezado repuesto rediseñado con select CdG directo (machine_raw unicos del parte + Otro); campo cdg_free para valor libre; _parse_spare_parts_from_post() refactorizado sin entry_idx. Fix artefactos bash en form_entry.html. Bug activo al cierre: UI repuestos sigue mostrando version antigua a pesar de archivos en disco correctos, collectstatic y reload ejecutados. Causa no identificada. TERCERA ACCION (historial de partes WorkOrderEntryHistoryView) pendiente. |
| 013    | 2026-05-07 | Diagnóstico bugs S012, fix _buildRepuestoRow, validación contadores parcial | Diagnóstico bug UI repuestos: causa raíz identificada como _buildRepuestoRow JS en form_entry.html no actualizado en S012 (generaba estructura antigua con entry_idx numérico). Corregido via PMA: _buildRepuestoRow reescrita usando _buildCdgOptions() igual que stt_entry.html y confirm_entry.html. Diagnóstico bug persistencia SparePartLine: spd["entry_idx"] eliminado en S012 pero aún accedido en ConfirmView.post() y FormView.post() — PMA preparado y autorizado (mv pendiente). Validación dinámica contadores (Gate 2b JS + _applyMeterFields con data-ref-value): completada en form_entry.html y stt_entry.html. confirm_entry.html bloqueado por fallo en construcción de OLD_A. Validación server-side Gate 2 contadores en views.py: pendiente. WorkOrderEntryHistoryView: pendiente. |
| 014    | 2026-05-07 | Bugs críticos resueltos, E2E Via A con contadores validado | Fix validators.py: prefetch_related entries__entry_lines → entries__lines y entry.entry_lines.all() → entry.lines.all() (AttributeError 500 en POST /operator/form/). Fix confirm_entry.html: PARCHE A _applyMeterFields con escritura data-ref-value en inputs meter-field + PARCHE B Gate 2b JS corregido con if condicionales. Fix guard if (!code) { return; } en onload ASSET_DETAIL_URL en form_entry.html, confirm_entry.html y stt_entry.html (400 en /assets/detail/?code=). Fix services.py: machine_asset.kms → machine_asset.mileage y machine_asset.horas → machine_asset.hours (error generación Excel). Segunda y Tercera Acción de S013 verificadas ya aplicadas en disco. Validación E2E Via A completa con contadores activos en G12 superada. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (015)

### CONTEXTO

La sesion 014 resolvio todos los bugs pendientes de S013 y valido el flujo
E2E Via A con contadores activos. La PRIMERA, SEGUNDA y TERCERA ACCION de
S013 quedaron completadas. La CUARTA ACCION (WorkOrderEntryHistoryView) es
la unica pendiente para S015.

ADVERTENCIA CRITICA sobre related_name: el FK WorkOrderEntryLine.entry tiene
related_name="lines" (NO "entry_lines"). Usar siempre entry.lines.all() y
prefetch_related("entries__lines"). El uso de "entry_lines" causa AttributeError.

### PRIMERA ACCION — WorkOrderEntryHistoryView

Vista nueva: WorkOrderEntryHistoryView (WorkshopRequiredMixin, View).
Endpoint: GET /panel/operator/history/
URL name: operator_history

Archivo: panel/views.py (PMA — insertar tras WorkOrderEntrySTTExtractView,
antes del bloque de vistas de analytics).

Logica de la vista:
  cu = request.user.company_user
  company = cu.company

  Queryset base:
    qs = WorkOrder.objects.filter(company=company, uploaded_by=cu)
          .prefetch_related(
              Prefetch("entries",
                       queryset=WorkOrderEntry.objects.prefetch_related("lines"))
          ).order_by("-id")

  Para ADMIN y SUPERVISOR: si GET ?user_pk=XX, sustituir cu por ese CompanyUser
    (verificar que pertenece a la misma company antes de filtrar).
    users = CompanyUser.objects.filter(company=company, is_active=True).select_related("user")

  Agrupacion por mes desde work_date del primer WorkOrderEntry de cada WorkOrder:
    Para cada WorkOrder: obtener work_date = wo.entries.first().work_date
    Clave de agrupacion: (work_date.year, work_date.month) o None si sin fecha.
    Calcular por WorkOrder:
      num_bloques = sum(entry.lines.count() for entry in wo.entries.all())
      horas_totales = sum(
          line.delta_hours for entry in wo.entries.all()
          for line in entry.lines.all()
          if line.delta_hours is not None
      )
    Agrupar en lista de dicts mensual, descendente por (year, month).

  Label de mes:
    MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",
                6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",
                10:"Octubre",11:"Noviembre",12:"Diciembre"}
    label = f"{MESES_ES[month]} {year}"

  Total de horas del mes: sum de horas_totales de todos los WorkOrder del grupo.

Contexto al template:
  {
    "monthly_groups": [
      {
        "label": "Mayo 2026",
        "total_hours": Decimal,
        "work_orders": [
          {
            "pk": int,
            "fecha": date o None,
            "num_bloques": int,
            "horas_totales": Decimal,
            "reviewed": bool,
          },
        ]
      },
    ],
    "company": company,
    "company_user": cu,
    "active_nav": "operator_history",
    "own_presence": ...,
    "users": queryset o [] (solo ADMIN/SUPERVISOR),
    "selected_user_pk": int o None,
  }

Template: panel/operator/history.html (Neonato Puro).
  - Extiende panel/base.html.
  - Para cada grupo mensual: card con header "Mes AAAA — X h totales (badge)".
  - Para cada WorkOrder: fila con fecha, num_bloques, horas_totales,
    badge "Revisado" (verde) o "Pendiente" (gris) segun reviewed.
  - ADMIN/SUPERVISOR: <select> de usuario con onchange GET ?user_pk=XX.
  - Sin paginacion en primera iteracion.
  - active_nav = "operator_history".

Sidebar panel/templates/panel/_nav_items.html (PMA):
  Descomentar el bloque comentado con 'pendiente Hito 7' y apuntar href a:
    {% url 'panel:operator_history' %}

URL panel/urls.py (PMA):
  - Importar WorkOrderEntryHistoryView.
  - Añadir antes de la seccion de work-orders:
    path("operator/history/", WorkOrderEntryHistoryView.as_view(), name="operator_history"),

### Estado de migraciones al cierre de sesion 014

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0004_alter_machineasset_options_and_more               |
| work_order_processor   | 0011_sparepartline_unit_price                          |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos a solicitar al inicio de sesion 015

OBLIGATORIO via SFTP antes de generar ningun PMA:
  - panel/views.py
  - panel/urls.py
  - panel/templates/panel/_nav_items.html
