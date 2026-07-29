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

Ejecutable de forma autónoma, en este orden:

1. **Auditoría del estado real**, leyendo los archivos del clon: los
   cuatro puntos de la sección 5. Sin este paso no se escribe una línea
   de modelo.
2. **Cerrar con Miguel Ángel los puntos abiertos 1 a 3** de la sección
   6, que son los que condicionan el esquema. Los puntos 4 y 5 pueden
   esperar.
3. **Diseñar el modelo de datos del índice**: fila por objeto, con cubo,
   ruta completa, nombre, tamaño, hash, tipo documental, bandera de
   existencia local, estado de borrado lógico y usuario propietario de
   la papelera. Dimensionado sobre las cifras reales del inventario de
   S036 (37.606 objetos en `cgs_grupo_alvarez`, más los cubos de la
   plataforma, aún por contar).
4. **Diseñar el modelo de permisos**: concesión recursiva desde una
   carpeta, por usuario o por rol, con el administrador exento.
5. **Escribir modelo y migración** en el mismo commit (directriz 4.5).
6. **Sembrado inicial del índice** a partir del contenido real de los
   cubos, como comando de gestión idempotente y reejecutable.
7. Solo después: vistas del explorador, papelera y navegación.
