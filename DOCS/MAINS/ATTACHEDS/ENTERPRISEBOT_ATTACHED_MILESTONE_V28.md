# H28 — Migración y Reorganización de Documentación Histórica

## 1. Objetivo del hito

Migrar toda la documentación histórica real de la empresa (hoy en
Microsoft 365/OneDrive, carpetas bajo `DOCUMENTOS GRUPO ALVAREZ` —
`DOC. MAQUINAS`, `DOC. PERSONAL`, y otras hermanas como `DOC. GRUAS
ALVAREZ`, `DOC. GRUAS LARIOS`, `DOC. GRUAS MAESTRANZA`, `DOC.
ASISTENCIA Y GRUAS GRANADA`, `DOC. MPE`, etc.) a Google Cloud Storage,
limpiarla y reorganizarla por completo, y solo entonces construir una
interfaz de servidor de archivos para el resto de la empresa.

Motivación explícita de Miguel Ángel (S030): "eliminar la selva" —
carpetas vacías, archivos duplicados con distinto nombre, dosieres
redundantes que ya tienen sus partes sueltos en el propio archivo, y
el problema concreto de nombres inconsistentes entre versiones del
mismo tipo de documento (ej. "ITV 2024-2024" vs "Inspección 2024" para
lo que debería ser el mismo documento con dos fechas distintas).

**Explícitamente fuera de alcance:** la ingesta ya construida de fotos
de partes de trabajo y de albaranes de repuestos no se toca — "eso va
a seguir exactamente igual."

**Relación con H23/H25:** este hito los precede y condiciona. Las
pruebas reales de H23/H25 (S028-S030) han evidenciado que trabajar
directamente contra la documentación histórica sin limpiar antes
genera ruido que dificulta validar si el enrutado/clasificación
automática funciona bien o si el problema es simplemente que el dato
de origen es un caos. H28 resuelve el origen del dato; H23/H25 siguen
siendo los hitos que consumen esa documentación una vez limpia.

## 2. Las tres fases

1. **Fase 1 — Copia.** Agente residente en una máquina Windows, sube
   en bruto (tal cual, con toda la suciedad real) las carpetas locales
   de Microsoft 365 elegidas a un cubo de GCS dedicado y separado de
   los cubos de producción de H23/H25 ("cubo sucio").
2. **Fase 2 — Clasificación.** Herramienta exclusiva para Miguel
   Ángel: explorador de archivos en la nube con clasificación asistida
   por Gemini + heurística, detección de duplicados, limpieza de
   carpetas vacías y dosieres redundantes, hasta dejar el árbol
   coherente y con nombres de archivo estables tanto para máquina como
   para humano.
3. **Fase 3 — Despachador.** Interfaz de servidor de archivos
   (subida/descarga ordenada) para el resto de usuarios de la empresa
   — construida solo cuando la Fase 2 ya ha dejado el árbol limpio,
   nunca antes.

Cada fase es condición de la siguiente. Este anexo, al abrirse el
hito, solo detalla la Fase 1 con hoja de ruta ejecutable — la Fase 2 y
la Fase 3 se diseñan con Miguel Ángel cuando llegue su turno, no antes
(evitar diseñar a ciegas una interfaz de clasificación sin haber visto
todavía el volumen y la forma real de la suciedad del cubo sucio).

## 3. Fase 1 — Decisiones de diseño confirmadas por Miguel Ángel (S030)

1. **Selección de carpetas: dinámica, no hardcodeada.** Las carpetas a
   copiar se eligen desde la propia interfaz del agente en el momento
   de usarlo ("se irán eligiendo desde esa primera interfaz de
   copia") — no una lista fija en configuración. El agente necesita,
   como mínimo, una pantalla/diálogo de selección de carpeta(s) local
   antes de lanzar la copia.
2. **Cubo sucio: sin transformar.** La copia inicial preserva la
   estructura y los nombres tal cual están en local, incluida toda la
   suciedad conocida (carpetas vacías, duplicados, dosieres
   redundantes). No se intenta limpiar nada durante la Fase 1 — eso es
   exclusivamente trabajo de la Fase 2.
3. **Vigilancia continua, con cuarentena — matiz importante.** El
   agente no es una migración puntual de usar-y-tirar: se queda
   corriendo en la máquina Windows vigilando las carpetas elegidas de
   forma indefinida. Pero tras la copia inicial, el comportamiento
   cambia: **los archivos nuevos que aparezcan después NO se escriben
   directamente en el árbol espejo del cubo sucio.** Van a una carpeta
   de cuarentena separada, dentro del mismo cubo o en otro dedicado
   (decisión pendiente de concretar en la implementación, ver Hoja de
   Ruta) — el sistema del servidor los revisará desde ahí para decidir
   qué son y a dónde corresponden, en vez de asumir que un archivo
   nuevo pertenece automáticamente al mismo sitio donde se detectó
   localmente.
4. **Subida directa a Google Cloud Storage**, no a través del
   servidor/endpoint de subida ya existente — usando la librería
   `google-cloud-storage`, con una cuenta de servicio dedicada para
   este agente (ver directriz de seguridad de secretos en
   `com-standards`, sección "Secretos" — la clave de esa cuenta de
   servicio nunca debe aparecer en ningún commit, mensaje de commit,
   ni documento versionado; vive solo en la máquina Windows local,
   fuera de este repositorio).

## 4. Decisiones de diseño cerradas por Miguel Ángel (S031)

Los 5 puntos que la Hoja de Ruta de S030 dejaba abiertos quedan
cerrados, verbatim, sin reinterpretación (directriz 4.8):

1. **Alcance de la primera copia real.** No hay lista fija ni
   acotación previa a dos carpetas concretas: "el alcance es copiar
   las carpetas que se digan, se van a copiar. Es decir, voy a coger
   una carpeta y voy a decir, esta carpeta se copia. Entonces se va a
   copiar esa carpeta, todas las subcarpetas, todos los archivos,
   todo. Todo lo que haya dentro de esa carpeta de forma recursiva.
   Todo absolutamente." — coherente con el punto 1 de la sección 3
   (selección dinámica), pero precisa que cada carpeta elegida se
   copia siempre de forma recursiva y completa, sin excepciones ni
   filtrado de contenido.
2. **Nombre y estructura del cubo sucio en GCS: `cgs_grupo_alvarez`**
   (en minúsculas — GCS no admite mayúsculas en nombres de bucket,
   verificado en línea contra la documentación oficial de Google
   Cloud el 2026-07-24; Miguel Ángel propuso el nombre en mayúsculas y
   confirmó el paso a minúsculas al conocer la restricción). Dentro
   del cubo se replica la ruta local completa tal cual.
3. **Cubo de cuarentena: aparte y dedicado**, distinto del cubo sucio
   `cgs_grupo_alvarez` (no un prefijo dentro del mismo cubo). Nombre
   del cubo de cuarentena pendiente de asignar en la sesión de
   construcción.
4. **Cuenta de servicio del agente:** Miguel Ángel la crea él mismo en
   Google Cloud Console, guiado paso a paso por el modelo durante la
   sesión de construcción — con permiso de escritura únicamente sobre
   el cubo sucio y el de cuarentena (principio de mínimo privilegio,
   sección 3 punto 4).
5. **Tecnología y formato de entrega del agente: ejecutable** —
   script Python (`watchdog` + `google-cloud-storage`) empaquetado
   con PyInstaller, con icono en la bandeja del sistema.

## 4bis. Recursos GCP reales creados en S031 (guiado paso a paso)

- **Proyecto:** el mismo `GOOGLE_CLOUD_PROJECT` que ya usa EnterpriseBot
  para Vertex AI (`gen-lang-client-0961484137`) — sin proyecto separado.
- **Cubo sucio:** `cgs_grupo_alvarez` — eu (multi-region), Standard,
  Uniform access, Not public (public access prevention enforced),
  Soft-delete (retención por defecto, 7 días), **Hierarchical
  namespace: Enabled**. Sin Object versioning ni Retention.
- **Cubo de cuarentena:** `cgs_grupo_alvarez_cuarentena` — misma
  configuración exacta que el cubo sucio (eu multi-region, Standard,
  Uniform, Not public, Soft-delete, Hierarchical namespace Enabled).
- **Labels aplicadas a ambos cubos:** `milestone: h28`,
  `purpose: dirty-migration` (cubo sucio) / `purpose: quarantine`
  (cuarentena).
- **Justificación de Hierarchical namespace (verificado en línea,
  documentación oficial de Google Cloud, 2026-07-24):** GCS no admite
  renombrado atómico de carpetas en un bucket sin HNS — cada
  renombrado de carpeta con muchos objetos son N operaciones de
  copia+borrado. Con HNS es una operación atómica sobre la carpeta,
  lo que beneficia directamente a la Fase 2 (reorganización,
  deduplicación, renombrado de dosieres). No soporta ACLs de objeto,
  versioning ni retention lock — no se pierde nada real porque ya se
  había decidido Uniform access sin versioning/retention para estos
  cubos de tránsito. **Restricción dura de la plataforma:** el ajuste
  HNS no se puede cambiar después de crear el bucket.
- **Rapid Cache: descartado.** Es una capa de caché de alto throughput
  pensada para cargas de lectura intensiva tipo entrenamiento ML;
  esta migración es un volcado periódico, no lectura repetitiva de
  alta frecuencia — no aporta beneficio y añade coste/complejidad.
- **Cuenta de servicio del agente:** creada sin roles a nivel de
  proyecto (permisos concedidos solo a nivel de bucket, mínimo
  privilegio). **Nombre real:**
  `enterprisebot-h28-migration-ag@gen-lang-client-0961484137.iam.gserviceaccount.com`
  — truncado por Google Cloud a 30 caracteres respecto al nombre
  propuesto originalmente (`enterprisebot-h28-migration-agent`, 34
  caracteres). **Usar siempre el nombre real (`...-ag@...`), nunca el
  propuesto originalmente (`...-agent@...`)** en cualquier código,
  configuración o documentación de sesiones futuras — origen de una
  incidencia real en S031 (ver más abajo).
- **Permisos concedidos (verificados con `gcloud storage buckets
  get-iam-policy`):** `roles/storage.objectAdmin` para
  `enterprisebot-h28-migration-ag@...` en `cgs_grupo_alvarez` y en
  `cgs_grupo_alvarez_cuarentena`. Aplicados vía Cloud Shell
  (`gcloud storage buckets add-iam-policy-binding`), no vía el
  formulario "Grant access" de la consola — ver incidencia.
- **Clave de la cuenta de servicio:** generada en S031 vía
  `gcloud iam service-accounts keys create` (Key ID
  `3309552c7eafa004aea366390f04b0f10cd729c6`), descargada por Miguel
  Ángel a su máquina Windows desde Cloud Shell y borrada de forma
  segura de Cloud Shell (`shred -u`) tras la descarga. Vive solo en la
  máquina Windows local, fuera de este repositorio — nunca debe
  aparecer en ningún commit ni documento versionado (mismo cuidado que
  el incidente de `GOOGLE_MAPS_API_KEY`).

### Incidencia S031 — nombre de cuenta de servicio truncado a 30 caracteres

**Origen:** el modelo propuso el nombre `enterprisebot-h28-migration-agent`
(34 caracteres) sin verificar el límite de 30 caracteres de Google
Cloud para IDs de cuenta de servicio. La consola lo truncó
silenciosamente a `enterprisebot-h28-migration-ag` al crearla, sin
aviso visible en el paso de creación. Esto causó una cascada de
fallos aparentemente inconexos con el email incorrecto
(`...-agent@...`): el campo "Grant access" de la consola no
reconocía el principal, el desplegable de autocompletado no lo
sugería, y `gcloud iam service-accounts describe` devolvía
`NOT_FOUND` — todos síntomas del mismo error de origen (email
inexistente), no de propagación de IAM ni de un bug de la consola,
como se llegó a sospechar durante la sesión antes de verificar con
`gcloud iam service-accounts list`, que reveló el nombre real.
**Lección:** verificar límites de longitud de nombre antes de
proponer identificadores de recursos GCP, y ante un fallo de
validación repetido en varias interfaces distintas, comprobar primero
si el dato de entrada es exacto (`gcloud ... list` sin filtro) antes
de atribuirlo a un problema de la plataforma.

## 5. Hoja de Ruta para la Siguiente Sesión de H28

Con las 5 decisiones ya cerradas, la sesión de construcción de la
Fase 1 hace, en este orden:

1. ~~Guiar a Miguel Ángel en la creación de la cuenta de servicio
   dedicada y de los cubos `cgs_grupo_alvarez` y
   `cgs_grupo_alvarez_cuarentena`.~~ **COMPLETADO en S031** — ver
   sección 4bis para los recursos reales, nombres exactos y permisos
   concedidos. Clave de la cuenta de servicio ya generada y en poder
   de Miguel Ángel en su máquina Windows.
2. ~~Construir el diálogo de selección de carpeta(s) local del
   agente Windows.~~ **CÓDIGO ESCRITO en S031** —
   `h28_migration_agent/main.py` (tkinter `filedialog.askdirectory`,
   invocado desde el menú del icono de bandeja).
3. ~~Construir la copia inicial en bruto al cubo sucio (recursiva,
   completa, sin transformar — sección 3 punto 2) con barra de
   progreso/log visible.~~ **CÓDIGO ESCRITO en S031** —
   `h28_migration_agent/uploader.py`
   (`transfer_manager.upload_many_from_filenames`, progreso vía log
   y notificaciones de bandeja, no barra visual gráfica — ver nota
   más abajo).
4. ~~Construir el modo vigilancia posterior (`watchdog`) con
   escritura en el cubo de cuarentena para archivos nuevos, nunca en
   el árbol espejo del cubo sucio (sección 3 punto 3).~~ **CÓDIGO
   ESCRITO en S031** — `h28_migration_agent/watcher.py`.
5. ~~Empaquetar como ejecutable con PyInstaller, icono en bandeja
   del sistema (sección 4, punto 5).~~ **DOCUMENTADO en S031** —
   comando de empaquetado en `h28_migration_agent/README.md` sección
   4. **No ejecutado todavía**: el modelo no tiene un entorno Windows
   real donde correr `pyinstaller` ni probar el icono de bandeja —
   pendiente de que Miguel Ángel lo ejecute y confirme.

**Nota sobre "barra de progreso" (punto 3):** la hoja de ruta original
pedía "barra de progreso/log visible". Lo construido en S031 es log
en archivo + consola + notificaciones puntuales de la bandeja del
sistema (recuento de archivos subidos/fallidos) — no una barra de
progreso gráfica dedicada. Si Miguel Ángel quiere una barra visual
real, es una mejora de UI a añadir en la sesión siguiente, no
construida en S031.

**Sin probar en un entorno Windows real** — todo el código de
S031 pasó `python3 -m py_compile` (sintaxis) en el workspace Linux
del modelo, pero ni el diálogo tkinter, ni la subida real contra los
cubos, ni el icono de bandeja pystray, ni el empaquetado PyInstaller
se han ejecutado de verdad. La sesión siguiente de H28 debe empezar
por una prueba end-to-end en la máquina Windows de Miguel Ángel
(`python main.py` en modo consola primero, antes de empaquetar) y
corregir lo que falle contra comportamiento real, nunca asumir que
compilar sin errores de sintaxis equivale a que funcione.

Infraestructura GCP lista y código de los 5 puntos escrito. La sesión
que retome H28 empieza por la prueba end-to-end en Windows real (ver
nota más arriba), no por escribir código nuevo.
