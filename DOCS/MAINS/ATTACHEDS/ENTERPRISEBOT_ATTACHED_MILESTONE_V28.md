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

**Probado en un entorno Windows real, dentro de la propia sesión
S031** — Miguel Ángel clonó el repo (`C:\EnterpriseBot`), creó el
entorno virtual, instaló `requirements.txt` sin ningún error de
compilación (confirmado: Python 3.14.6, `pyinstaller 6.21.0`,
`watchdog 6.0.0`, todo con wheels precompiladas, nada que compilar
desde fuente), configuró `H28_AGENT_KEY_PATH`, y ejecutó
`python main.py` en modo consola. Prueba end-to-end completa contra
una carpeta de prueba real (`prueba_h28`, 2 archivos + 1 subcarpeta):

- Icono de bandeja aparece correctamente, con el tooltip esperado.
- Diálogo de selección de carpeta (tkinter) funciona.
- Copia inicial: 2/2 archivos subidos, 0 fallos — verificado con
  `gcloud storage ls -r` que `archivo1.txt` y
  `subcarpeta/archivo2.txt` llegaron a
  `gs://cgs_grupo_alvarez/prueba_h28/` con la estructura de carpetas
  preservada.
- Vigilancia continua: un archivo nuevo creado tras la copia inicial
  (`archivo3_nuevo.txt`) se subió automáticamente a
  `gs://cgs_grupo_alvarez_cuarentena/prueba_h28/`, nunca al cubo
  sucio — comportamiento de cuarentena confirmado correcto.
- Datos de prueba limpiados de ambos cubos y de la máquina local
  tras la validación.

**Empaquetado con PyInstaller, probado en S031** —
`pyinstaller --onefile --windowed --name AgenteMigracionH28 main.py`
generó `dist\AgenteMigracionH28.exe` sin errores (solo un
`SyntaxWarning` interno de la librería `pystray`, ajeno a este
código, sin efecto funcional). Corrección previa necesaria antes de
empaquetar: `_configure_logging()` en `main.py` no debía añadir
`logging.StreamHandler()` cuando `sys.stdout` es `None` — caso real
en `--windowed`, sin consola — o el primer log hacía petar la app
(ver commit `c0abeb0`).

Prueba real del `.exe`: icono de bandeja correcto, copia real de una
carpeta de prueba con 3 archivos — 3/3 subidos, 0 fallos — y sin
procesos duplicados (dos PIDs por instancia es el comportamiento
normal del cargador `--onefile`, no una segunda instancia).

**Incidencia menor de sesión — variable de entorno de usuario y caché
de `explorer.exe`:** al lanzar el `.exe` por primera vez con doble
clic, dio el mismo error de "clave no configurada" aunque
`$env:H28_AGENT_KEY_PATH` estaba fijada — porque esa fijación solo
vivía en una ventana de PowerShell concreta, no a nivel de usuario.
Se corrigió con
`[System.Environment]::SetEnvironmentVariable(..., "User")`, pero
`explorer.exe` (y cualquier proceso ya abierto antes del cambio)
sigue usando su copia de entorno antigua hasta que se reinicia — para
lanzar el `.exe` por doble clic sin este problema, cerrar sesión de
Windows una vez tras fijar la variable.

## 6. Cierre de la Fase 1 (S031, continuación) — persistencia, reubicación de la clave, formato de blob confirmado, arranque automático

**Persistencia de carpetas vigiladas entre reinicios — decisión
verbatim de Miguel Ángel:** "el agente tiene que recordar qué estaba
haciendo y seguir haciéndolo". Implementado en `state.py`
(`agent_data/watched_folders.json`) y `main.py`
(`_resume_watched_folders()`, usado como `setup` de
`pystray.Icon.run()`). Alcance real, documentado como límite
conocido: retoma la *vigilancia* de cada carpeta, pero no repite la
copia inicial ni escanea archivos aparecidos mientras el agente
estaba apagado — solo los eventos en vivo de watchdog llegan a
cuarentena. Ver `h28_migration_agent/README.md` sección 6 para el
punto abierto derivado.

**Reubicación de la clave de la cuenta de servicio — incidencia de
Miguel Ángel:** la clave vivía en una carpeta de descargas ajena al
agente (`sdcard`, junto a decenas de archivos sin relación). Ahora
vive en `h28_migration_agent/agent_data/service_account_key.json`
(carpeta local nunca versionada — ver `.gitignore` nuevo en S031),
resuelta por defecto sin necesidad de variable de entorno
(`config.get_service_account_key_path()`); `H28_AGENT_KEY_PATH`
sigue soportada como alternativa opcional, con prioridad si está
fijada. Miguel Ángel movió la clave real y eliminó la variable de
entorno antigua durante la propia sesión.

**Formato del nombre de blob dentro del cubo sucio — confirmado
verbatim por Miguel Ángel:** "la ruta la vamos a guardar como raíz
esa carpeta" — la carpeta elegida en el diálogo es siempre la raíz
dentro del cubo; lo que haya por encima de ella en la ruta local de
Windows (unidad, OneDrive, `DOCUMENTOS GRUPO ALVAREZ`, etc.) nunca
se incluye. Confirma la implementación ya escrita en
`build_blob_name()` (`uploader.py`) — sin cambios de código
necesarios, solo cierre de la duda de diseño.

**Arranque automático — decisión de Miguel Ángel: tarea programada.**
Registrada `EnterpriseBot_H28_MigrationAgent` vía
`Register-ScheduledTask`, disparador `AtLogOn` del usuario de Windows
(no SYSTEM — un icono de bandeja necesita sesión de escritorio real),
sin privilegios de administrador (`-RunLevel Limited`). Comando
completo en `h28_migration_agent/README.md` sección 5. Probada en
S031 con `Start-ScheduledTask`: icono de bandeja apareció
correctamente. `LastTaskResult: 267009`
(`SCHED_S_TASK_RUNNING`) confirmado como resultado normal para una
tarea que se queda corriendo indefinidamente, no un error.

**Incidencia de sesión — reconstrucción del `.exe` bloqueada:** al
reconstruir el ejecutable tras los cambios de persistencia, PyInstaller
falló con `PermissionError: Acceso denegado` sobre
`AgenteMigracionH28.exe` — causa real: una instancia anterior del
`.exe` seguía en ejecución y Windows bloquea archivos abiertos por un
proceso. Resuelto cerrando el proceso (`Stop-Process`) antes de
reconstruir. Recordatorio para sesiones futuras: cualquier
reconstrucción del ejecutable requiere cerrar primero toda instancia
en marcha, incluida la que pueda haber arrancado la propia tarea
programada.

**Estado final de la Fase 1 al cierre de S031: completa.**
Infraestructura GCP, código de los 5 puntos originales, persistencia
entre reinicios, ubicación ordenada de la clave, formato de blob
confirmado, y arranque automático — todo construido y probado con
datos reales en la máquina Windows de Miguel Ángel. Ningún punto de
la Fase 1 queda sin decidir, sin construir o sin probar. Único punto
abierto para el futuro: el alcance de la persistencia frente a
archivos aparecidos con el agente apagado (`README.md` sección 6) —
mejora opcional, no bloqueante para empezar a usar el agente en
carpetas reales.
