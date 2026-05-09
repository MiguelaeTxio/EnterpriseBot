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
Estado: COMPLETADO (sesion 004).

#### Via B — STT (Speech-to-Text via Web Speech API)
Estado: COMPLETADO PARCIAL (sesion 006) — pendiente validacion E2E real con operario.

#### Via C — Upload (foto/PDF manuscrito con Gemini Vision)
Estado: COMPLETADO (sesion 003).
- WorkOrderEntryUploadView: rasteriza la imagen/PDF y llama a
  extract_work_order_page_full() (prompt completo, cara delantera + trasera).
- WorkOrderEntryConfirmView: formulario de confirmacion completo con
  validacion campo a campo. Persiste WorkOrder sintetico (status=DONE,
  source_pdf en blanco) + WorkOrderEntry + WorkOrderEntryLine + SparePartLine.
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
de duplicados creando dos WorkOrder identicos (mismo hash SHA-256).
Correccion: bloque transaction.atomic() + select_for_update() en Step 4
de WorkOrderUploadView.post() en panel/views.py.
Complemento: UniqueConstraint parcial sobre (company, source_pdf_hash).
Migracion: 0006_workorder_unique_pdf_hash_per_company.

### 2.10. Barrera de integridad sine qua non en Vias A y C

Toda persistencia de parte digital requiere superar una barrera de integridad
obligatoria antes del INSERT. Los datos deben estar completos al 100%.

Barrera server-side en WorkOrderEntryConfirmView.post() y WorkOrderEntryFormView.post():
  Gate 1: fecha presente y parseable (DD/MM/AAAA o YYYY-MM-DD).
  Gate 2: cada bloque tiene machine_raw, machine_asset, hc, hf, delta_hours
          positivo y fault_description no vacios.
  Gate 3: cada repuesto tiene material no vacio y quantity positiva.

Barrera client-side en confirm_entry.html y form_entry.html replica las tres gates.

### 2.11. Correccion identificadores Regla de Oro del Idioma (sesion 008)

Mapa de renombrado aplicado en templates y panel/views.py:
  machine_raw, fault_description, repair_notes, uncertain_date → EN.

### 2.12. Widget TimePicker custom (sesion 008)

Partial: panel/templates/panel/_time_picker_widget.html
Selector custom de dos columnas (horas 00-23 / minutos 00|30).
MutationObserver para inputs anadidos dinamicamente. Compatible HTMX.

### 2.13. Restriccion de minutos a 00/30 con step="1800"

Anadido a todos los input[type="time"] de form_entry.html, stt_entry.html
y _line_row.html.

### 2.14. Fix WorkshopAssetAutocompleteView (sesion 008)

Bug: code__icontains. Corregido en panel/views.py.

### 2.15. Tercer Fleco — Typeahead de descripciones (sesion 009)

Endpoint GET /panel/operator/descriptions/?field=fault_description&q=XXX
(WorkOrderDescriptionAutocompleteView). Partial _description_typeahead.html.

### 2.16. Validaciones de integridad temporal (sesion 009)

work_order_processor/validators.py — R1 a R5 implementadas.
Campo WorkOrder.has_overlap_incident. Partial _overlap_incident_modal.html.

### 2.17. Refactor UI repuestos — vehicle field (sesion 009)

Campo Vehiculo eliminado del formulario del operario.
_parse_spare_parts_from_post() rellena vehiculo_raw automaticamente.

### 2.18. Nuevo campo WorkOrder.has_cg_incident — PENDIENTE IMPLEMENTACION

Identificado en sesion 009. Implementacion diferida.

### 2.19. Dropdown CdG con opcion Otro — PENDIENTE IMPLEMENTACION

Identificado en sesion 009. Implementacion diferida.

### 2.20. Horometros y odometro en bloques de trabajo — COMPLETADO (sesiones 011-014)

Campos en WorkOrderEntryLine: odometer_reading, engine_hours_reading,
crane_hours_reading (DecimalField null=True, blank=True).
Campos en MachineAsset: has_odometer, has_engine_hours, has_crane_hours
(BooleanField default=False).
Validaciones R6, R7, R8 en validators.py.
Migracion fleet 0005, work_order_processor 0010.

### 2.21. Campo unit_price en SparePartLine (sesion 012)

unit_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True).
Migracion: 0011_sparepartline_unit_price.

### 2.22. Refactor UX operario — repuestos y etiquetas (sesion 012)

Etiquetas "Bloques de trabajo"→"Tareas", "Centro de Gasto"→"Maquina o Seccion".
_parse_spare_parts_from_post() sin entry_idx.

### 2.23. Auto-registro publico de operarios — WorkerSignupView (sesion 015)

Campos phone y dni en CompanyUser. WorkerSignupForm. WorkerSignupView publica.
Migracion: 0014_companyuser_dni_companyuser_phone.

### 2.24. WorkOrderEntryHistoryView — fix related_name (sesion 015)

entry.entry_lines → entry.lines. Template history.html creado.

### 2.25. Campo WorkOrder.source — segregacion de origen (sesion 016)

Nuevo campo WorkOrder.source (CharField choices):
  PDF_UPLOAD / DIGITAL / GENERATED.
Migracion: 0013_workorder_source.

### 2.26. Modelos WorkerAbsence y WorkPeriod (sesion 016)

Nuevos modelos en ivr_config/models.py. Migracion: 0015_workerabsence_workperiod.

### 2.27. WorkOrderAdminHistoryView y gestion de ausencias/periodos (sesiones 016-017)

WorkOrderAdminHistoryView (SupervisorAccessMixin, View).
Endpoint: GET/POST /panel/work-orders/history/ (name=work_order_admin_history).
Cinco pestanas: Pendientes / Revisados / Historico / Ausencias / Periodos.

WorkerAbsenceCreateView — POST /panel/worker-absences/create/
WorkerAbsenceUpdateView — POST /panel/worker-absences/<pk>/update/
WorkerAbsenceDeleteView — POST /panel/worker-absences/<pk>/delete/
WorkPeriodListView      — GET  /panel/work-periods/
WorkPeriodCreateView    — POST /panel/work-periods/create/
WorkPeriodCloseView     — POST /panel/work-periods/<pk>/close/

Nuevo campo WorkOrder.generated_by FK(CompanyUser, SET_NULL).
Migracion: 0012_workorder_generated_by.

### 2.28. Refactor WorkOrderEntryHistoryView para WORKSHOP (sesion 016)

Vista exclusiva para rol WORKSHOP. Cuatro pestanas: Periodo actual /
Historico / Horas extra / Ausencias. Fallback sin WorkPeriod activo.

### 2.29. JS estatico en admin_history (sesion 016)

panel/static/panel/js/admin_history.js extraido del template.

### 2.30. Auditorias Regla de Oro del Idioma (sesion 016)

tasks.py, views.py (AnalyticsDataView), signals.py corregidos.

### 2.31. Fix NameError WorkOrderAdminHistoryView (sesion 017)

Variable period_operator_groups referenciada sin estar definida en get().
Correccion via PMA quirurgico eliminando la linea del contexto.

### 2.32. WorkPeriod CRUD para SUPERVISOR validado (sesion 017)

WorkPeriodListView, WorkPeriodCreateView, WorkPeriodCloseView validadas.
Pestana Periodos integrada en admin_history.html.

### 2.33. WorkerAbsence edicion y baja — template (sesion 017)

Modal modalAbsenceEdit anadido a admin_history.html.
Botones Editar y Eliminar en cada fila de la tabla de ausencias.

### 2.34. Bootstrap alojado localmente en staticfiles (sesion 017)

bootstrap.min.css y bootstrap.bundle.min.js (v5.3.3) descargados a
panel/static/panel/vendor/. Tags CDN sustituidos en base.html por
{% static %}. collectstatic ejecutado.

### 2.35. Rediseno conceptual — Un parte por operario por fecha (S018)

DECISION DE DISENO CRITICA tomada en sesion 017.

#### Problema detectado

El modelo actual permite multiples WorkOrder con la misma work_date para
el mismo operario. Esto es conceptualmente incorrecto: un operario tiene
un unico parte por dia con todas sus tareas agrupadas. La deteccion de
solapamiento posterior (has_overlap_incident) es un parche sobre un error
de concepto.

#### Jerarquia correcta del modelo

Pipeline PDF:
  WorkOrder → periodo completo
    WorkOrderEntry → parte diario (pagina del PDF)
      WorkOrderEntryLine → tarea

Pipeline Digital:
  WorkOrder → parte del dia (1:1 con WorkOrderEntry)
    WorkOrderEntry → el parte (work_date = fecha del dia)
      WorkOrderEntryLine → tarea

Regla invariante: un operario NO puede tener dos WorkOrderEntry con la
misma work_date. Si lo intenta, se activa el flujo de merge.

#### Flujo de merge

Gate 0 en WorkOrderEntryConfirmView.post() antes de cualquier INSERT:

  existing_entry = WorkOrderEntry.objects.filter(
      work_order__company=company,
      work_order__uploaded_by=cu,
      work_order__source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
      work_order__reviewed=False,
      work_date=parsed_date,
  ).select_related("work_order").first()

  Si no existe → flujo normal.
  Si existe y reviewed=True → error, redirigir a historial.
  Si existe y reviewed=False → serializar lineas nuevas en sesion,
    redirigir a WorkOrderEntryMergeView.

Serializacion en request.session["pending_merge_lines"] como lista de dicts:
  machine_raw, machine_asset_pk, fault_description, repair_notes,
  hc ("HH:MM"), hf ("HH:MM"), delta_hours, odometer_reading,
  engine_hours_reading, crane_hours_reading, repuestos:[{material,
  reference, quantity, source, supplier, unit_price}]

WorkOrderEntryMergeView (WorkshopRequiredMixin, View):
  GET  /panel/operator/merge/<int:entry_pk>/
  POST /panel/operator/merge/<int:entry_pk>/

  Acciones POST (merge_action):
    "discard_new"      — limpiar sesion, conservar existente.
    "discard_existing" — eliminar WorkOrder existente (CASCADE), crear nuevo.
    "merge"            — anadir WorkOrderEntryLine nuevas al WorkOrderEntry
                         existente. Sin nuevo WorkOrder. Solo si sin solapamientos.

Deteccion de solapamiento (_detect_overlaps):
  Para cada par (linea_existente, linea_nueva):
    solapamiento = hc_e < hf_n AND hc_n < hf_e
  Ignorar lineas con hc o hf nulos.
  Output: lista de tuplas (idx_e, idx_n, hc_e, hf_e, hc_n, hf_n).

El operario puede editar hc/hf de cualquier linea (existente o nueva)
en merge_entry.html. JS recalcula solapamientos en tiempo real.

Partes revisados (reviewed=True): bloqueados para merge sin excepcion.

#### Excel por periodo — rediseno (pendiente sesion posterior)

La generacion de Excel pasa a ser responsabilidad del supervisor al
cerrar un WorkPeriod. Se implementa en sesion posterior.

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

### Paso 7 — Via A: formulario web estructurado (Form)
Estado: COMPLETADO (2026-04-30).

### Paso 8 — Via B: dictado por voz (STT)
Estado: COMPLETADO PARCIAL (sesion 006) — pendiente validacion E2E.

### Paso 9 — Validacion E2E de las tres vias
Estado: EN PROGRESO.

### Paso 10 — Vistas de historial y gestion de presencia/ausencia
Estado: COMPLETADO (sesiones 015-017).


---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados  | Resumen |
|--------|------------|-------------------|---------|
| 001    | 2026-04-27 | —                 | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-28 | Pasos 1 y 2       | Roles WORKSHOP y DRIVER anadidos. WorkshopRequiredMixin. OperatorDashboardView. Template operator/dashboard.html. Usuario taller_test_01 validado E2E. Hito pausado para H8. |
| 003    | 2026-04-30 | Pasos 3-5 + fixes | SparePartLine creado y migrado (0005). Prompt Gemini ampliado. Via C implementada. Fix multiempresa _resolve_machine_asset. Fix HTMX _line_row.html. Fix WorkOrderLineRestoreView. Fix doble form users/form.html. |
| 004    | 2026-04-30 | Pasos 6-7 + fixes | Race condition upload: select_for_update + UniqueConstraint (0006). Barrera integridad sine qua non Vias A y C. Boton Anadir repuesto dinamico. Hoja Repuestos Excel. WorkOrderEntryFormView (Via A). |
| 005    | 2026-04-30 | Paso 8 (parcial)  | WorkOrderEntrySTTView. stt_entry.html. Via B activada. |
| 006    | 2026-04-30 | Paso 8 + fixes    | Fix CSS H021. Nombre sintetico source_pdf. Fix autocomplete mobile. Refactor DRY STTView→FormView. Motor STT: Web Speech API → MediaRecorder + Gemini audio. WorkOrderEntrySTTExtractView. Via A validada E2E. |
| 007    | 2026-05-01 | —                 | Hito pausado para H8. |
| 008    | 2026-05-05 | Flecos + fixes    | Correccion atomica identificadores Regla de Oro. Widget TimePicker custom. Fix WorkshopAssetAutocompleteView. |
| 009    | 2026-05-06 | Flecos + refactor | Typeahead descripciones. Validaciones R1-R5 validators.py. Refactor UI repuestos: campo Vehiculo eliminado. |
| 011    | 2026-05-06 | SEGUNDA ACCION    | validators.py R6/R7/R8. WorkshopAssetDetailView. _parse_entry_lines_from_post con contadores. Templates con .meter-field. Migraciones fleet 0005 y work_order_processor 0010. |
| 012    | 2026-05-07 | unit_price + UX   | SparePartLine.unit_price (migr. 0011). Refactor etiquetas y repuestos. Bug UI repuestos activo al cierre. |
| 013    | 2026-05-07 | Diagnostico bugs  | Bug UI repuestos resuelto (_buildRepuestoRow JS). Bug persistencia SparePartLine diagnosticado. |
| 014    | 2026-05-07 | Bugs criticos     | Fix validators.py (entries__lines). Fix confirm_entry.html Gate 2b. Fix guard code vacio tres templates. Fix services.py (mileage/hours). E2E Via A con contadores superada. |
| 014b   | 2026-05-08 | Fix pre-relleno   | _applyMeterFields() en tres templates. form_entry.html: parche data-ref-value. |
| 015    | 2026-05-08 | Auto-registro + historial | WorkerSignupView publica. Campos phone/dni (migr. 0014). Fix WorkOrderEntryHistoryView (entry.lines). Template history.html. |
| 016    | 2026-05-08 | Historial admin completo | Modelos WorkerAbsence/WorkPeriod (migr. 0015). WorkOrderAdminHistoryView 5 pestanas. WorkOrder.generated_by (migr. 0012). WorkOrder.source (migr. 0013). WorkerAbsenceCreateView. Refactor WorkOrderEntryHistoryView WORKSHOP. Acciones bulk. JS → admin_history.js estatico. Auditorias idioma: tasks.py, views.py, signals.py. |
| 017    | 2026-05-08 | Fix NameError + validacion CRUD + Bootstrap local + diseno merge | Fix NameError period_operator_groups (PMA). WorkPeriod CRUD validado. Modal modalAbsenceEdit + botones Editar/Eliminar ausencias (PMA). Bootstrap 5.3.3 migrado a staticfiles locales. Diseno completo flujo merge documentado en seccion 2.35. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (S018)

### CONTEXTO

S017 resolvio los flecos de S016, valido el CRUD de periodos, completo
la edicion y baja de ausencias, migro Bootstrap a staticfiles locales y
definio el rediseno conceptual critico: un parte por operario por fecha
con flujo de merge supervisado por el operario.

S018 implementa el flujo de merge completo.

ADVERTENCIA CRITICA — mantener siempre presente:
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — Gate 0 en WorkOrderEntryConfirmView

Modificar WorkOrderEntryConfirmView.post() en panel/views.py (PMA).
Insertar Gate 0 antes de cualquier INSERT en BD:

  existing_entry = WorkOrderEntry.objects.filter(
      work_order__company=company,
      work_order__uploaded_by=cu,
      work_order__source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
      work_order__reviewed=False,
      work_date=parsed_date,
  ).select_related("work_order").first()

  if existing_entry:
      if existing_entry.work_order.reviewed:
          messages.error(request,
              "Este parte ya ha sido revisado por el supervisor y no puede "
              "modificarse. Contacta con tu supervisor para resolver el conflicto."
          )
          return redirect(reverse("panel:operator_history"))

      request.session["pending_merge_lines"] = _serialize_pending_lines(
          parsed_lines, parsed_repuestos, parsed_date
      )
      return redirect(
          reverse("panel:operator_merge", kwargs={"entry_pk": existing_entry.pk})
      )

Funcion auxiliar _serialize_pending_lines(parsed_lines, parsed_repuestos, parsed_date):
  Serializa los datos del formulario como lista de dicts JSON-safe.
  Estructura de cada dict de linea:
    machine_raw, machine_asset_pk (int|null), fault_description,
    repair_notes, hc ("HH:MM"|null), hf ("HH:MM"|null),
    delta_hours (str decimal|null), odometer_reading (str|null),
    engine_hours_reading (str|null), crane_hours_reading (str|null),
    repuestos: [{material, reference, quantity, source, supplier, unit_price}]

Archivos a solicitar al inicio via SFTP:
  panel/views.py

### SEGUNDA ACCION — WorkOrderEntryMergeView

Nueva vista WorkOrderEntryMergeView (WorkshopRequiredMixin, View) en
panel/views.py (PMA — anadir al final del bloque de vistas de operario,
antes de WorkOrderAdminHistoryView).

  GET /panel/operator/merge/<int:entry_pk>/
    - Recuperar existing_entry por pk acotado a empresa y operario.
    - Recuperar pending_merge_lines de request.session.
    - Si sesion vacia → redirect operator_history con error.
    - Calcular solapamientos con _detect_overlaps().
    - Renderizar merge_entry.html.

  POST /panel/operator/merge/<int:entry_pk>/
    merge_action = POST["merge_action"]

    "discard_new":
      Limpiar request.session["pending_merge_lines"].
      Redirect operator_history: "Parte nuevo descartado. Se conserva el parte existente."

    "discard_existing":
      transaction.atomic():
        existing_entry.work_order.delete()  # CASCADE elimina entry y lines.
        Crear nuevo WorkOrder + WorkOrderEntry + WorkOrderEntryLine
        desde pending_merge_lines (mismo flujo INSERT normal).
      Limpiar sesion. Redirect operator_history con mensaje exito.

    "merge":
      Revalidar solapamientos server-side con hc/hf editados del POST.
      Si solapamientos → re-renderizar merge_entry.html con errores.
      Si no → transaction.atomic():
        Para cada linea en pending_merge_lines:
          WorkOrderEntryLine.objects.create(
              entry=existing_entry,
              line_number=existing_entry.lines.count() + idx + 1,
              ... todos los campos ...
          )
          Para cada repuesto en linea["repuestos"]:
            SparePartLine.objects.create(entry_line=nueva_linea, ...)
      Limpiar sesion.
      Redirect operator_history:
        "Parte fusionado correctamente. Tareas anadidas al parte del {fecha}."

Funcion auxiliar _detect_overlaps(existing_lines, new_lines):
  Input: lista de dicts con hc/hf (existentes) + lista de dicts con hc/hf (nuevos).
  Output: lista de tuplas (idx_e, idx_n, hc_e, hf_e, hc_n, hf_n).
  Logica: solapamiento = hc_e < hf_n AND hc_n < hf_e (intervalos abiertos).
  Ignorar entradas con hc o hf nulos.

Edicion de horarios en pantalla de merge:
  El operario puede modificar hc/hf de cualquier linea antes de elegir accion.
  Las lineas editadas se reenvian via POST junto con merge_action.
  MergeView.post() re-parsea los horarios editados y revalida solapamientos.

### TERCERA ACCION — Template merge_entry.html (Neonato Puro — PEA)

Nuevo template: panel/templates/panel/operator/merge_entry.html

Estructura visual:
  Cabecera: "Conflicto de fecha — Ya existe un parte para el {fecha}"
  Alert warning con descripcion del conflicto.
  Grid Bootstrap col-md-6 / col-md-6:
    Columna izquierda — "Parte existente":
      Tabla de lineas existentes con inputs editables hc/hf.
      Lineas solapadas: clase CSS "table-danger".
    Columna derecha — "Parte nuevo":
      Tabla de lineas nuevas con inputs editables hc/hf.
      Lineas solapadas: clase CSS "table-danger".
  Panel inferior — solapamientos detectados (si los hay):
    Lista de conflictos:
    "Tarea {n} (existente) {hc_e}–{hf_e} solapa con Tarea {m} (nueva) {hc_n}–{hf_n}"
  Barra de acciones:
    Boton "Descartar parte nuevo"     — siempre activo, btn-outline-secondary.
    Boton "Descartar parte existente" — siempre activo, btn-outline-danger.
    Boton "Fusionar ambos"            — activo solo sin solapamientos, btn-success.
  JS client-side:
    Recalculo de solapamientos en tiempo real al editar hc/hf.
    Actualiza lista de conflictos y estado boton Fusionar sin recargar pagina.

### CUARTA ACCION — Ruta en panel/urls.py (PMA)

Anadir en panel/urls.py en el bloque de rutas de operario:
  path(
      "operator/merge/<int:entry_pk>/",
      WorkOrderEntryMergeView.as_view(),
      name="operator_merge",
  ),

Anadir WorkOrderEntryMergeView al bloque de imports de panel/urls.py.

Archivos a solicitar al inicio via SFTP:
  panel/urls.py

### Estado de migraciones al cierre de S017

| App                  | Ultima migracion aplicada                         |
|----------------------|---------------------------------------------------|
| fleet                | 0005_add_first_repair_to_machineasset             |
| work_order_processor | 0013_workorder_source                             |
| ivr_config           | 0015_workerabsence_workperiod                     |
| panel                | 0001_initial (AnalyticsProfile)                   |

### Archivos a solicitar al inicio de S018 via SFTP

OBLIGATORIO antes de generar ningun PMA:
  panel/views.py
  panel/urls.py
