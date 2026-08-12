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

### COMPLETADAS EN S46

**Objetivo de H30 ampliado de forma sustancial (decisión explícita de
Miguel Ángel, esta sesión).** Deja de ser solo "vincular documentos
existentes a su máquina/trabajador" y pasa a ser: dejar el **panel de
documentación funcional y usable de verdad**, con tres pestañas
propias — **Centros de Gasto**, **Personal**, **EPIs** — desde donde
se hace toda subida/baja/consulta real. Los supervisores de
documentación tienen lectura sobre `_CUARENTENA`/`NO CONFORMES` **más
la escritura específica de anotar (`curator_note`) y reencolar desde
ahí** (sin eso, todo lo no conforme se queda parado para siempre) —
pero cualquier otra escritura/cambio pasa exclusivamente por las tres
pestañas, nunca directamente sobre el explorador de archivos.

**Bug real corregido en la misma sesión (directriz 4.9):**
`resolve_or_create_machine_asset()`/`resolve_machine_asset()` solo
miraban `entry.parent_path` (la carpeta) para encontrar el código de
flota o la matrícula — nunca consultaban `machine_code_hint` (lo que
Gemini extrae del propio contenido del documento) ni la
`curator_note`. Un archivo reencolado desde NO CONFORMES que vivía en
la raíz del cubo (sin subcarpeta) nunca podía resolver, por muchos
datos reales que Gemini extrajera o que el curador anotara. Corregido
con un tercer intento vía `machine_code_hint` (commit `dc44408`) —
verificado en caliente contra un caso real (`P-26KHG CERTIF.
MANTENIMIENTO`, id 42325): tras el fix, reencolado y resuelto
correctamente contra el `MachineAsset` real de P-26.

**Caso real de personal, mismo reencolado (id 42340):** una "tarjeta
del conductor" sin DNI impreso no pudo resolver por identidad hasta
que Miguel Ángel dejó `curator_note` con el DNI — funcionamiento
correcto según el diseño ya existente (H29, decisión 3.14 ampliada),
no un bug. Gemini clasificó el resultado como `TACOGRAFO`, no
`CARNET_CONDUCIR` como se había asumido inicialmente por el nombre del
histórico — corregido sobre la marcha con el dato real.

**Diseño cerrado para extracción de fechas (`expiry_date`/
`issue_date`), tras plantear dos alternativas y que Miguel Ángel
confirmara la definitiva:** `DocumentTypeCatalog.tracks_expiry=True`
es la PUERTA para que Gemini intente leer una fecha si el documento la
muestra — nunca la obligación de que el 100% de los documentos del
tipo la lleven. Es cada documento, no el tipo, el que decide (vía
Gemini) si rellena `expiry_date_hint` (caducidad real) o
`issue_date_hint` (solo emisión/recencia) o ninguno de los dos — mismo
mecanismo ya usado por `vigencia_service.is_current()` para "sin
ninguna fecha = vigente por defecto". Confirmado explícitamente
también para `TACOGRAFO` (tarjeta de tacógrafo, vigencia legal fija de
5 años, sin DNI impreso) → `tracks_expiry=True` (migración `0020`).

**Nuevo tipo documental `ALTA_MEDICA`** (migración `0021`) — confirmado
por Miguel Ángel como tipo propio, distinto de `ALTA` (Seguridad
Social) y sin relación con "EPIS ALTA VISIBILIDAD" (ver hallazgo de
falsos positivos abajo).

**Hallazgo real crítico para el diseño del recorrido heurístico:**
`icontains` sin límite de palabra produce falsos positivos serios —
`RAE` casaba dentro de "ISRAEL", `OCA` dentro de "OCAÑA", `CAP` dentro
de "INCAPACIDAD"/"CAPACITACION". Corregido con coincidencia de palabra
completa (`\b`). Verificado contra el corpus real completo: **16.031
archivos bajo `DOC. MAQUINAS` y 21.519 bajo `DOC. PERSONAL` — 0% con
`document_type` asignado todavía** (el enganche real, más allá de las
migraciones de catálogo, sigue sin construirse).

**Decisión estratégica de coste, explícita y central para todo lo que
sigue:** nunca otra pasada masiva de clasificación por Gemini (la
anterior costó ≈300€). El recorrido de `DOC. MAQUINAS`/`DOC. PERSONAL`
se ataca en dos fases: **Fase A, gratis** — enganchar cada documento a
su máquina/trabajador (creando la ficha si no existe, mismo mecanismo
ya usado en cuarentena) y adivinar el tipo documental por heurística de
nombre de archivo, sin abrir ningún documento. **Fase B, barata** —
solo para los documentos ya enganchados a un tipo con
`tracks_expiry=True` sin fecha detectable por heurística: **OCR local
con Tesseract** (confirmado instalado en el servidor, versión 4.1.1,
sin coste de API) antes que Gemini; Gemini queda como último recurso,
acotado al mínimo posible.

**EPIs — alcance real mucho mayor de lo esperado, confirmado con
muestra de contenido real (35 archivos `.doc`/`.docx`, texto nativo
vía `_convert_to_pdf`/`python-docx`, nunca OCR para esta muestra por
fiabilidad):** al menos dos plantillas distintas a lo largo de los
años, vocabulario mucho más amplio que "prendas básicas" (máscara de
soldar, guantes de acción química, ropa de señalización de alta
visibilidad, ropa con arco eléctrico, equipos de rescate en carretera),
y un subconjunto (arneses, elementos de amarre) que **no es una
entrega puntual sino una revisión periódica** con plantilla propia
(`OPTIMO`/`DETERIORADO`/`CADUCADO`) — necesita historial de
revisiones, no solo fecha de entrega. Decisión de arquitectura para
EPIs, confirmada por Miguel Ángel: catálogo cerrado de EPIs
(`EpiItemCatalog`) agrupado por familia, con CRUD propio y opción
"nuevo EPI" accesible desde el propio desplegable de entrega (nunca
hay que salir del formulario para dar de alta un EPI nuevo); tabla de
entregas (`EpiDelivery`) y tabla de revisiones aparte para los EPIs
con vida útil.

**Otras decisiones confirmadas esta sesión, pendientes de construir:**
- Todos los CRUD del panel de documentación (Personal, Centros de
  Gasto, EPIs, tipos documentales) llevan ordenación ascendente/
  descendente y filtro por cada columna — estándar explícito, no
  opcional.
- El alta de trabajador/máquina para poder entregarle un EPI se hace
  siempre desde su propia pestaña (Personal/Centros de Gasto), nunca
  como atajo dentro del formulario de EPIs.
- El alta de un tipo documental nuevo (hoy solo disponible desde el
  Catálogo de tipos del explorador de archivos) tiene que estar
  también accesible desde el propio flujo de subida del panel de
  documentación, para cuando el supervisor no encuentre el tipo en el
  desplegable.
- **Vacaciones (H24)** se controlará también desde este panel, pero
  Miguel Ángel deja el diseño explícitamente abierto — no cerrar nada
  de esto por interpretación propia.
- Detectado, sin resolver: falta un tipo documental para el
  "justificante de asistencia a un organismo público" (Hacienda,
  Seguridad Social...) que un trabajador necesita para trámites
  personales — llegará vía partes de trabajo (fotos). Confirmado
  contra el catálogo completo (57 tipos ya existentes): no hay ningún
  código que lo cubra hoy. No se da de alta todavía — falta decidir
  código/etiqueta exacta y el punto real de entrada en partes de
  trabajo.

**Incidencia propia, corregida en la misma sesión:** una consulta
inicial mía para localizar los dos casos de NO CONFORMES filtraba por
`NO_CONFORMES_PREFIX` (`"NO CONFORMES/"`, con barra) contra
`parent_path` (que vale `"NO CONFORMES"`, sin barra) — no encontró
nada y generó una falsa sospecha de entorno equivocado. Corregido en
la siguiente consulta, sin impacto real más allá de la confusión
momentánea.

### COMPLETADAS EN S47

**1. Análisis de cobertura de manuales por familia de maquinaria —
CERRADO.** Llevaba dos sesiones seguidas (S44, S45) sin ejecución
real y S46 tampoco lo tocó (2.ª sesión sin avanzar, regla 2.2 —
convertido en pregunta abierta al cierre de S46, respondida hoy).
Consulta real contra `fleet.MachineAsset`/`SubjectDocumentReference`
(525 máquinas totales), depurada en varias rondas con Miguel Ángel
hasta un número limpio y auditado:

- 106 filas de centros de gasto/administrativo confirmadas fuera
  (TURISMOS, ADM, DEPENDENCIAS, HUELVA, LOGÍSTICA, PERSONAL, BEN,
  E.M., S/TM, VARIOS).
- Familia `REMOLQUE` (44) confirmada excluida entera — no necesita
  manual.
- Familia `TTE.` (20) confirmada como maquinaria real (cabezas
  tractoras + 1 góndola, verificado con `type_code`/`plate` reales,
  no centro de coste) — entra al backlog.
- Familia `S/F` (11) y 3 filas sueltas de `(SIN FAMILIA)` confirmadas
  como ruido de catálogo puro (`type_code='S/TM'`, sin marca) —
  excluidas.
- 9 altas nuevas de S043 (`A68`, `H10`, `H11`, `S16`, `S17`, `V10`,
  `Z135`, `Z136`, `Z138`, `G17`, `G18`) excluidas del cálculo hasta
  que se les rellene `family` real — no clasificables todavía.
- **Corrección real de datos** (directriz 4.9, detectada en la propia
  sesión): `A22` y `A41`, confirmadas vendidas en S45 pero seguían
  `is_active=True` en producción — corregidas a `is_active=False`.
- `EMPRESA_ALMACEN_MECANICO`/`EMPRESA_TALLER_MECANICO`/
  `EMPRESA_ALMACEN_ELEVACION`/`EMPRESA_TALLER_ELEVACION` (centros de
  gasto genéricos colados dentro de MOVILES/PLATAFOR) excluidas.
- **Total definitivo: 231 huecos reales** de maquinaria activa sin
  manual vigente (PLATAFOR 108, CARR 32, MOVILES 23, TTE. 20, CADENAS
  19, AUTOCARG 15, ASISTENC 12, ELEM 1, VENTOSA 1). Confirmado además
  que el backfill de S45 (78 `SubjectDocumentReference`, incluidos los
  22 emparejamientos JLG) sigue íntegro y correctamente reflejado —
  no había trabajo duplicado ni perdido, solo la duda de Miguel Ángel
  sobre en qué sesión se hizo.
- Criterio de cierre confirmado por Miguel Ángel: no se persigue
  máquina a máquina en este hito — los 231 huecos se irán resolviendo
  según aparezcan a través de la propia interfaz del panel de
  documentación (punto 4 de la hoja de ruta de abajo).
- De paso, resuelto definitivamente el punto "D012/MK140/V1" de la
  hoja de ruta arrastrada desde S45: confirmado con variantes
  (`D-012`, `UNICARRIERS`, `MK-140`, `URA`) que no existen en
  `fleet.MachineAsset` bajo ningún código ni modelo — descartados para
  siempre, no se vuelven a buscar.

**2. Modelo de datos de EPIs desplegado** (commit `03a3f2a`) —
`EpiItemCatalog` (familia, código, etiqueta,
`requires_periodic_review`, activo), `EpiDelivery` (persona, EPI,
fecha de entrega, `source_entry` nullable a `DocumentIndexEntry`,
`extraction_method` MANUAL/HEURISTIC/OCR/GEMINI, confianza), y
`EpiReview` (entrega, fecha de revisión, estado
`OPTIMAL`/`DETERIORATED`/`EXPIRED` — identificadores en inglés con
etiqueta en español, corrección explícita de Miguel Ángel sobre la
regla de oro del idioma, mismo patrón que
`DocumentTypeCatalog.DOMAIN_CHOICES`). Migración 0022 escrita a mano
en el mismo commit (`com-migrations` sección 1).

**3. Diccionario heurístico (Fase A) — verificado contra corpus real**
(16.031 archivos en DOC. MAQUINAS + 21.519 en DOC. PERSONAL). De los
35 tipos sin probar en S46, se generaron candidatos por tipo y se
verificaron con coincidencia de palabra completa (`\b`, ya validado
en S46) contra nombres reales:

- 4 solapes reales resueltos con prioridad explícita de Miguel Ángel:
  `DESGUACE` → gana `DOC_BAJA_DEFINITIVA` sobre `BAJA_DEFINITIVA`;
  `CUOTA`/`RECIBO` + `LEASING` → gana `RECIBO_LEASING` sobre
  `LEASING`; `CURSO` se mantiene tipo propio, distinto de
  `ENTREGA_INFORMACION`; `PROFORMA` gana siempre sobre `DOC_VENTA`
  (una proforma nunca formaliza una venta, aunque el nombre del
  archivo mencione "VENTA" — confirmado con contexto de negocio real:
  las proformas se usan también para subvenciones sin compra
  posterior).
- **Falso positivo real detectado y corregido**: "BAJA TENSION"
  (formación eléctrica) casaba con la palabra clave `BAJA` de
  `BAJA_PERSONAL` — excluido del patrón.
- **Hallazgo real que amplía el catálogo**: los 559 candidatos de
  `BAJA_PERSONAL` mezclaban tres conceptos distintos por carpeta real
  (`PERSONAL/BAJAS/` = baja en Seguridad Social;
  `PERSONAL/PARTES BAJA ENF.COMUN Y ACC.NO LABORAL/` = parte médico;
  `INVESTIGACION ACCIDENTES/CON BAJA|SIN BAJA/` = investigación de
  accidente laboral). Miguel Ángel confirmó que no pueden ir en el
  mismo tipo — dos tipos documentales nuevos dados de alta:
  `PARTE_BAJA_MEDICA` e `INVESTIGACION_ACCIDENTE` (commit `c21fdbd`,
  migración 0023, mismo patrón que `0021_seed_alta_medica.py`).
- 4 tipos sin ninguna coincidencia real con las palabras probadas
  (`CERT_NO_TARJ_TTES`, `JUSTIFICANTE_TRANSFERENCIA`,
  `PAGO_CORRIENTE`, `RECIBO_SENAL_COMPRA`) — Miguel Ángel aportó
  contexto de negocio sobre qué son (p. ej. `CERT_NO_TARJ_TTES` aplica
  a vehículos de asistencia) pero ninguna palabra clave nueva
  verificable — quedan pendientes de muestra real o palabra clave
  concreta.

### COMPLETADAS EN S48

**Gap real detectado al empezar la Fase A:** el "diccionario
heurístico" narrado en S46/S47 nunca quedó persistido como código —
vivía solo en consultas puntuales de esas sesiones. Se reconstruyó
desde cero contra el catálogo real (`DocumentTypeCatalog`, 59 tipos
activos) y se verificó con datos reales del corpus, nunca de memoria.
Artefacto real: `document_explorer/management/commands/
calibrate_fase_a_keywords.py` — comando de solo lectura, no escribe
nada, reutilizable para recalibrar en el futuro si el catálogo cambia.

**Incidencia real de sesión, reconocida explícitamente:** en la
primera pasada de resultados se propusieron preguntas de prioridad
para casos que Miguel Ángel ya había resuelto en sesiones anteriores
(EPIs) o que ya se explican por un principio general ya vigente en el
proyecto (dosieres = documentos distintos escaneados juntos, van a
papelera). Corregido en la misma sesión tras la corrección de Miguel
Ángel — de ahí que este framework quede registrado aquí con todo el
detalle, para que no se vuelva a perder entre sesiones.

**EPIS retirado de los candidatos de Fase A.** Los documentos de EPI
se consumen hacia `EpiDelivery`/`EpiReview` (modelo de S47), nunca se
clasifican como `document_type=EPIS` por este recorrido — flujo
distinto. Además, mantenerlo habría escondido un falso positivo real:
"EPIS ALTA VISIBILIDAD" (ropa de señalización) coincidía con el
candidato `ALTA` sin ser un alta de Seguridad Social.

**Falso positivo real corregido:** `ALTA` excluye ahora la frase "ALTA
VISIBILIDAD" (mismo patrón que la exclusión de "BAJA TENSIÓN" de
`BAJA_PERSONAL` en S46). Verificado que sin esta exclusión, 151
archivos de EPIs de alta visibilidad habrían quedado mal clasificados
como `ALTA`.

**Framework de prioridades cerrado con datos reales (S48), aplica a
la Fase A completa:**

*Reglas de S47, confirmadas de nuevo con datos reales:*
- `DESGUACE` → gana `DOC_BAJA_DEFINITIVA` sobre `BAJA_DEFINITIVA` (5
  archivos reales).
- `PROFORMA` → gana siempre sobre `DOC_VENTA` (3 archivos reales).

*Reglas nuevas, confirmadas por Miguel Ángel en S48:*
- `CONTRATO_COMPRAVENTA` → gana sobre `DOC_VENTA`.
- `ITV` → gana sobre `FICHA_TECNICA` cuando es un documento único (el
  propio catálogo ya dice que ITV incluye la ficha técnica) — 548
  archivos reales, el solape de mayor volumen de todos.
- `PERMISO_CIRCULACION` → gana sobre `DOC_VENTA`/`FICHA_TECNICA`
  cuando es un documento único (no un dosier real).
- Cualquier tipo específico → gana siempre sobre
  `SOLICITUD_ADMINISTRATIVA` cuando ambos coinciden en el mismo
  archivo (aplicado a `BAJA_DEFINITIVA`, `DECLARACION_HOMOLOGACION`,
  `ITV`, `LEASING`/`RECIBO_LEASING` frente a `SOLICITUD_ADMINISTRATIVA`).
- `RECIBO_LEASING` → gana sobre `LEASING` (regla de S47, re-confirmada
  con 9 archivos reales: "ULTIMA CUOTA LEASING", "ULTIMO RECIBO
  LEASING").
- `ALTA_MEDICA` → gana sobre `ALTA` (18 archivos reales, mismo patrón
  de especificidad).

*Regla de DOSIERES, aplicada por primera vez a la Fase A (principio ya
vigente en el proyecto — documentos distintos escaneados juntos se
presumen existentes por separado y el combinado va a papelera, mismo
mecanismo que `trash_dossier_entry()`):*
- `FICHA_TECNICA` + `PERMISO_CIRCULACION` (4 archivos: "Ficha Técnica,
  Permiso Circulación y CE...") → DOSIER.
- `CARNET_CONDUCIR` + `DNI` (12 archivos: "DNI +CARNE CONDUCIR
  COLOR.pdf") → DOSIER.
- `CARNET_CONDUCIR` + `TACOGRAFO` (2 archivos: "CARNE CONDUCIR,CAP,
  TARJ.TACOGRAFO, Y CARNE OP.MAQ.VARIAS...") → DOSIER.

*Falso positivo nuevo, mismo patrón que "alta EPIS":* `CURSO` ↔
`TACOGRAFO` (2 archivos: "CURSO TACOGRAFO DIGITAL...") son formación
sobre el tacógrafo, no el propio tacógrafo — gana `CURSO`.

**Los tres puntos pendientes — CONFIRMADOS por Miguel Ángel en S48, ya
no son propuesta, son regla definitiva:**
- `ALTA` ↔ `SEG_SOCIAL` → gana `ALTA`.
- `CURSO` ↔ `FORMACION` → gana `FORMACION` cuando hay patrón de horas,
  si no `CURSO`.
- `ITV` ↔ `TACOGRAFO` → DOSIER.

**Restan sin cerrar, volumen mínimo (1-2 archivos), sin propuesta
todavía:** `ENTREGA_INFORMACION` ↔ `FORMACION`, `DNI` ↔ `FORMACION`.
No bloquean el resto de la Fase A — se dejan sin `document_type`
asignado hasta que aparezcan más muestras o Miguel Ángel decida.

**Acrónimos de riesgo (`CE`, `IPO`, `ITC`, `OCA`, `RAE`, `CAP`, `CSS`,
`IDC`) — verificados contra ejemplos reales, sin falsos positivos
visibles en las muestras (a diferencia de S46, donde `OCA`/`CAP` sí
los tenían antes del límite de palabra completa). Confirmados como
seguros para escritura en bulk (S48).

**Resolución de `domain_object` en Fase A — diseño cerrado (S48):**
- **`MACHINE`**: `resolve_or_create_machine_asset()` (ya existe,
  `document_explorer/classification_service.py`) funciona por carpeta
  (código de flota o matrícula en `parent_path`), sin depender de
  Gemini — reutilizable tal cual, sin tocarlo.
- **`PERSONAL`**: `resolve_or_create_person_identity()` NO sirve aquí
  — exige `dni_hint`, que solo existe si Gemini ha leído el contenido
  del documento, y la Fase A por diseño (S46) no abre ningún
  documento. Se resuelve en su lugar contra `PersonIdentity.folder_path`
  (ya sembrado por DNI en su momento, dato real verificado): un
  archivo `PERSONAL` se asigna a la `PersonIdentity` cuyo `folder_path`
  coincide con `entry.parent_path` o lo contiene. Sin coincidencia →
  se queda sin resolver, nunca se crea una identidad nueva por esta
  vía (crear sigue exigiendo DNI real, eso no cambia).
- **AMPLIACIÓN EXPLÍCITA de Fase B, para que no se vuelva a perder
  entre sesiones (queja de Miguel Ángel en S48, PCS no lo capturaba
  bien):** los archivos `PERSONAL` que la Fase A NO resuelva por
  `folder_path` (sueltos en raíz, mal ubicados) no quedan huérfanos en
  silencio — pasan a la cola de Fase B para que el OCR local con
  Tesseract (ya decidido en S46 que va siempre antes que cualquier
  llamada a Gemini) intente leer el DNI del propio contenido y
  resolver la identidad por esa vía. Fase B deja de ser solo
  "fechas de caducidad sin heurística de nombre" — también resuelve
  identidad de personal sin carpeta reconocible.

- **AMPLIACIÓN EXPLÍCITA de Fase B, para que no se vuelva a perder
  entre sesiones (queja de Miguel Ángel en S48, PCS no lo capturaba
  bien):** los archivos `PERSONAL` que la Fase A NO resuelva por
  `folder_path` (sueltos en raíz, mal ubicados) no quedan huérfanos en
  silencio — pasan a la cola de Fase B para que el OCR local con
  Tesseract (ya decidido en S46 que va siempre antes que cualquier
  llamada a Gemini) intente leer el DNI del propio contenido y
  resolver la identidad por esa vía. Fase B deja de ser solo
  "fechas de caducidad sin heurística de nombre" — también resuelve
  identidad de personal sin carpeta reconocible.

**Resultado real del dry-run de `run_fase_a_sweep` (S48), sobre 14.469
candidatos `MACHINE` + candidatos `PERSONAL`:** 9.057 archivos con
tipo y dominio resueltos sin ambigüedad, 10 dosieres reales detectados
(papelera), 21.609 sin ningún tipo por palabra clave (línea base de
partida era 0% en S47, esperado — el diccionario cubre ~50 tipos con
frases concretas), 3.213 con tipo resuelto pero dominio SIN resolver.

**DECISIÓN DEFINITIVA de Miguel Ángel (S48) — personal de baja, FUERA
DE ALCANCE PARA SIEMPRE, no solo para esta sesión:** la inmensa
mayoría de esos 3.213 son archivos bajo carpetas `BAJAS/` (personal ya
no activo) — `PersonIdentity` solo tiene 70 filas, sembradas contra el
Excel de plantilla **activa** (S43), así que un trabajador de baja
nunca tiene fila `PersonIdentity` y nunca podrá resolver por este
mecanismo. Miguel Ángel confirma, verbatim: *"El personal de baja lo
vamos a dejar estar. No vamos a contar con él [...] Son datos que no
vamos a meter en ninguna base de datos [...] para no ensuciar nuestra
base de datos. Comenzamos con una base de datos limpia, sin incluir al
personal que ya está dado de baja."* Consecuencia de obligado
cumplimiento: **nunca** crear `PersonIdentity` para personal de baja,
ni en Fase A, ni en Fase B (OCR), ni en ninguna fase futura — el
histórico se queda en los archivos (GCS, nunca tocado, 4.12) pero no
entra en la base de datos limpia. Los archivos de personal de baja se
quedan sin `domain_object` para siempre, por diseño, no por
limitación técnica pendiente de resolver.

**APLICADO Y VERIFICADO en producción (S48).** `run_fase_a_sweep
--apply` ejecutado; resultado verificado con consulta real a la base
de datos, nunca fiándose solo de la salida del propio comando:
`DocumentIndexEntry.objects.filter(document_type__isnull=False,
deleted_at__isnull=True).count()` = **9.057**, y de esos, exactamente
**9.057** también con `domain_object_id` resuelto (sin huecos entre
tipo y dominio). **10** archivos en papelera con fecha de hoy (los
dosieres detectados, ni uno más ni uno menos). Ejemplo real verificado:
`P-07 PRESTAMO.pdf` → `document_type=PRESTAMO`, `domain_object_id=486`.
Los 3.213 de personal de baja y los 21.609 sin tipo por palabra clave
quedan exactamente como estaban — no se tocó nada de ellos, confirmado
por diseño (ver decisión de Miguel Ángel sobre personal de baja,
arriba).

**Punto 1 de la hoja de ruta de S47 ("Construir el comando de
recorrido dirigido") — CERRADO.** Criterio de cierre original ("
`document_type__isnull=False` sobre una proporción alta y medida del
corpus, línea base 0% de 37.550") cumplido: 9.057 archivos reales
resueltos en la primera pasada.

**2.ª pasada, punto 2 de la hoja de ruta de S47 ("cerrar los 4 tipos
sin palabra clave verificada") — CERRADO.** Bug real detectado y
corregido: `\b` (límite de palabra estándar) trata `_` como carácter
de palabra, así que nunca detectaba un candidato pegado entre guiones
bajos (p. ej. `CERT_NO_TARJ_TTES` dentro de
`A29_CERT_NO_TARJ_TTES_20230314` — verificado con datos reales que
fallaba). Corregido con un lookaround que solo trata `[A-Z0-9]` como
carácter de palabra (`_build_pattern` en `calibrate_fase_a_keywords`,
reutilizado por `run_fase_a_sweep`). Los 3 tipos con código literal en
el nombre (esquema `{CÓDIGO_MÁQUINA}_{TIPO}_{FECHA}` de una pasada
Gemini anterior, nunca reflejado en `document_type` hasta ahora) se
verificaron y aplicaron: `CERT_NO_TARJ_TTES` (2), `JUSTIFICANTE_
TRANSFERENCIA` (1), `RECIBO_SENAL_COMPRA` (1).

**`PAGO_CORRIENTE` — DECISIÓN DEFINITIVA de Miguel Ángel (S48), mismo
patrón que DECA: es un tipo de "servicios", no de personal ni de
máquina, fuera de alcance hasta que exista ese modelo.** La palabra
clave "PAGO CORRIENTE" sí encontró 832 archivos reales, pero viven
todos bajo `DECLARACION AL CORRIENTE/DECLARACION POR OBRAS/{empresa}/`
— una declaración de estar al corriente de pago que la empresa emite
por OBRA, incluyendo normalmente a varios trabajadores a la vez, nunca
ligada a una sola persona. Miguel Ángel, verbatim: *"Es un documento
que la empresa entrega de que está al corriente del pago de los
trabajadores, y normalmente van incluidos varios en ese documento y va
por obras. Así que esto tendría que ir también puesto en servicios
[...] no vamos a meter esos documentos ni en personal ni en
maquinaria."* Consecuencia: `run_fase_a_sweep` nunca fuerza un
`domain_object` de `PersonIdentity` para `PAGO_CORRIENTE` (ya era el
comportamiento real por la propia lógica de "solo escribe
`document_type` si también resuelve dominio" — sin ningún archivo mal
asignado que corregir), y el campo se queda vacío por diseño hasta que
exista el modelo de servicios (mismo horizonte que DECA, ver más
arriba).

**Resultado real de la 2.ª pasada, verificado con consulta directa a
producción:** 476 archivos nuevos resueltos (tipo + dominio), 0
dosieres nuevos. Total acumulado con `document_type` real: **9.533**
(9.057 + 476, verificado con `DocumentIndexEntry.objects.filter(
document_type__isnull=False, deleted_at__isnull=True).count()`).

**Punto 3 de la hoja de ruta de S47 ("cerrar `tracks_expiry` para
`AUTORIZACION_USO_MAQUINARIA`/`ESTIBA_PLATAFORMAS`") — CERRADO.**
Muestra real encontrada: `AUTORIZACION_USO_MAQUINARIA` tiene 6
documentos del mismo trabajador (Gómez García, José Antonio) con
fechas distintas a lo largo de varios años (2021-2026) — se renueva
periódicamente, `tracks_expiry=True` confirmado y aplicado y
verificado (`ANTES: False` → `DESPUES: True`). `ESTIBA_PLATAFORMAS`
solo tiene 4 archivos reales en total, uno por persona, sin ninguna
fecha repetida para la misma persona — sin evidencia de renovación,
`tracks_expiry=False` confirmado (sin cambio, ya estaba así).
Revisable si aparece muestra real que lo contradiga en el futuro.

**Bug real detectado y corregido (S48): `run_fase_a_sweep` nunca
aplicaba `SEGURO`/`TACOGRAFO`/`MANDATO`.** Estos tres tipos viven bajo
la clave `"BOTH"` del diccionario de candidatos (aplican a `MACHINE` y
`PERSONAL` por igual), pero el bucle principal del comando solo
recorría `domain in ("MACHINE", "PERSONAL")` — la clave `"BOTH"`
nunca se comprobaba, así que estos tres tipos tenían 0 archivos
asignados pese a que la calibración ya había verificado coincidencias
reales sólidas (`SEGURO`: 1.347, `TACOGRAFO`: 199, `MANDATO`: 47). El
propio comando de calibración (`calibrate_fase_a_keywords`) sí
recorría `BOTH` correctamente (por eso los solapes `ITV↔TACOGRAFO`,
`CURSO↔TACOGRAFO`, `CARNET_CONDUCIR↔TACOGRAFO` ya estaban cubiertos en
el framework de prioridades) — el fallo estaba solo en la aplicación
real. Corregido en `_match_candidates()` para comprobar siempre
`(domain, "BOTH")`. Aplicado y verificado con datos reales:
`SEGURO`: 1.393, `TACOGRAFO`: 184, `MANDATO`: 39 (suma 1.616, exacta).
Total acumulado con `document_type` real: **11.149**.

**Fase B1 (OCR) — en curso, hallazgo real importante (S48).** Comando
`run_fase_b1_ocr_dates` construido y probado contra muestra real.
Funciona bien contra documentos impresos con texto nativo/legible
(verificado: `SEGURO`, recibo con período de vigencia, resolvió
`expiry_date` correcto por contexto real — "VALIDEZ DE RECIBO...
31/12/2016 - 31/12/2017"). **No funciona, y no es un bug corregible,
contra tarjetas ITV manuscritas antiguas** (verificado visualmente por
Miguel Ángel sobre 4 archivos reales, `P-07 2728-BJB`): la marca de
fondo "ESPAÑA" repetida de la propia tarjeta oficial domina la lectura
de Tesseract frente a las fechas manuscritas a bolígrafo — ni subir a
300 dpi ni ningún ajuste de contexto lo arregla, es un límite real del
motor de OCR contra manuscrito con fondo de seguridad. **Este
subconjunto queda como cola real para Gemini (último recurso, acotado
al mínimo, tal como preveía el diseño original de S46)** — nunca se ha
intentado forzar más OCR sobre ellos, ni se ha llamado a Gemini
todavía en esta sesión.

### Punto 5 (S48, misma sesión) — Panel de documentación H30

**Decisión definitiva de Miguel Ángel:** sustituir por completo el
panel legado (`panel/views_documentation.py`, sobre
`MachineDocument`/`PersonalDocument`, 30/39 filas residuales) — nunca
mantener las dos versiones en paralelo. Ejecutado en la misma sesión:
`panel/documentacion/` es ya la interfaz real, integrada en la barra
lateral, el archivo legado y sus 30+ endpoints (alertas, dossier,
plantillas de email, diccionario aprendido, transferencia entre
máquinas) **eliminados** — sin uso real confirmado antes de borrar.

**Construido y desplegado:**
- `DocumentTypeCatalog.ocr_unreliable` y `DocumentIndexEntry.
  is_obsolete` (migración `0024`).
- `document_explorer.date_verification_service` — extracción de fecha
  compartida (OCR con contexto expiry/issue, o Gemini acotado a tipos
  `ocr_unreliable=True`, hoy solo `ITV`).
- `document_explorer.subject_upload_service` — subida real desde
  ficha: el supervisor elige tipo + escribe fecha, el sistema
  contrasta contra el propio documento (aviso visual si no coincide,
  nunca decide por encima del supervisor) y aplica
  `evaluate_substitution()` marcando `is_obsolete` en los documentos
  sustituidos — nunca mueve ni borra el archivo real (4.12).
- Tres pestañas (Centros de Gasto, Personal, EPIs) contra
  `DocumentIndexEntry`, con orden asc/desc y filtro de búsqueda.
- Cada documento con sus propios botones **Ver / Actualizar /
  Eliminar** en su fila (corrección real tras primera versión
  rechazada por Miguel Ángel — "un botón por tipo" no es el diseño
  correcto). Subida de varios archivos a la vez del mismo tipo en un
  único formulario.
- Acordeón Vigentes (abierto)/Histórico (cerrado) en cada ficha.
- **Bug de datos real, corregido:** 1.172 grupos (mismo tipo+sujeto)
  con más de un documento "vigente" a la vez — los 11.000+ documentos
  de la Fase A nunca pasaron por `evaluate_substitution()` (solo la
  subida desde ficha lo aplica). `backfill_obsolete_duplicates`
  (dry-run confirmado, aplicado y verificado): 8.566 documentos
  marcados `is_obsolete=True` con el mismo criterio real de
  `vigencia_service` cuando hay fecha, y "el más reciente indexado"
  cuando no hay ninguna fecha para desempatar. Quedan 102 grupos con
  más de un vigente — comportamiento correcto, no un fallo (mismo
  tipo con fechas de periodos distintos, p. ej. recibos de `SEGURO`
  trimestrales, ya documentado así en `vigencia_service`).

**Pendiente real, todavía sin cerrar:**
- Modelo de permisos de supervisor (lectura cuarentena/NO CONFORMES +
  escritura de anotación/reencolado + escritura completa solo vía las
  tres pestañas) — no construido todavía.
- Alta de tipo documental nuevo desde el propio panel de
  documentación (punto 6 de la hoja de ruta) — no construido.
- Cierre uno a uno de los 231 huecos reales de manuales — pendiente,
  ahora sí con interfaz real desde la que hacerlo.
- Cola de Gemini para `ITV` sin fecha por OCR (491 candidatos B1
  iniciales, `ocr_unreliable`) — todavía no se ha llamado a Gemini en
  esta sesión, sigue como cola documentada.
- Repuntar `document_management.tasks.send_document_expiry_alerts`
  (cron diario) y el envío de documentos por WhatsApp
  (`whatsapp/services.py`) a `DocumentIndexEntry` — identificado como
  dependencia real, no tocado todavía.

**Fase B1 (OCR) real sobre 100 documentos — hallazgo adicional real,
Fase B0 ampliada a `SEGURO` en consecuencia.** Solo 6/100 resolvieron
por contexto OCR — la inmensa mayoría de fallos eran `SEGURO`/
`TACOGRAFO`, avisos bancarios de domiciliación demasiado variados
("Fecha de expedición 16 DICIEMBRE 2011" con mes en letra, "ADEUDO POR
DOMICILIACIONES"...) para una regla de contexto genérica. Mirando el
propio nombre de archivo, sin embargo, el dato ya estaba ahí en el
71% de los casos. Tres subpatrones confirmados por Miguel Ángel:
fecha simple → `issue_date` (nunca caducidad — el único caso real que
sí resolvió por OCR mostró que la fecha del nombre cae un día después
de que termine el periodo cubierto); notación de trimestre ("1º TR.
2013") → `issue_date` = primer día de ese trimestre; rango explícito
("X a Y") → `expiry_date` = fecha Y. Aplicado y verificado: 988
`SEGURO` con fecha real escrita. Segunda pasada de
`backfill_obsolete_duplicates` con las fechas nuevas: 100 duplicados
adicionales resueltos correctamente (de 102 grupos restantes).

**Auditoría real de blob (S48), pedida explícitamente por Miguel
Ángel tras detectar en el propio panel que a A-29/B-38 "les faltaba
el seguro":** verbatim: *"Esto hay que hacerlo muy bien [...] no
podemos dejar máquinas sin documentos [...] si necesitas hacer primero
una auditoría del blob, hazla. Coge tres o cuatro máquinas, mira qué
documentos son los que tienen."* Auditadas A-29 (84 archivos, todos
clasificados correctamente) y B-38 (51 archivos, varios huecos reales
de diccionario encontrados):
- `POLIZA`/`REC SEG`/`REC.SEG` nunca se probaron como candidatos de
  `SEGURO` — error real mío: al principio los mezclé todos bajo
  `SEGURO`, pero Miguel Ángel corrigió: *"una cosa es la póliza y otra
  cosa es el recibo del seguro"*. Corregido: `SEGURO` (Recibo del
  seguro) solo cubre `REC SEG`/`REC POL`; `POLIZA` es tipo nuevo.
- **3 tipos nuevos dados de alta** (migración `0025`, sin
  `RunPython` reversible por `code`): `POLIZA_SEGURO` (Póliza de
  seguro, `tracks_expiry=True`), `CERTIFICADO_PODERES` (distinto de
  `MANDATO`, ya existente — conviven como archivos separados en la
  misma carpeta real de B-38, `tracks_expiry=False`),
  `FACTURA_TERCEROS` (factura por un cargo de un tercero a la máquina,
  distinta de `FACTURA_COMPRA`, `tracks_expiry=False`). Verificado en
  BD: los tres existen con los campos correctos.
- Candidatos nuevos verificados con datos reales antes de aplicar:
  `PODERES` (28 coincidencias reales) y `FACTURA` (54) — **sin
  aplicar todavía como candidatos de Fase A**, la sesión se cerró
  antes de decidir la palabra clave exacta y relanzar el recorrido
  (ver hoja de ruta).
- `PERM CIRC` (variante de `PERMISO_CIRCULACION`) y `CERT
  MANTENIMIENTO` sin "IF"/"IFICADO" (variante de
  `CERT_MANTENIMIENTO`) — huecos de diccionario detectados en la
  misma auditoría de B-38, **sin aplicar todavía**.
- `REC POL` identificado como el mismo concepto que `SEGURO` (recibo
  póliza = recibo del seguro) pero por descuido nunca se añadió al
  diccionario en el momento — corregido al final de la sesión,
  comiteado, **sin relanzar el recorrido todavía** (commit
  `9132ae4`).

**Dos ideas nuevas de Miguel Ángel, explícitamente para la próxima
sesión, no construir nada sin más contexto todavía:**
- **Documentos obligatorios por ley** (verbatim: *"documentos
  obligatorios... el seguro, la ITV, el permiso de circulación, el
  RAE... no sé exactamente cuáles son todos, tendrás que mirarlo"*) —
  pidió explícitamente que Claude busque en internet la lista real de
  documentación obligatoria para camiones/grúas en España antes de
  construir nada. Ver hoja de ruta.
- **Familias de documentos** (agrupación temática — obligatorios,
  técnicos, fotos del vehículo, recibos/facturas...) para
  personal/máquinas/EPIs, pensadas para dos usos reales en la
  interfaz: (a) organizar el acordeón de cada ficha por familia en
  vez de un único bloque "Vigentes"/"Histórico", y (b) permitir
  búsqueda granular real — verbatim: *"no podemos, por ejemplo,
  buscar una máquina, quiero ver el seguro de la máquina... tenemos
  que dotar la interfaz de una granularidad a la hora de la búsqueda
  de cosas que de momento no tenemos"*. Sin diseño concreto todavía —
  ¿es un campo nuevo en `DocumentTypeCatalog` (`family`), o una
  agrupación calculada en la propia vista? Sin decidir.

**Incidencia real de UI reportada, sin investigar todavía:** en el
explorador de archivos (la lista de resultados con casillas de
selección, no el panel nuevo de documentación — confirmar exactamente
cuál en la próxima sesión), al escribir en un campo de búsqueda con
autocompletado, en algún momento deja de recibir las pulsaciones de
teclado. Sin diagnosticar.

**Verificación de sesión completa (S48):** total real de
`DocumentIndexEntry` con `document_type` asignado: **11.149**.
Archivos con fecha real (`expiry_date`/`issue_date`) escrita:
**3.081** (2.093 de la primera pasada B0 + 988 de `SEGURO`). Total
`is_obsolete=True` tras las dos pasadas del backfill: **8.666**
(8.566 + 100). Punto 5 de la hoja de ruta original (panel de
documentación) construido y desplegado, con hallazgos reales de
calidad de datos que obligaron a parar y auditar en profundidad antes
de seguir — decisión correcta de Miguel Ángel, no un desvío.

### Hoja de Ruta para la Siguiente Sesión

**Documentos obligatorios por ley (camiones/grúas, España) —
pregunta abierta de Miguel Ángel, requiere búsqueda web antes de
construir nada.** Verbatim: *"Infórmate en internet, porque yo no sé
exactamente cuáles son todos los documentos que son obligatorios para
un camión y una grúa."* Investigar y confirmar con Miguel Ángel la
lista cerrada antes de marcar ningún tipo como "obligatorio" en el
catálogo. Criterio de cierre: lista confirmada por Miguel Ángel,
reflejada como campo o constante donde corresponda (a decidir junto
con el punto de "familias de documentos", más abajo).

**Familias de documentos — diseño abierto, sin decidir todavía.**
Dos usos reales pendientes de resolver: agrupar el acordeón de cada
ficha por familia (en vez de solo Vigentes/Histórico), y permitir
búsqueda granular ("ver el seguro de esta máquina" sin entrar en la
ficha). Preguntas concretas para la próxima sesión: ¿campo `family`
nuevo en `DocumentTypeCatalog` (migración) o agrupación calculada en
la vista sin tocar el modelo? ¿Las familias son fijas en código o
configurables desde algún sitio? Sin construir nada hasta resolver
esto con Miguel Ángel al inicio de la próxima sesión.

**Ampliar el diccionario de Fase A con los huecos reales ya
detectados en la auditoría de B-38, y relanzar el recorrido —
CONCRETO, listo para ejecutar de inmediato:**
1. Verificar volumen real de `PODERES` (28 ya contado) y `FACTURA`
   (54, cuidado con no confundir con `FACTURA_COMPRA` ya existente)
   como candidatos de `CERTIFICADO_PODERES`/`FACTURA_TERCEROS`.
2. Añadir `PERM CIRC` a los candidatos de `PERMISO_CIRCULACION`, y
   `CERT MANTENIMIENTO` (sin "IF"/"IFICADO") a `CERT_MANTENIMIENTO`.
3. Añadir `POLIZA` como candidato de `POLIZA_SEGURO` (ya separado de
   `SEGURO`, no repetir el error de mezclarlos).
4. Relanzar `run_fase_a_sweep` (dry-run primero, luego `--apply`) y
   `run_fase_b0_filename_dates` para las fechas de los tipos nuevos
   con `tracks_expiry=True` (`POLIZA_SEGURO`).
5. Repetir `backfill_obsolete_duplicates --apply` tras lo anterior.
   Criterio de cierre: verificación real con
   `DocumentIndexEntry.objects.filter(document_type__isnull=False).count()`
   mayor que 11.149, y consulta real confirmando que A-29/B-38 (y una
   tercera máquina de otra familia, para no repetir el mismo sesgo)
   tienen `SEGURO`+`POLIZA_SEGURO` completos.

**Continuar la auditoría real de blob — Miguel Ángel pidió "tres o
cuatro máquinas", solo se auditaron dos (A-29, B-38).** Auditar al
menos 2 máquinas más de familias distintas (p. ej. `Z` plataformas,
`T` carretillas, o una `R`/`G` remolque) antes de dar el diccionario
de `MACHINE` por completo. Criterio de cierre: 4 máquinas auditadas
en total, sin huecos de diccionario nuevos detectados en las últimas
2, o huecos nuevos añadidos y verificados igual que B-38.

**Incidencia de UI del autocompletado — sin investigar, primer paso
es reproducirla con precisión.** Confirmar con Miguel Ángel en qué
pantalla exacta ocurre (explorador de archivos legado vs. panel de
documentación H30) antes de tocar código. Criterio de cierre: pasos
de reproducción exactos confirmados, o corrección aplicada y
verificada si se reproduce a la primera.

**Cola de Gemini para `ITV` (`ocr_unreliable`) — arrastrado 1.ª
sesión sin avanzar.** ~491 candidatos iniciales de la Fase B1 (más
los que hayan quedado tras las últimas pasadas). Construir el
consumidor real de `date_verification_service.extract_expiry_via_gemini`
para este subconjunto, acotado (nunca pasada masiva). Criterio de
cierre: muestra real de `ITV` con `expiry_date` extraída por Gemini y
verificada contra el documento real.

**Fase B1 (OCR) sobre el resto del corpus real (2.068 candidatos
iniciales, ahora menos tras SEGURO por nombre) — arrastrado 1.ª
sesión sin avanzar, solo probado en muestra de 100.** Ejecutar por
lotes (`--limit`) sobre el resto, revisando periódicamente que el
contraste de contexto sigue dando resultados sensatos. Criterio de
cierre: `sin_fecha_reconocible` medido contra el total real restante,
verificado con consulta a BD, no solo con el resumen del comando.

**Cerrar el modelo de permisos de supervisor del panel** (lectura
cuarentena/NO CONFORMES + escritura de anotación/reencolado +
escritura completa solo vía las tres pestañas) — no construido
todavía. Sin criterio de cierre definido, diseñarlo con Miguel Ángel
al empezar este punto.

**Alta de tipo documental nuevo desde el propio panel de
documentación** (hoy solo existe desde el explorador de archivos) —
arrastrado 2.ª sesión sin avanzar. Miguel Ángel, ¿confirmas que sigue
siendo prioridad frente a lo demás, o se pospone sin fecha?

**Cierre uno a uno de los 231 huecos reales de manuales** — pendiente,
ahora sí con interfaz real desde la que hacerlo (ficha de máquina,
botón Actualizar). Sin criterio de cierre numérico fijado — decidir
con Miguel Ángel si se cierra por lotes o de verdad uno a uno.

**Repuntar `document_management.tasks.send_document_expiry_alerts`
(cron diario) y el envío de documentos por WhatsApp
(`whatsapp/services.py`) a `DocumentIndexEntry`** — identificado como
dependencia real de la migración de panel, no tocado todavía.
Criterio de cierre: ambas rutas leyendo `DocumentIndexEntry` en vez de
`MachineDocument`/`PersonalDocument`, verificado con una alerta/envío
real de prueba.

**Decidir el destino final de `MachineDocument`/`PersonalDocument`**
(69 filas legadas) — Miguel Ángel confirmó que se pueden borrar
("los cubos se pueden borrar y se pueden dejar de usar desde ya"),
pero no se llegó a ejecutar el borrado en esta sesión (la conversación
derivó hacia la auditoría de blob). Verificar primero que ningún flujo
activo (alertas, WhatsApp, ver punto anterior) siga dependiendo de
ellos antes de borrar.

**Anomalía `pk 607` (arrastrada desde S48, sin confirmar todavía) —
carpeta anidada dentro de sí misma** (`DOC. MAQUINAS/GRUAS MOVILES
(A)/A-59  E-5068-BHH/A-59 E-5068-BHH`, mismo nombre repetido dos
veces). Sin evidencia suficiente para tratarla como error real bajo
directriz 4.9 — no se toca sin confirmación explícita de Miguel Ángel.

**DECA — horizonte real, plazo octubre 2026, fuera de alcance
activo.** Recordatorio de que antes de esa fecha hará falta decidir si
se resuelve dentro de H30 (tipo documental simple, sin vínculo a
servicios) o si justifica un hito propio una vez exista el modelo de
"servicios". No es tarea de la próxima sesión salvo que Miguel Ángel
lo priorice antes de esa fecha.

**Código/etiqueta y punto de entrada real del "justificante de
asistencia a organismo público"** (detectado en S46, nunca resuelto,
arrastrado varias sesiones sin avanzar) — pedir a Miguel Ángel una
decisión concreta antes de darlo de alta en el catálogo, o retirarlo
de la hoja de ruta si ya no es prioridad.

**Vacaciones controladas desde el panel (H24)** — diseño
explícitamente abierto por Miguel Ángel, sin alcance definido
todavía. No construir nada hasta que lo concrete.

