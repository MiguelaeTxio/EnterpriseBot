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
npueda discriminar partes digitales de PDF en la columna Acciones.

### 2.44. Eliminacion Via B — Abandono definitivo (S022/S023)

La Via B (dictado por voz via STT) queda eliminada definitivamente del flujo
de entrada del operario. Motivo: baja funcionalidad practica y nula mejora
real respecto a las Vias A y C. Decision tomada en S022, eliminacion fisica
ejecutada en S023.

Acciones ejecutadas (S023):
  - Clases WorkOrderEntrySTTView y WorkOrderEntrySTTExtractView eliminadas de
    panel/views.py. Docstrings de modulo y de OperatorDashboardView actualizados.
    Comentario de helpers compartidos actualizado.
  - Rutas operator/stt/ y operator/stt/extract/ eliminadas de panel/urls.py.
    Imports de ambas vistas eliminados.
  - Boton Via B (tarjeta col-md-4 completa) eliminado de dashboard.html.
    Comentarios de cabecera y paso del tour Driver.js correspondiente eliminados.
  - Template panel/templates/panel/operator/stt_entry.html eliminado del servidor.
  - La Via C se mantiene con validacion reforzada: el parte no se persiste si
    Gemini Vision no puede leer con certeza todos los campos obligatorios.

### 2.45. Tipologia de Averias — Arquitectura aprobada (S022)

Decision de diseno tomada en S022. La clasificacion automatica de averias
se integrara en este hito como cierre final del mismo.

#### Modelo de datos

Dos nuevos campos en WorkOrderEntryLine (work_order_processor/models.py):
  fault_category    — CharField(max_length=40, choices=FaultCategory.choices, blank=True, default="")
  fault_subcategory — CharField(max_length=60, choices=FaultSubcategory.choices, blank=True, default="")

Clases de choices definidas como TextChoices en el mismo modulo.

#### Taxonomia de grupos y subgrupos

Grupos (8):
  ENGINE_TRANSMISSION        — Motor y transmision
  HYDRAULIC                  — Sistema hidraulico
  ELECTRICAL_ELECTRONIC      — Electrico y electronico
  BRAKES_STEERING_SUSPENSION — Frenos, direccion y suspension
  TYRES_RUNNING_GEAR         — Neumaticos y rodadura
  LIFTING_STRUCTURE          — Estructura y sistemas de elevacion
  BODYWORK_CHASSIS           — Carroceria y chasis
  OTHER                      — Otras averias

Subgrupos por grupo (~30 totales):
  ENGINE_TRANSMISSION:        ET_ENGINE, ET_TRANSMISSION, ET_PTO, ET_COOLING, ET_FUEL
  HYDRAULIC:                  HY_PUMP, HY_CYLINDERS, HY_VALVES, HY_OIL, HY_CENTRAL
  ELECTRICAL_ELECTRONIC:      EE_WIRING, EE_SENSORS, EE_CONTROLS, EE_LIGHTS, EE_BATTERY
  BRAKES_STEERING_SUSPENSION: BSS_BRAKES, BSS_STEERING, BSS_SUSPENSION
  TYRES_RUNNING_GEAR:         TRG_TYRES, TRG_AXLES, TRG_TRACKS
  LIFTING_STRUCTURE:          LS_BOOM, LS_HOOK_PULLEYS, LS_CABLE, LS_ROTATION,
                              LS_STABILIZERS, LS_MAST, LS_PLATFORM,
                              LS_FIFTH_WHEEL, LS_CHASSIS_TRAILER
  BODYWORK_CHASSIS:           BC_BODYWORK, BC_CHASSIS
  OTHER:                      OT_OTHER

#### Clasificacion automatica — arquitectura Celery (IMPLEMENTADO S023)

Helper classify_fault(fault_description: str, repair_notes: str) -> tuple[str, str]
en work_order_processor/services.py:
  - Llama a Gemini Flash (_GEMINI_MODEL, Vertex AI).
  - response_mime_type application/json, response_schema con dos campos.
  - thinking_budget=0, temperature=0.0, max_output_tokens=64, timeout=30s.
  - Valida que los codigos devueltos pertenezcan a la taxonomia definida.
  - Devuelve (fault_category, fault_subcategory) o ("", "") en caso de error.

Helper find_cached_classification(fault_description, repair_notes, company)
-> tuple[str, str] | None en work_order_processor/services.py:
  - Pre-consulta dentro de la misma empresa antes de encolar.
  - Busca WorkOrderEntryLine con fault_description + repair_notes identicos
    (LOWER + TRIM) y fault_category no vacio.
  - Scope limitado a la misma empresa (taxonomia varia entre empresas).
  - Si encuentra coincidencia: devuelve (category, subcategory).
  - Si no encuentra o error de BD: devuelve None.

Tarea Celery classify_fault_line(entry_line_pk: int) en tasks.py:
  - @app.task(base=DjangoTask, bind=True, max_retries=3, default_retry_delay=60,
    queue="work_orders")
  - Recupera WorkOrderEntryLine por pk. Si no existe, return silencioso.
  - Guardia de idempotencia: si ambos campos ya estan rellenos, return.
  - Llama a classify_fault(). Persiste via save(update_fields=[...]).
  - Reintenta en 429/RESOURCE_EXHAUSTED con countdown=60s.

Encolado con gate de cache previa en los tres puntos de INSERT:
  1. find_cached_classification() — si coincidencia: copiar directamente.
  2. Si no: classify_fault_line.apply_async(args=[pk], queue="work_orders").
Puntos implementados:
  WorkOrderEntryFormView.post() — Via A
  WorkOrderEntryConfirmView.post() — Via C
  WorkOrderEntryMergeView.post() — discard_existing y merge

#### Backfill de historicos (COMPLETADO — S024)

Comando: work_order_processor/management/commands/classify_entry_lines.py
  - Itera WorkOrderEntryLine.objects.filter(fault_category="") en batches.
  - Llama a find_cached_classification() primero; si no: classify_fault().
  - Persiste los dos campos. Imprime progreso. Idempotente.
  - Ejecucion real S024: 390 lineas procesadas, 75 por cache, 315 por Gemini,
    0 omitidas, 0 errores.
  - Estado: COMPLETADO (S024).

#### Clasificacion en pipeline PDF (COMPLETADO — S024)

Actualizados _EXTRACTION_PROMPT y _EXTRACTION_PROMPT_FULL en services.py para
incluir fault_category y fault_subcategory en el JSON de respuesta. Persistencia
en el propio pipeline (tasks.py) via defaults del update_or_create, con validacion
contra taxonomia antes de persistir. Correccion adicional: llaves literales del
bloque JSON de _CLASSIFY_PROMPT escapadas ({{ }}) para evitar KeyError en
_CLASSIFY_PROMPT.format().
  - Estado: COMPLETADO (S024).

#### Solo para analitica y filtrado

Los campos fault_category y fault_subcategory son exclusivamente para
analitica y filtrado. No se muestran al operario en ningun formulario ni vista.

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
Estado: ABANDONADO (S022) — eliminada definitivamente. Ver seccion 2.44.

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
| 020    | 2026-05-11 | Validacion E2E + bugs merge + tour guiado | Validacion E2E flujos merge (7 escenarios superados), edicion desde historial, barrera fecha minima y Via C. Bugs resueltos: btn Fusionar no se habilitaba (removeAttribute disabled + bloque extra_scripts), TimePicker sin restriccion 30min en merge_entry.html (include _time_picker_widget + step=1800), edicion desde historial activaba Gate 0 sobre el original (pre-eliminacion antes de Gate 0 en WorkOrderEntryFormView.post()). Sistema de visita guiada Driver.js implementado en todas las vistas WORKSHOP: _tour_driver_cdn.html, _tour_workshop.html (motor EbTour), boton Ayuda en base.html, tours en dashboard/form/stt/upload/confirm/history. |
| 021    | 2026-05-12 | Bugs S021 + Reglas jornada + Exportacion admin | PRIMERA ACCION: corrección posicionamiento popover Driver.js (onHighlightStarted + scrollIntoView). SEGUNDA ACCION: entrada por teclado en TimePicker (_openTextEntry + overlay input texto). TERCERA ACCION: Regla B ya correcta; Regla A (excepcion comida 60min 13:00-15:30) en validators.py; Regla C (cobertura minima 8h con excepcion WorkerAbsence) en views.py. CUARTA ACCION Bug A: formulario exportacion admin_history.html corregido (POST + work_order_admin_export + pks explicitos). CUARTA ACCION Bug B: nuevo endpoint WorkOrderMachineFilterView + ruta urls.py + admin_history.js apunta al nuevo endpoint. QUINTA ACCION: overtime_worked_hours anadido al contexto de WorkOrderEntryHistoryView. Incidencia: TimePicker entrada teclado no operativa en produccion; desplegable dinamico maquina no visible en UI. |
| 022    | 2026-05-12 | S022 completo — pendientes S021 + incidencias + tipologia | PRIMERA ACCION: _time_picker_widget.html corregido. SEGUNDA ACCION: admin_history.js showDropdown desanclado al body; WorkOrderMachineFilterView duplicada eliminada; parametro q anadido con filtro icontains. TERCERA ACCION: textos botones historial admin (Editar / Revisar, Marcar revisado). CUARTA ACCION: modal Nuevo periodo rediseñado — selector operario eliminado, end_date opcional, pre-relleno automatico. WorkPeriodCreateView.post() actualizado. QUINTA ACCION: titulo modal ausencia cambiado a Ausencia. DECISION VINCULANTE: periodo global para todos los operarios. Via B abandonada definitivamente. Arquitectura tipologia aprobada: 8 grupos + 30 subgrupos, Celery high_priority, fault_category/fault_subcategory en WorkOrderEntryLine, solo analitica. |
| 023    | 2026-05-13 | Tipologia de Averias — Implementacion parcial (acciones 1-5) | PRIMERA ACCION: Via B eliminada — WorkOrderEntrySTTView, WorkOrderEntrySTTExtractView, rutas STT, boton dashboard, stt_entry.html. SEGUNDA ACCION: FaultCategory y FaultSubcategory (8 grupos, 30 subgrupos) en models.py. Campos fault_category/fault_subcategory en WorkOrderEntryLine. Migracion 0014 aplicada. TERCERA ACCION: classify_fault() en services.py (Gemini Flash, response_schema, thinking_budget=0, validacion taxonomia). CUARTA ACCION: classify_fault_line() en tasks.py (retry 429 countdown=60s, idempotencia, best-effort). QUINTA ACCION: find_cached_classification() en services.py + encolado con gate en tres puntos INSERT de views.py (Via A, Via C, MergeView). Skill pea-pma corregida: AUTORIZADO va directo al mv. Pendientes: PRIMERA ACCION S024 (classify_entry_lines) y SEGUNDA ACCION S024 (_EXTRACTION_PROMPT pipeline PDF). |
| 024    | 2026-05-13 | Tipologia de Averias — Backfill + pipeline PDF (acciones 1-2) | PRIMERA ACCION: neonato classify_entry_lines.py (PEA). Comando de backfill con --batch-size y --dry-run, progreso cada 10 lineas, consulta cache antes de Gemini. Bugs resueltos durante diagnostico: KeyError en _CLASSIFY_PROMPT.format() por llaves literales no escapadas ({{ }}) en bloque JSON de ejemplo — corregido via PMP. Ejecucion real: 390 lineas, 75 cache, 315 Gemini, 0 errores. SEGUNDA ACCION: PMA sobre services.py (_EXTRACTION_PROMPT y _EXTRACTION_PROMPT_FULL ampliados con fault_category/fault_subcategory y taxonomia completa embebida). PMA sobre tasks.py (defaults update_or_create ampliado con _fault_cat/_fault_subcat, validacion contra _VALID_CATEGORIES/_VALID_SUBCATEGORIES, import interno en bloque de persistencia). |

---

## 5. Hoja de Ruta para la Siguiente Sesion (S025)

### CONTEXTO

S024 completo las dos acciones pendientes de la Tipologia de Averias:
  - PRIMERA ACCION: comando classify_entry_lines.py creado y ejecutado.
    390 lineas historicas clasificadas (75 por cache, 315 por Gemini, 0 errores).
    Bug corregido durante diagnostico: KeyError en _CLASSIFY_PROMPT.format()
    por llaves literales { } no escapadas en el bloque JSON de ejemplo del prompt.
    Correccion: {{ }} via PMP en services.py.
  - SEGUNDA ACCION: _EXTRACTION_PROMPT y _EXTRACTION_PROMPT_FULL ampliados
    con fault_category/fault_subcategory y taxonomia completa embebida.
    tasks.py actualizado para persistir ambos campos en el pipeline PDF.

ADVERTENCIA CRITICA — mantener siempre presente:
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — Excel consolidado al cerrar WorkPeriod

  Al ejecutar WorkPeriodCloseView.post(), tras marcar el periodo como cerrado,
  generar automaticamente el Excel consolidado de todos los WorkOrder del periodo.

  Solicitar al inicio de S025 via SFTP:
    panel/views.py — WorkPeriodCloseView.post() completo.
    ivr_config/models.py — modelo WorkPeriod completo.
    work_order_processor/services.py — generate_work_order_excel() completo.

  Logica a implementar en WorkPeriodCloseView.post() tras el cierre del periodo:
    1. Obtener todos los WorkOrder del periodo:
         work_orders = WorkOrder.objects.filter(
             company=company,
             uploaded_by__in=period_operators,   # todos los operarios del periodo
             work_date__gte=period.start_date,
             work_date__lte=period.end_date,
             source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
             reviewed=True,
         )
       Nota: "period_operators" se refiere a todos los CompanyUser con WorkOrderEntry
       cuya work_date este dentro del rango del periodo. Verificar en views.py como
       se construye actualmente el queryset de operarios del periodo.
    2. Por cada WorkOrder en work_orders:
         generate_work_order_excel(work_order.pk)
       La funcion ya existe en services.py y genera el Excel persistiendolo en
       work_order.excel_file. No requiere modificacion.
    3. Mostrar en el template (work_period_list.html o admin_history.html pestana
       Periodos) un indicador de cuantos Excels se han generado al cerrar.

  Consideraciones:
    - generate_work_order_excel() es sincrona. Si hay muchos WorkOrder en el
      periodo, evaluar si conviene encolarla via Celery (tarea existente
      process_work_order_pdf no aplica — crear nueva tarea si es necesario).
    - El Excel existente de cada WorkOrder (generado al crear el parte digital)
      debe sobreescribirse con el consolidado del periodo si ya existe.
    - Solo generar Excels de partes revisados (reviewed=True).

  Archivos afectados: panel/views.py (WorkPeriodCloseView.post()),
  panel/templates/panel/work_orders/work_period_list.html o admin_history.html.
  - Validacion E2E completa: 7 escenarios de merge superados, edicion desde
    historial, barrera fecha minima y Via C validadas.
  - Bug: boton Fusionar no se habilitaba al resolver solapamientos en
    merge_entry.html. Causa: atributo HTML disabled estatico renderizado por
    Django no eliminado por disabled=false JS. Correccion: removeAttribute
    ("disabled") en updateOverlapUI + bloque extra_scripts duplicado eliminado.
  - Bug: TimePicker mostraba minutos libres en merge_entry.html.
    Correccion: include _time_picker_widget.html en bloque extra_scripts
    correcto (estaba en extra_js — bloque inexistente en base.html) + step=1800.
  - Bug: editar parte desde Mi historial activaba Gate 0 sobre el propio
    original. Correccion: pre-eliminacion del WorkOrder original antes de
    ejecutar Gate 0 en WorkOrderEntryFormView.post() mediante bloque
    _edit_wo_pk_pre independiente.
  - Sistema de visita guiada Driver.js implementado: _tour_driver_cdn.html
    (CDN jsDelivr v1.3.6), _tour_workshop.html (motor EbTour con API publica
    register/start/startIfNew/reset/resetAll), boton Ayuda en base.html
    condicionado a roles WORKSHOP/ADMIN, tours en las seis vistas del operario.

ADVERTENCIA CRITICA — mantener siempre presente:
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — Tour guiado: correccion posicionamiento Driver.js

  El popover del ultimo paso del tour (elemento fuera del viewport visible)
  aparece desposicionado respecto al elemento anclado. Causa: layout con
  sidebar fixed y overflow en el contenedor principal interfiere con el
  calculo de coordenadas de Driver.js.
  Solucion propuesta por Alejandro: pendiente de especificar al inicio de S021.
  Archivos afectados: panel/templates/panel/_tour_workshop.html (configuracion
  driver) y/o CSS especifico para .driver-popover.

### SEGUNDA ACCION — TimePicker: admitir entrada por teclado

  El widget _time_picker_widget.html solo admite seleccion via desplegable.
  El operario debe poder escribir la hora directamente con el teclado.
  Implementacion: el input oculto debe hacerse visible y editable cuando el
  operario pulsa una tecla numerica sobre el tp-display, o anadir un input
  de texto sincronizado con el widget que actue como via alternativa de entrada.
  El widget debe seguir controlando que los minutos sean 00 o 30.
  Archivos afectados: panel/templates/panel/_time_picker_widget.html.

### TERCERA ACCION — Logica de jornada laboral y validaciones temporales

  Conjunto de reglas de negocio a implementar en validators.py y panel/views.py:

  Regla A — Hora de comida tolerada:
    Si en la jornada falta exactamente 1 hora en la franja 13:00-15:30
    (es decir, existe un hueco de 60 minutos dentro de ese rango) Y el
    resto de la jornada suma >= 8h, el parte debe poder guardarse sin error.
    El hueco de comida NO cuenta como horas trabajadas.
    Implementar en run_intra_part_validation como regla no bloqueante o
    en _gate_jornada() como excepcion explicita.

  Regla B — Bloques fuera de orden temporal:
    Los bloques de trabajo NO tienen que enviarse en orden cronologico.
    La validacion de solapamiento (R1) debe comparar todos los pares
    (i, j) independientemente del orden de insercion. Actualmente ya
    funciona asi en detectOverlaps JS, pero verificar que run_intra_part_
    validation en validators.py tampoco asume orden.
    Si asume orden, corregirlo para que ordene los bloques por HC antes
    de validar solapamientos.

  Regla C — Cobertura minima de jornada (8h):
    Al guardar un parte, la suma de horas de todos los bloques de trabajo
    debe ser >= 8h, O bien el operario debe tener una ausencia justificada
    o injustificada registrada para esa fecha (WorkerAbsence con
    start_date <= work_date <= end_date).
    Si no se cumple ninguna de las dos condiciones, el server-side debe
    devolver un error claro indicando las horas que faltan para completar
    la jornada.
    Implementar como Gate adicional en WorkOrderEntryFormView.post() y
    WorkOrderEntryConfirmView.post() tras las validaciones existentes.
    NO bloquear si existe WorkerAbsence para esa fecha del operario.

  Archivos afectados: work_order_processor/validators.py, panel/views.py.

### CUARTA ACCION — Bugs en vista de historial admin (WorkOrderAdminHistoryView)

  Bug A — Error al exportar seleccion:
    El boton "Exportar seleccion" en la vista de historial admin produce
    un error. Diagnosticar inspeccionando panel/views.py (WorkOrderAdminHistoryView
    y WorkOrderExportView) y admin_history.html. Solicitar ambos archivos
    al inicio de S021 si el bug no se resuelve en el diagnostico inicial.

  Bug B — Filtro de maquinaria debe ser desplegable dinamico:
    En los filtros del historial admin, el campo de maquinaria es un input
    de texto libre. Debe ser un <select> poblado dinamicamente con los codigos
    de MachineAsset presentes en los WorkOrderEntryLine de los partes que
    cumplen el filtro actual (operario + periodo). Al cambiar el filtro de
    operario o periodo, el desplegable de maquinaria debe actualizarse.
    Implementar via endpoint AJAX GET /panel/work-orders/machines/?operator=X
    &period=Y → {"results": ["G12", "A44", ...]} y JS que pueble el select.
    Archivos afectados: panel/views.py (nuevo endpoint), admin_history.html,
    panel/static/panel/js/admin_history.js.

### QUINTA ACCION — Bugs en historial del operario (WorkOrderEntryHistoryView)

  Bug A — Partes revisados no aparecen en Mi historial (Tab 1 Periodo actual):
    Tab 1 muestra solo partes no revisados del periodo activo. Debe mostrar
    TODOS los partes del periodo activo (revisados y no revisados).
    Revisar el queryset de Tab 1 en WorkOrderEntryHistoryView.get() en
    panel/views.py. El filtro reviewed=False debe eliminarse de Tab 1.

  Bug B — Historico no muestra partes revisados:
    Tab 2 (Historico) tampoco muestra partes revisados agrupados por periodo
    cerrado. Revisar el queryset correspondiente en WorkOrderEntryHistoryView.
    El filtro reviewed=False debe eliminarse de Tab 2 tambien.

  Bug C — Periodo Actual muestra partes ya revisados mezclados:
    Tab 1 muestra partes revisados que no deberian estar en Periodo Actual
    (deberian estar solo en Historico una vez revisados). Revisar la logica
    de asignacion de partes a pestanas: Tab 1 debe mostrar solo partes del
    WorkPeriod activo (revisados y no revisados); Tab 2 los de periodos cerrados.

  Archivos afectados: panel/views.py (WorkOrderEntryHistoryView.get()),
  panel/templates/panel/operator/history.html.

### SEXTA ACCION — Preservacion de datos en formulario al dar error

  Al producirse un error de validacion server-side en WorkOrderEntryFormView
  y WorkOrderEntryConfirmView, el formulario debe:
    1. Re-renderizarse con TODOS los datos introducidos por el operario
       (ya implementado parcialmente — verificar que funciona en todos
       los campos incluyendo repuestos y contadores).
    2. Marcar en rojo (field-flagged) EXCLUSIVAMENTE los campos que han
       producido error, no todos los campos vacios.
  Revisar el bloque de re-render en WorkOrderEntryFormView.post() y
  WorkOrderEntryConfirmView.post() y comparar contra los errores devueltos.
  Archivos afectados: panel/views.py, panel/templates/panel/operator/
  form_entry.html, panel/templates/panel/operator/confirm_entry.html.

## 5. Hoja de Ruta para la Siguiente Sesion (S024)

### CONTEXTO

S023 implemento las primeras cinco acciones de la tipologia de averias:
  - Via B eliminada completamente del servidor (vistas, rutas, template, boton).
  - FaultCategory y FaultSubcategory como TextChoices en models.py.
    Campos fault_category y fault_subcategory en WorkOrderEntryLine.
    Migracion 0014 aplicada y validada en produccion.
  - Helper classify_fault() en services.py (Gemini Flash, Vertex AI,
    response_schema, thinking_budget=0, validacion contra taxonomia).
  - Tarea Celery classify_fault_line() en tasks.py (retry 429, idempotencia).
  - Encolado con gate find_cached_classification() en los tres puntos de
    INSERT de panel/views.py (Via A, Via C, MergeView). Helper
    find_cached_classification() implementado en services.py.
  - Skill pea-pma corregida: flujo AUTORIZADO no repite diffs, va directo al mv.

ADVERTENCIA CRITICA — mantener siempre presente:
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — Comando classify_entry_lines (backfill de historicos)

  Verificar al inicio de S024 en el PROJECT_DIRECTORY si existe el directorio:
    work_order_processor/management/commands/
  Si no existe: crear __init__.py en management/ y en commands/ antes de
  crear el comando.

  Crear neonato puro via PEA:
    work_order_processor/management/commands/classify_entry_lines.py

  Logica del comando:
    - Clase Command(BaseCommand) con help descriptivo.
    - Argumento opcional --batch-size (default=50).
    - Argumento opcional --dry-run (no persiste, solo cuenta e informa).
    - Queryset base: WorkOrderEntryLine.objects.filter(fault_category="")
        .select_related("entry__work_order__company")
        .order_by("pk")
    - Procesamiento en batches usando iterator(chunk_size=batch_size).
    - Por cada linea: llamar a find_cached_classification() primero.
        Si hay coincidencia: persistir directamente (sin Gemini).
        Si no: llamar a classify_fault(fault_description, repair_notes).
        Si el resultado no esta vacio: persistir via
          WorkOrderEntryLine.objects.filter(pk=line.pk).update(
            fault_category=category, fault_subcategory=subcategory
          )
    - Contadores: procesadas, clasificadas_cache, clasificadas_gemini,
      omitidas (resultado vacio), errores.
    - self.stdout.write() con progreso cada 10 lineas y resumen final.
    - Idempotente: las lineas ya clasificadas (fault_category != "") se
      excluyen del queryset base.

  Imports necesarios:
    from django.core.management.base import BaseCommand
    from work_order_processor.models import WorkOrderEntryLine
    from work_order_processor.services import classify_fault, find_cached_classification

### SEGUNDA ACCION — Actualizacion _EXTRACTION_PROMPT en services.py

  Solicitar al inicio de S024 via SFTP:
    work_order_processor/services.py
    work_order_processor/tasks.py

  En services.py — _EXTRACTION_PROMPT (pipeline historico PDF):
    Anadir en el JSON de respuesta esperado dos campos nuevos:
      "fault_category": "<CODIGO_CATEGORIA>",
      "fault_subcategory": "<CODIGO_SUBCATEGORIA>"
    Incluir la taxonomia completa en el prompt para clasificacion en el mismo
    paso de extraccion. El pipeline PDF ya es asincrono, no se encola tarea
    adicional — se persiste directamente en el create() de tasks.py.

  En services.py — _EXTRACTION_PROMPT_FULL (Via C):
    Mismo tratamiento que _EXTRACTION_PROMPT.

  En tasks.py — process_work_order_pdf:
    En el bloque de persistencia de cada WorkOrderEntryLine, extraer
    fault_category y fault_subcategory del dict devuelto por
    extract_work_order_page() y pasarlos al create(). Si el campo no viene
    en el dict o esta vacio, dejar en "".

### Estado de migraciones al cierre de S024

| App                  | Ultima migracion aplicada                                          |
|----------------------|--------------------------------------------------------------------|
| fleet                | 0005_add_first_repair_to_machineasset                              |
| work_order_processor | 0014_workorderentryline_fault_category_and_more                    |
| ivr_config           | 0015_workerabsence_workperiod                                      |
| panel                | 0001_initial (AnalyticsProfile)                                    |

### Archivos a solicitar al inicio de S025 via SFTP

  panel/views.py — WorkPeriodCloseView (PRIMERA ACCION).
  ivr_config/models.py — modelo WorkPeriod (PRIMERA ACCION).
  work_order_processor/services.py — generate_work_order_excel() (PRIMERA ACCION).

### Hoja de ruta de sesiones futuras

S026 — Diferidos: has_cg_incident + Dropdown CdG Otro.
  Diferido hasta Hito 12 (Gestion de Centros de Gasto).
  No implementar hasta que el modelo CdG este maduro.

