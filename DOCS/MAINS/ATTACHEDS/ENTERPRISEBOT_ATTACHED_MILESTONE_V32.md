# Anexo H32 — Migraciones de Infraestructura (Modelo IA, Python, Registro Android)

---

## 1. Objetivo del Hito

Tres plazos externos reales, impuestos por terceros (Google/Vertex
AI, Google/PythonAnywhere, Google Play), convergen en
septiembre-octubre de 2026. Ninguno depende de decisiones de negocio
de Grupo Álvarez -- son fechas de corte técnicas que hay que cumplir
sí o sí. Se abre como hito propio (S92) en vez de colarse como
desvíos sueltos dentro de H30/H31, porque el volumen de auditoría
necesario (sobre todo el del modelo de IA) no está acotado todavía.

---

## 2. Contexto Técnico

### 2.1. Migración `gemini-2.5-flash` → `gemini-3.5-flash`

**CERRADA en S93.** Auditoría completa (`grep -rln` sobre todo el
árbol, no solo `.py`) y migración de las 5 líneas de código reales
encontradas -- ver sección "COMPLETADAS EN S93" para el detalle y el
commit. Sección conservada aquí solo por los plazos reales, que
siguen siendo relevantes hasta que Punto 3 (validación en producción)
se cierre:

**Plazos reales (verificados en línea en S001-H10, re-verificar si ha
pasado más de una semana antes de dar por buena la fecha):**
- Bloqueo de acceso a inferencia online **nueva**: ~16 de septiembre
  de 2026.
- Apagado total (`gemini-2.5-pro`, `gemini-2.5-flash`,
  `gemini-2.5-flash-lite`): 16 de octubre de 2026.
- Fuera de alcance de esta migración: `gemini-live-2.5-flash-native-audio`
  (Live API, voz/IVR) -- ciclo de vida propio, no asumir equivalencia
  automática con `gemini-3.5-flash`.

**Pendiente real, único punto abierto de este bloque:** validación en
producción con datos reales (Punto 3 de la hoja de ruta de S93, más
abajo) -- requiere que Miguel Ángel genere un caso real de Vision (un
parte de trabajo PDF) y uno de clasificación de texto (una descripción
de avería real por WhatsApp).

### 2.2. Migración de versión de Python en PythonAnywhere

**CERRADA en S93, ejecutada de principio a fin en la misma sesión** en
la que se investigó (no quedó para S94 como estaba previsto -- hubo
tiempo real de sobra tras cerrar el bloque Gemini). Ver sección
"COMPLETADAS EN S93" para el detalle completo, la incidencia real de
las tareas Always On, y los comandos ejecutados. Sección conservada
aquí solo como referencia de los plazos y la decisión de versión:

`google.api_core` deja de dar soporte a Python 3.10 a partir del **4
de octubre de 2026** (correo real de Google/PythonAnywhere ya
recibido por Miguel Ángel, con el detalle) -- confirmado también en
línea en S93 (issue real de `googleapis/google-cloud-python`, aviso
`FutureWarning` de `google.api_core._python_version_support` citando
la misma fecha 2026-10-04 y recomendando mínimo Python 3.11).

**Versión objetivo elegida y ya en producción: Python 3.12.8**, sobre
la imagen de sistema `innit` (Ubuntu 22.04). Cuenta migrada desde la
imagen `haggis` (Ubuntu 20.04, máximo 3.10) -- ver incidencia real de
S93 sobre la disponibilidad de versiones según imagen de sistema,
documentada en `com-environment-management` sección 4.2.

**Pendiente real, menor, sin fecha límite:** el venv antiguo
`EnterpriseBot_venv` (Python 3.10.5) sigue existiendo en el servidor,
ya sin ningún proceso apuntándolo (webapp, bridge de voz y worker
Celery migrados). Se puede borrar con `rmvirtualenv EnterpriseBot_venv`
en cualquier momento futuro sin urgencia -- conservarlo unos días como
red de seguridad no cuesta nada.

### 2.3. Registro de apps Android en Google Play Console

⛔ **CORREGIDO EN S93 -- alcance mal acotado en S92.** La redacción
original de esta sección evaluaba solo si **EnterpriseBot** tenía una
app Android nativa propia (no la tiene, sigue sin empezar) y concluía
"sin acción posible" -- pero el correo real de Google
(`android-developer-console-noreply@google.com`, recibido
2026-09-01, confirmado por Miguel Ángel en S93 con el texto íntegro)
no habla de un proyecto concreto: exige registrar **nombre de
paquete y clave de firma de todas las apps que Miguel Ángel
distribuye como desarrollador**, verificando su identidad, antes del
**30 de septiembre de 2026** ("Starting September 30, 2026, Android
apps from participating stores in select countries must be
registered to a developer with a verified identity in order to be
installed on certified Android devices").

**Acción real pendiente, sin relación con el código de EnterpriseBot:**
Miguel Ángel tiene dos apps Android reales fuera de este proyecto --
**miMoo** y **AperturasAjedrez** -- que si están distribuidas en
tiendas participantes necesitan su nombre de paquete y clave de firma
registrados en el Android Developer Console antes de esa fecha, o
identidad de desarrollador verificada si no lo está ya.

**Esto no se gestiona desde este repositorio ni desde ninguna skill
de código** -- es un trámite manual en el navegador, en la cuenta de
Google de Miguel Ángel (Play Console / Android Developer Console),
con datos (claves de firma) que solo existen en sus propios keystores
locales, fuera del alcance de cualquier `git`/Comando S. Seguimiento:
Miguel Ángel confirma en una próxima sesión si ya completó el
registro de las dos apps, o si necesita ayuda puntual con algún paso
concreto (p. ej. extraer la huella SHA de una keystore local para
pegarla en el formulario del Developer Console, que sí es una tarea
técnica que se puede ayudar a resolver).

Independientemente de esto, para EnterpriseBot en sí sigue sin haber
ninguna app Android nativa construida (la app de albaranes para
tablets de operarios, en Kotlin, offline, sigue solo anotada como
alcance futuro, sin empezar) -- ese punto del hito, tal como estaba
descrito originalmente, sigue siendo correcto y sin acción posible.

---

## 3. COMPLETADAS EN S92

Hito abierto en esta misma sesión (PCH desde H30, tras cerrar el
dominio PERSONAL al 100%). Sin trabajo de código todavía sobre las
migraciones en sí -- el bloque de trabajo de S92 fue íntegramente el
cierre de H30/PERSONAL (ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md`)
y la creación de este hito (documento maestro, enrutador, este mismo
anexo).

## 3.1. COMPLETADAS EN S93

**Punto 1 -- Auditoría completa cerrada.** `grep -rln` sobre todo el
árbol del clon (no solo `.py`) de `gemini-2.5-flash`/`gemini-2.5-pro`.
Solo 5 líneas de código real en 3 archivos pendientes de migrar:
`file_organizer/organizer_probe.py:34`, `whatsapp/services.py:170`,
`whatsapp/services.py:1298`, `whatsapp/services.py:1744`,
`work_order_processor/services.py:123`. El resto de coincidencias
(`work_order_processor/tasks.py`, `spare_parts/services.py`,
`ai_services/gemini_client.py`) eran comentarios/docstrings, no
constantes funcionales -- `document_explorer/date_verification_service.py`
y `ai_services/gemini_rate_limiter.py`, citados como candidatos en la
sección 2.1 original, **ya no aparecían** en el grep: ya resuelven a
`gemini-3.5-flash` vía `DEFAULT_MODEL` de `ai_services.gemini_client`,
sin que constara documentado en ningún sitio -- la migración real ya
había avanzado más de lo que registraba la lista parcial de S001-H10.

**Punto 2 -- Migración cerrada.** Las 5 líneas migradas a
`gemini-3.5-flash`, `py_compile` en verde tras cada cambio.
Verificado en línea antes de migrar (búsqueda "gemini-3.5-flash
Vertex AI response format changes"): ninguno de los 5 puntos usa
segmentación de imagen (no soportada en Gemini 3.x, hay que seguir
usando 2.5 Flash con thinking apagado para eso) ni `candidate_count`
(retirado en Gemini 3.x) -- `thinking_budget=0`, usado en
`work_order_processor/services.py` (2 llamadas), sigue soportado por
compatibilidad hacia atrás. Comentarios desactualizados que citaban la
deuda como pendiente, actualizados en el mismo bloque
(`work_order_processor/tasks.py`, `ai_services/gemini_client.py`,
`spare_parts/services.py`). Commit `253a057`, push a `main`, Action
"Deploy EnterpriseBot to PythonAnywhere" en `success` (sin migración
de modelo Django en este bloque, conclusion suficiente).

**Punto 4 -- CERRADO en la misma sesión, ejecución completa.**
Investigación (versión objetivo 3.12) más ejecución real de principio
a fin, sin quedar para S94:

1. Confirmado con Comando S que la cuenta estaba en imagen `haggis`
   (Ubuntu 20.04, Python 3.6-3.10) -- descartó de raíz el atajo que
   sugería la skill `com-environment-management` (mkvirtualenv directo
   sin cambiar de imagen), verificado como falso para esta cuenta con
   una prueba real (`RuntimeError: failed to find interpreter for
   python3.12`). Skill corregida en el propio turno.
2. Miguel Ángel cambió la imagen de sistema a `innit` (Ubuntu 22.04)
   desde el dashboard -- acción de navegador, autoservicio. Confirmado
   con Comando S: `/usr/bin/python3.12` disponible tras el cambio.
3. `pip freeze` de referencia del venv antiguo guardado como red de
   seguridad antes del cambio (`EnterpriseBot_003_GET.txt`).
4. `mkvirtualenv EnterpriseBot_venv_py312 --python=python3.12`,
   `pip-tools` instalado, `pip-compile requirements.in` regenerado en
   el intérprete nuevo. Comprobación de coherencia `.in`/`.txt`
   (`com-environment-management` sección 7.3) limpia antes de
   `pip-sync` -- 31 declaradas, 142 fijadas, ninguna faltante.
5. `pip-sync requirements.txt` limpio. Verificado explícitamente que
   los paquetes con extensión C compilada (`mysqlclient`, `PyMuPDF`,
   `pymupdf4llm`, `onnxruntime`, `weasyprint`) importan sin error en
   3.12 -- no solo que `pip-sync` terminara sin fallos.
6. Webapp: cambiado el campo "Virtualenv" y la versión de Python de la
   pestaña "Web" (dos ajustes independientes, hay que igualar los
   dos). Verificado con datos reales, no con ausencia de errores:
   `server.log` mostró `Python version: 3.12.8` y `PEP 405 virtualenv
   detected: EnterpriseBot_venv_py312` en el arranque de los 3 workers
   uWSGI tras el reload.
7. **Incidencia real -- tareas Always On con contenedor "pegado" al
   sistema de archivos antiguo tras el cambio de imagen.** Tanto el
   bridge de voz como el worker Celery, tras editar su comando/script
   para apuntar al venv nuevo y pararlos/arrancarlos desde el
   dashboard, siguieron fallando en bucle real (`bash: .../bin/python:
   No such file or directory` / `exec: python: not found`) durante más
   de 15 minutos, **pese a que el mismo binario, en la misma ruta,
   funcionaba sin problema desde una consola Bash nueva y desde la
   propia webapp** (confirmado en paralelo). La solución real, no
   documentada en ningún sitio oficial de PythonAnywhere que se haya
   encontrado, fue **borrar la tarea Always On por completo y
   recrearla desde cero** con el mismo comando -- parar/arrancar o
   solo editar el comando no basta, el contenedor de la tarea necesita
   reaprovisionarse. Regla derivada para cualquier migración futura de
   imagen de sistema: si una tarea Always On sigue fallando con un
   binario que se ha verificado real y funcional, borrar y recrear la
   tarea antes de escalar a soporte.
8. `start_celery_worker.sh` corregido (línea `source .../activate`
   apuntando al venv nuevo), commit `7ae950f`. Bridge de voz: comando
   de la tarea editado directamente en el dashboard (no hay archivo de
   código que lo referencie). Script de inicio de consola
   (`SYSTEM_DOCS/CONSOLE_INIT_COMMAND_ENTERPRISEBOT.md`, fuera del
   repositorio Git) también corregido con `sed`, mismo criterio.
9. Verificación final con datos reales, no con silencio del log: el
   `bridge.log` mostró `[READY] Puente HÍBRIDO (aiohttp) activo en
   puerto 8081` sin error tras el reinicio, y el log del worker Celery
   mostró el árbol de 18 tareas registradas, Beat disparando el
   schedule, y la ruta `EnterpriseBot_venv_py312` en el único warning
   real (`DuplicateNodenameWarning`, de un worker de otro proyecto
   compartiendo el mismo broker Redis, no relevante aquí).

**Pendiente real, menor, sin fecha límite:** borrar el venv antiguo
`EnterpriseBot_venv` cuando Miguel Ángel lo considere oportuno.

**Punto 3 -- Sin cerrar, requiere acción de Miguel Ángel** fuera del
alcance de esta sesión de chat: generar un caso real de Vision (parte
de trabajo PDF) y uno de clasificación de texto (descripción de
avería real por WhatsApp) en producción, ya con `gemini-3.5-flash`
activo tras el despliegue del Punto 2.

---

## 4. Hoja de Ruta para la Sesión Siguiente (S94)

Ejecución estrictamente secuencial, sin preguntar por dónde empezar.

**Punto 1 -- Validar el Punto 3 del bloque Gemini** (sección 2.1) si
Miguel Ángel ya generó los casos reales de Vision/texto -- confirmar
formato de respuesta de `gemini-3.5-flash` en producción antes de dar
la migración del modelo por completamente cerrada. Si todavía no hay
casos reales disponibles, dejarlo abierto y no bloquear el resto de
la sesión por ello.

**Punto 2 -- Google Play Console: seguimiento, no acción de código.**
Ver sección 2.3, corregida en S93 -- preguntar a Miguel Ángel si ya
registró **miMoo** y **AperturasAjedrez** en el Android Developer
Console antes del 30 de septiembre de 2026. Solo intervenir si pide
ayuda con un paso técnico puntual (p. ej. extraer una huella SHA de
una keystore local); el registro en sí es un trámite manual suyo, no
un punto de la hoja de ruta de EnterpriseBot.

**Con Puntos 1 y 2 resueltos o parqueados, H32 queda íntegramente
cerrado** (los tres plazos del objetivo del hito atendidos: Gemini
migrado y desplegado, Python migrado y verificado en los tres procesos
de producción, Google Play sin acción posible todavía). Momento de
proponer a Miguel Ángel retomar H30 (dominio MÁQUINAS, pausado desde
S92) o H31 (Interfaz de Ficha de Personal, pausado desde S77) como
siguiente hito EN PROGRESO -- ver PCH.
