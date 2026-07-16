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

### Hoja de Ruta para la Sesión Siguiente (S023)

**Prioridad 0 de S022 -- COMPLETADA en esta sesión.** Migración
Google Drive -> Google Cloud Storage hecha, verificada y desplegada
(ver "COMPLETADAS EN S022" arriba). No queda ninguna acción pendiente
de esa migración salvo el borrado manual de los 10 archivos
originales en Drive, que Miguel Ángel se encarga de hacer él mismo.

**Recomendación de Claude para abrir S023 (Miguel Ángel dejó la
decisión abierta al cierre de S022, "como tú lo veas mejor"):**
empezar por **H26 -- Infraestructura Documental Compartida**
(`ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md`), no por H25. Motivo: los
tres puntos pendientes de este propio hito (vigencia, archivado,
alarmas) ya tienen datos reales esperando y están bloqueados
exactamente por lo que construye H26; H25 en cambio todavía tiene 7
preguntas de diseño sin cerrar (ver anexo V25 sección 4) antes de
poder escribir código. Confirmar con Miguel Ángel al empezar la
sesión si se sigue esta recomendación o se prefiere lo contrario --
no asumir, preguntar primero (directriz 4.8).

**Si se empieza por H26** (ver ese anexo para el detalle completo):
1. Resolver las 5 preguntas abiertas del anexo V26 sección 4 con
   Miguel Ángel (ubicación del servicio, motor de fusión de PDF,
   contenido de la plantilla de email, periodicidad del motor de
   alertas, ámbito del diálogo de sustitución).
2. Construir en el orden sugerido en ese mismo anexo (a confirmar):
   diálogo de sustitución -> fusión/generación de PDF -> plantilla de
   email -> motor de alertas.
3. Verificar de nuevo el estado de la plantilla WhatsApp
   `document_expiry_alert` (`HX55da66276bb2025f691c378abff0123e`) --
   estado a fecha de S022: `pending`, Meta todavía no la ha resuelto.
   Si sigue `pending`, el motor de alertas puede construirse igual,
   pero no podrá enviar mensajes reales hasta que Meta apruebe.
4. Una vez H26 tenga las capacidades base, retomar los tres puntos
   pendientes de este propio hito (vigencia, archivado, modal de
   alerta) construyéndolos como consumidores de H26, no por separado.

**Si en cambio se empieza por H25** (ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md`
sección 4 y 5 para el detalle completo): resolver primero sus 7
preguntas abiertas de diseño (nombre de app, modelo exacto, categorías,
roles con acceso, relación con CompanyUser, ubicación de la vista,
vigencia de la API de Gemini Vision).

**Sin cambios, sigue pendiente independientemente de por dónde se
empiece:** revisión del CRUD de documentación de centros de gasto más
allá de lo anterior -- Miguel Ángel lo dejó abierto en S021 ("no sé si
habrá que mejorar el CRUD... está bien, pero habría que dotar las
diferentes funcionalidades") -- confirmar alcance concreto con él, no
asumir qué falta.

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
