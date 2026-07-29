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
   **Concretado en S036:** la duda que este punto dejaba abierta
   ("dentro del mismo cubo o en otro dedicado") se resolvió primero
   como cubo dedicado (decisión 3 de la sección 4, S031) y se ha
   revertido después a **prefijo dentro del mismo cubo** — ver
   DECISIONES DE DISEÑO DE MIGUEL ÁNGEL — S036, punto 1.
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
  **PARA ELIMINAR (decisión de S036, punto 1):** la cuarentena pasa a
  ser un prefijo en la raíz de `cgs_grupo_alvarez`. El borrado del
  cubo va al final, y solo tras verificar que su contenido vivo se ha
  migrado al prefijo nuevo — es irreversible.
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

### DECISIONES DE DISEÑO DE MIGUEL ÁNGEL — S035

Registradas literalmente según se dictaron (directriz 4.8). No son
reinterpretación del modelo.

#### 1. Patrón de nombres normalizado

Antes de cerrar cómo se clasifica, se cierra el patrón de nombres. El
objetivo es que el propio nombre del archivo informe de todo su
contenido, sin nombres distintos para lo mismo ni formatos de fecha
distintos.

```
IDENTIFICADOR_TIPO_XXaaaammdd[_aaaammdd].ext
```

- **Identificador.** En máquinas, el código de la máquina (`A-29`,
  `Z-71`), que está bien admitido en la empresa. En personal,
  apellidos y nombre. Va delante para que un listado plano quede
  ordenado como si estuviera en carpetas.
- **Tipo de documento**, en mayúsculas.
- **Fecha**: `aaaammdd`, ocho dígitos seguidos, **sin guiones ni
  espacios dentro de la fecha**. El orden año-mes-día se eligió
  expresamente para que el orden alfabético coincida con el
  cronológico; con `ddmmaaaa` no ocurre. Con el año a cuatro dígitos
  el formato se lee solo, porque ningún día ni mes empieza por `20`.
- **Código de dos letras delante de cada fecha**, que declara qué es
  esa fecha:
  - `EM` — fecha de emisión
  - `VH` — válido hasta
  - `PV` — periodo de validez, seguido de las dos fechas
- **Separador entre bloques**: guion bajo.
- La nomenclatura es tipo de documento y fecha si la tiene.

Ejemplos dictados por Miguel Ángel:

```
RECOMED_EM22102026_VH22092027.pdf
POLIZA_PV01012026_01012027.pdf
```

**Sobre incluir el identificador en el nombre** (decidido tras
plantearlo Miguel Ángel y razonarlo en sesión): se incluye. En
máquinas, solo el código, **no la matrícula** — el código es
institucional y permanente, la matrícula puede cambiar si la máquina
se rematricula y dejaría mintiendo a todos los nombres. En personal,
apellidos y nombre en mayúsculas, sin tildes, sin coma
(`ALONSO PEDROSA MANUEL`), **generado siempre por la herramienta
desde la ficha del operario en base de datos, nunca tecleado a mano**.
Esa condición es la que evita que se repita el caso `PEDREGOSA`
documentado más abajo, y permite corregir un apellido en un solo sitio
y regenerar los nombres.

Los tipos van en español y sin tildes: son nombres de archivo, no
identificadores de código, así que la Regla de Oro del Idioma no
aplica, y el ASCII evita problemas de codificación y de orden
alfabético entre Windows y GCS.

#### 2. Los EPIs salen del sistema de archivos y pasan a base de datos

Mantener un archivo que se reedita cada vez que un operario recibe una
prenda es, en palabras de Miguel Ángel, una burrada. Toda la
información de EPIs se extrae y se lleva a base de datos, colgando del
operario: qué EPI, código, fecha de entrega y todo lo referente a la
entrega. Es mucho más eficiente: no se guardan archivos, se actualiza
la lista de EPIs que ha recibido el operario.

Plazo dictado: se hace ya, y si no da tiempo, al día siguiente.

Mientras se implementa, el criterio provisional es **coger las copias
últimas como vigentes y guardar las obsoletas**.

En el nombre de archivo, mientras existan, el acrónimo `EPI` de tres
letras delimita perfectamente el contenido en la carpeta de personal.
(Nota de datos reales: los archivos existentes usan `EPIS`, en plural,
así que el detector debe aceptar ambas formas.)

#### 3. Versiones en conflicto: se mantienen ambas

Ante el caso real de `EPIS MILHEIRO FELICIO, JORGE.docx` (ver más
abajo), la decisión es **mantener ambas versiones y numerarlas `00` y
`01`**, y resolver el asunto a nivel de base de datos cuando los EPIs
pasen a tabla.

#### 4. Interfaz de limpieza — pendiente de diseño

Habrá que ver cómo es la interfaz con la que se hará la limpieza: las
carpetas que hay con iconos, nombres y su árbol de directorios, y
herramientas de renombrado. Y habrá que ir añadiendo a la base de
datos todos los documentos y las rutas a cada centro de coste y a cada
operario.

---

### ANÁLISIS DE NOMBRES REALES — S035

Tres auditorías de la Fase 2 ejecutadas en sesión sobre carpetas
completas, para extraer el vocabulario documental y el catálogo de
formatos de fecha antes de escribir ninguna regla:

| Carpeta | Archivos | Bytes | Páginas PDF |
|---|---|---|---|
| `ALONSO PEDROSA, MANUEL (PTE TR)` (operario) | 48 | 28.558.942 | 147 |
| `A-29 E-0356-BBZ (GR)` (máquina) | 85 | 303.801.561 | 2.540 |

Errores de lectura: 0 en las tres. Grupos de duplicados exactos
(SHA-256): **0 en las tres**.

#### Hallazgo 1 — Las variantes de compresión son el 79% de la carpeta

```
568 pág | 176,5 MB | A-29 E-0356-BBZ MANUAL USO.pdf
568 pág |  38,5 MB | A-29 E-0356-BBZ MANUAL USO-comp.pdf
568 pág |  26,1 MB | A-29 E-0356-BBZ MANUAL USO-opt.pdf
568 pág |  17,6 MB | A-29 E-0356-BBZ MANUAL USO-opt2.pdf
```

Cuatro archivos, las mismas 568 páginas, cuatro tamaños. Suman
258,7 MB de los 303,8 MB de la carpeta. Dejando solo el menor se
recuperan **241 MB, el 79% de la carpeta**, que pasaría de 303,8 MB a
62,7 MB.

La deduplicación exacta encuentra **cero**: los cuatro tienen hash
distinto. La señal que los relaciona es el nombre base más el número
de páginas. Confirma el cuarto frente de la Fase 2 con un caso
medido, y da la escala: donde S034 midió un 18,6% sobre toda
`DOC. MAQUINAS`, aquí es el 79% de una carpeta.

**Segunda familia de variantes, no de compresión**: sufijo
`_unlocked` (original protegido y copia desbloqueada). Casos reales:
`REC SEG AXA 31-12-2025` / `..._unlocked`, y `REC.SEG AXA 01-01-2025`
/ `..._unlocked`. El mecanismo es el mismo, el sufijo distinto.

#### Hallazgo 2 — Vocabularios disjuntos entre los dos mundos

**Máquinas:** FICHA TECNICA, PERM.CIRCULACION, ITV, IPO, OCA, CE,
RAE, C.ADECUACION, CERT.NO TARJ.TTES, CERT MANTENIMIENTO, LIBRO
HISTORIAL, TABLA DE CARGA, MANUAL USO, POLIZA, REC.SEG, SEGURO, BAJA
TEMPORAL.

**Personal:** RM, ALTA, APTO DEFINITIVO, AUT USO MAQ, CARNET DE
CONDUCIR, TARJETA DEL CONDUCTOR, TARJETA CUALIFICACION CONDUCTOR,
RENOVACION CAP, DNI, CONTRATO INDEF, COMUNIC CONTRATO INDEF, Mod 145,
IDC, ENTREGA INFORMACION, EPIS, FORM (2H, 6H, 60H), ESTIBA DE
PLATAFORMAS, PARTE VACACIONES, DOC VARIOS.

**Ni un tipo en común.** La carpeta raíz decide qué diccionario aplica
el clasificador.

#### Hallazgo 3 — Catálogo completo de formatos de fecha

Sobre los 133 archivos únicos de las dos carpetas: 92 tienen fecha en
el nombre, 41 no. 101 ocurrencias de fecha en total.

| Ocurrencias | Formato | Ejemplos |
|---|---|---|
| 46 | `DD-MM-AA` | `6-3-23`, `08-05-26` |
| 40 | `DD-MM-AAAA` | `21-07-2027`, `28-10-2028` |
| 6 | `AAMMDD` | `150611`, `150911` |
| 3 | `AAAA` solo | `2025`, `2024` |
| 2 | `DD-MM` sin año | `18-08`, `01-09` |
| 2 | día + mes en palabra + año | `19 agost 2013` |
| 1 | `MM-AAAA` | `10-2014` |
| 1 | dos `AAMMDD` pegadas | `151210150311` |

**El 85% de las fechas son el mismo formato** —día-mes-año separado
por guion— y solo varía la longitud del año. La selva aparente son
**15 ocurrencias** en seis familias marginales.

Los años de dos dígitos presentes son 15, 16, 17, 18, 20, 21, 22, 23,
24, 25, 26, 27 y 31: **todos del siglo XXI**, sin un solo caso
anterior a 2013. La expansión `20` + `aa` es segura en este corpus.

#### Hallazgo 4 — La semántica de la fecha NO es derivable del nombre

Dos archivos del **mismo tipo** en la misma carpeta de operario:

- `RM ALONSO PEDROSA, MANUEL 04-04-2026.pdf` — fecha pasada, es
  emisión.
- `RM ALONSO PEDROSA, MANUEL 21-07-2027.pdf` — fecha futura, es
  caducidad.

Una tabla de "qué significa la fecha según el tipo" **no resuelve el
problema**, porque dentro de un mismo tipo aparecen los dos
significados. Lo mismo ocurre en máquinas: la serie
`ITV 28-4-23 → 28-4-24 → 28-04-2025 → 28-04-2026` es claramente fecha
de inspección (`EM`), mientras que `OCA ... 23-1-27` es caducidad.

**Consecuencia de diseño:** la normalización del *formato* es
mecánica y automatizable; la asignación de `EM`/`VH`/`PV` **exige
leer el documento**. Es el argumento técnico que sostiene la intuición
de Miguel Ángel de clasificar con llamadas a Gemini: no es preferencia,
es que la información no está en el nombre.

#### Hallazgo 5 — Casos que rompen el patrón

- **Un archivo, dos tipos.** El `+` se usa como "contiene ambos":
  `FICHA TECNICA+PERM CIRC`, `CE+RAE`, `FICHA TECNICA+ITV 12-3-2021`,
  `POLIZA AXA+REC.SEG AXA 31-12-22`. El patrón asume un tipo por
  archivo.
- **Colisión de tipo y fecha idénticos.** `FORM 2H PRL CONDUCTOR- ...
  1-3-23` y `FORM 2H PRL CONDUCTOR-GRUISTA ... 1-3-23`; y
  `EPIS 6-3-23` frente a `EPIS 6-3-23 desglosados`. Al quitar el
  nombre del operario, quedarían con el mismo nombre exacto.
- **Estados dentro del nombre**: `-signed`, `firmado 1`, `des`,
  `_unlocked`, `-comp`, `-opt`, `-opt2`, `_compressed (1)`.
- **Suciedad léxica**: espacio antes de la extensión
  (`RENOVACION CAP .pdf`, `RAE .pdf`, `ITC .pdf`), doble espacio
  interno (`A-29 E-0356-BBZ  ITV.pdf`), coma sin espacio
  (`ALONSO PEDROSA,MANUEL`), extensión en mayúsculas (`RECIBO2.PDF`).
- **Nombres opacos de escáner**: `doc06420120240227093305.pdf`.
  Contienen `20240227 093305`, es decir fecha y hora de escaneo en
  `aaaammdd`. Es una señal aprovechable para el hallazgo C de S034.
- **Fecha seguida de guion y palabra** (`08-05-24-signed`): rompe los
  parseadores ingenuos que exigen fin de token tras la fecha.
  Detectado al fallar el primer clasificador escrito en esta sesión.
- **Periodos escritos de cuatro maneras**: `27-2-20 A 31-12-20`,
  `150611 AL 150911`, `151210150311` (sin separador), y
  `18-08 AL 01-09` con el año en otro bloque del nombre.
- **`RECIBO 151210150311.pdf`**: la serie de recibos trimestrales
  (`150311 AL 150611`, `150611 AL 150911`, `150911 AL 151211`) sugiere
  que este debería cubrir diciembre 2015 a marzo 2016, pero la segunda
  fecha dice `150311`. Probable error en el original; requiere leer el
  documento.
- **El nombre del operario aparece de ocho formas** en 48 archivos:
  `ALONSO PEDROSA, MANUEL`, `ALONSO PEDROSA MANUEL`,
  `MANUEL ALONSO PEDROSA`, `D. MANUEL ALONSO PEDROSA`, `Manuel
  Alonso`, `Alonso Pedrosa`, `ALONSO PEDROSA`, y `ALONSO PEDREGOSA`
  (apellido erróneo, en dos archivos). La carpeta dice `PEDROSA`:
  caso de manual para la regla de oro de que la carpeta prevalece.

#### Hallazgo 6 — Nivel de carpeta duplicado, en los dos mundos

- `ALONSO PEDROSA, MANUEL (PTE TR)/ALONSO PEDROSA MANUEL/`
- `A-29 E-0356-BBZ (GR)/A-29/`
- `Z-42 1089-KNL/Z-42 1089-KNL/` (detectado en la reconciliación)

El nivel interno **tiene contenido real**: en el operario, 45 de los
48 archivos cuelgan de él y solo 3 quedan en la raíz. No es una
carpeta vacía que se pueda colapsar sin más. Es sistemático, no un
despiste suelto.

#### Hallazgo 7 — Dato personal fuera de sitio

`ALONSO PEDROSA MANUEL/cta bco Alonso Pedrosa.txt`: una cuenta
bancaria en texto plano dentro de la carpeta del operario, ya subida
al cubo. No es documentación laboral. Requiere decisión propia sobre
si debe estar ahí.

---

### INCIDENCIA S035 — El agente estaba fuera de `pip-tools`

Detectada por Miguel Ángel al revisar un `pip install -r
requirements.txt` que el modelo había entregado para reconstruir el
`.exe`.

`h28_migration_agent/` se creó en S031 con un `requirements.txt`
escrito a mano, con rangos `>=` y sin `requirements.in`, y se editó a
mano dos veces más (`23fbdc1`, `a8b7409`). Incumplía
`com-environment-management` sección 2 y la directriz 4.3 desde el
primer día.

**Consecuencia real ya materializada:** al no haber ninguna versión
fijada, esa instalación resolvió libremente y dejó el Python del
sistema de la máquina Windows con un árbol de dependencias distinto
del que compiló el `.exe` anterior, sin registro de cuál era. Las
versiones de aquella compilación son irrecuperables.

**Corregido en la misma sesión** (directriz 4.9), commits `41f8f21` y
`4a1d3b1`:

- `requirements.in` con las seis dependencias directas.
- `requirements.txt` generado con `pip-compile` 7.6.0 **en la máquina
  Windows y con Python 3.14.6**: 30 paquetes con versión exacta, cero
  rangos. Un candado compilado en otra plataforma no sería válido
  (ruedas `pywin32-ctypes`, `pefile`, `watchdog` win_amd64,
  `google-crc32c` cp314-win_amd64).
- Entorno virtual `h28_agent_venv` **rehecho de cero** sobre Python
  3.14.6. El anterior no se había usado nunca: la directiva de
  ejecución de PowerShell bloqueaba `Activate.ps1` sin que nadie lo
  detectara, y las instalaciones acababan en el Python del sistema. Se
  invoca el intérprete del venv directamente
  (`.\h28_agent_venv\Scripts\python.exe -m piptools ...`), que no es
  un script y no está sujeto a esa restricción, en vez de rebajar la
  política de seguridad de la máquina.
- Aislamiento verificado con datos: `pyvenv.cfg` declara
  `include-system-site-packages = false`, y las versiones del venv
  difieren de las del sistema (`pillow` 12.3.0 frente a 12.2.0,
  `cryptography` 49.0.0 frente a 48.0.1, `certifi` 2026.7.22 frente a
  2026.5.20).

**Aclaración de la skill.** La ambigüedad que permitió el desvío era
que `com-environment-management` estaba redactada enteramente en
contexto PythonAnywhere/Django (prefijo `python -m dotenv run`,
`SERVER_VENV`, salida a SWAP) y se leyó como si solo cubriera ese
contexto. Por instrucción expresa de Miguel Ángel se elimina la
ambigüedad: se añade una sección 1.1 de **alcance universal** —la
norma cubre cualquier entorno Python, cualquier máquina, cualquier
sistema operativo, con o sin Django, incluidos agentes de escritorio y
ejecutables empaquetados—, con prohibición expresa de justificar un
`pip install` suelto apelando a que "eso corre en Windows" o "es solo
un script auxiliar". Se añaden además: sección 3.0 aclarando el
prefijo `dotenv`, 3.4 obligando a compilar el candado en la plataforma
de destino, 2.2 con el criterio de archivo único incluyendo
herramienta de compilación, 4.1 sobre invocación directa del
intérprete en Windows, y el aviso de que `pip-sync` nunca se ejecuta
contra el Python del sistema.

**Dos hallazgos verificados en línea** antes de ejecutar (directriz
4.4) que habrían estropeado el resultado de haberse escrito de
memoria:

- `pip-compile` no regenera nada si encuentra un `requirements.txt`
  existente que ya satisface las dependencias. El archivo escrito a
  mano había que borrarlo **antes** de compilar.
- `pip-sync` no desinstala `pip`, `setuptools` ni el propio
  `pip-tools`, así que la herramienta sobrevive al `sync`.

**Pendiente:** `pip-tools` 7.6.0 avisa de que `--strip-extras` pasa a
ser el comportamiento por defecto en 8.0.0. No altera este candado
porque ningún paquete del árbol declara extras, pero conviene fijar la
opción explícitamente para que una actualización de `pip-tools` no
cambie el resultado en silencio.

---

### VERIFICACIONES EN PRODUCCIÓN — S035

**Reconstrucción del `.exe`.** Compilado desde el venv aislado con
`python -m PyInstaller` (invocación como módulo, verificada en la
documentación oficial de PyInstaller 6.21.0: el comando `pyinstaller`
no estaba en el PATH). Artefacto de 29.258.728 bytes. El log declara
`Python environment: ...\h28_agent_venv`, no el del sistema.

**`pypdf` correctamente empaquetado pese a importarse dentro de una
función.** Prueba de humo sobre una carpeta de 13 PDF: 13 de 13 con
número de páginas leído, 0 errores. Los avisos de PyInstaller
(`collections.abc`, `typing_extensions`, `fontTools`, `Crypto`) son
todos falsos positivos o dependencias opcionales que el conteo de
páginas no toca: `pypdf` usa `cryptography`, que sí está en el candado.

**Decisión 2 confirmada en producción.** La reconciliación de arranque
registró literalmente `El cubo sucio no se ha modificado`: repara
contra cuarentena y deja el cubo sucio como foto fija.

**Primera verificación de contenido de las dos carpetas.** Hasta ahora
la verificación era cifra contra cifra (recuento y bytes). Con MD5
real, `DOC. MAQUINAS` arrojó 3 discrepancias sobre 16.019 archivos
(1 subida a cuarentena, 2 ya en cola) y `DOC. PERSONAL` 1. Las cuatro
identificadas por ruta. Ninguna era diferencia de contenido con
tamaño igual.

**Los 3 de `DOC. MAQUINAS` no son los 3 de la pregunta abierta de
S034.** Fechas locales: `Z-71 cert. mantenimiento` creado el
2026-07-28 a las 08:22 (mientras el agente estaba parado por la
reconstrucción), `B-48 6440 NMK FICHA TECNICA` modificado el
2026-07-27 a las 14:14 (después de la auditoría de esa mañana). El
tercero, `Z-42 1089-KNL ITV 02-08-2026`, es de agosto de 2025 y no se
ha modificado desde julio de 2025 — **queda como cabo suelto**: si
fuera un hueco antiguo del escaneo de S032, la reconciliación de S033,
que ya comparaba presencia y tamaño, debería haberlo detectado. Sin
explicación.

**Coste medido de la comparación híbrida (decisión 4).** Primera
ejecución con MD5 real: `DOC. MAQUINAS` 11,5 minutos (18,09 GB leídos
por el proceso, contra los 17,4 GB de la carpeta: se lee entera),
`DOC. PERSONAL` 11,5 minutos. **23 minutos de reconciliación de
arranque, en cada inicio de sesión de Windows**, frente a los 14-17
segundos que tardaba sin MD5.

El comentario de `_find_mismatches` justifica el híbrido diciendo que
comparar siempre por hash obligaría a leer los 28 GB en cada arranque,
pero el código solo se salta el MD5 cuando el tamaño ya difiere o el
blob no expone MD5: en una carpeta sana el tamaño coincide en todos
los archivos, así que **se leen los 28 GB igualmente**. El ahorro
buscado no se materializa en el caso común.

**Pero el caso real demuestra que el MD5 hace falta.** El conflicto de
`EPIS MILHEIRO FELICIO, JORGE.docx` (local 32.890 bytes, cuarentena
32.882) se descargó y se comparó descomprimiendo ambos `.docx`:

| Parte del ZIP | Local | Cuarentena |
|---|---|---|
| `word/document.xml` | 72.871 B | 72.871 B, **CRC distinto** |
| `word/settings.xml` | 5.134 B | 5.108 B |
| `docProps/core.xml` | 722 B | 722 B, CRC distinto |
| `docProps/app.xml` | 989 B | 989 B, CRC distinto |

Único cambio de texto en 38 párrafos: `A fecha (10/07/2026)` →
`A fecha (27/07/2026)`. **El contenido cambió con `document.xml`
idéntico en peso**; los 8 bytes de diferencia del archivo entero
vienen de los `rsid` de Word en `settings.xml`, no del cambio. Si
`settings.xml` no llega a crecer, el `.docx` habría pesado
exactamente igual y solo el MD5 lo habría visto. El falso negativo que
motivó la decisión 4 no es hipotético.

**Estado a resolver:** la nube tiene la versión del 10/07 y la vigente
del 27/07 solo existe en el disco de la oficina. El reconciliador se
negó a sobrescribir, que es lo correcto según el criterio, pero la
copia buena no está subida.

**Carencia de observabilidad confirmada.** `_find_mismatches` no
invoca el `progress_callback`: `total_count = len(mismatches)`, de modo
que el contador solo empieza después, sobre la lista de diferencias ya
detectada. La fase larga —11 minutos de hash— transcurre sin una sola
línea de log entre "listando cubo de cuarentena" y el recuento de
archivos ausentes. Durante la sesión hubo que recurrir a
`ReadTransferCount` del proceso en Windows para saber por dónde iba.


### COMPLETADAS EN S035

**Punto 1 de la hoja de ruta anterior — cerrado.** `.exe` reconstruido
sobre `4a1d3b1`, empaquetado desde un entorno virtual aislado y con un
árbol de dependencias fijado y versionado por primera vez. Verificado
en producción: `pip list` con las 30 versiones exactas del candado,
`IMPORTS OK`, `pyvenv.cfg` con `include-system-site-packages = false`,
y versiones del venv distintas de las del Python del sistema
(`pillow` 12.3.0 frente a 12.2.0, `cryptography` 49.0.0 frente a
48.0.1). `pypdf` correctamente empaquetado pese a importarse dentro de
una función: prueba de humo con 13 de 13 PDF y 0 errores.

**Punto 2 — hecho.** Auditadas las dos carpetas completas:
`DOC. MAQUINAS` (16.022 archivos) y `DOC. PERSONAL` (21.507 archivos,
10.729.113.705 bytes, 23 errores de lectura). Más tres auditorías de
carpeta individual para extraer vocabulario documental. Total analizado
para el diseño del patrón de nombres: 37.529 nombres reales.

**Duplicación exacta: los dos mundos son opuestos.** `DOC. PERSONAL`
tiene 1.962 grupos de duplicados exactos, 4.091 archivos implicados y
**1.008.082.518 bytes recuperables** dejando una sola copia. En
`DOC. MAQUINAS` la duplicación exacta es marginal y el ahorro está en
las variantes de compresión. Las reglas de limpieza no pueden ser las
mismas para las dos carpetas.

#### Flujo completo de la Fase 2, dictado por Miguel Ángel (literal)

1. OneDrive sincroniza a local.
2. El agente vigila la carpeta local.
3. Cuando entra un archivo desde otro puesto de la red vía OneDrive,
   no se ve. Hay que verlo y hay que forzar su descarga.
4. Una vez descargado, se sube a cuarentena.
5. En cuarentena, el clasificador lo clasifica y lo renombra.
6. Si falta información para clasificar, se llama a Gemini para que lo
   lea y lo determine.
7. Con la clasificación y la carpeta de destino resueltas, sale de
   cuarentena y va a su carpeta.
8. Si tiene que dejar constancia en base de datos, se deja.
9. Si es un documento de EPIs, Gemini extrae los datos y se actualiza
   la tabla del operario al que pertenece.
10. **Todo el trabajo de organización se hace sobre la copia de Google
    Cloud Storage.** Esa copia es un espejo de OneDrive y es sobre ella
    sobre la que se trabaja: se organiza, se renombra y se mueve.

#### Corrección de una interpretación errónea del modelo (S034 → S035)

En S034 quedó escrito «el cubo sucio como foto fija», y el modelo lo
arrastró en S035 como si fuera una prohibición general de tocar el
cubo, llegando a plantear un tercer cubo de trabajo para no violarla.
**Miguel Ángel lo desmintió expresamente:** nunca dijo que la copia
fuera inamovible. Lo que hay es un espejo de OneDrive, y sobre ese
espejo se trabaja sin más condiciones que las que él ponga. El alcance
real de aquella frase es únicamente que **la reconciliación repara
contra cuarentena y no modifica el cubo mientras repara** — que es lo
que el propio código registra en cada pasada (`El cubo sucio no se ha
modificado`). Queda anotado aquí para que ningún modelo futuro vuelva a
extrapolarlo.

Consecuencia técnica favorable, verificada en línea (directriz 4.4):
en un cubo con Namespace Jerárquico **renombrar y mover carpetas es una
operación solo de metadatos, atómica y sin coste de copia**
(`gcloud storage mv`, y `objects.move` para objetos sueltos). Todo el
trabajo de reorganización de la Fase 2 se hace dentro del mismo cubo,
gratis. La decisión de S030 de crear los cubos con Namespace Jerárquico
resulta ser la que hace viable la Fase 2.

#### Rehidratación de archivos solo-en-nube — mecanismo validado en producción

La auditoría de `DOC. PERSONAL` arrojó 23 errores de lectura, 17 de
ellos `[Errno 22] Invalid argument` sobre archivos de un mismo
operario. Diagnóstico completo, por descarte y con datos:

- **No es longitud de ruta.** Con 268 caracteres, `os.path.getsize`
  funciona perfectamente; lo que falla es `open()`. Metadatos sí,
  contenido no.
- **No es el prefijo `\\?\`.** Falla igual con él y sin él.
- **Es OneDrive.** El atributo `RECALL_ON_DATA_ACCESS` (`0x00400000`)
  está encendido: son marcadores de posición sincronizados desde otro
  puesto, sin contenido en disco. El archivo de control, sano, no tiene
  ninguna marca.

**Detección: gratis.** El atributo viene en los metadatos del
directorio. No hay que abrir nada. `Get-ChildItem` filtrando por ese
bit dio exactamente 17, el mismo número que los errores de la auditoría
por una vía independiente.

**Rehidratación: `attrib.exe` NO sirve para este árbol.** Devuelve
`Formato de parámetros incorrecto` sobre rutas de 268 caracteres — es
una herramienta heredada sujeta al límite de 260. El bit `PINNED` no
llegó a ponerse. Lo que sí funciona es llamar directamente a la API de
Windows:

```python
k32.SetFileAttributesW("\\\\?\\" + os.path.abspath(ruta), nuevo_attr)
```

Con `PINNED` (`0x00080000`) puesto por esa vía, los 17 se anclaron sin
un solo fallo y OneDrive los descargó: `RECALL` pasó de 17 a 0 y el PDF
de prueba se abrió devolviendo `%PDF-`. La reconciliación posterior los
subió sola: **13 a cuarentena, 20 ya en cola, 1 pendiente de decisión**.

**Regla derivada:** cualquier automatización de la Fase 2 que toque
estos archivos debe ir por la API de Windows con prefijo `\\?\`, nunca
por herramientas de línea de comandos heredadas. Comprobado en
producción, no en la documentación.

#### Defectos reales localizados en código de producción

**1. Corregido en esta sesión (commit `42bd826`) — ventana vacía
imposible de cerrar.** Las cuatro funciones que usaban Tkinter creaban
su propia `tk.Tk()` y la destruían **antes** de los `messagebox`
posteriores. Sin raíz viva y sin `parent=`, Tkinter fabrica una raíz
implícita para dibujar el diálogo: nace visible, sin un solo widget
dentro, y nadie la destruye. Al abrir después el historial,
`_show_history` hacía otra `tk.Tk()` con esa raíz huérfana viva — dos
raíces Tk en el mismo proceso, caso roto de fábrica: la ventana no
dibujaba, su bucle de eventos no atendía y solo se cerraba desde el
administrador de tareas, matando el agente entero. Corregido con una
raíz única y oculta (`_get_tk_root`), `parent=` explícito en los siete
`messagebox`, y `_show_history` sobre `tk.Toplevel` con `wait_window()`
en vez de `mainloop()`. **Verificado por Miguel Ángel en producción:**
el historial abre correctamente incluso con el agente reconciliando.

**2. Pendiente — `os.walk` sin `onerror` en el recorrido que copia y
verifica.** `iter_relative_file_paths` (`uploader.py` línea 41) usa
`os.walk(root_folder)` a secas. Esa función la usan
`upload_folder_recursive` (la copia de la Fase 1) y
`_find_mismatches` (la reconciliación). El blindaje escrito en S034
—`_on_walk_error`— se quedó **solo en `auditor.py`**. El propio
docstring de `_on_walk_error` documenta por qué importa: los 4 archivos
de `DOC. PERSONAL` que nunca llegaron al cubo en S032 se perdieron
exactamente así. Un directorio ilegible se descarta en silencio, y lo
que el recorrido no ve, la reconciliación tampoco puede repararlo.

**3. Pendiente — ceguera ante archivos solo-en-nube.** Ni la copia ni
la reconciliación comprueban `RECALL_ON_DATA_ACCESS`. Un archivo que
llega por sincronización sin contenido no se puede abrir, luego no se
sube ni se hashea, y no deja constancia de fallo en ningún sitio salvo
si pasa el auditor. El mecanismo de rehidratación ya está validado
(punto anterior); falta integrarlo.

**4. Pendiente — el vigilante se traga excepciones no `OSError`.**
`_upload_new_file` (`watcher.py`) captura solo `OSError`. Cualquier
otra excepción —un error del SDK de GCS, por ejemplo— desaparece **sin
dejar rastro alguno**, porque ocurre en un hilo demonio de una
aplicación compilada con `--windowed`, sin consola donde imprimir.
Tampoco registra los éxitos, así que su silencio es ambiguo por
diseño.

**5. Pendiente — fase silenciosa del reconciliador.**
`_find_mismatches` no invoca el `progress_callback`:
`total_count = len(mismatches)`, de modo que el contador solo empieza
después, sobre la lista ya detectada. La fase larga —11 minutos de hash
por carpeta— transcurre sin una sola línea de log. Durante la sesión
hubo que recurrir a `ReadTransferCount` del proceso en Windows para
saber por dónde iba.

#### Coste medido de la comparación híbrida (decisión 4)

Primera ejecución con MD5 real: `DOC. MAQUINAS` 11,5 minutos (18,09 GB
leídos por el proceso contra los 17,4 GB de la carpeta — se lee
entera), `DOC. PERSONAL` 11,5 minutos. **23 minutos de reconciliación
de arranque en cada inicio de sesión de Windows**, frente a los 14-17
segundos que tardaba sin MD5.

**Pero el MD5 hace falta, y hay caso real que lo prueba.** El conflicto
de `EPIS MILHEIRO FELICIO, JORGE.docx` se resolvió descargando el blob
de cuarentena y descomprimiendo ambos `.docx`: único cambio de texto en
38 párrafos, `A fecha (10/07/2026)` → `A fecha (27/07/2026)`, con
`word/document.xml` **idéntico en peso** (72.871 bytes) y CRC distinto.
Los 8 bytes de diferencia del archivo entero venían de los `rsid` de
Word en `settings.xml`, no del cambio. Si ese archivo no llega a crecer
26 bytes, el `.docx` habría pesado exactamente igual y **solo el MD5**
lo habría visto. El falso negativo que motivó la decisión 4 no es
hipotético.

Queda pendiente rediseñar **cuándo** se recalcula ese hash, no si se
calcula: hoy se rehace entero en cada arranque.

#### Cabos sueltos de S034 — los dos cerrados

**Z-42 1089-KNL ITV 02-08-2026: fue un traslado, no un hueco.** El
archivo (556.981 bytes) está en el cubo sucio bajo la carpeta activa
(subido el 24/07) y en local bajo `OBSOLETOS/`. **Rocío, de
plataformas, lo movió a obsoletos el 27 de julio** porque ya había
salido el ITV nuevo. Mover un archivo conserva sus fechas pero genera
un evento de creación en la ruta nueva: por eso tenía fechas de 2025 y
aun así estaba en cola de cuarentena. **El sistema funcionó
correctamente de extremo a extremo**, con una persona real de la
empresa como origen del cambio.

**Los 22 archivos de LAVADO NAVARRO no fueron reorganización.** El diff
de rutas completas dio «en el cubo y no en local: 0» — pura adición. El
subárbol entero llegó por sincronización de OneDrive **hoy a las
11:01:30**, hora y media después de la reconciliación de las 09:18 y
seis minutos antes de que terminara la auditoría. La reconciliación no
los vio porque no existían.

#### Corrección: la fecha de los ITV es `VH`, no `EM`

En el análisis de nombres de esta misma sesión se escribió que la serie
`ITV 28-4-23 → 28-4-24 → 28-04-2025 → 28-04-2026` era «claramente fecha
de inspección (`EM`)». **Es falso.** La carpeta activa de la Z-42
contiene hoy `ITV 02-08-2027`, con fecha futura: una inspección con
fecha futura es imposible. Lo que hay es un ITV que caduca el
02-08-2026 y su renovación, que caduca el 02-08-2027. La fecha del
nombre es **caducidad**. Refuerza el hallazgo 4: la semántica de la
fecha no es derivable del nombre ni del tipo.

#### Otras correcciones de registro

- La hoja de ruta de S034 decía «cuatro commits sin recoger
  (`a8b7409`..`404092e`)». Eran **tres** (`1692f78`, `e4c413a`,
  `404092e`): el `.exe` era de `a8b7409`, confirmado por el `git pull`
  de la máquina Windows, que partía de ese commit.
- Durante la sesión el modelo afirmó que no existía línea de fin de
  reconciliación en el log. **Existe**: `reconciler` la escribe
  (`Reconciliacion completada en ...`). La afirmación salió de mirar
  solo `main.py`.

#### Pendiente de decisión de Miguel Ángel

**`EPIS MILHEIRO FELICIO, JORGE.docx` tiene tres versiones vivas**, no
dos: 32.844 bytes en el cubo sucio (migrada el 24/07), 32.882 en
cuarentena (27/07, «A fecha 10/07/2026») y 32.890 en local (vigente,
«A fecha 27/07/2026»). Tres reediciones en cuatro días. La decisión
registrada es mantener ambas versiones numeradas `00` y `01`, pero con
tres en juego queda por concretar: si se numeran las tres o solo se
conserva la vigente, y si el `00` es la más antigua o la vigente.

Es el argumento más fuerte de la sesión a favor de sacar los EPIs a
base de datos: cada reedición genera un conflicto que pide decisión
humana sobre algo que no es una decisión.

---

### DECISIONES DE DISEÑO DE MIGUEL ÁNGEL — S036

Registradas literalmente según se dictaron (directriz 4.8). No son
reinterpretación del modelo.

#### 1. La cuarentena pasa a ser un prefijo dentro del cubo sucio

Verbatim: *"Me parece una buena decisión cambiar la cuarentena como
prefijo dentro del mismo cubo y eliminar el cubo de la cuarentena."*

**Sustituye a la decisión 3 de la sección 4 (S031)**, que fijó la
cuarentena como cubo aparte y dedicado, y deja sin uso el cubo
`cgs_grupo_alvarez_cuarentena` descrito en la sección 4bis.

**Motivo técnico que llevó a plantearlo**, verificado en S035 contra
la documentación oficial: renombrar y mover **dentro** de un cubo con
Namespace Jerárquico es una operación solo de metadatos, atómica y sin
coste de copia. Cruzar frontera de cubo no lo es: es copia real más
borrado, con su coste, en **cada archivo clasificado**. Con la
cuarentena como cubo aparte, el flujo completo de la Fase 2 pagaba una
copia por documento al salir de la cola; como prefijo del mismo cubo,
todo el movimiento es gratis.

**Constricción técnica derivada, pendiente de que Miguel Ángel fije el
nombre:** el prefijo de cuarentena debe vivir en la **raíz del cubo**,
como hermano de las carpetas migradas (`DOC. MAQUINAS`,
`DOC. PERSONAL`, ...), nunca dentro de ninguna de ellas. El
reconciliador lista el cubo con `prefix=f"{folder_name}/"`
(`_list_remote_info`, `reconciler.py`): si la cuarentena colgara de una
carpeta migrada, sus blobs entrarían en esa misma lista y contaminarían
la comparación local-contra-cubo. El nombre concreto del prefijo queda
sin decidir; debe ser uno que no pueda colisionar jamás con una carpeta
real de OneDrive.

**Trabajo que implica, no ejecutado todavía:** migrar el contenido vivo
del cubo de cuarentena al prefijo nuevo (no se pierde nada), adaptar
`config.QUARANTINE_BUCKET_NAME` y sus tres consumidores
(`uploader.upload_single_file_to_quarantine`,
`reconciler.reconcile_folder`, `_list_remote_info`), reconstruir el
`.exe`, y solo entonces eliminar el cubo. El borrado del cubo es
irreversible y va al final, nunca antes de verificar la migración.

#### 2. El consumidor de la cuarentena vive en una tarea always-on ya existente

Verbatim: *"El vigilante de la cola de la cuarentena ya no va a estar
ejecutándose en una máquina, sino será una parte de una always on task.
Tendremos que aprovechar las que tenemos para no aumentar la cuota de
Python Anywhere."*

Concreta la decisión 2 de S034, que ya anotaba "una tarea always-on
clasificadora que se diseñará en la Fase 3", añadiendo la restricción
nueva: **sin ampliar cuota**.

**Verificado en el código real durante esta sesión, no supuesto:**
`enterprise_core/settings.py` ya define un `CELERY_BEAT_SCHEDULE` con
cinco tareas periódicas activas (`expire-whatsapp-sessions` cada 30
min, `check-in-meeting-reminders` cada 15, `expire-presence-statuses`
cada 5, `send-document-expiry-alerts` a las 3:00,
`self-heal-unassigned-personal-documents` cada 15). Que esas cinco se
disparen implica que Celery Beat corre dentro de la always-on `242133`
(worker Celery, ver `SESSION_VARIABLES.md`).

**Consecuencia:** el consumidor es **una entrada más en ese schedule y
un `tasks.py`** — cero tareas always-on nuevas, cuota intacta. La otra
always-on de EnterpriseBot (`234987`, bridge de voz) queda descartada
por ser un puente de audio sensible a latencia.

**Precedente de forma casi idéntica ya en producción:**
`self_heal_unassigned_personal_documents` barre cada 15 minutos las
filas pendientes y las procesa con Gemini. El consumidor de cuarentena
es el mismo patrón — barrer, clasificar, mover — y hereda el blindaje
de resiliencia que settings ya trae desde S025 (`acks_late`,
`prefetch_multiplier=1`, `reject_on_worker_lost`), con la misma
exigencia de idempotencia por documento.

#### 3. Todo archivo que entre en cuarentena genera una llamada a Gemini

Verbatim: *"Todos los archivos de cuarentena deben generar una llamada
a Gemini para que los catalogue. De tal forma que si nosotros enviamos
un archivo a cuarentena con un nombre que no tenga nada que ver con el
archivo, Gemini, leyendo el archivo, debe de poder clasificarlo bien y
enviarlo a la ruta adecuada."*

El nombre del archivo deja de ser fuente de clasificación. Gemini lee
el contenido, determina qué es, y de ahí sale la ruta de destino. Es
coherente con el hallazgo 4 de S035 (la semántica de la fecha no es
derivable del nombre) y lo lleva más lejos: tampoco el tipo lo es.

**Dimensionamiento a tener presente:** combinado con la decisión 2 de
S034 (la reconciliación repara *contra cuarentena*), cada
reconciliación que encuentre huecos dispara una llamada por archivo. En
la de S035 fueron 13 + 20 + 1.

#### 4. Cuenta de servicio: pendiente de verificación empírica

Verbatim: *"La cuenta de servicio es la misma. O debería ser la misma.
Habrá que verlo."*

**Dato registrado en la sección 4bis (S031):**
`roles/storage.objectAdmin` sobre los cubos de H28 se concedió **solo**
a `enterprisebot-h28-migration-ag@...`, a nivel de cubo, sin roles de
proyecto, por mínimo privilegio. Si la cuenta que la plataforma usa
para Vertex AI y GCS es otra, hoy no puede ni listar la cuarentena y
hace falta un binding nuevo vía `gcloud` (directriz 4.10). **No se
asume ni una cosa ni la otra: se comprueba antes de diseñar el
consumidor.**

#### 5. `EPIS MILHEIRO FELICIO, JORGE.docx` — las tres versiones se conservan

Cierra el punto que S035 dejó abierto. Verbatim: *"Los archivos de
Milheiro se nombrarán pues uno con 00, otro con 01 y otro con 02, como
ya habíamos dicho. Por fecha de creación de archivo, tomamos el 00 como
la más antigua."* Y sobre el destino: *"creo que lo mejor es subirlos
ya directamente a la cuarentena, para luego ya clasificarlos con el
clasificador y con el vigilante de la cuarentena."*

Con las cifras de S035 eso ordena así: `00` la del cubo sucio (32.844
bytes, migrada el 24/07), `01` la de cuarentena (32.882, «A fecha
10/07/2026»), `02` la local vigente (32.890, «A fecha 27/07/2026»).

**Punto abierto señalado y no resuelto:** para que las tres coexistan
en la cuarentena hacen falta tres nombres de blob distintos — subidas
con el mismo nombre, cada una pisa a la anterior. Queda por decidir si
el sufijo `00`/`01`/`02` se aplica al subir o si la cola usa otra
convención.

---

### CORRECCIÓN DE LA CADENCIA DEL BARRIDO (S036, 29-07-2026)

Miguel Ángel rechaza la cadencia de 30 minutos que se acordó al
diseñar el modo "puesta al día". Verbatim: *"el barrido de 30 minutos
es algo inviable, tenemos que ir al minuto e incluso menos, para el
agente, la always on task con su frecuencia, pero el agente cada 30
segundos o un minuto como mucho."*

**Sustituye a la decisión 1 del punto 2** registrada más arriba en esta
misma sesión. Media hora de ventana ciega es demasiado cuando el
vigilante ya falló una vez con la sincronización de OneDrive.

**Distinción explícita que fija esta instrucción:** la cadencia del
agente y la del consumidor de la cuarentena son **independientes**. El
agente barre cada minuto en la máquina de Windows; el consumidor
always-on de la Fase 3 tiene su propio ritmo, gobernado por
`CELERY_BEAT_SCHEDULE` en PythonAnywhere.

**Valor tomado: 60 segundos**, el techo que dio Miguel Ángel, por ser
el extremo conservador. Bajar a 30 es una línea en `config.py`, y se
hará cuando haya medida real de cuánto tarda un barrido sobre el árbol
de producción — que a día de hoy no la hay.

**Consecuencias técnicas que arrastra el cambio, ninguna trivial:**

1. **Doble `os.stat` por archivo, corregido.** `scan_folder` consultaba
   los atributos dentro de `is_cloud_only` y volvía a llamar a
   `os.stat` después. Sobre ~37.500 archivos eran 75.000 llamadas al
   sistema por barrido. `st_file_attributes` ya viene en el resultado
   de `os.stat`, así que se reutiliza: 37.500. A cadencia de media
   hora era irrelevante; a un minuto, en la máquina donde Miguel Ángel
   trabaja, no.
2. **Medición de la duración del ciclo.** Nadie ha medido cuánto tarda
   un barrido sobre el árbol real. Si tarda más que el intervalo, el
   hilo encadena barridos sin descanso. El bucle mide su propio tiempo
   y emite un `WARNING` explícito si un ciclo excede
   `CATCHUP_INTERVAL_SECONDS`. Se mide en vez de suponerlo.
3. **Ruido de log.** Registrar "sin novedades" en cada pasada serían
   1.440 líneas diarias. Las pasadas mudas bajan a `DEBUG` y se emite
   un latido en `INFO` cada `CATCHUP_HEARTBEAT_EVERY_SWEEPS` barridos
   (30, es decir ~30 minutos) con la duración del último ciclo. Así el
   log sigue probando que el hilo está vivo sin ser ilegible.

**Pendiente de dato real:** la primera cifra de duración que emita el
agente en producción decide si 60 segundos es holgado, justo, o
insuficiente para bajar a 30.

---

### COMPLETADAS EN S036

Sesión larga y enteramente sobre el agente de migración. Trece
commits, 1.845 inserciones y 316 eliminaciones sobre 11 archivos. Todo
lo escrito quedó **verificado en producción** sobre el árbol real
antes de cerrar, con cinco ciclos de recompilación del `.exe`.

#### Los cuatro defectos del punto 1 de la hoja de ruta — cerrados

1. **`onerror` ausente en `iter_relative_file_paths`** (`5c7579e`). El
   blindaje escrito en S034 se había quedado solo en `auditor.py`. Se
   extrajo a un módulo nuevo `fs_utils.py`, sin dependencia de GCS,
   para que `auditor.py` conserve su frontera de "estrictamente local"
   y no existan dos copias. La copia inicial y la reconciliación se
   etiquetan por separado, porque comparten escaneo y sin etiqueta no
   se sabe cuál dejó el hueco. Probado contra un directorio realmente
   ilegible: sin el manejador se pierde un archivo y se emiten **cero**
   líneas de log; con él, los mismos archivos y un ERROR nombrando
   operación y directorio.
   Por la 4.9 se corrigieron además dos huecos de la misma familia
   detectados al leer el código: `upload_single_file_to_quarantine` y
   el reconciliador abrían archivos sin el prefijo de ruta larga, que
   es exactamente lo que hizo fallar un archivo real de 256 caracteres
   en S033 — y en el reconciliador acababa en un `continue` silencioso.

2. **Ceguera ante archivos solo-en-nube** (`189d98b`). Constantes
   verificadas en línea antes de escribir nada, con un hallazgo que el
   anexo no registraba: un archivo solo-en-nube tiene `PINNED=0`,
   `UNPINNED=1`, `RECALL_ON_DATA_ACCESS=1`, de modo que **anclar no es
   solo encender `PINNED`** — hay que apagar `UNPINNED` en la misma
   máscara o se le dan a OneDrive dos órdenes opuestas. La aritmética
   de bits vive en su propia función pura para poder probarse fuera de
   Windows, y de paso evita el error de precedencia de `a | P & ~U`.
   En la reconciliación, el archivo solo-en-nube ya no entra en la
   lista de diferencias: antes se intentaba subir, se quemaban los tres
   reintentos con sus esperas de 5/15/45 s y acababa marcado
   IRRECUPERABLE sin serlo. `reconcile_folder` pasa a devolver cinco
   elementos y `main.py` los muestra.

3. **El vigilante se tragaba las excepciones** (`7edde53`). Capturaba
   solo `OSError`; cualquier otra desaparecía sin rastro en un hilo
   demonio de una aplicación `--windowed` sin consola. Tres ramas
   ahora: `OSError` como aviso (archivo a medio escribir), cualquier
   otra con `logger.exception` y traza, y el éxito nombrando el blob.
   `BaseException` deliberadamente NO se captura. Se añadió además el
   registro de la RECEPCIÓN del evento, para distinguir "watchdog no lo
   vio" de "lo vio y falló callando".
   Corrección de registro: el defecto de S035 decía que "tampoco
   registra los éxitos"; era impreciso — el éxito ya se registraba un
   nivel más abajo, en `upload_single_file_to_quarantine`.

4. **Fase de hash muda** (`16ea121`). `_find_mismatches` no invocaba el
   callback. Ahora informa cada 500 archivos con total real y **MB
   realmente leídos de disco** — no el tamaño acumulado de la carpeta,
   porque un archivo cuyo tamaño ya difiere nunca se hashea y contarlo
   daría una barra que miente justo donde se mira para estimar. Se
   separó del callback de reparación: miden cosas distintas sobre
   totales distintos, y compartirlo dejaría un contador subiendo a
   16.040 seguido de otro subiendo a 3, con la misma redacción.

#### Modo "puesta al día" (`fcc6602`) y su evolución

Módulo nuevo `catchup.py` con índice ligero por carpeta. Decisiones de
diseño consultadas antes de construir, no después.

- **Comparación por RUTA, no por fecha**, deliberadamente: en S035
  Rocío movió un ITV a `OBSOLETOS/`, y mover conserva las fechas, así
  que un criterio de "modificado desde el último barrido" no lo habría
  visto nunca. Probado replicando el caso exacto.
- **El primer barrido sin índice previo no sube nada**, solo siembra.
  Tratar los 37.500 archivos ya migrados como novedades volcaría el
  árbol entero a cuarentena y, con la decisión 3, dispararía 37.500
  llamadas a Gemini. Igual ante un índice corrupto. Ambos casos
  cubiertos por prueba.
- Un fallo de subida **no se apunta en el índice**, de modo que el
  barrido siguiente lo reintenta solo.
- Ítem de menú "Poner al día ahora", que solo levanta un evento y
  vuelve sin bloquear el menú de bandeja.

#### La cuarentena pasa a ser un prefijo (`b437276`)

`_CUARENTENA/` en la raíz de `cgs_grupo_alvarez`. La propiedad de
corrección más delicada —que los dos listados por prefijo no se
contaminen— está cubierta por prueba explícita en ambos sentidos.
Beneficio no previsto al decidirlo: renombrar carpetas exige
`storage.folders.rename` en el cubo ORIGEN y `storage.folders.create`
en el DESTINO, así que con un solo cubo basta un binding.

**Migración ejecutada y verificada cifra contra cifra:** 45 objetos y
251.858.773 bytes, idénticos en origen y destino, con `gcloud storage
rsync` (que valida sumas de verificación) y sin la bandera de borrado.
El cubo `cgs_grupo_alvarez_cuarentena` quedó **eliminado**, con ventana
de restauración de 7 días.

#### Hallazgos de producción, ninguno anticipado desde el código

- **Temporales de OneDrive tratados como documentación** (`dd3abd8`).
  El primer barrido real ancló `A-59 E-5068-BHH_ DOCUMENTACION.pdf
  ~RF3913c72c.TMP` y dos más. No se subió ninguno porque estaban solo
  en la nube, pero fue suerte: uno con contenido en disco sí se habría
  subido, disparando una llamada a Gemini por basura. Y el historial
  mostró que llevaba **quince horas** anclando los mismos cuatro, una y
  otra vez. El filtro se aplica en el único recorrido del que beben
  copia, reconciliación y barrido. Validado contra los **37.606 nombres
  reales del cubo**: descarta 2 (`.partial`) y conserva los 23 nombres
  cortos de MS-DOS (`SEGUR~12.doc`) y los once nombres legítimos
  probados a propósito, incluido `TMP GRUAS 2026.pdf`.
- **Carrera de renombrado** (`d83eabd`). Durante la renovación de la
  ITV del B-38, el barrido vio `...ITV 29-07-26.pdf` y al subirlo ya se
  llamaba `...ITV 29-01-27.pdf`. El sistema se recuperó solo —el fallo
  no entró en el índice y el barrido siguiente subió el nombre nuevo—,
  lo que valida ese diseño. Pero estaba mal categorizado: pasa a aviso
  sin traza, porque sobre un árbol vivo esto ocurrirá a diario y un
  ERROR con traceback entrena a ignorar los errores.
- **Subidas triplicadas** (`0d659f3`). `B-38 9161-GVJ ITV
  29-01-27.pdf` se subió tres veces en dos minutos: vigilante 08:09:31,
  barrido 08:10:54, vigilante otra vez 08:11:30 (OneDrive reescribió el
  archivo al terminar de sincronizar). Ver decisión abajo.

#### Verificación IAM — la duda de la cuenta de servicio, resuelta

`enterprisebot-vertex@` (plataforma) y `enterprisebot-h28-migration-ag@`
(agente) son cuentas **distintas**. Pero `enterprisebot-vertex@` ya
tiene `roles/storage.objectAdmin` sobre `cgs_grupo_alvarez` — la
sección 4bis, que decía que los permisos se dieron solo a la del
agente, era incompleta.

**Error del modelo, corregido con datos:** se afirmó que `objectAdmin`
no incluía `storage.folders.*` y que por tanto la Fase 2 fallaría. Era
falso. La fuente usada era la referencia de la biblioteca cliente de
Java, que describe un ayudante del SDK y no el rol vigente.
`gcloud iam roles describe` contra el proyecto real demuestra que
`objectAdmin` es un **superconjunto estricto** de `objectUser`: mismos
`storage.folders.*` más cuatro permisos de IAM por objeto y retención.
**Conclusión: no hay ningún binding que crear.** Lección: los permisos
exactos de un rol se comprueban con `gcloud iam roles describe` contra
el proyecto, nunca contra páginas de referencia de bibliotecas cliente.

#### Mediciones reales, que sustituyen a las estimaciones

| Medida | Valor |
|---|---|
| Barrido `DOC. MAQUINAS` (16.039 arch.) | 4,7 s |
| Barrido `DOC. PERSONAL` (21.511 arch.) | 6,5 s |
| Ciclo completo del barrido | **11,2 s** (en caliente) |
| Ciclo con el `.exe` del doble `os.stat` | ~34 s |
| Reconciliación, fase de hash | ~15-20 s por cada 500 archivos |
| `.exe` con vigilante | 29.280.863 bytes |
| `.exe` sin vigilante | 29.145.436 bytes |

Los 11,2 s son **en caliente**, con los metadatos del directorio en
caché tras horas barriendo. Un barrido en frío será más lento, y para
eso el bucle vigila su propia duración y avisa si un ciclo excede el
intervalo.

#### Análisis del inventario completo del cubo — material para Fase 2

37.606 objetos: 21.519 en `DOC. PERSONAL`, 16.031 en `DOC. MAQUINAS`,
56 en `_CUARENTENA`. Doce caracteres problemáticos distintos:

- **15 nombres con acentos DESCOMPUESTOS** (U+0301 combinante ×13,
  U+0303 ×2). `Notificación venta.pdf` no lleva una `ó`: lleva `o` más
  un acento combinante invisible. En pantalla son idénticos a los
  normales pero son **bytes distintos**, y cualquier comparación de
  cadenas los trata como archivos diferentes. El normalizador tendrá
  que aplicar NFC antes de nada o generará duplicados fantasma. Es el
  hallazgo con más potencial de daño silencioso.
- **2 nombres ya corruptos, irrecuperables automáticamente:**
  `Allianz_P<U+FFFD>liza_...` (el byte original se perdió) y
  `13072020__Fecha_ ■ Validez_ ]Firma ysellQ^ MartiR_ CoRstEora I
  E.pdf`, que parece salida de OCR mal hecha. Necesitan decisión
  humana.
- Erratas humanas: `TRANSPÒRTE` (acento grave), `N“ 3` (comilla
  tipográfica por `º`), `EPI´S` (acento suelto). Y 1.034 apariciones
  legítimas de `º`.
- **2 archivos `.partial`** de descargas interrumpidas, ambos con su
  PDF completo al lado. Quedan como huérfanos en el cubo tras el
  filtro: limpieza de Fase 2, 2 objetos sobre 37.606.

#### Incidencia de sesión — encabezado del anexo eliminado cuatro veces

Al insertar secciones nuevas con `str_replace` usando como ancla
`### Hoja de ruta para la siguiente sesión`, el modelo sustituyó el
encabezado en vez de insertar antes de él. Ocurrió **cuatro veces**,
la última en el propio bloque que documentaba la regla para evitarlo.
Detectado y reparado en el acto las cuatro, con `git diff --stat`
confirmando cero eliminaciones netas.

**Regla para futuras sesiones:** al insertar antes de una sección
existente, el texto de reemplazo debe incluir siempre el encabezado
ancla. Y para reescribir una sección final completa —como la hoja de
ruta en el PCS—, es más seguro reconstruir el archivo por líneas que
usar `str_replace` con el encabezado como ancla.

#### Incidencia de sesión — sintaxis de consola equivocada

Se entregaron comandos con sintaxis de bash (`\` y `&&` como
continuación) para la Google Cloud SDK Shell, que es `cmd.exe`, pese a
estar registrado desde S033. Y se sugirió lanzar `gcloud` desde
PowerShell, donde resuelve a `gcloud.ps1` y la directiva de ejecución
lo bloquea. **Regla:** `gcloud` va en `cmd.exe`, un comando por línea;
si hiciera falta desde PowerShell, se invoca `gcloud.cmd`. Nunca se
cambia la política de seguridad de la máquina por esto.

#### Corrección de registro sobre el borrado de cubos

Se afirmó tres veces que borrar el cubo era irreversible. **No lo es**:
con eliminación temporal activada, borrar un cubo lo deja en estado
soft-deleted y permite restaurarlo entero, o sus objetos, durante la
retención — 7 días en este proyecto.


---

### Hoja de ruta para la siguiente sesión

**Dirección fijada por Miguel Ángel al cierre de S036:** la próxima
sesión se centra en **la plataforma, no en el agente**. Concretamente,
un explorador de archivos en el panel para navegar Google Cloud
Storage.

Verbatim: *"ya tenemos que centrarnos en la plataforma, en el panel,
para ubicar el visor, o sea, el explorador de archivos, para explorar
precisamente la Google Cloud Storage. Mi idea, en principio, era
hacerlo, montar tabla de base de datos, montar tabla de base de datos
para que las exploraciones sean más rápidas y no contemos con
cadencias en la consola. Es decir, tener una sincronización entre lo
que es la base de datos y lo que realmente hay en consola, la
cuarentena, en el cubo de cuarentena, la carpeta de la cuarentena y el
resto del cubo, así como las fotos, albaranes y todo, tener acceso
real vía interfaz de explorador de archivos en el panel. Ya te digo,
trabajando con base de datos solamente hasta que necesites ver el
contenido de un archivo. En ese caso, ya se accede directamente al
archivo y se muestra."*

Lo que eso fija, y lo que deja abierto:

1. **Tabla de índice en base de datos** que refleje el contenido real
   de GCS: el prefijo `_CUARENTENA/`, el resto de `cgs_grupo_alvarez`,
   y también los cubos propios de la plataforma
   (`enterprisebot-alvarez-machine-documents`,
   `...-personnel-documents`, `...-delivery-notes`,
   `...-task-photos`). El explorador consulta **solo** la base de
   datos.
2. **Acceso al archivo únicamente al ver su contenido.** Navegar,
   buscar y listar no tocan GCS; abrir un documento sí.
3. **Sincronización entre la tabla y el cubo**, que es la parte con
   más miga y no está diseñada. Preguntas abiertas antes de escribir
   una línea: quién la dispara y con qué cadencia (¿otra entrada en
   `CELERY_BEAT_SCHEDULE`, como el consumidor de cuarentena?); si es
   completa o incremental; cómo se detecta lo borrado en el cubo; y
   qué pasa mientras la tabla va por detrás de la realidad.
4. **Punto de partida ya disponible:** el inventario completo de los
   37.606 objetos se listó en S036 y su análisis de caracteres está en
   este anexo. Sirve para dimensionar la tabla sin volver a recorrer
   el cubo.
5. **Decidir si esto es H28 o un hito nuevo.** Un explorador de GCS en
   el panel es infraestructura de plataforma y podría no pertenecer a
   "Migración y Reorganización de Documentación Histórica". Si procede
   abrir hito, hay que ejecutar `nfs-enterprisebot-pch` — y solo
   Miguel Ángel lo decide.

**Trabajo de Fase 2 que sigue pendiente, sin orden fijado:**

6. **Cerrar el vocabulario de tipos documentales** de los dos mundos,
   a partir del análisis de nombres de S035. Son vocabularios
   disjuntos: la carpeta raíz decide qué diccionario aplica.
7. **Escribir el normalizador de nombres** sobre las reglas ya
   validadas contra los 16.022 nombres de `DOC. MAQUINAS`. **Requisito
   nuevo de S036, previo a todo lo demás: normalización Unicode NFC**,
   por los 15 nombres con acentos descompuestos hallados en el
   inventario. Sin eso, el normalizador generará duplicados fantasma.
   Falta además pasar las reglas por los 21.507 nombres de
   `DOC. PERSONAL`.
8. **Diseñar la extracción de EPIs a base de datos**, colgando del
   operario: qué EPI, código, fecha de entrega y todo lo referente a
   la entrega.
9. **Diseñar la interfaz de limpieza**: árbol de directorios con
   iconos y nombres, y herramientas de renombrado. Probablemente
   converge con el punto 1 — conviene mirarlos juntos y no por
   separado.
10. **Tabla de manuales por modelo** (decisión 6 de S034) y
    **deduplicación de variantes de compresión**: en la carpeta de la
    A-29 esas variantes son el 79% del volumen.
11. **Consumidor de la cuarentena** (Fase 3): entrada en
    `CELERY_BEAT_SCHEDULE` dentro de la always-on `242133`, sin
    ampliar cuota. `enterprisebot-vertex@` ya tiene permisos
    suficientes sobre `cgs_grupo_alvarez` — verificado en S036, no hay
    IAM que tocar. **Debe ser idempotente por diseño** (decisión de
    S036): ignorar un archivo ya clasificado cuyo hash no ha cambiado.
12. Solo después: dry-run sobre el cubo, verificación de coherencia y
    ejecución real.

**Cabos sueltos menores, ninguno bloqueante:**

- Los tres `EPIS MILHEIRO FELICIO, JORGE.docx` siguen sin numerar como
  `00`/`01`/`02`, y falta decidir si el sufijo se aplica al subir o si
  la cola usa otra convención (para que las tres coexistan hacen falta
  tres nombres de blob distintos).
- `main.py` dice todavía `Vigilancia retomada sobre:` al arrancar,
  cuando ya no hay vigilancia — solo carpetas registradas para barrer.
  Cosmético.
- `pip-compile` sigue avisando de que `--strip-extras` será el
  comportamiento por defecto en pip-tools 8.0.0. Pendiente fijarlo
  explícito en el candado del agente.
- Dos `.partial` huérfanos en el cubo, y dos nombres corruptos
  (`Allianz_P<U+FFFD>liza_...` y el de salida de OCR) que necesitan
  decisión humana.

**Estado de la Fase 1:** completa y probada. Las dos migraciones
verificadas cifra contra cifra (S032-S033), las carpetas confirmadas
íntegras en S034, y en S035 verificadas a nivel de **contenido** con
MD5 real. El agente tiene candado de dependencias real, ciclo de
reconstrucción probado, y desde S036 está **verificado en producción
de extremo a extremo**: los cuatro defectos corregidos, el barrido de
puesta al día como única vía de entrada a la cuarentena cada 30
segundos, y el prefijo `_CUARENTENA/` confirmado por partida doble en
las reconciliaciones de arranque.

**Nota sobre la clasificación (S035, sigue vigente):** los dos ITV
nuevos que subió Rocío se repararon en la reconciliación de arranque
de las 06:37, cuando el `.exe` era todavía el antiguo, así que fueron
**al cubo sucio y no a cuarentena** — no pasaron por la cola de
revisión. No es grave, porque la Fase 2 repasa el espejo entero, pero
es un caso real de documentos que se saltaron el paso de clasificación
y conviene tenerlo presente al diseñar el clasificador.
