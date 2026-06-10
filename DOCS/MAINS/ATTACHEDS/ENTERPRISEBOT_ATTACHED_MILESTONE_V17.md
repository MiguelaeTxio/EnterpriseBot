# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md

# Anexo de Hito V17 -- Albaranes y Ordenes de Trabajo ASISTENCIA
# Proyecto: EnterpriseBot
# Fecha de creacion: 2026-05-29

---

## 1. Vision General del Hito

La seccion de ASISTENCIA necesita digitalizar el flujo completo de trabajo
desde que se acepta un presupuesto (o se genera una orden directa) hasta que
el operario entrega el servicio al cliente y este firma el albaran. El objetivo
es eliminar el papel, reducir errores de transcripcion y dejar el albaran
listo para facturacion con un solo clic desde el panel de administracion.

**Vias de entrada:**
1. Presupuesto aceptado -> se convierte automaticamente en Orden de Trabajo.
2. Orden de Trabajo nueva directa -> sin presupuesto previo.

**Flujo de salida:**
El albaran digital firmado queda en el sistema listo para revision ADMIN
y exportacion a facturacion.

---

## 2. Arquitectura Tecnica -- DISENO REVISADO EN S001

### 2.1. Decisiones de diseno tomadas en S001

**Arquitectura de N vehiculos por servicio:**
Un servicio puede requerir multiples vehiculos simultaneos (grua, coche taller,
plataforma, etc.). Cada vehiculo genera su propio albaran individual. El modelo
original contemplaba unicamente dos fases/operarios -- redisenado para N unidades.

**Estrategia offline:**
La PWA con Service Worker fue descartada. Solucion adoptada: app Android nativa
(AlbaranApp) distribuida desde la app web Django, con persistencia offline via
SharedPreferences y sincronizacion al recuperar cobertura.

**Prototipo AlbaranApp:**
App Android nativa compilada y desplegada. Package: com.miguelaetxio.albaran.
Distribuida desde /panel/budgets/albaran-demo/. Codigo fuente en GitHub repo AlbaranApp.

**Campos adicionales identificados desde PDF Allianz Partners (pendiente validacion):**
- codigo_proveedor, num_poliza, tiempo_llegada, tipo_servicio
- averia, cod_averia, reparacion_in_situ (bool)
- nombre_asegurado, segundo_servicio (bool), gestion_propia_grua (bool)
- accidente (bool), comentarios (cobertura autorizada por la aseguradora)
- diferido (bool -- pendiente confirmar si es sinonimo de is_overnight)
- rueda_gemela (bool), num_pasajeros, anchura, cp_recogida

### 2.2. Modelos Django -- Arquitectura definitiva

WorkOrderAssistance -- Expediente del servicio completo.
  FK a Budget (nullable), Insurer, CompanyUser (gestor), Base.
  Campos de servicio: expediente, num_poliza, codigo_proveedor, tiempo_llegada,
  tipo_servicio, averia, cod_averia, reparacion_in_situ, nombre_asegurado,
  segundo_servicio, gestion_propia_grua, accidente, comentarios, diferido.
  Campos de vehiculo: vehicle_plate, vehicle_brand, vehicle_model, vehicle_color,
  vehicle_height, vehicle_length, vehicle_width, vehicle_pma, rueda_gemela, num_pasajeros.
  Campos de localizacion: vehicle_locality, vehicle_province, pickup_location, cp_recogida.
  status: PENDING / IN_PROGRESS / COMPLETED / INVOICED.
  service_date, created_at, updated_at.

WorkOrderAssistanceUnit -- Un albaran individual por vehiculo que asiste.
  FK a WorkOrderAssistance.
  unit_number -- ordinal (1,2,3...). Albaran impreso: work_order_number-unit_number.
  FK a CompanyUser (operario), machine (matricula), FK nullable a Base.
  is_overnight (bool).
  Datos de servicio: km_phase1, km_phase2, horas espera, horas rescate, departure_fee.
  status: PENDING / IN_PROGRESS / COMPLETED.
  synced_at (DateTimeField nullable) -- momento de sincronizacion offline.
  created_at, updated_at.

WorkOrderAssistanceSignature -- Firma digital del cliente.
  OneToOneField a WorkOrderAssistanceUnit.
  signature_data (TextField, base64 PNG, app Android).
  signed_at (DateTimeField auto).
  signer_name (CharField, opcional).
  signed_offline (bool) -- firma capturada sin cobertura.

WorkOrderAssistanceIncidence -- Delta de incidencias por unidad.
  FK a WorkOrderAssistanceUnit.
  Todos los campos de servicio de la unidad, todos nullable/blank.
  Solo se rellena lo que cambio respecto al albaran original.
  memo (TextField) -- memoriamdum de justificacion obligatorio.
  recorded_by FK a CompanyUser.
  recorded_at (DateTimeField auto).

### 2.3. Grafo de modelos

WorkOrderAssistance (expediente)
    WorkOrderAssistanceUnit x N (un albaran por vehiculo)
        WorkOrderAssistanceSignature (1:1, firma del conductor)
        WorkOrderAssistanceIncidence (0:1, delta de incidencias + memo)

---

## 3. Hoja de Ruta

### Paso 1 -- Modelos y migracion
- Estado: PENDIENTE
- PREREQUISITO: validar con responsables los campos del PDF Allianz antes de makemigrations.
- Confirmar si diferido es sinonimo de is_overnight o campo independiente.
- Crear los cuatro modelos en budgets/models.py.
- Ejecutar makemigrations + migrate.

### Paso 2 -- Vistas y URLs
- Estado: PENDIENTE
- WorkOrderCreateFromBudgetView, WorkOrderCreateDirectView,
  WorkOrderAlbaranView, WorkOrderDetailView, WorkOrderPdfView.

### Paso 3 -- Template movil operario
- Estado: PENDIENTE
- albaran_operario.html: mobile-first, integracion con app Android nativa.

### Paso 4 -- Notificacion WhatsApp al operario
- Estado: PENDIENTE

### Paso 5 -- Exportacion PDF
- Estado: PENDIENTE
- albaran_pdf.html + WorkOrderPdfView con weasyprint.

### Paso 6 -- Boton en BudgetResultView
- Estado: PENDIENTE
- Boton Generar orden de trabajo en result.html cuando budget.status == ACCEPTED.

### Paso 7 -- Sidebar acordeon (incidencia transversal)
- Estado: PENDIENTE
- Refactorizar panel/templates/panel/_nav_items.html para convertir la barra
  lateral en un acordeon colapsable por secciones usando Bootstrap Collapse.
- Cada seccion del sidebar se representa como un bloque colapsable independiente.
- Solo una seccion expandida a la vez (comportamiento acordeon).
- Persistencia del estado via sessionStorage.

### Paso 8 -- Nuevo campo servicios locales (< 20 km)
- Estado: PENDIENTE
- Anadir campo local_service (BooleanField, default=False) en
  WorkOrderAssistanceUnit para identificar servicios de corta distancia.
- Confirmar con responsables si es booleano simple o umbral numerico.

### Paso 9 -- Gestion de horarios nocturnos
- Estado: PENDIENTE
- Modelo NightSchedule con nombre, hora_inicio, hora_fin y grupo
  (choices: INSURER / INDIVIDUAL).
- CRUD completo desde el panel.
- Vinculado al calculo de tarifas nocturnas en WorkOrderAssistanceUnit.

### Paso 10 -- Clonado de aseguradora con nombre nuevo
- Estado: PENDIENTE
- Boton Clonar en listado/detalle de Insurer (app budgets).
- El clon copia todos los campos de tarifa; el usuario introduce nombre nuevo.
- InsurerCloneView en budgets/views.py.

---

## 4. Registro de Sesiones

Sesion | Fecha      | Pasos trabajados | Resumen
S001   | 2026-06-02 | Ninguno (diseno) | Hito iniciado. Rediseno completo arquitectura modelos: N vehiculos por servicio, estrategia offline Android nativa, identificacion campos adicionales PDF Allianz. Incidencias paralelas: fix nocturno/festivo wizard, fix redirect operario, prototipo AlbaranApp Android compilado y desplegado, 6 skills Android creadas, PEE y PICP actualizados.
S002   | 2026-06-09 | Incidencias previas (0.1 y parcial) | Sidebar acordeon Bootstrap Collapse con 9 secciones, persistencia sessionStorage y chevron animado. Fusion IVR+WhatsApp en seccion Telefonia. Iconos homogeneizados: bi-buildings-fill en cabecera sidebar y login, bi-truck-flatbed en acordeon Asistencia, bi-bar-chart en acordeon Analitica, bi-building reservado para Aseguradoras. Bloque 0.2 (autocompletado matricula) pendiente para S003.
S003   | 2026-06-10 | Incidencias previas (0.2 completado) + incidencia is_intensive_override | Fix autocompletado matricula: threshold 2 caracteres, reset lastQuery, busqueda por plate en WorkshopAssetAutocompleteView, matricula visible en dropdown. Fix NameError PresenceStatus en views_workorders.py. Nuevo campo is_intensive_override en CompanyUser (migracion 0033). WorkshopIntensiveToggleView: endpoint POST que persiste el flag y devuelve campos de horario actualizados. Checkbox jornada intensiva en form_entry.html con handler JS que recarga EB_CONFIG y actualiza DOM sin recarga de pagina. Correccion is_default WINTER/SUMMER en BD. PENDIENTE S004: corregir schedule para operarios con workday_schedule_id=2 asignado individualmente que ignoran el override.
S004   | 2026-06-10 | Incidencias (Bloque 0 + HTMX toggle parcial) | Fix Gate 1 _resolve_operator_schedule: condicional is_intensive_override vs schedule intensivo individual (cu=14, cu=12). Implementacion HTMX toggle jornada intensiva: partial _schedule_fields_fragment.html, WorkshopIntensiveToggleView convierte de JSON a render HTML, form_entry.html usa hx-post/hx-target. Fix form_entry_assets.js: prereelleno HC/HF bloques adicionales corregido (EB_CONFIG en tiempo de click, logica tarde/manana). Actualizacion ped-format.skill. Toggle HTMX reporta error en produccion -- diagnostico pendiente S005.
S005   | 2026-06-10 | Incidencias (Bloque 0 parcial) | Diagnostico error toggle HTMX jornada intensiva: causa raiz identificada como conflicto entre JS nativo fetch+json y respuesta HTML de WorkshopIntensiveToggleView. Eliminado bloque <script> nativo del toggle en form_entry.html (115 lineas). Anadido hx-on::after-request al checkbox para feedback visual via HTMX puro. PMA aplicado y validado con djlint + integridad OK. Pendientes S006: Issue A (campos pausa duplicados al volver de intensiva a partida) e Issue B (HF Tarea 1 muestra end_time_afternoon en lugar de end_time_morning al desmarcar intensiva).

---

## 5. Hoja de Ruta para la Siguiente Sesion (S006)

### BLOQUE 0 -- Issue A: campos de pausa duplicados al volver de intensiva a partida

**Contexto exacto del problema:**
Al marcar jornada intensiva y luego desmarcarla, el HTMX swap de
`#schedule-dependent-fields` reemplaza el div correctamente, pero los
campos de inicio/fin pausa aparecen duplicados en pantalla (imagen S005).
Causa probable: existe un segundo bloque de campos de pausa fuera del partial
en `form_entry.html`, o el swap inserta el partial nuevo sin eliminar
correctamente el contenido previo del div objetivo.

**Pasos:**
1. Auditar `form_entry.html` completo buscando cualquier elemento con
   `id="id_lunch_break_start"`, `id="id_lunch_break_end"` o
   `id="lunch-break-times"` fuera del `{% include ... _schedule_fields_fragment %}`.
2. Si existe un segundo bloque: eliminarlo mediante PMA.
3. Verificar que `hx-swap="outerHTML"` en el checkbox apunta a
   `hx-target="#schedule-dependent-fields"` y que ese id existe
   exactamente una vez en el DOM inicial.
4. Reload y confirmar que al ciclar intensiva -> partida no hay duplicados.

### BLOQUE 1 -- Issue B: HF Tarea 1 muestra end_time_afternoon al desmarcar intensiva

**Contexto exacto del problema:**
Al desmarcar jornada intensiva (volver a jornada partida), el campo H.F.
del Tarea 1 se rellena con `end_time_afternoon` (17:30) en lugar de
`end_time_morning` (13:30). Lo correcto es `end_time_morning` porque el
primer bloque del operario termina al final de la manana.

**Causa raiz exacta:**
En `WorkshopIntensiveToggleView.post()` (views_operator.py, linea ~6170):
```python
_first_hf = (
    end_time_afternoon
    if end_time_afternoon
    else end_time_morning
)
```
Esta logica devuelve siempre `end_time_afternoon` cuando existe,
independientemente de si la jornada es intensiva o partida.
Para jornada partida, `_first_hf` debe ser `end_time_morning`.

**Fix exacto en `WorkshopIntensiveToggleView.post()`:**
Sustituir el bloque de calculo de `_first_hf` por:
```python
if activate:
    # Jornada intensiva: usar end_time_morning como HF
    # Intensive shift: use end_time_morning as HF
    _first_hf = end_time_morning if end_time_morning else end_time_afternoon
else:
    # Jornada partida: HF es end_time_morning (fin de manana)
    # Split shift: HF is end_time_morning (end of morning block)
    _first_hf = end_time_morning
```
Ancla OLD exacta en views_operator.py (verificar linea antes de patchear):
```
        _first_hf = (
            end_time_afternoon
            if end_time_afternoon
            else end_time_morning
        )
```
PMA sobre `views_operator.py`. Barrera de fuego: `py_compile`.

### BLOQUE 2 -- Modelos y migracion (Paso 1)

Solo iniciar tras confirmar BLOQUE 0 y BLOQUE 1 resueltos.

Confirmar con responsables si el campo de servicios locales es BooleanField
simple (local_service) o umbral numerico configurable por empresa,
antes de ejecutar makemigrations.

1. Solicitar budgets/models.py completo para obtener anclas reales.
2. Anadir los cuatro modelos nuevos al final mediante PMA:
   WorkOrderAssistance, WorkOrderAssistanceUnit,
   WorkOrderAssistanceSignature, WorkOrderAssistanceIncidence.
   Arquitectura exacta en seccion 2.2 de este anexo.
3. Incorporar campo local_service en WorkOrderAssistanceUnit.
4. Ejecutar makemigrations y migrate. Verificar sin errores.
5. Registrar migraciones en PROJECT_DIRECTORY.
6. Continuar con Paso 2 -- Vistas y URLs.
