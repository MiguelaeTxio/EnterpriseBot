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

### COMPLETADAS EN S031

Resumen ejecutivo de la sesión (detalle completo en las secciones 4,
4bis, 5 y 6 de este mismo anexo):

- Cerradas verbatim las 5 decisiones de diseño que dejó abiertas
  S030 (alcance de copia, nombre del cubo sucio, cubo de cuarentena,
  cuenta de servicio, formato de entrega del agente).
- Infraestructura GCP real creada y verificada: cubos
  `cgs_grupo_alvarez` y `cgs_grupo_alvarez_cuarentena` (con
  Hierarchical namespace), cuenta de servicio con permisos mínimos,
  clave generada y entregada a Miguel Ángel.
- Directriz técnica nueva 4.10 en el documento maestro: infraestructura
  GCP siempre vía Cloud Shell/`gcloud`, nunca guiando por formularios
  de la consola web — origen: incidencia real de esta sesión (nombre
  de cuenta de servicio truncado sin aviso visible en la consola).
- Agente de migración construido de cero (`h28_migration_agent/`):
  diálogo de selección de carpeta, copia inicial recursiva, vigilancia
  con cuarentena, empaquetado ejecutable, persistencia de carpetas
  vigiladas entre reinicios, y arranque automático vía tarea
  programada de Windows.
- Todo probado end-to-end con datos reales en la máquina Windows de
  Miguel Ángel — en modo consola y como ejecutable empaquetado — no
  solo verificado por sintaxis.
- Fase 1 de H28 queda completa. Único punto abierto: alcance de la
  persistencia frente a archivos aparecidos con el agente apagado
  (mejora opcional, no bloqueante).

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

## 5. Pruebas end-to-end de la Fase 1 (S031)

**Nota sobre "barra de progreso" (punto 3 de la sección 4):** la
hoja de ruta de S030 pedía "barra de progreso/log visible". Lo
construido en S031 es log en archivo + consola + notificaciones
puntuales de la bandeja del sistema (recuento de archivos
subidos/fallidos) — no una barra de progreso gráfica dedicada. Si
Miguel Ángel quiere una barra visual real, es una mejora de UI para
una sesión futura, no construida en S031.

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

## 7. Hoja de Ruta para la Siguiente Sesión de H28

### COMPLETADAS EN S032

- **Primera migración real ejecutada y verificada.** Miguel Ángel
  arrancó el agente ya instalado y eligió `DOC. MAQUINAS` como
  primera carpeta real de `DOCUMENTOS GRUPO ALVAREZ` a copiar.
  Verificado cifra contra cifra entre local, agente y GCS: 16.019
  archivos, 17.430.554.398 bytes exactos en los tres sitios
  (`gcloud storage du -s`, notificación del `.exe`, Propiedades de
  Windows). Copia sin fallos.
- **Mecanismo de materialización de OneDrive confirmado contra
  código, no solo por hipótesis.** `uploader.py` usa
  `transfer_manager.upload_many_from_filenames`, que abre/lee cada
  archivo con la API estándar de Python antes de subirlo — en
  Windows con OneDrive Files On-Demand, ese `open` fuerza la
  descarga si el archivo está "solo en la nube". Explica por qué
  `DOC. MAQUINAS` acabó cuadrando en tamaño pese a no estar
  materializada de antemano, y confirma que `DOC. PERSONAL` (vista
  con "Tamaño en disco" muy inferior al real, mismo síntoma) no
  necesita materialización manual previa — el propio agente la
  fuerza sobre la marcha al leer cada archivo.
- **Segunda migración real, `DOC. PERSONAL`, iniciada pero sin
  terminar al cierre de esta sesión.** Miguel Ángel la lanzó tras la
  confirmación anterior; sigue subiendo a `gs://cgs_grupo_alvarez/`
  a cierre de sesión (9,97 GB reales pendientes de completar y
  verificar).
- **Decisión explícita de Miguel Ángel:** no se abre el diseño de la
  Fase 2 todavía. Se planteó adelantarlo en paralelo mientras
  `DOC. PERSONAL` terminaba de subir, pero contradice directamente la
  sección 2 de este anexo ("evitar diseñar a ciegas... sin haber
  visto todavía el volumen y la forma real de la suciedad") y el
  punto 3 de esta misma hoja de ruta heredada de S031 — señalado
  explícitamente antes de proceder, sin decidir por cuenta propia
  (directriz 4.8). Miguel Ángel no llegó a confirmar el adelanto;
  la sesión se cerró con `DOC. PERSONAL` todavía en curso.

### COMPLETADAS EN S033

- **`DOC. PERSONAL` verificada y cerrada, cifra contra cifra, en los
  dos ejes:** bytes (`10.721.747.350` en Windows y en
  `gcloud storage du -s`) y número de archivos (`21.506` en ambos
  lados, usando `ls -r ... | grep -v '/\$'` / equivalente
  `findstr /v /e /c:"/" | find /c /v ""` en `cmd.exe`, para excluir
  las entradas de carpeta propias de un cubo con Hierarchical
  Namespace). Ambos comandos ejecutados sobre GCS tardan varios
  minutos sin mostrar salida (~40-45 min para el recuento completo
  con `ls -r` sobre >21.000 objetos desde una conexión móvil) — no es
  un cuelgue, es el comportamiento normal al no haber progreso
  intermedio; para sesiones futuras, lanzar este tipo de comandos con
  `nohup ... &` o similar en vez de esperar con la consola abierta.
- **Primera comparación (`du -s` vs Propiedades de Windows) detectó
  una discrepancia real de `10.540.883 bytes` y `5 archivos`.**
  Aislada por bisección manual de subcarpetas (comparar `du -s` de
  cada subcarpeta de primer nivel, descender solo en la que no
  cuadra, repetir) en vez de comparar listados completos — técnica
  mucho más rápida que un `ls -r` recursivo sobre el árbol entero y
  a reutilizar en verificaciones futuras similares.
- **Causas raíz identificadas, las 5 con evidencia directa, ninguna
  por hipótesis sin confirmar:**
  1. 1 archivo (`.../BAJAS/FM-FORM-5.0_17136_VSA-...(4).pdf`, 922.711
     bytes) — fallo real de subida registrado en
     `h28_migration_agent.log` (`[Errno 22] Invalid argument`).
     Longitud de ruta investigada (256 caracteres) y descartada como
     causa concluyente (por debajo del límite clásico de 260); causa
     exacta no confirmada, pero irrelevante para la resolución.
  2. 4 archivos (3 en `OPERARIOS/CAMPOS ROMAN, DOMINGO (TR)/`, 1 en
     `OPERARIOS/MILHEIRO FELICIO JORGE (GR)/`) — **no aparecen como
     fallo en el log**; el propio recuento inicial del agente
     (`21.502` archivos detectados) ya no los incluía. El hueco
     ocurrió en el momento del escaneo (`os.walk`), no en el de la
     subida. Causa exacta no confirmada — se investigó la hipótesis
     de fecha de creación/modificación posterior al corte de la
     copia inicial y se descartó con datos (`Get-ChildItem ... Where
     CreationTime/LastWriteTime -gt $corte` devolvió cero
     resultados). Hipótesis más plausible sin confirmar: archivos
     "solo en la nube" de OneDrive Files On-Demand no materializados
     en el instante exacto del escaneo.
  3. **Los 4 archivos NO fueron a cuarentena** — se verificó
     directamente (`gcloud storage du -s` sobre
     `cgs_grupo_alvarez_cuarentena/` dio solo 1 objeto, de
     `DOC. MAQUINAS`, nada de `DOC. PERSONAL`). Confirma que el
     diseño de cuarentena (sección 3 punto 3 de este anexo) solo
     cubre archivos detectados por el watchdog en vivo con el agente
     corriendo — no archivos que el escaneo inicial se saltó sin
     que el agente lo supiera.
- **Los 5 archivos subidos manualmente**, verificados uno a uno por
  nombre y tamaño antes de subir (nunca a ciegas): 4 con
  `gcloud storage cp` directo, 1 (el de ruta larga) con el prefijo
  `\\?\` de Windows para forzar la API a ignorar el límite clásico de
  ruta — funcionó a la primera, lo que sugiere que la longitud de
  ruta sí era la causa de ese fallo concreto, aunque sin poder
  descartar del todo otra causa coincidente.
- **Incidencia de sesión — consolas Windows mezcladas sin criterio
  claro**, señalada explícitamente por Miguel Ángel como fuente de
  fricción real. Aclarado para el resto de la sesión y para
  siguientes: `gcloud` autenticado y funcional solo en la consola
  "Google Cloud SDK Shell" (`cmd.exe` con prompt
  `...AppData\Local\Google\Cloud SDK>`), no en PowerShell (sin
  `gcloud` en el PATH) ni en `cmd.exe` genérico sin inicializar. Esa
  misma consola crasheó una vez con `UnicodeEncodeError` al procesar
  un carácter acentuado combinado (`\u0303`) en un nombre de
  carpeta/archivo — resuelto con `set PYTHONUTF8=1` al inicio de la
  sesión de consola, antes de cualquier comando `gcloud` que liste
  contenido con acentos.
- **Punto de diseño planteado por Miguel Ángel, pendiente de
  decisión explícita — no implementado sin confirmación (directriz
  4.8):** el agente no tiene ningún mecanismo de reconciliación
  posterior a la copia inicial; si el escaneo se salta archivos (como
  ha ocurrido aquí) o falla una subida, no hay detección ni reintento
  automático, solo lo que aparece en el log si se revisa a mano.
  Propuesta sobre la mesa: añadir un paso de reconciliación al final
  de `upload_folder_recursive()` que vuelva a listar local vs. cubo
  con la librería `google-cloud-storage`, reintente automáticamente
  las diferencias con backoff, y registre aparte
  (`IRRECUPERABLE: ...`) lo que siga sin subir tras varios intentos —
  generalizando así el punto ya abierto de
  `h28_migration_agent/README.md` sección 6 (que hoy solo cubre
  archivos nuevos aparecidos con el agente apagado) a cualquier
  archivo que el escaneo inicial no haya visto, sea cual sea la
  causa. **Sin decidir todavía si se implementa antes de abrir la
  Fase 2 o se deja anotado para más adelante.**

**Punto de resiliencia (ver COMPLETADAS EN S033) — confirmado
verbatim por Miguel Ángel e implementado en la misma sesión:**
"El sistema debe de poder afrontar los errores, tener los manejos
de errores, para que pueda recuperarse y que no se pierda
información. Y sobre todo, no tener que estar echando mano de
consola para una cosa que debe hacerse desde la plataforma, desde
el agente que hemos creado en disco." Motivación explícita: no se
puede diseñar la Fase 2 sobre una Fase 1 que exige intervención
manual por consola cada vez que el escaneo o la subida fallan —
harán falta más carpetas después de estas dos primeras.

**Implementado:**
1. Nuevo módulo `h28_migration_agent/reconciler.py` —
   `reconcile_folder()` vuelve a comparar la carpeta local contra el
   cubo (por tamaño, vía `google-cloud-storage`, nunca `gcloud`
   CLI), reintenta con backoff (3 intentos: 5s/15s/45s —
   `config.RECONCILE_MAX_RETRIES` /
   `RECONCILE_RETRY_DELAYS_SECONDS`) lo que falte o no coincida, y
   registra `IRRECUPERABLE: <ruta>` en el log para lo que siga
   fallando tras agotar reintentos.
2. **Automática:** se ejecuta sola al terminar cada copia inicial
   (`_run_reconciliation()` en `main.py`), sin paso manual
   adicional.
3. **Bajo demanda:** nuevo ítem de menú de bandeja **"Verificar y
   reparar carpeta"** (`_verify_and_repair_folder()`) — selecciona
   cualquier carpeta (ya migrada o nueva) y ejecuta la misma
   reconciliación en cualquier momento, sin salir del agente ni
   abrir ninguna consola.
4. `uploader.py`: `_iter_relative_file_paths` pasa a pública
   (`iter_relative_file_paths`) para reutilizarse desde
   `reconciler.py`, sin duplicar lógica de escaneo local.
5. **Probado con datos reales, no solo por sintaxis:** cliente/cubo
   simulados con archivos reales en disco, cubriendo tanto la
   reparación exitosa (2/2 archivos ausentes detectados y subidos)
   como el fallo persistente (marcado `IRRECUPERABLE` tras agotar
   los 3 reintentos, sin excepciones sin capturar). `py_compile` y
   longitud de línea (79 caracteres, PEP8) verificados en todo el
   agente tras los cambios.

**Matiz documentado como pendiente, no resuelto en S033** (ver
`h28_migration_agent/README.md` sección 6): la reconciliación bajo
demanda no se dispara sola al arrancar el agente sobre las carpetas
persistidas (`_resume_watched_folders()`) — hoy requiere que Miguel
Ángel abra el menú y la pida. Si se quiere automática también al
reinicio, queda pendiente de decisión explícita.

**Bug real encontrado en la primera prueba en producción, corregido
en la misma sesión (S033, continuación):** al probar "Verificar y
reparar carpeta" sobre las dos carpetas ya migradas, la
reconciliación encontró y "reparó" 8 huecos reales — 1 en
`DOC. PERSONAL` (archivo nuevo genuino, `PERSONAL/TALLER/VELOSO
SAMPAIO, ESTEVAO/Plantilla_RYMP TRANSPORTE
V4_897512981 PETRU IORDACHI 1.pdf`, subido correctamente) y 7 en
`DOC. MAQUINAS`. De esos 7, **6 eran huecos genuinos del escaneo
inicial de S032** (nunca detectados hasta ahora porque nunca se
había ejecutado una reconciliación sobre esa carpeta) y se
repararon bien. El **séptimo era un error real**: el archivo
`PLATAFORMAS (Z)/Z-123 6795MTL/Z-123 6795MTL FICHA TECNICA.pdf` ya
vivía correctamente en el cubo de cuarentena (detectado por el
watchdog como archivo nuevo tras la copia inicial, verificado ese
mismo día a primera hora de esta sesión) — la reconciliación no
tenía ninguna noción de cuarentena y lo subió también al árbol
principal, duplicándolo y saltándose el flujo de revisión que la
cuarentena existe para proteger (sección 3, punto 3 de este anexo).

**Corregido de inmediato, dentro de la misma sesión (directriz sobre
errores fuera de alcance detectados en sesión — aunque aquí sí
estaba en alcance, al ser código de la propia sesión):**
`reconcile_folder()` ahora comprueba primero si el blob ya existe en
`config.QUARANTINE_BUCKET_NAME` antes de subir cualquier archivo
"ausente"; si está en cuarentena, se deja intacto y se cuenta aparte
(`skipped_in_quarantine_count`), sin duplicar. El duplicado ya creado
en producción se borró manualmente
(`gcloud storage rm` sobre la copia del cubo sucio, cuarentena
intacta). Probado con datos reales (mock de dos cubos, caso
"ausente en ambos" vs. "presente solo en cuarentena") antes de
subir, y **confirmado también en producción tras reconstruir el
`.exe`**: nueva ejecución de "Verificar y reparar carpeta" sobre
`DOC. MAQUINAS` devolvió `0 reparados, 1 ya en cuarentena (sin
duplicar)` — exactamente el resultado esperado.

Commits: `d5d00b5` (versión inicial con el bug), `96637f8` (fix).

**Visor local de historial — confirmado verbatim por Miguel Ángel e
implementado en la misma sesión:** "el propio agente" da el visor de
tareas, agente y plataforma quedan deliberadamente separados (no se
construye nada en EnterpriseBot para esto). Nuevo módulo
`h28_migration_agent/history.py` — persiste cada copia y cada
reconciliación como evento estructurado
(`agent_data/history.json`, últimos `config.HISTORY_MAX_EVENTS`,
200 por defecto). Nuevo ítem de menú **"Ver historial"** — ventana
`tkinter`/`ttk.Treeview` de solo lectura, más reciente primero.
Probado con datos reales en producción: vacío ("Sin eventos
todavía") antes de cualquier acción, y con la fila real de la
reconciliación tras ejecutarla — confirmado con captura de pantalla,
no solo por construcción de código.

Commits: `aef90cf` (visor de historial).

**Estado final del agente H28 al cierre de S033:** copia inicial,
vigilancia continua con cuarentena, persistencia entre reinicios,
reconciliación automática y bajo demanda respetando la cuarentena, y
visor de historial local — todo construido, probado con datos
reales (no solo sintaxis) y verificado en producción sobre las dos
carpetas ya migradas. Miguel Ángel decidió cerrar el trabajo sobre
el agente aquí y abrir la Fase 2 en una sesión nueva, no continuar
en esta misma.

## 8. Fase 2 — Decisiones de diseño confirmadas por Miguel Ángel (S033, sesión de planificación, sin ejecución todavía)

Miguel Ángel confirmó explícitamente: **GCS sigue siendo la copia
centralizada y definitiva.** Se descartó explícitamente la
alternativa de servir archivos en vivo desde el PC de cada usuario
sin copia central — riesgo de disponibilidad (PC apagado, sin
conexión, equipo averiado o dado de baja) inaceptable para
documentación de empresa. El patrón confirmado para el futuro
(múltiples usuarios, cada uno con su propio agente) es híbrido: cada
máquina sigue siendo donde se genera/edita el archivo, pero todo se
sincroniza igualmente hacia GCS como fuente de verdad — la
plataforma podrá controlar agentes remotos (sondeo periódico de
órdenes pendientes, patrón ya usado en germen por este mismo
agente), pero el archivo final siempre vive en GCS, nunca solo en un
PC. **No diseñado en detalle todavía — es una ampliación futura,
posterior a Fase 2 y Fase 3.**

**H28 no es un sistema aparte de H23/H25 — es la misma
infraestructura, verbatim:** "H23 y H25 fueron una aproximación
errónea... es la misma infraestructura... cuando hagamos el barrido
final, la información que tengamos ahí se va a meter en los centros
de gasto y en los personales." La diferencia entre H23/H25 y H28 es
solo el punto de entrada: H23/H25 filtraban en la subida (solo
entraba lo vigente, ya asignado); H28 subió todo en bruto primero, y
ahora hace falta un paso de limpieza antes del "barrido final" que
lo vuelca en los mismos modelos ya existentes
(`MachineDocument`, `PersonalDocument`).

**Alcance de la Fase 2 — solo limpieza, tres frentes, sin
asignación a centro de gasto/personal todavía (eso es el "barrido
final" de la Fase 3):**

1. **Deduplicación por hash de contenido (SHA-256).** Mismo hash =
   mismo archivo. Decisión verbatim sobre qué copia conservar: "da
   igual... nos vamos a quedar con uno... porque lo vamos a
   renombrar" — el criterio de selección entre duplicados es
   irrelevante porque el paso 3 (renombrado) sustituye el nombre de
   todos modos.
2. **Detección de dosieres, tratados como una forma más de
   duplicidad** (ya se subieron en la Fase 1, sin filtrar, tal como
   estaba decidido para esa fase). Heurística propuesta por Miguel
   Ángel, verbatim: comparar peso y número de páginas de cada
   archivo contra la media de su carpeta — un archivo que se sale
   claramente por encima es candidato a ser un dosier que agrupa a
   los demás. **Matiz difícil, señalado explícitamente y sin
   resolver todavía:** un archivo puede pertenecer a más de un
   dosier a la vez dentro de la misma carpeta (solapamiento parcial
   entre compilaciones distintas) — la fórmula exacta para ese caso
   queda pendiente de diseño con datos reales delante.
3. **Renombrado sistemático por tipo de documento**, patrón híbrido
   máquina/humano — reconocible y mecanizable a la vez (ej. "ITV",
   "PermCirc"), nunca códigos opacos. Los documentos con fecha de
   caducidad llevan la fecha impresa en el propio nombre.
   Motivación explícita de Miguel Ángel: hoy existe una "selva de
   nombres" por rotación de personal a lo largo de los años (mismo
   tipo de documento subido con nombres distintos por cada persona
   que ha pasado por el puesto), que impide filtrar de forma fiable.

**Secuencia de trabajo confirmada, con el matiz de local-primero
añadido por Miguel Ángel:**

1. **Auditoría real contra la copia local** (hoy prácticamente un
   espejo de lo subido) — hash, tamaño, número de páginas, extensión
   y carpeta de cada archivo. Se hace en local por velocidad (evita
   las llamadas lentas a la API de GCS vistas hoy, ~40-45 min para
   un `ls -r` recursivo completo) y para no gastar cuota.
2. **La copia local nunca se modifica** — es solo dataset de lectura
   para diseñar las reglas (patrones de nombre, umbral de la
   heurística de dosieres) con datos reales delante, nunca a ciegas.
3. **Dry-run en la nube:** con las reglas ya calibradas en local, se
   simula sobre GCS (qué se borraría, qué se detectaría como dosier,
   cómo quedaría cada nombre) sin ejecutar nada real — solo informe.
4. **Verificación de coherencia** entre las cifras del dry-run y lo
   observado en local, antes de aplicar nada.
5. **Ejecución real en GCS**, solo tras la verificación del paso 4.
   Coherente con el principio ya establecido del sistema: ninguna
   eliminación automática sin confirmación humana (sección de
   "Key learnings" del sistema).

**Fuera de alcance de la Fase 2, anotado para la Fase 3 (barrido
final e ingesta en base de datos):** asignación de documentos a
centro de gasto/personal; generación de dosieres bajo demanda para
envío (se ensamblan y descargan en el momento, nunca se persisten en
GCS — decisión explícita: "no nos interesa subir los dosieres...
información redundante que no necesitamos estar pagando por ella");
gestión de altas/bajas de maquinaria desde la plataforma. La
conversión de manuales a Markdown **ya existe en producción** (H23,
S025 — botón "Convertir a Markdown" en la ficha de máquina, vía
`pymupdf4llm`) — pendiente de decidir en su momento si la Fase 3
reutiliza ese mismo mecanismo tal cual sobre los manuales que salgan
limpios de H28, o si hace falta algo distinto por venir de un origen
distinto (cubo migrado vs. subida directa del usuario).

**No ejecutado nada de la Fase 2 en esta sesión — solo diseño y
decisiones.** El primer paso real (la auditoría del punto 1) queda
para la siguiente sesión, con sesión fresca dedicada enteramente a
ello, según decisión explícita de Miguel Ángel al cierre.

### COMPLETADAS EN S034

Primera sesión de ejecución real de la Fase 2. Se construyó el paso 1
de la secuencia (la auditoría local), se ejecutó sobre
`DOC. MAQUINAS`, y **los datos reales invalidaron parte del diseño de
la sección 8**. Además se cerraron tres decisiones de arquitectura que
estaban abiertas desde S031/S033.

#### Decisiones de diseño cerradas por Miguel Ángel

1. **Reconciliación automática al arrancar el agente**, sobre las
   carpetas persistidas. Verbatim: *"creo que es lo más lógico de
   hacerlo de forma automática una vez que arranque el agente."*
   Cierra el punto que S031 dejó documentado y S033 dejó pendiente de
   decisión.

2. **La reconciliación manda a CUARENTENA, no al cubo sucio, y la
   copia del cubo sucio no se toca jamás.** Motivo: el reconciliador
   no puede distinguir un hueco del escaneo inicial de un archivo
   nuevo aparecido después — ambos se ven igual. Consecuencias
   queridas y confirmadas antes de implementar: el cubo sucio pasa a
   ser **foto fija de la copia inicial**, base estable para analizar
   sin que el árbol se mueva bajo los pies; y la cuarentena deja de
   ser un aparcamiento para convertirse en **cola de proceso**, con
   consumidor propio — una tarea always-on clasificadora que se
   diseñará en la Fase 3, de modo que todo lo que entre en cuarentena
   se clasifique de forma asíncrona.

3. **Dos documentos con el mismo nombre y distinto contenido son dos
   documentos reales.** Verbatim: *"no estamos hablando del mismo
   archivo, sino de un archivo con el mismo nombre... Miramos hash,
   son dos archivos diferentes. Tiene que clasificarse."* Caso de uso
   citado: un permiso de circulación sin fecha de caducidad pero
   reexpedido por cambio de titular o importación. Se conservan ambos
   y se diferencian al clasificar — el primero pasa a `00` y el
   segundo entra como `01`. **La decisión final de borrar corresponde
   a la supervisora de documentación (Yolanda) desde el explorador de
   archivos de la plataforma, nunca automática.**

4. **Comparación híbrida tamaño+MD5** en la reconciliación, elegida
   entre tres opciones por coste asimétrico: el MD5 remoto llega
   gratis en el mismo listado paginado de `list_blobs`, pero el local
   obliga a leer el archivo entero. El tamaño decide cuando difiere;
   el MD5 local solo se calcula cuando los tamaños coinciden.

5. **El solapamiento de dosieres queda disuelto, no resuelto por
   fórmula.** El matiz que S033 dejó explícitamente sin resolver — un
   archivo que pertenece a más de un dosier a la vez — deja de ser un
   problema. Verbatim: *"si lo que vamos a eliminar es el dosier, no
   el archivo."* Cada dosier se evalúa por su cuenta y los archivos
   individuales no se tocan nunca, así que la pertenencia múltiple es
   irrelevante.

6. **Los manuales van en una tabla aparte, indexados por MODELO de
   máquina, no por centro de gasto.** Decisión tomada al ver los
   datos de la auditoría. Verbatim: *"un modelo determinado de grúa,
   pluma, camión, va a tener su manual de uso. Independientemente de
   si tienes siete vehículos del mismo tipo, es una tontería tener
   guardados siete manuales. Guardas uno y dices, el manual es este...
   Guardamos siete punteros y un manual."* Esto **resuelve el
   conflicto entre deduplicación y asignación a máquina** sin borrar
   documentación: no se elimina el manual de ninguna máquina, se
   sustituye la copia por una referencia al único objeto real.

#### Trabajo de código (4 commits)

- `a8b7409` — Módulo `auditor.py` nuevo y nuevo ítem de menú
  **"Auditar carpeta (Fase 2)"**. Decisión de Miguel Ángel: *"podemos
  integrarlo en el agente"* — nada de scripts sueltos por consola,
  coherente con su criterio de S033. Estrictamente local y de solo
  lectura, sin tocar GCS ni la cuenta de servicio. Genera por archivo
  ruta relativa, carpeta, nombre, extensión, tamaño, SHA-256 y número
  de páginas si es PDF; salida a `agent_data/audits/` (ya cubierta
  por `.gitignore`) como CSV en streaming más un resumen en
  castellano. Incluye la reconciliación automática de arranque
  (decisión 1), con los vigilantes arrancando **antes** de reconciliar
  para no perder eventos en vivo durante los minutos que dura, y cada
  carpeta dentro de su propio guardado de errores.
- `1692f78` — La notificación de reconciliación nombra la carpeta.
  Defecto detectado en la primera ejecución real: con dos carpetas
  reconciliándose sola, dos avisos idénticos son indistinguibles.
  Más dos tildes en texto visible (`Auditoría terminada`, tooltip
  `Agente de Migración H28`).
- `e4c413a` — Destino de la reconciliación cambiado a cuarentena
  (decisión 2). `reconcile_folder` pasa a devolver cuatro elementos.
  Caso nuevo `PENDIENTE DE DECISIÓN`: si el archivo ya tiene en
  cuarentena una versión de distinto contenido, **no se sobrescribe**
  — destruirla es exactamente lo que prohíbe la decisión 3.
- `404092e` — Comparación híbrida tamaño+MD5 (decisión 4).

**Librerías verificadas en línea antes de implementar (directriz
4.4), con dos hallazgos que habrían fallado de escribirse de
memoria:**

- `pypdf` **6.14.2**, BSD-3-Clause, Python puro (`py3-none-any`). Se
  descartó PyMuPDF a propósito: AGPL y con extensión compilada, y el
  agente corre empaquetado sobre Python 3.14 en Windows.
- `blob.md5_hash` viene codificado en **BASE64, no en hexadecimal**.
  Compararlo contra un `hexdigest()` habría dado distinto siempre,
  incluso con contenido idéntico — es decir, habría mandado el árbol
  entero a cuarentena en cada arranque. La documentación advierte
  además de que la propiedad puede ser `None` (objetos compuestos);
  se prevé explícitamente.

**Endurecimientos derivados de incidencias reales ya documentadas**,
no de hipótesis: `to_long_path()` con prefijo `\\?\` en Windows, por
el archivo de ruta de 256 caracteres que falló en S033 con
`[Errno 22]`; y `os.walk(onerror=...)`, que registra un directorio
ilegible en vez de descartarlo en silencio — la hipótesis más
plausible detrás de los 4 archivos que el escaneo inicial de S032 se
saltó sin dejar rastro.

#### Resultado de la auditoría de `DOC. MAQUINAS`

Ejecutada el 2026-07-27, ~33 minutos para 17,4 GB.

| Métrica | Valor |
|---|---|
| Archivos | 16.022 |
| Bytes | 17.441.055.320 |
| Errores | 4 (todos de conteo de páginas, ninguno de lectura) |
| PDFs | 14.707 (14.703 con páginas leídas, 147.441 páginas) |
| Grupos de duplicados exactos | 1.521 (3.414 archivos) |

**Los 4 errores**, todos con su SHA-256 calculado correctamente y por
tanto deduplicables — solo falló el conteo de páginas. Dos requieren
subsanarse **desde origen**, según criterio explícito de Miguel Ángel:

- `PLATAFORMAS (Z)/Z-22/Z-22 FACTURA COMPRA.pdf` — **0 bytes, archivo
  vacío**.
- `PLATAFORMAS (Z)/Z-43 1479-KTJ/.../Z-43 Catalogo partes.pdf` —
  48 MB con bytes corruptos a mitad de archivo.
- `MANUAL DE INSTRUCCIONES/A-44/A44.pdf` — 31 MB, `/Pages`
  malformado (benigno).
- `VEHICULOS DE EMPRESA/.../Factura contraseña B29405040.pdf` — PDF
  cifrado con contraseña (benigno).

#### Hallazgos que invalidan parte del diseño de la sección 8

**A. La deduplicación exacta no es donde está el ahorro, y donde lo
está es peligrosa.**

| Categoría | Archivos | Espacio |
|---|---|---|
| Variantes de compresión, misma carpeta | 736 | **3,247 GB** |
| Duplicados exactos entre carpetas | 1.827 | 1,833 GB |
| Duplicados exactos, misma carpeta | 66 | 0,046 GB |

De los 1.521 grupos de duplicados exactos, **1.456 están repartidos
entre carpetas distintas** — son manuales compartidos por varias
máquinas del mismo modelo, uno por carpeta. Borrarlos chocaba de
frente con la regla de oro (*la carpeta es la asignación a máquina*).
**Resuelto por la decisión 6**: tabla de manuales por modelo con
punteros, no borrado.

**B. La mayor ganancia está en una categoría que no figuraba en el
plan de tres frentes: las variantes de compresión.** 3,247 GB, el
18,6% de la carpeta entera, setenta veces más que los duplicados
exactos seguros — y es la categoría **más segura**, porque todas las
copias viven en la carpeta de la misma máquina. El SHA-256 no las ve:
comprimir cambia los bytes. Caso extremo real, mismo manual de 568
páginas cuatro veces en la carpeta de la A-29: 176,5 MB + 38,5 MB
(`-comp`) + 26,1 MB (`-opt`) + 17,6 MB (`-opt2`) = 258 MB para un
documento de 17,6 MB. Otro: `A-62 ... MANUAL USO-print.pdf` ocupa
441 MB frente a los 17,7 MB del mismo manual de 1.354 páginas.

**C. La heurística de dosieres de la sección 8 no detecta dosieres:
detecta manuales.** La mediana de páginas de un PDF en `DOC. MAQUINAS`
es **1**, y el 75% tiene 2 o menos — es un archivo de ITVs, permisos y
fichas de una página. Cualquier manual se sale por encima de la media
de su carpeta y dispara la alarma. Los candidatos más extremos son
`TABLA DE CARGA.pdf` (2.240 págs), `MANUAL USO LTM 1230-5.1`
(2.223 págs), `MANUAL OPERADOR` (1.843 págs): documentos legítimos de
una pieza, no compilaciones.

Miguel Ángel propuso discriminar por nombre: los manuales llevan
impresa la palabra *manual*, *instrucciones*, *manual de uso*.
**Verificado empíricamente contra el CSV: la regla es correcta en el
fondo pero el vocabulario se queda corto** — con
`manual|instrucciones|operador|catálogo` solo se filtra el **37%** de
los 979 candidatos. Lo que sobrevive sigue siendo documentación de
modelo con otras palabras: `DESPIECE`, `TABLA DE CARGA`, `PARTS`,
`bal_` (*Betriebsanleitung*), `MUM` (*Manual de Uso y
Mantenimiento*). Y hay códigos opacos de fabricante donde el nombre
no dice nada en absoluto
(`es_1465114_SKI-MAN-DE2ES-10384-3521.pdf`,
`3121172_AF_1250AJP_JLG_Parts_English.pdf`). **El nombre solo no
bastará; el vocabulario hay que ampliarlo y complementarlo.**

**D. El caso de dos nombres contradictorios para el mismo contenido.**
Ejemplo real en `CAMIONES BRAZO (B)/B-40 8985JLF`: los archivos
`8985-JLF FICHA TÉCNICA.PDF` y `B-40 8985-JLF PERMISO DE
CIRCULACION.PDF` tienen el mismo SHA-256 exacto — un nombre de los
dos miente. No lo resuelve ninguna regla automática: es exactamente
el tipo de decisión que la decisión 3 asigna a Yolanda.

#### Incidencias de sesión

- **Clon local de Windows parado tres sesiones.** El `git pull` de
  apertura abortó: el árbol de trabajo tenía el código de S031-S033
  como modificaciones locales sin commitear, sobre un `47b4550`
  anterior a las tres. Causa: en S033 los archivos llegaron a la
  máquina por descarga y copia manual en vez de por `pull`. Resuelto
  con `git stash push -u` y verificación de que no se perdía nada —
  365 inserciones y **cero borrados** al comparar contra `f92f111`,
  prueba de que no había trabajo local sin subir. **Criterio
  establecido para el futuro: `git pull` en la máquina Windows al
  empezar cada sesión, y compilar desde ahí — nunca descarga y copia
  manual.**
- **18 archivos entraron al cubo sucio la madrugada del 28.** El
  agente se reconcilió solo a las 04:37 UTC (6 en `DOC. MAQUINAS`,
  12 en `DOC. PERSONAL`) todavía con el `.exe` de `a8b7409`:
  reconciliación automática ya activa, pero destino aún el cubo
  sucio. **Miguel Ángel lo dio por no problemático**, verbatim: *"no
  te preocupes por las copias que hayan ocurrido... de todas maneras
  todavía no hemos limpiado nada... el programa ha funcionado
  bien."* No requiere reparación; a partir de la próxima
  reconstrucción del `.exe` irán a cuarentena.

#### Limitaciones conocidas, anotadas y no resueltas

- **La auditoría bloquea el menú de bandeja mientras corre.** Los
  callbacks de menú de `pystray` se ejecutan en el bucle de mensajes;
  el `setup` de arranque no (verificado en la documentación oficial
  de `pystray` 0.19.5, que confirma que corre en hilo aparte y que
  `stop()` intenta unirlo, con espera hasta `SETUP_THREAD_TIMEOUT`).
  La auditoría debería correr en su propio hilo. No tocado en S034
  para no matar la auditoría en curso.
- **Caso `PENDIENTE DE DECISIÓN`** del reconciliador: derivado del
  criterio de Miguel Ángel, no dictado explícitamente por él. Queda
  pendiente de confirmación.
- **No se pueden identificar los 3 archivos de diferencia** entre los
  16.022 de la auditoría y los 16.019 verificados en S032: la
  verificación de entonces fue por conteo, no por lista, y no existe
  inventario de aquel momento.

### Hoja de ruta para la siguiente sesión

1. **Reconstruir el `.exe` en la máquina Windows.** Arrastra cuatro
   commits sin recoger (`a8b7409`..`404092e`). Antes, `git pull`;
   y cerrar toda instancia en marcha, incluida la de la tarea
   programada, por la incidencia de `PermissionError` de S031. Aviso:
   la primera reconciliación con el código nuevo mandará a cuarentena
   cosas que antes iban al cubo sucio — es lo correcto y esperado.
2. **Auditar `DOC. PERSONAL`** (~21.507 archivos, 10,7 GB) con el
   mismo mecanismo, y analizar su CSV. `DOC. PERSONAL` tiene una
   naturaleza documental distinta a `DOC. MAQUINAS` (documentos de
   persona, no manuales de modelo), así que **no se pueden dar por
   trasladados los hallazgos A-D sin comprobarlos**.
3. **Diseñar la tabla de manuales por modelo** (decisión 6): modelo
   de máquina como clave, un único objeto en GCS, punteros desde cada
   máquina. Es lo que desbloquea los 1,833 GB de duplicados entre
   carpetas sin borrar documentación de nadie. Encaje con
   `MachineDocument` (H23) pendiente de definir.
4. **Añadir la deduplicación de variantes de compresión como cuarto
   frente de la Fase 2** — hoy el mayor ahorro individual (3,247 GB
   solo en `DOC. MAQUINAS`) y el más seguro. Pendiente de decidir el
   criterio de qué copia se conserva: la grande suele ser la original
   sin degradar, la pequeña puede haber perdido calidad de escaneo.
5. **Rediseñar la heurística de dosieres** a la luz del hallazgo C:
   ampliar el vocabulario de exclusión de manuales
   (`despiece`, `tabla de carga`, `parts`, `bal`, `MUM`, `catálogo`,
   `handbook`) y buscar una señal complementaria para los códigos
   opacos de fabricante, donde el nombre no sirve.
6. Solo después: dry-run en la nube, verificación de coherencia y
   ejecución real, según la secuencia de la sección 8.

La Fase 1 sigue completa y probada, con sus dos migraciones reales
verificadas cifra contra cifra (S032-S033) y las dos carpetas
confirmadas íntegras de nuevo en S034. El paso 1 de la Fase 2 (la
auditoría) está construido y ejecutado sobre `DOC. MAQUINAS`; falta
`DOC. PERSONAL` y el rediseño de las reglas que los datos reales han
obligado a replantear.

