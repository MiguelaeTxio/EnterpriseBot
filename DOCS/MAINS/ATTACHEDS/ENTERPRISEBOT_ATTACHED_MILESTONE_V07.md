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
Estado: PENDIENTE REDISENO (S021) — arquitectura de dictado global descartada.
Ver seccion 2.37 para el nuevo diseno aprobado.

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

### 2.36. Flujo de merge implementado — S018

Gate 0 insertado en WorkOrderEntryConfirmView.post() antes de cualquier
INSERT. Detecta WorkOrderEntry preexistente no revisado para la misma
fecha y operario. En caso de conflicto serializa las lineas entrantes en
request.session["pending_merge_lines"] y redirige a WorkOrderEntryMergeView.

Helpers de modulo anadidos a panel/views.py:
  _serialize_pending_lines(parsed_lines, parsed_repuestos, parsed_date)
    Produce dict JSON-safe almacenable en sesion Django.
  _detect_overlaps(existing_lines, new_lines)
    Condicion: hc_e < hf_n AND hc_n < hf_e (intervalos abiertos).
    Devuelve lista de tuplas (idx_e, idx_n, hc_e, hf_e, hc_n, hf_n).

WorkOrderEntryMergeView (WorkshopRequiredMixin, View) anadida a panel/views.py.
Tres acciones POST: discard_new, discard_existing, merge.
El operario puede editar hc/hf antes de elegir accion; JS recalcula
solapamientos en tiempo real sin recargar pagina.

Template: panel/templates/panel/operator/merge_entry.html (PEA, 0 errores djlint).
Ruta: operator/merge/<int:entry_pk>/ (name=operator_merge) en panel/urls.py.

Bug resuelto en S019: boton Desmarcar anadido a la pestana Revisados
de admin_history.html con hx-post apuntando a work_order_review,
hx-target a #review-badge-{{ wo.pk }} y hx-swap outerHTML.

La generacion de Excel pasa a ser responsabilidad del supervisor al
cerrar un WorkPeriod. Se implementa en S023.

### 2.37. Rediseno Via B — Dialogo progresivo con TTS nativo (S021)

DECISION DE DISENO aprobada en S019.

El enfoque anterior de dictado global del parte completo en un unico
bloque de audio es fragil: un error de reconocimiento en cualquier punto
invalida todo el dictado. Se reemplaza por un dialogo progresivo campo
a campo usando speechSynthesis nativo del navegador (coste cero,
sin dependencias externas, Chrome/Edge).

Flujo aprobado:
  1. El sistema sintetiza en voz la pregunta para cada campo.
     Ejemplo: "Diga la fecha por favor."
  2. El operario pulsa el boton de micro y dicta la respuesta.
  3. Web Speech API transcribe la respuesta.
  4. El sistema valida el campo 1:1 antes de avanzar al siguiente.
  5. Si la validacion falla, el sistema repite la pregunta con
     indicacion del error.
  6. Flujo de tareas: el sistema pregunta campo a campo para cada
     WorkOrderEntryLine (maquina, HC, HF, averia, notas).
  7. Al completar una tarea: "Desea anadir otra tarea?"
     Si el operario dice "Si" → nueva tarea.
     Si dice "No" → convergencia al formulario de Via A.
  8. El resultado prerellena form_entry.html como punto de convergencia.
     WorkOrderEntrySTTExtractView queda obsoleta y se retira.

Archivos afectados: panel/views.py (WorkOrderEntrySTTView refactor),
panel/templates/panel/operator/stt_entry.html (rediseno completo).

### 2.38. Gate 0 en WorkOrderEntryFormView.post() — S019

El Gate 0 (un parte por operario por fecha) solo existia en
WorkOrderEntryConfirmView.post() (Via C). Se detecto en S019 que
WorkOrderEntryFormView.post() (Via A) no lo tenia, permitiendo
duplicados al usar el formulario web.
Correccion: bloque Gate 0 identico anadido en WorkOrderEntryFormView.post()
inmediatamente antes del parseo de lineas.

### 2.39. Barrera de fecha minima — _get_min_allowed_date() — S019

Helper de modulo _get_min_allowed_date(cu) anadido a panel/views.py.
Regla: work_date > fecha del ultimo WorkOrderEntry con reviewed=True
del mismo operario. Si no hay partes revisados, sin restriccion.

Barrera server-side insertada en:
  WorkOrderEntryFormView.post() — antes del Gate 0.
  WorkOrderEntryConfirmView.post() — dentro del bloque if _gate0_work_date.

Barrera client-side:
  form_entry.html y stt_entry.html: atributo min="{{ min_date }}" en
  el input type=date.
  confirm_entry.html: atributo data-min-date y texto de ayuda (type=text,
  no admite min nativo).

min_date se pasa al contexto desde get() de FormView y ConfirmView.

### 2.40. Fix JS merge_entry.html — habilitacion boton Fusionar — S019

Bug: al editar los inputs HC/HF en merge_entry.html, el boton Fusionar
no se habilitaba aunque los solapamientos quedaran resueltos.
Causa: el TimePicker custom escribe input.value directamente via JS
sin disparar eventos nativos change/input.
Correccion: anadido listener blur + MutationObserver sobre atributo
value + polling de 300ms como fallback. Los tres mecanismos garantizan
que onTimeInputChange dispara independientemente del metodo de edicion.

### 2.41. Horas extra sin periodo activo — WorkOrderEntryHistoryView — S019

Tab 3 (Horas extra) mostraba bloqueo cuando no habia periodo activo.
Nuevo calculo con prioridad de cuatro casos:
  Caso 1: periodo activo → start=period.start_date, fin=hoy.
  Caso 2: sin activo, hay periodos cerrados → start=ultimo_cerrado.end_date+1.
  Caso 3: sin periodos → start=primer WorkOrderEntry del operario.
  Caso 4: sin partes → ceros, mensaje informativo.
Variable overtime_period_label anadida al contexto para mostrar el
rango calculado en el banner informativo del template.
Template history.html actualizado: el bloqueo {% if active_period %}
sustituido por {% if working_days_count or overtime_worked_hours %}.

### 2.42. Edicion de partes no revisados desde Mi historial — S019

El operario puede editar sus partes digitales no revisados desde la
pestana Periodo actual de history.html.

Implementacion:
  Nueva ruta: operator/form/<int:wo_pk>/edit/ (name=operator_form_edit)
  en panel/urls.py apuntando a WorkOrderEntryFormView.

  WorkOrderEntryFormView.get() ampliado con modo edicion:
    Si wo_pk en kwargs: carga el WorkOrder, verifica uploaded_by=cu y
    reviewed=False, prerellena entradas_enriched y repuestos_enriched
    desde los modelos existentes, pasa edit_mode=True y edit_wo_pk al
    contexto.

  WorkOrderEntryFormView.post() ampliado:
    Si edit_wo_pk en POST: elimina el WorkOrder original (CASCADE)
    antes del INSERT atomico del nuevo.

  form_entry.html: input oculto <input type=hidden name=edit_wo_pk>
  renderizado solo cuando edit_mode=True.

  history.html: boton Editar en columna Acciones (Tab 1) apunta a
  operator_form_edit con wo.pk. Visible solo si not wo.reviewed.

### 2.43. Campo source en dict enriquecido de _enrich_work_orders_for_period — S019

Anadido "source": wo.source al dict devuelto por
_enrich_work_orders_for_period(). Necesario para que history.html
pueda discriminar partes digitales de PDF en la columna Acciones.

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
Estado: PENDIENTE REDISENO (S021) — ver seccion 2.37.

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
| 018    | 2026-05-11 | Flujo merge completo | Gate 0 en WorkOrderEntryConfirmView.post(). Helpers _serialize_pending_lines y _detect_overlaps. WorkOrderEntryMergeView (discard_new / discard_existing / merge). Template merge_entry.html (0 errores djlint). Ruta operator_merge en urls.py. Bug detectado: boton demarcar ausente en pestana Revisados de admin_history.html. |
| 019    | 2026-05-11 | Bugs + mejoras UX + barrera fecha | Boton Desmarcar en pestana Revisados (admin_history.html). Gate 0 anadido a Via A (WorkOrderEntryFormView.post()). Fix JS merge_entry.html (MutationObserver + polling). Barrera fecha minima _get_min_allowed_date() server-side + client-side tres templates. Horas extra sin periodo activo (Tab 3 history.html). Edicion partes no revisados desde Mi historial (operator_form_edit). Diseno Via B dialogo progresivo TTS aprobado. Hoja de ruta S020-S023 definida. |

---

## 5. Hoja de Ruta para la Siguiente Sesion (S020)

### CONTEXTO

S019 resolvio los siguientes bugs e implemento las siguientes mejoras:
  - Boton Desmarcar en pestana Revisados de admin_history.html.
  - Gate 0 anadido a WorkOrderEntryFormView.post() (Via A).
  - Fix JS merge_entry.html: MutationObserver + polling para habilitacion
    del boton Fusionar al corregir horarios.
  - Barrera de fecha minima _get_min_allowed_date() server-side y client-side.
  - Horas extra sin periodo activo: calculo por cuatro casos en Tab 3.
  - Edicion de partes no revisados desde Mi historial (operator_form_edit).

S020 completa la validacion E2E de todas las funcionalidades implementadas
en S018 y S019, y valida el funcionamiento de la Via C.

ADVERTENCIA CRITICA — mantener siempre presente:
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — Validacion E2E flujo de merge completo

Validar manualmente los seis escenarios con el usuario operario:
  1. Operario envia parte para una fecha sin parte existente → flujo normal,
     parte creado correctamente.
  2. Operario envia segundo parte para misma fecha (parte existente sin revisar)
     → Gate 0 activa redireccion a merge_entry.html.
  3. Operario elige Descartar nuevo → parte existente se conserva, nuevo descartado.
  4. Operario elige Sustituir existente → parte antiguo eliminado (CASCADE),
     nuevo creado correctamente.
  5. Operario elige Fusionar sin solapamientos → WorkOrderEntryLines del nuevo
     anadidas al WorkOrderEntry existente. WorkOrder nuevo no creado.
  6. Operario elige Fusionar con solapamientos → boton Fusionar deshabilitado,
     alerta visible, errores por linea. Al corregir HC/HF el boton se habilita.
  7. Supervisor desmarca un parte revisado desde pestana Revisados de
     admin_history.html → parte vuelve a Pendientes.

### SEGUNDA ACCION — Validacion E2E edicion desde Mi historial

  1. Operario pulsa Editar en un parte pendiente desde Tab 1 (Periodo actual).
     → Redirige a /panel/operator/form/<wo_pk>/edit/.
     → Formulario prerelleno con todos los datos del parte original.
  2. Operario modifica datos y guarda.
     → WorkOrder original eliminado (CASCADE). Nuevo WorkOrder creado.
     → Operario regresa a Mi historial con el parte actualizado.
  3. Verificar que partes revisados NO muestran boton Editar.

### TERCERA ACCION — Validacion E2E barrera fecha minima

  1. Con al menos un parte revisado en BD para el operario de prueba:
     → El input de fecha en form_entry.html tiene min=fecha_minima.
     → Intentar enviar un parte con fecha anterior a la minima (forzando
       via POST directo si el selector nativo lo bloquea).
     → El server-side devuelve error claro con la fecha minima permitida.
  2. Verificar el mismo comportamiento en confirm_entry.html (Via C).

### CUARTA ACCION — Validacion E2E Via C (Upload + Gemini Vision)

  1. Subir foto o PDF de parte manuscrito desde /panel/operator/upload/.
  2. Verificar extraccion correcta de campos en confirm_entry.html.
  3. Verificar que las validaciones son identicas a Via A:
     Gate 1 (fecha), Gate 2 (maquina/HC/HF/averia), Gate 3 (repuestos).
  4. Verificar que si hay campos ilegibles el operario puede corregirlos
     en el formulario de confirmacion antes de guardar.
  5. Verificar que si la fecha del parte es anterior a la fecha minima,
     el server-side rechaza el INSERT con mensaje claro.
  6. Verificar que si existe parte previo para la misma fecha (Gate 0),
     la Via C redirige correctamente a merge_entry.html.

### Estado de migraciones al cierre de S019

| App                  | Ultima migracion aplicada                         |
|----------------------|---------------------------------------------------|
| fleet                | 0005_add_first_repair_to_machineasset             |
| work_order_processor | 0013_workorder_source                             |
| ivr_config           | 0015_workerabsence_workperiod                     |
| panel                | 0001_initial (AnalyticsProfile)                   |

### Archivos a solicitar al inicio de S020 via SFTP

No hay PMA planificado al inicio de S020. La sesion comienza con
validacion E2E directa en el navegador con el usuario operario.
Si durante la validacion se detectan bugs, solicitar los archivos
afectados en ese momento.

### Hoja de ruta de sesiones futuras (S021-S023)

S021 — Rediseno Via B: dialogo progresivo con TTS nativo.
  Ver seccion 2.37 para el diseno completo aprobado.
  Archivos afectados: panel/views.py (WorkOrderEntrySTTView refactor),
  panel/templates/panel/operator/stt_entry.html (rediseno completo).
  WorkOrderEntrySTTExtractView queda obsoleta y se retira.

S022 — Diferidos: has_cg_incident + Dropdown CdG Otro.
  WorkOrder.has_cg_incident BooleanField + migracion.
  Dropdown CdG con opcion Otro + free-text, resolucion contra MachineAsset.

S023 — Excel por periodo.
  Al cerrar un WorkPeriod, generacion del Excel consolidado del periodo.
  Integracion en WorkPeriodCloseView.
