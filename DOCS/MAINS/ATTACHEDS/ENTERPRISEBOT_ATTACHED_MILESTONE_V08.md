# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md

# Anexo de Hito V08 — Mejoras Procesador PDF->Excel + HTMX
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-28

---

## 1. Vision General del Hito

El Hito 8 agrupa las mejoras postcierre del Hito 6 sobre el procesador de
partes de trabajo PDF->Excel, mas la implantacion quirurgica de HTMX en los
dos puntos de mayor friccion del panel: la lista de PDFs y el editor de
entradas inline.

El hito se estructura en ocho bloques de trabajo (A-H). Los bloques A-F
quedaron implementados en la sesion 002. Los bloques G y H son el objetivo
de la sesion 003.

---

## 2. Arquitectura Tecnica

### 2.1. Bloque A — HTMX: polling de estado en lista de PDFs (COMPLETADO)

La lista de PDFs muestra el estado de cada WorkOrder mediante polling HTMX
automatico cada 4 segundos en filas PENDING o PROCESSING. El polling se
detiene automaticamente al alcanzar DONE o ERROR.

- WorkOrderStatusFragmentView en panel/views.py.
- Template parcial panel/work_orders/_status_fragment.html.
- Ruta work-orders/<int:pk>/status/ en panel/urls.py.
- CDN HTMX 1.9.12 con SHA384 verificado en base.html.
- Meta tag CSRF + handler htmx:configRequest en base.html.

### 2.2. Bloque B — HTMX: guardado automatico por campo en editor (COMPLETADO)

El editor de entradas inline guarda cada campo automaticamente al cambiar
(hx-trigger="change") sin recarga de pagina. La fila <tr> se reemplaza con
el fragmento devuelto por el servidor (outerHTML swap).

- WorkOrderLineSaveView en panel/views.py.
- Template parcial panel/work_orders/_line_row.html.
- Ruta work-orders/<wo_pk>/lines/<line_pk>/save/ en panel/urls.py.

### 2.3. Bloque C — Editor: mejoras de interaccion (COMPLETADO)

C1 — Insertar linea vacia entre dos existentes (boton + por fila).
C2 — Drag & drop para reordenar entradas (SortableJS 1.15.2).
C3 — Restaurar linea individual desde raw_gemini_response (por linea,
     no por grupo).
C4 — Avisos visuales de incidencias: row-has-flags (fondo amarillo),
     field-flagged (borde naranja).

Vistas anadidas: WorkOrderLineInsertView, WorkOrderLineReorderView,
WorkOrderLineRestoreView (restauracion individual de linea).
Rutas: insert/, reorder/, <line_pk>/restore/.
Neonatos: _entry_group_fragment.html (parcial de grupo completo).
Bugfix E2E: INSERT envuelto en transaction.atomic() para evitar
IntegrityError en (entry_id, line_number).
Bugfix E2E: RESTORE rediseniado para restaurar unicamente la linea
identificada por line_pk usando entradas[line_number-1] del
raw_gemini_response — no el grupo completo.
Nueva funcionalidad E2E: WorkOrderLineDeleteView + boton eliminar
linea individual en _line_row.html + handler JS en edit.html.

### 2.4. Bloque D — Pipeline: correcciones (COMPLETADO)

D1 — Formula COSTE M.O. corregida: $B$3 -> $C$3=0 en generate_work_order_excel().
D2 — _normalise_machine_code() ampliada con _OCR_DIGIT_MAP aplicado
     solo al bloque numerico: O->0, L->1, T->7, S->5, Z->2, G->6.

### 2.5. Bloque E — Upload: deteccion de duplicado (COMPLETADO)

WorkOrderUploadView.post() detecta duplicados (mismo operario + periodo
solapado) antes de crear el WorkOrder. Si se detecta duplicado y el usuario
no ha confirmado sobrescritura, se re-renderiza upload.html con modal
Bootstrap de advertencia. Campo oculto confirm_overwrite=1 autoriza la
eliminacion del duplicado y creacion del nuevo.

### 2.6. Bloque F — Lista PDFs: exportacion de Excels (COMPLETADO PARCIAL)

Checkboxes por fila DONE + boton Descargar seleccion en list.html.
WorkOrderExportView concatena los Excels seleccionados en un unico Workbook
multi-hoja y lo devuelve como descarga.

PENDIENTE rediseno segun especificacion acordada en sesion 002:
- Un solo operario (o varios PDFs del mismo): una sola hoja con todas
  las entradas ordenadas por fecha y membrete del operario al inicio.
- Varios operarios: modal de seleccion de modo antes del POST:
  - "Una hoja por operario": hoja separada por operario con su membrete.
  - "Una sola hoja": todos concatenados con membrete separador por operario,
    ordenados por operario y fecha.
- Campo oculto export_mode (single_sheet / multi_sheet) transporta la
  decision al servidor.
- Deteccion de operarios unicos en JS: si hay un unico operario, saltar
  el modal y enviar directamente con single_sheet.

### 2.7. Bloque G — Campo reviewed + rol SUPERVISOR (PENDIENTE)

Nuevo campo reviewed en WorkOrder:
- reviewed = BooleanField(default=False)
- reviewed_by = ForeignKey(CompanyUser, null=True, blank=True,
  on_delete=SET_NULL, related_name="reviewed_work_orders")
- reviewed_at = DateTimeField(null=True, blank=True)

Nueva migracion requerida en work_order_processor.

Nuevo rol SUPERVISOR en CompanyUser.Role:
- SUPERVISOR = "SUPERVISOR"
- Nueva migracion requerida en ivr_config.

Nuevo mixin SupervisorAccessMixin (acceso para ADMIN y SUPERVISOR):
- Verificar que company_user.role in (ADMIN, SUPERVISOR).
- Redirigir a login si no autenticado, a dashboard si rol insuficiente.

Permisos del rol SUPERVISOR:
- Puede subir PDFs (WorkOrderUploadView).
- Puede ver lista de partes con pestanas (WorkOrderListView rediseniada).
- Puede marcar/desmarcar revisado.
- Puede descargar Excel.
- NO puede editar lineas del editor inline.
- NO puede acceder al resto del panel (secciones, contactos, usuarios, etc.).

WorkOrderMarkReviewedView:
POST /panel/work-orders/<pk>/review/
  - Alterna reviewed True/False en el WorkOrder.
  - Si True: establece reviewed_by y reviewed_at.
  - Si False: limpia reviewed_by y reviewed_at.
  - Devuelve fragmento HTML del badge de revision para HTMX swap.
  - Restringido a SupervisorAccessMixin.

### 2.8. Bloque H — Pestanas en list.html + rediseno Bloque F (PENDIENTE)

Cuatro pestanas Bootstrap en list.html:
  1. "En cola" — WorkOrders en PENDING o PROCESSING.
     Polling HTMX activo unicamente en esta pestana.
  2. "Error" — WorkOrders en estado ERROR.
  3. "Pendiente revision" — WorkOrders DONE con reviewed=False.
  4. "Revisados" — WorkOrders DONE con reviewed=True.

Boton "Marcar revisado" / "Desmarcar" en pestanas 3 y 4 (DONE).
Exportacion multi-Excel (Bloque F rediseniado) solo en pestanas 3 y 4.
Acceso a WorkOrderListView restringido a SupervisorAccessMixin.
WorkOrderUploadView restringido a SupervisorAccessMixin.

---

## 3. Hoja de Ruta

### Paso 1 — HTMX en base.html + WorkOrderStatusFragmentView (Bloque A)
- Estado: COMPLETADO (sesion 002).

### Paso 2 — HTMX guardado automatico por campo en editor (Bloque B)
- Estado: COMPLETADO (sesion 002).

### Paso 3 — Editor: insertar + drag & drop + restaurar + avisos (Bloque C)
- Estado: COMPLETADO con correcciones E2E (sesion 002).
- Bugfixes aplicados: atomic INSERT, restore individual, delete linea.

### Paso 4 — Columna mano de obra + parser OCR (Bloque D)
- Estado: COMPLETADO (sesion 002).

### Paso 5 — Deteccion de duplicado en upload (Bloque E)
- Estado: COMPLETADO (sesion 002).

### Paso 6 — Exportacion de Excels (Bloque F)
- Estado: COMPLETADO PARCIAL (sesion 002) — rediseno pendiente sesion 003.

### Paso 7 — Campo reviewed + rol SUPERVISOR (Bloque G)
- Estado: PENDIENTE.

### Paso 8 — Pestanas en list.html + rediseno Bloque F (Bloque H)
- Estado: PENDIENTE.

### Paso 9 — Validacion E2E completa
- Validar polling HTMX con PDF real en extraccion.
- Validar guardado automatico en editor sin scroll.
- Validar insercion, reordenado, restauracion individual y eliminacion de lineas.
- Validar correccion columna mano de obra en Excel descargado.
- Validar deteccion duplicado + modal + sobrescritura.
- Validar exportacion multi-Excel en todos los modos.
- Validar pestanas y filtrado por estado/revision.
- Validar permisos del rol SUPERVISOR.
- Estado: PENDIENTE.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-28 | —               | Creacion del anexo. Inicio formal del hito. H7 pausado. |
| 002    | 2026-04-28 | 1-6 + E2E       | Implementacion completa bloques A-F. Correcciones E2E: atomic INSERT, restore individual de linea, WorkOrderLineDeleteView, WorkOrderDeleteView. Bugfix formula COSTE M.O. Especificacion acordada para bloques G y H (rol SUPERVISOR, pestanas list.html, rediseno exportacion). |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Objetivo principal
Paso 7 (Bloque G) y Paso 8 (Bloque H).

### PRIMERA ACCION — Bloque G: migraciones y modelos

#### G1 — Campo reviewed en WorkOrder
Archivo: work_order_processor/models.py
Anadir tres campos al modelo WorkOrder tras el campo error_log:

    reviewed    = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_work_orders",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

Generar migracion:
    python -m dotenv run python manage.py makemigrations work_order_processor

#### G2 — Rol SUPERVISOR en CompanyUser
Archivo: ivr_config/models.py
En la clase CompanyUser.Role anadir:
    SUPERVISOR = "SUPERVISOR"

Generar migracion:
    python -m dotenv run python manage.py makemigrations ivr_config

Aplicar ambas migraciones:
    python -m dotenv run python manage.py migrate

#### G3 — SupervisorAccessMixin en panel/mixins.py
Nuevo mixin que permite acceso a ADMIN y SUPERVISOR.
Redirige a login si no autenticado.
Redirige a dashboard con mensaje de error si rol insuficiente.
Verificacion: company_user.role in ("ADMIN", "SUPERVISOR").

#### G4 — WorkOrderMarkReviewedView en panel/views.py
Vista POST que alterna reviewed True/False en el WorkOrder identificado
por pk, acotado a la empresa autenticada.
Si True: reviewed_by = request.user.company_user, reviewed_at = now().
Si False: reviewed_by = None, reviewed_at = None.
Devuelve fragmento HTML del badge de revision (Neonato Puro
_review_badge_fragment.html) para HTMX swap inline en list.html.
Restringido a SupervisorAccessMixin.
Ruta: work-orders/<int:pk>/review/

#### G5 — Restriccion de acceso en vistas existentes
WorkOrderUploadView: cambiar AdminRoleRequiredMixin por SupervisorAccessMixin.
WorkOrderListView: cambiar AdminRoleRequiredMixin por SupervisorAccessMixin.
WorkOrderExportView: cambiar AdminRoleRequiredMixin por SupervisorAccessMixin.
WorkOrderStatusFragmentView: mantener AdminRoleRequiredMixin (HTMX interno).
WorkOrderEditView: mantener AdminRoleRequiredMixin (edicion solo ADMIN).
WorkOrderDeleteView: mantener AdminRoleRequiredMixin.

### SEGUNDA ACCION — Bloque H: pestanas y rediseno list.html

#### H1 — Rediseno WorkOrderListView
Pasar cuatro querysets al contexto:
    wo_queue    = WorkOrder.objects.filter(company=company,
                      status__in=["PENDING","PROCESSING"]).order_by("-upload_date")
    wo_error    = WorkOrder.objects.filter(company=company,
                      status="ERROR").order_by("-upload_date")
    wo_pending  = WorkOrder.objects.filter(company=company,
                      status="DONE", reviewed=False).order_by("-upload_date")
    wo_reviewed = WorkOrder.objects.filter(company=company,
                      status="DONE", reviewed=True).order_by("-upload_date")

#### H2 — Rediseno list.html con pestanas Bootstrap
Cuatro pestanas nav-tabs:
  - "En cola" (badge con count de wo_queue) — tabla con _status_fragment HTMX.
  - "Error" (badge con count de wo_error) — tabla con log de error y boton reintentar.
  - "Pendiente revision" (badge con count de wo_pending) — tabla con boton
    Marcar revisado + checkboxes exportacion.
  - "Revisados" (badge con count de wo_reviewed) — tabla con boton Desmarcar
    + checkboxes exportacion.
La pestana activa por defecto es "Pendiente revision" si wo_pending > 0,
si no "En cola".

#### H3 — Neonato _review_badge_fragment.html
Fragmento HTML del badge de revision devuelto por WorkOrderMarkReviewedView.
Incluye boton Marcar/Desmarcar con atributos HTMX:
  hx-post="{% url 'panel:work_order_review' pk=wo.pk %}"
  hx-trigger="click"
  hx-target="#review-badge-{{ wo.pk }}"
  hx-swap="outerHTML"

#### H4 — Rediseno Bloque F en WorkOrderExportView y list.html
Modal de seleccion de modo (single_sheet / multi_sheet) en list.html.
JS: detectar operarios unicos en seleccion; si uno solo, saltar modal.
Campo oculto export_mode en el formulario de exportacion.
WorkOrderExportView.post():
  Si export_mode == "single_sheet":
    - Agrupar todas las lineas de todos los WorkOrders seleccionados
      por (worker_name, date_key), ordenar por worker_name y date_key.
    - Construir una unica hoja con membrete por operario como separador
      visual (fila con fondo azul oscuro y nombre del operario en negrita)
      antes del primer bloque de cada nuevo operario.
  Si export_mode == "multi_sheet":
    - Agrupar WorkOrders por worker_name.
    - Una hoja por operario con su membrete individual.
    - Dentro de cada hoja, filas ordenadas por date_key.

### Estado de migraciones al inicio de la sesion

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |
| panel                  | 0001_initial (AnalyticsProfile)                        |

NOTA: las migraciones de los Bloques G (reviewed + SUPERVISOR) son la
PRIMERA accion de la sesion 003 — aplicarlas antes de cualquier otra cosa.

### Archivos clave al inicio de la sesion

- work_order_processor/models.py — anadir campos reviewed (G1).
- ivr_config/models.py — anadir rol SUPERVISOR (G2).
- panel/mixins.py — anadir SupervisorAccessMixin (G3).
- panel/views.py — WorkOrderMarkReviewedView (G4) + restricciones (G5)
  + WorkOrderExportView rediseniada (H4).
- panel/urls.py — ruta work-orders/<pk>/review/ (G4) + ajustes.
- panel/templates/panel/work_orders/list.html — pestanas + Bloque F (H2+H4).
- panel/templates/panel/work_orders/_review_badge_fragment.html — Neonato (H3).
