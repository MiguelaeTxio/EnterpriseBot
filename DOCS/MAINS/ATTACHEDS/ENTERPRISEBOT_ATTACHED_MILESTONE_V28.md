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

## 4. Hoja de Ruta para la Siguiente Sesión de H28

**Antes de escribir una sola línea de código**, cerrar con Miguel
Ángel (directriz 4.8, no decidir nada de esto unilateralmente):

1. **Alcance de la primera copia real.** ¿Se abre el agente ya
   apuntando a elegir cualquier carpeta bajo `DOCUMENTOS GRUPO
   ALVAREZ`, o se acota la primera prueba real a `DOC. MAQUINAS` y
   `DOC. PERSONAL` únicamente, dejando el resto (`DOC. GRUAS ALVAREZ`,
   `DOC. GRUAS LARIOS`, etc.) para una copia posterior una vez
   validado el agente con las dos carpetas ya conocidas?
2. **Nombre y estructura del cubo sucio en GCS.** Proponer un nombre
   de cubo nuevo (ej. `enterprisebot-{company}-migracion-sucia` o
   similar) y confirmar si dentro del cubo se replica la ruta local
   completa tal cual (`DOCUMENTOS GRUPO ALVAREZ/DOC. MAQUINAS/...`) o
   se usa una raíz distinta.
3. **Carpeta/cubo de cuarentena.** Decidir la ubicación exacta (prefijo
   dentro del mismo cubo sucio, ej. `_CUARENTENA/`, o un cubo GCS
   aparte) — pendiente desde el punto 3 de la sección 3 de este anexo.
4. **Cuenta de servicio del agente.** Crear en Google Cloud Console una
   cuenta de servicio nueva, con permiso de escritura ÚNICAMENTE sobre
   el cubo sucio (y el de cuarentena) — nunca reutilizar una cuenta de
   servicio con permisos más amplios (principio de mínimo privilegio).
   Miguel Ángel gestiona la creación y la custodia de la clave
   descargada, igual que ya hace con `.env` (ver el incidente de
   seguridad de `GOOGLE_MAPS_API_KEY`, mismo cuidado aplicado aquí
   desde el principio).
5. **Tecnología del agente.** Con las cuatro decisiones ya tomadas
   (subida directa, vigilancia continua, cuarentena para lo nuevo),
   el candidato más directo es un script Python con la librería
   `watchdog` (vigilancia de carpeta en tiempo real) +
   `google-cloud-storage` (subida), empaquetado como ejecutable de
   Windows (PyInstaller) o corriendo como tarea programada — a
   confirmar con Miguel Ángel el formato de entrega final (¿ejecutable
   con icono en bandeja del sistema, tarea silenciosa en segundo
   plano, o consola visible?).
6. Una vez cerrados los puntos 1-5, construir: (a) el diálogo de
   selección de carpeta(s), (b) la copia inicial en bruto al cubo
   sucio con barra de progreso/log visible, (c) el modo vigilancia
   posterior con cuarentena para archivos nuevos.

Sin código todavía — este anexo se abre en S030 solo con el diseño
cerrado, la implementación empieza en la sesión siguiente dedicada a
H28.
