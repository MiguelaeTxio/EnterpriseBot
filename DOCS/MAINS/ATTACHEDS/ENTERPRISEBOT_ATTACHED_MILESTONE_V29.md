# H29 — Explorador de Archivos y Gobierno Documental del Panel sobre Google Cloud Storage

## 1. Objetivo del hito

Construir en el panel de EnterpriseBot un explorador de archivos sobre
Google Cloud Storage servido **exclusivamente desde una tabla de índice
en base de datos**, y con él un modelo completo de gobierno documental:
permisos por carpeta, borrado en dos niveles con papelera por usuario, y
una bandera que refleje si cada archivo sigue existiendo en las carpetas
locales de Microsoft 365.

Navegar, listar y buscar consultan **solo** la base de datos. El acceso
al objeto real de Google Cloud Storage ocurre únicamente cuando se abre
el contenido de un documento concreto.

Objetivo de fondo, en palabras de Miguel Ángel: blindar el mantenimiento
del directorio documental en la nube y acabar con la selva de nombres,
los borrados accidentales, los archivos mal nombrados con contenido que
no corresponde y los documentos ubicados donde no deben — canalizando
absolutamente toda la gestión por el panel.

## 2. Origen y relación con H28

Nace de la hoja de ruta de cierre de S036 (anexo H28, punto 1), donde
Miguel Ángel fijó la dirección: *"ya tenemos que centrarnos en la
plataforma, en el panel, para ubicar el visor, o sea, el explorador de
archivos, para explorar precisamente la Google Cloud Storage."*

Ese mismo punto dejaba abierto si el trabajo pertenecía a H28 o merecía
hito propio. **Decisión de Miguel Ángel en S037: hito nuevo.** Un
explorador de GCS en el panel es infraestructura de plataforma, no
migración de documentación histórica.

**Qué aporta H28 y no se rehace aquí:** la Fase 1 completa y verificada
en producción — el agente de Windows, el prefijo `_CUARENTENA/` en la
raíz de `cgs_grupo_alvarez`, el barrido de puesta al día como única vía
de entrada a la cuarentena, y el inventario real de 37.606 objetos
analizado carácter a carácter, que sirve para dimensionar la tabla de
índice sin volver a recorrer el cubo.

**Qué queda en H28 y no se absorbe aquí:** el normalizador de nombres,
el vocabulario de tipos documentales, la deduplicación, la extracción de
EPIs y el consumidor de la cuarentena. Son trabajo de Fase 2/3 de aquel
hito. La frontera puede volverse porosa —el punto 9 de la hoja de ruta
de S036 ya anticipaba que la interfaz de limpieza "probablemente
converge" con el explorador— y conviene revisarla cuando ambos hitos
avancen, no darla por inmutable.

## 3. Decisiones de diseño de Miguel Ángel (S037)

Registradas literalmente según se dictaron (directriz 4.8). No son
reinterpretación del modelo.

### 3.1. No hay causa externa que actúe sobre los cubos

Verbatim: *"Vamos a tener en cuenta que al quitarnos de la cuarentena y
de los métodos que hay para guardar las fotos y eso, que es de donde nos
vamos a nutrir para la base de datos, no hay ninguna causa externa que
actúe sobre los cubos. Quiero decir, todos los borrados y eso los vamos
a hacer siempre desde esta interfaz de explorador y podrán hacerlo única
y exclusivamente sobre las partes donde se tenga permiso."*

Es la premisa de la que cuelga todo lo demás: si nada externo modifica
el cubo, la base de datos puede ser la autoridad para navegar sin
perseguir continuamente a GCS.

### 3.2. El borrado en local NUNCA se refleja en la nube

Verbatim: *"No vamos a borrar archivos, esto debe quedar claro. Si
alguien borra en local, ese borrado no debe persistir en la nube. ¿Vale?
El borrado en la nube debe de ser única y exclusivamente a través del
panel. Nunca, nunca vamos a reflejar un borrado en local con una
desaparición de documentación en la nube."*

Y la justificación, en sus palabras: *"De esta forma, todo el control de
la documentación en Google Cloud Storage va a través del panel, evitando
nombres erróneos, selva de nombres, fallos y borrados accidentales de
documentación, fallos a la hora de archivos mal nombrados con contenido
diferente subidos, archivos que no deben estar en una carpeta y que
están. Vamos a blindar el mantenimiento del directorio en Google Cloud
Storage y todo, toda la gestión va a través del panel."*

### 3.3. La bandera de existencia local es el único reflejo de lo local

Verbatim: *"Vamos a marcar esos archivos que pasan a obsoletos,
tendremos que idear un sistema para que no se borren realmente. Para que
no se borren realmente. Es decir, hacer un marcado de que se han borrado
en local, pero mantenerlos en el panel. Es decir, tendremos que dotar a
la base de datos con una bandera que indique si el fichero sigue
existiendo o no en local. Ese es el único reflejo que vamos a tomar de
lo que se haga en local en las carpetas de Microsoft 365. Un flag que
nos indique si el archivo está o no está realmente de los que tengamos
subidos."*

### 3.4. El canal de esa bandera es la propia cuarentena

Pregunta planteada por el modelo: el agente de Windows detecta ya la
desaparición de una ruta (`catchup.py` compara por ruta, no por fecha),
pero no tiene ninguna vía hacia MySQL ni hacia el panel.

Verbatim: *"Yo creo que lo suyo sería, ya que sí tiene acceso a la
propia cuarentena, escribir las marcas ahí. Y luego consumirlo."*

**Valoración técnica que acompañó la decisión:** el agente ya posee
`roles/storage.objectAdmin` sobre `cgs_grupo_alvarez` y ninguna otra
credencial. Cualquier alternativa (endpoint autenticado del panel,
acceso directo a la base de datos) obligaría a abrir un canal nuevo con
su propia autenticación en una máquina Windows de escritorio. Usar el
cubo como buzón no añade superficie de ataque.

**Constricción derivada, a respetar sin excepción:** la decisión 3 de
S036 establece que *todo archivo que entre en cuarentena genera una
llamada a Gemini*. Las marcas no son documentos y no deben clasificarse.
Necesitan por tanto un subprefijo propio y una exclusión explícita en el
consumidor de la cuarentena. Su ubicación no puede contaminar tampoco
los listados por prefijo del reconciliador (`_list_remote_info`,
`reconciler.py`, lista con `prefix=f"{folder_name}/"`).

### 3.5. Alcance del índice: los cubos de la plataforma entran también

Pregunta planteada por el modelo: los cubos propios de la plataforma sí
tienen escritores externos hoy (el código de H23/H25/H10/H7 escribe
directamente contra GCS), de modo que sobre ellos la premisa 3.1 no se
cumple todavía.

Verbatim: *"Esos cubos deberían de entrar como solo lectura y como
escritura también para el administrador. Por tanto, hay que indexarlos
también."*

### 3.6. Papelera por usuario, vaciado por el administrador

Verbatim: *"Podríamos simular una papelera, sería lo mejor, y que esa
papelera la vacíe el administrador. Para que el supervisor pueda
recuperar lo que él haya borrado de esa papelera, las papeleras deben
ser por usuario y cada usuario solamente puede ver su papelera. Le
dejamos la gestión de poder recuperar, o sea, tanto escribir como leer,
como sacar de la papelera al usuario que la gestiona, y el vaciado lo
dejamos a cargo del administrador."*

Cierra el modelo de dos niveles ya anunciado: *"Y será el supervisor
encargado de cada una de las secciones el que pueda borrar archivos y
todo lo vamos a hacer a través de base de datos. Los borrados reales los
dejaremos para el administrador."*

### 3.7. Permisos en base de datos, no en IAM

Verbatim: *"Únicamente dentro de ese cubo podremos dar permisos a
carpetas, puesto que ya aquí lo que es la infraestructura de Google
Cloud no nos afecta, puesto que nosotros vamos a trabajar en base de
datos, daremos permisos donde queramos, cuando queramos y de la forma
que más nos plazca. Es decir, podremos dar permisos recursivos a partir
de una carpeta dentro del cubo, puesto que estamos dando permisos de
acceso a una parte de la base de datos. Entonces, como vamos a trabajar
de esa forma, cuando un usuario tenga permiso sobre las carpetas de
maquinaria, por ejemplo, podrá borrar y meter documentación de
maquinaria. Si no, no podrá hacerlo. Y el que tenga permiso para
personal podrá hacerlo de personal. Si no, no podrá hacerlo."*

Y sobre el alcance de cada rol: *"el administrador no, yo podré borrar y
añadir donde quiera, pero, por ejemplo, supervisor de documentación
única y exclusivamente podrá gestionar el cubo de documentación."*

### 3.8. El explorador NO sube documentos

Precisión de Miguel Ángel que cambia el diseño respecto a la primera
lectura del modelo. Verbatim: *"un supervisor de documentación, por
ejemplo, el que está dedicado a máquina, entre en lo que es el
explorador, lo único que va a poder es leer, ver cómo está, poder ver
documentos, etcétera. Él no va a poder meter documentos por esa vía.
¿Por dónde va a meter los documentos? En la gestión de documentación,
cuando tengamos el botón preparado para subir documentación (...)
Entonces, actualizamos por documentos. Voy a actualizar la ITV. Vale.
Sube el archivo de ITV. Se sube el archivo de ITV, se comprueba que es
un archivo de ITV, se clasifica. Ahí ya no entra el supervisor para
nada, él solamente gestiona la subida del archivo y el sistema debe
decir, este archivo es correcto, se ha guardado, tal. Este archivo no es
correcto, no se ha guardado por esto, por esto y por esto. Con lo cual,
mantendremos siempre una limpieza pulcra de todo el almacén de datos."*

También: *"todo irá a cuarentena y será Gemini quien clasifique"*, y
sobre la excepción a la premisa 3.2: *"La única carpeta que se va a
salvar de esto va a ser la de cuarentena, en la que si hay documentación
nueva que se mete por la vía normal, como lo de obsoletos, esa sí irá a
la cuarentena. El resto, nada."*

### 3.9. Las marcas de existencia local: un manifiesto por carpeta

Cierra el punto abierto 1. Verbatim: *"Un manifiesto por carpeta
vigilada en `_CUARENTENA/_MARCAS/`, sobrescrito en cada barrido."*

**Propiedades que se siguen de esa forma, y que el diseño debe
preservar:** al reutilizar siempre el mismo nombre de blob por carpeta,
el manifiesto es idempotente por construcción —cada barrido pisa al
anterior y el consumidor solo lee el último estado— y el número de
objetos generados no crece con el tiempo, a diferencia de una marca por
archivo desaparecido, que obligaría además a decidir cuándo se limpian.

**Exclusión obligatoria:** el prefijo `_CUARENTENA/_MARCAS/` no contiene
documentos y no debe generar ninguna llamada a Gemini. El consumidor de
la cuarentena tiene que excluirlo explícitamente (decisión 3 de S036).
La ubicación bajo `_CUARENTENA/` es segura respecto al reconciliador,
que lista con `prefix=f"{folder_name}/"` sobre carpetas migradas y por
tanto nunca alcanza este subprefijo.

### 3.10. El vaciado de papelera conserva la fila como registro histórico

Cierra el punto abierto 2. Verbatim: *"Registro histórico puede ser útil
para auditorías."*

El vaciado que ejecuta el administrador elimina el objeto en Google
Cloud Storage, pero **la fila de la tabla de índice sobrevive** como
constancia de que ese documento existió, quién lo borró y cuándo. El
esquema debe contemplar por tanto filas sin objeto asociado, y el
explorador debe distinguirlas de las vivas.

### 3.11. Lo marcado como borrado es invisible para los demás

Cierra el punto abierto 3. Verbatim: *"Creo que la visibilidad, en
cuanto se marque, debe ser invisible. Porque además lo va a marcar la
persona que es la que tiene el acceso al borrado virtual. Por tanto los
demás deben depender de su gestión."*

En cuanto un usuario con permiso borra un archivo, este desaparece del
explorador para todo el mundo. Solo lo ve quien lo borró, en su propia
papelera, y de su gestión depende que vuelva a estar disponible para el
resto. No hay estado intermedio de "visible pero marcado".

## 4. Consecuencia directa: las tres únicas vías de escritura

De 3.1, 3.2 y 3.8 se sigue que un objeto solo puede aparecer o
desaparecer en Google Cloud Storage por tres caminos, y ninguno más:

1. **Cuarentena.** El agente de Windows deposita en `_CUARENTENA/` lo
   que aparece nuevo en las carpetas vigiladas de Microsoft 365. Gemini
   clasifica y determina el destino a partir del contenido, nunca del
   nombre (decisión 3 de S036).
2. **Subida tipada desde gestión de documentación.** El usuario declara
   qué documento sube (ITV, permiso de circulación, etc.), el sistema
   valida que el archivo corresponde a ese tipo, y responde aceptando o
   rechazando con motivo explícito. El supervisor gestiona la subida; no
   interviene en la clasificación.
3. **El administrador**, con escritura directa sobre cualquier cubo
   indexado y el vaciado de las papeleras.

**El explorador nunca escribe documentos.** Su superficie es lectura,
borrado lógico a la papelera propia y recuperación desde ella.

## 5. Auditoría del código real (S037)

Auditoría ejecutada en S037 leyendo los archivos reales del clon
(método empírico, nunca "bola de cristal"). Lo que sigue son hallazgos
verificados, no documentación heredada:

1. **El servicio compartido de GCS ya existe y es único:**
   `spare_parts/gcs_service.py`, 470 líneas. Declara los cuatro cubos de
   la plataforma como constantes y los agrupa en `ALL_BUCKETS`; expone
   `get_storage_client()` (credenciales por `GCP_CREDENTIALS_PATH` y
   `GOOGLE_CLOUD_PROJECT`, las mismas de la directriz 4.1),
   `generate_signed_url()` con `SIGNED_URL_EXPIRATION` de 30 minutos,
   `sanitize_path_component()` y `ensure_bucket()`. Lo consumen
   `machine_documents`, `personal_documents`, `delivery_notes`,
   `spare_parts`, `work_order_processor`, `history`, `chat`,
   `document_ingestion` y tres módulos del panel. **H29 no construye
   cliente propio: extiende este.**
   Su propio comentario sobre `SIGNED_URL_EXPIRATION` ya expresa el
   principio que H29 generaliza: el control de acceso real es la
   autenticación del panel, y la URL firmada es solo el mecanismo de
   entrega puntual de un archivo ya autorizado.
2. **`cgs_grupo_alvarez` no figura en `ALL_BUCKETS`.** La plataforma hoy
   no conoce el cubo de H28. Incorporarlo forma parte del alcance de
   este hito.
3. **Existe ya media solución al problema de coherencia:**
   `document_ingestion/management/commands/purge_orphaned_gcs_blobs.py`
   detecta blobs huérfanos —objetos en GCS sin fila en base de datos—,
   que es una de las dos direcciones de la sincronización tabla-cubo.
   Debe leerse antes de diseñar el sembrado y la auditoría del índice.
4. **Los roles dan la base pero no la granularidad.** `CompanyUser`
   (`ivr_config/models.py`) define ocho roles reales: ADMIN, OPERATOR,
   WORKSHOP, WORKSHOPBOSS, SUPERVISOR, DRIVER, ASSISTANCE y
   DOCS_SUPERVISOR ("Supervisor de Documentación"), que es la figura de
   la decisión 3.7. Pero `role` es un `CharField` con `choices`, un enum
   plano: no puede expresar "manda en esta carpeta y no en aquella".
   **El permiso recursivo por carpeta exige un modelo de concesión
   aparte** colgado de `CompanyUser`.
5. **`CELERY_BEAT_SCHEDULE` confirmado** en `enterprise_core/settings.py`
   con cinco tareas periódicas activas, coincidiendo con lo registrado
   en el anexo de H28. Dos de ellas viven en las apps documentales:
   `send_document_expiry_alerts` en `document_management` y
   `self_heal_unassigned_personal_documents` en `document_ingestion`.
6. **Pendiente, requiere Cloud Shell y no puede hacerlo el modelo:**
   permisos efectivos de `enterprisebot-vertex@` sobre los cuatro cubos
   de la plataforma. Sobre `cgs_grupo_alvarez` se verificó en S036 que
   ya tiene `objectAdmin`; sobre los otros cuatro no se ha comprobado, y
   la comprobación va por `gcloud` (directriz 4.10).

### Hallazgo colateral reparado en la misma sesión (directriz 4.9)

El mapa de apps del `ENTERPRISEBOT_MASTER_DOCUMENT.md` (§1.1) estaba
desactualizado en tres puntos, corregidos en S037 sin dejarlos anotados
como deuda:

- Faltaban dos apps presentes en `INSTALLED_APPS`: `document_ingestion`
  y `document_management`.
- La fila de `panel` listaba `views_fleet.py`, que **no existe** en el
  árbol y al que ningún módulo hace referencia, y omitía tres módulos
  reales (`views_documentation.py`, `views_task_photos.py`,
  `views_gdrive_setup.py`).
- Las filas de `machine_documents` y `personal_documents` anotaban "en
  curso", una mención de estado de hito prohibida fuera del enrutador de
  anexos. Además `machine_documents` decía "Drive" cuando su
  persistencia real es GCS, verificado por sus propios imports.

## 6. Puntos abiertos

Ninguno se resuelve por interpretación del modelo (directriz 4.8). Los
puntos 1 a 3 originales quedaron cerrados en S037 y viven ahora como
decisiones 3.9, 3.10 y 3.11.

1. **Cadencia de la auditoría de coherencia** entre tabla y cubo, si se
   decide que exista como red de seguridad. Existe precedente directo en
   el proyecto: `document_ingestion/management/commands/purge_orphaned_gcs_blobs.py`
   ya detecta objetos en GCS sin fila en base de datos — hay que leerlo
   antes de diseñar nada nuevo.
2. **Frontera con H28.** Si la interfaz de limpieza de la Fase 2
   converge con este explorador (punto 9 de la hoja de ruta de S036),
   decidir en qué hito vive.

## 7. Hoja de ruta para la siguiente sesión

### COMPLETADAS EN S037

Sesión larga: 14 commits, 179 archivos tocados, 3.712 inserciones y
37.646 eliminaciones (la cifra de eliminaciones la domina la limpieza
de `STATIC_ROOT`, ver más abajo). Los siete pasos de la hoja de ruta
que dejó abierta la apertura del hito quedan **completos y verificados
en producción**, no solo escritos.

#### Cierre de los tres puntos abiertos (verbatim, directriz 4.8)

Decisiones 3.9, 3.10 y 3.11 registradas en la sección 3: manifiesto de
existencia local por carpeta en `_CUARENTENA/_MARCAS/` sobrescrito en
cada barrido; el vaciado de papelera conserva la fila como registro
histórico de auditoría; un archivo marcado como borrado es invisible
para todos salvo su dueño desde el instante del borrado.

#### Auditoría del código real (paso 1)

`spare_parts/gcs_service.py` es el servicio compartido único, con los
cuatro cubos de la plataforma en `ALL_BUCKETS` — `cgs_grupo_alvarez`
deliberadamente fuera, porque esa tupla la consume
`create_gcs_buckets`. `CompanyUser` tiene ocho roles reales, incluido
`DOCS_SUPERVISOR`, pero ninguna granularidad por carpeta: de ahí sale
`DocumentFolderGrant`. Reparación colateral del mapa de apps del
documento maestro (directriz 4.9): faltaban `document_ingestion` y
`document_management`, y `panel` listaba un `views_fleet.py`
inexistente.

#### Modelo de datos y migración (pasos 3-5)

`document_explorer/models.py`: `DocumentIndexEntry` (una fila por
objeto o carpeta, con `blob_name_hash`/`parent_path_hash` como
resúmenes SHA-256 de 64 caracteres para sortear el límite de índice de
InnoDB sobre una ruta de hasta 1024 bytes UTF-8) y
`DocumentFolderGrant` (permiso recursivo por prefijo). Seis decisiones
de rendimiento incorporadas: navegación por igualdad indexada nunca
por LIKE, carpetas como filas con contadores precalculados, CRC32C
como hash autoritativo (verificado en línea: MD5 no está garantizado
en objetos compuestos ni en subidas multipart de la API XML),
`GenericForeignKey` nunca resuelto al navegar, permisos resueltos una
vez por petición, y `path_digest()` normalizando a NFC por los 15
nombres con acentos descompuestos del inventario de S036.

Migración `0001_initial.py` **no escrita a ojo**: generada con Django
5.2.12 real sobre un proyecto mínimo en el entorno de verificación del
modelo, verificada con `makemigrations --check --dry-run` ("No changes
detected") antes de comitear.

#### Sembrado del índice y las dos vías de descubrimiento de carpetas (pasos 6-7)

`seed_document_index` (barrido completo, caro, para sembrar/reparar) y
`refresh_document_folder` (refresco por carpeta, el camino rutinario)
comparten toda su lógica de escritura vía `document_explorer/
index_writer.py`, para no duplicarla entre los dos comandos.

Verificado en producción con datos reales: el barrido completo de
`cgs_grupo_alvarez` (37.628 archivos) tardó **3m34s** contra Storage
Control; el refresco de una sola carpeta (`DOC. MAQUINAS`, 44 archivos
y 64 subcarpetas) tardó **11 segundos** — veinte veces más barato,
confirmando la recomendación oficial de Google. Metadatos completos al
100% en el listado (tamaño, crc32c, md5, generación) en los cinco
cubos: no hace falta leer objeto por objeto.

Hallazgo revisado sobre la marcha: **cero carpetas vacías** en todo el
cubo histórico. La primera lectura del aviso de "carpeta vacía
invisible" se emitía también en los cuatro cubos planos de la
plataforma, donde una carpeta vacía no puede existir por definición
(es solo el prefijo de un objeto). Corregido para informar de HNS/no-HNS
por separado.

Dependencia nueva `google-cloud-storage-control==1.12.0` (vía A) más
`include_folders_as_prefixes` de `google-cloud-storage` (vía B), ambas
verificadas por introspección real contra la versión exacta fijada en
el candado, nunca contra documentación genérica.

#### Vistas, plantillas y permisos (paso 7, cierre)

`document_explorer/permissions.py` resuelve el permiso **una vez**,
contra la carpeta que se abre, nunca fila a fila — filtrar por prefijo
habría exigido un `LIKE` sobre `blob_name`, justo lo que el índice
existe para evitar. Tres respuestas (`ALL`/`PARTIAL`/`NONE`), con
`PARTIAL` mostrando solo los hijos que llevan hacia una concesión más
profunda.

Vistas basadas en clases sobre `CompanyUserRequiredMixin` (convención
real del panel, `panel/mixins.py`). Listado paginado **por cursor**
(terna tipo/nombre/id de la última fila), nunca por `OFFSET`. GCS solo
se toca en dos momentos: `OpenDocumentView` (URL firmada al abrir un
documento) y `PurgeTrashView` (vaciado real, solo ADMIN). El explorador
**no sube documentos**, conforme a la decisión 3.8.

Contra HTMX **1.9.12** (la que carga `panel/base.html`), no la 2.0.9
estable actual — anotado, no abordado: el salto de versión mayor no es
trabajo de este hito.

Probado en producción por Miguel Ángel: navegación, scroll infinito
sobre `DOC. PERSONAL` (21.500+ archivos) y apertura de documento con
URL firmada, los tres correctos a la primera. Veredicto explícito:
"Ha quedado de lujo […] tal y como yo quería".

#### Hallazgos no buscados, los cuatro reparados en la misma sesión (directriz 4.9)

1. **`requirements.txt` le faltaban 11 paquetes** (`pymupdf4llm` y su
   cadena completa), desde S025 — nueve días. Un `pip-sync` en esa
   ventana habría desinstalado la conversión PDF→Markdown de H23 en
   producción. Detectado al regenerar el candado para añadir
   `google-cloud-storage-control`. Documentado también en el anexo de
   H23 por ser desvío (directriz 4.9), sin mover el marcador de hito.
2. **`STATIC_ROOT` (`static/`) estaba versionado**: 147 archivos,
   ninguno huérfano (127 del paquete `django.contrib.admin`, 20 de las
   fuentes de `panel/` y `vox_bridge/`), pero 4 desincronizados de su
   fuente y el directorio se ensuciaba en cada `collectstatic`, que es
   lo que causó el primer fallo real de despliegue de la sesión. Sacado
   del control de versiones (`/static/` y `celerybeat-schedule` al
   `.gitignore`); las fuentes reales siguen versionadas donde deben.
3. **Deuda técnica con fecha, documentada por primera vez**: fin de
   soporte de Python 3.10 el 4 de octubre de 2026 (aviso real de
   `google-api-core` visto en producción), con la respuesta ya obtenida
   del soporte de PythonAnywhere. Sección 4.3.1 nueva en el documento
   maestro.
4. **La sidebar perdía entradas de forma recurrente**, reportado por
   Miguel Ángel como algo "habitual". Causa raíz: `_nav_items.html`
   condiciona casi todo a `company_user` sin que ningún procesador de
   contexto lo proveyera — 23 vistas de `panel/` lo inyectaban a mano y
   cualquiera que se olvidara perdía medio menú en silencio. Reparado
   con `panel/context_processors.company_context`, registrado en
   `settings.py`: corrige de golpe todas las vistas pasadas y futuras.

#### Incidencia de sesión — dos despliegues fallidos, verificados y corregidos

El modelo dejó de comprobar despliegues tras confirmar el primero con
la migración inicial, tratando pushes de dependencias como "triviales"
— no lo eran. Dos despliegues seguidos fallaron
(`bded7e9`, `e04e693`) por `git pull` en el servidor negándose a
sobrescribir un `requirements.txt` modificado localmente, porque una
sesión anterior había ejecutado `pip-compile` directamente en la
consola del servidor sin descartar después la copia del árbol de
trabajo. Diagnosticado con la API de GitHub Actions (permisos
`actions:write`/`contents:write` ya concedidos), reparado con
`git checkout -- requirements.txt` (contenido idéntico al de
`origin/main`, descarte inocuo) y **verificado paso a paso**, no solo
por el icono verde, antes de continuar. Corregido a partir de ahí:
verificación de los siete pasos del Action tras cada push, sin
excepción por tipo de commit.

**Limitación de red anotada, no resuelta:** la descarga de logs de
Actions redirige a `productionresultssa*.blob.core.windows.net`, y
solo `...sa17...` está en la lista de red permitida del modelo. El
diagnóstico se hizo por otras vías (estado de jobs/steps por API,
anotaciones, y el log pegado directamente por Miguel Ángel). Si se
amplía la lista de red con el comodín, el modelo podría leer los logs
de Actions sin depender de que se los peguen.

**Estado de la Fase 1 de H29 (los siete pasos de la hoja de ruta):**
completa, con modelo, migración, permisos, sembrado, las dos vías de
descubrimiento de carpetas y la interfaz del panel, todo verificado en
producción con datos reales, no solo desplegado.

#### Addenda tras el cierre formal de S037 — bug real corregido en producción

Dos commits sueltos, posteriores al commit de cierre (`acc2d62`), a raíz
de una comprobación de Miguel Ángel sobre el propio explorador ya en
uso: `DOC. MAQUINAS` mostraba el tamaño en blanco mientras
`DOC. PERSONAL` y `_CUARENTENA` lo mostraban con normalidad.

**Causa:** en la verificación de la sesión se había ejecutado
`refresh_document_folder --path "DOC. MAQUINAS"` para medir el tiempo
de la vía B. Ese comando construye la fila de la carpeta refrescada sin
tamaño (valor por defecto `0`), y `persist_rows` actualizaba entonces
**todos** los campos de la fila existente, pisando el total real de
1,7 TB calculado por el barrido completo. Lo mismo le pasó a sus 64
subcarpetas directas. No fue un fallo de visualización: el dato en base
de datos estaba realmente a cero.

**Corrección** (`42429b6`): `index_writer.persist_rows()` acepta ahora
`skip_fields`, que excluye columnas de la actualización por lotes —
`bulk_update` solo escribe los campos indicados, así que uno omitido
conserva el valor ya guardado. `refresh_document_folder` pasa
`skip_fields=("total_size_bytes",)`, porque un refresco de un solo
nivel nunca puede conocer el total recursivo real.
`seed_document_index` no cambia: un barrido completo sí es autoritativo
sobre el tamaño y debe seguir escribiéndolo.

**Reparación del dato:** reejecutado `seed_document_index --bucket
cgs_grupo_alvarez` en producción (3m22s, 41.109 filas), verificado el
despliegue de ambos commits paso a paso vía API de GitHub Actions
(`success`, sin fallos).

**Implicación anotada para el diseño futuro, no resuelta:** cualquier
refresco por carpeta sobre una carpeta ya sembrada deja su tamaño «sin
dato» hasta el siguiente barrido completo — la contrapartida correcta
de no escribir un cero falso, pero significa que el tamaño puede
quedar temporalmente desactualizado tras usos puntuales de la vía B. Si
el futuro consumidor de la cuarentena dispara refrescos con frecuencia,
decidir entonces si calcular el tamaño real (archivos directos + total
ya guardado de cada subcarpeta) en vez de dejarlo en blanco.

### Hoja de ruta para la siguiente sesión

Ninguno de estos puntos es bloqueante para dar H29 por operativo; son
mejoras y trabajo que se dejó fuera de forma explícita.

1. **Consumidor de la cuarentena** (Fase 3 de H28, no de H29): sigue
   sin construirse. Los 78 archivos reales de `_CUARENTENA` ya son
   visibles y navegables en el explorador, pero nada los clasifica ni
   los mueve todavía — decisión 3 de S036, entrada en
   `CELERY_BEAT_SCHEDULE`.
2. **Subida tipada desde gestión de documentación** (decisión 3.8):
   el explorador delibradamente no sube nada; la vía de alta por tipo
   documental declarado no se ha diseñado todavía.
3. **Auditoría de coherencia tabla↔cubo** (punto abierto 1 de la
   sección 6): sigue sin cadencia ni mecanismo. Precedente real ya en
   el proyecto,
   `document_ingestion/management/commands/purge_orphaned_gcs_blobs.py`,
   pendiente de leer antes de diseñar nada nuevo.
4. **Confirmación de `storage.folders.list`** en la cuenta de la
   plataforma (`enterprisebot-vertex@`) vía `gcloud`, para cuando haga
   falta escribir en vez de solo leer con Storage Control (renombrado y
   borrado atómico de carpeta, que necesitará la Fase 2 de H28).
5. **Migración de Python 3.10 → 3.12/3.13** antes del 4 de octubre de
   2026 (sección 4.3.1 del documento maestro, procedimiento completo en
   `com-environment-management` sección 4.2). Incluye verificar si las
   *always-on* referencian el entorno virtual por ruta.
6. **Salto de HTMX 1.9.12 a la serie 2.x**, anotado pero no evaluado:
   tiene cambios incompatibles y afecta a todo `panel/base.html`, no
   solo a esta app.
7. **Frontera con H28** (punto abierto 2 de la sección 6, sigue sin
   cerrar): si la interfaz de limpieza de la Fase 2 converge con este
   explorador, decidir en qué hito vive.

**Cabo suelto menor, no bloqueante:** las cuatro copias de estáticos
que estaban desincronizadas de su fuente antes de S037
(`panel/css/panel.css`, `panel/js/admin_history.js`,
`panel/js/form_entry_assets.js`, `panel/js/form_entry_modal.js`) ya no
pueden volver a desincronizarse tras el punto 2 de "hallazgos no
buscados", pero no se ha verificado si las fuentes actuales son las
versiones correctas o si el desfase escondía una regresión real.
