# H30 — Vinculación Documental Real: Centros de Gasto y Personal con Referencia Viva a su Documentación

## 1. Objetivo del hito

Dotar a `fleet.MachineAsset` y a `document_explorer.PersonIdentity` de
una referencia real y **viva** a su documentación — no un catálogo de
identidad aislado (lo que ya existe hoy), sino un vínculo que sepa
dónde está cada documento de cada máquina y cada persona, y que se
mantenga correcto solo, sin intervención manual, cuando ese documento
se mueva, se renombre, se sustituya por uno más reciente del mismo
tipo, o se borre — siempre dentro del sistema de archivos virtual ya
construido en H29 (`DocumentIndexEntry`, 4.12: nunca se toca GCS para
esto, solo `parent_path`/`name`).

Miguel Ángel, verbatim (S043), al abrir el hito: *"Ahora se trata de
recorrer nuestra base de datos y añadir entradas con la ruta de la
documentación de cada ítem [...] cada máquina ya va a tener en base de
datos su ruta donde está su archivo [...] cada vez que se mueva el
directorio se tiene que mover ese dato en el modelo del centro de
gasto y en el modelo del personal."*

## 2. Punto de partida real — qué ya existe, verificado en S043

- `fleet.MachineAsset` (513 filas antes de S043, +12 dadas de alta en
  S043 por comparación de secuencia de familia de código) y
  `document_explorer.PersonIdentity` (70 filas, todas verificadas
  contra un Excel real de plantilla activa) están al día como
  catálogos de **identidad** — código/matrícula/DNI, empresa,
  carpeta base — pero **no** llevan ninguna referencia a documentos
  individuales por tipo (ITV vigente, seguro vigente, DNI, etc.).
- `PersonIdentity.folder_path` ya apunta a la carpeta real de cada
  persona en `DOC. PERSONAL` — es una referencia a **carpeta**, no a
  documento concreto por tipo. `MachineAsset` no tiene ni siquiera
  eso todavía.
- H26 (`document_management`) ya construyó exactamente el mecanismo de
  sustitución silenciosa por fecha que este hito necesita
  (`DocumentSubstitutionLog` + `vigencia_service.
  evaluate_substitution()`, decisión real S025: nunca pregunta, decide
  sola por fecha y deja registro consultable) — pero enganchado al
  modelo legado `machine_documents.MachineDocument`, no al
  `DocumentIndexEntry` unificado de H29. Sin diseño propio, no es
  reutilizable tal cual.
- Las interfaces de administración de H23/H25/H26 (subida tipada,
  sustitución, alertas de caducidad) siguen construidas sobre los
  cubos/modelos legados (`machine_documents`, `personal_documents`),
  cuya consolidación hacia `cgs_grupo_alvarez`/`DocumentIndexEntry`
  quedó aplazada en H29 (decisión 3.12) hasta que la clasificación
  automática estuviera estable — Miguel Ángel confirmó en S043 que
  ese punto ya se ha alcanzado: *"la interfaz y entrada para
  gestionar la documentación será la que teníamos... ya hemos
  llegado al punto de ligar lo anterior con lo nuevo."*

## 3. Decisiones ya tomadas por Miguel Ángel (S043), registradas verbatim

- **Vía de entrada de documentación, sin cambios**: buzón de entrada
  (`AccesoBuzonDocumentacion`, H29 3.14), agente H28 en las carpetas ya
  vigiladas, o subida directa a Microsoft 365 — en los tres casos el
  documento pasa siempre por cuarentena y se clasifica igual que hoy.
  *"O me va a entrar máquina, me va a entrar documentación a través
  del buzón. O directamente van a meter documentación nueva a través
  de la vía normal que utilizan."*
- **Sustitución automática, sin diálogo**: *"Voy a subir documentación
  de esta máquina [...] la ITV nueva. Automáticamente tendremos que
  marcar la ITV que teníamos como obsoleta y poner la ITV nueva como
  documento ya vigente."* Mismo principio ya validado en H26/S025
  (silenciosa, con registro).
- **Nunca se renombra fuera de la plataforma**: *"Renombrarse no se va
  a poder renombrar porque lo vamos a hacer todo a través de la
  plataforma."* Coherente con 4.12 — todo movimiento/renombrado es
  siempre una escritura de `DocumentIndexEntry`, nunca una operación
  real sobre el archivo de origen.
- **Organización de manuales, antes o en paralelo**: *"Antes de hacer
  esto, organizar la carpeta de manuales y dejar ya un manual por
  modelo de máquina [...] para que tú sepas lo que tienes que hacer y
  puedas organizar la tarea como mejor quieras."* Conecta con el punto
  ya registrado en H29 3.21/3.22 (34 discrepancias reales de
  `audit_manual_models`, sin decisión de deduplicación tomada
  todavía).

## 4. Preguntas abiertas, sin resolver por interpretación propia — a confirmar con Miguel Ángel antes de construir nada (directriz 4.8)

1. **Granularidad de la referencia real.** ¿Un campo por tipo de
   documento relevante (ITV vigente, seguro vigente, DNI, RM...) en
   `MachineAsset`/`PersonIdentity` directamente, o una tabla aparte
   (un `DocumentIndexEntry` marcado como "vigente" por
   `GenericForeignKey`, similar al patrón ya usado en H26
   `DocumentAlert`/`DocumentSubstitutionLog`)? La segunda opción evita
   migraciones de esquema cada vez que aparece un tipo de documento
   nuevo en el catálogo cerrado (H29 3.34); la primera es más simple
   de consultar pero más rígida.
2. **Alcance real de la sustitución automática.** H26 la limitó
   explícitamente a documentos con fecha de caducidad clara (ITV,
   seguro...) — ¿se extiende ahora a cualquier tipo del catálogo
   cerrado, o sigue acotada a los mismos tipos que ya tenía H26?
3. **Consolidación de cubos (H29 3.12) — orden real de dependencia.**
   ¿Este hito espera a que la consolidación de `machine_documents`/
   `personal_documents` hacia `cgs_grupo_alvarez` esté terminada antes
   de construir la referencia viva, o construye la referencia
   directamente contra `DocumentIndexEntry` y dan igual los cubos
   legados todavía activos mientras tanto?
4. **Organización de manuales — antes, en paralelo, o dentro de este
   mismo hito.** Miguel Ángel dejó la decisión de organización de la
   tarea explícitamente en mis manos ("puedas organizar la tarea como
   mejor quieras") — confirmar con él el orden real antes de empezar
   a tocar `MANUALES DE USO`.
5. **`DocumentSubstitutionLog`/`vigencia_service` — puerto o
   reconstrucción.** Leer primero el código real completo de H26 antes
   de decidir si se generaliza para aceptar `DocumentIndexEntry` (vía
   `GenericForeignKey`, ya lo permite) o si se escribe una versión
   nueva específica de H29/H30.

## 5. Hoja de ruta ejecutable para la primera sesión de H30

1. Leer `document_management/models.py` y
   `document_management/vigencia_service.py` completos (nunca de
   memoria) — confirmar exactamente qué tipos de documento participan
   hoy en sustitución y cómo decide `evaluate_substitution()` cuál
   documento gana.
2. Presentar a Miguel Ángel las cinco preguntas de la sección 4 de
   este anexo, una a una, y registrar sus respuestas verbatim
   (directriz 4.8) antes de escribir ninguna migración.
3. Con las respuestas ya registradas, diseñar el modelo de datos real
   (campo directo o tabla aparte) y escribir la migración
   correspondiente (`com-migrations` sección 1: modelo + migración en
   el mismo commit).
4. Construir el mecanismo de actualización automática: cuando
   `move_service.move_entry()`/`move_entries()` cambien
   `parent_path`/`name` de un `DocumentIndexEntry` referenciado como
   "vigente" por una máquina o persona, la referencia debe seguir
   apuntando a la fila correcta sin intervención manual — comprobar
   si esto ya funciona gratis (la referencia sería por FK/PK, no por
   ruta de texto) o si hace falta lógica nueva.
5. Adaptar o reconstruir la sustitución automática contra
   `DocumentIndexEntry`, con el mismo criterio silencioso de H26/S025
   (nunca preguntar, decidir por fecha, dejar registro consultable).
6. Decidir y ejecutar la organización de manuales (`MANUALES DE USO`,
   un manual por modelo de máquina) según lo acordado en el punto 4 de
   la sección 4.

## 6. Registro de Sesiones

### COMPLETADAS EN S44

Primera sesión de trabajo real de H30. Repaso completo:

**Paso 1 de la hoja de ruta — lectura real, no de memoria.** Se leyó
completo `document_management/models.py` y
`document_management/vigencia_service.py`. De esa lectura salió un
hallazgo real (directriz 4.9, corregido de inmediato, commit
`38a8c50`): los docstrings de `evaluate_substitution()` y
`SubstitutionResult` en `vigencia_service.py` seguían describiendo el
diseño original de H26 §2.4 (diálogo interactivo), obsoleto desde la
corrección de S025 (sustitución silenciosa) — verificado contra el
código real de `machine_documents/tasks.py` (Step 2bis). Corregido
para reflejar el comportamiento real.

**Paso 2 de la hoja de ruta — las cinco preguntas de la sección 4,
respondidas verbatim:**

1. **Granularidad:** tabla aparte (no campo directo en
   `MachineAsset`/`PersonIdentity`), siguiendo el patrón
   `GenericForeignKey` ya usado en H26.
2. **Alcance de la sustitución automática:** solo para documentos con
   fecha de caducidad clara — igual que H26, sin extender. Para
   documentos sin fecha clara: numeración ordinal, notificación visual
   en la tabla de documentos del activo, menú de acciones sobre los
   documentos en conflicto, y espera de orden directa del supervisor
   (Yolanda Bandera, `DOCS_SUPERVISOR`) para resolver — nunca
   sustitución automática silenciosa en ese caso.
3. **Consolidación de cubos — orden de dependencia:** las tres vías de
   entrada de documentación quedan así — carpetas vigiladas M365
   (`DOC. MÁQUINAS`/`DOC. PERSONAL`), `ACCESO_BUZON_DOCUMENTACION`, y
   CRUD adaptado de subida tipada (el legado se adapta, no se
   descarta). El CRUD tipado deja de escribir en los modelos legados
   (`machine_documents`/futuro de personal) y pasa a escribir
   directamente en `DocumentIndexEntry`/`cgs_grupo_alvarez`, igual que
   las otras dos vías — no se espera una consolidación previa separada.
   Matiz añadido sobre `ACCESO_BUZON_DOCUMENTACION`: recibe adjuntos de
   correo sin clasificar de antemano — el agente H28 debe separar lo
   que es documentación real (vía normal de cuarentena) de lo que no lo
   es (carpeta de adjuntos aparte, accesible al departamento que lo
   necesite).
4. **Organización de manuales:** va **antes** de construir la
   referencia viva — primer bloque de trabajo real de H30, confirmado
   explícitamente.
5. **`vigencia_service`/`DocumentSubstitutionLog`:** se reutilizan tal
   cual (el servicio ya es agnóstico; el modelo ya usa
   `GenericForeignKey`, apuntar a `DocumentIndexEntry` en vez de
   `MachineDocument` no requiere migración de esquema). Lo nuevo a
   construir es el llamador, hoy acoplado a `machine_documents/tasks.py`
   Step 2bis, que debe trasladarse a operar sobre `DocumentIndexEntry`
   dentro del flujo de indexación/clasificación de H29.

**Punto 6 de la hoja de ruta — organización de `MANUALES DE USO`,
trabajo real de esta sesión:**

- **Bug real encontrado y corregido** (commit `f97309f`):
  `audit_manual_models.py` (H29, S041) llevaba roto desde S042 —
  importaba `_extract_first_pages_pdf`, sustituida por
  `_extract_pdf_edges` (firma distinta) al introducirse el recorte
  primeras+últimas páginas. Nadie lo había vuelto a ejecutar desde
  entonces.
- **Verificación de límites reales de Gemini** (directriz técnica
  crítica, API externa): 50 MB por archivo es el límite estable en
  toda la familia Gemini; el límite de páginas varía por modelo
  (1.000-3.600 según generación), sin cifra pública confirmada
  específica para `gemini-3.5-flash` (nuestro `DEFAULT_MODEL`).
  Consulta real contra la BD: **291 candidatos actuales** (no 219,
  cifra desactualizada de S041), de los cuales **16 superan los 50
  MB** (hasta 420,6 MB).
- **Segundo bug real encontrado y corregido** (commit `340e9b9`):
  `audit_manual_models.py` se caía con `MySQLdb.OperationalError 4031`
  (conexión inactiva más tiempo que `wait_timeout` durante esperas
  largas de reintentos de Gemini) — corregido con
  `close_old_connections()` antes de cada iteración y aislamiento de
  fallo por entrada, para que un archivo problemático no tumbe los 290
  restantes.
- **Decisión de Miguel Ángel: cero llamadas a Gemini para esta
  tarea.** En vez de relanzar `audit_manual_models`, se construyó
  `export_manual_covers.py` (comando nuevo, solo lectura, commit
  `10c3a8b`): extrae las 2 primeras páginas de cada uno de los 291
  candidatos y las combina en un único PDF de revisión manual, con
  página de rótulo (carpeta/nombre/tamaño) antes de cada extracto.
  Ejecutado en producción sin incidencias: 291 procesados, 285 con
  extracto, 6 omitidos (no-PDF: `.zip`, `.docx`, `.rar`).
- **OCR y análisis del PDF combinado** (hecho fuera del proyecto, en
  el entorno de trabajo del modelo — sin coste de Gemini, sin tocar
  producción): 850 páginas / 211 MB procesadas con Tesseract
  (español+alemán+inglés). De los 291 candidatos, 171 tienen código de
  máquina detectable en el nombre (64 máquinas distintas), 120 no.
- **Plan de deduplicación construido para las 64 máquinas con código.**
  Criterio inicial (excluir fragmentos tipo portada/índice, quedarse
  con el más pesado) **corregido por Miguel Ángel a mitad de sesión:
  quedarse con el más ligero** entre candidatos de contenido
  equivalente — razón explícita: límites de tamaño de subida a
  plataformas, y estrategia futura de convertir a Markdown para
  aligerar aún más (idea registrada, no implementada esta sesión).
  Recalculado con el criterio corregido: 30 de las 64 máquinas cambian
  de archivo ganador.
- **Siete casos ambiguos revisados uno a uno contra el propio texto
  OCR** (no solo por tamaño): A67, B23 y H02 resueltos — son
  documentos genuinamente distintos y complementarios, no duplicados,
  se mantienen ambos. **A56 — bug real de archivo mal ubicado
  descubierto**: un `.rar` en la carpeta de A56 decía LTM 1230-5.1
  (BAL 27000-07-10) mientras el resto de A56 es LTM 1130-5.1 —
  confirmado con capturas reales del propio Miguel Ángel que ese
  BAL/modelo coincide exactamente con el manual ya catalogado de A59;
  el `.rar` queda excluido del grupo A56 como redundante con A59.
  **A62 — confirmado**: usar la versión de 16,9 MB en vez de la de
  420,6 MB (mismo contenido verificado, mismas 1.354 páginas).
  **A65 y B22 — sin resolver, pendientes de respuesta de Miguel
  Ángel** (ver Hoja de Ruta).
- **Verificación de cobertura real contra `fleet.MachineAsset`**
  (comprobación pedida explícitamente por Miguel Ángel antes de tocar
  nada: "no sea que por heurística eliminemos un manual que esté
  siendo necesario"). 498 máquinas activas en BD; tras filtrar
  turismos/administrativo (no requieren manual) y corregir un bug real
  de normalización de ceros a la izquierda en el cruce de códigos
  (Z1↔Z01), quedan **312 máquinas de maquinaria pesada real sin ningún
  manual detectado en el corpus**. Cruce automático contra los 120
  archivos sin código: nivel marca-sola generó demasiado ruido (falso
  positivo real detectado: "MAN" como marca coincidía por subcadena
  con cualquier "MANUAL"); nivel marca+número de modelo también generó
  ruido por números cortos genéricos. **Hallazgo sólido y confirmado**:
  19 plataformas JLG (Z101/Z125/Z126/Z127/Z52/Z53/Z58/Z59/Z60/Z61/Z62/
  Z71/Z72/Z73, Z114/Z115/Z131/Z132, Z120/Z44/Z69) tienen su manual real
  ya en el corpus, archivado sin código de máquina en el nombre —
  pendiente de aplicar (ver Hoja de Ruta).
- **Miguel Ángel propone criterio de cierre para la sesión
  siguiente**: analizar la cobertura de manuales por **familia de
  maquinaria**, no máquina a máquina — si una familia entera ya tiene
  manuales (A, B), buscar solo los huecos reales dentro de esa
  familia; si una familia entera nunca los necesita por el tipo de
  máquina (turismos, motos, furgonetas, y confirmado explícitamente
  la familia G de góndolas/remolques), no perder tiempo buscándole
  manual a ninguna de sus máquinas.

**Incidencia de sesión, sin impacto en el resultado**: confusión real
sobre en qué consola de PythonAnywhere estaba corriendo
`audit_manual_models` — resuelta con dato real (documentación oficial
de PythonAnywhere: sin espacio de procesos compartido entre consolas),
no por suposición.

### COMPLETADAS EN S45

**Punto 1 de la hoja de ruta — los dos casos ambiguos, cerrados con
respuesta verbatim:**
- A65: confirmado que **no** está mal archivado — UTM 845 es la
  denominación alemana de la misma máquina, LTM 1070-4.1 (confirmado
  con la "Manufacturer confirmation" real de Liebherr, que lista
  ambos nombres para el mismo modelo).
- B22: `MANUAL USO+CE.pdf` es la declaración CE + el mismo manual que
  ya existe por separado en `MANUAL USO.pdf` — contenido redundante,
  no complementario (a diferencia de B23). Se descarta el `+CE`.

**Criterio de deduplicación corregido dos veces en vivo, con datos
reales cada vez:**
1. El documento `H30_plan_dedup_manuales.md` que Miguel Ángel aportó
   resultó ser la versión **sin recalcular** tras la corrección de
   criterio de S44 (confirmado explícitamente) — se recalcularon los
   64 grupos contra tamaños reales de BD, no contra ese documento.
2. Miguel Ángel decide en esta misma sesión volver al criterio
   original (**más pesado gana**, con recompresión posterior como
   trabajo aparte, pendiente), con dos excepciones de contenido fijas
   verificadas por OCR: **A62** (16,9 MB, no 420,6 MB — mismo
   contenido, 1.354 páginas) y **A58** (16,9 MB, no 81,7 MB del
   archivo `PDF-AD.pdf`, que el documento original ya trataba como
   documento distinto — probable adenda, no variante de compresión).
3. **A22, A41, A43** no eran casos de deduplicación: A22 y A41 son
   máquinas **vendidas** sin manual en ningún sitio (solo
   documentación administrativa); A43 (`TEREX DEMAG AC 35`, activa)
   tiene un archivo candidato (`A-43 E-7099-BDP.pdf`, 19 páginas,
   escaneado sin capa de texto) que Miguel Ángel confirmó tras abrirlo
   personalmente que **es un dossier administrativo, no el manual**
   (foto real del manual real aportada: `TEREX DEMAG AC35 L`). Los
   tres quedan fuera de deduplicación, como huecos reales de cobertura
   para el punto 5 de la hoja de ruta.
4. **U9** (`EuroCompact`) confirmado ausente de todo el índice, ningún
   archivo con ese nombre ni con "EuroCompact" como texto libre.

**Papelera virtual ejecutada** (`DataOperationLog` operación **#252**,
mismo patrón que `ResolveDuplicatesView`, H29 §3.22): 40 grupos con
más de un candidato real, 95 archivos a papelera, 43 conservados,
**1.782 MB recuperables**. Ejecutado sin visto bueno final por
decisión explícita de Miguel Ángel ("vamos mal de tiempo... si alguien
chilla ya nos enteraremos").

**Punto 4 — los 19 (en realidad 22) emparejamientos JLG aplicados.**
Verificación cruzada real detectó que **Z137** debía sumarse al grupo
510AJ (su propia carpeta tenía un manual y una ficha técnica 510AJ ya
enviados a papelera como duplicados en una operación anterior,
operación #1 del proyecto) — y que `fleet.MachineAsset` de Z137 tenía
`brand_model`/`family` vacíos, corregido a `J.L.G 510AJ`/`PLATAFOR`.
Grupo 510AJ final: Z114/Z115/Z131/Z132/**Z137** (5, no 4).

**Backfill real de `SubjectDocumentReference` (nuevo modelo, ver
abajo): 78 vínculos máquina→manual vigente**, con verificación uno a
uno contra `fleet.MachineAsset` real — 7 códigos del plan original no
resolvieron a la primera (`D012`, `MK140`, `V1`, `V7`, `Z10`, `Z7`,
`Z1`); con el listado real de maquinaria que aportó Miguel Ángel se
resolvieron 5 (`Z010`, `Z07`, `Z01` — códigos con cero a la izquierda
distintos de `Z100`-`Z109`/`Z70`-`Z79`; `V7` no era código, era
"S3370RT V7" del nombre de modelo → Z110/Z111, comparten manual).
`D012`, `MK140` y `V1`("URA 376 & 506") quedan sin resolver — no
existen en `fleet.MachineAsset` ni en el listado completo de
maquinaria, ni por código ni por modelo.

**Modelo de datos real (puntos 3-4 de la hoja de ruta original de
H30), diseñado y desplegado:**
- `document_explorer.SubjectDocumentReference` (migración 0017):
  referencia viva sujeto (`MachineAsset`/`PersonIdentity`, vía
  `GenericForeignKey`) → documento vigente de un tipo dado, por **FK
  directa a `DocumentIndexEntry`** — confirmado en la propia sesión
  que esto resuelve gratis el punto 4 original de la hoja de ruta (un
  mover/renombrar virtual, 4.12, no rompe la referencia, cero hooks en
  `move_service`).
- `DocumentIndexEntry.document_type/expiry_date/issue_date` y
  `DocumentTypeCatalog.tracks_expiry` (migraciones 0018-0019):
  prerequisito real descubierto en la propia sesión para poder
  enganchar `vigencia_service.evaluate_substitution()` a la
  clasificación H29 — la clasificación H29 **no extrae fechas en
  absoluto** hoy (solo lo hacía el sistema legado H23). Decisión de
  escalabilidad explícita de Miguel Ángel: qué tipos documentales
  participan en fechas/sustitución vive como dato en el propio
  catálogo (`tracks_expiry`), nunca como lista fija en código.
- Catálogo `tracks_expiry` cerrado con auditoría real (muestra por
  tipo, PyMuPDF + revisión directa de Miguel Ángel sobre capturas de
  los propios documentos, ya que varios son escaneos sin capa de
  texto): `ITV`, `OCA`, `SEGURO`, `PERMISO_CIRCULACION`,
  `CARNET_CONDUCIR`, `EXCEDENCIA`, `FORMACION`, `CONTRATO` en `True`;
  `RAE` (obligatorio pero sin caducidad, verbatim) y `MANDATO` (dura
  hasta revocación expresa, no hasta fecha fija) confirmados en
  `False`. `AUTORIZACION_USO_MAQUINARIA`/`ESTIBA_PLATAFORMAS` quedan
  pendientes — cero archivos reales en todo el corpus con ese código,
  nada que auditar todavía.

**Incidente real de producción, diagnosticado y resuelto en la misma
sesión (directriz 4.13, nueva, ver documento maestro):** 71 commits
existiendo solo en el servidor y no en GitHub, origen en un commit
huérfano de S040 (`10bc93e`, nunca empujado) que causó un merge
automático en cada despliegue desde entonces. Resuelto con un único
`git push origin main` ejecutado directamente en el servidor
(fast-forward limpio). Documentado en el documento maestro para que
ninguna sesión futura tenga que reinvestigarlo.

**Bug real de producción cometido y corregido en la misma sesión**:
el commit de la migración 0018 rompió la importación de `models.py`
(`NameError`: `DocumentTypeCatalog` referenciada directamente antes de
su propia definición, más abajo en el archivo) — tumbaba `manage.py`
y previsiblemente la web app completa. `py_compile` no lo detectó
(solo sintaxis, no ejecución). Corregido de inmediato con referencia
por cadena, mismo patrón ya usado en `deleted_by`/`purged_by` del
propio modelo, y verificado con `manage.py check` real contra el
servidor tras el fix.

**Incidencia de sesión, sin impacto en el resultado**: el token de
GitHub caducó/se revocó a mitad de sesión (API y git devolvían `401`)
con todo el trabajo ya empujado a GitHub — solo bloqueó el propio
cierre (PCS), resuelto con un token nuevo.

### Hoja de Ruta para la Siguiente Sesión

1. **Enganchar `vigencia_service.evaluate_substitution()` a la
   clasificación H29** — bloque grande, con la base de datos ya lista
   desde esta sesión (`document_type`/`expiry_date`/`issue_date` en
   `DocumentIndexEntry`, `tracks_expiry` en `DocumentTypeCatalog`,
   `SubjectDocumentReference` poblado). Queda por delante:
   - **Verificación online obligatoria** de la API de Gemini
     (directriz crítica) antes de tocar el prompt/`response_schema` —
     no se ha comprobado en meses.
   - Ampliar el prompt/schema de `classification_service.py` para que
     extraiga `expiry_date`/`issue_date` **solo** cuando
     `document_type.tracks_expiry` sea `True` — acotado, por decisión
     explícita de Miguel Ángel, a un recorrido dirigido solo sobre
     `DOC. MAQUINAS`/`DOC. PERSONAL` (no todo el corpus), y solo sobre
     los tipos documentales que ya sabemos que llevan fecha — nunca
     releer manuales ni el resto de tipos sin fecha.
   - El hook real: al clasificar un documento de un tipo con
     `tracks_expiry=True`, llamar a `evaluate_substitution()` contra
     los `DocumentIndexEntry` del mismo tipo y el mismo sujeto (vía
     `SubjectDocumentReference`), actualizar `current_entry` y
     registrar en `DocumentSubstitutionLog` (sin cambios de esquema,
     ya genérico).
2. **Cerrar `tracks_expiry` para los dos tipos pendientes** en cuanto
   aparezca un archivo real que auditar: `AUTORIZACION_USO_MAQUINARIA`
   y `ESTIBA_PLATAFORMAS`. Criterio de cierre: al menos una muestra
   real localizada en el índice con ese código exacto en el nombre.
3. **Resolver `D012`, `MK140` y `V1`("URA 376 & 506")** — no
   resolvieron ni por código ni por modelo contra `fleet.MachineAsset`
   ni contra el listado completo de maquinaria aportado en S45.
   Criterio de cierre: Miguel Ángel identifica de qué máquina son (o
   confirma que no pertenecen a Grupo Álvarez / son de otra empresa
   del grupo no cubierta por este `fleet`), o se descartan
   explícitamente.
4. **Mover el `.rar` de A56 mal ubicado** (`A-56 MANUAL USO
   bal_27000-07-10 LTM 1230-5.1 manual.rar`, pertenece a A59 por el
   propio contenido del nombre — LTM 1230-5.1 es el modelo de A59, no
   el de A56) — detectado en S45, deliberadamente no tocado en la
   papelera de hoy porque es un "mover" (4.12), no un "borrar".
5. **Análisis de cobertura por familia de maquinaria** (arrastrado de
   S44, sin ejecución real en S45): para cada familia real
   (`fleet.MachineAsset.family`), determinar huecos reales de manual,
   incorporando ya los hallazgos de S45 (A22/A41 fuera por venta, A43
   hueco real activo, U9 ausente del índice). Criterio de cierre:
   lista final de huecos reales, filtrada por familia.
6. **Revisar el resto de los archivos sin código** (agrupados por
   marca) contra la lista de huecos reales del punto 5.
7. **DECA (nuevo, S45)** — documento electrónico de control
   administrativo, obligatorio en transporte de mercancías por
   carretera desde el 5 de octubre de 2026 (Resolución de 5 de junio
   de 2026, DGTCF). Miguel Ángel plantea generación/modificación
   programática (PyMuPDF, sin licencia Adobe) con formulario para que
   el chófer actualice datos en obra. Sin alcance definido todavía —
   valorar si es ampliación de H30 o hito propio antes de empezar a
   construir nada. Requiere tipo documental nuevo en
   `DocumentTypeCatalog` cuando se aborde.

