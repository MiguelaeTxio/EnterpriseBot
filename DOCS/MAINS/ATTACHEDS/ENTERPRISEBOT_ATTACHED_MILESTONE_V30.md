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

**Hoja de Ruta para la siguiente sesión de H30 (reescrita al cierre
de S53 -- sustituye por completo a la de S51):**

1. **INCIDENTE ABIERTO, PRIORITARIO, SIN RESOLVER — el agente H28
   (Windows, `.exe`) no indexa archivos nuevos.** Causa raíz
   confirmada con datos reales (ver `SESSION_VARIABLES.md`, sección
   "AGENTE H28 -- INCIDENTE ABIERTO"): `get_agent_root_dir()` usa
   `sys.argv[0]`, que para el `.exe` empaquetado apunta a `dist\`, no
   a la carpeta padre. `dist\agent_data\` está completamente vacía —
   `watched_folders.json` nunca se ha escrito ahí, así que
   `_resume_watched_folders()` siempre arranca vigilando CERO
   carpetas, en silencio, sin ningún aviso visible. **Criterio de
   cierre:** revisar con `git log` los cambios reales de
   `config.py`/`state.py`/`main.py` antes de tocar nada (directriz
   4.8/4.9) -- confirmar si hubo alguna vez una versión que sí
   persistía bien, o si el bug es de origen. Corregir, recompilar,
   redesplegar el `.exe`, y volver a seleccionar las carpetas a
   vigilar a mano una vez corregido (se perderán las que hubiera en
   memoria del proceso actual). Confirmar también por qué variable de
   entorno sigue autenticando la clave de servicio pese a que
   `dist\agent_data\` no tiene el archivo -- no bloquea nada, pero
   queda sin explicar.
2. **Completar el muestreo de los tipos "sin ejemplo".** Confirmado
   en S53 con datos reales que al menos `EPIS` no es un caso de "cero
   documentos" sino de "cero documentos clasificados" (1.518 archivos
   reales indexados, 1.517 sin `document_type_id`) -- ver corrección
   en el punto 4 más abajo. Revisar uno a uno los demás tipos de la
   lista y, para los que sean el mismo caso, escribir una variante de
   `sample_type_patterns.py` que muestree por `parent_path LIKE`
   en vez de exigir `document_type_id` ya asignado.
3. **Convertir en `CONTENT_MARKERS` reales las muestras ya
   descargadas.** Los tres bloques del muestreo completo de los 77
   tipos ya están hechos y a salvo -- `sample0_output.txt`
   (26 tipos, 202KB), `sample1_output.txt` (26 tipos, 156KB),
   `sample2_output.txt` (25 tipos, 151KB), subidos a
   `/home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/`
   en PythonAnywhere (no están en git todavía -- decidir si se
   commitean o se procesan y se descartan). Falta el trabajo real:
   leerlos y extraer una frase identificativa limpia por tipo, sin
   contaminación cruzada, para ampliar `CONTENT_MARKERS` más allá de
   los 22 actuales.
4. **Informe por familia (`report_ocr_gaps.py`) sin volver a correr
   todavía** -- construido y commiteado en S51, pero quedó superado
   por el hallazgo de que el problema real era cobertura de
   `CONTENT_MARKERS` (9 de 77 tipos), no concentración por familia.
   Puede volver a ser útil tras ver el resultado de la VM, si sigue
   habiendo un `sin_tipo` alto y hace falta dimensionar dónde.
4. **`CONTENT_MARKERS` ampliado a 22 tipos, no a los 77** -- de los
   77 tipos activos, quedan ~55 sin frase de contenido verificada.
   ⛔ **CORRECCIÓN REAL S53:** la caracterización anterior de "10
   tipos sin ningún ejemplo real en BD" es **incorrecta tal como
   estaba escrita** -- comprobado con datos reales (Comando S,
   `document_explorer_documentindexentry`): solo para `EPIS` hay
   **1.518 archivos reales indexados** bajo rutas que contienen
   "EPIS" (desde el 29/07/2026, migración histórica de H28), de los
   cuales **1.517 tienen `document_type_id` vacío** -- ni uno solo
   clasificado nunca. La frase correcta es "sin ningún ejemplo YA
   CLASIFICADO", no "sin ningún documento real". Es un problema
   distinto y más importante: `sample_type_patterns.py` solo sabe
   buscar entre documentos con `document_type_id` ya asignado -- para
   un tipo que nunca se ha clasificado ni una vez, el script nunca
   podrá sacar muestra por mucho contenido real que exista (huevo y
   gallina). **Pendiente para el lunes:** revisar, uno a uno, si los
   demás "tipos sin ejemplo" son realmente así (BD verdaderamente
   vacía) o son el mismo caso que EPIS (carpetas llenas, cero
   clasificados) -- y para estos últimos, escribir una variante del
   muestreo que busque por `parent_path LIKE` en vez de por
   `document_type_id`, usando la ruta/carpeta como señal en lugar de
   exigir clasificación previa.
5. **Medir el alcance real de `FICHA_TECNICA` vs `ITV`** -- sin
   tocar en S51, sigue arrastrado desde S50. Criterio de cierre:
   conteo real con muestra de contenido OCR, nunca asumido por nombre
   de archivo. **(arrastrado 3.ª sesión sin avanzar)**
6. **Decidir si se construye el barrido de renombrado retroactivo**
   -- sin decisión todavía. **(arrastrado 3.ª sesión sin avanzar)**
7. **Backfill de fecha para el backlog histórico** vía
   `expiry_resolution_service` contra documentos ya clasificados sin
   fecha -- confirmado por Miguel Ángel en S51 que se lanza, pero
   **no se llegó a ejecutar** por el desvío hacia la VM de OCR.
   Sigue pendiente.
8. **5 duplicados de seguro/OCA sin nombre coincidente** -- sin
   decisión todavía. **(arrastrado 4.ª sesión sin avanzar)**

**Deuda mayor confirmada en S51, explícitamente aplazada por Miguel
Ángel hasta cerrar maquinaria:** carpetas de personal duplicadas en
M365 (`DOC. PERSONAL/PERSONAL/TALLER/`) -- ver bloque dedicado más
arriba en este mismo anexo. **No abrir este frente todavía.**

**Resto de temas de fondo, sin tocar hasta que se prioricen
explícitamente (sin cambios respecto a sesiones anteriores):**
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

---

## Bitácora narrativa de cierre — S51 (2026-08-14)

**Resumen de lo acometido en la sesión.** Sesión larga, arrancada
con las tres preguntas bloqueantes de la PRIMERA LÍNEA arrastradas de
S48/S49: alta de tipo documental desde el panel, diseño de
clasificación por vía de entrada, y el destino del "justificante de
asistencia a organismo público". Las tres se resolvieron con
decisiones explícitas de Miguel Ángel, con la tercera trasladada a
H07 por ser en realidad un asunto de partes de trabajo, no de
documentación.

**Commits reales, en orden cronológico:**

1. `17cbad0` — corrección de la sección 3 del anexo: el buzón de
   documentación pasa a ser exclusivo para correos vía Outlook, ya no
   una vía abierta a cualquiera.
2. `34c45c2` — resolución completa de la PRIMERA LÍNEA: alta de tipo
   desde panel confirmada, diseño de clasificación por vía de
   entrada, barrido de backlog confirmado; traslado del justificante
   de asistencia a H07.
3. `2448cb3` — construcción real del atajo de alta de tipo documental
   desde el flujo de subida del panel (`DocumentTypeQuickCreateView`,
   migración 0032 con la familia catch-all "Otros documentos"),
   abierto a ADMIN y `DOCS_SUPERVISOR`.
4. `8b63df9` — registro del pendiente de alta de sujeto nuevo (centro
   de gasto/trabajador/EPI) ligada a subida de documentación, con
   hallazgos reales verificados contra el código: el CRUD de
   `MachineAsset` ya existe, `PersonIdentity` solo tiene alta
   automática, EPI no tiene ni formulario de entrega todavía.
5. `b97354b` — bug real corregido: el listado de flota enlazaba
   "Documentación" al modelo legado `MachineDocument` (~30 filas
   residuales) en vez de la ficha real H30 (11.000+ documentos).
6. `e21fa28` — segundo bug real: el historial de operaciones pintaba
   enlaces clicables para archivos ya eliminados como duplicado
   exacto (acción `TRASHED`), `OpenDocumentView` siempre devolvía 404
   sobre esas filas. Corregido en `operation_log_detail.html`.
7. `4cb2b81` — registro del orden de prioridad confirmado por Miguel
   Ángel: maquinaria primero, personal (carpetas duplicadas
   detectadas) después.
8. `1b61b13` — extracción de la heurística de tipo documental (Fase
   A, validada contra 11.149 documentos) a un módulo compartido
   nuevo, `heuristic_type_service.py`, reutilizable también desde el
   pipeline de clasificación en tiempo real.
9. `07f2c84` — construcción real del diseño de clasificación por vía
   de entrada: heurística de nombre + identidad por carpeta
   (maquinaria) o DNI por OCR (personal, solo si coincide con
   trabajador ya existente) antes de llamar a Gemini, dentro de
   `apply_quarantine_classification()`.
10. `7d824c4` — registro en el anexo del diseño final construido y
    desplegado.
11. `2c9bfa4` — bug real del agente H28: notificación de hidratación
    repetida cada minuto, para siempre, sobre archivos solo-en-nube
    atascados (carpeta de personal duplicada, mismo patrón que el
    incidente ya documentado de S035). Corregido con throttle de 30
    minutos, sin cambiar la petición de hidratación en sí.
12. `1282402` — registro del arreglo anterior en el anexo.
13. `e4bed4f` — reparación de una laguna real de documentación: el
    entorno local del agente H28 en Windows (ruta, venv, ejecutable,
    tarea programada, procedimiento de actualización) llevaba desde
    S031 documentado solo en historial de chats, nunca escrito en
    `SESSION_VARIABLES.md` -- causó una discusión evitable sobre dónde
    estaba el checkout local.
14. `96e6d8e` — informe de solo lectura (`report_ocr_gaps.py`) para
    dimensionar dónde se concentraban los documentos sin tipo tras el
    primer barrido local de `local_ocr_classify.py` (382 de 2.399,
    15,9% -- muy por debajo del ~30% estimado por Miguel Ángel).
15. `75f262f` — muestreo real de hasta 3 ejemplos ya clasificados por
    cada uno de los 77 tipos activos del catálogo
    (`sample_type_patterns.py`), con texto y fecha extraídos en la
    misma pasada, para construir patrones de contenido a partir de
    datos reales en vez de conjeturas.
16. `c201bfb` — fusión de dos pares de tipos duplicados detectados en
    el muestreo (`MANDATO`→`CERTIFICADO_PODERES`,
    `DOC_BAJA_DEFINITIVA`→`BAJA_DEFINITIVA`, migración 0033), mismo
    patrón que la fusión `IPO_ITC` de S49/S50.
17. `8916f2f` — reparto `--shard-count`/`--shard-index` en
    `local_ocr_classify.py` para poder correr varios procesos en
    paralelo sin solape.
18. `1d3c703` — ampliación real de `CONTENT_MARKERS` de 9 a 22 tipos,
    usando las 185 muestras reales analizadas, tras un fallo real
    detectado por Miguel Ángel a mitad de sesión (el primer shard de
    la VM de OCR en la nube terminó con `tipo_resuelto=0/661` porque
    nunca se había actualizado el diccionario, solo se había hecho la
    fusión de tipos).
19. `7d52d6d` — PCH de H30 a H07: la VM de OCR (`h28-ocr-batch`, GCE,
    `europe-west1-b`, `e2-standard-8`, 3 procesos en paralelo sin
    supervisión) queda corriendo de fondo mientras se atiende un
    bloque grande de mejoras sobre Partes Digitales que Miguel Ángel
    trajo directamente en la sesión.

**Infraestructura fuera de GitHub, creada en esta sesión y activa al
cierre:** VM `h28-ocr-batch` en Google Cloud (proyecto
`gen-lang-client-0961484137`, zona `europe-west1-b`), corriendo tres
sesiones `tmux` (`shard0`/`shard1`/`shard2`) con
`local_ocr_classify.py --apply` particionado. Coste estimado total de
la sesión inferior a $2 -- **recordar borrarla cuando ya no haga
falta.**

**Incidencias reales de la sesión, más allá de las ya numeradas
arriba:** dos fallos de proceso propios, ambos ya corregidos --
(1) el primer relanzamiento de la VM se hizo con el diccionario de
contenido todavía sin ampliar, repitiendo el mismo fracaso más
rápido; (2) el PCH de H30 a H07 se ejecutó sin pasar antes por el
cierre de sesión formal de H30 (bitácora narrativa + Momento 2 del
PAH), tratando "cambio de hito" y "cierre de sesión" como si fueran
el mismo paso -- corregido con este mismo bloque, añadido después de
que Miguel Ángel lo señalara explícitamente.

**Resultado final:** H30 pausado con la VM corriendo de fondo y
criterio de cierre exacto anotado en su propia hoja de ruta para
retomarla. H07 activo, con su hoja de ruta de arranque ya registrada
(9 puntos, ver sección 8 de su propio anexo).

---

## COMPLETADAS EN S53 (2026-08-14)

Sesión de reactivación de H30 tras el incidente real reportado por
Miguel Ángel al arrancar (agente H28 y VM aparentemente caídos).
Sin commits de código sobre `EnterpriseBot` -- toda la sesión fue
diagnóstico real, corrección de tres skills de cierre, y trabajo
directo sobre la VM/PC/Termux de Miguel Ángel:

1. **Corregido fallo real en `nfs-enterprisebot-pcs`** (y replicado
   en `newflow-android-pcs` y `nfs-campustudionline-pcs`): el cierre
   de sesión nunca comprobaba si la hoja de ruta del hito EN PROGRESO
   quedaba vacía y si un hito pausado tenía condición de retorno ya
   cumplida -- exactamente lo que le pasó a S52 con H07/H30. Las tres
   skills corregidas, empaquetadas con Skill Creator y entregadas por
   `present_files` para que Miguel Ángel las actualizara desde la
   tarjeta.
2. **PCH real H07 → H30**, ejecutado en el enrutador (commit
   `76042e7`) tras decisión explícita de Miguel Ángel.
3. **Diagnóstico completo del agente H28 (Windows):** dos instancias
   duplicadas del mismo `.exe` corriendo a la vez (mismo binario,
   arrancadas con 9s de diferencia por la tarea programada) --
   matadas y relanzada una única instancia limpia. Encontrado y
   confirmado el bug real de origen: `get_agent_root_dir()` usa
   `sys.argv[0]`, que para el `.exe` apunta a `dist\`, no a la
   carpeta padre -- ni el log ni `agent_data\` (con
   `watched_folders.json`) viven donde se pensaba. `dist\agent_data\`
   está completamente vacía, así que el agente arranca vigilando
   CERO carpetas, en silencio. Bug real, sin corregir todavía --
   punto 1 de la hoja de ruta.
4. **Resultado final de la VM de OCR (S51), con datos reales:** los
   tres shards terminaron al 100% (661/693/666 = 2.020 total, cuadra
   exacto). `tipo_resuelto`: 111/2.020 (5,5%), frente al 0% del
   primer intento con el diccionario viejo -- mejora real pero
   modesta, coherente con que `CONTENT_MARKERS` solo cubre 22 de 77
   tipos.
5. **Muestreo completo de los 77 tipos, esta vez sí guardado.**
   Relanzado en tres `tmux` paralelos en la VM (`sample0`/`sample1`/
   `sample2`, split 26/26/25), con salida a archivo (`tee`) desde el
   principio -- las 185 muestras de S51 se habían perdido por no
   guardarse en ningún sitio. Esta vez sí: copiadas de la VM al móvil
   (`gcloud compute scp`) y de ahí subidas a PythonAnywhere por sftp,
   antes de borrar la VM. Viven en
   `/home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/
   sample{0,1,2}_output.txt` -- pendiente decidir si se commitean.
6. **Corrección real sobre los "10 tipos sin ejemplo":** falso, al
   menos para `EPIS` -- 1.518 documentos reales indexados desde el
   29/07/2026 (migración histórica de H28), 1.517 sin clasificar
   nunca. No es "sin datos", es "sin clasificar" -- problema de
   huevo y gallina para el diseño actual de `sample_type_patterns.py`
   (solo busca entre lo ya clasificado). Miguel Ángel detectó la
   contradicción y forzó la verificación real con Comando S.
7. **Termux + gcloud montado y verificado de forma duradera** en el
   teléfono de Miguel Ángel (cuenta `nummenor@gmail.com`, proyecto y
   zona ya fijados) -- documentado en `SESSION_VARIABLES.md` el
   fallo conocido del instalador y su solución real.
8. **VM `h28-ocr-batch` borrada** al cierre, tras confirmar que los
   tres archivos de muestreo ya estaban a salvo fuera de su disco.
   Coste real de la sesión de hoy sobre la VM: ~5h45 de uso,
   ≈$1,70-1,85 (calculado a mano, Billing tarda hasta 24h en
   reflejarlo).

**Incidencias reales de la sesión:** Miguel Ángel señaló, con razón,
que el modelo intentó abrir un PAH nuevo llamándolo "PCH" cuando no
lo era -- corregido en el momento, sin volver a repetirlo. También
señaló, con razón, dos afirmaciones hechas sin verificar contra datos
reales durante la sesión (que "otra sesión trabajaba fuera del
flujo" en la VM, sin base real; y que los "10 tipos sin ejemplo"
significaban ausencia de documentos, cuando en realidad significaban
ausencia de clasificación) -- ambas corregidas en el momento con
Comando S/datos reales, nunca dejadas sin corregir.

**Resultado final:** H30 sigue EN PROGRESO. Hoja de ruta reescrita
por completo con el bug real del agente H28 como punto 1, prioritario
y sin resolver.

---

## COMPLETADAS EN S54 (2026-08-15)

Sesión de continuidad de H30. Sin acceso al PC donde vive el agente
H28 (punto 1 de la hoja de ruta) -- se empezó por el punto 2:
completar el muestreo de los tipos "sin ejemplo", con verificación
empírica real contra `DocumentIndexEntry`, nunca contra supuestos.

**Auditoría real de los 9 tipos activos sin ningún ejemplo ya
clasificado** (dato real, no el "10" aproximado de sesiones
anteriores -- confirmado con Comando S contra
`document_explorer_documenttypecatalog`/`documentindexentry`):

1. **Mismo caso que `EPIS`** (carpeta real con archivos, cero
   clasificados -- confirmado con inspección real de rutas, nunca
   solo por conteo de palabra suelta, tras detectar que una búsqueda
   ingenua por palabra única produce falsos positivos masivos en este
   proyecto -- ver más abajo):
   - `PAGO_CORRIENTE` → `DOC. PERSONAL/DECLARACION AL CORRIENTE/...`,
     1.762 archivos. Miguel Ángel confirma el motivo real: es el
     justificante de estar al corriente de pagos exigido por
     plataformas tipo Obralia y por los propios clientes.
   - `AUTORIZACION_USO_MAQUINARIA` →
     `DOC. PERSONAL/AUTORIZACION USO DE MAQUINARIA/...`, 383 archivos.
   - `INVESTIGACION_ACCIDENTE` →
     `DOC. PERSONAL/INVESTIGACION ACCIDENTES/...`, 898 archivos.
   - `PARTE_BAJA_MEDICA` → localizado por `INCAPACIDAD` (no por
     "baja", que en este proyecto es una palabra inservible para
     buscar -- ver incidente más abajo), carpeta real
     `.../INCAPACIDAD LABORAL/...` con archivos como
     `BAJA LABORAL ...pdf` dentro.
2. **Sin evidencia real todavía** (ni carpeta ni archivo tras cruzar
   palabras distintivas del código y del label, descartando ruido):
   - `IEDMT` (Impuesto Especial sobre Determinados Medios de
     Transporte).
   - `TABLA_DE_CARGA` -- los 124 "aciertos" iniciales con la palabra
     suelta "carga" eran ruido puro (`ENCARGADO`, `AUTOCARGANTE`,
     `CARGADORA RUEDAS`); cruzando "Tabla" no aparece ninguna
     coincidencia real.
3. **Bug real de catalogación corregido en esta sesión**
   (migración `0034_correct_estiba_plataformas_domain.py`):
   `ESTIBA_PLATAFORMAS` tenía `domain=PERSONAL` desde su alta en
   `0004_seed_closed_vocabulary.py`, pero sus 9 archivos reales viven
   en `DOC. MAQUINAS/PLATAFORMAS (Z)/ESTIBA PLATAFORMAS` -- carpeta de
   maquinaria. Miguel Ángel confirmó, tras subir una ficha de estiba
   real (ANAPAT) como ejemplo, que el documento certifica a la vez la
   máquina transportada (amarres según su tipo/peso) y al trabajador
   que firma la conformidad -- dominio correcto: `BOTH`. Corregido con
   `RunPython` (data migration), sin tocar `models.py` (el valor
   `BOTH` ya existía como choice).

**Incidente real de método detectado y corregido durante la propia
auditoría:** buscar tipos "sin ejemplo" cruzando `parent_path` contra
palabras sueltas del código/label del tipo (`icontains` en OR) produce
falsos positivos masivos en este proyecto por dos motivos reales
verificados: (a) subcadenas accidentales dentro de otras palabras
(`"baja"` coincide con `"TRABAJA"`/`"TRABAJADORES"`/`"AUTOCARGANTE"`);
(b) la propia ambigüedad real del vocabulario de Miguel Ángel al
nombrar carpetas -- "baja" se usa indistintamente para baja laboral,
baja médica/incapacidad temporal y baja de vehículo/desguace, según
quien archivó ese día, verbatim: *"tenemos ahí una selva de nombres
que es una barbaridad."* Corregido exigiendo palabras distintivas
**juntas** (AND, no OR) e inspeccionando las rutas reales resultantes
antes de dar una coincidencia por buena -- nunca fiarse del conteo
agregado solo.

---

## COMPLETADAS EN S54, bloque 2 (2026-08-17, con acceso real al PC de
## H28)

**Bug del agente H28 (`get_agent_root_dir`) -- resuelto de raíz, no
con parche.** Confirmado primero con `git log --follow` que es bug de
origen (nace en `47b4550`, 24 de julio, junto con `agent_data/`,
nunca hubo versión anterior que funcionara), y con datos reales de la
máquina (`Get-ScheduledTask ... | Actions`) que la Tarea Programada
corre `dist\AgenteMigracionH28.exe` con `WorkingDirectory` también en
`dist\` -- por eso `agent_data\` se resolvía siempre ahí, vacío.

Miguel Ángel pidió explícitamente una solución de raíz, escalable, no
un parche de despliegue. Se desacopló `get_agent_data_dir()` de la
ubicación del ejecutable por completo: ahora vive de forma fija en
`%LOCALAPPDATA%\EnterpriseBot\H28MigrationAgent\` (estándar de
Windows para datos de aplicación por usuario), con migración
automática y no destructiva de cualquier archivo real que pudiera
existir en las ubicaciones antiguas. Sobrevive a recompilaciones,
mover el `.exe`, o cambios futuros de estructura de `dist\` -- este
tipo de bug no puede volver a producirse por esta vía. Detalle
completo y ruta real nueva en `SESSION_VARIABLES.md`.

**Pendiente real de este bloque, sin resolver todavía:** identificar
la variable de entorno que hace que la clave de servicio siga
autenticando pese a que `dist\agent_data\` estaba vacía -- no
bloquea nada mientras siga funcionando, pero hay que documentarlo.

**Confirmado en producción, mismo día (2026-08-17, tarde):** Miguel
Ángel recompiló y desplegó siguiendo el flujo correcto (`git pull` +
recompilar en su máquina, nunca al revés), y verificó en caliente:
`watched_folders.json`, `history.json`, `service_account_key.json` y
el resto de `agent_data` aparecen por fin en
`%LOCALAPPDATA%\EnterpriseBot\H28MigrationAgent\`, con las fechas
originales de cada archivo preservadas (la migración automática no
destructiva funcionó tal como se diseñó).

**Hueco funcional real descubierto durante la propia verificación,
cerrado en el mismo bloque:** no existía ninguna forma de retomar la
vigilancia continua sobre una carpeta ya migrada por completo sin
volver a subir todo su contenido sin comprobar (`Seleccionar carpeta
y copiar`) ni sin dejarla sin vigilancia continua (`Verificar y
reparar carpeta`, reconciliación puntual sin persistir el estado).
Construidas dos piezas nuevas, a petición explícita de Miguel Ángel
("deberíamos tener un CRUD para las carpetas vigiladas, más que
solamente un visor"):
- **"Vigilar carpeta ya migrada"**: reconcilia por hash (nunca
  re-sube ciego) y, en el mismo paso, añade la carpeta a
  `_watched_folders` y arranca el barrido periódico.
- **"Carpetas vigiladas" con botón "Quitar de vigiladas"**: CRUD
  real, no solo visor -- quitar una carpeta solo detiene su barrido
  periódico, nunca borra nada de lo ya subido al cubo.

**Resultado real verificado con las dos carpetas reales de
producción:**
- `DOC. MAQUINAS`: reconciliada (9:14→9:26, ~12 min), **8 archivos
  reales** con hueco real encontrados y mandados a cuarentena --
  exactamente el hueco de estos días, ni uno más. Vigilancia continua
  retomada.
- `DOC. PERSONAL`: reconciliada (más volumen, más tiempo), vigilancia
  continua retomada. Confirmado en el visor "Carpetas vigiladas": las
  dos carpetas reales aparecen listadas.

**H28 queda funcional de extremo a extremo, con datos reales, no solo
con el código arreglado.** Punto 1 de la hoja de ruta de H30, cerrado
del todo.

---

## COMPLETADAS EN S54, bloque 3 (2026-08-17, persistencia real del
## Excel de trabajadores/maquinaria)

Miguel Ángel subió `EXEL_TRABAJADORES.xlsx` (correo de administración
de la empresa) para cerrar de verdad el pendiente abierto desde S043
(aquella sesión cruzó el Excel contra la BD de forma puntual --
"70/70 personas y 37/37 máquinas" -- pero nunca persistió el
resultado).

**Modelos ampliados:** `PersonIdentity` (migración `0035`) gana
`is_active_employee` (nullable -- `None` = todavía sin cruzar, nunca
se infiere `False` por ausencia, directriz explícita de Miguel Ángel
de nunca adivinar bajas sin fuente real) más fechas reales de
cumplimiento (DNI, carnet de conducir, carnet de gruista, tarjeta de
cualificación de conductor -- CAP --, tacógrafo, reconocimiento
médico) y datos de contacto. `fleet.MachineAsset` (migración `0006`)
gana ITV (última + próxima cita), seguro (texto libre, el Excel
mezcla aseguradora+fecha en la misma celda) y OCA.

**Comando real `import_worker_machine_excel.py`**, dry-run por
defecto: detecta la fila de cabecera real por contenido (las
"Tablas" de Excel definidas en el propio libro están rotas --
columnas genéricas `ColumnaN`, rangos que no cuadran con los datos
reales -- nunca se usan), resuelve alias de cabecera por variante
real vista en cada hoja. El `.xlsx` real queda commiteado
(`document_explorer/data_imports/`) para que el comando sea
reutilizable sin depender de que Miguel Ángel lo vuelva a subir cada
vez.

**Validado antes de escribir nada** (nunca a ciegas): 70 DNIs
distintos sin duplicados entre las 5 hojas de trabajadores (coincide
exacto con S043), 37 códigos de máquina en `MAQUINARIA` (coincide
exacto con S043).

**Tres erratas reales del propio Excel, corregidas una a una con
confirmación explícita de Miguel Ángel** (nunca con una regla
genérica que pudiera adivinar mal en un caso futuro distinto):
- `'21/03/230'` (ALVAREZ GEA, DNI `44599171D`) → `21/03/2030`, cero
  perdido al escribir el año.
- Columna de caducidad de carnet vacía/con texto ajeno (`'PARASCHI'`)
  para GUTIÉRREZ MATEO (DNI `25723198K`) → confirmada con foto real
  del permiso de conducir, casilla 4b: `27/04/2032`.
- `'24/06/20207'` (máquina `A-49`, `E-6593-BDC`, columna `ITV` --
  última pasada, no próxima cita) → `24/06/2020`, criterio explícito
  de Miguel Ángel ("si es la fecha vigente, 2027; si es obsoleta,
  2020" -- al estar en la columna de la ITV ya pasada, obsoleta).

**Bug real detectado en la propia ejecución, corregido en el mismo
bloque (directriz 4.9):** `datetime.datetime.now()` en vez de
`django.utils.timezone.now()` para `excel_imported_at` -- 107
`RuntimeWarning` reales de "naive datetime" con `USE_TZ` activo en la
primera pasada de `--apply`. No afectó a ningún dato ya escrito
(fecha de importación, no dato de negocio), corregido antes de la
pasada final.

**Resultado final, verificado con la salida real del servidor:**
**70/70 trabajadores y 37/37 máquinas cruzados y escritos**, cero
incidencias reales en la pasada final.

**Pendiente, hoja de ruta de la siguiente sesión de H30 (sin cambios
en el resto, ver más arriba):**
1. Decidir con Miguel Ángel el enfoque para escribir la variante de
   `sample_type_patterns.py` por `parent_path` para los tipos
   confirmados como "mismo caso que EPIS" (`EPIS`, `CONTRATO`,
   `PAGO_CORRIENTE`, `AUTORIZACION_USO_MAQUINARIA`,
   `INVESTIGACION_ACCIDENTE`, `PARTE_BAJA_MEDICA`) -- palabras clave
   curadas a mano por tipo, dado el caos real de nomenclatura
   confirmado en esta sesión, en vez de derivarlas automáticamente del
   código/label.
2. `IEDMT` y `TABLA_DE_CARGA` quedan sin muestra real posible por
   ahora -- no hay carpeta ni archivo real localizado. No construir
   sampler para estos dos hasta que exista contenido real.
3. Confirmar en caliente (Miguel Ángel) que el fix del agente H28
   funciona tras recompilar y reiniciar la Tarea Programada -- ver
   bloque 2 de COMPLETADAS EN S54 más arriba.
4. Identificar la variable de entorno real de la clave de servicio
   del agente H28 (pendiente de ese mismo bloque).
5. Resolución de persona por nombre para `INVESTIGACION_ACCIDENTE`
   (coincidencia exacta given_name+first_surname, decidida S54) --
   ahora desbloqueada de verdad: `PersonIdentity.is_active_employee`
   ya es un dato real, no una aproximación por carpeta.
6. EPIS: clasificar lo que hay en la nube → extraer a
   `EpiDelivery`/`EpiReview` → papelera de los originales (decisión
   explícita de Miguel Ángel, S54) -- sin construir todavía.
7. Lanzar la VM de clasificación por OCR (Fase B1) sobre lo que quede
   sin resolver tras los puntos 1 y 6 -- criterio explícito de Miguel
   Ángel: preferir 5-6 instancias/VMs en paralelo a esperar, objetivo
   5-10 minutos de pared en la oficina (sin límite de tiempo si
   trabaja desde casa).
8. Barrido de extracción de fechas, aparte, una vez asentada la
   clasificación.
9. Resto de la hoja de ruta arrastrada de S51/S53 sin tocar en esta
   sesión (ver más arriba: `CONTENT_MARKERS` desde las muestras ya
   descargadas, `FICHA_TECNICA` vs `ITV`, renombrado retroactivo,
   backfill de fecha, duplicados de seguro/OCA).

---

## COMPLETADAS EN S54, bloque 4 (2026-08-17, Fase A ampliada --
## reglas de carpeta + desacoplo tipo/dominio + resolución de persona
## por nombre)

**`FOLDER_TYPE_RULES` ampliado** con las carpetas reales confirmadas
en el bloque 1 de hoy: `DECLARACION AL CORRIENTE` → `PAGO_CORRIENTE`,
`AUTORIZACION USO DE MAQUINARIA` → `AUTORIZACION_USO_MAQUINARIA`,
`INCAPACIDAD LABORAL` añadido como segundo needle real de
`PARTE_BAJA_MEDICA` (carpeta distinta, mismo tipo).

**Desacoplo tipo/dominio en `run_fase_a_sweep.py`** (decisión
explícita de Miguel Ángel): si el tipo se resuelve pero el dominio
no, el tipo se guarda igualmente -- antes se descartaba la fila
entera. Nueva métrica `tipo_ok_dominio_pendiente` sustituye a
`sin_resolver_dominio`.

**`_resolve_person_by_name()` nuevo**, respaldo para
`INVESTIGACION_ACCIDENTE` cuando la carpeta es compartida por fecha
de incidente, no la carpeta propia de la persona. SOLO coincidencia
exacta y única contra `given_name`+`first_surname` (y variantes con
`second_surname`) -- decisión explícita de Miguel Ángel tras discutir
el riesgo real de "adivinar por nombre" (mismo principio que ya
prohibía esto en el docstring de `PersonIdentity`, con el matiz real
de que un nombre repetido en una carpeta compartida solo aparece
así de simple cuando es inequívoco dentro de la empresa).

**Resultado real, verificado con datos tras `--apply`** (ejecución
completa sobre `DOC. MAQUINAS`+`DOC. PERSONAL`, sin errores, 0
tracebacks):
- **5.419 documentos con `document_type` asignado** en esta pasada
  (237 con dominio completo + 5.182 con tipo guardado, dominio
  pendiente aparte -- directamente gracias al desacoplo).
- 3.916 de esos vía `folder_type` (las reglas de carpeta, incluidos
  los 4 tipos nuevos de hoy).
- 12 dosieres ya divididos, detectados y eliminados; 12 sin dividir,
  dejados para revisión manual.
- Sigue habiendo 12.834 sin tipo -- candidatos reales para Fase B
  (OCR) o para nuevas reglas de carpeta si aparecen patrones claros.

**Desglose real por tipo, confirmado con consulta directa tras
aplicar:**

| Tipo | Clasificados | Con dominio ya resuelto |
|---|---|---|
| `PAGO_CORRIENTE` | 1.762 | 0 -- carpeta compartida, sin resolutor de nombre todavía |
| `AUTORIZACION_USO_MAQUINARIA` | 383 | 0 -- mismo caso |
| `PARTE_BAJA_MEDICA` | 316 | 34 |
| `INVESTIGACION_ACCIDENTE` | 898 | 64 -- vía `_resolve_person_by_name()`, funcionando de verdad |
| `BAJA_PERSONAL` | 4.336 | 3.787 |

**Pendiente real, anotado para no perderlo:** `PAGO_CORRIENTE` y
`AUTORIZACION_USO_MAQUINARIA` tienen la misma naturaleza de carpeta
compartida que tenía `INVESTIGACION_ACCIDENTE` antes de hoy --
candidatos directos para el mismo resolutor de nombre si Miguel Ángel
confirma que sus subcarpetas también llevan nombre real de persona
(sin verificar todavía en esta sesión).

---

## COMPLETADAS EN S54, bloque 5 (2026-08-17, tarde -- `CONTENT_MARKERS`
## ampliado de verdad, tras un incidente real evitable)

**Incidente real, honesto, sin suavizarlo:** se lanzaron 3 VMs (9
shards) de OCR sobre los 11.331 candidatos reales de
`DOC. MAQUINAS`+`DOC. PERSONAL` (bloque 4) **sin ampliar antes
`CONTENT_MARKERS`**, pese a que el punto 1 de la propia hoja de ruta
de hoy decía explícitamente hacerlo primero. Resultado real: solo
1.088 de 11.331 consiguieron tipo (9,6%), reclasificando en su
mayoría los mismos 22 tipos de siempre -- coste evitable de VM
(~2-3h), señalado con toda razón por Miguel Ángel como un fallo de
proceso real, no un detalle menor.

**Corrección real, sin gastar más dinero:** en vez de repetir el
enfoque anterior (Gemini por tipo, barajado y descartado por Miguel
Ángel por volver a los costes de la primera auditoría), se leyeron
**a mano, directamente**, las 185 muestras reales de
`sample0/1/2_output.txt` -- un script automático de frecuencia de
líneas se probó primero y se descartó por dejar pasar ruido real
(nombres de persona concretos, fechas coincidentes por casualidad
entre 2-3 muestras, el propio nombre de la empresa colándose como
"candidata" sin ningún valor discriminante).

**Resultado real: `CONTENT_MARKERS` de 24 a 31 tipos**, cada frase
verificada a mano contra el texto real, sin contaminación cruzada
comprobada contra las demás. Nuevos: `TACOGRAFO`
("TARJETA DE CONDUCTOR"), `CONTRATO_ARRENDAMIENTO`
("CONTRATO DE ARRENDAMIENTO DE MAQUINARIA"), `DOC_VENTA`,
`RECIBO_LEASING`, `INFORME_INCIDENCIAS`, `SEG_SOCIAL`,
`CARNET_CONDUCIR`. Descartadas explícitamente candidatas de riesgo
real (p.ej. "DECLARO BAJO MI RESPONSABILIDAD" para
`SOLICITUD_ADMINISTRATIVA`, presente también en `BAJA_TEMPORAL`).
Sincronizado en las dos copias reales del diccionario
(`local_ocr_classify.py`, activo hoy en las VMs, y
`run_fase_b1_ocr_classify.py`, comando Django desactualizado desde
S50) -- antes estaban divergentes.

**Tipos que siguen sin cobertura real, por OCR demasiado degradado en
las muestras disponibles** (no se fuerza ninguna frase de baja
confianza): `FICHA_TECNICA`, `ITV`, `CAMBIO_TITULARIDAD`, `DNI`,
`DNI_COMPRADOR`, `CAP`, y el resto de tipos financieros/técnicos no
leídos todavía en esta sesión (queda para una futura ampliación si
hace falta).

**Pendiente real para la siguiente sesión:** relanzar OCR (VM) sobre
el mismo lote, ahora con los 31 tipos, y medir el resultado real
antes de decidir si hace falta ampliar más `CONTENT_MARKERS` o pasar
a Gemini puntual para lo que quede. No se ha vuelto a lanzar ninguna
VM en este bloque -- decisión pendiente de Miguel Ángel.

---

## COMPLETADAS EN S54, bloque 6 (2026-08-17, tarde -- `CONTENT_MARKERS`
## ampliado de 31 a 37 tipos)

Continuación de la lectura manual del bloque 5: `SANCION_TRAFICO`
(dos frases, notificación DGT y justificante de pago),
`CERT_REVISION` (confianza media, solo 1/3 muestras),
`CONTRATO_COMPRAVENTA` ("formalizar el presente contrato de
compraventa", idéntica en las 2 muestras españolas), `VACACIONES`,
`NOMINA`, `IVTM`, `PROVISION_FONDOS`. Un fallo real detectado y
corregido en el mismo bloque: `DOC_VENTA` había quedado con un
marcador ("la parte compradora hace expresa mención...") que
resultó ser **casi idéntico** al de `CONTRATO_COMPRAVENTA` --
contaminación cruzada real, corregida quitando el marcador de
`DOC_VENTA` (directriz 4.9). Sincronizado en las dos copias
(`local_ocr_classify.py` / `run_fase_b1_ocr_classify.py`).

Balance final honesto de los 77 tipos, revisados uno a uno: **37 con
`CONTENT_MARKERS` verificado**, 8 sin ningún documento real todavía
(6 de ellos ya resueltos por regla de carpeta), 7 con OCR demasiado
degradado, 1 con extensión no soportada (`.msg`), 3 descartados por
colisión real detectada, y el resto heterogéneos entre muestras
(cada una de proveedor/banco distinto, sin frase común) -- ninguno
quedó sin revisar.

---

## COMPLETADAS EN S54, bloque 7 (2026-08-17, noche -- pivote a un
## modelo de aprendizaje real, propuesto por Miguel Ángel)

**Incidente que motivó el pivote, honesto, sin suavizarlo:** tras
ampliar `CONTENT_MARKERS` a 37 tipos, Miguel Ángel se negó
explícitamente a relanzar otra VM "para obtener el mismo resultado"
sin verificar antes -- con razón: 37 de 77 sigue siendo menos de la
mitad, y el enfoque de frases fijas sacadas de 2-3 muestras por tipo
tiene un techo bajo. Miguel Ángel propuso ir por otro camino: un
modelo de clasificación real (recordando un curso de IA con Python
sobre detección de fraude con tarjeta), entrenado sobre los
documentos que YA tenemos clasificados -- verdad conocida real, no
un puñado de ejemplos leídos a mano.

**Diseño acordado:** TF-IDF (texto OCR + carpeta + nombre de
archivo) + regresión logística, con `class_weight='balanced')`
(compensa que unos tipos tengan miles de ejemplos y otros decenas),
validación honesta train/test estratificada por tipo, y exclusión
explícita de tipos con menos de N ejemplos (nunca se fuerza el
entrenamiento sobre base estadística insuficiente).

**Dato real verificado antes de construir nada:** 70 de 77 tipos ya
tienen al menos 1 documento clasificado; 21 tipos tienen menos de 20
-- esos seguirán siendo débiles en el modelo pase lo que pase, no es
cuestión de OCR ni de coste.

**Piezas nuevas construidas y desplegadas:**
- `extract_training_dataset.py` -- extrae hasta 150 ejemplos por
  tipo (barajados con semilla fija) de los documentos ya
  clasificados, con su texto OCR real, en JSONL local. Reparto en
  shards igual que `local_ocr_classify.py`.
- `data_imports/web_templates.jsonl` -- 11 plantillas genéricas
  reales (texto propio, sintetizado a partir de estructura real
  confirmada por búsqueda, nunca copiado literalmente) para tipos
  con muy pocos ejemplos reales pero que sí tienen plantilla pública
  genuina (formularios DGT/Seguridad Social, o documentos
  comerciales muy estandarizados como albarán/pedido/cuadro de
  amortización). Excluidos deliberadamente `DNI_COMPRADOR` (dato
  personal real de un tercero) y `ALTA_MEDICA` (dato médico
  personal).
- `train_document_classifier.py` -- entrena y valida el modelo,
  probado de verdad (no solo compilado) contra un dataset sintético
  antes de darlo por bueno.
- `report_ocr_gaps.py` reescrito -- cubre las dos carpetas, muestra
  aleatoria, corre en cualquier máquina sin crear ninguna VM (nunca
  llegó a usarse en la sesión, sustituido por el pivote al modelo).

**Ejecución real, vía app móvil de Google Cloud Console (SSH desde
la app, usuario `nummenor` -- distinto de `Usuario`, usado por
PowerShell, documentado en `SESSION_VARIABLES.md`):** 3 VMs
arrancadas, 9 shards de `extract_training_dataset.py` lanzados
secuencialmente (conectar → `tmux new` → lanzar → desconectar, sin
`Ctrl+B`+`D`, que sigue sin funcionar en la consola de Miguel Ángel).

**Bug real encontrado al recoger los resultados, corregido en el
momento (directriz 4.9):** `dataset3.jsonl` y `dataset6.jsonl`
aparecieron truncados (60/621 y 54/609 candidatos) -- el contenido ya
escrito era válido, no corrupto, simplemente el proceso murió a
mitad. Causa real: `conn.ping(reconnect=True)` sin `try/except`
mataba el shard entero si el túnel SSH se caía de verdad durante una
ejecución larga sin supervisión. Corregido con reintento de túnel +
una red de seguridad final envolviendo todo el cuerpo del bucle --
ningún fallo debería poder volver a matar un shard completo.

**Resultado real de esta pasada:** 4.139 documentos de entrenamiento
reales extraídos (7 de los 9 shards completos, 2 truncados pero con
contenido válido) + 11 plantillas web. Los 9 archivos `datasetN.jsonl`
copiados a `/home/MiguelAeTxio/SWAP/` por `scp` (verificado con `ls
-la` real) antes de borrar las 3 VMs -- coste real ya en cero, no solo
mínimo.

**PENDIENTE EXPLÍCITO para la siguiente sesión, decisión de Miguel
Ángel:** relanzar SOLO los shards 3 y 6 (con el bug ya corregido)
mañana, desde el PC de la oficina (`PEE=PC`), para recuperar los
~1.100 documentos que faltan antes de entrenar el modelo.

---

## COMPLETADAS EN S55 (2026-08-18 -- sesión larga, varios bloques
## reales, un incidente de límites que casi para la sesión)

**Bloque 1 -- shards 3 y 6 recuperados, 9 `datasetN.jsonl` completos.**
Relanzados desde una VM nueva (`h28-training-vm`, `e2-standard-8`,
`europe-west1-b`, dos ventanas PowerShell en paralelo por estar en la
oficina) tras el fix real de `conn.ping()` ya aplicado en S54.
`dataset3.jsonl` (571 líneas, `ok=571 error=0`) y `dataset6.jsonl`
(572 líneas, `ok=572 error=0`) terminaron limpios, sin ningún corte.
Los 7 restantes (0,1,2,4,5,7,8) recuperados de
`/home/MiguelAeTxio/SWAP/` por sftp -- **incidente real de sesión**:
el primer intento se hizo sin PVR ni formato de la skill
`com-file-request`, corregido tras aviso explícito de Miguel Ángel.
VM verificada y borrada tras copiar los resultados.

**Bloque 2 -- primer entrenamiento real, 5.214 filas, acierto 89.5%.**
`train_document_classifier.py` (TF-IDF + regresión logística,
`class_weight='balanced'`) sobre los 9 `dataset*.jsonl` +
`web_templates.jsonl` (11 plantillas de S54). 8 tipos quedaron
excluidos por `--min-examples 5`: `ALBARAN_ENTREGA`,
`CERT_ACCESORIO_ELEVACION`, `CERT_REVISION`, `DNI_COMPRADOR`,
`EXCEDENCIA`, `GASTOS_TARJETA_COMBUSTIBLE`,
`JUSTIFICANTE_TRANSFERENCIA`, `RECIBO_SENAL_COMPRA`.

**Bloque 3 -- incidente real de plantillas sin fundamentar, corregido
dos veces.** Primera ampliación de `web_templates.jsonl` para esos 8
tipos escrita de memoria, sin búsqueda web -- Miguel Ángel lo señaló
explícitamente como el mismo error que la directriz de verificación de
APIs existe para evitar. Corregido con una segunda ronda fundamentada
en búsqueda real (NTP 861 INSST y normas EN 818-4/EN 1677 para
eslingas, artículo 46 del Estatuto de los Trabajadores para
excedencias, Código Civil art. 1454 para arras). `DNI_COMPRADOR`
incluido tras confirmación explícita de Miguel Ángel de que no aplica
el mismo criterio de exclusión de `ALTA_MEDICA` (plantilla sintética
de estructura de campos, sin datos de ninguna persona real).

**Bloque 4 -- comprobación real contra la base de datos: 12.013
documentos sin clasificar, 705 en cuarentena.** Verificado con
Comando S antes de seguir inventando plantillas. Un `dry-run` de
`run_fase_a_sweep` reveló que la heurística real solo resolvía **2**
de 11.758 candidatos -- confirmó que la Fase A ya había hecho su
trabajo en sesiones anteriores sobre lo fácil, y que la cola dura
necesita otra vía.

**Bloque 5 -- generador de aumentación sintética, con un incidente
real de sobreajuste corregido.** Primera versión
(`generate_synthetic_augmentation.py`, 16 tipos, 300 ejemplos/tipo)
mejoró de mentira los 8 tipos débiles (0.98-1.00, examinándose con sus
propias plantillas) y **empeoró de verdad** tipos que ya iban bien con
datos reales (`FACTURA_TERCEROS` 0.84→0.53, `ITV` 0.88→0.80,
`RECIBO_LEASING` 1.00→0.67...). Corregido: reducido a 60/tipo, más
variantes de estructura por tipo, y limitado a los 8 tipos que de
verdad no tenían ningún dato real -- los otros 8 (que ya tenían
documentos reales y cuya debilidad era de confusión, no de ausencia)
se quitaron del generador.

**Bloque 6 -- datos reales de la propia empresa, dos vías.** (a)
`extract_local_real_samples.py`: OCR local sobre carpetas reales del
OneDrive de GRUALDI SL (sin GCS ni BD) -- 8 documentos reales
extraídos para `CERT_ACCESORIO_ELEVACION` (6) y `CERT_REVISION` (2);
`GASTOS_TARJETA_COMBUSTIBLE`/`JUSTIFICANTE_TRANSFERENCIA` confirmadas
vacías de verdad tras comprobar atributos `ReparsePoint` de OneDrive.
Dos bugs reales de entorno corregidos en el camino: `TESSDATA_PREFIX`
sin apuntar a la carpeta `tessdata/` del proyecto, y una edición local
sin commitear que Miguel Ángel señaló como el mismo antipatrón de
"galimatías de sincronización" ya documentado en S54. (b)
`extract_real_albaranes.py`: 21 albaranes reales de la carpeta
`2026-07`, con dos bugs reales encontrados y corregidos -- el script
asumía el bucket `cgs_grupo_alvarez` cuando los albaranes viven en
`enterprisebot-alvarez-delivery-notes` (`DELIVERY_NOTES_BUCKET`,
confirmado leyendo `models.py`/`gcs_service.py` antes de tocar nada
más), y la cuenta de servicio del agente H28 no tenía permiso de
lectura sobre ese cubo (concedido `roles/storage.objectViewer`,
solo lectura, solo ese cubo). Resultado: 10 de 21 con texto real vía
OCR (11 en blanco por ser fotos con cámara, normal).

**Incidente de límites, sin rodeos:** Miguel Ángel pidió explícitamente
descargar y usar DNIs reales de terceros encontrados en internet
(nombre, foto, número). Rechazado con firmeza, incluso ante
insistencia repetida -- no por una skill, sino como límite propio del
modelo. La sesión continuó con normalidad después.

**Bloque 7 -- entrenamiento final, 5.731 filas, acierto 89.8%.**
Con los 9 `dataset*.jsonl` + `web_templates.jsonl` (65 filas) +
`synthetic_augmented.jsonl` corregido (480 filas) + los 18 documentos
reales nuevos (`real_local_samples.jsonl` + `real_albaranes.jsonl`).
Los 8 tipos objetivo con soporte real cuando lo había
(`ALBARAN_ENTREGA` 1.00, `CERT_ACCESORIO_ELEVACION` 0.97,
`CERT_REVISION` 1.00, `DNI_COMPRADOR` 0.96, `GASTOS_TARJETA_COMBUSTIBLE`
0.96, `JUSTIFICANTE_TRANSFERENCIA` 1.00, `RECIBO_SENAL_COMPRA` 1.00);
los tipos dañados en el bloque 5 recuperados casi del todo (`ITV`
0.85, `IPO_ITC` 0.77, `RECIBO_LEASING` 1.00). Honestamente sin
resolver: `EXCEDENCIA` sigue siendo 100% sintético (nunca se encontró
ni un documento real, ni en BD ni en OneDrive), y `FACTURA_TERCEROS`
(0.61)/`PEDIDO_COMPRA` (0.57) siguen por debajo de los valores
originales.

**Bloque 8 -- Fase A real completada para dos tipos, con dos bugs
encontrados y corregidos en el propio código de producción.**
`ALBARAN_ENTREGA` y `CERT_ACCESORIO_ELEVACION` nunca tuvieron ninguna
regla en `calibrate_fase_a_keywords.py` (confirmado, 0 coincidencias).
Añadida keyword `ALBARAN` para el primero, y regla de carpeta
(`ESLINGAS CABLE ACERO`/`HUELVA`/`MINIGRUA`) para el segundo, para
evitar colisión real detectada con `CERT_REVISION`
(`"Cert.revision eslinga cable acero...pdf"`). Segundo bug real
encontrado con el propio dry-run: `folder_based_type()` bloqueaba
CUALQUIER regla de carpeta para dominio distinto de `PERSONAL`, así
que las 3 reglas nuevas (dominio `MACHINE`) nunca se llegaban a
evaluar -- corregido quitando el filtro de dominio. `run_fase_a_sweep
--apply` ejecutado de verdad: **80 documentos reales** resueltos (49
asignados del todo, 31 con tipo guardado y dominio pendiente),
verificado que el resumen de `--apply` coincidió exactamente con el
`dry-run` previo antes de darlo por bueno.

**Decisiones técnicas explícitas de Miguel Ángel esta sesión:**
- Generar aumentación sintética con datos ficticios (nombres, DNIs,
  matrículas, fechas de una lista genérica) es aceptable; scraping o
  reproducción de datos reales de terceros no lo es, bajo ninguna
  circunstancia.
- `DNI_COMPRADOR` puede llevar plantilla sintética de estructura de
  campos (sin datos de nadie real) -- no aplica el mismo criterio de
  exclusión que `ALTA_MEDICA`.
- Los 8 tipos que ya tenían documentos reales (`CAMBIO_TITULARIDAD`,
  `PRESTAMO`, `OCA`, `PROFORMA`, `SEG_SOCIAL`, `CUADRO_AMORTIZACION`,
  `CONTRATO_COMPRAVENTA`, `DOC_VENTA`) no deben recibir aumentación
  sintética masiva -- su debilidad es de confusión entre tipos
  parecidos, no de ausencia de datos, y el sintético solo tapa el
  síntoma.

---

## COMPLETADAS EN S56 (2026-08-19 -- sesión larga, cuatro bloques:
## generador sintético PEDIDO_COMPRA, unificación de taxonomía de
## facturas, calibración carpeta+nombre sobre el catálogo completo, y
## resolución de dominio de RECONOCIMIENTO_MEDICO)

**Bloque 1 -- Generador sintético de `PEDIDO_COMPRA`.** A partir de
plantillas en blanco genéricas encontradas por Miguel Ángel (sin datos
de terceros reales, solo estructura), se añadió `_tpl_pedido_compra`
a `GENERATORS` en `generate_synthetic_augmentation.py` -- hueco real
confirmado (11 documentos reales, 0 backlog vivo que la heurística
pudiera resolver hoy). Verificado con una generación de muestra real
antes de comitear. `FACTURA_TERCEROS` quedó deliberadamente fuera de
este bloque por la política de S55 (colisión con `FACTURA_COMPRA`) --
resuelto de raíz en el Bloque 2, no como sintético.

**Bloque 2 -- Unificación de taxonomía de facturas (migración
`0036_factura_venta_compra_s56.py`).** Decisión explícita de Miguel
Ángel: el único criterio real de distinción entre tipos de factura es
quién emite, no quién paga. `FACTURA_TERCEROS` (53 documentos vivos)
se fusionó en `FACTURA_COMPRA` (pasa a 112), mismo patrón que
`0033_merge_duplicate_types_s51.py` -- `FACTURA_TERCEROS` desactivado
(`is_active=False`), nunca borrado. `DOC_VENTA` se renombró a
`code=FACTURA_VENTA`, `label="Factura de venta"` (mismo objeto de
catálogo, 89 documentos) -- incluye renombrado retroactivo de los 4
archivos que ya llevaban el código antiguo incrustado en el nombre
(`H05_DOC_VENTA_...` → `H05_FACTURA_VENTA_...`, verificado 0 casos
residuales tras aplicar). `CONTRATO_COMPRAVENTA` quedó fuera de la
migración, confirmado como concepto distinto (contrato, no factura).
Heurística actualizada en el mismo commit: keyword `"FACTURA"` movida
de `FACTURA_TERCEROS` a `FACTURA_COMPRA`, keyword `"VENTA"` renombrada
de clave `DOC_VENTA` a `FACTURA_VENTA`, regla `SPECIFIC_WINS`
`("FACTURA_COMPRA", "FACTURA_TERCEROS")` retirada por obsoleta.
Migración verificada aplicada en producción (`showmigrations`) y
contra datos reales (`FACTURA_COMPRA` 112, `FACTURA_TERCEROS` 0
vivos/inactivo, `FACTURA_VENTA` 89, 4/4 renombrados, 0 residuales de
`DOC_VENTA` en nombres de archivo).

Trabajo posterior sobre `FACTURA_VENTA` (mismo bloque, ya con el tipo
renombrado): auditoría por palabra clave del nombre reveló que el
tipo NO es mayoritariamente factura en la práctica -- desglose real
de los 89: 26 `CONTRATO` (mal archivados, contratos de venta de
máquina), ~33 `FACTURA`/`FRA`/`FACT` (facturas reales), 11
`NOTIFICACION`/`NOTIF` (sospecha real de mal archivado -- la única
muestreada resultó ser un Permiso Provisional de Circulación de la
DGT, nada que ver con venta), ~19 solo "VENTA" sin más pista (sin
revisar). Verificados 3/3 documentos reales del grupo `CONTRATO`
(estructura real de contrato: REUNIDOS/EXPONEN/ESTIPULACIONES,
COMPRADOR/VENDEDOR) antes de mover nada en bloque. Los 26 se
reasignaron a `CONTRATO_COMPRAVENTA` (pasa a 45 vivos) mediante
reasignación directa de `document_type` (sin migración -- operación de
datos puntual sobre patrón de nombre verificado, no cambio de
esquema). Detectado además, sin resolver todavía, un dosier sin
dividir real (`DOC.VENTA P-12 MA-7366-CT 27-4-16.pdf`: página 1
factura real + páginas 2-3 baja DGT por exportación + mandato
notarial, los tres mezclados en un solo PDF) -- mismo patrón
`DOSSIER_PAIRS` ya conocido del proyecto, pendiente decidir si se
divide.

Sobre el marcador de contenido (Fase B1): confirmado con 2 muestras
reales de `CONTRATO_COMPRAVENTA` que el marcador actual
(`"FORMALIZAR EL PRESENTE CONTRATO DE COMPRAVENTA"`) solo cubre una de
las dos redacciones reales -- la otra dice "capacidad legal bastante
para obligarse en los términos del presente contrato de compraventa".
Candidato identificado para ampliar cobertura (`"CONTRATO DE
COMPRAVENTA"` sin más, presente en ambas redacciones reales, ausente
de la factura de venta muestreada) -- **NO llegó a aplicarse en
código esta sesión**, queda como acción concreta pendiente en la hoja
de ruta. El marcador de `FACTURA_VENTA` (`CONTENT_MARKERS`) sigue sin
fijar -- con la contaminación de "CONTRATO"/"NOTIFICACION" ya
detectada, cualquier marcador fijado antes de limpiar el grupo
repetiría el incidente del 9,6%.

**Bloque 3 -- Calibración de solo lectura, nombre+carpeta combinados,
sobre el catálogo completo (77 tipos).** A petición explícita de
Miguel Ángel de "agotar todas las vías antes de entrenar": se
construyó una tabla real carpeta→tipo a partir de los 22.231
documentos ya clasificados, probando cada segmento de ruta como
substring en cualquier parte del path (igual que `folder_based_type()`
real), filtrando candidatas ya cubiertas por regla existente y
nombres de persona (no generalizan). De 256 candidatas brutas
iniciales, 14 quedaron confirmadas -- 9 aceptadas directamente por
pureza/volumen, 5 verificadas contra el documento real descargado
antes de confirmarse (`COMO Z-13`→`CERT_MANTENIMIENTO`,
`SOLICITUD BAJA INDUSTRIA`→`RAE`,
`PARTES ALTA OPERARIOS 27-12-17`→`ALTA`,
`CARNE CAMION AUTOCARGANTE`→`FORMACION`, `SEPT 2014`→`IDC`). Una
candidata (`CURSO 2022`→`RAE`, 17 documentos) resultó ser basura real
tras verificación -- listas de admitidos/aprobados a exámenes de
operador de grúa móvil de más de 5 años, sin valor de archivo según
Miguel Ángel (existe copia en Microsoft 365) -- enviados a papelera
con `trash_dossier_entry()` (17/17 OK, `deleted_by` resuelto,
recuperable). Las 14 reglas añadidas a `FOLDER_TYPE_RULES`
(`heuristic_type_service.py`), verificadas con `run_fase_a_sweep`
dry-run antes y después del `--apply`: 357 documentos reales resueltos
por las reglas nuevas (149 tipo+dominio completos, 213
tipo-ok-dominio-pendiente en el momento del dry-run). Aplicado con
`--apply` real: 150 asignados en firme.

**Bloque 4 -- Resolución de dominio de `RECONOCIMIENTO_MEDICO`.**
Investigando por qué 213 documentos con tipo ya resuelto (Bloque 3)
seguían sin máquina/persona vinculada, se encontró un **bug real de
origen** en `_resolve_person_by_name()` (`run_fase_a_sweep.py`): nunca
quitaba la coma real de carpetas con formato "APELLIDOS, NOMBRE"
antes de comparar contra `person_name_index` (cuyas claves se
construyen siempre sin coma) -- ninguna carpeta con coma pudo matchear
jamás desde que se escribió la función en S54. Corregido (quitar
comas + colapsar espacios antes de normalizar). Impacto medido
empíricamente antes y después: el fix por sí solo solo resolvió 13 de
269 `RECONOCIMIENTO_MEDICO` sin dominio -- el problema de fondo es más
grave: `PersonIdentity.folder_path` sembrado en muchos casos apunta a
una ubicación distinta de donde vive hoy el documento real (mismo
trabajador con carpetas en `OPERARIOS/...` y en
`BAJAS/OPERARIOS BAJAS/...` simultáneamente, por cambios de situación
laboral a lo largo de los años). Se construyó un resolutor nuevo
(ventana deslizante de 2-4 palabras sobre TODOS los segmentos de la
ruta + el nombre de archivo, reutilizando `_build_person_name_index()`
existente, exigiendo unicidad exacta -- nunca ambigüedad) que elevó la
resolución a 123 de 269 (0 de ellos con `is_active_employee=False`,
así que no hizo falta enviar ninguno a papelera). Aplicado en
producción con el mismo patrón real de escritura de dominio
(`domain_content_type`/`domain_object_id`) que usa
`run_fase_a_sweep.py`. Verificado contra datos reales:
`RECONOCIMIENTO_MEDICO` con dominio resuelto pasa de 373 a 496 vivos.
Quedan 146 sin resolver, con motivos reales distintos documentados en
la hoja de ruta (no genéricos "pendiente de revisar").

**Estado global del índice al cierre (verificado, no de memoria):**
34.161 documentos vivos, 22.577 clasificados (66,1%), 11.584 sin tipo
(bajó de 11.672 al arrancar la sesión), 5.667 con tipo pero sin
dominio resuelto (bajó de 5.790). `CONTENT_MARKERS` (Fase B1) sigue en
37 tipos, sin tocar esta sesión -- ningún VM ni batch OCR lanzado,
cero riesgo de repetir el incidente del 9,6%.

---

### COMPLETADAS EN S57 (2026-08-19 -- cierre del punto 1 completo de
la hoja de ruta de S56, más resolución parcial del punto 5)

**Bloque 1 -- Marcador `CONTRATO_COMPRAVENTA`.** Aplicado el candidato
`"CONTRATO DE COMPRAVENTA"` identificado en S56 pero nunca escrito en
código, sincronizado en los dos archivos reales que mantienen
`CONTENT_MARKERS` (`run_fase_b1_ocr_classify.py` y
`local_ocr_classify.py`, éste último la fuente real activa de las VMs
de OCR). Verificado en producción con datos reales del lote vivo:
0 casos nuevos de `ambiguo_varios_marcadores` contra ningún otro tipo
del catálogo. Commit `206d187`.

**Bloque 2 -- Los 11 `NOTIFICACION`/`NOTIF` de `FACTURA_VENTA`.**
Descargados y leídos los 10 documentos reales localizables (uno,
"Confirmación notificación de venta...", resultó ser un correo de la
DGT, no un documento indexado aparte) -- ninguno era una factura de
venta, confirmando la sospecha de S56. Desglose real: 6 →
`CAMBIO_TITULARIDAD` (formularios DGT de cambio de titularidad/
notificación de venta, y una declaración interna de la empresa), 3 →
tipo nuevo `AUTORIZACION_PROVISIONAL_CIRCULACION` (autorización
provisional de circulación, distinta del permiso definitivo), 1 →
tipo nuevo `AVISO_BAJA` (propuesta de baja de oficio RD 2042/94,
distinta de una baja ya ejecutada). Ambos tipos nuevos confirmados
verbatim por Miguel Ángel antes de escribir la migración `0037`
(`document_explorer/migrations/0037_seed_s57_notif_types.py`, patrón
`RunPython` idéntico a `0029`), desplegada y verificada con
`showmigrations` + consulta real al catálogo tras el push (commit
`e6ddc52`).

**Bloque 3 -- Los ~19 `FACTURA_VENTA` solo con "VENTA" en el
nombre.** Aislado el grupo real (13 tras excluir `FACTURA`/`FRA`/
`FACT` ya cubierto y el dosier del punto 4), descargado y leído el
contenido real de cada uno. Desglose confirmado por Miguel Ángel tras
revisión suya en el propio panel: 6 quedan igual en `FACTURA_VENTA`
(incluida venta de exportación a Irak sin importe visible en el
extracto, y dos informes de subasta de Ritchie Bros confirmados como
facturas de venta reales), 4 → `CAMBIO_TITULARIDAD` (formularios DGT
+ declaración interna), 1 → `CONTRATO_COMPRAVENTA` (estructura
REUNIDOS/comprador-vendedor, mismo patrón que los 26 de S56), 1 →
`FACTURA_COMPRA` (Luis Simões, transportista portugués, vendiendo un
remolque A Grúas Álvarez -- al revés de lo que sugería el nombre de
archivo), 1 → `ALBARAN_ENTREGA` (albarán de Aerial Platforms con
Grúas Álvarez como cliente/comprador de un Mercedes ML, no como
vendedor). `FACTURA_VENTA` pasa de 89 a 46 vivos entre los bloques 2 y
3, verificado con conteo real tras cada lote.

**Bloque 4 -- Dosier sin dividir (`DOC.VENTA P-12 MA-7366-CT
27-4-16.pdf`, id 3649).** Descarga y lectura completa de las 3
páginas reales (Fase B1 solo lee 2 por defecto -- releído con
`max_pages` real de `ocr_pdf_to_text()` para confirmar que no faltaba
contenido): página 1 factura real de venta a Mauritania, páginas 2-3
un único paquete de representación/mandato ante la DGT (documento de
representación de personas jurídicas + mandato con representación a
gestor administrativo). Miguel Ángel confirmó dividir. Ejecutado con
PyMuPDF (`insert_pdf`/`tobytes()`, API verificada por `web_search`
contra la versión real `1.27.x` antes de escribir el comando): páginas
2-3 subidas como blob nuevo real vía `upload_bytes()`, reindexadas con
`index_writer.refresh_folder()` (ya validado en producción, reutilizado
sin escribir nada a mano), tipo `CERTIFICADO_PODERES` asignado a la
fila nueva (id 42685), dominio heredado del original. El documento
original (id 3649, `FACTURA_VENTA`) queda intacto, `blob_name` sin
tocar (directriz 4.12) -- única excepción real de la sesión a "todas
las operaciones son virtuales", justificada porque el contenido físico
sí mezclaba dos documentos distintos en un solo archivo escaneado.

**Bloque 5 -- 146 `RECONOCIMIENTO_MEDICO` sin dominio (resolución
parcial, pospuesta a mañana el resto).**

- **Corrección de error real cometido en esta misma sesión:** al
  aplicar el primer lote de resoluciones automáticas se vinculó por
  error el id 36922 (`RM DELGADO ZURERA, MANUEL...pdf`) a
  `PersonIdentity` de Jorge Ramírez García, por vivir dentro de su
  carpeta -- exactamente el caso de documento mal archivado que el
  propio anexo de S56 ya advertía y que no se comprobó antes de
  aplicar. Corregido de inmediato (directriz 4.9): vínculo erróneo
  deshecho, `PersonIdentity` real de Manuel Delgado Zurera localizada
  por DNI (`80126342T`, ya sembrada bajo `TRABAJADORES INACTIVOS`),
  vinculada correctamente, y el archivo además MOVIDO de verdad a su
  ubicación real (`move_service.move_entry()`, operación de índice
  pura, `blob_name` nunca tocado) por decisión explícita de Miguel
  Ángel de que dominio y ubicación coincidan en este caso excepcional.
- **Alta real de Adelaida Álvarez Díaz.** DNI real (`25040739H`)
  confirmado dentro del propio contenido OCR de sus 2 documentos
  (`FRANCISCO JAVIER VILLARREAL RIVAS... CERTIFICA... DNI 25040739H`),
  coincide exactamente con el docx de plantilla histórica que Miguel
  Ángel adjuntó en sesión. `PersonIdentity` creada directamente con su
  carpeta real ya existente (`ADMINISTRACION/ALVAREZ DIAZ, ADELAIDA`,
  no la carpeta de staging `PTE CONTRATACION` que usa el alta
  automática vía Gemini -- ella es administradora de toda la vida, no
  una alta nueva en proceso de contratación). Sus 2 documentos
  vinculados.
- **Ampliación reutilizable de `_build_person_name_index()`/
  `_resolve_person_by_name()`** (`run_fase_a_sweep.py`, commit
  `3fd2c29`): nueva clave de índice "apellido1 apellido2" sin nombre
  de pila (mucho backlog histórico solo lleva los dos apellidos en la
  carpeta), y desambiguación por empresa real
  (`_company_hint_from_path()` contra `PersonIdentity.employer_
  company`) cuando el nombre solo empata entre dos personas de
  empresas distintas del grupo. Miguel Ángel confirmó el enfoque y
  advirtió el riesgo real de hermanos con los mismos dos apellidos
  (familia Álvarez Díaz, y un segundo par de hermanos no identificado
  por nombre) -- protegido de raíz por el mismo criterio de unicidad
  estricta ya existente, sin necesidad de caso especial.
- **Resolutor de ventana deslizante como función reutilizable**
  (`_resolve_person_by_sliding_window()`, commit `ec91cb7`) -- hasta
  ahora el "Bloque 4 de S56" era un script suelto, nunca comiteado.
  Reconstruido y enganchado como tercera vía en el flujo principal del
  comando (tras `_resolve_person_by_folder`/`_resolve_person_by_
  name`), para que sirva también al punto 6 de esta misma hoja de
  ruta con el resto de `tipo_ok_dominio_pendiente`. Recorre todos los
  segmentos de `parent_path` MÁS el nombre de archivo (sin extensión),
  ventana de 2-4 palabras, mismo `person_name_index` compartido, misma
  exigencia de unicidad total.
- **Resultado real medido:** de 146 `RECONOCIMIENTO_MEDICO` sin
  dominio al arrancar el bloque, quedan **77 sin resolver** al cierre
  (565 con dominio resuelto en total). Motivos reales documentados,
  no genéricos: ambigüedad real entre hermanos con los mismos dos
  apellidos (familia Álvarez Díaz y similares, correctamente sin
  forzar), nombres con grafía distinta a la registrada (typos,
  segundo nombre de pila ausente en el archivo), y un grupo
  irreducible sin ningún nombre útil (`TODO.pdf`, `A.pdf`, `E.pdf`,
  `image001.gif`, `Mensaje_.html`, `DOC008.pdf`, `RRMM 2011-2012(3).
  xlsx`, `GRUALDI.doc`, `TRANSGRUAL.doc`). Miguel Ángel decidió
  explícitamente posponer el repaso uno a uno de estos 77 más el
  grupo irreducible a la próxima sesión, desde la oficina.

**Estado global del índice al cierre (verificado, no de memoria):**
`FACTURA_VENTA` pasa de 89 a 46 vivos. `RECONOCIMIENTO_MEDICO` con
dominio resuelto pasa de 496 a 565 (de 146 a 77 sin resolver).
`CONTENT_MARKERS` (Fase B1) sigue en 37 tipos, ampliado solo con la
redacción alternativa de `CONTRATO_COMPRAVENTA` -- ningún VM ni batch
OCR lanzado esta sesión.

---

### COMPLETADAS EN S58

**Bloque 1 -- punto 1 de la hoja de ruta de S57, cerrado.** Aplicado
`_resolve_person_by_sliding_window()` (ya reutilizable desde S57) al
resto de `tipo_ok_dominio_pendiente`, con un comando nuevo comiteado
de verdad (`resolve_domain_pending_types`, dry-run por defecto) --
fija de una vez el patrón que en S56/S57 vivió como script suelto.
Resultado real medido, verificado contra consulta directa a la BD tras
el `--apply` (`sin_dominio` de cada tipo coincide exacto con
`sin_resolver` del comando, sin discrepancias):

| Tipo | Antes | Resueltos | Sin resolver |
|---|---|---|---|
| `PAGO_CORRIENTE` | 1.762 | 274 | 1.488 (ver Bloque 2) |
| `INVESTIGACION_ACCIDENTE` | 834 | 596 | 238 |
| `ENTREGA_INFORMACION` | 636 | 470 | 166 |
| `BAJA_PERSONAL` | 549 | 303 | 246 |
| `AUTORIZACION_USO_MAQUINARIA` | 383 | 271 | 112 |
| `PARTE_BAJA_MEDICA` | 282 | 215 | 67 |
| **Total** | **4.446** | **2.129** | **2.317** |

**Bloque 2 -- decisión nueva de Miguel Ángel: tercer dominio
`CompanyWorksite` (empresa+obra), junto a `MachineAsset`/
`PersonIdentity`.** Miguel Ángel, verbatim (S58): *"estos pagos al
corriente van por empresa [...] es muy, muy, muy raro que vengan para
un solo trabajador [...] esto será algo habitual tener este tipo de
documentación [...] debe ser posible acceder a ella desde la
plataforma cuando hagamos su interfaz [...] Podemos crear una nueva
tabla [...] empresa, obra y el documento donde está [...] igual que
haríamos personal."* Motivado por los 274 `PAGO_CORRIENTE` del Bloque
1: en la práctica casi ninguno es de una sola persona, y forzarlos a
`PersonIdentity` no encajaba con la realidad del documento.

- Modelo `CompanyWorksite` nuevo (`company`/`worksite`, constraint
  único, migración `0038_company_worksite`) + dominio `COMPANY` nuevo
  en `DocumentTypeCatalog.DOMAIN_CHOICES` + `PAGO_CORRIENTE`
  reasignado de `PERSONAL` a `COMPANY` (dato, vía `RunPython` en la
  misma migración). Desplegado y verificado con datos reales
  (`git log -1` + `showmigrations` contra el servidor, no solo el
  verde del Action -- incidente S014).
- Investigación real del árbol antes de construir nada (directriz
  4.8): 1.149 archivos bajo `GRUAS`, 511 bajo `TRANSGRUAL`, ~70 obras
  distintas ya organizadas por carpeta real; 102 archivos sin carpeta
  de obra, con la empresa marcada en el propio nombre de archivo
  (`(GR)`/`(TR)`/`GRUAS`/`TRANSGRUAL`).
- Comando `resolve_company_worksite_domain` (dry-run por defecto),
  reemplaza CUALQUIER dominio previo de la entrada (incluidos los 274
  del Bloque 1 ya vinculados a `PersonIdentity` -- decisión explícita
  de Miguel Ángel de que el vínculo es siempre por empresa/obra, nunca
  por persona, ni en el caso minoritario de alta suelta).
- **Corrección real tras el primer dry-run:** patrón de marcador
  ampliado (`GR`/`TR` sueltos sin paréntesis, `GRUAS` sin `ALVAREZ`
  detrás) tras detectar 8 casos reales que el patrón original dejaba
  fuera -- de paso, esta ampliación destapó un archivo
  (`DECLARACION AL CORRIENTE CON GR (TR).docx`) que el patrón
  estrecho había asignado (mal) solo a TRANSGRUAL por no ver el "GR"
  suelto; con el patrón ampliado queda correctamente `SIN RESOLVER`
  por llevar los dos marcadores a la vez.
- **Resultado real medido y verificado contra la BD:** 1.743 de 1.762
  `PAGO_CORRIENTE` vinculados a `CompanyWorksite` (74 filas reales de
  empresa+obra), 0 quedan en `PersonIdentity`, 19 sin resolver por
  falta de marcador real -- ver "Pendiente real" abajo.

**Bloque 3 -- alcance real de Fase A, medido por primera vez con
datos reales (sin construir nada todavía).** A petición de Miguel
Ángel ("hay que listar las carpetas que no hemos tocado aún, para
poder determinar el alcance del trabajo previsible"):

- `MAQUINAS`: 14.491 archivos totales, 3.185 sin tipo (22,0%), 355
  tipo OK/dominio pendiente, 10.951 completos. El `sin_tipo` mezcla
  carpetas ya excluidas a propósito en S50 (`SCOPE` de
  `run_fase_a_sweep_scoped`) con carpetas reales nunca miradas -- sin
  desglosar todavía cuánto es cada cosa.
- `PERSONAL`: 19.419 archivos totales, 8.147 sin tipo (42,0%), 1.645
  tipo OK/dominio pendiente, 9.627 completos -- sin ninguna exclusión
  de alcance como la de `MAQUINAS`. Tres carpetas de primer nivel
  concentran el 74% de lo pendiente: `PERSONAL` (3.978),
  `FORMACION TRABAJADORES` (1.510), `ENTREGA EPIS` (1.508).
- Desglose real de `DOC. PERSONAL/PERSONAL` (3.978 sin tipo):
  `OPERARIOS` 2.618, `TALLER` 527, `ADMINISTRACION` 524, `GUARDA` 83,
  `AUTORIZACIÓN MEDIOS DE COMUNICACIÓN` 62,
  `PERSONAL ASISTENCIA GRANADA` 58, `PENDIENTES` 44,
  `PTE CONTRATACION` 38, `AUTONOMOS SUBCONTRATAS` 14, `PRACTICAS` 6,
  `PARTES BAJA PATERNIDAD` 1, 3 sueltos en la raíz (uno de ellos
  `.ptn`, pinta a basura).
- **Candidato real sin confirmar todavía** (un solo archivo de
  muestra, no una regla ya verificada): `OPERARIOS` -- 66% del total
  de `PERSONAL/PERSONAL` sin tipo -- tiene al menos un archivo
  (`AUT USO MAQ RODRIGUEZ MORENO, JUAN C 12-5-22.pdf`) que es
  `AUTORIZACION_USO_MAQUINARIA` en forma abreviada, patrón que la
  regla heurística actual (`"AUTORIZACION USO DE MAQUINARIA"`
  completa) no reconoce. Miguel Ángel decidió no muestrear más hoy y
  entrar directo a clasificar mañana.

**Pendiente real, pospuesto explícitamente por Miguel Ángel a la
sesión de mañana desde la oficina:**
- 77 `RECONOCIMIENTO_MEDICO` sin resolver de S57 (sin cambios esta
  sesión).
- 19 `PAGO_CORRIENTE` sin resolver del Bloque 2 -- 13 de ellos en
  `DOC. PERSONAL/DECLARACION AL CORRIENTE/nominas huelva` (Huelva es
  una sucursal real de Grupo Álvarez, verbatim de Miguel Ángel, pero
  sin determinar todavía a qué empresa del grupo se asigna); los 6
  restantes por nombre de archivo sin marcador reconocible
  (`DECLARACION ESTAR AL CORRIENTE GENERAL.pdf`,
  `03072025_rmsmm, si.pdf`, `30052025_mmoALsi...pdf`,
  `DECLARACION AL CORRIENTE CON GR (TR).docx` -- ambiguo a propósito,
  `DECLARACION representante de trabajadores.docx`).

---

### COMPLETADAS EN S59 (2026-08-20 -- cierre de los puntos 1/2/3 de
la hoja de ruta de S58, más una segunda fase real de S59 sobre
`RECONOCIMIENTO_MEDICO` (partición física de dosieres) no prevista en
esa hoja de ruta, y dos bugs reales corregidos en producción)

**Punto 1 -- `OPERARIOS` cerrado y verificado.** Confirmado a escala
contra Comando S real: `"AUT USO MAQ"` solo cubría 168/2.618 (6,4%),
nunca "el grueso" como se hipotetizaba en S58 con una sola muestra --
la carpeta es mucho más heterogénea (EPIS, CARNET DE CONDUCIR,
CONTRATO, CAMBIO IRPF, formación PRL...). Regla heurística añadida de
todos modos (168 coincidencias limpias, sin falso positivo visible).
`run_fase_a_sweep --apply` relanzado. `OPERARIOS` sin tipo: 2.618 →
2.450, verificado contra la BD.

**Punto 2 -- resto de `DOC. PERSONAL/PERSONAL` sin tipo, cerrado.**
Muestra real de las diez carpetas restantes reveló un patrón nuevo de
nombrado (`APELLIDO_NOMBRE_TIPO_FECHA`, alta digital reciente) bajo
`PTE CONTRATACION`. Confirmado por Miguel Ángel como regla reutilizable
-- añadidas `AUTORIZACION USO MAQUINARIA` (forma completa),
`SEG SOCIAL`, y `CONTRATO` en bruto (acotado a dominio PERSONAL, nunca
colisiona con `CONTRATO_COMPRAVENTA` de MÁQUINA). **Bug real detectado
antes de aplicar** (directriz 4.9): `CONTRATO DE ENCOMIENDA`/
`CONTRATO ENCOMIENDA` (acuerdos de gestión de formación con FUNDAE/
TAGA/ILURO/EESEA, nunca contratos laborales) se colaban como
`CONTRATO` -- corregido con exclusión antes de aplicar nada. Tipo
nuevo `AUTONOMO` dado de alta (migración `0039_seed_autonomo_s59`,
domain=PERSONAL, family=LABORAL, tracks_expiry=False) para los recibos
mensuales de autónomo de la familia Álvarez en `ADMINISTRACION`, a
petición explícita de Miguel Ángel. Total de las diez carpetas: 1.357
→ 962 sin tipo (`AUTORIZACION MEDIOS DE COMUNICACION` queda en 0).
Catálogo real tras aplicar: `CONTRATO` 446, `AUTORIZACION_USO_
MAQUINARIA` 604, `AUTONOMO` 47, `SEG_SOCIAL` 40.

**Punto 3a -- `PAGO_CORRIENTE`, los 19 de S58, cerrado.** Confirmado
por Miguel Ángel: la delegación de Huelva pertenece a Grúas Adolfo
Álvarez SL. Regla de carpeta nueva en `resolve_company_worksite_
domain.py` (`nominas huelva` → `GRUAS`/`HUELVA`). Resultado real: 1.762
`PAGO_CORRIENTE` con `document_type`, 1.757/1.762 con dominio resuelto
(14 de los 19 pendientes resueltos vía Huelva, 5 quedan documentados
como irresolubles por falta de marcador real).

**Punto 3b -- `RECONOCIMIENTO_MEDICO`, Grupo A (13 archivos de S57),
cerrado.** De los 13, 9 personas (11 archivos) no tenían ninguna
`PersonIdentity` real -- confirmado con consulta real antes de
borrar nada (evitó un error real: dos casos que parecían "ruido" en
realidad correspondían a personas reales, `GOMEZ GOMEZ, FRANCISCO` y
`DIAZ QUINTERO` ambiguo entre dos personas). Los 11 confirmados a
papelera de `alvarez_admin` (`trash_dossier_entry`). Los 2 casos
reales resueltos a mano: Francisco Gómez Gómez vinculado directamente;
el archivo de `DIAZ QUINTERO` lo abrió Miguel Ángel y confirmó que
era Antonio Jesús -- vinculado a su `PersonIdentity` (pk=3).

**Grupo B de `RECONOCIMIENTO_MEDICO` -- pipeline de partición física
construido, no previsto en la hoja de ruta de S58.** Los ~137 dosieres
de `RECONOCIMIENTOS MEDICOS` restantes resultaron ser PDFs "lote" (un
certificado por página, un trabajador por página, confirmado con
ejemplo real e imagen de Miguel Ángel), nunca documentos de una sola
persona. Decisión explícita de Miguel Ángel: OCR completo + partición
física real del PDF por trabajador (única excepción real que permite
tocar GCS, 4.12) + subida a GCS + indexado nuevo + vínculo por DNI.

Construido un pipeline de dos fases, deliberadamente separado por
coste de CPU:
1. `h28_migration_agent/split_rm_dossier_vm.py` (standalone, sin
   Django, mismo patrón de túnel SSH/shard de `local_ocr_classify.py`)
   -- hace TODO el OCR y la subida de blobs nuevos a GCS, escribe un
   manifiesto JSONL por shard. Nunca escribe en MySQL directamente
   (evita reimplementar a mano el cálculo de `blob_name_hash`/
   `parent_path_hash`/propagación de `total_size_bytes`, que vive en
   `index_writer.refresh_folder()`).
2. `apply_rm_split_manifest` (comando Django en PythonAnywhere) --
   lee el/los manifiesto(s), indexa cada blob nuevo vía
   `refresh_folder()`, asigna `document_type`/dominio, manda a
   papelera el dosier original solo cuando TODAS sus páginas se
   repartieron con éxito.

Patrón de extracción por regex, calibrado contra ejemplos reales,
nunca un único patrón universal -- lista `RECORD_PATTERNS`:
- `MEDIOS_PREVENCION_SUR` (calibrado con `RM 2015 FEB VARIOS.pdf`, 5
  páginas, 5/5 tras corregir el DNI).
- `FRATERNIDAD_MUPRESPA` (calibrado con 3 imágenes reales de Miguel
  Ángel, corregido dos veces tras fallos reales a escala: OCR
  confunde "N.I.F." con "N.|.F.", y el bloque subrayado "APTO PARA EL
  DESEMPEÑO..." puede leerse ANTES de "...permite calificarle como,"
  por el orden de lectura del layout subrayado -- se ancla en el
  texto final, no en "calificarle como").

`_correct_ocr_dni()`: corrección determinista de la letra de control
del DNI cuando el OCR la lee como dígito parecido (confirmado real:
"A"→"4", "Q"→"0"), usando el mismo algoritmo público que
`is_valid_spanish_dni()`, nunca Gemini para esto.

Ejecutado en VM `h28-ocr-batch` (recreada, bootstrap con
`requirements-ocr-vm.txt` ya existente, sin dependencias nuevas), 3
shards en paralelo (petición explícita de Miguel Ángel: "una máquina,
tres instancias"). Resultado real tras dos rondas de calibración: de
137 dosieres, 12 completamente resueltos y enviados a papelera, 16
páginas indexadas como `RECONOCIMIENTO_MEDICO` (14 vinculadas a
`PersonIdentity` real, 2 en `DOCUMENTACION PENDIENTE DE REVISION` por
DNI sin sembrar). **Quedan 125 dosieres sin resolver**, casi todos en
`RM CERT. APTITUD` -- probablemente una tercera mutua o variantes de
Fraternidad-Muprespa no cubiertas todavía. VM detenida (no borrada) al
cierre, a petición de Miguel Ángel -- retomar con
`gcloud compute instances start h28-ocr-batch` y relanzar los 3 shards
directamente, sin rehacer bootstrap.

**Bonus real -- `DOC. PERSONAL/FOTOS CARNET` (174 archivos) sacada
del alcance de clasificación**, decisión explícita de Miguel Ángel
(son fotos tipo DNI, nunca van a tener un tipo del catálogo). Excluida
tanto en `calibrate_fase_a_keywords._files_for_domain()` (nuevo
`OUT_OF_SCOPE_FOLDERS`) como en `local_ocr_classify.py` (VM).

**Dos bugs reales corregidos en producción durante la sesión:**
1. Cambio de scope por defecto del explorador rompió la navegación en
   árbol completa: cualquier clic de carpeta o "Directorio Principal"
   se convertía en búsqueda recursiva, porque `_folder_nav_url()`
   resetea deliberadamente "scope" en cada navegación, y el nuevo
   default (`SCOPE_RECURSIVE`) se aplicaba también ahí. Corregido:
   `SCOPE_HERE` sigue siendo el default real del backend; "recursivo
   por defecto" vive solo como preselección visual del desplegable de
   búsqueda (`scope_param_given`, nuevo en el contexto), sin afectar a
   la navegación real. Verificado por Miguel Ángel tras el despliegue.
2. `resolve_domain_pending_types`/`resolve_company_worksite_domain`
   no eran el foco de este bug -- fue puramente el default de
   `_read_filters()` en `views.py`.

**Incidentes de proceso reales (S59), ya corregidos y documentados
para que no se repitan:**
- Comando entregado con placeholder (`GITHUB_PAT_AQUI`) para que
  Miguel Ángel sustituyera contenido -- prohibido explícitamente,
  reforzado en `com-standards`.
- Pregunta sobre si existía ya la clave de servicio de GCS, pese a
  estar ya documentada en `SESSION_VARIABLES.md` -- regla nueva:
  releer `SESSION_VARIABLES.md` antes de preguntar por cualquier
  credencial de infraestructura.
- `git clone` con prompt interactivo de usuario/contraseña falla
  siempre en consolas SSH remotas (4.ª vez real) -- documentado el
  método que sí funciona (`read -s` + token inline en la URL).
- Coste de CPU de OCR sin criterio de dónde ejecutar según volumen --
  nueva directriz en `com-standards` (consola PythonAnywhere para un
  puñado de archivos, local para volumen medio, VM para volumen
  grande).

**Migraciones:** `0039_seed_autonomo_s59` (tipo `AUTONOMO`), aplicada
y verificada con datos reales (`showmigrations` contra el servidor,
nunca solo el verde del Action -- incidente S014).

---

### COMPLETADAS EN S60 (2026-08-20 -- calibración iterativa de
`RECONOCIMIENTO_MEDICO` a partir del resto real de S59, 3 patrones
nuevos, 1 tipo documental nuevo, y un bug real de orientación
corregido de raíz)

**Punto de partida real:** S59 cerró con 125 dosieres RM sin resolver
(`RM CERT. APTITUD`, casi todos Fraternidad-Muprespa). Se abrió la
sesión relanzando directamente los 3 shards de `split_rm_dossier_vm.py`
con el código ya corregido en S59 (`64b2d7e`) que el manifiesto
original nunca llegó a usar -- primer bloque, 125 → 89, sin cambio de
código, solo confirmando que el fix de S59 ya cubría una parte real.

**Ciclo de calibración real, cinco vueltas completas (herramienta
nueva `inspect_sin_patron_pages.py`, solo lectura, reOCR puntual de
páginas `SIN_PATRON` de los manifiestos -- no hay texto OCR guardado
en el manifiesto en sí, solo `page_index`/`status`):**

1. **`examen de salud inicial`** (el patrón solo aceptaba
   "periodico") + tolerancia a `N.I.F.` con 1-2 caracteres de ruido
   OCR (`N.!|.F.`) -- verificado contra 2 ejemplos reales
   (`4f5b446`). 89 → 78.
2. **Tolerancia ampliada de `N.I.F.`** a la letra `I` confundida por
   OCR con `1` (dígito) o `L` (mayúscula) -- `N.1.F.`/`N.LF.`/`N.L.F.`,
   3 ejemplos reales distintos (`07f7fa5`). 78 → 73.
3. **Patrón nuevo `FRATERNIDAD_NOTIFICACION_PENDIENTE`** -- plantilla
   SPFM distinta ("NOTIFICACIÓN DE LA REALIZACIÓN DE RECONOCIMIENTO
   MEDICO"), sin conclusión de aptitud (queda pendiente de pruebas
   complementarias), fecha en texto y "D.N.I." en vez de "N.I.F.".
   Verificado contra 3 ejemplos reales limpios (`6f6558c`); el propio
   `main()` nunca usa el grupo `aptitud`, así que el patrón nuevo no lo
   necesita. 73 → 53 (bloque más productivo de la sesión, 101 páginas
   OK en un solo pase).
4. **Bug real de orientación, corregido de raíz.** `DOC008.pdf`
   (5 páginas, todas `SIN_PATRON`) resultó estar escaneada boca abajo
   -- confirmado visualmente por Miguel Ángel. Añadido `_detect_rotation()`
   (Tesseract OSD) tanto en `_ocr_all_pages()` (para poder leer el
   texto) como en `_split_single_page()` (`page.set_rotation()`, para
   que el PDF final suba también bien orientado, no solo se clasifique
   bien) -- verificado contra la API real de PyMuPDF por búsqueda web
   antes de escribirlo (`57793ba`). Confirmado con datos reales: las 5
   páginas de `DOC008.pdf` se resolvieron al 100% en el siguiente pase.

**Alta de tipo documental nuevo, confirmada por Miguel Ángel:**
`CERT_LIMITACIONES` (migración `0040_seed_cert_limitaciones_s60`,
`domain=PERSONAL`, `family=SALUD_BAJAS_PERSONA`,
`tracks_expiry=False`) -- declaración del administrador de que un
trabajador con limitaciones médicas usará los EPIs recomendados por el
médico, sin `APTO`/`NO APTO` ni estructura de examen. Detectado al
calibrar contra `CERT.LIMITACIONES RM Perez Fernandez 2-3-16.pdf`.
Migración desplegada y verificada con datos reales del servidor
(`git log -1` + `showmigrations` + consulta directa al catálogo, no
solo el verde del Action -- incidente S014). Solo 2 ejemplos reales
vistos hasta ahora (`Perez Fernandez`, `Casilla Nieto`) -- por debajo
del umbral de 3+ que exige el criterio de calibración de la sesión, así
que su propio patrón de extracción queda sin escribir todavía.

**Resultado acumulado real, verificado contra la BD tras cada bloque
(nunca solo contra el resumen del propio comando):** 125 → 89 → 78 →
73 → 53 dosieres `RM CERT. APTITUD` sin resolver. `apply_rm_split_manifest`
ejecutado 5 veces, siempre dry-run primero y `--apply` solo si el
dry-run cuadraba exacto con el resumen del manifiesto -- ninguna
sorpresa en ningún bloque.

**Incidencia de proceso real:** Miguel Ángel señaló, con razón, que
las instrucciones de una respuesta intermedia (varias cajas alternativas
sin dejar claro cuál pegar y dónde) resultaron confusas -- corregido en
el momento, pasando a un único bloque de comandos en el orden exacto en
que se pegan.

**Migraciones:** `0040_seed_cert_limitaciones_s60` (tipo
`CERT_LIMITACIONES`), aplicada y verificada con datos reales.

---

## COMPLETADAS EN S61 (2026-08-21)

**Sesión con mucho más ruido de proceso que trabajo real — el balance
neto de código es pequeño pero deja arrancado un patrón productivo
nuevo, con un fallo de despliegue real sin resolver a mitad de
camino.**

**1. Fix real de tolerancia OCR, desplegado y verificado
(`2d81c53`).** Investigando los 6 casos `SIN_PATRON` de
`RECONOCIMIENTO_MEDICO` con `inspect_sin_patron_pages.py`, se
confirmó que **no había ninguna tercera mutua** (hipótesis abierta
desde S59/S60) — eran variantes ya conocidas de
`FRATERNIDAD_NOTIFICACION_PENDIENTE` con ruido OCR sobre el marcador
`D.N.I.` (leído como `D.N.l.`/`D.N./.`/`D.N.!.`/`D.N.1.`/`D.N.].`) y
sobre el prefijo `D/Dña` (`D/Dfña`). Ampliada la tolerancia del
regex, verificada con test unitario contra los 7 textos OCR reales
antes de commitear. Relanzados los 3 shards con este fix ya aplicado
→ **`RM CERT. APTITUD` bajó de 45 a 37 dosieres sin resolver**,
verificado contra la BD real tras el `--apply` (8 dosieres a
papelera, 58 páginas indexadas, cifras del `--apply` coincidentes
exactas con el `dry-run` previo).

**2. Bug real corregido: `CERT_LIMITACIONES` nunca se había aplicado
a ningún documento desde su alta en S60.** El propio ejemplo de
calibración de la migración `0040` (`Perez Fernandez`) y el segundo
ejemplo (`Casilla Nieto`) seguían con `document_type=
RECONOCIMIENTO_MEDICO`. Corregidos los 3 casos reales encontrados por
nombre (los 2 de arriba + una plantilla en blanco,
`CERT.LIMITACIONES RM TRABAJADOR.docx`, sin dominio por ser
genérica). **Siguen sin patrón de extracción propio** — solo hay 2
ejemplos reales con persona (por debajo del umbral de 3+ de la
sesión) — no construir el regex hasta encontrar un tercero real.

**3. Patrón nuevo `ANP_INFORME_APTITUD` calibrado, escrito y
commiteado (`3ef71a4`), pero NUNCA LLEGÓ A PROBARSE DE VERDAD EN LA
VM — punto 1 de la hoja de ruta de abajo.** Proveedor de prevención
distinto a Fraternidad-Muprespa ("SERVICIO DE PREVENCIÓN AJENO",
cabecera "GRUPO", "INFORME DE APTITUD MÉDICA"), 4 ejemplos reales
verificados con test unitario contra el texto ya normalizado
(`strip_accents`+`upper`, tal como lo procesa el pipeline real):
Carlin Carvajal, Rosado Racero, Lopez Blazquez, Alvarez Diaz. Captura
`aptitud` literal (`APTO`/`APTO EN OBSERVACION`/`SIN APTITUD`/`NO
APTO`), más variado que el resto de patrones.

**4. Incidente real sin resolver: el `git pull` de después de este
commit falló, y los 3 shards relanzados corrieron con el código
VIEJO.** El segundo dry-run (`45 dosieres`, `58 páginas OK`, `87
error`) dio números **idénticos** al primero — sospecha confirmada
con `git log -1`/`grep` directos en la VM: `HEAD` seguía en `2d81c53`
(el fix de S61 anterior), nunca llegó a `3ef71a4`. Intento de `git
pull` en caliente falló con `Invalid username or token` — el token
usado para el clon original de esta VM ya no es válido (probablemente
revocado al cierre de una sesión anterior) y no hay uno nuevo
configurado en el remoto de esa VM. **`ANP_INFORME_APTITUD` sigue sin
probarse contra datos reales de producción** — el commit existe y
está verificado por test unitario, pero nunca se ha ejecutado dentro
del pipeline real.

**5. Incidencia de proceso grave, autoinfligida y ya corregida:** el
modelo confundió dos veces la consola sftp permanente (Git Bash,
única función: `sdcard/Download/` local ↔ `SWAP` del servidor) con
las conexiones necesarias para VM↔PythonAnywhere, llegando a cerrar
la consola permanente real de Miguel Ángel con un `exit` que nunca
debió generarse. Corregido de raíz, documentado en dos sitios
distintos para que no se repita:
- `SESSION_VARIABLES.md`, sección "DOS CONSOLAS DISTINTAS" (con la
  nota literal de Miguel Ángel sobre el uso exclusivo de cada una).
- La propia skill `com-file-request`, sección nueva "COMUNICACIÓN VM
  ↔ PYTHONANYWHERE" — empaquetada y entregada por `present_files` en
  esta sesión; **confirmar si Miguel Ángel pulsó "Guardar habilidad"
  antes de asumir que la corrección persiste a la sesión
  siguiente** (ver `com-standards`, "Modificar o crear una skill").
  Regla resumen: la consola permanente NUNCA se abre ni se cierra por
  el modelo y NUNCA se usa para nada que no sea
  local↔`SWAP`; las conexiones VM↔PythonAnywhere se abren y cierran
  dentro de la propia consola PowerShell de la VM, sin tocar la
  permanente, y sin cerrar nunca la propia PowerShell (eso lo
  controla Miguel Ángel).
- Además, se documentó y verificó el método real de `gcloud compute
  scp` en Windows: `pscp` no admite comodines ni varios orígenes
  remotos a la vez; la solución que sí funciona es agrupar los
  archivos en una carpeta dentro de la VM y descargarla entera con
  `--recurse` en un solo comando, con ruta absoluta (nunca `~`).

**Incidencia de seguridad real, reconocida:** en un momento de la
sesión el modelo llegó a escribir el valor completo del token de
GitHub en su propia respuesta de texto — prohibición absoluta de
`nfs-enterprisebot-token`. Miguel Ángel lo señaló de inmediato. **El
token de esta sesión debe darse por comprometido y revocarse sin
falta** (ver recordatorio de cierre).

**Commits reales de la sesión** (7, `1fcf13d..fe76437`): `2d81c53`
fix tolerancia OCR; `d24ce2f`/`abee8d6`/`d7e6f2e` documentación
iterativa de `gcloud compute scp` hasta dar con el método real;
`e396a1f`/`4a657fd` documentación de las dos consolas (la primera
versión, `e396a1f`, quedó incorrecta y quedó corregida por
`4a657fd`); `3ef71a4` patrón `ANP_INFORME_APTITUD` + ampliación
D.N.I.; `fe76437` nota final de las dos consolas. 2 archivos tocados
(`SESSION_VARIABLES.md`, `split_rm_dossier_vm.py`).

---

## HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (sustituye por completo a
## cualquier "pendiente" suelto de bloques anteriores)

**EMPEZAR AQUÍ, SIN PREGUNTAR POR DÓNDE EMPEZAR — instrucción
explícita: el punto 1 es bloqueante y debe resolverse antes que
cualquier otra cosa de este hito.**

1. **BLOQUEANTE — arreglar la autenticación git de la VM
   `h28-ocr-batch` y verificar de verdad que `ANP_INFORME_APTITUD` se
   aplica.** El código del patrón nuevo ya está en GitHub
   (`3ef71a4`), pero la VM sigue en `2d81c53` — el `git pull` normal
   falla con `Invalid username or token`. Pasos:
   1. Pedir a Miguel Ángel un token de GitHub nuevo para la sesión
      (`nfs-enterprisebot-token`).
   2. En la VM (conexión PowerShell efímera, `gcloud compute ssh
      h28-ocr-batch --project=gen-lang-client-0961484137
      --zone=europe-west1-b`): comprobar `git remote -v` primero para
      ver si la URL remota necesita token embebido o si basta con
      `git pull` usando el método `read -s` ya documentado en
      `SESSION_VARIABLES.md` ("CLONAR EL REPO EN UNA VM/CONSOLA SSH
      REMOTA").
   3. Confirmar `git log -1 --oneline
      h28_migration_agent/split_rm_dossier_vm.py` → debe mostrar
      `3ef71a4` o posterior, y `grep -c "ANP_INFORME_APTITUD"
      h28_migration_agent/split_rm_dossier_vm.py` → debe dar 1 o más,
      antes de relanzar ningún shard.
   4. Relanzar los 3 shards (`split_rm_dossier_vm.py --shard-count 3
      --shard-index N`), traer los manifiestos (carpeta +
      `gcloud compute scp --recurse`, método ya verificado en
      `SESSION_VARIABLES.md`), subir a `SWAP` desde la consola sftp
      permanente, y `apply_rm_split_manifest` (dry-run primero,
      `--apply` solo si cuadra). **Criterio de cierre:** bajar de 37
      dosieres `RM CERT. APTITUD` sin resolver, verificado contra
      consulta directa a la BD tras el `--apply`.
2. **Patrón de extracción para `CERT_LIMITACIONES`** — sigue con solo
   2 ejemplos reales (`Perez Fernandez`, `Casilla Nieto`). Buscar un
   tercero real antes de escribir el regex (criterio de calibración
   de 3+ casos de la sesión, sin cambios desde S60/S61).
3. **Confirmar si la skill `com-file-request` quedó guardada de
   verdad.** Si Miguel Ángel no pulsó "Guardar habilidad" en la
   tarjeta entregada en S61, la corrección de la sección "COMUNICACIÓN
   VM ↔ PYTHONANYWHERE" no persiste — verificar al arrancar la sesión
   (releer la skill) y, si falta, reempaquetarla y volver a
   entregarla. La regla en sí (consola permanente = solo
   local↔`SWAP`; VM↔PythonAnywhere = conexión efímera dentro de la
   propia PowerShell de la VM, nunca la permanente) sigue vigente
   pase lo que pase con el estado de la skill — está también en
   `SESSION_VARIABLES.md`, que sí es fuente de verdad segura.
4. Resto de la hoja de ruta de H30 arrastrada de sesiones anteriores,
   sin tocar en S56-S61: EPIS (extracción a `EpiDelivery`, fundida con
   Fase B/Gemini como último recurso -- conecta directo con `ENTREGA
   EPIS`, 1.508 archivos sin tipo), `resolve_domain_pending_types`
   sin relanzar sobre los ~844 de S58 (BAJA_PERSONAL,
   INVESTIGACION_ACCIDENTE, ENTREGA_INFORMACION,
   AUTORIZACION_USO_MAQUINARIA, PARTE_BAJA_MEDICA), variable de
   entorno de la clave de servicio del agente H28, `FICHA_TECNICA` vs
   `ITV`, backfill de fecha, duplicados de seguro/OCA. El "renombrado
   retroactivo" genérico sigue sin mecanismo reutilizable.
5. Carpetas pequeñas de `DOC. PERSONAL/PERSONAL` (arrastrado, sin
   avanzar desde S60): `PENDIENTES` (44), `AUTONOMOS SUBCONTRATAS`
   (14), `PRACTICAS` (6), `PARTES BAJA PATERNIDAD` (1) -- sin patrón
   dominante claro en la muestra ya vista, revisar tipo por tipo antes
   de escribir regla.

**Preguntas explícitas ya resueltas en S60/S61** (no se vuelven a
listar): `CERT.LIMITACIONES` → tipo documental nuevo, confirmado (S60);
"tercera mutua" → descartada, era ruido OCR sobre patrón ya conocido
(S61). El resto de preguntas arrastradas de S56-S59 (Fase A del resto
del catálogo, OneDrive de GRUALDI SL, techo de `EXCEDENCIA` 100%
sintético) siguen sin tocar -- ya van 6 sesiones sin ejecución real,
**pasan a pregunta directa obligatoria al arrancar la próxima sesión**
por directriz 2.2, sin esperar más.

**Recordatorio operativo real para la próxima sesión (no repetir los
errores de S61):**
- La consola sftp permanente (Git Bash) del usuario NUNCA se abre ni
  se cierra por el modelo, y se usa única y exclusivamente para
  `sdcard/Download/` local ↔ `SWAP` del servidor.
- Las conexiones VM↔PythonAnywhere van dentro de la propia consola
  PowerShell de la VM, abiertas y cerradas ahí, sin tocar la
  permanente. La consola PowerShell en sí no la cierra el modelo.
- `gcloud compute scp` en Windows: agrupar en carpeta + `--recurse`,
  un comando, ruta absoluta.
- Nunca imprimir un token en la respuesta de texto, bajo ningún
  concepto.

---

## COMPLETADAS EN S62 (2026-08-21)

**Punto 1 de la hoja de ruta de S61, cerrado de verdad esta vez.**
Bloqueante resuelto: token de GitHub nuevo capturado con `read -s` en
la VM `h28-ocr-batch`, `git pull` con cabecera `Authorization: Basic`
(nunca en la URL del remoto) trajo el commit `3ef71a4` (fast-forward
`2d81c53..3ac0af4`), confirmado con `git log -1 --oneline` +
`grep -c "ANP_INFORME_APTITUD"` = 1 antes de relanzar nada. Los 3
shards se relanzaron en paralelo (3 ventanas PowerShell independientes,
`tmux new -s shard{0,1,2}` en cada una -- el `Ctrl+B D` de detach
sigue sin funcionar en esta consola, confirmado otra vez). Manifiestos
agrupados en una carpeta y bajados con `gcloud compute scp --recurse`
en un solo comando, subidos a `SWAP/` (ver incidencia de proceso más
abajo). `apply_rm_split_manifest --apply`: 66 páginas indexadas, 8
dosieres a papelera. Verificado contra la BD real (no solo contra el
resumen del comando): `RM CERT. APTITUD` bajó de 37 a 2 dosieres
vivos -- muy por debajo del objetivo original.

**Hallazgo real sobre esos 2 dosieres restantes, resuelto en la misma
sesión:** no eran páginas sueltas sin resolver -- eran dos carpetas
contenedoras (`RECONOCIMIENTO MED. 2011`, `RECONOCIMIENTOS MEDICOS
2010`) con **todo su contenido de archivo ya clasificado**
`RECONOCIMIENTO_MEDICO` (8/8 y 21/21 respectivamente), pero la carpeta
en sí nunca fue candidata de `split_rm_dossier_vm.py` (que solo
detecta PDFs sueltos, nunca carpetas ya organizadas en subcarpetas por
proveedor/color) y por tanto nunca llegó a papelera. `trash_dossier_
entry()` aplicado a las 48 filas (carpeta + todo su contenido, 14+34,
0 fallos) tras confirmar con Miguel Ángel que todo estaba ya
clasificado. **`RM CERT. APTITUD` queda en 0 dosieres vivos.**

**`CERT_LIMITACIONES` -- búsqueda del tercer caso real, sin patrón
automático escrito.** Búsqueda por nombre de archivo ('LIMITACIONES')
encontró 2 candidatos nuevos que el modelo asumió erróneamente como
plantillas en blanco sin comprobar contenido real -- corregido tras
capturas de Miguel Ángel: son declaraciones reales, con nombre y DNI
(Juan Manuel Alhamar Avellaneda, Carlos Bas Blanco). Con los 2 ya
conocidos (Perez Fernandez, Casilla Nieto) se llega a 4 casos reales,
pero comparado el texto completo de los 4 (2 vía captura, 2 vía
descarga+subida directa de Miguel Ángel -- nunca OCR de consola, ver
incidencia más abajo), resultan **3 redacciones distintas**, ninguna
con 3+ ejemplos idénticos: "va a hacer uso de los epis recomendados
por el médico" (2, Perez Fernandez/Casilla Nieto), redacción de
Alhamar Avellaneda (1), plantilla de Carlos Bas Blanco sin mención de
EPIs (1). Decisión de Miguel Ángel: no fabricar un marcador único que
fuerce a las 3 redacciones -- clasificar los 4 a mano (hecho, los 4
quedan `CERT_LIMITACIONES`) y dejar el patrón automático pendiente
hasta 3+ ejemplos reales de una misma redacción, con llamada a Gemini
como respaldo futuro pendiente de diseñar. Perez Fernandez (pk=123) y
Casilla Nieto (pk=87) vinculados a su `PersonIdentity` ya existente;
Alhamar Avellaneda (DNI 44207291A) y Bas Blanco (DNI 28917345C)
quedan sin vincular -- no existe `PersonIdentity` para ninguno de los
dos.

**Decisión real sobre Carlos Bas Blanco y David Contreras Marquez:**
confirmados como trabajadores activos de verdad (240+ documentos
sueltos de Bas Blanco en categorías/año, sin carpeta personal propia;
27+ entradas de Contreras Marquez en partes de trabajo digitales,
`WorkOrderEntry.worker_name`) -- ambos de la delegación de Huelva, que
nunca tuvo rama propia dentro de `DOC. PERSONAL/PERSONAL/`. Decisión
explícita de Miguel Ángel: **quedan fuera del sistema de
documentación por completo** -- se gestionan única y exclusivamente
vía partes de trabajo, su documentación la controla Huelva por su
cuenta. No se crea `PersonIdentity` para ninguno de los dos, no se
crea rama nueva de carpetas. Cerrado, no volver a investigarlo.

**`resolve_domain_pending_types` relanzado -- 0 resueltos, verificado
que NO es un bug.** Antes de reportarlo como incidencia se comprobó
contra el propio historial del anexo: los números de hoy
(`INVESTIGACION_ACCIDENTE` 237, `ENTREGA_INFORMACION` 166,
`BAJA_PERSONAL` 246, `AUTORIZACION_USO_MAQUINARIA` 127,
`PARTE_BAJA_MEDICA` 67) coinciden casi exactos con el "sin resolver"
que ya dejó S58 tras su propio `--apply` (2.129 resueltos de 4.446
entonces) -- es el mismo remanente que los tres resolutores ya no
pueden cerrar solos, resultado correcto, no una regresión.

**`audit_mandatory_documents` (S49, solo lectura) relanzado a
petición de Miguel Ángel, antes de autorizar ningún borrado.**
Resultado real: **300 de 557 máquinas activas con algún hueco de
documentación obligatoria (649 huecos en total), solo 21 completas.**
Hallazgo grande, documentado aquí, pero **fuera de alcance de esta
sesión** -- tarea de máquinas, no de personal, para sesión dedicada
aparte. Confirmado que no interfiere con el borrado de huérfanos de
personal (ejes de datos independientes, `MachineAsset` vs
`PersonIdentity`).

**Comando nuevo `trash_orphan_personal_documents` (commiteado,
`9fdcb47`), decisión explícita de Miguel Ángel.** Tras confirmar que
6 nombres reales sacados de los "tipo OK, dominio pendiente" (Moya
Gómez, Saavedra Pérez, Rafael Baena, Barrios Gómez, García Morillo,
López Domínguez) **no existen** en el catálogo de 70 `PersonIdentity`
(comprobado uno a uno contra la BD, un séptimo caso -- Hurtado de
Mendoza -- sí resultó ser una coincidencia real y se vinculó aparte),
Miguel Ángel confirmó el criterio de diseño: **la interfaz de
documentación solo accede a los 70 activos del Excel** -- un
documento que referencia a alguien fuera de esos 70 queda huérfano
para siempre, nunca visible desde el panel de documentación (sí desde
el explorador de archivos crudo o M365). Dry-run (843 candidatos, 5
tipos: `INVESTIGACION_ACCIDENTE`/`ENTREGA_INFORMACION`/
`BAJA_PERSONAL`/`AUTORIZACION_USO_MAQUINARIA`/`PARTE_BAJA_MEDICA`,
`PAGO_CORRIENTE` excluido a propósito por ser dominio `COMPANY` desde
S58) confirmado y aplicado: **843 documentos a papelera, 0 fallos**
(`trash_dossier_entry()`, `blob_name` en GCS intacto, 4.12).

**Estado final de `DOC. PERSONAL` verificado tras la limpieza (18.528
archivos vivos):** 10.346 completos (56%), 7.417 sin ningún tipo
(`DOC. PERSONAL/PERSONAL` 3.262, `ENTREGA EPIS` 1.508, `FORMACION
TRABAJADORES` 1.497, resto residual), 765 con tipo pero sin persona
(bajó de 1.963 tras la limpieza de hoy) -- mayores: `FORMACION` (131),
`CAP` (125), `ALTA` (110), `IDC` (76), `CURSO` (65).

**Tres incidencias de proceso reales, todas corregidas en la misma
sesión (directriz 4.9):**

1. **El modelo borró archivos de `SWAP/` a mitad de sesión (`rm
   SWAP/...` en cajas sftp de Comando S) pese a instrucción explícita
   de Miguel Ángel de que el borrado de SWAP es exclusivo del cierre
   de sesión.** Señalado por Miguel Ángel con dureza, corregido de
   inmediato -- ninguna caja sftp posterior de la sesión volvió a
   incluir borrado remoto. Consecuencia real, ya aplicada: el vaciado
   total de `SWAP/` pasa a ser un paso formal del propio cierre de
   sesión (ver PASO 11 nuevo, más abajo) -- nunca disperso en cajas
   intermedias.
2. **El modelo intentó subir a PythonAnywhere archivos ya descargados
   de la VM (`gcloud compute scp`) usando la consola sftp permanente
   con una ruta relativa equivocada** (asumía que la ruta remota real
   de `SWAP` colgaba de `PROJECTS/EnterpriseBot/`, cuando en realidad
   cuelga directamente de `/home/MiguelAeTxio/`) -- corregido dos
   veces hasta dar con la ruta real, verificada contra el propio
   listado de archivos del panel Files de Miguel Ángel.
   `SESSION_VARIABLES.md` corregido con la ruta real y el patrón de
   conexión sftp efímera correcto (misma PowerShell donde caen los
   archivos del `scp`, nunca la consola permanente).
3. **El modelo invocó OCR manualmente (`extract_text`) desde el shell
   de Django en la consola de PythonAnywhere** para leer el contenido
   de dos archivos conocidos -- Miguel Ángel lo interrumpió (`Ctrl+C`)
   señalando el coste real de CPU y la cuota limitada. Corregido de
   raíz en `com-standards`: **queda terminantemente prohibido invocar
   OCR manualmente en la consola de PythonAnywhere, incluso para un
   solo archivo** -- la única vía aceptable para consultar contenido
   puntual es que Miguel Ángel descargue el archivo y se lo suba
   directamente al modelo (archivo o captura), nunca que el modelo
   ejecute OCR él mismo salvo dentro del pipeline real de producción.

**Skills corregidas y guardadas esta sesión (con confirmación de
Miguel Ángel de que el botón "Guardar habilidad" se pulsó en las
cuatro):** `nfs-enterprisebot-pcs` (PASO 11 nuevo, vaciado total de
`SWAP/` en cada cierre -- instrucción explícita, verbatim en el propio
PASO 11), `nfs-campustudionline-pcs` y `nfs-system-pcs` (mismo PASO 11
replicado, aplica a todas las sesiones de todos los proyectos según
instrucción explícita de Miguel Ángel), `com-standards` (prohibición
de OCR manual en consola de PythonAnywhere). `englishb1-pcs` y
`newflow-android-pcs` revisadas y descartadas a propósito -- no usan
SWAP, no aplica.

**Commits reales de la sesión** (3, `3ac0af4..9fdcb47`): `5d5cd2b`
documentación del patrón de subida sftp efímera post-scp (incidencia
2 de arriba, primera corrección); `9735419` corrección de la ruta
real de SWAP en esa misma nota; `9fdcb47` comando nuevo
`trash_orphan_personal_documents`. 2 archivos tocados
(`SESSION_VARIABLES.md`, el comando nuevo). El grueso del trabajo de
esta sesión fue sobre datos (BD vía Comando S: migraciones de dominio,
papelera, indexación), no sobre código versionado -- coherente con
sesiones de hito H30 anteriores.

---

## COMPLETADAS EN S63 (2026-08-23)

**Punto 1 de la hoja de ruta de S62, cerrado para Fase A (heurística
de nombre) -- no al 100%, hasta el techo real de lo que un nombre de
archivo puede dar.** Retomó una sesión previa ya interrumpida por
Miguel Ángel (el commit `8cdac3e`, S63, ya vivía en el repo al
arrancar: `FORM`/`MOD 145`/`TARJETA DEL CONDUCTOR`/`RM` confirmados
con datos reales).

**3 códigos de catálogo nuevos, decisión explícita de Miguel Ángel
(opción A las tres veces)**, creados como filas reales de
`DocumentTypeCatalog` (sin migración de esquema, solo datos):
`CARNET_GRUISTA` (domain=PERSONAL, family=IDENTIDAD_PERSONAL,
tracks_expiry=True -- ya existía el concepto desde S54 en
`PersonIdentity.crane_operator_card_expiry_date`, nunca tuvo código),
`RECURSO_PREVENTIVO` (family=PRL_FORMACION, tracks_expiry=False),
`REGISTRO_JORNADA` (family=LABORAL, tracks_expiry=False, resuelto
sobre todo por carpeta: `REGISTRO DE JORNADA`, `PARTE SEMANAL`).

**Bug real corregido de raíz:** el commit heredado `8cdac3e` metía
`"RM": ["RM"]` como código de catálogo nuevo en vez de frase adicional
de `RECONOCIMIENTO_MEDICO` -- `RM` nunca fue un código válido,
provocaba `KeyError` real en `run_fase_a_sweep --apply` (confirmado
con traceback en producción, sin datos corruptos escritos). Corregido
fusionando la frase en el código ya existente.

**Segundo bug real, más grave, detectado y corregido en la misma
sesión:** al ampliar la regla de carpeta de `BAJA_PERSONAL` de
`PERSONAL/BAJAS` a `/BAJAS/` (cobertura real, antes se perdían
`TALLER/BAJAS`, `OPERARIOS/.../BAJAS`), la exclusión de EPIS (S48:
van a `EpiDelivery`/`EpiReview`, nunca a este recorrido heurístico)
solo estaba implementada en la vía de palabra clave, nunca en
`folder_based_type()`, que se comprueba ANTES. Consecuencia real:
**503 archivos EPI dentro de carpetas BAJAS se tiparon mal como
`BAJA_PERSONAL`.** Corregido de raíz (exclusión universal de "EPI" en
`folder_based_type()`, aplica a cualquier regla de carpeta presente o
futura) y los 503 revertidos (`document_type=None`) en la misma
sesión.

**Calibración iterativa completa contra datos reales** (nunca
interpretación propia sin verificar): decenas de variantes de nombre
añadidas a `CARNET_CONDUCIR` (CARNET/CARNE/PERMISO DE CONDUCIR,
CONDUCCIÓN, TARJ DEL CONDUCTOR, CCONDUCIR, AUT PROV CONDUCIR), `CAP`
(TARJETA/TARJ CUALIFICACIÓN en sus variantes reales, con y sin "DE" --
mismo bug de límite de palabra corregido 3 veces sobre distintas
variantes), `CARNET_GRUISTA` (CERT OPERADOR/OP GRUA, GRHIDRAULICA,
CARNE GRUAS, CERTIFICADOS DE GRUISTAS), `AUTORIZACION_USO_MAQUINARIA`
(AUT MAQ, AUT USO MAQUINA/UTILES, con/sin DE), `FORMACION`
(FICHA INSCRIPCION, LISTADO ALUMNOS, CAPACITACION, APARATOS
ELEVADORES, PRL AUXILIO), `RECURSO_PREVENTIVO` (RECURSO/REC
PREVENTIVO, NOMB REC PREV, INF REC PREVENTIVO),
`RECONOCIMIENTO_MEDICO` (REC/RECO MEDICO, RMEDICO), `SEG_SOCIAL`
(TARJETA S SOCIAL, VIDA LABORAL), `TACOGRAFO` (TTACOGRAFO),
`BAJA_PERSONAL` (CARTA BAJA VOLUNTARIA + carpeta `TRABAJADORES
INACTIVOS`), `SOLICITUD_ADMINISTRATIVA` (replicado de MACHINE a
PERSONAL, nunca había existido ahí). Cada tanda verificada con
`calibrate_fase_a_keywords` (dry-run) antes de `--apply`, incluyendo
2 falsos positivos reales detectados y excluidos antes de escribir
mal ningún dato ("CIRCULAR INFORMATIVA PERMISO CONDUCIR" genérica en
raíz de `DOC. PERSONAL`; "Los trabajadores autónomos estarán
obligados..." texto legal genérico -- este último sí llegó a
aplicarse mal a 2 archivos, revertido en la misma sesión).

**Comando nuevo `apply_formacion_folder_default.py`** (commiteado,
dry-run por defecto): fallback post-Fase A que asigna `FORMACION` a
todo lo que quede sin tipo bajo `DOC. PERSONAL/FORMACION TRABAJADORES`
-- confirmado con muestra real (30 archivos de subcarpetas distintas)
que el 100% de ese árbol es documentación de soporte de formación.
Nunca puede pisar un tipo más específico ya resuelto (solo actúa sobre
`document_type__isnull=True` en el momento de ejecutarse). Aplicado:
**1.143 archivos** (458 con persona resuelta, 685 con dominio
pendiente).

**Método de cierre real, a petición explícita de Miguel Ángel tras
detectar que ir de 3-4 tipos en 3-4 tipos era insostenible a este
volumen:** barrido de **firmas de tipo** sobre todo el remanente --
quitar de cada nombre de archivo toda palabra de nombre real
(`PersonIdentity.given_name`/`first_surname`/`second_surname`) y toda
fecha, agrupar por lo que queda. Bajó el remanente real (EPIS aparte)
de **3.376 archivos en 194 patrones distintos (3+ archivos) a 1.287
en 64 patrones** en una sola tanda de correcciones dirigidas por esa
tabla completa, no por hallazgos sueltos.

**Estado final real de `DOC. PERSONAL` al cierre (verificado contra
BD, no de memoria):**
- **14.706 archivos ya con tipo** (histórico + lo añadido hoy).
- **2.565 EPI**, aparte, otro flujo (extracción a `EpiDelivery`,
  nunca tipado por este recorrido -- confirmado de nuevo por Miguel
  Ángel en esta sesión).
- **1.270 sin tipo, techo real de Fase A** -- 315 sin ninguna palabra
  de tipo tras quitar nombre/fecha (imposible resolver por nombre de
  archivo), resto en su mayoría imágenes/capturas WhatsApp sueltas sin
  texto legible. Necesita OCR real (Fase B), no más calibración de
  palabras clave.
- **2.062 con tipo correcto pero sin persona/dominio resuelto** --
  este es el trabajo real pendiente de mayor volumen, no ruido.

**Preguntas arrastradas de S56-S59 (Fase A del resto del catálogo,
OneDrive de GRUALDI SL, techo de `EXCEDENCIA`) -- retiradas de la
hoja de ruta.** Miguel Ángel las señaló en esta sesión como
preguntas que no correspondían/no tenían contexto real vigente;
quedan cerradas, no se vuelven a arrastrar.

**Commits reales de la sesión** (13, `17e2f59..763a417`): fix del bug
RM (`d2fe117`), 4 tandas de calibración
(`5a090a6`/`d177363`/`1315497`/`16adae9`), fix de exclusión universal
de EPI en `folder_based_type()` (`31f09e4`), 3 tipos nuevos
(`32b6c33`), comando `apply_formacion_folder_default` (`d413937`),
cuarta pasada sobre firmas (`06ac9c2`), fix final `TARJETA DE
CUALIFICACION` (`763a417`). Ningún archivo `.py` de modelo tocado --
las 3 filas de catálogo nuevas son datos (`DocumentTypeCatalog`), no
requieren migración de esquema.

---

## HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (sustituye por completo a
## cualquier "pendiente" suelto de bloques anteriores)

**EMPEZAR AQUÍ, SIN PREGUNTAR POR DÓNDE EMPEZAR -- instrucción
explícita de Miguel Ángel al cierre de S63. Sesión planificada para
mañana, desde el PC de la oficina (nunca Android para este bloque --
"un engorro" verbatim), usando una o varias VMs de Compute Engine con
varias instancias en paralelo para reducir tiempo.**

1. **Punto 1 -- resolver dominio de los 2.062 archivos con tipo
   correcto pero sin persona vinculada.** Ciclo
   `resolve_domain_pending_types` + `trash_orphan_personal_documents`
   ya existente (ver S58/S62), con `--types` explícito cubriendo
   también los 3 tipos nuevos de hoy (`CARNET_GRUISTA`,
   `RECURSO_PREVENTIVO`, `REGISTRO_JORNADA`) y el resto de tipos
   reales que aparezcan en el desglose. **Criterio de cierre:** cada
   tipo se resuelve a una persona real o se manda a papelera como
   huérfano -- no se deja sin decidir.
2. **VM de esta sesión (`h28-ocr-batch`), decisión explícita de
   Miguel Ángel al cierre: se borra por completo** (detenida, sin
   nada persistido en disco -- "no sirve para nada"). **Mañana se
   crean las VMs que hagan falta desde cero** -- una para empezar, y
   más si el volumen lo justifica (hasta 3 VMs x 3 instancias cada
   una si hace falta, criterio de "tiene prisa" ya documentado en
   `SESSION_VARIABLES.md`). Recordar `com-environment-management`
   sección 1.1 para el bootstrap de cualquier VM nueva (nunca `pip
   install` suelto).
3. **Punto 2 -- solo cuando el punto 1 esté agotado: pasar los 1.270
   archivos reales sin tipo (EPI aparte) por OCR (Fase B).** Lo que
   OCR resuelva, se clasifica. Lo que OCR no resuelva, decidir en esa
   sesión según volumen real: llamada a Gemini como respaldo, o
   revisión manual directa -- decisión explícita de Miguel Ángel
   pendiente de tomar con el dato real delante, no de antemano.
4. **EPIS (2.565 archivos, `DOC. PERSONAL` + `ENTREGA EPIS`) --
   siguen fuera de este flujo, confirmado de nuevo en S63.** Pasan a
   información en base de datos (extracción a `EpiDelivery`), no a
   `document_type`. Se acometen al final, como ya estaba decidido
   desde S48/S58 -- no se tocan mientras quede trabajo real de
   dominio u OCR pendiente.
5. **Máquinas -- 300 de 557 activas con hueco de documentación
   obligatoria (649 huecos), hallazgo de S62, sin tocar todavía.**
   Tarea aparte de personal, para cuando el hito vuelva a máquinas o
   Miguel Ángel decida priorizarla explícitamente.
6. Resto de la hoja de ruta arrastrada de H30, sin tocar en S63:
   `FICHA_TECNICA` vs `ITV`, backfill de fecha, duplicados de
   seguro/OCA, "renombrado retroactivo" genérico sin mecanismo
   reutilizable.
7. Carpetas pequeñas de `DOC. PERSONAL/PERSONAL` (arrastrado desde
   S60, sin avanzar en S63 tampoco -- **arrastrado 2.ª sesión sin
   avanzar**): `PENDIENTES` (44), `AUTONOMOS SUBCONTRATAS` (14),
   `PRACTICAS` (6), `PARTES BAJA PATERNIDAD` (1). Sin patrón dominante
   claro en la muestra ya vista -- **pregunta directa obligatoria al
   arrancar la próxima sesión que toque este punto:** ¿revisar tipo
   por tipo estas 4 carpetas ahora, o esperar a que el volumen de
   dominio/OCR esté cerrado?

## DECISIÓN REGISTRADA EN S64 (2026-08-24) -- `CERT_LIMITACIONES` NO SON
## PLANTILLAS, SON DOCUMENTOS REALES; YA SE HABÍA CONFIRMADO ANTES SIN
## QUEDAR ANOTADO EN NINGÚN SITIO

Durante el dry-run de `resolve_domain_pending_types` en S64 (Grupo B,
0% de resolución), el modelo asumió por el nombre genérico del archivo
que los 3 `.docx` de `CERT_LIMITACIONES`
(`DOC. PERSONAL/CERTIFICADO LIMITACIONES APTOS MEDICOS.docx`,
`DOC. PERSONAL/INVESTIGACION ACCIDENTES/CERT.TRABAJADOR LIMITACIONES
REC.MEDICO.docx`, `DOC. PERSONAL/RECONOCIMIENTOS MEDICOS/CERT.LIMITACIONES
RM TRABAJADOR.docx`) eran plantillas en blanco -- **asunción
incorrecta**, corregida por Miguel Ángel con una captura real de uno de
estos documentos (certificado de uso de EPIs de GRUAS ADOLFO ALVAREZ
SL, firmado por Alejandro Álvarez Díaz como administrador, nombrando a
D. Juan Manuel Alhamar Avellaneda con DNI real). Miguel Ángel, verbatim:
*"Antes de dar por sentado a esos que dicen que parece que son
plantillas, concretamente los DocCX. Voy a mirar antes lo que son. De
hecho, ya lo vimos el viernes, pero no lo anotaste en ningún sitio. Así
que no puedes sacarlos. Esos van para OCR."*

**Consecuencia real:** son documentos reales cumplimentados con nombre y
DNI de un trabajador concreto dentro del cuerpo del `.docx` -- el nombre
nunca vive en el nombre de archivo, por eso los tres resolutores de
`resolve_domain_pending_types` (que solo miran carpeta/nombre de
archivo) no tenían ninguna oportunidad de resolverlos. **No se excluyen
del ciclo de vinculación** -- pasan a Fase B (extracción de
texto/OCR), no a revisión manual ni a exclusión.

**Confirmado por Miguel Ángel en S64:** "van para OCR" en sentido amplio
de extracción de texto, no el pipeline Tesseract de Fase B -- al ser
`.docx` con texto ya seleccionable (no imagen escaneada), el mecanismo
real es **extracción de texto nativo del `.docx`** (sin Tesseract),
aplicando después el mismo heurístico de nombre (`_resolve_person_by_name`/
`_resolve_person_by_sliding_window`) sobre el texto extraído. Sin
construir todavía -- queda como tarea real de la hoja de ruta de H30,
no urgente frente al resto del punto 1.

## DECISIÓN REGISTRADA EN S64 (2026-08-24) -- `SEG_SOCIAL` ES PERSONAL,
## `SEGURO` A SECAS ES MÁQUINA (NORMA GENERAL, NO ABSOLUTA)

Confirmado con muestra real (`document_explorer/models.py` visto en
S64): `SEGURO`/`SEG_SOCIAL` son dos códigos de catálogo distintos, pero
`resolve_domain_pending_types` los trataba igual (ambos dominio
PERSONAL en el lote por defecto) sin que nadie hubiera verificado si
`SEGURO` a secas encajaba ahí. Muestra real de `SEGURO` (8 archivos, dry-run
S64): 100% bajo `DOC. MAQUINAS` (barca, cabezas tractoras, cargadora de
ruedas) -- seguro de maquinaria, no de persona.

Miguel Ángel, verbatim: *"si es seguro social, entonces sí son de
personal. Si pone seguro solamente, probablemente sean de máquinas."*
**Norma general, no absoluta** -- no excluye revisar casos concretos
si aparece un `SEGURO` real de persona.

**Consecuencia:** `SEG_SOCIAL` se queda en el ciclo de
`resolve_domain_pending_types` (dominio PERSONAL) tal cual. `SEGURO` se
saca de ese lote -- no pertenece a este ciclo de vinculación de
personal, necesita resolución contra `fleet.MachineAsset`
(`resolve_or_create_machine_asset()`), tarea distinta, no de este
punto 1 (que es exclusivamente el ciclo de dominio PERSONAL).

## ⛔ INCIDENTE REAL S64 -- EL REVERT DE S63 DEL FALSO POSITIVO
## "TRABAJADORES AUTONOMOS" NUNCA SE COMPLETÓ EN BASE DE DATOS

**Hechos, verificados con `git log`/`git show` reales, no de
memoria.** El anexo registraba (S63, ver bloque "Método de cierre
real" más abajo en este documento) que el falso positivo real
detectado tras un `--apply` -- los dos archivos "Los trabajadores
autónomos estarán obligados -CIII" (`.docx`/`.pdf`, dentro de
`DOC. PERSONAL/FORMACION TRABAJADORES/CUROS METADATA CAE`, texto legal
genérico sobre coordinación de actividades empresariales, sin ningún
trabajador concreto como sujeto) se había *"aplicado mal a 2 archivos,
revertido en la misma sesión"*.

**Verificado real:** el commit `b7ed3cc` de S63 solo añadió el patrón
a `EXCLUSIONS` de `calibrate_fase_a_keywords.py` -- protege pasadas
FUTURAS del heurístico, pero no contiene ninguna escritura de BD. No
existe ningún commit posterior en S63 que documente una reversión de
datos (una reversión real de `document_type` habría sido una
escritura directa vía Comando S, sin rastro en git, pero el propio
dry-run de `resolve_domain_pending_types` en S64
(`EnterpriseBot_002_GET.txt`) muestra que estos 2 archivos **siguen**
con `document_type=AUTONOMO`, `domain_object_id` pendiente, en
producción ahora mismo). El "revertido en la misma sesión" registrado
en S63 no se corresponde con el estado real de la base de datos.

**Decisión de Miguel Ángel en S64, verbatim:** *"el documento (...) de
los trabajadores autónomos estarán obligados, ese directamente lo que
habría que hacer es marcarlo para delete (...) es un documento que
realmente es que no nos dice nada (...) parece que está ahí como
huérfano. No lo vamos a asignar a ningún sitio, ni a company ni a
nada. Simplemente lo marcamos para la papelera (...) los dos archivos,
el de extensión de Microsoft Word y el PDF."* Vía `trash_dossier_entry`
(4.12, escritura pura de índice, `blob_name` intacto), nunca vía
reasignación de dominio.

**RESUELTO EN S64, confirmado con datos reales (no de resumen):**
`trash_dossier_entry` ejecutado sobre `pk=24445`
(`Los trabajadores autónomos estarán obligados -CIII.docx`) y
`pk=24446` (mismo nombre, `.pdf`) -- ambos `-> papelera OK`. Verificado
en `EnterpriseBot_005_GET.txt`. Incidente cerrado de verdad esta vez.

**Regla derivada:** este mismo patrón (un commit de código que
documenta "revertido aparte" sin verificación posterior contra datos
reales) es exactamente el tipo de afirmación que la regla de
verificación contra BD real (S014, com-mysql) existe para atrapar --
nunca dar por buena una reversión de datos solo porque el mensaje de
commit la menciona.

## DECISIÓN REGISTRADA EN S64 (2026-08-24) -- `CSS` PASA A DOMINIO
## COMPANY, MISMO CRITERIO QUE `PAGO_CORRIENTE` (MIGRACIÓN 0038)

Muestra real (2 archivos, único contenido de `CSS` sin dominio
resuelto): `CONTRATO ENCOMIENDA AGG 27-12-17.pdf` y `CONTRATO
ENCOMIENDA GRUALDI 27-12-17.pdf`, ambos en
`DOC. PERSONAL/FORMACION TRABAJADORES/FORMACION-MATERIAL EPICENTER`.
Miguel Ángel revisó el PDF real (adhesión al Contrato de Encomienda de
EpiCenter/Fundación Estatal, firmado por Jose Luis Álvarez Díaz como
representante legal de la empresa, con CIF/CNAE/cuenta de cotización
de la propia empresa) -- documento de empresa, no de un trabajador
concreto, pese a que la persona que firma en representación aparece
en el propio documento. Miguel Ángel, verbatim: *"Sí, sí, lo pasamos a
company sin problemas."*

**Discrepancia real detectada, sin resolver (fuera de lo pedido en
esta sesión):** el label original de `CSS` (migración `0003`,
"Certificado de estar al corriente (Seguridad Social)") no describe
el contenido real de estos 2 archivos -- posible label desactualizado
o tipo mal definido desde el origen. No se corrige aquí porque no fue
lo pedido; revisar si aparece más volumen real de este código en
sesiones futuras.

**Migración `0041_reasignar_css_domain_company_s64.py`** (mismo patrón
`RunPython` reversible por `code` que la 0038 para `PAGO_CORRIENTE`):
`CSS` de `PERSONAL` a `COMPANY`.

## ⛔ REGLA PERMANENTE, REGISTRADA EN S64 -- HUELVA QUEDA EXCLUIDA DEL
## CICLO DE VINCULACIÓN DOCUMENTAL DE H30. NO VOLVER A PREGUNTAR.

Ya estaba registrado en memoria de proyecto (Carlos Bas Blanco / David
Contreras Márquez, delegación Huelva, fuera de alcance para
`PersonIdentity` y vinculación de documentos, gestionada de forma
independiente por Huelva) pero no constaba como regla explícita del
propio ciclo de resolución de dominio de H30 -- se detectó en S64 al
ver a Bas Blanco aparecer en la muestra real de `REGISTRO_JORNADA`,
`BAJA_PERSONAL` y `CARNET_GRUISTA`.

Miguel Ángel, verbatim (S64): *"Huelva ya lo dijimos. Anótalo, que
queda excluido. No vayamos a estar cada vez que iniciemos una sesión
preguntando si lo excluimos. Ya está excluido. Ya no preguntamos más
por Huelva. Que en un futuro se decide: oye, mira, hay que meter
Huelva, pues ya lo meteremos. Mientras tanto, Huelva se queda fuera."*

**Consecuencia de obligado cumplimiento, sin excepción, para cualquier
sesión futura de H30 (o de cualquier otro hito que toque
`resolve_domain_pending_types`/`trash_orphan_personal_documents`/
`run_fase_a_sweep` u otro comando de vinculación de personal):**
1. Ningún archivo real o presunto de personal de Huelva se intenta
   resolver contra el roster de 70 activos, ni se manda a papelera
   como huérfano de plataforma -- se queda tal cual (tipo asignado si
   ya lo tiene, dominio pendiente) fuera de este ciclo, sin tocar.
2. **No preguntar** si se incluye Huelva al empezar una sesión nueva
   de este hito -- la respuesta ya es no, de forma permanente, hasta
   que Miguel Ángel decida explícitamente lo contrario.
3. Pendiente real, sin mecanismo construido todavía: identificar de
   forma sistemática qué archivos son de Huelva (hoy solo detectado
   por coincidencia visual de apellido en muestra, no por ningún
   marcador de datos) -- tarea aparte, no bloqueante para el resto del
   punto 1.

---

**Recordatorio operativo real para la próxima sesión:**
- **`SWAP/` se vacía por completo en el cierre de cada sesión, de
  cualquier proyecto** -- ver PASO 11 de `nfs-enterprisebot-pcs`.
- **Nunca invocar OCR manualmente en la consola de PythonAnywhere.**
- Al bajar archivos de una VM con `gcloud compute scp --recurse` y
  subirlos a PythonAnywhere, usar la conexión sftp efímera dentro de
  esa misma PowerShell -- nunca la consola sftp permanente.
- **Nuevo, S63:** antes de añadir una variante de palabra clave con
  prefijo compartido (p.ej. "CUALIFIC" dentro de "CUALIFICACION"),
  verificar contra `_build_pattern()` que el límite de palabra
  completa no la rompe -- 3 bugs reales de este tipo en la misma
  sesión, todos con el mismo patrón (palabra parcial como frase).
- **Nuevo, S63:** cualquier regla nueva de `FOLDER_TYPE_RULES` debe
  revisar si colisiona con la exclusión universal de EPI en
  `folder_based_type()` -- ya está centralizada, no hace falta
  repetirla, pero sí verificar que ninguna regla la esquive.


