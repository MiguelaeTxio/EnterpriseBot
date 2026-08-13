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
  **CORREGIDO EN S51:** el buzón deja de ser una vía abierta a
  cualquiera. Miguel Ángel, verbatim: *"Ya lo tengo muy claro que va a
  ser la vía de entrada única y exclusivamente para correos. Si el
  supervisor quiere un hecho y olvido, tendrá que enviar el correo a
  administración y el documento como adjunto [...] la carpeta que creé
  no es visible a los demás puestos, por tanto será usada por Outlook
  para depositar los archivos adjuntos exclusivamente."* Consecuencia
  real: como esta vía nunca es un supervisor conocido subiendo con
  disciplina de nombre de archivo, el diseño de clasificación de tipo
  para esta vía nunca se salta la llamada a Gemini (a diferencia de
  las carpetas vigiladas por agente H28/M365, donde heurística+OCR sin
  discrepancia sí evitan la llamada) — ver hoja de ruta de esta
  sesión.
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

**Dos ideas nuevas de Miguel Ángel, planteadas en S48, resueltas en S49** (documentos obligatorios por ley y familias de documentos — ver `COMPLETADAS EN S49` más abajo).

**Incidencia real de UI reportada, sin investigar todavía (arrastrado 1.ª sesión sin avanzar):** en el explorador de archivos (la lista de resultados con casillas de selección, no el panel nuevo de documentación — confirmar exactamente cuál en la próxima sesión), al escribir en un campo de búsqueda con autocompletado, en algún momento deja de recibir las pulsaciones de teclado. Sin diagnosticar.

**Verificación de sesión completa (S48):** total real de
`DocumentIndexEntry` con `document_type` asignado: **11.149**.
Archivos con fecha real (`expiry_date`/`issue_date`) escrita:
**3.081** (2.093 de la primera pasada B0 + 988 de `SEGURO`). Total
`is_obsolete=True` tras las dos pasadas del backfill: **8.666**
(8.566 + 100). Punto 5 de la hoja de ruta original (panel de
documentación) construido y desplegado, con hallazgos reales de
calidad de datos que obligaron a parar y auditar en profundidad antes
de seguir — decisión correcta de Miguel Ángel, no un desvío.

### COMPLETADAS EN S49

Sesión larga, con desvío explícito y correcto de Miguel Ángel a mitad
de sesión desde "seguir extrayendo fechas" hacia "primero garantizar
que toda la documentación (máquinas + documentos) está correctamente
reflejada en base de datos" — ver el cierre de esta misma sección
para el razonamiento completo, verbatim, de por qué se paró la
ingesta de fechas.

**Documentos obligatorios por ley (S48, punto pendiente).** Búsqueda
web real (RD 837/2003 grúas móviles autopropulsadas, RD 1215/1997 +
RD 1644/2008 equipos de trabajo/marcado CE, RD 836/2003 grúas torre,
normativa DGT de circulación) para las familias reales de la flota
(tabla completa de prefijos A/B/Z/H/MK/P/T/V/S/R-G confirmada por
Miguel Ángel con foto de spider crane real). Confirmado que los
camiones grúa autocargantes (familia B) están **excluidos** del RD
837/2003 (solo grúas móviles autopropulsadas puras, familia A, caen
bajo ese reglamento reforzado con inspección OCA periódica). Turismos
y remolques siguen excluidos del alcance de H30 (S47).

**Familias de documentos (S48, punto pendiente) — decidido y
desplegado.** Miguel Ángel confirmó: campo real `family` en
`DocumentTypeCatalog` (no agrupación calculada en la vista) con lista
fija de `choices` en código (no tabla configurable aparte) — 10
familias (Circulación, Técnica y seguridad, Seguros, Financiero y
compraventa, Bajas de máquina, Administrativo, Identidad y personal,
Laboral, Salud y bajas de persona, PRL y formación). Migración
`0028_add_family_and_backfill.py`: `AddField` + backfill de las 58
filas del catálogo cerrado a esa fecha, sin huecos (verificado con
`git rev-list`/`showmigrations`/consulta real tras el despliegue). 5
tipos dados de alta después de esas migraciones (`DECLARACION_
HOMOLOGACION`, `DNI_COMPRADOR`, `JUSTIFICANTE_TRANSFERENCIA`,
`MANUAL_DESPIECE`, `RECIBO_SENAL_COMPRA`) detectados sin familia y
asignados en el mismo cierre — catálogo completo (64 tipos en ese
momento) con familia al 100%.

**Caso real HOEFLON (S-19 SEPARADOR) — dos tipos documentales
nuevos.** Dos archivos subidos por Miguel Ángel para revisión
(certificado neerlandés "CERTIFICAAT HIJSMIDDELEN" de un balancín/
separador extensible, fabricante Deij Hijstechniek B.V., suministrado
vía Hoeflon International BV; y su albarán de entrega) resultaron NO
ser una minigrúa mal clasificada — corrección explícita de una
conclusión prematura propia antes de ver los documentos reales.
Altas: `CERT_ACCESORIO_ELEVACION` (`tracks_expiry=True`, migración
`0026`) y `ALBARAN_ENTREGA` (`tracks_expiry=False`, migración `0027`).
Localizadas con datos reales 4 filas del mismo certificado (3 copias
distintas de blob, no la misma fila) más el albarán — reclasificadas
una a una tras confirmación de Miguel Ángel: pk 17587 (ubicación
correcta) → `CERT_ACCESORIO_ELEVACION`; pk 17586 (albarán, misma
carpeta) → `ALBARAN_ENTREGA`; pk 11042 y 41748 (copias sobrantes,
una en `_CUARENTENA` sin procesar 9 días) → mismo tipo, marcadas
`is_obsolete=True`. Ninguna llegó nunca a NO CONFORMES (verificado).

**Ampliación del diccionario de Fase A y corrección real del
framework de dosier.** Añadidos al diccionario real
(`calibrate_fase_a_keywords.py`, que alimenta también `run_fase_a_
sweep.py` al importarlo directamente): `CERT MANTENIMIENTO` (variante
sin "IF"/"IFICADO", **1.518** coincidencias reales — el hueco más
grande de la sesión), `PERM CIRC` (50), `PERMISO DE CIRCULACION` con
"DE" en medio (133, detectado al investigar el caso 7245GBM), `PODERES`
para `CERTIFICADO_PODERES` (28), `FACTURA` para `FACTURA_TERCEROS`
(54, solape deliberado con `FACTURA_COMPRA`), `POLIZA` para
`POLIZA_SEGURO` (750) y `RECIBO` suelto para `SEGURO` (223, detectado
en el mismo caso 7245GBM). **Fallo real corregido (directriz 4.9):**
`DOSSIER_PAIRS` mandaba a papelera cualquier archivo con dos tipos
candidatos a la vez SIN comprobar si esos dos documentos ya existían
por separado en algún otro sitio — Miguel Ángel confirmó la regla real
("siempre y cuando los documentos separados estén, el dosier se puede
eliminar; si no, no se puede eliminar") y se corrigió con
`_dossier_types_already_filed()`, que resuelve el objeto de dominio
del candidato a dosier y solo elimina si CADA tipo del par ya tiene
una fila archivada fuera de cuarentena para esa misma máquina/persona.
Nueva regla de prioridad `FACTURA_COMPRA` > `FACTURA_TERCEROS`
(confirmada: una factura entre dos terceros sigue siendo, a todos los
efectos, una factura de compra ligada al vehículo). `POLIZA_SEGURO`
↔ `SEGURO` añadido a `DOSSIER_PAIRS` (póliza+recibo escaneados juntos).
Exclusión del falso positivo real "POLIZA RC - FORMACION". Dos pasadas
de `run_fase_a_sweep --apply`: primera (2.938 asignados, 8 dosieres
eliminados por ya estar divididos, 2 dejados intactos para revisión
manual) y segunda tras añadir `PERMISO DE CIRCULACION`/`RECIBO` (331
asignados más, 2 dosieres eliminados más). Total verificado con
consulta real tras ambas pasadas: 14.091 `DocumentIndexEntry` con
`document_type` asignado (subida desde 11.149 al cierre de S48).

**Fase B0 (fechas por heurística de nombre) — ejecutada y luego
pausada por decisión de Miguel Ángel.** `run_fase_b0_filename_dates
--apply`: 572 fechas escritas. `POLIZA_SEGURO` deliberadamente
excluido de esta fase (Miguel Ángel: mejor esperar a Fase B1/OCR real
para confirmar si la fecha del nombre es emisión o caducidad, en vez
de generalizar sin evidencia, mismo criterio que ya se aplicó a
`EXCEDENCIA` en S48).

**Informe de cobertura de documentación obligatoria (`audit_
mandatory_documents`, nuevo).** Primer corte de tipos obligatorios
por familia (A/B/Z/H/P/T/V/S), acotado a tipos ya existentes en el
catálogo — deliberadamente sin `IPO`/`ITC` hasta confirmar su
significado real en el archivo de Grupo Álvarez. **Fallo real
corregido en el propio comando:** el primer informe colaba carpetas
administrativas (`ADMINIST`, `ADOLFO`, `BEN`, `PAOLA`, `PERSONAL`,
`PILOTES`, `VARIOS`, `VENTA`) como si fueran máquinas de la familia
A/B/P/V solo por compartir la letra inicial — corregido exigiendo
regex letra(s)+dígitos exacto. También retirado `MK` como prefijo
real (las grúas torre sobre camión, p.ej. "MK80"/"MK100", están
codificadas dentro de la familia A, MK es solo parte del nombre del
modelo). Resultado real tras la corrección: 550 máquinas activas
evaluadas, 316 con algún hueco (698 huecos en total), 17 completas,
217 fuera del alcance del prefijo (turismos/remolques/administrativo,
excluidos correctamente).

**Reconciliación de máquinas sin `MachineAsset` (`reconcile_machine_
folders`, nuevo) — hecha y verificada.** Detectado el caso raíz real:
`resolve_or_create_machine_asset()` solo se dispara como efecto
colateral de clasificar un archivo (Fase A) — una carpeta cuyos
archivos nunca pasaron por clasificación nunca dispara la creación
automática, aunque el nombre de la carpeta tenga forma válida de
código de flota o matrícula. Caso real que lo destapó: el Peugeot
307 que conduce Miguel Ángel (matrícula 7245GBM) — la máquina SÍ
existía en `MachineAsset` (creada en una sesión anterior porque un
documento suyo se había clasificado), pero de 6 archivos reales en su
carpeta solo 1 tenía `document_type`; los otros 5 (incluido el propio
`PERMISO DE CIRCULACION.pdf`) estaban sin clasificar por el hueco de
diccionario ya descrito arriba. Comando de reconciliación construido
reutilizando exactamente `_FOLDER_MACHINE_CODE_RE`/`_FOLDER_PLATE_RE`/
`resolve_machine_asset`/`resolve_or_create_machine_asset` de
`classification_service.py`, sin reescribir el patrón de detección.
Dry-run: 1.461 carpetas de máquina reales bajo `DOC. MAQUINAS`, 1.145
ya resueltas, 155 candidatas (deduplicadas por código/matrícula real:
**91 vehículos/máquinas distintos**), 161 sin forma reconocible de
código (revisión manual, fuera de alcance de este comando). Miguel
Ángel revisó el listado completo de 91 y confirmó excluir 6 casos
dudosos (`AC300` catálogo de referencia de modelo, `CONT03`/`CONT04`
contenedores de obra, `MIRA10` EPI de persona, `E1405`/`SE7625`
posibles máquinas reales -A y P- sin código de flota clásico
confirmado todavía) — "mejor no contaminar por tres o cuatro
máquinas", se añadirán a mano cuando corresponda. `--apply` sobre los
85 restantes: **149 resoluciones reales** (algunas reutilizan la
misma `MachineAsset` ya creada momentos antes en el mismo run para
subcarpetas del mismo vehículo). Verificado con datos reales tras el
despliegue: `MachineAsset.objects.count()` = 585 (556 activas), las 6
excluidas confirmadas NO existen, sin duplicados.

**Desvío explícito de Miguel Ángel a mitad de sesión, verbatim:**
*"¿Para qué vamos a leer las fechas? ¿Para qué vamos a nutrir la base
de datos de fechas si todavía nos falta documentación? [...] Primero
que todos los vehículos tengan la documentación que tienen que tener.
[...] Es lo primero."* — se paró la Fase B0/B1 de fechas a mitad de
ejecución y se giró el resto de la sesión hacia cobertura de
documentos y reconciliación de máquinas. Decisión correcta, no un
desvío que corregir — cambia el orden de la hoja de ruta siguiente,
ver abajo.

**Instrucción explícita de Miguel Ángel sobre el propio PCS, verbatim
(a incorporar como principio permanente de esta skill, no solo de
esta sesión):** *"El PCS es la herramienta de cierre de sesión que
prepara el inicio de la sesión siguiente y todo el trabajo de la
siguiente sesión [...] El modelo, cuando comience, no debe tener
ninguna laguna ni ninguna ambigüedad [...] no puede repetir preguntas
que ya se han contestado, no puede no saber que ya hemos reconciliado
maquinaria con la base de datos."* Aplicado en la Hoja de Ruta de
abajo: el estado de la reconciliación de máquinas se da por CERRADO y
VERIFICADO (no se vuelve a plantear la pregunta), y el orden de
trabajo para la próxima sesión queda explícito paso a paso, sin
redacción abierta.

**Commits reales de la sesión** (10, `7f1671c..86eb79f`): `9ba2909`
alta `CERT_ACCESORIO_ELEVACION`; `59ae71f` alta `ALBARAN_ENTREGA`;
`e21dadf` campo `family` + backfill; `7ec93a9` ampliación diccionario
Fase A (huecos B-38); `ec79dab` corrección framework de dosier + 3
reglas nuevas; `2ae700c` informe de cobertura `audit_mandatory_
documents`; `cbdc44a` corrección de falsos positivos de prefijo;
`84b6229` `PERMISO DE CIRCULACION`/`RECIBO` sueltos; `0dda674`
`reconcile_machine_folders`; `86eb79f` exclusión de las 6 candidatas
dudosas confirmadas. 8 archivos tocados, 713 inserciones/18
eliminaciones.

### COMPLETADAS EN S50

Sesión larguísima (39 commits) con dos frentes reales: cerrar de
verdad la vinculación documental de maquinaria (heurística de nombre
→ OCR → Gemini, orden ya vinculante desde S49), y descubrir y tapar
un hueco crítico real -- el motor de alertas WhatsApp (H26, completo
y en producción desde hace meses) nunca estaba conectado al flujo
nuevo de `DocumentIndexEntry`.

**1. Limpieza de vigencia y duplicados, previa a todo lo demás:**
`resolve_vigencia` (442 filas obsoletas por fecha efectiva, con
blindaje explícito anverso/reverso tras encontrar 3 casos reales mal
marcados -- Antonio Aranda DNI, González Millán DNI, A-31 ficha
técnica -- corregidos), `resolve_itv_ficha_tecnica_dossier` (9 casos,
regla confirmada por Miguel Ángel: si ya existe `FICHA_TECNICA`
suelta, el combinado sobra; si no, se queda el combinado),
`resolve_obsoleto_folder_flag` (3.804 archivos corregidos por vivir
en una subcarpeta `OBSOLETO` real de su propia máquina, 111
excluidos correctamente por ser carpetas de máquina de baja
completa -- caso B, semántica distinta, nunca tocado),
`resolve_variant_marker_duplicates` (17 duplicados `_unlocked`/
`copia` resueltos -- **bug real encontrado y corregido en la misma
sesión**: la primera versión comparaba fecha y `None == None` colaba
como "misma fecha", emparejando documentos que no eran el mismo
archivo; corregido exigiendo nombre base idéntico tras quitar solo
el marcador).

**2. `IPO`/`ITC` resuelto y luego fusionado:** confirmado por
búsqueda real (IPO = Inspección Periódica Oficial de grúa móvil, ITC
= la instrucción técnica que la regula) y añadidos a
`MANDATORY_BY_PREFIX` familia A. Después, construyendo
`sample_known_type_ocr_text` (herramienta de análisis, nunca escribe
nada -- extrae texto OCR de 3 ejemplos reales por tipo ya confirmado
para descubrir patrones de contenido), se descubrió que **el
contenido real de IPO e ITC es literalmente el mismo documento** --
"ACTA DE INSPECCIÓN PERIÓDICA DE GRÚAS MÓVILES AUTOPROPULSADAS" en
ambos. Miguel Ángel: *"si en documentos conocidos no podemos
discernir entre IPO e ITC lo suyo es fusionar el tipo."* Migración
0031: fusionados en `IPO_ITC`, los dos tipos antiguos desactivados
(no borrados), las 457 filas reales reasignadas.

**3. Mapa de alcance de maquinaria confirmado carpeta por carpeta con
Miguel Ángel** (`run_fase_a_sweep_scoped.py`, `SCOPE`) -- nunca por
heurística de código de flota (eso colaba carpetas administrativas
como "OBSOLETO/OBSOLETO P07", máquinas de baja completa). Familia por
familia: `CABEZAS TRACTORAS` solo las nombradas explícitamente;
`CAMIONES BRAZO`/`GRUAS MOVILES`/`PLATAFORMAS` todo menos las
carpetas administrativas confirmadas (`PROPUESTA SEGURO`,
`OBSOLETO`/`BAJA`, `ALTESUR` -empresa de alquiler ajena-, `ESTIBA
PLATAFORMAS` -fichas por categoría, no por máquina-, `POLIZA RC`
-póliza colectiva, no de una sola máquina-); `MK 100`, `CARRETILLA
(HL)`, `DOCUMENT 1884JB` excluidos explícitamente tras verlos en el
primer dry-run real. `RAE` y `CE PLATAFORMAS` dentro de alcance con
resolución de dominio por NOMBRE de archivo (no por carpeta,
compartida entre máquinas).

**4. Cobertura de nombre agotada de verdad, dos rondas completas:**
primera ronda con las 80 palabras más frecuentes del resto sin
clasificar (238+16 asignados), y una segunda ronda completa tras
protesta explícita de Miguel Ángel ("no nos podemos dejar
documentos por el camino, no solo el top 80") repasando las 504
palabras reales con 3+ apariciones -- 8 tipos documentales nuevos
(`CONTRATO_ARRENDAMIENTO`, `CAMBIO_TITULARIDAD`, `CARTA_VERDE`,
`REVISION_ESLINGAS`, `GARANTIA_FABRICANTE`, `INFORME_INCIDENCIAS`,
`PEDIDO_COMPRA`, `PROVISION_FONDOS`) y otros 6
(`IEDMT`/`IVTM`/`CERT_EXENCION_PERMISO`/`SANCION_TRAFICO`/
`CUADRO_AMORTIZACION`/`GASTOS_TARJETA_COMBUSTIBLE`) confirmados con
texto real descargado de GCS (nunca por nombre de archivo a ciegas),
más 12 keywords de tipos ya existentes con volumen medido. Total
**704 documentos reales clasificados** por heurística de nombre en
la sesión. `run_fase_a_sweep_scoped` queda como comando permanente y
reutilizable.

**5. Clasificación por CONTENIDO vía OCR** (`run_fase_b1_ocr_classify`)
-- **bug real detectado y corregido en la misma sesión**: la primera
versión reutilizaba el mismo matcher de palabra suelta que la
heurística de nombre, dando falsos positivos reales (un informe de
mantenimiento que mencionaba "ITV" de pasada se clasificó como ITV).
Corregido con `CONTENT_MARKERS`: frases largas y específicas
descubiertas con `sample_known_type_ocr_text` contra 14 tipos
confirmados, nunca palabra suelta. Verificado que los dos falsos
positivos ya no aparecen. Aplicado en el servidor hasta que el
tarpit de CPU de PythonAnywhere lo hizo inviable (6.000/5.000
segundos consumidos en una sola noche).

**6. Ejecución movida a local** (`h28_migration_agent/
local_ocr_classify.py`) -- versión standalone sin Django, túnel SSH a
MySQL + GCS directo con la clave del agente H28, reutilizando
literalmente el mismo `SCOPE`/`CONTENT_MARKERS` que el comando del
servidor. Instalación real en el PC de Miguel Ángel con varios
tropiezos reales, todos corregidos: `paramiko.DSSKey` ausente
(`sshtunnel` lo referencia incondicionalmente al montar el túnel,
aunque solo se use contraseña -- se rellena con un valor de
relleno), contraseña de MySQL distinta de la de la web (dos prompts
separados), Tesseract sin permisos de administrador para escribir en
`Program Files` (se usa una carpeta `tessdata\` propia junto al
script). **Al cierre de sesión sigue corriendo en el PC de Miguel
Ángel, en primer plano, sin límite** (`python local_ocr_classify.py
--apply`, sin `--limit`) sobre los ~2.670 candidatos que quedaban --
ver Hoja de Ruta.

**7. Hueco crítico real descubierto y cerrado: el motor de alertas
WhatsApp (H26) nunca se llamaba desde `document_explorer`.**
`document_management.alert_service.create_default_expiry_alerts`
(Twilio, plantilla `document_expiry_alert` aprobada, tarea diaria
`send_document_expiry_alerts`) llevaba activo desde H26 pero solo lo
invocaban `machine_documents`/`personal_documents` (los modelos
legados, ya sustituidos). **Ni la subida manual desde el panel ni la
vía del agente/cuarentena creaban ninguna alerta** -- confirmado con
datos reales: 70 `DocumentAlert` en BD, todas de antes de la
migración a `DocumentIndexEntry`. Cerrado con:
- `document_explorer/filename_date_service.py` -- heurística de
  fecha por nombre (Fase B0), extraída de
  `run_fase_b0_filename_dates.py` a servicio compartido.
- `document_explorer/expiry_resolution_service.py` -- encadena
  heurística → OCR → Gemini, en ese orden exacto, parando en el
  primer paso que encuentre fecha. Nunca bloquea la clasificación si
  falla; la ausencia de fecha en un tipo `tracks_expiry=True` es la
  propia señal de "necesita atención humana".
- Enganchado en `consume_quarantine_task` (Always-on Task real, vía
  del agente) justo tras relocar un archivo, y en
  `subject_upload_service.upload_subject_document` (subida manual
  desde el panel) -- las dos vías reales de ingesta, ninguna se
  queda fuera. Ambas crean alertas con
  `get_docs_supervisor_contacts()` (Yolanda Bandera + Miguel Ángel
  Muñoz Cara, resueltos por `role=DOCS_SUPERVISOR`, nunca nombre
  fijo) más quien sube el documento si aplica.
- Corregido de paso: `PERMISO_CIRCULACION` tenía `tracks_expiry=True`
  -- confirmado con fuentes reales (DGT, RACE) que este documento NO
  caduca en España, corregido a `False`.
- Horario de la tarea diaria movido de las 3:00 a las 8:00 -- un
  aviso de WhatsApp real a las 3 de la madrugada no tiene sentido.

**8. Aviso visual en el panel** (Centros de Gasto y Personal): fila
roja + icono de alerta en la ficha de cada sujeto cuando un
documento vigente de tipo `tracks_expiry=True` no tiene fecha o ya
caducó; columna de alerta nueva en ambos listados para verlo de un
vistazo sin entrar máquina por máquina.

**9. Dos bugs reales de interfaz encontrados y corregidos, fuera del
plan pero bloqueantes para el equipo de documentación:**
- Autocompletado roto en las 3 pestañas de Documentación: el
  `<input>` de búsqueda vivía DENTRO del contenedor que HTMX
  sustituye en cada tecleo (debounce 300ms) -- cada carácter
  destruía y recreaba el campo, perdiendo el foco a mitad de
  escritura. Corregido separando formulario (nunca se sustituye) de
  resultados (sí se sustituye) en las 3 pestañas, con URLs/vistas
  nuevas para los endpoints de solo-resultados.
- Comentarios Django `{# ... #}` multilínea rotos (Django no los
  soporta, se renderizan como texto crudo) en los parciales nuevos
  de la corrección anterior -- corregido con `{% comment %}
  ... {% endcomment %}`. Verificado que no hay más casos en todo el
  proyecto.

**Hallazgos nuevos, todavía sin resolver, para la próxima sesión:**
- **Los nombres de archivo no se normalizan retroactivamente.** El
  esquema fijo de `naming_service` solo se aplica en la vía del
  agente/cuarentena y en la subida manual -- ningún comando de Fase A
  ni de OCR de esta sesión renombra nada, solo escribe tipo/fecha/
  máquina. El histórico sigue con el nombre original de siempre.
- **`FICHA_TECNICA` vs `ITV` -- ambigüedad real, no solo de este
  sistema.** Confirmado por fuentes reales (DGT, RACE) que "ficha
  técnica" y "tarjeta ITV" son sinónimos en el uso oficial español la
  mayoría de las veces -- coincide con lo que se ve en el corpus
  (documentos "FICHA TECNICA.pdf" cuyo contenido OCR es un
  certificado oficial de inspección, no un tríptico de fabricante).
  Miguel Ángel quiere distinguir para el negocio: documento oficial
  de la administración → `ITV`; tríptico de especificaciones del
  fabricante → `FICHA_TECNICA`. Sin medir todavía cuántos de los
  `FICHA_TECNICA` actuales son en realidad uno u otro.

### COMPLETADAS EN S51

**1. Resolución de la PRIMERA LÍNEA arrastrada (alta de tipo desde
panel, diseño de clasificación por vía de entrada, barrido de
backlog, justificante de asistencia trasladado a H07)** -- ver bloque
"PRIMERA LÍNEA" más abajo en este mismo anexo para el detalle
íntegro con las citas verbatim de Miguel Ángel.

**2. Atajo de alta de tipo documental desde el flujo de subida del
panel, construido y desplegado:** migración 0032 (familia catch-all
`OTROS_DOCUMENTOS`, 11.ª, fija -- S49 no se revierte),
`DocumentTypeQuickCreateView` (abierta a ADMIN/`DOCS_SUPERVISOR` vía
`DocsUploadAccessMixin`), opción "+ Añadir tipo documental nuevo" en
el desplegable de las pestañas Centros de Gasto/Personal. Verificado
en producción -- Action `2448cb3` con todos los pasos en verde,
incluido `migrate`.

**3. Anotado, sin construir: alta de sujeto nuevo (centro de
gasto/trabajador/EPI) ligada a la subida de su primera
documentación.** Ver bloque dedicado más abajo en este anexo -- las
tres piezas parten de un estado real muy distinto (CRUD de centro de
gasto ya existe, trabajador solo tiene alta automática, EPI casi todo
por construir).

**4. Bug real encontrado y corregido en la misma sesión (directriz
4.9), fuera del hilo principal de H30:** el listado de flota
(`panel/templates/panel/fleet/_table_fragment.html`, CRUD de
`fleet.MachineAsset`) tenía su acción "Documentación" apuntando a
`history:machine_history?machine_code=...#documentacion` -- una
sección que lee `selected_machine.documents`, el modelo legado
`MachineDocument` (~30 filas residuales, dado por sustituido en S48
por el panel H30 sobre `DocumentIndexEntry`, con 11.000+ documentos
reales). Un admin que pulsara ahí veía casi vacío en vez de la
documentación real de la máquina. Corregido: el enlace pasa a
`panel:documentation_machine_detail` (ficha H30 real, ya construida y
en producción). Con esto queda resuelto de paso lo pedido en el punto
1 de la hoja de ruta anterior ("enlazar el CRUD de centro de gasto ya
existente con la subida de documentación") -- no hacía falta
construir nada nuevo, solo corregir el enlace roto.

**5. Bug real encontrado y corregido -- enlaces rotos en el historial
de operaciones (`document_explorer/operaciones/<pk>/`,
`DataOperationLogDetailView`).** Origen real: Miguel Ángel reportó un
404 (`No DocumentIndexEntry matches the given query`) al abrir un
documento desde la Operación #289. Investigado a fondo con consultas
reales contra producción -- el pk en cuestión (`FORM. CURSO
CARRETILLA ELEVADORA.pdf`, trabajador Estevao Veloso Sampaio) SÍ
existía, con `deleted_at` puesto hoy mismo por `alvarez_admin`
(`_DOSSIER_TRASH_USERNAME`, la identidad de sistema para borrados
automáticos). **Mecanismo real confirmado por Miguel Ángel viendo la
propia pantalla de Operación #289** (no era `is_photo`/`is_dossier`,
hipótesis inicial descartada): duplicado exacto por CRC32C y tamaño
de un documento ya archivado fuera de cuarentena, `ACTION_TRASHED`
(`DataOperationLogEntry`), eliminado automáticamente sin pasar por
Gemini -- mecanismo ya existente y correcto, no hacía falta tocarlo.
**El bug real estaba en la plantilla, no en el borrado:** `{% if
line.index_entry_id %}` pintaba SIEMPRE un enlace a `document_explorer
:open` sin comprobar `line.action` -- para toda fila `TRASHED`
(`deleted_at` no nulo), `OpenDocumentView` da 404 sin excepción
(filtra `deleted_at__isnull=True`), así que cada operación con
duplicados eliminados mostraba enlaces rotos garantizados. Corregido
en `operation_log_detail.html`: las filas `TRASHED` ya no enlazan,
muestran el nombre en texto plano con nota de que el contenido sigue
accesible en la copia "Conservada" del mismo grupo. Comprobado
`duplicates.html` (misma familia de tarjeta, mismo mecanismo de
enlace) -- NO tiene el bug, por diseño solo lista duplicados
pendientes de decidir, nunca entradas ya borradas (`DuplicatesView`,
"Deliberadamente NO preselecciona nada para borrar").

**6. Bug real encontrado y corregido -- aviso repetido cada minuto
del agente H28 por hidratación atascada.** Miguel Ángel, verbatim:
*"Vamos a quitar de en medio estas notificaciones cada minuto, porque
es que se vuelve uno loco."* Diagnosticado con un script PowerShell
ad-hoc (replica `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`,
`0x00400000`, el mismo criterio que ya usa `is_cloud_only()`) contra
`DOC. PERSONAL` real: el archivo atascado es el `CARNE CONDUCIR` de
la carpeta duplicada `SAMPAIO, ESTEVAO` (la misma detectada antes en
esta sesión) -- mismo patrón que el incidente ya documentado de S035
(placeholders sincronizados desde otro puesto que nunca hidratan).
Causa raíz: `sweep_folder()` pedía la hidratación en cada barrido
(cada minuto) sin ningún seguimiento de si ya se había avisado antes,
así que un archivo atascado generaba aviso nuevo para siempre, sin
límite. Corregido: `hydration_notify_state.json` nuevo (`agent_data/`,
nunca commiteado) guarda cuándo se avisó por última vez de cada ruta;
el aviso no se repite hasta pasados 30 minutos
(`HYDRATION_NOTIFY_INTERVAL_MINUTES`). La petición de hidratación en
sí no cambia, se sigue pidiendo cada barrido. **Pendiente de que
Miguel Ángel actualice/reinicie su agente local** -- sin despliegue
automático vía GitHub Actions, `h28_migration_agent` corre en su
propio PC.

**Deuda identificada, NO corregida esta sesión -- alcance mayor,
fuera de lo pedido hoy:** la sección `#documentacion` de
`panel/machine_history.html` (con su propio botón "Subir
documentación" hacia `machine_documents:upload`, el flujo H23
antiguo) queda huérfana -- ya no es alcanzable desde el listado de
flota tras la corrección del punto 4, pero sigue siendo alcanzable
por URL directa o marcador antiguo, y sigue mostrando datos del
modelo legado. Retirar esa sección por completo (y valorar qué pasa
con `machine_documents:upload`) es una limpieza mayor que toca
`history/views.py` y esa plantilla entera -- pendiente, no
comprometida para la próxima sesión salvo que Miguel Ángel lo pida.

**Deuda mayor identificada esta sesión, NO abordada -- carpetas de
persona duplicadas en Microsoft 365 (`DOC. PERSONAL/PERSONAL/
TALLER/`).** Miguel Ángel, verbatim: *"Hay un tal Nicolás, Santiago
Gutiérrez, Omar, que también hay dos carpetas. Madre mía, qué selva,
qué selva."* Confirmado con datos reales: Estevao Sampaio tiene dos
carpetas (`SAMPAIO, ESTEVAO` con 4 documentos reales sin clasificar
todavía, y `VELOSO SAMPAIO, ESTEVAO` con 3 documentos ya en la ficha
del panel) -- mismo trabajador, mismo problema que la reconciliación
de `MachineAsset` ya resuelta en S49 (585 casos), pero **nunca hecha
para personal**. Sin dimensionar todavía cuántas personas están
afectadas -- pendiente una consulta de solo lectura que agrupe
carpetas por similitud de nombre antes de decidir cómo reconciliarlas
(mismo criterio que `reconcile_machine_folders`, pero para
`PersonIdentity`/carpetas de `DOC. PERSONAL`). No confundir con el
pendiente ya registrado de "alta de trabajador nuevo" (bloque de
arriba) -- esto es sobre trabajadores que YA EXISTEN pero con su
documentación repartida en dos carpetas por variación de nombre.
**Orden confirmado por Miguel Ángel (S51): "Vamos a terminar primero
con la maquinaria y cuando tengamos la maquinaria, le metemos mano a
personal."** No abrir este frente hasta que el trabajo de maquinaria
en curso (barrido `local_ocr_classify.py` + resto de OCR/fecha en
`DOC. MAQUINAS`) esté cerrado.



**PRIMERA LÍNEA -- resuelta en S51, decisiones de Miguel Ángel
registradas verbatim (directriz 2.2 de `nfs-enterprisebot-pcs`
aplicada, las tres preguntas arrastradas dejan de repetirse):**

1. **Alta de tipo documental nuevo desde el propio flujo de subida
   del panel — CONFIRMADO, se construye.** Ya existía la vía desde el
   Catálogo de tipos del explorador (la que usa Miguel Ángel hoy por
   comodidad, nunca puesta en duda) — lo pendiente y ya confirmado en
   S51 es el atajo dentro de las tres pestañas de documentación, para
   cuando el supervisor no encuentre el tipo en el desplegable. Sin
   diseño abierto por parte de Miguel Ángel para el texto exacto del
   desplegable -- decisión no bloqueante tomada en S51: última opción
   del desplegable con el literal "+ Añadir tipo documental nuevo",
   formulario inline mínimo (nombre, familia, `tracks_expiry`), sin
   salir de la pantalla de subida. Ajustable si Miguel Ángel lo pide
   al verlo construido. Sin construir todavía -- queda en la hoja de
   ruta de la próxima sesión.
2. **Diseño de clasificación de TIPO por vía de entrada — CONFIRMADO
   en S51, sin construir todavía.** Extiende a la clasificación de
   TIPO (hoy `classify_entry()` llama a Gemini directamente, sin paso
   heurístico previo -- verificado contra el código real en S51,
   confirmado que solo la resolución de FECHA sigue hoy el orden
   heurística→OCR→Gemini) el mismo criterio ya validado para fecha,
   diferenciado por vía real de entrada:
   - **Panel (supervisor tipa a mano):** sin ambigüedad, el tipo ya
     es dato confirmado por persona, no aplica este diseño.
   - **Carpetas vigiladas (agente H28/M365, `DOC MAQUINARIA`/`DOC
     PERSONAL`):** heurística de nombre + OCR de contenido; si
     coinciden sin discrepancia, se acepta sin llamar a Gemini; si
     hay discrepancia, se llama a Gemini con nombre de archivo +
     resultado heurístico + resultado OCR como contexto.
   - **Buzón de documentación:** desde S51 exclusivo para correos vía
     Outlook (ver sección 3, corrección S51) -- nunca se asume
     disciplina de supervisor, siempre se llama a Gemini, siempre con
     heurística+OCR como contexto adjunto. Requiere ampliar la
     extracción de Gemini en esta vía (hoy `classify_entry()` no hace
     resolución de fecha en la misma llamada).
   Miguel Ángel, verbatim (S51), sobre el criterio de ahorro de
   llamadas: *"Una cosa es lo que estamos haciendo ahora mismo, que es
   intentar ahorrarnos las llamadas a Gemini, y otra cosa es lo que
   pase en producción. Cuando ya estemos en producción, el camino es
   heurística, OCR, Gemini [...] ahora, mientras estamos construyendo
   todo el sistema, es intentar eliminar las llamadas a Gemini."* Es
   decir: en producción Gemini como último recurso es el diseño
   normal, no una excepción a evitar -- la minimización de llamadas es
   un criterio de esta fase de limpieza del backlog, no una regla
   permanente.

   **CONSTRUIDO Y DESPLEGADO en S51 (commits `1b61b13`/`07f2c84`),
   diseño final real -- distinto del boceto inicial de arriba, tras
   verificar contra el código real que el buzón YA vigila el mismo
   agente H28 (no hacía falta pipeline nuevo, solo diferenciar
   origen) y que la reubicación de PERSONAL depende de un DNI que
   antes solo daba Gemini:**
   - `document_explorer/heuristic_type_service.py` (módulo nuevo):
     heurística de TIPO extraída de `run_fase_a_sweep.py` (S48/S49,
     validada contra 11.149 documentos), ahora compartida entre el
     barrido batch y el pipeline en tiempo real. Cero duplicación --
     `run_fase_a_sweep.py`/`run_fase_a_sweep_scoped.py` actualizados
     para importar de aquí.
   - `_try_heuristic_classification()` (`classification_service.py`),
     enganchada en `apply_quarantine_classification()` antes de
     `classify_entry()`: MÁQUINA -- tipo por heurística basta, la
     identidad ya se resuelve por carpeta en el resto del pipeline
     existente, sin depender de ningún hint de Gemini en el caso
     normal. PERSONAL -- tipo por heurística + DNI por OCR
     (`_extract_dni_via_ocr()`, reutiliza `date_verification_service.
     extract_text()` sin tocarla, valida con el algoritmo real de
     letra de control ya existente) que resuelva a una
     `PersonIdentity` YA EXISTENTE. Miguel Ángel, verbatim: *"No
     podemos dar de alta a un trabajador sin llamar a Gemini."* -- DNI
     no leído, ambiguo (más de un DNI válido en el texto), o sin
     coincidencia con nadie conocido cae siempre a Gemini, sin
     excepción; el alta de trabajador nuevo sigue exigiendo su
     verificación de nombre tal cual ya funciona hoy.
   - Buzón (`domain=None` de `quarantine_domain_for_entry()` para esa
     vía, confirmado con datos reales -- pk 42285) sin cambios,
     siempre Gemini.
   - Sin construir todavía: contraste explícito heurística-vs-OCR con
     Gemini como último recurso "si no coinciden" (el diseño
     construido es más simple -- si la heurística+identidad resuelven
     limpio, se acepta; si no, Gemini decide solo, como hoy). Ampliar
     si Miguel Ángel lo pide tras ver el ahorro real en producción.
3. **Barrido de `expiry_resolution_service` sobre el backlog histórico
   -- CONFIRMADO en S51, se lanza.** Los ~491 documentos históricos ya
   tipados (`ITV`/otros `ocr_unreliable`) que quedaron sin fecha
   porque el servicio (S50) solo se disparó para ingesta nueva en
   tiempo real. El propio servicio ya minimiza el gasto por diseño
   (para en el primer paso que resuelve fecha) -- no hace falta
   construir nada nuevo, solo ejecutarlo contra el histórico. Sin
   ejecutar todavía -- queda en la hoja de ruta de la próxima sesión.
4. **Código/etiqueta del "justificante de asistencia a organismo
   público" -- TRASLADADA a H07 en S51, ya no vive en este anexo.**
   Miguel Ángel, verbatim: *"Esto en realidad forma parte del tema de
   partes de trabajo [...] modificaremos el tema de las vacaciones y
   modificaremos el tema de las ausencias de personal [...] ahora
   mismo lo tenemos puesto de una manera confusa."* Registrada en
   `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`, sección 8, ligada al
   selector `AbsenceCategory` (H07, 2.3) y al rediseño pendiente de
   vacaciones/ausencias (H24). No se vuelve a plantear en H30.

**PENDIENTE ANOTADO EN S51, SIN CONSTRUIR -- alta de sujeto nuevo
(centro de gasto/trabajador/EPI) ligada a la subida de su primera
documentación.** Miguel Ángel, verbatim: *"Es necesario poder dar de
alta centros de gasto con documentación [...] los trabajadores luego
serán extendidos a usuarios, de acuerdo, pero de momento solo van a
figurar como ítems, digamos, con fichas [...] es necesario poder dar
de alta EPIs, poder dar de baja EPIs, tener el CRUD de EPIs y ligarlo
todo con la documentación."* Verificado contra el código real en S51,
las tres piezas parten de un estado muy distinto:

- **Centro de gasto (`MachineAsset`, app `fleet`):** el CRUD YA
  EXISTE completo -- `MachineAssetCreateView`/`UpdateView`/
  `DeactivateView`/`ReactivateView`/`DeleteView` (`fleet/views.py`),
  restringido a `AdminRoleRequiredMixin` (solo admin, a diferencia de
  `DocsUploadAccessMixin` que abre a supervisor). `MachineAssetForm`
  solo exige `code`, todo lo demás es opcional. Lo que falta NO es el
  alta en sí, sino **enlazar** ese flujo ya existente con la subida
  de documentación (p. ej., tras crear la máquina, ofrecer subir su
  primer documento sin salir de la pantalla, mismo patrón que
  `SubjectDocumentUploadView`). Pieza pequeña relativa a las otras
  dos.
- **Trabajador (`PersonIdentity`, app `document_explorer`):** sin
  CRUD manual todavía -- existe únicamente alta automática cuando
  Gemini detecta un DNI nuevo en cuarentena (`classification_service.
  py`, ~línea 1425), con solo 3 campos (DNI, apellidos, nombre),
  carpeta `PTE CONTRATACION`, `source_entry` de origen. Miguel Ángel
  confirma que esto basta por ahora: el trabajador vive como "ficha"
  con su documentación, sin ser todavía un `CompanyUser` (el CRUD de
  usuarios YA existe y es una cosa distinta -- la extensión
  ficha→usuario queda para más adelante, sin fecha). Construir: alta
  manual desde el panel con los mismos 3 campos mínimos ya validados
  por el flujo automático.
- **EPI (`EpiItemCatalog` + `EpiDelivery`):** la pieza más grande de
  las tres, sin construir casi nada todavía. `EpiItemCatalog` (S046)
  documenta ya la intención de un atajo "+ nuevo EPI" en el propio
  desplegable del formulario de entrega -- pero **ese formulario de
  entrega no existe**, solo hay listados de solo lectura
  (`EpiTabFragmentView`/`EpiResultsFragmentView`). Miguel Ángel pide
  además: CRUD completo de tipos de EPI (alta/baja), ingesta desde
  Microsoft 365, ficha de EPI ligada al trabajador con fechas de
  entrega, y patrones de entrega periódica variables según el tipo
  (p. ej. dos mudas de ropa al año) -- esto último puede necesitar
  campo(s) nuevo(s) en `EpiItemCatalog` (periodicidad/cantidad
  esperada por año), sin decidir todavía.

**Contexto más amplio registrado (S51), para no perderlo:** ingesta
en curso de Microsoft 365 → cuarentena → `cgs_grupo_alvarez`, con
algunos documentos quedando en "no conformes"; centros de
gasto/personal ya dotados de documentación a nivel de BD, EPIs
todavía pendiente; y una limpieza de datos pendiente y distinta de
esto -- hay `MachineAsset` en BD que son obsoletos (vendidos/dados de
baja) generando "ruido"; el mecanismo de `is_active`/
`MachineAssetDeactivateView` ya existe, así que no es una pieza que
falte construir, es un repaso/depuración de datos reales pendiente de
hacer.

Miguel Ángel, verbatim, sobre el volumen de trabajo: *"El volumen de
trabajo es bastante grande."* Sin orden de prioridad fijado entre las
tres piezas ni con el resto de la hoja de ruta -- decidir en sesión
antes de construir cualquiera.

**ESTADO YA CERRADO — no volver a preguntar ni replantear:**
- Reconciliación de `MachineAsset`: CERRADA desde S49 (ver anexo).
- Tabla normativa `MANDATORY_BY_PREFIX` (documentos obligatorios por
  familia): CERRADA, incluye ya `IPO_ITC`. Ajustable, no redecidir.
- Diseño de familias de documentos (`DocumentTypeCatalog.family`):
  CERRADO.
- **`IPO`/`ITC`: CERRADO Y FUSIONADO** (migración 0031, S50) -- un
  solo tipo `IPO_ITC`, contenido real indistinguible.
- **Anomalía `pk 607`: RESUELTA en S50** -- carpeta desanidada,
  fusionada con `merge_folders`, verificada.
- **Mapa de alcance de maquinaria (`SCOPE` de
  `run_fase_a_sweep_scoped`): CERRADO, confirmado carpeta por
  carpeta con Miguel Ángel en S50.** No se vuelve a preguntar por
  familia -- solo se amplía si Miguel Ángel trae una carpeta nueva
  explícitamente.
- **El motor de alertas WhatsApp SÍ está conectado a
  `DocumentIndexEntry` desde S50** -- vía agente/cuarentena y subida
  manual, con el pipeline heurística→OCR→Gemini de fecha incluido.
  No es "trabajo pendiente" de fondo, ya está en producción.

**ORDEN DE TRABAJO VINCULANTE, sin cambios desde S49 -- NUNCA
saltarse:** heurística de nombre → OCR → Gemini/IA solo como último
recurso.

**Plan concreto de la próxima sesión, en este orden:**

1. **Comprobar el resultado de `local_ocr_classify.py --apply`**,
   corrido en local durante el cierre de S50 sobre ~2.670
   candidatos. Miguel Ángel estima ~30% de acierto real (~900
   documentos) -- confirmar la cifra real con el resumen del propio
   script (`tipo_resuelto_por_ocr`/`tipo_y_fecha_resueltos`/
   `sin_tipo_reconocible_en_ocr`) antes de decidir el siguiente
   paso. Criterio de cierre: número real confirmado, no estimado.
2. **Decidir qué hacer con el resto tras el punto 1** -- Miguel
   Ángel, verbatim (S50): "habrá que ver cuánta morralla tenemos
   ahí, y a ver cómo resolvemos para tener toda la documentación al
   día." Sin criterio de cierre fijado todavía -- decidir con datos
   reales delante al empezar este punto.
3. **Medir el alcance real de `FICHA_TECNICA` vs `ITV`** antes de
   tocar el catálogo -- cuántos de los `FICHA_TECNICA` actuales son
   por contenido real el documento oficial (deberían ser `ITV`)
   frente a los que son un tríptico de fabricante genuino. Criterio
   de cierre: conteo real con muestra de contenido OCR, nunca
   asumido por nombre de archivo.
4. **Decidir si se construye el barrido de renombrado retroactivo**
   (esquema fijo de `naming_service` aplicado al histórico ya
   clasificado) -- explicado el porqué a Miguel Ángel en S50, sin
   decisión tomada todavía sobre si merece la pena el riesgo/coste
   frente al beneficio.
5. **Backfill de fecha para el backlog histórico** (documentos
   `tracks_expiry=True` ya clasificados sin fecha, fuera del alcance
   de `local_ocr_classify.py` que solo resuelve TIPO) -- usar
   `expiry_resolution_service` (heurística→OCR→Gemini) contra el
   histórico, no solo contra ingesta nueva. Ligado a la pregunta 2
   de arriba (Gemini para `ocr_unreliable`).
6. **5 duplicados de seguro/OCA sin nombre coincidente**
   (P-22/8099JFK, B-33/9875GBF, A-34/E6460BCS, A-56/E8743BGW,
   X-15/5215MVF) -- arrastrados desde S50 sin decisión de Miguel
   Ángel todavía, bajo volumen, revisar cuando haya hueco.

**Resto de temas de fondo, sin tocar hasta que se prioricen
explícitamente (sin cambios respecto a sesiones anteriores, no
repetir la pregunta salvo que Miguel Ángel la traiga él mismo):**
- Cierre uno a uno de los 231 huecos reales de manuales.
- Decidir el destino final de `MachineDocument`/`PersonalDocument`
  (residuales) -- Miguel Ángel ya confirmó que se pueden borrar, solo
  falta ejecutar tras verificar que ningún flujo activo depende de
  ellos.
- DECA — horizonte octubre 2026, fuera de alcance activo salvo que
  Miguel Ángel lo priorice antes.
- Vacaciones controladas desde el panel (H24) — diseño explícitamente
  abierto por Miguel Ángel, sin alcance definido. No construir nada
  hasta que lo concrete él mismo.