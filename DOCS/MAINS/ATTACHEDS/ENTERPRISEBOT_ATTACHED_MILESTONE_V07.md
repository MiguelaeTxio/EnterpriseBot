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
  Gate 2: cada bloque tiene machine_raw no vacio, machine_asset resuelto
          en catalogo, hc y hf presentes, delta_hours positivo, y
          fault_description no vacio.
  Gate 3: cada repuesto tiene material no vacio y quantity positiva.

En caso de fallo: re-renderiza el formulario con mensaje de error detallado
por campo y bloque, sin perder los datos ya introducidos.

Barrera client-side en confirm_entry.html y form_entry.html:
  Replica las tres gates antes del submit. Marca campos con field-flagged,
  hace scroll al alert y bloquea el envio si hay errores. El servidor actua
  como segunda barrera independiente.

### 2.11. Correccion identificadores Regla de Oro del Idioma (sesion 008)

Los templates del operario y panel/views.py usaban los nombres de campo
anteriores al renombrado aplicado en H8/S009. La correccion fue atomica
y simultanea en vistas + templates.

Mapa de renombrado aplicado:
  machine_raw        → machine_raw       (WorkOrderEntryLine.machine_raw)
  fault_description  → fault_description (WorkOrderEntryLine.fault_description)
  repair_notes       → repair_notes      (WorkOrderEntryLine.repair_notes)
  uncertain_date     → uncertain_date    (contexto de confirmacion)

### 2.12. Widget TimePicker custom (sesion 008)

Partial: panel/templates/panel/_time_picker_widget.html
  Selector custom de dos columnas (horas 00-23 scrollable / minutos 00|30
  fijos). Dropdown anclado al body via getBoundingClientRect(). MutationObserver
  para inputs anadidos dinamicamente. Compatible HTMX.

### 2.13. Restriccion de minutos a 00/30 con step="1800"

Anadido a todos los input[type="time"] de form_entry.html, stt_entry.html
y _line_row.html.

### 2.14. Fix WorkshopAssetAutocompleteView (sesion 008)

Bug: code__icontains. Corregido en panel/views.py.

### 2.15. Tercer Fleco — Typeahead de descripciones (sesion 009)

Endpoint GET /panel/operator/descriptions/?field=fault_description&q=XXX
(WorkOrderDescriptionAutocompleteView). Partial _description_typeahead.html.
Incluido en las tres vias de entrada.

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

### 2.20. Horómetros y odómetro en bloques de trabajo — COMPLETADO (sesiones 011-014)

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
Encabezado repuesto rediseñado. _parse_spare_parts_from_post() sin entry_idx.

### 2.23. Auto-registro publico de operarios — WorkerSignupView (sesion 015)

Campos phone y dni en CompanyUser. WorkerSignupForm. WorkerSignupView publica.
Migracion: 0014_companyuser_dni_companyuser_phone.

### 2.24. WorkOrderEntryHistoryView — fix related_name (sesion 015)

entry.entry_lines → entry.lines. Template history.html creado.

### 2.25. Campo WorkOrder.source — segregacion de origen (sesion 016)

Nuevo campo WorkOrder.source (CharField choices):
  PDF_UPLOAD — parte procesado desde PDF escaneado (pipeline historico).
  DIGITAL    — parte introducido manualmente por el operario (Vias A/B/C).
  GENERATED  — parte sintetico generado automaticamente desde una ausencia.

Migracion: 0013_workorder_source.
Backfill: registros existentes clasificados (2 DIGITAL, 8 PDF_UPLOAD).

Impacto en vistas:
  WorkOrderListView — filtra source=PDF_UPLOAD (pipeline supervisor).
  WorkOrderAdminHistoryView._build_base_queryset() — filtra source__in=[DIGITAL, GENERATED].
  WorkOrderEntryHistoryView._base_qs() — filtra source__in=[DIGITAL, GENERATED].
  WorkOrderEntryFormView y WorkOrderEntryConfirmView — asignan source=DIGITAL.
  WorkOrderAdminHistoryView.post() — asigna source=GENERATED.

### 2.26. Modelos WorkerAbsence y WorkPeriod (sesion 016)

Nuevos modelos en ivr_config/models.py. Migracion: 0015_workerabsence_workperiod.

WorkerAbsence:
  company_user FK(CompanyUser, CASCADE, related_name="absences")
  absence_type CharField choices: VACATION/SICK_LEAVE/WORK_ACCIDENT/
               MATERNITY_PATERNITY/BEREAVEMENT/PERSONAL/OTHER
  start_date DateField, end_date DateField
  registered_by FK(CompanyUser, SET_NULL, related_name="registered_absences")
  notes TextField(blank=True)
  created_at/updated_at DateTimeField(auto_now_add/auto_now)

WorkPeriod:
  company_user FK(CompanyUser, CASCADE, related_name="work_periods")
  start_date DateField, end_date DateField(null=True) — null = periodo abierto
  label CharField(max_length=100, blank=True)
  created_by FK(CompanyUser, SET_NULL, related_name="created_work_periods")
  created_at DateTimeField(auto_now_add=True)

### 2.27. WorkOrderAdminHistoryView y WorkerAbsenceCreateView (sesion 016)

Nueva vista WorkOrderAdminHistoryView (SupervisorAccessMixin, View).
Endpoint: GET/POST /panel/work-orders/history/ (name=work_order_admin_history).
ADMIN y SUPERVISOR son redirigidos automaticamente desde WorkOrderEntryHistoryView.

Cuatro pestanas:
  Pendientes  — partes DIGITAL/GENERATED sin revisar. Checkboxes bulk.
                Acciones: Editar, Revisar, Eliminar individual, Marcar revisados
                en bloque, Eliminar en bloque.
  Revisados   — partes revisados. Exportacion Excel disponible SOLO aqui.
  Historico   — todos los partes revisados, filtros cruzados.
  Ausencias   — WorkerAbsence de la empresa. Alta, generacion de partes.

WorkerAbsenceCreateView (SupervisorAccessMixin, View).
Endpoint: POST /panel/worker-absences/create/ (name=worker_absence_create).

Nuevo campo WorkOrder.generated_by FK(CompanyUser, SET_NULL,
  related_name="generated_work_orders"). Migracion: 0012_workorder_generated_by.

### 2.28. Refactor WorkOrderEntryHistoryView para WORKSHOP (sesion 016)

Vista exclusiva para rol WORKSHOP tras redireccion ADMIN/SUPERVISOR.
Cuatro pestanas: Periodo actual / Historico / Horas extra / Ausencias.

Fallback sin WorkPeriod activo: muestra todos los partes del operario
(source__in=[DIGITAL, GENERATED]) cuando no hay WorkPeriod configurado.
Esto evita pantalla vacia al inicio antes de que el supervisor configure periodos.

### 2.29. JS estatico en admin_history (sesion 016)

Logica JS de admin_history.html extraida a archivo estatico:
panel/static/panel/js/admin_history.js
Norma establecida: la logica va en las vistas, los templates solo renderizan,
el JavaScript va en archivos estaticos.

### 2.30. Auditorias Regla de Oro del Idioma (sesion 016)

Correcciones aplicadas en:
  work_order_processor/tasks.py — fecha_incierta, maquina_raw, maquina_norm,
    descripcion_averia, reparacion, delta_horas → EN.
  panel/views.py — machine_asset__codigo → machine_asset__code (AnalyticsDataView).
  ivr_config/signals.py — asset['codigo'] → asset['code'], familia__in → family__in,
    es_activo → is_active, codigos/cod/tipo → codes/code/asset_type.

### Paso 9 — Validacion E2E de las tres vias
Estado: COMPLETADO PARCIAL (sesiones 006-009).
- Via A (Form): VALIDADA.
- Via B (STT): PENDIENTE validacion E2E real con operario.
- Via C (Upload): PENDIENTE validacion E2E real con operario.

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
Estado: COMPLETADO PARCIAL (sesion 006) — pendiente validacion E2E Via B.

### Paso 9 — Validacion E2E de las tres vias
Estado: EN PROGRESO.

### Paso 10 — Vistas de historial y gestion de presencia/ausencia
Estado: COMPLETADO (sesiones 015-016).

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-27 | —               | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-28 | Pasos 1 y 2     | Arquitectura de roles ampliada: WORKSHOP y DRIVER anadidos a CompanyUser.role. WorkshopRequiredMixin creado en panel/mixins.py. OperatorDashboardView implementada. Navegacion restringida. Template operator/dashboard.html creado. Usuario taller_test_01 validado E2E. Hito pausado para abrir H8. |
| 003    | 2026-04-30 | Pasos 3-5 + fixes | Modelo SparePartLine creado y migrado (0005). Prompt Gemini ampliado (_EXTRACTION_PROMPT_FULL + extract_work_order_page_full). Via C implementada: WorkOrderEntryUploadView + WorkOrderEntryConfirmView + WorkshopAssetAutocompleteView + templates + CSS + pdf2image. Fix multiempresa en _resolve_machine_asset (company=). Fix HTMX _line_row.html (row_class con pk_str). Fix WorkOrderLineRestoreView para partes digitales. Fix doble form en users/form.html. Fix listado roles (badge-supervisor, badge-workshop). |
| 004    | 2026-04-30 | Paso 6 + Paso 7 + fixes fuera HR | Diagnostico y limpieza de duplicados en BD (race condition upload). UniqueConstraint parcial + select_for_update en WorkOrderUploadView. Barrera integridad sine qua non en Vias A y C (server-side + client-side). Boton Anadir repuesto dinamico en confirm_entry.html. Hoja Repuestos en generate_work_order_excel(). WorkOrderEntryFormView implementada (Via A). form_entry.html creado (Neonato Puro). Dashboard Via A activada. |
| 005    | 2026-04-30 | Paso 8 (parcial) | WorkOrderEntrySTTView implementada en panel/views.py (PMA). stt_entry.html creado (PEA). Dashboard Via B activada. |
| 006    | 2026-04-30 | Paso 8 (completado parcial) + fixes | H021 CSS corregido. Nombre sintetico source_pdf en Vias A/B/C. Fix autocomplete mobile. type=date/time en formularios. Refactor DRY STTView→FormView via MRO. Motor STT reemplazado: Web Speech API → MediaRecorder + Gemini audio. WorkOrderEntrySTTExtractView. Via A validada E2E. |
| 007    | 2026-05-01 | Sesion 007 (ver H8 sesion 007) | Hito pausado para trabajar H8. |
| 008    | 2026-05-05 | Pasos 8 (fix), 9 (parcial), flecos | PRIMERA ACCION: correccion atomica identificadores Regla de Oro del Idioma. Widget TimePicker custom. Fix WorkshopAssetAutocompleteView (code__icontains). |
| 009    | 2026-05-06 | Flecos, validaciones, refactor UI | Typeahead descripciones. Validaciones R1-R5 en validators.py. Refactor UI repuestos: campo Vehiculo eliminado. |
| 011    | 2026-05-06 | SEGUNDA ACCION completa: R6/R7/R8, horómetros, persistencia | Diagnostico migraciones. validators.py R6/R7/R8. WorkshopAssetDetailView. _parse_entry_lines_from_post con contadores. Tres templates con .meter-field. |
| 012    | 2026-05-07 | unit_price, refactor UX repuestos | SparePartLine.unit_price (migr. 0011). Refactor UX etiquetas y repuestos. Bug UI repuestos activo al cierre. |
| 013    | 2026-05-07 | Diagnostico bugs S012, fix _buildRepuestoRow | Bug UI repuestos resuelto (_buildRepuestoRow JS). Bug persistencia SparePartLine diagnosticado. Validacion dinamica contadores parcial. |
| 014    | 2026-05-07 | Bugs criticos resueltos, E2E Via A validado | Fix validators.py (entries__lines). Fix confirm_entry.html Gate 2b. Fix guard code vacio en tres templates. Fix services.py (mileage/hours). E2E Via A con contadores superada. |
| 014b   | 2026-05-08 | Fix pre-relleno campos contador con valor BD | _applyMeterFields() en tres templates: input.value pre-rellenado con valor actual BD. form_entry.html: parche data-ref-value completo. |
| 015    | 2026-05-08 | Auto-registro operarios + historial + fix related_name | WorkerSignupView publica. Campos phone/dni CompanyUser (migr. 0014). Fix WorkOrderEntryHistoryView (entry_lines→lines). Template history.html creado. |
| 016    | 2026-05-08 | Historial admin, ausencias, campo source, auditorias idioma | PRIMERA ACCION: bloque "Mis partes de hoy" eliminado del dashboard. SEGUNDA ACCION: modelos WorkerAbsence/WorkPeriod + migr. 0015. TERCERA ACCION: WorkOrderAdminHistoryView 4 pestanas + WorkOrder.generated_by (migr. 0012) + WorkOrder.source (migr. 0013) + WorkerAbsenceCreateView + panel/urls.py. CUARTA ACCION: refactor WorkOrderEntryHistoryView para WORKSHOP + fallback sin WorkPeriod. Acciones bulk (checkboxes, Marcar revisados, Eliminar individual/bloque). Fix boton Volver en editor (back_url ?from=taller). JS extraido a admin_history.js (estatico). Auditorias Regla de Oro del Idioma: tasks.py, views.py, signals.py. Fix AnalyticsDataView (machine_asset__code). Fixes signals.py (family__in, is_active, asset['code'], asset_type, codes). |

---

## 5. Hoja de Ruta para la Siguiente Sesion (017)

### CONTEXTO

La sesion 016 completo las cuatro acciones del bloque de historial y
gestion de presencia/ausencia: modelos WorkerAbsence/WorkPeriod,
WorkOrderAdminHistoryView con cuatro pestanas y acciones bulk,
WorkerAbsenceCreateView, refactor WorkOrderEntryHistoryView para WORKSHOP
con fallback sin periodo, campo WorkOrder.source para segregar pipeline PDF
de partes digitales, y varias auditorias de la Regla de Oro del Idioma.

S017 cierra los flecos abiertos de S016 y completa la gestion de periodos
de trabajo del supervisor.

ADVERTENCIA CRITICA (mantener siempre presente):
  El FK WorkOrderEntryLine.entry tiene related_name="lines" (NO "entry_lines").
  Usar siempre entry.lines.all() y prefetch_related("entries__lines").

### PRIMERA ACCION — WorkPeriod CRUD para SUPERVISOR

El supervisor necesita una interfaz para crear, cerrar y etiquetar los
periodos de trabajo de los operarios. Sin esta funcionalidad, el historial
WORKSHOP siempre usa el fallback "todos los partes" del operario.

Modelo WorkPeriod ya existe en ivr_config/models.py (migr. 0015):
  company_user FK(CompanyUser, CASCADE, related_name="work_periods")
  start_date   DateField()
  end_date     DateField(null=True, blank=True)  — null = periodo abierto
  label        CharField(max_length=100, blank=True)
  created_by   FK(CompanyUser, SET_NULL, related_name="created_work_periods")
  created_at   DateTimeField(auto_now_add=True)

Implementar en panel/views.py (PMA):

  WorkPeriodListView (SupervisorAccessMixin, View):
    GET /panel/work-periods/ (name=work_period_list)
    Lista todos los WorkPeriod de la empresa, agrupados por operario,
    descendente por start_date. Muestra: operario, inicio, fin (o "Activo"),
    etiqueta, acciones (cerrar, eliminar).

  WorkPeriodCreateView (SupervisorAccessMixin, View):
    POST /panel/work-periods/create/ (name=work_period_create)
    Recibe: company_user_pk, start_date, label (opcional).
    Validaciones: company_user debe ser WORKSHOP y de la misma empresa.
    start_date no puede solapar con un periodo abierto del mismo operario.
    Crea WorkPeriod con created_by=cu autenticado.

  WorkPeriodCloseView (SupervisorAccessMixin, View):
    POST /panel/work-periods/<pk>/close/ (name=work_period_close)
    Recibe: end_date.
    Validaciones: end_date >= start_date del periodo.
    El periodo debe pertenecer a la empresa autenticada.
    Cierra el periodo asignando end_date.

Integrar en admin_history.html: anadir un bloque de gestion de periodos
en la pestana Ausencias o crear una pestana nueva "Periodos" (decision a
tomar en sesion segun criterio de Miguel Angel).

Archivos a solicitar al inicio via SFTP:
  - panel/views.py
  - panel/urls.py
  - panel/templates/panel/work_orders/admin_history.html

### SEGUNDA ACCION — WorkerAbsence edicion y baja

La pestana Ausencias de WorkOrderAdminHistoryView solo tiene el boton
"Generar partes". Faltan las acciones de editar y dar de baja una ausencia.

Implementar en panel/views.py (PMA):

  WorkerAbsenceUpdateView (SupervisorAccessMixin, View):
    POST /panel/worker-absences/<pk>/update/ (name=worker_absence_update)
    Recibe: absence_type, start_date, end_date, notes.
    Validaciones: ausencia debe pertenecer a la empresa autenticada.
    start_date <= end_date.

  WorkerAbsenceDeleteView (SupervisorAccessMixin, View):
    POST /panel/worker-absences/<pk>/delete/ (name=worker_absence_delete)
    Elimina la ausencia. Scope empresa obligatorio.

En admin_history.html: anadir botones Editar y Eliminar en cada fila de
la tabla de ausencias. Modal de edicion similar al modal de alta existente.

### TERCERA ACCION — Sidebar ADMIN/SUPERVISOR

El item "Historial" del sidebar (panel/templates/panel/base.html) solo
aparece en la seccion TALLER visible para WORKSHOP. Los roles ADMIN y
SUPERVISOR no tienen acceso directo desde el sidebar a work_order_admin_history.

Anadir en base.html (PMA) en la seccion ADMINISTRACION (visible para
ADMIN/SUPERVISOR) un nuevo item:
  <i class="bi bi-clock-history"></i> Historial
  href: {% url 'panel:work_order_admin_history' %}
  Activo cuando active_nav == 'work_order_admin_history'.

Verificar que WorkOrderAdminHistoryView.get() pasa active_nav='work_order_admin_history'
al contexto.

Archivo a solicitar al inicio via SFTP:
  - panel/templates/panel/base.html

### CUARTA ACCION — WorkOrderExportView adaptada para partes digitales

La exportacion Excel desde la pestana Revisados de WorkOrderAdminHistoryView
usa el mismo WorkOrderExportView que el pipeline PDF. Necesita adaptarse para
filtrar source__in=[DIGITAL, GENERATED] y respetar el filtro operator_pk
del contexto.

Verificar en panel/views.py WorkOrderExportView:
  - Anadir filtro source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED]
    cuando la peticion proviene de work_order_admin_history (detectar via
    parametro GET from_admin=1 o via Referer).
  - Alternativa mas limpia: crear WorkOrderAdminExportView separada que
    filtre directamente source__in=[DIGITAL, GENERATED] y operator_pk.
    Endpoint: GET /panel/work-orders/admin-export/ (name=work_order_admin_export).
    Recibe: operator_pk (opcional), date_from, date_to, export_mode.

Archivo a solicitar al inicio via SFTP:
  - panel/views.py (zona WorkOrderExportView)

### QUINTA ACCION — Fix SRI Bootstrap (fleco tecnico)

La consola del navegador muestra 9 Issues relacionados con el SRI de Bootstrap
cargado desde cdn.jsdelivr.net. El error es:
  "Failed to find a valid digest in the 'integrity' attribute for resource
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js'"

El base.html no tiene atributo integrity — el error proviene del propio CDN
jsDelivr que aniade headers SRI en su respuesta HTTP. La solucion es cargar
Bootstrap desde un CDN que no anada SRI headers automaticamente, o bien
alojar los archivos de Bootstrap en staticfiles del proyecto.

Investigar al inicio de sesion: cargar Bootstrap desde unpkg.com como
alternativa (sin SRI headers automaticos) o copiar bootstrap.min.css y
bootstrap.bundle.min.js a panel/static/panel/vendor/.

Archivo a solicitar al inicio via SFTP:
  - panel/templates/panel/base.html

### SEXTA ACCION — I9 Partes solapados del operario

El operario recibe el aviso has_overlap_incident=True en su parte pero no
tiene ninguna accion disponible para corregirlo desde su historial
(WorkOrderEntryHistoryView). Las opciones son:

  Opcion A — Solo lectura con indicador visual:
    En la pestana Periodo actual del historial WORKSHOP, marcar visualmente
    los partes con has_overlap_incident=True con un badge de advertencia
    y un tooltip explicativo. El operario sabe que hay incidencia pero no
    puede modificarla — debe comunicarlo al supervisor.

  Opcion B — Acceso a edicion limitada:
    Permitir al operario acceder al WorkOrderEditView desde su historial
    para corregir las horas del parte solapado.

Decision a tomar en sesion segun criterio de Miguel Angel.

### Estado de migraciones al cierre de sesion 016

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0005_add_first_repair_to_machineasset                  |
| work_order_processor   | 0013_workorder_source                                  |
| ivr_config             | 0015_workerabsence_workperiod                          |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos a solicitar al inicio de sesion 017

OBLIGATORIO via SFTP antes de generar ningun PMA:
  - panel/views.py
  - panel/urls.py
  - panel/templates/panel/base.html
  - panel/templates/panel/work_orders/admin_history.html
