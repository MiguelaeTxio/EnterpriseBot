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

**Hito recién creado — sin trabajo de código todavía.** Primera sesión:

1. Resolver las 5 preguntas abiertas de la sección 4 con Miguel Ángel
   antes de escribir una sola línea de modelo.
2. Verificación online de la API de Gemini Vision para PDFs (directriz
   4.4) — obligatoria antes de cualquier implementación.
3. Modelo `MachineDocument` + migración (según la app decidida en la
   pregunta 1).
4. Servicio de clasificación (Gemini) — validar primero contra los 8
   documentos reales de la máquina A-45 (ya persistidos a mano en S016)
   como caso de prueba conocido, antes de generalizar.
5. Generalización de `gdrive_service.py` (tercera raíz) + vista de
   subida + vista de listado + entrada de sidebar.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| — | — | Hito creado en S016 (desvío desde H17), a petición explícita de Miguel Ángel. Sin trabajo de código todavía — ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión. |
