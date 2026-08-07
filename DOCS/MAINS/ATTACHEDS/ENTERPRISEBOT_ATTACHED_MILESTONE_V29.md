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

### 3.12. Consolidación de cubos y renombrado de pestañas (S038 — pestañas completadas, resto pendiente)

Registrada literalmente según se dictó (directriz 4.8). **El
renombrado de pestañas y la retirada de los dos cubos borrados de la
lista SÍ se implementaron en esta sesión** (commit `5d51d8c`,
desplegado y verificado en Actions). **Lo que sigue pendiente para
cuando se aborde de nuevo:** retirar por completo las apps
`machine_documents`/`personal_documents` (modelos, vistas de subida,
`purge_orphaned_gcs_blobs.py`) y rediseñar la vía de subida tipada
(decisión 3.8) para escribir directamente en `cgs_grupo_alvarez`.

**Renombrado de pestañas visibles a castellano**, verbatim: *"lo que es
los nombres visibles de las 'pestañas' o mejor dicho 'cubos' habrá que
cambiarlos cuando toquemos la parte del código donde residen para que
tengan los nombres en castellano: `Fotos Partes`, `Fotos Albaranes` y
`Directorio Principal`."*

**Eliminación de los cubos de documentación de máquina y de personal**,
verbatim: *"Lo que son los cubos, tanto el de documentación como el de
maquinaria, esos van a quedar eliminados. El de CGS Grupo Álvarez va a
pasar a ser el directorio principal."*

**Motivo explícito**, verbatim: *"¿Por qué es eliminar los otros dos
grupos? Bueno, pues muy fácil, porque van a estar integrados en lo que es
el cubo del directorio principal. Entonces va a ser redundante tenerlos
ahí."*

**Consecuencia sobre la vía de subida tipada** (decisión 3.8, punto
abierto 2 de la hoja de ruta), verbatim: *"Como vamos a adaptar lo que se
hizo en el tema de subida de documentación, vamos a cambiarlo, lo vamos a
poner de otra forma, pero van a subir directamente, no a esos cubos, sino
ya al cubo principal, a su carpeta correspondiente. Y vamos a tener la
reordenación de todo el directorio, no tiene sentido conservar esos dos
cubos."*

**Lectura de lo dicho, sin resolver nada por interpretación propia
(pendiente de confirmar con Miguel Ángel antes de tocar código):**
- `cgs_grupo_alvarez` (hoy "Directorio Principal" implícito, sin ese
  nombre visible todavía) absorbe el contenido de los cubos hoy
  gestionados por las apps `machine_documents` (H23) y `personal_documents`
  (H25).
- Los otros dos cubos de la plataforma no se mencionan como eliminados:
  los nombres en castellano dados (`Fotos Partes`, `Fotos Albaranes`)
  corresponden previsiblemente a `task_photos`/`delivery_notes` — **a
  confirmar con Miguel Ángel cuando se aborde**, nunca asumido.
- Afecta como mínimo a: `document_explorer` (pestañas de H29),
  `machine_documents`/`personal_documents` (H23/H25, cuyo cubo propio
  desaparece), y la vía de subida tipada de H26 (decisión 3.8 de este
  mismo anexo, que aún no se ha diseñado).
- **No se decide aquí ni la fecha ni el hito exacto** en que se aborda —
  Miguel Ángel no lo ha fijado todavía.

**Respuesta a la pregunta de arrastre (S043)**, tras tres sesiones
consecutivas (S040, S041, S042) sin ejecución real: Miguel Ángel
confirma que la consolidación se refiere a la subida de documentos y
el CRUD ya construidos (H23/H25/H26), y fija la condición de
dependencia explícita, verbatim: *"cuando tengamos lista la
clasificación automática de documentos, ligaremos ambas partes y nos
dedicaremos a la extracción de datos de los documentos y adición a la
BBDD."* No ha dejado de ser prioritario — queda **bloqueado por**
cerrar antes la clasificación automática (S040-S042, consumidor de
cuarentena), no por falta de decisión. Deja de contar como arrastre
sin motivo a partir de esta sesión: es una dependencia de orden de
trabajo declarada, no un ítem abandonado.

### 3.13. Ejecución del borrado de los dos cubos (S038)

**Ejecutado por Miguel Ángel en su consola local (PowerShell,
confirmado con salida real), no por el modelo** — el modelo no tiene
acceso de red a GCP desde este entorno.

Premisa confirmada por Miguel Ángel, verbatim, tras una comprobación
por nombre de archivo que dio 0 coincidencias y generó confusión
innecesaria (S038): *"Los objetos que se subieron a esos cubos están
dentro de las carpetas de personal y de docmáquinas en el directorio
principal. Así que se pueden borrar con toda la tranquilidad del
mundo."* Instrucción de ejecución inmediata, verbatim: *"Los borras
ahora mismo, no compruebes más nada. [...] Si se pierde la información
es por mi culpa."*

Comando ejecutado: `gcloud storage rm --recursive gs://BUCKET_NAME`
sobre los dos cubos. Resultado real, confirmado con la salida de la
consola:
- `enterprisebot-alvarez-machine-documents`: 29/29 objetos borrados,
  cubo borrado (`Completed 1/1`).
- `enterprisebot-alvarez-personnel-documents`: 39/39 objetos borrados,
  cubo borrado (`Completed 1/1`).

**Riesgo operativo señalado por el modelo tras la ejecución — cerrado
por Miguel Ángel:** el código de `machine_documents`/`personal_documents`
(subida de documentos, `document_ingestion/management/commands/
purge_orphaned_gcs_blobs.py`, `create_gcs_buckets`) sigue apuntando a
estos dos nombres de cubo, que ya no existen. Miguel Ángel confirma,
verbatim: *"nadie va a subir documentación a esos cubos, porque la
persona que lo está usando está avisada de que no funciona [...] y que
hemos cambiado el sistema, así que no hay problema."* Sin guardia de
código añadida — el aviso directo a la usuaria (Yolanda, DOCS_SUPERVISOR)
cubre el riesgo hasta que se aborde el código de consolidación de 3.12.

### 3.14. Buzón de documentación, "la vuelta" y carpeta de no conformes (S040 — diseño registrado; ASIGNADO A H29 en S041, pendiente de construir)

Registrada literalmente según se dictó (directriz 4.8). **Ninguna
parte de esto se ha implementado todavía.** Miguel Ángel señaló él
mismo que podría ser un hito propio, sin decidirlo — queda como
punto abierto de enrutamiento, no como trabajo en curso de H29.

**Punto de partida — problema real a resolver:** facilitar la tarea
a las personas que gestionan documentación cuando la reciben por
correo electrónico como adjunto.

**Buzón de documentación (carpeta local nueva):** verbatim: *"vamos a
poner una regla para que los documentos adjuntos vayan a parar a una
carpeta. Esta carpeta, que vamos a denominarla buzón de documentación,
está en local (...) vamos a tener que modificar el agente que tenemos
local, el agente de migración, el H28, lo vamos a modificar para que
vigile esta carpeta del buzón de entrada, además de vigilar las
carpetas que ya está vigilando. De tal forma que cuando entre ahí
algún archivo, bien porque venga a través de un correo electrónico
como adjunto, o bien porque la persona que está dedicada a gestionar
algún tipo de documentación lo suelte ahí, el agente, como hacemos
barridos cada 30 segundos, lo va a coger y los va a enviar a
cuarentena. Cuarentena los va a recoger cada 5 minutos, la tarea
Always on Task, los va a clasificar y los va a enviar cada uno a su
carpeta."*

**El problema de la selva, y "la vuelta" como solución:** verbatim:
*"Si no hacemos nada más, la carpeta buzón de documentación irá
acumulando archivos uno detrás de otro, hasta que será una auténtica
selva. ¿Cómo solucionamos esto? Muy sencillo, con una vuelta. Cuando
Gemini haya clasificado correctamente dicho documento, lo habrá
renombrado con el formato que tenemos para renombrar, el agente debe
recoger esa información y hacer lo mismo, renombrar el archivo y
colocarlo en la carpeta correspondiente, y eliminarlo, evidentemente,
de la carpeta del buzón de documentación."*

**Carpeta de "no conformes" para lo rechazado por Gemini:** verbatim:
*"¿Qué ocurre con los archivos que no se puedan clasificar o que sean
erróneos y queden rechazados por Gemini? Pues muy simple, los vamos a
echar a una carpeta de rechazados o no conformes. Mejor, no conformes.
En esa carpeta de no conformes se guardarán en la Google Cloud Storage
dentro del directorio principal y haremos lo mismo en la vuelta, en el
local, lo guardaremos en una carpeta de no conformes. Y además haremos
una anotación en el servidor, en el panel, para que se sepa por qué se
ha puesto este archivo en no conforme. Bien, porque ya hubiese un
archivo exactamente igual, bien, porque no cumpla o porque no sea
ningún tipo de documento de los que se necesita guardar, etcétera."*

**Valoración de Miguel Ángel sobre el alcance:** verbatim: *"esto en
sí mismo puede que sea ya un hito por sí solo."* **Resuelto en el
cierre de S041: asignado a H29** (la parte del agente local H28 --
buzón de documentación y "la vuelta" -- sigue pendiente de revisar
desde ese lado si hace falta tocar el agente; la parte de "no
conformes" es puramente panel/BD, H29). Pendiente de construir,
todavía sin empezar.

**No resueltos por interpretación propia, a confirmar cuando se
aborde:** el formato exacto de renombrado que debe replicar el
agente en la vuelta, el mecanismo de correlación entre el archivo
original en el buzón y el resultado ya clasificado en cuarentena/
directorio principal (¿mismo nombre de blob de cuarentena?, ¿algún
identificador?), y el detalle de qué escribe exactamente la
anotación en el panel para un archivo no conforme.

**Recordatorio añadido (S040, misma sesión que 3.19/3.24/3.25 más
abajo) -- el agente debe reportar de qué carpeta subió cada
archivo.** Verbatim: *"que no se nos olvide modificar el agente que
funciona en local para que nos diga desde qué carpeta ha subido
determinado documento. Porque si ha subido (...) desde el buzón de
documentación, pues ha subido desde el buzón de documentación. Pero
si se ha subido porque la persona que está encargada de la
documentación ha soltado un archivo en la carpeta correspondiente a
un trabajador o a una máquina, ya desde ahí sabemos cuál es el código
de la máquina. Y lo único que tendríamos que hacer en un momento dado
es una comprobación rutinaria, simple y sencilla (...) que sepa
Gemini que tiene que comprobar el dato con el nombre de la carpeta."*

Mismo principio que ya se aplicó en la sesión al motor de
clasificación real (ver más abajo, corrección sobre `build_new_name`):
cuando ya se sabe la carpeta/máquina real por otra vía distinta del
propio documento, esa vía prevalece sobre lo que Gemini lea dentro
del contenido -- Gemini deja de tener que adivinar lo que el sistema
ya sabe con certeza. Asignado a H29 en el cierre de S041 (ver
cabecera de 3.14), sin construir nada todavía.

**Precisión S041, misma carpeta de "no conformes", origen distinto.**
Registrada a
raíz de una pregunta real de Miguel Ángel sobre `consume_quarantine_
task`: hoy no existe ninguna marca de "esto ya se intentó antes" --
un archivo que nunca resuelve (ni máquina, ni identidad, ni dossier
cierto) vuelve a entrar en el lote de los 40 más antiguos pasada tras
pasada, para siempre, gastando una llamada real a Gemini cada vez sin
ningún límite. La carpeta de "no conformes" es la salida a ese bucle,
verbatim: *"cuando hacemos una pasada [...] no marcamos de alguna
manera para saber si se han intentado clasificar anteriormente [...]
Ya se apuntó la idea de una carpeta de no conformes, esa carpeta es
donde haremos estudio de documentos para añadir más tipos y se tiene
que mover su contenido cuando cuarentena esté vacía, es decir, un
documento sin tipificar se echa a no conformes, cuando cuarentena
esté vacía, no conformes mueve su contenido a cuarentena de forma
manual, mejor de forma manual, sería una tontería mover los archivos
si no hemos creado un tipo nuevo, volverían a ver en no conformes en
bucle."*

Mecanismo descrito, a confirmar junto con el resto de 3.14 antes de
construir nada: (1) un archivo que no resuelve tras N pasadas (N sin
decidir) se reubica virtualmente a "no conformes" -- deja de
coincidir con `parent_path__startswith=QUARANTINE_PREFIX`, así que
`consume_quarantine_task` deja de volver a llamarlo, sin gastar más
Gemini; (2) "no conformes" es el espacio de estudio de Miguel Ángel
para decidir si hace falta un tipo nuevo en el catálogo cerrado; (3)
la vuelta de "no conformes" a cuarentena es un botón **"Reencolar"**
en el panel sobre la propia carpeta de no conformes, disparado a mano
por Miguel Ángel cuando él decida -- **sin ninguna relación con el
estado de cuarentena**, ni falta que esté vacía ni que tenga nada
pendiente. Al pulsarlo, mueve TODO el contenido de no conformes de
vuelta a cuarentena de golpe; lo que ya tenga un tipo nuevo creado se
clasifica y reubica bien en la siguiente pasada, lo que siga sin
tipo vuelve a caer en no conformes, sin más coste que haberlo
intentado una vez. **Corrección explícita de Miguel Ángel sobre su
propia primera aproximación** (verbatim): *"lo he pensado bien (...)
No tengo que esperar a que esté vacía la cuarentena. Eso ha sido un
error por mi parte (...) el hecho de que sea manual y no sea
automático es para evitar llamadas inútiles (...) si no tenemos
tipos nuevos [...] van a volver otra vez, entonces vamos a crear una
serie de llamadas a la API que nunca van a lograr su objetivo y van
a ser un gasto de dinero tontamente. Entonces por eso tiene que ser
manual, independientemente de lo que quede o no quede en
cuarentena."* El único motivo de que sea manual es no gastar Gemini
en documentos que van a volver a fallar si no se ha creado antes el
tipo que les faltaba -- nada que ver con el estado de la cola.

**Aclaración S043 -- dos carpetas separadas, ida y vuelta, todavía sin
construir.** Miguel Ángel corrigió una lectura del modelo que asumía
una única carpeta de buzón sirviendo ambas direcciones -- verbatim:
*"Tenemos una vuelta, cierto, pero esto no es para la vuelta, esto es
camino de ida aún, es decir, tendremos dos carpetas, una de acceso y
otra de entrada. La de acceso es esta que estamos hablando, es la
entrada de documentación. La de entrada es dónde el agente encontrará
los archivos clasificados para colocar en Microsoft 365."*

Nomenclatura y comportamiento exactos, verbatim:
- **`AccesoBuzonDocumentacion`** (camino de ida): *"Todo archivo
  encontrado aquí se sube a cuarentena para clasificación."*
- **`BandejaEntradaDocumentacion`** (camino de vuelta -- "la vuelta"
  de más arriba en esta misma sección): *"Todo archivo encontrado aquí
  viene con su carta de clasificación listo para ser [movido] a su
  carpeta de destino en Microsoft 365."*

Además, Miguel Ángel fue explícito en que `AccesoBuzonDocumentacion`
**no debe aparecer como carpeta en el panel** -- solo los archivos que
pasen por ella deben acabar en cuarentena, la carpeta de acceso en sí
misma no es una entidad que el explorador deba mostrar. Contrasta con
el comportamiento hoy vigente para cualquier otra carpeta vigilada por
el agente, donde el nombre de la carpeta local se convierte siempre en
un segmento real de `blob_name`
(`_CUARENTENA/{nombre_carpeta}/{ruta_relativa}`) y por tanto en una
fila `FOLDER` visible en el panel -- `AccesoBuzonDocumentacion`
necesita, por tanto, una ruta de subida distinta a la que usa hoy
cualquier otra carpeta vigilada.

**Preguntas abiertas, sin resolver por interpretación propia (S043),
a confirmar antes de construir nada:**
1. Para `AccesoBuzonDocumentacion`: si sus archivos suben directos a
   la raíz de `_CUARENTENA/` (sin segmento de carpeta), ¿es eso lo que
   se busca? Y si dos archivos de distinto origen llegan con el mismo
   nombre, ¿colisión resuelta con ordinal automático, igual que ya
   hace el resto del sistema?
2. Para `BandejaEntradaDocumentacion`: ¿cómo descubre el agente qué
   archivos están "listos"? ¿Sondea un prefijo nuevo de GCS que el
   servidor puebla tras clasificar, o hay algún otro canal (mismo
   patrón de aviso instantáneo que `RegisterUploadedObjectView`, pero
   en sentido servidor→agente)?
3. ¿Qué información exacta viaja de vuelta -- el propio archivo
   clasificado (bytes reales) más su nombre/ruta de destino final en
   Microsoft 365, o solo un aviso con esos dos datos y el agente
   recupera el contenido real de GCS por su cuenta?
4. ¿Qué marca a un archivo como "listo para la vuelta" -- el momento
   en que Gemini lo clasifica con éxito, o una confirmación humana
   posterior en el panel antes de soltarlo hacia local?

**Respuestas de Miguel Ángel (S043), cierran los cuatro puntos:**

1. **`AccesoBuzonDocumentacion` no es mecanismo nuevo.** Verbatim:
   *"No es nada nuevo, la carpeta acabo de ponerla en observación por
   el agente, cualquier archivo que se suelte aquí sigue el mismo
   camino que cualquier otro que se suelte en las carpetas ya
   vigiladas."* Se añade por el mecanismo ya existente (tray →
   "Seleccionar carpeta y copiar"), sin ruta de subida especial, sin
   excepción de "no debe aparecer como carpeta en el panel" -- esa
   lectura del modelo era incorrecta; queda descartada. La carpeta se
   comporta exactamente igual que cualquier otra carpeta vigilada,
   incluida la aparición de su propio segmento en `blob_name` y su
   fila `FOLDER` visible en el panel.
2. **`BandejaEntradaDocumentacion` -- diseño registrado, construcción
   deliberadamente aplazada.** Verbatim: *"El agente vigila la
   carpeta igual que vigila las de entrada a documentación. Esta es la
   de salida de documentación. Esto no se implementa aún hasta que
   terminemos el camino de subida y sea totalmente funcional. Cuando
   se detecta un archivo tendrá una galletita con su carta de
   recomendación (ruta final del archivo, puede que sea en el mismo
   nombre o un fichero de txt anexo). El agente lee la ruta final y lo
   mueve."* Mecanismo real cuando se aborde: el agente vigila esta
   carpeta con el mismo watchdog que ya usa para las de entrada: un
   archivo que aparece ahí lleva consigo su destino final (codificado
   en el propio nombre, o en un `.txt` anexo -- sin decidir cuál de
   los dos todavía), el agente lo lee y mueve el archivo a esa ruta
   dentro de Microsoft 365. **Bloqueante explícito para empezar:**
   dar antes por completo verificado y estable el camino de ida
   (`AccesoBuzonDocumentacion` + clasificación real en cuarentena) --
   nunca antes.
3. Respondida en el punto 2 (misma decisión, un único mecanismo).
4. Respondida en el punto 2 (misma decisión, un único mecanismo).

### 3.15. Enriquecimiento de la interfaz del explorador (S040): clasificación, búsqueda y eliminación de duplicados

Registrada literalmente según se dictó (directriz 4.8). **Esto sí es
trabajo de S040, dentro de H29** — continuación explícita de lo
añadido "ayer" (mover archivos): *"De momento, lo que nos vamos a
dedicar es a enriquecer la interfaz de gestión del directorio. Ya
añadimos ayer el tema para mover archivos. Vamos a añadir hoy, pues,
temas de clasificación, búsqueda de duplicados, eliminación de
duplicados, etcétera, etcétera."*

**Objetivo de fondo explícito, ligado a 3.14:** verbatim: *"ya lo que
nos toca es clasificar todo lo que, todas las carpetas, clasificar
tipos de documentos, extracción de información, etcétera. Dotar a la
interfaz de todos esos métodos que luego se van a reutilizar en la
clasificación automática de la carpeta de la cuarentena."* Los
métodos de clasificación que se construyan en el explorador de H29
deben quedar diseñados para ser reutilizables después por el
consumidor de la cuarentena (H28 Fase 3) y, si se confirma, por la
vuelta del buzón de documentación (3.14) — sin acoplarlos
innecesariamente a la interfaz.

**No especificado por Miguel Ángel, pendiente de confirmar antes de
implementar (directriz 4.8):**
- Criterio exacto de detección de duplicados (¿hash de contenido del
  objeto GCS, nombre normalizado, o ambos combinados?).
- Acción exacta que dispara "clasificación" desde la interfaz sobre
  un archivo o carpeta ya existente en el índice (¿llamada a Gemini
  bajo demanda por archivo, por carpeta completa, o ambas?) y qué
  hace con el resultado (¿solo sugiere tipo/nombre para revisión
  humana, o renombra/mueve directamente?) — coherente con el
  principio ya vigente de que Gemini propone y el humano confirma
  (sin borrados automáticos).
- Flujo exacto de "eliminación de duplicados": ¿a la papelera del
  usuario (3.6, recuperable) o borrado directo con confirmación
  (3.10, registro histórico)?

**Aclaración de Miguel Ángel (misma sesión, S040):**

**Duplicados — criterio confirmado:** hash de contenido, de momento.
Verbatim: *"Hash de momento."*

**Clasificación y renombrado — dos responsabilidades separadas,
NUNCA una sola llamada a Gemini que decida el nombre final.** Verbatim:
*"Tendremos muchos archivos, hay que definir los formatos y nombrarlos
siguiendo siempre el mismo formato, quizás Gemini sugiere el tipo y el
renombrado lo tendremos que hacer nosotros con un método dedicado y
automatizado. No creo que Gemini siga siempre un formato fijo
establecido y podemos llegar a tener inconsistencias de nomenclatura
que no tendríamos si parseamos los nombres de archivo y luego
renombramos cuando ya tenemos una clasificación."*

Lectura directa de lo dicho, sin añadir nada: Gemini se limita a
**sugerir el tipo documental** (y la extracción de datos que
corresponda); el **nombre final se construye siempre con un método
propio, determinista**, a partir de esa clasificación — nunca se usa
el nombre que devuelva Gemini directamente. Pendiente de localizar
(antes de escribir código nuevo) si ya existe un método así en H23/H25
que se pueda reutilizar, o si hay que crearlo desde cero para H29.

**Formato de renombrado — confirmado por Miguel Ángel (misma sesión):**

- **Máquina:** confirmado el formato propuesto por el modelo —
  `{CÓDIGO_MÁQUINA}_{TIPO_DOCUMENTO}_{FECHA}.pdf`.
- **Personal — NUNCA por DNI ni identificador numérico.** Verbatim:
  *"Para los trabajadores, imagínate un montón de números con tipo de
  documento y fecha. No. Para los trabajadores lo que nos sirve es
  apellido, nombre, tipo de documento y fecha, para que cuando estés
  mirando el archivo sepas perfectamente de quién estás hablando."*
  Formato: `{APELLIDO}_{NOMBRE}_{TIPO_DOCUMENTO}_{FECHA}.pdf`.

**Diccionario de tipos documentales — pendiente de crear.** Verbatim:
*"hay que crear un diccionario con los tipos de documentos que
tenemos. Porque tenemos ITV, tenemos OCA, tenemos recibo del seguro,
tenemos cursos, tenemos DNI, tenemos, no sé, tarjeta de la seguridad
social, reconocimientos médicos. Hay que catalogarlo todo, hay que
catalogarlo todo y generar un diccionario con lo, bueno, un diccionario
o lo que creas más conveniente para luego poder reutilizarlo a la hora
del motor de renombrado."* Lista inicial de tipos citada, no
necesariamente cerrada: ITV, OCA, recibo del seguro, cursos, DNI,
tarjeta de la seguridad social, reconocimientos médicos.

**Tensión detectada por el modelo con lo ya existente en producción
(H23/H25, S026) — a resolver con Miguel Ángel antes de implementar:**
`document_ingestion.LearnedDocumentTypeKeyword.canonical_group` ya es
un diccionario de tipos, pero **de categorías libres sin lista
cerrada** — cada `company` aprende sus propios grupos a partir de lo
que Gemini proponga, sin catálogo fijo (decisión S016: "Gemini puede
proponer categorías libres, sin lista cerrada"). Es exactamente la
fuente de inconsistencia que Miguel Ángel quiere evitar para el motor
de renombrado.

**Resuelto por Miguel Ángel (misma sesión, S040) — aislamiento total
respecto a H17-H25:** Verbatim: *"H23, H25 se empezaron y se pararon
porque íbamos a cambiar totalmente el sistema. Así que, depender de
canonical_group... Nos olvidamos de H23 y H25. Estamos construyendo
sobre lo que tenemos. ¿Qué tenemos? Tenemos ahora mismo dos carpetas
subidas a Google Cloud Storage que tenemos que clasificar. Tenemos una
carpeta llamada cuarentena que tenemos que clasificar. Así que lo
primero que tenemos que hacer es, sin mirar a ningún otro sitio,
tenemos que ver lo que hay en esas dos grandes carpetas para clasificar
y hacer un algoritmo que clasifique y envíe lo que hay en la cuarentena
a esas carpetas. No quiero oír hablar de otra cosa que no sea esto. Es
decir, ni quiero ver H23, ni quiero ver H25, ni 22, ni 21, ni 20, ni
19, ni 18, ni 17. Quiero que nos centremos en lo que estamos haciendo y
nos olvidemos de lo que ya hay hecho en producción, y en ningún sitio.
Estamos dedicados a hacer una cosa nueva por completo. No podemos
estar mirando hacia otro lado. Y por supuesto, no podemos basar nada de
lo que estamos haciendo en unos hitos que están parados porque se ha
abandonado la forma de hacer de esa forma. Es decir, todo ese método,
toda esa infraestructura la hemos abandonado y estamos creando una
cosa nueva. No podemos estar pensando en esos hitos."*

**Regla derivada, de obligado cumplimiento para el resto de H29:** el
diccionario de tipos documentales, el motor de renombrado y el
algoritmo de clasificación de cuarentena se construyen **enteramente
dentro de `document_explorer`**, sin importar ni depender de
`document_ingestion.LearnedDocumentTypeKeyword`, `entity_matching_service`,
`machine_documents` ni `personal_documents`. El ámbito de trabajo son
únicamente los cubos/carpetas ya indexados por H29 dentro de
`cgs_grupo_alvarez` y la cuarentena (`_CUARENTENA/`). Código de
H17-H25 no se lee, no se cita ni se reutiliza para esta parte del
trabajo.

**Corrección real detectada en la propia sesión (directriz 4.9) — NO
es H17-H25, es trabajo previo de H28/`document_explorer` que sí
aplica:** al ir a escribir un comando de inventario heurístico nuevo,
se encontró que `document_explorer/management/commands/
audit_document_names.py` y `find_duplicate_documents.py` **ya
existen**, escritos en S039 como primer y segundo paso concreto de la
fusión H28 Fase 2/H29. `audit_document_names.py` ya hace exactamente
el mapeo heurístico pedido ahora (parte cada nombre por el primer
token con forma de fecha, cuenta frecuencia de la frase candidata a
tipo), afinado en dos pasadas reales sobre una muestra de 133 archivos
de las dos carpetas (Hallazgos 1-6 de este mismo anexo, sección 8) —
incluyendo **dos vocabularios ya disjuntos por dominio**:

- **Máquinas:** FICHA TECNICA, PERM.CIRCULACION, ITV, IPO, OCA, CE,
  RAE, C.ADECUACION, CERT.NO TARJ.TTES, CERT MANTENIMIENTO, LIBRO
  HISTORIAL, TABLA DE CARGA, MANUAL USO, POLIZA, REC.SEG, SEGURO, BAJA
  TEMPORAL.
- **Personal:** RM, ALTA, APTO DEFINITIVO, AUT USO MAQ, CARNET DE
  CONDUCIR, TARJETA DEL CONDUCTOR, TARJETA CUALIFICACION CONDUCTOR,
  RENOVACION CAP, DNI, CONTRATO INDEF, COMUNIC CONTRATO INDEF, Mod
  145, IDC, ENTREGA INFORMACION, EPIS, FORM (2H, 6H, 60H), ESTIBA DE
  PLATAFORMAS, PARTE VACACIONES, DOC VARIOS.

**Pero seguía pendiente al cierre de S039** (última "Hoja de ruta"
del anexo H28, punto 6): cerrar el vocabulario sobre el **corpus
completo** (16.022 + 21.507 archivos), no solo la muestra de 133 -- la
propia razón de ser de `audit_document_names.py`, según su docstring.

**Consecuencia sobre lo ya construido en esta sesión (S040):** el
`DocumentTypeCatalog` sembrado con 7 tipos genéricos (ITV, OCA,
SEGURO, CURSO, DNI, SEG_SOCIAL, RECONOCIMIENTO_MEDICO) queda **como
seed provisional, a sustituir por el vocabulario real** en cuanto se
cierre sobre el corpus completo -- los dos vocabularios de arriba ya
son más ricos y correctos que el seed provisional. No se reescribe el
catálogo todavía porque el corpus completo aún no se ha auditado.

**No se escribe ningún comando nuevo de inventario** -- se reutiliza
`audit_document_names.py` tal cual, ejecutándolo sobre el corpus
completo en vez de escribir algo redundante.

### 3.16. Auditoría sobre el corpus completo (S040) — resultado real y corrección de Miguel Ángel

Ejecutado `audit_document_names.py --bucket cgs_grupo_alvarez --top
200` sobre el corpus real: 16.031 archivos en `DOC. MAQUINAS`, 21.519
en `DOC. PERSONAL` (37.550 en total).

**Hallazgo técnico:** 6.563 archivos de MÁQUINAS (41%) y 7.464 de
PERSONAL (35%) no tienen fecha reconocible en el nombre, y el
heurístico actual (parte por la fecha) no cuenta ninguna frase
candidata para ellos aunque la mayoría sí tiene un tipo legible
(`0069-GXX FICHA TECNICA.pdf`, `0168-DZS SEGURO.pdf`). Pendiente de
mejorar antes de cerrar el vocabulario, para no perder ~38% del
corpus.

**Error del modelo, corregido por Miguel Ángel en la misma sesión:**
el modelo propuso fusionar `NOMINA`/`NOMINAS` con `PAGO CORRIENTE`
como el mismo tipo, basándose únicamente en el nombre de archivo.
Verbatim de Miguel Ángel: *"Pago corriente y nómina no son lo mismo,
por eso te he dicho que es necesario ver los documentos antes de
normalizar los nombres."* Quedan como dos tipos distintos,
`NOMINA` y `PAGO_CORRIENTE`, no fusionados.

**Regla derivada, de obligado cumplimiento para el resto de la
curación del vocabulario:** el modelo **no fusiona ni asume
sinónimos por similitud de nombre de archivo**. Para cualquier grupo
donde la equivalencia no sea evidente sin ambigüedad, el modelo debe
pedir a Miguel Ángel que suba una muestra real del documento (el
modelo no tiene acceso de red a GCS desde este entorno, así que no
puede abrirlos por sí mismo) antes de decidir si dos frases
candidatas son el mismo tipo documental o no.

**Pendiente de confirmar con muestra real subida por Miguel Ángel,
sin asumir nada:** `IDC` (237 casos) y `CSS ADOLFO ALVAREZ` (88
casos) -- abreviaturas no identificables por el modelo solo con el
nombre de archivo.

**Confirmado leyendo el contenido real de las muestras subidas por
Miguel Ángel (S040) -- cuatro tipos distintos, ninguno fusionable con
otro:**

- **`CSS`** -- Certificado de estar al corriente en las obligaciones
  de Seguridad Social, emitido por la Tesorería General de la
  Seguridad Social.
- **`IDC`** -- Informe de Datos para la Cotización: historial de
  cotización/relación laboral de un trabajador, emitido por
  Seguridad Social. Documento distinto de `CSS` pese a compartir
  organismo emisor.
- **`NOMINA`** -- Nómina real, individual, mensual, por trabajador.
- **`PAGO_CORRIENTE`** -- **No es una nómina.** Declaración de la
  propia empresa (firmada por Adolfo Álvarez como administrador),
  listando varios trabajadores a la vez, certificando que están al
  corriente de cobro de salarios, emitida **por obra/cliente**
  (ADITEL, ANFRASA...) para subcontratación -- nunca un documento
  individual del trabajador. Confirma la corrección de Miguel Ángel
  al inicio de esta sección.

Añadidos al catálogo (migración `0003_seed_confirmed_types.py`, datos
únicamente, sin cambio de esquema), los cuatro con `domain=PERSONAL`.

### 3.17. Formato definitivo de renombrado personal: apellido1_apellido2_nombre, con el nombre real extraído del DNI (S040)

Registrada literalmente según se dictó (directriz 4.8). Sustituye por
completo al formato provisional de 3.15
(`{APELLIDO}_{NOMBRE}_{TIPO}_{FECHA}`).

**Fuente de verdad del nombre real -- el DNI, no el nombre de
archivo.** Verbatim: *"Tenemos que sacar los nombres y apellidos del
DNI. No hay otra. En el DNI viene nombre por un lado y apellidos por
otro. Viene, es más, viene como primer apellido, segundo apellido y
nombre. Con lo cual podemos perfectamente inferir el nombre del
DNI."* Cierra directamente el problema de Hallazgo 5 (el nombre del
operario aparece de ocho formas distintas en el propio nombre de
archivo, con errores incluidos) -- el nombre de archivo deja de ser la
fuente, lo es el contenido real del documento DNI de esa persona.

**Motivo de fondo -- orden alfabético útil en cualquier contexto,
mezclados o no en carpetas.** Verbatim: *"Lo digo porque es
importante que el nombre del archivo, tanto en la máquina vaya primero
con el código de la máquina, como el personal vaya primero con los
apellidos y el nombre del personal. De tal manera que van a quedar
ordenados, digamos, si estuvieran todos juntos sin meter en carpetas,
estarían bien ordenados. Es decir, si sacamos diversos documentos de
diversos trabajadores y los metemos en una carpeta, van a quedar
perfectamente ordenados por trabajador. Y de un vistazo vas a saber
cuáles documentos pertenecen a cada uno de los trabajadores. Si
formamos un dossier para enviarlo a alguna otra empresa, ese mismo
orden nos va a ayudar a que los PDFs del dossier, las hojas, estén
también ordenadas de forma correcta."*

**Formato exacto**, verbatim: *"la nomenclatura debe de ser, primer
apellido, guión bajo, segundo apellido, guión bajo, nombre, guión
bajo, tipo de documento, y fecha y ordinal por si hay varios
documentos que se llamen igual o que tengan la misma fecha."*

```
{PRIMER_APELLIDO}_{SEGUNDO_APELLIDO}_{NOMBRE}_{TIPO_DOCUMENTO}_{FECHA}[_{ORDINAL}].pdf
```

El formato de máquina (3.15) no cambia -- ya cumplía la misma regla de
fondo (código primero) desde el principio:
`{CÓDIGO_MÁQUINA}_{TIPO_DOCUMENTO}_{FECHA}[_{ORDINAL}].pdf`.

**No resuelto por interpretación propia, pendiente cuando se aborde
la extracción real:** cómo se obtiene el DNI de cada trabajador para
leerlo (¿un DNI de referencia por persona, ya clasificado una vez, que
sirve para todos sus demás documentos? ¿re-lectura si no se
encuentra?), y qué pasa con personas cuyo DNI no está todavía en el
corpus o no se puede leer. Se resuelve al diseñar el motor de
clasificación real, no aquí.

### 3.18. Vocabulario cerrado, primera versión (S040)

Cerrado a partir de las frases candidatas reales de
`audit_document_names.py` sobre el corpus completo -- 24 tipos
MÁQUINA + 12 tipos PERSONAL, sumados a los 4 confirmados con
contenido real de 3.16 y los provisionales de 3.15 que siguen
vigentes (`DNI`, `SEG_SOCIAL`, `RECONOCIMIENTO_MEDICO`; `CURSO` se
sustituye por `FORMACION`, más ajustado al vocabulario real).
Migración `0004_seed_closed_vocabulary.py`, solo datos. Fusionado
únicamente donde el propio texto no deja ambigüedad (variantes de
formato de la misma sigla administrativa) -- extensible, no cerrado
para siempre. Detalle completo en el propio archivo de migración.

### 3.19. Clasificar es 100% virtual: nunca se toca GCS, ni para mover ni para renombrar (S040)

Registrada literalmente según se dictó (directriz 4.8). Corrige un
vacío de diseño de `ClassifyView` (S040, ver más abajo): la vista
actual (commit `ec71779`) es de solo lectura -- muestra la sugerencia
de Gemini por mensaje, sin persistir nada -- así que no contradice
esta decisión, pero el paso de "aplicar" la clasificación (todavía sin
construir) debe seguir esta regla desde el primer commit, sin excepción.

**Ni renombrado real, ni movimiento real -- mismo patrón que
`move_service` (v2, puntero puro, S039).** Verbatim: *"vamos a hacer
igual que con los... como cuando movemos archivos. En realidad no
vamos a tocar CGS, lo vamos a hacer todo a nivel de datos, o sea, a
nivel de base de datos, para que sea lo más rápido posible. Cuando se
descargue un archivo, es cuando lo descargaremos, lo descargaremos
con el nombre ya correcto. Mientras tanto, se quedan con el nombre con
el que se subieron a CGS. Al clasificarla le damos el nombre nuevo en
base de datos, con lo cual es muchísimo más rápido que cambiar los
nombres de los archivos en la nube. Y una vez que vayan a
descargarlos porque se vayan a usar, es cuando les cambiamos el
nombre."*

**Por qué no hace falta tocar el nombre real nunca en GCS:** verbatim:
*"los que vamos a tener en CGS, como el nombre que vamos a presentar,
lo vamos a presentar nosotros en las plantillas, no es necesario
cambiarles el nombre realmente, tan solo cambiarlo cuando se van a
descargar."*

**Tampoco se mueve nada de cuarentena -- la ubicación clasificada
también es solo un puntero.** Verbatim: *"realmente no vamos a mover
los archivos de cuarentena. Simplemente le vamos a decir que están en
tal carpeta a nivel de datos (...) aunque los archivos sigan en
cuarentena. Todo va a quedar de forma virtual y en base de datos."*
Confirma explícitamente que esto ya se había decidido antes: *"esto se
dijo ayer (...) para no mover archivos realmente, para no borrar
archivos realmente (...) por flags, banderas (...) y con anotaciones
de punteros que realmente los archivos no se mueven y quedan siempre
en el mismo sitio. Hemos hecho un primer movimiento que sí fue real,
pero ahora realmente quedará todo en (...) cuarentena y de cuarentena
realmente no se va a mover a ningún sitio."*

**Consecuencia técnica directa, reutilizando lo ya construido en
`move_service` (nunca reinventado):** aplicar una clasificación sobre
un archivo de cuarentena es, mecánicamente, lo mismo que ya hace
`move_service.move_entries()` -- escribir `parent_path`/`name`
(ubicación y nombre VIRTUALES) sin tocar jamás `blob_name` (la ruta
real en GCS, que sigue apuntando dentro de `_CUARENTENA/` para
siempre). El `name` virtual pasa a ser el nombre normalizado que
construye `naming_service`, no el nombre con el que se subió
originalmente.

**Excepción -- la vuelta del buzón de documentación (3.14, todavía sin
hito asignado) SÍ renombra de verdad, pero en local, nunca en GCS.**
Verbatim: *"Cuando hagamos la vuelta (...) tendremos que incluir
también una herramienta de renombrado en el agente (...) todos los
documentos que tenemos ahora mismo en local, en Microsoft 365. Ahí sí
tendremos que renombrar realmente los archivos, porque ahí interesa
que sean renombrados."* El agente de Windows (H28) es quien
renombraría de verdad los archivos LOCALES; GCS nunca se toca por este
motivo bajo ninguna circunstancia.

**Pendiente, no resuelto aquí -- para cuando se construya el paso de
"aplicar clasificación":**

- `OpenDocumentView` hoy redirige a una URL firmada sobre el nombre
  REAL del objeto (`entry.blob_name`) sin forzar ningún nombre de
  descarga -- verificado contra el código real, `spare_parts.
  gcs_service.generate_signed_url()` no acepta todavía ningún
  parámetro para forzar el nombre de descarga. Para que la descarga
  llegue "con el nombre ya correcto" hace falta añadir soporte de
  `response-content-disposition` (parámetro real de las URLs firmadas
  V4 de GCS) a `generate_signed_url()` -- cambio en `spare_parts`, app
  compartida, a evaluar con cuidado por afectar a otros llamantes.
- Falta decidir el mecanismo real de extracción del DNI como fuente
  del nombre (ya apuntado como pendiente en 3.17) antes de que
  `ClassifyView` pueda aplicar nada de verdad sobre `DOC. PERSONAL`.

### 3.20. Plan ampliado tras la interfaz de clasificación (S040)

Registrada literalmente según se dictó (directriz 4.8). Ninguno de
estos puntos está construido todavía salvo el primero (clasificación
real de las dos carpetas), que se aborda en esta misma sesión --
`ClassifyView` pasa de solo mostrar la sugerencia a aplicarla de
verdad (siempre virtual, ver 3.19).

Verbatim, orden de trabajo dado por Miguel Ángel: *"con el tema de la
interfaz y comenzamos ya la clasificación de las dos carpetas, que
habrá que hacerlo ya. Y una vez que tengamos la clasificación
correcta, habrá que realizar, implementar la always on task que
clasifique la carpeta de cuarentena. Y tras ello, tenemos que preparar
la vuelta (...) La vuelta y la clasificación en local. Y preparando
también el buzón, el buzón de documentación, donde van a ir los
documentos adjuntos. Hay que preparar la interfaz de la plataforma del
panel también para gestionar esa carpeta, para saber lo que ha entrado
nuevo, lo que se ha clasificado, lo que está no conforme, etcétera. De
igual manera, también necesitamos una carpeta de no conformidad para
el tema de la cuarentena, o marcar los archivos, no sé si tendremos
que hacer alguna migración, si hay que hacerla, pues se hace."*

**Orden de trabajo, sin fecha ni sesión fijada para cada punto --
depende de cómo avance la clasificación real:**

1. Clasificación real de `DOC. MAQUINAS`/`DOC. PERSONAL` -- en curso
   en esta sesión (`ClassifyView`/`apply_classification`).
2. Always-on Task que clasifique automáticamente la cuarentena --
   sustituye/concreta al "consumidor de la cuarentena" (Fase 3 de
   H28) ya anotado en la hoja de ruta. Reutilizará
   `apply_classification()`, pero además tendrá que escribir la
   ubicación VIRTUAL (`parent_path`) además del nombre, ya que un
   archivo de cuarentena sí cambia de carpeta clasificada (a
   diferencia de renombrar en el sitio, que es lo único que hace hoy
   `apply_classification()` sobre las dos carpetas ya pobladas).
3. "La vuelta" y la clasificación en local (agente de Windows, H28) --
   depende de 3.14, ya asignada a H29, pendiente de construir.
4. Interfaz de panel para el buzón de documentación (3.14): qué ha
   entrado nuevo, qué se ha clasificado, qué está no conforme.
5. Carpeta/marca de "no conformidad" también para la cuarentena (no
   solo para la vuelta del buzón, 3.14) -- Miguel Ángel deja abierto
   si hace falta migración nueva, delegando la decisión: *"no sé si
   tendremos que hacer alguna migración, si hay que hacerla, pues se
   hace."*

**No resuelto por interpretación propia, a decidir cuando se aborde
cada punto:** el esquema exacto de "no conformidad" para cuarentena
(¿campo en `DocumentIndexEntry`, o carpeta virtual dedicada tipo
`_NO_CONFORME/` dentro del árbol clasificado?), y el diseño completo
de la interfaz del buzón (2 y 4 dependen de que 3.14 tenga hito
asignado).

### 3.21. Un manual por modelo de máquina: diferido; eliminación de duplicados: conectada a la interfaz ya (S040)

Registrada literalmente según se dictó (directriz 4.8).

**Un manual por modelo, no por máquina -- diferido explícitamente,
sin resolver aquí.** Verbatim: *"en la clasificación de los manuales,
que, como ya sabes, que vamos a tener solamente un manual por modelo
de máquina, y no por máquina que se tenga. Porque si hay tres máquinas
que son iguales, no vamos a tener tres manuales. Vamos a conservar
uno, y cada una va a decir que tiene ese manual (...) O lo hacemos
luego."* Pendiente sin fecha: diseñar cómo un único `DocumentIndexEntry`
de manual queda "asociado" a varias máquinas del mismo modelo (¿tabla
puente, `domain_object` múltiple, algo distinto?) -- **no se decide
nada de esto aquí, ni se construye.**

**Eliminación de duplicados -- esto sí, ya, en esta sesión.** Verbatim:
*"Eliminar los duplicados de los manuales y de bueno y de todo. Porque
no lo he visto en la interfaz."* Corrección de un hueco real: el
modelo había construido `duplicates_service.find_duplicate_groups()`
antes en la misma sesión pero nunca lo conectó a ninguna vista --
`DuplicatesView`/`SendDuplicatesToTrashView` (enlace "Duplicados" en
el explorador, solo administrador) cierran ese hueco. Ningún duplicado
se preselecciona para borrar -- ver docstring de `DuplicatesView` para
el motivo. El borrado sigue pasando por la papelera de dos niveles ya
existente (3.6/3.10), nunca un borrado duro directo.

### 3.22. Corrección sobre 3.21: resolución automática en bloque + registro de auditoría persistente (S040)

Registrada literalmente según se dictó (directriz 4.8). Corrige el
diseño "sin preselección" de 3.21 en cuanto se vio el volumen real.

**El diseño manual de 3.21 no escala -- 3.570 grupos reales.**
Verbatim: *"Hay 3.570 grupos. Es decir, tendría que hacer 3.750 marcas
y luego enviar a la papelera. Esto es un rollo. Luego aparte, estamos
sacando nada más duplicados. Puede haber triplicados, puede haber
cuadriplicados. Yo lo que quiero es una única copia de cada uno de los
archivos. Y todas las demás copias a la papelera."*

**Da igual qué copia se conserve ni dónde esté -- el hash ya lo
garantiza, y la ubicación deja de importar en cuanto se clasifica por
máquina/persona, no por carpeta.** Verbatim: *"Con el hash nos
aseguramos que si tienen el mismo hash, son exactamente el mismo
archivo (...) me da igual dónde estén (...) la clasificación total va
a ser por máquina, a nivel de base de datos (...) poco importa también
dónde los dejemos, puesto que luego va a ser la propia hoja ficha de
la máquina la que nos va a decir dónde está cada documento (...)
anotar qué documento es el que queda, dónde está, cuál es su puntero
virtual. Si es necesario luego, movemos el puntero virtual donde
corresponde."* Confirma y refuerza 3.19 (todo virtual, nunca se toca
GCS) también para esta operación.

**`ResolveDuplicatesView`**, un solo clic: conserva una copia
arbitraria de cada grupo, el resto a la papelera del administrador --
dos consultas en total para el envío a papelera (`UPDATE ... WHERE pk
IN (...)`, nunca un `.save()` por fila), mismo principio que
`move_service.move_entries()` (S039). El listado manual de 3.21 se
conserva como alternativa, acotado a 200 grupos por página para no
generar una respuesta enorme, pero deja de ser el camino principal.

**Registro de auditoría -- nueva necesidad, sin la cual esta operación
sería opaca.** Verbatim: *"Tenemos que dejar un informe (...) un
historial de qué hemos hecho (...) para que podamos decir, pues mira,
se han eliminado tantos miles de archivos, las carpetas que se han
visto afectadas han sido estas, y el listado de todos los archivos que
se han eliminado, que realmente no hemos eliminado, que simplemente
están marcados como eliminados, para poder hacer una auditoría en el
momento que queramos."* Nuevos modelos `DataOperationLog` (cabecera:
cuándo, quién, ámbito, cuántos grupos/conservados/enviados a papelera,
bytes recuperables) y `DataOperationLogEntry` (una línea por archivo,
con foto fija de `bucket`/`blob_name`/`name`/`parent_path`/
`size_bytes` en el momento de la operación, para que el informe siga
leyéndose bien aunque la fila real cambie o se vacíe después).
Migración `0005_dataoperationlog.py`. Historial navegable desde el
panel (enlace "Historial" junto a "Duplicados"), paginado por offset
(vista ocasional de auditoría, no ruta de navegación caliente).
`operation_type` es genérico a propósito para que futuras operaciones
masivas (clasificación por lote, consumidor de cuarentena) registren
de la misma forma.

### 3.23. Registro de auditoría extendido a la clasificación (S040)

Registrada literalmente según se dictó (directriz 4.8). Confirma la
previsión genérica de `operation_type` en 3.22: verbatim, Miguel
Ángel, al retomar tras confirmar que la resolución de duplicados
funcionó de verdad en producción ("ha entrado una persona, le he dado
duplicado y me ha dicho que ya no existe ninguno"): *"el registro de
auditoría es fundamental. Y deja eso preparado primero y hacemos
primero una pequeña prueba controlada."*

`ClassifyView` ahora escribe `DataOperationLog`
(`operation_type=BATCH_CLASSIFICATION`) igual que
`ResolveDuplicatesView`. Ampliaciones necesarias en los modelos
(migración `0007_dataoperationlog_classification_support.py`, sin
backfill porque no había ninguna fila de clasificación previa):

- Dos acciones nuevas en `DataOperationLogEntry`: `CLASSIFIED`
  (aplicada) y `NOT_CLASSIFIED` (sin datos suficientes, o error de
  Gemini).
- `previous_name`: nombre virtual antes de aplicar -- vacío en
  duplicados (ahí el nombre no cambia, solo la ubicación en papelera).
- `detail`: texto libre -- en clasificación, dominio/tipo/confianza/
  razonamiento de Gemini; reutilizable por cualquier operación futura
  que necesite explicar su decisión.
- `DataOperationLog.primary_count_label`/`secondary_count_label`:
  propiedades que traducen `kept_count`/`trashed_count` a la etiqueta
  correcta según `operation_type` ("Clasificadas con éxito"/"Sin
  poder aplicar" vs. "Copias conservadas"/"Copias enviadas a
  papelera"), sin necesitar columnas nuevas por tipo de operación.

Cada archivo clasificado es su propio "grupo" de tamaño 1 en el
mismo detalle agrupado por `group_number` de 3.22 -- ninguna plantilla
nueva, el historial de clasificación se ve con el mismo diseño de
tarjetas que ya validó Miguel Ángel para duplicados.

### 3.24. Archivos "dos en uno" (dosieres): desdoblar en documentos únicos, nunca conservar el combinado (S040)

Registrada literalmente según se dictó (directriz 4.8), a raíz de un
hallazgo real de la primera prueba controlada (`CE+RAE.pdf`).

Verbatim: *"Cuando van dos en uno deben existir dos documentos con
cada uno y se borra el que contiene a los dos. Dejamos archivos con
documentos únicos en vez de dosieres, eso sí, los componentes
unitarios de los dosieres debe existir sí o sí."*

Lectura directa, sin resolver nada por interpretación propia:

1. Un archivo que contiene dos (o más) tipos documentales distintos
   (`CE+RAE`) es un "dosier" -- el objetivo final es que cada tipo
   exista como **documento único e independiente**, nunca como
   combinado.
2. El combinado se borra (a papelera, como todo en este proyecto) una
   vez que **cada componente unitario existe de verdad** como archivo
   propio -- ya sea porque ya existía por separado en otro sitio, o
   porque hay que generarlo desde el propio combinado.
3. **Nunca se borra un combinado dejando un componente sin existir en
   ningún sitio** -- "los componentes unitarios de los dosieres debe
   existir sí o sí" es una condición previa al borrado, no posterior.

**RESUELTO EN S041 -- la condición previa de este punto (punto 3 de
"no resuelto" más abajo) queda expresamente abandonada por decisión
de Miguel Ángel, no reinterpretada.** Verbatim: *"Vamos a dar por
sentado de que cuando hay un dossier, todos los documentos están. Lo
damos por sentado. Es decir, esa regla la vamos a obviar. Cuando hay
un dossier, el dossier se borra. Porque presumimos que ambos
documentos, o todos los documentos que lo conforman, existen."*

Consecuencia directa: el punto 2 de la lectura de abajo ("una vez
que cada componente unitario existe de verdad") deja de ser una
condición verificada -- se presume cierta, nunca se comprueba. El
punto 3 ("nunca se borra... sin existir en ningún sitio") queda sin
efecto. Los otros dos "no resueltos" quedan así:

- Generar el componente que falte partiendo el PDF (tensión con
  3.19): **ya no aplica** -- al presumir que los componentes existen,
  no hay generación que hacer. Sigue sin construirse ninguna
  herramienta de partición de PDF, y no hace falta.
- Cómo detecta el motor que un archivo es un dosier: **resuelto en
  S041** -- campo `is_dossier` en la respuesta de Gemini
  (`classification_service._RESPONSE_SCHEMA`), solo `true` con
  certeza real de varios tipos catalogados distintos, nunca por
  simple `DESCONOCIDO` sin identificar. Ver 3.39 para el detalle
  completo de la implementación.

**Corrección importante, misma sesión -- la Tarjeta ITV NO es un
ejemplo de dosier.** El modelo interpretó por error que la Tarjeta ITV
con Hoja Adicional de Inspecciones (Hallazgo 3 de la primera prueba
controlada) mezclaba dos documentos (ficha técnica + historial ITV).
Miguel Ángel corrige: es un único documento por diseño. Verbatim:
*"la tarjeta de inspección técnica es un documento que tiene dos
partes (...) Eso es un documento completo. No son dos documentos.
Eso normalmente viene como documento completo. ¿Qué ocurre cuando una
máquina ha rellenado todo el historial? Lo que se hace es meter una
hoja adicional, pero forma parte del mismo documento. Lo único que
pasa es que los huecos para la firma y sello de las diferentes
inspecciones periódicas técnicas ya están rellenos, y se añade una
hoja adicional para seguir rellenando, pero es el mismo documento. Es
lo que llamamos normalmente ITV."* Con vida útil larga, se van
añadiendo más hojas adicionales conforme se llenan los huecos de
sellado (el ejemplo real tenía 12 huecos en la hoja adicional).
**Consecuencia:** ese archivo concreto de la prueba estaba mal
clasificado como `FICHA_TECNICA` -- debía ser `ITV`. No es un caso de
dosier; es un fallo de clasificación normal, a tener en cuenta al
seguir probando (ver también el ajuste de descripción del tipo `ITV`
en el catálogo, mismo commit).

**Estado final tras S041 (ya no "no resuelto", solo un residual
distinto -- ver 3.38 y punto 3 de la hoja de ruta):** el caso "dos en
uno" del **mismo tipo repetido para varias personas** (Modelo 145 con
varios trabajadores, ver 3.31) NO entra en `is_dossier` -- ese campo
exige tipos catalogados *distintos*, no el mismo tipo repetido. Sigue
sin decisión tomada sobre ese caso concreto, pendiente como punto 3
de la hoja de ruta de la siguiente sesión.

### 3.25. Aviso de máquina equivocada: marca/modelo del documento contra `fleet.MachineAsset` (S040)

Registrada literalmente según se dictó (directriz 4.8). Distinta del
fallo #4 de la primera prueba (ese era `machine_code_hint` leyendo el
modelo del fabricante en vez del código de flota, ya corregido) --
este caso es al revés: el documento SÍ es de verdad de esa máquina
por marca/modelo, pero puede estar archivado en la carpeta de otra
máquina distinta.

Verbatim, con ejemplo explícito para descartar el falso positivo:
*"aquí hemos visto un documento que es de la máquina Luna tal (...)
Ese documento está en la carpeta de esa máquina porque esa máquina
realmente es una Luna tal, aunque (...) puso el modelo real de la
máquina [en vez del código interno] (...) realmente ese documento sí
pertenece a esa máquina [-- eso NO debe avisar]. Entonces, lo que hay
que detectar es cuando (...) ese documento que es de una Luna, de una
grúa Luna, modelo tal, se encuentra en (...) la B34 que resulta que es
una Liebherr. Y ahora nos encontramos que es una Liebherr y nos
encontramos un documento que dice que es la Luna modelo tal. Error.
Tiene que avisar."*

**Construido en la misma sesión** (no queda pendiente, a diferencia de
3.24):

- Nuevo campo `brand_model_hint` en la respuesta de Gemini (marca +
  modelo tal cual los dé el propio documento, p. ej. "LUNA AT-35/32"),
  distinto y complementario de `machine_code_hint`.
- `classification_service.resolve_machine_asset()`: resuelve la
  máquina real de la carpeta buscando un segmento con forma de código
  de flota en `parent_path` y consultando `fleet.MachineAsset.code`
  (sin guiones, sin distinguir mayúsculas). `fleet` (H12) es
  infraestructura viva en producción, no H17-H25 -- consultarla en
  solo lectura no rompe el aislamiento de 3.15.
- `classification_service.check_machine_mismatch()`: compara solo la
  **marca** (primera palabra), sin distinguir mayúsculas, contra
  `MachineAsset.brand_model` -- a propósito basto, para no generar
  falsos positivos por variantes de modelo dentro de la misma marca.
  Devuelve un aviso solo cuando la marca no coincide en absoluto.
- El aviso aparece como mensaje en `ClassifyView` y queda también en
  el `detail` de `DataOperationLogEntry`, visible en el Historial.

**No resuelto, pendiente si hace falta más adelante:** qué hacer de
forma activa con el aviso (hoy es solo informativo -- no mueve, no
reclasifica, no crea ninguna tarea de revisión aparte).

### 3.26. Corrección: reclasificar un archivo ya bien nombrado se mostraba como fallo (S040)

Diagnosticado con datos reales del servidor (`classify_entry`/
`build_new_name` ejecutados a mano contra un caso concreto, PK 8282),
nunca por especulación -- Miguel Ángel repitió la clasificación sobre
los mismos 21 archivos de la primera prueba (varios ya renombrados
correctamente) y la mayoría de los ya correctos salieron como "no se
pudo aplicar (faltan datos para el nombre)", con `machine_code_hint`
presente en las propias pistas mostradas -- contradicción visible que
disparó el diagnóstico.

**Causa raíz real:** `build_new_name()` funcionaba perfectamente y
devolvía el nombre correcto -- que resultó ser idéntico al nombre que
el archivo ya tenía (clasificado bien en la sesión anterior). Como
`renamed = final_name != entry.name` daba `False` en ese caso, y
`apply_classification()`/`ClassifyView` solo distinguían
`renamed=True` de `renamed=False`, un "ya estaba bien, no hacía falta
tocar nada" se mostraba exactamente igual que un fallo genuino.

**Corregido:** `apply_classification()` devuelve ahora también
`classified` (bool -- se pudo construir un nombre válido, sea cual
sea el resultado) además de `renamed` (bool -- el nombre cambió de
verdad). `ClassifyView` distingue tres casos: renombrado (éxito, con
flecha `->`), ya correcto (éxito, sin cambios, mensaje informativo
aparte), y fallo real (sin datos suficientes, aviso). Los dos
primeros cuentan como éxito en el registro de auditoría -- solo el
tercero cuenta como "sin poder aplicar".

### 3.27. El código de máquina de la carpeta prevalece sobre lo que lea Gemini (S040)

Hallazgo real de la segunda repetición de la prueba controlada:
`E0356BBZ_PERMISO_CIRCULACION_20200225.pdf` (máquina A-29, confirmado
por `blob_name`) se reclasificó una vez con `machine_code_hint`
correcto (`E0356BBZ`) y la siguiente vez con uno incorrecto (`A-24`,
inventado) para el mismo archivo sin cambios -- Gemini no es
perfectamente determinista entre llamadas pese a `temperature=0.0`.

**Corregido:** `build_new_name()` ahora resuelve primero la máquina
real de la carpeta vía `resolve_machine_asset()` (ya construida para
3.25) y, si la resuelve, usa siempre `MachineAsset.code` -- ignorando
por completo `machine_code_hint` de Gemini. Gemini solo decide el
código de máquina cuando la carpeta no resuelve a ninguna máquina
real (el caso futuro de cuarentena, antes de clasificar). Mismo
principio anotado como recordatorio en 3.14 para el agente de
Windows y el buzón de documentación: cuando el sistema ya sabe la
respuesta por otra vía fiable, Gemini deja de tener que adivinarla.

### 3.28. Incidente real: 504 del balanceador en lote recursivo -- clasificación pasa a Celery, auditoría incremental (S040)

Al pedir clasificar `A-29` recursivamente (carpeta + subcarpetas,
usando el selector de ámbito de búsqueda ya existente, sin código
nuevo) apareció un 504 real de PythonAnywhere ("Something went
wrong :-("). Confirmado con capturas reales del dashboard que el
sitio en sí no estaba caído (todas las Always-on Tasks seguían
Running) -- solo esa petición larga murió.

**Causa raíz:** `ClassifyView.post()` encadenaba una llamada real a
Gemini por archivo, una detrás de otra, dentro de la misma petición
HTTP síncrona -- con suficientes archivos, se supera el tiempo límite
del balanceador.

**Segundo problema real, expuesto por el mismo incidente:** el
registro de auditoría (3.23) solo se escribía al final del lote, en
un `bulk_create`. Si la petición muere a mitad, varios archivos ya se
habían renombrado de verdad en base de datos (`apply_classification`
guarda por archivo, al momento) sin dejar ningún rastro en el
Historial -- justo la opacidad que 3.23 existe para evitar.

**Corregido, los dos a la vez:**

- `document_explorer/tasks.py` (nuevo): `classify_entries_task`,
  tarea Celery real que reutiliza el worker ya en producción
  (`spare_parts.tasks.extract_delivery_note_data` es el mismo
  mecanismo, no uno nuevo). `ClassifyView.post()` ahora solo crea la
  cabecera `DataOperationLog` (`status=RUNNING`) y encola la tarea
  con `.delay()`, devolviendo el control al instante -- nada de
  Gemini ocurre ya dentro de la petición HTTP.
- La tarea escribe una `DataOperationLogEntry` justo después de cada
  archivo, nunca al final -- un fallo de Celery, del worker, de
  cualquier cosa, solo pierde la cola sin procesar, nunca el rastro
  de lo ya hecho.
- Nuevo campo `DataOperationLog.status`
  (`RUNNING`/`COMPLETED`/`FAILED`, migración `0009`) -- el Historial
  muestra "en curso" con el número de archivos ya procesados mientras
  la tarea corre, y pide recargar la página para ver avance (sin
  progreso en vivo por WebSocket ni similar, deliberadamente simple).

### 3.29. Conversión de Office a PDF (LibreOffice headless) para poder clasificar .docx/.xlsx/.pptx (S040)

Verbatim: *"cuando encontremos un documento como el que tenemos de
ejemplo, el docx (...) convertirlo a PDF y clasificarlo."* Resuelve
el fallo real de la primera prueba controlada (`.docx` rechazado por
Gemini, 400 INVALID_ARGUMENT).

**Verificado antes de escribir nada, nunca asumido:** `soffice`/
`libreoffice` (6.4.7.2) confirmado instalado en el servidor real
(`/usr/bin/soffice`) vía Comando S antes de tocar código. No hizo
falta ninguna dependencia Python nueva -- se invoca por
`subprocess`, de la librería estándar, así que `requirements.in` no
se toca. Comprobación de coherencia 7.3 de `com-environment-management`
ejecutada igualmente antes de empezar (candado limpio, sin
divergencias).

`classification_service._convert_to_pdf()`: convierte con
`soffice --headless --convert-to pdf`, en un directorio temporal
desechable con perfil de usuario propio
(`-env:UserInstallation=...`, evita el bloqueo conocido de
LibreOffice ante conversiones concurrentes). **Nunca toca GCS** -- el
PDF convertido vive solo en memoria/disco temporal el tiempo de
dárselo a Gemini, coherente con 3.19 (clasificar nunca toca GCS): no
es un documento nuevo que se guarde en ningún sitio, es un intermedio
desechable para que Gemini pueda leer contenido que no admite de
forma nativa.

Cubre `.docx`/`.doc`/`.odt`/`.rtf`/`.xlsx`/`.xls`/`.ods`/`.pptx`/
`.ppt`/`.odp` -- todo lo que `soffice` sabe convertir a PDF, no solo
el caso concreto del `.docx` de la prueba. Probado con un `.docx` real
antes de comitear (conversión correcta, cabecera `%PDF-` verificada).

**Incidente de despliegue real, mismo día:** el fix llegó al servidor
(`git pull` correcto, verificado) pero el worker Celery no lo recogió
-- `deploy.yml` reinicia el worker según un patrón de rutas que no
cubría `document_explorer/` en absoluto (mismo tipo exacto de
incidente que S025 con `document_management/`). Confirmado con el log
real del worker: seguía arrancado desde el despliegue anterior, sin
ninguna línea de reinicio tras el push. `deploy.yml` corregido
(`document_explorer/` añadido al patrón); ese commit no reinicia el
worker por sí solo (no está en su propio patrón), así que hizo falta
un reinicio manual del worker para que el fix quedara activo esa vez.

### 3.30. Corrección de arquitectura: el índice se escribe AL MOMENTO de subir, no por refresco periódico (S040)

Corrige el enfoque de la propia sesión (una tarea Celery Beat que
refrescaba `_CUARENTENA` cada pocos minutos, construida y luego
descartada como mecanismo principal antes de comitear nada).

Verbatim: *"la visión del explorador de archivos es a nivel de base
de datos (...) al margen de que se suba a cuarentena, al margen de que
luego los va a clasificar Gemini, cuando hacemos la subida (...) ya
debe marcar que ese archivo está en cuarentena en la base de datos.
Entonces, cuando (...) renderizamos (...) el contenido de la carpeta
de cuarentena, ya debemos también renderizar la carpeta que haya
nueva o el archivo que haya nuevo (...) no debe de ser necesario
refrescar desde Google Cloud Storage (...) cuando se sube, realmente
se graba el archivo en GCS (...) y a la misma vez anotamos en base de
datos dónde se encuentra el archivo (...) cuando nosotros vamos a
renderizar el explorador, automáticamente nos debe de reflejar ya sin
necesidad de actualizar GCS."*

**Diseño correcto:** quien crea el objeto en GCS (el agente H28, al
subir a cuarentena) es quien debe disparar la escritura de la fila del
índice, en el mismo momento -- no un proceso aparte que vaya a
comprobar más tarde si hay algo nuevo. El agente no tiene conexión
directa a la base de datos (solo tiene la clave de la cuenta de
servicio de GCS) -- necesita un endpoint autenticado en el propio
servidor Django al que avisar justo después de cada subida con éxito.

**Construido esta sesión, lado servidor:** `RegisterUploadedObjectView`
(`POST /panel/documentacion/explorador/agente/registrar/`) -- recibe
`bucket`+`blob_name`, autenticado por token compartido
(`settings.H28_AGENT_API_TOKEN`, `constant_time_compare`), lee los
metadatos reales del blob recién subido directamente de GCS (una sola
llamada dirigida, coherente con el principio ya vigente de "GCS solo
se toca al abrir contenido", ampliado aquí a "o cuando alguien avisa
explícitamente de un objeto nuevo") y escribe la fila (más la cadena
de carpetas ancestras) al momento. `index_writer.refresh_folder()`
extraída como función reutilizable (antes vivía solo dentro del
comando `refresh_document_folder`) para no duplicar la lógica de
persistencia entre el comando, la vista y la tarea de seguridad.

**Construido esta sesión, lado agente
(`h28_migration_agent/`):** `server_notify.notify_server_of_upload()`
-- POST de mejor esfuerzo, solo librería estándar (`urllib.request`,
sin dependencia nueva, sin tocar `requirements.in` del agente),
llamado justo tras cada subida con éxito a cuarentena en los DOS
caminos reales que suben a cuarentena (`uploader.
upload_single_file_to_quarantine`, usado por el vigilante y por la
puesta al día; y `reconciler._upload_with_retries`, el camino de
reconciliación -- verificado que no había un tercero). Token leído con
el mismo patrón que la clave de cuenta de servicio: variable de
entorno primero, si no, un archivo de texto plano dentro de
`agent_data/` (nunca commiteado). Nunca fatal -- un aviso fallido no
bloquea ni revierte la subida a GCS, que sigue siendo siempre directa
(decisión 4 de S030, sin contradicción: esto es un canal de aviso
aparte, sin contenido de archivo, no una ruta de subida alternativa).

**Pendiente, fuera del alcance de esta sesión -- workflow distinto al
de este repositorio:** recompilar y desplegar el ejecutable
(PyInstaller local, no `git push` al servidor) en la máquina de Miguel
Ángel, y fijar el mismo token en `.env` del servidor
(`H28_AGENT_API_TOKEN`) y en `agent_data/server_api_token.txt` del
agente.

**Tarea Celery Beat de refresco periódico:** reencuadrada como red de
seguridad de baja frecuencia (cada hora, `refresh-quarantine-index-safety-net`
en `CELERY_BEAT_SCHEDULE`), no como mecanismo principal -- cubre el
caso de que el aviso instantáneo falle (agente caído a mitad, sin red
en ese instante, etc.).

### 3.31. Consumidor de cuarentena: identidad por DNI para personal, revisión humana ante duda (S040)

Verificado con datos reales antes de diseñar nada (18 documentos
reales de un mismo trabajador, subidos por Miguel Ángel): todos menos
uno llevan el nombre y/o DNI de la persona dentro del propio
contenido. La única excepción real (`MOD_145_GRUAS_A_ALVAREZ_2020-
ADMON.pdf`) confirma un caso "dos en uno" -- un Modelo 145 con varios
trabajadores en el mismo archivo -- exactamente el mismo patrón que
3.24 (`CE+RAE.pdf`), ahora confirmado también en personal.

Verbatim: *"eso es fundamental (...) diseñar cómo extraer el nombre
más el DNI del contenido para poder emparejar con la carpeta del
personal (...) eso forma parte de la confección de la Always-on Task,
porque es necesario."* Y, como red de seguridad: *"se clasifican
todos y los que generen alguna duda, porque no esté claro el nombre,
se clasifican y se marcan como con duda para revisión por un humano."*

**Diseño:**

1. `classify_entry()` gana un campo nuevo, `dni_hint` -- el DNI leído
   del propio documento, cuando aparezca con claridad. Más fiable que
   el nombre para emparejar: un DNI no tiene variantes de escritura
   (Hallazgo 5), un nombre sí.
2. Nuevo modelo `PersonIdentity` (DNI → carpeta real de `DOC.
   PERSONAL`, más apellido1/apellido2/nombre de referencia) --
   equivalente para personal de lo que `fleet.MachineAsset` ya es para
   máquina. Se siembra clasificando los documentos de tipo `DNI` ya
   existentes dentro de `DOC. PERSONAL` (comando de gestión nuevo,
   mismo patrón que `audit_document_names`).
3. Al clasificar un archivo de cuarentena de dominio PERSONAL: si
   `dni_hint` coincide con un `PersonIdentity` ya sembrado, se
   resuelve la carpeta con certeza -- mismo principio que 3.27 (dato
   ya conocido por otra vía prevalece sobre lo que lea Gemini caso a
   caso). Si no hay `dni_hint` legible, o no coincide con ningún
   `PersonIdentity` conocido, o coincide con más de uno (ambigüedad),
   **no se relocaliza nada** -- se clasifica igualmente (tipo
   sugerido, nombre propuesto) y queda marcado en el Historial como
   pendiente de revisión humana, nunca se fuerza un emparejamiento
   dudoso.

**Parcialmente resuelto en S041, ver 3.39 -- sigue "no resuelto" solo
para el patrón distinto que describe este punto:** el caso "dos en
uno" de tipos catalogados *distintos* (equivalente personal de
`CE+RAE.pdf`, 3.24) queda resuelto -- se detecta con `is_dossier` y
se borra directamente, sin condición previa (decisión S041, ver
3.39). El Modelo 145 con varias personas es un patrón *distinto*:
**mismo tipo catalogado, repetido para varios sujetos** -- no dispara
`is_dossier`, que exige tipos distintos. Sigue sin decisión tomada
sobre este patrón concreto, pendiente como punto 3 de la hoja de
ruta de la siguiente sesión.

**Corrección real, primera prueba controlada de `seed_person_identities`
(15 candidatos, S040):** un mismo DNI puede aparecer varias veces en
el corpus (el escaneo vigente y viejos escaneos guardados en una
subcarpeta `OBSOLETO`/`OBSOLETOS`), y `update_or_create` sobrescribía
la carpeta cada vez que encontraba otro -- si el último candidato
procesado (orden alfabético de `blob_name`) resultaba ser el obsoleto,
la identidad quedaba apuntando a la carpeta equivocada. Confirmado con
un caso real: Alberto Álvarez Díaz (`25099061N`) terminó con
`OBSOLETOS` como carpeta. Corregido: una carpeta obsoleta nunca
sobrescribe una ya buena; entre dos igual de buenas (o igual de
obsoletas), se conserva la primera encontrada.

**Hallazgo cerrado con datos reales de Miguel Ángel:** confirmado con
capturas de 5 documentos distintos de la persona (certificado PEMP,
el propio DNI escaneado, dos certificados de formación, informe de
vida laboral) que el DNI real es `24902678A` -- el documento de la
carpeta `ANAPAT` es perfectamente legible, así que **no** era un
problema de mala calidad del escaneo: Gemini simplemente leyó mal un
dígito en un documento claro. Motivó la corrección siguiente.

### 3.32. Validación de la letra de control del DNI/NIE antes de aceptar cualquier `dni_hint` (S040)

`classification_service.is_valid_spanish_dni()`: algoritmo público y
determinista del DNI/NIE español (8 dígitos, o NIE con la letra
inicial sustituida por 0/1/2, módulo 23, indexa una tabla de 23
letras) -- puramente aritmético, sin llamada de red ni a Gemini.
Verificado contra el caso real: `24902678A` pasa (letra esperada `A`),
`25902678A` no pasa (letra esperada `D`) -- el propio número delata la
lectura errónea sin necesidad de abrir el documento.

Conectado en dos sitios: `resolve_person_identity()` rechaza cualquier
`dni_hint` inválido antes de consultar `PersonIdentity` (nunca deja
que un DNI matemáticamente imposible reubique un archivo), y
`seed_person_identities` descarta el candidato antes de guardarlo en
el índice. Ningún DNI inválido puede llegar a persistirse ni a usarse
para resolver una carpeta, venga de donde venga.

### 3.33. Always-on Task real de consumo de cuarentena (H29 roadmap punto 2, S040)

Verbatim: *"es necesario empezar ya a clasificar lo que tenemos en
cuarentena, tener la Always-on Task para que ya se vea y quede
reflejado. Todo lo que haga el agente de la Always-on Task tiene que
quedar reflejado en el historial, en el mismo historial que estamos
viendo los cambios que hacemos, la clasificación, etcétera."*

`document_explorer.tasks.consume_quarantine_task` (Celery Beat, cada
10 minutos, hasta 40 archivos por pasada -- acotado, mismo motivo que
llevó `classify_entries_task` a segundo plano):

- **Dominio MÁQUINA:** si `resolve_machine_asset()` resuelve con
  certeza la máquina real a partir de la ruta reflejada dentro de
  cuarentena (el agente conserva la ruta relativa original bajo
  `_CUARENTENA/`, confirmado en `uploader.py`), el archivo se clasifica
  **y se reubica de verdad** a su carpeta real de `DOC. MAQUINAS`,
  renombrado -- reutiliza `move_service.move_entry()` tal cual (escritura
  de índice pura, `blob_name` en GCS nunca se toca). Sin máquina
  resuelta: se clasifica, nunca se reubica.
- **Dominio PERSONAL:** se clasifica siempre (tipo sugerido registrado),
  **nunca se reubica en automático todavía** -- red de seguridad
  explícita de Miguel Ángel: *"se clasifican todos y los que generen
  alguna duda (...) se marcan como con duda para revisión por un
  humano."* El emparejamiento por `PersonIdentity` (3.31/3.32) da
  nombre canónico al construir el archivo cuando se aplica desde otro
  sitio, pero esta tarea todavía no mueve nada de personal -- pendiente
  de decisión futura sobre cuándo la identidad resuelta es suficiente
  para reubicar también ahí.
- **Mismo Historial que todo lo demás** -- nuevo
  `operation_type=QUARANTINE_CONSUME` y `action=RELOCATED`, una
  `DataOperationLogEntry` por archivo según termina (mismo patrón de
  auditoría incremental de 3.28, nunca todo junto al final). Migración
  `0011` (solo cambio de `choices`, sin backfill).

**Corrección real, primera ejecución en producción del Beat:**
`consume_quarantine_task` ordenaba por `created_at`, un campo que no
existe en `DocumentIndexEntry` -- el campo real de fecha de alta en el
índice se llama `indexed_at` (`auto_now_add=True`). Detectado gracias
al panel de estado de cuarentena (3.33) y confirmado con el log real
del worker: `FieldError` en cada uno de los cinco disparos entre
05:56 y 06:30, sin efecto en el resto del worker (Celery marca la
tarea como fallida y sigue, no arrastra a las demás) ni pérdida de
datos -- simplemente ninguna pasada llegó a procesar nada hasta la
corrección. `order_by("created_at")` → `order_by("indexed_at")`.

### 3.34. Catálogo de tipos documentales gestionable desde el panel, sin tocar código (S040)

Hallazgo real de la primera pasada de `consume_quarantine_task`:
varios manuales de despiece (catálogo de piezas) de carretillas
quedaban `DESCONOCIDO` -- y por tanto sin aplicar, sin reubicar -- pese
a que la máquina se conocía con total certeza (ya vivían dentro de la
carpeta de esa carretilla en cuarentena). No era un fallo del
emparejamiento de máquina: el tipo documental "manual de despiece"
simplemente no existía en el vocabulario cerrado.

Miguel Ángel, en vez de pedir que se añadiera ese tipo a mano (lo que
sí se hizo, vía migración, y se descartó): *"no lo añadas ya, sino que
añade el sistema para que se pueda añadir el tipo (...) a nuestro
catálogo (...) con esto quiero evitar tener que tocar código para
añadir un tipo de documento al catálogo."*

**Construido:** `DocumentTypeCatalogListView`
(`/panel/documentacion/explorador/catalogo/`) -- listado con alta/baja
inline, formulario de añadir (código, nombre visible, dominio).
`code` pasa por `naming_service._sanitize_token()`, el mismo
normalizador que ya usa el motor de renombrado, así que nunca puede
entrar un código con acentos/espacios que rompería un nombre de
archivo generado. Desactivar (nunca borrar) conserva el histórico de
archivos ya renombrados con ese código, según el propio `help_text`
del campo `is_active`.

Confirmado que no hace falta ningún paso más: `classify_entry()`'s
`_build_prompt()` ya lee `DocumentTypeCatalog.objects.filter(
is_active=True)` en vivo en cada llamada -- una fila añadida aquí está
disponible para la siguiente clasificación real sin desplegar nada.

**Corrección real, primera pasada real observada por Miguel Ángel:**
el panel de estado de cuarentena (3.33) mostraba "0 archivo(s)
procesado(s)" para una pasada `en curso` que el propio detalle de esa
misma operación ya mostraba con 25 procesados -- discrepancia real
entre dos pantallas del mismo dato. Causa: `QuarantineStatusView` leía
`groups_count`/`kept_count`/`trashed_count` directamente del
`DataOperationLog`, campos que solo se cierran al terminar la tarea
(mismo patrón exacto ya corregido para el detalle en 3.28). Corregido:
mientras `status != COMPLETED`, los tres se calculan contando las
`DataOperationLogEntry` reales que ya existen, igual que ya hacía
`DataOperationLogDetailView`.

### 3.35. Archivos grandes (>100 MB) fallaban en Gemini: `Part.from_uri` en vez de descargar y empaquetar (S040)

Hallazgo real de la primera pasada de `consume_quarantine_task`: siete
catálogos de piezas reales (plataformas Genie/JLG, 150-270 MB) fallaban
siempre con el mismo `400 INVALID_ARGUMENT` en crudo de Vertex AI.

Verificado online contra la documentación real de Gemini (2026-08-04,
nunca de memoria): el límite de payload en línea (`Part.from_bytes`,
lo que usaba `classify_entry()`) es de 100 MB -- muy por debajo del
tamaño real de estos archivos.

**Corregido:** para los tipos que Gemini ya acepta de forma nativa
(PDF, imágenes), `classify_entry()` ya no descarga el objeto en
absoluto -- le pasa a Gemini una referencia `gs://` directa
(`Part.from_uri`, confirmado soportado en Vertex AI sin techo de
tamaño de payload en línea, porque el objeto se lee directamente de
GCS en vez de viajar dentro de la petición). Efecto secundario
positivo: también deja de descargar bytes al servidor para este
camino, no solo arregla el límite. Los documentos de Office (que
necesitan LibreOffice, y por tanto una descarga real para poder
convertirlos) siguen igual que antes.

### 3.36. Pasadas de cuarentena huérfanas se cierran solas al arrancar la siguiente (S040)

Hallazgo real: varias pasadas de `consume_quarantine_task` quedaron
en `RUNNING` para siempre en el panel de estado (3.33), pese a tener
líneas reales escritas (registro incremental de 3.28 funcionando
bien). Confirmado con datos reales que **no era un cuelgue de
verdad**: cada una se paró justo en el momento de un reinicio del
worker Celery por un despliegue -- con tantos desplegados seguidos en
esta misma sesión, varias pasadas automáticas coincidieron con un
reinicio a mitad de trabajo. El proceso muere en seco y nunca llega
al bloque `except` propio, así que la fila del log se queda huérfana
sin que nada la cierre.

**Corregido:** al arrancar, `consume_quarantine_task` busca cualquier
`DataOperationLog` de `QUARANTINE_CONSUME` que siga en `RUNNING` y lo
cierra como `FAILED` con una nota en el log del servidor -- con
`concurrency=1` y un solo disparo por intervalo del Beat, cualquier
`RUNNING` que exista al empezar una pasada nueva solo puede ser
exactamente eso, huérfana de un reinicio anterior. Nunca se deja
acumulando confusión en el panel de estado.

### 3.37. Límite real de Vertex AI para PDF (50 MB), incluso por `gs://`: recorte a las primeras páginas (S040)

El arreglo 3.35 (`Part.from_uri`) mejoró el error pero no lo resolvió
del todo -- Vertex AI devolvió, ya con detalle real (no supuesto),
el motivo exacto: *"The file size of `gs://...` is 90015260, which
exceeds max allowed file size of 52428800 for `application/pdf`
files."* 52428800 bytes = 50 MiB -- un límite específico de PDF,
distinto del límite genérico de payload en línea, y que aplica
también por referencia `gs://`, no solo al empaquetar bytes.

Miguel Ángel, ante la propuesta de convertir a otro formato: *"¿sería
conveniente convertirlos a otro tipo de archivo (...)? O simplemente
enviamos dos o tres páginas de PDF."* Confirmado que convertir de
formato no ayuda (el límite es de cómo Vertex AI procesa PDF en
concreto, no del formato del archivo) -- y clasificar solo necesita
reconocer el tipo de documento, no transcribirlo entero, así que las
primeras páginas bastan casi siempre.

**Construido:** `_extract_first_pages_pdf()`, con PyMuPDF (`fitz`, ya
dependencia del proyecto -- sin paquete nuevo, sin coordinación de
`pip-compile`/`pip-sync`). Cuando `entry.size_bytes` (ya en el índice,
sin descargar de más para decidir) supera 45 MB, se descarga el
archivo, se extraen las 3 primeras páginas a un PDF nuevo en memoria,
y ese extracto -- nunca el archivo completo -- es lo que se envía a
Gemini. Probado con un PDF real de prueba antes de comitear.

### 3.38. Bug real, con coste: "en cola" filtraba por la ruta real de GCS, no por la ubicación virtual -- reprocesaba archivos ya reubicados

Miguel Ángel, verbatim: *"esos 707 en cola, qué quiere decir? Porque
ahí lleva ya un rato con 707 y no baja."* Correcto -- el contador
nunca bajaba de verdad pese a decenas de pasadas reubicando archivos.

**Causa raíz, doble, en dos sitios distintos:** tanto
`QuarantineStatusView` (el conteo de "en cola") como
`consume_quarantine_task` (qué archivos elige procesar cada pasada)
filtraban por `blob_name__startswith=QUARANTINE_PREFIX` -- la ruta
REAL en GCS, que por diseño (3.19, virtual filesystem) **nunca
cambia** al reubicar un archivo, solo cambia `parent_path` (la
ubicación virtual). Consecuencia real, no solo cosmética: la propia
tarea automática podía volver a elegir un archivo YA reubicado (su
`blob_name` seguía empezando por `_CUARENTENA/` aunque su
`parent_path` ya fuera `DOC. MAQUINAS/...`), lanzar una llamada real a
Gemini para clasificarlo otra vez, y solo `move_service.move_entry()`
evitaba el daño real (retorno temprano si el destino ya coincide) --
pero el gasto de la llamada ya se había hecho.

**Corregido en los dos sitios:** `parent_path__startswith=
QUARANTINE_PREFIX` en vez de `blob_name__startswith=...` -- "sigue en
cuarentena" se decide por dónde vive el archivo AHORA (virtual), nunca
por dónde se subió originalmente en GCS (real, congelado para
siempre).

### 3.39. Consumidor de cuarentena: reubicación real de PERSONAL por DNI, y borrado directo de dosieres ciertos (S041)

Dos decisiones distintas de la misma sesión, ambas registradas
literalmente (directriz 4.8), que juntas cierran los dos puntos que
3.24 y 3.31 dejaban "no resuelto por interpretación propia".

**1. PERSONAL deja de ser "solo clasifica, nunca reubica".** Hasta
S040, `apply_quarantine_classification()` reubicaba MÁQUINA con
certeza (3.27) pero para PERSONAL solo clasificaba, nunca escribía
`parent_path` -- red de seguridad explícita de S040 (3.31). Miguel
Ángel, S041, tras confirmar que la clasificación viene siendo
correcta y que se trabaja sobre una copia de la realidad de
Microsoft 365 (riesgo bajo): *"el sistema clasifica bien (...) vamos
a hacer ya los movimientos de manera real [en base de datos] (...)
vamos a ver los resultados y si hay que cambiar algo, se cambia."*
Implementado con el mismo principio de certeza que ya regía para
MÁQUINA: `resolve_person_identity(dni_hint)` -- coincidencia exacta
de DNI contra `PersonIdentity` ya sembrado -- resuelve
`PersonIdentity.folder_path` como `parent_path` nuevo. Sin identidad
resuelta, sigue exactamente el fallback de antes: clasificado, sin
mover, marcado para revisión humana.

**2. Dosieres ciertos: nuevo campo `is_dossier`, borrado directo a
papelera del administrador.** Resuelve el punto "no resuelto" de 3.24
(detección de dosier) y sustituye por completo su condición previa de
borrado (ver el bloque "RESUELTO EN S041" añadido dentro de la propia
3.24, no repetido aquí). Origen: captura real de Miguel Ángel con 5
archivos MÁQUINA en curso de clasificación, todos `DESCONOCIDO` por
ser compilaciones reales (ITV+permiso de circulación+seguro+
autorización en un mismo PDF) -- "habría que marcarlos para que no
aparezcan en el listado (...) marcarlos como eliminados."

**Diseño, con el criterio de certeza explícito de Miguel Ángel:**
*"cuando tenemos la seguridad de que es un dossier (...) cuando
estamos viendo que tiene una tarjeta de inspección técnica y tiene un
permiso de circulación, o tiene un DNI más un curso, o tiene un DNI
más permiso de conducción. Cuando son varios documentos, eso es un
dossier."* Explícitamente **no** vale la simple imposibilidad de
identificar un único documento: *"no podemos eliminar documentos que
sean desconocidos simplemente por el hecho de que sean desconocidos y
no estén integrados en un tipo de documento."* Ni el número de
páginas es el criterio (dicho literalmente al hilo de un ejemplo de
tres vs. cinco páginas).

- `_RESPONSE_SCHEMA`/`_PROMPT_TEMPLATE`: campo booleano `is_dossier`
  nuevo, con instrucción explícita de solo marcarlo `true` ante
  certeza real de dos o más tipos catalogados distintos.
- `trash_dossier_entry()` / `_resolve_dossier_trash_user()`: borrado
  lógico (`deleted_at`/`deleted_by`) a la papelera de
  `alvarez_admin` (pk=1, único `CompanyUser` real confirmado por
  Miguel Ángel con captura de pantalla -- cuenta compartida del
  departamento de administración, no personal, pero es la que
  indicó). `blob_name` en GCS nunca se toca. Si esa cuenta no se
  puede resolver, no se elimina nada -- nunca un `deleted_by` nulo/
  huérfano e irrecuperable desde ninguna papelera del panel.
- `apply_quarantine_classification()`: intercepta antes de cualquier
  ramificación por dominio -- aplica igual a MÁQUINA y PERSONAL.
- `consume_quarantine_task()`: nueva acción `ACTION_TRASHED` (ya
  existía en el modelo, sin usar hasta ahora en esta operación), con
  contador propio `DataOperationLog.dossier_trashed_count` --
  deliberadamente separado de `trashed_count`, que en esta operación
  sigue significando "clasificado, pendiente de revisión humana", no
  "eliminado".
- **Alcance:** solo `consume_quarantine_task` (Always-on Task). La
  clasificación manual por lote (`classify_entries_task`,
  `BATCH_CLASSIFICATION`) usa `apply_classification()`, función
  distinta, no se ve afectada.

**Bug real encontrado y corregido de paso, mismo bloque:** la cabecera
de texto de `operation_log_detail.html` ("arriba la copia que se
conservó... comparten tamaño y CRC32C") estaba fija para las tres
`operation_type` posibles, describiendo solo resolución de duplicados
-- se veía también, incorrecta, en una operación `QUARANTINE_CONSUME`
real (captura de Miguel Ángel). Corregido con `DataOperationLog.
intro_note`, contextual por tipo de operación, mismo patrón ya
existente de `primary_count_label`/`secondary_count_label`.

**Residual, no resuelto, distinto del caso ya cerrado:** el "dos en
uno" del **mismo tipo repetido para varias personas** (Modelo 145 con
varios trabajadores, 3.31) no dispara `is_dossier` -- ese campo exige
tipos catalogados *distintos*, no el mismo tipo repetido. Sigue sin
decisión tomada, ver punto 3 de la hoja de ruta de la siguiente
sesión.

**Bug real encontrado y corregido de paso, mismo bloque (directriz
4.9):** archivos MÁQUINA correctamente tipificados por Gemini (p. ej.
tres manuales de despiece reales, `MANUAL_DESPIECE`) se quedaban
`Sin aplicar` para siempre, nunca se reubicaban -- reportado por
Miguel Ángel al ver los grupos 6-8 de una clasificación en curso.
Causa: `resolve_machine_asset()` probaba el código de flota anclado
al **segmento de carpeta completo** (`_FOLDER_MACHINE_CODE_RE.match()`
sobre el segmento entero). Carpetas tipo `P-14 3232-DLM (TR)`
funcionan (código primero), pero las de carretillas/dumpers escriben
antes una palabra descriptiva (`CARRETILLA T13 - E-1364-BFL`,
`DUMPER T27 E-9982-BHD`) -- el regex nunca llegaba a probar `T13`/
`T27`, y ni la reubicación ni `check_machine_mismatch` (misma función
compartida) funcionaban para esas máquinas. Corregido: se prueba
cada palabra de cada segmento, no el segmento completo -- un token
que solo parece un código (una matrícula) pero no coincide con
ningún `MachineAsset` real es inofensivo, la búsqueda simplemente
continúa. Verificado con simulación de las 5 rutas reales de la
sesión antes de comitear.

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

## 6.1. Nota de desvío — sesión invasora en paralelo (2026-08-04)

Ver directriz 4.11 del documento maestro para el patrón general de
"sesión invasora". Esta nota es puramente informativa -- **no toca la
hoja de ruta de la sección 7**, que sigue siendo la que deje escrita
la sesión principal sobre H29.

Mientras H29 seguía `EN PROGRESO` en otra sesión trabajando en
paralelo sobre el explorador, esta sesión (desvío tipo Caso A del
enrutador de anexos) trabajó sobre H10 (Albaranes de Proveedores),
sin modificar código de H29. Detalle completo del trabajo realizado
en `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`, sección 5: prompt de
albaranes más permisivo (marca manuscrita, commit `e3c065b`) y
albarán de abono a proveedor (commit `af2d6b9`), resolviendo además
un pendiente anotado desde S028.

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

### COMPLETADAS EN S038

Sesión de 13 commits, 7 archivos tocados (458 inserciones, 25
eliminaciones). Empezó como continuación de la hoja de ruta de S037 y
acabó incluyendo una incidencia real de producción y una skill nueva
de plataforma.

**Incidencia real de producción, corregida en la misma sesión**
(directriz 4.9, fuera de H29): Pablo no podía cerrar un parte con la
máquina `A59` — "no existe" pese a estar en BD, activa y visible en el
desplegable. Causa raíz confirmada con datos reales: `brand_model`
vacío rompía la extracción de código de la Pasada 3 en
`_parse_entry_lines_from_post` (exigía `\s+` tras el guion, nunca
casaba sin texto detrás). Bug genérico, no exclusivo de A59. Corregido
(`fdc546e`, `\s+` → `\s*`) y verificado con los cuatro casos reales
antes de comitear; `brand_model` de A59 relleno con dato provisional
(`"LIEBHERR LTM 1230-5.1"`) por instrucción explícita de Miguel Ángel,
a la espera del dato definitivo de H28.

**Punto 4 de la hoja de ruta de S037 resuelto:** permisos de
`enterprisebot-vertex@` verificados con datos reales
(`roles/storage.admin` a nivel de proyecto, incluye `storage.folders.*`
completo) — la Fase 2 de H28 ya tiene lo que necesita, sin conceder
nada nuevo.

**Punto 1 (auditoría de coherencia) resuelto con alcance reducido:**
tras leer `purge_orphaned_gcs_blobs.py` y `seed_document_index.py`, se
detectó que solo faltaba una dirección real de comprobación —
`find_orphaned_index_entries` (commit `c6fbb59`), que audita filas
vivas del índice sin blob real en GCS. Ejecutado contra los cinco
cubos reales: 0 huérfanas.

**Consolidación de cubos (decisión verbatim de Miguel Ángel, anexo
3.12):** los cubos `enterprisebot-alvarez-machine-documents` (29
objetos) y `enterprisebot-alvarez-personnel-documents` (39 objetos) se
borraron por completo de GCS (`gcloud storage rm --recursive`,
ejecutado por Miguel Ángel, confirmado con salida real) — su contenido
ya vivía duplicado en `cgs_grupo_alvarez` desde la migración de H28.
Las apps `machine_documents`/`personal_documents` en sí NO se tocaron
(retirada de código pendiente). El explorador se actualizó para
reflejarlo: `INDEXED_BUCKETS` ya no incluye esos dos cubos, y las tres
pestañas restantes muestran nombre en castellano (`Fotos Partes`,
`Fotos Albaranes`, `Directorio Principal`) vía un nuevo
`BUCKET_DISPLAY_NAMES` en `buckets.py`, con la lógica de mapeo en la
vista (`bucket_tabs()`, `build_breadcrumbs()`), nunca en la plantilla.

**Nueva skill de plataforma, fuera del repositorio del proyecto:**
`com-gcloud-windows`, tras verificar en línea que el entorno real de
Miguel Ángel es el SDK de Google Cloud instalado en local sobre
Windows (nunca Cloud Shell del navegador). Documenta el patrón de
bucle sin archivo en PowerShell (evita el problema de `%%` de
`cmd.exe`), el patrón de script de una sola caja con here-string, la
corrección de política de ejecución (`Set-ExecutionPolicy -Scope
CurrentUser RemoteSigned`, ya aplicada y verificada), y las trampas de
sintaxis de `gcloud storage buckets get-iam-policy` ya conocidas.

**Desvíos de la sesión:** dos vueltas evitables por no verificar el
entorno real antes de generar comandos (sintaxis bash entregada para
un entorno que resultó ser `cmd.exe`, y luego Notepad innecesario para
comandos sueltos sin bucle) — ambas corregidas dentro de la propia
sesión y documentadas en `SESSION_VARIABLES.md` y la skill nueva para
no repetirse.

### COMPLETADAS EN S039

Sesión larga, dedicada en su mayor parte al punto 1 de la hoja de ruta
de S038 (funcionalidad avanzada del panel del explorador) y, dentro de
ella, a construir y **reconstruir cuatro veces** la herramienta de
mover archivos hasta dar con el diseño correcto — el desarrollo más
extenso de toda la sesión y el que más aprendizajes de fondo dejó.

**1. Funcionalidad avanzada del explorador** (commits `3fb8af1`,
`4254aad`, `37d3af4`): columnas ordenables (nombre/tamaño/fecha, con
carpetas siempre primero — decisión explícita de Miguel Ángel, "como
en el Explorador de Windows"), tres alcances de búsqueda (`here`,
`here_recursive`, `global`), filtros por extensión y por bandera
`exists_in_local`, y diseño responsivo real (scroll horizontal en
móvil, corregido tras feedback directo de Miguel Ángel viendo la
interfaz rota en su teléfono — la primera versión ocultaba columnas
por debajo de `md`, dejándolo sin forma de llegar a ellas). Dos
incidentes de producción reales corregidos en el camino: un 500 en
todos los cubos por `Coalesce(gcs_updated_at, Value)` sin
`output_field` explícito en MySQL, y el propio bug de scroll móvil.

**2. Auditoría de vocabulario documental y duplicados**
(`audit_document_names`, `find_duplicate_documents` — commits
`1cc76b8`, `a95807f`, `49c8ba9`, `145721c`, `11b4398`, `6269df0`):
comandos de gestión sobre el corpus ya indexado (sin barrer GCS de
nuevo). Vocabulario parcialmente cerrado con datos reales (EPIS, RM,
IDC, ALTA/BAJA, NOMINA vs. PAGO CORRIENTE, CARNET_CONDUCIR,
AUT_TEMP_CONDUCIR, ITV, REV_TACOGRAFO, MANUAL_USO/MANUAL_DE_
INSTRUCCIONES compartidos por modelo de máquina, entre otros).
Duplicados exactos por `(crc32c, size_bytes)`: 2,7 GB recuperables en
3.541 grupos. Corregido un falso positivo real en variantes de
compresión: sufijos `(001)`/`(002)`/`(004)` de un libro de familia
escaneado son numeración de página, no compresión — retirado del
patrón automático.

**3. Unificación visual del árbol del explorador** (commit `4d47c68`):
decisión verbatim de Miguel Ángel — "nadie tiene por qué saber que son
cubos diferentes... por construcción no vamos a cambiar la
construcción". Las pestañas de cubo desaparecen; Fotos Partes, Fotos
Albaranes y Cuarentena pasan a mostrarse como subcarpetas normales de
un único `Directorio Principal`, vía filas sintéticas
(`VirtualBucketFolder`) inyectadas solo en la raíz.

**4. Búsqueda "Todo el cubo" pasa a buscar en los tres cubos reales**
(commit `4b62627`): con el árbol unificado, una búsqueda desde la raíz
que solo mirara el cubo histórico se perdería en silencio cualquier
cosa en Fotos Partes/Fotos Albaranes — justo el problema que Miguel
Ángel señaló probándolo ("vas a buscar un parte y no te lo va a
encontrar"). Descartada la alternativa de fusionar físicamente los
cubos (también planteada por Miguel Ángel): el campo `id` de
`DocumentIndexEntry` es único en toda la tabla, no por cubo, así que
la paginación por cursor sigue siendo correcta buscando en varios
cubos a la vez sin tocar la infraestructura de GCS.

**5. Nombres amigables para albaranes y fotos de tarea** (commit
`d5f90d1`, `document_explorer/friendly_names.py` nuevo): decisión
verbatim de Miguel Ángel viendo nombres de cámara opacos en
producción — "esto realmente no es un explorador de archivos, es a
base de base de datos, podemos presentar lo que queramos". Resuelto en
bloque (una consulta por modelo de dominio y página, nunca fila a
fila) para no reintroducir el N+1 que el propio `domain_object` ya
advertía evitar.

**6. Herramienta de mover archivos — cuatro iteraciones completas,**
todas con Miguel Ángel probando en producción real y corrigiendo el
rumbo con datos, no con suposiciones:

- **v1 (commit `13d3974` y siguientes hasta `23dd04c`):** copia física
  en GCS (`gcs_service.move_file`, copy+delete real), modal con árbol
  navegable y "crear carpeta aquí" (sin escribir rutas a mano — primer
  feedback: "parece que estamos trabajando desde consola"), selección
  múltiple con "mover todos los manuales" reutilizando la búsqueda
  recursiva ya existente, y colisión de nombre resuelta con
  numeración correlativa automática (nunca cancelar el lote ni
  preguntar uno a uno — decisión explícita ante el caso real de cinco
  `MANUAL DEL OPERADOR.pdf` distintos con el mismo nombre genérico).
  Dos salvaguardas fijadas como **permanentes**, no de v1: mover
  restringido para siempre a administrador únicamente (ni el jefe de
  Miguel Ángel), y acotado para siempre al cubo histórico real — Fotos
  Partes/Fotos Albaranes son inamovibles, ni como origen ni como
  destino.
- **v2 — rediseño a puntero puro (commit `c1cb827`):** fallo de diseño
  real señalado por Miguel Ángel tras ver el coste de mover un manual
  de 400 MB sin barra de progreso: *"deberíamos de haberlo hecho casi
  a nivel de base de datos y no mover archivos realmente... si
  movemos, movemos punteros"* (su propia analogía: la pista de
  directorio de un disquete frente a la pista de datos).
  `move_service.move_entry()` deja de tocar GCS por completo —
  `blob_name` (la ruta real y permanente) nunca vuelve a escribirse;
  solo cambia `parent_path`/`name` (la ubicación virtual). La
  navegación normal (`scope=here`) ya funcionaba así sin querer desde
  el primer día de H29; hubo que corregir la búsqueda recursiva y el
  acotado de permisos, que sí usaban `blob_name` como si fuera la
  ubicación real (`_virtual_descendant_q`, con reparto por tipo de
  entrada: archivos por `parent_path`, carpetas —que nunca se mueven—
  por `blob_name`).
- **v3 — barra de progreso, luego retirada (commits `de5b84f`,
  `20ccf3e`, `d844bb0`):** petición explícita de Miguel Ángel de no
  quedar "a ciegas" mientras mueve un lote grande. Primero archivo a
  archivo (`MoveOneView`), medido en producción en ~197 segundos para
  197 archivos — diagnóstico correcto de Miguel Ángel confirmado con
  el `response-time` real del log de acceso: ~350-420 ms de servidor
  por archivo más el viaje de red completo repetido 197 veces. Luego
  en bloques de 15 (`MoveBatchView`), mejor pero "seguía tardando
  bastante". Miguel Ángel decidió entonces renunciar del todo a la
  visibilidad en vivo a cambio de velocidad — *"que le den a la
  visibilidad... como mucho un spinner"* — vuelta a una única petición
  con spinner en el propio botón, sin AJAX ni JSON.
- **v4 — consultas agrupadas para el lote entero (commits `c1be2bd`,
  `a20cb4d`):** incluso en una sola petición, 190 archivos tardaban
  ~75 segundos — la causa real ya no era la red, era que
  `move_entry()` seguía haciendo ~6 consultas separadas por archivo.
  Nueva `move_service.move_entries()`: resuelve colisiones del lote
  entero con una sola consulta de lectura (ampliada en memoria para
  que dos archivos del mismo lote que choquen entre sí también se
  numeren bien), un único `bulk_update()` para todas las filas
  movidas, y un único `UPDATE ... CASE WHEN` por campo
  (`total_size_bytes`, `child_count`) cubriendo todas las carpetas
  distintas que toca el lote — en vez de una `UPDATE` por carpeta y
  por archivo. Verificado con una simulación local (sin base de
  datos) antes de desplegar, contra un caso con colisiones dentro del
  mismo lote, colisión con lo ya existente, y una carpeta ancestro
  compartida por origen y destino. Un `FieldError` real de Django
  (`Case`/`When` mezclando `IntegerField` con `BigIntegerField` al
  combinar `F(field) + delta`) apareció en el primer despliegue y se
  corrigió pasando el campo real del modelo como `output_field`
  explícito. **Resultado final, confirmado por Miguel Ángel: de 75
  segundos a ~2.**

**Incidencia real corregida fuera de alcance, según directriz 4.9:**
ninguna detectada esta sesión más allá de las ya resueltas dentro del
propio desarrollo de la herramienta de mover.

**Limitación conocida, documentada, no bloqueante:** una carpeta
vaciada al mover todo su contenido fuera queda como fila huérfana en
el índice (`child_count=0`, sin borrarse) — candidata a una futura
herramienta de "carpetas vacías".

### COMPLETADAS EN S040

Sesión larguísima -- 46 commits propios en el rango, la mayor parte
del H29 real: primera versión funcional completa del motor de
clasificación con Gemini, probada de verdad contra el corpus real en
varios lotes controlados, con una decena larga de bugs reales
encontrados y corregidos sobre la marcha (nunca supuestos). Trabajo en
paralelo, sin choque, de otra sesión sobre H10 (albaranes de
proveedor) -- solo tocó `spare_parts/`, tres mezclas limpias durante
la sesión.

**1. Motor de clasificación con Gemini, primera versión real
funcionando** (`b7207bb`, `6dd5fb2`, `ec71779` y siguientes):
`DocumentTypeCatalog` (vocabulario cerrado, 24 tipos MÁQUINA + 12
PERSONAL, extensible), `naming_service` (formato fijo por dominio,
ordinal propio para colisiones), `classification_service.classify_entry()`
+ `apply_classification()`. `ClassifyView` conectado a la interfaz.
Primera prueba controlada (21 archivos reales de una máquina) encontró
y corrigió en el momento: colisión de nombre resuelta con el sufijo
" (N)" equivocado (de la herramienta de mover) en vez del ordinal
"_N" propio; `.docx` rechazado por Gemini sin conversión; prompt
confundiendo el modelo del fabricante con el código de flota interno
(confirmado con las imágenes reales que subió Miguel Ángel); la
Tarjeta ITV mal entendida como "dos documentos en uno" cuando en
realidad es un único documento por diseño (corregido tras explicación
directa de Miguel Ángel). Decisión de diseño registrada y sin
resolver todavía: archivos "dos en uno" de verdad (`CE+RAE.pdf`, un
Modelo 145 con varios trabajadores) deben desdoblarse en documentos
únicos -- pendiente de decidir cómo partir un PDF sin salirse del
principio de que clasificar nunca toca GCS.

**2. Aviso de máquina equivocada por marca/modelo** (`ada3ffc`):
`fleet.MachineAsset` como fuente de verdad para el código de flota
real (prevalece siempre sobre lo que lea Gemini en el documento,
`05ab8e3`) y para detectar cuándo un documento de una marca/modelo
distinta aparece archivado en la carpeta de otra máquina.

**3. Clasificación pasa a Celery -- incidente real de producción**
(`68c15c3`): un lote recursivo real reventó el balanceador de
PythonAnywhere (504) al encadenar llamadas a Gemini dentro de una
petición HTTP síncrona. Movido al mismo mecanismo de tarea en segundo
plano ya probado en el proyecto. El mismo incidente expuso un segundo
problema real: el registro de auditoría solo se escribía al final del
lote -- corregido a registro incremental, una línea por archivo según
termina, para que un fallo a mitad nunca pierda el rastro de lo ya
hecho. `deploy.yml` no reiniciaba el worker Celery ante cambios en
`document_explorer/` (mismo patrón exacto que el incidente S025 con
`document_management/`) -- corregido y documentado en el propio
workflow (`3b4b9f2`).

**4. Conversión de Office a PDF con LibreOffice** (`c5666b2`): sin
dependencia Python nueva (`subprocess`, biblioteca estándar).
Verificado que `soffice` está instalado en el servidor antes de
escribir nada.

**5. Corrección de arquitectura: el índice se escribe al momento de
subir, no por refresco periódico** (`d8f499e`, la más grande de la
sesión): Miguel Ángel corrigió el enfoque inicial (una tarea Celery
Beat de refresco periódico) -- el explorador es una vista de base de
datos, nunca debe depender de sondear GCS. `RegisterUploadedObjectView`
(webhook autenticado por token compartido) escrito en el servidor;
`h28_migration_agent/server_notify.py` (solo librería estándar,
`urllib`) avisa al servidor justo tras cada subida con éxito a
cuarentena, en los dos caminos reales del agente
(`uploader.upload_single_file_to_quarantine` y
`reconciler._upload_with_retries`). No contradice la decisión 4 de
S030 (subida directa a GCS) -- es un canal de aviso aparte, sin
contenido de archivo. Probado en producción de principio a fin con la
ayuda de Miguel Ángel (compilación del agente en su máquina Windows
incluida, con varios contratiempos reales resueltos sobre la marcha:
carpeta equivocada para el token, extensión `.txt.txt` oculta).
Refresco periódico reencuadrado como red de seguridad de baja
frecuencia, no como mecanismo principal.

**6. Identidad de personal por DNI** (`673a1a9`, `329f84b`):
`PersonIdentity` (DNI → carpeta real de `DOC. PERSONAL`), sembrado con
`seed_person_identities` (filtro barato por nombre de archivo +
confirmación real con Gemini, nunca por el nombre a ciegas -- Hallazgo
5 del anexo H28: el mismo nombre escrito de ocho formas). Corregido un
bug real de la primera siembra (una carpeta `OBSOLETO` sobrescribía la
carpeta buena ya guardada). `is_valid_spanish_dni()`: algoritmo real y
público de la letra de control del DNI/NIE, puramente aritmético --
detectó gratis una lectura errónea de Gemini en un documento
perfectamente legible, confirmado con capturas reales de Miguel Ángel
de cinco documentos distintos de la misma persona.

**7. Always-on Task real de consumo de cuarentena** (`f5bb21c` y
siguientes, punto 2 de la hoja de ruta de H29 desde hace varias
sesiones): MÁQUINA se reubica de verdad cuando se resuelve con
certeza (vía `resolve_machine_asset` sobre la ruta ya reflejada dentro
de cuarentena); PERSONAL se clasifica siempre pero nunca se reubica en
automático todavía -- red de seguridad explícita de Miguel Ángel
("clasificar todo, marcar con duda para revisión humana"). Mismo
Historial que el resto de operaciones masivas. Cadena de incidentes
reales en producción, cada uno diagnosticado con datos del servidor
antes de corregir, nunca supuesto: campo `created_at` inexistente
(el real es `indexed_at`); límite real de Vertex AI de 100 MB en línea
(`Part.from_uri` en vez de descargar y empaquetar) y, más específico
todavía, 50 MB exactos solo para PDF (confirmado por el propio mensaje
de error de la API) -- resuelto recortando a las 3 primeras páginas
con PyMuPDF (ya dependencia del proyecto) cuando hace falta, decisión
tomada junto con Miguel Ángel tras descartar convertir de formato;
pasadas huérfanas por reinicios del worker a mitad de tarea (varios
despliegues seguidos en la misma sesión) que se cierran solas al
arrancar la siguiente; y, el más caro de corregir, el filtro de "sigue
en cuarentena" comparaba contra `blob_name` (la ruta real en GCS, que
nunca cambia por diseño) en vez de `parent_path` (la ubicación
virtual) -- la propia tarea automática podía reprocesar con Gemini,
de verdad, archivos ya reubicados, detectado por Miguel Ángel al ver
que el contador de "en cola" nunca bajaba.

**8. Panel de estado de cuarentena y catálogo de tipos gestionable
desde el panel** (`595714a`, `fb20efe`): Miguel Ángel -- "no tenemos
ningún visor del trabajo del worker" -- pantalla con la cola en vivo y
el resumen de la última pasada. Catálogo de tipos con alta/baja desde
la interfaz, sin desplegar código -- motivado por un hallazgo real
(manuales de despiece de carretillas sin clasificar pese a que la
máquina se conocía con certeza, por faltar el tipo en el vocabulario).

### COMPLETADAS EN S041

Sesión también larguísima -- 15 commits, casi todo H29, sobre el
consumo real de cuarentena en producción. Patrón que se repite todo
el día: cada decisión de diseño se registró verbatim antes de tocar
código (directriz 4.8), y cada hallazgo raro se persiguió con datos
reales del servidor hasta la causa, nunca supuesto (directriz 4.9) --
el hallazgo más caro del día (`persist_rows`) solo salió a la luz
así. Token de GitHub caducado a media sesión, sustituido por uno
nuevo sin incidencias.

**1. PERSONAL pasa a reubicarse de verdad por DNI** (`e039c8a`):
hasta ahora solo se clasificaba, nunca se movía (punto 1 de la hoja
de ruta de S040). Miguel Ángel, con la clasificación ya funcionando
bien y trabajando sobre copia de la realidad de Microsoft 365 (riesgo
bajo): "vamos a hacer ya los movimientos de manera real [en base de
datos]". Mismo mecanismo de certeza que ya regía para MÁQUINA
(`resolve_person_identity`, coincidencia exacta de DNI).

**2. Dosieres ciertos: detección y borrado directo** (`c5042d1`,
`1e27d8a`): campo nuevo `is_dossier` en la respuesta de Gemini, con
instrucción explícita de solo marcarlo `true` ante certeza real de
varios documentos catalogados distintos combinados en un mismo
archivo (nunca por simple `DESCONOCIDO` sin identificar). Cuando hay
certeza, se reubica directamente a la papelera del administrador
(`alvarez_admin`, pk=1, único `CompanyUser` confirmado por Miguel
Ángel con captura real). Esto **sustituye por completo** la condición
previa registrada en S040 (3.24: "nunca se borra un combinado sin que
cada componente exista ya por separado") -- retirada expresamente por
Miguel Ángel: "presumimos que todos los documentos que lo conforman
existen". De paso, corregido un bug real de interfaz: el texto de
cabecera de `operation_log_detail.html` era fijo de resolución de
duplicados y se mostraba también, incorrecto, en operaciones de
clasificación/cuarentena (`d35d72a`).

**3. `resolve_machine_asset` no encontraba el código si no era la
primera palabra de la carpeta** (`82138fe`, `15d6b18`): bug real
reportado por Miguel Ángel -- manuales de despiece correctamente
tipificados se quedaban `Sin aplicar` para siempre. Carpetas tipo
`P-14 3232-DLM (TR)` funcionan (código primero), pero
`CARRETILLA T13 - E-1364-BFL` no (palabra descriptiva antes). Se
prueba cada palabra de cada segmento, no el segmento completo.

**4. Auditoría de manuales por modelo real del fabricante**
(`80d087d`, `a43db18`, `2cff0e8`): primer paso de "un solo manual por
modelo real de máquina" -- comando de solo lectura
`audit_manual_models`, compara el modelo que dice cada manual (Gemini,
primeras páginas) contra el `brand_model` de la máquina de origen en
`fleet.MachineAsset` (resuelta por carpeta o, en su defecto, por
nombre de archivo). Dos corridas reales sobre 219 candidatos: 34
discrepancias reales encontradas (algunas correcciones de dato claras,
otras ambigüedad chasis/brazo de grúa, otras sospecha de falso
positivo del propio comando con denominaciones comerciales tipo
Snorkel). Descubierta de paso una segunda jerarquía de manuales en
paralelo a "MANUALES DE USO" (la antigua "MANUAL DE INSTRUCCIONES/
{CODIGO}/..."), y corregido el ámbito de búsqueda tras encontrar 120
archivos de `DOC. PERSONAL/ENTREGA MANUAL COMBUSTIBLE` colándose por
error (nada que ver con manuales de máquina).

**5. Bug CRÍTICO: `persist_rows()` deshacía en silencio cualquier
reubicación/renombrado virtual al reindexar** (`e27fd6a`, directriz
4.12 en `c8720f3`): el hallazgo más importante del día. Un archivo de
cuarentena llevaba 29 `ACTION_RELOCATED` correctos en 26h sin que la
cola bajara nunca -- `refresh_quarantine_index_task` (cada hora)
recalculaba `parent_path`/`name` desde `blob_name` (inmutable por
diseño) también para filas YA EXISTENTES, deshaciendo cualquier
reubicación hecha después de la última vez que se indexaron. Corregido
excluyendo esos tres campos de la actualización de una fila existente
de forma permanente, no solo para este llamador. Elevado a directriz
vinculante para todo el proyecto (4.12): `blob_name` inmutable, solo
un borrado real por el administrador termina la existencia de un
objeto en GCS -- verbatim de Miguel Ángel.

**6. Reparación del backlog dejado por el bug** (`f5f4120` + ejecución
real): comando `repair_reverted_quarantine_relocations` -- reaplica,
sin volver a llamar a Gemini, la última decisión (`ACTION_RELOCATED`/
`ACTION_TRASHED`) ya registrada en el historial de cada archivo que
seguía en cuarentena. Ejecutado en producción: 48 de 585 pendientes
reparados de golpe (confirmado con el contador real: 585 → 537).

**7. Creación automática de trabajadores nuevos, con detección de
posible error de DNI** (`ec8ce3f`): a raíz de un caso real (contrato
de un trabajador cuyo DNI/NIE no coincidía con nadie sembrado).
`resolve_or_create_person_identity()`: primero compara el nombre
completo contra todas las identidades existentes (sospecha de error
de lectura si coincide con un DNI distinto, nunca crea un duplicado);
si tampoco coincide con nadie, crea la identidad real, aterriza en
`DOC. PERSONAL/PERSONAL/PTE CONTRATACION/{apellidos, nombre}`
(categoría de aterrizaje confirmada por Miguel Ángel -- ninguna de las
13 categorías reales se puede inferir de forma fiable solo del
documento).

**8. Precisión del diseño de "no conformes" (3.14), con corrección
del propio Miguel Ángel sobre su primera aproximación** (`ad8e393`,
`4fd70d4`): responde a la pregunta real de por qué la cola no bajaba
como se esperaba -- hoy no hay ninguna marca de "ya intentado antes",
un archivo sin resolver reentra en el lote para siempre. Diseño: sale
a "no conformes" (deja de coincidir con el prefijo de cuarentena, dejar
de reprocesarse), Miguel Ángel lo estudia para decidir si hace falta
un tipo nuevo, y la vuelta es un botón "Reencolar" sobre la propia
carpeta, disparado a mano **sin ninguna relación con el estado de la
cola** -- Miguel Ángel corrigió expresamente su propia primera
redacción ("cuando cuarentena esté vacía"), el único motivo de que sea
manual es no gastar Gemini en documentos que van a volver a fallar si
no se ha creado antes el tipo que les falta. **Asignado a H29** en el
cierre de esta sesión (antes sin hito), pendiente de construir.

### COMPLETADAS EN S042

Sesión larguísima -- 28 commits, la más extensa de H29 hasta la
fecha. Empezó terminando "No Conformes" (decisión 3.14, punto 1 de la
hoja de ruta de S041) y acabó reescribiendo capas enteras del
consumidor de cuarentena tras encontrar, con datos reales y nunca
supuestos, varias causas raíz que llevaban arrastrándose desde antes
de esta sesión -- la más grave, un ciclo infinito de 142 pasadas de
reclasificación sobre un único archivo. Patrón que se repite todo el
día, más marcado que en sesiones anteriores: Miguel Ángel corrigió
varias veces el rumbo en caliente ("no podemos nosotros borrar
nada... dotar al sistema de las herramientas pertinentes para que lo
haga de forma automática", repetido tras cada intento de resolver algo
a mano), y cada vez que un dato no encajaba se persiguió hasta el
código real en vez de darlo por bueno (directriz 4.9) -- incluida una
autocorrección propia a media sesión al confirmar que una regla que
Miguel Ángel ya había pedido dos veces ("hasta 4 páginas entero, más
de 4 recorte a extremos") solo se había aplicado a medias.

**1. No Conformes construido de verdad** (`370b6b3` a `002d6c6`,
cierra decisión 3.14 / punto 1 de S041): carpeta real con anotación
del supervisor para Gemini, reencolado (con incidente real de
selección vacía cayendo en "reencolar todo" corregido dos veces,
`ffabb93`/`1b3835f`), `MANUAL_USO` enrutado directo sin depender de
resolución de máquina, XPS convertido con `fitz` (`soffice` confirmado
sin filtro de importación para XPS), contador de seleccionados.

**2. Simplificación radical de la interfaz de selección** (`a23deac`,
`0499d39`): a petición explícita de Miguel Ángel, un único casillero
por archivo y un único "Seleccionar todo" alimentan los cuatro botones
de acción (Mover, Clasificar, Reencolar, Eliminar) -- sustituye por
completo al sistema de dos casilleros paralelos que generaba
ambigüedad real. El propio botón "Reencolar todo" se retiró después,
por decisión del propio Miguel Ángel revocando su propia petición
anterior una vez el arreglo de paginación (ver punto 4) lo volvió
redundante: "no nos podemos agarrar a un clavo ardiendo... se cambia
si es para mejorar."

**3. "Seleccionar todo" se quedaba corto por el scroll infinito**
(`123d74a`): incidente real -- una carpeta con más de `PAGE_SIZE=200`
archivos marcaba solo lo ya cargado en el DOM, nunca el resto. Ahora
carga todas las páginas restantes antes de marcar.

**4. Recorte de PDF: de "solo primeras páginas" a "principio + final",
y de "reacción a errores" a "regla general para todo PDF, siempre"**
(`b7d99a8`, `562f8da`, `2d1662b`): tres pasos reales, no uno solo.
Primero, reintento en 504/DEADLINE_EXCEEDED (antes solo 429) y recorte
reactivo al 400 de límite de páginas de Vertex AI. Segundo, a
propuesta de Miguel Ángel tras revisar una muestra real de 20 dosieres
(solo 3 de 20 cabían en 3 páginas, 176 el máximo), el recorte pasó de
"primeras N páginas" a "primeras 2 + últimas 2" -- mejor señal de
dosier, con aviso explícito a Gemini de que el extracto no es
contiguo. Tercero, y el más caro: un manual real de 979 páginas (979
imágenes escaneadas, 0 texto, confirmado con `fitz` antes de suponer
nada) fallaba igual pese a pesar poco y tener menos de 1000 páginas --
huérfano de los dos disparadores existentes. Corrección de fondo,
verbatim de Miguel Ángel repetida con frustración real ante el fallo:
el número de páginas se cuenta SIEMPRE, para cualquier PDF, antes de
la primera llamada -- ya no se espera a que falle nada.

**5. Máquinas y personal ya no bloquean la clasificación por falta de
datos** (`4642de5`, `ffb7919`): `resolve_or_create_machine_asset()`
crea la máquina en `fleet.MachineAsset` sola cuando la carpeta nombra
un código de flota real sin match -- confirmado con datos reales que
`company` (FK a `ivr_config.Company`) nunca es ambiguo (una única fila
en toda la plataforma), la ambigüedad real vive en `company_code`/
`company_name`, con "GRA" como cajón por defecto explícito de Miguel
Ángel. Aparte, dos fallos reales de coincidencia de DNI (cero espurio
delante, dígito mal leído rompiendo la letra de control antes de
llegar a la salvaguarda de "nombre coincide con DNI distinto" de
S041) corregidos en `_normalize_dni()`/
`resolve_or_create_person_identity()`.

**6. Causa raíz real de la deriva negativa de `total_size_bytes`**
(`fdbbad4`, `645ff27`, `01bc79b`): tres capas del mismo síntoma.
Primero, comando `recalculate_folder_counters` como parche puntual
(946 carpetas desajustadas, 318 en negativo). Segundo,
`quarantine_scope_q()` -- archivos sueltos en la raíz de `_CUARENTENA`
invisibles para "en cola" por comparar por `startswith` en vez de
incluir la igualdad exacta. Tercero, y el real: `persist_rows()` (la
tarea horaria de red de seguridad) creaba archivos nuevos sin sumar su
tamaño a las carpetas antecesoras -- corregido de raíz, no solo
parcheado otra vez.

**7. Catálogo ampliado con datos reales, nunca supuestos**
(`162d07b`, `c1e1865`): 5 tipos nuevos (`RECIBO_LEASING`, `PRESTAMO`,
`PROFORMA`, `SOLICITUD_ADMINISTRATIVA`, `EXCEDENCIA`) confirmados uno
a uno contra el razonamiento real de Gemini ya guardado en el
historial, más filtros de búsqueda/dominio/estado en el CRUD.

**8. Herramientas de archivos comprimidos, de cero a automáticas**
(`307170f`, `69b99a4`, `e223c17`): visor de `.zip`/`.rar` en el
explorador (`unrar` confirmado ya instalado en el servidor antes de
escribir una sola línea, ningún paquete nuevo), y
`resolve_archive_redundancy()` -- borrado automático de un archivo
comprimido cuando el 100% de su contenido ya existe archivado por
separado (CRC32C real vía `google-crc32c`, ya dependencia transitiva,
confirmado que coincide exactamente con el de GCS). Deuda técnica
registrada aparte (sección 9): extraer y subir contenido genuinamente
nuevo de dentro de un comprimido es una pieza mayor, deliberadamente
fuera de alcance.

**9. Borrado automático generalizado, sin decisión humana**
(`e54dcd0`, `04fea9c`): a petición explícita y repetida de Miguel
Ángel ("no podemos nosotros borrar nada... dotar al sistema"),
`is_empty_file()` (0 bytes, confirmado con `pru4eba.docx`) y
`resolve_duplicate_of_filed_document()` (mismo CRC32C+tamaño que un
archivo ya archivado fuera de cuarentena) se ejecutan siempre ANTES de
Gemini, coste cero, con `trash_dossier_entry()` reutilizado sin
mecanismo nuevo.

**10. Causa raíz real de un ciclo de 142 pasadas** (`a64414b`, el
hallazgo más caro de la sesión): `A-69 Leasing BBVA.pdf` tenía dos
filas vivas con el mismo CRC32C y tamaño -- una ya archivada, otra
dando vueltas por cuarentena desde el 4 de agosto sin resolver ni una
sola vez pese a que Gemini identificaba tipo y dominio con confianza
ALTA casi siempre. Causa real: `RequeueNoConformesView` movía SIEMPRE
a la raíz plana de `_CUARENTENA`, nunca a la subcarpeta original --
sin ningún segmento de carpeta con forma de código de flota que
escanear, la resolución de máquina nunca tenía de dónde tirar, y el
propio reencolado siguiente destruía otra vez el contexto que la
próxima pasada necesitaba. Corregido restaurando la carpeta mirror
real desde `entry.blob_name` (nunca cambia, 4.12) en vez de la raíz
plana.

**11. Historial auditable para la papelera en bloque** (`f784393`):
`BulkTrashView` ahora escribe un `DataOperationLog`/entries reales,
mismo patrón que el resto de operaciones -- antes marcaba
`deleted_at` sin dejar ningún rastro.

**Incidente de infraestructura ajeno al proyecto:** avería real de
GitHub Actions (confirmada contra `githubstatus.com`, "Partial
Outage" desde las 15:22 UTC) bloqueó un despliegue durante ~45
minutos: cancelado dos veces, resuelto relanzando el run por API en
cuanto GitHub mitigó. Ningún commit se perdió; el código nunca dejó
de estar a salvo en GitHub.

### Hoja de ruta para la siguiente sesión (S043)

**Pregunta explícita a Miguel Ángel** (regla de contador de arrastre
2.2 -- este ítem lleva sin ejecución real desde S040, tres sesiones
consecutivas: S040, S041 y esta): la consolidación de cubos (retirar
`machine_documents`/`personal_documents`, decisión 3.12) sigue sin
tocarse. ¿Qué falta exactamente para poder abordarlo, o ha dejado de
ser prioritario frente al resto de H29?

1. **Verificación de arranque obligatoria** (criterio de cierre
   objetivo, regla 2.1): al empezar la sesión, comprobar con Comando S
   cuántos archivos quedan en `_CUARENTENA` de los 139 reencolados al
   cierre de S042 (0 en No Conformes en ese momento) -- con todos los
   arreglos de hoy (raíz plana, duplicados, DNI, máquinas nuevas,
   recorte universal de páginas) el número EN COLA debe bajar de
   forma sostenida pasada tras pasada, nunca estancarse ni volver a
   subir. Si algún archivo concreto vuelve a No Conformes pese a los
   arreglos de hoy, diagnosticar con datos reales antes de suponer
   nada -- puede ser un caso genuinamente nuevo, no necesariamente el
   mismo patrón.
2. **Deuda técnica registrada en la sección 9** (extraer y subir a
   GCS el contenido genuinamente nuevo de dentro de un `.zip`/`.rar`
   cuando no es 100% redundante): sigue pendiente de diseño propio,
   explícitamente fuera de alcance de S042.
3. **Heurística por nombre de archivo para `.zip`/`.rar` cuando el
   contenido SÍ es nuevo** (petición original de Miguel Ángel, motivo
   de construir el visor): con la comprobación de redundancia ya
   automática, este punto queda acotado a los comprimidos que
   contienen contenido genuinamente nuevo -- decidir si aplica una
   heurística por nombre (ej. "MANUAL" en el nombre → tipo MANUAL_USO
   por defecto) o si depende directamente de la deuda técnica del
   punto 2.
4. **Documentación de utillaje/equipo de taller compartido** (patrón
   real confirmado dos veces esta sesión: `Certificado GATOS
   MANUALES.pdf` y `Manual eslinga cable acero.pdf`, ambos "catálogo
   general... no un documento específico de una máquina de la
   flota"): no existe hoy ningún tratamiento para documentación que
   no pertenece a ninguna máquina concreta. Decidir con Miguel Ángel
   si necesita su propio dominio/tipo, o una carpeta fija al estilo
   `MANUAL_USO`.
5. **Modelo 145 y "dos en uno" del mismo tipo repetido para varias
   personas** (3.31): sigue sin decisión tomada -- el mecanismo de
   `is_dossier` (S041) exige tipos catalogados *distintos*, no cubre
   este caso.
6. **Revisar las 34 discrepancias reales de `audit_manual_models`**
   una a una con Miguel Ángel, y decidir el criterio de deduplicación
   para los 119 archivos que son candidatos reales a consolidar en un
   único manual por modelo -- antes de tocar `fleet.MachineAsset` en
   producción.
7. **Subida tipada desde gestión de documentación** (decisión 3.8):
   depende de la consolidación de cubos (ver pregunta explícita
   arriba).
8. **Herramienta de "carpetas vacías"**: limpiar las filas huérfanas
   que deja mover/reubicar archivos fuera de una carpeta sin vaciarla
   del índice.
9. **Buzón de documentación / "la vuelta"** (resto de la decisión
   3.14 -- la parte del agente H28, distinta de "no conformes"):
   modificación pendiente del agente H28 para reportar la carpeta de
   origen local.
10. **Migración de Python 3.10 → 3.12/3.13** antes del 4 de octubre de
    2026 -- sigue sin tocarse, ya varias sesiones.
11. **Salto de HTMX 1.9.12 a la serie 2.x**: anotado, sin evaluar.
12. **Frontera con H28** (si la interfaz de limpieza de la Fase 2
    converge con el explorador): sigue sin cerrar.

**Cabo suelto menor, arrastrado ya varias sesiones, no bloqueante:**
las cuatro copias de estáticos desincronizadas de su fuente
(`panel/css/panel.css`, `panel/js/admin_history.js`,
`panel/js/form_entry_assets.js`, `panel/js/form_entry_modal.js`).

---

## 8. Incidencia real fuera de alcance, corregida en S038 (directriz 4.9)

Reportada por Pablo durante la sesión: el activo `A59` (Grúa móvil
Liebherr LTM 1230-5.1, `GRUAS ADOLFO ALVAREZ, S.L.`, pk=78) no dejaba
cerrar un parte que lo referenciaba — error "no existe" pese a que el
código está en BD, activo, y visible en el desplegable.

**Causa raíz confirmada con datos reales** (no supuesta): `A59` tenía
`brand_model=""` en BD. El desplegable compone el label como
`código + " — " + brand_model`; con `brand_model` vacío queda
`"A59 —"` sin nada detrás del guion. `machine_raw` pierde cualquier
espacio final por el `.strip()` aplicado al leerlo del POST. La
Pasada 3 de resolución de máquina en `_parse_entry_lines_from_post`
(`panel/views_operator.py`) exigía `\s+` (una o más espacios) tras el
guion largo/corto, lo que nunca casaba sin texto detrás — y las
Pasadas 1, 2 y 4 tampoco resuelven en ese caso. Resultado:
`machine_asset` quedaba `None` y el cierre fallaba.

**Bug genérico, no exclusivo de A59** — afecta a cualquier activo con
`brand_model` vacío.

**Corrección de código** (commit `fdc546e`, desplegado y verificado
en Actions — `git pull + migrate + collectstatic` y recarga de la
webapp con conclusión `success`, no solo el icono verde): cambiado
`\s+` por `\s*` tras el guion en la Pasada 3. Verificado con los
cuatro casos reales (con y sin espacio final, con y sin descripción)
antes de comitear.

**Corrección de dato provisional** (pk=78): `brand_model` rellenado a
`"LIEBHERR LTM 1230-5.1"` — únicamente para desbloquear el cierre de
partes ya. Verbatim de Miguel Ángel: *"pon el valor que nos está
molestando y cuando acabemos con el hito 29 tendrá su verdadero valor
cada campo"*, y aclarado después: *"ahora es la descripción de la
máquina, para que se puedan cerrar los partes, el resto de datos,
cuando terminemos con la documentación se pondrán justamente los
suyos sacados de la documentación real"*.

**`chassis_number` y `plate` de A59, NO tocados, pendientes de H28:**
- `chassis_number` = `"LIEBHERR LTM1230"` — texto de marca/modelo, no
  un número de bastidor.
- `plate` = `"E-5068-BHH WLFA54CZ2LEZZ0299"` — parece matrícula
  española (`E-5068-BHH`) y VIN de 17 caracteres
  (`WLFA54CZ2LEZZ0299`) concatenados en el mismo campo.
- Miguel Ángel ha localizado documentación real en GCS con datos de
  fábrica (tipo `LTM 1230-5.1`, n.º de serie de fábrica `094190`) que
  no necesariamente coincide con el VIN del chasis portante — una
  grúa automotriz tiene identificador propio de grúa e identificador
  de vehículo portante, son cosas distintas. **No asumir cuál va en
  cada campo sin confirmación explícita cuando se aborde.**
- Indicio de un desplazamiento de columnas en la importación original
  del catálogo de este activo concreto (`fleet/management/commands/
  import_machine_catalog.py`, H23) — a revisar si se repite en otros
  activos cuando se aborde la documentación real en H28, sin asumir
  que es un caso aislado.

## 9. Deuda técnica pendiente, explícitamente registrada (S042)

Miguel Ángel, verbatim, tras confirmar el alcance de la primera mitad
de esta pieza: *"Ok, pero que no caiga en saco roto, esta deuda
técnica debe ser resuelta."*

**Construido en S042:** `resolve_archive_redundancy()`
(`classification_service.py`) detecta cuando un `.zip`/`.rar` de
cuarentena es 100% redundante — cada entrada de dentro coincide, byte
a byte (CRC32C real + tamaño, `archive_service.compute_crc32c()`),
con un archivo ya archivado fuera de cuarentena/No Conformes — y lo
borra solo, sin decisión humana, vía la papelera automática ya
existente (`trash_dossier_entry()`). Corre antes que Gemini, nunca
llega a intentar leer bytes comprimidos.

**NO construido, deliberadamente fuera de alcance de S042 — esta es
la deuda pendiente:** cuando un `.zip`/`.rar` de cuarentena trae
contenido que **no** existe ya archivado en ningún sitio (el caso
contrario al redundante), el sistema hoy se limita a dejarlo en No
Conformes con una nota indicando cuántas entradas coincidieron y
cuántas son nuevas — nadie extrae ni sube nada todavía.

**Por qué se dejó aparte y no se resolvió en la misma sesión:**
extraer contenido nuevo de dentro de un archivo comprimido y
archivarlo de verdad exige **escribir objetos nuevos en GCS** — subir
bytes reales a la nube, con su propio `blob_name`, su propia entrada
en el índice, y solo entonces pasar por clasificación normal. Es una
categoría de operación distinta a todo lo construido hasta ahora en
H29 (mover, renombrar, borrar lógicamente, crear filas de índice —
todo son escrituras de base de datos puras, `blob_name` nunca se toca,
4.12). Escribir en GCS de verdad merece su propio diseño explícito
(¿qué nombre de blob se le da al extraído? ¿en qué carpeta aterriza
antes de clasificar — cuarentena, directamente en su destino final si
se puede inferir? ¿qué pasa con el `.zip`/`.rar` original una vez
extraído su contenido nuevo, se borra, se conserva?) — no algo que
deba decidirse sobre la marcha como efecto colateral de otra pieza.

**Pendiente para una sesión dedicada:** diseñar y construir la
extracción + subida a GCS + indexación + clasificación normal del
contenido genuinamente nuevo de un archivo comprimido de cuarentena,
cerrando así el ciclo completo que empezó en S042 con la detección de
redundancia.
