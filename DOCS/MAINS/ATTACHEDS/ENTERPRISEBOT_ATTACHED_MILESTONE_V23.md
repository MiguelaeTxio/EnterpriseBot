# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md

# Anexo de Hito V23 — Documentación de Centros de Gasto
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-07-14 (S016)

---

## 1. Visión General del Hito

Cada máquina/centro de gasto (`fleet.MachineAsset`) tiene documentación
oficial dispersa: ficha técnica, tarjeta ITV, certificados de inspección
periódica (OCA u otro organismo), recibos de seguro, inscripción en
registro de grúas, declaración de conformidad CE, etc. Hoy esa
documentación vive en el ordenador de Miguel Ángel (o en papel escaneado),
sin ningún vínculo con la plataforma.

Este hito construye un flujo de **subida e ingesta de documentación desde
la propia plataforma**: el usuario selecciona una carpeta (o varios
archivos) desde su navegador, el sistema examina cada documento con
Gemini Vision, lo clasifica, detecta si hay un "documento maestro" (un
PDF combinado que agrupa varios documentos, como el que se procesó a mano
en S016 para la máquina A-45) y sus componentes individuales, reconcilia
ambos, y persiste **únicamente los documentos individuales** en Google
Drive con su registro correspondiente en BD — vinculados al
`MachineAsset` — para poder recuperarlos rápido desde un listado nuevo,
sin que el usuario necesite saber dónde está guardado cada archivo.

Origen: sesión S016, a partir de un caso real — Miguel Ángel subió un PDF
combinado ("documento maestro") con 8 documentos distintos de la máquina
A-45 (E-6998-BDY): ficha técnica, tarjeta ITV, dos certificados OCA,
recibo de seguro, inscripción de registro y declaración CE. Se separó a
mano en esa sesión (ver conversación S016) como prueba de concepto de lo
que este hito debe automatizar.

---

## 2. Principios Rectores (tal como los planteó Miguel Ángel en S016)

1. **Clasificación por contenido, no por nombre de archivo.** Gemini
   examina cada documento y decide su tipo — nunca se infiere del nombre
   del archivo tal como lo entregó el usuario.
2. **Flujo 100% desde la plataforma web**, no un script de servidor que
   Miguel Ángel ejecute a mano. El usuario entra en "Documentación
   Centros de Gasto" → Administración, elige la máquina, y sube una
   carpeta/varios archivos desde el navegador.
3. **Detección de documento maestro vs. individuales:**
   - Si **no hay** documento maestro entre los archivos subidos → cada
     archivo se trata directamente como documento individual a clasificar
     y persistir.
   - Si **hay** un documento maestro (Gemini lo identifica como un PDF
     que combina contenido de varios de los otros archivos subidos) →
     comparar: ¿la suma de los documentos individuales ya subidos cubre
     por completo el contenido del maestro?
     - **Sí** → el documento maestro no se persiste ni se hace nada más
       con él (los individuales ya lo cubren).
     - **No** (hay contenido en el maestro que no está presente como
       documento individual) → **extraer del maestro** las páginas que
       correspondan a ese contenido faltante y tratarlas como un
       documento individual nuevo, con su propia clasificación.
4. **Solo se persisten documentos individuales**, nunca el maestro
   completo — el maestro es exclusivamente un medio de detección/
   extracción cuando hace falta.
5. **Persistencia doble:** el archivo en Google Drive (mismo patrón que
   `TaskPhoto`/`DeliveryNote` — H7/H10), y un puntero en BD (nuevo
   modelo, vía ORM Django) para que el listado de "Documentación Centros
   de Gasto" pueda recuperar y enlazar cada documento sin que el usuario
   necesite conocer su ubicación real.
6. **Nombres coherentes** tanto en BD como en el propio archivo
   persistido en Drive — legibles por una persona (ej. "Certificado OCA
   2025-2026" en vez de un hash o un nombre de archivo original opaco) y
   útiles para clasificación/búsqueda.
7. **Nueva entrada de menú "Documentación Centros de Gasto"** dentro de
   Administración (sidebar) — listado de toda la documentación
   persistida, filtrable por máquina, con enlace directo a cada archivo
   en Drive.

---

## 3. Arquitectura Técnica (punto de partida — a confirmar/ajustar al inicio de la sesión que retome este hito)

### 3.1. Modelo de datos (nuevo)

Nuevo modelo, app a decidir (candidata: `fleet`, ya que es donde vive
`MachineAsset`, o una app nueva `machine_documents` siguiendo la
directriz arquitectónica de H22 de no seguir engordando apps existentes
— **decisión pendiente, plantear a Miguel Ángel al empezar**):

```
MachineDocument
  machine_asset      FK -> fleet.MachineAsset (CASCADE)
  company             FK -> ivr_config.Company (denormalizado, mismo
                       patrón que TaskPhoto)
  document_type       CharField con choices — categorías a definir con
                       Miguel Ángel (candidatas iniciales, basadas en el
                       caso real de S016: FICHA_TECNICA, TARJETA_ITV,
                       CERTIFICADO_INSPECCION, RECIBO_SEGURO,
                       INSCRIPCION_REGISTRO, DECLARACION_CE, OTRO) —
                       Gemini debe poder proponer una categoría nueva si
                       ninguna de las existentes encaja, sin forzarlo a
                       "OTRO" de forma sistemática.
  display_name         CharField — nombre legible generado (ej.
                       "Certificado OCA 2025-2026 (vigente)").
  source_master_hint   CharField opcional — si el documento se extrajo de
                       un maestro en vez de subirse ya individual, anotar
                       de qué archivo maestro procede (trazabilidad).
  drive_file_id / drive_web_link  — mismo patrón que TaskPhoto/DeliveryNote.
  uploaded_by          FK -> ivr_config.CompanyUser
  created_at
```

### 3.2. Servicio de clasificación (Gemini Vision)

Nuevo servicio (candidato: `fleet/document_classification_service.py`)
que, dado un PDF:
1. Extrae/rasteriza sus páginas (mismo patrón usado a mano en S016:
   `pypdf` para leer, `pdf2image`/`pdftoppm` si hace falta rasterizar
   páginas sin texto).
2. Envía el contenido a Gemini Vision pidiendo: tipo de documento,
   nombre legible propuesto, y — cuando se procesan varios archivos a la
   vez — si este archivo concreto parece ser un "documento maestro" que
   combina el contenido de otros archivos del mismo lote.
3. Si se detecta maestro: comparación de cobertura (¿qué páginas/
   contenido del maestro no aparece en ningún individual?) y extracción
   de las páginas faltantes a un PDF nuevo (mismo mecanismo `pypdf`
   `PdfWriter`/`add_page` usado a mano en S016).

**Verificar en línea (directriz 4.4 del master document, SINE QUA NON)**
antes de implementar: API de Gemini Vision para PDFs multi-página
(`google-genai` 2.7.0 ya en uso en el proyecto) — confirmar límites de
tamaño/páginas por request y si conviene rasterizar a imágenes o si el
SDK admite PDF nativo directamente.

### 3.3. Persistencia en Drive

Generalizar `spare_parts/gdrive_service.py` una vez más (mismo patrón ya
usado dos veces — albaranes S014, fotos de tarea S016): nueva raíz
`MACHINE_DOCS_ROOT_FOLDER_NAME` ('EnterpriseBot - Documentación Centros
de Gasto'), localizada/creada bajo demanda con `ensure_root_folder()`,
subcarpeta por máquina (código de `MachineAsset`, ej. `A-45_E-6998-BDY/`)
en vez de por mes — la documentación de un centro de gasto no es
mensual, es del propio activo.

### 3.4. Vista de subida

Nueva vista en Administración (candidata: `panel/views_machine_documents.py`).
Selector de máquina + input de archivos múltiples (`<input type="file"
webkitdirectory multiple>` para selección de carpeta completa desde el
navegador, con fallback a selección múltiple de archivos sueltos).
Procesamiento en segundo plano (Celery, mismo patrón que
`upload_task_photo_to_drive`/`extract_delivery_note_data`) — la
clasificación + comparación maestro/individuales + subida a Drive no
debe bloquear la petición HTTP.

### 3.5. Listado "Documentación Centros de Gasto"

Nueva vista de solo listado, filtrable por máquina y por
`document_type`, con enlace directo a `drive_web_link` de cada
documento. Entrada de sidebar bajo Administración (gate de rol a
confirmar con Miguel Ángel — candidato natural: mismo gate que
"Centros de gasto", ADMIN/SUPERVISOR/WORKSHOPBOSS).

---

## 4. Preguntas Abiertas — Resolver al Empezar la Sesión que Retome Este Hito

Estas decisiones no quedaron cerradas en S016 y deben confirmarse con
Miguel Ángel antes de escribir el modelo definitivo (para no tener que
deshacer una migración ya aplicada):

1. **App Django destino** del nuevo modelo — `fleet` vs. app nueva
   dedicada (ver directriz arquitectónica de H22, sección 3.1 de ese
   anexo: "cada dominio funcional nuevo va en app propia").
2. **Lista de categorías (`document_type`)** — ¿cerrada de antemano
   (con las candidatas de la sección 3.1) o Gemini puede proponer
   categorías nuevas libremente?
3. **Rol(es) con acceso** a "Documentación Centros de Gasto" (listado
   y subida) — Administración sugiere ADMIN/SUPERVISOR/WORKSHOPBOSS,
   pero confirmar explícitamente, especialmente si WORKSHOP debería
   poder subir documentación desde el propio taller.
4. **Comparación de cobertura maestro vs. individuales** — ¿por número
   de páginas, por similitud de contenido vía Gemini, o ambos? Definir
   el criterio concreto antes de implementarlo, con al menos un caso de
   prueba real (la propia máquina A-45, cuyos 8 documentos individuales
   ya están persistidos manualmente en Drive desde S016 — pueden
   reutilizarse como fixture de validación).
5. **Verificación online de la API de Gemini** (directriz 4.4/SINE QUA
   NON) antes de escribir el servicio de clasificación — pendiente,
   no hecha en S016.

---

## 5. Hoja de Ruta para la Siguiente Sesión

### COMPLETADAS EN S017

Primera sesión de trabajo real sobre el hito (S016 solo lo creó, sin
código). Resumen narrativo completo en el mensaje del commit de
cierre de esta sesión — aquí solo el registro estructurado para
consulta rápida en sesiones futuras.

**Decisiones resueltas con Miguel Ángel (las 5 preguntas abiertas de
la sección 4):**
1. App nueva dedicada `machine_documents` (no se amplía `fleet`).
2. `document_type` libre — Gemini puede proponer categorías nuevas,
   sin lista cerrada.
3. Lectura: cualquier usuario autenticado (mismo gate `!= ASSISTANCE`
   que Historial de Máquina — pendiente de que Miguel Ángel confirme
   si quiere ampliarlo también a ASISTENCIA, preguntado dos veces en
   la sesión, sin respuesta explícita todavía). Subida: rol nuevo
   `DOCS_SUPERVISOR` + `ADMIN`.
4. Comparación de cobertura maestro/individuales: por similitud de
   contenido vía Gemini, nunca por número de páginas.
5. Verificación online de la API de Gemini Vision para PDF hecha
   (confirma procesamiento nativo hasta 1000 páginas/50MB, sin
   rasterizar).

**Construido:**
- Modelo `MachineDocument` (app `machine_documents`) con migraciones
  0001→0003: relación a `MachineAsset`/`Company`/`CompanyUser`,
  clasificación (`document_type`, `display_name`,
  `source_master_hint`, `original_filename`), metadatos extraídos
  (`expiry_date`, `issue_date`, `document_number`, `issuing_entity`
  — añadidos en la segunda mitad de la sesión), persistencia Drive
  (`drive_file_id`/`drive_web_link`), archivo local de staging
  (`source_file`, se borra tras éxito de subida a Drive, alineado con
  TaskPhoto/DeliveryNote), y estado de procesamiento (`status`
  PENDING/CLASSIFIED/ERROR + `error_message`).
- Rol `DOCS_SUPERVISOR` en `ivr_config.CompanyUser`.
- `machine_documents/document_classification_service.py`:
  `classify_document()` (clasificación + metadatos en una sola
  llamada Gemini), `assess_master_coverage()`, `extract_pages()`
  (PyMuPDF, sin dependencia nueva), `classify_by_filename_heuristic()`
  (manuales de uso, nunca tocan Gemini), reintento con espera
  bloqueante de 60s ante 429 de Vertex AI.
- `spare_parts/gdrive_service.py`: tercera raíz
  (`MACHINE_DOCUMENTS_ROOT_FOLDER_NAME`), subcarpeta por código de
  máquina, `upload_machine_document_file()`.
- Integración en el panel: **no** se creó un listado global cruzado
  (decisión de Miguel Ángel, con cientos de máquinas sería
  inmanejable) — la documentación vive dentro de la sección
  "#documentacion" de `history.MachineHistoryView` (mismo precedente
  que la galería de fotos de H7), con enlace desde cada fila de
  `fleet_list`. Vista de subida
  `machine_documents.views.MachineDocumentBatchUploadView`.
- `machine_documents/tasks.py`:
  `process_machine_document_batch`, tarea Celery que ejecuta todo el
  pipeline (clasificar → detectar/comparar maestro → extraer páginas
  no cubiertas → subir a Drive), idempotente por documento.

**Incidencias reales encontradas y resueltas:**
- **504 de PythonAnywhere** en la primera prueba end-to-end real (9
  documentos de la máquina A-45): un manual de uso incluido por error
  provocó un timeout de 60s en Gemini + reintentos que agotaron
  cuota (429), empujando la petición completa contra el límite duro
  de 5 minutos del webapp. El servidor sí terminó de persistir todo
  justo a tiempo (confirmado vía log de errores + consulta directa a
  BD) pero el navegador recibió un 504. Resuelto en dos fases: (1)
  heurística de nombre de archivo para excluir manuales de Gemini por
  completo, (2) a petición explícita de Miguel Ángel ("desde ya, sin
  deuda técnica"), migración completa del pipeline síncrono a
  asíncrono vía Celery/Always-on Task — el límite de 5 minutos deja
  de ser relevante sin importar el tamaño del lote.
- **Bug de traducción de categorías de avería** (fuera de este hito,
  detectado por Miguel Ángel en una captura de Historial de Máquina
  durante la prueba de esta sesión): `history/views.py` mantenía su
  propia copia hardcodeada de la taxonomía `FaultCategory`/
  `FaultSubcategory`, desactualizada desde antes de este hito.
  `analytics/views.py` tenía TRES copias más de la misma taxonomía
  (correctas, pero duplicadas). A petición explícita de Miguel Ángel
  ("no dejes deudas técnicas"), las cuatro copias se sustituyeron por
  un único punto de verdad construido desde `FaultCategory.choices`/
  `FaultSubcategory.choices` en ambos archivos.
- Error propio detectado y corregido en el mismo turno: un
  `str_replace` sobre `gdrive_service.py` dejó la firma
  `def upload_delivery_note_file(...)` huérfana (docstring suelto a
  nivel de módulo, sintácticamente válido pero con la función
  inexistente) — detectado por verificación AST explícita tras la
  edición, no solo `py_compile`, y reparado antes de continuar.

### Hoja de ruta — continuación de este hito

**Nota de reordenación (S022):** al plantear cómo continuar estos tres
puntos, Miguel Ángel identificó que la interfaz de Administración
completa (alertas, subida, borrado, sustitución, dossier PDF, plantilla
de email) no debe construirse por separado para cada dominio documental
(centros de gasto aquí, personal en H25) — eligió construir primero un
hito de infraestructura compartida, **H26 — Infraestructura Documental
Compartida** (ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md`), del que
los tres puntos de abajo pasan a depender. El criterio de vigencia
(punto 1) y el diseño de archivado (punto 2) siguen siendo los cerrados
en S021 (sin cambios) — lo que cambia es que su implementación en
interfaz vive ahora dentro de H26/su consumo desde aquí, no como pieza
aislada de este anexo.

1. **Prevalencia de documentos vigentes** — criterio cerrado en S021
   (ver más abajo), lógica de cálculo pendiente de implementar. Su
   comparación de fechas es la misma que usará el diálogo de
   sustitución de H26.
2. **Archivado y borrado de documentos obsoletos** — diseño cerrado en
   S021 (ver más abajo), campo/vista pendientes de implementar.
3. ~~**Alarmas vía WhatsApp** para documentos próximos a caducar~~ —
   **plantilla creada, corregida tras rechazo de Meta, y en revisión**
   (ver "COMPLETADAS EN S021"). Estado verificado en S022 vía API de
   Twilio: **`pending`**, Meta no la ha resuelto todavía. Falta la
   tarea que la dispare de verdad — construida dentro de H26 (motor de
   alertas, sección 2.1 de ese anexo), no aquí.

#### Decisiones cerradas en S021 (tal cual las dio Miguel Ángel, sin reinterpretar -- directriz 4.8)

1. **Criterio de vigencia:** "Todos los documentos serán vigentes
   cuando la fecha de caducidad no se haya alcanzado o fecha de
   emisión o el periodo de referencia sean más modernos." Es decir,
   un documento es vigente si `expiry_date` (cuando existe) todavía
   no ha pasado, O si su `issue_date`/periodo de referencia es más
   reciente que el de otro documento del mismo tipo para la misma
   máquina. **Pendiente de implementar** — el modelo de datos que lo
   soporta ya está construido (punto 4), falta la lógica en sí
   (método/manager que calcule `is_current`, o cómputo al vuelo en la
   vista).
2. **Archivado (no borrado directo):** "Se marca y en el visor de
   documentación se pone abajo en archivados y con la posibilidad de
   que se borre." Un documento superado por uno más vigente se marca
   como archivado (nuevo campo booleano, **pendiente de añadir al
   modelo** — no construido en S021) y se muestra en una sección
   "Archivados" al final del visor de documentación, con opción de
   borrado manual desde ahí. Los documentos vigentes solo se pueden
   ver, no se pueden borrar directamente — salvo la excepción del
   punto siguiente.
   **Precisión añadida por Miguel Ángel al cierre de S021, tal cual:**
   "Podríamos tener la posibilidad de poder borrarlos por si se suben
   documentos equivocados" — es decir, aunque la regla general es que
   los vigentes no se borran, sí debe existir una vía de borrado
   manual para el caso de subida errónea (a diseñar: ¿acción directa
   con confirmación, o siempre pasa primero por archivado?).
3. **Alarmas WhatsApp -- construida en S021, con una corrección real a
   mitad de sesión:** plantilla `document_expiry_alert` diseñada
   siguiendo el patrón de coletilla "trabajador de Grupo Alvarez" ya
   usado en las plantillas de H17, creada vía API de Twilio (Content
   API v1) y enviada a revisión de Meta. **Primer intento rechazado
   dos veces** (`HXc85c75b0d8ba412025ff09db4960cd35` y su duplicado
   `HX1b943a259babe8fe3e9f329bf7f7b25b`, motivo real de Meta:
   "Variables can't be at the start or end of the template" -- el
   cuerpo terminaba en "..., {{1}}."). Ambas borradas de Twilio vía
   API (`DELETE /v1/Content/{Sid}`, confirmado). Cuerpo corregido por
   Miguel Ángel (variable de saludo `{{1}}` movida al principio,
   cierre en texto plano) y **plantilla nueva enviada a revisión**:
   `content_sid = HX55da66276bb2025f691c378abff0123e`, `status =
   received`, categoría `UTILITY` — **pendiente de que Meta confirme
   la aprobación**, primer punto a verificar al abrir la sesión
   siguiente. Registrada en `whatsapp/management/commands/
   seed_whatsapp_templates.py` como `PENDING_APPROVAL`. **No
   construida todavía:** la tarea (Celery, probablemente periódica)
   que detecte documentos próximos a caducar y dispare el envío real
   -- la plantilla es el primer paso, no la funcionalidad completa.
4. **Modelo de datos dinámico por tipo de documento (construido en
   S021):** aclaración explícita de Miguel Ángel -- "Todas estas
   fechas deberían de tener sus campos en la base de datos... tenemos
   que ser dinámicos con esto, puesto que no sabemos qué documentos
   podemos llegar a encontrar... Cuando lleguemos al tema de personal,
   también tendremos muchos tipos de documentos, cursos, certificados,
   etcétera." Diseño híbrido acordado (Opción A JSON vs. Opción B EAV
   planteadas, Miguel Ángel confirma el híbrido): columnas propias con
   tipo real para los campos que se repiten entre varios tipos de
   documento (`period_start`/`period_end` -- periodo de cobro/
   cobertura, ej. pagos trimestrales de seguro, distinto de
   `issue_date`/`expiry_date`; `amount` -- importe en euros), más un
   campo `extra_data` (JSONField, sin lista cerrada de claves) para lo
   genuinamente impredecible por tipo de documento, pensado sobre todo
   para cuando se aborde documentación de personal. Migración
   `0004_machinedocument_period_amount_extra_data` escrita y
   desplegada en esta sesión (verificado `[X]` aplicada en producción).

### COMPLETADAS EN S022

**Prioridad 0 -- Migración Google Drive -> Google Cloud Storage,
completada y verificada de principio a fin.** Ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md` para el hito nuevo nacido de
esta misma sesión (infraestructura documental compartida) y el propio
`spare_parts/gcs_service.py` para el detalle técnico completo.
Resumen:

- Verificación online (directriz 4.4): `google-cloud-storage==3.13.0`,
  compatible con Python 3.10.5 del proyecto; confirmado que
  `*.googleapis.com` está en la whitelist de red de PythonAnywhere.
- 4 decisiones de diseño cerradas con Miguel Ángel: un bucket por tipo
  (`enterprisebot-alvarez-{task-photos,delivery-notes,
  machine-documents,personnel-documents}`), solo se migran a GCS los
  archivos con datos reales (albaranes -- la documentación de H23 era
  de prueba y se borró en vez de migrarse, ver más abajo), campos
  `drive_file_id`/`drive_web_link` mantenidos como legado + campo
  nuevo `gcs_blob_name`, buckets privados con acceso uniforme + URL
  firmada V4 generada bajo demanda (nunca acceso público, nunca
  persistida en BD).
- `spare_parts/gcs_service.py` nuevo, sucesor de `gdrive_service.py`
  para toda subida nueva de `TaskPhoto`/`DeliveryNote`/`MachineDocument`.
  Autenticación con la misma Service Account de Vertex AI -- el
  problema de cuota que forzó OAuth delegado en Drive no aplica a GCS.
- Migraciones `spare_parts.0010`, `work_order_processor.0031`,
  `machine_documents.0005` (campo `gcs_blob_name`), desplegadas y
  verificadas con datos reales (`showmigrations`, `manage.py check`)
  tras un incidente real de despliegue (ver más abajo).
- Las tres tareas Celery de subida migradas de `gdrive_service` a
  `gcs_service`. Vistas de `history`, `chat`, `delivery_notes`,
  `spare_parts` y el admin de `TaskPhoto` resuelven la URL de descarga
  en la vista (nunca en el template), con GCS preferente y Drive
  legado como fallback.
- **Incidente real de despliegue:** `pip-compile requirements.in`
  ejecutado sin `-o` reescribió `requirements.txt` directamente en el
  árbol de trabajo del servidor, dejando una modificación local sin
  commitear que bloqueó dos `git pull` consecutivos del Action (commits
  `6146d22` y `fefbcdb`, ambos en rojo en GitHub Actions -- confirmado
  con `git log -1`/`showmigrations` reales en el servidor, no solo con
  el semáforo). Corregido con `git checkout -- requirements.txt` +
  pull manual; las 3 migraciones se aplicaron correctamente. El push
  siguiente (`f42aa2b`) sí desplegó en verde.
- **Bug real detectado y corregido en la misma sesión:**
  `migrate_delivery_notes_to_gcs` anteponía el número de albarán al
  nombre de blob aunque el nombre ya guardado en Drive lo llevaba de
  antes, generando nombres duplicados/anidados cuando el número
  contenía `/` (ej. `BA/2606366`). Corregido con
  `gcs_service.sanitize_path_component()` + modo `--repair` del propio
  comando; los 10 albaranes ya migrados se repararon y se verificó
  abriendo la URL firmada de uno de ellos (foto real del albarán #12
  cargó correctamente).
- 10 albaranes reales migrados de Drive a GCS (`drive_file_id`/
  `drive_web_link` intactos, Miguel Ángel se encarga de borrar los
  originales de Drive él mismo).
- 11 documentos de prueba de H23 (máquina A45) borrados de BD y Drive
  vía `reset_machine_documents --machine-code A45 --confirm` (comando
  ya existente de S017), confirmado también visualmente por Miguel
  Ángel en Drive.
- Estado de la plantilla WhatsApp `document_expiry_alert`
  (`HX55da66276bb2025f691c378abff0123e`) verificado vía API de Twilio:
  **`pending`**, Meta no la ha resuelto todavía.
- **H25 -- Documentación de Personal** y **H26 -- Infraestructura
  Documental Compartida** creados como hitos nuevos PAUSADOS (Caso C),
  ver sus propios anexos para el detalle completo.

### COMPLETADAS EN S023

Sesión que arrancó con H23 EN PROGRESO. El trabajo real se dividió en
dos bloques: un incidente real detectado por Miguel Ángel al probar
(dentro del propio dominio de H23), y un desvío deliberado a H26 para
construir la infraestructura compartida que la hoja de ruta de S022
dejaba como bloqueante — el marcador `EN PROGRESO` **no se movió** en
ningún momento (Caso A de `ENTERPRISEBOT_ANNEX_ROUTER.md`: desvío de
sesión, no cambio de hito).

**Incidente real — Vertex AI roto para toda la plataforma tras la
migración a GCS de S022:**
- Miguel Ángel detectó al reintentar subir los 11 documentos de prueba
  de A-45 (los mismos borrados en S021) que solo 1 de 11 se procesó
  (el manual de uso, único que no llama a Gemini). Diagnóstico
  exclusivamente por logs reales (`alwayson-log-242133.log`,
  `bridge.log`), nunca por hipótesis — Miguel Ángel corrigió
  explícitamente al modelo cuando este empezó a especular sobre el
  proyecto GCP en vez de seguir el log.
- **Causa raíz confirmada:** al conceder el rol `Storage Admin` a la
  cuenta de servicio `enterprisebot-vertex@gen-lang-client-0961484137`
  para la migración GCS de S022, la consola de IAM **sustituyó** los
  roles existentes en vez de añadirlos — la cuenta se quedó sin ningún
  rol de Vertex AI. Afectó a `generateContent` (documentos) y a
  `BidiGenerateContent`/Live API (IVR) por igual, mismo permiso
  denegado (`aiplatform.endpoints.predict`) en ambos casos, confirmado
  en `alwayson-log-242133.log` y en `bridge.log` respectivamente.
- **Hallazgo adicional:** la llamada de prueba al IVR que Miguel Ángel
  hizo creyendo que "funcionaba" en realidad fallaba igual (confirmado
  por `bridge.log` — la sesión de voz moría con el mismo error nada
  más descolgar, el usuario solo oía la llamada conectar a nivel
  Twilio). Corregido tras el fix de IAM y reverificado con una llamada
  real posterior: audio bidireccional confirmado en el log.
- **Arreglo:** añadido el rol `Agent Platform User` (`roles/
  aiplatform.user` — nombre nuevo tras el rebranding de Vertex AI,
  verificado online) junto a `Storage Admin`, sin quitar este último.
- **Verificación con datos reales:** los 10 documentos de A-45 en
  `ERROR` se resetearon a `PENDING` (sin volver a subir archivos —
  `source_file` seguía en el servidor porque el fallo ocurría antes de
  llegar a Drive/GCS) y se reencolaron; los 10 quedaron `CLASSIFIED` y
  subidos a GCS, incluida la detección correcta del PDF maestro
  (`#34`, cobertura completa por los 9 individuales). Llamada IVR real
  posterior con audio `GEMINI-TX`/`GEMINI-RX` confirmado en `bridge.log`.
- Detectado de paso (fuera de alcance de H23, corregido igual):
  `CELERY_BEAT_SCHEDULE` seguía disparando a diario
  `chat.tasks.purge_old_chat_messages`, tarea eliminada por completo
  en H17 Paso 1 junto con `ChatRoom`/`ChatMessage`/
  `BreakdownConversationTurn` — ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`
  para el registro de esa corrección. El hueco horario (3:00) se
  reutilizó para la tarea de alertas de H26.

**Desvío a H26 — Infraestructura Documental Compartida completada:**
las cuatro capacidades del anexo V26 sección 2 construidas y
desplegadas (app `document_management` nueva, servicio de vigencia/
sustitución, fusión de PDF, motor de alertas) — ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md` sección "COMPLETADAS EN
S023" para el detalle técnico completo (commits, decisiones,
verificaciones). Relevante para H23: el modelo dinámico de metadatos
construido en S021 (`period_start`/`period_end`, `issue_date`,
`expiry_date`) es exactamente lo que consume el nuevo
`document_management.vigencia_service` — sin cambios necesarios en
`MachineDocument` para que H23 empiece a usarlo.

**Corrección explícita de rumbo por Miguel Ángel durante la sesión:**
al proponer que `EmailTemplate` (H26) fuera editable desde el admin de
Django, Miguel Ángel corrigió — él nunca mencionó "admin", pidió
"desde la misma aplicación"/"desde el panel", y solo él tiene acceso
al admin. Revertido antes de desplegar. Decisión final de Miguel Ángel
sobre esa misma pieza: no construir ninguna interfaz mínima desechable
para plantillas de email — se deja como modelo sin UI hasta que haga
falta de verdad, sin deuda técnica.

### Decisiones cerradas en S024 (tal cual las dio Miguel Ángel, sin reinterpretar -- directriz 4.8)

**Contexto:** al arrancar S024 con el punto de partida heredado de
S023 (construir la interfaz de panel de H23 sobre los servicios de
`document_management`), Miguel Ángel especificó el diseño completo de
esa interfaz antes de empezar a construir. Sustituye por completo
cualquier diseño de pantalla no cerrado que quedara pendiente de S023.

1. **Lo ya construido (subida por máquina individual) se mantiene
   intacto.** El flujo actual -- elegir una máquina, subirle su propia
   documentación, clasificarla -- no se toca ni se reemplaza.
2. **Nueva vía de entrada: subida de carpeta completa.** Se examina
   cada documento de la carpeta, se determina automáticamente a qué
   `MachineAsset` (o, para documentación de personal, a qué
   trabajador) pertenece cada uno, se clasifica y se persiste con sus
   metadatos en BD -- sin que el usuario indique la máquina/trabajador
   de antemano.
3. **Listado en pestañas:** "Maquinaria" y "Personal" como dos
   pestañas separadas del mismo listado.
4. **Vista de detalle en acordeón:** al entrar en una máquina o un
   trabajador, su documentación se organiza en acordeón -- vigente /
   archivada, y también por tipo de documento cuando proceda.
5. **Navegación listado → detalle también en acordeón, sin cambiar de
   vista.** El propio listado se despliega en acordeón y, al acceder a
   un elemento, su detalle se abre igualmente en acordeón dentro de la
   misma pantalla -- nunca una navegación que saque de la interfaz de
   listado.
6. **Filtros de búsqueda en vivo**, imprescindibles: localizar máquina
   o trabajador según se escribe, sin acción explícita de "buscar".

**Propuestas del modelo, admitidas explícitamente por Miguel Ángel sin
modificación -- incorporarlas tal cual:**

a. Reutilizar el mismo servicio de clasificación de fondo tanto para
   la vía de "subida de carpeta" (aquí) como para la futura ingesta de
   correo (H27) -- nunca duplicar el motor de clasificación entre
   vías de entrada (DRY).
b. Contenido del acordeón de detalle cargado vía HTMX de forma
   perezosa al desplegarse, no todo de golpe en el HTML inicial, si el
   volumen de máquinas/personal lo justifica.
c. Filtro en vivo vía HTMX con `hx-trigger="keyup changed
   delay:300ms"` sobre el listado, para no disparar una petición por
   cada tecla.
d. Estado intermedio "sin asignar" para documentos de la subida de
   carpeta donde Gemini no tenga confianza suficiente para decidir a
   qué máquina/trabajador pertenecen -- bloque propio en el listado en
   vez de forzar una asignación dudosa. Previsto en el diseño, no
   necesariamente implementado en el primer corte.

**Premisa explícita de implementación (aplica a H23 y a H27 por
igual):** máxima modularización. Archivos pequeños y con
responsabilidad única -- evitar archivos grandes que mezclen varias
responsabilidades, tanto en código como en documentación, para no
penalizar la escalabilidad futura.

### Corrección de rumbo — vista de documentación completamente aparte (S024, tal cual la dio Miguel Ángel -- directriz 4.8)

El modelo propuso mal en un turno de S024 mezclar el acceso de esta
interfaz nueva con el de Historial de Máquina/Centros de gasto
(visible a cualquier usuario no-ASISTENCIA). Miguel Ángel corrigió de
forma explícita y sin ambigüedad:

- **La interfaz nueva de "Documentación" es una vista COMPLETAMENTE
  APARTE**, sin ninguna relación con Historial de Máquina ni con
  Centros de gasto. Esa vista existente **no se toca, sigue exactamente
  igual**, con su acceso y su propósito actuales (ver intervenciones,
  ver qué mecánico ha tocado la máquina, etc.).
- **Acceso: única y exclusivamente ADMIN y DOCS_SUPERVISOR, en las DOS
  pestañas (Maquinaria y Personal), sin excepción.** Palabras de Miguel
  Ángel: "aquí no tiene que entrar nadie, nadie, a excepción de un
  administrador y doc supervisor. Nadie más, ni otros supervisores, ni
  operarios, ni jefes de taller, nada de nada." Queda descartada
  cualquier variante con acceso ampliado para la pestaña de Maquinaria.
- **Alcance funcional de esta vista, único y exclusivo (nada de
  historial de intervenciones/mecánicos):** subir documentación,
  descargar documentación, ver la documentación vigente, ver la
  documentación archivada/obsoleta, borrar documentación archivada,
  modificar documentación vigente.

### Hoja de Ruta para la Sesión Siguiente (S024) — COMPLETADA, ver COMPLETADAS EN S024 más abajo

**Punto de partida confirmado por Miguel Ángel al cierre de S023:**
construir la interfaz de panel de H23 que consuma los servicios de
`document_management` ya desplegados. No asumir el diseño de pantalla
— preguntar antes de construir (directriz 4.8), especialmente en:

1. **Vigencia visible + archivado** (criterio ya cerrado en S021,
   lógica ya implementada en `document_management.vigencia_service`
   S023): la vista de "Documentación de Centros de Gasto" debe marcar
   qué documentos son vigentes vs. archivados, con sección "Archivados"
   al final y opción de borrado manual — ver anexo H26 sección 2.4 y
   "Decisiones cerradas en S021" más arriba para el diseño exacto
   (incluida la excepción de borrado manual de vigentes por subida
   errónea).
2. **Diálogo de sustitución en la subida:** al subir un documento de un
   tipo ya existente para la misma máquina, llamar a
   `document_management.vigencia_service.evaluate_substitution()` y
   mostrar el diálogo con las dos acciones (archivar el obsoleto /
   revertir la subida) — flujo exacto en anexo H26 sección 2.4.
3. **Botón "generar dossier":** llamar a
   `document_management.pdf_merge_service.merge_pdfs()` con los
   documentos seleccionados por el usuario (acción bajo demanda,
   nunca automática).
4. **Formulario de alta de alerta:** crear un `DocumentAlert` desde la
   vista de un documento concreto — máquina y documento ya conocidos
   por contexto (rellenar `document_label`/`subject_label`
   automáticamente desde el `MachineDocument`, nunca a mano), el
   usuario solo indica `alert_offset_days` y `contacts` (confirmado
   con Miguel Ángel en S023, contacto por defecto = quien crea la
   alerta + desplegable/autocompletado para añadir otros, igual patrón
   que los códigos de máquina existentes).
5. **Verificar primero** el estado de la plantilla WhatsApp
   `document_expiry_alert` vía API de Twilio — Miguel Ángel indicó en
   S023 que la aprobación de Meta suele tardar ~24h desde el envío
   (S021), así que a la fecha de S024 debería estar resuelta. Si sigue
   `pending`, el motor de alertas ya construido funciona igual, solo
   no podrá enviar mensajes reales.

**Sin cambios, sigue pendiente independientemente de lo anterior:**
revisión del CRUD de documentación de centros de gasto más allá de lo
anterior — Miguel Ángel lo dejó abierto en S021 ("no sé si habrá que
mejorar el CRUD... está bien, pero habría que dotar las diferentes
funcionalidades") — confirmar alcance concreto con él, no asumir qué
falta.

**Observación sin acción inmediata (S023):** PythonAnywhere limita las
versiones de Python disponibles a 3.10 (y anteriores) a fecha de esta
sesión; `google-api-core` dejará de dar soporte a Python 3.10 el
2026-10-04. Sin acción posible por nuestra parte (depende de que
PythonAnywhere añada una versión superior) — vigilar antes de esa
fecha si no ha cambiado, para planificar la migración con margen.

### COMPLETADAS EN S024 (2026-07-17)

Sesión larguísima, un único hito EN PROGRESO (H23) durante toda la
sesión, sin desvíos ni PCH. 26 commits reales, 61 archivos tocados,
+7795/-560 líneas. Resumen narrativo completo por bloques:

**1. Cierre del alcance de H23/H25 (commits `e14e517`…`2c47244`).**
Abierto H25 (app `personal_documents` + modelo `PersonalDocument`,
espejo de `MachineDocument`) y H27 (ingesta por correo, PAUSADO, sin
código). Refactor `ai_services` para extraer los helpers de Gemini
Vision agnósticos de dominio (antes solo en `machine_documents`) más
un limitador de cuota proactivo (`gemini_rate_limiter.py`, token
bucket, `GEMINI_VISION_MAX_RPM`). Construida desde cero la app
`document_ingestion`: `entity_matching_service.py` (enrutado
máquina-vs-trabajador), `deduplication_service.py` (hash SHA-256),
modelo `IngestedFile` de staging, tarea `route_ingested_files`. Nueva
vista exclusiva "Documentación" (acceso único ADMIN + DOCS_SUPERVISOR,
confirmado explícitamente por Miguel Ángel sin excepciones), con
pestañas Maquinaria/Personal, subida de carpeta con detección
automática (sin elegir máquina/trabajador de antemano), deduplicación
por hash antes de gastar ninguna llamada a Gemini, alertas automáticas
de caducidad (30/15/7 días, corregido de una sola a tres tras aviso de
Miguel Ángel), CRUD completo de alertas por documento, y cierre del
resto del alcance pendiente: vincular a mano documentos "sin asignar",
borrar documentación archivada, modificar documento vigente.

**2. Corrección real del enrutado (commit `28de508`).** Miguel Ángel
mostró una captura real: archivos con el código/matrícula de la
máquina literalmente en el nombre (`A-45 E-6998-BDY Manual.pdf`)
caían en "sin asignar". Causa doble: (a) el prompt de enrutado
prohibía a Gemini mirar el nombre de archivo, calco erróneo de un
principio de H23 que no aplicaba aquí; (b) el emparejamiento contra la
BD era exacto carácter a carácter, sin normalizar guiones/espacios.
Corregido: el prompt ahora mira nombre de archivo Y contenido, y el
emparejamiento normaliza (quita todo lo que no sea letra/dígito) antes
de comparar.

**3. Panel de alertas completo + CRUD de plantillas de email +
generación de dossier (commits `2c47244`, `e2ec236`).** A petición
explícita de Miguel Ángel tras corregir que "10 puntos hechos" no era
lo mismo que "el hito completo": pestaña "Alertas" con TODAS las
alertas de la empresa (fecha de disparo calculada, vencidas-sin-enviar
resaltadas, resolución manual), pestaña "Plantillas de email" (CRUD
completo, resuelve un "pendiente de confirmar ubicación" anotado desde
S023), y generación de dossier PDF (nunca persistido, temporal en GCS
hasta confirmar, automático-sin-manuales para máquina vía
`MANUAL_DOCUMENT_TYPE`, con casillas para personal) — rediseñado varias
veces a lo largo de la sesión según las especificaciones exactas que
fue dando Miguel Ángel. Añadido también reenrutado a demanda
(`retry_unassigned_routing`) para documentos que se quedaron "sin
asignar" con lógica de enrutado antigua.

**4. Conversión completa a HTMX, sin recargas de página (commit
`3d9ae4e`).** Auditoría de las 16 apariciones de `redirect` a la
página completa en `views_documentation.py` — varias no eran solo
"recarga molesta" sino un bug real (formularios con `hx-post`
apuntando a contenedores pequeños que, al redirigir a la página
completa, metían TODO el HTML dentro de esa tarjeta). Corregidas
todas: vistas de fragmento nuevas para "sin asignar"
(`UnassignedMachineFragmentView`/`...PersonalFragmentView`), redirects
de borrar/editar documento al fragmento de detalle de la entidad, y el
dossier convertido de página aparte a modal cargado por HTMX.

**5. `reset_documentation` — zona cero completa (commit `d88e52d`).**
Comando de gestión nuevo (BD + GCS, los dos dominios + staging +
alertas, `--dry-run`/`--confirm`/`--company`), usado repetidamente a
lo largo de la sesión para poder repetir pruebas reales desde limpio.
De paso, eliminado `reset_machine_documents.py` (comando anterior,
alcance a una sola máquina) — llevaba meses obsoleto, seguía llamando
a Google Drive sin que nadie lo hubiera actualizado tras la migración
completa a GCS en S022.

**6. El documento maestro se persistía pese a procesarse con éxito
(commits `b44dd39`, `153f1f2`, y refinado en `18deb8a`).** Bug real
confirmado con datos reales del reset de zona cero (filas "Dossier de
Maquinaria" que nunca deberían existir). El maestro se clasificaba en
el Paso 1 igual que cualquier documento y nunca se excluía de
`classified` en los casos de éxito del Paso 2 — corregido con
`masters_to_discard` (borra fila + archivo local + alertas huérfanas).
Segunda salvaguarda añadida tras otro caso real: el juicio de Gemini
sobre qué páginas del maestro están "sin cubrir" puede equivocarse —
ahora se comprueba también contra documentos ya persistidos del mismo
tipo y fecha antes de crear el documento extraído.

**7. Visor de subida en vivo (commit `f93e966`, S024-ter, "interfaz
verbosa que comunique, sin tocar nada").** Nuevos campos en
`IngestedFile` (`upload_batch_id`, `routed_document_pk`,
`source_folder_path`, migración `0003`). La subida ya no devuelve un
mensaje — devuelve un visor que se sondea a sí mismo cada 3s mientras
quede algo pendiente, con spinner, estado por archivo (en cola,
clasificando, asignado a X, sin asignar, descartado por ser maestro,
error), carpeta de origen, y lista desplazable.

**8. Regresión del manual de uso + falso "Asignado" del maestro +
quitar el botón "Actualizar" (commit `18deb8a`, S024-cuater).** El
manual (pesado, provoca 504 de Gemini) volvió a fallar porque el
ENRUTADO nuevo (distinto de la clasificación) no tenía el mismo
heurístico de "nunca llamar a Gemini para esto" — corregido con
`route_document()`/`is_manual_by_filename()`/
`match_machine_asset_by_filename()`, un manual enruta siempre a
MACHINE sin pasar por Gemini. Campo nuevo `is_possible_master`
(migraciones `machine_documents` `0008` y `personal_documents` `0003`)
para que el visor sepa distinguir "clasificado de verdad" de
"clasificado pero el Paso 2 todavía puede descartarlo" — antes el
maestro aparecía como "Asignado" un instante antes de desaparecer.
Quitados los 4 botones "Actualizar": el sondeo del visor de subida
ahora empuja también, vía `hx-swap-oob`, el acordeón y los bloques
"sin asignar" — un único sondeo, cuatro contenedores.

**9. Fix del modal del dossier que se quedaba abierto (commit
`59fb650`).** "Descargar y borrar" no cerraba el modal (comportamiento
normal de un adjunto vía POST no-AJAX) — se cierra ahora en el propio
`onsubmit`.

**10. Bug de visualización del listado de usuarios (commit
`c6c62a2`).** Miguel Ángel reportó que `yolanda.bandera` aparecía como
"Operador" pese a haberla creado como Supervisor de Documentación —
**antes de tocar nada**, comprobación real en BD (rol, contraseña,
`must_change_password` correctos desde el principio) que confirmó que
el fallo era solo de visualización: el listado (`panel/users/list.html`)
tenía un `if/elif` que solo distinguía 4 de los 8 roles reales,
`WORKSHOPBOSS`/`ASSISTANCE`/`DOCS_SUPERVISOR` caían en el "Operador"
genérico. Corregido, con la lección explícita de Miguel Ángel de no
dar nada por hecho sin mirar antes los datos.

**11. Spinner + maestro "tragado entero" + borrar vigente con cuenta
atrás (commit `893a166`, S024-quinquies).** Botón de subida con
spinner nativo de HTMX visible desde el clic (lotes de 100+ archivos
no daban ninguna señal). Fix real: al repetir una subida donde los
individuales ya existían (deduplicados antes de llegar al enrutado),
el maestro se quedaba comparando contra una lista vacía y se
persistía entero — ahora también compara contra documentos YA
persistidos de la misma máquina/trabajador, descargados de GCS.
Añadido botón de eliminar también en documentos vigentes (antes solo
archivados), con modal de confirmación y cuenta atrás de 5 segundos
antes de activar el botón "Eliminar" — salvaguarda trasladada del
backend al frontend, a petición explícita de Miguel Ángel.

**12. Subida de carpetas grandes troceada automáticamente (commit
`48ad447`, S024-sexies).** Incidente real: la carpeta de la A36 (121
archivos, 112 PDF) nunca llegó a `DocumentationFolderUploadView` — sin
traceback, solo dos "OSError: write error" en el log web. Diagnosticado
con logs reales (Celery + web error) y confirmado con búsqueda del
foro oficial de PythonAnywhere: límite DURO de 100 MiB por petición
HTTP, sin excepción ni en cuentas de pago, no configurable, y al
superarlo no queda ningún rastro en la aplicación (coincide
exactamente con lo observado). El JS del navegador ahora trocea la
subida en tandas de hasta 70 MiB, enviadas secuencialmente con el
mismo `batch_id` compartido — el visor de subida en vivo no necesitó
ningún cambio, ya filtraba solo por `batch_id`.

**Incidencias reales encontradas y corregidas (no solo trabajo de
código nuevo):** doble subida casi simultánea no detectada por la
deduplicación (corregido comparando también contra `IngestedFile`
pendientes, no solo documentos ya persistidos); mensaje de subida que
seguía pidiendo "recarga esta página" pese a que el mecanismo ya no lo
hacía; botón "Subir documentación" sobrante dentro de cada
máquina/trabajador (remanente sin función, señalado por Miguel Ángel y
eliminado); Miguel Ángel corrigió al modelo en dos ocasiones por dar
cosas por hechas sin comprobar datos primero (la creación del usuario,
y si el descarte del dossier fue automático o manual) — ambas
correcciones aceptadas explícitamente sin defensa, con el compromiso
de comprobar antes de afirmar.

### COMPLETADAS EN S025

Sesión larguísima, sin desvíos de hito (H23 EN PROGRESO durante toda
la sesión, aunque con un desvío puntual real a `spare_parts` H10 —
albaranes de proveedor — por petición explícita de Miguel Ángel, sin
PCH, el marcador nunca se movió). 27 commits, 37 archivos,
+2657/-458 líneas.

**Bloque 1 — Documentación (H23):** subida archivo por archivo con
modal de progreso real (`_TokenBucket` corregido para arrancar
vacío, bajado a 12 RPM). Sustitución silenciosa de documentos +
historial visible (nuevo modelo `DocumentSubstitutionLog`) —
revierte el diseño original de diálogo interactivo de H26 §2.4
(decisión explícita de Miguel Ángel: "no tiene sentido que salte...
se hace el cambio simplemente y no se avisa"). Plantilla WhatsApp
`document_expiry_alert` verificada **aprobada** vía API real de
Twilio. Panel de Alertas rediseñado (una fila por documento, columnas
30/15/7 días) tras un incidente real de worker Celery sin reiniciar
(patrón de `deploy.yml` ampliado varias veces a lo largo de la
sesión: `document_management/`, `spare_parts/services.py`,
`spare_parts/gcs_service.py`, `whatsapp/services.py`,
`whatsapp/models.py`, `enterprise_core/settings.py` — todos
encontrados como huecos reales, no hipotéticos). Descarte heurístico
del documento maestro/dossier por nombre+peso, sin ninguna llamada a
Gemini. Envío manual de alertas por WhatsApp + edición de contactos
— encontrado y corregido un 405 real (orden de patrones de URL,
genérico antes que literal) que llevaba desde S023/S024 rompiendo
editar/borrar/resolver/enviar-ahora sin que nadie lo hubiera
detectado. Filtro de búsqueda por máquina/centro de gasto en el panel
de Alertas. Barra de progreso real del lote de subida (contador X/Y +
porcentaje), sustituyendo el spinner suelto anterior.

**Restructuración de navegación (H23, decisión explícita de Miguel
Ángel):** el listado de Maquinaria dejó de desplegar un accordion
in-situ (sin URL propia, un F5 perdía el filtro) — ahora cada máquina
enlaza a una **ficha de página completa propia**
(`MachinePageView`, URL `/documentacion/maquinaria/<pk>/ficha/`),
con su documentación, sus alertas ya acotadas a esa máquina
(reutilizando `_alerts_dashboard_context()` con `search` precargado,
sin duplicar lógica), dossier y conversión a Markdown. La vista
general de Documentación se queda como listado + Alertas cruzadas
filtrables (conviven las dos vistas, cada una con su propósito).
`DocumentationMachineDetailFragmentView` (el fragmento HTMX antiguo)
se conserva sin borrar, ya no enlazado desde ningún sitio — deuda
técnica menor anotada.

**Conversión de manuales a Markdown (H23, petición explícita de
Miguel Ángel: "los manuales son muy pesados"):** verificado en línea
(directriz 4.4) antes de elegir librería — `pymupdf4llm`, extensión
oficial de PyMuPDF, sin GPU/API externa, instalada y confirmada en
producción. Botón "Convertir a Markdown"/"Descargar Markdown" en la
ficha de máquina, solo para manuales; persistencia en el mismo bucket
GCS que el PDF original.

**Desvío a `spare_parts` H10 (albaranes de proveedor), sin PCH:**
petición explícita de Miguel Ángel tras varios albaranes reales
rechazados (foto ilegible, código a mano, código sin delimitar en
línea). Foto original invisible en albaranes `PROCESSED` nunca
confirmados corregida (fallback a archivo local, la subida a GCS solo
ocurría al confirmar). Asignación **manual** de máquina/centro de
gasto cuando la extracción automática falla — revierte parcialmente
la norma de S015 ("no se admite corrección manual"), pero queda
siempre marcada como tal (`manually_assigned`/`manually_assigned_by`/
`manually_assigned_at`, migración `0011`). Prompt de extracción
ampliado: reconoce campos impresos estructurados ("Matrícula: X")
además de Observaciones/línea delimitada, y transcribe anotaciones
**a mano** como pista para el operario (nunca automática) — commit
sin migración, campo ya vivía en `extraction_raw` (JSON).

**Bug crítico real encontrado y corregido — pérdida de contenido en
`assess_master_coverage()`:** ante un error de Gemini (aquí, límite
de tokens superado por acumular muchos individuales ya persistidos
de la A-45), el sistema interpretaba el fallo como "cobertura
confirmada" y descartaba el documento maestro **sin haberlo
comparado de verdad**. Corregido con un campo `comparison_failed`
explícito en el dict de retorno, comprobado ANTES de mirar
`uncovered_pages` en los dos llamadores (`machine_documents.tasks` y
`personal_documents.tasks`) — a partir del despliegue (11:37 UTC), el
maestro se conserva como documento real ante cualquier error de
comparación, nunca se descarta sin comparar.

**⚠️ INCIDENTE REAL — 13 documentos maestros perdidos ANTES del fix
de arriba**, todos de la A-45 (E-6998-BDY), confirmado buscando en el
log completo del worker (no solo fragmentos): pks 110, 155, 164, 170,
173, 176, 177, 178, 179, 180, 181, 182, 183 — archivos "FICHA
TECNICA+ITV" de varios años, pólizas Allianz, y algún PDF
desbloqueado/comprimido. Se borraron de verdad (nunca se subieron a
GCS, archivo local eliminado) — no recuperables desde el sistema.
Miguel Ángel informado con la lista completa de nombres de archivo
antes de cerrar sesión, para que compruebe si Yolanda conserva copia
fuera del sistema y pueda volver a subirlos (ahora sí se procesarán
bien).

**⚠️ INCIDENTE REAL — worker Celery caído en medio de un lote de 95
documentos**, sin ningún error en el log (10+ minutos de silencio
total). Diagnóstico con datos reales en cada paso (nunca supuesto):
`ps aux` resultó no fiable en este entorno (la always-on task corre
en un contenedor propio, invisible desde la consola SSH); la señal
real fue el silencio del log + el banner `(recovery)` de Celery al
reiniciar (confirmación propia de Celery de una caída no limpia);
consulta real a BD identificó exactamente 4 documentos huérfanos
(#207-210, `PENDING` sin ninguna tarea encolada) — reencolados a
mano tras confirmar que seguían `PENDING` justo antes de tocarlos.
**Causa raíz identificada y corregida**: `enterprise_core/celery.py`
no configuraba `task_acks_late` ni `worker_prefetch_multiplier` —
con los valores por defecto de Celery (concurrency=1 x
prefetch_multiplier=4 por defecto) el worker reservaba hasta 4 tareas
en su buffer local ANTES de ejecutarlas, marcándolas como entregadas
ante Redis en ese mismo instante — encaja exactamente con los 4
documentos perdidos. Verificado en línea (directriz 4.4) contra la
documentación oficial de Celery 5.6.3 (misma versión instalada);
corregido con `CELERY_TASK_ACKS_LATE=True` +
`CELERY_WORKER_PREFETCH_MULTIPLIER=1` +
`CELERY_TASK_REJECT_ON_WORKER_LOST=True`, verificado cargado en el
proceso real tras el reinicio. Se descartó explícitamente la cuota de
CPU de PythonAnywhere como causa de que el auto-reinicio no saltara
solo (7% usado, captura de pantalla real de Miguel Ángel) — causa
exacta de ese punto concreto sin determinar, anotada para vigilar si
se repite.

**Errores propios corregidos en la misma sesión, reconocidos sin
excusas:** nombre de variable de entorno inventado sin comprobar
(`WHATSAPP_SENDER_NUMBER` en vez del real `TWILIO_WHATSAPP_SENDER`) —
corregido tras que Miguel Ángel señalara la contradicción real
("otras plantillas se están enviando... sin ningún error"). Mismo
patrón repetido: `content_variables` de Twilio sin `json.dumps()` en
dos sitios (`document_management/alert_service.py` y, encontrado en
la auditoría completa pedida por Miguel Ángel tras el primer fallo,
`whatsapp/services.py send_capture_notification()`) — verificado
contra la documentación oficial de Twilio (error 21656) antes de
corregir, tal como exige la directriz 4.4.

### Decisiones cerradas en S026 (tal cual las dio Miguel Ángel, sin
reinterpretar -- directriz 4.8)

**Corrección sobre la hoja de ruta heredada de S025:** Miguel Ángel
indicó explícitamente que **no** hace falta recuperar los 13
documentos maestros perdidos (punto 1 de la hoja de ruta anterior,
ver más abajo) -- al analizar sus nombres reales, ninguno de los 13
debería haberse subido nunca. Prioridad real de la sesión: construir
un filtro de descarte por nombre de archivo que se ejecute ANTES de
la subida.

**Flujo, palabras textuales de Miguel Ángel:** "Leer nombre de
archivo -> heurística -> lista de descarte -> conformidad -> subir
únicamente los que pasen el primer filtro. Cuando se descartan se
presenta la lista de descartados para subir, para que el supervisor
confirme."

**Regla de agrupación por obsolescencia, palabras textuales:** "Yo
crearía un diccionario... con una palabra que se repita y añades
todo... forma grupos, conjuntos. Conjunto de archivos con palabras
clave que se repite [ITV, OCA, seguro, Allianz, etcétera]. Lo agrupa
y se coge el más moderno, porque los otros son obsoletos. Y ya
subimos única y exclusivamente lo más moderno." Confirmado
explícitamente que el código de máquina y la matrícula se excluyen
siempre del análisis ("eso no lo vas a poner... tú tienes que meter
en lo que es ya el nombre que diferencia el documento"). Confirmado
también: "podemos comparar contra lo que ya hay [BD]... el candidato
será el más moderno del lote, evidentemente, es una pérdida de
tiempo comparar los más antiguos del lote [entre sí]" -- y los
archivos cuya fecha no se identifique bien "hay que subirlos" (nunca
se descartan por no tener fecha reconocible).

**Datos reales usados para diseñar la heurística** (nunca
hipotetizados -- empirismo, ver log real del worker Celery,
`grep` dirigido sobre `/var/log/alwayson-log-242133.log`): los 13
nombres de archivo reales de los documentos perdidos en S025, todos
de la A-45 (E-6998-BDY):

`_compressed (7).pdf`, `FICHA TECNICA+ ITV 03-7-2024.pdf`,
`POLIZA ALLIANZ+REC 1-1-2023.pdf`,
`REC SEG ALLIANZ 01-01-2026_unlocked.pdf`, `_unlocked.pdf`,
`FICHA TECNICA+ ITV 24-4-19.pdf`, `FICHA TECNICA+ ITV 24-4-2020.pdf`,
`FICHA TECNICA+ ITV 24-4-2021.pdf`, `FICHA TECNICA+ ITV 24-4-2022.pdf`,
`FICHA TECNICA+ ITV 24-4-2023.pdf`, `FICHA TECNICA+ ITV 28-4-18.pdf`,
`FICHA TECNICA+ ITV 5-5-17.pdf`, `FICHA TECNICA+ITV 24-4-2020.pdf`
(prefijo común `A-45 E-6998-BDY` omitido).

**Corrección sobre UNLOCKED, misma sesión (S026):** Miguel Ángel
señaló que, a diferencia de COMPRIMIDO/COMPRESSED (que sí reconoce
sin ambigüedad como señal de dossier completo), no encuentra ninguna
relación entre "UNLOCKED" y "dossier" -- palabras textuales: "no le
encuentro relación con el dossier... para mí unlocked es algo que se
ha abierto, que ya no tiene llave". Preguntó si quedaba copia del
archivo real en el servidor para comprobarlo -- confirmado que NO:
un maestro descartado borra su archivo local y "nunca llegó a
subirse a GCS" (ver `machine_documents.tasks.process_machine_document_batch`),
así que no hay ningún sitio con una copia recuperable. Con el nombre
real delante (`REC SEG ALLIANZ 01-01-2026_unlocked.pdf`), Miguel Ángel
concluyó: "ya el nombre nos está diciendo lo que es. Es el recibo del
seguro de Allianz... y es de 2026. Ese no se puede descartar" --
confirmando que el criterio correcto es el de tres factores (máquina +
tipo + fecha), no palabras sueltas como UNLOCKED. **UNLOCKED se retira
de la REGLA A estructural** -- solo quedan `+` y COMPRIMIDO/COMPRESSED
como señales de descarte incondicional.

**Formato de fecha en el nombre, palabras textuales:** "siempre el
formato va a ser español, día, mes y año, pero no sabemos el formato
que va a tener, si va a venir el día con dos dígitos, con uno, si el
año va a tener dos dígitos, cuatro, si van a estar separados por un
guion, por un guion bajo... no lo vamos a saber" -- `parse_date_from_filename()`
reescrito para ser agnóstico de separador (`-`, `_`, `.`, `/`,
espacio, en cualquier combinación) y de ancho de dígitos, siempre en
orden día-mes-año.

**Máquina como condición previa de la REGLA B:** "principal, encontrar
el código de la máquina... encontrar la matrícula si viene. Si no
viene, no. Pero si viene, hay que encontrarla" (ya cubierto por
`match_machine_asset_by_filename`, que busca código O matrícula). Sin
máquina identificada en BD, la REGLA B nunca se aplica -- ni siquiera
la comparación dentro del propio lote.

**Implementación (S026), decisiones técnicas no explícitas de Miguel
Ángel, declaradas como suposición y no bloqueantes** (regla de
preferencia de sesión: se decide de forma autónoma cuando no bloquea
el avance):
- Comparación contra lo ya persistido usa los campos reales ya
  extraídos por Gemini (`issue_date`/`period_end`/`period_start`/
  `expiry_date` de `MachineDocument`), no un re-parseo del nombre de
  los ya persistidos -- más fiable.
- Identificación de máquina en el preflight reutiliza
  `document_ingestion.entity_matching_service.match_machine_asset_by_filename()`
  (ya existente), sin llamar a Gemini.
- El filtro se engancha en el hub genérico
  (`panel/documentation/hub.html` + `DocumentationFolderUploadView`),
  punto de entrada real de producción (confirmado por el log de esta
  sesión) -- la vista manual antigua (`MachineDocumentBatchUploadView`,
  H23 original) no se toca, sigue sin usarse en producción.
- El modal de conformidad solo aparece si hay algo que descartar; si
  el preflight no encuentra nada, la subida sigue directa.
- Si el servidor del preflight falla o no responde, el JS sube todo
  sin filtrar (nunca se bloquea una subida real por un fallo de este
  filtro opcional).

### COMPLETADAS EN S026 -- reconstrucción completa del pipeline de ingesta de maquinaria (5 fases, todas cerradas)

Tras registrar el punto 1 (parcial, arriba), Miguel Ángel pidió parar
y rediseñar el flujo completo con calma ("te has liado a hacer cosas,
quizás deberíamos haber hablado un poco más... creo que debemos
dedicarle más tiempo a esto"). El resto de la sesión se dedicó
íntegramente a la reconstrucción del pipeline de ingesta de
documentación de maquinaria, en 5 fases, cada una comiteada y
verificada por separado antes de pasar a la siguiente:

1. **Modelo de aprendizaje** (`d95a6d2`→`fff4f93` para el modelo real)
   -- `document_ingestion.LearnedDocumentTypeKeyword`, migración
   escrita a mano y verificada empíricamente (`makemigrations --check`
   contra sqlite: cero diferencias).
2. **Motor de tipo por máquina+tipo+fecha** (`382ed73`) --
   diccionario dinámico (estático + `budgets.Insurer` real de BD +
   aprendizaje), coincidencia por la keyword más larga,
   `learn_from_classification()`. Gap cerrado de paso:
   INSTRUCTIONS/INSTRUCCIONES añadidas a la heurística de manual.
3. **Gemini como extractor** (`ae73966`) -- cuando la heurística ya
   tiene el tipo claro, Gemini se sigue llamando (única vía de
   extracción de fechas/número/entidad) pero su `document_type` se
   sustituye por la etiqueta de la heurística; cuando no lo reconoce,
   se aprende de lo que Gemini clasificó.
4. **Pantalla de revisión con dos listas** (`d719481`) -- Descartados
   / Se van a subir, casillas por archivo, marcar/desmarcar todos por
   lista, un único botón "Subir seleccionados". Se muestra siempre
   tras el preflight, no solo cuando hay algo que descartar. De paso,
   aclarado el aviso de "carpeta añadida, todavía no se ha subido
   nada" (confusión real de Miguel Ángel con el botón "Subir" del
   selector nativo del navegador, ajeno a la aplicación).
5. **CRUD del diccionario aprendido** (`e59e6a2`) -- pestaña nueva en
   el hub, listado/edición/alta manual/borrado. Bug real encontrado y
   corregido por la propia prueba de extremo a extremo antes de
   comitear: una ruta genérica ya existente
   (`documentacion/<domain>/<pk>/borrar/`) interceptaba la ruta nueva
   por orden de coincidencia en `panel/urls.py` -- corregido
   reordenando, verificado con Django test Client real que las cuatro
   operaciones (crear/editar/listar/borrar) funcionan y que la ruta
   genérica sigue intacta para los dominios reales.

Decisiones de negocio cerradas con Miguel Ángel a lo largo de las 5
fases (verbatim, íntegro):

- **Corrección sobre la primera regla de descarte:** "el signo más
  combinando dos tipos" se mantiene como señal de descarte
  incondicional ("casi con toda seguridad esos mismos documentos van
  a estar por separado"); COMPRIMIDO/COMPRESSED también, pero
  **excluyendo siempre manuales/instrucciones** ("si lleva la
  palabra... manual de instrucciones... no es para eliminarlo").
- **Criterio de tres factores:** "encontrar el código de la máquina...
  encontrar la matrícula si viene... determinamos la máquina, el tipo
  de documento y la fecha a la que hace referencia el documento,
  podemos discriminar perfectamente los archivos a subir o no."
- **Comparación por nombre insegura a largo plazo:** el nombre de
  archivo puede cambiar de formato/aseguradora de un año a otro (ej.
  Allianz → AXA) -- resuelto comparando siempre contra el
  `document_type`/fecha ya persistidos en BD (dato estructurado, no
  el nombre de archivo antiguo), y contra un diccionario que crece
  (aseguradoras reales de BD + aprendizaje), no contra texto fijo.
- **Tipos sin fecha de caducidad:** "se hacen una vez y sirven para
  toda la vida útil de la máquina... esos habrá que subirlos
  inequívocamente" -- inferido directamente de la ausencia de fecha
  en el nombre, sin necesitar un diccionario tipo→caduca aparte.
- **Aprendizaje automático:** "el propio sistema propone
  automáticamente nuevas entradas de diccionario... se usa en la
  propia sesión de subida... por empresa... hay que construirlo ya."
- **Gemini dejó de decidir el tipo cuando la heurística ya lo sabe**
  ("directamente lo tenemos ya clasificado por el nombre"), pero
  sigue siendo la única vía de extracción de datos del contenido --
  matiz importante frente a la decisión de S016 (Gemini propone
  categorías libres): esa libertad se conserva íntegra para los casos
  que la heurística NO reconoce, que es donde alimenta el
  aprendizaje.

Hallazgo aparte, señalado a Miguel Ángel pero sin corregir en esta
sesión (requiere su consola de PythonAnywhere, sin acceso de red desde
esta sesión GitHub-directa): `pymupdf4llm` está en `requirements.in`
desde S025 pero nunca se propagó a `requirements.txt` -- pendiente de
`pip-compile requirements.in` + `pip-sync requirements.txt`.

Personal (H25) queda como siguiente capítulo natural, reutilizando
toda esta infraestructura tal cual -- `document_ingestion` es
agnóstico de dominio a propósito desde el diseño de H26.

### CIERRE DE S026 -- prueba en limpio con otra máquina, fixes adicionales

Tras cerrar las 5 fases, Miguel Ángel pidió dejar H23 "a cero" para
repetir la subida con una máquina distinta de la A-45 y probar todo
el pipeline nuevo de extremo a extremo. Tres cosas más, en el mismo
cierre de sesión:

1. **Fix real de enrutado** (`f929ae0`) -- 3 documentos de la subida
   original de la A-45 quedaron `SIN ASIGNAR` porque el propio
   escáner les puso nombres genéricos (`doc06655820240605095138.pdf`,
   sin código de máquina). Miguel Ángel: "aunque en el nombre no
   tenga el código de la máquina, están en la carpeta de la
   máquina... los documentos que se están subiendo de esa carpeta
   pertenecen a esa máquina". `document_ingestion.tasks.route_ingested_files`
   ahora hereda la máquina de los hermanos de la MISMA carpeta del
   mismo lote, solo si todos los hermanos ya emparejados coinciden en
   una única máquina.

2. **Timeout de despliegue** (`6780d21`) -- `--max-time 60` añadido a
   las tres llamadas curl del workflow contra la API de
   PythonAnywhere (reload webapp, reinicio bridge/worker). Miguel
   Ángel: "hay mucho tráfico en PythonAnywhere y suele dar error por
   eso... el error es única y exclusivamente por el tema del
   timeout". Confirmado en vivo: dos despliegues de esta misma sesión
   fallaron en el paso de reload pese al fix (tráfico real alto ese
   día), resueltos reintentando el job vía API sin necesitar un
   commit nuevo.

3. **⚠ Incidente real -- comando de reset duplicado con bug, corregido
   en la misma sesión (`3622420`):** para dejar la zona a cero, se
   escribió `machine_documents/management/commands/reset_machine_documents.py`
   SIN comprobar antes si ya existía una herramienta equivalente. Ya
   existía `document_ingestion/management/commands/reset_documentation.py`
   -- creado explícitamente para SUSTITUIR a un comando con ese mismo
   nombre y propósito, borrado en su día por quedar obsoleto tras la
   migración de Drive a GCS. El comando nuevo reintrodujo el mismo
   tipo de fallo: nunca borraba el blob real de GCS
   (`MACHINE_DOCUMENTS_BUCKET`), solo el archivo local de staging
   (`source_file`, vacío para documentos ya `CLASSIFIED`, cuyo
   contenido real vive en `gcs_blob_name`). Se ejecutó con `--confirm`
   antes de detectar el fallo: 84 `MachineDocument` borrados
   correctamente de BD, pero 74 blobs de GCS quedaron huérfanos.
   Corregido: comando duplicado eliminado,
   `document_ingestion/management/commands/purge_orphaned_gcs_blobs.py`
   nuevo (lista blobs sin referencia en BD, dry-run por defecto) para
   limpiar el estropicio -- verificado con dry-run (74 huérfanos en
   `MACHINE_DOCUMENTS_BUCKET`, 0 en personal) y confirmado tras el
   borrado real (74 borrados, coincide exacto). `reset_documentation.py`
   sigue siendo la herramienta correcta para "zona cero" completa --
   `python manage.py reset_documentation --confirm` (o `--company
   <slug>` para acotar).

Estado real al cierre: BD y GCS de documentación de maquinaria en
CERO para Grupo Álvarez -- listo para la prueba de subida con una
máquina distinta de la A-45.

### COMPLETADAS EN S026 (parcial, sesión en curso) -- registro original del punto 1

1. **`document_ingestion/preflight_discard_service.py`** (nuevo) --
   REGLA A (descarte estructural: `+` combinando dos tipos, o sufijo
   `COMPRIMIDO`/`COMPRESSED`, excluyendo siempre los manuales de uso;
   `UNLOCKED` retirado de esta lista en la misma sesión, ver
   corrección arriba) y REGLA B (criterio de tres factores -- máquina
   identificada en BD, tipo por diccionario de palabras clave
   excluyendo código/matrícula, y fecha de nombre agnóstica de
   separador/ancho de dígitos; sin los tres, se sube sin comparar).
   Se queda el más moderno del lote por fecha, comparado después
   contra lo ya persistido en BD. Probado manualmente en este
   workspace contra los 13 nombres reales de S025 (11 se descartan
   por REGLA A, los 2 "unlocked" ya NO se descartan -- uno por ser el
   recibo de seguro más reciente, otro por no tener tipo reconocible)
   y contra los individuales vigentes del mismo lote (ninguno se
   descarta) -- encontrado y corregido un falso positivo real en la
   propia prueba: el manual de uso ("...MANUAL DE USO-comprimido-2.pdf")
   se descartaba por contener "comprimido" en su propio nombre;
   corregido excluyendo siempre `is_manual_by_filename()` antes de
   aplicar la REGLA A.
2. **`panel/views_documentation.py`** -- nueva vista
   `DocumentationPreflightDiscardView` (solo lectura, JSON, agrupa
   los nombres recibidos por máquina detectada y llama al servicio).
3. **`panel/urls.py`** -- ruta `documentacion/subir/preflight/`.
4. **`panel/templates/panel/documentation/hub.html`** -- modal de
   conformidad de descarte nuevo (`discardConfirmModal`) + JS: el
   submit llama primero al preflight (solo nombres, nunca bytes),
   muestra la lista de descarte con motivo por archivo si hay algo,
   y solo sube lo que el supervisor confirme tras pulsar "Confirmar y
   subir el resto" (o cancela con "Cancelar subida"). Subida real
   extraída a función propia (`beginActualUpload`) para poder
   llamarse tanto directa como tras la conformidad.
5. **Aviso de linter no bloqueante reparado en la misma sesión**
   (directriz 4.9, ampliación S024): `djlint` marcó 5 estilos inline
   en `hub.html` al tocar el archivo -- 4 preexistentes (barras de
   progreso del modal de subida, S025) y 1 propio de esta sesión
   (lista de descarte). Los 5 extraídos a clases CSS nuevas en un
   bloque `{% block extra_head %}` (`upload-progress-thin/thick`,
   `progress-bar-start`, `discard-list-scroll`) -- el ancho dinámico
   de las barras lo sigue fijando el JS en tiempo de ejecución, sin
   cambios de comportamiento.

### CIERRE DE S026, PARTE 2 — sistema de incidencias, REGLA B-bis, hallazgo de datos de flota

Continuación de la misma sesión S026 (mismo día, chat renovado por
límite de contexto) tras la prueba real de subida completa de la
A-36. Miguel Ángel probó el sistema en persona (sin depender de
Yolanda) y fue encontrando, uno a uno, problemas reales con datos
reales -- todos corregidos en la misma sesión:

1. **Timeout de despliegue** (`6780d21`) -- `--max-time 60` en las
   tres llamadas curl de `deploy.yml` contra la API de PythonAnywhere.
   PythonAnywhere siguió teniendo días de tráfico alto que hacían
   fallar igualmente el paso de recarga varias veces a lo largo de la
   sesión (nunca el `git pull`) -- Miguel Ángel decidió, a mitad de
   sesión, que el modelo **deje de reintentar el Action** y avise
   directamente para que él recargue a mano desde el panel
   (aplicación web y/o worker según qué tocara el commit) -- "es un
   problema de infraestructura de PythonAnywhere con el que no
   podemos lidiar".

2. **Comando de reset duplicado con bug real, corregido en la misma
   sesión** (`3622420`) -- se escribió
   `machine_documents/management/commands/reset_machine_documents.py`
   sin comprobar antes si ya existía una herramienta equivalente. Ya
   existía `document_ingestion/management/commands/reset_documentation.py`
   (creado explícitamente para sustituir a un comando con ese mismo
   nombre, borrado en su día por quedar obsoleto tras la migración de
   Drive a GCS) -- el nuevo reintrodujo el mismo fallo: nunca borraba
   el blob real de GCS. Se ejecutó con `--confirm` antes de detectarlo
   (84 filas de BD borradas bien, 74 blobs de GCS quedaron huérfanos).
   Corregido: comando duplicado eliminado,
   `document_ingestion/management/commands/purge_orphaned_gcs_blobs.py`
   nuevo para limpiar el estropicio (dry-run por defecto, verificado:
   74 huérfanos detectados y borrados, coincide exacto).

3. **Restricción del Diccionario aprendido a superusuario** (`0bb5615`)
   -- Miguel Ángel, tras ver la pestaña nueva en producción: "esta
   vista debería ser visible única y exclusivamente para mi usuario".
   `SuperuserRequiredMixin` (ya existente, creado en S021 para
   sustituir el antipatrón de username hardcodeado) reutilizado en las
   tres vistas del CRUD, en vez de reintroducir ese antipatrón.

4. **La máquina se determina PRIMERO por nombre de archivo, no por
   contenido** (`8a99e60`, urgente, con subida real en curso) --
   `document_ingestion.tasks.route_ingested_files` seguía
   determinando la máquina por CONTENIDO (Gemini) exclusivamente; la
   decisión de "nombre de archivo manda" de las fases 2-3 solo se
   había aplicado a la determinación del TIPO, nunca al enrutado real.
   Corregido: `match_machine_asset_by_filename()` primero, Gemini
   como respaldo solo si el nombre no trae código reconocible.

5. **Barra lateral vacía en la ficha de máquina** (`fc61454`) --
   `MachinePageView` (S025) nunca pasaba `company_user`/`active_nav`
   al contexto -- sin esos dos valores, `_nav_items.html` no puede
   evaluar ninguno de sus condicionales por rol. Bug distinto del
   corregido en S021 (aquel fue en la vista antigua de subida).

6. **Salvaguarda de Gemini para discrepancias nombre/contenido**
   (`b6d8f57`) -- caso real: certificado CE de la A-45 archivado en
   la carpeta de la A-36, con el número de bastidor real de la A-45
   en el contenido. Miguel Ángel: "no deberíamos de dejarlo única y
   exclusivamente al nombre del archivo... si se sube y se asigna a
   esa máquina, marcarlo con incidencia". Campo nuevo
   `content_mismatch_warning` en `MachineDocument` + extracción de
   `machine_reference_in_content` en `classify_document()` (Gemini),
   comparado contra la máquina ya asignada -- nunca reasigna sola,
   solo avisa.

7. **La CARPETA manda sobre el nombre de archivo individual**
   (`b521699`, `df81f75`) -- Miguel Ángel, tras comprobar que el
   fix (4) había movido automáticamente un documento a otra máquina
   sin dejar rastro del error: "el movimiento no debe ser
   automático... para que salte la liebre de que el mismo error
   puede estar también en otros sistemas". Prioridad invertida:
   carpeta > nombre de archivo individual > contenido (Gemini). Bug
   real detectado y corregido en la misma verificación: `source_folder_path`
   (de `webkitRelativePath`) incluye el nombre de archivo como último
   segmento -- buscar la máquina sobre el string completo colaba el
   código mencionado en el propio nombre dentro de la búsqueda "por
   carpeta"; corregido quedándose solo con la parte de carpeta.
   También en este commit: reconocimiento de fechas `AAAA-AAAA`
   (cadena real de certificados OCA 2014→2018 subida entera por no
   reconocerse ese formato de fecha).

8. **Sistema completo de resolución manual de incidencias** (`97b5be4`,
   `d089df5`) -- campo FK `content_mismatch_candidate_machine` +
   columna de incidencias en el listado de máquinas + botón "Resolver
   con `<máquina>`" por cada máquina distinta implicada, visible solo
   si existe esa incidencia concreta + pantalla partida
   (`MachineDocumentTransferView`/`transfer.html`) para mover
   documentación entre dos máquinas a mano, siempre con clic explícito
   (`DocumentMoveToMachineView`) -- nunca automático. Caso "sin
   asignar" (sin máquina candidata resuelta) con selector libre de
   máquina por documento, en vez de un botón fijo.

9. **Rediseño completo del reconocimiento de tipo por nombre**
   (`5182081`, `e9e347a`, `6e3b855`) -- tras una tanda de capturas
   reales de Miguel Ángel mostrando decenas de archivos "tipo no
   reconocido" pese a tener un tipo claramente inferible:
   - Bug de fondo real: la normalización usada al APRENDER una
     palabra clave (separadores colapsados a espacio) era distinta de
     la usada al BUSCARLA en un archivo nuevo (separadores intactos)
     -- una keyword aprendida nunca podía volver a encontrarse a sí
     misma. Unificado en `_normalize_group_search_text()`, usada en
     los dos lados sin excepción.
   - "SCAN"/"IMG"/etc. (nombres de escáner genéricos) ya no se
     aprenden como palabra clave -- caso real: "SCAN" se había
     aprendido → grupo ITV a partir de un único error de Gemini, y
     contaminó todos los archivos futuros de ese escáner.
   - REGLA B-bis nueva: archivos de tipo DESCONOCIDO (ningún
     diccionario los reconoce) pero con fecha identificable se
     agrupan por "molde" (mismo nombre sin máquina/fecha/copia)
     dentro del propio lote -- sin necesitar saber el nombre del
     tipo (caso real: "GDR 2011...2026", "IPO ...", "ITC..." -- se
     queda solo con el más moderno de cada molde).
   - "COPIA"/"COPY" se ignora al construir el molde -- un archivo y
     su copia comparten molde y fecha, sobrevive el que NO es copia.
   - Año suelto (`SEGURO 2014.pdf`) y periodo compacto SIN separador
     interno unido por "AL" (`RECIBO 150311 AL 150611.pdf`) añadidos
     como nuevos formatos de fecha reconocidos.
   - Verificado con Django real, ciclo completo aprendizaje→BD→
     búsqueda futura, y con TODOS los ejemplos reales aportados por
     Miguel Ángel en sus capturas.

10. **Prueba real completa de la A-36 (42 documentos) -- resultado
    limpio**: 42/42 correctamente asignados a la A-36, cero fugas a
    la A-35, cero sin asignar. `Scan2025-10-28_175658.pdf` clasificado
    correctamente como "Libro de revisiones periódicas" (antes:
    "Tarjeta ITV", por el bug de "SCAN" ya corregido).

11. **Hallazgo real, sin corregir todavía**: los avisos de
    "discrepancia nombre/contenido" tienen falsos positivos
    sistemáticos cuando Gemini extrae un número de BASTIDOR/SERIE del
    contenido (ej. "VHX2FF1P204251036", el bastidor real y correcto
    de la propia A-36) -- `MachineAsset` no tiene ningún campo de
    bastidor con el que comparar, así que ese dato SIEMPRE sale como
    "incidencia" aunque sea correcto. Miguel Ángel: "hay que
    enriquecer el modelo con el campo de bastidor, por supuesto" --
    pendiente para la sesión siguiente.

12. **Hallazgo real, sin corregir todavía, no es un bug de código**:
    varias decenas de filas de `fleet.MachineAsset` (empresa Grupo
    Álvarez) tienen datos corruptos -- `code`/`plate`/`brand_model`
    con FECHAS en vez de código/matrícula reales (ej. `pk=375
    code='08/06/2020' plate='0'`, `pk=432 code='01/01/2000'`, `pk=418
    code='PEUGEOT 206' plate='16/06/2017'`). Esto explica avisos de
    discrepancia carpeta/nombre sin sentido aparente ("nombre dice
    A20", "nombre dice 08/06/2020") -- son coincidencias reales contra
    datos de flota mal importados, no invenciones del sistema. Miguel
    Ángel pidió el listado completo para revisar la matrícula real de
    esos vehículos -- **pendiente de entregar, sesión siguiente**
    (la petición llegó justo al cierre, sin tiempo de generarlo).

### COMPLETADAS EN S028 (2026-07-22)

H23 EN PROGRESO durante toda la sesión, con dos desvíos puntuales
breves (Caso A, marcador nunca movido): a H07 (investigación de un
bug real, ver anexo H07 fila `S_H07_13` para el detalle completo) y a
H10 (una petición nueva anotada para su propia hoja de ruta, sin
trabajo de código). Sesión larguísima: 22 commits, 18 archivos,
+2173/-298 líneas.

**Cierre retroactivo de S027** (commit `5cc30ae`, al empezar): sesión
anterior había quedado interrumpida por una caída de herramientas del
modelo -- verificado que los dos commits pendientes (`372faae`,
`6eb7bbb`) llegaron bien a producción, cerrado formalmente.

**Bastidor de `fleet.MachineAsset` y falsos positivos de discrepancia**
(primera tarea heredada de S026/S027, cerrada por completo):
- Descubierto que el campo `chassis_number` YA EXISTÍA en el modelo
  (la nota de S026 que decía lo contrario era incorrecta) -- el
  problema real era que la comparación de discrepancia
  (`machine_documents/tasks.py`) nunca lo tenía en cuenta, solo
  code/plate (commit `3f9b77c`). Añadido relleno progresivo: cuando el
  bastidor está vacío y un documento lo menciona, se rellena solo, sin
  backfill retroactivo -- decisión explícita de Miguel Ángel.
- **Hallazgo real más profundo, encontrado con datos reales de la
  A-36** (commits `dc0c3c2`, `67cddc6`, `2c59abf`): un documento con
  matrícula E-2052-BCW Y bastidor VHX2FF1P204251036 a la vez se
  marcaba como discrepancia porque (a) `match_machine_asset_by_filename`
  comparaba por subcadena libre sobre el nombre de archivo entero
  pegado sin separadores, y "A20" aparecía por pura coincidencia de
  caracteres dentro de "...POLIZA2024..." -- corregido a comparación
  por token completo; y (b) Gemini solo podía extraer UNA referencia
  por documento (`machine_reference_in_content`), así que si elegía el
  bastidor y este no coincidía con el `chassis_number` ya guardado (a
  su vez contaminado por un documento anterior con un dígito
  equivocado), se generaba una incidencia falsa aunque la matrícula,
  también presente, ya demostrara la máquina correcta sin duda.
  Solución de fondo: Gemini ahora extrae matrícula/bastidor/código de
  flota como TRES campos separados, que pueden rellenarse a la vez; si
  matrícula o código coinciden con la máquina asignada, la identidad
  queda confirmada y NUNCA se marca discrepancia, y un bastidor
  confirmado por matrícula puede CORREGIR uno no confirmado ya
  guardado (verificado con simulación del peor caso de orden de
  procesamiento posible). Bastidor real de la A-36 confirmado y
  corregido: `VHX2FF1P204251036` (el guardado antes,
  `...037`, era el erróneo).
- Auditoría completa de los 566 `MachineAsset` de la empresa: 58 filas
  borradas (código=fecha, código numérico duplicado de otra máquina
  real, o carpetas basura con 0 documentos enlazados, verificado
  contra las 10 relaciones inversas antes de borrar cada una) y 31
  máquinas reales con bastidor placeholder/autoduplicado vaciado a
  mano, a petición explícita de Miguel Ángel.

**Pantalla de transferencia de incidencias -- rediseño completo**
(commits `42e7e4f`, `01fa6ee`, `027c306`, `f6754b7`, `0f589f5`,
`b42e46a`, `e91e401`): visor de documento, filtro de columna acotado a
la máquina candidata real, botón "Correcto" (más tarde superado por el
mecanismo de puntero), modal de confirmación con cuenta atrás extraído
a parcial reutilizable (DRY, sustituye a la duplicación entre
`hub.html`/`machine_page.html`), mecanismo de puntero visual definitivo
(la tarjeta se mueve de verdad entre columnas del DOM, sin toggle
interno), y preservación del `back_url` de origen al volver.

**Candidatos a documento obsoleto -- funcionalidad completa nueva**
(commit `945fc27` en adelante, el bloque de trabajo más grande de la
sesión): a partir de un caso real (un recibo de seguro de 2015-2016
marcado como incidencia de máquina cuando en realidad solo era
papeleo obsoleto), Miguel Ángel: "que sea Gemini quien decida... solo
que la decisión final de eliminar sea de un humano". Gemini juzga por
el contenido (`is_obsolete_candidate`/`obsolete_reason`, nuevos campos
del mismo JSON de clasificación, sin llamada extra) si un documento ya
no tiene valor operativo; nunca se borra solo. Prioridad de resolución
explícita: mientras un documento sea candidato a obsoleto, se excluye
de la cola de incidencias de máquina (la obsolescencia se resuelve
primero). Sección nueva y separada en la ficha de máquina, con el
mismo patrón de borrado con cuenta atrás. Ampliada en el resto de la
sesión con selección múltiple + borrado en bloque (`297aa44`),
generalizada después a vigente/archivado también (`52251c1`,
restringida inicialmente a solo obsoletos, luego abierta a cualquier
documento del dominio -- misma barrera de seguridad, cuenta atrás +
selección explícita, que el borrado individual), comparación de dos
documentos vía Gemini (`compare_documents`, nueva llamada) para
detectar duplicados reales (`52251c1`, corregida en `f5fd389` para
marcar los DOS documentos comparados como candidatos, no elegir uno
automáticamente -- "prefiero... escoger... el que quiere quedarse", y
con modal de espera con spinner en `0c0cbeb` para que no pareciera que
la página se había bloqueado durante la llamada síncrona a Gemini), y
las dos acciones en bloque simétricas que faltaban (`3e417dc`):
descartar obsoletos en bloque y marcar como obsoleto en bloque desde
vigente/archivado, unificadas en una sola vista genérica
(`DocumentBulkObsoleteToggleView`).

**Vigencia forzada manualmente -- "recuperar del cajón de archivos"**
(commit `8f6f428`): `document_management.vigencia_service` es
deliberadamente genérico (solo fechas, sin conocimiento de dominio) y
no tenía ningún mecanismo de anulación manual -- confirmado antes de
construir nada. Nuevo campo `MachineDocument.force_current` (migración
`0013`): un documento marcado así se trata siempre como vigente, y
queda excluido de la comparación automática de "siblings" del mismo
tipo, para no influir en si otros documentos se consideran vigentes.
Botón "Recuperar como vigente" por fila archivada. Misma sesión,
pulido de UX: barra de acciones (Comparar/Eliminar
seleccionados/Marcar como obsoleto) duplicada encima de "Archivados"
(antes solo arriba del todo, "muy tedioso subir arriba") -- convertida
de IDs únicos a clases compartidas para que todas las copias se
sincronicen entre sí.

**Otro fix real encontrado y corregido en la misma sesión** (commit
`3fd7ccf`): los manuales de uso mostraban "Tipo no reconocido por
nombre -- se sube para que Gemini lo clasifique" en la pantalla de
preflight, pese a que la regla real (nunca llamar a Gemini para un
manual) seguía intacta -- el problema era solo el mensaje, que usaba
un diccionario de "grupo" completamente distinto sin conocimiento de
manuales; corregido con un caso especial en el mensaje, sin tocar la
lógica real de descarte (que sí lo tenía en cuenta correctamente para
evitar tratarlo como dossier).

**Desvío a H07** (investigación, sin código tocado -- ver anexo H07
fila `S_H07_13`): mientras esperaba el reinicio del worker, Miguel
Ángel reportó que el modo edición de partes digitales "no está
renderizando exactamente lo que la base de datos tiene". Confirmado
con lectura directa de `panel/views_operator.py`: es un riesgo real de
PÉRDIDA DE DATOS, no solo de visualización -- `show_lunch_break` en
edición se calcula del horario EN VIVO del operario, no de los datos
reales del `first_entry`, y al guardar puede sobrescribir con `None`
una pausa de comida real ya guardada. Registrado como primer punto de
la próxima sesión de H07, sin arreglar todavía por decisión explícita
de Miguel Ángel ("no es cosa de dos minutos... prefiero ir con cuidado
en vez de rápido").

**Prueba real con Yolanda (supervisora de documentación) al cierre**:
zona cero + subida completa, confirmación de que el bastidor de la
A-36 persiste correctamente (no se toca con zona cero, solo borra
documentos). Feedback muy positivo, con dos incidencias menores
reportadas para la sesión siguiente (ver hoja de ruta abajo).

### COMPLETADAS EN S029

**Sesión partida en dos chats por una caída de herramientas del lado
de Anthropic**, no del proyecto. El primer chat llegó a commitear y
pushear los dos primeros puntos de la hoja de ruta antes de caerse,
sin poder cerrar sesión formalmente ni registrar nada en este anexo.
El segundo chat ("Continuación") arrancó sin dar nada por hecho:
releyó este anexo (que todavía mostraba los tres puntos como
pendientes -- desfase de documentación, no de código) y verificó con
`git log`/`git diff --stat` contra el remoto que el trabajo descrito
por Miguel Ángel sí estaba realmente en `origin/main` antes de
continuar. Sin pérdida real de código: solo la bitácora de este anexo
quedó un paso por detrás del repositorio.

**Punto 1 -- condición de carrera del modal de cuenta atrás (commit
`a54d6dd`, primer chat):** el borrado se ejecutaba de verdad en el
servidor, pero el modal HTMX se quedaba abierto indefinidamente
porque nada llamaba a `hide()` en la vía HTMX -- solo se limpiaba el
intervalo en `hidden.bs.modal`, evento que nunca se disparaba.
Solución: listener `htmx:afterRequest` que cierra el modal
(`bootstrap.Modal.hide()`) cuando `evt.detail.successful` es `true`,
añadido/quitado en cada apertura porque el `<form>` es el mismo nodo
DOM reutilizado por todas las acciones del modal genérico.

**Punto 2 -- HTMX real en vez de recarga de página completa (commit
`201bb0b`, primer chat):** causa de fondo encontrada -- `DocumentDeleteView`
ya estaba enganchada a `hx-target=#machine-detail-container`, pero
seguía haciendo `redirect()` a `MachinePageView` (página completa);
HTMX sigue redirecciones de forma transparente, así que lo que se
metía en el contenedor era la página entera. Nuevo helper
`_machine_detail_htmx_response()` aplicado a las 5 vistas que mutan
documentación de máquina (`DocumentDeleteView`,
`DocumentForceCurrentView`, `DocumentBulkObsoleteToggleView`,
`DocumentBulkDeleteView`, `DocumentCompareView`), con dos regresiones
evitadas de forma general (no solo parcheadas): mensajes Django vía
`panel/_messages_oob.html` (OOB, reutilizable por cualquier vista HTMX
futura del panel) y sección "Candidatos a documento obsoleto" también
como OOB para no quedarse con datos obsoletos hasta el próximo F5.
Dominio Personal no tocado (su vista de redirect ya era un fragmento
puro, sin el problema).

**Toggle documentadas/sin documentar (commit `088055b`, segundo
chat):** antes de escribir código, criterio de "documentado" verificado
empíricamente contra la BD real (Comando S vía consola PythonAnywhere,
shell Django/ORM) usando la A-36 como caso conocido documentado que
Miguel Ángel indicó -- hallazgo real de paso: el código en BD es `A36`
(sin guion), no `A-36`. Con el código correcto: 508 `MachineAsset` en
total, solo 2 documentadas (`A36`, `A29`), 506 sin documentar. `doc_count`
anotado con el mismo criterio que `_machine_documents_view_data`/
`_machine_obsolete_candidates` (CLASSIFIED, excluyendo maestro
pendiente y candidato a obsoleto) -- coincide hoy con "cualquier
documento" porque los 30 `MachineDocument` reales no tienen ninguno de
esos dos flags activos, pero es el criterio semánticamente correcto de
cara a volumen futuro. UI: grupo de radio botones (Todas/Documentadas/
Sin documentar, `btn-check` de Bootstrap) junto al buscador existente
en `hub.html`, mismo patrón `hx-get`+`hx-trigger=change` que el resto
del panel; `hx-include` cambiado de un solo campo a `closest .card`
para que buscador y toggle compartan valores en cada petición.

**Decisión cerrada con Miguel Ángel:** planteado un badge por máquina
en el listado además del toggle -- descartado explícitamente: *"con el
toggle todas/documentadas/sin documentar no hace falta badge por
máquina"*. No se implementa.

**Cierre de sesión:** Miguel Ángel considera esta parte del hito
(documentación de maquinaria) "supuestamente cerrada" -- en su propia
aclaración, los hitos nunca se cierran de verdad, solo se pausan; H23
permanece `EN PROGRESO` en el enrutador, sin PCH. Los puntos que
quedaron sin empezar hoy se trasladan íntegros a la hoja de ruta de
mañana.

### Hoja de Ruta para la Sesión Siguiente (S030)

1. **H10 -- fotos de abonos al devolver mercadería.** Arrastrado sin
   cambios desde S028: "hay que arreglar también una cosa en el tema
   de los albaranes, que es cuando se devuelve mercadería para que
   puedan subir la foto de los abonos." Ver anexo H10
   (`ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`) para el detalle -- este
   anexo solo deja la referencia, el punto de partida completo vive
   allí. Sin investigar todavía.
2. **Decidir si la funcionalidad de vacaciones/calendario abre hito
   propio.** Sigue sin decidir -- ver sección "Funcionalidad nueva
   anotada por Miguel Ángel al cierre" más abajo para el detalle
   íntegro registrado en S028. Primera decisión de la sesión: hito
   nuevo (`nfs-enterprisebot-pch` Caso C / `com-picp`) o colgarlo de
   H23.
3. **Probar el dominio Personal de extremo a extremo** — sigue sin
   probarse, arrastrado desde S024 (quinta sesión consecutiva sin
   atenderse). `PersonalDocument` sigue en 0 filas reales. El
   accordion de Personal (`_personal_accordion.html`) sigue con el
   diseño antiguo (sin ficha de página propia, sin sistema de
   incidencias, sin candidatos a obsoleto, sin vigencia forzada, sin
   selección múltiple ni comparación, y ahora tampoco tiene el toggle
   documentadas/sin documentar que sí tiene Maquinaria) -- decidir con
   Miguel Ángel si aplicar toda la reconstrucción de Maquinaria de las
   últimas sesiones antes o después de probar el dominio tal cual está.
4. **Considerar limitar el tamaño de "individuales" enviados a
   `assess_master_coverage()`** (arrastrado desde S025) — el límite de
   tokens de Gemini se ha tocado repetidamente al acumular muchos
   documentos ya persistidos de la misma máquina -- mejora aparte, no
   implementada todavía.
5. **Dos ambigüedades de datos sin resolver de la auditoría de
   `MachineAsset`** (arrastradas desde S028, sin urgencia): valores
   cortos ambiguos que no se tocaron (A28=3388, A42=39053, series de 5
   dígitos D01/D02/D03, etc.) -- se corregirán solos conforme se suba
   documentación real de esas máquinas, no requieren acción activa.

**Observación sin acción inmediata (arrastrada de S023):**
PythonAnywhere limita las versiones de Python disponibles a 3.10 (y
anteriores) a fecha de esta sesión; `google-api-core` dejará de dar
soporte a Python 3.10 el 2026-10-04. Sin acción posible por nuestra
parte (depende de que PythonAnywhere añada una versión superior) —
vigilar antes de esa fecha si no ha cambiado, para planificar la
migración con margen. Correo a soporte de PythonAnywhere redactado y
entregado a Miguel Ángel en S028 (sin confirmar todavía si llegó a
enviarse ni respuesta recibida -- preguntar al empezar la siguiente).

### Funcionalidad nueva anotada por Miguel Ángel al cierre — evaluar si abre hito propio

Miguel Ángel especificó al cierre de esta sesión una funcionalidad de
**vacaciones y calendario**, de un dominio distinto (RRHH/planificación)
al de este hito. Se registra aquí íntegra para no perder el detalle,
pero la primera decisión de la siguiente sesión debe ser si esto abre
un hito nuevo (`nfs-enterprisebot-pch` Caso C / `com-picp`) en vez de
colgarlo de H23 — **no evaluado todavía, decidir con Miguel Ángel al
empezar**.

**Tarea automática de vacaciones:**
- Al registrar vacaciones para un operario/chófer, se añade
  automáticamente una tarea con centro de gasto `PERSONAL` (nuevo
  valor a dar de alta donde corresponda — ubicación exacta del
  catálogo de centros de gasto/motivos a confirmar).
- Añadir `VACACIONES` al desplegable de motivos existente (identificar
  en qué modelo/formulario vive ese desplegable al empezar la
  sesión — no localizado todavía).
- En el campo donde normalmente iría la resolución de la avería, para
  esta tarea automática va el día de fin de vacaciones.
- Se añade en la última jornada de trabajo antes de las vacaciones
  (generación automática, no manual).
- Duración automática: 1 hora.
- **No cuenta en el cómputo de horas** (excluir explícitamente de
  cualquier agregado de horas trabajadas/facturables).

**Aplicación de calendario:**
- Visible para todo el mundo (todos los roles autenticados).
- Si el usuario es `ADMIN` o `SUPERVISOR`: filtro por
  operario/chófer, puede ver el calendario de cualquiera.
- Si el usuario es `WORKSHOP` (mecánico) o `DRIVER` (chófer): solo ve
  su propio calendario, sin selector.
- Código de colores por día:
  - **Azul** — día trabajado (con parte registrado).
  - **Verde** — día de vacaciones.
  - **Naranja** — día de baja (opción dentro de "personal" —
    confirmar catálogo exacto de motivos de baja con Miguel Ángel).
  - **Rojo** — día laborable sin parte, sin vacaciones, sin festivo y
    sin baja (ausencia no justificada / hueco a revisar).
  - **Amarillo** — festivo.

**Nota de cierre (S021):** esta funcionalidad abrió como hito propio,
**H24 — Vacaciones y Calendario**, en S018, y quedó completa en S020.
Se deja esta sección tal cual como registro histórico de cómo se
originó, sin más acción pendiente aquí.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| — | — | Hito creado en S016 (desvío desde H17), a petición explícita de Miguel Ángel. Sin trabajo de código todavía — ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión. |
| S017 | 2026-07-14 | Primera sesión de código del hito. Modelo `MachineDocument` + app `machine_documents` + rol `DOCS_SUPERVISOR`, servicio de clasificación Gemini Vision (clasificación + metadatos en una sola llamada), integración en Historial de Máquina/Centros de gasto, pipeline migrado de síncrono a asíncrono (Celery) tras un 504 real de PythonAnywhere. Bug de traducción de categorías de avería corregido de paso (fuera de este hito). Ver COMPLETADAS EN S017 arriba para el detalle completo. |
| S021 | 2026-07-16 | Sesión con H24 EN PROGRESO al arrancar, pero prácticamente todo el trabajo real fue de H23 (**PCH H24→H23 ejecutado al cierre**, confirmado por Miguel Ángel). Fix de sidebar de `alvarez_admin` (commit `e2a5ecc` -- `company_user` ausente del contexto de `MachineDocumentBatchUploadView`). Modelo dinámico de metadatos: `period_start`/`period_end`/`amount` + `extra_data` JSON (commit `4ffebee`, migración `0004` verificada aplicada en producción). Plantilla WhatsApp `document_expiry_alert` creada, rechazada dos veces por Meta ("Variables can't be at the start or end of the template"), plantillas rechazadas borradas de Twilio, rediseñada y reenviada a revisión (`HX55da66276bb2025f691c378abff0123e`, pendiente de aprobación). Desvío puntual a H07 (sin PCH, marcador no se movió hasta el cierre): verificación del mecanismo `PARTE-BACKUP` (confirmado funcional, 39 líneas reales en `error.log`), dos partes recuperados a mano por Miguel Ángel (Antonio Fontalba 22/06, Pablo Cañamero 03/07), y nueva vista de Administración "Borradores de Partes" + `SuperuserRequiredMixin` (sustituye el hardcode de username `alvarez_admin` por `is_superuser` de Django) -- ver anexo H07 para el detalle completo de esa pieza. Un incidente de despliegue propio (`ImportError` por `WorkOrderDraftListView` sin re-exportar en `panel/views.py`) diagnosticado con datos reales y corregido en la misma sesión (commit `7344d46`). Cuatro decisiones de diseño cerradas con Miguel Ángel para la continuación de H23 (vigencia, archivado, plantilla, modelo dinámico) -- ver "Decisiones cerradas en S021" y "Hoja de Ruta para la Sesión Siguiente (S022)" arriba. |
| S023 | 2026-07-16 | H23 EN PROGRESO durante toda la sesión (desvío Caso A, marcador nunca movido). Incidente real: Vertex AI roto para toda la plataforma (documentos + IVR) tras el cambio de IAM de S022 (rol de Vertex AI sustituido por `Storage Admin` en vez de añadido); diagnosticado exclusivamente por logs reales (`alwayson-log-242133.log`, `bridge.log`) tras corrección explícita de Miguel Ángel cuando el modelo empezó a especular sobre el proyecto GCP; arreglado añadiendo `Agent Platform User` (`roles/aiplatform.user`); verificado reprocesando los 10 documentos de A-45 (todos `CLASSIFIED`, maestro detectado correctamente) y con una llamada IVR real (audio bidireccional confirmado). Hallazgo: el IVR llevaba roto desde el cambio de IAM aunque Miguel Ángel creía que funcionaba -- confirmado por log, no por suposición. Bug fuera de alcance corregido de paso: tarea Celery muerta `purge_old_chat_messages` (eliminada en H17, seguía en `CELERY_BEAT_SCHEDULE`) -- ver anexo H17. Desvío al resto de la sesión: H26 -- Infraestructura Documental Compartida completada por entero (app `document_management`, servicio de vigencia/sustitución, fusión de PDF, motor de alertas) -- ver anexo H26 "COMPLETADAS EN S023" para el detalle. Corrección de rumbo de Miguel Ángel durante la sesión: `EmailTemplate` no se edita desde el admin de Django (nunca lo pidió), y no se construye ninguna interfaz mínima desechable -- se queda como modelo sin UI. Ver "Hoja de Ruta para la Sesión Siguiente (S024)" arriba para el punto de partida: interfaz de panel de H23 consumiendo los servicios de H26. |
| S024 | 2026-07-17 | H23 EN PROGRESO durante toda la sesión, sin desvíos ni PCH. Sesión larguísima: 26 commits, 61 archivos, +7795/-560 líneas. Interfaz de panel de H23/H25 construida y cerrada por completo (vincular sin asignar, borrar archivado, modificar vigente, panel de alertas, CRUD de plantillas de email, generación de dossier), reconvertida entera a HTMX sin recargas de página, con visor de subida en vivo (sondeo automático, sin botones "Actualizar") y comando `reset_documentation` para poder repetir pruebas reales desde limpio. Encontrados y corregidos en la misma sesión, todos con datos reales (logs del worker Celery, log web, consultas de solo lectura a BD, búsqueda del foro oficial de PythonAnywhere): enrutado que ignoraba el nombre de archivo y comparaba códigos de máquina byte a byte; documento maestro que se persistía en GCS pese a descartarse su contenido (dos capas de corrección, incluida una segunda salvaguarda semántica); regresión del manual de uso en el enrutado (heurístico "nunca llamar a Gemini" que faltaba en el punto nuevo); falso estado "Asignado" del maestro en el visor por una condición de carrera con la Fase 2; listado de usuarios mostrando "Operador" para 3 de los 8 roles reales (bug de visualización puro, la BD nunca estuvo mal -- Miguel Ángel corrigió al modelo por dar la creación del usuario por fallida sin comprobar antes); doble subida no detectada por la deduplicación; y el hallazgo más grande de la sesión, un límite duro de 100 MiB por petición HTTP de PythonAnywhere (no configurable, sin rastro en la aplicación al superarlo) que impedía subir la carpeta de la A36 (121 archivos) -- resuelto troceando la subida automáticamente en el navegador. Ver "COMPLETADAS EN S024" arriba para el detalle completo, y "Hoja de Ruta para la Sesión Siguiente (S025)" para el punto de partida. |
| S025 | 2026-07-20 | H23 EN PROGRESO durante toda la sesión (un desvío puntual real a `spare_parts` H10 -- albaranes de proveedor -- sin PCH). Sesión larguísima: 27 commits, 37 archivos, +2657/-458 líneas. Ver "COMPLETADAS EN S025" arriba para el detalle completo -- resumen: modal de subida rediseñado, sustitución silenciosa + historial, plantilla WhatsApp confirmada aprobada, panel de Alertas rediseñado con envío manual/filtro por máquina, descarte heurístico de dossiers, restructuración de navegación (ficha de página completa por máquina, con URL propia), conversión de manuales a Markdown, asignación manual + prompt ampliado en albaranes, y dos incidentes reales de producción diagnosticados y corregidos con datos reales en cada paso: (1) bug crítico de `assess_master_coverage()` que interpretaba un error de Gemini como "cobertura confirmada" y descartaba maestros sin comparar -- **13 documentos reales perdidos antes del fix**, lista completa entregada a Miguel Ángel para recuperación manual; (2) worker Celery caído en medio de un lote de 95 documentos sin ningún error en el log -- causa raíz identificada (Celery sin `acks_late`/`prefetch_multiplier` configurados) y corregida con los tres ajustes de resiliencia recomendados por la documentación oficial de Celery 5.6.3. Ver "Hoja de Ruta para la Sesión Siguiente (S026)" arriba para el punto de partida. |
| S026 | 2026-07-21 | H23 EN PROGRESO durante toda la sesión, sin desvíos ni PCH. La sesión más larga del hito hasta la fecha (varios chats consecutivos por límite de contexto, mismo número de sesión): 22 commits, 22 archivos, +3172/-49 líneas. Reconstrucción completa del pipeline de ingesta de documentación de maquinaria en 5 fases (reglas heurísticas de descarte por nombre, modelo de aprendizaje automático de tipos, Gemini como extractor puro cuando la heurística ya sabe el tipo, pantalla de revisión con checkboxes, CRUD del diccionario), seguida de una prueba real de subida completa de la A-36 que fue encontrando, uno a uno, una cadena larga de bugs reales -- todos corregidos en la misma sesión con datos reales (logs del worker, consultas de BD, capturas de Miguel Ángel): comando de reset duplicado con el mismo bug que motivó sustituir uno anterior (blobs de GCS huérfanos, limpiados con comando nuevo); la máquina se determinaba por contenido en vez de por nombre de archivo pese a la decisión ya cerrada; barra lateral vacía en la ficha de máquina (`company_user` ausente del contexto, bug distinto del de S021); tras un movimiento automático entre máquinas sin dejar rastro del error, Miguel Ángel cerró que el movimiento NUNCA debe ser automático -- la CARPETA manda, con sistema completo de resolución manual de incidencias (botón "Resolver con `<máquina>`" por cada máquina distinta implicada, pantalla partida, caso "sin asignar" con selector libre); "SCAN" (nombre de escáner genérico) aprendido como palabra clave de tipo ITV a partir de un único error de Gemini, contaminando todos los archivos futuros de ese escáner; y el hallazgo más grande de la sesión, un bug de fondo en la normalización de palabras clave (lo aprendido nunca podía volver a encontrarse a sí mismo en un archivo futuro) que explicaba casi todos los "tipo no reconocido" de las capturas de Miguel Ángel -- corregido de raíz junto con una REGLA B-bis nueva (agrupar por "molde" archivos de tipo desconocido, sin necesitar saber el nombre del tipo) y varios formatos de fecha nuevos (año suelto, rango `AAAA-AAAA`, periodo compacto `DDMMAA AL DDMMAA`). Prueba final de 42 documentos: 42/42 correctamente asignados a la A-36, cero fugas, cero sin asignar. Dos hallazgos reales sin corregir todavía, ambos primera tarea de la sesión siguiente: falsos positivos de discrepancia por bastidor (`MachineAsset` no tiene ese campo) y datos corruptos en varias decenas de filas de `fleet.MachineAsset` (fechas en vez de código/matrícula real). Ver "CIERRE DE S026, PARTE 2" arriba para el detalle completo, y "Hoja de Ruta para la Sesión Siguiente (S027)" para el punto de partida. |
| S027 | 2026-07-21 | **NOTA DE DESVÍO — sin trabajo directo en H23, sesión interrumpida por caída de herramientas del modelo.** Sesión arrancada para ejecutar la hoja de ruta de arriba, desviada de inmediato (Caso D del enrutador de anexos, sin PCH, marcador `EN PROGRESO` sin mover) para atender 4 incidencias reales que Miguel Ángel reportó al empezar en la vista unificada de partes digitales, ninguna ligada a H23: selector de periodo y preservación de filtros en `WorkOrderAdminHistoryView` (dominio H17, unificada allí en S012), botón "Marcar revisado" en el editor de parte digital (dominio H07, `form_entry.html`/`WorkOrderEntryFormView`), verificación sin cambios de la suma de horas del filtro en Revisados, y un 404 real corregido de paso (redirect roto desde la unificación H17-S012). Detalle técnico completo, los dos commits (`372faae`, `6eb7bbb`) y la verificación de despliegue en `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md` (fila `S_H07_12`) y `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md` (fila `S027`). Las herramientas del modelo cayeron antes de poder volver a la hoja de ruta de H23 y sin poder cerrar la sesión formalmente ni registrar el desvío -- confirmado por Miguel Ángel al reanudar que ningún commit se perdió (ambos en `origin/main`, ambos con despliegue verificado vía API de GitHub Actions, sin migración) y que las dos decisiones de diseño autónomas de la sesión (selector de periodo como desplegable, no auto-ajuste; suma de horas correcta sin cambios) funcionan perfectamente en producción. Cierre de S027 documentado retroactivamente en sesión posterior (S028), que retoma la hoja de ruta de abajo sin cambios -- Caso D: "el hito no avanzó". |
| S028 | 2026-07-22 | H23 EN PROGRESO durante toda la sesión, con dos desvíos puntuales breves (Caso A, marcador nunca movido): a H07 (investigación de un bug real de pérdida de datos en modo edición de partes digitales, sin código tocado -- ver anexo H07 fila `S_H07_13`) y a H10 (una petición nueva sobre fotos de abonos al devolver mercadería, anotada en su propia hoja de ruta, sin trabajo de código). Sesión larguísima: 22 commits, 18 archivos, +2173/-298 líneas. Cerró retroactivamente S027 al empezar. Cerró por completo la primera tarea heredada de S026 (bastidor de `fleet.MachineAsset`): el campo ya existía, el problema real era que la comparación de discrepancia nunca lo tenía en cuenta; encontrado y corregido además un hallazgo más profundo con datos reales de la A-36 -- un documento con matrícula Y bastidor a la vez se marcaba como discrepancia falsa por dos causas encadenadas (comparación de nombre de archivo por subcadena libre en vez de token completo, y Gemini solo podía extraer una referencia por documento) -- solución de fondo: tres campos separados (matrícula/bastidor/código de flota), matrícula o código como ancla fuerte de identidad que nunca marca discrepancia y que puede CORREGIR un bastidor no confirmado ya guardado, verificado con simulación del peor caso de orden de procesamiento. Auditoría completa de los 566 `MachineAsset`: 58 filas borradas, 31 bastidores placeholder vaciados a mano. Rediseño completo de la pantalla de transferencia de incidencias (visor de documento, mecanismo de puntero visual definitivo, modal de cuenta atrás extraído a parcial reutilizable). Bloque de trabajo más grande de la sesión: funcionalidad nueva completa de "candidatos a documento obsoleto" (Gemini juzga por contenido, un humano siempre confirma el borrado, prioridad de resolución sobre incidencias de máquina), ampliada con selección múltiple y borrado en bloque, generalizada después a vigente/archivado (mismo mecanismo, sin restricción), comparación de dos documentos vía Gemini para detectar duplicados reales (con modal de espera, y corregida para marcar los DOS documentos comparados en vez de elegir uno automáticamente -- decisión explícita de Miguel Ángel), y las dos acciones en bloque simétricas (marcar/descartar obsoleto) en una sola vista genérica. Nuevo campo `force_current` para poder "recuperar documentos del cajón de archivos" -- vigencia forzada manualmente cuando el cálculo automático por fechas archivaría por error un documento que sigue siendo válido para toda la vida útil de la máquina. Otro fix real de paso: mensaje incorrecto en la pantalla de preflight para manuales de uso (la regla real nunca se había perdido, solo el texto mostrado). Prueba real con Yolanda (supervisora de documentación) al cierre, con feedback muy positivo ("de escándalo, de lujo, de cine") y dos incidencias menores para la sesión siguiente. Ver "COMPLETADAS EN S028" arriba para el detalle completo, y "Hoja de Ruta para la Sesión Siguiente (S029)" para el punto de partida. |
| S029 | 2026-07-22 | **Sesión partida en dos chats por una caída de herramientas del lado de Anthropic (no del proyecto), sin pérdida real de código.** H23 EN PROGRESO durante toda la sesión, sin PCH. Primer chat: resueltos los dos primeros puntos heredados de S028 y commiteados/pusheados antes de la caída -- condición de carrera del modal de cuenta atrás (`a54d6dd`, listener `htmx:afterRequest` que cierra el modal tras respuesta HTMX exitosa) y migración a HTMX real de las 5 vistas que mutan documentación de máquina (`201bb0b`, nuevo helper `_machine_detail_htmx_response()`, con mensajes Django y "Candidatos a documento obsoleto" resueltos como `hx-swap-oob` reutilizable). Segundo chat ("Continuación", título puesto por Miguel Ángel): arrancó verificando con `git log`/`git diff --stat` contra `origin/main` -- sin dar nada por hecho de memoria -- que el trabajo del primer chat sí estaba realmente commiteado y desplegado (el anexo, al no haberse cerrado la sesión anterior, seguía mostrando esos dos puntos como pendientes: desfase de documentación, no de código). Implementó el tercer punto pendiente, el toggle documentadas/sin documentar en el listado de Documentación (`088055b`): criterio de "documentado" verificado empíricamente contra la BD real antes de escribir código (Comando S vía consola PythonAnywhere), usando la A-36 como caso conocido -- hallazgo de paso: el código real en BD es `A36` sin guion; con eso corregido, 508 `MachineAsset` en total, solo 2 documentadas (`A36`, `A29`). `doc_count` con el mismo criterio que `_machine_documents_view_data` (CLASSIFIED, sin maestro pendiente, sin candidato a obsoleto). Badge por máquina planteado y descartado explícitamente por Miguel Ángel ("con el toggle... no hace falta badge por máquina"). Cierre: Miguel Ángel da esta parte del hito (documentación de maquinaria) por "supuestamente cerrada" -- aclarando él mismo que los hitos nunca se cierran de verdad, solo se pausan; H23 sigue `EN PROGRESO`. Ver "COMPLETADAS EN S029" arriba para el detalle completo, y "Hoja de Ruta para la Sesión Siguiente (S030)" para el punto de partida: H10 (fotos de abonos), decisión sobre hito de vacaciones/calendario, y prueba end-to-end del dominio Personal (quinta sesión consecutiva sin atenderse). |
