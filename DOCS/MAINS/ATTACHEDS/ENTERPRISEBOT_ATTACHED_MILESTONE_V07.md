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

---

## 5. Hoja de Ruta para la Siguiente Sesion (007)

### Primera accion — Validacion E2E Via B (STT con MediaRecorder + Gemini)

El motor STT fue reemplazado en sesion 006 por MediaRecorder + Gemini audio.
La validacion E2E Via B no pudo completarse al cierre de sesion.

Flujo esperado:
1. Acceder a /panel/operator/stt/ desde taller_test_01 (Chrome/Opera/Firefox).
2. Pulsar "Iniciar grabacion" — el navegador pedira permiso de microfono.
3. Dictar el parte con claridad. Ejemplo:
   "Parte del veinte de abril de dos mil veintisei. Maquina A44.
    De ocho a catorce. Averia en el sistema hidraulico."
4. Pulsar "Detener y procesar" — aparece el spinner.
5. Gemini procesa el audio (endpoint POST /panel/operator/stt/extract/).
6. Los campos del formulario se pre-rellenan con el JSON devuelto.
7. El operario revisa, corrige si es necesario y guarda el parte.
8. Verificar persistencia en BD y Excel descargable con nombre sintetico legible.

Si la llamada Gemini falla (error de red, timeout, formato audio no soportado):
- Comprobar logs del servidor: buscar "# [STTExtract]" en el log de Django.
- El content_type del blob grabado por el navegador puede variar por plataforma.
  En ese caso ajustar la deteccion de MIME en WorkOrderEntrySTTExtractView.post()
  o en el JS (audioMimeType). Los formatos aceptados por Gemini son:
  audio/webm, audio/ogg, audio/mp4, audio/wav, audio/mpeg.

### Segunda accion — Validacion E2E Via C (Upload foto/PDF manuscrito)

Flujo:
1. Acceder a /panel/operator/upload/ desde taller_test_01.
2. Subir foto de parte manuscrito.
3. Verificar extraccion Gemini Vision, formulario de confirmacion campo a campo.
4. Persistencia en BD y Excel con hoja Repuestos.

### Tercera accion — Validacion barrera de integridad (todas las vias)

En cada via, intentar enviar el formulario con campos obligatorios vacios y
verificar que:
- La barrera client-side bloquea el submit y muestra el error antes de enviar.
- Si se fuerza el envio directo (desactivando JS), la barrera server-side
  re-renderiza el formulario con el mensaje de error detallado por campo.

### Tema pendiente de estudio — Colas Celery diferenciadas

Los partes de Via A, B y C persisten sincronamente — no usan Celery.
El riesgo es futuro: si alguna tarea del operario usa Celery, competira
con process_work_order_pdf (historicos, lentos) por los mismos workers.

Estudiar en sesion posterior (no bloquea el Paso 9):
- Auditar enterprise_core/celery.py: configuracion actual de colas y workers.
- Definir cola-historicos para process_work_order_pdf.
- Definir cola-operarios para cualquier tarea futura de alta prioridad.
- Revisar configuracion de workers en PythonAnywhere.

### Estado de migraciones al cierre de sesion 006

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0006_workorder_unique_pdf_hash_per_company             |
| ivr_config             | 0013_alter_companyuser_role                            |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave modificados en sesion 006

- panel/static/panel/css/panel.css — clase .stt-transcript-box (H021 fix) +
  collectstatic ejecutado.
- panel/views.py — source_pdf sintetico en Vias A/B/C; refactor DRY
  (STTView.post() delega en FormView.post(), funciones de modulo
  _parse_entry_lines_from_post y _parse_spare_parts_from_post con resolucion
  en dos pasadas); WorkOrderEntrySTTExtractView (nueva, audio binario Gemini).
- panel/urls.py — ruta operator/stt/extract/ + import WorkOrderEntrySTTExtractView.
- panel/templates/panel/operator/form_entry.html — autocomplete fix mobile
  (pointerdown + _selecting), type=date fecha, type=time hc/hf.
- panel/templates/panel/operator/stt_entry.html — H021 fix (.stt-transcript-box),
  autocomplete fix mobile, type=date fecha, type=time hc/hf, motor STT
  reemplazado: Web Speech API eliminada, MediaRecorder + fetch Gemini audio.
